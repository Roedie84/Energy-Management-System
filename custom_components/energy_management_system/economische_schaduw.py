"""Economische schaduw (v5.187.0): andere bewaarmarges naast productie, alleen meten.

Plan v5.187.0 (akkoord Ruud 05-11, fase 1 en 2). Elke schaduw (C2: bewaarmarge
2 ct, C0: 0 ct) krijgt een VIRTUELE accu. Per kwartier plant hij met dezelfde
invoer als productie (diepe kopie, alleen bewaarmarge en inhoud anders) en voert
de eerste planactie uit tegen de GEMETEN huislast en zon - hetzelfde
uitvoeringsmodel als de offline herspeling (19,09 tegen werkelijk 19,04 EUR
over 10 dagen). Productie wordt afgerekend met de echte meting (P1, accumeter)
en de echte inhoud.

Vergelijken alleen op geld: afname x inkoop - teruglevering x terug (de prijzen
waarmee het plan dat kwartier rekende, tijdens de saldering marginaal) +
slijtage per ontladen kWh, en per dag een voorraadcorrectie tegen één
gemeenschappelijke waarde per kWh inhoud.

Geen Home Assistant, geen dienstaanroepen: puur rekenen, zodat het zonder HA
te toetsen is. De lijm staat in `economische_schaduw_sturing.py`.
"""
from __future__ import annotations

import copy
import statistics
from dataclasses import dataclass

#: v5.187.0: de varianten (naam -> bewaarmarge EUR/kWh). Productie is de referentie.
VARIANTEN: dict[str, float] = {"c2": 0.02, "c0": 0.0}

#: v5.187.0: bewaartermijnen (plan sectie 4).
KWARTIER_DAGEN = 30
DAG_DAGEN = 90
#: Een dag telt mee in de evaluatie als minstens dit deel van de kwartieren klopt.
DAG_VOLLEDIG_FRACTIE = 0.9
#: Evaluatie over zoveel volledige dagen (plan sectie 8, fase 3/4).
EVALUATIE_DAGEN = 14
#: Gelijk binnen een halve cent per dag.
GELIJK_EUR = 0.005
#: Slijtage voor de gevoeligheidstoets (beslisregel 'positief bij 6 ct').
SLIJTAGE_TOETS_EUR = 0.06
KWARTIER_H = 0.25

#: Vaste kolomvolgorde van een kwartierregel (compact opgeslagen als lijst).
_PER_VARIANT = ("actie", "inh0", "inh1", "in", "uit", "imp", "exp")
KOLOMMEN: tuple = (
    "t", "status", "pin", "puit", "slijt", "huis_v", "zon_v", "huis_w", "zon_w",
    *(f"p_{v}" for v in _PER_VARIANT),
    *(f"{n}_{v}" for n in VARIANTEN for v in _PER_VARIANT),
    "p_reden", *(f"{n}_reden" for n in VARIANTEN),
    "midk",
)
_IDX = {k: i for i, k in enumerate(KOLOMMEN)}

#: Kolommen van een dag in het sensorattribuut (klein houden, < 4 kB).
DAG_KORT = ("date", "production_cost_eur", "c2_cost_eur", "c0_cost_eur", "zonder_accu_eur",
            "saving_c2_eur", "saving_c0_eur", "ems_besparing_eur", "ems_regret_eur",
            "kwartieren_ok", "kwartieren_totaal")


# --- de virtuele accu ----------------------------------------------------------

@dataclass
class VirtueleAccu:
    """Een accu op papier: inhoud boven de ondergrens, grenzen per kwartier."""

    inhoud_kwh: float
    capaciteit_kwh: float
    eta_l: float
    eta_o: float
    ontladen_kw: float          # slimme stand: huis dekken
    laden_slim_kw: float        # slimme stand: zon opslaan
    laden_kw: float             # handmatig netladen
    verkoop_kw: float           # handmatig verkopen

    def ruimte_ac(self) -> float:
        return max(0.0, self.capaciteit_kwh - self.inhoud_kwh) / max(self.eta_l, 1e-6)

    def leverbaar_ac(self) -> float:
        return max(0.0, self.inhoud_kwh) * self.eta_o


