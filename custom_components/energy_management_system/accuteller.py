"""Eigen laad- en ontlaadteller uit de lokale lezing van de accu (v5.103).

Gevraagd 19-10: "We hadden ook een lokale verbinding met de accu in het
EMS gebouwd" - en dan "hoe beter de integratie wordt hoe tevredener ik ben".

De kWh die de accu laadt en ontlaadt kwamen alleen uit de tellers van de
Zendure-integratie (`aggr_charge`/`aggr_discharge`, in HA opgeteld
vermogen). Valt die integratie uit, dan vallen de accukwartieren in de
meetlog weg - en daarmee een dag in het dagarchief en de zelfanalyse.

Hier telt het EMS zelf: elke lokale lezing (2 s) wordt het vermogen
opgeteld (trapeziumregel), twee koppelingen naast elkaar, want welke van de
twee de Zendure-integratie telt staat nergens beschreven:

    pack   outputPackPower (laden) / packInputPower (ontladen) - DC, aan de accu
    ac     gridInputPower (laden) / outputHomePower (ontladen) - AC, aan het net

Elk kwartier legt de meetlaag de eigen kWh naast die van de Zendure-tellers.
Pas als een koppeling over minstens een dag (MIN_KWARTIEREN) binnen
MAX_AFWIJKING ligt, is hij "betrouwbaar" en mag hij een kwartier invullen
waarin de Zendure-teller ontbreekt. Tot dan: alleen vergelijken.

Een gat langer dan MAX_GAT_S (geen lezing) wordt niet opgevuld - dan telt
de eigen teller niet, en is het kwartier ook niet in te vullen.

Zuivere functies, zonder Home Assistant.
"""
from __future__ import annotations

KOPPELINGEN = {
    "pack": ("outputPackPower", "packInputPower"),
    "ac": ("gridInputPower", "outputHomePower"),
}
MAX_GAT_S = 30.0
MIN_KWARTIEREN = 96
MAX_AFWIJKING = 0.05
#: De eigen stand mag hooguit zo oud zijn op een kwartiergrens.
VERS_S = 30.0


def leeg() -> dict:
    return {"t": None, "w": {}, "kwh": {f"{k}_{r}": 0.0 for k in KOPPELINGEN for r in ("laden", "ontladen")},
            "gat_s": 0.0, "gaten": 0}


def integreer(teller: dict, apparaat: dict, nu: float) -> None:
    """Eén lezing optellen. `apparaat`: de genormaliseerde velden (W)."""
    vorige_t, vorige_w = teller.get("t"), teller.get("w") or {}
    nieuw_w = {}
    for koppeling, (laden, ontladen) in KOPPELINGEN.items():
        for richting, veld in (("laden", laden), ("ontladen", ontladen)):
            w = apparaat.get(veld)
            if w is not None:
                nieuw_w[f"{koppeling}_{richting}"] = max(0.0, float(w))
    if vorige_t is not None:
        dt = nu - vorige_t
        if 0 < dt <= MAX_GAT_S:
            kwh = teller.setdefault("kwh", leeg()["kwh"])
            for sleutel, w in nieuw_w.items():
                if sleutel in vorige_w:
                    kwh[sleutel] = kwh.get(sleutel, 0.0) + (vorige_w[sleutel] + w) / 2 * dt / 3_600_000
        elif dt > MAX_GAT_S:
            teller["gat_s"] = float(teller.get("gat_s") or 0.0) + dt
            teller["gaten"] = int(teller.get("gaten") or 0) + 1
    teller["t"] = nu
    teller["w"] = nieuw_w


def standen(teller: dict | None, nu: float) -> dict | None:
    """De eigen tellerstanden (kWh) per koppeling, of None als de laatste lezing te oud is."""
    if not teller or teller.get("t") is None or nu - teller["t"] > VERS_S:
        return None
    kwh = teller.get("kwh") or {}
    return {k: {"battery_in": kwh.get(f"{k}_laden"), "battery_out": kwh.get(f"{k}_ontladen")} for k in KOPPELINGEN}


def deltas(begin: dict | None, eind: dict | None) -> dict | None:
    """Per koppeling de kWh in het kwartier."""
    if not begin or not eind:
        return None
    uit = {}
    for k in KOPPELINGEN:
        b, e = begin.get(k) or {}, eind.get(k) or {}
        waarden = {}
        for t in ("battery_in", "battery_out"):
            if b.get(t) is None or e.get(t) is None or e[t] < b[t]:
                break
            waarden[t] = e[t] - b[t]
        else:
            uit[k] = waarden
    return uit or None


def lege_vergelijking() -> dict:
    return {k: {"n": 0, "zendure_kwh": 0.0, "eigen_kwh": 0.0, "abs_verschil_kwh": 0.0} for k in KOPPELINGEN}


def vergelijk_kwartier(verg: dict, zendure: dict, eigen: dict) -> None:
    """Eén kwartier: de Zendure-teller (battery_in/out kWh) tegen de eigen per koppeling."""
    for k, d in (eigen or {}).items():
        v = verg.setdefault(k, lege_vergelijking()[k])
        z = zendure["battery_in"] + zendure["battery_out"]
        e = d["battery_in"] + d["battery_out"]
        v["n"] += 1
        v["zendure_kwh"] += z
        v["eigen_kwh"] += e
        v["abs_verschil_kwh"] += (abs(zendure["battery_in"] - d["battery_in"])
                                  + abs(zendure["battery_out"] - d["battery_out"]))


def afwijking(v: dict) -> float | None:
    if not v.get("zendure_kwh"):
        return None
    return v["abs_verschil_kwh"] / v["zendure_kwh"]


def beste_koppeling(verg: dict) -> str | None:
    """De koppeling die betrouwbaar dezelfde kWh telt als de Zendure-integratie."""
    kandidaten = [(afwijking(v), k) for k, v in (verg or {}).items()
                  if v.get("n", 0) >= MIN_KWARTIEREN and afwijking(v) is not None]
    kandidaten = [(a, k) for a, k in kandidaten if a <= MAX_AFWIJKING]
    return min(kandidaten)[1] if kandidaten else None


def samenvatting(teller: dict | None, verg: dict | None, ingevuld: int = 0) -> dict:
    teller, verg = teller or {}, verg or {}
    beste = beste_koppeling(verg)
    per = {}
    for k, v in verg.items():
        a = afwijking(v)
        per[k] = {"kwartieren": v.get("n", 0), "zendure_kwh": round(v.get("zendure_kwh", 0.0), 2),
                  "eigen_kwh": round(v.get("eigen_kwh", 0.0), 2),
                  "afwijking_procent": round(100 * a, 1) if a is not None else None}
    if beste:
        oordeel = f"betrouwbaar ({beste}, {per[beste]['afwijking_procent']}% afwijking) - vult ontbrekende kwartieren in"
    elif max((v.get("n", 0) for v in verg.values()), default=0) < MIN_KWARTIEREN:
        oordeel = f"vergelijkt nog (minimaal {MIN_KWARTIEREN} kwartieren)"
    else:
        oordeel = f"geen koppeling binnen {round(100 * MAX_AFWIJKING)}% - vult niets in"
    return {
        "oordeel": oordeel,
        "betrouwbare_koppeling": beste,
        "per_koppeling": per,
        "stand_kwh": {k: round(v, 3) for k, v in (teller.get("kwh") or {}).items()},
        "gaten": teller.get("gaten", 0),
        "gat_totaal_s": round(float(teller.get("gat_s") or 0.0), 1),
        "kwartieren_ingevuld": ingevuld,
    }
