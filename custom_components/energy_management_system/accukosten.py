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
#: v5.167.0: wijkt de bijgehouden voorraad (partijen) zoveel af van de
#: gemeten inhoud, dan wordt hij gelijkgezet (~2 SoC-stappen van 0,115 kWh;
#: kleiner is de afronding van de laadstand).
GELIJKZETTEN_KWH = 0.25
#: v5.167.0: een eigen kwartiermeting in het dagverloop telt vanaf deze dekking.
DEKKING_MIN = 0.8


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
        self.afwijking: list = []     # (laaddag, ac_kwh, verwacht - gerealiseerd per kWh, ontlaaddag)
        # v5.167.0
        self.gat_dagen: set = set()
        self.gat_kwh = 0.0
        self.gemeten_kwartieren = 0
        self.onbekend_geleverd_kwh = 0.0


def doorreken(
    dagverloop: dict,
    eta_laad: float,
    eta_ontlaad: float,
    slijtage_eur: float,
    nu: datetime | None = None,
    banden: dict | None = None,
    gemeten: dict | None = None,
) -> dict:
    """Reken het dagverloop door. Rendementen als fractie (0,92), slijtage in
    euro per kWh DOOR DE CELLEN (v5.167.0; per kWh die erin gaat is dat
    slijtage x laadrendement).

    v5.122.0 (punt 7): met `banden` (`rendement_per_band`) het rendement van
    de vermogensband van dat kwartier, zolang die band betrouwbaar is; anders
    `eta_laad`/`eta_ontlaad`.

    v5.167.0 (audit 02-11): met een gemeten kwartier (eigen kwartiermeting in
    het dagverloop, of `gemeten[dag]["HH:MM"]` uit de meetlaag) telt de
    AC-energie van dat kwartier: wat eruit kwam IS de levering, wat erin ging
    maal het laadrendement komt erbij. De laadstand (stappen van 1 %) zet de
    voorraad alleen gelijk in een stilstandkwartier (tijdens laden of
    ontladen loopt hij achter op de meter) en als hij meer dan
    GELIJKZETTEN_KWH afwijkt. Zonder
    meting de laadstand als voorheen. Een gat van meer dan MAX_GAT gooit de
    partijen niet meer weg: niets toerekenen over het gat, daarna gelijkzetten;
    dagen met zo'n gat tellen niet mee in de datacorrectie.
    """
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
        vermogen = _getal(r, "accu_w")
        e_l = band_rendement(banden, "laden", vermogen, eta_laad)
        e_o = band_rendement(banden, "ontladen", vermogen, eta_ontlaad)
        if vorig_moment is None:
            if inhoud > 0:
                partijen.append(Partij(inhoud, 0.0, "begin", dag, None))
        elif moment - vorig_moment > MAX_GAT or moment <= vorig_moment:
            # v5.167.0: niets toerekenen over het gat, de partijen houden
            tel.gat_dagen.update({dag, vorig_moment.date().isoformat()})
            tel.gat_kwh += abs(_gelijkzetten(partijen, inhoud, dag, None, 0.0))
        else:
            stroom = meting_kwartier(dag, r, gemeten)
            if stroom is not None:
                tel.gemeten_kwartieren += 1
                _verwerk_gemeten(partijen, tel, dag, r, stroom, e_l, e_o, slijtage_eur)
                if stroom[0] + stroom[1] <= STIL_KWH:
                    # alleen in stilstand: tijdens laden/ontladen loopt de
                    # laadstand achter op de meter
                    _gelijkzetten(partijen, inhoud, dag, tel, e_l)
            else:
                _verwerk(partijen, tel, dag, r, inhoud - vorige_inhoud, e_l, e_o, slijtage_eur)
        vorig_moment, vorige_inhoud = moment, inhoud
    uit = _samenvatting(tel, partijen, eta_laad * eta_ontlaad, slijtage_eur, nu)
    uit["voorraad_kostprijs"] = voorraad_kostprijs(partijen, eta_laad)
    return uit


