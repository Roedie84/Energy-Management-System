"""Self-learned battery round-trip efficiency (v0.34.0) and its use in
discounting the expected-PV offset in the reserve calculation (v0.33.0).
"""
from datetime import datetime, timedelta, timezone

import pytest

DAY0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


def test_learns_efficiency_from_a_full_charge_discharge_cycle(make_coordinator, hass):
    """A simulated charge-then-discharge cycle at a known 80% efficiency
    should be recovered almost exactly by the learner."""
    coordinator = make_coordinator(
        {
            "battery_power_sensor_entity": "sensor.batt",
            "available_energy_sensor_entity": "sensor.available",
        }
    )

    current = DAY0
    available = 5.0
    hass.states.set("sensor.available", str(available))
    hass.states.set("sensor.batt", "0")
    coordinator._update_battery_efficiency_learning(current)  # seed checkpoint

    step = timedelta(minutes=15)
    for _cycle in range(3):
        for _ in range(8):  # 2 hours charging at 1000W, 80% round-trip efficiency
            current += step
            hass.states.set("sensor.batt", "-1000")
            available += (1000 / 1000) * 0.25 * 0.80
            hass.states.set("sensor.available", str(round(available, 4)))
            coordinator._update_battery_efficiency_learning(current)
        for _ in range(8):  # 2 hours discharging everything back out at 800W
            current += step
            hass.states.set("sensor.batt", "800")
            available -= (800 / 1000) * 0.25
            hass.states.set("sensor.available", str(round(available, 4)))
            coordinator._update_battery_efficiency_learning(current)

    assert coordinator.learned_battery_efficiency_percent == 80.0


def test_learned_efficiency_takes_priority_over_config_default(make_coordinator, hass):
    """Once enough samples exist, the learned value should be used
    instead of the manually configured guess."""
    coordinator = make_coordinator(
        {
            "solar_forecast_sensor_entity": "sensor.solcast",
            "battery_round_trip_efficiency_percent": 95.0,  # deliberately wrong
        }
    )
    coordinator.learned_efficiency_history = [80.0, 80.0, 80.0]

    detailed = [
        {
            "period_start": DAY0.replace(hour=h, minute=m),
            "pv_estimate": 2.0 if 9 <= h < 12 else 0.0,
        }
        for h in range(24)
        for m in (0, 30)
    ]
    hass.states.set("sensor.solcast", "10.0", {"detailedForecast": detailed})

    start = DAY0.replace(hour=9, minute=0)
    end = DAY0.replace(hour=12, minute=0)
    offset = coordinator._get_efficiency_discounted_pv_offset(start, end)

    # 6.0 kWh raw PV * learned 80% (not the configured 95%) = 4.8
    assert offset == pytest.approx(4.8)


def test_pv_hourly_bias_persists_partial_progress(make_coordinator, hass):
    """Regression test for the v0.31.1 bug: raw_pv_hourly_avg must return
    a value even for an hour with fewer samples than the confidence
    threshold, so partial progress survives a restart instead of being
    silently discarded (learned_pv_hourly_ratio correctly still hides it
    from live decisions until there's enough data)."""
    coordinator = make_coordinator({})
    coordinator.pv_hourly_bias_history[10] = [0.85]  # only 1 sample so far

    assert coordinator.learned_pv_hourly_ratio(10) is None  # not confident yet
    assert coordinator.raw_pv_hourly_avg(10) == 0.85  # but persisted for later
