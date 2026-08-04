"""Trend ('Verschil') data must not reset to unavailable on every
restart (v0.56.1). Only the averaged value per hour is persisted, not
the raw sample history - so a naive single-value restore left
previous_hourly_avg_kw / previous_pv_hourly_ratio with nothing to
compare against until new samples came in, showing "-" in the dashboard
right after every restart.
"""
import asyncio

import pytest


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


def test_hourly_consumption_profile_fallback_restore_needs_two_new_samples_for_trend(
    make_coordinator,
):
    """With the pre-v0.60.1 fallback restore (duplicates the single
    restored value twice - see HourlyConsumptionProfileSensor), one new
    real sample alone isn't enough to move the *median* (v0.62.0): the
    duplicated old value holds a 2-vote majority against the single new
    one. This differs from the old mean-based behaviour, where one
    sample was already enough. A second new sample breaks the tie and
    the median moves - the trend still recovers, just one sample later
    than before. This one-time lag only affects state saved by a
    pre-v0.60.1 version; the current profile_history-based restore
    doesn't have this limitation (see the test below).
    """
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
    assert coordinator.learned_hourly_avg_kw(9) == 0.497  # unchanged - still 2 vs 1

    coordinator.hourly_consumption_profile[9].append(0.6)
    assert coordinator.previous_hourly_avg_kw(9) == 0.497
    assert coordinator.learned_hourly_avg_kw(9) != 0.497  # now 2 vs 2 -> moves


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


def test_hourly_consumption_profile_restores_genuine_history(make_coordinator):
    """v0.60.1: the raw per-day sample list (profile_history) restores
    intact across a restart, instead of the previous behaviour of only
    persisting the collapsed average - which meant the 'Verschil' column
    reset to +0 on every restart until enough new samples came in
    (reported live)."""
    coordinator = make_coordinator({})
    from custom_components.energy_management_system.sensor import (
        HourlyConsumptionProfileSensor,
    )

    sensor = HourlyConsumptionProfileSensor(coordinator, "entry1")

    async def get_last_state():
        return _FakeLastState(
            {
                "profile": {"9": 0.45},
                "profile_history": {"9": [0.4, 0.5]},
            }
        )

    sensor.async_get_last_state = get_last_state
    asyncio.run(sensor.async_added_to_hass())

    # The genuine pre-restart history survives, not a flat duplicate -
    # previous/current differ immediately, no waiting for a new sample.
    assert coordinator.hourly_consumption_profile[9] == [0.4, 0.5]
    assert coordinator.previous_hourly_avg_kw(9) == 0.4
    assert coordinator.learned_hourly_avg_kw(9) == pytest.approx(0.45)
    assert coordinator.previous_hourly_avg_kw(9) != coordinator.learned_hourly_avg_kw(9)


def test_hourly_consumption_profile_falls_back_without_history_attribute(
    make_coordinator,
):
    """State saved by a pre-v0.60.1 version has no profile_history -
    must still restore via the old duplication approach rather than
    losing the data entirely."""
    coordinator = make_coordinator({})
    from custom_components.energy_management_system.sensor import (
        HourlyConsumptionProfileSensor,
    )

    sensor = HourlyConsumptionProfileSensor(coordinator, "entry1")

    async def get_last_state():
        return _FakeLastState({"profile": {"9": 0.497}})

    sensor.async_get_last_state = get_last_state
    asyncio.run(sensor.async_added_to_hass())

    assert coordinator.hourly_consumption_profile[9] == [0.497, 0.497]


def test_pv_hourly_bias_restores_genuine_history(make_coordinator):
    coordinator = make_coordinator({})
    from custom_components.energy_management_system.sensor import (
        PvHourlyBiasSensor,
    )

    sensor = PvHourlyBiasSensor(coordinator, "entry1")

    async def get_last_state():
        return _FakeLastState(
            {
                "profile": {"9": 0.31},
                "profile_history": {"9": [0.25, 0.284, 0.31]},
            }
        )

    sensor.async_get_last_state = get_last_state
    asyncio.run(sensor.async_added_to_hass())

    assert coordinator.pv_hourly_bias_history[9] == [0.25, 0.284, 0.31]
    assert coordinator.previous_pv_hourly_ratio(9) == pytest.approx((0.25 + 0.284) / 2)


