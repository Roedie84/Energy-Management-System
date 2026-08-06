"""Sensor-gezondheid stond op 21% door een trage sensor (v1.1.3).

Gevraagd: "Kun je uitzoeken waarom de sensor gezondheid zo laag is? Of
komt dit door een recente herstart?"

Nee, geen herstart. De foutwaarden in de export herhaalden zich verdacht
exact: 2019,1 / 2020,3 / 2020,9 / 2025,6 W, en 1111,1 / 1112,9 W. Ruis
ziet er niet zo uit.

Root cause: de beschikbare-energiesensor werkt veel trager bij dan de
tick van vijf minuten. Stond hij stil, dan kwam het AFGELEIDE
accuvermogen op 0 uit terwijl de accu werkelijk ~2000 W leverde - en dan
is de "fout" precies gelijk aan dat accuvermogen. Geen sensorstoring,
maar een verschil in meetfrequentie. Daarna volgde het spiegelbeeld: de
opgespaarde sprong kwam in één tick binnen, goed voor 15330 W.

De check meet nu wat hij hoort te meten: klopt de BEWEGING als de sensor
beweegt.
"""
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)

# v1.1.6: de check wacht op ENERGY_BALANCE_MIN_INTERVAL_MINUTES voordat
# hij oordeelt - de sensor stapt in hele SoC-procenten, en over een kort
# interval meet je dan de resolutie in plaats van de sensoren. De
# scenario's hieronder gebruiken daarom realistische, langere intervallen.
STAP = 35  # minuten, ruim boven het minimum


def _config():
    return {
        "available_energy_sensor_entity": "sensor.available_energy",
        "battery_power_sensor_entity": "sensor.battery_power",
    }


def _tick(c, hass, now, beschikbaar, vermogen):
    hass.states.set("sensor.available_energy", f"{beschikbaar:.4f}")
    hass.states.set("sensor.battery_power", str(vermogen))
    c._update_energy_balance_validation(now)


# --- de gerapporteerde situatie -------------------------------------


def test_a_stale_sensor_records_nothing(make_coordinator, hass):
    """De kern: een sensor die niet beweegt terwijl de accu 2000 W
    levert, leverde vier "fouten" van precies 2000 W op."""
    c = make_coordinator(_config())
    now = DAY0
    _tick(c, hass, now, 6.5, 2000)

    for _ in range(6):
        now += timedelta(minutes=5)
        _tick(c, hass, now, 6.5, 2000)

    assert c.energy_balance_error_history == []
    assert c.sensor_health_score is None


def test_the_catch_up_jump_is_not_counted_as_a_huge_error(
    make_coordinator, hass
):
    """Het spiegelbeeld: na stilstand kwam de opgespaarde sprong in één
    tick binnen (15330 W in de export). Die hoort over het WERKELIJKE
    interval te worden gerekend."""
    c = make_coordinator(_config())
    now = DAY0
    _tick(c, hass, now, 6.5, 2000)

    # Zeven ticks stilstand, dan de inhaalslag. 2000 W gedurende 40
    # minuten is 1,3333 kWh. Zonder de correctie zou die sprong over
    # één tick worden gerekend en een absurd tempo opleveren.
    for _ in range(7):
        now += timedelta(minutes=5)
        _tick(c, hass, now, 6.5, 2000)
    now += timedelta(minutes=5)
    _tick(c, hass, now, 6.5 - 1.3333, 2000)

    assert len(c.energy_balance_error_history) == 1
    assert c.energy_balance_error_history[0] < 100


# --- echte fouten worden nog steeds gevangen ------------------------


def test_a_genuine_mismatch_is_still_flagged(make_coordinator, hass):
    """Waar de check voor bestaat: de sensor beweegt, maar niet zoals
    het gemeten vermogen belooft."""
    c = make_coordinator(_config())
    now = DAY0
    _tick(c, hass, now, 6.5, 0)

    now += timedelta(minutes=STAP)
    _tick(c, hass, now, 5.5, 0)  # 1 kWh weg terwijl de accu niets doet

    assert len(c.energy_balance_error_history) == 1
    # 1 kWh over 35 minuten is ~1714 W, terwijl de accu 0 W meldt.
    assert c.energy_balance_error_history[0] > 1000


def test_a_matching_movement_is_a_good_sample(make_coordinator, hass):
    """1000 W ontladen gedurende 35 minuten is 0,5833 kWh."""
    c = make_coordinator(_config())
    now = DAY0
    _tick(c, hass, now, 6.5, 1000)

    now += timedelta(minutes=STAP)
    # 1000 W gedurende 35 minuten = 0,5833 kWh.
    _tick(c, hass, now, 6.5 - 0.5833, 1000)

    assert len(c.energy_balance_error_history) == 1
    assert c.energy_balance_error_history[0] < 50


# --- middelen over het juiste venster -------------------------------


