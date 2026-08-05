"""Advisory readiness assessment (v0.63.40): "kunnen we een advies
afgeven wanneer betrouwbaar genoeg om er werkelijk iets mee te doen?"

Deliberate honesty distinction: modules with a genuine data-maturity
signal (Kirchhoff, sluipverbruik, Monte Carlo, Kalman, NILM) get a real
readiness status ("klaar"/"bijna_klaar"/"onvoldoende_data"). Modules
with no mechanism comparing past predictions to what actually happened
(Weather Ensemble, MPC, Digital Twin) get "structureel_beschikbaar"
instead - never a false claim of proven accuracy.
"""
from datetime import datetime, timezone

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def test_kirchhoff_not_configured(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._update_advisory_readiness(DAY0)

    assert coordinator.advisory_readiness["kirchhoff"]["status"] == "niet_geconfigureerd"


def test_kirchhoff_insufficient_data(make_coordinator, hass):
    coordinator = make_coordinator(
        {
            "available_energy_sensor_entity": "sensor.available_energy",
            "battery_power_sensor_entity": "sensor.battery_power",
        }
    )
    coordinator.energy_balance_error_history = [1.0, 2.0]
    coordinator._update_advisory_readiness(DAY0)

    assert coordinator.advisory_readiness["kirchhoff"]["status"] == "onvoldoende_data"


def test_kirchhoff_ready_with_good_score(make_coordinator, hass):
    coordinator = make_coordinator(
        {
            "available_energy_sensor_entity": "sensor.available_energy",
            "battery_power_sensor_entity": "sensor.battery_power",
        }
    )
    coordinator.energy_balance_error_history = [0.0] * 20
    coordinator.sensor_health_score = 95.0
    coordinator._update_advisory_readiness(DAY0)

    assert coordinator.advisory_readiness["kirchhoff"]["status"] == "klaar"


def test_kirchhoff_quality_too_low(make_coordinator, hass):
    coordinator = make_coordinator(
        {
            "available_energy_sensor_entity": "sensor.available_energy",
            "battery_power_sensor_entity": "sensor.battery_power",
        }
    )
    coordinator.energy_balance_error_history = [500.0] * 20
    coordinator.sensor_health_score = 30.0
    coordinator._update_advisory_readiness(DAY0)

    assert coordinator.advisory_readiness["kirchhoff"]["status"] == "kwaliteit_te_laag"


def test_sluipverbruik_maturity_levels(make_coordinator, hass):
    coordinator = make_coordinator({})

    coordinator.baseline_load_history = [0.2] * 5
    coordinator._update_advisory_readiness(DAY0)
    assert coordinator.advisory_readiness["sluipverbruik"]["status"] == "onvoldoende_data"

    coordinator.baseline_load_history = [0.2] * 15
    coordinator._update_advisory_readiness(DAY0)
    assert coordinator.advisory_readiness["sluipverbruik"]["status"] == "bijna_klaar"

    coordinator.baseline_load_history = [0.2] * 30
    coordinator._update_advisory_readiness(DAY0)
    assert coordinator.advisory_readiness["sluipverbruik"]["status"] == "klaar"


def test_weather_ensemble_labelled_structural_not_ready(make_coordinator, hass):
    """Honesty check: never claims 'klaar' for a module with no
    accuracy-tracking mechanism."""
    coordinator = make_coordinator({})
    coordinator.weather_ensemble_sources_used = ["weather.knmi"]
    coordinator._update_advisory_readiness(DAY0)

    status = coordinator.advisory_readiness["weather_ensemble"]["status"]
    assert status == "structureel_beschikbaar"
    assert status != "klaar"
    assert "nauwkeurigheid" in coordinator.advisory_readiness["weather_ensemble"]["reden"]


def test_weather_ensemble_not_configured(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._update_advisory_readiness(DAY0)

    assert (
        coordinator.advisory_readiness["weather_ensemble"]["status"]
        == "niet_geconfigureerd"
    )


def test_mpc_labelled_structural_not_ready(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.mpc_horizon_quarters_used = 96
    coordinator._update_advisory_readiness(DAY0)

    status = coordinator.advisory_readiness["mpc"]["status"]
    assert status == "structureel_beschikbaar"
    assert status != "klaar"


def test_monte_carlo_maturity_levels(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._update_advisory_readiness(DAY0)
    assert coordinator.advisory_readiness["monte_carlo"]["status"] == "onvoldoende_data"

    for h in range(24):
        coordinator.hourly_consumption_profile[h] = [0.3] * 7
    coordinator._update_advisory_readiness(DAY0)
    assert coordinator.advisory_readiness["monte_carlo"]["status"] == "klaar"


def test_kalman_not_configured(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._update_advisory_readiness(DAY0)

    assert coordinator.advisory_readiness["kalman"]["status"] == "niet_geconfigureerd"


def test_kalman_converges_after_many_consistent_updates(make_coordinator, hass):
    coordinator = make_coordinator(
        {"available_energy_sensor_entity": "sensor.available_energy"}
    )
    for _ in range(50):
        coordinator._kalman_soc.update(3.0)
    coordinator._update_advisory_readiness(DAY0)

    assert coordinator.advisory_readiness["kalman"]["status"] in (
        "klaar",
        "bijna_klaar",
    )


def test_digital_twin_labelled_structural_not_ready(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.digital_twin_trajectory = [{"start": "x", "mode": "smart", "soc_kwh": 1.0}]
    coordinator.digital_twin_hours_simulated = 24
    coordinator._update_advisory_readiness(DAY0)

    status = coordinator.advisory_readiness["digital_twin"]["status"]
    assert status == "structureel_beschikbaar"
    assert status != "klaar"


def test_nilm_not_configured(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._update_advisory_readiness(DAY0)

    assert coordinator.advisory_readiness["nilm"]["status"] == "niet_geconfigureerd"


def test_nilm_maturity_across_devices(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.nilm_confirmed_devices = {
        "sensor.a": {"friendly_name": "A", "daily_avg_history": [1.0] * 30},
        "sensor.b": {"friendly_name": "B", "daily_avg_history": [1.0] * 5},
    }
    coordinator._update_advisory_readiness(DAY0)

    assert coordinator.advisory_readiness["nilm"]["status"] == "bijna_klaar"

    coordinator.nilm_confirmed_devices["sensor.b"]["daily_avg_history"] = [1.0] * 30
    coordinator._update_advisory_readiness(DAY0)
    assert coordinator.advisory_readiness["nilm"]["status"] == "klaar"


def test_all_eight_modules_always_present(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._update_advisory_readiness(DAY0)

    expected = {
        "kirchhoff",
        "sluipverbruik",
        "weather_ensemble",
        "mpc",
        "monte_carlo",
        "kalman",
        "digital_twin",
        "nilm",
    }
    assert set(coordinator.advisory_readiness.keys()) == expected


def test_never_calls_any_hass_service(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._update_advisory_readiness(DAY0)

    assert hass.services.calls == []
