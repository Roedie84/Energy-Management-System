"""Schaduwberekeningen (v5.28): rekenen en rapporteren, nooit sturen.

Twee strikt gescheiden dingen, op verzoek van de review:

1. **Productiespiegel** (`spiegel`): bewijst dat de huidige productieregels
   correct worden nagerekend. Zelfde invoer, zelfde reserve, zelfde
   beschermingspoorten - de spiegel leest die uit wat productie al vastlegt.
   Hij rekent de twee afwegingen waarin de slijtage zit opnieuw uit: laden in
   het goedkope blok (`latere prijs x rendement - slijtage > prijs nu`) en de
   piekverkoop (`prijs nu > duurste kwartier tot het bijvullen`). Met de
   productieslijtage MOET hij hetzelfde besluit geven als productie
   (`mirror_matches_production`). Met andere slijtagewaarden laat hij zien
   wat de regelstrategie dan had gedaan.

   De overige takken (negatieve prijs, noodlading, overname, verkopen boven
   de reserve, zonvangst) worden doorgegeven: daar zit geen
   slijtageafweging in die de spiegel kan variëren.

2. **Economisch schaduwoptimum** (`optimaliseer`, `alternatieven`): mag en
   moet afwijken van productie. Dynamisch programmeren over de horizon van
   het snapshot met import- en exportwaarde, rendement, slijtagevariant,
   zon- en verbruiksverwachting en een eindwaarde voor wat er overblijft.
   Een verschil met productie is geen fout - het is een meetresultaat.

Geen Home Assistant, geen dienstaanroepen. Een broncodetoets bewaakt dat.
"""
from __future__ import annotations

import random
import statistics
from datetime import datetime, timedelta

SLIJTAGEVARIANTEN_CT = (0.0, 2.0, 4.22, 11.28)
ACTIES = ("huis_dekken", "bewaren", "verkopen", "laden")

# --- categorieën -----------------------------------------------------------

_OVERGENOMEN = ("manual", "calibrat", "learning", "user_override", "handmatig", "kalibr")
_LADEN = ("negative_price", "grid_charging", "emergency", "nu_laden", "dip_")
_BEWAREN = ("battery_saved", "smart_charging", "solar_capture", "solar_ramp", "zonvangst", "post_salderen")


def productie_categorie(reden: str | None, stand: str | None, vermogen_w: float | None) -> str:
    """Wat productie met de accu deed, in vier soorten (plus overgenomen)."""
    r = (reden or "").lower()
    if any(w in r for w in _OVERGENOMEN):
        return "overgenomen"
    if any(w in r for w in _LADEN) or (stand == "manual" and (vermogen_w or 0) < 0):
        return "laden"
    if stand == "manual" and (vermogen_w or 0) > 0:
        return "verkopen"
    if any(w in r for w in _BEWAREN) or stand == "smart_charging":
        return "bewaren"
    return "huis_dekken"


# --- productiespiegel ------------------------------------------------------

def vervangprijs(blokprijzen: list[float], rendement_procent: float | None, slijtage_ct: float) -> float | None:
    """Nagebouwd naar `_piek_vervangprijs`: goedkoopste blokprijs / rendement + slijtage."""
    if not blokprijzen or not rendement_procent:
        return None
    return min(blokprijzen) / (rendement_procent / 100) + slijtage_ct / 100


def duurste_later(moment: datetime, reeks: list, blok: datetime | None, vervang: float | None) -> float:
    """Nagebouwd naar `_duurste_later`."""
    if vervang is None:
        horizon = blok if blok is not None and blok > moment else moment + timedelta(hours=24)
    else:
        horizon = moment + timedelta(hours=24)
    later = []
    for begin, prijs in reeks:
        if not (moment + timedelta(minutes=15) <= begin < horizon):
            continue
        if vervang is not None and blok is not None and begin >= blok > moment:
            prijs = min(prijs, vervang)
        later.append(prijs)
    return max(later) if later else float("-inf")