def meting_kwartier(dag: str, r: dict, gemeten: dict | None) -> tuple[float, float, str] | None:
    """(AC erin, AC eruit, bron) van een kwartier, of None zonder meting (v5.167.0).

    Eerst de eigen kwartiermeting in het dagverloop (`accu_in_kwh`,
    `accu_uit_kwh`: het accuvermogen over het kwartier opgeteld, met
    `accu_dekking` >= DEKKING_MIN); dan de meetlaag (`gemeten[dag]["HH:MM"]`,
    tellers per kwartier vanaf zijn begin - dezelfde sleutel als de regel
    van het dagverloop, waarvan de inhoud op het eind van dat kwartier staat).
    """
    erin, eruit = _getal(r, "accu_in_kwh"), _getal(r, "accu_uit_kwh")
    if erin is not None and eruit is not None and (_getal(r, "accu_dekking") or 0.0) >= DEKKING_MIN:
        return max(0.0, erin), max(0.0, eruit), "kwartiermeting"
    m = ((gemeten or {}).get(dag) or {}).get(str(r.get("tijd")))
    if not isinstance(m, dict):
        return None
    erin, eruit = _getal(m, "accu_in_kwh"), _getal(m, "accu_uit_kwh")
    if erin is not None and eruit is not None:
        return max(0.0, erin), max(0.0, eruit), "meetlaag"
    netto = _getal(m, "accu_kwh")
    if netto is None:
        return None
    return max(0.0, -netto), max(0.0, netto), "meetlaag"


def _gelijkzetten(partijen: list, inhoud: float, dag: str, tel, eta_laad: float) -> float:
    """Zet de partijen gelijk aan de gemeten inhoud als ze meer dan
    GELIJKZETTEN_KWH afwijken (v5.167.0). Te veel: de oudste partijen eruit
    (met `tel` als rustverbruik: de accu verloor het zonder te leveren). Te
    weinig: een partij met onbekende inkoop erbij. Geeft het verschil terug."""
    verschil = inhoud - sum(p.kwh for p in partijen)
    if abs(verschil) <= (GELIJKZETTEN_KWH if tel is not None else STAP_KWH):
        return 0.0
    if verschil > 0:
        partijen.append(Partij(verschil, 0.0, "begin", dag, None))
        return verschil
    _rust(partijen, tel, -verschil, eta_laad)
    return verschil


def _rust(partijen: list, tel, weg: float, eta_laad: float) -> None:
    """`weg` kWh uit de oudste partijen zonder levering: rustverbruik (met
    `tel`), of niet toe te rekenen (zonder)."""
    while weg > 1e-9 and partijen:
        p = partijen[0]
        x = min(p.kwh, weg)
        p.kwh -= x
        weg -= x
        if p.kwh <= 1e-9:
            partijen.pop(0)
        if tel is not None:
            tel.rust_kwh += x
            if p.bron != "begin" and eta_laad > 0:
                tel.rust_eur += x / eta_laad * p.inkoop_eur


def _verwerk_gemeten(partijen, tel, dag, r, stroom, eta_laad, eta_ontlaad, slijtage_eur) -> None:
    """Een gemeten kwartier: AC erin maal laadrendement erbij, AC eruit is de
    levering en haalt eruit / ontlaadrendement uit de oudste partijen."""
    prijs = _getal(r, "prijs_ct")
    if prijs is None:
        return
    erin, eruit, _bron = stroom
    if erin > 1e-6:
        _boek_lading(partijen, tel, dag, r, erin * eta_laad, eta_laad, prijs / 100)
    if eruit > 1e-6:
        _boek_levering(partijen, tel, dag, eruit / eta_ontlaad, eta_ontlaad, eta_laad,
                       prijs / 100, slijtage_eur)


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


def _dagtel(tel, dag) -> dict:
    return tel.per_dag.setdefault(dag, {"net_in_kwh": 0.0, "net_inkoop_eur": 0.0,
                                        "geleverd_kwh": 0.0, "opbrengst_eur": 0.0,
                                        "net_marge_eur": 0.0, "net_uit_ac_kwh": 0.0})


