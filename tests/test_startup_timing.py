"""Wait for Home Assistant to fully start before the first data fetch
(v0.45.0) - fixes spurious "No usable forecast entries" warnings seen
right at startup, before other integrations (e.g. the price sensor's
own integration) had finished loading.
"""
import asyncio

from conftest import FakeHass


def test_cold_boot_waits_for_homeassistant_started(coordinator_cls):
    hass = FakeHass(core_state="STARTING")
    coordinator = coordinator_cls(
        hass, {"price_sensor_entity": "sensor.price", "operation_select_entity": "select.op"}
    )

    calls = []

    async def fake_update():
        calls.append(True)

    coordinator.async_update = fake_update
    asyncio.run(coordinator.async_setup())

    assert calls == [], "should not fetch data immediately during a cold boot"
    assert len(hass.bus.listeners) == 1
    event_type, _callback_fn = hass.bus.listeners[0]
    assert event_type == "homeassistant_started"


def test_reload_after_hass_already_running_fetches_immediately(coordinator_cls):
    hass = FakeHass(core_state="RUNNING")
    coordinator = coordinator_cls(
        hass, {"price_sensor_entity": "sensor.price", "operation_select_entity": "select.op"}
    )

    calls = []

    async def fake_update():
        calls.append(True)

    coordinator.async_update = fake_update
    asyncio.run(coordinator.async_setup())

    assert calls == [True], "should fetch immediately if HA is already fully running"
