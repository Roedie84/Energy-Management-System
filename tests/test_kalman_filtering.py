"""Kalman filtering advisory engine (v0.63.35).

Advisory ONLY - a smoothed estimate shown alongside the raw sensor
reading, never fed into any decision. Tests both the generic
_KalmanFilter1D class directly and its wiring into
_update_kalman_filters() for the three live signals (SoC/available_kwh,
live PV power, live household load).
"""
from datetime import datetime, timezone

from custom_components.energy_management_system.coordinator import (
    _KalmanFilter1D,
)

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def test_first_measurement_seeds_the_estimate():
    kf = _KalmanFilter1D(process_noise=0.01, measurement_noise=0.05)
    result = kf.update(5.0)

    assert result == 5.0
    assert kf.estimate == 5.0


def test_converges_toward_the_true_value_despite_noise():
    """Alternating noisy measurements around a true value of 3.0 should
    converge toward 3.0, not drift off."""
    kf = _KalmanFilter1D(process_noise=0.001, measurement_noise=0.05)
    measurements = [3.2, 2.8, 3.1, 2.9, 3.15, 2.85, 3.05, 2.95, 3.0, 3.0]
    result = None
    for m in measurements:
        result = kf.update(m)

    assert abs(result - 3.0) < 0.1


def test_smooths_more_than_the_raw_last_measurement():
    """The filtered estimate after a single large outlier shouldn't jump
    all the way to that outlier - that's the entire point of filtering."""
    kf = _KalmanFilter1D(process_noise=0.001, measurement_noise=0.05)
    for m in [3.0, 3.0, 3.0, 3.0, 3.0]:
        kf.update(m)
    result = kf.update(10.0)  # a sudden spike/glitch

    assert result < 10.0
    assert result > 3.0


def test_higher_measurement_noise_reacts_slower():
    """A filter that distrusts the sensor more (higher R) should move
    less per update than one that trusts it more (lower R), given the
    same measurement sequence."""
    trusting = _KalmanFilter1D(process_noise=0.01, measurement_noise=0.01)
    skeptical = _KalmanFilter1D(process_noise=0.01, measurement_noise=10.0)

    trusting.update(0.0)
    skeptical.update(0.0)
    trusting_result = trusting.update(10.0)
    skeptical_result = skeptical.update(10.0)

    assert trusting_result > skeptical_result


def test_uncertainty_shrinks_as_measurements_accumulate():
    """Repeated consistent measurements should reduce the filter's own
    uncertainty about its estimate over time."""
    kf = _KalmanFilter1D(process_noise=0.001, measurement_noise=0.1)
    kf.update(3.0)
    first_uncertainty = kf.uncertainty
    for _ in range(20):
        kf.update(3.0)

    assert kf.uncertainty < first_uncertainty


def test_wired_into_coordinator_for_soc_pv_and_load(make_coordinator, hass):
    hass.states.set("sensor.available_energy", "3.2")
    hass.states.set("sensor.pv", "1200")
    hass.states.set("sensor.p1", "300")

    coordinator = make_coordinator(
        {
            "available_energy_sensor_entity": "sensor.available_energy",
            "pv_power_sensor_entity": "sensor.pv",
            "consumption_power_sensor_entity": "sensor.p1",
        }
    )
    coordinator._update_kalman_filters()

    assert coordinator.kalman_soc_raw_kwh == 3.2
    assert coordinator.kalman_soc_filtered_kwh == 3.2  # first sample seeds exactly
    assert coordinator.kalman_pv_raw_w == 1200.0
    assert coordinator.kalman_pv_filtered_w == 1200.0
    assert coordinator.kalman_load_raw_w is not None
    assert coordinator.kalman_load_filtered_w is not None


def test_missing_sensors_leave_estimates_none(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._update_kalman_filters()

    assert coordinator.kalman_soc_filtered_kwh is None
    assert coordinator.kalman_pv_filtered_w is None


def test_never_touches_the_battery(make_coordinator, hass):
    hass.states.set("sensor.available_energy", "3.2")
    hass.states.set("sensor.pv", "1200")

    coordinator = make_coordinator(
        {
            "available_energy_sensor_entity": "sensor.available_energy",
            "pv_power_sensor_entity": "sensor.pv",
        }
    )
    coordinator._update_kalman_filters()

    assert hass.services.calls == []


def test_filtered_state_survives_across_multiple_ticks(make_coordinator, hass):
    """The filter should genuinely accumulate state across calls (not
    reset each tick) - confirms it's a real filter, not a one-shot
    smoothing pass."""
    coordinator = make_coordinator(
        {"available_energy_sensor_entity": "sensor.available_energy"}
    )
    hass.states.set("sensor.available_energy", "3.0")
    coordinator._update_kalman_filters()
    hass.states.set("sensor.available_energy", "3.5")
    coordinator._update_kalman_filters()

    # With nonzero process/measurement noise, the second filtered value
    # should land somewhere between the two raw readings, not jump
    # straight to 3.5.
    assert 3.0 < coordinator.kalman_soc_filtered_kwh < 3.5