def _verwerk(partijen, tel, dag, r, delta, eta_laad, eta_ontlaad, slijtage_eur) -> None:
    """Een kwartier zonder meting: uit de verandering van de laadstand."""
    prijs = _getal(r, "prijs_ct")
    if prijs is None or abs(delta) < STAP_KWH:
        return
    prijs /= 100
    if delta > 0:
        _boek_lading(partijen, tel, dag, r, delta, eta_laad, prijs)
        return
    weg = -delta
    ontlaadt = (_getal(r, "accu_w") or 0.0) > STIL_W or (
        (_getal(r, "huis_w") or 0.0) > (_getal(r, "pv_w") or 0.0) + STIL_W
    )
    if not ontlaadt:
        _rust(partijen, tel, weg, eta_laad)
        return
    _boek_levering(partijen, tel, dag, weg, eta_ontlaad, eta_laad, prijs, slijtage_eur)


def _boek_lading(partijen, tel, dag, r, opgeslagen, eta_laad, prijs) -> None:
    """`opgeslagen` kWh erbij, verdeeld over net en zon naar de netmeter."""
    dagtel = _dagtel(tel, dag)
    net = _aandeel_net(r)
    verwacht = _getal(r, "laad_waarde_ct")
    for bron, deel in (("net", net), ("zon", 1.0 - net)):
        kwh = opgeslagen * deel
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


def _boek_levering(partijen, tel, dag, weg, eta_ontlaad, eta_laad, prijs, slijtage_eur) -> None:
    """`weg` kWh uit de oudste partijen; elke kWh uit de cellen levert
    `eta_ontlaad` kWh aan het huis of het net. Slijtage per kWh door de
    cellen (v5.167.0: niet meer per kWh die erin ging)."""
    dagtel = _dagtel(tel, dag)
    rest = weg
    while rest > 1e-9:
        if not partijen:
            # meer geleverd dan er bijgehouden was: de rest uit onbekende voorraad
            geleverd = rest * eta_ontlaad
            dagtel["geleverd_kwh"] += geleverd
            dagtel["opbrengst_eur"] += geleverd * prijs
            tel.onbekend_geleverd_kwh += geleverd
            break
        p = partijen[0]
        x = min(p.kwh, rest)
        p.kwh -= x
        rest -= x
        if p.kwh <= 1e-9:
            partijen.pop(0)
        geleverd = x * eta_ontlaad
        dagtel["geleverd_kwh"] += geleverd
        dagtel["opbrengst_eur"] += geleverd * prijs
        if p.bron == "begin":
            tel.onbekend_geleverd_kwh += geleverd
            continue
        ac = x / eta_laad                      # wat er voor dit deel in ging
        t = tel.t[p.bron]
        t["uit_kwh"] += ac
        t["geleverd_kwh"] += geleverd
        t["opbrengst_eur"] += geleverd * prijs
        t["kosten_uit_eur"] += ac * p.inkoop_eur + x * slijtage_eur
        # per kWh die erin ging: zelfde maat als het laadbesluit
        gerealiseerd = (geleverd * prijs - x * slijtage_eur) / ac
        if p.bron == "net":
            dagtel["net_uit_ac_kwh"] += ac
            dagtel["net_marge_eur"] += ac * (gerealiseerd - p.inkoop_eur)
            if p.verwacht_eur is not None:
                t["verwacht_eur"] += ac * p.verwacht_eur
                t["verwacht_ac_kwh"] += ac
                t["gerealiseerd_bij_verwacht_eur"] += ac * gerealiseerd
                tel.afwijking.append((p.dag, ac, p.verwacht_eur - gerealiseerd, dag))


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
        # v5.167.0: alles wat de accu leverde (ook uit voorraad met onbekende
        # inkoop) - hoort bij de AC-teller van de accu te liggen
        "ontladen_totaal_kwh": round(sum(d["geleverd_kwh"] for d in tel.per_dag.values()), 2),
        "ontladen_onbekende_inkoop_kwh": round(tel.onbekend_geleverd_kwh, 2),
        "gemeten_kwartieren": tel.gemeten_kwartieren,
        "dagen_met_gat": sorted(tel.gat_dagen),
        "niet_toegerekend_over_gaten_kwh": round(tel.gat_kwh, 2),
        "correctie": correctie(
            [(a[0], a[1], a[2]) for a in tel.afwijking
             if a[0] not in tel.gat_dagen and a[3] not in tel.gat_dagen], nu),
    }


