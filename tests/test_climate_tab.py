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

    assert coordinator._get_live_outdoor_temp_c(DAY0) == 8.5


def test_falls_back_to_openweathermap(make_coordinator, hass):
    hass.states.set("weather.owm", "sunny", {"temperature": 9.5})
    coordinator = make_coordinator(
        {"openweathermap_weather_entity": "weather.owm"}
    )

    assert coordinator._get_live_outdoor_temp_c(DAY0) == 9.5


def test_backyard_sensor_preferred_over_weather_entities(make_coordinator, hass):
    """v0.63.95, gevraagd: "zijn er zaken waardoor ik de voorspelling
    kan verbeteren" - een eigen achtertuinsensor is nauwkeuriger voor
    de eigen locatie dan een regionale weerentiteit-schatting, en moet
    daarom als voorkeursbron gelden."""
    hass.states.set("weather.knmi", "sunny", {"temperature": 23.0})
    hass.states.set("sensor.achtertuin_temp", "15.3")
    coordinator = make_coordinator(
        _base_config(backyard_temperature_sensor_entity="sensor.achtertuin_temp")
    )

    assert coordinator._get_live_outdoor_temp_c(DAY0) == 15.3


def test_falls_back_to_weather_entity_without_backyard_reading(make_coordinator, hass):
    hass.states.set("weather.knmi", "sunny", {"temperature": 23.0})
    coordinator = make_coordinator(
        _base_config(backyard_temperature_sensor_entity="sensor.achtertuin_temp")
    )
    # backyard sensor not set up at all - should fall through cleanly

    assert coordinator._get_live_outdoor_temp_c(DAY0) == 23.0


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

    # v3.41.0: de cel sleutelt op het VERSCHIL met binnen, niet op de
    # buitentemperatuur. Buiten 10, binnen 19 bij het anker: verschil -9,
    # dus vakje -10 bij stappen van twee graden.
    verschil = coordinator._climate_verschil_bucket(10.0, 19.0)
    key = coordinator._climate_rate_key(verschil, "beide_dicht", "uit")
    assert coordinator.climate_rate_history[key] == [1.0]


def test_the_bucket_follows_the_difference_not_the_outdoor_temp(
    make_coordinator, hass
):
    """De aanleiding: bij 26 graden buiten warmt een kamer van 21 op en

    koelt een kamer van 28 af. Zelfde emmer, tegengesteld teken - en dat
    stond ook zo in de gemeten reeks:

        26.0|beide_open|uit: [-0.284, +0.137, -0.067, +0.009, -0.156]
    """
    c = make_coordinator(_base_config())

    warm = c._climate_verschil_bucket(26.0, 21.0)
    koel = c._climate_verschil_bucket(26.0, 28.0)

    assert warm != koel
    assert warm.startswith("d")


def test_old_cells_are_thrown_away(make_coordinator, hass):
    """De oude sleutels zijn niet om te rekenen: de binnentemperatuur van

    dat moment is niet bewaard. Ze laten staan zou twee soorten sleutels
    naast elkaar geven waarvan de helft nooit meer gelezen wordt.
    """
    c = make_coordinator(_base_config())
    c.climate_rate_history = {
        "26.0|beide_open|uit": [-0.284, 0.137],
        "d-4.0|beide_dicht|uit": [-0.1],
    }

    c._ruim_oude_klimaatcellen_op()

    assert list(c.climate_rate_history) == ["d-4.0|beide_dicht|uit"]


def test_a_cell_that_disagrees_with_itself_is_not_learned(
    make_coordinator, hass
):
    """Ook met de juiste sleutel blijft een cel waarin de helft opwarmt

    en de helft afkoelt onbruikbaar - dan vangt hij nog iets anders,
    bijvoorbeeld de zon op het raam.
    """
    c = make_coordinator(_base_config())
    key = c._climate_rate_key("d4.0", "beide_open", "uit")
    # v3.42.2: met een mediaan ruim boven het omslagpunt. Bij een mediaan
    # rond nul is tekenwisseling juist te verwachten - zie de toets
    # hieronder.
    c.climate_rate_history = {key: [-0.42, 0.14, -0.51, -0.38, -0.47]}

    oordeel = c.get_climate_rate("d4.0", "beide_open", "uit")

    assert oordeel["eenduidig"] is False
    assert oordeel["betrouwbaarheid"] == "niet_eenduidig"
    assert oordeel["voldoende_data"] is False


