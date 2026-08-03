"""The Energy Management System integration."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import EnergyManagementSystemCoordinator
from .solar_forecast import SolarForecastAccuracyTracker

PLATFORMS = ["switch", "sensor"]

_LOGGER = logging.getLogger(__name__)

DASHBOARD_FILENAME = "energy_management_system_dashboard.yaml"


def _copy_dashboard_template(hass: HomeAssistant) -> None:
    """Copy the bundled example dashboard to the Home Assistant config
    directory, always overwriting whatever is there.

    This intentionally always overwrites (unlike a typical "only if
    missing" safe-provisioning approach) - the person maintaining this
    integration has explicitly agreed to always feed back any manual
    dashboard change first, so it can be folded into the bundled
    template before shipping a new version. If you've made your own
    changes without reporting them back, they will be lost on the next
    restart - copy dashboards/energy_management_system_dashboard.yaml
    from the repository again afterwards if needed.

    Runs as a blocking file operation, so must be called via
    hass.async_add_executor_job - never directly on the event loop.
    """
    destination = Path(hass.config.path(DASHBOARD_FILENAME))
    source = Path(__file__).parent / "dashboard_template.yaml"
    if not source.exists():
        _LOGGER.debug(
            "Bundled dashboard template not found at %s - skipping "
            "auto-provisioning",
            source,
        )
        return

    try:
        shutil.copyfile(source, destination)
        _LOGGER.info(
            "Copied the example dashboard to %s (always overwritten - "
            "see the integration's README)",
            destination,
        )
    except OSError as err:
        _LOGGER.warning(
            "Could not copy the example dashboard to %s: %s. You can "
            "still copy dashboards/%s from the repository manually.",
            destination,
            err,
            DASHBOARD_FILENAME,
        )


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
    await hass.async_add_executor_job(_copy_dashboard_template, hass)

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
