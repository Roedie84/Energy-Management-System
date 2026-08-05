"""Appliance-ready notification toggle (v0.63.54, requested): "Goedkoop
moment voor de vaatwasser/wasmachine" moet apart uit te zetten zijn,
zonder de gedeelde appliance_notify_service (gebruikt door veel andere
meldingstypes) helemaal stil te leggen.
"""
import asyncio
from datetime import datetime, timezone

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _base_config(**overrides):
    config = {
        "dishwasher_ready_sensor_entity": "binary_sensor.dishwasher_ready",
        "appliance_notify_service": "notify.mobile_app_test",
    }
    config.update(overrides)
    return config


def test_enabled_by_default(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    assert coordinator.appliance_ready_notifications_enabled is True


def test_notification_sent_when_enabled(make_coordinator, hass):
    hass.states.set("binary_sensor.dishwasher_ready", "on")
    coordinator = make_coordinator(_base_config())

    async def run():
        coordinator._check_and_notify_appliance_ready(
            DAY0, is_currently_cheapest_block=True
        )
        await asyncio.sleep(0)

    asyncio.run(run())

    notify_calls = [c for c in hass.services.calls if c[0] == "notify"]
    assert len(notify_calls) == 1
    assert "vaatwasser" in notify_calls[0][2]["title"].lower()


def test_no_notification_when_disabled(make_coordinator, hass):
    hass.states.set("binary_sensor.dishwasher_ready", "on")
    coordinator = make_coordinator(_base_config())
    coordinator.appliance_ready_notifications_enabled = False

    coordinator._check_and_notify_appliance_ready(
        DAY0, is_currently_cheapest_block=True
    )

    notify_calls = [c for c in hass.services.calls if c[0] == "notify"]
    assert notify_calls == []


def test_disabling_this_does_not_affect_other_notification_types(
    make_coordinator, hass
):
    """The toggle is scoped to just this notification type - other
    features using the same appliance_notify_service must keep
    working."""
    coordinator = make_coordinator(_base_config())
    coordinator.appliance_ready_notifications_enabled = False

    async def run():
        coordinator._dispatch_notification(
            notify_service=coordinator.config.get("appliance_notify_service"),
            title="🔔 Een andere melding",
            message="test",
            notification_id="ems_other_test",
        )
        await asyncio.sleep(0)

    asyncio.run(run())

    notify_calls = [c for c in hass.services.calls if c[0] == "notify"]
    assert len(notify_calls) == 1


def test_switch_entity_reflects_and_updates_the_coordinator_flag(
    make_coordinator, hass
):
    from custom_components.energy_management_system.switch import (
        ApplianceReadyNotificationsSwitch,
    )

    coordinator = make_coordinator(_base_config())
    switch = ApplianceReadyNotificationsSwitch(coordinator, "entry1")

    assert switch.is_on is True

    asyncio.run(switch.async_turn_off())
    assert coordinator.appliance_ready_notifications_enabled is False
    assert switch.is_on is False

    asyncio.run(switch.async_turn_on())
    assert coordinator.appliance_ready_notifications_enabled is True
    assert switch.is_on is True


class _FakeLastState:
    def __init__(self, state):
        self.state = state


def test_switch_restores_off_state_across_a_restart(make_coordinator, hass):
    from custom_components.energy_management_system.switch import (
        ApplianceReadyNotificationsSwitch,
    )

    coordinator = make_coordinator(_base_config())
    switch = ApplianceReadyNotificationsSwitch(coordinator, "entry1")

    async def get_last_state():
        return _FakeLastState("off")

    switch.async_get_last_state = get_last_state
    asyncio.run(switch.async_added_to_hass())

    assert coordinator.appliance_ready_notifications_enabled is False
