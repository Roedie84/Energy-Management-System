"""NILM confirm/reject service registration (v0.63.39)."""
from datetime import datetime, timezone

from custom_components.energy_management_system import (
    _async_register_nilm_services,
    SERVICE_CONFIRM_NILM_DEVICE,
    SERVICE_REJECT_NILM_DEVICE,
    SERVICE_UNCONFIRM_NILM_DEVICE,
)
from custom_components.energy_management_system.const import DOMAIN


def test_services_get_registered(make_coordinator, hass):
    coordinator = make_coordinator({})
    hass.data = {DOMAIN: {"entry1": coordinator}}

    _async_register_nilm_services(hass)

    assert hass.services.has_service(DOMAIN, SERVICE_CONFIRM_NILM_DEVICE)
    assert hass.services.has_service(DOMAIN, SERVICE_REJECT_NILM_DEVICE)
    assert hass.services.has_service(DOMAIN, SERVICE_UNCONFIRM_NILM_DEVICE)


def test_registering_twice_does_not_error(make_coordinator, hass):
    coordinator = make_coordinator({})
    hass.data = {DOMAIN: {"entry1": coordinator}}

    _async_register_nilm_services(hass)
    _async_register_nilm_services(hass)  # must be a no-op, not a crash

    assert hass.services.has_service(DOMAIN, SERVICE_CONFIRM_NILM_DEVICE)


def test_confirm_service_calls_the_coordinator(make_coordinator, hass):
    import asyncio

    from homeassistant.core import ServiceCall

    hass.states.set(
        "sensor.koelkast_vermogen",
        "80",
        {"unit_of_measurement": "W", "friendly_name": "Koelkast"},
    )
    coordinator = make_coordinator({})
    coordinator._update_nilm_discovery(datetime(2026, 8, 4, tzinfo=timezone.utc))
    hass.data = {DOMAIN: {"entry1": coordinator}}
    _async_register_nilm_services(hass)

    handler = hass.services._registered[(DOMAIN, SERVICE_CONFIRM_NILM_DEVICE)]
    call = ServiceCall({"entity_id": "sensor.koelkast_vermogen"})
    asyncio.run(handler(call))

    assert "sensor.koelkast_vermogen" in coordinator.nilm_confirmed_devices


def test_reject_service_calls_the_coordinator(make_coordinator, hass):
    import asyncio

    from homeassistant.core import ServiceCall

    coordinator = make_coordinator({})
    hass.data = {DOMAIN: {"entry1": coordinator}}
    _async_register_nilm_services(hass)

    handler = hass.services._registered[(DOMAIN, SERVICE_REJECT_NILM_DEVICE)]
    call = ServiceCall({"entity_id": "sensor.iets"})
    asyncio.run(handler(call))

    assert "sensor.iets" in coordinator.nilm_rejected_entities


def test_unconfirm_service_calls_the_coordinator(make_coordinator, hass):
    """v0.63.68, requested ('hoe kan ik een NILM apparaat verwijderen
    en opnieuw beoordelen?')."""
    import asyncio

    from homeassistant.core import ServiceCall

    coordinator = make_coordinator({})
    coordinator.nilm_confirmed_devices["sensor.oude_koelkast"] = {
        "friendly_name": "Oude koelkast",
        "daily_avg_history": [80.0, 82.0],
    }
    hass.data = {DOMAIN: {"entry1": coordinator}}
    _async_register_nilm_services(hass)

    handler = hass.services._registered[(DOMAIN, SERVICE_UNCONFIRM_NILM_DEVICE)]
    call = ServiceCall({"entity_id": "sensor.oude_koelkast"})
    asyncio.run(handler(call))

    assert "sensor.oude_koelkast" not in coordinator.nilm_confirmed_devices
    assert "sensor.oude_koelkast" not in coordinator.nilm_rejected_entities
