"""Deed de accu zelf wat het EMS opdroeg? (v5.244.0, alleen meten)

Ruud 19-11: "Zendure lokaal aansturen", stap a. De opdrachtcontrole
(v3.87.0) kijkt na of de ENTITEIT van de Zendure-integratie de opgedragen
waarde draagt. Dat zegt niet of de accu het ook deed: de integratie kan de
waarde tonen terwijl de opdracht de accu niet of te laat bereikt (in het
logboek van 16-19 november: acht time-outs en drie verbroken verbindingen).

Hier wordt een opgedragen handmatig vermogen na de wachttijd vergeleken
met wat het EMS de accu zelf ziet doen (de eigen lezing van
zendure_lokaal, elke 2 s). Vier uitkomsten:

    gevolgd        het gemeten vermogen ligt binnen de marge
    niet_gevolgd   de accu doet iets anders
    kan_niet       de accu is vol (laden) of leeg (ontladen): geen oordeel
    onbekend       geen verse eigen lezing

Zuivere functies; schrijft nergens naar de accu.
"""
from __future__ import annotations

#: Binnen max(150 W, 15 %) telt als gevolgd: de accu regelt in stappen en de
#: lezing loopt tot 2 s achter.
MARGE_W = 150.0
MARGE_FRACTIE = 0.15
#: Een eigen lezing ouder dan dit zegt niets over nu.
MAX_LEEFTIJD_S = 15.0
#: Onder dit opgedragen vermogen valt er niets te beoordelen.
MIN_OPDRACHT_W = 100.0
#: Zoveel procent van de grens af telt de accu als vol of leeg.
GRENSMARGE_PROCENT = 1.0
LAATSTE_AFWIJKINGEN = 10
DAGEN = 30

UITKOMSTEN = ("gevolgd", "niet_gevolgd", "kan_niet", "onbekend")


def beoordeel(verwacht_w, gemeten_w, leeftijd_s=None, soc=None, ondergrens=None, bovengrens=None) -> str:
    """Positief = ontladen, negatief = laden (zoals het handmatige vermogen)."""
    try:
        verwacht = float(verwacht_w)
    except (TypeError, ValueError):
        return "onbekend"
    if abs(verwacht) < MIN_OPDRACHT_W:
        return "onbekend"
    if gemeten_w is None or leeftijd_s is None or leeftijd_s > MAX_LEEFTIJD_S:
        return "onbekend"
    gemeten = float(gemeten_w)
    if abs(gemeten - verwacht) <= max(MARGE_W, abs(verwacht) * MARGE_FRACTIE):
        return "gevolgd"
    if soc is not None:
        if verwacht < 0 and bovengrens is not None and float(soc) >= float(bovengrens) - GRENSMARGE_PROCENT:
            return "kan_niet"
        if verwacht > 0 and ondergrens is not None and float(soc) <= float(ondergrens) + GRENSMARGE_PROCENT:
            return "kan_niet"
    return "niet_gevolgd"


def leeg() -> dict:
    return {"totaal": {u: 0 for u in UITKOMSTEN}, "dagen": {}, "afwijkingen": []}


def noteer(tellingen: dict, uitkomst: str, *, dag: str, moment: str, verwacht_w=None, gemeten_w=None,
           soc=None) -> dict:
    if uitkomst not in UITKOMSTEN:
        return tellingen
    totaal = tellingen.setdefault("totaal", {})
    totaal[uitkomst] = int(totaal.get(uitkomst) or 0) + 1
    dagen = tellingen.setdefault("dagen", {})
    d = dagen.setdefault(dag, {})
    d[uitkomst] = int(d.get(uitkomst) or 0) + 1
    for oud in sorted(dagen)[:-DAGEN]:
        del dagen[oud]
    if uitkomst == "niet_gevolgd":
        lijst = tellingen.setdefault("afwijkingen", [])
        lijst.append({
            "moment": moment,
            "verwacht_w": round(float(verwacht_w)) if verwacht_w is not None else None,
            "gemeten_w": round(float(gemeten_w)) if gemeten_w is not None else None,
            "soc": soc,
        })
        del lijst[:-LAATSTE_AFWIJKINGEN]
    return tellingen


def overzicht(tellingen: dict | None) -> dict:
    t = tellingen or {}
    totaal = {u: int((t.get("totaal") or {}).get(u) or 0) for u in UITKOMSTEN}
    beoordeeld = totaal["gevolgd"] + totaal["niet_gevolgd"]
    return {
        **totaal,
        "beoordeeld": beoordeeld,
        "aandeel_gevolgd_procent": round(100 * totaal["gevolgd"] / beoordeeld, 1) if beoordeeld else None,
        "per_dag": dict(sorted((t.get("dagen") or {}).items())[-7:]),
        "laatste_afwijkingen": list(t.get("afwijkingen") or [])[-5:],
        "toelichting": (
            "Een opgedragen handmatig vermogen, na de wachttijd vergeleken met wat het EMS de accu zelf "
            "ziet doen (eigen lezing). 'kan_niet' = accu vol of leeg; 'onbekend' = geen verse eigen lezing."
        ),
    }
