"""Keuzelijsten van het EMS (v5.85).

De stand van de luchtreiniger, gezet over het lokale netwerk door het EMS
zelf (`luchtreiniger_lokaal`) - geen cloud, geen integratie van derden.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_NAME, DOMAIN, GEEN_ATTRIBUTEN_IN_RECORDER
from .luchtreiniger_lokaal import STANDEN

_LOGGER = logging.getLogger(__name__)

# v5.85.1: de keuzelijst wordt opgezet vóór het meelezen start (de platforms
# komen eerst). Bleef na een herstart "onbeschikbaar". Nu kijkt hij elke 10 s
# of het meelezen er is en meldt zich dan aan; daarna ververst hij meteen bij
# elke wijziging.
SCAN_INTERVAL = timedelta(seconds=10)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LuchtreinigerStandSelect(coordinator, entry.entry_id)])


class LuchtreinigerStandSelect(SelectEntity):
    """De stand van de luchtreiniger: uit, low, mid, high, turbo, auto, sleep."""

    _attr_has_entity_name = True
    _attr_name = "Luchtreiniger stand"
    _attr_icon = "mdi:air-purifier"
    _attr_options = list(STANDEN)
    _attr_should_poll = True
    _unrecorded_attributes = GEEN_ATTRIBUTEN_IN_RECORDER

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_luchtreiniger_stand"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}, "name": DEFAULT_NAME}
        self._afmelden = None

    @property
    def _meelezer(self):
        return getattr(self._coordinator, "luchtreiniger_lokaal", None)

    async def async_added_to_hass(self) -> None:
        self._meld_aan()

    def _meld_aan(self) -> None:
        meelezer = self._meelezer
        if meelezer is not None and self._afmelden is None:
            self._afmelden = meelezer.luister(self.async_write_ha_state)

    async def async_update(self) -> None:
        self._meld_aan()

    async def async_will_remove_from_hass(self) -> None:
        afmelden, self._afmelden = self._afmelden, None
        if afmelden is not None:
            afmelden()

    @property
    def available(self) -> bool:
        m = self._meelezer
        return bool(m is not None and m.verbonden and m.stand is not None)

    @property
    def current_option(self) -> str | None:
        m = self._meelezer
        stand = m.stand if m is not None else None
        return stand if stand in STANDEN else None

    @property
    def extra_state_attributes(self) -> dict:
        m = self._meelezer
        if m is None:
            return {}
        return {"bron": "lokaal (eigen Tuya-protocol)", "ip": m.tellingen.get("ip"),
                "protocol": m.tellingen.get("versie")}

    async def async_select_option(self, option: str) -> None:
        m = self._meelezer
        if m is None:
            raise HomeAssistantError("Het lokaal meelezen van de luchtreiniger is niet gestart.")
        try:
            gelukt = await m.async_zet_stand(option)
        except (ConnectionError, ValueError, OSError) as err:
            raise HomeAssistantError(f"Luchtreiniger niet gezet: {err}") from err
        if not gelukt:
            raise HomeAssistantError(
                f"De luchtreiniger bevestigde stand {option} niet binnen 5 seconden."
            )
        self.async_write_ha_state()
