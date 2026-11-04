"""v5.186.0-A: het waardeplan na de review (punten 1-20).

Exacte slimme stand (geen afronding op 0,1 kWh), verkoopvloer alleen voor
echte verkopen, bewaarmarge in het plan, aflopende eindwaarde, zachte
balanceereis, netlading-herkomst voor huis eerst, geen netlading in de ruimte
die de zon nog vult, slim laadvermogen, toetsen per kwartier (geen globale
herberekening), rondes zichtbaar, rekenwerk in de executor.
"""
import asyncio
import math
import time
from datetime import datetime, timedelta

import pytest

from custom_components.energy_management_system import waardeplan as W

T0 = datetime(2026, 11, 4, 19, 0)


def _accu(**x):
    basis = dict(inhoud_kwh=3.0, bruikbaar_kwh=7.8, laden_kw=2.4, ontladen_kw=2.4, verkoop_kw=1.2,
                 rendement=0.835, slijtage_eur=0.0422, verkoopmarge_eur=0.02, netlaadmarge_eur=0.03,
                 rendement_laden=0.9, rendement_ontladen=0.93,
                 ontlaadbanden=((500, 0.85), (1500, 0.958), (math.inf, None)),
                 min_actie_w=400, min_laad_w=500, zon_export_afdwingbaar=True,
                 huis_eerst=True, bewaarmarge_eur=0.05, bewaarkost_eur_per_kwh_uur=0.002)
    basis.update(x)
    return W.Accu(**basis)


def _dag(n=144, start=datetime(2026, 11, 4, 12)):
    """De dag van de review (bench.py): zon rond het middaguur, avondpiek."""
    ks = []
    for i in range(n):
        t = start + timedelta(minutes=15 * i)
        h = t.hour + t.minute / 60
        zon = max(0.0, math.sin((h - 8) / 9 * math.pi)) * 0.6 if 8 < h < 17 else 0.0
        verb = 0.12 + (0.25 if 17 <= h < 20 else 0)
        prijs = (0.25 + 0.12 * math.exp(-((h - 18) / 1.5) ** 2) + 0.06 * math.exp(-((h - 8) / 1.2) ** 2)
                 - 0.04 * math.exp(-((h - 13) / 2) ** 2))
        ks.append(W.Kwartier(t, verb, zon, prijs, prijs + 0.02, 1.5 if 15 <= h < 21 else 0.0))
    return ks


# --- punt 1: de verkoopvloer blokkeert het huis niet meer -----------------------

@pytest.mark.parametrize("verbruik", [0.15, 0.17, 0.25])
def test_vloer_boven_de_inhoud_laat_het_huis_dekken(verbruik):
    """Review vloer.py: inhoud 1,2 kWh onder een vloer van 1,5 kWh -> het plan
    bewaarde ('houden') terwijl het huis op 40 ct het net op ging."""
    ks = [W.Kwartier(T0 + timedelta(minutes=15 * i), verbruik, 0.0, 0.40 if i < 12 else 0.30,
                     0.42 if i < 12 else 0.32, 1.5 if i < 12 else 0.0) for i in range(48)]
    rijen = W._plan(ks, _accu(inhoud_kwh=1.2, huis_eerst=False, bewaarmarge_eur=0)).kwartieren
    assert rijen[0]["actie"] == "huis"
    assert all(r["actie"] != "verkopen" for r in rijen[:12])


# --- punt 2: exacte slimme dekking en zonopslag ---------------------------------

def test_kleine_huislast_trekt_de_accu_niet_sneller_leeg():
    """Review nacht.py: huis 0,04 kWh per kwartier; met de stap van 0,1 kWh trok
    het plan de accu ~1,5x zo snel leeg. Nu zakt de inhoud met tekort / rendement."""
    ks = [W.Kwartier(datetime(2026, 11, 4, 22) + timedelta(minutes=15 * i), 0.04, 0.0,
                     0.36, 0.38, 0.0) for i in range(64)]
    acc = _accu(inhoud_kwh=2.0, huis_eerst=False, bewaarmarge_eur=0, verkopen=False, netladen=False)
    eta = W.ontlaadrendement(160, acc, W.rendementen(acc)[1])
    for r in W.plan(ks, acc).kwartieren:
        if r["actie"] == "huis" and r["inhoud_kwh"] > 0.05:
            assert -r["inhoud_delta_kwh"] == pytest.approx(0.04 / eta, abs=0.002)
            assert r["net_kwh"] == pytest.approx(0.0, abs=1e-6)


