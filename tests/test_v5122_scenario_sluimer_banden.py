"""v5.122.0 (23-10, "Wat verbetert toepassen"): punten 2, 4 en 7.

2. Plan gewogen over drie scenario's: proefstandkandidaat, stuurt niets.
4. Sluimerverbruik van de Zendure per stilstand-uur: alleen meten.
7. Rendement per vermogensband: in de nacalculatie (en zo de datacorrectie)
   zodra een band betrouwbaar is, anders het gemiddelde.
"""
from datetime import datetime, timedelta

import pytest

from custom_components.energy_management_system import accukosten as A
from custom_components.energy_management_system import vooruitplan as V


# --- punt 2 -------------------------------------------------------------------

def _dag(n=96, reserve=3.0, zon=0.6, duur=0.40, goedkoop=0.20):
    kw = []
    for i in range(n):
        h = (i // 4) % 24
        prijs = duur if 17 <= h < 21 else goedkoop
        kw.append({"zon_kwh": zon if 10 <= h < 15 else 0.0, "verbruik_kwh": 0.12,
                   "import_eur": prijs, "export_eur": prijs, "reserve_kwh": reserve})
    return kw


ARG = dict(laad_kwh=0.6, ontlaad_kwh=0.6, rendement=0.85, slijtage_eur=0.03)


def test_verkopen_nooit_onder_de_reserve():
    kw = {"zon": (0, 0, 0), "verbruik": (0.1, 0.1, 0.1), "reserve_kwh": 3.0,
          "import_eur": 0.4, "export_eur": 0.4}
    s2, net, uit = V.stap_modus("verkopen", 3.2, kw, 1, cap=8.0, laad_kwh=0.6, ontlaad_kwh=0.6, rendement=0.85)
    # 0,1 voor het huis mag (ook onder de reserve), verkopen alleen tot de reserve
    assert s2 == pytest.approx(3.0)
    assert uit == pytest.approx(0.2)
    s2, _net, _uit = V.stap_modus("verkopen", 2.0, kw, 1, cap=8.0, laad_kwh=0.6, ontlaad_kwh=0.6, rendement=0.85)
    assert s2 == pytest.approx(1.9)   # alleen het huis


def test_scenarioplan_verkoopt_nooit_onder_de_reserve_in_geen_enkel_scenario():
    kw = _dag(reserve=4.0)
    opt = V.optimaliseer_scenarios(kw, 6.0, 8.0, **ARG)
    assert opt["beschikbaar"]
    for k in range(3):
        s = 6.0
        for q, m in zip(V.scenario_kwartieren(kw), opt["modi"]):
            voor = s
            s, net, uit = V.stap_modus(m, s, q, k, cap=8.0, laad_kwh=0.6, ontlaad_kwh=0.6, rendement=0.85)
            tekort = max(0.0, q["verbruik"][k] - q["zon"][k])
            if uit > tekort + 1e-9:   # er werd verkocht
                assert s >= q["reserve_kwh"] - 1e-9 or s >= voor


def test_eindwaarde_is_de_laagste_inkoop_min_slijtage():
    assert V.eindwaarde_laagste_inkoop(_dag(), 0.03) == pytest.approx(0.17)


def test_scenarioplan_is_niet_slechter_dan_het_plan():
    kw = _dag()
    uit = V.vergelijk_scenarios(kw, 4.0, ["smart"] * len(kw), 8.0, **ARG)
    assert uit["beschikbaar"]
    # het DP kiest per stand de beste modus; als vaste reeks langs de mediaan
    # hoort hij niet duidelijk slechter te zijn dan alleen "smart"
    assert uit["verschil_eur"] >= -0.05
    assert len(uit["plan_per_scenario_eur"]) == 3


def test_band_uit_de_voorspelling_wordt_gebruikt():
    kw = [{"zon_kwh": 1.0, "verbruik_kwh": 0.1, "import_eur": 0.2, "export_eur": 0.2,
           "zon_p10_kwh": 0.2, "zon_p90_kwh": 1.5}]
    s = V.scenario_kwartieren(kw)[0]
    assert s["zon"] == (0.2, 1.0, 1.5)
    assert s["verbruik"][0] == pytest.approx(0.11)
    assert V.scenario_kwartieren([{**kw[0], "zon_p10_kwh": None, "zon_p90_kwh": None}])[0]["zon"] == (0.6, 1.0, 1.3)


def test_plan_modi_worden_vertaald():
    assert V.PLAN_MODUS["manual (verkopen)"] == "verkopen"
    assert V.PLAN_MODUS["smart_discharging"] == "uitstellen"


def test_kandidaat_scenarioplan(make_coordinator):
    c = make_coordinator({})
    c.vooruitplan_history = []
    k = c._kandidaat_scenarioplan()
    assert k["zou_hebben_opgeleverd"]["te_becijferen"] is False
    c.vooruitplan_history = [
        {"dag": f"2026-10-{d:02d}", "scenario": {"verschil_eur": 0.1 * (d % 3), "kwartieren_anders": 5}}
        for d in range(1, 21)
    ]
    k = c._kandidaat_scenarioplan()
    assert k["zou_hebben_opgeleverd"]["te_becijferen"] is True
    assert k["zou_hebben_opgeleverd"]["dagen"] == 20
    namen = [x["naam"] for x in c._bereken_proefstand()["kandidaten"]]
    assert "Plan gewogen over drie scenario's" in namen


# --- punten 4 en 7: meetreeks ---------------------------------------------------

def _verloop(rijen):
    """rijen: (tijd, beschikbaar, accu_w, soc, stand)"""
    return {"2026-10-20": [
        {"tijd": t, "beschikbaar_kwh": b, "accu_w": w, "soc": s, "stand": st, "reden": ""}
        for t, b, w, s, st in rijen
    ]}


def _tijden(n, begin=0):
    start = datetime(2026, 10, 20, 0, 0) + timedelta(minutes=15 * begin)
    return [(start + timedelta(minutes=15 * i)).strftime("%H:%M") for i in range(n)]


def test_sluimer_bij_sparen_uit_de_cellen():
    tijden = _tijden(40)
    rijen = [(t, 5.0 - 0.005 * i, 0.0, 50, "smart_charging (sparen)") for i, t in enumerate(tijden)]
    reeks = A.kwartierreeks(_verloop(rijen))
    uit = A.sluimerverbruik(reeks, 10, 100)
    sp = uit["per_stand"]["sparen"]
    assert sp["uren"] == pytest.approx(39 / 4, abs=0.1)
    assert sp["gemiddeld_w"] == pytest.approx(20.0, abs=0.5)
    assert sp["betrouwbaar"] is True


def test_sluimer_bij_vol_uit_het_net():
    tijden = _tijden(20)
    rijen = [(t, 8.0, -24.0, 100, "smart") for t in tijden]   # 24 W van het net, inhoud gelijk
    uit = A.sluimerverbruik(A.kwartierreeks(_verloop(rijen)), 10, 100)
    vol = uit["per_stand"]["vol"]
    assert vol["gemiddeld_w"] == pytest.approx(24.0, abs=0.5)
    assert vol["betrouwbaar"] is False   # nog geen zes uur


def test_meetlaag_gaat_voor_het_vermogen():
    tijden = _tijden(3)
    rijen = [(t, 8.0, 0.0, 100, "smart") for t in tijden]
    gemeten = {"2026-10-20": {tijden[1]: {"accu_kwh": -0.006}, tijden[2]: {"accu_kwh": -0.006}}}
    reeks = A.kwartierreeks(_verloop(rijen), gemeten)
    assert all(q["bron"] == "meetlaag" for q in reeks)
    assert A.sluimerverbruik(reeks, 10, 100)["per_stand"]["vol"]["gemiddeld_w"] == pytest.approx(24.0, abs=0.5)


def _laad_ontlaad_reeks(n, laad_w, ontlaad_w, eta_l, eta_o):
    uit = []
    for i in range(n):
        uit.append({"delta_kwh": laad_w / 4000 * eta_l, "accu_kwh": -laad_w / 4000, "soc": 50,
                    "stand": "manual", "reden": "", "dag": "d", "tijd": "t", "bron": "meetlaag"})
        uit.append({"delta_kwh": -ontlaad_w / 4000 / eta_o, "accu_kwh": ontlaad_w / 4000, "soc": 50,
                    "stand": "smart", "reden": "", "dag": "d", "tijd": "t", "bron": "meetlaag"})
    return uit


def test_rendement_per_band():
    reeks = _laad_ontlaad_reeks(50, 2000, 300, 0.95, 0.85) + _laad_ontlaad_reeks(60, 2000, 2200, 0.95, 0.93)
    banden = A.rendement_per_band(reeks)
    assert banden["ontladen"]["<500 W"]["rendement_procent"] == pytest.approx(85.0, abs=0.2)
    assert banden["ontladen"][">1500 W"]["rendement_procent"] == pytest.approx(93.0, abs=0.2)
    assert banden["ontladen"]["<500 W"]["betrouwbaar"] is False   # 50 x 0,088 kWh = 4,4 kWh < 5
    assert banden["ontladen"][">1500 W"]["betrouwbaar"] is True
    assert banden["laden"][">1500 W"]["rendement_procent"] == pytest.approx(95.0, abs=0.2)
    # terugval zolang een band niet betrouwbaar is
    assert A.band_rendement(banden, "ontladen", 300, 0.9) == 0.9
    assert A.band_rendement(banden, "ontladen", 2200, 0.9) == pytest.approx(0.93, abs=0.002)
    afw = A.afweging_huis_of_verkopen(banden, 300, 2400, 0.9)
    assert afw["verkopen_rendement_procent"] == pytest.approx(93.0, abs=0.2)
    assert afw["huis_dekken_rendement_procent"] == pytest.approx(90.0)


def test_meetfouten_tellen_niet():
    reeks = [{"delta_kwh": 0.5, "accu_kwh": -0.1, "soc": 50, "stand": "", "reden": ""}]   # rendement 500 %
    assert A.rendement_per_band(reeks)["laden"]["<500 W"]["kwartieren"] == 0


def test_doorreken_gebruikt_de_band(monkeypatch):
    """Ontladen bij een betrouwbare band rekent met dat rendement."""
    tijden = _tijden(8)
    rijen = []
    inhoud = 2.0
    for i, t in enumerate(tijden):
        if i < 4:
            w = -2000.0
            inhoud += 0.5 * 0.95 if i else 0.0
        else:
            w = 2200.0
            inhoud -= 0.55 / 0.93
        rijen.append({"tijd": t, "beschikbaar_kwh": inhoud, "accu_w": w, "net_w": 2000.0 if i < 4 else 0.0,
                      "huis_w": 300.0, "pv_w": 0.0, "prijs_ct": 20.0 if i < 4 else 40.0, "reden": "grid_charging"})
    verloop = {"2026-10-20": rijen}
    zonder = A.doorreken(verloop, 0.95, 0.80, 0.0)
    banden = {"ontladen": {">1500 W": {"betrouwbaar": True, "rendement_procent": 93.0}}, "laden": {}}
    met = A.doorreken(verloop, 0.95, 0.80, 0.0, banden=banden)
    assert met["net"]["ontladen_kwh"] > zonder["net"]["ontladen_kwh"]


def test_coordinator_sluimer_en_banden(make_coordinator):
    c = make_coordinator({})
    tijden = _tijden(30)
    c.dagverloop = _verloop([(t, 5.0 - 0.005 * i, 0.0, 50, "smart_charging (sparen)") for i, t in enumerate(tijden)])
    c._gemeten_kwartieren = lambda dag: {}
    c._bovengrens_procent = lambda: 100.0
    uit = c.get_sluimerverbruik(datetime(2026, 10, 21, 8, 0))
    assert uit["per_stand"]["sparen"]["gemiddeld_w"] == pytest.approx(20.0, abs=0.5)
    assert uit["dagen"] == 1
    assert "laden" in c.get_rendement_per_band(datetime(2026, 10, 21, 8, 0))
