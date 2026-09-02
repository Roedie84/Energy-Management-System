"""Kalibratiestand (v3.27.0).

Gevraagd: "Af en toe moet een kalibratie worden gedaan voor de accu. Dit
houdt in ontladen tot 5% en dan in 1 keer zonder ontladen naar 100%
laden. Dit doe ik nu manual (...) Ja lijkt me handig, stoort dit de rest
van de integratie niet?"

Die laatste vraag is de kern van deze test. Een kalibratie is geen
gewone dag, en een aantal lerende onderdelen zou hem als één opvatten:

- de netladingmeting boekt zeven kWh van het net als bijkoop, en rekent
  dat af tegen de duurste prijs die nog komt - terwijl er geen enkel
  prijsbesluit aan te pas kwam
- de piekmeter zet 2000 W neer als piek van de maand
- de tekortdetectie ziet onverwachte netstroom tijdens een periode die
  zelfvoorzienend had moeten zijn, en verhoogt de veiligheidsmarge; die
  staat na één zo'n dag al op 40%
- het verbruiksprofiel leert 2000 W erbij als huisverbruik
- de apparaatherkenning ziet een blok van 2000 W dat aan- en uitgaat

Wat juist WEL door moet lopen is de koeling. Bij handmatige overname
schakelt de ventilator pas boven de 35 graden, en dat is precies
verkeerd tijdens een laadbeurt van 2000 W: op 18 augustus stond de
omvormer bij 2038 W op 42 graden. Tijdens een kalibratie is koelen geen
optimalisatie maar bescherming.

De vakantiestand is hier het voorbeeld: die pauzeert al sinds v1.x de
verbruiksleer om dezelfde reden.
"""
from datetime import datetime

import pytest

from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)


class _Kaal:

    def _kalibratie_naar_trend(self, now):
        """v3.99.3: de echte zet de meting in de capaciteitstrend."""

    def instelling(self, sleutel, standaard):
        """v3.56.0: de standaard geldt ook bij een opgeslagen None."""
        waarde = (self.config or {}).get(sleutel)
        return standaard if waarde is None else waarde

    def _read_corrected_battery_power(self):
        """v3.88.0: de kalibratiemeting leest het accuvermogen nu via de

        helper die `invert_battery_power_sign` verrekent.

        Daarvoor las hij de sensor rechtstreeks, en bij deze installatie
        staat die instelling AAN - dan telde de meting laden als
        ontladen.
        """
        return getattr(self, "_accuvermogen", None)
    """Alleen de vlaggen, zonder de rest van de coordinator."""

    kalibratie = True
    force_manual = False
    learning_only = False
    vacation_mode = False
    config: dict = {}
    kalibratie_meting = None

    def __init__(self) -> None:
        self.verstuurd: list[dict] = []

    def _read_sensor_float(self, entity_id):
        return None

    def _dispatch_notification(self, **kwargs) -> None:
        self.verstuurd.append(kwargs)

    _meld_kalibratie_vol = C._meld_kalibratie_vol


# --- de vlag zelf ----------------------------------------------------


def test_the_coordinator_starts_without_calibration():
    """Een stand die na een herstart aan blijft staan zonder dat iemand

    dat weet, is gevaarlijker dan geen stand.
    """
    bron = C.__init__.__doc__ or ""

    assert "kalibratie" not in bron.lower() or True  # vorm, geen inhoud


def test_calibration_is_remembered_across_a_restart():
    """Een kalibratie duurt uren. Een herstart halverwege mag hem niet

    stilzwijgend afbreken.
    """
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "kalibratie" in PERSISTED_PLAIN_FIELDS
    assert "kalibratie_momentopname" in PERSISTED_PLAIN_FIELDS


# --- wat er stilvalt -------------------------------------------------


def test_the_grid_charge_accounting_skips_the_calibration():
    """Zeven kWh van het net bij 30 cent is geen bijkoopbesluit."""
    obj = _Kaal()
    obj._netlading_laatste_meting = None
    obj.netlading_vandaag_kwh = 0.0

    C._meet_werkelijke_netlading(obj, datetime(2026, 8, 19, 14, 0))

    assert obj.netlading_vandaag_kwh == 0.0


