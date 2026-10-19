"""v5.103: eigen laad-/ontlaadteller uit de lokale lezing van de accu."""
from datetime import datetime, timezone

from custom_components.energy_management_system import accuteller as A
from custom_components.energy_management_system import zendure_lokaal as Z
from custom_components.energy_management_system.meetlaag import Meetlaag


def _lees(teller, t, laden=0.0, ontladen=0.0):
    A.integreer(teller, {"outputPackPower": laden, "packInputPower": ontladen,
                         "gridInputPower": laden * 1.05, "outputHomePower": ontladen * 0.95}, t)


def test_integreert_vermogen_naar_kwh():
    t = A.leeg()
    for i in range(1801):           # een uur, elke 2 s, 1000 W laden
        _lees(t, 2.0 * i, laden=1000.0)
    assert abs(t["kwh"]["pack_laden"] - 1.0) < 1e-6
    assert abs(t["kwh"]["ac_laden"] - 1.05) < 1e-6
    assert t["kwh"]["pack_ontladen"] == 0.0 and t["gaten"] == 0


def test_een_gat_wordt_niet_opgevuld():
    t = A.leeg()
    _lees(t, 0.0, laden=1000.0)
    _lees(t, 100.0, laden=1000.0)   # 100 s geen lezing
    assert t["kwh"]["pack_laden"] == 0.0 and t["gaten"] == 1 and t["gat_s"] == 100.0
    _lees(t, 102.0, laden=1000.0)
    assert t["kwh"]["pack_laden"] > 0


def test_standen_alleen_vers():
    t = A.leeg()
    _lees(t, 1000.0, laden=500.0)
    assert A.standen(t, 1010.0)["pack"] == {"battery_in": 0.0, "battery_out": 0.0}
    assert A.standen(t, 1000.0 + A.VERS_S + 1) is None
    assert A.standen(None, 0.0) is None


def test_deltas_en_teruglopen():
    b = {"pack": {"battery_in": 1.0, "battery_out": 2.0}, "ac": {"battery_in": 1.0, "battery_out": 2.0}}
    e = {"pack": {"battery_in": 1.2, "battery_out": 2.0}, "ac": {"battery_in": 0.5, "battery_out": 2.0}}
    d = A.deltas(b, e)
    assert set(d) == {"pack"} and abs(d["pack"]["battery_in"] - 0.2) < 1e-9
    assert A.deltas(None, e) is None


def test_beste_koppeling_pas_na_een_dag_en_binnen_de_marge():
    v = A.lege_vergelijking()
    for _ in range(A.MIN_KWARTIEREN - 1):
        A.vergelijk_kwartier(v, {"battery_in": 0.1, "battery_out": 0.0},
                             {"pack": {"battery_in": 0.101, "battery_out": 0.0},
                              "ac": {"battery_in": 0.12, "battery_out": 0.0}})
    assert A.beste_koppeling(v) is None
    assert "vergelijkt nog" in A.samenvatting(A.leeg(), v)["oordeel"]
    A.vergelijk_kwartier(v, {"battery_in": 0.1, "battery_out": 0.0},
                         {"pack": {"battery_in": 0.101, "battery_out": 0.0},
                          "ac": {"battery_in": 0.12, "battery_out": 0.0}})
    assert A.beste_koppeling(v) == "pack"
    s = A.samenvatting(A.leeg(), v, 3)
    assert s["betrouwbare_koppeling"] == "pack" and s["per_koppeling"]["ac"]["afwijking_procent"] == 20.0
    assert s["kwartieren_ingevuld"] == 3 and s["oordeel"].startswith("betrouwbaar (pack")


def test_geen_koppeling_als_beide_te_ver_af_liggen():
    v = A.lege_vergelijking()
    for _ in range(A.MIN_KWARTIEREN):
        A.vergelijk_kwartier(v, {"battery_in": 0.1, "battery_out": 0.0},
                             {"pack": {"battery_in": 0.2, "battery_out": 0.0},
                              "ac": {"battery_in": 0.0, "battery_out": 0.0}})
    assert A.beste_koppeling(v) is None
    assert "vult niets in" in A.samenvatting(None, v)["oordeel"]


