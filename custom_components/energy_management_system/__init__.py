"""The Energy Management System integration."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import EnergyManagementSystemCoordinator
from .solar_forecast import SolarForecastAccuracyTracker

PLATFORMS = ["switch", "sensor", "button"]

_LOGGER = logging.getLogger(__name__)

DASHBOARD_FILENAME = "energy_management_system_dashboard.yaml"
# v0.63.125: de achtergrondtekening voor de picture-elements-kaart. Moet
# onder `www/` staan, want dat is de enige map die Home Assistant als
# statische bestanden serveert (bereikbaar als /local/<naam>).
BACKGROUND_SOURCE_FILENAME = "overview_background.svg"
BACKGROUND_TARGET_PATH = "www/energy_management_system_overview.svg"

SERVICE_CONFIRM_NILM_DEVICE = "confirm_nilm_device"
SERVICE_REJECT_NILM_DEVICE = "reject_nilm_device"
SERVICE_UNCONFIRM_NILM_DEVICE = "unconfirm_nilm_device"
# v1.1.7: drift accepteren als nieuw normaal, zonder de leergeschiedenis
# weg te gooien.
SERVICE_ACCEPT_NILM_DRIFT = "accept_nilm_device_drift"
# v0.63.118: duplicaatparen beoordelen, spiegelbeeld van confirm/reject
# voor losse apparaten.
SERVICE_DISMISS_NILM_DUPLICATE = "dismiss_nilm_duplicate_pair"
SERVICE_CONFIRM_NILM_DUPLICATE = "confirm_nilm_duplicate_pair"
NILM_SERVICE_SCHEMA = vol.Schema({vol.Required("entity_id"): cv.entity_id})
NILM_DUPLICATE_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id_1"): cv.entity_id,
        vol.Required("entity_id_2"): cv.entity_id,
    }
)


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


def _copy_overview_background(hass: HomeAssistant) -> None:
    """Zet de achtergrondtekening klaar onder `www/` (v0.63.125).

    Home Assistant serveert alleen `<config>/www/` als statische map, via
    de URL `/local/`. De picture-elements-kaart verwijst daarheen, dus
    zonder deze kopie zou de kaart een gebroken afbeelding tonen terwijl
    alle waarden er wél overheen staan - verwarrender dan een lege kaart.

    Maakt `www/` aan als die nog niet bestaat. LET OP: Home Assistant
    registreert die map alleen bij het opstarten, dus als `www/` hier
    voor het eerst wordt aangemaakt, is één extra herstart nodig voordat
    de afbeelding daadwerkelijk geserveerd wordt. Dat staat ook in de
    README.

    Blokkerende bestandsoperatie - alleen aanroepen via
    hass.async_add_executor_job.
    """
    source = Path(__file__).parent / BACKGROUND_SOURCE_FILENAME
    if not source.exists():
        _LOGGER.debug(
            "Achtergrondtekening niet gevonden op %s - overgeslagen", source
        )
        return

    destination = Path(hass.config.path(BACKGROUND_TARGET_PATH))
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        _LOGGER.info(
            "Achtergrondtekening voor het dashboard gekopieerd naar %s "
            "(bereikbaar als /local/%s)",
            destination,
            destination.name,
        )
    except OSError as err:
        _LOGGER.warning(
            "Kon de achtergrondtekening niet naar %s kopiëren: %s. De "
            "picture-elements-kaart toont dan een gebroken afbeelding; "
            "kopieer dashboards/%s handmatig naar www/.",
            destination,
            err,
            BACKGROUND_SOURCE_FILENAME,
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

    # v0.63.115: de opgeslagen NILM-staat MOET geladen zijn voordat de
    # platforms worden opgezet. `NilmConfirmedDevicesSensor.
    # async_added_to_hass` heeft een migratiepad vanuit de eigen
    # herstelde entiteit-state, en die entiteit-attributen zijn met
    # opzet afgekapt op 20 items. Draaide platform-setup eerst (zoals
    # tot en met v0.63.114), dan zag die migratie altijd lege lijsten,
    # sloeg elke herstart opnieuw toe, en overschreef de volledige
    # Store met een afgekapte kopie - waardoor bevestigde apparaten én
    # afgewezen entiteiten permanent op 20 bleven steken en de rest bij
    # elke herstart terugkwam als "onbevestigde kandidaat". Zie
    # `_async_load_nilm_confirmed_devices_store`'s docstring.
    # v1.0.4: alle opgebouwde toestand terugzetten voordat de platforms
    # draaien - zelfde volgorde-eis als de NILM-store (v0.63.115).
    await coordinator.async_load_persisted_state()
    await coordinator.async_load_persisted_nilm_state()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_setup()
    await solar_tracker.async_setup()
    await hass.async_add_executor_job(_copy_dashboard_template, hass)
    await hass.async_add_executor_job(_copy_overview_background, hass)

    entry.async_on_unload(entry.add_update_listener(async_update_options))
    _async_register_nilm_services(hass)

    return True


def _async_register_nilm_services(hass: HomeAssistant) -> None:
    """Register the confirm/reject NILM-device services (v0.63.39) once
    per Home Assistant instance - not per config entry, to avoid a
    "service already registered" error if the integration's options are
    ever reloaded. Applies the action to every coordinator this
    integration has set up (in practice, just one per household) -
    confirming/rejecting an entity_id that a particular coordinator
    doesn't currently have as a candidate is a harmless no-op there.
    """
    if hass.services.has_service(DOMAIN, SERVICE_CONFIRM_NILM_DEVICE):
        return

    def _iter_coordinators():
        for key, value in hass.data.get(DOMAIN, {}).items():
            if isinstance(key, str) and key.endswith("_solar_tracker"):
                continue
            yield value

    async def _handle_confirm(call: ServiceCall) -> None:
        entity_id = call.data["entity_id"]
        confirmed_anywhere = False
        for coordinator in _iter_coordinators():
            if coordinator.confirm_nilm_device(entity_id):
                confirmed_anywhere = True
        if not confirmed_anywhere:
            _LOGGER.warning(
                "confirm_nilm_device: %s was not a known NILM candidate",
                entity_id,
            )

    async def _handle_reject(call: ServiceCall) -> None:
        entity_id = call.data["entity_id"]
        for coordinator in _iter_coordinators():
            coordinator.reject_nilm_device(entity_id)

    async def _handle_unconfirm(call: ServiceCall) -> None:
        entity_id = call.data["entity_id"]
        unconfirmed_anywhere = False
        for coordinator in _iter_coordinators():
            if coordinator.unconfirm_nilm_device(entity_id):
                unconfirmed_anywhere = True
        if not unconfirmed_anywhere:
            _LOGGER.warning(
                "unconfirm_nilm_device: %s was not a confirmed NILM device",
                entity_id,
            )

    async def _handle_dismiss_duplicate(call: ServiceCall) -> None:
        entity_1 = call.data["entity_id_1"]
        entity_2 = call.data["entity_id_2"]
        for coordinator in _iter_coordinators():
            coordinator.dismiss_nilm_duplicate_pair(entity_1, entity_2)

    async def _handle_confirm_duplicate(call: ServiceCall) -> None:
        entity_1 = call.data["entity_id_1"]
        entity_2 = call.data["entity_id_2"]
        handled_anywhere = False
        for coordinator in _iter_coordinators():
            if coordinator.confirm_nilm_duplicate_pair(entity_1, entity_2):
                handled_anywhere = True
        if not handled_anywhere:
            _LOGGER.warning(
                "confirm_nilm_duplicate_pair: %s is not a confirmed NILM device",
                entity_2,
            )

    async def _handle_accept_drift(call: ServiceCall) -> None:
        entity_id = call.data["entity_id"]
        geaccepteerd = False
        for coordinator in _iter_coordinators():
            if coordinator.accept_nilm_device_drift(entity_id):
                geaccepteerd = True
        if not geaccepteerd:
            _LOGGER.warning(
                "accept_nilm_device_drift: %s is geen bevestigd NILM-apparaat",
                entity_id,
            )

    hass.services.async_register(
        DOMAIN, SERVICE_CONFIRM_NILM_DEVICE, _handle_confirm, schema=NILM_SERVICE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ACCEPT_NILM_DRIFT,
        _handle_accept_drift,
        schema=NILM_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DISMISS_NILM_DUPLICATE,
        _handle_dismiss_duplicate,
        schema=NILM_DUPLICATE_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CONFIRM_NILM_DUPLICATE,
        _handle_confirm_duplicate,
        schema=NILM_DUPLICATE_SERVICE_SCHEMA,
    )
    async def _handle_confirm_water_source(call: ServiceCall) -> None:
        """v1.18.0, gevraagd: "Misschien is er een mechanisme te
        bedenken zodat ik ook daadwerkelijk kan bevestigen dat
        bijvoorbeeld de wc is doorgespoeld, en je daarvan leert?"

        Dezelfde opzet als de NILM-bevestiging: het vermoeden is een
        startpunt, de bevestiging maakt er een feit van.
        """
        bron = call.data["bron"]
        for gegevens in hass.data.get(DOMAIN, {}).values():
            coordinator = (gegevens or {}).get("coordinator")
            if coordinator is not None:
                coordinator.confirm_water_source(bron)

    hass.services.async_register(
        DOMAIN,
        "confirm_water_source",
        _handle_confirm_water_source,
        schema=vol.Schema({vol.Required("bron"): cv.string}),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REJECT_NILM_DEVICE, _handle_reject, schema=NILM_SERVICE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UNCONFIRM_NILM_DEVICE,
        _handle_unconfirm,
        schema=NILM_SERVICE_SCHEMA,
    )


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
