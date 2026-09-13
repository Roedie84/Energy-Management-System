"""ModelTrendInsightSensor (v0.63.88): bundelt de trend van drie nieuwe
metrics uit deze release - gevraagd: "inzicht zien op het dashboard met
trends... en of het model/parameter nauwkeuriger wordt".
"""


def test_exposes_trends_for_all_three_metrics(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        ModelTrendInsightSensor,
    )
    from custom_components.energy_management_system.solar_forecast import (
        SolarForecastAccuracyTracker,
    )

    coordinator = make_coordinator({})
    coordinator.solar_tracker = SolarForecastAccuracyTracker(hass, {})
    coordinator.solar_tracker.deviation_stdev_history = [20.0, 18.0, 16.0, 14.0, 12.0]
    coordinator.extra_dip_margin_history = [0.05, 0.06, 0.07, 0.08]
    coordinator.temp_consumption_prediction_error_history = [15.0, 12.0, 10.0, 8.0]
    coordinator.last_temp_consumption_note = "Voorspeld 5.0 kWh, werkelijk 5.2 kWh"

    sensor = ModelTrendInsightSensor(coordinator, "entry1")
    attrs = sensor.extra_state_attributes

    assert attrs["zon_voorspelling_spreiding_trend"]["richting"] == "dalend"
    assert attrs["extra_dip_marge_trend"]["richting"] == "stijgend"
    assert attrs["temperatuur_regressie_nauwkeurigheid_trend"]["richting"] == "dalend"
    assert sensor.native_value == "Voorspeld 5.0 kWh, werkelijk 5.2 kWh"


def test_restores_all_histories_after_restart(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        ModelTrendInsightSensor,
    )

    coordinator = make_coordinator({})
    sensor = ModelTrendInsightSensor(coordinator, "entry1")

    class _FakeLastState:
        attributes = {
            "temperatuur_regressie_paren": [{"temp_c": -3.0, "kwh": 6.0}],
            "temperatuur_regressie_note": "Voorspeld 6.0 kWh",
            "temperatuur_regressie_nauwkeurigheid_geschiedenis": [10.0, 8.0],
            "extra_dip_marge_eur_per_kwh": 0.07,
            "extra_dip_marge_geschiedenis": [0.05, 0.06, 0.07],
        }

    async def get_last_state():
        return _FakeLastState()

    sensor.async_get_last_state = get_last_state

    import asyncio

    asyncio.run(sensor.async_added_to_hass())

    assert coordinator.temp_consumption_history == [{"temp_c": -3.0, "kwh": 6.0}]
    assert coordinator.last_temp_consumption_note == "Voorspeld 6.0 kWh"
    assert coordinator.temp_consumption_prediction_error_history == [10.0, 8.0]
    assert coordinator.last_extra_dip_margin_eur_per_kwh == 0.07
    assert coordinator.extra_dip_margin_history == [0.05, 0.06, 0.07]


def test_deviation_stdev_history_restored_via_pv_forecast_sensor(make_coordinator, hass):
    """The spread history piggybacks on the existing PvForecastAccuracySensor
    restore path, alongside deviation_history itself."""
    from custom_components.energy_management_system.sensor import (
        PvForecastAccuracySensor,
    )
    from custom_components.energy_management_system.solar_forecast import (
        SolarForecastAccuracyTracker,
    )

    tracker = SolarForecastAccuracyTracker(hass, {})
    sensor = PvForecastAccuracySensor(tracker, "entry1")

    class _FakeLastState:
        state = "5.0"
        attributes = {
            "deviation_history": [1.0, 2.0],
            "deviation_stdev_history": [15.0, 14.0, 13.0],
        }

    async def get_last_state():
        return _FakeLastState()

    sensor.async_get_last_state = get_last_state
    sensor.async_write_ha_state = lambda: None

    import asyncio

    asyncio.run(sensor.async_added_to_hass())

    assert tracker.deviation_stdev_history == [15.0, 14.0, 13.0]
