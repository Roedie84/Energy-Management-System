"""Wat de accu werkelijk kost en oplevert, uit de eigen gegevens (v5.115.0).

Gevraagd 21-10: "Kijk vooral nog even naar of het rendabel is om bij te laden
met kleinere prijsverschillen en het accu rendement" en daarna "Op basis van
data dus inkoop/ontlaadt/rendement kosten etc bepalen".

Het laadbesluit rekent vooraf: een kWh van nu is straks
``latere prijs x rendement - slijtage`` waard. Of dat ook zo uitkomt, wist
niemand. Hier wordt het nagerekend, kwartier voor kwartier uit het
dagverloop (40 dagen):

* Elke toename van de inhoud is een PARTIJ, met zijn herkomst (net of zon,
  uit wat de netmeter op dat moment deed) en zijn inkoopprijs per kWh die
  erin ging. Bij een partij uit het net staat erbij wat het laadbesluit
  verwachtte dat hij waard zou zijn.
* Elke afname wordt uit de oudste partij gehaald (eerst erin, eerst eruit)
  en gewaardeerd tegen de prijs van het kwartier waarin hij het huis of het
  net in ging, maal het ontlaadrendement. Een afname zonder ontladen
  (rustverbruik van de omvormer) levert niets op en telt apart.

Daaruit volgt per herkomst: inkoop, opbrengst en de GEREALISEERDE marge per
kWh, en voor netladingen het verschil tussen verwacht en gerealiseerd. Valt
dat stelselmatig tegen (de lading bleef langer zitten, ging in goedkopere
kwartieren op of verdween in rustverbruik), dan is dat verschil de
DATACORRECTIE: zoveel moet een netlading voortaan extra opleveren voordat
het EMS hem doet. Nooit negatief - een meevaller maakt het laden niet
ruimer - en begrensd, zodat een paar rare dagen het laden niet stilzetten.

Zon wordt gewaardeerd tegen de prijs van het kwartier waarin hij werd
opgeslagen: zolang er gesaldeerd wordt, is dat wat hij bij teruglevering
had opgebracht. Zuiver Python, zonder Home Assistant.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

#: Kleiner verschil in inhoud is afronding (de inhoud komt uit de laadstand).
STAP_KWH = 0.005
#: Een gat in het dagverloop van meer dan dit: daarover niets toerekenen.
MAX_GAT = timedelta(minutes=60)
#: Vermogen waaronder de accu als stilstaand telt.
STIL_W = 50.0
#: Zoveel dagen terug telt de datacorrectie.
CORRECTIE_DAGEN = 30
#: Pas een correctie bij zoveel dagen met netlading, en zoveel kWh ontladen.
CORRECTIE_MIN_DAGEN = 5
CORRECTIE_MIN_KWH = 10.0
#: Nooit meer dan dit per kWh (in euro).
CORRECTIE_MAX_EUR = 0.05


@dataclass
class Partij:
    kwh: float                  # opgeslagen kWh die er nog in zit
    inkoop_eur: float           # per kWh die erin ging (AC)
    bron: str                   # "net", "zon" of "begin"
    dag: str
    verwacht_eur: float | None  # laadbesluit: waarde per kWh die erin ging


def _moment(dag: str, tijd: str) -> datetime | None:
    try:
        return datetime.fromisoformat(f"{dag}T{tijd}")
    except (TypeError, ValueError):
        return None


def _regels(dagverloop: dict):
    for dag in sorted(dagverloop or {}):
        for r in sorted(dagverloop[dag] or [], key=lambda x: str(x.get("tijd"))):
            if isinstance(r, dict):
                yield dag, r


def _getal(r: dict, sleutel: str) -> float | None:
    v = r.get(sleutel)
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _aandeel_net(r: dict) -> float:
    """Welk deel van een toename uit het net kwam."""
    laad_w = -(_getal(r, "accu_w") or 0.0)
    net_w = _getal(r, "net_w")
    if laad_w > STIL_W and net_w is not None:
        return min(1.0, max(0.0, net_w / laad_w))
    return 1.0 if str(r.get("reden") or "").startswith("grid_charging") else 0.0


class _Teller:
    def __init__(self) -> None:
        self.t = {b: {"in_kwh": 0.0, "inkoop_eur": 0.0, "uit_kwh": 0.0, "geleverd_kwh": 0.0,
                      "opbrengst_eur": 0.0, "kosten_uit_eur": 0.0, "verwacht_eur": 0.0,
                      "verwacht_ac_kwh": 0.0, "gerealiseerd_bij_verwacht_eur": 0.0}
                  for b in ("net", "zon")}
        self.rust_kwh = 0.0
        self.rust_eur = 0.0
        self.per_dag: dict = {}
        self.afwijking: list = []     # (dag, ac_kwh, verwacht - gerealiseerd per kWh)


def doorreken(
    dagverloop: dict,
    eta_laad: float,
    eta_ontlaad: float,
    slijtage_eur: float,
    nu: datetime | None = None,
) -> dict:
    """Reken het dagverloop door. Rendementen als fractie (0,92), slijtage in
    euro per kWh die erin gaat - dezelfde eenheden als het laadbesluit."""
    if not (0 < eta_laad <= 1 and 0 < eta_ontlaad <= 1):
        return {"beschikbaar": False, "reden": "geen rendement"}
    partijen: list[Partij] = []
    tel = _Teller()
    vorig_moment = vorige_inhoud = None
    for dag, r in _regels(dagverloop):
        moment = _moment(dag, str(r.get("tijd")))
        inhoud = _getal(r, "beschikbaar_kwh")
        if moment is None or inhoud is None:
            continue
        if vorig_moment is None or moment - vorig_moment > MAX_GAT or moment <= vorig_moment:
            # (opnieuw) beginnen: wat erin zit heeft een onbekende inkoop
            partijen = [Partij(inhoud, 0.0, "begin", dag, None)] if inhoud > 0 else []
        else:
            _verwerk(partijen, tel, dag, r, inhoud - vorige_inhoud, eta_laad, eta_ontlaad, slijtage_eur)
        vorig_moment, vorige_inhoud = moment, inhoud
    uit = _samenvatting(tel, partijen, eta_laad * eta_ontlaad, slijtage_eur, nu)
    uit["voorraad_kostprijs"] = voorraad_kostprijs(partijen, eta_laad)
    return uit


#: Pas een kostprijs van de voorraad bij zoveel opgeslagen kWh met bekende inkoop.
VOORRAAD_MIN_KWH = 0.1


def voorraad_kostprijs(partijen: list, eta_laad: float) -> dict:
    """Wat de energie die nu in de accu zit gekost heeft (v5.116.0).

    Per OPGESLAGEN kWh: de inkoop per kWh die erin ging, gedeeld door het
    laadrendement. Alleen partijen met een bekende inkoop (net en zon); een
    beginvoorraad na een gat telt niet mee. Daarmee waardeert de dagbesparing
    het verschil in accu-inhoud tegen wat het werkelijk kostte om erin te
    krijgen, in plaats van tegen de prijs van het moment.
    """
    bekend = [p for p in partijen if p.bron in ("net", "zon") and p.kwh > 0]
    kwh = sum(p.kwh for p in bekend)
    uit = {"bekend_kwh": round(kwh, 2),
           "onbekend_kwh": round(sum(p.kwh for p in partijen if p.bron == "begin"), 2),
           "eur_per_kwh": None}
    if kwh >= VOORRAAD_MIN_KWH and eta_laad > 0:
        uit["eur_per_kwh"] = round(sum(p.kwh * p.inkoop_eur for p in bekend) / kwh / eta_laad, 4)
    return uit


def _verwerk(partijen, tel, dag, r, delta, eta_laad, eta_ontlaad, slijtage_eur) -> None:
    prijs = _getal(r, "prijs_ct")
    if prijs is None or abs(delta) < STAP_KWH:
        return
    prijs /= 100
    dagtel = tel.per_dag.setdefault(dag, {"net_in_kwh": 0.0, "net_inkoop_eur": 0.0,
                                          "geleverd_kwh": 0.0, "opbrengst_eur": 0.0,
                                          "net_marge_eur": 0.0, "net_uit_ac_kwh": 0.0})
    if delta > 0:
        net = _aandeel_net(r)
        verwacht = _getal(r, "laad_waarde_ct")
        for bron, deel in (("net", net), ("zon", 1.0 - net)):
            kwh = delta * deel
            if kwh <= 0:
                continue
            ac = kwh / eta_laad
            tel.t[bron]["in_kwh"] += ac
            tel.t[bron]["inkoop_eur"] += ac * prijs
            if bron == "net":
                dagtel["net_in_kwh"] += ac
                dagtel["net_inkoop_eur"] += ac * prijs
            partijen.append(Partij(kwh, prijs, bron, dag,
                                   verwacht / 100 if bron == "net" and verwacht is not None else None))
        return
    weg = -delta
    ontlaadt = (_getal(r, "accu_w") or 0.0) > STIL_W or (
        (_getal(r, "huis_w") or 0.0) > (_getal(r, "pv_w") or 0.0) + STIL_W
    )
    while weg > 1e-9 and partijen:
        p = partijen[0]
        x = min(p.kwh, weg)
        p.kwh -= x
        weg -= x
        if p.kwh <= 1e-9:
            partijen.pop(0)
        if not ontlaadt:
            tel.rust_kwh += x
            if p.bron != "begin":
                tel.rust_eur += x / eta_laad * p.inkoop_eur
            continue
        geleverd = x * eta_ontlaad
        dagtel["geleverd_kwh"] += geleverd
        dagtel["opbrengst_eur"] += geleverd * prijs
        if p.bron == "begin":
            continue
        ac = x / eta_laad                      # wat er voor dit deel in ging
        t = tel.t[p.bron]
        t["uit_kwh"] += ac
        t["geleverd_kwh"] += geleverd
        t["opbrengst_eur"] += geleverd * prijs
        t["kosten_uit_eur"] += ac * (p.inkoop_eur + slijtage_eur)
        # per kWh die erin ging: zelfde maat als het laadbesluit
        gerealiseerd = geleverd * prijs / ac - slijtage_eur
        if p.bron == "net":
            dagtel["net_uit_ac_kwh"] += ac
            dagtel["net_marge_eur"] += ac * (gerealiseerd - p.inkoop_eur)
            if p.verwacht_eur is not None:
                t["verwacht_eur"] += ac * p.verwacht_eur
                t["verwacht_ac_kwh"] += ac
                t["gerealiseerd_bij_verwacht_eur"] += ac * gerealiseerd
                tel.afwijking.append((p.dag, ac, p.verwacht_eur - gerealiseerd))


def _per_kwh(eur: float, kwh: float) -> float | None:
    return round(eur / kwh * 100, 1) if kwh > 0.05 else None


def _bron_samen(t: dict) -> dict:
    marge = t["opbrengst_eur"] - t["kosten_uit_eur"]
    return {
        "erin_kwh": round(t["in_kwh"], 2),
        "inkoop_ct": _per_kwh(t["inkoop_eur"], t["in_kwh"]),
        "ontladen_kwh": round(t["geleverd_kwh"], 2),
        "opbrengst_ct": _per_kwh(t["opbrengst_eur"], t["geleverd_kwh"]),
        "marge_eur": round(marge, 2),
        # per kWh die erin ging, na rendement en slijtage
        "marge_ct_per_kwh": _per_kwh(marge, t["uit_kwh"]),
    }


def correctie(afwijking: list, nu: datetime | None) -> dict:
    """Wat een netlading extra moet opleveren: het gewogen mediane tekort
    tussen verwacht en gerealiseerd, over de laatste CORRECTIE_DAGEN dagen."""
    if nu is not None:
        grens = (nu.date() - timedelta(days=CORRECTIE_DAGEN)).isoformat()
        afwijking = [a for a in afwijking if a[0] >= grens]
    dagen = len({a[0] for a in afwijking})
    kwh = sum(a[1] for a in afwijking)
    uit = {"dagen": dagen, "kwh": round(kwh, 2), "eur": 0.0}
    if dagen < CORRECTIE_MIN_DAGEN or kwh < CORRECTIE_MIN_KWH:
        uit["status"] = (
            f"nog te weinig gemeten ({dagen} van {CORRECTIE_MIN_DAGEN} dagen, "
            f"{kwh:.1f} van {CORRECTIE_MIN_KWH:.0f} kWh); geen correctie"
        )
        return uit
    gesorteerd = sorted(afwijking, key=lambda a: a[2])
    helft, loop, mediaan = kwh / 2, 0.0, 0.0
    for _d, k, v in gesorteerd:
        loop += k
        if loop >= helft:
            mediaan = v
            break
    uit["mediaan_tekort_ct"] = round(mediaan * 100, 2)
    uit["eur"] = round(min(CORRECTIE_MAX_EUR, max(0.0, mediaan)), 4)
    uit["status"] = (
        f"netladingen leverden {mediaan * 100:.1f} ct/kWh minder op dan verwacht; "
        f"laden moet {uit['eur'] * 100:.1f} ct/kWh extra opleveren"
        if uit["eur"] > 0
        else "netladingen leverden op wat verwacht was; geen correctie"
    )
    return uit


def _samenvatting(tel: _Teller, partijen: list, eta: float, slijtage_eur: float, nu) -> dict:
    net = tel.t["net"]
    dagen = []
    for dag, d in sorted(tel.per_dag.items())[-14:]:
        dagen.append({
            "datum": dag,
            "net_erin_kwh": round(d["net_in_kwh"], 2),
            "net_inkoop_ct": _per_kwh(d["net_inkoop_eur"], d["net_in_kwh"]),
            "ontladen_kwh": round(d["geleverd_kwh"], 2),
            "opbrengst_ct": _per_kwh(d["opbrengst_eur"], d["geleverd_kwh"]),
            "net_marge_eur": round(d["net_marge_eur"], 2),
        })
    return {
        "beschikbaar": True,
        "rendement_procent": round(eta * 100, 1),
        "slijtage_ct": round(slijtage_eur * 100, 2),
        "net": {
            **_bron_samen(net),
            "verwacht_ct": _per_kwh(net["verwacht_eur"], net["verwacht_ac_kwh"]),
            "gerealiseerd_ct": _per_kwh(net["gerealiseerd_bij_verwacht_eur"], net["verwacht_ac_kwh"]),
        },
        "zon": _bron_samen(tel.t["zon"]),
        "rust_kwh": round(tel.rust_kwh, 2),
        "rust_eur": round(tel.rust_eur, 2),
        "nog_in_accu_kwh": {b: round(sum(p.kwh for p in partijen if p.bron == b), 2)
                            for b in ("net", "zon", "begin")},
        "per_dag": dagen,
        "correctie": correctie(tel.afwijking, nu),
    }