def test_huis_rij_zonder_nepexport_en_kosten_kloppen():
    """Punt 15: kosten_plan rekent geen teruglevering uit een afgerond restje."""
    ks = [W.Kwartier(T0 + timedelta(minutes=15 * i), 0.12, 0.0, 0.40, 0.42, 0.0) for i in range(16)]
    res = W.plan(ks, _accu(inhoud_kwh=1.0, verkopen=False, netladen=False, huis_eerst=False,
                           bewaarmarge_eur=0))
    assert all(r["net_kwh"] >= -1e-9 for r in res.kwartieren)
    accu = _accu(inhoud_kwh=1.0)
    kosten = sum(max(r["net_kwh"], 0) * 0.40 + max(-r["accu_kwh"], 0) * accu.slijtage_eur
                 for r in res.kwartieren)
    # plus de eindwaarde van wat er uit de accu ging (korte horizon: lineair)
    kosten += (1.0 - res.kwartieren[-1]["inhoud_kwh"]) * res.eindwaarde_eur_per_kwh
    assert res.kosten_plan_eur == pytest.approx(kosten, abs=0.005)


def test_zonopslag_exact_en_doorlopende_inhoud():
    ks = [W.Kwartier(T0 + timedelta(minutes=15 * i), 0.05, 0.25, 0.30, 0.32) for i in range(8)]
    acc = _accu(inhoud_kwh=1.03, huis_eerst=False, bewaarmarge_eur=0, zon_export_afdwingbaar=False)
    rijen = W.plan(ks, acc).kwartieren
    eta_l = W.rendementen(acc)[0]
    assert rijen[0]["actie"] == "zon"
    assert rijen[0]["inhoud_kwh"] == pytest.approx(1.03 + 0.2 * eta_l, abs=0.002)
    assert rijen[0]["net_kwh"] == pytest.approx(0.0, abs=1e-6)


# --- punt 7: een kort lopend kwartier ------------------------------------------

@pytest.mark.parametrize("minuten", [1.5, 3, 5, 8])
def test_kort_lopend_kwartier_dekt_het_huis(minuten):
    """Review part.py: met 1,5-3 min over kon het plan niet ontladen (de kleinste
    stap was een 'verkoop' boven het vermogen) en bewaarde het."""
    ks = []
    for i in range(48):
        uren = 0.25 if i else minuten / 60
        p = 0.40 if i < 8 else 0.25
        ks.append(W.Kwartier(T0 + timedelta(minutes=15 * i), 0.15 * uren / 0.25, 0.0, p, p + 0.02, 0.0,
                             uren=uren))
    rij = W.plan(ks, _accu(inhoud_kwh=4.0)).kwartieren[0]
    assert rij["actie"] == "huis"
    assert -rij["accu_kwh"] == pytest.approx(0.15 * (minuten / 60) / 0.25, abs=1e-6)


# --- punt 3: bewaren met de waarde uit het plan ---------------------------------

def test_te_duur_bewaard_gebruikt_de_planwaarde():
    k = [W.Kwartier(T0, 0.3, 0.0, 0.40, 0.42)]
    acc = _accu()
    eta_h = W.ontlaadrendement(1200, acc, W.rendementen(acc)[1])
    # later 44 ct (na rendement en slijtage) -> 4 ct boven 40 ct: te weinig
    lam = (0.44 - acc.slijtage_eur) * eta_h
    rij = {"actie": "houden", "net_kwh": 0.3, "inhoud_kwh": 2.0, "waarde_dekking_eur_per_kwh": lam}
    assert W.te_duur_bewaard([rij], k, acc) == [0]
    rij["waarde_dekking_eur_per_kwh"] = (0.46 - acc.slijtage_eur) * eta_h
    assert W.te_duur_bewaard([rij], k, acc) == []


