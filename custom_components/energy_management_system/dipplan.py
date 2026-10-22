"""Laden in een prijsdip in het kwartierplan, met de regel van de beslissing (v5.117.0, L-EMS-028).

Leerronde 22-10 (H-EMS-13): het plan zette lading in een dip die de sturing
nooit deed. De beslissing (`_dipbesluit`) rekent met het spaarplan: de
behoefte tot het blok geschaald naar de verkooptoets, ook de kwartieren ná
het blok die het blok niet zinvol bijvult, en het laadmoment via
`_goedkoopste_laadmomenten` (alle prijzen tot het doelkwartier, bij het
ingestelde laadvermogen per heel kwartier). Het plan gebruikte per kwartier
het eigen profiel tot het blok, telde alleen die kwartieren als goedkoper en
rekende een lopend kwartier als deelkwartier.

Hier dezelfde stappen, met de gesimuleerde stand van het plan in plaats van
de gemeten stand. De kwartieren (`dip`) zijn die van de beslissing:
(begin, prijs, tekort met DIP_MARGE tot het blok).
"""
from __future__ import annotations

import math
from datetime import datetime


def plan_dip_laadt(
    netregels: dict,
    dip: list,
    start: datetime,
    prijs: float,
    soc: float,
    bruikbaar: float,
    laad_kwh: float,
) -> float:
    """Hoeveel het plan in dit kwartier in een dip laadt (kWh)."""
    slijtage = netregels.get("slijtage_ct")
    if slijtage is None:
        return 0.0
    toekomst = [(b, p, d) for b, p, d in dip if b >= start]
    nodig = sum(d for _b, _p, d in toekomst)
    # Zoals `spaarplan`: haalt de accu het, dan is er niets te doen.
    if not toekomst or soc >= nodig:
        return 0.0
    # De duurste kwartieren krijgen de lading; het duurste dat overblijft
    # bepaalt wat de volgende kWh waard is.
    rest = soc
    doel = None
    for b, p, d in sorted(toekomst, key=lambda k: k[1], reverse=True):
        if d <= 0:
            continue
        if rest > 0:
            rest -= d
            continue
        doel = (b, p)
        break
    if doel is None:
        return 0.0
    waarde = doel[1] * netregels["rendement"] / 100 - slijtage / 100
    if waarde <= prijs:
        return 0.0
    gat = min(bruikbaar - soc, nodig - soc)
    if gat <= 0:
        return 0.0
    # Zoals `_goedkoopste_laadmomenten`: alle prijzen tussen nu en het doel,
    # en een heel kwartier op het ingestelde laadvermogen.
    per_kwartier = netregels.get("laad_per_kwartier") or 0.0
    if per_kwartier <= 0:
        return 0.0
    benodigd = max(1, math.ceil(gat / per_kwartier))
    goedkoper = [
        p for b, p in netregels.get("reeks", []) if start < b < doel[0] and p < prijs
    ]
    if len(goedkoper) >= benodigd:
        return 0.0
    return max(0.0, min(laad_kwh, gat))
