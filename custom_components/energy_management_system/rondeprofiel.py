"""Eén ronde onder de profiler (v5.224.0).

De klokken per stap zeggen welke stap zwaar is, niet waarom. Na v5.223.0
stonden `besluit_snapshot` (255 ms) en `planningsmeldingen` (147 ms)
bovenaan, terwijl dezelfde code met een plan uit de rondecache 1 ms kost.
Waar die tijd op de echte installatie heen gaat, valt niet uit de code te
lezen; deze module meet het: welke functies van de integratie de meeste
tijd kosten in één ronde.

Alleen lezen. Een ronde onder de profiler duurt ongeveer twee keer zo lang
en telt daarom niet mee in de rondeduur.
"""
from __future__ import annotations

import cProfile
import os
import pstats

MAP = os.path.dirname(os.path.abspath(__file__))
# De ronde na de start die vanzelf gemeten wordt: voorbij het inlezen.
RONDE_NA_START = 8
TOP_TOTAAL = 30
TOP_EIGEN = 12


def start():
    """Een lopende profiler, of None als er al een actief is."""
    try:
        profiel = cProfile.Profile()
        profiel.enable()
        return profiel
    except Exception:  # noqa: BLE001 - meten mag de ronde nooit breken
        return None


def _naam(bestand: str, regel: int, functie: str) -> str:
    if bestand.startswith(MAP):
        return f"{os.path.basename(bestand)[:-3]}.{functie}:{regel}"
    if bestand == "~":
        return functie
    return f"{os.path.basename(bestand)}:{functie}"


def samenvatting(profiel, moment: str | None = None) -> dict:
    """De zwaarste functies van de gemeten ronde."""
    try:
        profiel.disable()
        stats = pstats.Stats(profiel).stats
    except Exception as fout:  # noqa: BLE001
        return {"beschikbaar": False, "reden": f"{type(fout).__name__}: {fout}"}
    eigen, totaal = [], []
    som = 0.0
    for (bestand, regel, functie), (_cc, aanroepen, eigen_s, totaal_s, _callers) in stats.items():
        som += eigen_s
        rij = {
            "functie": _naam(bestand, regel, functie),
            "aanroepen": aanroepen,
            "eigen_ms": round(eigen_s * 1000, 1),
            "totaal_ms": round(totaal_s * 1000, 1),
        }
        eigen.append(rij)
        if bestand.startswith(MAP):
            totaal.append(rij)
    totaal.sort(key=lambda r: -r["totaal_ms"])
    eigen.sort(key=lambda r: -r["eigen_ms"])
    return {
        "beschikbaar": True,
        "moment": moment,
        "gemeten_ms": round(som * 1000, 1),
        # Inclusief wat de functie aanroept; alleen de integratie zelf.
        "zwaarste_totaal": totaal[:TOP_TOTAAL],
        # Alleen de functie zelf; ook Python en Home Assistant.
        "zwaarste_eigen": eigen[:TOP_EIGEN],
        "toelichting": (
            "Eén ronde onder de profiler. 'totaal' telt mee wat een functie "
            "aanroept, 'eigen' niet. De profiler maakt de ronde ongeveer "
            "twee keer zo traag; de verhoudingen kloppen, de milliseconden "
            "zijn te hoog."
        ),
    }