def uitvoeren(accu: VirtueleAccu, actie: str | None, accu_kwh: float, huis: float, zon: float) -> dict:
    """Een kwartier met `actie` tegen de gemeten huislast en zon (zoals replay.py).

    Werkt `accu.inhoud_kwh` bij; geeft laden/ontladen (AC), afname/teruglevering
    en de inhoud voor en na terug. Onbekende actie = de slimme stand ('huis').
    """
    d = float(huis) - float(zon)            # + tekort, - overschot
    h = KWARTIER_H
    inh0 = accu.inhoud_kwh
    lad = ont = 0.0
    if actie in ("laden_net",):
        lad = min(max(float(accu_kwh or 0.0), 0.0), accu.laden_kw * h, accu.ruimte_ac())
    elif actie == "verkopen":
        ont = min(max(-float(accu_kwh or 0.0), 0.0), accu.verkoop_kw * h, accu.leverbaar_ac())
    elif actie == "houden":
        if d < 0:
            lad = min(-d, accu.laden_slim_kw * h, accu.ruimte_ac())
    elif actie == "zon_export":
        pass
    else:   # huis, zon (en terugval)
        if d > 0:
            ont = min(d, accu.ontladen_kw * h, accu.leverbaar_ac())
        else:
            lad = min(-d, accu.laden_slim_kw * h, accu.ruimte_ac())
    inhoud = inh0 + lad * accu.eta_l - ont / max(accu.eta_o, 1e-6)
    accu.inhoud_kwh = max(0.0, min(accu.capaciteit_kwh, inhoud))
    net = d + lad - ont
    return {"actie": actie or "huis", "inh0": inh0, "inh1": accu.inhoud_kwh, "in": lad, "uit": ont,
            "imp": max(net, 0.0), "exp": max(-net, 0.0)}


def kosten(imp: float, exp: float, uit: float, pin: float, puit: float, slijt: float) -> float:
    """Kasstroom + slijtage van één kwartier (zelfde formule voor elke variant)."""
    return float(imp) * pin - float(exp) * puit + float(uit) * slijt


def zonder_accu(huis: float, zon: float, pin: float, puit: float) -> float:
    d = float(huis) - float(zon)
    return max(d, 0.0) * pin - max(-d, 0.0) * puit


def gepland_voor_kwartier(accu_kwh: float, uren: float | None) -> float:
    """De planstap van het (lopende) eerste kwartier naar een heel kwartier,
    zoals de sturing het vermogen over de rest van het kwartier inhaalt."""
    try:
        u = float(uren or KWARTIER_H)
    except (TypeError, ValueError):
        u = KWARTIER_H
    if u <= 0.01:
        return float(accu_kwh or 0.0)
    return float(accu_kwh or 0.0) * KWARTIER_H / min(u, KWARTIER_H)


# --- plannen (in de executor) --------------------------------------------------

def schaduwinvoer(kwartieren: list, accu, bewaarmarge: float, inhoud: float) -> tuple:
    """Diepe kopie van de productie-invoer; ALLEEN bewaarmarge en inhoud anders."""
    ks = copy.deepcopy(kwartieren)
    a = copy.deepcopy(accu)
    a.bewaarmarge_eur = float(bewaarmarge)
    a.inhoud_kwh = max(0.0, min(float(getattr(a, "bruikbaar_kwh", inhoud) or inhoud), float(inhoud)))
    return ks, a


def plan_varianten(plan_fn, kwartieren: list, accu, varianten: dict) -> dict:
    """Plant elke variant ({naam: (bewaarmarge, inhoud)}) op een eigen kopie.

    Uitkomst per naam: {"actie", "accu_kwh", "uren", "waarde"} of None (geen plan);
    fouten apart in "_fouten" (de lijm telt die via _bewaak_stap).
    """
    uit: dict = {"_fouten": {}}
    for naam, (marge, inhoud) in varianten.items():
        try:
            ks, a = schaduwinvoer(kwartieren, accu, marge, inhoud)
            res = plan_fn(ks, a)
            if not getattr(res, "beschikbaar", False) or not res.kwartieren:
                uit[naam] = None
                continue
            r0 = res.kwartieren[0]
            uit[naam] = {"actie": r0.get("actie"), "accu_kwh": float(r0.get("accu_kwh") or 0.0),
                         "uren": r0.get("uren"), "waarde": r0.get("waarde_inhoud_eur_per_kwh")}
        except Exception as fout:  # noqa: BLE001 - één variant mag de rest niet breken
            uit[naam] = None
            uit["_fouten"][naam] = f"{type(fout).__name__}: {fout}"
    return uit


