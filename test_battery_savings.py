"""Battery cost-basis savings tracking (v0.63.24): a weighted-average
EUR/kWh cost basis for whatever energy currently sits in the battery,
updated on every charge (at the current dynamic price, regardless of
source) and realised as savings/earnings on every discharge - whether
sold explicitly during an expensive quarter, or simply used to cover
household load and avoid an import.

Valid under a salderen (net-metering) contract: feed-in pays the same
dynamic rate as import, so PV routed into the battery instead of
exported has exactly the same opportunity cost as buying that energy
from the grid at that moment - equating PV-charged and grid-charged
energy into one unified model.
"""
from datetime import datetime, timezone

import pytest

from conftest import make_price_forecast

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _flat_price(price_eur):
    def price_fn(hour, minute):
        return int(price_eur * 10_000_000)

    return price_fn


def _base_config(**overrides):
    config = {
        "price_sensor_entity": "sensor.price",
        "price_attribute": "price_tax_included",
        "available_energy_sensor_entity": "sensor.available_energy",
    }
    config.update(overrides)
    return config


def _entries(coordinator):
    return coordinator._get_forecast_entries()


def test_first_tick_seeds_without_computing_anything(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _flat_price(0.20))
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.available_energy", "3.0")

    coordinator = make_coordinator(_base_config())
    now = DAY0.replace(hour=12, minute=0)
    coordinator._update_battery_cost_basis_and_savings(now, _entries(coordinator))

    assert coordinator.battery_cost_basis_eur_per_kwh is None
    assert coordinator.total_battery_savings_eur == 0.0


def test_charge_sets_cost_basis_at_current_price(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _flat_price(0.20))
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.available_energy", "3.0")

    coordinator = make_coordinator(_base_config())
    now = DAY0.replace(hour=12, minute=0)
    coordinator._update_battery_cost_basis_and_savings(now, _entries(coordinator))

    hass.states.set("sensor.available_energy", "4.0")  # +1 kWh charged at 0.20
    coordinator._update_battery_cost_basis_and_savings(now, _entries(coordinator))

    assert coordinator.battery_cost_basis_eur_per_kwh == 0.20


def test_charge_updates_weighted_average(make_coordinator, hass):
    forecast_cheap = make_price_forecast(DAY0, _flat_price(0.20))
    hass.states.set("sensor.price", "0", {"forecast": forecast_cheap})
    hass.states.set("sensor.available_energy", "0.0")

    coordinator = make_coordinator(_base_config())
    now = DAY0.replace(hour=12, minute=0)
    coordinator._update_battery_cost_basis_and_savings(now, _entries(coordinator))

    # Charge 2 kWh at 0.20
    hass.states.set("sensor.available_energy", "2.0")
    coordinator._update_battery_cost_basis_and_savings(now, _entries(coordinator))
    assert coordinator.battery_cost_basis_eur_per_kwh == 0.20

    # Charge another 2 kWh at 0.40 -> weighted average (2*0.20 + 2*0.40)/4 = 0.30
    forecast_expensive = make_price_forecast(DAY0, _flat_price(0.40))
    hass.states.set("sensor.price", "0", {"forecast": forecast_expensive})
    hass.states.set("sensor.available_energy", "4.0")
    coordinator._update_battery_cost_basis_and_savings(now, _entries(coordinator))

    assert coordinator.battery_cost_basis_eur_per_kwh == pytest.approx(0.30)


def test_discharge_realises_savings_against_cost_basis(make_coordinator, hass):
    """Reproduces the core scenario: charge cheap (or from PV, same
    model under salderen), later discharge (sell, or just avoid an
    import) at a higher price - the difference is realised as savings."""
    forecast_cheap = make_price_forecast(DAY0, _flat_price(0.20))
    hass.states.set("sensor.price", "0", {"forecast": forecast_cheap})
    hass.states.set("sensor.available_energy", "0.0")

    coordinator = make_coordinator(_base_config())
    now = DAY0.replace(hour=12, minute=0)
    coordinator._update_battery_cost_basis_and_savings(now, _entries(coordinator))

    hass.states.set("sensor.available_energy", "2.0")  # charge 2 kWh @ 0.20
    coordinator._update_battery_cost_basis_and_savings(now, _entries(coordinator))

    forecast_expensive = make_price_forecast(DAY0, _flat_price(0.40))
    hass.states.set("sensor.price", "0", {"forecast": forecast_expensive})
    hass.states.set("sensor.available_energy", "1.0")  # discharge 1 kWh @ 0.40
    coordinator._update_battery_cost_basis_and_savings(now, _entries(coordinator))

    # 1 kWh * (0.40 - 0.20) = 0.20 EUR saved/earned
    assert coordinator.total_battery_savings_eur == pytest.approx(0.20, abs=1e-6)


