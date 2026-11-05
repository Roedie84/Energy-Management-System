"""v5.187.0 economische schaduw - het pure deel (plantoetsen 2, 5, 6, 12, 13).

2  bewaarmarge-isolatie: de kopie verschilt alleen in bewaarmarge en inhoud
5  gelijke afrekening: zelfde prijzen, meting, rendement en slijtage voor alle varianten
6  start- en eindwaarde: voorraadcorrectie tegen de gemeenschappelijke waarde; resync
12 opslaggrootte: 30 dagen kwartierregels < 3 MB, sensorattribuut < 4 kB
13 beslisregels 14 dagen: elke regel apart laten falen
"""
import ast
import dataclasses
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from custom_components.energy_management_system import economische_schaduw as es
from custom_components.energy_management_system import waardeplan as W

T0 = datetime(2026, 11, 4, 19, 0, tzinfo=timezone.utc)


def _accu(**x):
    basis = dict(inhoud_kwh=3.0, bruikbaar_kwh=7.8, laden_kw=2.4, ontladen_kw=2.4, verkoop_kw=1.2,
                 rendement=0.835, slijtage_eur=0.0422, verkoopmarge_eur=0.02, netlaadmarge_eur=0.03,
                 rendement_laden=0.9, rendement_ontladen=0.93,
                 ontlaadbanden=((500, 0.85), (1500, 0.958), (math.inf, None)),
                 min_actie_w=400, min_laad_w=500, zon_export_afdwingbaar=True,
                 huis_eerst=True, bewaarmarge_eur=0.05, bewaarkost_eur_per_kwh_uur=0.002, vol_na_kwartier=None)
    basis.update(x)
    return W.Accu(**basis)


def _dag(n=96):
    ks = []
    for i in range(n):
        t = T0 + timedelta(minutes=15 * i)
        h = t.hour + t.minute / 60
        prijs = 0.25 + 0.12 * math.exp(-((h - 18) / 1.5) ** 2)
        ks.append(W.Kwartier(t, 0.15, 0.0, prijs, prijs + 0.02, 1.0, prijs_incl_eur=prijs + 0.11))
    return ks


def _va(inhoud=3.0):
    return es.VirtueleAccu(inhoud_kwh=inhoud, capaciteit_kwh=7.8, eta_l=0.914, eta_o=0.919,
                           ontladen_kw=2.4, laden_slim_kw=2.4, laden_kw=2.4, verkoop_kw=1.2)


# --- 2: isolatie ---------------------------------------------------------------

def test_kopie_verschilt_alleen_in_bewaarmarge_en_inhoud():
    ks, accu = _dag(), _accu()
    origineel = (json.dumps([dataclasses.asdict(k) for k in ks], default=str), dataclasses.asdict(accu))
    gezien = []

    def spion(k2, a2):
        gezien.append((k2, a2))
        return W.plan(k2, a2)

    uit = es.plan_varianten(spion, ks, accu, {"c2": (0.02, 1.234), "c0": (0.0, 5.0)})
    assert uit["_fouten"] == {} and uit["c2"]["actie"] and uit["c0"]["actie"]
    for (k2, a2), (marge, inhoud) in zip(gezien, [(0.02, 1.234), (0.0, 5.0)]):
        assert a2 is not accu and all(x is not y for x, y in zip(k2, ks))
        assert [dataclasses.asdict(k) for k in k2] == [dataclasses.asdict(k) for k in ks]
        verschil = {f for f, v in dataclasses.asdict(a2).items() if v != dataclasses.asdict(accu)[f]}
        assert verschil == {"bewaarmarge_eur", "inhoud_kwh"}
        assert a2.bewaarmarge_eur == marge and a2.inhoud_kwh == pytest.approx(inhoud)
    # productie-invoer onaangeroerd
    assert json.dumps([dataclasses.asdict(k) for k in ks], default=str) == origineel[0]
    assert dataclasses.asdict(accu) == origineel[1]


