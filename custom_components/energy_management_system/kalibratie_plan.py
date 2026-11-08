"""De planning tijdens een kalibratie (v5.194.2).

Gemeld 08-11: zolang de kalibratie liep werd de planning niet bijgewerkt. De
kalibratieronde stuurt buiten het waardeplan om en rekende daarom ook geen
plan meer; de tabel en de cockpit bleven op het plan van vóór de kalibratie
staan (accu 10 %, sparen).

Nu: de eerste kwartieren laden op het handmatige laadvermogen tot vol en
houden de accu daarna KALIBRATIE_HOUD_MIN bovenin (het huis komt dan uit het
net), precies zoals `_kalibratie_ronde` doet. Vanaf het einde van de
kalibratie rekent het gewone waardeplan verder met een volle accu.

Alleen pure functies; de planner (waardeplan.plan) komt als argument mee.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Callable

from . import waardeplan as W

#: Onder dit verschil (kWh) met vol telt de accu als vol.
VOL_MARGE_KWH = 0.01


def _rij(k: W.Kwartier, b: float, c: float, c2: float, max_ac: float) -> dict:
    return {
        "begin": k.begin,
        "actie": "laden_net",
        "kwh": round(b, 3),
        "accu_kwh": round(b, 3),
        "net_kwh": round(k.verbruik_kwh - k.zon_kwh + b, 3),
        "inhoud_kwh": round(c2, 3),
        "inhoud_delta_kwh": round(c2 - c, 3),
        "verbruik_kwh": round(k.verbruik_kwh, 3),
        "zon_kwh": round(k.zon_kwh, 3),
        "vol_vermogen": b > 0 and b >= max_ac - 1e-9,
        "prijs_eur": round(k.inkoop_eur if k.prijs_incl_eur is None else k.prijs_incl_eur, 4),
        "rekenprijs_eur": round(k.inkoop_eur, 4),
        "uren": round(k.uren, 4),
        "verkoop_vloer_kwh": round(k.verkoop_vloer_kwh, 2),
        "kalibratie": True,
    }


def kalibratierijen(kwartieren: list, accu: W.Accu, houd_tot: datetime | None,
                    houd_min: int) -> tuple[list[dict], float, int]:
    """(rijen, inhoud na de kalibratie, aantal kwartieren).

    `houd_tot`: einde van het vasthouden als de accu al vol is, anders None
    (dan houd_min na het moment waarop het plan vol bereikt)."""
    eta_l = W.rendementen(accu)[0]
    cap = accu.bruikbaar_kwh
    c = min(max(accu.inhoud_kwh, 0.0), cap)
    rijen: list[dict] = []
    for k in kwartieren:
        if houd_tot is not None and k.begin >= houd_tot:
            break
        uren = k.uren
        max_ac = accu.laden_kw * uren * getattr(k, "laad_factor", 1.0)
        b = 0.0
        c2 = c
        if cap - c > VOL_MARGE_KWH:
            b = min(max_ac, (cap - c) / eta_l) if eta_l > 0 else 0.0
            c2 = min(cap, c + b * eta_l)
            if houd_tot is None and cap - c2 <= VOL_MARGE_KWH:
                deel = (b / max_ac) if max_ac > 0 else 1.0
                vol_om = k.begin + timedelta(hours=uren * deel)
                houd_tot = vol_om + timedelta(minutes=houd_min)
        rijen.append(_rij(k, b, c, c2, max_ac))
        c = c2
    return rijen, c, len(rijen)


def plan(kwartieren: list, accu: W.Accu, houd_tot: datetime | None, houd_min: int,
         planner: Callable = W.plan) -> W.Uitkomst:
    """Kalibratie eerst, daarna het gewone plan vanaf een volle accu."""
    rijen, inhoud, n = kalibratierijen(kwartieren, accu, houd_tot, houd_min)
    kosten = sum(
        float(r["net_kwh"]) * (k.inkoop_eur if r["net_kwh"] >= 0 else k.teruglever_eur)
        for r, k in zip(rijen, kwartieren)
    )
    zonder = sum(
        (k.verbruik_kwh - k.zon_kwh)
        * (k.inkoop_eur if k.verbruik_kwh >= k.zon_kwh else k.teruglever_eur)
        for k in kwartieren[:n]
    )
    rest = list(kwartieren[n:])
    if not rest:
        return W.Uitkomst(True, "", rijen, kosten, zonder)
    res = planner(rest, replace(accu, inhoud_kwh=inhoud, vol_na_kwartier=None))
    if not res.beschikbaar:
        return W.Uitkomst(True, "", rijen, kosten, zonder)
    res.kwartieren = rijen + list(res.kwartieren)
    res.kosten_plan_eur = kosten + (res.kosten_plan_eur or 0.0)
    res.kosten_zonder_accu_eur = zonder + (res.kosten_zonder_accu_eur or 0.0)
    return res