def spiegel(invoer: dict, slijtage_ct: float) -> dict:
    """De productieregels nagerekend met een expliciete slijtage.

    `invoer`: productie_categorie, laadbesluit (productie), piek (productie),
    moment, reeks [(begin, prijs)], blok, blokprijzen, rendement_procent.
    """
    actie = invoer["productie_categorie"]
    uit = {"actie": actie, "laden": None, "piek": None, "doorgegeven": True}
    if actie == "overgenomen":
        return uit
    laad = invoer.get("laadbesluit") or {}
    if laad.get("latere_prijs_eur") is not None and laad.get("prijs_nu_eur") is not None and laad.get("rendement_procent"):
        laden = laad["latere_prijs_eur"] * laad["rendement_procent"] / 100 - slijtage_ct / 100 > laad["prijs_nu_eur"]
        uit["laden"] = laden
        uit["doorgegeven"] = False
        if laden and actie in ("huis_dekken", "bewaren"):
            actie = "laden"
        elif not laden and actie == "laden" and laad.get("laden"):
            actie = "huis_dekken"
    piek = invoer.get("piek") or {}
    if piek.get("prijs_nu_eur") is not None and invoer.get("reeks"):
        blok = invoer.get("blok")
        blok = blok if blok is not None and blok > invoer["moment"] else None
        vervang = vervangprijs(invoer.get("blokprijzen") or [], invoer.get("rendement_procent"), slijtage_ct) if blok else None
        grens = duurste_later(invoer["moment"], invoer["reeks"], blok, vervang)
        verkopen = grens != float("-inf") and piek["prijs_nu_eur"] > round(grens, 4)
        uit["piek"] = {"verkopen": verkopen, "duurste_later_eur": round(grens, 4) if grens != float("-inf") else None}
        uit["doorgegeven"] = False
        if piek.get("verkopen") and not verkopen and actie == "verkopen" and invoer.get("onder_reserve"):
            actie = "huis_dekken"
        elif verkopen and not piek.get("verkopen") and actie in ("huis_dekken", "bewaren") and invoer.get("duur_kwartier"):
            actie = "verkopen"
    uit["actie"] = actie
    return uit


# --- economisch schaduwoptimum ---------------------------------------------

def _stap_kosten(kw: dict, ac_in: float, ac_uit: float, slijtage_eur: float) -> float:
    net = kw["verbruik"] - kw["zon"] + ac_in - ac_uit
    waarde = kw["import"] if net > 0 else kw["export"]
    return net * waarde + ac_uit * slijtage_eur


def optimaliseer(
    kwartieren: list[dict],
    *,
    emax_kwh: float,
    laad_kwh: float,
    ontlaad_kwh: float,
    rendement_procent: float,
    slijtage_ct: float,
    stap: float = 0.1,
) -> dict:
    """Kosten-tot-het-einde per kwartier en energie-inhoud (dynamisch programmeren).

    `kwartieren`: per kwartier import, export (€/kWh), verbruik, zon (kWh).
    Eindwaarde: resterende energie gewaardeerd tegen de mediaan van de
    importwaarde x rendement - slijtage (niet negatief) - zo mag het optimum
    de accu niet leegtrekken om beter te lijken.
    """
    if not kwartieren or emax_kwh <= 0:
        return {"V": [], "stap": stap, "ns": 0}
    eta = (rendement_procent / 100) ** 0.5
    slijt = slijtage_ct / 100
    ns = int(round(emax_kwh / stap))
    k_min = -int(ontlaad_kwh / eta / stap)
    k_max = int(laad_kwh * eta / stap)
    importen = [k["import"] for k in kwartieren if k["import"] is not None]
    eindwaarde = max(0.0, statistics.median(importen) * (rendement_procent / 100) - slijt) if importen else 0.0
    V = [[0.0] * (ns + 1) for _ in range(len(kwartieren) + 1)]
    V[-1] = [-(s * stap) * eindwaarde for s in range(ns + 1)]
    for q in range(len(kwartieren) - 1, -1, -1):
        kw = kwartieren[q]
        rij, volgende = V[q], V[q + 1]
        for s in range(ns + 1):
            beste = float("inf")
            for k in range(max(k_min, -s), min(k_max, ns - s) + 1):
                d = k * stap
                kosten = _stap_kosten(kw, d / eta if d > 0 else 0.0, -d * eta if d < 0 else 0.0, slijt) + volgende[s + k]
                if kosten < beste:
                    beste = kosten
            rij[s] = beste
    return {"V": V, "stap": stap, "ns": ns, "eta": eta, "slijtage_eur": slijt,
            "laad_kwh": laad_kwh, "ontlaad_kwh": ontlaad_kwh, "eindwaarde_eur": eindwaarde}


def alternatieven(opt: dict, kwartieren: list[dict], q: int, energie_kwh: float) -> dict:
    """Verwachte netto waarde (€) van elke actie in kwartier q, uit de waardefunctie."""
    if not opt.get("V") or q < 0 or q >= len(kwartieren):
        return {}
    stap, ns, eta = opt["stap"], opt["ns"], opt["eta"]
    s = max(0, min(ns, int(round(energie_kwh / stap))))
    kw = kwartieren[q]
    tekort = max(0.0, kw["verbruik"] - kw["zon"])
    overschot = max(0.0, kw["zon"] - kw["verbruik"])
    opties = {
        "huis_dekken": (min(overschot, opt["laad_kwh"]), min(tekort, opt["ontlaad_kwh"])),
        "bewaren": (min(overschot, opt["laad_kwh"]), 0.0),
        "verkopen": (0.0, opt["ontlaad_kwh"]),
        "laden": (opt["laad_kwh"], 0.0),
    }
    uit = {}
    for actie, (ac_in, ac_uit) in opties.items():
        delta = ac_in * eta - ac_uit / eta
        t = max(0, min(ns, s + int(round(delta / stap))))
        werkelijk_uit = max(0.0, (s - t) * stap * eta) if t < s else 0.0
        werkelijk_in = max(0.0, (t - s) * stap / eta) if t > s else 0.0
        kosten = _stap_kosten(kw, werkelijk_in, werkelijk_uit, opt["slijtage_eur"]) + opt["V"][q + 1][t]
        uit[actie] = round(-kosten, 4)
    return uit


