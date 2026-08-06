"""Klimaat-tabblad: geleerde woonkamertemperatuur-projectie (v0.63.56,
requested). Bewust vereenvoudigd: bewolking is expliciet weggelaten als
aparte leerdimensie, maar de KNMI/OpenWeatherMap-buitentemperatuur-
voorspelling wordt wel gebruikt om de projectie uur voor uur door te
rekenen. Geleerd: verandersnelheid (°C/uur) per combinatie van
buitentemperatuur-bucket x rolluikstand x airco-status, in een kort,
glijdend venster (spring/autumn-responsiviteit).
"""
import asyncio
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 4, 1, tzinfo=timezone.utc)


def _base_config(**overrides):
    config = {
        "living_room_temperature_sensor_entity": "sensor.living_room_temp",
        "living_room_shutter_entity_1": "cover.rolluik_achter",
        "living_room_shutter_entity_2": "cover.rolluik_voor",
        "airco_climate_entity": "climate.woonkamer_airco",
        "knmi_weather_entity": "weather.knmi",
    }
    config.update(overrides)
    return config


def _seed_common(hass, temp="19.0", outdoor="10.0", shutter1="closed", shutter2="closed"):
    hass.states.set("sensor.living_room_temp", temp)
    hass.states.set("weather.knmi", "cloudy", {"temperature": float(outdoor)})
    hass.states.set("cover.rolluik_achter", shutter1)
    hass.states.set("cover.rolluik_voor", shutter2)


def test_shutter_state_both_closed(make_coordinator, hass):
    _seed_common(hass, shutter1="closed", shutter2="closed")
    coordinator = make_coordinator(_base_config())

    assert coordinator._get_shutter_state_label() == "beide_dicht"


def test_shutter_state_both_open(make_coordinator, hass):
    _seed_common(hass, shutter1="open", shutter2="open")
    coordinator = make_coordinator(_base_config())

    assert coordinator._get_shutter_state_label() == "beide_open"


def test_shutter_state_mixed(make_coordinator, hass):
    _seed_common(hass, shutter1="open", shutter2="closed")
    coordinator = make_coordinator(_base_config())

    assert coordinator._get_shutter_state_label() == "gedeeltelijk"


def test_shutter_state_none_configured(make_coordinator, hass):
    coordinator = make_coordinator({})

    assert coordinator._get_shutter_state_label() is None


def test_airco_state_heating(make_coordinator, hass):
    hass.states.set(
        "climate.woonkamer_airco", "heat", {"hvac_action": "heating"}
    )
    coordinator = make_coordinator(_base_config())

    assert coordinator._get_current_airco_state_label() == "verwarmen"


def test_airco_state_cooling(make_coordinator, hass):
    hass.states.set(
        "climate.woonkamer_airco", "cool", {"hvac_action": "cooling"}
    )
    coordinator = make_coordinator(_base_config())

    assert coordinator._get_current_airco_state_label() == "koelen"


def test_airco_state_off(make_coordinator, hass):
    hass.states.set(
        "climate.woonkamer_airco", "heat", {"hvac_action": "idle"}
    )
    coordinator = make_coordinator(_base_config())

    assert coordinator._get_current_airco_state_label() == "uit"


def test_airco_state_unknown_without_entity(make_coordinator, hass):
    coordinator = make_coordinator({})

    assert coordinator._get_current_airco_state_label() == "onbekend"


def test_reads_live_outdoor_temp_from_knmi(make_coordinator, hass):
    hass.states.set("weather.knmi", "sunny", {"temperature": 8.5})
    coordinator = make_coordinator(_base_config())

    assert coordinator._get_live_outdoor_temp_c() == 8.5


def test_falls_back_to_openweathermap(make_coordinator, hass):
    hass.states.set("weather.owm", "sunny", {"temperature": 9.5})
    coordinator = make_coordinator(
        {"openweathermap_weather_entity": "weather.owm"}
    )

    assert coordinator._get_live_outdoor_temp_c() == 9.5


def test_first_tick_only_seeds(make_coordinator, hass):
    _seed_common(hass, temp="19.0")
    coordinator = make_coordinator(_base_config())

    coordinator._update_climate_rate_learning(DAY0)

    assert coordinator.climate_rate_history == {}


