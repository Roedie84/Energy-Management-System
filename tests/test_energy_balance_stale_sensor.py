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

    # Twee ticks stilstand, dan de inhaalslag. 2000 W gedurende 15
    # minuten is 0,5 kWh. (Langer dan MAX_HOUR_TRACKING_GAP_MINUTES
    # stilstaan wordt sowieso overgeslagen - zie de laatste test.)
    for _ in range(2):
        now += timedelta(minutes=5)
        _tick(c, hass, now, 6.5, 2000)
    now += timedelta(minutes=5)
    _tick(c, hass, now, 6.0, 2000)

    assert len(c.energy_balance_error_history) == 1
    assert c.energy_balance_error_history[0] < 100


# --- echte fouten worden nog steeds gevangen ------------------------


def test_a_genuine_mismatch_is_still_flagged(make_coordinator, hass):
    """Waar de check voor bestaat: de sensor beweegt, maar niet zoals
    het gemeten vermogen belooft."""
    c = make_coordinator(_config())
    now = DAY0
    _tick(c, hass, now, 6.5, 0)

    now += timedelta(minutes=6)
    _tick(c, hass, now, 5.5, 0)  # 1 kWh weg terwijl de accu niets doet

    assert len(c.energy_balance_error_history) == 1
    assert c.energy_balance_error_history[0] > 5000


def test_a_matching_movement_is_a_good_sample(make_coordinator, hass):
    """1000 W ontladen gedurende 6 minuten is precies 0,1 kWh."""
    c = make_coordinator(_config())
    now = DAY0
    _tick(c, hass, now, 6.5, 1000)

    now += timedelta(minutes=6)
    _tick(c, hass, now, 6.4, 1000)

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

    now += timedelta(minutes=6)
    _tick(c, hass, now, 6.5, 0)  # geen beweging: alleen vermogen verzamelen

    now += timedelta(minutes=6)
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
    c._update_energy_balance_validation(DAY0 + timedelta(minutes=6))

    assert c.energy_balance_error_history == [None]


def test_a_long_stall_is_not_attributed_to_one_rate(make_coordinator, hass):
    """Staat de sensor uren stil, dan is de sprong daarna niet meer
    betrouwbaar aan één tempo toe te schrijven."""
    c = make_coordinator(_config())
    _tick(c, hass, DAY0, 6.5, 1000)

    _tick(c, hass, DAY0 + timedelta(hours=3), 5.0, 1000)

    assert c.energy_balance_error_history == []
