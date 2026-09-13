"""MPC (Model Predictive Control) advisory engine (v0.63.33).

Advisory ONLY - confirmed explicitly before building: never sends a
device command, never overrides the existing decision tree. Pure
price-arbitrage greedy interval pairing over the available forecast
horizon.
"""
from datetime import datetime, timezone

from conftest import make_price_forecast

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _base_config(**overrides):
    config = {
        "price_sensor_entity": "sensor.price",
        "price_attribute": "price_tax_included",
        "available_energy_sensor_entity": "sensor.available_energy",
        "battery_total_capacity_sensor_entity": "sensor.total_capacity",
        "battery_min_soc_number_entity": "number.min_soc",
        "manual_discharge_power": 1600,
        "manual_charge_power": -1600,
    }
    config.update(overrides)
    return config


def _setup_capacity(hass, available_kwh, total_kwh, min_soc_percent):
    hass.states.set("sensor.available_energy", str(available_kwh))
    hass.states.set("sensor.total_capacity", str(total_kwh))
    hass.states.set("number.min_soc", str(min_soc_percent))


def test_no_plan_without_capacity_sensors(make_coordinator, hass):
    def price_fn(hour, minute):
        return 2_000_000 if hour < 12 else 4_000_000

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.available_energy", "2.0")

    coordinator = make_coordinator(
        {
            "price_sensor_entity": "sensor.price",
            "price_attribute": "price_tax_included",
            "available_energy_sensor_entity": "sensor.available_energy",
        }
    )
    entries = coordinator._get_forecast_entries()
    coordinator._compute_mpc_plan(DAY0.replace(hour=0, minute=0), entries)

    assert coordinator.mpc_planned_actions == []
    assert coordinator.mpc_projected_total_profit_eur is None
    assert "capacity" in coordinator.mpc_note.lower()


def test_charges_cheap_and_discharges_expensive(make_coordinator, hass):
    """Clear price shape: cheap in the morning, expensive in the
    evening - MPC should plan to charge in the cheap window and
    discharge in the expensive one."""

    def price_fn(hour, minute):
        return 1_500_000 if hour in (2, 3) else (4_500_000 if hour in (19, 20) else 2_500_000)

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    _setup_capacity(hass, available_kwh=1.0, total_kwh=4.2, min_soc_percent=0)

    coordinator = make_coordinator(_base_config())
    coordinator.learned_efficiency_history = [90.0] * 7
    entries = coordinator._get_forecast_entries()

    coordinator._compute_mpc_plan(DAY0.replace(hour=0, minute=0), entries)

    actions = coordinator.mpc_planned_actions
    assert any(a["action"] == "laden" for a in actions)
    assert any(a["action"] == "ontladen" for a in actions)
    assert coordinator.mpc_projected_total_profit_eur > 0

    charge_hours = {
        datetime.fromisoformat(a["start"]).hour
        for a in actions
        if a["action"] == "laden"
    }
    discharge_hours = {
        datetime.fromisoformat(a["start"]).hour
        for a in actions
        if a["action"] == "ontladen"
    }
    assert charge_hours <= {2, 3}
    assert discharge_hours <= {19, 20}


def test_no_pairs_when_margin_too_small(make_coordinator, hass):
    """A flat price day (tiny spread) shouldn't produce any plan - the
    round-trip loss eats any theoretical margin."""

    def price_fn(hour, minute):
        return 2_500_000

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    _setup_capacity(hass, available_kwh=1.0, total_kwh=5.0, min_soc_percent=0)

    coordinator = make_coordinator(_base_config())
    coordinator.learned_efficiency_history = [90.0] * 7
    entries = coordinator._get_forecast_entries()

    coordinator._compute_mpc_plan(DAY0.replace(hour=0, minute=0), entries)

    assert coordinator.mpc_planned_actions == []
    assert coordinator.mpc_projected_total_profit_eur == 0.0


def test_charge_bounded_by_remaining_headroom(make_coordinator, hass):
    """Very little remaining capacity headroom (nearly full battery)
    should sharply limit how much can be planned to charge."""

    def price_fn(hour, minute):
        return 1_500_000 if hour in (2, 3) else (4_500_000 if hour in (19, 20) else 2_500_000)

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    # Only 0.1 kWh of headroom left (4.9 available out of 5.0 usable).
    _setup_capacity(hass, available_kwh=4.9, total_kwh=5.0, min_soc_percent=0)

    coordinator = make_coordinator(_base_config())
    coordinator.learned_efficiency_history = [90.0] * 7
    entries = coordinator._get_forecast_entries()

    coordinator._compute_mpc_plan(DAY0.replace(hour=0, minute=0), entries)

    total_charge_kwh = sum(
        a["energy_kwh"] for a in coordinator.mpc_planned_actions if a["action"] == "laden"
    )
    assert total_charge_kwh <= 0.1 + 1e-6


def test_never_touches_the_battery(make_coordinator, hass):
    """The advisory guarantee: no select/number/switch service call is
    ever made by computing an MPC plan."""

    def price_fn(hour, minute):
        return 1_500_000 if hour in (2, 3) else (4_500_000 if hour in (19, 20) else 2_500_000)

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    _setup_capacity(hass, available_kwh=1.0, total_kwh=5.0, min_soc_percent=0)

    coordinator = make_coordinator(_base_config())
    coordinator.learned_efficiency_history = [90.0] * 7
    entries = coordinator._get_forecast_entries()

    coordinator._compute_mpc_plan(DAY0.replace(hour=0, minute=0), entries)

    assert len(coordinator.mpc_planned_actions) > 0  # a plan was genuinely made
    assert hass.services.calls == []  # yet nothing was ever sent to the device


def test_note_always_explains_the_advisory_nature(make_coordinator, hass):
    def price_fn(hour, minute):
        return 1_500_000 if hour in (2, 3) else (4_500_000 if hour in (19, 20) else 2_500_000)

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    _setup_capacity(hass, available_kwh=1.0, total_kwh=5.0, min_soc_percent=0)

    coordinator = make_coordinator(_base_config())
    coordinator.learned_efficiency_history = [90.0] * 7
    entries = coordinator._get_forecast_entries()

    coordinator._compute_mpc_plan(DAY0.replace(hour=0, minute=0), entries)

    assert "adviserend" in coordinator.mpc_note.lower()
    assert "nooit" in coordinator.mpc_note.lower()
