"""Mode/power-change notification (v0.63.8), built into the integration
itself and reusing CONF_APPLIANCE_NOTIFY_SERVICE (already configured for
appliance-ready suggestions, v0.47.0) - no separate automation needed.

Reported: on this setup the Zendure device does nothing autonomous in
'smart' mode, so every charge/discharge change genuinely comes from this
integration - worth a direct notification rather than only being
readable indirectly via the mode/power entities.
"""
import asyncio
from datetime import datetime, timezone

from conftest import make_price_forecast

DAY0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _flat_price_with_negative_quarter(hour, minute):
    if hour == 13 and minute == 0:
        return -500_000
    return 2_500_000


def _base_config(**overrides):
    config = {
        "price_sensor_entity": "sensor.price",
        "price_attribute": "price_tax_included",
        "operation_select_entity": "select.op",
        "manual_power_number_entity": "number.pow",
        "manual_discharge_power": 1600,
        "negative_price_charge_power": -2000,
        "appliance_notify_service": "notify.mobile_app_test",
    }
    config.update(overrides)
    return config


def with_now(coordinator, when: datetime) -> None:
    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: when


async def _tick_and_flush(coordinator, hass, when: datetime) -> None:
    """Run one update tick, then yield control back to the event loop a
    couple of times so any fire-and-forget notification task (scheduled
    via hass.async_create_task -> asyncio.ensure_future) actually gets a
    chance to run before the test inspects hass.services.calls."""
    with_now(coordinator, when)
    await coordinator._async_update_locked()
    await asyncio.sleep(0)
    await asyncio.sleep(0)


def _notify_calls(hass):
    """Only the notification-related service calls - _async_update_locked
    also calls select.select_option / number.set_value to actually
    control the Zendure, which land in the same hass.services.calls list."""
    return [
        c for c in hass.services.calls if c[0] in ("notify", "persistent_notification")
    ]


def test_no_notification_on_the_very_first_tick(make_coordinator, hass):
    """Nothing to compare against yet on the first tick after a
    restart/reload - must not fire a spurious notification."""
    forecast = make_price_forecast(DAY0, _flat_price_with_negative_quarter)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "200")

    coordinator = make_coordinator(_base_config())

    asyncio.run(_tick_and_flush(coordinator, hass, DAY0.replace(hour=13, minute=0)))

    assert coordinator.last_reason == "negative_price"
    assert _notify_calls(hass) == []


def test_notification_sent_on_genuine_mode_change(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _flat_price_with_negative_quarter)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "200")

    coordinator = make_coordinator(_base_config())

    async def run():
        await _tick_and_flush(coordinator, hass, DAY0.replace(hour=12, minute=45))
        assert _notify_calls(hass) == []
        await _tick_and_flush(coordinator, hass, DAY0.replace(hour=13, minute=0))

    asyncio.run(run())

    assert coordinator.last_reason == "negative_price"
    calls = _notify_calls(hass)
    assert len(calls) == 1
    domain, service, data = calls[0]
    assert domain == "notify"
    assert service == "mobile_app_test"
    # v3.95.0: kort, met de stand erin ("Accu: ontladen").
    assert data["title"].startswith(("🎁⬆️", "🔄")) or "Accu:" in data["title"]
    assert "Accu:" in data["title"]
    assert coordinator.last_explanation in data["message"]


def test_no_duplicate_notification_for_the_same_signature(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _flat_price_with_negative_quarter)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "200")

    coordinator = make_coordinator(_base_config())

    async def run():
        await _tick_and_flush(coordinator, hass, DAY0.replace(hour=12, minute=45))
        await _tick_and_flush(coordinator, hass, DAY0.replace(hour=13, minute=0))
        await _tick_and_flush(
            coordinator, hass, DAY0.replace(hour=13, minute=0, second=1)
        )

    asyncio.run(run())

    assert len(_notify_calls(hass)) == 1


def test_no_notification_without_configured_notify_service(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _flat_price_with_negative_quarter)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "200")

    coordinator = make_coordinator(_base_config(appliance_notify_service=None))

    async def run():
        await _tick_and_flush(coordinator, hass, DAY0.replace(hour=12, minute=45))
        await _tick_and_flush(coordinator, hass, DAY0.replace(hour=13, minute=0))

    asyncio.run(run())

    assert _notify_calls(hass) == []


def test_no_notification_in_learning_only_mode(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _flat_price_with_negative_quarter)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "200")

    coordinator = make_coordinator(_base_config())
    coordinator.learning_only = True

    async def run():
        await _tick_and_flush(coordinator, hass, DAY0.replace(hour=12, minute=45))
        await _tick_and_flush(coordinator, hass, DAY0.replace(hour=13, minute=0))

    asyncio.run(run())

    assert _notify_calls(hass) == []


def test_no_notification_while_force_manual_is_on(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _flat_price_with_negative_quarter)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "200")

    coordinator = make_coordinator(_base_config())

    async def run():
        await _tick_and_flush(coordinator, hass, DAY0.replace(hour=12, minute=45))
        coordinator.force_manual = True
        await _tick_and_flush(coordinator, hass, DAY0.replace(hour=13, minute=0))

    asyncio.run(run())

    assert coordinator.last_reason == "force_manual"
    assert _notify_calls(hass) == []


def test_dispatch_notification_falls_back_to_persistent_notification(
    make_coordinator, hass
):
    """Confirms the shared _dispatch_notification helper (v0.63.8
    refactor) still correctly falls back for the pre-existing
    appliance-ready notification path when no notify service is set."""
    coordinator = make_coordinator({})

    async def run():
        coordinator._dispatch_notification(
            notify_service=None,
            title="Test titel",
            message="Test bericht",
            notification_id="ems_test",
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(run())

    calls = _notify_calls(hass)
    assert len(calls) == 1
    domain, service, data = calls[0]
    assert domain == "persistent_notification"
    assert service == "create"
    assert data["notification_id"] == "ems_test"
