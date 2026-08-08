"""Procenten en procentpunten uit elkaar houden (v1.15.7).

Gemeld met screenshot: de rendementskaart zei "vorige meting was 94.0%
(-34.6%)" naast een tegel die 86,9% toonde.

Twee dingen misten. Het verschil tussen 94,0 en 59,4 is 34,6
PROCENTPUNTEN, niet 34,6 procent - en "%" achter een verschil leest als
een procentuele daling. Bovendien vergeleek de kaart twee LOSSE
laadcycli terwijl de tegel ernaast de MEDIAAN toont, zodat het leek
alsof die 34,6 op de 86,9% sloeg.

De mediaan bestaat juist omdat één cyclus sterk kan afwijken (v0.63.10).
Dat verschil tonen zonder uit te leggen waarom, maakt het onbruikbaar.
"""
import re
from pathlib import Path

import custom_components.energy_management_system as pkg

PAKKET = Path(pkg.__file__).parent


def _efficiency_card() -> str:
    yaml_tekst = (PAKKET / "dashboard_template.yaml").read_text()
    start = yaml_tekst.index("Laatste laadcyclus")
    return yaml_tekst[max(0, start - 600) : start + 600]


def test_a_difference_is_labelled_as_percentage_points():
    kaart = _efficiency_card()

    assert "procentpunt" in kaart
    assert "%)" not in kaart.split("procentpunt")[0][-40:]


def test_the_card_says_what_it_compares():
    """"Vorige meting" zonder te zeggen wat dat is, laat je gissen -
    zeker naast een tegel die iets anders toont."""
    kaart = _efficiency_card()

    assert "Laatste laadcyclus" in kaart
    assert "mediaan" in kaart


def test_it_explains_why_the_tile_differs():
    """Zonder die uitleg lijkt het alsof een van de twee getallen fout
    is."""
    kaart = _efficiency_card()

    assert "nauwelijks in mee" in kaart


def test_the_code_uses_percentage_points_consistently():
    """In de coordinator wordt "procentpunt" al correct gebruikt voor
    weerbronnen en drift; het dashboard liep daarop achter."""
    bron = (PAKKET / "coordinator.py").read_text()

    for fragment in ("verschil_procentpunt", "procentpunt "):
        assert fragment in bron, fragment