def test_learns_a_rate_from_two_ticks(make_coordinator, hass):
    _seed_common(hass, temp="19.0", outdoor="10.0", shutter1="closed", shutter2="closed")
    coordinator = make_coordinator(_base_config())
    hass.states.set(
        "climate.woonkamer_airco", "heat", {"hvac_action": "idle"}
    )

    coordinator._update_climate_rate_learning(DAY0)

    hass.states.set("sensor.living_room_temp", "20.0")  # +1C over 1 hour
    coordinator._update_climate_rate_learning(DAY0 + timedelta(hours=1))

    key = coordinator._climate_rate_key("10.0", "beide_dicht", "uit")
    assert coordinator.climate_rate_history[key] == [1.0]


def test_no_sample_recorded_without_shutter_data(make_coordinator, hass):
    hass.states.set("sensor.living_room_temp", "19.0")
    hass.states.set("weather.knmi", "sunny", {"temperature": 10.0})
    coordinator = make_coordinator(
        {
            "living_room_temperature_sensor_entity": "sensor.living_room_temp",
            "knmi_weather_entity": "weather.knmi",
        }
    )

    coordinator._update_climate_rate_learning(DAY0)
    hass.states.set("sensor.living_room_temp", "20.0")
    coordinator._update_climate_rate_learning(DAY0 + timedelta(hours=1))

    assert coordinator.climate_rate_history == {}


def test_stale_gap_not_counted(make_coordinator, hass):
    _seed_common(hass, temp="19.0")
    coordinator = make_coordinator(_base_config())

    coordinator._update_climate_rate_learning(DAY0)
    hass.states.set("sensor.living_room_temp", "25.0")
    coordinator._update_climate_rate_learning(DAY0 + timedelta(hours=4))

    assert coordinator.climate_rate_history == {}


