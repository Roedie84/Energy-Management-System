"""ExplanationSensor exposes its crucial values as flat attributes
(v0.61.1), so a markdown card can render an icon summary above the full
explanation text instead of only having the prose to parse."""
from datetime import datetime, timezone

from custom_components.energy_management_system.sensor import ExplanationSensor


def test_explanation_sensor_exposes_crucial_values_as_attributes(make_coordinator):
    coordinator = make_coordinator({})
    coordinator.last_explanation = "Er is nu geen speciale reden om in te grijpen."
    coordinator.last_successful_update = datetime(
        2026, 8, 4, 7, 30, 55, tzinfo=timezone.utc
    )
    coordinator.force_manual = False
    coordinator.last_expected_mode = "smart"
    coordinator.last_current_price_per_kwh = 0.3389
    coordinator.last_expensive_price_threshold = 0.378
    coordinator.last_secondary_price_threshold = 0.349
    coordinator.last_effective_expensive_quarters_count = 8
    coordinator.last_heavy_load_source = "airco"

    sensor = ExplanationSensor(coordinator, "entry1")
    attrs = sensor.extra_state_attributes

    assert attrs["explanation"] == coordinator.last_explanation
    assert attrs["last_successful_update"] == "2026-08-04T07:30:55+00:00"
    assert attrs["force_manual"] is False
    assert attrs["expected_mode"] == "smart"
    assert attrs["current_price_per_kwh"] == 0.3389
    assert attrs["expensive_price_threshold"] == 0.378
    assert attrs["secondary_price_threshold"] == 0.349
    assert attrs["effective_expensive_quarters_count"] == 8
    assert attrs["heavy_load_source"] == "airco"


def test_explanation_sensor_handles_missing_data_gracefully(make_coordinator):
    coordinator = make_coordinator({})

    sensor = ExplanationSensor(coordinator, "entry1")
    attrs = sensor.extra_state_attributes

    assert attrs["last_successful_update"] is None
    assert attrs["expensive_price_threshold"] is None
    assert attrs["heavy_load_source"] is None
