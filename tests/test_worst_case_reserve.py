"""Worst-case cumulative deficit reserve calculation (v0.43.0/0.43.1).

The most important safety fix in the whole project: a simple net
balance over the whole bridging window can look fine on paper (abundant
solar expected tomorrow) while still hiding a real overnight shortfall,
since solar credit is concentrated in daylight hours. This walks hour by
hour and protects against the deepest point reached, not just the net
end-of-window balance.
"""
from datetime import datetime, timedelta, timezone

import pytest

DAY0 = datetime(2026, 8, 2, tzinfo=timezone.utc)


def _two_day_pv_forecast(peak_kw: float = 1.4, start_hour: int = 8, end_hour: int = 16):
    detailed = []
    for day_offset in range(2):
        for hour in range(24):
            for minute in (0, 30):
                pv = peak_kw if start_hour <= hour < end_hour else 0.0
                detailed.append(
                    {
                        "period_start": (DAY0 + timedelta(days=day_offset)).replace(
                            hour=hour, minute=minute
                        ),
                        "pv_estimate": pv,
                    }
                )
    return detailed


def test_worst_case_deficit_exceeds_naive_net_balance(make_coordinator, hass):
    """Reproduces the exact field scenario: ~11+ kWh of solar expected
    tomorrow makes the naive net balance look like ~0 reserve is needed,
    while a real overnight deficit (before any solar arrives) remains."""
    coordinator = make_coordinator({"solar_forecast_sensor_entity": "sensor.solcast"})
    for hour in range(24):
        coordinator.hourly_consumption_profile[hour] = [0.3]  # flat 300W all day

    hass.states.set(
        "sensor.solcast", "11.2", {"detailedForecast": _two_day_pv_forecast()}
    )

    start = DAY0.replace(hour=23, minute=45)
    end = (DAY0 + timedelta(days=1)).replace(hour=11, minute=15)

    naive_consumption = coordinator._estimate_consumption_kwh_for_period(start, end)
    naive_pv_offset = coordinator._get_efficiency_discounted_pv_offset(start, end)
    naive_reserve = max(0.0, naive_consumption - naive_pv_offset)

    worst_case_reserve = coordinator._estimate_worst_case_deficit_kwh(start, end)

    assert naive_reserve == pytest.approx(0.0, abs=0.01)
    assert worst_case_reserve > 2.0  # a real overnight deficit remains
    assert worst_case_reserve > naive_reserve


def test_worst_case_deficit_reacts_to_live_consumption_spike(make_coordinator, hass):
    """An airco running right now should scale up the whole worst-case
    estimate proportionally, not just get averaged away by history."""
    coordinator = make_coordinator(
        {
            "solar_forecast_sensor_entity": "sensor.solcast",
            "consumption_power_sensor_entity": "sensor.p1",
        }
    )
    for hour in range(24):
        coordinator.hourly_consumption_profile[hour] = [0.3]

    hass.states.set(
        "sensor.solcast", "11.2", {"detailedForecast": _two_day_pv_forecast()}
    )

    start = DAY0.replace(hour=23, minute=45)
    end = (DAY0 + timedelta(days=1)).replace(hour=11, minute=15)

    hass.states.set("sensor.p1", "300")  # matches the learned average
    for _ in range(4):
        coordinator._track_recent_consumption_reading(start)
    reserve_normal = coordinator._estimate_worst_case_deficit_kwh(start, end)

    coordinator2 = make_coordinator(
        {
            "solar_forecast_sensor_entity": "sensor.solcast",
            "consumption_power_sensor_entity": "sensor.p1",
        }
    )
    for hour in range(24):
        coordinator2.hourly_consumption_profile[hour] = [0.3]
    hass.states.set("sensor.p1", "900")  # airco on and sustained: 3x the learned avg
    for _ in range(4):
        coordinator2._track_recent_consumption_reading(start)
    reserve_with_airco = coordinator2._estimate_worst_case_deficit_kwh(start, end)

    assert reserve_with_airco == pytest.approx(reserve_normal * 3, rel=0.01)


def test_brief_single_tick_spike_does_not_scale_the_whole_estimate(
    make_coordinator, hass
):
    """Regression test for a real-world incident: a single brief power
    spike used to scale a 15+ hour estimate to an absurd value (reported:
    17.4 kWh baseline for what should have been a few kWh). Smoothing
    over a short rolling window should mostly cancel out a one-off blip
    surrounded by normal readings."""
    coordinator = make_coordinator(
        {"consumption_power_sensor_entity": "sensor.p1"}
    )
    for hour in range(24):
        coordinator.hourly_consumption_profile[hour] = [0.3]

    start = DAY0.replace(hour=7, minute=0)
    end = DAY0.replace(hour=22, minute=0)  # a long ~15 hour window

    # Establish the normal (no-spike) baseline for comparison.
    hass.states.set("sensor.p1", "300")
    for _ in range(4):
        coordinator._track_recent_consumption_reading(start)
    normal_estimate = coordinator._estimate_consumption_kwh_for_period(start, end)

    # Now simulate a single brief spike among otherwise-normal readings.
    coordinator2 = make_coordinator({"consumption_power_sensor_entity": "sensor.p1"})
    for hour in range(24):
        coordinator2.hourly_consumption_profile[hour] = [0.3]
    hass.states.set("sensor.p1", "300")
    coordinator2._track_recent_consumption_reading(start)
    coordinator2._track_recent_consumption_reading(start)
    hass.states.set("sensor.p1", "9000")  # a huge, brief spike (e.g. a glitch)
    coordinator2._track_recent_consumption_reading(start)
    hass.states.set("sensor.p1", "300")
    coordinator2._track_recent_consumption_reading(start)
    spiky_estimate = coordinator2._estimate_consumption_kwh_for_period(start, end)

    # A single blip should be dampened by the surrounding normal
    # readings AND capped - not allowed to apply anywhere near its raw
    # ratio (9000/300 = 30x). The smoothed average here (2.475 kW vs a
    # 0.3 kW learned baseline) works out to 8.25x, which the cap then
    # limits to exactly 5x - still far below the uncapped/unsmoothed 30x
    # a single-point reading would have produced.
    assert spiky_estimate == pytest.approx(normal_estimate * 5.0, rel=0.01)
    assert spiky_estimate < normal_estimate * 30


def test_moderate_brief_spike_is_dampened_by_smoothing(make_coordinator, hass):
    """A milder single-tick spike (not extreme enough to hit the ratio
    cap) should still be visibly dampened by the surrounding normal
    readings, compared to what a single-instant reading would have
    produced."""
    coordinator = make_coordinator({"consumption_power_sensor_entity": "sensor.p1"})
    for hour in range(24):
        coordinator.hourly_consumption_profile[hour] = [0.3]

    start = DAY0.replace(hour=7, minute=0)

    hass.states.set("sensor.p1", "300")
    coordinator._track_recent_consumption_reading(start)
    coordinator._track_recent_consumption_reading(start)
    hass.states.set("sensor.p1", "900")  # one brief 3x spike
    coordinator._track_recent_consumption_reading(start)
    hass.states.set("sensor.p1", "300")
    coordinator._track_recent_consumption_reading(start)

    ratio = coordinator._get_smoothed_consumption_correction_ratio(7)

    # Smoothed average = (300+300+900+300)/4 = 450W -> 450/300 = 1.5x,
    # well below the raw single-reading ratio of 3x.
    assert ratio == pytest.approx(1.5, rel=0.01)
    assert ratio < 3.0



