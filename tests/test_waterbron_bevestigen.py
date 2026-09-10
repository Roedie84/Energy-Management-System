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


def test_de_knop_hangt_aan_het_apparaat_en_heeft_een_vaste_entiteit(make_coordinator, hass):
    """v4.9.2. Gemeld na de installatie:

        6 dashboardkaart(en) wijzen naar niets
        Deze entiteiten bestaan niet (meer):
        button.woonkamer_energy_management_system_water_was_douche ...

    De knoppen werden wel aangemaakt, maar zonder `device_info`. Met
    `has_entity_name = True` en geen apparaat leidt Home Assistant het
    entiteits-id af zonder de apparaatnaam ervoor:
    `button.water_was_toilet` in plaats van
    `button.woonkamer_energy_management_system_water_was_toilet`. De
    kaarten wezen dus naar iets dat niet bestond.

    De bestaande knoppen doen twee dingen die ik oversloeg: ze zetten
    `_attr_device_info`, en de NILM-knoppen zetten het entiteits-id
    expliciet - juist omdat het anders van de apparaatnaam afhangt.
    """
    from custom_components.energy_management_system.button import WaterbronKnop
    from custom_components.energy_management_system.const import DOMAIN

    knop = WaterbronKnop(make_coordinator({}), "entry1", "toilet")

    assert knop._attr_device_info["identifiers"] == {(DOMAIN, "entry1")}
    assert knop.entity_id == (
        "button.woonkamer_energy_management_system_water_was_toilet"
    )


def test_elke_bron_krijgt_een_eigen_entiteit(make_coordinator, hass):
    from custom_components.energy_management_system.button import WaterbronKnop

    c = make_coordinator({})
    ids = {
        WaterbronKnop(c, "entry1", bron).entity_id for bron in WATERBRONNEN
    }

    assert len(ids) == len(WATERBRONNEN)


def test_de_kaart_wijst_naar_bestaande_entiteiten():
    """De ratel: elk entiteits-id dat de waterchips gebruiken, moet door
    een knop worden gezet."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    from custom_components.energy_management_system.button import WaterbronKnop

    kaart = (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    for bron in WATERBRONNEN:
        entiteit = WaterbronKnop(None, "entry1", bron).entity_id
        assert entiteit in kaart, entiteit