# --- v5.122.0: sluimerverbruik per stilstand-uur (punt 4) en rendement per
# vermogensband (punt 7) -------------------------------------------------------
#
# Beide uit dezelfde kwartierreeks: per kwartier de beschikbare energie aan
# het eind (dagverloop) en wat de accu aan de netkant deed (meetlaag:
# uit - in, of het accuvermogen als terugval).

#: Een kwartier is stilstand als er minder dan dit door de accu ging (kWh, 50 W).
STIL_KWH = 0.0125
#: Pas na zoveel stilstand-uren per stand een betrouwbaar getal.
SLUIMER_MIN_UUR = 6.0
#: Binnen zoveel procentpunt van de bovengrens/ondergrens telt de accu als vol/leeg.
GRENS_MARGE_PROCENT = 2.0
#: De vermogensbanden (W, aan de netkant): bovengrenzen.
BANDEN_W = (500.0, 1500.0)
BAND_NAMEN = ("<500 W", "500-1500 W", ">1500 W")
#: Een band is betrouwbaar met zoveel kwartieren en zoveel kWh.
BAND_MIN_KWARTIEREN = 40
BAND_MIN_KWH = 5.0
#: Een kwartier telt alleen mee als er minstens dit door de accu ging (kWh).
#: v5.166.0: niet meer gebruikt door `rendement_per_band` (zie RONDE_*);
#: blijft staan voor wie er nog naar verwijst.
BAND_MIN_KWARTIER_KWH = 0.03
#: Rendementen buiten deze grenzen zijn meetfouten (SoC-stap, gat).
BAND_RENDEMENT_MIN = 0.5
BAND_RENDEMENT_MAX = 1.0
#: v5.166.0: een ronde (laden of ontladen) mag per ronde tot zoveel boven
#: BAND_RENDEMENT_MAX uitkomen voor hij als meetfout geldt. Ontladen in
#: inhoud-eenheden is gemeten ~1,0 (de SoC is op de bruikbare afgifte
#: geijkt); de SoC-stap van 1 % laat een ronde daar eerlijk overheen gaan.
#: De uitkomst per band blijft op BAND_RENDEMENT_MAX afgekapt.
RONDE_RENDEMENT_SPELING = 0.15
#: Een ronde telt pas mee met minstens zoveel kWh aan de netkant (~3
#: SoC-stappen van 0,115 kWh). Bewust op de AC-kant geselecteerd, niet op
#: de inhoud: selecteren op de SoC-stap brengt precies de vertekening terug
#: die v5.166.0 weghaalt.
RONDE_MIN_KWH = 0.35


