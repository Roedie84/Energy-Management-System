"""v5.211.0 (Ruud 11-11 10:18: "Aanzetten"): de snelle zon-correctie stuurt mee."""
from custom_components.energy_management_system import coordinator as C

Coord = C.EnergyManagementSystemCoordinator


def _c(rijen):
    c = Coord.__new__(Coord)
    c.plan_review_history = [
        {"datum": d, "zon": {"voorspeld_kwh": v, "werkelijk_kwh": w, **({"snelle_factor": f} if f else {})}}
        for d, v, w, f in rijen
    ]
    c.learned_pv_hourly_ratio = lambda uur: None
    c._utc_uur = lambda m: 12
    return c


def test_onder_vijf_dagen_geen_correctie():
    c = _c([(f"d{i}", 10.0, 8.0, None) for i in range(4)])
    assert c._pv_snelle_factor() == 1.0


def test_vaste_afwijking_wordt_gecorrigeerd():
    c = _c([(f"d{i}", 10.0, 9.0, None) for i in range(6)])
    assert abs(c._pv_snelle_factor() - 0.9) < 1e-9


def test_begrensd_op_08_en_12():
    assert _c([(f"d{i}", 10.0, 3.0, None) for i in range(6)])._pv_snelle_factor() == 0.8
    assert _c([(f"d{i}", 10.0, 20.0, None) for i in range(6)])._pv_snelle_factor() == 1.2


def test_alleen_de_laatste_vijf_dagen_tellen():
    rijen = [(f"a{i}", 10.0, 5.0, None) for i in range(5)] + [(f"b{i}", 10.0, 10.0, None) for i in range(5)]
    assert _c(rijen)._pv_snelle_factor() == 1.0


def test_rekent_met_de_voorspelling_zonder_eigen_factor():
    """Voorspeld 9 met factor 0,9 = ruw 10; opgewekt 9 -> factor blijft 0,9."""
    c = _c([(f"d{i}", 9.0, 9.0, 0.9) for i in range(6)])
    assert abs(c._pv_snelle_factor() - 0.9) < 1e-9


def test_factor_komt_bovenop_de_geleerde_correctie():
    c = _c([(f"d{i}", 10.0, 9.0, None) for i in range(6)])
    assert abs(c._zon_bias_factor(None, None) - 0.9) < 1e-9
    assert abs(c._zon_bias_factor(None, -10.0) - 0.81) < 1e-9
    c.learned_pv_hourly_ratio = lambda uur: 0.5
    assert abs(c._zon_bias_factor(None, None) - 0.45) < 1e-9


def test_uit_te_zetten(monkeypatch):
    monkeypatch.setattr(C, "PV_SNELLE_CORRECTIE_AAN", False)
    c = _c([(f"d{i}", 10.0, 9.0, None) for i in range(6)])
    assert c._pv_snelle_factor() == 1.0


def test_nieuwe_dag_ververst_de_onthouden_factor():
    c = _c([(f"d{i}", 10.0, 9.0, None) for i in range(6)])
    assert abs(c._pv_snelle_factor() - 0.9) < 1e-9
    c.plan_review_history.append({"datum": "e0", "zon": {"voorspeld_kwh": 10.0, "werkelijk_kwh": 14.0}})
    assert abs(c._pv_snelle_factor() - 1.0) < 1e-9


def test_kapotte_geschiedenis_breekt_niets():
    c = Coord.__new__(Coord)
    c.plan_review_history = [None, {"zon": "x"}, 5]
    assert c._pv_snelle_factor() == 1.0
