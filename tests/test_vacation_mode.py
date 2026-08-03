"""Vacation mode (v0.46.0): scale down assumed consumption and pause
consumption-related learning, so an atypical vacation period doesn't
distort the learned "normal" household profile.
"""
import asyncio
from datetime import datetime, timezone

from conftest import make_price_forecast

DAY0 = datetime(2026, 8, 2, tzinfo=timezone.utc)


def test_vacation_mode_reduces_estimated_consumption(make_coordinator, hass):
    hass.states.set("sensor.p1", "300")
    coordinator = make_coordinator({"consumption_power_sensor_entity": "sensor.p1"})
    for hour in range(24):
        coordinator.hourly_consumption_profile[hour] = [0.3]

    start = DAY0.replace(hour=0, minute=0)
    end = DAY0.replace(hour=10, minute=0)

    normal = coordinator._estimate_consumption_kwh_for_period(start, end)

    coordinator.vacation_mode = True
    reduced = coordinator._estimate_consumption_kwh_for_period(start, end)

    # Default reduction is 60% -> only 40% of normal remains.
    assert reduced == normal * 0.4


def test_vacation_mode_pauses_consumption_learning(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, lambda h, m: 2_500_000)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "300")

    coordinator = make_coordinator(
        {
            "price_sensor_entity": "sensor.price",
            "price_attribute": "price_tax_included",
            "operation_select_entity": "select.op",
            "manual_power_number_entity": "number.pow",
            "consumption_power_sensor_entity": "sensor.p1",
        }
    )
    coordinator.vacation_mode = True

    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: DAY0.replace(hour=12, minute=0)

    before = {k: list(v) for k, v in coordinator.hourly_consumption_profile.items()}
    asyncio.run(coordinator._async_update_locked())
    after = {k: list(v) for k, v in coordinator.hourly_consumption_profile.items()}

    assert before == after, "hourly consumption profile should not change during vacation mode"


def test_vacation_mode_off_by_default(make_coordinator):
    coordinator = make_coordinator({})
    assert coordinator.vacation_mode is False