def kwartierreeks(dagverloop: dict, gemeten: dict | None = None) -> list[dict]:
    """Opeenvolgende kwartierparen: Δinhoud en de netkant van de accu.

    De netkant uit `meting_kwartier` (v5.167.0: eerst de eigen kwartiermeting
    in het dagverloop, dan de meetlaag `gemeten[dag]["HH:MM"]`), anders het
    accuvermogen van het dagverloop / 4000. `accu_kwh` = eruit - erin;
    `in_kwh`/`uit_kwh` apart. Een gat van meer dan een kwartier begint
    opnieuw.
    """
    uit = []
    vorige = None
    for dag, r in _regels(dagverloop):
        moment = _moment(dag, str(r.get("tijd")))
        inhoud = _getal(r, "beschikbaar_kwh")
        if moment is None or inhoud is None:
            vorige = None
            continue
        if vorige is not None and timedelta(0) < moment - vorige[0] <= timedelta(minutes=16):
            stroom = meting_kwartier(dag, r, gemeten)
            if stroom is not None:
                erin, eruit, bron = stroom
                accu = eruit - erin
            else:
                accu = (_getal(r, "accu_w") or 0.0) / 4000
                erin, eruit, bron = max(0.0, -accu), max(0.0, accu), "vermogen"
            uit.append({
                "dag": dag, "tijd": r.get("tijd"), "delta_kwh": inhoud - vorige[1], "accu_kwh": accu,
                "in_kwh": erin, "uit_kwh": eruit,
                "bron": bron, "soc": _getal(r, "soc"), "stand": str(r.get("stand") or ""),
                "reden": str(r.get("reden") or ""),
            })
        vorige = (moment, inhoud)
    return uit


def _stilstand_soort(q: dict, min_soc: float, bovengrens: float) -> str:
    soc = q.get("soc")
    if soc is not None and soc >= bovengrens - GRENS_MARGE_PROCENT:
        return "vol"
    if soc is not None and soc <= min_soc + GRENS_MARGE_PROCENT:
        return "leeg"
    if "sparen" in q["stand"] or "spaar" in q["reden"] or q["stand"].startswith("smart_charging"):
        return "sparen"
    return "overig"


def sluimerverbruik(reeks: list[dict], min_soc: float, bovengrens: float) -> dict:
    """Wat de accu gebruikt als hij stilstaat, per stand (punt 4).

    Per stilstandkwartier: sluimer = afname van de inhoud + wat er van het
    net in ging (min wat eruit kwam). Vol of leeg trekt hij het uit het net,
    halverwege (sparen) uit de cellen. Alleen meten; stuurt niets.
    """
    per: dict = {}
    for q in reeks:
        if abs(q["accu_kwh"]) * 1 > STIL_KWH:
            continue
        sluimer = -q["delta_kwh"] - q["accu_kwh"]
        if sluimer < -0.05 or sluimer > 0.1:
            continue   # een SoC-stap of meetfout, geen sluimer
        soort = _stilstand_soort(q, min_soc, bovengrens)
        t = per.setdefault(soort, {"kwartieren": 0, "kwh": 0.0})
        t["kwartieren"] += 1
        t["kwh"] += sluimer
    uit = {}
    for soort in ("sparen", "vol", "leeg", "overig"):
        t = per.get(soort)
        if not t:
            continue
        uren = t["kwartieren"] / 4
        uit[soort] = {
            "uren": round(uren, 1),
            "kwh": round(t["kwh"], 3),
            "gemiddeld_w": round(max(0.0, t["kwh"]) / uren * 1000, 1) if uren else None,
            "betrouwbaar": uren >= SLUIMER_MIN_UUR,
        }
    totaal_uren = sum(v["uren"] for v in uit.values())
    totaal_kwh = sum(v["kwh"] for v in uit.values())
    return {
        "per_stand": uit,
        # v5.167.0: over lange stilstandblokken, zonder kwartierfilter
        "zelfontlading_blokken": sluimer_blokken(reeks, min_soc, bovengrens),
        "stilstand_uren": round(totaal_uren, 1),
        "gemiddeld_w": round(max(0.0, totaal_kwh) / totaal_uren * 1000, 1) if totaal_uren else None,
        "toelichting": (
            "Per kwartier zonder laden of ontladen (< 50 W): afname van de inhoud plus wat er van "
            "het net in ging. Vol of leeg komt het uit het net, bij sparen uit de cellen. "
            "Alleen meten; schrijven naar de Zendure is niet goedgekeurd."
        ),
    }


