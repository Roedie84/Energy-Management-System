"""v5.175.0 punt 1 - het waardeplan rekent met zon-opslag zoals de slimme stand.

03-11 13:15-14:45: de tabel zei ~200 W ontladen / 'houden' met de SoC vlak,
gemeten werd 388 W geladen: de Zendure slaat in smart (en smart_charging) elk
zonoverschot op. Sinds de marginale prijs (v5.168) is terugleveren (prijs -
belastingdeel + 2 ct premie) vaak een paar ct meer waard dan opslaan voor de
avond, dus plande het DP terugleveren dat de sturing niet kan afdwingen.
"""
from datetime import datetime, timedelta

import pytest

from custom_components.energy_management_system import planvolging as P
from custom_components.energy_management_system import waardeplan as W

T0 = datetime(2026, 11, 3, 12, 0)
BEL, PREM = 0.1108, 0.02


def _k(i, incl, huis_w, zon_w):
    ink = incl - BEL
    return W.Kwartier(T0 + timedelta(minutes=15 * i), huis_w / 4000, zon_w / 4000, ink, ink + PREM,
                      prijs_incl_eur=incl)


def _dag():
    # middag: ~800 W overschot bij 40 ct; avond 49-50 ct zonder zon (03-11)
    ks = [_k(i, 0.40, 200, 1000) for i in range(12)]
    ks += [_k(12 + i, 0.495, 600, 0) for i in range(24)]
    return ks


def _accu(**kw):
    basis = dict(inhoud_kwh=1.0, bruikbaar_kwh=10.37, rendement=0.83, slijtage_eur=0.0422,
                 verkoopmarge_eur=0.05, netlaadmarge_eur=0.05, rendement_laden=0.836,
                 rendement_ontladen=0.99, min_actie_w=400.0)
    basis.update(kw)
    return W.Accu(**basis)


def test_oud_model_levert_het_overschot_terug():
    rijen = W.plan(_dag(), _accu(zon_opslaan=False)).kwartieren
    assert sum(r["inhoud_delta_kwh"] for r in rijen[:12]) < 0.5


def test_nieuw_model_slaat_het_overschot_op():
    rijen = W.plan(_dag(), _accu()).kwartieren
    for r in rijen[:12]:
        assert r["actie"] == "zon"
        assert r["inhoud_delta_kwh"] == pytest.approx(0.2, abs=0.01)   # 0,2 kWh x 0,836 -> 2 stappen
        assert r["accu_ac_w"] == -800
        assert r["net_kwh"] <= 0.06                                    # niets of een afrondrestje terug


def test_houden_kan_geen_overschot_terugleveren():
    for r in W.plan(_dag(), _accu()).kwartieren:
        if r["actie"] == "houden":
            assert r["net_kwh"] >= -0.06


def test_volle_accu_levert_terug_zonder_onmogelijk_plan():
    u = W.plan(_dag(), _accu(inhoud_kwh=10.37))
    assert u.beschikbaar
    eerste = u.kwartieren[0]
    assert eerste["net_kwh"] < -0.1 or eerste["actie"] == "verkopen"


def test_echt_verkopen_in_een_zonkwartier_blijft_mogelijk():
    ks = [_k(0, 0.95, 200, 1000)] + [_k(1 + i, 0.30, 200, 0) for i in range(8)]
    eerste = W.plan(ks, _accu(inhoud_kwh=5.0)).kwartieren[0]
    assert eerste["actie"] == "verkopen"


def test_terugleveren_afdwingbaar_alleen_met_de_marge():
    # terugleveren ~0,31 tegen opslaan ~0,385 x 0,83 - 0,042 = ~0,28: 3 ct
    # beter, onder de marge van 5 ct -> opslaan
    u = W.plan(_dag(), _accu(zon_export_afdwingbaar=True))
    assert all(r["inhoud_delta_kwh"] > 0.1 for r in u.kwartieren[:12])
    # met een avond van 30 ct is terugleveren ruim 5 ct beter -> terugleveren
    ks = [_k(i, 0.40, 200, 1000) for i in range(12)] + [_k(12 + i, 0.30, 600, 0) for i in range(24)]
    u = W.plan(ks, _accu(zon_export_afdwingbaar=True))
    assert sum(r["inhoud_delta_kwh"] for r in u.kwartieren[:12]) < 0.5


def test_zon_opslag_stappen():
    s = W.zon_opslag_stappen(0.2, 0.836, 5, 20)
    assert s[0] == 2 and s[-1] == 0 and s[-2] == 1
    assert W.zon_opslag_stappen(0.2, 0.836, 1, 20)[0] == 1
    assert W.zon_opslag_stappen(0.13, 0.836, 5, 20, naar_beneden=True)[0] == 1
    assert (W.zon_opslag_stappen(0.0, 0.836, 5, 20) == 0).all()


def test_planvolging_gebruikt_het_overschot_aan_de_netkant():
    rij = {"inhoud_delta_kwh": 0.1, "accu_ac_w": -388, "uren": 0.25}
    assert P._accu_w(rij, None) == -388
    assert P._accu_w({"inhoud_delta_kwh": 0.1}, None) == -400


# 03-11 gemeten (5-min-statistiek, kwartiergemiddelde): zon, huis, accu laden (W)
GEMETEN = [
    ("12:00", 1003, 151, 832), ("12:30", 1112, 171, 984), ("13:15", 1296, 206, 1038),
    ("13:45", 1134, 154, 960), ("14:15", 940, 170, 763), ("14:45", 711, 190, 496),
]


@pytest.mark.parametrize("van,zon,huis,laden", GEMETEN)
def test_herspeel_03_11_plan_volgt_de_meting(van, zon, huis, laden):
    """Met de gemeten zon en het gemeten huis volgt het plan nu de accu
    (planvolging-drempel 150 W); het oude model plande 0 W."""
    ks = [_k(0, 0.40, huis, zon)] + [_k(1 + i, 0.495, 600, 0) for i in range(24)]
    nieuw = W.plan(ks, _accu(inhoud_kwh=2.3)).kwartieren[0]
    oud = W.plan(ks, _accu(inhoud_kwh=2.3, zon_opslaan=False)).kwartieren[0]
    assert abs(P._accu_w(nieuw, None) - (-laden)) <= P.DREMPEL_W
    assert abs(P._accu_w(oud, None) - (-laden)) > P.DREMPEL_W
