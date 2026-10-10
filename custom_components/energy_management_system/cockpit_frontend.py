"""De cockpitkaart en -strategie aan de frontend geven (v5.71).

Zelfde route als StormchaseNL en Gold Scalper: het script wordt door de
integratie zelf geserveerd en als Lovelace-bron vastgelegd, met de versie
en de starttijd in de URL zodat een browser na een update nooit een oud
script uit de cache blijft gebruiken.

De Home Assistant-imports staan in de functies: de toetsen laden dit
pakket met een nagebootste `homeassistant` zonder frontend.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

COCKPIT_FILE = "ems-cockpit.js"
COCKPIT_URL = f"/{DOMAIN}/{COCKPIT_FILE}"
_GEREGISTREERD = f"{DOMAIN}_cockpit_geregistreerd"


async def _async_bron(hass, versie_url: str) -> bool:
    """Zet het script in de Lovelace-bronnenlijst, of werk de versie bij."""
    lovelace = hass.data.get("lovelace")
    bronnen = getattr(lovelace, "resources", None)
    if bronnen is None:
        return False
    try:
        if hasattr(bronnen, "async_get_info"):
            await bronnen.async_get_info()
        bestaand = [
            item
            for item in bronnen.async_items()
            if str(item.get("url", "")).split("?")[0] == COCKPIT_URL
        ]
        if any(item.get("url") == versie_url for item in bestaand):
            return True
        if bestaand:
            await bronnen.async_update_item(
                bestaand[0]["id"], {"res_type": "module", "url": versie_url}
            )
        else:
            await bronnen.async_create_item({"res_type": "module", "url": versie_url})
        return True
    except Exception as err:  # noqa: BLE001 - de Lovelace-API varieert per versie
        _LOGGER.warning("Cockpitscript niet als bron vastgelegd: %s", err)
        return False


async def async_registreer_cockpit(hass, versie: str) -> None:
    """Serveer het cockpitscript en zorg dat de frontend het laadt."""
    bron = Path(__file__).parent / "www" / COCKPIT_FILE
    if not bron.is_file():
        _LOGGER.warning("Cockpitscript niet gevonden op %s", bron)
        return
    try:
        from homeassistant.components.frontend import add_extra_js_url
        from homeassistant.components.http import StaticPathConfig
        from homeassistant.util import dt as dt_util
    except ImportError as err:  # pragma: no cover - zonder frontend geen dashboard
        _LOGGER.debug("Geen frontend: %s", err)
        return

    if not hass.data.get(_GEREGISTREERD):
        try:
            await hass.http.async_register_static_paths(
                [StaticPathConfig(COCKPIT_URL, str(bron), cache_headers=True)]
            )
        except (RuntimeError, ValueError) as err:
            _LOGGER.debug("Pad stond er al: %s", err)
        hass.data[_GEREGISTREERD] = True

    versie_url = f"{COCKPIT_URL}?v={versie}&t={int(dt_util.utcnow().timestamp())}"
    via_bron = await _async_bron(hass, versie_url)
    try:
        add_extra_js_url(hass, versie_url)
    except Exception as err:  # noqa: BLE001 - mag de opstart niet blokkeren
        _LOGGER.debug("Script niet aan de frontend meegegeven: %s", err)
    if not via_bron:
        _LOGGER.info(
            "Het cockpitscript staat niet in de Lovelace-bronnen; het laadt via "
            "de frontend. Lukt dat niet, voeg dan %s toe als JavaScript-module "
            "onder Instellingen > Dashboards > Bronnen.",
            COCKPIT_URL,
        )
