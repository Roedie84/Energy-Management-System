"""Living-room-temperature airco activation predictor (v0.63.55,
requested: "verwacht wanneer ik de airco aanzet"). Uses the same
"queue an observation, confirm it later" technique as
SolarForecastAccuracyTracker - each temperature reading is bucketed
and queued, then confirmed AIRCO_PREDICTION_LOOKAHEAD_MINUTES later as
True/False depending on whether the airco was confirmed active at any
point during that window. Short rolling window per bucket, not a
long/seasonal one - spring/autumn conditions can swing day to day.
"""
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 4, 1, tzinfo=timezone.utc)


def _base_config(**overrides):
    config = {
        "living_room_temperature_sensor_entity": "sensor.living_room_temp",
        "living_room_humidity_sensor_entity": "sensor.living_room_humidity",
    }
    config.update(overrides)
    return config


def test_no_temperature_sensor_does_nothing(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._update_living_room_airco_prediction(DAY0)

    assert coordinator.living_room_current_temp_c is None
    assert coordinator._temp_prediction_pending == []


def test_reads_temperature_and_humidity(make_coordinator, hass):
    hass.states.set("sensor.living_room_temp", "19.4")
    hass.states.set("sensor.living_room_humidity", "55")
    coordinator = make_coordinator(_base_config())

    coordinator._update_living_room_airco_prediction(DAY0)

    assert coordinator.living_room_current_temp_c == 19.4
    assert coordinator.living_room_current_humidity_percent == 55.0


def test_queues_an_observation(make_coordinator, hass):
    hass.states.set("sensor.living_room_temp", "19.4")
    coordinator = make_coordinator(_base_config())

    coordinator._update_living_room_airco_prediction(DAY0)

    assert len(coordinator._temp_prediction_pending) == 1
    assert coordinator._temp_prediction_pending[0]["bucket"] == "19.0"


def test_finalises_after_the_lookahead_window_with_airco_inactive(
    make_coordinator, hass
):
    hass.states.set("sensor.living_room_temp", "19.4")
    coordinator = make_coordinator(_base_config())
    coordinator.last_heavy_load_source = None  # airco not active

    coordinator._update_living_room_airco_prediction(DAY0)
    coordinator._update_living_room_airco_prediction(
        DAY0 + timedelta(minutes=65)
    )

    result = coordinator.get_airco_activation_probability("19.0")
    assert result["sample_count"] == 1
    assert result["probability_percent"] == 0.0


def test_finalises_as_active_if_airco_confirmed_within_the_window(
    make_coordinator, hass
):
    hass.states.set("sensor.living_room_temp", "18.0")
    coordinator = make_coordinator(_base_config())
    coordinator.last_heavy_load_source = None

    coordinator._update_living_room_airco_prediction(DAY0)

    # 30 minutes later (still within the 60-min lookahead), the airco
    # turns on.
    coordinator.last_heavy_load_source = "airco"
    coordinator._update_living_room_airco_prediction(
        DAY0 + timedelta(minutes=30)
    )

    # 65 minutes after the original observation - now finalised.
    coordinator.last_heavy_load_source = None
    coordinator._update_living_room_airco_prediction(
        DAY0 + timedelta(minutes=70)
    )

    result = coordinator.get_airco_activation_probability("18.0")
    assert result["sample_count"] >= 1
    assert result["probability_percent"] == 100.0


def test_probability_averages_over_the_rolling_window(make_coordinator, hass):
    """A single moment of airco activity can retroactively confirm more
    than one nearby still-pending observation (any observation queued
    within the last lookahead window gets marked active too) - so this
    scenario (airco active for one tick, in the middle of an otherwise
    inactive sequence) correctly yields 2 "active" outcomes out of 4,
    not just 1. Each call also seeds a fresh pending observation of its
    own (every tick queues one); timestamps are spaced 3h apart so every
    earlier pending entry is always finalised before the next queue
    call, keeping the resulting count predictable."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.living_room_temp", "20.0")

    for i in range(3):
        coordinator.last_heavy_load_source = None
        coordinator._update_living_room_airco_prediction(DAY0 + timedelta(hours=3 * i))

    coordinator.last_heavy_load_source = "airco"
    coordinator._update_living_room_airco_prediction(DAY0 + timedelta(hours=9))
    coordinator.last_heavy_load_source = None
    coordinator._update_living_room_airco_prediction(DAY0 + timedelta(hours=12))

    result = coordinator.get_airco_activation_probability("20.0")
    assert result["sample_count"] == 4
    assert result["probability_percent"] == 50.0


def test_not_enough_data_flag(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())

    result = coordinator.get_airco_activation_probability("20.0")

    assert result["voldoende_data"] is False
    assert result["probability_percent"] is None


def test_history_bounded_to_a_short_rolling_window(make_coordinator, hass):
    """Short window, not a long/seasonal one - requested: spring/autumn
    conditions can swing day to day."""
    coordinator = make_coordinator(_base_config())

    for i in range(40):
        hass.states.set("sensor.living_room_temp", "20.0")
        coordinator.last_heavy_load_source = None
        t = DAY0 + timedelta(hours=2 * i)
        coordinator._update_living_room_airco_prediction(t)
        coordinator._update_living_room_airco_prediction(t + timedelta(minutes=65))

    from custom_components.energy_management_system.const import (
        AIRCO_PREDICTION_HISTORY_LENGTH,
    )

    assert len(coordinator.living_room_temp_bucket_history["20.0"]) == (
        AIRCO_PREDICTION_HISTORY_LENGTH
    )


def test_humidity_tracked_as_context_per_bucket(make_coordinator, hass):
    hass.states.set("sensor.living_room_temp", "20.0")
    hass.states.set("sensor.living_room_humidity", "60")
    coordinator = make_coordinator(_base_config())
    coordinator.last_heavy_load_source = None

    coordinator._update_living_room_airco_prediction(DAY0)
    coordinator._update_living_room_airco_prediction(DAY0 + timedelta(minutes=65))

    result = coordinator.get_airco_activation_probability("20.0")
    assert result["gemiddelde_luchtvochtigheid_percent"] == 60.0


def test_never_calls_any_hass_service(make_coordinator, hass):
    hass.states.set("sensor.living_room_temp", "19.4")
    coordinator = make_coordinator(_base_config())

    coordinator._update_living_room_airco_prediction(DAY0)

    assert hass.services.calls == []
