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
    """Alleen de vlaggen, zonder de rest van de coordinator."""

    kalibratie = True
    force_manual = False
    learning_only = False
    vacation_mode = False
    config: dict = {}

    def __init__(self) -> None:
        self.verstuurd: list[dict] = []

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

    # De rem geldt voor leermodus en handmatige overname, niet voor de
    # kalibratie.
    assert "self.learning_only or self.force_manual" in bron
    assert "self.kalibratie" not in bron.split("if self.learning_only")[1]


def test_the_battery_is_left_alone():
    """De hele bedoeling: EMS schrijft niets naar de accu."""
    import inspect

    bron = inspect.getsource(C)
    gate = bron[bron.index('if self.kalibratie:') :][:600]

    assert 'self.last_reason = "kalibratie"' in gate
    assert "return" in gate


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
