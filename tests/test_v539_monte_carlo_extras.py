"""Monte Carlo met dezelfde extra's als de vaste wandeling (v5.39).

Uit de controle van 7 oktober 18:05: de Monte-Carlo-trekkingen misten wat
`_segmenten_verbruik_zon` bovenop het geleerde uurprofiel telt (P1-
verschuiving, gepland en lopend witgoed, live-correctie, vakantie), terwijl
de docstring "exact dezelfde wandeling" belooft. Daardoor lag de tekortkans
structureel te laag naast de reserve.
"""
from datetime import datetime, timedelta, timezone

import pytest

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _vlak(c, kw=0.3):
    for h in range(24):
        c.hourly_consumption_profile[h] = [kw] * 7
        c.pv_hourly_bias_history[h] = [0.0] * 7
    c.learned_hourly_avg_kw = lambda h: kw
    c._get_smoothed_consumption_correction_ratio = lambda h: 1.0


def test_p1_verschuiving_telt_mee(make_coordinator, hass):
    c = make_coordinator({})
    _vlak(c)
    c.regelverschuiving_kw = lambda: 0.05

    c._run_monte_carlo_simulation(DAY0, DAY0 + timedelta(hours=3))

    # 0,3 kW + 0,05 kW over 3 uur, geen zon
    assert c.monte_carlo_median_deficit_kwh == pytest.approx(1.05, abs=0.01)
    assert c.monte_carlo_extra_kwh == pytest.approx(0.15, abs=0.01)


def test_gepland_witgoed_telt_mee(make_coordinator, hass):
    c = make_coordinator({})
    _vlak(c)
    c.regelverschuiving_kw = lambda: 0.0
    c.geplande_witgoed_kwh_in_periode = lambda a, b: 0.4 if a == DAY0 else 0.0

    c._run_monte_carlo_simulation(DAY0, DAY0 + timedelta(hours=2))

    assert c.monte_carlo_median_deficit_kwh == pytest.approx(1.0, abs=0.01)


def test_zonder_extras_gelijk_aan_vroeger(make_coordinator, hass):
    c = make_coordinator({})
    _vlak(c)
    c.regelverschuiving_kw = lambda: 0.0

    c._run_monte_carlo_simulation(DAY0, DAY0 + timedelta(hours=3))

    assert c.monte_carlo_median_deficit_kwh == pytest.approx(0.9, abs=0.01)
    assert c.monte_carlo_extra_kwh == 0.0


def test_vakantie_verlaagt_de_trekking(make_coordinator, hass):
    c = make_coordinator({"vacation_consumption_reduction_percent": 50})
    _vlak(c)
    c.regelverschuiving_kw = lambda: 0.0
    c.vacation_mode = True
    c.instelling = lambda k, d=None: 50 if "vacation" in str(k) else d

    c._run_monte_carlo_simulation(DAY0, DAY0 + timedelta(hours=2))

    assert c.monte_carlo_median_deficit_kwh == pytest.approx(0.3, abs=0.01)


def test_zonder_geleerd_uurprofiel_geen_extras(make_coordinator, hass):
    c = make_coordinator({})
    _vlak(c)
    c.learned_hourly_avg_kw = lambda h: None
    c.regelverschuiving_kw = lambda: 0.05

    c._run_monte_carlo_simulation(DAY0, DAY0 + timedelta(hours=2))

    assert c.monte_carlo_extra_kwh == 0.0
