"""v5.212.0 (Ruud 11-11 11:14, akkoord): live toets op het gemeten verbruik.

11-11 11:03-11:15: het plan rekende met 0,9 kW en hield de accu vast; het huis
gebruikte 1,7-2,2 kW en er kwam 1,3 kW uit het net tegen 57,3 ct, terwijl
dekken bij dat vermogen meer waard was dan de inhoud bewaren.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import coordinator as C

TZ = timezone(timedelta(hours=1))
T0 = datetime(2026, 11, 11, 11, 3, 0, tzinfo=TZ)
BANDEN = [{"tot_w": 500.0, "rendement_procent": 99.0}, {"tot_w": 1500.0, "rendement_procent": 106.1},
          {"tot_w": None, "rendement_procent": 101.8}]


class Coord(C.EnergyManagementSystemCoordinator):
    learned_discharge_efficiency_percent = 100.0
    learned_battery_efficiency_percent = 84.2

    def __init__(self):  # noqa: D401 - kale testversie
        self.tekort_w = 1300.0
        self.leeg = False
        self.waardeplan_herplanningen = None

    def _overschot_toestand(self):
        return {"overschot_w": None if self.tekort_w is None else -self.tekort_w}

    def slimme_ontlaadgrens_w(self):
        return 2400.0

    def _waardeplan_accu_leeg(self, now):
        return self.leeg

    def _waardeplan_slijtage_ct(self):
        return 1.7


def _plan(lam=0.4307, prijs=0.462):
    return {"ontlaadbanden": BANDEN, "nu": {"rekenprijs_eur": prijs, "waarde_inhoud_eur_per_kwh": lam}}


def _loop(c, actie, start=T0, stappen=6, plan=None):
    uit = []
    for i in range(stappen):
        p = plan or _plan()
        uit.append(c._live_toets(start + timedelta(seconds=30 * i), p, p, actie))
    return uit


def test_het_geval_van_11_november_wisselt_na_twee_minuten():
    c = Coord()
    uit = _loop(c, "houden")
    assert uit[:4] == ["houden"] * 4          # 0, 30, 60, 90 s
    assert uit[4:] == ["huis", "huis"]        # vanaf 120 s
    assert c.waardeplan_herplanningen["live_wissel"] == 1
    assert c.waardeplan_herplanningen["live_wissel_eur"] > 0.005


def test_bij_het_verwachte_kleine_tekort_blijft_houden():
    """472 W: de slechtste band (99 %), dekken is minder waard dan bewaren."""
    c = Coord()
    c.tekort_w = 472.0
    assert _loop(c, "houden") == ["houden"] * 6


def test_een_korte_piek_wisselt_niet():
    c = Coord()
    p = _plan()
    assert c._live_toets(T0, p, p, "houden") == "houden"
    assert c._live_toets(T0 + timedelta(seconds=60), p, p, "houden") == "houden"
    c.tekort_w = 300.0
    assert c._live_toets(T0 + timedelta(seconds=90), p, p, "houden") == "houden"
    c.tekort_w = 1300.0
    assert c._live_toets(T0 + timedelta(seconds=120), p, p, "houden") == "houden"   # opnieuw begonnen
    assert c._live_toets(T0 + timedelta(seconds=240), p, p, "houden") == "huis"


def test_hooguit_een_wissel_per_kwartier_en_daarna_weer_het_plan():
    c = Coord()
    _loop(c, "houden")
    c.tekort_w = 100.0
    p = _plan()
    assert c._live_toets(T0 + timedelta(minutes=5), p, p, "houden") == "huis"      # blijft dit kwartier
    assert p["live_toets"]["gewisseld"] is True
    assert c._live_toets(T0 + timedelta(minutes=13), p, p, "houden") == "houden"   # 11:16: nieuw kwartier


def test_van_huis_naar_houden_als_dekken_te_weinig_oplevert():
    """Plan dekt het huis; in werkelijkheid een klein tekort en dure inhoud."""
    c = Coord()
    c.tekort_w = 450.0
    uit = _loop(c, "huis", plan=_plan(lam=0.52))
    assert uit[-1] == "houden"


def test_te_weinig_voordeel_aan_het_eind_van_het_kwartier():
    c = Coord()
    uit = _loop(c, "houden", start=T0.replace(minute=13, second=30), stappen=3)
    assert uit == ["houden"] * 3


def test_lege_accu_gaat_niet_dekken():
    c = Coord()
    c.leeg = True
    assert _loop(c, "houden") == ["houden"] * 6


def test_zonder_meting_of_zonder_waarde_geldt_het_plan():
    c = Coord()
    c.tekort_w = None
    assert _loop(c, "houden") == ["houden"] * 6
    c.tekort_w = 1300.0
    p = {"ontlaadbanden": BANDEN, "nu": {"rekenprijs_eur": 0.46}}
    assert _loop(c, "houden", plan=p) == ["houden"] * 6


def test_andere_acties_blijven_van_het_plan():
    c = Coord()
    for actie in ("verkopen", "laden_net", "zon_export", "zon"):
        assert _loop(c, actie) == [actie] * 6


def test_zonoverschot_wisselt_niets():
    c = Coord()
    c.tekort_w = -400.0
    assert _loop(c, "houden") == ["houden"] * 6


def test_dekwaarde_per_band():
    c = Coord()
    p = _plan()
    laag = c._live_dekwaarde(p, p["nu"], 472.0)[0]
    midden = c._live_dekwaarde(p, p["nu"], 1300.0)[0]
    hoog = c._live_dekwaarde(p, p["nu"], 1700.0)[0]
    assert round(laag, 4) == round(0.462 * 0.99 - 0.017, 4)
    assert round(midden, 4) == round(0.462 * 1.061 - 0.017, 4)
    assert round(hoog, 4) == round(0.462 * 1.018 - 0.017, 4)


def test_onbetrouwbare_band_valt_terug_op_het_gemeten_ontlaadrendement():
    c = Coord()
    p = {"ontlaadbanden": [{"tot_w": None, "rendement_procent": None}], "nu": {"rekenprijs_eur": 0.5}}
    assert c._live_dekwaarde(p, p["nu"], 1000.0) == (0.5 * 1.0 - 0.017, 1.0)