def test_the_measured_power_is_averaged_over_the_interval(
    make_coordinator, hass
):
    """Het afgeleide tempo is een gemiddelde over het interval, dus
    daar hoort het GEMIDDELDE gemeten vermogen naast - niet de
    momentopname van nu.

    Hier draait de accu eerst op 2000 W en daarna op 0. Het afgeleide
    tempo over het hele interval is 1000 W. Tegen de momentopname (0 W)
    zou de fout 1000 W zijn; tegen het gemiddelde is ze aanzienlijk
    kleiner. Exact nul wordt het niet - de metingen zijn discreet - maar
    dat is precies het punt: dichter bij de waarheid, niet perfect."""
    c = make_coordinator(_config())
    now = DAY0
    _tick(c, hass, now, 6.5, 2000)

    now += timedelta(minutes=STAP)
    _tick(c, hass, now, 6.5, 0)  # geen beweging: alleen vermogen verzamelen

    now += timedelta(minutes=STAP)
    _tick(c, hass, now, 6.3, 0)

    assert len(c.energy_balance_error_history) == 1
    fout = c.energy_balance_error_history[0]
    assert fout < 500, "tegen de momentopname zou dit 1000 W zijn"


def test_an_unavailable_sensor_is_still_a_bad_sample(make_coordinator, hass):
    """Een wegvallende sensor is wél een gezondheidssignaal - dat moet
    onderscheiden blijven van een sensor die gewoon traag is."""
    c = make_coordinator(_config())
    _tick(c, hass, DAY0, 6.5, 1000)

    hass.states.set("sensor.battery_power", "unavailable")
    c._update_energy_balance_validation(DAY0 + timedelta(minutes=STAP))

    assert c.energy_balance_error_history == [None]


def test_a_long_stall_is_not_attributed_to_one_rate(make_coordinator, hass):
    """Staat de sensor uren stil, dan is de sprong daarna niet meer
    betrouwbaar aan één tempo toe te schrijven."""
    c = make_coordinator(_config())
    _tick(c, hass, DAY0, 6.5, 1000)

    _tick(c, hass, DAY0 + timedelta(hours=3), 5.0, 1000)

    assert c.energy_balance_error_history == []


# --- v1.1.6: kwantisatieruis -----------------------------------------


def test_a_single_quantisation_step_over_a_short_interval_is_ignored(
    make_coordinator, hass
):
    """De kern van de tweede melding ("waarom nog steeds een slechte
    score?").

    De beschikbare-energiesensor stapt in hele SoC-procenten: bij ~7,7
    kWh is dat ~0,077 kWh per stap. Over vijf minuten komt zo'n stap
    neer op ~920 W afgeleid vermogen, terwijl de drempel op 300 W ligt.
    De check mat dan niet de sensoren maar de RESOLUTIE van de sensor
    gedeeld door een kort interval.
    """
    c = make_coordinator(_config())
    _tick(c, hass, DAY0, 7.6896, 0)

    _tick(c, hass, DAY0 + timedelta(minutes=5), 7.6896 - 0.077, 0)

    assert c.energy_balance_error_history == []


def test_the_same_step_over_a_long_interval_is_within_tolerance(
    make_coordinator, hass
):
    """Over 35 minuten komt diezelfde stap uit op ~130 W - ruim binnen
    de drempel. Wachten lost het probleem dus echt op in plaats van het
    te verbergen."""
    c = make_coordinator(_config())
    _tick(c, hass, DAY0, 7.6896, 0)

    _tick(c, hass, DAY0 + timedelta(minutes=35), 7.6896 - 0.077, 0)

    assert len(c.energy_balance_error_history) == 1
    assert c.energy_balance_error_history[0] < 300


def test_history_from_an_older_method_is_discarded(make_coordinator, hass):
    """Tussen v1.1.2 en v1.1.6 is de meetmethode twee keer wezenlijk
    veranderd. Oude metingen zeggen niets over de huidige manier van
    meten, maar bleven wel in het venster van twintig hangen en drukten
    de score omlaag zonder dat er iets mis was."""
    import asyncio

    from custom_components.energy_management_system.const import (
        ENERGY_BALANCE_METHOD_VERSION,
    )

    c = make_coordinator(_config())
    c.energy_balance_error_history = [15330.1, 2014.7, 1174.7]
    c.sensor_health_score = 20.0
    c.measurement_quality = "slecht"
    c.energy_balance_method_version = ENERGY_BALANCE_METHOD_VERSION - 1

    c._discard_history_from_an_older_method()

    assert c.energy_balance_error_history == []
    assert c.sensor_health_score is None
    assert c.energy_balance_method_version == ENERGY_BALANCE_METHOD_VERSION
    assert asyncio is not None


def test_history_from_the_current_method_is_kept(make_coordinator, hass):
    """Alleen wissen bij een echte methodewijziging - anders zou elke
    herstart de meting terugzetten."""
    from custom_components.energy_management_system.const import (
        ENERGY_BALANCE_METHOD_VERSION,
    )

    c = make_coordinator(_config())
    c.energy_balance_error_history = [12.0, 15.0]
    c.energy_balance_method_version = ENERGY_BALANCE_METHOD_VERSION

    c._discard_history_from_an_older_method()

    assert c.energy_balance_error_history == [12.0, 15.0]
