"""v5.190.0 (L-EMS-072): panelen bedekt door sneeuw of ijs.

Gevraagd 07-11 (rijp op de panelen, camera zolder): het EMS moet zelf zien of de
panelen schoon zijn. Herkenning met de eigen heldere-hemel-ijklijn: vorst +
heldere lucht + een uur lang < 35 % van de ijklijn. Dan rekent de zonschatting
met de gemeten verhouding en tellen die uren/dagen niet mee in het leren.
07-11 zelf (rijp, 09-10 u ~0,8 van de ijklijn) mag NIET als bedekt tellen.
"""
import asyncio
import datetime as dtm
from datetime import timedelta

import pytest

import custom_components.energy_management_system.solar_forecast as sfm
from custom_components.energy_management_system import panelen_bedekt as P
from tests.test_daily_forecast_comparison import _op, _run, _tracker
from tests.test_v5186_C_zon import DAG, _loop, _pv, _vandaag

T0 = DAG.replace(month=12, day=5, hour=10)   # winterochtend


def _reeks(t, start, minuten, helderheid, bewolking=10.0, temp=-2.0, recent=None):
    for i in range(minuten + 1):
        t = P.stap(t, start + timedelta(minutes=i), helderheid, bewolking, temp, recent)
    return t


def test_sneeuw_wordt_na_een_uur_herkend():
    t = _reeks(None, T0, 59, 0.05, recent=0.04)
    assert not t["bedekt"]
    t = _reeks(t, T0 + timedelta(minutes=60), 1, 0.05, recent=0.04)
    assert t["bedekt"]
    assert P.factor(t) == pytest.approx(0.04)
    assert P.dag_bedekt(t, T0.date())
    assert "bedekt" in P.melding(t)


def test_rijp_van_07_11_telt_niet():
    """07-11 09-10 u: 622 W tegen ~780 W op heldere dagen = ~0,8."""
    t = _reeks(None, T0, 120, 0.8, recent=0.8)
    assert not t["bedekt"] and P.factor(t) is None


def test_korte_rijp_onder_de_drempel_telt_niet():
    t = _reeks(None, T0, 40, 0.2)
    t = _reeks(t, T0 + timedelta(minutes=41), 30, 0.9)
    assert not t["bedekt"]


def test_bewolkt_is_geen_sneeuw():
    t = _reeks(None, T0, 120, 0.1, bewolking=85.0)
    assert not t["bedekt"]


def test_zonder_vorst_geen_sneeuw():
    t = _reeks(None, T0, 120, 0.1, temp=8.0)
    assert not t["bedekt"]


def test_vorst_van_vannacht_telt_nog():
    t = P.stap(None, T0 - timedelta(hours=10), None, None, -3.0, None)
    t = _reeks(t, T0, 70, 0.05, temp=3.0)
    assert t["bedekt"]


def test_vrij_zodra_de_panelen_weer_leveren():
    t = _reeks(None, T0, 70, 0.05, recent=0.05)
    assert t["bedekt"]
    t = _reeks(t, T0 + timedelta(hours=2), 10, 0.7)
    assert t["bedekt"]                          # nog geen kwartier
    t = _reeks(t, T0 + timedelta(hours=2, minutes=11), 5, 0.7)
    assert not t["bedekt"] and t["einde"]["reden"] == "levert weer"
    assert P.dag_bedekt(t, T0.date())           # die dag blijft niet geleerd


def test_bewolkte_dagen_houden_de_toestand_tot_het_verloopt():
    t = _reeks(None, T0, 70, 0.05, recent=0.05)
    later = T0 + timedelta(hours=30)
    t = _reeks(t, later, 10, 0.2, bewolking=90.0)
    assert t["bedekt"]                          # bewolkt: niet te beoordelen
    t = P.stap(t, T0 + timedelta(hours=74), None, None, 2.0, None)
    assert not t["bedekt"] and t["einde"]["reden"] == "verlopen"


