"""Zelfconsumptie-/zelfvoorzieningsratio (v0.63.101, gevraagd: "zaken
voor een typisch EMS welke we kunnen toevoegen"). Puur informatief.
"""
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


def _base_config(**overrides):
    config = {
        "consumption_power_sensor_entity": "sensor.p1",
        "pv_power_sensor_entity": "sensor.pv",
    }
    config.update(overrides)
    return config


def test_first_tick_only_seeds(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.p1", "-500")
    hass.states.set("sensor.pv", "2000")

    coordinator._update_self_sufficiency_tracking(DAY0)

    assert coordinator.pv_production_today_kwh == 0.0


def test_self_consumption_ratio_with_partial_export(make_coordinator, hass):
    """2000W PV, 500W exported (P1 = -500W) -> 1500W self-consumed ->
    75% self-consumption ratio."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.p1", "-500")
    hass.states.set("sensor.pv", "2000")
    coordinator._update_self_sufficiency_tracking(DAY0)

    coordinator._update_self_sufficiency_tracking(DAY0 + timedelta(hours=1))

    assert coordinator.self_consumption_ratio_percent == 75.0


def test_self_sufficiency_ratio_with_partial_import(make_coordinator, hass):
    """Household needs 1000W gross; 300W still imported from the grid
    -> 700W self-supplied -> 70% self-sufficiency."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.p1", "300")
    hass.states.set("sensor.pv", "700")
    coordinator._update_self_sufficiency_tracking(DAY0)

    coordinator._update_self_sufficiency_tracking(DAY0 + timedelta(hours=1))

    # gross = p1 + battery(0) + pv = 300 + 700 = 1000W
    assert coordinator.gross_consumption_today_kwh == 1.0
    assert coordinator.self_sufficiency_ratio_percent == 70.0


def test_full_self_sufficiency_when_no_import_at_all(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.p1", "-200")  # exporting, no import
    hass.states.set("sensor.pv", "1200")
    coordinator._update_self_sufficiency_tracking(DAY0)

    coordinator._update_self_sufficiency_tracking(DAY0 + timedelta(hours=1))

    assert coordinator.self_sufficiency_ratio_percent == 100.0


def test_ratios_none_without_any_data_yet(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())

    assert coordinator.self_consumption_ratio_percent is None
    assert coordinator.self_sufficiency_ratio_percent is None


def test_day_rollover_resets_totals(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.p1", "-500")
    hass.states.set("sensor.pv", "2000")
    coordinator._update_self_sufficiency_tracking(DAY0)
    coordinator._update_self_sufficiency_tracking(DAY0 + timedelta(hours=1))
    assert coordinator.pv_production_today_kwh > 0

    next_day = DAY0 + timedelta(days=1)
    coordinator._update_self_sufficiency_tracking(next_day)

    assert coordinator.pv_production_today_kwh == 0.0


def test_no_error_without_configured_sensors(make_coordinator, hass):
    coordinator = make_coordinator({})

    coordinator._update_self_sufficiency_tracking(DAY0)

    assert coordinator.pv_production_today_kwh == 0.0