def test_bijladen_in_de_oude_schatting_door_beide_rendementen():
    """Zonder planwaarde (losse rijen): bijladen kost (prijs + marge) / (laden x ontladen)."""
    k = [W.Kwartier(T0 + timedelta(minutes=15 * i), 0.3, 0.0, p, p) for i, p in enumerate([0.40, 0.30, 0.60])]
    acc = _accu(netlaadmarge_eur=0.0, slijtage_eur=0.0)
    rijen = [{"actie": "houden", "net_kwh": 0.3, "inhoud_kwh": 2.0},
             {"actie": "laden_net", "accu_kwh": 0.5, "inhoud_kwh": 2.4},
             {"actie": "huis", "accu_kwh": -0.3, "inhoud_kwh": 2.0}]
    eta_l, eta_o = W.rendementen(acc)
    assert 0.30 / (eta_l * eta_o) - 0.40 < 0.05     # bijladen ~0,36: minder dan 5 ct boven 40 ct
    assert W.te_duur_bewaard(rijen, k, acc) == [0]


def test_plan_bewaart_niet_voor_minder_dan_de_marge():
    ks = _dag()
    acc = _accu()
    res = W.plan(ks, acc)
    assert W.te_duur_bewaard(res.kwartieren, ks, acc) == []
    assert res.resterend == {}


# --- punt 4: aflopende eindwaarde ------------------------------------------------

def test_eindwaarde_knik_en_geen_netlading_alleen_voor_het_eind():
    # twee etmalen, vlakke prijs; 's nachts goedkoop; aan het eind zou een
    # lineaire eindwaarde (75e percentiel) laden voor 'na de horizon' belonen
    ks = []
    for i in range(192):
        t = datetime(2026, 11, 4, 0) + timedelta(minutes=15 * i)
        p = 0.22 if t.hour < 6 else 0.30
        ks.append(W.Kwartier(t, 0.05, 0.0, p, p - 0.10))     # 2027: terugleveren onder de inkoop
    acc = _accu(inhoud_kwh=0.0, huis_eerst=False, bewaarmarge_eur=0)
    eta_l, eta_o = W.rendementen(acc)
    hoog = W.eindwaarde(ks, acc, eta_o)
    knik, laag = W.eindwaarde_knik(ks, acc, eta_l, eta_o, hoog, 7.8)
    assert knik == pytest.approx(96 * 0.05 / eta_o, rel=0.02)   # een etmaal huis, geen zon
    assert laag < hoog
    res = W.plan(ks, acc)
    assert res.eindwaarde_knik_kwh == pytest.approx(knik, abs=0.01)
    # de tweede nacht laadt het plan niet boven wat het huis daarna nog nodig heeft
    assert res.kwartieren[-1]["inhoud_kwh"] <= knik + 0.6


def test_korte_horizon_houdt_de_lineaire_eindwaarde():
    ks = [W.Kwartier(T0 + timedelta(minutes=15 * i), 0.1, 0.0, 0.3, 0.3) for i in range(20)]
    acc = _accu()
    eta_l, eta_o = W.rendementen(acc)
    assert W.eindwaarde_knik(ks, acc, eta_l, eta_o, 0.25, 7.8) == (7.8, 0.25)


# --- punt 5: dekken -------------------------------------------------------------

def test_dekken_verbiedt_bewaren_en_netladen_met_inhoud():
    ks = [W.Kwartier(T0 + timedelta(minutes=15 * i), 0.3, 0.0, 0.30, 0.32, dekken=(i == 0))
          for i in range(4)] + [W.Kwartier(T0 + timedelta(minutes=15 * (4 + i)), 0.3, 0.0, 0.60, 0.62)
                                for i in range(8)]
    acc = _accu(inhoud_kwh=1.0, huis_eerst=False, bewaarmarge_eur=0, verkopen=False)
    rijen = W._plan(ks, acc).kwartieren
    assert rijen[0]["actie"] == "huis"
    assert rijen[1]["actie"] in ("houden", "laden_net")    # zonder vlag: bewaren voor 60 ct


