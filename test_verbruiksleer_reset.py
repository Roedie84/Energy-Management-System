"""Verbruiksleer opnieuw beginnen (v3.30.0).

Gevraagd: "Graag een reset knop aanbrengen, voor direct na de vakantie.
Vanaf dat moment dient er opnieuw geleerd te worden."

Aanleiding: hij is sinds 14 augustus 11:00 op vakantie zonder dat de
vakantiestand aanstond. Vijf dagen leeg huis zijn de leerbestanden in
gelopen. Het uurprofiel staat kaarsvlak op 0,18 tot 0,29 kW - samen 5,5
kWh per dag, terwijl het huis er op 12 en 13 augustus 12,3 en 12,6 door
joeg. Geen ochtendpiek, geen avondpiek: dat is een basislast, geen
huishouden.

Zonder ingrijpen reserveert de integratie bij thuiskomst voor een huis
van 5,5 kWh en loopt de accu 's avonds leeg. De tekortdetectie corrigeert
dat met 5 procentpunt per dag - een week lang, met dure avonden.

Wat de knop WEL wist: alles wat uit het gedrag van het huishouden is
geleerd. Wat hij NIET wist: metingen (de dagreeks, de cyclustelling), en
alles wat losstaat van bewoning - de zonvoorspelling, het accurendement,
de herkende apparaten. Die 25 bevestigde apparaten opnieuw laten
ontdekken zou weken kosten en er is niets mis mee.
"""
from datetime import date, datetime, timedelta

from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)


class _Kaal:
    """Alles wat de knop aanraakt, met vakantiewaarden erin."""

    def __init__(self) -> None:
        # --- wat gewist moet worden ---
        self.hourly_consumption_profile = {
            str(u): [0.2, 0.25] for u in range(24)
        }
        self.night_consumption_history = [0.207, 0.197, 0.185, 0.161]
        self.temp_consumption_history = [{"temp_c": 21.5, "kw": 0.215}]
        self.temp_consumption_prediction_error_history = [90.7, 11.0]
        self.baseline_load_history = [0.19, 0.18, 0.2]
        self.sluipverbruik_reference_w = 190.0
        self.sluipverbruik_estimated_drift_w = 12.0
        self.sluipverbruik_detected = True
        self.cusum_accumulator_kw = 0.4
        self.reserve_daily_records = [
            {"date": "2026-08-16", "shortfall": True, "excess": False}
        ]
        self.bedtime_history = ["22:22", "22:40"]
        self.presence_week_profile = {"6-1130": [12, 12]}

        # de dag die op dit moment loopt
        self._hour_energy_kwh = 0.18
        self._hour_duration_hours = 0.6
        self._today_min_load_kw = 0.19
        self._shortfall_detected_today = True
        self._excess_detected_today = False

        # --- wat met rust gelaten moet worden ---
        self.energy_daily_history = [{"datum": "2026-08-14", "opwek_kwh": 21.0}]
        self.battery_cumulative_discharged_kwh = 86.32
        self.learned_efficiency_history = [84.5, 85.0]
        self.nilm_confirmed_devices = {"sensor.vaatwasser": {}}
        self.pv_hourly_bias_profile = {"12": 0.921}
        self.first_seen_date = date(2026, 8, 1)

        self.verstuurd: list[dict] = []
        self.opgeslagen = 0
        self.verbruiksleer_reset_op = None
        self.verbruiksleer_reset_historie: list[dict] = []
        self._verbruiksleer_reset_gevraagd_op = None
        self.config: dict = {}

    def schedule_persisted_state_save(self):
        self.opgeslagen += 1

    def _dispatch_notification(self, **kwargs):
        self.verstuurd.append(kwargs)

    def _notify_listeners(self):
        pass

    # afgeleide eigenschappen die de samenvatting opvraagt
    learned_night_consumption_kw = 0.197

    reset_verbruiksleer = C.reset_verbruiksleer
    vraag_verbruiksleer_reset = C.vraag_verbruiksleer_reset
    verbruiksleer_reset_wacht_op_bevestiging = (
        C.verbruiksleer_reset_wacht_op_bevestiging
    )


def _na_reset(nu=datetime(2026, 8, 30, 12, 0)):
    """Twee drukken: de eerste wapent, de tweede voert uit."""
    obj = _Kaal()
    obj.vraag_verbruiksleer_reset(nu)
    obj.vraag_verbruiksleer_reset(nu + timedelta(seconds=5))
    return obj


# --- wat er weg moet ------------------------------------------------


