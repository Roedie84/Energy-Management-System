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
    reserve_normal = coordinator._estimate_worst_case_deficit_kwh(start, end)

    hass.states.set("sensor.p1", "900")  # airco on: 3x the learned average
    reserve_with_airco = coordinator._estimate_worst_case_deficit_kwh(start, end)

    assert reserve_with_airco == pytest.approx(reserve_normal * 3, rel=0.01)
