"""Planvolging: doet de accu wat de planning voor dit kwartier verwachtte? (v5.91)

Gevraagd (12-10): "Wordt er ook rekening gehouden met hoeveel W de accu nu al
laadt ten opzichte van de planning en of dit verwacht was?"

Het EMS plant elke minuut opnieuw vanaf de echte laadstand, dus een afwijking
werd stilzwijgend opgevangen - zonder dat ergens stond DAT het afweek, en
waardoor. Deze module legt per kwartier het geplande accuvermogen naast het
gemeten vermogen en wijst een oorzaak aan:

- **zon**: er schijnt meer of minder zon dan voorspeld. In de slimme standen
  volgt de accu het overschot, dus extra zon gaat de accu in. Dat is een
  verklaarde afwijking.
- **verbruik**: het huis gebruikt meer of minder dan verwacht - idem.
- **accu**: wat overblijft na zon en verbruik. Dan doet de accu zelf iets
  anders: vol, leeg of begrensd.
- **sturing** (v5.93.2): de stand die het EMS koos is een andere soort dan
  het plan (handmatig laden/verkopen tegenover slim). Dan volgt de accu
  gewoon de sturing; het verschil komt van een ander besluit, niet van de
  accu. Gemeld 12-10 13:16: "de accu wijkt zelf 0,6 kW af" terwijl de
  sturing sparen koos en het plan laden van het net.

In de handmatige standen (laden, verkopen) ligt het vermogen vast; daar gaan
zon en verbruik naar het net en is elke afwijking van de accu zelf.

Tekenafspraak zoals in de rest van het EMS: positief is ontladen, negatief is
laden. Alleen meten en tonen - dit stuurt niets.

Zuivere functies, zonder Home Assistant.
"""
from __future__ import annotations

import statistics

DREMPEL_W = 150.0
DAGEN_BEWAREN = 30
KWARTIEREN_BEWAREN = 96


def _handmatig(modus: str | None) -> bool:
    return str(modus or "").startswith("manual")


def gepland_uit_plan(rij: dict, start_kwh: float) -> dict:
    """Het plan voor dit kwartier, in watt.

    `rij` is de planregel van het lopende kwartier; `start_kwh` de stand bij
    het begin ervan. De stand na het kwartier min die aan het begin is wat
    het plan de accu in (of uit) laat gaan.
    """
    delta = (rij.get("soc_kwh") or 0.0) - start_kwh
    return {
        "kwartier": rij.get("start"),
        "van": rij.get("van"),
        "modus": rij.get("modus"),
        "accu_w": round(-delta * 4000),
        "zon_w": round((rij.get("zon_kwh") or 0.0) * 4000),
        "huis_w": round((rij.get("verbruik_kwh") or 0.0) * 4000),
    }


def beoordeel(
    gepland: dict, accu_w: float | None, zon_w: float | None, huis_w: float | None,
    stand: str | None = None,
) -> dict:
    """Gemeten tegen gepland, met de oorzaak van het verschil.

    `stand` is de werkelijke stand van de accu (de operation-select); is die
    een andere soort dan het plan, dan is de oorzaak de sturing (v5.93.2).
    """
    if not gepland or accu_w is None:
        return {"beschikbaar": False}
    verschil = accu_w - gepland["accu_w"]
    zon_d = None if zon_w is None else zon_w - gepland["zon_w"]
    huis_d = None if huis_w is None else huis_w - gepland["huis_w"]
    if _handmatig(gepland.get("modus")):
        verklaard = 0.0
        bijdragen = {}
    else:
        # meer zon -> meer laden (negatiever); meer verbruik -> meer ontladen
        bijdragen = {
            "zon": -(zon_d or 0.0),
            "verbruik": huis_d or 0.0,
        }
        verklaard = sum(bijdragen.values())
    rest = verschil - verklaard
    bijdragen["accu"] = rest

    andere_stand = (
        stand is not None and gepland.get("modus") is not None
        and _handmatig(stand) != _handmatig(gepland.get("modus"))
    )
    if abs(verschil) < DREMPEL_W:
        oorzaak, status = "geen", "volgens plan"
    elif andere_stand:
        oorzaak, status = "sturing", "afwijking sturing"
    else:
        oorzaak = max(bijdragen, key=lambda k: abs(bijdragen[k]))
        status = "afwijking accu" if abs(rest) >= DREMPEL_W else "verklaard"
    return {
        "beschikbaar": True,
        "gepland_accu_w": gepland["accu_w"],
        "gemeten_accu_w": round(accu_w),
        "verschil_w": round(verschil),
        "verschil_tekst": verschil_tekst(gepland["accu_w"], accu_w),
        "zon_verschil_w": None if zon_d is None else round(zon_d),
        "verbruik_verschil_w": None if huis_d is None else round(huis_d),
        "onverklaard_w": round(rest),
        "oorzaak": oorzaak,
        "status": status,
        "modus": gepland.get("modus"),
        "stand": stand,
        "tekst": tekst(gepland["accu_w"], accu_w, oorzaak, zon_d, huis_d, rest,
                       stand=stand, plan_modus=gepland.get("modus")),
    }


