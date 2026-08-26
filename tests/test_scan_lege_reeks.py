"""Structuurscan 12: `min()` op een gefilterde reeks (v3.45.2).

Uit een echte storing voortgekomen. Op 26 augustus 07:05 vielen twee
sensoren weg - `zendure_manager_available_kwh` en `hw_p1_vermogen`,
allebei minstens een kwartier lang. Om 09:15 lagen vijf onderdelen
eruit:

    ValueError: min() iterable argument is empty

De code stond er zo:

    min(r["soc_bruikbaar_procent"] for r in plan
        if r.get("soc_bruikbaar_procent") is not None) if plan else None

De bewaking kijkt naar `plan` - de HERKOMST - terwijl de reeks die in
`min()` gaat door een filter is gehaald. Het plan bevatte 59 kwartieren,
dus `if plan` was waar; geen enkel kwartier had nog een bruikbare
accustand, dus de reeks was leeg.

Eén regel hoger staat het wél goed: `min(socs) if socs`. Daar wordt de
lijst zelf getoetst.

Deze scan zoekt dat patroon: een `min` of `max` over een comprehension
mét filter, bewaakt door een toets op precies de lijst waar de
comprehension overheen loopt.
"""
import ast
from pathlib import Path

import pytest

import custom_components.energy_management_system as pkg

MAP = Path(pkg.__file__).parent
BESTANDEN = sorted(MAP.glob("*.py"))


def _verdachte_regels(pad: Path) -> list[str]:
    boom = ast.parse(pad.read_text())
    gevonden = []
    for knoop in ast.walk(boom):
        if not isinstance(knoop, ast.IfExp):
            continue
        aanroep = knoop.body
        if not (
            isinstance(aanroep, ast.Call)
            and isinstance(aanroep.func, ast.Name)
            and aanroep.func.id in ("min", "max", "statistics")
        ):
            continue
        if not aanroep.args:
            continue
        arg = aanroep.args[0]
        if not isinstance(arg, (ast.GeneratorExp, ast.ListComp)):
            continue
        # Zonder filter kan de reeks niet leeglopen terwijl de bron vol is.
        if not any(g.ifs for g in arg.generators):
            continue
        bewaakt = {
            n.id for n in ast.walk(knoop.test) if isinstance(n, ast.Name)
        }
        doorlopen = {
            g.iter.id for g in arg.generators if isinstance(g.iter, ast.Name)
        }
        if bewaakt and bewaakt <= doorlopen:
            gevonden.append(
                f"{pad.name}:{knoop.lineno} - {aanroep.func.id}() over een "
                f"gefilterde reeks, bewaakt door {sorted(bewaakt)}"
            )
    return gevonden


@pytest.mark.parametrize("pad", BESTANDEN, ids=lambda p: p.name)
def test_no_guard_checks_the_source_instead_of_the_values(pad):
    """Een filter kan een reeks leegmaken terwijl de bron gevuld blijft.

    Dan hoort de toets op de gefilterde reeks te staan.
    """
    verdacht = _verdachte_regels(pad)

    assert not verdacht, "\n".join(verdacht)


def test_the_scan_catches_the_storing_of_26_august(tmp_path):
    """Een scan die niets vindt in code die klopt, bewijst niets."""
    code = '''
def samenvatting(plan):
    return {
        "laagste": (
            min(r["soc"] for r in plan if r.get("soc") is not None)
            if plan
            else None
        )
    }
'''
    pad = tmp_path / "voorbeeld.py"
    pad.write_text(code)

    assert len(_verdachte_regels(pad)) == 1


def test_a_guard_on_the_filtered_list_is_fine(tmp_path):
    """De vorm die er één regel hoger al stond, en die klopt."""
    code = '''
def samenvatting(plan):
    socs = [r["soc"] for r in plan if r["soc"] is not None]
    return {"laagste": min(socs) if socs else None}
'''
    pad = tmp_path / "goed.py"
    pad.write_text(code)

    assert _verdachte_regels(pad) == []


def test_an_unfiltered_comprehension_is_fine(tmp_path):
    """Zonder filter loopt de reeks niet leeg terwijl de bron vol is."""
    code = '''
def samenvatting(plan):
    return {"laagste": min(r["soc"] for r in plan) if plan else None}
'''
    pad = tmp_path / "ongefilterd.py"
    pad.write_text(code)

    assert _verdachte_regels(pad) == []
