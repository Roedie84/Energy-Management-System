"""Elke melding zegt waardoor en wat te doen (v4.3).

Gevraagd: "Maar wat kan ik er mee, dat geldt eigenlijk voor alle
meldingen, ik wil graag dat de integratie ook aangeeft waardoor, wat te
doen. Niet alleen specifiek voor deze melding maar voor alles."

"Sluipverbruik-detectie staat aan: structurele stijging in het
dagelijkse basisverbruik" vertelt WAT er is gezien, en niets over waar
het vandaan komt of wat er te doen valt. Dat gold voor bijna alle
negenendertig soorten.
"""
import pytest

from custom_components.energy_management_system.const import (
    MELDING_ADVIES,
    NOTIFICATION_TYPES,
)


def test_elke_soort_heeft_een_advies():
    """De ratel: een nieuwe meldingssoort zonder advies laat deze
    omvallen."""
    soorten = {k for k, *_ in NOTIFICATION_TYPES}

    ontbreekt = sorted(soorten - set(MELDING_ADVIES))

    assert not ontbreekt, ontbreekt


def test_er_staan_geen_adviezen_voor_soorten_die_niet_bestaan():
    soorten = {k for k, *_ in NOTIFICATION_TYPES}

    verdwenen = sorted(set(MELDING_ADVIES) - soorten)

    assert not verdwenen, verdwenen


def test_elk_advies_heeft_twee_zinnen_met_inhoud():
    """Twee delen: waardoor en wat te doen. Geen van beide leeg, en geen
    van beide een herhaling van de titel."""
    titels = {k: titel for k, titel, *_ in NOTIFICATION_TYPES}
    kort = []
    for soort, advies in MELDING_ADVIES.items():
        assert len(advies) == 2, soort
        waardoor, doen = advies
        if len(waardoor) < 40 or len(doen) < 20:
            kort.append(soort)
        assert titels[soort].lower() not in waardoor.lower(), soort
    assert not kort, kort


def test_het_bericht_draagt_het_advies(make_coordinator, hass):
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["appliance_notify_service"] = "notify.test"
    c.notification_enabled = {"sluipverbruik": True}
    c.notifications_master_enabled = True
    c.notification_history = []

    c._dispatch_notification(
        "notify.test", "⚠️ Mogelijk sluipverbruik", "Het basisverbruik steeg met 40 W.",
        "ems_sluipverbruik", kind="sluipverbruik",
    )

    bericht = c.notification_history[-1]["bericht"]
    assert "Waardoor:" in bericht
    assert "Wat te doen:" in bericht
    assert "02:00" in bericht          # de concrete handeling
    assert bericht.startswith("Het basisverbruik steeg met 40 W.")


def test_zonder_advies_geen_lege_kopjes(make_coordinator, hass):
    """Een melding zonder `kind` (bijvoorbeeld een herstelmelding) krijgt
    geen kopjes, geen lege regels."""
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["appliance_notify_service"] = "notify.test"
    c.notification_history = []

    c._dispatch_notification(
        "notify.test", "✅ Opgelost", "Alles weer in orde.",
        "ems_x", geschiedenis_soort="x_hersteld",
    )

    assert c.notification_history[-1]["bericht"] == "Alles weer in orde."