def test_tellingen_en_herstel_houden_de_eigen_teller():
    basis = Z.lege_tellingen()
    assert "eigen_teller" in basis and "teller_vergelijking" in basis
    bewaard = {**basis, "eigen_teller": {**A.leeg(), "kwh": {"pack_laden": 12.5}}}
    assert Z.herstel(bewaard)["eigen_teller"]["kwh"]["pack_laden"] == 12.5


class _Lokaal:
    def __init__(self, koppeling=None):
        self.koppeling, self.vergeleken, self.ingevuld = koppeling, [], 0

    def vergelijk_teller(self, zendure, eigen):
        self.vergeleken.append((zendure, eigen))

    def betrouwbare_koppeling(self):
        return self.koppeling

    def noteer_ingevuld(self):
        self.ingevuld += 1


def _st(w, vers=True):
    return {"waarde": w, "vers": vers, "leeftijd_s": 5}


GRENS = datetime(2026, 10, 19, 10, 0, tzinfo=timezone.utc)
BEGIN = {"grid_import": _st(100.0), "grid_export": _st(50.0), "pv": _st(10.0),
         "battery_out": _st(20.0), "battery_in": _st(30.0)}
EIGEN_B = {"pack": {"battery_in": 5.0, "battery_out": 7.0}, "ac": {"battery_in": 5.0, "battery_out": 7.0}}
EIGEN_E = {"pack": {"battery_in": 5.3, "battery_out": 7.0}, "ac": {"battery_in": 5.32, "battery_out": 7.0}}


def test_meetlaag_vergelijkt_als_de_zendure_teller_er_is():
    from custom_components.energy_management_system import kwartierenergie

    eind = {**BEGIN, "grid_import": _st(100.4), "battery_in": _st(30.3)}
    record = kwartierenergie.kwartier(GRENS, BEGIN, eind, 0.3)
    lokaal = _Lokaal("pack")
    uit = Meetlaag._met_eigen_accuteller(lokaal, record, (GRENS, BEGIN, eind, 0.3), EIGEN_B, EIGEN_E)
    assert uit is record and len(lokaal.vergeleken) == 1 and lokaal.ingevuld == 0


def test_meetlaag_vult_in_als_de_zendure_teller_ontbreekt():
    from custom_components.energy_management_system import kwartierenergie

    eind = {**BEGIN, "grid_import": _st(100.4), "battery_in": _st(None)}
    record = kwartierenergie.kwartier(GRENS, BEGIN, eind, 0.3)
    assert record["battery_in_kwh"] is None and record["house_kwh"] is None
    # nog geen betrouwbare koppeling: niets invullen
    assert Meetlaag._met_eigen_accuteller(_Lokaal(None), record, (GRENS, BEGIN, eind, 0.3), EIGEN_B, EIGEN_E) is record
    lokaal = _Lokaal("pack")
    uit = Meetlaag._met_eigen_accuteller(lokaal, record, (GRENS, BEGIN, eind, 0.3), EIGEN_B, EIGEN_E)
    assert abs(uit["battery_in_kwh"] - 0.3) < 1e-9 and uit["battery_out_kwh"] == 0.0
    assert uit["kwaliteit_per_teller"]["battery_in"] == "partially_estimated" and uit["accu_bron"] == "pack"
    assert abs(uit["house_kwh"] - (0.4 - 0.3)) < 1e-9 and lokaal.ingevuld == 1


def test_meetlaag_zonder_eigen_standen_ongewijzigd():
    record = {"kwaliteit_per_teller": {}}
    assert Meetlaag._met_eigen_accuteller(_Lokaal("pack"), record, (GRENS, BEGIN, BEGIN, None), None, EIGEN_E) is record
    assert Meetlaag._met_eigen_accuteller(None, record, (GRENS, BEGIN, BEGIN, None), EIGEN_B, EIGEN_E) is record
