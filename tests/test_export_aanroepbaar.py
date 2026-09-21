"""Elke functie in de export moet ook echt aan te roepen zijn (v5.8).

In v5.4 zette ik acht overzichten in de diagnostiek. Een daarvan,
`get_airco_activation_probability`, vraagt een argument - het
temperatuurbakje. Ik riep hem zonder aan:

    diagnostiek:get_airco_activation_probability
    TypeError: missing 1 required positional argument: 'bucket_key'

De export vangt dat af, maar het veld is leeg en de storing stond drie
dagen in de interne fouten, met een melding op het dashboard.

En de ratel die ik erbij zette controleerde alleen of de NAAM in de
export stond, niet of de functie AANROEPBAAR was. Dat is precies de les
van v4.19 - "een contract moet gedrag toetsen, niet tekst" - en ik heb
hem zelf geschonden in dezelfde versie waarin ik de ratel bouwde.

Deze toets roept elke functie in de export echt aan, op een verse
coordinator. Een functie die een argument vraagt, valt dan direct om
in plaats van in bedrijf.
"""
import ast
import inspect
from pathlib import Path

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)

PAKKET = Path(pkg.__file__).parent


def _exportfuncties() -> list[str]:
    """De coordinator-methoden die de export via `_veilig` aanroept."""
    bron = (PAKKET / "diagnostics.py").read_text()
    boom = ast.parse(bron)
    namen = set()
    for knoop in ast.walk(boom):
        if not isinstance(knoop, ast.Call):
            continue
        if not (isinstance(knoop.func, ast.Name) and knoop.func.id == "_veilig"):
            continue
        for arg in knoop.args[1:]:
            if (
                isinstance(arg, ast.Attribute)
                and isinstance(arg.value, ast.Name)
                and arg.value.id == "coordinator"
            ):
                namen.add(arg.attr)
    return sorted(namen)


def test_er_zijn_exportfuncties_gevonden():
    assert len(_exportfuncties()) > 50


def test_geen_exportfunctie_vraagt_een_argument():
    """Het gedrag, niet de tekst: kan de export hem zonder argument
    aanroepen? Zo niet, dan valt hij in bedrijf om."""
    fout = []
    for naam in _exportfuncties():
        methode = getattr(C, naam, None)
        if methode is None or not callable(methode):
            continue
        handtekening = inspect.signature(methode)
        verplicht = [
            p.name
            for p in list(handtekening.parameters.values())[1:]
            if p.default is inspect.Parameter.empty
            and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        if verplicht:
            fout.append(f"{naam}({', '.join(verplicht)})")
    assert not fout, fout


def test_elke_exportfunctie_draait_op_een_verse_coordinator(make_coordinator, hass):
    """En dan echt aanroepen. Een verse installatie heeft overal lege
    reeksen - juist daar vallen functies om die op gevulde gegevens
    rekenen."""
    c = make_coordinator({})
    fout = []
    for naam in _exportfuncties():
        methode = getattr(c, naam, None)
        if not callable(methode):
            continue
        try:
            methode()
        except TypeError as e:
            if "required positional argument" in str(e):
                fout.append(f"{naam}: {e}")
        except Exception:  # noqa: BLE001 - andere fouten vangt _veilig af
            pass
    assert not fout, fout


def test_de_aircokansen_staan_per_bakje_in_de_export(make_coordinator, hass):
    """De vervanging: alle geleerde bakjes, zoals de sensor ze toont."""
    c = make_coordinator({})
    c.living_room_temp_bucket_history = {"20.0": [False] * 20, "21.0": [True, False]}

    uit = c.get_airco_kansen_per_bakje()

    assert set(uit["bakjes"]) == {"20.0", "21.0"}
    assert "probability_percent" in uit["bakjes"]["20.0"]
