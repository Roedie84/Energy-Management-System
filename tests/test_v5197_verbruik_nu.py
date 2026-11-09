"""v5.197.0: het plan volgt ook een lager verbruik dan geleerd.

09-11 11:04 (cockpit): accu gepland 747 W laden, gemeten 1,39 kW - "huis
verbruikt minder dan verwacht". Ruud: "zelfde geldt dus eigenlijk voor de
accu". De live verbruikscorrectie stuurde alleen omhoog; nu rekent het plan het
eerstvolgende uur ook met een lager verbruik, uitdovend. De reserve
(veilig=True) blijft alleen omhoog bijsturen.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import coordinator as mod
from custom_components.energy_management_system.const import VERBRUIK_NU_MIN

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 9, 11, 0, tzinfo=TZ)


def _c(make_coordinator, monkeypatch, live_kw):
    c = make_coordinator({})
    monkeypatch.setattr(mod.dt_util, "now", lambda: NU)
    c._recent_consumption_readings_kw = [live_kw] * 4
    c.last_heavy_load_source = None
    c._profiel_zonder_witgoed_kw = lambda uur, moment=None: 0.5
    c._basis_uur_kw = lambda uur, moment=None: 0.5
    c._estimate_pv_kwh_for_period = lambda a, b, veilig=True: 0.0
    c.geplande_witgoed_kwh_in_periode = lambda a, b: 0.0
    c.lopend_witgoed_kwh_in_periode = lambda a, b: 0.0
    c.regelverschuiving_kw = lambda: 0.0
    return c


def test_factor_omlaag_en_begrensd(make_coordinator, monkeypatch):
    assert _c(make_coordinator, monkeypatch, 0.3)._verbruik_nu_omlaag() == pytest.approx(0.6)
    assert _c(make_coordinator, monkeypatch, 0.05)._verbruik_nu_omlaag() == VERBRUIK_NU_MIN
    assert _c(make_coordinator, monkeypatch, 0.8)._verbruik_nu_omlaag() is None


def test_zwaar_apparaat_niet(make_coordinator, monkeypatch):
    c = _c(make_coordinator, monkeypatch, 0.3)
    c.last_heavy_load_source = "vaatwasser"
    assert c._verbruik_nu_omlaag() is None


def test_plan_lager_reserve_niet(make_coordinator, monkeypatch):
    c = _c(make_coordinator, monkeypatch, 0.3)
    plan = c._segmenten_verbruik_zon(NU, NU + timedelta(minutes=15), veilig=False)
    reserve = c._segmenten_verbruik_zon(NU, NU + timedelta(minutes=15), veilig=True)
    assert plan[0][0] < reserve[0][0]
    assert reserve[0][0] == pytest.approx(0.5 * 0.25)


def test_na_een_uur_geen_invloed(make_coordinator, monkeypatch):
    c = _c(make_coordinator, monkeypatch, 0.3)
    a = NU + timedelta(hours=2)
    plan = c._segmenten_verbruik_zon(a, a + timedelta(minutes=15), veilig=False)
    assert plan[0][0] == pytest.approx(0.5 * 0.25)
