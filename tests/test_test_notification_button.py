"""Test-notification button (v0.63.9): lets you verify the configured
notify service works end-to-end without waiting for a genuine
mode/power change."""
import asyncio


def test_button_sends_notification_via_configured_service(make_coordinator, hass):
    from custom_components.energy_management_system.button import (
        TestNotificationButton,
    )

    coordinator = make_coordinator(
        {"appliance_notify_service": "notify.mobile_app_test"}
    )
    button = TestNotificationButton(coordinator, entry_id="entry1")

    async def run():
        await button.async_press()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(run())

    calls = [c for c in hass.services.calls if c[0] == "notify"]
    assert len(calls) == 1
    domain, service, data = calls[0]
    assert service == "mobile_app_test"
    assert "Testmelding" in data["title"]


def test_button_falls_back_to_persistent_notification_without_service(
    make_coordinator, hass
):
    from custom_components.energy_management_system.button import (
        TestNotificationButton,
    )

    coordinator = make_coordinator({})
    button = TestNotificationButton(coordinator, entry_id="entry1")

    async def run():
        await button.async_press()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(run())

    calls = [c for c in hass.services.calls if c[0] == "persistent_notification"]
    assert len(calls) == 1
    assert calls[0][2]["notification_id"] == "ems_test_notification"
