"""Logica in een dashboardveld gaat stil kapot (v3.95.4).

Gevraagd: "Kun je alle kaarten nakijken?"

Drie fouten op één avond zaten alle drie in een Jinja-sjabloon, niet in
de code:

- "Laagste 19%, eind 10%" - twee vensters naast elkaar (v3.95.2)
- Hetzelfde aandachtspunt twee keer, door `p[0].split('.')[0]` naast een
  lus over dezelfde lijst (v3.95.3)
- `{% set g = ... %}` twee keer in hetzelfde sjabloon met een andere
  betekenis (hieronder)

Een sjabloon draait alleen in Home Assistant, faalt daar stil, en er
staat geen toets onder. Dat is dezelfde reden als structuurscan 19.

Deze ratel meet hoeveel logica er in een sjabloon zit en laat dat niet
groeien. Nieuwe logica hoort in de coordinator, met een toets eronder -
zoals `haalt_de_accu_het_zin` en `statuskop_zin` nu.
"""
import re
from pathlib import Path

import yaml

import custom_components.energy_management_system as pkg

SJABLOON = Path(pkg.__file__).parent / "dashboard_template.yaml"

# Gemeten op v3.95.4. Alleen naar BENEDEN bijstellen.
GRENS = {
    "detail-weer": 12,
    "detail-rendement": 12,
    "detail-perioden": 11,
    "detail-aanwezigheid": 7,
    "detail-planning-samenvatting": 6,
    "detail-planning": 6,
    "detail-kwartier": 6,
    "detail-zelfconsumptie": 5,
    "detail-betrouwbaarheid": 5,
    "detail-accu": 5,
    "overzicht": 4,
    "detail-proefstand": 4,
    "detail-kwaliteit": 4,
    "detail-water": 4,
}


def _kaarten():
    doc = yaml.safe_load(SJABLOON.read_text())
    uit = []

    def loop(o, pad):
        if isinstance(o, dict):
            if isinstance(o.get("type"), str):
                uit.append((pad, o))
            for v in o.values():
                loop(v, pad)
        elif isinstance(o, list):
            for v in o:
                loop(v, pad)

    for view in doc["views"]:
        loop(view.get("sections", view.get("cards", [])), view.get("path", "?"))
    return uit


def _zwaarte(tekst: str) -> int:
    """Hoeveel BESLISSINGEN staan er in dit sjabloon?

    Tekst opmaken is prima; kiezen wat er getoond wordt en rekenen met
    getallen hoort in de code.
    """
    return (
        tekst.count("{% if")
        + tekst.count("{%- if")
        + tekst.count("{% for")
        + tekst.count("split(")
        + tekst.count("| round")
        + len(re.findall(r"[+\-*/]\s*\d", tekst))
    )


def _zwaarste_per_pagina():
    zwaarste = {}
    for pad, kaart in _kaarten():
        for veld in ("content", "primary", "secondary"):
            tekst = kaart.get(veld)
            if not isinstance(tekst, str) or "{" not in tekst:
                continue
            zwaarste[pad] = max(zwaarste.get(pad, 0), _zwaarte(tekst))
    return zwaarste


def test_no_template_grows_more_logic():
    """De ratel: er iets aan toevoegen betekent er eerst iets uit halen."""
    te_zwaar = []
    for pagina, score in sorted(_zwaarste_per_pagina().items()):
        grens = GRENS.get(pagina, 3)
        if score > grens:
            te_zwaar.append(f"{pagina}: {score} > {grens}")

    assert not te_zwaar, (
        "deze sjablonen kregen er logica bij - zet die in de coordinator, "
        f"met een toets eronder: {te_zwaar}"
    )


def test_the_ratchet_knows_every_page_it_guards():
    """Een grens voor een pagina die niet meer bestaat, bewaakt niets."""
    paginas = set(_zwaarste_per_pagina())

    verdwenen = set(GRENS) - paginas

    assert not verdwenen, verdwenen


def test_no_template_reuses_a_variable_name():
    """`{% set g = grootheden %}` en verderop `{% set g = gemiddelde %}`

    in hetzelfde sjabloon. Het ging goed omdat de eerste lus al klaar
    was, maar dat is geen eigenschap van de code - dat is geluk met de
    volgorde.
    """
    fouten = []
    for pad, kaart in _kaarten():
        for veld in ("content", "primary", "secondary"):
            tekst = kaart.get(veld)
            if not isinstance(tekst, str) or "{%" not in tekst:
                continue
            namen = re.findall(r"\{%-?\s*set\s+(\w+)\s*=", tekst)
            dubbel = sorted({n for n in namen if namen.count(n) > 1})
            if dubbel:
                fouten.append(f"{pad}/{veld}: {dubbel}")

    assert not fouten, fouten


def test_no_page_shows_the_same_card_twice():
    """Gevonden bij het nalopen van alle kaarten (v3.95.5).

    Op `detail-advies` stond de kaart "Zelflerende waarden" twee keer,
    letterlijk identiek: bovenaan als samenvatting en verderop nog een
    keer tussen de modules. Twee kaarten die hetzelfde zeggen, is het
    patroon van de landingspagina uit v3.95.3.
    """
    import json
    from collections import Counter

    doc = yaml.safe_load(SJABLOON.read_text())
    fout = []
    for view in doc["views"]:
        kaarten = []

        def loop(o):
            if isinstance(o, dict):
                if isinstance(o.get("type"), str) and o["type"] != "grid":
                    kaarten.append(json.dumps(o, sort_keys=True))
                for v in o.values():
                    loop(v)
            elif isinstance(o, list):
                for v in o:
                    loop(v)

        loop(view.get("sections", view.get("cards", [])))
        for kaart, aantal in Counter(kaarten).items():
            if aantal > 1:
                fout.append(f"{view.get('path')}: {json.loads(kaart).get('primary', kaart)[:60]}")

    assert not fout, fout
