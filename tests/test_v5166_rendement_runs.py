"""v5.166.0 - rendement per vermogensband over hele laad-/ontlaadrondes.

Akkoord Ruud 02-11 21:49. De Zendure meldt de SoC in stappen van 1 % =
0,1152 kWh. Per kwartier telde een kwartier alleen mee als de inhoud
bewoog: bij 240 W (60 Wh per kwartier) alleen de kwartieren MET stap, en
dan 60 Wh tegen 115 Wh. Gemeten (AC-teller tegen SoC x 11,52): ontladen
~100 %, laden ~80 %. Live meldde de kwartiermethode 68 / 74 %.
"""
import math
from datetime import datetime, timedelta

import pytest

from custom_components.energy_management_system import accukosten as A

STAP = 0.1152          # 1 % van 11,52 kWh
DAG0 = datetime(2026, 10, 24, 0, 0)


def _kwartieren(segmenten, inhoud0=5.0, begin=DAG0):
    """segmenten: [(aantal_kwartieren, accu_w, eta)], accu_w > 0 = ontladen.

    Bouwt dagverloop-regels met een SoC in stappen van 1 % (afgerond naar
    beneden, zoals een SoC-sensor) en de meetlaag (AC-kWh per kwartier), en
    haalt ze door `kwartierreeks` zoals de coordinator dat doet.
    """
    echt = inhoud0
    t = begin
    regels: dict = {}
    gemeten: dict = {}

    def _regel(moment, accu_w):
        dag = moment.date().isoformat()
        tijd = moment.strftime("%H:%M")
        soc = math.floor(echt / STAP + 1e-9)
        regels.setdefault(dag, []).append(
            {"tijd": tijd, "beschikbaar_kwh": round(soc * STAP, 4), "accu_w": accu_w, "soc": soc})
        gemeten.setdefault(dag, {})[tijd] = {"accu_kwh": accu_w / 4000}

    _regel(t, 0.0)
    for n, accu_w, eta in segmenten:
        for _ in range(n):
            t += timedelta(minutes=15)
            ac = abs(accu_w) / 4000
            echt += -ac / eta if accu_w > 0 else ac * eta
            _regel(t, accu_w)
    return A.kwartierreeks(regels, gemeten)


def _oude_methode(reeks):
    """De kwartiermethode van v5.122.0-v5.165.0, ter vergelijking."""
    som = {"laden": [0.0, 0.0], "ontladen": [0.0, 0.0]}
    for q in reeks:
        a, d = q["accu_kwh"], q["delta_kwh"]
        if abs(a) < A.BAND_MIN_KWARTIER_KWH:
            continue
        if a < 0 < d:
            eta, sleutel, teller, noemer = d / -a, "laden", d, -a
        elif a > 0 > d:
            eta, sleutel, teller, noemer = a / -d, "ontladen", a, -d
        else:
            continue
        if A.BAND_RENDEMENT_MIN <= eta <= A.BAND_RENDEMENT_MAX + 0.1:
            som[sleutel][0] += teller
            som[sleutel][1] += noemer
    return {k: (v[0] / v[1] if v[1] else None) for k, v in som.items()}


def _rondes_met_pauze(n_rondes, kwartieren, accu_w, eta):
    """Rondes van `kwartieren` lang, met een uur stilstand ertussen."""
    seg = []
    for _ in range(n_rondes):
        seg += [(kwartieren, accu_w, eta), (4, 0.0, 1.0)]
    return seg


def test_ontladen_240_w_is_100_procent_niet_de_kwartierselectie():
    reeks = _kwartieren(_rondes_met_pauze(10, 16, 240.0, 1.0), inhoud0=10.0)
    oud = _oude_methode(reeks)["ontladen"]
    assert oud == pytest.approx(0.52, abs=0.03)   # 60 Wh tegen een stap van 115 Wh
    b = A.rendement_per_band(reeks)["ontladen"]["<500 W"]
    assert b["rendement_procent"] == pytest.approx(100.0, abs=4.0)
    assert b["kwartieren"] == 160
    assert b["betrouwbaar"] is True         # 160 kwartieren, ~9,6 kWh


def test_ontladen_1000_w_is_100_procent():
    reeks = _kwartieren(_rondes_met_pauze(6, 8, 1000.0, 1.0), inhoud0=11.0)
    b = A.rendement_per_band(reeks)["ontladen"]["500-1500 W"]
    assert b["rendement_procent"] == pytest.approx(100.0, abs=4.0)
    assert b["kwartieren"] == 48 and b["betrouwbaar"] is True


def test_ontladen_wisselend_vermogen_rond_de_stap():
    # het huis dekken: 150-400 W door elkaar, echt rendement 1,0
    seg = []
    for i in range(12):
        seg += [(4, 150.0, 1.0), (4, 400.0, 1.0), (4, 250.0, 1.0), (4, 0.0, 1.0)]
    reeks = _kwartieren(seg, inhoud0=11.0)
    assert _oude_methode(reeks)["ontladen"] < 0.85
    b = A.rendement_per_band(reeks)["ontladen"]["<500 W"]
    assert b["rendement_procent"] == pytest.approx(100.0, abs=4.0)


def test_laden_1400_w_is_80_procent():
    reeks = _kwartieren(_rondes_met_pauze(5, 8, -1400.0, 0.80), inhoud0=0.5)
    b = A.rendement_per_band(reeks)["laden"]["500-1500 W"]
    assert b["rendement_procent"] == pytest.approx(80.0, abs=3.0)
    assert b["betrouwbaar"] is True         # 40 kwartieren, 14 kWh
    assert A.laadrendement_uit_banden(A.rendement_per_band(reeks)) == pytest.approx(0.80, abs=0.03)