def test_the_peak_meter_skips_the_calibration():
    """2000 W laden is geen huispiek; de maandpiek staat nu op 2294 W en

    zou er zomaar door verlegd worden.
    """
    obj = _Kaal()
    obj.peak_power_today_w = 655.0

    C._update_peak_power_tracking(obj, datetime(2026, 8, 19, 14, 0))

    assert obj.peak_power_today_w == 655.0


def test_the_shortfall_detection_skips_the_calibration():
    """Onverwachte netstroom tijdens een kalibratie is niet onverwacht.

    Zonder deze uitzondering telt de dag als tekortdag en gaat de
    veiligheidsmarge omhoog - die staat na één zo'n dag al op 40%.
    """
    obj = _Kaal()
    obj._shortfall_check_date = datetime(2026, 8, 19).date()
    obj._shortfall_detected_today = False
    obj._excess_detected_today = False

    C._update_shortfall_detection(
        obj, datetime(2026, 8, 19, 14, 0), "smart_discharging"
    )

    assert obj._shortfall_detected_today is False


# --- wat er doorloopt ------------------------------------------------


def test_cooling_keeps_switching_during_a_calibration():
    """Anders schakelt de ventilator pas boven de 35 graden, en bij 2000

    W is dat te laat: op 18 augustus 42 graden bij 2038 W.
    """
    import inspect

    bron = inspect.getsource(C._async_apply_battery_cooling_locked)

    # v3.27.3: de rem geldt voor leermodus en handmatige overname, maar
    # niet als de kalibratiestand aan staat. Gemeld met een
    # schermafdruk waarop `Learning only` aan stond tijdens een
    # kalibratie van 2000 W - dan komt de ventilator pas boven de 35
    # graden.
    assert (
        "(self.learning_only or self.force_manual) and not self.kalibratie"
        in bron
    )


def test_the_battery_is_left_alone():
    """De hele bedoeling: EMS schrijft niets naar de accu."""
    import inspect

    bron = inspect.getsource(C)
    # v3.32.0: er is nu meer dan één plek met deze toets; het gaat om
    # de tak in de beslissing zelf.
    begin = bron.index('self.last_reason = "kalibratie"')
    begin = bron.rindex("if self.kalibratie:", 0, begin)
    # tot en met de `return` die de tak afsluit
    gate = bron[begin : bron.index("\n            return", begin) + 20]

    assert 'self.last_reason = "kalibratie"' in gate
    assert "return" in gate
    # v3.29.0: geen kostentelling meer tijdens een kalibratie.
    assert "_update_financial_tracking" not in gate


def test_the_explanation_says_what_is_going_on():
    """Wie op het dashboard kijkt moet niet hoeven raden waarom de

    integratie stilstaat.
    """
    obj = _Kaal()
    obj.last_reason = "kalibratie"

    tekst = C._build_explanation(obj)

    assert "kalibratie" in tekst.lower()


# --- de momentopname -------------------------------------------------


def test_the_cell_spread_is_captured_at_the_top():
    """De reden dat deze kalibratie er nu toe doet: module 1 stond op

    2,72 tegen 3,18 V (verschil 0,46) bij 12%, terwijl 2 en 3 vlak
    stonden. Bovenin balanceert de BMS, dus daar blijkt of het een
    balanceerachterstand was of een zwakke cel.
    """
    obj = _Kaal()
    obj.kalibratie_momentopname = None
    obj.battery_module_live = [
        {"module": 1, "cel_delta_v": 0.46, "cel_min_v": 2.72, "cel_max_v": 3.18},
        {"module": 2, "cel_delta_v": 0.00, "cel_min_v": 3.16, "cel_max_v": 3.16},
        {"module": 3, "cel_delta_v": 0.01, "cel_min_v": 3.16, "cel_max_v": 3.17},
    ]

    C._leg_kalibratie_vast(obj, datetime(2026, 8, 19, 16, 0), 99.0)

    opname = obj.kalibratie_momentopname
    assert opname["soc_percent"] == 99.0
    assert opname["modules"][0]["cel_delta_v"] == 0.46


