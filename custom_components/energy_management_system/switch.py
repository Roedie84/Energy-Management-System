"""Switch entity that forces manual mode (bypasses the control loop entirely)."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DEFAULT_NAME, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ForceManualSwitch(coordinator, entry_id=entry.entry_id),
            LearningOnlySwitch(coordinator, entry_id=entry.entry_id),
            VacationModeSwitch(coordinator, entry_id=entry.entry_id),
        ]
    )


class ForceManualSwitch(SwitchEntity, RestoreEntity):
    """When on, the coordinator will not touch the Zendure operation mode at all."""

    _attr_has_entity_name = True
    _attr_name = "Force manual"
    _attr_icon = "mdi:hand-back-right"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_force_manual"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def is_on(self) -> bool:
        return self._coordinator.force_manual

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._coordinator.force_manual = last_state.state == "on"

    async def async_turn_on(self, **kwargs) -> None:
        await self._coordinator.async_set_force_manual(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._coordinator.async_set_force_manual(False)
        self.async_write_ha_state()


class LearningOnlySwitch(SwitchEntity, RestoreEntity):
    """When on: keep computing and learning, but never control the Zendure.

    Useful to validate the logic (and let the night-consumption / solar-bias
    learning build up history) before trusting it to actually steer the
    battery.
    """

    _attr_has_entity_name = True
    _attr_name = "Learning only (no control)"
    _attr_icon = "mdi:school-outline"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_learning_only"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def is_on(self) -> bool:
        return self._coordinator.learning_only

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._coordinator.learning_only = last_state.state == "on"

    async def async_turn_on(self, **kwargs) -> None:
        await self._coordinator.async_set_learning_only(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._coordinator.async_set_learning_only(False)
        self.async_write_ha_state()


class VacationModeSwitch(SwitchEntity, RestoreEntity):
    """When on: assume much lower household consumption (see the
    'Vacation consumption reduction (%)' option), and pause learning from
    live consumption data entirely - so the unusually low vacation
    readings don't pollute the learned "normal" profile, which would
    otherwise take a while to recover after coming back.
    """

    _attr_has_entity_name = True
    _attr_name = "Vacation mode"
    _attr_icon = "mdi:bag-suitcase-outline"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_vacation_mode"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def is_on(self) -> bool:
        return self._coordinator.vacation_mode

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._coordinator.vacation_mode = last_state.state == "on"

    async def async_turn_on(self, **kwargs) -> None:
        self._coordinator.vacation_mode = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._coordinator.vacation_mode = False
        self.async_write_ha_state()