def test_rate_history_bounded(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    for i in range(30):
        _seed_common(hass, temp=str(19.0 + i * 0.1))
        coordinator._update_climate_rate_learning(DAY0 + timedelta(hours=i))

    from custom_components.energy_management_system.const import (
        CLIMATE_RATE_HISTORY_LENGTH,
    )

    key = coordinator._climate_rate_key("10.0", "beide_dicht", "uit")
    assert len(coordinator.climate_rate_history.get(key, [])) <= (
        CLIMATE_RATE_HISTORY_LENGTH
    )


def test_get_climate_rate_not_enough_data(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())

    result = coordinator.get_climate_rate("10.0", "beide_dicht", "uit")

    assert result["voldoende_data"] is False
    assert result["rate_c_per_hour"] is None


def test_fetch_forecast_returns_none_without_a_service_response(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())

    result = asyncio.run(
        coordinator._async_fetch_hourly_outdoor_forecast("weather.knmi")
    )

    assert result is None


def test_fetch_forecast_converts_datetimes_to_local_time(make_coordinator, hass):
    """v0.63.93, reported: switching to a UTC-timestamped weather
    entity (weather.forecast_thuis) instead of one that happened to
    already report local time (weather.knmi_thuis) would have exposed
    a 2-hour display offset if the fetch didn't explicitly convert to
    local time. Verifies the conversion call actually happens for
    every parsed forecast entry, regardless of which timezone the
    source data uses - not something that should only work by
    coincidence for one specific weather integration."""
    from custom_components.energy_management_system import coordinator as coord_mod

    coordinator = make_coordinator(_base_config())
    hass.services.set_response(
        "weather",
        "get_forecasts",
        {
            "weather.knmi": {
                "forecast": [
                    {"datetime": "2026-08-06T05:00:00+00:00", "temperature": 15.9},
                    {"datetime": "2026-08-06T06:00:00+00:00", "temperature": 17.1},
                ]
            }
        },
    )

    calls = []
    original_as_local = coord_mod.dt_util.as_local

    def spy_as_local(value):
        calls.append(value)
        return original_as_local(value)

    coord_mod.dt_util.as_local = spy_as_local
    try:
        result = asyncio.run(
            coordinator._async_fetch_hourly_outdoor_forecast("weather.knmi")
        )
    finally:
        coord_mod.dt_util.as_local = original_as_local

    assert len(calls) == 2
    assert len(result) == 2


def test_fetch_forecast_parses_a_valid_response(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.services.set_response(
        "weather",
        "get_forecasts",
        {
            "weather.knmi": {
                "forecast": [
                    {"datetime": "2026-04-01T13:00:00+00:00", "temperature": 11.0},
                    {"datetime": "2026-04-01T14:00:00+00:00", "temperature": 12.0},
                ]
            }
        },
    )

    result = asyncio.run(
        coordinator._async_fetch_hourly_outdoor_forecast("weather.knmi")
    )

    assert len(result) == 2
    assert result[0][1] == 11.0


def test_fetch_forecast_handles_a_broken_service_gracefully(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())

    async def broken_call(*a, **k):
        raise RuntimeError("boom")

    hass.services.async_call = broken_call

    result = asyncio.run(
        coordinator._async_fetch_hourly_outdoor_forecast("weather.knmi")
    )

    assert result is None


def test_forecast_projection_without_temp_sensor(make_coordinator, hass):
    coordinator = make_coordinator({})

    asyncio.run(coordinator._async_update_climate_forecast(DAY0))

    assert coordinator.climate_forecast_trajectory == []
    assert "living_room_temperature_sensor_entity" in coordinator.climate_forecast_note


def test_forecast_projection_without_weather_entity(make_coordinator, hass):
    hass.states.set("sensor.living_room_temp", "19.0")
    coordinator = make_coordinator(
        {"living_room_temperature_sensor_entity": "sensor.living_room_temp"}
    )
    coordinator.living_room_current_temp_c = 19.0  # normally set by the airco predictor

    asyncio.run(coordinator._async_update_climate_forecast(DAY0))

    assert coordinator.climate_forecast_trajectory == []
    assert "weather" in coordinator.climate_forecast_note.lower()


def test_forecast_projection_walks_forward_using_learned_rates(make_coordinator, hass):
    _seed_common(hass, temp="19.0", outdoor="10.0", shutter1="closed", shutter2="closed")
    coordinator = make_coordinator(_base_config())
    hass.states.set("climate.woonkamer_airco", "heat", {"hvac_action": "idle"})

    # 6 samples clears CLIMATE_RATE_MIN_SAMPLES (5, "indicatief") but not
    # CLIMATE_RATE_RELIABLE_SAMPLES (15, "betrouwbaar").
    key = coordinator._climate_rate_key("10.0", "beide_dicht", "uit")
    coordinator.climate_rate_history[key] = [0.5] * 6
    coordinator.climate_shutter_state = "beide_dicht"
    coordinator.climate_airco_state = "uit"
    coordinator.living_room_current_temp_c = 19.0

    hass.services.set_response(
        "weather",
        "get_forecasts",
        {
            "weather.knmi": {
                "forecast": [
                    {"datetime": "2026-04-01T13:00:00+00:00", "temperature": 10.0},
                    {"datetime": "2026-04-01T14:00:00+00:00", "temperature": 10.0},
                ]
            }
        },
    )

    asyncio.run(coordinator._async_update_climate_forecast(DAY0))

    trajectory = coordinator.climate_forecast_trajectory
    assert len(trajectory) == 2
    # "indicatief" tier - kort_termijn applies the rate...
    assert trajectory[0]["kort_termijn_temp_c"] == 19.5
    assert trajectory[1]["kort_termijn_temp_c"] == 20.0
    # ...but betrouwbaar (needs 15 samples) doesn't, and carries forward.
    assert trajectory[0]["betrouwbaar_temp_c"] == 19.0
    assert trajectory[1]["betrouwbaar_temp_c"] == 19.0
    assert trajectory[0]["betrouwbaarheid"] == "indicatief"


def test_forecast_projection_reaches_betrouwbaar_tier_with_enough_samples(
    make_coordinator, hass
):
    _seed_common(hass, temp="19.0", outdoor="10.0", shutter1="closed", shutter2="closed")
    coordinator = make_coordinator(_base_config())
    hass.states.set("climate.woonkamer_airco", "heat", {"hvac_action": "idle"})

    key = coordinator._climate_rate_key("10.0", "beide_dicht", "uit")
    coordinator.climate_rate_history[key] = [0.5] * 15  # meets the reliable threshold
    coordinator.climate_shutter_state = "beide_dicht"
    coordinator.climate_airco_state = "uit"
    coordinator.living_room_current_temp_c = 19.0

    hass.services.set_response(
        "weather",
        "get_forecasts",
        {
            "weather.knmi": {
                "forecast": [
                    {"datetime": "2026-04-01T13:00:00+00:00", "temperature": 10.0},
                ]
            }
        },
    )

    asyncio.run(coordinator._async_update_climate_forecast(DAY0))

    trajectory = coordinator.climate_forecast_trajectory
    assert trajectory[0]["betrouwbaar_temp_c"] == 19.5
    assert trajectory[0]["kort_termijn_temp_c"] == 19.5
    assert trajectory[0]["betrouwbaarheid"] == "betrouwbaar"


def test_forecast_projection_carries_forward_when_insufficient_data(
    make_coordinator, hass
):
    """An hour with no learned rate for that cell shouldn't guess - both
    series should just carry forward unchanged, flagged."""
    _seed_common(hass, temp="19.0", outdoor="10.0", shutter1="closed", shutter2="closed")
    coordinator = make_coordinator(_base_config())
    hass.states.set("climate.woonkamer_airco", "heat", {"hvac_action": "idle"})
    coordinator.climate_shutter_state = "beide_dicht"
    coordinator.climate_airco_state = "uit"
    coordinator.living_room_current_temp_c = 19.0

    hass.services.set_response(
        "weather",
        "get_forecasts",
        {
            "weather.knmi": {
                "forecast": [
                    {"datetime": "2026-04-01T13:00:00+00:00", "temperature": 10.0},
                ]
            }
        },
    )

    asyncio.run(coordinator._async_update_climate_forecast(DAY0))

    trajectory = coordinator.climate_forecast_trajectory
    assert trajectory[0]["kort_termijn_temp_c"] == 19.0
    assert trajectory[0]["betrouwbaar_temp_c"] == 19.0
    assert trajectory[0]["betrouwbaarheid"] == "onvoldoende_data"


def test_forecast_is_throttled(make_coordinator, hass):
    _seed_common(hass, temp="19.0", outdoor="10.0")
    coordinator = make_coordinator(_base_config())
    hass.services.set_response(
        "weather",
        "get_forecasts",
        {
            "weather.knmi": {
                "forecast": [
                    {"datetime": "2026-04-01T13:00:00+00:00", "temperature": 10.0},
                ]
            }
        },
    )

    asyncio.run(coordinator._async_update_climate_forecast(DAY0))
    first_call_count = len(hass.services.calls)

    asyncio.run(
        coordinator._async_update_climate_forecast(DAY0 + timedelta(minutes=5))
    )

    assert len(hass.services.calls) == first_call_count


def test_never_touches_the_battery(make_coordinator, hass):
    _seed_common(hass, temp="19.0", outdoor="10.0")
    coordinator = make_coordinator(_base_config())

    coordinator._update_climate_rate_learning(DAY0)
    asyncio.run(coordinator._async_update_climate_forecast(DAY0))

    non_weather_calls = [c for c in hass.services.calls if c[0] != "weather"]
    assert non_weather_calls == []


def test_trajectory_re_anchors_to_a_new_measurement_within_the_fetch_throttle(
    make_coordinator, hass
):
    """v0.63.58, requested ('correctie op de actueel gemeten waarde'):
    even though the outdoor forecast fetch is throttled to 30 min, the
    projection itself must still re-walk from whatever the CURRENT
    living room temperature is on every call - not stay frozen at
    whatever it was when the forecast was last fetched."""
    _seed_common(hass, temp="19.0", outdoor="10.0", shutter1="closed", shutter2="closed")
    coordinator = make_coordinator(_base_config())
    coordinator.living_room_current_temp_c = 19.0
    hass.services.set_response(
        "weather",
        "get_forecasts",
        {
            "weather.knmi": {
                "forecast": [
                    {"datetime": "2026-04-01T13:00:00+00:00", "temperature": 10.0},
                ]
            }
        },
    )

    asyncio.run(coordinator._async_update_climate_forecast(DAY0))
    assert coordinator.climate_forecast_trajectory[0]["kort_termijn_temp_c"] == 19.0

    # The room measurably warmed up a few minutes later - still well
    # within the 30-minute fetch throttle window.
    hass.states.set("sensor.living_room_temp", "21.0")
    coordinator.living_room_current_temp_c = 21.0
    fetch_call_count_before = len(hass.services.calls)

    asyncio.run(
        coordinator._async_update_climate_forecast(DAY0 + timedelta(minutes=5))
    )

    # No new fetch happened (still throttled)...
    assert len(hass.services.calls) == fetch_call_count_before
    # ...but the trajectory re-anchored to the new measurement anyway.
    assert coordinator.climate_forecast_trajectory[0]["kort_termijn_temp_c"] == 21.0


def test_live_temperature_rounded_to_one_decimal(make_coordinator, hass):
    """v0.63.92, reported with a screenshot: the live living-room
    temperature displayed with excessive precision
    (24.1230773925781°C) on the dashboard, unlike the outdoor
    temperature (already rounded via the weather entity). The
    underlying sensor itself reports at high precision (e.g. a Zigbee
    sensor) - must be rounded to 1 decimal, consistent with every
    other temperature display in this integration."""
    hass.states.set("sensor.living_room_temp", "24.1230773925781")
    coordinator = make_coordinator(
        {"living_room_temperature_sensor_entity": "sensor.living_room_temp"}
    )

    coordinator._update_living_room_airco_prediction(DAY0)

    assert coordinator.living_room_current_temp_c == 24.1