def test_discharge_before_any_charge_is_skipped(make_coordinator, hass):
    """Pre-existing energy with an unknown origin (e.g. right after a
    fresh install) shouldn't be guessed at - no cost basis yet means no
    savings realised, not a wrong one."""
    forecast = make_price_forecast(DAY0, _flat_price(0.30))
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.available_energy", "3.0")

    coordinator = make_coordinator(_base_config())
    now = DAY0.replace(hour=12, minute=0)
    coordinator._update_battery_cost_basis_and_savings(now, _entries(coordinator))

    hass.states.set("sensor.available_energy", "2.0")  # discharge, no basis yet
    coordinator._update_battery_cost_basis_and_savings(now, _entries(coordinator))

    assert coordinator.total_battery_savings_eur == 0.0


def test_tiny_deltas_are_ignored_as_noise(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _flat_price(0.30))
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.available_energy", "3.0")

    coordinator = make_coordinator(_base_config())
    now = DAY0.replace(hour=12, minute=0)
    coordinator._update_battery_cost_basis_and_savings(now, _entries(coordinator))

    hass.states.set("sensor.available_energy", "3.001")  # 1 Wh - noise
    coordinator._update_battery_cost_basis_and_savings(now, _entries(coordinator))

    assert coordinator.battery_cost_basis_eur_per_kwh is None


def test_loss_can_be_realised_when_selling_below_cost_basis(make_coordinator, hass):
    """A real possibility, not hidden: state_class must be 'total', not
    'total_increasing', since this can genuinely decrease."""
    forecast_expensive = make_price_forecast(DAY0, _flat_price(0.40))
    hass.states.set("sensor.price", "0", {"forecast": forecast_expensive})
    hass.states.set("sensor.available_energy", "0.0")

    coordinator = make_coordinator(_base_config())
    now = DAY0.replace(hour=12, minute=0)
    coordinator._update_battery_cost_basis_and_savings(now, _entries(coordinator))

    hass.states.set("sensor.available_energy", "1.0")  # charge @ 0.40
    coordinator._update_battery_cost_basis_and_savings(now, _entries(coordinator))

    forecast_cheap = make_price_forecast(DAY0, _flat_price(0.10))
    hass.states.set("sensor.price", "0", {"forecast": forecast_cheap})
    hass.states.set("sensor.available_energy", "0.0")  # forced to discharge @ 0.10
    coordinator._update_battery_cost_basis_and_savings(now, _entries(coordinator))

    assert coordinator.total_battery_savings_eur == pytest.approx(-0.30, abs=1e-6)


def test_no_available_energy_sensor_does_nothing(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _flat_price(0.30))
    hass.states.set("sensor.price", "0", {"forecast": forecast})

    coordinator = make_coordinator(
        {"price_sensor_entity": "sensor.price", "price_attribute": "price_tax_included"}
    )
    now = DAY0.replace(hour=12, minute=0)
    coordinator._update_battery_cost_basis_and_savings(now, _entries(coordinator))

    assert coordinator.battery_cost_basis_eur_per_kwh is None


def test_export_portion_gets_the_feedin_premium(make_coordinator, hass):
    """v0.63.25 (Zonneplan Zonnebonus criteria, confirmed via web
    search): a fixed EUR/kWh feed-in premium applies to genuine grid
    export - even from a battery (only the separate 10% bonus excludes
    battery-sourced feed-in, which this integration never claims).
    Reproduces: 1 kWh discharged over 1 hour, but household load is only
    200W - so 800W (0.8 kWh) of that hour is genuine export, 0.2 kWh
    just covers load. Configures battery_power_sensor_entity so
    _read_corrected_consumption_power() correctly reconstructs the true
    200W household load from the P1 meter's net -800W export reading."""
    import datetime as dt

    forecast_cheap = make_price_forecast(DAY0, _flat_price(0.20))
    hass.states.set("sensor.price", "0", {"forecast": forecast_cheap})
    hass.states.set("sensor.available_energy", "0.0")
    hass.states.set("sensor.p1", "0")
    hass.states.set("sensor.battery_power", "0")

    coordinator = make_coordinator(
        _base_config(
            consumption_power_sensor_entity="sensor.p1",
            battery_power_sensor_entity="sensor.battery_power",
        )
    )
    t0 = DAY0.replace(hour=12, minute=0)
    coordinator._update_battery_cost_basis_and_savings(t0, _entries(coordinator))

    hass.states.set("sensor.available_energy", "1.0")  # charge 1 kWh @ 0.20
    t1 = t0 + dt.timedelta(minutes=5)
    coordinator._update_battery_cost_basis_and_savings(t1, _entries(coordinator))

    forecast_expensive = make_price_forecast(DAY0, _flat_price(0.40))
    hass.states.set("sensor.price", "0", {"forecast": forecast_expensive})
    # 200W household load, battery discharges 1000W (1 kWh/hour) ->
    # P1 meter nets to -800W export; battery_power +1000W (discharging).
    hass.states.set("sensor.p1", "-800")
    hass.states.set("sensor.battery_power", "1000")
    hass.states.set("sensor.available_energy", "0.0")  # discharge 1 kWh over 1h
    t2 = t1 + dt.timedelta(hours=1)
    coordinator._update_battery_cost_basis_and_savings(t2, _entries(coordinator))

    # Base arbitrage: 1 kWh * (0.40 - 0.20) = 0.20
    # Plus feed-in premium on the exported 0.8 kWh: 0.8 * 0.02 = 0.016
    assert coordinator.total_battery_savings_eur == pytest.approx(0.216, abs=1e-6)
    assert coordinator.total_feedin_premium_eur == pytest.approx(0.016, abs=1e-6)


