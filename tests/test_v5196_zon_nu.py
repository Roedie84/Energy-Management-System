"""v5.196.0: de zonverwachting reageert sneller op een omslag.

09-11 10:48: de zon brak rond 10:15 door; gemeten 1,55 kW, Solcast ~0,96 kW,
het plan rekende met 0,88 kW (het donkere uur 09-10 telde nog mee, en de
verhouding was begrensd op 1,3). Akkoord Ruud 09-11 10:50: het afgelopen
halfuur telt voor het eerstvolgende uur, grens 1,6x Solcast.
"""
from datetime import timedelta

import pytest

from custom_components.energy_management_system.const import ZON_NU_MAX, ZON_NU_VERVAL_UREN, ZON_RECENT_MAX
from tests.test_v5186_C_zon import DAG, _pv, _vandaag

NU = DAG.replace(hour=10, minute=48)


def _metingen(c, watt, minuten=30, begrensd=False):
    for i in range(minuten + 1):
        c._noteer_pv_nu(NU - timedelta(minutes=minuten - i), watt, begrensd)


def test_halfuur_tegen_ruwe_solcast(make_coordinator, hass):
    c = _pv(make_coordinator, hass)
    c._ruwe_zon_kwh = lambda a, b: 0.96 * (b - a).total_seconds() / 3600
    _metingen(c, 1400)
    assert c._zon_nu(NU) == pytest.approx(1400 / 960, abs=0.01)
    c2 = _pv(make_coordinator, hass)
    c2._ruwe_zon_kwh = c._ruwe_zon_kwh
    _metingen(c2, 1550)                  # 1,61x: op de grens
    assert c2._zon_nu(NU) == ZON_NU_MAX


def test_begrensd_op_1_6():
    assert ZON_NU_MAX == 1.6 and ZON_RECENT_MAX == 1.6


def test_te_kort_of_begrensd_telt_niet(make_coordinator, hass):
    c = _pv(make_coordinator, hass)
    c._ruwe_zon_kwh = lambda a, b: 0.96 * (b - a).total_seconds() / 3600
    _metingen(c, 1550, minuten=10)
    assert c._zon_nu(NU) is None
    c2 = _pv(make_coordinator, hass)
    c2._ruwe_zon_kwh = c._ruwe_zon_kwh
    _metingen(c2, 1550, begrensd=True)
    assert c2._zon_nu(NU) is None


def test_nacht_telt_niet(make_coordinator, hass):
    c = _pv(make_coordinator, hass)
    c._ruwe_zon_kwh = lambda a, b: 0.0
    _metingen(c, 0)
    assert c._zon_nu(NU) is None


def test_eerstvolgende_uur_volgt_de_meting_daarna_uitdoven(make_coordinator, monkeypatch):
    c = _vandaag(make_coordinator, monkeypatch, NU)
    c._zon_recent = lambda n: 0.83
    c._zon_nu = lambda n: 1.6
    c.learned_pv_hourly_ratio = lambda uur: 0.8
    a = NU + timedelta(minutes=12)        # 11:00, 12 min weg
    dichtbij = c._estimate_pv_kwh_for_period(a, a + timedelta(minutes=15))
    c._pv_vast_cache = None
    c._zon_nu = lambda n: None
    zonder = c._estimate_pv_kwh_for_period(a, a + timedelta(minutes=15))
    assert dichtbij > zonder * 1.5
    # na ZON_NU_VERVAL_UREN geen invloed meer
    c._pv_vast_cache = None
    ver = NU + timedelta(hours=ZON_NU_VERVAL_UREN + 1)
    met = c._estimate_pv_kwh_for_period(ver, ver + timedelta(minutes=15))
    c._pv_vast_cache = None
    c._zon_nu = lambda n: 1.6
    assert c._estimate_pv_kwh_for_period(ver, ver + timedelta(minutes=15)) == pytest.approx(met)
