"""De meldingskaart raakte zijn tekst kwijt (v4.8).

Gemeld met een schermafdruk van de meldingenpagina:

    10 Sep 09:15 · 't Goedkope blok begint zo
    (bericht niet bewaard — melding van vóór v1.6.3)

Dat klopt niet: die melding is van vanochtend. De kaart leest
`meldingen_historie` op de statussensor, en in v3.99.17 heb ik het
bericht daaruit gehaald - het attributenblok kwam boven de 16 kB van de
recorder. De kaart heeft toen zijn tekst verloren en viel terug op een
melding over v1.6.3 die nergens meer op slaat.

De oplossing is optie B uit de foutmelding van 8 september: een APARTE
sensor voor de meldingen, met de volledige tekst. `system_status` blijft
klein en wordt weer bewaard door de recorder; de meldingssensor draagt
de tekst voor de kaart. Twintig meldingen met bericht is ruim onder de
grens, en die sensor herstelt niets - er gaat dus niets verloren als de
recorder hem overslaat.
"""
import json

import pytest


def test_de_statussensor_draagt_geen_berichten():
    """Waarom het bericht daar weg moest: de 16 kB-grens."""
    from custom_components.energy_management_system.sensor import (
        _meldingen_voor_de_kaart,
    )

    kort = _meldingen_voor_de_kaart(
        [{"moment": "m", "titel": "t", "soort": "s", "verstuurd": True, "bericht": "x" * 900}]
    )

    assert "bericht" not in kort[0]


def test_de_meldingensensor_draagt_ze_wel(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import MeldingenSensor

    c = make_coordinator({})
    c.notification_history = [
        {"moment": f"2026-09-10T09:{i:02d}:00+02:00", "soort": "cheap_block_soon",
         "titel": "'t Goedkope blok begint zo", "bericht": "Van 09:30 tot 17:30.",
         "verstuurd": True}
        for i in range(30)
    ]
    s = MeldingenSensor(c, "entry1")

    assert s.native_value == 30
    meldingen = s.extra_state_attributes["meldingen"]
    assert len(meldingen) == 12
    assert meldingen[0]["moment"].endswith("09:29:00+02:00")   # nieuwste bovenaan
    assert meldingen[0]["bericht"] == "Van 09:30 tot 17:30."


def test_de_sensor_blijft_ruim_onder_de_grens(make_coordinator, hass):
    """De langste soort berichten, meer dan er passen."""
    from custom_components.energy_management_system.sensor import MeldingenSensor

    c = make_coordinator({})
    c.notification_history = [
        {"moment": "2026-09-10T09:00:00+02:00", "soort": "mode_change",
         "titel": "⏳ Accu: huis dekken", "bericht": "x" * 950, "verstuurd": True}
        for _ in range(30)
    ]
    s = MeldingenSensor(c, "entry1")

    omvang = len(json.dumps(s.extra_state_attributes, ensure_ascii=False))
    assert omvang < 16384, omvang


def test_de_sensor_herstelt_niets():
    """Slaat de recorder hem over, dan gaat er niets verloren - de
    geschiedenis staat in de Store."""
    import ast
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "sensor.py").read_text()
    i = bron.index("class MeldingenSensor")
    j = bron.index("\nclass ", i + 10)

    assert "async_added_to_hass" not in bron[i:j]