# --- middenin het kwartier -----------------------------------------------------

def midkwartier_voordeel(plan: dict, oud: dict, waarde) -> float | None:
    """Zelfde schatting als `_midkwartier_voordeel_eur`, met een andere waarde per kWh."""
    nieuw, vorig = plan.get("nu") or {}, oud.get("nu") or {}
    uren_n, uren_o = float(nieuw.get("uren") or 0.0), float(vorig.get("uren") or 0.0)
    prijs = nieuw.get("rekenprijs_eur")
    if uren_n <= 0 or uren_o <= 0 or prijs is None or waarde is None:
        return None
    rest_oud = float(vorig.get("accu_kwh") or 0.0) * min(1.0, uren_n / uren_o)
    verschil = abs(float(nieuw.get("accu_kwh") or 0.0) - rest_oud)
    return verschil * abs(float(prijs) - float(waarde))


def midk_bij(midk: list | None, geweigerd: bool, v_eind, v_marg) -> list:
    """[geweigerd, toegestaan, max voordeel eindwaarde, max voordeel marginaal] bijwerken."""
    m = list(midk or [0, 0, None, None])
    m[0 if geweigerd else 1] += 1
    if geweigerd:
        if v_eind is not None:
            m[2] = round(max(float(v_eind), m[2] if m[2] is not None else float("-inf")), 4)
        if v_marg is not None:
            m[3] = round(max(float(v_marg), m[3] if m[3] is not None else float("-inf")), 4)
    return m


# --- het boek: kwartierregels, dagen, opslag ----------------------------------

def _r(x, n=4):
    return None if x is None else round(float(x), n)


def rij_als_lijst(rij: dict) -> list:
    uit = []
    for k in KOLOMMEN:
        v = rij.get(k)
        uit.append(_r(v) if isinstance(v, float) else v)
    return uit


def rij_als_dict(rij: list) -> dict:
    return {k: (rij[i] if i < len(rij) else None) for i, k in enumerate(KOLOMMEN)}


def _som(rijen: list, kolom: str) -> float:
    i = _IDX[kolom]
    return sum(float(r[i] or 0.0) for r in rijen)


def _variantkosten(rijen: list, pre: str, slijt_vast: float | None = None) -> tuple:
    """(kas, slijtage, voorraadverschil, ontladen) van een variant over de rijen."""
    kas = slijt = dvoorraad = uit = 0.0
    for r in rijen:
        d = rij_als_dict(r)
        pin, puit = float(d["pin"] or 0.0), float(d["puit"] or 0.0)
        s = float(d["slijt"] or 0.0) if slijt_vast is None else slijt_vast
        kas += float(d[f"{pre}_imp"] or 0.0) * pin - float(d[f"{pre}_exp"] or 0.0) * puit
        slijt += float(d[f"{pre}_uit"] or 0.0) * s
        dvoorraad += float(d[f"{pre}_inh1"] or 0.0) - float(d[f"{pre}_inh0"] or 0.0)
        uit += float(d[f"{pre}_uit"] or 0.0)
    return kas, slijt, dvoorraad, uit


def _wissels(acties: list) -> int:
    return sum(1 for a, b in zip(acties, acties[1:]) if a != b)


def gemeenschappelijke_waarde(waarde, rijen: list, eta_o: float) -> tuple:
    """(EUR/kWh, bron): de eindwaarde van het eerste productieplan van de dag,
    anders mediaan inkoop x eta_o - slijtage."""
    if waarde is not None:
        return float(waarde), "eindwaarde productieplan"
    prijzen = [float(rij_als_dict(r)["pin"]) for r in rijen if rij_als_dict(r)["pin"] is not None]
    slijt = [float(rij_als_dict(r)["slijt"]) for r in rijen if rij_als_dict(r)["slijt"] is not None]
    if not prijzen:
        return 0.0, "geen prijzen"
    s = statistics.median(slijt) if slijt else 0.0
    return max(0.0, statistics.median(prijzen) * eta_o - s), "mediaan inkoop x rendement - slijtage"


