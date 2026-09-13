"""Structuurscan 13: elk attribuut bestaat vóór het gelezen wordt
(v3.45.3).

Uit een echte storing voortgekomen, met traceback:

    File "coordinator.py", line 15534, in _meld_planningswijzigingen
      if self._plan_tekort_vrij_sinds is None:
    AttributeError: 'EnergyManagementSystemCoordinator' object has no
    attribute '_plan_tekort_vrij_sinds'

Dat veld werd op vijf plekken gezet en op één plek gelezen, en stond
niet in `__init__`. In vrijwel elk pad wordt het eerst gezet en dan
gelezen - behalve als er eerder een tekortmelding is geweest die daarna
verdwijnt, zonder herstart ertussen. Zeldzaam genoeg om jaren te blijven
zitten.

Dit is de derde storing in vier dagen van dezelfde familie: een waarde
die er in de praktijk altijd was, tot hij er een keer niet was. Eerst
een leeg uurprofiel na de resetknop, toen een weggevallen sensor, nu een
attribuut dat nooit is aangemaakt.

De scan kijkt naar de coordinator, want daar zit de toestand. Attributen
die alleen via `getattr(self, ...)` worden benaderd tellen niet mee -
daar is de afwezigheid uitdrukkelijk afgevangen.
"""
import ast
from pathlib import Path

import pytest

import custom_components.energy_management_system as pkg

MAP = Path(pkg.__file__).parent


def _klasse(pad: Path, naam_bevat: str):
    boom = ast.parse(pad.read_text())
    for knoop in ast.walk(boom):
        if isinstance(knoop, ast.ClassDef) and naam_bevat in knoop.name:
            return knoop
    return None


def _ongezette_attributen(klasse: ast.ClassDef, bron: str) -> list[str]:
    init = next(
        (
            n
            for n in klasse.body
            if isinstance(n, ast.FunctionDef) and n.name == "__init__"
        ),
        None,
    )
    if init is None:
        return []

    # v3.58.0: ook wat de door `__init__` aangeroepen hulpfuncties
    # zetten.
    #
    # De ratel dwong af dat er een blok uit `__init__` moest; die velden
    # staan nu in `_init_laatste_beslissing()`. Ze zijn daarmee niet
    # minder geinitialiseerd - deze scan keek alleen op de verkeerde
    # plek, en zou anders elke opsplitsing bestraffen.
    hulpfuncties = {
        n.func.attr
        for n in ast.walk(init)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "self"
    }
    zetters = [init] + [
        n
        for n in klasse.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name in hulpfuncties
    ]
    gezet = {
        n.attr
        for zetter in zetters
        for n in ast.walk(zetter)
        if isinstance(n, ast.Attribute)
        and isinstance(n.value, ast.Name)
        and n.value.id == "self"
        and isinstance(n.ctx, ast.Store)
    }
    gelezen, geschreven = set(), set()
    for n in ast.walk(klasse):
        if (
            isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name)
            and n.value.id == "self"
        ):
            if isinstance(n.ctx, ast.Store):
                geschreven.add(n.attr)
            else:
                gelezen.add(n.attr)

    # v3.96.0: een klasse-attribuut met een beginwaarde telt ook.
    #
    # `_nachtrust_onderbroken_sinds: datetime | None = None` staat op de
    # klasse en niet in `__init__` - omdat die op de ratel van v3.35.0
    # staat. Zo'n veld IS geinitialiseerd; deze scan keek alleen naar
    # `__init__`, net als in v3.58.0 met de hulpfuncties.
    gezet |= {
        n.target.id
        for n in klasse.body
        if isinstance(n, ast.AnnAssign)
        and isinstance(n.target, ast.Name)
        and n.value is not None
    }
    gezet |= {
        doel.id
        for n in klasse.body
        if isinstance(n, ast.Assign)
        for doel in n.targets
        if isinstance(doel, ast.Name)
    }

    # Methoden en eigenschappen zijn geen toestand.
    namen = {
        n.name
        for n in klasse.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    # Wat via getattr wordt gelezen, is uitdrukkelijk afgevangen.
    via_getattr = set(
        __import__("re").findall(r'getattr\(self, "([a-z_]+)"', bron)
    )

    return sorted(
        a
        for a in (gelezen & geschreven) - gezet - namen - via_getattr
        if not a.startswith("__")
    )


def test_the_coordinator_initialises_everything_it_reads():
    """De aanleiding: één veld, vijf schrijvers, één lezer, geen

    beginwaarde - en dat lezen kwam in één pad eerst.
    """
    pad = MAP / "coordinator.py"
    bron = pad.read_text()

    ontbreekt = _ongezette_attributen(_klasse(pad, "Coordinator"), bron)

    assert not ontbreekt, (
        "deze attributen worden gelezen en geschreven maar staan niet in "
        f"__init__: {ontbreekt}"
    )


def test_the_tracker_initialises_everything_it_reads():
    pad = MAP / "solar_forecast.py"
    bron = pad.read_text()
    klasse = _klasse(pad, "Tracker")

    assert not _ongezette_attributen(klasse, bron)


def test_the_scan_catches_the_crash_of_26_august(tmp_path):
    """Een scan die niets vindt in code die klopt, bewijst niets."""
    code = '''
class Iets:
    def __init__(self):
        self.teller = 0

    def melden(self, nu):
        if self._vrij_sinds is None:
            self._vrij_sinds = nu

    def wissen(self):
        self._vrij_sinds = None
'''
    pad = tmp_path / "voorbeeld.py"
    pad.write_text(code)

    ontbreekt = _ongezette_attributen(_klasse(pad, "Iets"), code)

    assert ontbreekt == ["_vrij_sinds"]


def test_getattr_counts_as_handled(tmp_path):
    """Wie `getattr` gebruikt, heeft de afwezigheid al afgevangen."""
    code = '''
class Iets:
    def __init__(self):
        self.teller = 0

    def lezen(self):
        return getattr(self, "_los", None)

    def zetten(self):
        self._los = 1
'''
    pad = tmp_path / "getattr.py"
    pad.write_text(code)

    assert _ongezette_attributen(_klasse(pad, "Iets"), code) == []
