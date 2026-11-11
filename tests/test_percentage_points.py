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
from tests._coordinator_bron import coordinator_bron

PAKKET = Path(pkg.__file__).parent


def test_the_code_uses_percentage_points_consistently():
    """In de coordinator wordt "procentpunt" al correct gebruikt voor
    weerbronnen en drift; het dashboard liep daarop achter."""
    bron = coordinator_bron()

    for fragment in ("verschil_procentpunt", "procentpunt "):
        assert fragment in bron, fragment


# --- v1.85.0: de oude reeks is geen trend ----------------------------