def _kw(w: float) -> str:
    return f"{abs(w) / 1000:.1f}".replace(".", ",") + " kW"


def _richting(w: float) -> str:
    if w <= -50:
        return f"laadt {_kw(w)}"
    if w >= 50:
        return f"ontlaadt {_kw(w)}"
    return "in rust"


def verschil_tekst(gepland_w: float, gemeten_w: float) -> str:
    """Het verschil in woorden (v5.93.2): "minder laden" in plaats van
    "meer ontladen" als de accu wel laadt, maar minder dan gepland."""
    verschil = gemeten_w - gepland_w
    if abs(verschil) < 50:
        return "geen"
    if gepland_w <= -50 and gemeten_w <= -50:
        return "minder laden" if verschil > 0 else "meer laden"
    if gepland_w >= 50 and gemeten_w >= 50:
        return "meer ontladen" if verschil > 0 else "minder ontladen"
    return "meer ontladen" if verschil > 0 else "meer laden"


def tekst(gepland_w: float, gemeten_w: float, oorzaak: str, zon_d, huis_d, rest,
          stand: str | None = None, plan_modus: str | None = None) -> str:
    """Een zin voor het dashboard: wat er gebeurt, wat er gepland was, waarom."""
    plan = _richting(gepland_w).replace("laadt", "laden").replace("ontlaadt", "ontladen")
    kop = f"Accu {_richting(gemeten_w)}, gepland {plan}"
    if oorzaak == "geen":
        return f"Accu {_richting(gemeten_w)}, volgens plan"
    if oorzaak == "zon":
        reden = f"{'meer' if zon_d > 0 else 'minder'} zon dan voorspeld ({'+' if zon_d > 0 else '-'}{_kw(zon_d)})"
    elif oorzaak == "verbruik":
        reden = f"huis verbruikt {'meer' if huis_d > 0 else 'minder'} dan verwacht ({'+' if huis_d > 0 else '-'}{_kw(huis_d)})"
    elif oorzaak == "sturing":
        reden = f"de sturing koos {_stand_tekst(stand)} in plaats van {_stand_tekst(plan_modus)}"
    else:
        reden = f"de accu wijkt zelf {_kw(rest)} af"
    return f"{kop} – {reden}"


def _stand_tekst(stand: str | None) -> str:
    t = str(stand or "")
    if t.startswith("manual (laden)"):
        return "laden van het net"
    if t.startswith("manual (verkopen)"):
        return "verkopen"
    if t.startswith("manual"):
        return "handmatig"
    if "smart_charging" in t:
        return "sparen (alleen zon laden)"
    if "smart_discharging" in t:
        return "ontladen naar het huis"
    if t.startswith("smart"):
        return "slim"
    return t or "onbekend"


def sluit_kwartier(gepland: dict, monsters: list[dict]) -> dict | None:
    """Het oordeel over een afgelopen kwartier, uit de gemiddelde metingen."""
    if not gepland or not monsters:
        return None

    def gem(sleutel):
        reeks = [m[sleutel] for m in monsters if m.get(sleutel) is not None]
        return sum(reeks) / len(reeks) if reeks else None

    standen = [m.get("stand") for m in monsters if m.get("stand")]
    stand = max(set(standen), key=standen.count) if standen else None
    oordeel = beoordeel(gepland, gem("accu_w"), gem("zon_w"), gem("huis_w"), stand=stand)
    if not oordeel.get("beschikbaar"):
        return None
    return {
        "kwartier": gepland.get("kwartier"),
        "van": gepland.get("van"),
        "monsters": len(monsters),
        **{k: oordeel[k] for k in ("gepland_accu_w", "gemeten_accu_w", "verschil_w", "onverklaard_w", "oorzaak", "status")},
    }


def dagsamenvatting(dag: str, kwartieren: list[dict]) -> dict | None:
    """Per dag: hoe vaak volgde de accu het plan, en waardoor niet."""
    if not kwartieren:
        return None
    oorzaken: dict[str, int] = {}
    for k in kwartieren:
        oorzaken[k["oorzaak"]] = oorzaken.get(k["oorzaak"], 0) + 1
    volgens = oorzaken.get("geen", 0)
    afwijking_accu = sum(1 for k in kwartieren if k["status"] == "afwijking accu")
    return {
        "dag": dag,
        "kwartieren": len(kwartieren),
        "volgens_plan_procent": round(100 * volgens / len(kwartieren), 1),
        "afwijking_accu": afwijking_accu,
        "mediaan_verschil_w": round(statistics.median(abs(k["verschil_w"]) for k in kwartieren)),
        "energie_verschil_kwh": round(sum(k["verschil_w"] for k in kwartieren) / 4000, 2),
        "oorzaken": oorzaken,
    }