def test_schaduwmodule_heeft_geen_home_assistant_en_geen_diensten():
    pad = Path(es.__file__)
    boom = ast.parse(pad.read_text())
    imports = [n for n in ast.walk(boom) if isinstance(n, (ast.Import, ast.ImportFrom))]
    namen = {(getattr(n, "module", None) or "") for n in imports} | {a.name for n in imports for a in n.names}
    assert not any("homeassistant" in x for x in namen)
    tekst = pad.read_text()
    for verboden in ("services", "async_call", "hass", "select.", "number."):
        assert verboden not in tekst.replace("geen dienstaanroepen", ""), verboden
    lijm = (pad.parent / "economische_schaduw_sturing.py").read_text()
    for verboden in ("services.", "async_call", "_async_apply", "async_set_value", "select_option",
                     "_waardeplan_cache =", "last_waardeplan =", "_kwartier_uitvoering ="):
        assert verboden not in lijm, verboden


# --- uitvoeringsmodel ------------------------------------------------------------

def test_uitvoeren_volgt_de_herspeling():
    a = _va(1.0)
    u = es.uitvoeren(a, "huis", 0.0, 0.5, 0.0)            # tekort 0,5 -> max 0,6, inhoud*eta_o 0,919
    assert u["uit"] == pytest.approx(0.5) and u["imp"] == pytest.approx(0.0)
    a = _va(0.2)
    u = es.uitvoeren(a, "huis", 0.0, 0.5, 0.0)            # leeg na 0,2 x 0,919
    assert u["uit"] == pytest.approx(0.2 * 0.919) and a.inhoud_kwh == pytest.approx(0.0)
    assert u["imp"] == pytest.approx(0.5 - 0.2 * 0.919)
    a = _va(3.0)
    u = es.uitvoeren(a, "houden", 0.0, 0.5, 0.0)          # houden: tekort uit het net
    assert u["uit"] == 0 and u["imp"] == pytest.approx(0.5)
    u = es.uitvoeren(a, "houden", 0.0, 0.1, 0.9)          # houden: overschot de accu in
    assert u["in"] == pytest.approx(0.6) and u["exp"] == pytest.approx(0.2)
    a = _va(3.0)
    u = es.uitvoeren(a, "laden_net", 1.0, 0.1, 0.0)       # begrensd op 2,4 kW x 0,25
    assert u["in"] == pytest.approx(0.6) and u["imp"] == pytest.approx(0.7)
    a = _va(3.0)
    u = es.uitvoeren(a, "verkopen", -0.5, 0.1, 0.0)       # verkoop 1,2 kW x 0,25
    assert u["uit"] == pytest.approx(0.3) and u["exp"] == pytest.approx(0.2)
    a = _va(3.0)
    u = es.uitvoeren(a, "zon_export", 0.0, 0.1, 0.9)      # niets de accu in
    assert u["in"] == 0 and u["exp"] == pytest.approx(0.8)
    a = _va(7.7)
    u = es.uitvoeren(a, "zon", 0.0, 0.0, 1.0)             # vol: ruimte 0,1 / 0,914
    assert u["in"] == pytest.approx(0.1 / 0.914) and a.inhoud_kwh == pytest.approx(7.8)


def test_lopend_kwartier_naar_heel_kwartier():
    assert es.gepland_voor_kwartier(0.5, 0.25) == pytest.approx(0.5)
    assert es.gepland_voor_kwartier(0.4, 0.2) == pytest.approx(0.5)
    assert es.gepland_voor_kwartier(0.4, None) == pytest.approx(0.4)


# --- 5 en 6: gelijke afrekening, voorraadcorrectie -------------------------------

def _rij(t, actie_p="huis", **x):
    rij = {"t": t, "status": "ok", "pin": 0.20, "puit": 0.10, "slijt": 0.0422, "huis_w": 0.3, "zon_w": 0.0}
    for pre in ("p", "c2", "c0"):
        rij.update({f"{pre}_actie": actie_p, f"{pre}_inh0": 3.0, f"{pre}_inh1": 3.0 - 0.3 / 0.919,
                    f"{pre}_in": 0.0, f"{pre}_uit": 0.3, f"{pre}_imp": 0.0, f"{pre}_exp": 0.0})
    rij.update(x)
    return es.rij_als_lijst(rij)


