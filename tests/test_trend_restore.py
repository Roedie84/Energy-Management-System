"""Trend ('Verschil') data must not reset to unavailable on every
restart (v0.56.1). Only the averaged value per hour is persisted, not
the raw sample history - so a naive single-value restore left
previous_hourly_avg_kw / previous_pv_hourly_ratio with nothing to
compare against until new samples came in, showing "-" in the dashboard
right after every restart.
"""
import asyncio


class _FakeLastState:
    def __init__(self, attributes):
        self.attributes = attributes


def test_hourly_consumption_profile_restore_seeds_a_comparable_previous(
    make_coordinator,
):
    coordinator = make_coordinator({})
    from custom_components.energy_management_system.sensor import (
        HourlyConsumptionProfileSensor,
    )

    sensor = HourlyConsumptionProfileSensor(coordinator, "entry1")

    async def get_last_state():
        return _FakeLastState({"profile": {"9": 0.497}})

    sensor.async_get_last_state = get_last_state
    asyncio.run(sensor.async_added_to_hass())

    # Immediately after restore, "previous" should equal "current" (a
    # real number, not None/unavailable).
    assert coordinator.learned_hourly_avg_kw(9) == 0.497
    assert coordinator.previous_hourly_avg_kw(9) == 0.497


def test_hourly_consumption_profile_shows_a_real_trend_after_one_new_sample(
    make_coordinator,
):
    coordinator = make_coordinator({})
    from custom_components.energy_management_system.sensor import (
        HourlyConsumptionProfileSensor,
    )

    sensor = HourlyConsumptionProfileSensor(coordinator, "entry1")

    async def get_last_state():
        return _FakeLastState({"profile": {"9": 0.497}})

    sensor.async_get_last_state = get_last_state
    asyncio.run(sensor.async_added_to_hass())

    coordinator.hourly_consumption_profile[9].append(0.6)

    assert coordinator.previous_hourly_avg_kw(9) == 0.497
    assert coordinator.learned_hourly_avg_kw(9) != 0.497


def test_pv_hourly_bias_restore_seeds_a_comparable_previous(make_coordinator):
    coordinator = make_coordinator({})
    from custom_components.energy_management_system.sensor import (
        PvHourlyBiasSensor,
    )

    sensor = PvHourlyBiasSensor(coordinator, "entry1")

    async def get_last_state():
        return _FakeLastState({"profile": {"9": 0.284}})

    sensor.async_get_last_state = get_last_state
    asyncio.run(sensor.async_added_to_hass())

    assert coordinator.previous_pv_hourly_ratio(9) == 0.284
