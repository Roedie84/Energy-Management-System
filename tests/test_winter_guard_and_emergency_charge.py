"""Winter guard (v0.27.0) and emergency low-battery charge (v0.28.1 /
v0.29.0), including the fix that scopes emergency charging to a
low-solar (winter) expectation only.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from conftest import make_price_forecast

DAY0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _flat_price_with_cheap_block(hour, minute):
    if 9 <= hour < 12:
        return 1_300_000
    return 2_500_000


def test_grid_charged_today_suppresses_same_day_expensive_discharge(
    make_coordinator, hass
):
    """If the battery force-charged from the grid today (low solar), it
    should not also manual-discharge at high prices that same day - and
    the very next day it should work normally again."""
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.solcast", "2.0")  # low solar -> triggers grid charging
    hass.states.set("sensor.p1", "200")

    coordinator = make_coordinator(
        {
            "price_sensor_entity": "sensor.price",
            "price_attribute": "price_tax_included",
            "operation_select_entity": "select.op",
            "manual_power_number_entity": "number.pow",
            "manual_discharge_power": 1600,
            "manual_charge_power": -2000,
            "solar_forecast_sensor_entity": "sensor.solcast",
            "consumption_power_sensor_entity": "sensor.p1",
            "low_solar_threshold_kwh": 5.0,
        }
    )

    async def run():
        # During the cheap block, with low solar expected -> grid charge.
        with_now(coordinator, DAY0.replace(hour=10, minute=0))
        await coordinator._async_update_locked()
        assert coordinator.last_reason == "grid_charging_low_solar"
        assert coordinator._grid_charged_today is True

        # Later the same evening, an expensive quarter arrives - should
        # NOT manual-discharge (selling grid-bought energy at a loss).
        with_now(coordinator, DAY0.replace(hour=19, minute=15))
        await coordinator._async_update_locked()
        assert coordinator.last_reason != "expensive_quarter"

        # The next day, a fresh expensive quarter should work normally.
        day1 = DAY0 + timedelta(days=1)
        forecast2 = make_price_forecast(day1, _flat_price_with_cheap_block)
        hass.states.set("sensor.price", "0", {"forecast": forecast2})
        with_now(coordinator, day1.replace(hour=19, minute=15))
        await coordinator._async_update_locked()
        assert coordinator.last_reason == "expensive_quarter"

    asyncio.run(run())


def test_winter_guard_suppression_flag_visible_in_diagnostics(make_coordinator, hass):
    """The v0.60.0 diagnostic flag mirrors the suppression itself: set
    for the rest of the day it happens, cleared again the next day."""
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.solcast", "2.0")
    hass.states.set("sensor.p1", "200")

    coordinator = make_coordinator(
        {
            "price_sensor_entity": "sensor.price",
            "price_attribute": "price_tax_included",
            "operation_select_entity": "select.op",
            "manual_power_number_entity": "number.pow",
            "manual_discharge_power": 1600,
            "manual_charge_power": -2000,
            "solar_forecast_sensor_entity": "sensor.solcast",
            "consumption_power_sensor_entity": "sensor.p1",
            "low_solar_threshold_kwh": 5.0,
        }
    )

    async def run():
        with_now(coordinator, DAY0.replace(hour=10, minute=0))
        await coordinator._async_update_locked()
        assert coordinator.last_winter_guard_suppressed_today is False

        with_now(coordinator, DAY0.replace(hour=19, minute=15))
        await coordinator._async_update_locked()
        assert coordinator.last_winter_guard_suppressed_today is True

        day1 = DAY0 + timedelta(days=1)
        forecast2 = make_price_forecast(day1, _flat_price_with_cheap_block)
        hass.states.set("sensor.price", "0", {"forecast": forecast2})
        with_now(coordinator, day1.replace(hour=8, minute=0))
        await coordinator._async_update_locked()
        assert coordinator.last_winter_guard_suppressed_today is False

    asyncio.run(run())


def test_emergency_charge_only_when_low_solar_expected(make_coordinator, hass):
    """A critically low SoC should trigger emergency grid-charging only
    when little solar is expected (winter scenario) - not when solar is
    abundant (summer), where letting it run low and refill is preferred.
    """
    hass.states.set("sensor.soc", "7")  # critically low in both cases

    config_base = {
        "battery_soc_sensor_entity": "sensor.soc",
        "min_soc_percent": 15,
        "solar_forecast_sensor_entity": "sensor.solcast",
        "low_solar_threshold_kwh": 5.0,
    }

    # Summer: abundant solar forecast -> no emergency charge.
    hass.states.set("sensor.solcast", "20.0")
    coordinator_summer = make_coordinator(config_base)
    assert coordinator_summer._is_emergency_low_battery() is False

    # Winter: little solar forecast -> emergency charge should trigger.
    hass.states.set("sensor.solcast", "2.0")
    coordinator_winter = make_coordinator(config_base)
    assert coordinator_winter._is_emergency_low_battery() is True


def with_now(coordinator, when: datetime) -> None:
    """Patch dt_util.now() used inside the coordinator module for this test."""
    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: when