def test_gelijke_afrekening_voor_alle_varianten():
    rijen = [_rij(1000 + 900 * i) for i in range(96)]
    dag = es.dagsamenvatting("2026-11-05", rijen, 0.30, 0.919, 7.8)
    assert dag["production_cost_eur"] == dag["c2_cost_eur"] == dag["c0_cost_eur"]
    assert dag["production_slijtage_eur"] == pytest.approx(96 * 0.3 * 0.0422, abs=1e-3)
    # zelfde meting, andere actie: alleen de actie bepaalt het verschil
    u_p = es.uitvoeren(_va(3.0), "huis", 0.0, 0.3, 0.0)
    u_c = es.uitvoeren(_va(3.0), "houden", 0.0, 0.3, 0.0)
    k_p = es.kosten(u_p["imp"], u_p["exp"], u_p["uit"], 0.2, 0.1, 0.0422)
    k_c = es.kosten(u_c["imp"], u_c["exp"], u_c["uit"], 0.2, 0.1, 0.0422)
    assert k_p == pytest.approx(0.3 * 0.0422) and k_c == pytest.approx(0.3 * 0.2)


def test_voorraadcorrectie_tegen_de_gemeenschappelijke_waarde():
    # C2 houdt vast (0,3 kWh uit het net), productie dekt uit de accu
    rijen = [_rij(1000 + 900 * i, c2_actie="houden", c2_uit=0.0, c2_imp=0.3, c2_inh1=3.0) for i in range(96)]
    dag = es.dagsamenvatting("2026-11-05", rijen, 0.30, 0.919, 7.8)
    dv_p = 96 * (-0.3 / 0.919)
    assert dag["production_voorraad_kwh"] == pytest.approx(dv_p, abs=1e-2)
    assert dag["c2_voorraad_kwh"] == 0
    p = 96 * 0.3 * 0.0422 - dv_p * 0.30
    c2 = 96 * 0.3 * 0.20
    assert dag["production_cost_eur"] == pytest.approx(p, abs=5e-3)   # rijen op 4 decimalen
    assert dag["c2_cost_eur"] == pytest.approx(c2, abs=1e-3)
    assert dag["saving_c2_eur"] == pytest.approx(p - c2, abs=5e-3)
    assert dag["different_actions_c2_pct"] == 100.0
    assert dag["max_soc_delta_c2_kwh"] == pytest.approx(0.3 / 0.919, abs=1e-3)
    # zonder eindwaarde: mediaan inkoop x eta_o - slijtage
    dag2 = es.dagsamenvatting("2026-11-05", rijen, None, 0.919, 7.8)
    assert dag2["waarde_inhoud"] == pytest.approx(0.20 * 0.919 - 0.0422, abs=1e-4)
    assert dag2["waarde_bron"].startswith("mediaan")


def test_niet_gemeten_kwartier_telt_niet():
    rijen = [_rij(1000 + 900 * i) for i in range(96)]
    rijen[5] = _rij(1000 + 900 * 5, status="geen_meting", p_inh1=0.0)
    dag = es.dagsamenvatting("2026-11-05", rijen, 0.30, 0.919, 7.8)
    assert dag["kwartieren_ok"] == 95 and dag["kwartieren_totaal"] == 96 and dag["volledig"] is True


def test_resync_geeft_gelijke_start():
    boek = es.Schaduwboek()
    boek.virtueel = {"c2": 1.0, "c0": 6.0}
    boek.resync(3.3, "2026-11-05T00:00:00")
    assert boek.virtueel == {"c2": 3.3, "c0": 3.3}


def test_dag_sluiten_en_opslag_terug():
    boek = es.Schaduwboek()
    boek.open("2026-11-05", 0.0)
    boek.zet_waarde("2026-11-05", 0.31)
    boek.zet_waarde("2026-11-05", 0.99)          # alleen het eerste plan van de dag telt
    for i in range(96):
        boek.voeg_rij_toe(es.rij_als_dict(_rij(900 * i)))
    regel = boek.sluit_dag(86400.0, 0.919, 7.8)
    assert regel["waarde_inhoud"] == 0.31 and boek.open_dag is None
    terug = es.Schaduwboek(json.loads(json.dumps(boek.naar_opslag())))
    assert terug.dagen == boek.dagen and terug.rijen == boek.rijen


# --- 12: opslaggrootte ------------------------------------------------------------

