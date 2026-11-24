"""Vermoedelijke ontdooibeurten van de airco herkennen en tellen (v5.256.0).

Ruud 24-11: "Kun je ook zien wanneer de buitenunit 'bevroren' is?" De Daikin
geeft geen ontdooisignaal door. Wat hij wel meldt (om de twee minuten, hele
graden): de compressorfrequentie en de temperatuur bij de binnenunit. Tijdens
het ontdooien draait de compressor door terwijl de binnenunit geen warmte
geeft; de temperatuur bij de binnenunit zakt dan snel. 24-11 11:05-11:13 bij
0 °C buiten: 22 -> 19 °C in acht minuten, frequentie 40 -> 18 Hz.

Alleen een METING: het EMS stuurt er niet op. Het patroon is op één
waarneming gebaseerd en moet nog geijkt worden met een moment waarop Ruud de
buitenunit zelf ziet ontdooien; daarom heet het overal 'vermoedelijk'.

Een beurt telt als:
- de airco verwarmt en het buiten hooguit `BUITEN_MAX_C` is;
- de compressor de tien minuten ervoor al draaide (geen koude start: dan
  zakt de meting ook, omdat de ventilator kamerlucht gaat aanzuigen);
- het doel in die tijd niet is veranderd (geen bediening);
- de temperatuur bij de binnenunit binnen `VENSTER_MIN` minuten minstens
  `DALING_C` zakt.

Alleen pure functies; de beurten staan in het dagritme (`ritme["ontdooi"]`),
de laatste metingen in een buffer die de coordinator vasthoudt.
"""
from __future__ import annotations

from datetime import datetime, timedelta

BUITEN_MAX_C = 7.0
DALING_C = 2.0
VENSTER_MIN = 10
VOORAF_MIN = 10
#: Zoveel metingen vooraf nodig (één per ronde van een minuut; ruim genomen).
VOORAF_METINGEN = 3
BUFFER_MIN = 25
#: Een nieuwe beurt pas zoveel minuten na het begin van de vorige.
TUSSENTIJD_MIN = 20
#: Een beurt die na zoveel minuten niet hersteld is, sluiten we af.
DUUR_MAX_MIN = 30
BEURTEN_MAX = 120


def leeg() -> dict:
    return {"beurten": []}


def geldig(waarde) -> dict:
    basis = leeg()
    if not isinstance(waarde, dict):
        return basis
    beurten = waarde.get("beurten")
    if isinstance(beurten, list):
        basis["beurten"] = [
            dict(b) for b in beurten
            if isinstance(b, dict) and isinstance(b.get("begin"), str)
        ][-BEURTEN_MAX:]
    return basis


def _tijd(tekst) -> datetime | None:
    try:
        return datetime.fromisoformat(tekst)
    except (TypeError, ValueError):
        return None


def ronde(
    model: dict, buffer: list, now: datetime, *, hz, unit_c, buiten_c, doel_c, verwarmt: bool,
) -> dict | None:
    """Eén meetronde. Werkt `buffer` (lijst van [tijd, hz, unit_c, doel_c]) en
    `model` bij; geeft de nieuwe beurt terug als er net een is herkend."""
    beurten = model.setdefault("beurten", [])
    # een lopende beurt afsluiten zodra de binnenunit weer warm is
    if beurten and beurten[-1].get("duur_min") is None:
        lopend = beurten[-1]
        begin = _tijd(lopend.get("begin"))
        minuten = (now - begin).total_seconds() / 60 if begin else DUUR_MAX_MIN
        voor = lopend.get("unit_voor_c")
        hersteld = (
            unit_c is not None and isinstance(voor, (int, float)) and unit_c >= voor - 0.5
        )
        if hersteld or minuten >= DUUR_MAX_MIN or not verwarmt:
            lopend["duur_min"] = round(min(minuten, DUUR_MAX_MIN), 0)
            lopend["hersteld"] = bool(hersteld)
    if hz is None or unit_c is None or not verwarmt:
        buffer.clear()
        return None
    buffer.append([now, float(hz), float(unit_c), doel_c])
    grens = now - timedelta(minutes=BUFFER_MIN)
    while buffer and buffer[0][0] < grens:
        buffer.pop(0)
    if buiten_c is None or buiten_c > BUITEN_MAX_C:
        return None
    if beurten:
        vorige = _tijd(beurten[-1].get("begin"))
        if vorige is not None and (now - vorige).total_seconds() < TUSSENTIJD_MIN * 60:
            return None
    venster_begin = now - timedelta(minutes=VENSTER_MIN)
    vooraf = [m for m in buffer if m[0] < venster_begin]
    venster = [m for m in buffer if m[0] >= venster_begin]
    if len(vooraf) < VOORAF_METINGEN or not venster:
        return None
    if (venster_begin - vooraf[0][0]).total_seconds() < (VOORAF_MIN - 2) * 60:
        return None
    if any(m[1] <= 0 for m in vooraf):
        return None
    if len({m[3] for m in buffer}) > 1:
        return None
    voor_c = vooraf[-1][2]
    if voor_c - unit_c < DALING_C:
        return None
    begin = next((m[0] for m in venster if m[2] < voor_c), now)
    beurt = {
        "begin": begin.isoformat(),
        "buiten_c": round(float(buiten_c), 1),
        "unit_voor_c": voor_c,
        "unit_laagst_c": float(unit_c),
        "hz_voor": vooraf[-1][1],
        "hz_laagst": min(m[1] for m in venster),
        "hz_hoogst": max(m[1] for m in venster),
        "duur_min": None,
    }
    beurten.append(beurt)
    del beurten[:-BEURTEN_MAX]
    return beurt


def overzicht(model: dict | None, now: datetime) -> dict:
    """Voor de sensor en de diagnose."""
    beurten = list((model or {}).get("beurten") or [])
    vandaag = now.date().isoformat()
    week = (now - timedelta(days=7)).isoformat()
    duren = [b["duur_min"] for b in beurten if isinstance(b.get("duur_min"), (int, float)) and b.get("hersteld")]
    return {
        "zeker": False,
        "toelichting": (
            "Vermoedelijke ontdooibeurten, afgeleid uit de compressorfrequentie en de "
            "temperatuur bij de binnenunit. Nog niet geijkt; het EMS stuurt er niet op."
        ),
        "vandaag": sum(1 for b in beurten if str(b.get("begin", ""))[:10] == vandaag),
        "laatste_7_dagen": sum(1 for b in beurten if str(b.get("begin", "")) >= week),
        "gemiddelde_duur_min": round(sum(duren) / len(duren), 1) if duren else None,
        "laatste": beurten[-1] if beurten else None,
        "beurten": beurten[-20:],
    }
