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
    assert knop.entity_id == "button.water_was_toilet"


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


def test_de_bevestigingskaart_is_een_kernkaart_met_een_kop():
    """v4.9.3. Gemeld: de knoppen waren op de waterpagina niet te zien.

    Ze stonden er wel, als `custom:mushroom-chips-card` onderaan de
    sectie - een chipsrij zonder kop, onder een lange markdownkaart, en
    afhankelijk van een custom-kaart die geïnstalleerd moet zijn. Drie
    redenen om iets niet te zien.

    Gevraagd: "zelfde opzet als bij de NILM apparaten een optie?" - en
    dat is precies goed: de NILM-bevestiging gebruikt `type: entities`
    met de kop "Beoordelen" en knopregels, en die werkt zichtbaar. Deze
    kaart volgt die opzet tot en met de grid_options; geen custom-kaart
    die geïnstalleerd moet zijn.
    """
    import yaml
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    d = yaml.safe_load((Path(pkg.__file__).parent / "dashboard_template.yaml").read_text())
    water = next(v for v in d["views"] if v.get("title") == "Water")
    kaarten = water["sections"][0]["cards"]
    kaart = next(
        k for k in kaarten
        if k.get("title") == "Bevestig de laatste onbekende watersessie"
    )
    # exact de opzet van de NILM-beoordelingskaart: kern-`entities`, een
    # kop, kale entiteitsregels, dezelfde grid_options.
    nilm = next(
        k
        for v in d["views"]
        for s in v.get("sections") or []
        for k in (s.get("cards") or [])
        if k.get("type") == "entities" and k.get("title") == "Beoordelen"
    )
    assert kaart["type"] == nilm["type"]
    assert kaart.get("grid_options") == nilm.get("grid_options")
    assert len(kaart["entities"]) == len(WATERBRONNEN)
    assert all(set(r) == {"entity"} for r in kaart["entities"])
    # direct onder de tabel, niet onderaan de pagina
    tabel = next(n for n, k in enumerate(kaarten) if "Waar ging het water heen" in str(k.get("title") or ""))
    assert kaarten.index(kaart) == tabel + 1
    assert not any(k.get("type") == "custom:mushroom-chips-card" for k in kaarten)


def test_de_kaart_wijst_naar_de_bestaande_entiteiten(make_coordinator, hass):
    """v4.9.5. Gemeld met een lijst uit Ontwikkelhulpmiddelen:
    `button.water_was_toilet` en vijf soortgenoten, aan het apparaat, met
    de goede naam - werkend.

    Die knoppen bestaan sinds v4.9.1. Alleen het ID week af van wat de
    kaart verwachtte, omdat de eerste registratie zonder `device_info`
    gebeurde en het register die toewijzing voorgoed vasthoudt. In
    v4.9.2 tot v4.9.4 heb ik geprobeerd de entiteiten naar de kaart te
    verplaatsen - drie leveringen. De kaart naar de entiteiten brengen
    was één regel.

    De knoppen van v4.9.1 registreerden zonder `device_info` als
    `button.water_was_*`, en die toewijzing van unique_id naar entity_id
    is permanent in het register. Het entity_id in v4.9.2 met de hand
    zetten hielp dus niet - het register hield vast wat het al wist.

    Precies wat er bij de NILM-knoppen staat, met "_v3" als uitkomst.
    Een nieuw unique_id heeft niets om mee te botsen.
    """
    from custom_components.energy_management_system.button import WaterbronKnop

    knop = WaterbronKnop(make_coordinator({}), "entry1", "toilet")

    # v4.9.5: geen nieuwe generatie. De entiteiten van v4.9.1 werken;
    # de KAART is naar hun naam toe gegaan in plaats van andersom.
    assert knop._attr_unique_id == "entry1_water_bevestig_toilet"
    assert knop.entity_id == "button.water_was_toilet"


def test_elke_knop_met_een_vast_entity_id_heeft_een_versiesuffix():
    """De ratel: zet een knop zijn entity_id met de hand, dan hoort het
    unique_id een generatiesuffix te hebben - anders is een verkeerde
    eerste registratie niet meer te herstellen."""
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "button.py").read_text()
    # De duplicaatknoppen (v0.63.118) zijn hun eerste generatie en zijn
    # nooit verkeerd geregistreerd; die hebben geen suffix nodig. Zodra
    # er WEL een generatie bij komt, hoort hij er te staan - vandaar de
    # lijst met wat al gecontroleerd is.
    ZONDER_SUFFIX = {"_NilmDuplicateSlotButton"}
    for blok in re.split(r"\nclass ", bron)[1:]:
        naam = blok.split("(")[0]
        if "self.entity_id = " not in blok or naam in ZONDER_SUFFIX:
            continue
        m = re.search(r"_attr_unique_id = f\"([^\"]+)\"", blok)
        assert m, naam
        # v4.9.5: WaterbronKnop heeft geen suffix nodig - zijn
        # entity_id is juist gelijk aan wat er al geregistreerd staat.
        if naam == "WaterbronKnop":
            continue
        assert re.search(r"_v\d$", m.group(1)), f"{naam}: {m.group(1)}"