def test_in_progress_hour_survives_a_restart(make_coordinator, hass):
    """v0.63.16: without this, a restart mid-hour silently discards
    whatever of the current hour had already been sampled - with
    frequent restarts, a genuinely new sample might never land at all,
    leaving 'Verschil' at +0 indefinitely rather than just briefly."""
    from datetime import datetime, timedelta, timezone

    from custom_components.energy_management_system.sensor import (
        HourlyConsumptionProfileSensor,
    )

    coordinator = make_coordinator({"consumption_power_sensor_entity": "sensor.p1"})
    hass.states.set("sensor.p1", "300")

    now = datetime(2026, 8, 4, 14, 0, 0, tzinfo=timezone.utc)
    coordinator._update_hourly_consumption_profile(now)  # first tick, seeds tracker
    now2 = now + timedelta(minutes=20)
    coordinator._update_hourly_consumption_profile(now2)  # 20 min accumulated at 300W

    # Simulate a restart: a fresh sensor restores from the saved attrs.
    sensor = HourlyConsumptionProfileSensor(coordinator, "entry1")
    saved_attrs = sensor.extra_state_attributes

    fresh_coordinator = make_coordinator(
        {"consumption_power_sensor_entity": "sensor.p1"}
    )
    fresh_sensor = HourlyConsumptionProfileSensor(fresh_coordinator, "entry1")

    async def get_last_state():
        return _FakeLastState(saved_attrs)

    fresh_sensor.async_get_last_state = get_last_state
    asyncio.run(fresh_sensor.async_added_to_hass())

    assert fresh_coordinator._current_tracked_hour == 14
    assert fresh_coordinator._hour_duration_hours == pytest.approx(20 / 60, abs=0.01)

    # Cross into the next hour via realistic 5-minute ticks (not one big
    # jump - a jump bigger than MAX_HOUR_TRACKING_GAP_MINUTES would (and
    # should) trip the staleness guard tested separately below). The
    # finalized sample should reflect the restored 20 minutes plus
    # whatever ran after the "restart".
    tick = now2
    while tick < datetime(2026, 8, 4, 15, 5, 0, tzinfo=timezone.utc):
        tick += timedelta(minutes=5)
        fresh_coordinator._update_hourly_consumption_profile(tick)

    assert fresh_coordinator.hourly_consumption_profile.get(14)


def test_in_progress_hour_discarded_after_a_long_gap(make_coordinator, hass):
    """A genuine long outage (not a quick restart) shouldn't attribute
    the whole gap to a single power level - the stale progress is
    discarded instead of restored."""
    from datetime import datetime, timedelta, timezone

    from custom_components.energy_management_system.sensor import (
        HourlyConsumptionProfileSensor,
    )

    coordinator = make_coordinator({"consumption_power_sensor_entity": "sensor.p1"})
    hass.states.set("sensor.p1", "300")

    stale_saved_attrs = {
        "profile_history": {},
        "in_progress": {
            "hour": 10,
            "energy_kwh": 0.5,
            "duration_hours": 1.0,
            "last_sample": datetime(
                2026, 8, 4, 10, 30, 0, tzinfo=timezone.utc
            ).isoformat(),
        },
    }
    sensor = HourlyConsumptionProfileSensor(coordinator, "entry1")

    async def get_last_state():
        return _FakeLastState(stale_saved_attrs)

    sensor.async_get_last_state = get_last_state
    asyncio.run(sensor.async_added_to_hass())

    # Restored, but the *next* tick is hours later - the gap guard in
    # _update_hourly_consumption_profile should discard it rather than
    # attributing a multi-hour gap to a single power reading.
    much_later = datetime(2026, 8, 4, 16, 0, 0, tzinfo=timezone.utc)
    coordinator._update_hourly_consumption_profile(much_later)

    assert coordinator._hour_energy_kwh == 0.0
    assert coordinator._hour_duration_hours == 0.0
    assert coordinator._current_tracked_hour == 16