def dagsamenvatting(dag: str, rijen: list, waarde, eta_o: float, cap: float, kwartieren_dag: int = 96) -> dict:
    """De dagregel uit de kwartierregels van die dag (plan sectie 4).

    Alleen kwartieren met status ok tellen; het voorraadverschil is de som over
    die kwartieren, zodat een ongemeten kwartier geen geld en geen voorraad telt.
    """
    ok = [r for r in rijen if r[_IDX["status"]] == "ok"]
    w, bron = gemeenschappelijke_waarde(waarde, ok, eta_o)
    uit: dict = {"date": dag, "waarde_inhoud": round(w, 4), "waarde_bron": bron,
                 "kwartieren_ok": len(ok), "kwartieren_totaal": len(rijen), "kwartieren_dag": kwartieren_dag}
    kost: dict = {}
    for pre, naam in (("p", "production"), *((n, n) for n in VARIANTEN)):
        kas, slijt, dv, ontl = _variantkosten(ok, pre)
        kas6, slijt6, _dv, _o = _variantkosten(ok, pre, SLIJTAGE_TOETS_EUR)
        kost[pre] = kas + slijt - dv * w
        uit[f"{naam}_cost_eur"] = round(kost[pre], 4)
        uit[f"{naam}_cost_6ct_eur"] = round(kas6 + slijt6 - dv * w, 4)
        uit[f"{naam}_kas_eur"] = round(kas, 4)
        uit[f"{naam}_slijtage_eur"] = round(slijt, 4)
        uit[f"{naam}_voorraad_kwh"] = round(dv, 3)
        uit[f"{naam}_ontladen_kwh"] = round(ontl, 3)
        uit[f"{naam}_cycles"] = round(ontl / cap, 3) if cap else None
        uit[f"{naam}_switches"] = _wissels([r[_IDX[f"{pre}_actie"]] for r in ok])
    niets = sum(
        zonder_accu(r[_IDX["huis_w"]] or 0.0, r[_IDX["zon_w"]] or 0.0, r[_IDX["pin"]] or 0.0, r[_IDX["puit"]] or 0.0)
        for r in ok)
    uit["zonder_accu_eur"] = round(niets, 4)
    for n in VARIANTEN:
        uit[f"saving_{n}_eur"] = round(kost["p"] - kost[n], 4)
        verschil = [r for r in ok if r[_IDX[f"{n}_actie"]] != r[_IDX["p_actie"]]]
        uit[f"different_actions_{n}_pct"] = round(100.0 * len(verschil) / len(ok), 1) if ok else None
        deltas = []
        for r in ok:
            d = rij_als_dict(r)
            kv = kosten(d[f"{n}_imp"] or 0, d[f"{n}_exp"] or 0, d[f"{n}_uit"] or 0, d["pin"] or 0, d["puit"] or 0, d["slijt"] or 0)
            kp = kosten(d["p_imp"] or 0, d["p_exp"] or 0, d["p_uit"] or 0, d["pin"] or 0, d["puit"] or 0, d["slijt"] or 0)
            deltas.append(kv - kp)
        uit[f"worst_quarter_{n}_delta_eur"] = round(max(deltas), 4) if deltas else None
        soc = [abs(float(r[_IDX[f"{n}_inh1"]] or 0) - float(r[_IDX["p_inh1"]] or 0)) for r in ok]
        uit[f"max_soc_delta_{n}_kwh"] = round(max(soc), 3) if soc else None
    besparing = niets - kost["p"]
    uit["ems_besparing_eur"] = round(besparing, 4)
    uit["ems_regret_eur"] = round(kost["p"] - min(kost[n] for n in VARIANTEN), 4)
    midk = [r[_IDX["midk"]] for r in rijen if r[_IDX["midk"]]]
    uit["midk_geweigerd"] = sum(int(m[0] or 0) for m in midk)
    uit["midk_toegestaan"] = sum(int(m[1] or 0) for m in midk)
    ve = [m[2] for m in midk if m[2] is not None]
    vm = [m[3] for m in midk if m[3] is not None]
    uit["midk_max_voordeel_eind_eur"] = round(max(ve), 4) if ve else None
    uit["midk_max_voordeel_marg_eur"] = round(max(vm), 4) if vm else None
    uit["volledig"] = len(ok) >= DAG_VOLLEDIG_FRACTIE * kwartieren_dag
    return uit


