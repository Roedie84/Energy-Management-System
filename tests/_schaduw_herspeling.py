"""Herspeling van gemeten kwartieren voor de economische schaduw (v5.187.0, plantoets 1).

Zelfde aannames als de gevalideerde offline herspeling (scratchpad eco/replay.py):
marginale prijs = prijs - 0,1108, terug = +0,02, eta_l 0,914, eta_o 0,919, cap 7,8,
verbruik = 7-daags kwartierprofiel, zon = 3-daags profiel, day-ahead vanaf 13:00,
eindprijs = p75 van de echte prijzen na de horizon. Alleen het uitvoeren en afrekenen
loopt hier via `economische_schaduw` (de productiecode die getoetst wordt).
Hoort NIET in de productiecode.
"""
from __future__ import annotations

import collections
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from custom_components.energy_management_system import economische_schaduw as es
from custom_components.energy_management_system import waardeplan as W

FIXTURE = Path(__file__).parent / "fixtures" / "kwartieren_2610_0411.json"
TZ = timezone(timedelta(hours=1))
BELASTING, PREMIE, CAP = 0.1108, 0.02, 7.8
ETA_L, ETA_O, SLIJT = 0.914, 0.919, 0.0422
HORIZON_Q, PUBLICATIE_UUR = 144, 13


def laad():
    rows = json.loads(FIXTURE.read_text())
    for r in rows:
        r["dt"] = datetime.fromtimestamp(r["t"], timezone.utc)
    return rows


def inkoop(p):
    return p - BELASTING


def terug(p):
    return p - BELASTING + PREMIE


def _q(dt):
    loc = dt.astimezone(TZ)
    return loc.hour * 4 + loc.minute // 15


def _profiel(rows, i, dagen, veld):
    som, n = collections.defaultdict(float), collections.defaultdict(int)
    for j in range(max(0, i - dagen * 96), i):
        q = _q(rows[j]["dt"])
        som[q] += rows[j][veld]
        n[q] += 1
    return {q: som[q] / n[q] for q in som}


def _bekend_tot(t):
    loc = t.astimezone(TZ)
    eind = (loc + timedelta(days=1 if loc.hour >= PUBLICATIE_UUR else 0)).replace(hour=0, minute=0) + timedelta(days=1)
    return eind.timestamp()


def accu(inhoud, eindprijs, bewaarmarge=0.05):
    return W.Accu(
        inhoud_kwh=max(0.0, min(CAP, inhoud)), bruikbaar_kwh=CAP, laden_kw=2.4, ontladen_kw=2.4,
        verkoop_kw=1.2, laden_slim_kw=2.4, rendement=ETA_L * ETA_O, rendement_laden=ETA_L,
        rendement_ontladen=ETA_O, slijtage_eur=SLIJT, verkoopmarge_eur=0.05, netlaadmarge_eur=0.0,
        huis_eerst=True, bewaarmarge_eur=bewaarmarge, bewaarkost_eur_per_kwh_uur=0.002,
        min_actie_w=400.0, min_laad_w=500.0, zon_export_afdwingbaar=True, eindprijs_eur=eindprijs,
    )


def _invoer(rows, i, prof_v, prof_z):
    r = rows[i]
    tot = _bekend_tot(r["dt"])
    ks, j = [], i
    while j < len(rows) and rows[j]["t"] < tot and j - i < HORIZON_Q:
        rj = rows[j]
        q = _q(rj["dt"])
        ks.append(W.Kwartier(begin=rj["dt"], verbruik_kwh=max(0.0, prof_v.get(q, 0.25)),
                             zon_kwh=max(0.0, prof_z.get(q, 0.0)), inkoop_eur=inkoop(rj["prijs"]),
                             teruglever_eur=terug(rj["prijs"]), verkoop_vloer_kwh=0.15 * CAP,
                             prijs_incl_eur=rj["prijs"]))
        j += 1
    rest = [rows[k]["prijs"] for k in range(j, min(len(rows), j + 48))]
    eindprijs = None
    if len(rest) >= 16:
        s = sorted(inkoop(p) for p in rest)
        eindprijs = s[round(0.75 * (len(s) - 1))]
    return ks, eindprijs


def herspeel(start_dag="2026-10-26", eind_dag="2026-10-29", bewaarmarge=0.05):
    """Productie (bewaarmarge 5 ct) per kwartier plannen en via `es.uitvoeren`
    uitvoeren. Geeft {dag: [kwartierregels]} (dict-vorm), {dag: eindwaarde eerste plan}."""
    rows = laad()
    t0 = datetime.fromisoformat(start_dag + "T00:00:00+01:00").timestamp()
    t1 = datetime.fromisoformat(eind_dag + "T00:00:00+01:00").timestamp()
    i0 = next(i for i, r in enumerate(rows) if r["t"] >= t0)
    i1 = next((i for i, r in enumerate(rows) if r["t"] >= t1), len(rows))
    va = es.VirtueleAccu(inhoud_kwh=max(0.0, (rows[i0]["soc"] - 10) / 90) * CAP, capaciteit_kwh=CAP,
                         eta_l=ETA_L, eta_o=ETA_O, ontladen_kw=2.4, laden_slim_kw=2.4, laden_kw=2.4, verkoop_kw=1.2)
    per_dag, waarden = collections.defaultdict(list), {}
    prof_v = prof_z = None
    for i in range(i0, i1):
        r = rows[i]
        loc = r["dt"].astimezone(TZ)
        if prof_v is None or (loc.hour == 0 and loc.minute == 0):
            prof_v, prof_z = _profiel(rows, i, 7, "huis"), _profiel(rows, i, 3, "pv")
        ks, eindprijs = _invoer(rows, i, prof_v, prof_z)
        res = W.plan(ks, accu(va.inhoud_kwh, eindprijs, bewaarmarge))
        r0 = res.kwartieren[0] if res.beschikbaar and res.kwartieren else {"actie": "huis", "accu_kwh": 0.0}
        dag = loc.date().isoformat()
        waarden.setdefault(dag, res.eindwaarde_eur_per_kwh)
        uit = es.uitvoeren(va, r0["actie"], float(r0.get("accu_kwh") or 0.0), r["huis"], r["pv"])
        rij = {"t": r["t"], "status": "ok", "pin": inkoop(r["prijs"]), "puit": terug(r["prijs"]),
               "slijt": SLIJT, "huis_w": r["huis"], "zon_w": r["pv"]}
        for pre in ("p", *es.VARIANTEN):
            rij.update({f"{pre}_{k}": v for k, v in uit.items()})
        per_dag[dag].append(rij)
    return per_dag, waarden
