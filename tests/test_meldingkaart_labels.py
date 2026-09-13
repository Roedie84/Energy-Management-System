"""Twee meldingen met dezelfde naam op één pagina (v3.95.5).

Gevonden bij het nalopen van alle kaarten. Op de meldingenpagina staan
twee schakelaars met exact dezelfde tekst:

    Accu haalt de nacht niet   ... demping 60 min
    Accu haalt de nacht niet   ... demping 180 min

Het zijn twee verschillende meldingen:

    plan_tekort                "Accu haalt de nacht mogelijk niet"
                               - de kwartierplanning voorziet dat de
                                 woning aan het net komt
    battery_wont_last_night    "Accu haalt de nacht niet"
                               - de overnachtingsbehoefte is groter dan
                                 wat er in de accu zit

De kaart van `plan_tekort` had het woord "mogelijk" verloren. Daarmee
zijn de twee schakelaars niet uit elkaar te houden, en weet je bij het
aantikken niet wat je uitzet.

De namen op de kaarten zijn met de hand overgeschreven uit
NOTIFICATION_TYPES. Deze toets vergelijkt ze, zodat de volgende die
verandert niet stilletjes uit de pas loopt.
"""
import re
from pathlib import Path

import yaml

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system.const import (
    NOTIFICATION_TYPES,
)

SJABLOON = Path(pkg.__file__).parent / "dashboard_template.yaml"
TITELS = {sleutel: titel for sleutel, titel, _, _, _ in NOTIFICATION_TYPES}


def _meldingkaarten():
    """(sleutel, tekst op de kaart) voor elke meldingschakelaar."""
    doc = yaml.safe_load(SJABLOON.read_text())
    uit = []

    def loop(o):
        if isinstance(o, dict):
            entiteit = o.get("entity")
            primair = o.get("primary")
            if (
                isinstance(entiteit, str)
                and "_melding_" in entiteit
                and isinstance(primair, str)
            ):
                sleutel = entiteit.split("_melding_", 1)[1]
                uit.append((sleutel, primair.strip()))
            for v in o.values():
                loop(v)
        elif isinstance(o, list):
            for v in o:
                loop(v)

    loop(doc["views"])
    return uit


def test_every_notification_card_uses_its_own_title():
    """Het geval hierboven: "mogelijk" was weggevallen."""
    fout = []
    for sleutel, tekst in _meldingkaarten():
        verwacht = TITELS.get(sleutel)
        if verwacht is None:
            continue
        if tekst != verwacht:
            fout.append(f"{sleutel}: kaart '{tekst}' tegen '{verwacht}'")

    assert not fout, fout


def test_no_two_cards_carry_the_same_label():
    """Twee schakelaars met dezelfde tekst zijn niet uit elkaar te

    houden, ook niet als beide teksten los kloppen.
    """
    teksten = [tekst for _, tekst in _meldingkaarten()]
    dubbel = sorted({t for t in teksten if teksten.count(t) > 1})

    assert not dubbel, dubbel


def test_every_card_points_at_a_known_kind():
    """Een schakelaar voor een melding die niet bestaat, doet niets."""
    onbekend = sorted(
        {s for s, _ in _meldingkaarten() if s not in TITELS}
    )

    assert not onbekend, onbekend