def test_the_hourly_profile_is_emptied():
    """Het profiel dat de reserveberekening gebruikt, staat vol met een

    leeg huis: kaarsvlak op 0,18 tot 0,29 kW.
    """
    assert _na_reset().hourly_consumption_profile == {}


def test_the_night_baseline_is_emptied():
    """Vijf van de zeven nachten zijn vakantie."""
    assert _na_reset().night_consumption_history == []


def test_the_temperature_relation_is_emptied():
    """Alle zeven monsters komen uit de vakantie."""
    obj = _na_reset()

    assert obj.temp_consumption_history == []
    assert obj.temp_consumption_prediction_error_history == []


def test_the_standby_reference_is_emptied():
    """Anders komt er bij thuiskomst een valse sluipverbruik-melding: de

    referentie staat op een leeg huis, dus normaal gebruik ziet eruit als
    een sprong.
    """
    obj = _na_reset()

    assert obj.baseline_load_history == []
    assert obj.sluipverbruik_reference_w is None
    assert obj.sluipverbruik_estimated_drift_w is None
    assert obj.sluipverbruik_detected is False
    assert obj.cusum_accumulator_kw == 0.0


def test_the_shortfall_days_are_emptied():
    """De tekortdag van 16 augustus verhoogde de marge met 5 procentpunt,

    en die dag zegt niets over een bewoond huis.
    """
    assert _na_reset().reserve_daily_records == []


def test_the_household_rhythm_is_emptied():
    """Elke vakantienacht stond er 6,5 uur "slaapt" terwijl er niemand

    was. Die bedtijden zijn geen bedtijden.
    """
    obj = _na_reset()

    assert obj.bedtime_history == []
    assert obj.presence_week_profile == {}


# --- wat er moet blijven --------------------------------------------


def test_measurements_are_never_touched():
    """De dagreeks en de cyclustelling zijn metingen, geen leerwerk. Die

    wissen zou echte geschiedenis weggooien.
    """
    obj = _na_reset()

    assert obj.energy_daily_history
    assert obj.battery_cumulative_discharged_kwh == 86.32
    assert obj.first_seen_date == date(2026, 8, 1)


def test_learning_that_has_nothing_to_do_with_the_household_stays():
    """De zonvoorspelling, het accurendement en de herkende apparaten

    hebben geen last van een leeg huis. Die 25 bevestigde apparaten
    opnieuw laten ontdekken zou weken kosten.
    """
    obj = _na_reset()

    assert obj.pv_hourly_bias_profile
    assert obj.learned_efficiency_history
    assert obj.nilm_confirmed_devices


# --- wat er wordt vastgelegd ----------------------------------------


def test_the_moment_is_recorded():
    """Zonder datum is later niet te zien waarom het profiel maar drie

    dagen oud is.
    """
    nu = datetime(2026, 8, 30, 12, 0)

    assert _na_reset(nu).verbruiksleer_reset_op == (
        nu + timedelta(seconds=5)
    ).isoformat()


def test_what_was_thrown_away_is_kept_for_inspection():
    """Een onomkeerbare knop zonder spoor is een knop die je niet durft

    te gebruiken. De weggegooide waarden blijven na te lezen.
    """
    historie = _na_reset().verbruiksleer_reset_historie

    assert len(historie) == 1
    weg = historie[0]["gewist"]
    assert weg["uurprofiel_uren"] == 24
    assert weg["nachten"] == 4
    assert weg["tekortdagen"] == 1


def test_it_says_so_out_loud():
    """Een stille reset is niet van een storing te onderscheiden."""
    melding = _na_reset().verstuurd[0]

    assert melding["kind"] == "verbruiksleer_reset"
    assert "weggegooid" in melding["message"].lower()


def test_the_state_is_written_away_immediately():
    """Een herstart vlak na de knop zou de oude waarden terugzetten."""
    assert _na_reset().opgeslagen >= 1


def test_pressing_twice_keeps_both_records():
    """De geschiedenis is een reeks, geen laatste waarde."""
    obj = _Kaal()
    for moment in (datetime(2026, 8, 30, 12, 0), datetime(2026, 9, 1, 12, 0)):
        obj.vraag_verbruiksleer_reset(moment)
        obj.vraag_verbruiksleer_reset(moment + timedelta(seconds=5))

    assert len(obj.verbruiksleer_reset_historie) == 2


# --- de knop zelf ----------------------------------------------------