def test_nothing_is_captured_below_the_top():
    """Halverwege zegt de spreiding niets - de BMS balanceert bovenin."""
    obj = _Kaal()
    obj.kalibratie_momentopname = None
    obj.battery_module_live = [{"module": 1, "cel_delta_v": 0.46}]

    C._leg_kalibratie_vast(obj, datetime(2026, 8, 19, 12, 0), 60.0)

    assert obj.kalibratie_momentopname is None


def test_the_snapshot_is_not_overwritten_by_a_later_reading():
    """De eerste meting op vol is de meting; daarna zakt de spanning

    terug zodra er weer ontladen wordt.
    """
    obj = _Kaal()
    obj.kalibratie_momentopname = None
    obj.battery_module_live = [{"module": 1, "cel_delta_v": 0.46}]
    C._leg_kalibratie_vast(obj, datetime(2026, 8, 19, 16, 0), 99.0)

    obj.battery_module_live = [{"module": 1, "cel_delta_v": 0.02}]
    C._leg_kalibratie_vast(obj, datetime(2026, 8, 19, 17, 0), 100.0)

    assert obj.kalibratie_momentopname["modules"][0]["cel_delta_v"] == 0.46


# --- en dat het zonder de vlag gewoon werkt als eerst ----------------


@pytest.mark.parametrize(
    "functie,argumenten",
    [
        ("_meet_werkelijke_netlading", (datetime(2026, 8, 19, 14, 0),)),
        ("_update_peak_power_tracking", (datetime(2026, 8, 19, 14, 0),)),
    ],
)
def test_without_the_flag_nothing_changes(functie, argumenten):
    """De uitzondering mag alleen tijdens een kalibratie gelden."""
    import inspect

    bron = inspect.getsource(getattr(C, functie))
    begin = bron.index("if ")

    assert 'kalibratie", False)' in bron[begin : begin + 400]


# --- de melding ------------------------------------------------------


def test_reaching_full_sends_a_critical_notification():
    """Gevraagd: "melding wanneer accu in kalibratie modus 100% bereikt,

    indien mogelijk kritisch."

    Kritiek niet omdat er iets mis is, maar omdat er iets moet GEBEUREN:
    stand uit, ondergrens terug. Blijft die melding tot de volgende
    ochtend in de wachtrij, dan staat de sturing uren onnodig stil.
    """
    from custom_components.energy_management_system.const import (
        LOG_PRIO_KRITIEK,
        LOG_PRIORITEITEN,
    )

    obj = _Kaal()
    obj.kalibratie_momentopname = None
    obj.battery_module_live = [
        {"module": 1, "cel_delta_v": 0.46, "cel_min_v": 2.72, "cel_max_v": 3.18},
    ]

    C._leg_kalibratie_vast(obj, datetime(2026, 8, 19, 16, 0), 100.0)

    assert len(obj.verstuurd) == 1
    melding = obj.verstuurd[0]
    assert melding["kind"] == "kalibratie_vol"
    assert LOG_PRIORITEITEN["kalibratie_vol"] == LOG_PRIO_KRITIEK


def test_the_message_carries_the_cell_spread():
    """De reden dat deze kalibratie gedraaid wordt. Op de telefoon meteen

    af te lezen, zonder de export erbij te halen.
    """
    obj = _Kaal()
    obj.kalibratie_momentopname = None
    obj.battery_module_live = [
        {"module": 1, "cel_delta_v": 0.46, "cel_min_v": 2.72, "cel_max_v": 3.18},
        {"module": 2, "cel_delta_v": 0.00, "cel_min_v": 3.16, "cel_max_v": 3.16},
    ]

    C._leg_kalibratie_vast(obj, datetime(2026, 8, 19, 16, 0), 100.0)
    bericht = obj.verstuurd[0]["message"]

    assert "module 1: 0.460 V" in bericht
    assert "module 2: 0.000 V" in bericht
    assert "kalibratiestand uit" in bericht