#: v5.167.0: een stilstandblok telt mee vanaf zoveel uur aaneen.
SLUIMER_BLOK_MIN_UUR = 3.0
#: Een blok met meer dan dit gemiddeld (W) is geen sluimer maar een meetfout.
SLUIMER_BLOK_MAX_W = 100.0


def _stilstand_blokken(reeks: list[dict]) -> list[list[dict]]:
    """Aaneengesloten stilstandkwartieren (< 50 W, zonder gat) als blokken."""
    blokken: list[list[dict]] = []
    huidig: list[dict] = []
    vorig = None
    for q in reeks:
        moment = _moment(str(q.get("dag")), str(q.get("tijd")))
        aansluitend = (moment is not None and vorig is not None
                       and timedelta(0) < moment - vorig <= timedelta(minutes=16))
        vorig = moment
        if huidig and (not aansluitend or abs(q["accu_kwh"]) > STIL_KWH):
            blokken.append(huidig)
            huidig = []
        if abs(q["accu_kwh"]) <= STIL_KWH:
            huidig.append(q)
    if huidig:
        blokken.append(huidig)
    return blokken


def sluimer_blokken(reeks: list[dict], min_soc: float, bovengrens: float) -> dict:
    """Zelfontlading over lange stilstandblokken (v5.167.0, audit punt 8).

    Per kwartier valt een kwartier MET SoC-stap (0,115 kWh) buiten het filter
    van `sluimerverbruik`, dus de cellen leken nooit iets te verliezen. Over
    een blok van >= SLUIMER_BLOK_MIN_UUR uur: afname inhoud (begin - eind)
    plus wat er van het net in ging min wat eruit kwam. De stap van 1 % aan
    begin en eind middelt over veel blokken uit. Per stand van het eerste
    kwartier. Alleen meten; stuurt niets.
    """
    per: dict = {}
    for blok in _stilstand_blokken(reeks):
        uren = len(blok) / 4
        if uren < SLUIMER_BLOK_MIN_UUR:
            continue
        kwh = -sum(q["delta_kwh"] for q in blok) - sum(q["accu_kwh"] for q in blok)
        if abs(kwh) / uren * 1000 > SLUIMER_BLOK_MAX_W:
            continue
        t = per.setdefault(_stilstand_soort(blok[0], min_soc, bovengrens), {"blokken": 0, "uren": 0.0, "kwh": 0.0})
        t["blokken"] += 1
        t["uren"] += uren
        t["kwh"] += kwh
    return {
        soort: {"blokken": t["blokken"], "uren": round(t["uren"], 1), "kwh": round(t["kwh"], 3),
                "gemiddeld_w": round(t["kwh"] / t["uren"] * 1000, 1),
                "betrouwbaar": t["uren"] >= SLUIMER_MIN_UUR and t["blokken"] >= 3}
        for soort, t in per.items()
    }


def _band(kw: float) -> int:
    w = kw * 1000
    for i, grens in enumerate(BANDEN_W):
        if w < grens:
            return i
    return len(BANDEN_W)


def _richting(accu_kwh: float) -> str | None:
    """'laden', 'ontladen' of None (stilstand, < 50 W) voor één kwartier."""
    if accu_kwh >= STIL_KWH:
        return "ontladen"
    if accu_kwh <= -STIL_KWH:
        return "laden"
    return None