# --- punt 6: zachte, haalbare balanceereis --------------------------------------

def test_onhaalbare_eis_geeft_toch_een_laadplan():
    """Review eis.py: lege accu, eis 'vol na kwartier 14' (niet haalbaar): het
    hele plan werd 'houden' terwijl het beschikbaar heette."""
    ks = []
    for i in range(60):
        uren = 0.25 if i else 2 / 60
        p = 0.22 if i < 32 else 0.40
        ks.append(W.Kwartier(datetime(2026, 11, 4, 22) + timedelta(minutes=15 * i), 0.15 * uren / 0.25,
                             0.0, p, p + 0.02, uren=uren))
    res = W.plan(ks, _accu(inhoud_kwh=0.0, vol_na_kwartier=14))
    assert res.beschikbaar
    assert sum(1 for r in res.kwartieren[:15] if r["actie"] == "laden_net") >= 13
    assert res.kwartieren[14]["inhoud_kwh"] >= 6.9
    res = W.plan(ks, _accu(inhoud_kwh=3.0, vol_na_kwartier=14))
    assert res.kwartieren[14]["inhoud_kwh"] == pytest.approx(7.8, abs=0.01)


def test_balanceren_rekent_met_het_laadrendement():
    from pathlib import Path
    import custom_components.energy_management_system as pkg
    code = (Path(pkg.__file__).parent / "waardeplan_sturing.py").read_text(encoding="utf-8")
    deel = code.split("    def _waardeplan_balanceren(", 1)[1].split("\n    def ", 1)[0]
    assert "waardeplan_mod.rendementen(accu)[0]" in deel
    assert "** 0.5" not in deel


# --- punt 8: huis eerst met de herkomst van de lading ---------------------------

def test_kleine_netlading_verbiedt_latere_zonverkoop_niet():
    ks = [W.Kwartier(T0 + timedelta(minutes=15 * i), 0.1, 0.0, 0.3, 0.3) for i in range(6)]
    acc = _accu(inhoud_kwh=5.0)
    rijen = [
        {"actie": "laden_net", "accu_kwh": 0.2, "inhoud_kwh": 5.18, "inhoud_delta_kwh": 0.18},
        {"actie": "houden", "accu_kwh": 0.0, "inhoud_kwh": 5.18, "inhoud_delta_kwh": 0.0},
        {"actie": "verkopen", "accu_kwh": -0.3, "inhoud_kwh": 4.86, "inhoud_delta_kwh": -0.32},
    ] + [{"actie": "huis", "accu_kwh": -0.1, "inhoud_kwh": 4.75, "inhoud_delta_kwh": -0.11}] * 3
    assert W.verkopen_voor_huis(rijen, ks, acc) == []


def test_klein_zonoverschot_is_nog_geen_bijvullen():
    """Een kwartier met 0,03 kWh overschot gold als 'bijvullen': de verkoop ervoor
    mocht, terwijl het huis daarna leeg kwam te staan."""
    spec = [(0.3, 0.0)] + [(0.3, 0.0)] * 2 + [(0.05, 0.08)] + [(0.3, 0.0)] * 6
    ks = [W.Kwartier(T0 + timedelta(minutes=15 * i), v, z, 0.3, 0.3) for i, (v, z) in enumerate(spec)]
    acc = _accu(inhoud_kwh=1.5)
    rijen = [{"actie": "verkopen", "accu_kwh": -0.3, "inhoud_kwh": 1.2, "inhoud_delta_kwh": -0.3}]
    rijen += [{"actie": "huis", "accu_kwh": -0.3, "inhoud_kwh": 1.0, "inhoud_delta_kwh": -0.3}] * 9
    assert W.verkopen_voor_huis(rijen, ks, acc) == [0]


# --- punt 9: geen netlading in de ruimte die de zon nog vult --------------------

