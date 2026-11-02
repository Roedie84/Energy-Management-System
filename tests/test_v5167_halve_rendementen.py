"""v5.167.0 punt 3 en 4 - laad- en ontlaadrendement uit hele rondes; het
waardeplan valt voor een onbetrouwbare ontlaadband op hetzelfde gemeten getal terug.

Audit 02-11: geleerd laden 86,3 % (mediaan van 20 stukken, 72,9-93,3) tegen
~81-83 % op de meter; ontladen 96,2 % tegen ~100 %, omdat alles boven 100 %
als onmogelijk werd weggegooid (te_hoog 10x). Het product klopte (~83 %).
"""
from types import SimpleNamespace

import pytest

from custom_components.energy_management_system import accukosten as A
from custom_components.energy_management_system import waardeplan as W
from custom_components.energy_management_system.coordinator import EnergyManagementSystemCoordinator as C
from tests._v5167_reeks import bouw


def _reeks(eta_l=0.82, eta_o=1.0, dagen=4):
    seg = []
    for _ in range(dagen):
        seg += [(4, 0.0, 0.0), (12, -1800.0, 0.0), (6, 0.0, 0.0), (40, 300.0, 0.0), (8, 0.0, 0.0),
                (6, 1600.0, 0.0), (20, 0.0, 0.0)]
    regels, gemeten, *_ = bouw(seg, inhoud0=0.5, eta_l=eta_l, eta_o=eta_o)
    return A.kwartierreeks(regels, gemeten)


def test_hele_rondes_geven_de_meter():
    r = A.rendement_over_rondes(_reeks())
    assert r["laden"]["rendement"] == pytest.approx(0.82, abs=0.01)
    assert r["ontladen"]["rendement"] == pytest.approx(1.0, abs=0.001)   # afgekapt op 1,0
    assert r["laden"]["rondes"] >= 3 and r["ontladen"]["rondes"] >= 3


def test_ontladen_boven_100_procent_per_ronde_telt_mee():
    """Een ronde van 300 W x 2 uur die 6 SoC-stappen ziet terwijl er 0,6 kWh
    uitkwam: 0,6/0,576 = 104 %. Telt mee; weggooien zou het gemiddelde
    omlaag trekken (selectie)."""
    r = {"richting": "ontladen", "kwartieren": 8, "ac_kwh": 0.6, "delta_kwh": -0.576}
    assert A._ronde_meting(r) == (0.6, 0.576)


def test_te_weinig_rondes_geen_uitspraak():
    r = A.rendement_over_rondes(_reeks(dagen=1))
    assert r["laden"]["rendement"] is None


def _c(**kw):
    c = SimpleNamespace(charge_efficiency_history=[86.3] * 5, discharge_efficiency_history=[96.0] * 5)
    c.__dict__.update(kw)
    return c


def test_property_neemt_de_rondes_als_ze_er_zijn():
    c = _c(_rendement_uit_rondes=lambda: {"laden": 81.9, "ontladen": 100.0})
    assert C.learned_charge_efficiency_percent.fget(c) == 81.9
    assert C.learned_discharge_efficiency_percent.fget(c) == 100.0


def test_property_valt_terug_op_de_mediaan_afgekapt():
    c = _c(_rendement_uit_rondes=lambda: {}, discharge_efficiency_history=[98.0, 104.0, 112.0])
    assert C.learned_charge_efficiency_percent.fget(c) == 86.3
    assert C.learned_discharge_efficiency_percent.fget(c) == 100.0


def test_rendement_uit_rondes_in_de_coordinator():
    reeks = _reeks()
    c = SimpleNamespace(_accu_meetreeks=lambda now=None: reeks)
    uit = C._rendement_uit_rondes(c)
    assert uit == {"laden": pytest.approx(82.0, abs=1.0), "ontladen": 100.0}
    assert C._rendement_uit_rondes(c) is uit          # bewaard bij dezelfde reeks
    kapot = SimpleNamespace(_accu_meetreeks=lambda now=None: 1 / 0)
    assert C._rendement_uit_rondes(kapot) == {}


def test_rondrit_blijft_rond_de_meter():
    """Product van de halve rendementen ~82-85 % (meter 85,0 %)."""
    c = _c(_rendement_uit_rondes=lambda: {"laden": 82.0, "ontladen": 100.0})
    c.learned_charge_efficiency_percent = C.learned_charge_efficiency_percent.fget(c)
    c.learned_discharge_efficiency_percent = C.learned_discharge_efficiency_percent.fget(c)
    assert C.learned_battery_efficiency_percent.fget(c) == pytest.approx(82.0)


def test_stuk_ontladen_tot_115_procent_in_de_reeks(make_coordinator, hass):
    c = make_coordinator({})
    c._rendement_uit_rondes = lambda: {}
    c.discharge_efficiency_history = []
    for verschil, ac in ((-2.0, 2.1), (-2.0, 2.24), (-2.0, 2.4)):   # 105 %, 112 %, 120 %
        c._efficiency_segment_direction = 1
        c._efficiency_segment_ac_kwh = ac
        c._efficiency_segment_start_kwh = 6.0
        c._sluit_rendementsstuk(6.0 + verschil)
    assert c.discharge_efficiency_history == [105.0, 112.0]
    assert c.rendement_afwijzingen.get("te_hoog") == 1
    # laden blijft tot 100 %
    c._efficiency_segment_direction = -1
    c._efficiency_segment_ac_kwh = 2.0
    c._efficiency_segment_start_kwh = 2.0
    c._sluit_rendementsstuk(4.1)
    assert c.charge_efficiency_history[-1:] != [105.0]


def test_waardeplan_terugval_voor_een_onbetrouwbare_band_is_het_gemeten_ontladen():
    accu = W.Accu(inhoud_kwh=5.0, bruikbaar_kwh=9.8, laden_kw=2.4, ontladen_kw=2.4,
                  rendement=0.83, slijtage_eur=0.0422, rendement_laden=0.819, rendement_ontladen=0.97,
                  ontlaadbanden=((500.0, 0.958), (1500.0, None), (float("inf"), None)))
    eta_l, eta_o = W.rendementen(accu)
    assert (eta_l, eta_o) == (0.819, 0.97)
    assert W.ontlaadrendement(2000.0, accu, eta_o) == 0.97      # was 0,83/0,819 -> 1,0
    assert W.ontlaadrendement(300.0, accu, eta_o) == 0.958
    oud = W.Accu(**{**accu.__dict__, "rendement_ontladen": None})
    assert W.rendementen(oud)[1] == 1.0


def test_coordinator_geeft_het_ontlaadrendement_aan_het_waardeplan():
    from pathlib import Path
    bron = (Path(A.__file__).parent / "coordinator.py").read_text(encoding="utf-8")
    assert 'uit["rendement_ontladen"] = min(1.0, ontladen / 100)' in bron