def beste_twee(waarden: dict) -> tuple:
    if not waarden:
        return None, None
    volgorde = sorted(waarden, key=lambda a: waarden[a], reverse=True)
    return volgorde[0], (volgorde[1] if len(volgorde) > 1 else None)


# --- kansgewogen reserve ---------------------------------------------------

def tekortverdeling(kwartieren: list[dict], tot_index: int, zaad: str, trekkingen: int = 200) -> dict:
    """Verdeling van het diepste tekort tot het bijvullen, uit de banden.

    Verbruik per kwartier tussen P10 en P90, zon tussen laag en hoog
    (driehoeksverdeling rond het midden). Vast zaad per snapshot: dezelfde
    invoer geeft dezelfde uitkomst.
    """
    gen = random.Random(zaad)
    deel = kwartieren[: max(0, tot_index)]
    if not deel or any(k.get("verbruik_p10") is None or k.get("zon_laag") is None for k in deel):
        return {"beschikbaar": False, "reden": "verbruiks- of zonband onbekend"}
    tekorten = []
    for _ in range(trekkingen):
        cum = diep = 0.0
        for k in deel:
            v = gen.triangular(k["verbruik_p10"], max(k["verbruik_p90"], k["verbruik_p10"]), k["verbruik"])
            z = gen.triangular(k["zon_laag"], max(k["zon_hoog"], k["zon_laag"]), k["zon"])
            cum = max(0.0, cum + v - z)
            diep = max(diep, cum)
        tekorten.append(diep)
    tekorten.sort()
    gewicht = [max(0.0, k["verbruik"] - k["zon"]) for k in deel]
    totaal = sum(gewicht)
    later = (
        sum(g * k["import"] for g, k in zip(gewicht, deel) if k["import"] is not None) / totaal
        if totaal > 0 else statistics.median([k["import"] for k in deel if k["import"] is not None] or [0.0])
    )
    return {"beschikbaar": True, "tekorten": tekorten, "importwaarde_later_eur": later}


def risicoreserve(verdeling: dict, verkoopwaarde_nu_eur: float | None, rendement_procent: float, stap: float = 0.25) -> dict:
    """Bewaar de volgende 0,25 kWh zolang P(nodig) x importwaarde later x
    ontlaadrendement groter is dan wat hij nu oplevert."""
    if not verdeling.get("beschikbaar") or verkoopwaarde_nu_eur is None:
        return {"kwh": None, "vertrouwen": None, "reden": verdeling.get("reden") or "verkoopwaarde onbekend"}
    tekorten = verdeling["tekorten"]
    n = len(tekorten)
    eta_uit = (rendement_procent / 100) ** 0.5
    k = 0.0
    while k < max(tekorten):
        kans = sum(1 for t in tekorten if t >= k + stap) / n
        if kans * verdeling["importwaarde_later_eur"] * eta_uit > verkoopwaarde_nu_eur:
            k += stap
        else:
            break
    spreiding = (tekorten[int(0.9 * (n - 1))] - tekorten[int(0.1 * (n - 1))]) if n > 1 else 0.0
    return {"kwh": round(k, 2), "vertrouwen": "hoog" if spreiding < 0.5 else ("middel" if spreiding < 1.5 else "laag"),
            "p50_tekort_kwh": round(tekorten[n // 2], 2), "p90_tekort_kwh": round(tekorten[int(0.9 * (n - 1))], 2)}


# --- waarom productie anders koos -----------------------------------------

def oorzaak(
    productie: str,
    schaduw_actie: str | None,
    *,
    reden: str | None,
    onder_bodem: bool,
    spiegel_lage_slijtage: str | None,
    snapshot_onvolledig: bool,
    vertrouwen: str | None,
) -> str | None:
    """Eén oorzaak uit een vaste lijst, als productie en schaduw verschillen."""
    if schaduw_actie is None or productie == schaduw_actie:
        return None
    r = (reden or "").lower()
    if snapshot_onvolledig:
        return "ontbrekende_informatie"
    if onder_bodem:
        return "harde_soc_grens"
    if spiegel_lage_slijtage == schaduw_actie:
        return "slijtage"
    if "soc_protected" in r or "reserve" in r:
        return "reserve"
    if "zonarm" in r or "plan" in r or "blocked" in r or "geblokkeerd" in r:
        return "beschermingspoort"
    if "offline" in r or "unavailable" in r or "niet_aangekomen" in r:
        return "zendure_beperking"
    if vertrouwen == "laag":
        return "forecast"
    return "andere_regel"