def test_a_cell_that_agrees_is_learned(make_coordinator, hass):
    c = make_coordinator(_base_config())
    key = c._climate_rate_key("d-6.0", "beide_dicht", "uit")
    c.climate_rate_history = {key: [-0.10, -0.12, -0.05, -0.17, -0.20]}

    oordeel = c.get_climate_rate("d-6.0", "beide_dicht", "uit")

    assert oordeel["eenduidig"] is True
    assert oordeel["voldoende_data"] is True
    assert oordeel["rate_c_per_hour"] == -0.12


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
    # v3.47.0: de cel hoort bij het VERSCHIL tussen buiten (10) en de
    # kamer (19), dus vakje d-8.0.
    verschil = coordinator._climate_verschil_bucket(10.0, 19.0)
    key = coordinator._climate_rate_key(verschil, "beide_dicht", "uit")
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

    # v3.41.0: de cel hoort bij het verschil tussen buiten (10) en de
    # kamer zoals die er in de projectie voor staat (19).
    verschil = coordinator._climate_verschil_bucket(10.0, 19.0)
    key = coordinator._climate_rate_key(verschil, "beide_dicht", "uit")
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
    assert trajectory[0]["betrouwbaarheid_streng"] == "betrouwbaar"


def test_indicatief_cell_shows_onvoldoende_data_in_the_strict_field(
    make_coordinator, hass
):
    """v0.63.94, reported with a screenshot: 'de 2 tabellen lijken
    hetzelfde weer te geven' - both dashboard tables read the same
    single 'betrouwbaarheid' field, so a cell with only 8 samples
    (enough for the lenient 'indicatief' tier, ≥5, but not the strict
    'betrouwbaar' tier, ≥15) showed "indicatief" in BOTH tables,
    including the one that promises ≥15 measurements. The new
    'betrouwbaarheid_streng' field must show 'onvoldoende_data' here -
    never 'indicatief', which would still give the wrong impression in
    the strict table."""
    _seed_common(hass, temp="19.0", outdoor="10.0", shutter1="closed", shutter2="closed")
    coordinator = make_coordinator(_base_config())
    hass.states.set("climate.woonkamer_airco", "heat", {"hvac_action": "idle"})

    # v3.47.0: de cel hoort bij het VERSCHIL. Binnen 19, buiten 10 geeft
    # -9, en dat valt in vakje d-8.0.
    verschil = coordinator._climate_verschil_bucket(10.0, 19.0)
    key = coordinator._climate_rate_key(verschil, "beide_dicht", "uit")
    coordinator.climate_rate_history[key] = [0.5] * 8  # indicatief, not betrouwbaar
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
    assert trajectory[0]["betrouwbaarheid"] == "indicatief"
    assert trajectory[0]["betrouwbaarheid_streng"] == "onvoldoende_data"


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


def test_bias_sample_recorded_when_backyard_sensor_configured(make_coordinator, hass):
    """v0.63.95, gevraagd: "zijn er zaken waardoor ik de voorspelling
    kan verbeteren, door bijvoorbeeld correlaties" - elke verse
    voorspelling wordt vergeleken met de actuele achtertuinsensor-
    meting, en het verschil wordt bijgehouden."""
    hass.states.set("sensor.achtertuin_temp", "15.3")
    coordinator = make_coordinator(
        _base_config(backyard_temperature_sensor_entity="sensor.achtertuin_temp")
    )
    hass.services.set_response(
        "weather",
        "get_forecasts",
        {
            "weather.knmi": {
                "forecast": [
                    {"datetime": "2026-04-01T13:00:00+00:00", "temperature": 23.0},
                ]
            }
        },
    )

    asyncio.run(coordinator._async_maybe_refresh_outdoor_forecast(DAY0))

    assert coordinator.climate_forecast_bias_history == [-7.7]  # 15.3 - 23.0