def test_the_button_exists_and_is_wired():
    from custom_components.energy_management_system import button as mod

    bron = mod.__file__
    tekst = open(bron).read()

    assert "VerbruiksleerResetButton" in tekst
    assert "vraag_verbruiksleer_reset" in tekst


def test_the_reset_survives_a_restart():
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "verbruiksleer_reset_op" in PERSISTED_PLAIN_FIELDS
    assert "verbruiksleer_reset_historie" in PERSISTED_PLAIN_FIELDS


# --- de bevestiging in twee stappen ----------------------------------


def test_one_press_changes_nothing():
    """Gevraagd: "De reset button moet na een druk op de knop nog een

    keer bevestigd worden dat een reset zeker gewenst is." De knop gooit
    onomkeerbaar weg wat in weken is opgebouwd.
    """
    obj = _Kaal()

    uitkomst = obj.vraag_verbruiksleer_reset(datetime(2026, 8, 30, 12, 0))

    assert uitkomst["stap"] == "bevestiging_nodig"
    assert obj.hourly_consumption_profile != {}
    assert obj.verbruiksleer_reset_op is None
    assert obj.verstuurd == []


def test_the_second_press_carries_it_out():
    obj = _Kaal()
    nu = datetime(2026, 8, 30, 12, 0)
    obj.vraag_verbruiksleer_reset(nu)

    uitkomst = obj.vraag_verbruiksleer_reset(nu + timedelta(seconds=10))

    assert uitkomst["stap"] == "uitgevoerd"
    assert obj.hourly_consumption_profile == {}


def test_the_request_expires_on_its_own():
    """Een knop die na een uur nog scherp staat is gevaarlijker dan een

    knop zonder bevestiging: dan drukt iemand er een keer op zonder te
    weten dat de vorige druk er nog stond.
    """
    from custom_components.energy_management_system.const import (
        VERBRUIKSLEER_RESET_BEVESTIGING_SECONDEN,
    )

    obj = _Kaal()
    nu = datetime(2026, 8, 30, 12, 0)
    obj.vraag_verbruiksleer_reset(nu)

    laat = nu + timedelta(
        seconds=VERBRUIKSLEER_RESET_BEVESTIGING_SECONDEN + 1
    )
    uitkomst = obj.vraag_verbruiksleer_reset(laat)

    assert uitkomst["stap"] == "bevestiging_nodig"
    assert obj.hourly_consumption_profile != {}


def test_the_remaining_time_is_visible():
    """Zonder aftellende tijd is niet te zien of de knop nog scherp

    staat.
    """
    obj = _Kaal()
    nu = datetime(2026, 8, 30, 12, 0)

    assert obj.verbruiksleer_reset_wacht_op_bevestiging(nu) is None

    obj.vraag_verbruiksleer_reset(nu)

    assert obj.verbruiksleer_reset_wacht_op_bevestiging(
        nu + timedelta(seconds=20)
    ) == 40
    assert obj.verbruiksleer_reset_wacht_op_bevestiging(
        nu + timedelta(seconds=90)
    ) is None


def test_the_button_asks_before_it_wipes():
    from custom_components.energy_management_system import button as mod

    tekst = open(mod.__file__).read()

    assert "vraag_verbruiksleer_reset" in tekst
    assert "bevestiging_nodig" in tekst


# --- de dag die op dit moment loopt ----------------------------------


def test_the_hour_in_progress_is_dropped_too():
    """Gevraagd: "Moet dit dan precies om 12 uur snachts of zo? Dat is

    niet handig toch dan slaap ik." Nee - en juist daarom moet het uur
    dat op dat moment loopt er ook uit. Anders schuift dat na afloop
    alsnog het verse profiel in, met het verbruik van een leeg huis
    erin.
    """
    obj = _na_reset()

    assert obj._hour_energy_kwh == 0.0
    assert obj._hour_duration_hours == 0.0
    assert obj._today_min_load_kw is None


def test_todays_shortfall_flag_is_cleared():
    """Stond de tekortvlag van vandaag aan, dan schoof die om middernacht

    alsnog als tekortdag de reeks in - en dan levert de eerste dag na de
    reset meteen 5 procentpunt marge op.
    """
    obj = _na_reset()

    assert obj._shortfall_detected_today is False
    assert obj._excess_detected_today is False


def test_the_summary_says_the_flag_was_set():
    """Zodat achteraf te zien is dat er een tekortdag is weggevallen."""
    historie = _na_reset().verbruiksleer_reset_historie

    assert historie[0]["gewist"]["tekortvlag_vandaag"] is True
