"""v5.191.0 (L-EMS-073): laden bij koude cellen.

Gevraagd 07-11: de AB3000-modules verwarmen zich bij zeer koud weer eerst en
laden dan pas. Akkoord Ruud 07-11 10:33: het laadplan vervroegen bij ~0 °C.
Het plan rekent dan met een deel van het laadvermogen (eerst 50 %, daarna
geleerd per gemeten koud laadkwartier) en begint zo vanzelf eerder.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import koude_accu as K
from custom_components.energy_management_system import waardeplan as W

TZ = timezone(timedelta(hours=1))
T0 = datetime(2026, 12, 10, 2, 0, tzinfo=TZ)


def test_warm_is_volle_kracht():
    assert K.factor(None, 8.0, False) == 1.0
    assert K.factor(None, None, False) == 1.0


def test_koud_eerst_de_standaard():
    assert K.factor(None, 0.5, False) == K.KOUD_FACTOR_STANDAARD
    assert K.factor(None, 6.0, True) == K.KOUD_FACTOR_STANDAARD   # verwarmt nu


def _kwartier_meten(t, begin, gevraagd_w, geladen_w, temp=-1.0, verwarmt=False):
    for s in range(0, 15 * 60 + 1, 30):
        t = K.stap(t, begin + timedelta(seconds=s), temp, verwarmt, gevraagd_w, geladen_w)
    return t


def test_leert_het_deel_dat_er_echt_in_gaat():
    t = None
    for i in range(K.KOUD_MIN_METINGEN):
        t = _kwartier_meten(t, T0 + timedelta(minutes=15 * i), 2400, 1700)
    t = K.stap(t, T0 + timedelta(minutes=15 * K.KOUD_MIN_METINGEN, seconds=30), -1.0, False, 0, 0)
    assert len(t["metingen"]) == K.KOUD_MIN_METINGEN
    assert K.factor(t, -1.0, False) == pytest.approx(1700 / 2400, abs=0.01)


def test_warme_kwartieren_tellen_niet():
    t = None
    for i in range(6):
        t = _kwartier_meten(t, T0 + timedelta(minutes=15 * i), 2400, 2350, temp=9.0)
    assert t["metingen"] == []


def test_verwarmingsperiode_vastgelegd():
    t = K.stap(None, T0, -2.0, True, 0, 0)
    t = K.stap(t, T0 + timedelta(minutes=25), 1.5, False, 0, 0)
    assert t["episodes"][-1]["minuten"] == pytest.approx(25.0)
    assert t["episodes"][-1]["temp_c"] == -2.0


def test_factor_alleen_binnen_de_horizon():
    ks = [W.Kwartier(T0 + timedelta(minutes=15 * i), 0.1, 0.0, 0.30, 0.05) for i in range(96)]
    n = K.pas_toe(ks, T0, 0.5)
    assert n == K.KOUD_HORIZON_UREN * 4
    assert ks[0].laad_factor == 0.5 and ks[-1].laad_factor == 1.0


def _plan(laad_factor: float):
    """Goedkoop van 02:00-04:00, duur vanaf 07:00; de accu is leeg."""
    ks = []
    for i in range(24 * 4):
        t = T0 + timedelta(minutes=15 * i)
        uur = t.hour
        prijs = 0.20 if 2 <= uur < 4 else (0.30 if uur < 7 else 0.60)
        ks.append(W.Kwartier(t, 0.25, 0.0, prijs, 0.05, laad_factor=laad_factor))
    accu = W.Accu(inhoud_kwh=0.0, bruikbaar_kwh=8.0, laden_kw=2.4, rendement=0.85,
                  slijtage_eur=0.04, verkopen=False)
    return W.plan(ks, accu)


def _geladen_voor_7(res) -> float:
    return sum(
        max(0.0, r.get("accu_kwh") or 0.0)
        for r in res.kwartieren
        if r.get("actie") == "laden_net" and r["begin"].hour < 7
    )


def test_koude_accu_laadt_meer_kwartieren_dus_eerder():
    warm = _plan(1.0)
    koud = _plan(0.5)
    n_warm = sum(1 for r in warm.kwartieren if r.get("actie") == "laden_net")
    n_koud = sum(1 for r in koud.kwartieren if r.get("actie") == "laden_net")
    assert n_koud > n_warm
    eerste_warm = min(r["begin"] for r in warm.kwartieren if r.get("actie") == "laden_net")
    eerste_koud = min(r["begin"] for r in koud.kwartieren if r.get("actie") == "laden_net")
    assert eerste_koud <= eerste_warm
    assert any(r.get("laad_factor") == 0.5 for r in koud.kwartieren)


def test_opdracht_wordt_groter_bij_koude(make_coordinator):
    c = make_coordinator({})
    warm = {"accu_kwh": 0.2, "uren": 0.25}
    koud = {"accu_kwh": 0.2, "uren": 0.25, "laad_factor": 0.5}
    w = c._waardeplan_laadvermogen_w(warm)
    assert c._waardeplan_laadvermogen_w(koud) == pytest.approx(min(2 * w, c._waardeplan_laadvermogen_w({"vol_vermogen": True})))


def test_ronde_meet_en_plan_krijgt_de_factor(make_coordinator, hass):
    c = make_coordinator({"battery_module_temperature_sensor_entities": ["sensor.ab3000_1_max_temp"]})
    c._read_battery_modules = lambda: [{"temperatuur_c": -1.0}]
    hass.states.set("binary_sensor.ab3000_1_heat_state", "on")
    c._read_corrected_battery_power = lambda: -1200.0
    c._waardeplan_rijen = [{"actie": "laden_net", "accu_kwh": 0.6, "uren": 0.25}]
    c._update_koude_laden(T0)
    assert c._koude_nu == (-1.0, True)
    ks = [W.Kwartier(T0 + timedelta(minutes=15 * i), 0.1, 0.0, 0.3, 0.05) for i in range(8)]
    c._koude_laadfactor_toepassen(T0, ks)
    assert all(k.laad_factor == K.KOUD_FACTOR_STANDAARD for k in ks)
    assert c.get_koude_laden_overzicht()["koud"] is True
