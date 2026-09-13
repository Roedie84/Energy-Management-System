"""Monte Carlo advisory engine (v0.63.34).

Advisory ONLY - never sends a device command, never overrides the
existing deterministic worst-case-deficit calculation or reserve
margin. Bootstrap-resamples the already-collected empirical history
(hourly_consumption_profile, pv_hourly_bias_history) to run many
randomised trajectories of the same hour-by-hour "diepste tekort" walk,
producing a probability distribution instead of a single point estimate.
"""
from datetime import datetime, timedelta, timezone

import pytest

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _seed_history(coordinator, consumption_kw=0.3, pv_bias=1.0, hours=range(24)):
    for h in hours:
        coordinator.hourly_consumption_profile[h] = [consumption_kw] * 7
        coordinator.pv_hourly_bias_history[h] = [pv_bias] * 7


def test_no_cheap_block_start_produces_no_simulation(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._run_monte_carlo_simulation(DAY0, None)

    assert coordinator.monte_carlo_simulations_run == 0
    assert coordinator.monte_carlo_median_deficit_kwh is None
    assert "geen" in coordinator.monte_carlo_note.lower()


def test_cheap_block_in_the_past_produces_no_simulation(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._run_monte_carlo_simulation(DAY0, DAY0 - timedelta(hours=1))

    assert coordinator.monte_carlo_simulations_run == 0


def test_runs_the_full_1000_simulations(make_coordinator, hass):
    coordinator = make_coordinator({})
    _seed_history(coordinator)

    coordinator._run_monte_carlo_simulation(DAY0, DAY0 + timedelta(hours=4))

    assert coordinator.monte_carlo_simulations_run == 1000
    assert coordinator.monte_carlo_hours_simulated == 4


def test_zero_variance_history_gives_zero_spread(make_coordinator, hass):
    """With identical samples every hour (no real variance), every
    simulated trajectory should land on the same deficit - median, p10
    and p90 all equal."""
    coordinator = make_coordinator({})
    _seed_history(coordinator, consumption_kw=0.3, pv_bias=0.0)

    coordinator._run_monte_carlo_simulation(DAY0, DAY0 + timedelta(hours=3))

    assert coordinator.monte_carlo_median_deficit_kwh == coordinator.monte_carlo_p90_deficit_kwh
    assert coordinator.monte_carlo_median_deficit_kwh == coordinator.monte_carlo_p10_deficit_kwh
    # 0.3 kW * 3h = 0.9 kWh deficit, no PV contribution (bias 0).
    assert coordinator.monte_carlo_median_deficit_kwh == pytest.approx(0.9, abs=0.01)


def test_variance_in_history_produces_a_spread(make_coordinator, hass):
    """Genuinely different historical samples per hour should produce a
    real spread between p10 and p90 - not collapse to a single value."""
    coordinator = make_coordinator({})
    for h in range(24):
        coordinator.hourly_consumption_profile[h] = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
        coordinator.pv_hourly_bias_history[h] = [0.0] * 7

    coordinator._run_monte_carlo_simulation(DAY0, DAY0 + timedelta(hours=6))

    assert coordinator.monte_carlo_p90_deficit_kwh > coordinator.monte_carlo_p10_deficit_kwh


def test_shortfall_probability_computed_against_available_energy(make_coordinator, hass):
    coordinator = make_coordinator(
        {"available_energy_sensor_entity": "sensor.available_energy"}
    )
    hass.states.set("sensor.available_energy", "0.5")  # deliberately tight
    _seed_history(coordinator, consumption_kw=0.3, pv_bias=0.0)

    coordinator._run_monte_carlo_simulation(DAY0, DAY0 + timedelta(hours=4))

    # 4h * 0.3kW = 1.2 kWh deficit > 0.5 kWh available - every trajectory
    # should be a shortfall.
    assert coordinator.monte_carlo_shortfall_probability_percent == 100.0


def test_no_shortfall_probability_without_available_energy_sensor(make_coordinator, hass):
    coordinator = make_coordinator({})
    _seed_history(coordinator)

    coordinator._run_monte_carlo_simulation(DAY0, DAY0 + timedelta(hours=2))

    assert coordinator.monte_carlo_shortfall_probability_percent is None


def test_horizon_capped_for_performance(make_coordinator, hass):
    coordinator = make_coordinator({})
    _seed_history(coordinator)

    coordinator._run_monte_carlo_simulation(DAY0, DAY0 + timedelta(hours=72))

    assert coordinator.monte_carlo_hours_simulated <= 48


def test_falls_back_to_learned_average_without_history(make_coordinator, hass):
    """Hours with no sampled history yet shouldn't crash - fall back to
    the learned point estimate (or 1.0 bias / 0.0 consumption if that's
    also unavailable)."""
    coordinator = make_coordinator({})
    coordinator._run_monte_carlo_simulation(DAY0, DAY0 + timedelta(hours=2))

    assert coordinator.monte_carlo_simulations_run == 1000


def test_never_touches_the_battery(make_coordinator, hass):
    coordinator = make_coordinator({})
    _seed_history(coordinator)

    coordinator._run_monte_carlo_simulation(DAY0, DAY0 + timedelta(hours=4))

    assert hass.services.calls == []
