"""v5.237.0: de zonverwachting van het plan per uur bewaard (alleen meten).

Ruud 17-11 ("Wel gaan bewaren voor betere resultaten?"): de dagcontrole zag
de planvoorspelling 9,6 % te hoog over 10 dagen, maar kon de uren niet
aanwijzen omdat alleen het dagtotaal werd bewaard.
"""
from datetime import datetime

from custom_components.energy_management_system import zon_per_uur as z
from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)


def test_plankwartieren_worden_uren():
    rijen = [(9, 0.10), (9, 0.12), (9, 0.14), (9, 0.16), (10, 0.2), ("x", 1), (11, None)]
    assert z.plan_per_uur(rijen) == {"9": 0.52, "10": 0.2}


def test_stand_hoort_bij_het_begin_van_het_uur():
    s = z.noteer_stand({}, 9, 0.4)
    s = z.noteer_stand(s, 9, 0.9)  # later in hetzelfde uur: blijft staan
    s = z.noteer_stand(s, 10, 1.1)
    assert s == {"9": 0.4, "10": 1.1}
    assert z.noteer_stand(s, 25, 1.0) == s
    assert z.noteer_stand(s, 11, None) == s


def test_vergelijk_vanaf_de_opname_tot_de_eindstand():
    voorspeld = {"8": 0.2, "9": 0.5, "10": 0.8, "11": 0.9, "12": 0.6}
    standen = {"8": 0.05, "9": 0.2, "10": 0.6, "11": 1.3, "12": 2.0}
    uit = z.vergelijk(voorspeld, standen, 8, 0.05, 2.5)
    assert uit["8"] == {"voorspeld_kwh": 0.2, "werkelijk_kwh": 0.15}
    assert uit["10"]["werkelijk_kwh"] == 0.7
    assert uit["12"]["werkelijk_kwh"] == 0.5  # laatste uur: tot de eindstand
    assert round(sum(x["werkelijk_kwh"] for x in uit.values()), 3) == 2.45


def test_late_opname_begint_bij_de_stand_van_de_opname():
    uit = z.vergelijk({"10": 0.3, "11": 0.9}, {"10": 1.0, "11": 1.5, "12": 2.3}, 10, 1.2, 3.0)
    assert uit["10"]["werkelijk_kwh"] == 0.3  # 1,5 - 1,2, niet 1,5 - 1,0
    assert uit["11"]["werkelijk_kwh"] == 0.8


def test_gemiste_uurgrens_valt_weg_en_vervuilt_de_buren_niet():
    voorspeld = {"9": 0.5, "10": 0.8, "11": 0.9, "12": 0.4}
    standen = {"9": 0.2, "10": 0.6, "12": 2.0}  # 11:00 gemist (herstart)
    uit = z.vergelijk(voorspeld, standen, 8, 0.0, 2.3)
    assert set(uit) == {"9", "12"}
    assert uit["12"]["werkelijk_kwh"] == 0.3


def test_teruglopende_teller_en_lege_invoer():
    assert z.vergelijk({"9": 0.5}, {"9": 1.0, "10": 0.2}, 8, 0.0, 0.2) == {}
    assert z.vergelijk(None, None, None, None, None) == {}
    assert z.vergelijk({"9": 0.5}, {}, 9, None, 1.0) == {}


def _dag(datum, paren):
    return {"datum": datum, "zon": {"voorspeld_kwh": 5, "werkelijk_kwh": 4, "per_uur": {
        str(u): {"voorspeld_kwh": v, "werkelijk_kwh": w} for u, (v, w) in paren.items()}}}


def test_kwaliteit_wijst_het_uur_aan():
    hist = [_dag(f"2026-11-{d:02d}", {10: (0.8, 0.8), 12: (1.0, 0.7), 14: (0.5, 0.45), 16: (0.01, 0.0)})
            for d in range(10, 15)]
    k = z.kwaliteit(hist)
    assert k["beschikbaar"] and k["dagen"] == 5
    assert k["grootste_verschil_uur"] == 12
    assert k["uren"]["12"] == {"dagen": 5, "voorspeld_kwh": 5.0, "werkelijk_kwh": 3.5,
                               "verschil_kwh": -1.5, "bias_procent": -30.0}
    assert "16" not in k["uren"]  # schemer zegt niets
    assert "12:00" in k["duiding"] and "86 %" in k["duiding"]


def test_kwaliteit_zonder_of_met_te_weinig_dagen():
    assert z.kwaliteit([{"datum": "2026-11-01", "zon": {"voorspeld_kwh": 5, "werkelijk_kwh": 4}}])["beschikbaar"] is False
    k = z.kwaliteit([_dag("2026-11-10", {12: (1.0, 0.7)})])
    assert k["beschikbaar"] and k["grootste_verschil_uur"] is None
    assert "te weinig dagen" in k["duiding"]


def test_alleen_de_laatste_tien_dagen():
    hist = [_dag(f"2026-11-{d:02d}", {12: (1.0, 1.0 if d > 5 else 0.0)}) for d in range(1, 16)]
    assert z.kwaliteit(hist)["uren"]["12"]["bias_procent"] == 0.0


def test_plankwaliteit_draagt_de_uren():
    hist = [_dag(f"2026-11-{d:02d}", {12: (1.0, 0.7)}) for d in range(10, 14)]
    k = C._pv_plan_kwaliteit(hist)
    assert k["per_uur"]["uren"]["12"]["bias_procent"] == -30.0


def test_uurstand_komt_in_de_momentopname(make_coordinator):
    c = make_coordinator({})
    c.schedule_persisted_state_save = lambda *a, **k: None
    c.pv_production_today_kwh = 0.4
    c.plan_snapshot = {"datum": "2026-11-17", "pv_uurstanden": {}}
    c._noteer_pv_uurstand(datetime(2026, 11, 17, 9, 0, 30))
    c.pv_production_today_kwh = 0.9
    c._noteer_pv_uurstand(datetime(2026, 11, 17, 9, 30))
    c._noteer_pv_uurstand(datetime(2026, 11, 17, 10, 0, 10))
    assert c.plan_snapshot["pv_uurstanden"] == {"9": 0.4, "10": 0.9}
    # een opname van een andere dag of van voor deze versie blijft ongemoeid
    c._noteer_pv_uurstand(datetime(2026, 11, 18, 9, 0))
    assert "9" in c.plan_snapshot["pv_uurstanden"] and len(c.plan_snapshot["pv_uurstanden"]) == 2
    c.plan_snapshot = {"datum": "2026-11-17"}
    c._noteer_pv_uurstand(datetime(2026, 11, 17, 11, 0))
    assert "pv_uurstanden" not in c.plan_snapshot


def test_plan_per_uur_uit_planregels_in_lokale_tijd():
    plan = [{"start": "2026-11-17T08:00:00+00:00", "zon_kwh": 0.1},
            {"start": "2026-11-17T08:15:00+00:00", "zon_kwh": 0.2},
            {"start": "2026-11-17T09:00:00+00:00", "zon_kwh": 0.3}, {"start": None, "zon_kwh": 9}]
    uit = C._plan_zon_per_uur(plan)
    assert list(uit.values()) == [0.3, 0.3] and len(uit) == 2
