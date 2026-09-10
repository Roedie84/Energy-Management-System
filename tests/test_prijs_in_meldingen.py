"""Prijzen in meldingen in euro's, niet in rauwe eenheden (v4.9).

Gemeld met de melding van 10 september 00:00:

    Om 19:45 kost stroom 8631642.0000 EUR/kWh, ruim het dubbele van de
    mediaan van vandage (3406983.0000 EUR/kWh).

De prijsreeks staat intern in eenheden van 1e-7 euro
(PRICE_SCALE_FACTOR); dat is een bewuste keuze en overal in de code
wordt er door gedeeld waar een absoluut bedrag telt. Ik dacht eerst dat
die deling structureel ontbrak en heb de reeks bij de bron willen
omrekenen - waarna vier toetsen rond de reservebodem omvielen. Dat was
mijn fout: de deling stond er wel, op alle plekken waar hij hoort. Op
EEN plek niet: de tekst van deze melding.

Deze toets vangt het geval, en de scan eronder vangt de klasse: een
tekst met "EUR/kWh" of "ct" erin mag geen rauwe reeksprijs bevatten.
"""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import custom_components.energy_management_system as pkg
import pytest

from custom_components.energy_management_system.const import PRICE_SCALE_FACTOR

NU = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)


def test_de_melding_noemt_euros(make_coordinator, hass):
    """Het geval uit het logboek: piek 0,863, mediaan 0,341."""
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["appliance_notify_service"] = "notify.test"
    c.notification_enabled = {"exceptional_peak_price": True}
    c.notifications_master_enabled = True
    c.notification_history = []
    entries = [
        (
            NU + timedelta(minutes=15 * i),
            NU + timedelta(minutes=15 * (i + 1)),
            (0.8631642 if i == 79 else 0.2020) * PRICE_SCALE_FACTOR,
        )
        for i in range(96)
    ]

    bericht = c._uitzonderlijke_piekprijs_bericht(entries, NU)

    assert bericht is not None
    assert "0.8632" in bericht or "0,8632" in bericht
    assert "8631642" not in bericht
    getallen = [float(g) for g in re.findall(r"\d+\.\d+", bericht)]
    assert all(g < 100 for g in getallen), getallen


def test_zonder_uitschieter_geen_melding(make_coordinator, hass):
    c = make_coordinator({})
    entries = [
        (NU + timedelta(minutes=15 * i), NU + timedelta(minutes=15 * (i + 1)),
         0.25 * PRICE_SCALE_FACTOR)
        for i in range(96)
    ]

    assert c._uitzonderlijke_piekprijs_bericht(entries, NU) is None


def test_geen_enkele_tekst_toont_een_rauwe_reeksprijs():
    """De scan, per FUNCTIE: gebruikt een functie een rauwe reeksprijs
    (`e[2]`) EN maakt hij een bedrag in EUR/kWh of ct op, dan moet
    PRICE_SCALE_FACTOR er ook in staan. Een venster van een paar regels
    was te smal - de deling staat soms tien regels boven de tekst."""
    import ast

    boom = ast.parse((Path(pkg.__file__).parent / "coordinator.py").read_text())
    fouten = []
    for knoop in ast.walk(boom):
        if not isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        bron = ast.unparse(knoop)
        toont_bedrag = re.search(r"EUR/kWh|€/kWh", bron)
        rauwe_prijs = re.search(r"\b(e|entry)\[2\]", bron)
        if toont_bedrag and rauwe_prijs and "PRICE_SCALE_FACTOR" not in bron:
            fouten.append(knoop.name)
    assert not fouten, fouten