def test_een_gat_splitst_de_ronde():
    seg = [(6, 240.0, 1.0)]
    reeks = _kwartieren(seg, inhoud0=8.0)
    reeks2 = _kwartieren(seg, inhoud0=7.0, begin=DAG0 + timedelta(hours=5))
    rondes = A.laad_ontlaadrondes(reeks + reeks2)
    assert len(rondes) == 2
    assert all(r["kwartieren"] == 6 for r in rondes)


def test_korte_rondes_tellen_niet():
    # 4 kwartieren x 60 Wh = 0,24 kWh < RONDE_MIN_KWH
    reeks = _kwartieren(_rondes_met_pauze(20, 4, 240.0, 1.0), inhoud0=8.0)
    assert len(A.laad_ontlaadrondes(reeks)) == 20
    b = A.rendement_per_band(reeks)["ontladen"]["<500 W"]
    assert b["kwartieren"] == 0
    assert b["rendement_procent"] is None
    assert b["betrouwbaar"] is False


def test_omdraaien_voegt_niet_samen():
    reeks = _kwartieren([(8, -1400.0, 0.8), (8, 1000.0, 1.0)], inhoud0=3.0)
    rondes = A.laad_ontlaadrondes(reeks)
    assert [r["richting"] for r in rondes] == ["laden", "ontladen"]
    assert [r["kwartieren"] for r in rondes] == [8, 8]


def test_uitvoer_structuur_ongewijzigd():
    uit = A.rendement_per_band(_kwartieren([(8, 1000.0, 1.0)], inhoud0=5.0))
    assert set(uit) == {"laden", "ontladen"}
    for richting in uit.values():
        assert tuple(richting) == A.BAND_NAMEN
        for band in richting.values():
            assert set(band) == {"kwartieren", "kwh", "rendement_procent", "betrouwbaar"}
    assert A.rendement_per_band([]) == {
        r: {n: {"kwartieren": 0, "kwh": 0.0, "rendement_procent": None, "betrouwbaar": False}
            for n in A.BAND_NAMEN} for r in ("laden", "ontladen")}


def test_betrouwbaarheidseisen_blijven():
    # 36 kwartieren < BAND_MIN_KWARTIEREN (40), ruim genoeg kWh
    reeks = _kwartieren(_rondes_met_pauze(3, 12, 2000.0, 1.0), inhoud0=11.5)
    b = A.rendement_per_band(reeks)["ontladen"][">1500 W"]
    assert b["kwartieren"] == 36 and b["kwh"] >= A.BAND_MIN_KWH
    assert b["betrouwbaar"] is False
    reeks = _kwartieren(_rondes_met_pauze(4, 12, 2000.0, 1.0), inhoud0=11.5)
    # 48 kwartieren, maar de accu raakt leeg - neem een tweede dag
    reeks += _kwartieren(_rondes_met_pauze(1, 12, 2000.0, 1.0), inhoud0=11.5, begin=DAG0 + timedelta(days=1))
    b = A.rendement_per_band(reeks)["ontladen"][">1500 W"]
    assert b["kwartieren"] >= 40 and b["betrouwbaar"] is True


def test_ronde_boven_100_procent_telt_mee_uitkomst_afgekapt():
    # SoC-stap laat een ronde licht boven 1,0 uitkomen; niet weggooien
    r = {"richting": "ontladen", "kwartieren": 8, "ac_kwh": 0.48, "delta_kwh": -0.4608}
    assert A._ronde_meting(r) is not None                 # 1,04
    r_fout = {"richting": "ontladen", "kwartieren": 8, "ac_kwh": 0.48, "delta_kwh": -0.2}
    assert A._ronde_meting(r_fout) is None                # 2,4: meetfout
    reeks = _kwartieren(_rondes_met_pauze(10, 16, 240.0, 1.06), inhoud0=10.0)
    # v5.169.0: ontladen (inhoud -> AC) niet meer op 100 % afgekapt maar op
    # 120 %: de gesimuleerde 1,06 komt (met de SoC-stap) als ~106 % door
    assert A.rendement_per_band(reeks)["ontladen"]["<500 W"]["rendement_procent"] == pytest.approx(106.0, abs=1.5)


def test_laadrendement_uit_banden_alleen_betrouwbaar():
    banden = {"laden": {
        "<500 W": {"kwh": 2.0, "rendement_procent": 60.0, "betrouwbaar": False},
        "500-1500 W": {"kwh": 10.0, "rendement_procent": 80.0, "betrouwbaar": True},
        ">1500 W": {"kwh": 30.0, "rendement_procent": 84.0, "betrouwbaar": True},
    }}
    assert A.laadrendement_uit_banden(banden) == pytest.approx(0.83)
    assert A.laadrendement_uit_banden({"laden": {}}) is None
    assert A.laadrendement_uit_banden(None) is None


def test_waardeplan_laadt_met_de_laadbanden(make_coordinator):
    c = make_coordinator({})
    c.laadcorrectie_ct = lambda: 0.0
    c.charge_efficiency_history = [86.3, 86.3, 86.3]
    c.get_rendement_per_band = lambda now=None: {
        "laden": {">1500 W": {"kwh": 20.0, "rendement_procent": 79.8, "betrouwbaar": True}},
        "ontladen": {"<500 W": {"kwh": 10.0, "rendement_procent": 100.0, "betrouwbaar": True}},
    }
    uit = c._waardeplan_rendementen(DAG0)
    assert uit["rendement_laden"] == pytest.approx(0.798)
    assert uit["ontlaadbanden"][0] == (500.0, 1.0)
    # zonder betrouwbare laadband: het geleerde laadrendement
    c.get_rendement_per_band = lambda now=None: {"laden": {}, "ontladen": {}}
    assert c._waardeplan_rendementen(DAG0)["rendement_laden"] == pytest.approx(0.863)