def laad_ontlaadrondes(reeks: list[dict]) -> list[dict]:
    """De aaneengesloten laad- en ontlaadrondes uit de kwartierreeks (v5.166.0).

    Een ronde = opeenvolgende kwartieren zonder gat (hooguit 16 min tussen
    twee kwartieren, als in `kwartierreeks`) die dezelfde kant op gaan
    (laden of ontladen, >= 50 W). Stilstand, een gat of omdraaien sluit de
    ronde. Kwartieren zonder SoC-stap tellen gewoon mee: over de hele ronde
    middelt de stap van 1 % uit. Per ronde: richting, kwartieren, AC-energie
    (|accu_kwh| opgeteld) en het inhoudsverschil (delta_kwh opgeteld).
    """
    rondes: list[dict] = []
    huidig = None
    vorig_moment = None
    for q in reeks:
        moment = _moment(str(q.get("dag")), str(q.get("tijd")))
        aansluitend = (
            moment is not None and vorig_moment is not None
            and timedelta(0) < moment - vorig_moment <= timedelta(minutes=16)
        )
        vorig_moment = moment
        richting = _richting(q["accu_kwh"])
        if huidig is not None and (not aansluitend or richting != huidig["richting"]):
            rondes.append(huidig)
            huidig = None
        if richting is None:
            continue
        if huidig is None:
            huidig = {"richting": richting, "kwartieren": 0, "ac_kwh": 0.0, "delta_kwh": 0.0}
        huidig["kwartieren"] += 1
        huidig["ac_kwh"] += abs(q["accu_kwh"])
        huidig["delta_kwh"] += q["delta_kwh"]
    if huidig is not None:
        rondes.append(huidig)
    return rondes


def _ronde_meting(r: dict) -> tuple[float, float] | None:
    """(teller, noemer) van een ronde, of None als hij niet meetelt."""
    ac, d = r["ac_kwh"], r["delta_kwh"]
    if ac < RONDE_MIN_KWH:
        return None
    if r["richting"] == "laden":
        teller, noemer = d, ac           # toename inhoud / wat erin ging
    else:
        teller, noemer = ac, -d          # wat eruit kwam / afname inhoud
    if teller <= 0 or noemer <= 0:
        return None
    if not BAND_RENDEMENT_MIN <= teller / noemer <= BAND_RENDEMENT_MAX + RONDE_RENDEMENT_SPELING:
        return None
    return teller, noemer


def rendement_per_band(reeks: list[dict]) -> dict:
    """Laad- en ontlaadrendement per vermogensband (punt 7, v5.166.0 per ronde).

    Laden: toename inhoud / wat er aan de netkant in ging. Ontladen: wat er
    aan de netkant uit kwam / afname inhoud.

    v5.166.0 (akkoord Ruud 02-11 21:49): over hele laad-/ontlaadrondes, niet
    meer per kwartier. Per kwartier telde een kwartier alleen mee als de
    SoC (stappen van 1 % = 115 Wh) bewoog; bij 240 W (60 Wh per kwartier)
    alleen de kwartieren MET stap, en dan 60 Wh tegen 115 Wh: ontladen onder
    500 W kwam op 68 % terwijl het gemeten ~100 % is. Nu per ronde
    (`laad_ontlaadrondes`): de ronde valt in de band van zijn gemiddelde
    vermogen (een lange ronde wordt niet opgeknipt: eenvoudig, en bij het
    huis dekken blijft het vermogen grotendeels in één band). De
    plausibiliteitstoets geldt per ronde. `kwartieren` telt de kwartieren
    van de meegetelde rondes, zodat de betrouwbaarheidseisen gelijk blijven.
    """
    som = {(r, b): [0, 0.0, 0.0] for r in ("laden", "ontladen") for b in range(len(BAND_NAMEN))}
    for r in laad_ontlaadrondes(reeks):
        meting = _ronde_meting(r)
        if meting is None:
            continue
        t = som[(r["richting"], _band(r["ac_kwh"] / (r["kwartieren"] / 4)))]
        t[0] += r["kwartieren"]
        t[1] += meting[0]
        t[2] += meting[1]
    uit: dict = {"laden": {}, "ontladen": {}}
    for (richting, b), (n, teller, noemer) in som.items():
        eta = min(BAND_RENDEMENT_MAX, teller / noemer) if noemer > 0 else None
        uit[richting][BAND_NAMEN[b]] = {
            "kwartieren": n,
            "kwh": round(noemer, 2),
            "rendement_procent": round(eta * 100, 1) if eta is not None else None,
            "betrouwbaar": n >= BAND_MIN_KWARTIEREN and noemer >= BAND_MIN_KWH and eta is not None,
        }
    return uit