def test_netladen_voor_zon_die_overloopt():
    ks = [W.Kwartier(T0 + timedelta(minutes=15 * i), 0.1, 0.4 if i >= 2 else 0.0, 0.25, 0.27)
          for i in range(5)]
    acc = _accu(bruikbaar_kwh=2.0)
    rijen = [
        {"actie": "laden_net", "kwh": 0.5, "accu_kwh": 0.5, "net_kwh": 0.6, "inhoud_kwh": 1.5},
        {"actie": "laden_net", "kwh": 0.3, "accu_kwh": 0.3, "net_kwh": 0.4, "inhoud_kwh": 1.8},
        {"actie": "zon", "accu_kwh": 0.2, "net_kwh": -0.1, "inhoud_kwh": 2.0},
        {"actie": "zon", "accu_kwh": 0.0, "net_kwh": -0.3, "inhoud_kwh": 2.0},
        {"actie": "huis", "accu_kwh": -0.1, "net_kwh": 0.0, "inhoud_kwh": 1.9},
    ]
    # 0,4 kWh zon het net op: alleen de laatste netlading (0,3) is niet genoeg,
    # dus beide; een eerdere zonder overloop erna blijft
    assert W.netladen_voor_zonoverloop(rijen, ks, acc) == [0, 1]
    rijen[3]["net_kwh"] = -0.05
    rijen[2]["net_kwh"] = 0.0
    assert W.netladen_voor_zonoverloop(rijen, ks, acc) == [1]


def test_plan_laadt_niet_vol_voor_de_zon():
    """Review: netladen tot vol vlak voor zon die daarna het net op gaat."""
    ks = []
    for i in range(96):
        t = datetime(2026, 11, 5, 4) + timedelta(minutes=15 * i)
        h = t.hour + t.minute / 60
        zon = max(0.0, math.sin((h - 8) / 8 * math.pi)) * 0.5 if 8 < h < 16 else 0.0
        p = 0.24 if 10 <= h < 13 else (0.45 if 17 <= h < 21 else 0.32)
        ks.append(W.Kwartier(t, 0.1, zon, p, p + 0.02))
    acc = _accu(inhoud_kwh=0.5)
    rijen = W.plan(ks, acc).kwartieren
    assert W.netladen_voor_zonoverloop(rijen, ks, acc) == []


# --- punt 10: één verkoopvloer, een kwartier opgeschoven en met rendement -------

def test_vloeren_gelijktrekken_neemt_het_volgende_tekort():
    ks = [W.Kwartier(T0, 0.1, 0.0, 0.5, 0.5, 3.0),
          W.Kwartier(T0 + timedelta(minutes=15), 0.5, 0.0, 0.5, 0.5, 3.0),
          W.Kwartier(T0 + timedelta(minutes=30), 0.2, 0.0, 0.5, 0.5, 1.0),
          W.Kwartier(T0 + timedelta(minutes=45), 0.2, 0.0, 0.5, 0.5, 0.0)]
    uit = W.vloeren_gelijktrekken(ks, 0.2, eta_o=0.8)
    # vloer na kwartier 1 = vloer na 2 (1,0) + tekort van kwartier 2 (0,2) / 0,8
    assert uit[1].verkoop_vloer_kwh == pytest.approx(1.0 + 0.2 / 0.8)
    assert uit[0].verkoop_vloer_kwh == pytest.approx(1.25 + 0.5 / 0.8)
    # een rendement boven 1 telt als 1 (nooit onder het tekort aan de netkant)
    assert W.vloeren_gelijktrekken(ks, 0.2, eta_o=1.1)[1].verkoop_vloer_kwh == pytest.approx(1.2)


# --- punt 13: slim laadvermogen voor zon ----------------------------------------

def test_zon_opslag_tot_het_slimme_laadvermogen():
    ks = [W.Kwartier(T0 + timedelta(minutes=15 * i), 0.1, 0.9, 0.30, 0.32) for i in range(4)]
    for slim, verwacht_ac in ((None, 0.3), (3.2, 0.8)):
        acc = _accu(inhoud_kwh=1.0, laden_kw=1.2, laden_slim_kw=slim, huis_eerst=False,
                    bewaarmarge_eur=0, zon_export_afdwingbaar=False, verkopen=False)
        rij = W.plan(ks, acc).kwartieren[0]
        assert rij["actie"] == "zon" and rij["accu_kwh"] == pytest.approx(verwacht_ac, abs=1e-6)