def test_no_bias_sample_without_backyard_sensor(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.services.set_response(
        "weather",
        "get_forecasts",
        {
            "weather.knmi": {
                "forecast": [
                    {"datetime": "2026-04-01T13:00:00+00:00", "temperature": 23.0},
                ]
            }
        },
    )

    asyncio.run(coordinator._async_maybe_refresh_outdoor_forecast(DAY0))

    assert coordinator.climate_forecast_bias_history == []


def test_learned_bias_none_without_enough_samples(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    coordinator.climate_forecast_bias_history = [-7.7, -6.5]  # fewer than min

    assert coordinator.climate_forecast_learned_bias_c is None


def test_learned_bias_is_the_average_deviation(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    coordinator.climate_forecast_bias_history = [-7.0, -8.0, -7.5, -8.5, -7.0]

    assert coordinator.climate_forecast_learned_bias_c == -7.6


def test_bias_history_capped_at_max_length(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        CLIMATE_FORECAST_BIAS_HISTORY_LENGTH,
    )

    hass.states.set("sensor.achtertuin_temp", "15.0")
    coordinator = make_coordinator(
        _base_config(backyard_temperature_sensor_entity="sensor.achtertuin_temp")
    )
    hass.services.set_response(
        "weather",
        "get_forecasts",
        {
            "weather.knmi": {
                "forecast": [
                    {"datetime": "2026-04-01T13:00:00+00:00", "temperature": 20.0},
                ]
            }
        },
    )

    now = DAY0
    for _ in range(CLIMATE_FORECAST_BIAS_HISTORY_LENGTH + 5):
        asyncio.run(coordinator._async_maybe_refresh_outdoor_forecast(now))
        now += timedelta(minutes=31)  # past the fetch throttle each time

    assert len(coordinator.climate_forecast_bias_history) == (
        CLIMATE_FORECAST_BIAS_HISTORY_LENGTH
    )


def test_bias_correction_applied_across_the_whole_trajectory(make_coordinator, hass):
    """The learned bias must shift EVERY hour's outdoor temperature in
    the projection, not just the starting point - so it also affects
    which learned rate cell gets looked up for each hour."""
    _seed_common(hass, temp="19.0", outdoor="10.0", shutter1="closed", shutter2="closed")
    coordinator = make_coordinator(_base_config())
    coordinator.climate_forecast_bias_history = [5.0] * 5  # learned +5C bias
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
    # 10.0 raw + 5.0 learned bias = 15.0 corrected
    assert trajectory[0]["buitentemp_voorspeld_c"] == 15.0


def test_backyard_spike_filter_first_reading_accepted_immediately(
    make_coordinator, hass
):
    hass.states.set("sensor.achtertuin_temp", "15.3")
    coordinator = make_coordinator(
        _base_config(backyard_temperature_sensor_entity="sensor.achtertuin_temp")
    )

    assert coordinator._get_filtered_backyard_temp_c(DAY0) == 15.3


def test_backyard_spike_filter_plausible_change_accepted(make_coordinator, hass):
    """A normal, gradual temperature change (well within the plausible
    rate) must be accepted immediately, not treated as a spike."""
    hass.states.set("sensor.achtertuin_temp", "15.0")
    coordinator = make_coordinator(
        _base_config(backyard_temperature_sensor_entity="sensor.achtertuin_temp")
    )
    coordinator._get_filtered_backyard_temp_c(DAY0)

    hass.states.set("sensor.achtertuin_temp", "16.0")  # +1C over 1 hour - plausible
    result = coordinator._get_filtered_backyard_temp_c(DAY0 + timedelta(hours=1))

    assert result == 16.0


def test_backyard_spike_filter_ignores_a_brief_sun_glare_spike(make_coordinator, hass):
    """v0.63.96, reported with a graph: the sensor briefly sits in
    direct morning sun, causing a sharp, implausible jump that later
    reverts. The filter must keep returning the last trusted value
    while the spike hasn't been sustained long enough to confirm."""
    hass.states.set("sensor.achtertuin_temp", "12.0")
    coordinator = make_coordinator(
        _base_config(backyard_temperature_sensor_entity="sensor.achtertuin_temp")
    )
    coordinator._get_filtered_backyard_temp_c(DAY0)

    # A sharp jump 5 minutes later - way beyond the plausible rate.
    hass.states.set("sensor.achtertuin_temp", "20.0")
    result = coordinator._get_filtered_backyard_temp_c(
        DAY0 + timedelta(minutes=5)
    )

    assert result == 12.0  # still the last trusted value
    assert coordinator.last_backyard_spike_filtered_note is not None

    # Brief spike reverts back down shortly after (sun moved on).
    hass.states.set("sensor.achtertuin_temp", "12.2")
    result = coordinator._get_filtered_backyard_temp_c(
        DAY0 + timedelta(minutes=10)
    )

    assert result == 12.2  # plausible change from 12.0, accepted directly


def test_backyard_spike_filter_confirms_a_sustained_change(make_coordinator, hass):
    """A jump that persists for the full confirmation window must
    eventually be trusted as a genuine change (e.g. a cold front),
    not dismissed forever as noise."""
    hass.states.set("sensor.achtertuin_temp", "12.0")
    coordinator = make_coordinator(
        _base_config(backyard_temperature_sensor_entity="sensor.achtertuin_temp")
    )
    coordinator._get_filtered_backyard_temp_c(DAY0)

    hass.states.set("sensor.achtertuin_temp", "20.0")
    # First suspicious reading - not yet trusted.
    result = coordinator._get_filtered_backyard_temp_c(
        DAY0 + timedelta(minutes=5)
    )
    assert result == 12.0

    # Same elevated reading, still within the confirmation window.
    result = coordinator._get_filtered_backyard_temp_c(
        DAY0 + timedelta(minutes=30)
    )
    assert result == 12.0

    # Same elevated reading, now past the confirmation window.
    result = coordinator._get_filtered_backyard_temp_c(
        DAY0 + timedelta(minutes=50)
    )
    assert result == 20.0


def test_backyard_spike_filter_returns_none_without_sensor_configured(
    make_coordinator, hass
):
    coordinator = make_coordinator({})

    assert coordinator._get_filtered_backyard_temp_c(DAY0) is None


def test_the_crossover_cell_is_allowed_to_flip_sign(make_coordinator, hass):
    """De eerste cel die zich vulde na de omzetting naar verschil-

    sleutels, gemeten op 20 augustus 20:43:

        d0.0|gedeeltelijk|uit  [0.394, 0.219, -0.142, -0.068, 0.045]

    Bij buiten gelijk aan binnen is het werkelijke tempo per definitie
    ongeveer nul, en dan wisselt het teken vanzelf. De toets van v3.41.0
    zou die cel ALTIJD afwijzen - niet omdat hij onbruikbaar is, maar
    omdat hij op het omslagpunt ligt. Dat was de ene cel die per
    constructie nooit kon slagen.
    """
    c = make_coordinator(_base_config())
    key = c._climate_rate_key("d0.0", "gedeeltelijk", "uit")
    c.climate_rate_history = {key: [0.394, 0.219, -0.142, -0.068, 0.045]}

    oordeel = c.get_climate_rate("d0.0", "gedeeltelijk", "uit")

    assert oordeel["eenduidig"] is True
    assert oordeel["voldoende_data"] is True
    assert abs(oordeel["rate_c_per_hour"]) < 0.1


def test_a_clear_rate_that_disagrees_is_still_refused(make_coordinator, hass):
    """De uitzondering geldt alleen rond nul. Een cel die zegt dat het

    een halve graad per uur opwarmt én afkoelt, blijft onbruikbaar.
    """
    c = make_coordinator(_base_config())
    key = c._climate_rate_key("d8.0", "beide_open", "uit")
    c.climate_rate_history = {key: [0.62, -0.55, 0.71, -0.48, 0.66]}

    oordeel = c.get_climate_rate("d8.0", "beide_open", "uit")

    assert oordeel["eenduidig"] is False
