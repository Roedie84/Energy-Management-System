"""CUSUM sluipverbruik-detectie (v0.63.29): a cumulative-sum control
chart on the household's daily "floor load" (lowest corrected-
consumption reading of the day), catching a *sustained* upward drift
that the adaptive 7-day rolling median would just quietly absorb as
"the new normal".
"""
from datetime import datetime, timedelta, timezone

import pytest

DAY0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _base_config(**overrides):
    config = {"consumption_power_sensor_entity": "sensor.p1"}
    config.update(overrides)
    return config


def _run_days(coordinator, hass, loads_w, start_day=DAY0):
    """Simulate one tick per day at a fixed low-load hour, each with the
    given household load (W), to drive the daily floor-load tracker."""
    for i, load_w in enumerate(loads_w):
        hass.states.set("sensor.p1", str(load_w))
        day = start_day + timedelta(days=i)
        coordinator._update_anomaly_detection(day.replace(hour=3, minute=0))


def test_no_detection_with_insufficient_history(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    _run_days(coordinator, hass, [200] * 5)

    assert coordinator.sluipverbruik_detected is False
    assert coordinator.baseline_load_history == [0.2] * 4  # last day not yet closed out


def test_stable_load_never_triggers(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    _run_days(coordinator, hass, [200] * 20)

    assert coordinator.sluipverbruik_detected is False
    assert coordinator.cusum_accumulator_kw == 0.0


def test_sustained_drift_is_detected(make_coordinator, hass):
    """A stable baseline (200W) for 15 days, then a sustained jump to
    260W (+60W, well above the 20W slack) for several days - should
    accumulate past the alarm threshold."""
    coordinator = make_coordinator(_base_config())
    stable_days = [200] * 15
    drifted_days = [260] * 6
    _run_days(coordinator, hass, stable_days + drifted_days)

    assert coordinator.sluipverbruik_detected is True
    assert coordinator.sluipverbruik_estimated_drift_w == pytest.approx(60.0, abs=1)


def test_single_noisy_day_does_not_trigger(make_coordinator, hass):
    """One unusually high night (e.g. a guest, a late-night appliance
    cycle) at a modest +60W shouldn't alarm on its own - only a
    *sustained* shift should (a much larger single-day jump legitimately
    can and should alarm immediately, that's by design)."""
    coordinator = make_coordinator(_base_config())
    stable_days = [200] * 15
    one_spike = [260]
    back_to_normal = [200] * 3
    _run_days(coordinator, hass, stable_days + one_spike + back_to_normal)

    assert coordinator.sluipverbruik_detected is False


def test_small_deviation_within_slack_never_accumulates(make_coordinator, hass):
    """Deviations smaller than CUSUM_SLACK_KW (20W) are a deliberate
    dead zone - normal noise shouldn't slowly accumulate into a false
    alarm."""
    coordinator = make_coordinator(_base_config())
    stable_days = [200] * 15
    tiny_drift_days = [210] * 10  # +10W, below the 20W slack

    _run_days(coordinator, hass, stable_days + tiny_drift_days)

    assert coordinator.cusum_accumulator_kw == 0.0
    assert coordinator.sluipverbruik_detected is False


def test_paused_during_vacation_mode(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    coordinator.vacation_mode = True
    _run_days(coordinator, hass, [50] * 10)  # artificially low vacation load

    assert coordinator.baseline_load_history == []


def test_lower_reading_within_the_same_day_updates_the_running_minimum(
    make_coordinator, hass
):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.p1", "300")
    coordinator._update_anomaly_detection(DAY0.replace(hour=1, minute=0))
    hass.states.set("sensor.p1", "180")
    coordinator._update_anomaly_detection(DAY0.replace(hour=3, minute=0))
    hass.states.set("sensor.p1", "400")
    coordinator._update_anomaly_detection(DAY0.replace(hour=5, minute=0))

    assert coordinator._today_min_load_kw == pytest.approx(0.18)


def test_no_consumption_sensor_does_nothing(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._update_anomaly_detection(DAY0.replace(hour=3, minute=0))

    assert coordinator.baseline_load_history == []


def test_notification_sent_only_on_the_detection_edge(make_coordinator, hass):
    """Edge-triggered: notifies once when detection first flips to True,
    not again every subsequent day the drift stays elevated."""
    import asyncio

    coordinator = make_coordinator(
        _base_config(appliance_notify_service="notify.mobile_app_test")
    )
    stable_days = [200] * 15
    drifted_days = [260] * 8  # several days past the alarm threshold

    async def run():
        _run_days(coordinator, hass, stable_days + drifted_days)
        await asyncio.sleep(0)  # flush the scheduled notification task

    asyncio.run(run())

    notify_calls = [c for c in hass.services.calls if c[0] == "notify"]
    assert len(notify_calls) == 1
    assert "sluipverbruik" in notify_calls[0][2]["title"].lower()
