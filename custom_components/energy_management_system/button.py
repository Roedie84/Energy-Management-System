"""Button entity to verify the mode/power-change notification (v0.63.8)
works end-to-end, without waiting for a genuine decision change."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_APPLIANCE_NOTIFY_SERVICE,
    DEFAULT_NAME,
    DOMAIN,
    NILM_DASHBOARD_SLOT_COUNT,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [TestNotificationButton(coordinator, entry_id=entry.entry_id)]
    for slot in range(NILM_DASHBOARD_SLOT_COUNT):
        entities.append(NilmConfirmCandidateButton(coordinator, entry.entry_id, slot))
        entities.append(NilmRejectCandidateButton(coordinator, entry.entry_id, slot))
    async_add_entities(entities)


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


class _NilmSlotButton(ButtonEntity):
    """Shared base for the 8 confirm/reject slot-pairs (v0.63.41/.43/.47)
    - see `EnergyManagementSystemCoordinator.get_nilm_candidate_at_slot`
    for why a fixed number of slots is used instead of one dynamic
    button per candidate (a static Lovelace dashboard can't render an
    unknown-length, changing list without an extra HACS frontend card).

    v0.63.43: the entity's own `name` is dynamic (candidate name + live
    power), not a static "slot N" label - reported: a static label plus
    a separate cross-reference table got badly truncated on a narrow/
    mobile dashboard, making it unusable. Putting the actual candidate
    directly in the button's name removes the need to cross-reference
    anything.

    v0.63.47: `has_entity_name` deliberately OFF (unlike every other
    entity in this integration) - reported: with it on, Home Assistant
    prefixes every display of the name with the device name ("Energy
    Management System ..."), which in a narrow name column truncated
    down to just "E..." - defeating the whole point of v0.63.43's fix.
    These buttons are read as standalone action labels, not as
    device-scoped sub-features, so the prefix adds nothing but length.

    v0.63.48: registers itself as a coordinator listener (same pattern
    already used by `SolarForecastAccuracyTracker`) - reported: slots
    stayed empty indefinitely, even right after a fresh discovery.
    `ButtonEntity` doesn't poll by default (unlike `SensorEntity`, which
    is why the sensors in this integration refresh fine on their own),
    so without an explicit push after every coordinator update, the
    button's displayed name/attributes just froze at whatever they
    happened to be the one time Home Assistant wrote their initial
    state during setup - typically "(leeg)", since discovery hadn't run
    yet at that point.
    """

    def __init__(self, coordinator, entry_id: str, slot: int, unique_suffix: str) -> None:
        self._coordinator = coordinator
        self._slot = slot
        self._attr_unique_id = f"{entry_id}_nilm_slot_{slot}_{unique_suffix}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._coordinator.register_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.unregister_listener(self.async_write_ha_state)
        await super().async_will_remove_from_hass()

    def _slot_label(self) -> str:
        entity_id = self._coordinator.get_nilm_candidate_at_slot(self._slot)
        if entity_id is None:
            return f"Sleuf {self._slot + 1} (leeg)"
        candidate = self._coordinator.nilm_unconfirmed_candidates.get(entity_id, {})
        naam = candidate.get("friendly_name") or entity_id
        power_w = candidate.get("current_power_w")
        power_txt = f" {power_w:.0f}W" if power_w is not None else ""
        return f"{naam}{power_txt}"

    @property
    def extra_state_attributes(self) -> dict:
        entity_id = self._coordinator.get_nilm_candidate_at_slot(self._slot)
        if entity_id is None:
            return {"kandidaat_entity_id": None, "kandidaat_naam": None}
        candidate = self._coordinator.nilm_unconfirmed_candidates.get(entity_id, {})
        return {
            "kandidaat_entity_id": entity_id,
            "kandidaat_naam": candidate.get("friendly_name"),
            "kandidaat_vermogen_w": candidate.get("current_power_w"),
        }


class NilmConfirmCandidateButton(_NilmSlotButton):
    """Confirms whichever candidate currently occupies this slot."""

    _attr_icon = "mdi:check-circle-outline"

    def __init__(self, coordinator, entry_id: str, slot: int) -> None:
        super().__init__(coordinator, entry_id, slot, "confirm")

    @property
    def name(self) -> str:
        return f"✅ {self._slot_label()}"

    async def async_press(self) -> None:
        entity_id = self._coordinator.get_nilm_candidate_at_slot(self._slot)
        if entity_id is not None:
            self._coordinator.confirm_nilm_device(entity_id)


class NilmRejectCandidateButton(_NilmSlotButton):
    """Rejects whichever candidate currently occupies this slot."""

    _attr_icon = "mdi:close-circle-outline"

    def __init__(self, coordinator, entry_id: str, slot: int) -> None:
        super().__init__(coordinator, entry_id, slot, "reject")

    @property
    def name(self) -> str:
        return f"❌ {self._slot_label()}"

    async def async_press(self) -> None:
        entity_id = self._coordinator.get_nilm_candidate_at_slot(self._slot)
        if entity_id is not None:
            self._coordinator.reject_nilm_device(entity_id)
