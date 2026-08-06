"""Tegenfeitelijke besparingsvergelijking (v0.63.101, gevraagd: "als
je dit systeem niet had, had je deze maand €X betaald; nu betaalde je
€Y"). Reconstrueert wat de netmeter zou hebben getoond zonder de accu
(zelfde PV, geen accu-sturing), en rekent beide scenario's tegen
dezelfde prijs af.
"""
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc)


def _base_config(**overrides):
    config = {
        "consumption_power_sensor_entity": "sensor.p1",
        "battery_power_sensor_entity": "sensor.battery",
    }
    config.update(overrides)
    return config


def test_first_tick_only_seeds_no_cost_yet(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.p1", "1000")
    hass.states.set("sensor.battery", "800")  # discharging, covers most load
    coordinator.last_current_price_per_kwh = 0.30

    coordinator._update_counterfactual_savings(DAY0)

    assert coordinator.actual_cost_today_eur == 0.0
    assert coordinator.counterfactual_cost_today_eur == 0.0


def test_battery_discharge_reduces_actual_cost_vs_counterfactual(make_coordinator, hass):
    """The core scenario: battery discharging covers most household
    load, so actual grid import (and cost) is low, while the
    counterfactual (no battery) would have needed much more from the
    grid at the same price."""
    coordinator = make_coordinator(_base_config())
    coordinator.last_current_price_per_kwh = 0.30
    hass.states.set("sensor.p1", "200")  # low import - battery covers most
    hass.states.set("sensor.battery", "800")  # discharging 800W
    coordinator._update_counterfactual_savings(DAY0)

    next_tick = DAY0 + timedelta(hours=1)
    hass.states.set("sensor.p1", "200")
    hass.states.set("sensor.battery", "800")
    coordinator._update_counterfactual_savings(next_tick)

    # Actual: 200W * 1h * 0.30 = 0.06 EUR
    assert round(coordinator.actual_cost_today_eur, 4) == 0.06
    # Counterfactual: (200+800)W * 1h * 0.30 = 0.30 EUR
    assert round(coordinator.counterfactual_cost_today_eur, 4) == 0.30


def test_day_rollover_resets_daily_totals(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    coordinator.last_current_price_per_kwh = 0.30
    hass.states.set("sensor.p1", "500")
    hass.states.set("sensor.battery", "0")
    coordinator._update_counterfactual_savings(DAY0)
    coordinator._update_counterfactual_savings(DAY0 + timedelta(hours=1))
    assert coordinator.actual_cost_today_eur > 0

    next_day = DAY0 + timedelta(days=1)
    coordinator._update_counterfactual_savings(next_day)

    assert coordinator.actual_cost_today_eur == 0.0


def test_month_rollover_resets_monthly_totals(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    coordinator.last_current_price_per_kwh = 0.30
    hass.states.set("sensor.p1", "500")
    hass.states.set("sensor.battery", "0")
    coordinator._update_counterfactual_savings(DAY0)
    coordinator._update_counterfactual_savings(DAY0 + timedelta(hours=1))
    assert coordinator.actual_cost_current_month_eur > 0

    next_month = DAY0.replace(month=9, day=1)
    coordinator._update_counterfactual_savings(next_month)

    assert coordinator.actual_cost_current_month_eur == 0.0


def test_all_time_totals_keep_accumulating_across_months(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    coordinator.last_current_price_per_kwh = 0.30
    hass.states.set("sensor.p1", "500")
    hass.states.set("sensor.battery", "0")
    coordinator._update_counterfactual_savings(DAY0)
    coordinator._update_counterfactual_savings(DAY0 + timedelta(hours=1))

    next_month = DAY0.replace(month=9, day=1)
    coordinator._update_counterfactual_savings(next_month)
    coordinator._update_counterfactual_savings(next_month + timedelta(hours=1))

    assert coordinator.actual_cost_all_time_eur > 0
    assert coordinator.actual_cost_current_month_eur > 0  # only the new month


def test_large_gap_after_restart_is_discarded(make_coordinator, hass):
    """A large gap (e.g. after a restart) must not be integrated as if
    the power had been constant for hours."""
    coordinator = make_coordinator(_base_config())
    coordinator.last_current_price_per_kwh = 0.30
    hass.states.set("sensor.p1", "500")
    hass.states.set("sensor.battery", "0")
    coordinator._update_counterfactual_savings(DAY0)

    much_later = DAY0 + timedelta(hours=5)
    coordinator._update_counterfactual_savings(much_later)

    assert coordinator.actual_cost_today_eur == 0.0


def test_no_error_without_configured_sensors(make_coordinator, hass):
    coordinator = make_coordinator({})

    coordinator._update_counterfactual_savings(DAY0)

    assert coordinator.actual_cost_today_eur == 0.0