# --- evaluatie ----------------------------------------------------------------

def evalueer(dagen: list[dict], variant: str = "c2", aantal: int = EVALUATIE_DAGEN) -> dict:
    """De beslisregels (plan sectie 7, aangepast) over de laatste `aantal` volledige dagen.

    Alle vergelijkingen met voorraadcorrectie. 'te weinig dagen' tot er genoeg zijn.
    """
    volledig = [d for d in dagen if d.get("volledig")][-aantal:]
    uit: dict = {"variant": variant, "dagen": len(volledig), "nodig": aantal}
    if len(volledig) < aantal:
        uit.update(status="te weinig dagen", advies=f"te weinig dagen ({len(volledig)} van {aantal})", regels={})
        return uit
    sav = [float(d[f"saving_{variant}_eur"]) for d in volledig]
    totaal = sum(sav)
    sw_p = sum(int(d["production_switches"]) for d in volledig)
    sw_v = sum(int(d[f"{variant}_switches"]) for d in volledig)
    cy_p = sum(float(d["production_cycles"] or 0) for d in volledig)
    cy_v = sum(float(d[f"{variant}_cycles"] or 0) for d in volledig)
    zes = sum(float(d["production_cost_6ct_eur"]) - float(d[f"{variant}_cost_6ct_eur"]) for d in volledig)
    gelijk_of_beter = sum(1 for s in sav if s >= -GELIJK_EUR)
    regels = {
        "totaal_beter": (totaal > 0, round(totaal, 2)),
        "geen_dag_meer_dan_0_25_slechter": (min(sav) >= -0.25, round(min(sav), 2)),
        "minstens_9_van_14_gelijk_of_beter": (gelijk_of_beter >= round(aantal * 9 / 14), gelijk_of_beter),
        "wisselingen_max_plus_10_pct": (sw_v <= 1.10 * sw_p, f"{sw_v} tegen {sw_p}"),
        "cycli_max_plus_10_pct": (cy_v <= 1.10 * cy_p + 1e-9, f"{cy_v:.2f} tegen {cy_p:.2f}"),
        "positief_bij_6_ct_slijtage": (zes > 0, round(zes, 2)),
        "niet_vooral_een_dag": (totaal > 0 and max(sav) < 0.5 * totaal, round(max(sav), 2)),
    }
    uit["regels"] = {k: {"gehaald": bool(ok), "waarde": w} for k, (ok, w) in regels.items()}
    gezakt = [k for k, (ok, _w) in regels.items() if not ok]
    uit["besparing_eur"] = round(totaal, 2)
    if gezakt:
        uit.update(status="afgewezen", advies=f"{variant.upper()} niet invoeren: niet gehaald: " + ", ".join(gezakt))
    else:
        uit.update(status="geschikt", advies=f"{variant.upper()} kan worden voorgesteld: alle beslisregels "
                                             f"gehaald, besparing EUR {totaal:.2f} over {aantal} dagen")
    return uit


def rollend(dagen: list[dict], aantal: int) -> dict:
    """Som over de laatste `aantal` dagen (alleen volledige dagen)."""
    sel = [d for d in dagen if d.get("volledig")][-aantal:]
    uit = {"dagen": len(sel)}
    for veld in ("ems_besparing_eur", "ems_regret_eur", *(f"saving_{n}_eur" for n in VARIANTEN),
                 "production_cost_eur", "zonder_accu_eur"):
        uit[veld] = round(sum(float(d.get(veld) or 0.0) for d in sel), 2)
    return uit


