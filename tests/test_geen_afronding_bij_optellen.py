"""Geen afronding bij het optellen (v5.14).

Gevonden bij het bouwen van het ventilatorverbruik: elke optelling werd
afgerond op vier decimalen. 40 W per minuut is 0,000667 kWh; afgerond
0,0007 - over een uur 5% te veel. De toets die het ving, rekende toevallig
een uur door.

Een afrondfout bij het optellen is onzichtbaar in een enkele stap en groeit
met elke stap. Daarom een structurele regel, op de syntaxboom en niet op
tekst: een waarde die op zichzelf wordt opgeteld, wordt niet afgerond.

    x = round(x + stap)      verboden - de afronding stapelt zich op
    x += round(stap)         verboden - idem, per stap
    x = x + stap             goed - afronden bij het TONEN

Toen deze regel voor het eerst draaide, vond hij nog een geval: het
waterverbruik per dag, afgerond op 0,01 liter per tapbeurt. Daar was de
fout klein, maar de regel geldt zonder uitzonderingen.
"""
import ast
from pathlib import Path

import custom_components.energy_management_system as pkg

PAKKET = Path(pkg.__file__).parent


def _is_round(knoop) -> bool:
    return (
        isinstance(knoop, ast.Call)
        and isinstance(knoop.func, ast.Name)
        and knoop.func.id == "round"
    )


def test_geen_afronding_bij_optellen():
    fout = []
    for bestand in sorted(PAKKET.glob("*.py")):
        for knoop in ast.walk(ast.parse(bestand.read_text())):
            # x += round(...)
            if (
                isinstance(knoop, ast.AugAssign)
                and isinstance(knoop.op, (ast.Add, ast.Sub))
                and _is_round(knoop.value)
            ):
                fout.append(f"{bestand.name}:{knoop.lineno}  {ast.unparse(knoop)[:80]}")
            # x = round(x + ...)
            if isinstance(knoop, ast.Assign) and _is_round(knoop.value):
                som = knoop.value.args[0] if knoop.value.args else None
                if not isinstance(som, ast.BinOp) or not isinstance(
                    som.op, (ast.Add, ast.Sub)
                ):
                    continue
                doel = ast.unparse(knoop.targets[0]).split("[")[0]
                if doel in ast.unparse(som):
                    fout.append(
                        f"{bestand.name}:{knoop.lineno}  {ast.unparse(knoop)[:80]}"
                    )
    assert not fout, "\n".join(fout)


def test_de_regel_vangt_de_fout_van_het_ventilatorverbruik():
    """De fout die deze regel uitlokte, moet hij ook echt vangen."""
    code = "x = round(x + stap, 4)"
    knoop = ast.parse(code).body[0]
    som = knoop.value.args[0]
    assert _is_round(knoop.value)
    assert ast.unparse(knoop.targets[0]) in ast.unparse(som)
