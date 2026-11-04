"""Het geleerde verbruiksprofiel van een witgoedcyclus (v5.184.4).

Ruud 04-11 19:22: "Je weet inmiddels aardig wat van het verbruik van mijn
apparaten, je kunt het dus zeer specifiek verdelen?" Aanleiding: een geplande
vaatwasser telde met zijn hele cyclus in het eerste kwartier (05-11 05:00 huis
5.112 W in het plan).

Gemeten (5-minutengemiddelden uit de recorder, 27/28-10):
* vaatwasser: ~1,2 kWh in ~50 min, per kwartier ~34 / 26 / 30 / 10 %;
* wasmachine: ~1,0-1,7 kWh in 2,5-3 uur, het meeste in het eerste uur
  (opwarmen), daarna een lange staart van centrifugeren en pompen.

Een profiel is de fractie van de cyclusenergie per kwartier vanaf de start.
Het komt uit de 5-minutengemiddelden van de vermogenssensor van het apparaat:
cycli herkennen, per kwartier de energie, normeren, gemiddeld over de cycli.
Zuiver Python, zonder Home Assistant.
"""
from __future__ import annotations

from datetime import datetime, timedelta

#: boven dit gemiddelde (W, per 5 minuten) draait het apparaat
AAN_W = 20.0
#: zoveel 5-minutenvakken onder AAN_W = de cyclus is klaar
STIL_VAKKEN = 6
#: een cyclus telt pas vanaf deze energie (kWh); kleiner is een spoelbeurt of fragment
MIN_KWH = 0.3
#: hooguit zoveel kwartieren per profiel (4 uur)
MAX_KWARTIEREN = 16
#: zoveel cycli zijn genoeg voor een profiel (de rest is terugval)
MIN_CYCLI = 1


def cycli(vijfminuten: list[float]) -> list[list[float]]:
    """De cycli in een reeks 5-minutengemiddelden (W), oudste eerst."""
    uit: list[list[float]] = []
    huidig: list[float] | None = None
    stil = 0
    for w in vijfminuten:
        w = float(w or 0.0)
        if w > AAN_W:
            if huidig is None:
                huidig = []
            huidig.append(w)
            stil = 0
        elif huidig is not None:
            huidig.append(w)
            stil += 1
            if stil >= STIL_VAKKEN:
                uit.append(huidig[:-stil])
                huidig, stil = None, 0
    # een cyclus die nog loopt, telt niet
    return uit


def per_kwartier(cyclus: list[float]) -> list[float]:
    """Energie (kWh) per kwartier van een cyclus uit 5-minutengemiddelden."""
    return [sum(cyclus[i:i + 3]) / 12 / 1000 for i in range(0, len(cyclus), 3)]


def profiel(vijfminuten: list[float]) -> list[float] | None:
    """Fractie per kwartier vanaf de start, gemiddeld over de herkende cycli."""
    reeksen = []
    for c in cycli(vijfminuten):
        q = per_kwartier(c)
        totaal = sum(q)
        if totaal < MIN_KWH:
            continue
        reeksen.append([x / totaal for x in q[:MAX_KWARTIEREN]])
    if len(reeksen) < MIN_CYCLI:
        return None
    lengte = max(len(r) for r in reeksen)
    gem = [sum(r[i] if i < len(r) else 0.0 for r in reeksen) / len(reeksen) for i in range(lengte)]
    som = sum(gem)
    if som <= 0:
        return None
    # staartjes onder 1 % weg aan het eind, dan opnieuw normeren
    while len(gem) > 1 and gem[-1] < 0.01:
        gem.pop()
    som = sum(gem)
    return [round(x / som, 4) for x in gem]


def kwh_in_periode(kwh: float, start: datetime, fracties: list[float],
                   van: datetime, tot: datetime) -> float:
    """Het deel van `kwh` (cyclus vanaf `start` met profiel `fracties`) dat in
    [van, tot) valt; binnen een kwartier gelijk verdeeld."""
    totaal = 0.0
    for i, f in enumerate(fracties):
        a = start + timedelta(minutes=15 * i)
        b = a + timedelta(minutes=15)
        overlap = (min(b, tot) - max(a, van)).total_seconds()
        if overlap > 0:
            totaal += kwh * f * overlap / 900.0
    return totaal


def rest_fracties(fracties: list[float], verstreken_min: float) -> list[float]:
    """Het profiel vanaf `verstreken_min` na de start, opnieuw genormeerd, als
    fracties per kwartier vanaf NU (voor een lopende cyclus)."""
    if not fracties:
        return []
    rest = []
    t = max(0.0, verstreken_min)
    eind = 15.0 * len(fracties)
    while t < eind - 1e-9:
        stuk_eind = min(eind, t + 15.0)
        f = 0.0
        x = t
        while x < stuk_eind - 1e-9:
            j = int(x // 15)
            grens = min(stuk_eind, 15.0 * (j + 1))
            f += fracties[j] * (grens - x) / 15.0
            x = grens
        rest.append(f)
        t = stuk_eind
    som = sum(rest)
    return [x / som for x in rest] if som > 0 else []
