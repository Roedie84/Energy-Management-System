"""Steelstofzuiger/fietsladers learned data must survive a restart
(v0.63.64) - gap found while auditing today's changes for persistence:
the self-learned completion threshold's idle-power samples (v0.63.46)
and the learned charge duration (pre-existing) were both being
silently reset to empty on every restart, since these status sensors
previously only extended the non-restoring diagnostic base class.
"""
import asyncio


class _FakeLastState:
    def __init__(self, attributes):
        self.attributes = attributes


def test_steelstofzuiger_restores_idle_power_history(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        SteelstofzuigerStatusSensor,
    )

    coordinator = make_coordinator({})
    sensor = SteelstofzuigerStatusSensor(coordinator, "entry1")

    async def get_last_state():
        return _FakeLastState({"idle_power_history_w": [2.0, 2.1, 1.9]})

    sensor.async_get_last_state = get_last_state
    asyncio.run(sensor.async_added_to_hass())

    assert coordinator._steelstofzuiger_idle_power_history == [2.0, 2.1, 1.9]


def test_steelstofzuiger_restores_duration_history(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        SteelstofzuigerStatusSensor,
    )

    coordinator = make_coordinator({})
    sensor = SteelstofzuigerStatusSensor(coordinator, "entry1")

    async def get_last_state():
        return _FakeLastState({"duration_history_minutes": [45.0, 50.0]})

    sensor.async_get_last_state = get_last_state
    asyncio.run(sensor.async_added_to_hass())

    assert coordinator.steelstofzuiger_charge_duration_history == [45.0, 50.0]


def test_fietsladers_restores_idle_power_history(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        FietsladersStatusSensor,
    )

    coordinator = make_coordinator({})
    sensor = FietsladersStatusSensor(coordinator, "entry1")

    async def get_last_state():
        return _FakeLastState({"idle_power_history_w": [1.5, 1.6]})

    sensor.async_get_last_state = get_last_state
    asyncio.run(sensor.async_added_to_hass())

    assert coordinator._fietsladers_idle_power_history == [1.5, 1.6]


def test_fietsladers_restores_duration_history(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        FietsladersStatusSensor,
    )

    coordinator = make_coordinator({})
    sensor = FietsladersStatusSensor(coordinator, "entry1")

    async def get_last_state():
        return _FakeLastState({"duration_history_minutes": [120.0]})

    sensor.async_get_last_state = get_last_state
    asyncio.run(sensor.async_added_to_hass())

    assert coordinator.fietsladers_charge_duration_history == [120.0]


def test_no_prior_state_leaves_empty_history(make_coordinator, hass):
    """First-ever run (no restored state) shouldn't crash, and should
    leave the freshly-initialised empty history untouched."""
    from custom_components.energy_management_system.sensor import (
        SteelstofzuigerStatusSensor,
    )

    coordinator = make_coordinator({})
    sensor = SteelstofzuigerStatusSensor(coordinator, "entry1")

    asyncio.run(sensor.async_added_to_hass())

    assert coordinator._steelstofzuiger_idle_power_history == []
