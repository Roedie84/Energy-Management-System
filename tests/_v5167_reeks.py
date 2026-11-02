"""Gedeelde realistische reeks voor de v5.167.0-toetsen (geen toets zelf).

Een SoC in stappen van 1 % = 0,1152 kWh (afgerond naar beneden, zoals de
Zendure), laden met rendement ETA_L aan de netkant, ontladen met ETA_O
(de SoC is op de bruikbare afgifte geijkt: ~1,0). Per kwartier het
dagverloop (inhoud aan het EIND van het kwartier, onder de sleutel van zijn
begin) en de meetlaag zoals `_gemeten_kwartieren` hem teruggeeft
(accu_in_kwh / accu_uit_kwh / accu_kwh per 'HH:MM' = begin van het kwartier).
"""
import math
from datetime import datetime, timedelta

STAP = 0.1152
DAG0 = datetime(2026, 10, 24, 0, 0)


def bouw(segmenten, inhoud0=3.0, begin=DAG0, eta_l=0.82, eta_o=1.0, prijs=lambda t: 25.0,
         gat_na=None, gat_kwartieren=0):
    """segmenten: [(aantal, accu_w, net_w)] met accu_w > 0 = ontladen.

    `gat_na`: na zoveel kwartieren `gat_kwartieren` geen regels (de accu doet
    in het gat wat het segment doet, maar niemand schrijft het op).
    Geeft (dagverloop, gemeten, echte_ac_in, echte_ac_uit)."""
    echt = inhoud0
    t = begin
    regels: dict = {}
    gemeten: dict = {}
    ac_in = ac_uit = 0.0
    teller = 0

    def regel(moment, accu_w, net_w, erin, eruit, schrijf=True):
        if not schrijf:
            return
        dag = moment.date().isoformat()
        tijd = moment.strftime("%H:%M")
        soc = math.floor(echt / STAP + 1e-9)
        regels.setdefault(dag, []).append({
            "tijd": tijd, "beschikbaar_kwh": round(soc * STAP, 4), "accu_w": accu_w, "soc": soc,
            "net_w": net_w, "huis_w": 300.0, "pv_w": 0.0, "prijs_ct": prijs(moment)})
        gemeten.setdefault(dag, {})[tijd] = {"accu_in_kwh": erin, "accu_uit_kwh": eruit,
                                             "accu_kwh": eruit - erin}

    regel(t - timedelta(minutes=15), 0.0, 300.0, 0.0, 0.0)
    for n, accu_w, net_w in segmenten:
        for _ in range(n):
            ac = abs(accu_w) / 4000
            if accu_w > 0:
                echt -= ac / eta_o
                erin, eruit = 0.0, ac
            elif accu_w < 0:
                echt += ac * eta_l
                erin, eruit = ac, 0.0
            else:
                erin = eruit = 0.0
            ac_in += erin
            ac_uit += eruit
            teller += 1
            in_gat = gat_na is not None and gat_na < teller <= gat_na + gat_kwartieren
            # de regel van het kwartier dat om t begint, geschreven aan zijn eind
            regel(t, accu_w, net_w, erin, eruit, schrijf=not in_gat)
            t += timedelta(minutes=15)
    return regels, gemeten, ac_in, ac_uit


def zonder_meting(regels):
    return {d: [dict(r) for r in rs] for d, rs in regels.items()}
