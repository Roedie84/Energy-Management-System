"""De coordinator als één bron voor de structuur- en teksttoetsen (B4).

Sinds B4 staat een deel van `EnergyManagementSystemCoordinator` in
mixin-modules (`class XxxMixin:` in een eigen bestand, door de coordinator
geërfd) en een deel van de hulpfuncties op moduleniveau in
`coordinator_hulp.py`. Voor de werking verandert dat niets; voor toetsen die
de TEKST of de BOOM van `coordinator.py` lezen wel: die zouden de verhuisde
methodes niet meer zien, en een verbod ("de coordinator roept nooit X aan")
zou stilletjes alleen nog voor het overgebleven deel gelden.

`coordinator_bron()` geeft daarom de coordinator zoals hij vóór de splitsing
was: `coordinator.py` met de lichamen van de mixin-klassen in de klasse
gevoegd, en de rest van de deel-modules (imports, hulpfuncties) erachter.
Dezelfde bedoeling als voorheen, over de hele coordinator.
"""
from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

import custom_components.energy_management_system as pkg

MAP = Path(pkg.__file__).parent
KLASSE = "EnergyManagementSystemCoordinator"
HULP = "coordinator_hulp.py"


def _coordinator_boom() -> ast.Module:
    return ast.parse((MAP / "coordinator.py").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def deel_bestanden() -> tuple[str, ...]:
    """De bestandsnamen die bij de coordinator horen (mixins en hulp)."""
    boom = _coordinator_boom()
    klasse = next(
        n for n in boom.body if isinstance(n, ast.ClassDef) and n.name == KLASSE
    )
    basissen = {b.id for b in klasse.bases if isinstance(b, ast.Name)}
    namen = []
    for knoop in boom.body:
        if isinstance(knoop, ast.ImportFrom) and knoop.level == 1 and knoop.module:
            if any((a.asname or a.name) in basissen for a in knoop.names):
                namen.append(knoop.module + ".py")
    if (MAP / HULP).exists():
        namen.append(HULP)
    return tuple(namen)


def _zonder_kop(tekst: str) -> str:
    """Moduledocstring en `from __future__` eraf, zodat het geheel compileert."""
    boom = ast.parse(tekst)
    regels = tekst.splitlines(keepends=True)
    weg = set()
    for knoop in boom.body:
        is_doc = isinstance(knoop, ast.Expr) and isinstance(
            getattr(knoop, "value", None), ast.Constant
        ) and isinstance(knoop.value.value, str) and knoop is boom.body[0]
        is_future = isinstance(knoop, ast.ImportFrom) and knoop.module == "__future__"
        if is_doc or is_future:
            weg.update(range(knoop.lineno, knoop.end_lineno + 1))
    return "".join(r for i, r in enumerate(regels, 1) if i not in weg)


@lru_cache(maxsize=1)
def coordinator_bron() -> str:
    """`coordinator.py` met de mixin-lichamen erin gevoegd (zie boven)."""
    tekst = (MAP / "coordinator.py").read_text(encoding="utf-8")
    regels = tekst.splitlines(keepends=True)
    klasse = next(
        n for n in ast.parse(tekst).body if isinstance(n, ast.ClassDef) and n.name == KLASSE
    )
    in_klasse: list[str] = []
    na_module: list[str] = []
    for naam in deel_bestanden():
        deel = (MAP / naam).read_text(encoding="utf-8")
        boom = ast.parse(deel)
        deel_regels = deel.splitlines(keepends=True)
        weg = set()
        for knoop in boom.body:
            if isinstance(knoop, ast.ClassDef) and knoop.name.endswith("Mixin"):
                lichaam = knoop.body
                # de docstring van de mixin zelf hoort niet in de klasse
                if (
                    isinstance(lichaam[0], ast.Expr)
                    and isinstance(getattr(lichaam[0], "value", None), ast.Constant)
                ):
                    begin = lichaam[0].end_lineno + 1
                else:
                    begin = lichaam[0].lineno
                in_klasse.append("\n")
                in_klasse.extend(deel_regels[begin - 1 : knoop.end_lineno])
                weg.update(range(knoop.lineno, knoop.end_lineno + 1))
        rest = "".join(r for i, r in enumerate(deel_regels, 1) if i not in weg)
        na_module.append("\n\n" + _zonder_kop(rest))
    eind = klasse.end_lineno
    samen = "".join(regels[:eind]) + "".join(in_klasse) + "".join(regels[eind:])
    return samen + "".join(na_module)


def lees(pad) -> str:
    """Lees een bestand; voor `coordinator.py` de samengevoegde bron."""
    pad = Path(pad)
    if pad.name == "coordinator.py":
        return coordinator_bron()
    return pad.read_text(encoding="utf-8")


def is_deel(pad) -> bool:
    """Hoort dit bestand bij de coordinator (dan zit het al in de samengevoegde bron)?"""
    return Path(pad).name in deel_bestanden()

