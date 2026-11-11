"""Jaarafrekening (v5.188.0): betaald tegenover werkelijk, en wat de afrekening wordt.

Gevraagd (Ruud 05-11-2026): "Ik betaal Zonneplan nu maandelijks 70 euro, hoeveel
ik nog over heb t.o.v. verwachte jaarrekening etc." Contractjaar Zonneplan begint
op 1 april; de termijn wordt rond de 25e afgeschreven; gas valt tot 22-11-2026
onder Zonneplan en gaat daarna naar een andere leverancier (vaste prijs).

Werkelijk tot nu = afname min teruglevering (de dagkosten van de leverancier, dus
met saldering zoals hij rekent) + gas tot de overstap + vaste kosten (vastrecht
levering, netbeheer) min de vermindering energiebelasting, alles naar rato per dag.

De rest van het contractjaar is een schatting: elke resterende dag krijgt het
verbruik en de opbrengst van dezelfde dag een jaar eerder. Na het einde van de
saldering levert een teruggeleverde kWh het tarief van toen min de
energiebelasting (incl. btw) op. De bandbreedte is een kwart van het variabele
deel van die schatting.

Zuivere functies, zonder Home Assistant. Dagwaarden komen binnen als
{date: {"afname_eur", "terug_eur", "gas_eur", "gas_m3", "afname_kwh", "terug_kwh"}}.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

VELDEN = ("afname_eur", "terug_eur", "gas_eur", "gas_m3", "afname_kwh", "terug_kwh")
#: Energiebelasting stroom 2026 incl. btw (EUR/kWh); na de saldering levert
#: een teruggeleverde kWh dit niet meer op.
EB_STROOM_INCL_EUR = 0.11085
#: Bandbreedte: dit deel van het variabele deel van de schatting.
BAND_DEEL = 0.25
#: v5.220.0: de schatting van de rest van het jaar rekent met het prijsniveau
#: van nu. Per drager: prijs per eenheid over de laatste dagen, gedeeld door
#: die van dezelfde dagen vorig jaar. Zonder genoeg dagparen: factor 1.
PRIJSNIVEAU_DAGEN = 30
PRIJSNIVEAU_MIN_DAGEN = 14
PRIJSNIVEAU_MIN = 0.5
PRIJSNIVEAU_MAX = 3.0
_NIVEAU_DRAGERS = (("afname", "afname_eur", "afname_kwh"), ("terug", "terug_eur", "terug_kwh"), ("gas", "gas_eur", "gas_m3"))
MAANDEN = ("jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec")


@dataclass
class Instellingen:
    termijn_eur: float = 70.0
    afschrijfdag: int = 25
    vastrecht_stroom_mnd: float = 6.25
    vastrecht_gas_mnd: float = 6.25
    netbeheer_stroom_jaar: float = 478.0
    netbeheer_gas_jaar: float = 267.0
    vermindering_eb_jaar: float = 628.96
    saldering_eind: date | None = None      # laatste dag met saldering
    gas_overstap: date | None = None        # eerste dag bij de nieuwe gasleverancier
    gas_nieuw_prijs_m3: float | None = None
    gas_nieuw_vastrecht_mnd: float = 8.33
    gas_nieuw_korting_jaar: float = 210.0
    gas_nieuw_termijn_eur: float | None = None


def _dag_in_jaar(dag: date, jaar: int) -> date:
    try:
        return dag.replace(year=jaar)
    except ValueError:
        return dag.replace(year=jaar, day=28)


def contractjaar(start: date, vandaag: date) -> tuple[date, date]:
    """Begin en laatste dag van het lopende contractjaar."""
    begin = _dag_in_jaar(start, vandaag.year)
    if begin > vandaag:
        begin = _dag_in_jaar(start, vandaag.year - 1)
    eind = _dag_in_jaar(begin, begin.year + 1) - timedelta(days=1)
    return begin, eind


def _maand_plus(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def afschrijfdatums(begin: date, dag: int) -> list[date]:
    """De twaalf afschrijvingen van het contractjaar (dag begrensd op de maandlengte)."""
    uit = []
    for i in range(12):
        eerste = _maand_plus(begin, i)
        volgende = _maand_plus(begin, i + 1)
        laatste = (volgende - timedelta(days=1)).day
        uit.append(eerste.replace(day=max(1, min(dag, laatste))))
    return uit


def _vast_per_dag(inst: Instellingen, dag: date) -> tuple[float, float]:
    """(vaste kosten levering + netbeheer, vermindering EB) voor één dag."""
    stroom = (inst.vastrecht_stroom_mnd * 12 + inst.netbeheer_stroom_jaar) / 365.0
    gas = 0.0
    if inst.gas_overstap is None or dag < inst.gas_overstap:
        gas = (inst.vastrecht_gas_mnd * 12 + inst.netbeheer_gas_jaar) / 365.0
    return stroom + gas, inst.vermindering_eb_jaar / 365.0


def vaste_kosten_dag(inst: Instellingen, dag: date) -> dict:
    """v5.203.0: de vaste kosten van één dag, per drager (EUR).

    Ruud 09-11: "Waarom tellen vaste kosten niet mee? Ik moet toch een
    totaal plaatje hebben voor zowel tablet en cockpit voor gas en elektra."
    Stroom: vastrecht + netbeheer min de vermindering energiebelasting (die
    staat op de stroomrekening). Gas: vastrecht + netbeheer; vanaf de
    overstap het vastrecht van de nieuwe leverancier min zijn korting.
    """
    stroom_vast = (inst.vastrecht_stroom_mnd * 12 + inst.netbeheer_stroom_jaar) / 365.0
    eb = inst.vermindering_eb_jaar / 365.0
    if inst.gas_overstap is not None and dag >= inst.gas_overstap:
        gas = (inst.gas_nieuw_vastrecht_mnd * 12 + inst.netbeheer_gas_jaar - inst.gas_nieuw_korting_jaar) / 365.0
    else:
        gas = (inst.vastrecht_gas_mnd * 12 + inst.netbeheer_gas_jaar) / 365.0
    return {
        "stroom_vastrecht_netbeheer_eur": stroom_vast,
        "eb_vermindering_eur": eb,
        "stroom_eur": stroom_vast - eb,
        "gas_eur": gas,
    }


def kosten_vandaag(*, afname_eur, terug_eur, gas_eur, vast: dict) -> dict:
    """v5.203.0: stroom, gas en totaal van vandaag, variabel + vast (EUR).
    Een ontbrekende variabele waarde maakt dat deel (en het totaal) None."""
    stroom_var = None if afname_eur is None else afname_eur - (terug_eur or 0.0)
    stroom = None if stroom_var is None else stroom_var + vast["stroom_eur"]
    gas = None if gas_eur is None else gas_eur + vast["gas_eur"]
    totaal = None if stroom is None or gas is None else stroom + gas
    r = lambda v: None if v is None else round(v, 2)  # noqa: E731
    return {
        "stroom_eur": r(stroom), "gas_eur": r(gas), "totaal_eur": r(totaal),
        "stroom_variabel_eur": r(stroom_var), "stroom_vast_eur": r(vast["stroom_eur"]),
        "stroom_vastrecht_netbeheer_eur": r(vast["stroom_vastrecht_netbeheer_eur"]),
        "eb_vermindering_eur": r(vast["eb_vermindering_eur"]),
        "gas_variabel_eur": r(gas_eur), "gas_vast_eur": r(vast["gas_eur"]),
        "afname_eur": r(afname_eur), "teruglevering_eur": r(terug_eur),
    }


def prijsniveau(dagen: dict, tot: date) -> dict:
    """Hoe duur is het nu tegenover dezelfde dagen vorig jaar? (v5.220.0)

    De schatting nam de eurobedragen van vorig jaar over, en daarmee de
    prijzen van vorig jaar: op 11-11-2026 rekende ze de rest van het jaar met
    EUR 1,22 per m3 gas (nu 1,80) en 23 ct per kWh stroom (afgelopen week
    53 ct). Het verbruik van vorig jaar blijft de basis; de bedragen gaan
    naar het prijsniveau van de laatste PRIJSNIVEAU_DAGEN dagen. Alleen
    dagparen waarin beide jaren verbruik hadden tellen; bij minder dan
    PRIJSNIVEAU_MIN_DAGEN paren blijft de factor 1 (zoals voorheen).
    """
    uit = {}
    for naam, veld_eur, veld_vol in _NIVEAU_DRAGERS:
        nu_eur = nu_vol = oud_eur = oud_vol = 0.0
        paren = 0
        for i in range(PRIJSNIVEAU_DAGEN):
            dag = tot - timedelta(days=i)
            nu, oud = dagen.get(dag), dagen.get(_dag_in_jaar(dag, dag.year - 1))
            if not nu or not oud:
                continue
            try:
                a_vol, b_vol = float(nu.get(veld_vol) or 0.0), float(oud.get(veld_vol) or 0.0)
                a_eur, b_eur = float(nu.get(veld_eur) or 0.0), float(oud.get(veld_eur) or 0.0)
            except (TypeError, ValueError):
                continue
            if a_vol <= 0 or b_vol <= 0 or a_eur <= 0 or b_eur <= 0:
                continue
            paren += 1
            nu_eur, nu_vol, oud_eur, oud_vol = nu_eur + a_eur, nu_vol + a_vol, oud_eur + b_eur, oud_vol + b_vol
        rij = {"factor": 1.0, "dagen": paren, "toegepast": False}
        if paren >= PRIJSNIVEAU_MIN_DAGEN and nu_vol > 0 and oud_vol > 0:
            prijs_nu, prijs_oud = nu_eur / nu_vol, oud_eur / oud_vol
            if prijs_oud > 0:
                rij.update({
                    "factor": round(min(PRIJSNIVEAU_MAX, max(PRIJSNIVEAU_MIN, prijs_nu / prijs_oud)), 3),
                    "toegepast": True,
                    "nu_per_eenheid": round(prijs_nu, 4),
                    "vorig_jaar_per_eenheid": round(prijs_oud, 4),
                })
        uit[naam] = rij
    return uit


def _dagkosten(w: dict, dag: date, inst: Instellingen, schatting: bool, niveau: dict | None = None) -> dict:
    """De variabele kosten van één dag; bij een schatting met de regels van die dag
    en (v5.220.0) het prijsniveau van nu."""
    afname = float(w.get("afname_eur") or 0.0)
    terug = float(w.get("terug_eur") or 0.0)
    gas_factor = 1.0
    if schatting and niveau:
        afname *= float((niveau.get("afname") or {}).get("factor") or 1.0)
        terug *= float((niveau.get("terug") or {}).get("factor") or 1.0)
        gas_factor = float((niveau.get("gas") or {}).get("factor") or 1.0)
    if schatting and inst.saldering_eind is not None and dag > inst.saldering_eind:
        terug = max(0.0, terug - float(w.get("terug_kwh") or 0.0) * EB_STROOM_INCL_EUR)
    gas = float(w.get("gas_eur") or 0.0) * gas_factor
    m3 = float(w.get("gas_m3") or 0.0)
    if inst.gas_overstap is not None and dag >= inst.gas_overstap:
        gas, m3 = 0.0, 0.0
    return {"afname_eur": afname, "terug_eur": terug, "gas_eur": gas, "gas_m3": m3,
            "afname_kwh": float(w.get("afname_kwh") or 0.0), "terug_kwh": float(w.get("terug_kwh") or 0.0)}


def _leeg() -> dict:
    return {"afname_eur": 0.0, "terug_eur": 0.0, "gas_eur": 0.0, "gas_m3": 0.0,
            "afname_kwh": 0.0, "terug_kwh": 0.0, "vast_eur": 0.0, "eb_eur": 0.0}


def _tel(som: dict, k: dict, vast: float, eb: float) -> None:
    for v in VELDEN:
        som[v] += k[v]
    som["vast_eur"] += vast
    som["eb_eur"] += eb


def _netto(s: dict) -> float:
    return s["afname_eur"] - s["terug_eur"] + s["gas_eur"] + s["vast_eur"] - s["eb_eur"]


def _loop(dagen: dict, inst: Instellingen, begin: date, eind: date, tot: date, niveau: dict | None = None):
    """Loopt het contractjaar door: werkelijk t/m `tot`, daarna de schatting.

    Geeft (werkelijk, schatting, per maand netto, ontbrekende vorigjaardagen)."""
    werkelijk, schatting = _leeg(), _leeg()
    maand_netto: dict[tuple[int, int], float] = {}
    ontbreekt = 0
    dag = begin
    while dag <= eind:
        vast, eb = _vast_per_dag(inst, dag)
        if dag <= tot:
            k = _dagkosten(dagen.get(dag) or {}, dag, inst, False)
            _tel(werkelijk, k, vast, eb)
        else:
            vorig = dagen.get(_dag_in_jaar(dag, dag.year - 1))
            if vorig is None:
                ontbreekt += 1
            k = _dagkosten(vorig or {}, dag, inst, True, niveau)
            _tel(schatting, k, vast, eb)
        sleutel = (dag.year, dag.month)
        maand_netto[sleutel] = maand_netto.get(sleutel, 0.0) + (
            k["afname_eur"] - k["terug_eur"] + k["gas_eur"] + vast - eb)
        dag += timedelta(days=1)
    return werkelijk, schatting, maand_netto, ontbreekt


def _reeks(begin: date, tot: date, inst: Instellingen, maand_netto: dict, afschrijvingen: list[date]) -> list[dict]:
    """Twaalf maanden cumulatief: betaald, werkelijk en verwacht."""
    rijen, betaald, kosten = [], 0.0, 0.0
    for i, afschrijf in enumerate(afschrijvingen):
        eerste = _maand_plus(begin, i)
        betaald += inst.termijn_eur
        kosten += maand_netto.get((eerste.year, eerste.month), 0.0)
        rijen.append({
            "maand": MAANDEN[eerste.month - 1],
            "betaald_cum": round(betaald, 2),
            "kosten_cum": round(kosten, 2),
            "betaald_echt": afschrijf <= tot,
            "kosten_echt": _maand_plus(begin, i + 1) - timedelta(days=1) <= tot,
        })
    return rijen


def _termijnadvies(inst: Instellingen, verwacht_kosten: float, betaald: float, resterend: int) -> dict:
    if resterend <= 0:
        return {"resterende_termijnen": 0, "advies_termijn_eur": None}
    nodig = (verwacht_kosten - betaald) / resterend
    advies = max(0.0, math.ceil(nodig / 5.0) * 5.0)
    return {"resterende_termijnen": resterend, "advies_termijn_eur": advies, "nodig_per_termijn_eur": round(nodig, 2)}


def gas_nieuw(dagen: dict, vandaag: date, inst: Instellingen) -> dict | None:
    """Verwachte jaarkosten bij de nieuwe gasleverancier (verbruik: de laatste 365 dagen)."""
    if inst.gas_overstap is None or inst.gas_nieuw_prijs_m3 is None:
        return None
    m3 = sum(float((dagen.get(vandaag - timedelta(days=i)) or {}).get("gas_m3") or 0.0) for i in range(1, 366))
    if m3 <= 0:
        return None
    jaar = (m3 * inst.gas_nieuw_prijs_m3 + inst.gas_nieuw_vastrecht_mnd * 12
            + inst.netbeheer_gas_jaar - inst.gas_nieuw_korting_jaar)
    uit = {"vanaf": inst.gas_overstap.isoformat(), "m3_per_jaar": round(m3, 1), "prijs_m3": inst.gas_nieuw_prijs_m3,
           "kosten_jaar_eur": round(jaar, 2), "per_maand_eur": round(jaar / 12.0, 2),
           "termijn_eur": inst.gas_nieuw_termijn_eur}
    if inst.gas_nieuw_termijn_eur is not None:
        uit["verschil_per_maand_eur"] = round(inst.gas_nieuw_termijn_eur - jaar / 12.0, 2)
    return uit


def bereken(dagen: dict, start: date, vandaag: date, inst: Instellingen) -> dict:
    """De hele kaart: stand nu, verwachte afrekening, opbouw, maandreeks en advies."""
    begin, eind = contractjaar(start, vandaag)
    tot = vandaag - timedelta(days=1)          # vandaag is nog niet af
    niveau = prijsniveau(dagen, tot)
    werkelijk, schatting, maand_netto, ontbreekt = _loop(dagen, inst, begin, eind, tot, niveau)
    afschrijvingen = afschrijfdatums(begin, inst.afschrijfdag)
    n_betaald = sum(1 for d in afschrijvingen if d <= vandaag)
    betaald = n_betaald * inst.termijn_eur
    kosten_nu = _netto(werkelijk)
    rest = _netto(schatting)
    verwacht = kosten_nu + rest
    band = BAND_DEEL * abs(schatting["afname_eur"] + schatting["gas_eur"] - schatting["terug_eur"])
    saldo = 12 * inst.termijn_eur - verwacht      # + = terug
    volgende = next((d for d in afschrijvingen if d > vandaag), None)
    return {
        "contractjaar_begin": begin.isoformat(),
        "contractjaar_eind": eind.isoformat(),
        "maand_nr": (vandaag.year - begin.year) * 12 + vandaag.month - begin.month + 1,
        "dag_aandeel": round(((vandaag - begin).days + 1) / ((eind - begin).days + 1), 3),
        "termijn_eur": inst.termijn_eur,
        "termijnen_betaald": n_betaald,
        "volgende_afschrijving": volgende.isoformat() if volgende else None,
        "betaald_eur": round(betaald, 2),
        "werkelijk_eur": round(kosten_nu, 2),
        "stand_eur": round(betaald - kosten_nu, 2),
        "verwacht_kosten_eur": round(verwacht, 2),
        "verwacht_saldo_eur": round(saldo, 2),
        "band_laag_eur": round(saldo - band, 2),
        "band_hoog_eur": round(saldo + band, 2),
        "opbouw": {k: round(v, 2) for k, v in werkelijk.items()},
        "schatting_rest": {k: round(v, 2) for k, v in schatting.items()},
        "maanden": _reeks(begin, tot, inst, maand_netto, afschrijvingen),
        "advies": _termijnadvies(inst, verwacht, betaald, 12 - n_betaald),
        "gas_nieuw": gas_nieuw(dagen, vandaag, inst),
        "saldering_eind": inst.saldering_eind.isoformat() if inst.saldering_eind else None,
        "gas_overstap": inst.gas_overstap.isoformat() if inst.gas_overstap else None,
        "vorig_jaar_ontbreekt_dagen": ontbreekt,
        # v5.220.0: waarmee de bedragen van vorig jaar zijn omgerekend
        "prijsniveau": niveau,
        "aannames": {
            "vastrecht_stroom_mnd": inst.vastrecht_stroom_mnd, "vastrecht_gas_mnd": inst.vastrecht_gas_mnd,
            "netbeheer_stroom_jaar": inst.netbeheer_stroom_jaar, "netbeheer_gas_jaar": inst.netbeheer_gas_jaar,
            "vermindering_eb_jaar": inst.vermindering_eb_jaar, "eb_stroom_incl": EB_STROOM_INCL_EUR,
        },
    }
