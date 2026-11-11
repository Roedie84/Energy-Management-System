"""Het detaildashboard zelf aanmelden bij Home Assistant (v5.218.0).

De cockpit linkt naar /energy-management-system/<pagina>. Het bestand met die
pagina's werd al bij elke start naar de configuratiemap gekopieerd, maar
niemand meldde het aan: zonder eigen regel in configuration.yaml bestond het
dashboard niet en leidden de links nergens heen (gevonden 11-11).

Hier wordt het als YAML-dashboard aangemeld, op dezelfde manier als Home
Assistant dat zelf doet voor `lovelace: dashboards:`. Het staat niet in de
zijbalk; de cockpit is de ingang. Omdat het bestand bij elke start wordt
overschreven volgt het dashboard elke release vanzelf.

De Home Assistant-imports staan in de functie: de toetsen laden dit pakket
met een nagebootste `homeassistant` zonder Lovelace.
"""
from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

DETAIL_URL_PAD = "energy-management-system"
DETAIL_TITEL = "EMS details"
DETAIL_ICOON = "mdi:home-lightning-bolt-outline"


def detail_config(bestandsnaam: str) -> dict:
    """De dashboardbeschrijving zoals Lovelace die voor YAML-dashboards kent."""
    return {
        "mode": "yaml",
        "title": DETAIL_TITEL,
        "icon": DETAIL_ICOON,
        "show_in_sidebar": False,
        "require_admin": False,
        "filename": bestandsnaam,
    }


def registreer_detaildashboard(hass, bestandsnaam: str) -> str:
    """Meld het detaildashboard aan. Geeft terug wat er gebeurde.

    "aangemeld", "bestond al" (een eigen dashboard op dit pad gaat voor) of
    "niet mogelijk: <reden>". Mag de opstart nooit tegenhouden.
    """
    try:
        from homeassistant.components import lovelace as ll
        from homeassistant.components.lovelace import dashboard as ll_dashboard
    except ImportError as err:
        return f"niet mogelijk: geen Lovelace ({err})"

    gegevens = hass.data.get("lovelace")
    dashboards = getattr(gegevens, "dashboards", None)
    if dashboards is None and isinstance(gegevens, dict):
        dashboards = gegevens.get("dashboards")
    if dashboards is None:
        return "niet mogelijk: Lovelace is nog niet geladen"
    if DETAIL_URL_PAD in dashboards:
        return "bestond al"

    config = detail_config(bestandsnaam)
    try:
        dashboards[DETAIL_URL_PAD] = ll_dashboard.LovelaceYAML(hass, DETAIL_URL_PAD, config)
        registreer = getattr(ll, "_register_panel", None)
        if registreer is not None:
            registreer(hass, DETAIL_URL_PAD, "yaml", config, False)
        else:  # pragma: no cover - oudere of nieuwere Lovelace zonder die helper
            from homeassistant.components import frontend

            frontend.async_register_built_in_panel(
                hass,
                "lovelace",
                frontend_url_path=DETAIL_URL_PAD,
                require_admin=False,
                config={"mode": "yaml"},
                update=False,
            )
    except ValueError:
        # Het paneel bestond al (herladen van de integratie): het dashboard
        # zelf staat er, dat is genoeg.
        return "bestond al"
    except Exception as err:  # noqa: BLE001 - de Lovelace-API varieert per versie
        dashboards.pop(DETAIL_URL_PAD, None)
        return f"niet mogelijk: {err}"
    return "aangemeld"