class Schaduwboek:
    """Kwartierregels, dagregels, virtuele inhoud en de open dag (één Store)."""

    VERSIE = 1

    def __init__(self, data: dict | None = None) -> None:
        data = data if isinstance(data, dict) and data.get("versie") == self.VERSIE else {}
        self.rijen: list = list(data.get("rijen") or [])
        self.dagen: list = list(data.get("dagen") or [])
        self.virtueel: dict = {n: data.get("virtueel", {}).get(n) for n in VARIANTEN}
        self.open_dag: dict | None = data.get("open_dag")
        self.waarden: dict = dict(data.get("waarden") or {})
        self.gestart: str | None = data.get("gestart")
        if list(data.get("kolommen") or KOLOMMEN) != list(KOLOMMEN):
            self.rijen = []   # andere kolommen: oude regels niet verkeerd lezen

    def naar_opslag(self) -> dict:
        return {"versie": self.VERSIE, "kolommen": list(KOLOMMEN), "rijen": self.rijen, "dagen": self.dagen,
                "virtueel": self.virtueel, "open_dag": self.open_dag, "waarden": self.waarden,
                "gestart": self.gestart}

    def resync(self, inhoud: float, wanneer: str | None = None) -> None:
        for n in VARIANTEN:
            self.virtueel[n] = max(0.0, float(inhoud))
        if wanneer:
            self.gestart = self.gestart or wanneer

    def zet_waarde(self, dag: str, waarde) -> None:
        if waarde is not None and dag not in self.waarden:
            self.waarden[dag] = round(float(waarde), 4)

    def voeg_rij_toe(self, rij: dict) -> None:
        self.rijen.append(rij_als_lijst(rij))

    def open(self, dag: str, t0: float) -> None:
        self.open_dag = {"dag": dag, "t0": t0}

    def sluit_dag(self, t1: float, eta_o: float, cap: float) -> dict | None:
        """Sluit de open dag (kwartieren t0 <= t < t1) en zet de dagregel erbij."""
        if not self.open_dag:
            return None
        dag, t0 = self.open_dag["dag"], float(self.open_dag["t0"])
        rijen = [r for r in self.rijen if t0 <= float(r[0]) < t1]
        self.open_dag = None
        if not rijen:
            return None
        n = max(1, int(round((t1 - t0) / 900)))
        regel = dagsamenvatting(dag, rijen, self.waarden.get(dag), eta_o, cap, n)
        self.dagen = [d for d in self.dagen if d.get("date") != dag] + [regel]
        return regel

    def opschonen(self, nu: float) -> None:
        grens = nu - KWARTIER_DAGEN * 86400
        self.rijen = [r for r in self.rijen if float(r[0]) >= grens]
        self.dagen = self.dagen[-DAG_DAGEN:]
        bewaar = {d.get("date") for d in self.dagen} | ({self.open_dag["dag"]} if self.open_dag else set())
        laatste = sorted(self.waarden)[-3:]
        self.waarden = {k: v for k, v in self.waarden.items() if k in bewaar or k in laatste}

    def open_rijen(self) -> list:
        if not self.open_dag:
            return []
        t0 = float(self.open_dag["t0"])
        return [r for r in self.rijen if float(r[0]) >= t0]

    def samenvatting(self) -> dict:
        """Klein (< 4 kB): laatste 14 dagen kort, totalen, evaluatie."""
        laatste = self.dagen[-EVALUATIE_DAGEN:]
        evaluatie = {n: evalueer(self.dagen, n) for n in VARIANTEN}
        for e in evaluatie.values():
            e.pop("nodig", None)
        return {
            "dagen_kolommen": list(DAG_KORT),
            "dagen": [[d.get(k) for k in DAG_KORT] for d in laatste],
            "rollend": {f"{n}_dagen": rollend(self.dagen, n) for n in (7, 14, 30, 90)},
            "evaluatie": evaluatie,
            "virtueel_kwh": {n: _r(v, 2) for n, v in self.virtueel.items()},
            "open_dag": {"dag": (self.open_dag or {}).get("dag"),
                         "kwartieren": len(self.open_rijen())},
            "gestart": self.gestart,
        }

    def besparing_c2_14d(self):
        sel = [d for d in self.dagen if d.get("volledig")][-EVALUATIE_DAGEN:]
        if not sel:
            return None
        return round(sum(float(d.get("saving_c2_eur") or 0.0) for d in sel), 2)
