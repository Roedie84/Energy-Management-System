"""Waterbron bevestigen zonder ontwikkelhulpmiddelen (v4.9).

Gemeld met een schermafdruk van "Waar ging het water heen?":

    08:34  8.1 L  toilet  mogelijk
    08:06  1.4 L  ?       onbekend
    07:57  4.5 L  keuken  mogelijk

En de opmerking: "Bevestigen water verbruik moet gebruiks
vriendelijker."

Twee dingen waren mis. Het kostte vijf handelingen - kaart, dan
Ontwikkelhulpmiddelen, dan de actie opzoeken, bron intikken, uitvoeren.
En de actie bevestigde altijd de LAATSTE sessie, terwijl de onbekende
meestal een paar regels lager staat: die van 08:06, niet die van 08:34.

Nu: de actie krijgt een tweede veld `sessie` met als standaard "de
laatste ONBEKENDE sessie", en er komen knoppen per bron op de
waterpagina, zodat één tik genoeg is.
"""
from datetime import datetime, timezone

import pytest

from custom_components.energy_management_system.const import WATERBRONNEN


def _sessies(c):
    c.water_session_history = [
        {"moment": "2026-09-10T07:57:00+02:00", "liters": 4.5, "bron": "keuken",
         "zekerheid": "mogelijk"},
        {"moment": "2026-09-10T08:06:00+02:00", "liters": 1.4, "bron": None,
         "zekerheid": "onbekend"},
        {"moment": "2026-09-10T08:34:00+02:00", "liters": 8.1, "bron": "toilet",
         "zekerheid": "mogelijk"},
    ]


def test_standaard_bevestigt_de_laatste_onbekende(make_coordinator, hass):
    """Niet de laatste sessie, maar de laatste die nog een vraagteken
    heeft - dat is waar je hulp iets oplevert."""
    c = make_coordinator({})
    _sessies(c)

    c.confirm_water_source("toilet")

    assert c.water_session_history[1]["bron"] == "toilet"
    assert c.water_session_history[1]["zekerheid"] == "bevestigd"
    assert c.water_session_history[2]["zekerheid"] == "mogelijk"


def test_een_bepaalde_sessie_is_te_kiezen(make_coordinator, hass):
    c = make_coordinator({})
    _sessies(c)

    c.confirm_water_source("douche", sessie="08:34")

    assert c.water_session_history[2]["bron"] == "douche"
    assert c.water_session_history[2]["zekerheid"] == "bevestigd"


def test_zonder_onbekende_sessie_de_laatste(make_coordinator, hass):
    c = make_coordinator({})
    _sessies(c)
    c.water_session_history[1]["zekerheid"] = "bevestigd"

    c.confirm_water_source("keuken")

    assert c.water_session_history[2]["bron"] == "keuken"


def test_een_onbekende_sessietijd_verandert_niets(make_coordinator, hass):
    c = make_coordinator({})
    _sessies(c)

    c.confirm_water_source("toilet", sessie="23:59")

    assert all(s["zekerheid"] != "bevestigd" for s in c.water_session_history)


def test_er_is_een_knop_per_bron():
    """Zes knopentiteiten, zodat bevestigen één tik is."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "button.py").read_text()

    assert "WaterbronKnop" in bron
    assert "for waterbron in WATERBRONNEN" in bron
    assert len(WATERBRONNEN) == 6


def test_de_knop_bevestigt_de_laatste_onbekende(make_coordinator, hass):
    from custom_components.energy_management_system.button import (
        WaterbronKnop,
    )

    c = make_coordinator({})
    _sessies(c)
    knop = WaterbronKnop(c, "entry1", "toilet")

    import asyncio

    asyncio.run(knop.async_press())

    assert c.water_session_history[1]["bron"] == "toilet"