def test_no_premium_when_discharge_only_covers_load(make_coordinator, hass):
    """No genuine export at all - discharge rate stays at/below
    household load throughout - so no feed-in premium, only the
    avoided-import value."""
    import datetime as dt

    forecast_cheap = make_price_forecast(DAY0, _flat_price(0.20))
    hass.states.set("sensor.price", "0", {"forecast": forecast_cheap})
    hass.states.set("sensor.available_energy", "0.0")
    hass.states.set("sensor.p1", "0")
    hass.states.set("sensor.battery_power", "0")

    coordinator = make_coordinator(
        _base_config(
            consumption_power_sensor_entity="sensor.p1",
            battery_power_sensor_entity="sensor.battery_power",
        )
    )
    t0 = DAY0.replace(hour=12, minute=0)
    coordinator._update_battery_cost_basis_and_savings(t0, _entries(coordinator))

    hass.states.set("sensor.available_energy", "1.0")  # charge 1 kWh @ 0.20
    t1 = t0 + dt.timedelta(minutes=5)
    coordinator._update_battery_cost_basis_and_savings(t1, _entries(coordinator))

    forecast_expensive = make_price_forecast(DAY0, _flat_price(0.40))
    hass.states.set("sensor.price", "0", {"forecast": forecast_expensive})
    # 1000W household load, battery discharges exactly 1000W -> P1 nets
    # to 0 (no import, no export at all).
    hass.states.set("sensor.p1", "0")
    hass.states.set("sensor.battery_power", "1000")
    hass.states.set("sensor.available_energy", "0.0")  # discharge 1 kWh over 1h
    t2 = t1 + dt.timedelta(hours=1)
    coordinator._update_battery_cost_basis_and_savings(t2, _entries(coordinator))

    assert coordinator.total_feedin_premium_eur == 0.0
    assert coordinator.total_battery_savings_eur == pytest.approx(0.20, abs=1e-6)


def test_discharge_value_sensor_also_gets_the_feedin_premium(make_coordinator, hass):
    """v0.63.26: for consistency, the pre-existing
    discharge_value_expensive_quarters sensor (_update_financial_tracking)
    gets the same export-vs-covers-load feed-in premium split as the
    newer cost-basis savings model - it represents actual money received,
    so it should include the real feed-in premium too, not just the
    market price."""
    forecast = make_price_forecast(DAY0, _flat_price(0.40))
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    # 200W household load, 1000W discharge -> 800W (0.8 kWh/h) genuine export.
    hass.states.set("sensor.p1", "-800")
    hass.states.set("sensor.battery_power", "1000")

    coordinator = make_coordinator(
        _base_config(
            consumption_power_sensor_entity="sensor.p1",
            battery_power_sensor_entity="sensor.battery_power",
        )
    )
    entries = _entries(coordinator)
    now = DAY0.replace(hour=20, minute=0)

    # First call seeds _last_value_calc_time (elapsed_hours would be 0).
    coordinator._update_financial_tracking(now, entries, "expensive_quarter", 1000, None)

    import datetime as dt

    later = now + dt.timedelta(hours=1)
    coordinator._update_financial_tracking(
        later, entries, "expensive_quarter", 1000, None
    )

    # Base value: 1 kWh * 0.40 = 0.40. Plus premium on the exported
    # 0.8 kWh: 0.8 * 0.02 = 0.016.
    assert coordinator.total_discharge_value_eur == pytest.approx(0.416, abs=1e-6)
    assert coordinator.total_feedin_premium_eur == pytest.approx(0.016, abs=1e-6)