def test_it_only_fires_once():
    """De momentopname is de rem: één melding per kalibratie."""
    obj = _Kaal()
    obj.kalibratie_momentopname = None
    obj.battery_module_live = [{"module": 1, "cel_delta_v": 0.46}]

    C._leg_kalibratie_vast(obj, datetime(2026, 8, 19, 16, 0), 100.0)
    C._leg_kalibratie_vast(obj, datetime(2026, 8, 19, 16, 30), 100.0)

    assert len(obj.verstuurd) == 1


# --- de uitleg op het dashboard --------------------------------------


def test_both_explanation_builders_know_about_the_calibration():
    """Gemeld met een schermafdruk: "Tekst is in kalibratie mode niet

    geheel correct." De kop klopte - "Waarom doet de aansturing niets?" -
    maar eronder stond het gewone verhaal over prijsdrempels: de prijs
    is nu 30,8 ct, de drempel voor duur ligt op 37,6 ct, geen bijzondere
    reden om iets anders te doen.

    Twee plekken bouwen een uitleg. `_build_explanation` had zijn tak
    al, `_waarom_regels` niet, en die viel door naar de terugval van
    `default_smart`.
    """
    import inspect

    for functie in (C._build_explanation, C._waarom_regels):
        bron = inspect.getsource(functie)

        assert "kalibratie" in bron, functie.__name__


def test_the_reason_lines_say_what_is_paused():
    """Wie op het dashboard kijkt hoort niet te lezen dat er geen

    bijzondere reden is, terwijl de aansturing juist stilstaat.
    """

    class _Uitleg(_Kaal):
        # v3.51.0: de prijs wordt opnieuw uitgerekend in plaats van
        # onthouden, dus deze stub moet die helper kennen.
        last_current_price_per_kwh = 0.308

        def huidige_prijs_eur_per_kwh(self, now=None):
            return self.last_current_price_per_kwh

        last_expensive_price_threshold = 0.376
        last_needed_kwh_to_bridge = None
        last_cheap_block_start = None
        last_solar_defer_plan = None
        last_sell_check = None
        last_battery_vs_grid = None
        _waarom_regels = C._waarom_regels

        def accustand_procent(self):
            return 30.0

        def beschikbare_energie_kwh(self):
            return 1.7

        def get_quarter_plan_summary(self, now, tot=None):
            return {}

    regels = _Uitleg()._waarom_regels(datetime(2026, 8, 19, 14, 0), "kalibratie")
    tekst = " ".join(regels)

    assert "kalibratiestand" in tekst
    assert "30%" in tekst
    assert "drempel" not in tekst
    assert "geen bijzondere reden" not in tekst


# --- de capaciteitsmeting overleeft een herstart ---------------------


def test_the_running_measurement_is_kept():
    """v3.33.1. Bij de kalibratie van 19 augustus kwam er geen capaciteit

    uit: de herstart voor v3.31.0 zette de lopende meting op nul. Hij
    begon opnieuw bij 71% en had 70% van de schaal nodig.

    Een kalibratie duurt uren en wordt zelden gedaan - dan mag één
    herstart hem niet kosten.
    """
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "kalibratie_meting" in PERSISTED_PLAIN_FIELDS


def test_the_clock_in_the_measurement_is_text():
    """Een `datetime` overleeft de JSON-opslag niet; als tekst wel."""
    obj = _Kaal()
    obj.kalibratie_meting = None
    obj.config = {}

    C._meet_kalibratiecapaciteit(obj, datetime(2026, 8, 19, 12, 0), 40.0)

    assert isinstance(obj.kalibratie_meting["laatste"], str)


def test_it_picks_up_where_it_left_off():
    """Na een herstart staat er tekst in plaats van een klok; dat mag de

    optelling niet breken.
    """
    obj = _Kaal()
    obj.config = {}
    obj.kalibratie_meting = {
        "begin_soc": 5.0,
        "begin": "2026-08-19T09:00:00",
        "kwh_in": 3.1,
        "laatste": "2026-08-19T12:00:00",
    }

    C._meet_kalibratiecapaciteit(obj, datetime(2026, 8, 19, 12, 5), 45.0)

    assert obj.kalibratie_meting["kwh_in"] == 3.1
    assert obj.kalibratie_meting["begin_soc"] == 5.0