def test_factor_begrensd():
    t = _reeks(None, T0, 70, 0.3, recent=0.9)
    assert t["bedekt"] and P.factor(t) == pytest.approx(P.BEDEKT_FACTOR_MAX)
    t2 = _reeks(None, T0, 70, 0.05, recent=None)
    assert P.factor(t2) == pytest.approx(P.BEDEKT_FACTOR_STANDAARD)


def test_zonschatting_rekent_met_de_gemeten_verhouding(make_coordinator, monkeypatch):
    nu = DAG.replace(hour=9)
    c = _vandaag(make_coordinator, monkeypatch, nu)
    c._zon_recent = lambda n: None
    c.learned_pv_hourly_ratio = lambda uur: 0.9
    a = nu.replace(hour=13)
    assert c._estimate_pv_kwh_for_period(a, a + timedelta(hours=1)) == pytest.approx(2.0 * 0.9)
    c.panelen_bedekt = {**P.leeg(), "bedekt": True, "sinds": nu.isoformat(), "factor": 0.05}
    c._pv_vast_cache = None
    assert c._estimate_pv_kwh_for_period(a, a + timedelta(hours=1)) == pytest.approx(2.0 * 0.05)
    m = a + timedelta(days=1)                   # morgen ook, tot ze weer leveren
    assert c._estimate_pv_kwh_for_period(m, m + timedelta(hours=1)) == pytest.approx(2.0 * 0.05)


def test_bedekt_uur_leert_niet(make_coordinator, hass):
    c = _pv(make_coordinator, hass)
    uur = DAG.replace(hour=11, minute=30)
    c.panelen_bedekt = {**P.leeg(), "uren": [P._uursleutel(uur)]}
    _loop(c, DAG.replace(hour=10, minute=59), DAG.replace(hour=12, minute=1))
    assert not any(c.pv_hourly_bias_history.values())
    # wel gemeten voor de herkenning
    assert c._pv_recente_uren[-1]["meetbaar"] is True
    assert c._pv_recente_uren[-1]["geldig"] is False


def test_onbedekt_uur_leert_wel(make_coordinator, hass):
    c = _pv(make_coordinator, hass)
    _loop(c, DAG.replace(hour=10, minute=59), DAG.replace(hour=12, minute=1))
    assert sum(len(v) for v in c.pv_hourly_bias_history.values()) == 1


def test_recent_ruw_zonder_ondergrens(make_coordinator, hass):
    c = _pv(make_coordinator, hass)
    nu = DAG.replace(hour=12)
    c._pv_hour_duration_hours = 0.0
    c._pv_recente_uren = [{"begin": nu - timedelta(hours=1), "eind": nu, "geldig": False,
                           "meetbaar": True, "werkelijk_kwh": 0.03, "verwacht_kwh": 1.0}]
    assert c._zon_recent_ruw(nu) == pytest.approx(0.03)


def test_dagcorrectie_slaat_een_bedekte_dag_over(hass, monkeypatch):
    t = _tracker(hass)
    t.dag_uitsluiten = lambda dag: dag == dtm.date(2026, 8, 10)
    hass.states.set("sensor.solcast_morgen", "18.2")
    _op(monkeypatch, 2026, 8, 9, 20, 0)
    _run(t._async_handle_forecast_capture())
    _op(monkeypatch, 2026, 8, 9, 23, 59)
    _run(t._async_handle_compare())
    hass.states.set("sensor.solaredge_vandaag", "1.0")
    _op(monkeypatch, 2026, 8, 10, 23, 59)
    _run(t._async_handle_compare())
    assert t.deviation_history == []


def test_update_in_de_ronde(make_coordinator, monkeypatch):
    c = make_coordinator({})
    c._get_live_outdoor_temp_c = lambda now: -3.0
    c._weather_cloud_cover_percent = lambda: 5.0
    c.gemeten_helderheid = lambda: 0.05
    c._zon_recent_ruw = lambda now: 0.04
    for i in range(62):
        c._update_panelen_bedekt(T0 + timedelta(minutes=i))
    assert c.panelen_bedekt["bedekt"] and c.panelen_bedekt_factor() == pytest.approx(0.04)
    assert c.zon_dag_niet_leren(T0.date())
    assert "bedekt" in (c._panelen_bedekt_aandachtspunt() or "")
