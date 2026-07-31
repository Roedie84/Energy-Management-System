"""The Energy Management System integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import EnergyManagementSystemCoordinator
from .solar_forecast import SolarForecastAccuracyTracker

PLATFORMS = ["switch", "sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Energy Management System from a config entry."""
    config = {**entry.data, **entry.options}

    coordinator = EnergyManagementSystemCoordinator(hass, config)
    solar_tracker = SolarForecastAccuracyTracker(hass, config)
    coordinator.solar_tracker = solar_tracker

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    hass.data[DOMAIN][f"{entry.entry_id}_solar_tracker"] = solar_tracker

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_setup()
    await solar_tracker.async_setup()

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options being updated via the options flow."""
    coordinator: EnergyManagementSystemCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.config = {**entry.data, **entry.options}

    solar_tracker: SolarForecastAccuracyTracker = hass.data[DOMAIN][
        f"{entry.entry_id}_solar_tracker"
    ]
    solar_tracker.config = {**entry.data, **entry.options}

    await coordinator.async_update()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: EnergyManagementSystemCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_unload()

    solar_tracker: SolarForecastAccuracyTracker = hass.data[DOMAIN][
        f"{entry.entry_id}_solar_tracker"
    ]
    await solar_tracker.async_unload()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        hass.data[DOMAIN].pop(f"{entry.entry_id}_solar_tracker")

    return unload_ok
