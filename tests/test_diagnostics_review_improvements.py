"""Verbeteringen uit de diagnostiek-analyse van v0.63.120.

Vier bevindingen uit een verse diagnostiek-export, elk hier apart
getest:

1. `living_room_current_humidity_percent: 45.9213256835938` - exact
   dezelfde klacht die in v0.63.92 voor de temperatuur werd opgelost,
   maar de luchtvochtigheid ernaast bleef ongemoeid.
2. `water_session_history` bevatte tijdstempels met ZOWEL "+02:00" als
   "+00:00" - oude momenten uit de listener staan in UTC. De
   "vandaag"-vergelijking las de eerste tien tekens als datum, wat voor
   een UTC-tijdstempel tussen middernacht en 02:00 lokaal de verkeerde
   dag oplevert.
3. De waterschuwing zei "mogelijk worden stoten gemist" - een gok die
   twee keer de verkeerde kant op wees. Het aantal herkende momenten
   onderscheidt de twee mogelijke oorzaken juist meteen.
4. Sensor-gezondheid velde een oordeel op één of twee metingen
   ("slecht (0.0%, 1 metingen)", "verminderd (50.0%, 2 metingen)").
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import (
    CONF_LIVING_ROOM_HUMIDITY_SENSOR,
    CONF_LIVING_ROOM_TEMPERATURE_SENSOR,
    CONF_WATER_DAILY_TOTAL_SENSOR,
    MEASUREMENT_QUALITY_MIN_SAMPLES,
)

LOCAL = timezone(timedelta(hours=2))
NOW_UTC = datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc)


# --- 1. luchtvochtigheid afronden ---------------------------------


def test_humidity_is_rounded_like_every_other_reading(make_coordinator, hass):
    coordinator = make_coordinator(
        {
            CONF_LIVING_ROOM_TEMPERATURE_SENSOR: "sensor.temp",
            CONF_LIVING_ROOM_HUMIDITY_SENSOR: "sensor.hum",
        }
    )
    hass.states.set("sensor.temp", "23.4123456789")
    hass.states.set("sensor.hum", "45.9213256835938")

    coordinator._update_living_room_airco_prediction(NOW_UTC)

    assert coordinator.living_room_current_humidity_percent == 45.9
    assert coordinator.living_room_current_temp_c == 23.4


def test_missing_humidity_stays_none(make_coordinator, hass):
    coordinator = make_coordinator(
        {CONF_LIVING_ROOM_TEMPERATURE_SENSOR: "sensor.temp"}
    )
    hass.states.set("sensor.temp", "23.4")

    coordinator._update_living_room_airco_prediction(NOW_UTC)

    assert coordinator.living_room_current_humidity_percent is None


# --- 2 + 3. waterschuwing -----------------------------------------


@pytest.fixture
def _fixed_now():
    """Zet de klok vast en ruimt zichzelf op - conform de les uit
    v0.63.108 over testbestanden die dt_util globaal patchen zonder
    cleanup."""
    from custom_components.energy_management_system import coordinator as mod

    origineel_now = mod.dt_util.now
    origineel_as_local = mod.dt_util.as_local
    mod.dt_util.now = lambda: datetime(2026, 8, 6, 12, 0, tzinfo=LOCAL)
    mod.dt_util.as_local = lambda value: (
        value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    ).astimezone(LOCAL)
    yield
    mod.dt_util.now = origineel_now
    mod.dt_util.as_local = origineel_as_local


def _water_coordinator(make_coordinator, liters_vandaag):
    coordinator = make_coordinator(
        {CONF_WATER_DAILY_TOTAL_SENSOR: "sensor.water_daily"}
    )
    coordinator.water_daily_total_l = liters_vandaag
    return coordinator


def test_utc_stored_session_still_counts_for_today(
    make_coordinator, hass, _fixed_now
):
    """Een moment om 01:15 lokaal staat als 23:15 UTC van GISTEREN in de
    geschiedenis. Dat hoort gewoon bij vandaag te tellen."""
    coordinator = _water_coordinator(make_coordinator, 100.0)
    coordinator.water_session_history = [
        {"gestart": "2026-08-05T23:15:00+00:00", "liter": 40.0},
        {"gestart": "2026-08-06T08:00:00+00:00", "liter": 20.0},
    ]

    punten = coordinator.get_diagnostic_summary()["aandachtspunten"]

    # 60 van 100 L verklaard - boven de 30%-drempel, dus geen
    # waarschuwing. Zonder de omrekening telde de eerste sessie niet mee
    # (die leest als 2026-08-05) en bleef er 20 van 100 L over: dan
    # sloeg de waarschuwing wél aan, volledig ten onrechte.
    assert not any("Waterverbruik" in p for p in punten)


def test_few_sessions_points_at_the_detection(make_coordinator, hass, _fixed_now):
    coordinator = _water_coordinator(make_coordinator, 85.0)
    coordinator.water_session_history = [
        {"gestart": "2026-08-06T08:00:00+02:00", "liter": 2.0},
        {"gestart": "2026-08-06T09:00:00+02:00", "liter": 3.0},
    ]

    melding = next(
        p
        for p in coordinator.get_diagnostic_summary()["aandachtspunten"]
        if "Waterverbruik" in p
    )

    assert "2 gebruiksmoment" in melding
    assert "detectie" in melding


def test_many_sessions_points_at_the_volume(make_coordinator, hass, _fixed_now):
    """Veel momenten met weinig liters betekent iets heel anders: de
    detectie werkt, de volumebepaling niet."""
    coordinator = _water_coordinator(make_coordinator, 85.0)
    coordinator.water_session_history = [
        {"gestart": f"2026-08-06T0{u}:00:00+02:00", "liter": 0.5} for u in range(8)
    ]

    melding = next(
        p
        for p in coordinator.get_diagnostic_summary()["aandachtspunten"]
        if "Waterverbruik" in p
    )

    assert "8 gebruiksmomenten" in melding
    assert "volume" in melding
    assert "liter_uit_meterstand" in melding


def test_unparseable_timestamp_is_skipped_not_crashing(
    make_coordinator, hass, _fixed_now
):
    coordinator = _water_coordinator(make_coordinator, 85.0)
    coordinator.water_session_history = [
        {"gestart": "niet-een-datum", "liter": 5.0},
        {"gestart": None, "liter": 5.0},
    ]

    punten = coordinator.get_diagnostic_summary()["aandachtspunten"]

    assert any("Waterverbruik" in p for p in punten)


# --- 4. sensor-gezondheid: minimum aantal metingen ------------------


def test_no_verdict_on_a_single_measurement(make_coordinator, hass):
    """"slecht (0.0%, 1 metingen)" - statistisch betekenisloos, maar het
    bracht de systeemstatus wel op "Aandacht gewenst"."""
    coordinator = make_coordinator({})

    coordinator._record_balance_sample(99999.0)

    assert coordinator.sensor_health_score is None
    assert coordinator.measurement_quality is None


def test_no_verdict_just_below_the_threshold(make_coordinator, hass):
    coordinator = make_coordinator({})

    for _ in range(MEASUREMENT_QUALITY_MIN_SAMPLES - 1):
        coordinator._record_balance_sample(99999.0)

    assert coordinator.sensor_health_score is None


def test_verdict_appears_exactly_at_the_threshold(make_coordinator, hass):
    coordinator = make_coordinator({})

    for _ in range(MEASUREMENT_QUALITY_MIN_SAMPLES):
        coordinator._record_balance_sample(99999.0)

    assert coordinator.sensor_health_score == 0.0
    assert coordinator.measurement_quality == "slecht"


def test_a_lone_bad_sample_no_longer_lowers_the_system_status(
    make_coordinator, hass
):
    """Het praktische gevolg: één ongelukkige meting vlak na een
    herstart mag de systeemstatus niet omlaag trekken."""
    coordinator = make_coordinator({})
    coordinator.last_error = None
    coordinator.last_error_time = None
    coordinator.last_successful_update = None

    coordinator._record_balance_sample(99999.0)

    assert coordinator.system_status == "OK"


def test_a_genuinely_bad_sensor_is_still_reported(make_coordinator, hass):
    """De drempel mag een échte storing niet verbergen."""
    coordinator = make_coordinator({})
    coordinator.last_error = None
    coordinator.last_error_time = None
    coordinator.last_successful_update = None

    for _ in range(MEASUREMENT_QUALITY_MIN_SAMPLES + 5):
        coordinator._record_balance_sample(99999.0)

    assert coordinator.measurement_quality == "slecht"
    assert coordinator.system_status == "Aandacht gewenst"
