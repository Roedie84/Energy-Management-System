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
  anders: vol, leeg, begrensd, of een andere stand dan bedoeld.

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


def beoordeel(gepland: dict, accu_w: float | None, zon_w: float | None, huis_w: float | None) -> dict:
    """Gemeten tegen gepland, met de oorzaak van het verschil."""
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

    if abs(verschil) < DREMPEL_W:
        oorzaak, status = "geen", "volgens plan"
    else:
        oorzaak = max(bijdragen, key=lambda k: abs(bijdragen[k]))
        status = "afwijking accu" if abs(rest) >= DREMPEL_W else "verklaard"
    return {
        "beschikbaar": True,
        "gepland_accu_w": gepland["accu_w"],
        "gemeten_accu_w": round(accu_w),
        "verschil_w": round(verschil),
        "zon_verschil_w": None if zon_d is None else round(zon_d),
        "verbruik_verschil_w": None if huis_d is None else round(huis_d),
        "onverklaard_w": round(rest),
        "oorzaak": oorzaak,
        "status": status,
        "modus": gepland.get("modus"),
        "tekst": tekst(gepland["accu_w"], accu_w, oorzaak, zon_d, huis_d, rest),
    }


def _kw(w: float) -> str:
    return f"{abs(w) / 1000:.1f}".replace(".", ",") + " kW"


def _richting(w: float) -> str:
    if w <= -50:
        return f"laadt {_kw(w)}"
    if w >= 50:
        return f"ontlaadt {_kw(w)}"
    return "in rust"


def tekst(gepland_w: float, gemeten_w: float, oorzaak: str, zon_d, huis_d, rest) -> str:
    """Een zin voor het dashboard: wat er gebeurt, wat er gepland was, waarom."""
    plan = _richting(gepland_w).replace("laadt", "laden").replace("ontlaadt", "ontladen")
    kop = f"Accu {_richting(gemeten_w)}, gepland {plan}"
    if oorzaak == "geen":
        return f"Accu {_richting(gemeten_w)}, volgens plan"
    if oorzaak == "zon":
        reden = f"{'meer' if zon_d > 0 else 'minder'} zon dan voorspeld ({'+' if zon_d > 0 else '-'}{_kw(zon_d)})"
    elif oorzaak == "verbruik":
        reden = f"huis verbruikt {'meer' if huis_d > 0 else 'minder'} dan verwacht ({'+' if huis_d > 0 else '-'}{_kw(huis_d)})"
    else:
        reden = f"de accu wijkt zelf {_kw(rest)} af"
    return f"{kop} – {reden}"


def sluit_kwartier(gepland: dict, monsters: list[dict]) -> dict | None:
    """Het oordeel over een afgelopen kwartier, uit de gemiddelde metingen."""
    if not gepland or not monsters:
        return None

    def gem(sleutel):
        reeks = [m[sleutel] for m in monsters if m.get(sleutel) is not None]
        return sum(reeks) / len(reeks) if reeks else None

    oordeel = beoordeel(gepland, gem("accu_w"), gem("zon_w"), gem("huis_w"))
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