def laadrendement_uit_banden(banden: dict | None) -> float | None:
    """Het laadrendement over alle betrouwbare laadbanden samen (v5.166.0).

    Gewogen naar de kWh die erin ging; None zolang geen enkele laadband
    betrouwbaar is.
    """
    teller = noemer = 0.0
    for b in ((banden or {}).get("laden") or {}).values():
        if b.get("betrouwbaar") and b.get("rendement_procent") and b.get("kwh"):
            teller += b["kwh"] * b["rendement_procent"] / 100
            noemer += b["kwh"]
    return teller / noemer if noemer > 0 else None


#: v5.167.0: het geleerde laad-/ontlaadrendement uit hele rondes vanaf zoveel
#: rondes en zoveel kWh aan de netkant per richting.
RONDES_MIN = 3
RONDES_MIN_KWH = 5.0


def rendement_over_rondes(reeks: list[dict]) -> dict:
    """Laad- en ontlaadrendement over ALLE hele rondes samen (v5.167.0, audit punt 3).

    Laden: som toename inhoud / som AC erin. Ontladen: som AC eruit / som
    afname inhoud. Per ronde dezelfde toets als de banden (`_ronde_meting`:
    tot BAND_RENDEMENT_MAX + RONDE_RENDEMENT_SPELING, dus ontladen mag per
    ronde tot 1,15 - de SoC-stap laat een ronde daar eerlijk overheen gaan);
    de uitkomst afgekapt op 1,0. Geen mediaan van losse stukken en geen
    weggooien boven 100 %: dat gaf ontladen 96 % tegen ~100 % op de meter.
    Per richting None tot RONDES_MIN rondes en RONDES_MIN_KWH.
    """
    som = {"laden": [0, 0.0, 0.0], "ontladen": [0, 0.0, 0.0]}
    for r in laad_ontlaadrondes(reeks):
        meting = _ronde_meting(r)
        if meting is None:
            continue
        t = som[r["richting"]]
        t[0] += 1
        t[1] += meting[0]
        t[2] += meting[1]
    uit = {}
    for richting, (n, teller, noemer) in som.items():
        ac = noemer if richting == "laden" else teller
        eta = min(BAND_RENDEMENT_MAX, teller / noemer) if noemer > 0 else None
        uit[richting] = {
            "rondes": n, "ac_kwh": round(ac, 2),
            "rendement": eta if (n >= RONDES_MIN and ac >= RONDES_MIN_KWH) else None,
            "rendement_procent": round(eta * 100, 1) if eta is not None else None,
        }
    return uit


def band_rendement(banden: dict | None, richting: str, vermogen_w: float | None, terugval: float) -> float:
    """Het rendement bij dit vermogen als die band betrouwbaar is, anders de terugval."""
    if not banden or vermogen_w is None:
        return terugval
    b = (banden.get(richting) or {}).get(BAND_NAMEN[_band(abs(vermogen_w) / 1000)]) or {}
    if b.get("betrouwbaar") and b.get("rendement_procent"):
        return b["rendement_procent"] / 100
    return terugval


def afweging_huis_of_verkopen(banden: dict | None, huis_w: float, verkoop_w: float, terugval: float) -> dict:
    """Het ontlaadrendement bij het huis dekken (laag vermogen) tegen verkopen
    (hoog vermogen): een kWh uit de cellen levert bij verkopen zoveel meer of
    minder op."""
    huis = band_rendement(banden, "ontladen", huis_w, terugval)
    verkoop = band_rendement(banden, "ontladen", verkoop_w, terugval)
    return {
        "huis_dekken_w": round(huis_w),
        "huis_dekken_rendement_procent": round(huis * 100, 1),
        "verkopen_w": round(verkoop_w),
        "verkopen_rendement_procent": round(verkoop * 100, 1),
        "verkopen_per_kwh_uit_de_cellen_procent": round((verkoop - huis) * 100, 1),
        "uit_de_meting": huis != terugval or verkoop != terugval,
    }
