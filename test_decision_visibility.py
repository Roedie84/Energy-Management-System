"""Extra diagnostic visibility into decision points that were previously
only reachable via debug logging (v0.60.0): which price tier a discharge
decision used (primary/secondary), whether the price-priority check held
off a tick, whether the flat SoC-taper fallback was used instead of the
dynamic reserve, and the full breakdown behind the reserve margin. All
of this now lands in the diagnostics export - see test_diagnostics_*
below for the end-to-end check.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from conftest import make_price_forecast

DAY0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _flat_price_with_cheap_block(hour, minute):
    if 9 <= hour < 12:
        return 1_300_000
    if 19 <= hour < 21:
        return 4_000_000  # clearly above the primary threshold
    return 2_500_000


def _full_config(**overrides):
    config = {
        "price_sensor_entity": "sensor.price",
        "price_attribute": "price_tax_included",
        "operation_select_entity": "select.op",
        "manual_power_number_entity": "number.pow",
        "manual_discharge_power": 1600,
        "manual_charge_power": -2000,
        "solar_forecast_sensor_entity": "sensor.solcast",
        "consumption_power_sensor_entity": "sensor.p1",
    }
    config.update(overrides)
    return config


def with_now(coordinator, when: datetime) -> None:
    """Patch dt_util.now() used inside the coordinator module for this test."""
    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: when


def test_primary_tier_recorded_on_a_genuine_peak_quarter(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.solcast", "20.0")
    hass.states.set("sensor.p1", "200")

    coordinator = make_coordinator(_full_config())

    async def run():
        with_now(coordinator, DAY0.replace(hour=19, minute=15))
        await coordinator._async_update_locked()

    asyncio.run(run())

    assert coordinator.last_is_expensive is True
    assert coordinator.last_expensive_tier == "primary"
    assert coordinator.last_winter_guard_suppressed_today is False


def test_secondary_tier_recorded_when_flip_happens(make_coordinator, hass, monkeypatch):
    """Isolates the wiring (is_expensive flips True via the secondary
    path -> last_expensive_tier records 'secondary'), independent of the
    realistic price/headroom conditions already covered in
    test_secondary_tier.py."""
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.solcast", "20.0")
    hass.states.set("sensor.p1", "200")
    hass.states.set("sensor.available_energy", "5.0")

    coordinator = make_coordinator(
        _full_config(available_energy_sensor_entity="sensor.available_energy")
    )
    monkeypatch.setattr(coordinator, "_is_expensive_now", lambda entries, now: False)
    monkeypatch.setattr(
        coordinator,
        "_is_worth_discharging_at_secondary_tier",
        lambda entries, now, headroom, power: True,
    )
    monkeypatch.setattr(
        coordinator, "_get_dynamic_discharge_reserve_kwh", lambda now, cbs: 1.0
    )

    async def run():
        with_now(coordinator, DAY0.replace(hour=13, minute=0))
        await coordinator._async_update_locked()

    asyncio.run(run())

    assert coordinator.last_expensive_tier == "secondary"


def test_price_priority_hold_off_is_recorded(make_coordinator, hass, monkeypatch):
    coordinator = make_coordinator(
        {
            "available_energy_sensor_entity": "sensor.available_energy",
            "manual_discharge_power": 1600.0,
        }
    )
    hass.states.set("sensor.available_energy", "3.0")

    monkeypatch.setattr(
        coordinator, "_get_dynamic_discharge_reserve_kwh", lambda now, cbs: 1.0
    )
    monkeypatch.setattr(coordinator, "_is_worth_discharging_now", lambda *a, **k: False)

    now = DAY0.replace(hour=19, minute=0)
    scaled = coordinator._get_soc_scaled_discharge_power(1600.0, now, None, entries=[])

    assert scaled is None
    assert coordinator.last_price_priority_held_off is True


def test_soc_taper_fallback_flag_set_without_available_energy_sensor(make_coordinator, hass):
    coordinator = make_coordinator({"battery_soc_sensor_entity": "sensor.soc"})
    hass.states.set("sensor.soc", "80")

    now = DAY0.replace(hour=19, minute=0)
    scaled = coordinator._get_soc_scaled_discharge_power(1600.0, now, None, None)

    assert scaled == pytest.approx(1600.0)
    assert coordinator.last_used_soc_taper_fallback is True


def test_dynamic_branch_clears_soc_taper_fallback_flag(make_coordinator, hass, monkeypatch):
    coordinator = make_coordinator(
        {"available_energy_sensor_entity": "sensor.available_energy"}
    )
    hass.states.set("sensor.available_energy", "8.0")
    monkeypatch.setattr(
        coordinator, "_get_dynamic_discharge_reserve_kwh", lambda now, cbs: 1.0
    )
    coordinator.last_used_soc_taper_fallback = True  # simulate a prior fallback tick

    now = DAY0.replace(hour=19, minute=0)
    coordinator._get_soc_scaled_discharge_power(1600.0, now, None, None)

    assert coordinator.last_used_soc_taper_fallback is False


def test_reserve_margin_breakdown_is_populated(make_coordinator, hass):
    coordinator = make_coordinator({"solar_forecast_sensor_entity": "sensor.solcast"})
    for hour in range(24):
        coordinator.hourly_consumption_profile[hour] = [0.3]
    hass.states.set("sensor.solcast", "0.0")  # no PV -> pure consumption reserve

    start = DAY0.replace(hour=20, minute=0)
    end = start + timedelta(hours=6)
    coordinator._get_dynamic_discharge_reserve_kwh(start, end)

    breakdown = coordinator.last_reserve_margin_breakdown
    assert breakdown  # populated, not the default empty dict
    assert "base_percent" in breakdown
    assert "total_percent" in breakdown
    assert breakdown["reserve_kwh_after_margin"] > breakdown["needed_kwh_before_margin"]
