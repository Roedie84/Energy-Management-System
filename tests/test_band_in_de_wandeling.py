"""De zonvoorspelling in de reserve: de band, niet het midden (v4.1).

Op de lijst als derde structurele punt. In zestien gemeten dagen viel
de werkelijke opwek nul keer onder p10 van Solcast; de veilige positie
in de band is 0,29. De reserve rekende met het MIDDEN van de
voorspelling en legde daar een percentage bovenop
(`pv_onzekerheid_percent`, v2.4.0) - een vlakke opslag op het hele
tekort, ook op het deel dat verbruik is.

Nu rekent de wandeling naar het diepste tekort per halfuur met de
band: p10 + 0,29 x (p90 - p10). De onzekerheid zit dan waar hij hoort -
in de zon, op de uren dat er zon verwacht wordt - en het percentage
erbovenop vervalt, anders telt hij dubbel. Alle andere lezers van de
zonvoorspelling (zonvangst, planning, uitstel) blijven het midden
gebruiken: die vragen niet "hoeveel is er minstens" maar "hoeveel is er
waarschijnlijk".
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)


def _solcast(hass, c, regels):
    """regels: (uur, centraal_kw, p10_kw, p90_kw)"""
    c.config = dict(c.config or {})
    c.config["solar_today_forecast_sensor_entity"] = "sensor.solcast"
    items = [
        {"period_start": (NU.replace(hour=u, minute=0)).isoformat(),
         "pv_estimate": m, "pv_estimate10": lo, "pv_estimate90": hi}
        for u, m, lo, hi in regels
    ]
    hass.states.set("sensor.solcast", "1", {"detailedForecast": items})
    c._begin_ronde_cache(NU)
    c.get_pv_band_calibration = lambda: {"beschikbaar": True, "veilige_positie": 0.29}
    c._get_pv_remaining_correction_ratio = lambda nu, e: None
    c.learned_pv_hourly_ratio = lambda uur: None


def test_de_band_per_halfuur_wordt_gelezen(make_coordinator, hass):
    c = make_coordinator({})
    _solcast(hass, c, [(9, 2.0, 1.0, 3.0), (10, 2.0, 1.0, 3.0)])

    band = c._pv_band_per_interval()

    assert len(band) == 2
    s = min(band)
    assert band[s] == pytest.approx((1.0, 3.0), abs=0.01)


def test_veilig_rekent_met_de_bandpositie(make_coordinator, hass):
    """Midden 2 kW, band 1-3: veilig = 1 + 0,29 x 2 = 1,58 kW."""
    c = make_coordinator({})
    _solcast(hass, c, [(9, 2.0, 1.0, 3.0), (10, 2.0, 1.0, 3.0)])
    a, b = NU.replace(hour=9), NU.replace(hour=11)

    midden = c._estimate_pv_kwh_for_period(a, b)
    veilig = c._estimate_pv_kwh_for_period(a, b, veilig=True)

    assert midden == pytest.approx(4.0, abs=0.05)
    assert veilig == pytest.approx(3.16, abs=0.05)


def test_zonder_band_valt_veilig_terug_op_het_midden(make_coordinator, hass):
    c = make_coordinator({})
    _solcast(hass, c, [(9, 2.0, 1.0, 3.0)])
    c.get_pv_band_calibration = lambda: {"beschikbaar": False}
    a, b = NU.replace(hour=9), NU.replace(hour=10)

    assert c._estimate_pv_kwh_for_period(a, b, veilig=True) == pytest.approx(
        c._estimate_pv_kwh_for_period(a, b), abs=0.01)


def test_de_wandeling_gebruikt_de_veilige_zon(make_coordinator, hass):
    c = make_coordinator({})
    gezien = []
    c._estimate_pv_kwh_for_period = lambda a, b, veilig=False: (gezien.append(veilig), 0.0)[1]
    c.hourly_consumption_profile = {h: [0.3] * 7 for h in range(24)}
    c._get_smoothed_consumption_correction_ratio = lambda h: 1.0
    c.lopend_witgoed_kwh_in_periode = lambda a, b: 0.0
    c.geplande_witgoed_kwh_in_periode = lambda a, b: 0.0

    c._estimate_worst_case_deficit_kwh(NU, NU + timedelta(hours=3))

    assert gezien and all(gezien)


def test_het_percentage_erbovenop_vervalt_met_de_band(make_coordinator, hass):
    """Anders telt de onzekerheid dubbel: in de zon én op het tekort."""
    c = make_coordinator({})
    c.get_pv_band_calibration = lambda: {"beschikbaar": True, "veilige_positie": 0.29}

    assert c._pv_onzekerheidsmarge_procent() == 0.0
