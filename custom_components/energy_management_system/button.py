"""Button entity to verify the mode/power-change notification (v0.63.8)
works end-to-end, without waiting for a genuine decision change."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_APPLIANCE_NOTIFY_SERVICE, DEFAULT_NAME, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TestNotificationButton(coordinator, entry_id=entry.entry_id)])


class TestNotificationButton(ButtonEntity):
    """Sends a test notification through the same code path as the real
    mode/power-change notification (_dispatch_notification), using
    whatever CONF_APPLIANCE_NOTIFY_SERVICE is currently configured - so
    pressing it verifies the actual configured notify service works,
    not just a generic HA test notification unrelated to this
    integration's own setup.
    """

    _attr_has_entity_name = True
    _attr_name = "Test notificatie versturen"
    _attr_icon = "mdi:bell-ring-outline"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_test_notification"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    async def async_press(self) -> None:
        notify_service = self._coordinator.config.get(CONF_APPLIANCE_NOTIFY_SERVICE)
        self._coordinator._dispatch_notification(
            notify_service=notify_service,
            title="🔔 Testmelding Energy Management System",
            message=(
                "Dit is een testmelding om te bevestigen dat de "
                "notify-service correct is ingesteld. Als je dit ziet, "
                "werken modus/vermogen-wijziging-meldingen ook."
            ),
            notification_id="ems_test_notification",
        )
