"""Meldingen in het Repairs-scherm van Home Assistant (v3.5.0).

Uit een externe review: "Ik mis een vermelding van Repair Issues. Veel
meldingen worden nu via notificaties, dashboard en diagnostiek
afgehandeld. Maar Home Assistant heeft tegenwoordig een uitstekend
Repairs-framework."

Terecht, en het is het beste punt uit die review. Wat er nu gebeurt bij
een ontbrekende sensor of een vastgelopen leerproces:

- een melding op de telefoon, die je wegklikt;
- een regel op een dashboardpagina die je moet opzoeken;
- een veld in de diagnostiek dat alleen bij een export zichtbaar is.

Repairs is waar een gebruiker dit soort dingen VERWACHT: bij Instellingen
naast de andere integraties, met een uitleg en een knop. En het blijft
staan tot het is opgelost, in plaats van weg te scrollen.

Alleen zaken die de gebruiker ZELF kan verhelpen komen hier terecht. Een
leerproces dat nog dagen nodig heeft is geen reparatie maar geduld, en
zoiets in Repairs zetten leert mensen het scherm te negeren.
"""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Wat er in Repairs mag verschijnen, en waarom.
#
# Elk van deze is door de gebruiker op te lossen: een veld invullen, een
# sensor herstellen, een integratie bijwerken. Wat alleen tijd nodig
# heeft hoort hier NIET.
REPAIR_ONTBREKENDE_INGANG = "ontbrekende_ingang"
REPAIR_HALVE_INSTALLATIE = "halve_installatie"
REPAIR_INTERNE_FOUT = "interne_fout"
REPAIR_DASHBOARD_ENTITEIT = "dashboard_entiteit"


def _issue_registry():
    """Het Repairs-kader, of niets als het niet beschikbaar is."""
    try:
        from homeassistant.helpers import issue_registry

        return issue_registry
    except ImportError:  # pragma: no cover - zeer oude Home Assistant
        return None


def meld(
    hass: HomeAssistant,
    sleutel: str,
    vertaalsleutel: str,
    plaatshouders: dict[str, str],
    ernstig: bool = False,
) -> None:
    """Zet een melding in Repairs, of ververst een bestaande."""
    ir = _issue_registry()
    if ir is None:
        return
    try:
        ir.async_create_issue(
            hass,
            "energy_management_system",
            sleutel,
            is_fixable=False,
            severity=(
                ir.IssueSeverity.ERROR if ernstig else ir.IssueSeverity.WARNING
            ),
            translation_key=vertaalsleutel,
            translation_placeholders=plaatshouders,
        )
    except Exception:  # noqa: BLE001 - een melding mag nooit breken
        _LOGGER.exception("Kon de reparatiemelding %s niet plaatsen", sleutel)


def los_op(hass: HomeAssistant, sleutel: str) -> None:
    """Haalt een melding weg zodra het probleem over is.

    Even belangrijk als het plaatsen: een Repairs-scherm dat vol blijft
    staan met opgeloste dingen wordt niet meer gelezen.
    """
    ir = _issue_registry()
    if ir is None:
        return
    try:
        ir.async_delete_issue(hass, "energy_management_system", sleutel)
    except Exception:  # noqa: BLE001
        pass


def werk_bij(hass: HomeAssistant, coordinator) -> None:
    """Zet de huidige stand in Repairs (v3.5.0).

    Draait elke ronde. Verschijnt een probleem, dan komt de melding;
    verdwijnt het, dan gaat de melding weg.
    """
    # --- 1. Een ingang die niet leest wat hij hoort te lezen ---
    gebreken = coordinator.get_input_health() or []
    if gebreken:
        namen = ", ".join(
            str(g.get("onderdeel") or g.get("naam", "?")) for g in gebreken[:3]
        )
        meld(
            hass,
            REPAIR_ONTBREKENDE_INGANG,
            "ontbrekende_ingang",
            {"aantal": str(len(gebreken)), "namen": namen},
        )
    else:
        los_op(hass, REPAIR_ONTBREKENDE_INGANG)

    # --- 2. Een half aangekomen update ---
    #
    # Tijdens de GitHub-storing van 17 augustus (50% foutkans op
    # downloads) kan het ene bestand nieuw zijn en het andere oud. Dat is
    # aan de buitenkant niet te zien.
    bevindingen = (coordinator.get_consistency_checks() or {}).get(
        "bevindingen"
    ) or []
    installatie = [b for b in bevindingen if b["naam"] == "Installatie"]
    if installatie:
        meld(
            hass,
            REPAIR_HALVE_INSTALLATIE,
            "halve_installatie",
            {"uitleg": installatie[0]["uitleg"]},
            ernstig=True,
        )
    else:
        los_op(hass, REPAIR_HALVE_INSTALLATIE)

    # --- 3. Een onderdeel dat blijft omvallen ---
    fouten = coordinator.internal_failures or {}
    if fouten:
        meld(
            hass,
            REPAIR_INTERNE_FOUT,
            "interne_fout",
            {
                "aantal": str(len(fouten)),
                "namen": ", ".join(sorted(fouten)[:3]),
            },
            ernstig=True,
        )
    else:
        los_op(hass, REPAIR_INTERNE_FOUT)

    # --- 4. Een dashboardkaart die naar niets wijst ---
    gezondheid = coordinator.get_dashboard_health() or {}
    weg = gezondheid.get("niet_bestaande_entiteiten") or []
    if weg:
        meld(
            hass,
            REPAIR_DASHBOARD_ENTITEIT,
            "dashboard_entiteit",
            {"aantal": str(len(weg)), "namen": ", ".join(weg[:3])},
        )
    else:
        los_op(hass, REPAIR_DASHBOARD_ENTITEIT)
