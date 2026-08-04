"""Household-consumption floor on the reserve-scaled discharge power
(v0.59.0).

Field-reported bug: during a genuinely expensive (is_expensive) quarter,
the reserve-based headroom scaling throttled the forced discharge down to
~150W while the house was drawing ~340W - importing the ~190W gap at the
same peak price the system had just decided was worth selling into.
Live numbers from diagnostics: available=1.728 kWh, and a "Beschikbare
Energie" history graph showing ~5.7-5.8 kWh available around the time of
the incident, base_power (manual_discharge_power) = 1600W.

The fix: `_get_soc_scaled_discharge_power` now never returns less than
the live corrected household load, capped by what's physically available
this tick and by base_power - so an expensive-quarter tick either sells
enough to cover the house, or (if truly empty) sells nothing, but never
sells a trickle while quietly importing the rest at the peak rate.
"""
from datetime import datetime, timezone

import pytest

DAY0 = datetime(2026, 8, 3, tzinfo=timezone.utc)


def _base_config(**overrides):
    config = {
        "available_energy_sensor_entity": "sensor.available_energy",
        "consumption_power_sensor_entity": "sensor.p1",
        "manual_discharge_power": 1600.0,
    }
    config.update(overrides)
    return config


def test_low_headroom_is_raised_to_cover_household_load(make_coordinator, hass, monkeypatch):
    """Reproduces the reported field incident: tiny headroom (~12.5 Wh,
    scaling to ~150W) but the house is drawing 340W - the applied power
    must be raised to cover the house, not left at the throttled value."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.available_energy", "5.75")
    hass.states.set("sensor.p1", "340")

    # Isolate the floor logic: pin the dynamic reserve so headroom works
    # out to ~12.5 Wh, exactly like the reported incident.
    monkeypatch.setattr(
        coordinator, "_get_dynamic_discharge_reserve_kwh", lambda now, cbs: 5.7375
    )

    now = DAY0.replace(hour=22, minute=0)
    scaled = coordinator._get_soc_scaled_discharge_power(1600.0, now, None, None)

    assert scaled == pytest.approx(340.0, abs=0.5)


def test_no_headroom_still_applies_floor(make_coordinator, hass, monkeypatch):
    """Even when headroom is fully exhausted (max_power_w <= 0), a live
    household load should still be covered rather than skipping the
    forced discharge entirely and importing at the peak price."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.available_energy", "3.0")
    hass.states.set("sensor.p1", "250")

    monkeypatch.setattr(
        coordinator, "_get_dynamic_discharge_reserve_kwh", lambda now, cbs: 3.0
    )

    now = DAY0.replace(hour=22, minute=0)
    scaled = coordinator._get_soc_scaled_discharge_power(1600.0, now, None, None)

    assert scaled == pytest.approx(250.0, abs=0.5)


def test_floor_never_exceeds_physically_available_energy(make_coordinator, hass, monkeypatch):
    """The floor must not promise more than the battery actually holds
    this tick, even if the house is drawing more than that."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.available_energy", "0.05")  # 0.05 kWh left
    hass.states.set("sensor.p1", "900")  # house drawing far more

    monkeypatch.setattr(
        coordinator, "_get_dynamic_discharge_reserve_kwh", lambda now, cbs: 0.0
    )

    now = DAY0.replace(hour=22, minute=0)
    scaled = coordinator._get_soc_scaled_discharge_power(1600.0, now, None, None)

    # interval = 5 min -> 0.05 kWh over 5 min = 600W physical ceiling
    assert scaled == pytest.approx(600.0, abs=0.5)


def test_ample_headroom_unaffected_by_floor(make_coordinator, hass, monkeypatch):
    """When headroom already comfortably covers the household load, the
    floor is a no-op and behavior matches the pre-fix result."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.available_energy", "8.0")
    hass.states.set("sensor.p1", "340")

    monkeypatch.setattr(
        coordinator, "_get_dynamic_discharge_reserve_kwh", lambda now, cbs: 2.0
    )

    now = DAY0.replace(hour=22, minute=0)
    scaled = coordinator._get_soc_scaled_discharge_power(1600.0, now, None, None)

    assert scaled == pytest.approx(1600.0, abs=0.5)


def test_no_consumption_sensor_no_floor_applied(make_coordinator, hass, monkeypatch):
    """Without a consumption sensor configured, behavior is unchanged
    from before the fix - still returns None on exhausted headroom."""
    coordinator = make_coordinator(
        {
            "available_energy_sensor_entity": "sensor.available_energy",
            "manual_discharge_power": 1600.0,
        }
    )
    hass.states.set("sensor.available_energy", "3.0")

    monkeypatch.setattr(
        coordinator, "_get_dynamic_discharge_reserve_kwh", lambda now, cbs: 3.0
    )

    now = DAY0.replace(hour=22, minute=0)
    scaled = coordinator._get_soc_scaled_discharge_power(1600.0, now, None, None)

    assert scaled is None


def test_floor_event_logged_and_exposed_in_diagnostics(make_coordinator, hass, monkeypatch):
    """When the floor actually raises the power (the reported field
    incident), it must show up in a shared diagnostics export - so a
    future report can be diagnosed from the file alone, without also
    needing a separately-pulled sensor history graph."""
    import asyncio
    import json

    from custom_components.energy_management_system import diagnostics as diag_mod
    from custom_components.energy_management_system.const import DOMAIN

    class _FakeConfigEntry:
        data = {}
        options = {}
        entry_id = "entry1"

    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.available_energy", "5.75")
    hass.states.set("sensor.p1", "340")
    monkeypatch.setattr(
        coordinator, "_get_dynamic_discharge_reserve_kwh", lambda now, cbs: 5.7375
    )

    now = DAY0.replace(hour=22, minute=0)
    scaled = coordinator._get_soc_scaled_discharge_power(1600.0, now, None, None)
    assert scaled == pytest.approx(340.0, abs=0.5)

    assert coordinator.last_discharge_floor_applied is True
    assert coordinator.last_household_load_w == pytest.approx(340.0, abs=0.5)
    assert len(coordinator.discharge_floor_events) == 1
    event = coordinator.discharge_floor_events[0]
    assert event["household_load_w"] == pytest.approx(340.0, abs=0.5)
    assert event["applied_w"] == pytest.approx(340.0, abs=0.5)
    assert event["headroom_scaled_w"] < event["applied_w"]

    hass.data = {DOMAIN: {"entry1": coordinator}}
    result = asyncio.run(
        diag_mod.async_get_config_entry_diagnostics(hass, _FakeConfigEntry())
    )
    c = result["coordinator"]
    assert c["last_discharge_floor_applied"] is True
    assert len(c["discharge_floor_events"]) == 1
    json.dumps(result)  # must remain JSON-serializable