def test_sturing_leest_het_slimme_laadvermogen(make_coordinator):
    from custom_components.energy_management_system.const import CONF_BATTERY_MAX_CHARGE_POWER_ENTITY
    c = make_coordinator({CONF_BATTERY_MAX_CHARGE_POWER_ENTITY: "number.max_laden"})
    c._read_sensor_float = lambda e: 3200.0 if e == "number.max_laden" else None
    c._waardeplan_rendementen = lambda now: {}
    c._waardeplan_eindprijs = lambda kw: None
    acc = c._waardeplan_accu(T0, 2.0, 7.8, 83.0, [])
    assert acc.laden_slim_kw == pytest.approx(3.2)


# --- punt 14/15: per kwartier, en zichtbaar wat de toetsen deden ----------------

def test_rondes_en_resterend_in_de_uitkomst():
    res = W.plan(_dag(), _accu())
    assert 1 <= res.rondes <= W.MAX_RONDES
    assert res.rondelimiet is False
    assert isinstance(res.resterend, dict)


def test_rondelimiet_wordt_gemeld(monkeypatch):
    monkeypatch.setattr(W, "MAX_RONDES", 1)
    res = W.plan(_dag(), _accu())
    assert res.rondes == 1 and res.rondelimiet is True and res.resterend


def test_verboden_verkoop_toont_de_echte_vloer():
    ks = [W.Kwartier(T0 + timedelta(minutes=15 * i), 0.1, 0.0, 0.7 if i < 2 else 0.2, 0.7 if i < 2 else 0.2,
                     0.5, verkoop_verboden=(i == 0)) for i in range(8)]
    rijen = W._plan(ks, _accu(inhoud_kwh=3.0, huis_eerst=False, bewaarmarge_eur=0, netladen=False)).kwartieren
    assert rijen[0]["actie"] != "verkopen" and rijen[0]["verkoop_vloer_kwh"] == 0.5
    assert rijen[1]["actie"] == "verkopen"


def test_sturing_attributen_en_waarschuwing(make_coordinator, caplog):
    c = make_coordinator({})
    res = W.plan(_dag(), _accu())
    res.rondelimiet, res.resterend = True, {"verkopen_voor_huis": 2}
    voor = {"kwartieren": _dag(), "accu": _accu(), "bruikbaar": 7.8, "balans": {}}
    c._waardeplan_knip = None
    c.salderingspositie_weergave = lambda: None
    with caplog.at_level("WARNING"):
        uit = c._waardeplan_afronden(T0, voor, res)
        c._waardeplan_afronden(T0 + timedelta(minutes=5), voor, res)
    assert uit["toets_rondelimiet"] is True and uit["toets_resterend"] == {"verkopen_voor_huis": 2}
    assert "toets_rondes" in uit and "eindwaarde_knik_kwh" in uit
    assert sum("rondes staan er nog overtredingen" in r.message for r in caplog.records) == 1


# --- punt 20: het rekenwerk in de executor --------------------------------------

def test_plan_draait_in_de_executor(make_coordinator):
    c = make_coordinator({})
    voor = {"kwartieren": _dag(48), "accu": _accu(), "bruikbaar": 7.8, "balans": {}}
    c._waardeplan_invoer = lambda now, entries: voor
    c._waardeplan_knip = None
    c.salderingspositie_weergave = lambda: None
    gezien = []

    async def executor(func, *args):
        gezien.append(func)
        return func(*args)

    c.hass.async_add_executor_job = executor
    uit = asyncio.run(c._async_bereken_waardeplan(T0, []))
    assert gezien == [W.plan]
    assert uit["beschikbaar"] is True


def test_rekentijd():
    """Gemeten op de reviewdag (144 kwartieren, huis eerst): ruim onder 0,5 s per
    plan op de ontwikkelmachine; hier ruim genomen tegen een trage CI."""
    ks, acc = _dag(), _accu()
    t = time.perf_counter()
    W.plan(ks, acc)
    assert time.perf_counter() - t < 3.0
