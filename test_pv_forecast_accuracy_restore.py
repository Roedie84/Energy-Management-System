"""PvForecastAccuracySensor restore fallback (v0.63.17): restoring
last_deviation_percent from the sensor's own previous state string is
self-perpetuating once that state happens to be "unknown" (e.g. before
the first comparison ever completed) - every subsequent restart just
restores "unknown" -> None again, even once deviation_history has real
entries from later, successful daily comparisons. Falls back to the
most recent history entry instead of staying stuck.
"""
import asyncio


class _FakeLastState:
    def __init__(self, state, attributes):
        self.state = state
        self.attributes = attributes


def test_falls_back_to_history_when_last_state_was_unknown(hass):
    from custom_components.energy_management_system.sensor import (
        PvForecastAccuracySensor,
    )
    from custom_components.energy_management_system.solar_forecast import (
        SolarForecastAccuracyTracker,
    )

    tracker = SolarForecastAccuracyTracker(hass, {})
    sensor = PvForecastAccuracySensor(tracker, "entry1")

    async def get_last_state():
        return _FakeLastState(
            "unknown",
            {
                "predicted_kwh": None,
                "actual_kwh": None,
                "compared_date": None,
                "deviation_history": [-37.2, -22.1, 12.9, -9.3, -10.4, -4.5, -10.3],
            },
        )

    sensor.async_get_last_state = get_last_state
    sensor.async_write_ha_state = lambda: None
    asyncio.run(sensor.async_added_to_hass())

    assert tracker.last_deviation_percent == -10.3


def test_uses_the_real_value_when_last_state_was_a_number(hass):
    from custom_components.energy_management_system.sensor import (
        PvForecastAccuracySensor,
    )
    from custom_components.energy_management_system.solar_forecast import (
        SolarForecastAccuracyTracker,
    )

    tracker = SolarForecastAccuracyTracker(hass, {})
    sensor = PvForecastAccuracySensor(tracker, "entry1")

    async def get_last_state():
        return _FakeLastState(
            "-5.1",
            {"deviation_history": [-37.2, -22.1, -5.1]},
        )

    sensor.async_get_last_state = get_last_state
    sensor.async_write_ha_state = lambda: None
    asyncio.run(sensor.async_added_to_hass())

    assert tracker.last_deviation_percent == -5.1


def test_stays_none_without_any_history_either(hass):
    from custom_components.energy_management_system.sensor import (
        PvForecastAccuracySensor,
    )
    from custom_components.energy_management_system.solar_forecast import (
        SolarForecastAccuracyTracker,
    )

    tracker = SolarForecastAccuracyTracker(hass, {})
    sensor = PvForecastAccuracySensor(tracker, "entry1")

    async def get_last_state():
        return _FakeLastState("unknown", {"deviation_history": []})

    sensor.async_get_last_state = get_last_state
    sensor.async_write_ha_state = lambda: None
    asyncio.run(sensor.async_added_to_hass())

    assert tracker.last_deviation_percent is None