def test_opslag_30_dagen_en_attribuut_klein():
    boek = es.Schaduwboek()
    t = 1_790_000_000.0
    for d in range(90):
        boek.open(f"d{d:02d}", t)
        for i in range(96):
            boek.voeg_rij_toe(es.rij_als_dict(_rij(t + 900 * i, midk=[1, 0, 0.0123, 0.0456],
                                                   p_reden=0.3123, c2_reden=0.2987, c0_reden=0.2876,
                                                   huis_v=0.1234, zon_v=0.0567)))
        boek.zet_waarde(f"d{d:02d}", 0.3)
        boek.sluit_dag(t + 86400, 0.919, 7.8)
        t += 86400
        boek.opschonen(t)
    assert 30 * 96 <= len(boek.rijen) <= 31 * 96
    assert len(boek.dagen) == 90
    grootte = len(json.dumps(boek.naar_opslag()))
    assert grootte < 3_000_000, grootte
    attribuut = len(json.dumps({"status": "loopt", "fout": None, **boek.samenvatting()}))
    assert attribuut < 4096, attribuut


# --- 13: beslisregels ---------------------------------------------------------------

def _dagen(n=14, **over):
    uit = []
    for i in range(n):
        d = {"date": f"2026-11-{i + 1:02d}", "volledig": True, "saving_c2_eur": 0.05, "saving_c0_eur": 0.05,
             "production_switches": 20, "c2_switches": 20, "c0_switches": 20,
             "production_cycles": 0.8, "c2_cycles": 0.8, "c0_cycles": 0.8,
             "production_cost_6ct_eur": 1.00, "c2_cost_6ct_eur": 0.95, "c0_cost_6ct_eur": 0.95}
        for k, v in over.items():
            d[k] = v(i) if callable(v) else v
        uit.append(d)
    return uit


def test_beslisregels_alle_gehaald():
    e = es.evalueer(_dagen(), "c2")
    assert e["status"] == "geschikt" and all(r["gehaald"] for r in e["regels"].values())


def test_te_weinig_dagen():
    e = es.evalueer(_dagen(13), "c2")
    assert e["status"] == "te weinig dagen" and "13 van 14" in e["advies"]
    dagen = _dagen(15)
    dagen[3]["volledig"] = False
    assert es.evalueer(dagen, "c2")["dagen"] == 14


@pytest.mark.parametrize("regel,over", [
    ("geen_dag_meer_dan_0_25_slechter", {"saving_c2_eur": lambda i: -0.30 if i == 0 else 0.10}),
    ("minstens_9_van_14_gelijk_of_beter", {"saving_c2_eur": lambda i: 0.30 if i < 8 else -0.01}),
    ("wisselingen_max_plus_10_pct", {"c2_switches": 23}),
    ("cycli_max_plus_10_pct", {"c2_cycles": 0.9}),
    ("positief_bij_6_ct_slijtage", {"c2_cost_6ct_eur": 1.01}),
    ("niet_vooral_een_dag", {"saving_c2_eur": lambda i: 0.80 if i == 0 else 0.0}),
    ("totaal_beter", {"saving_c2_eur": lambda i: -0.01}),
])
def test_elke_beslisregel_apart(regel, over):
    e = es.evalueer(_dagen(**over), "c2")
    gezakt = {k for k, r in e["regels"].items() if not r["gehaald"]}
    assert regel in gezakt and e["status"] == "afgewezen" and regel in e["advies"]
    if regel not in ("totaal_beter", "minstens_9_van_14_gelijk_of_beter"):
        assert gezakt == {regel}


def test_rollend_en_besparing_14d():
    boek = es.Schaduwboek()
    boek.dagen = _dagen(20, ems_besparing_eur=0.2, ems_regret_eur=0.05)
    r = boek.samenvatting()["rollend"]
    assert r["14_dagen"]["dagen"] == 14 and r["14_dagen"]["ems_besparing_eur"] == pytest.approx(2.8)
    assert r["90_dagen"]["dagen"] == 20
    assert boek.besparing_c2_14d() == pytest.approx(0.70)


def test_midkwartier_voordeel_en_teller():
    plan = {"nu": {"uren": 0.2, "rekenprijs_eur": 0.30, "accu_kwh": 0.0, "waarde_inhoud_eur_per_kwh": 0.25}}
    oud = {"nu": {"uren": 0.25, "accu_kwh": -0.5}}
    assert es.midkwartier_voordeel(plan, oud, 0.10) == pytest.approx(0.4 * 0.20)
    assert es.midkwartier_voordeel(plan, oud, None) is None
    m = es.midk_bij(None, True, 0.08, 0.02)
    m = es.midk_bij(m, False, 0.5, 0.5)
    m = es.midk_bij(m, True, 0.01, 0.03)
    assert m == [2, 1, 0.08, 0.03]
