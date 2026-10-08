"""Monte Carlo gecentreerd op het deterministische diepste tekort (v5.40).

Gemeld op 7 oktober 20:24: mediaan 4,12 kWh, terwijl de planning een diepste
tekort van 6,11 kWh rekende, en 0% tekortkans naast 4 tekortnachten in 7
dagen. Drie oorzaken:

1. de reserve telt sinds v3.99.18 de lange horizon mee (het tekort na het
   goedkope blok, ~1,7 kWh); Monte Carlo niet;
2. Monte Carlo rekende met de GEWONE zonverwachting, de reserve met de
   voorzichtige (de band);
3. de geleerde zonverhouding telde dubbel: de schatting past de mediane
   uurverhouding al toe, en de trekking vermenigvuldigde er nog een overheen.

Zonder spreiding (alle trekkingen gelijk) moet de mediaan precies het
deterministische getal zijn: dezelfde horizon, dezelfde invoer.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 10, 7, 18, 24, tzinfo=timezone.utc)
BLOK = datetime(2026, 10, 8, 10, 15, tzinfo=timezone.utc)


def _zon(start, eind, veilig=False):
    """Zon tussen 07 en 15 UTC; de voorzichtige band ligt lager."""
    uren = (eind - start).total_seconds() / 3600
    if 7 <= start.hour < 15:
        return (0.4 if veilig else 0.9) * uren
    return 0.0


def _opzet(make_coordinator, hass, spreiding=False):
    c = make_coordinator(
        {"available_energy_sensor_entity": "sensor.available_energy"}
    )
    hass.states.set("sensor.available_energy", "5.96")
    for h in range(24):
        c.hourly_consumption_profile[h] = (
            [0.20, 0.25, 0.30, 0.35, 0.40, 0.30, 0.30] if spreiding else [0.3] * 7
        )
        # Een geleerde verhouding van 1,3: zat al in de schatting, en de
        # oude trekking vermenigvuldigde er nog eens mee.
        c.pv_hourly_bias_history[h] = (
            [1.0, 1.2, 1.3, 1.4, 1.6, 1.3, 1.3] if spreiding else [1.3] * 7
        )
    c._get_smoothed_consumption_correction_ratio = lambda h: 1.0
    c.regelverschuiving_kw = lambda: 0.05
    c._estimate_pv_kwh_for_period = _zon
    c.last_cheap_block_start = BLOK
    c._lange_reserve_extra_kwh = 1.7
    return c


def test_zonder_spreiding_is_de_mediaan_het_deterministische_tekort(
    make_coordinator, hass
):
    c = _opzet(make_coordinator, hass)

    c._run_monte_carlo_simulation(NU, BLOK)
    c._get_dynamic_discharge_reserve_kwh(NU, BLOK)
    deterministisch = c.last_reserve_margin_breakdown["needed_kwh_before_margin"]

    assert c.monte_carlo_median_deficit_kwh == pytest.approx(deterministisch, abs=0.001)
    assert c.monte_carlo_deterministisch_kwh == pytest.approx(deterministisch, abs=0.001)
    assert c.monte_carlo_p10_deficit_kwh == c.monte_carlo_p90_deficit_kwh


def test_de_lange_horizon_telt_mee(make_coordinator, hass):
    c = _opzet(make_coordinator, hass)
    c._run_monte_carlo_simulation(NU, BLOK)
    met = c.monte_carlo_median_deficit_kwh

    c._lange_reserve_extra_kwh = 0.0
    c._run_monte_carlo_simulation(NU, BLOK)

    assert met - c.monte_carlo_median_deficit_kwh == pytest.approx(1.7, abs=0.001)
    assert c.monte_carlo_lange_extra_kwh == 0.0


def test_lange_horizon_uit_dan_ook_niet_in_monte_carlo(make_coordinator, hass):
    c = _opzet(make_coordinator, hass)
    c.lange_horizon_actief = False

    c._run_monte_carlo_simulation(NU, BLOK)
    c._get_dynamic_discharge_reserve_kwh(NU, BLOK)

    assert c.monte_carlo_lange_extra_kwh == 0.0
    assert c.monte_carlo_median_deficit_kwh == pytest.approx(
        c.last_reserve_margin_breakdown["needed_kwh_before_margin"], abs=0.001
    )


def test_de_terugvalhorizon_krijgt_geen_lange_horizon(make_coordinator, hass):
    """Tot 09:00 (geen blok bekend) is er geen reserve om mee te vergelijken."""
    c = _opzet(make_coordinator, hass)

    c._run_monte_carlo_simulation(NU, None)

    assert c.monte_carlo_lange_extra_kwh == 0.0


def test_met_spreiding_ligt_de_mediaan_rond_het_deterministische_tekort(
    make_coordinator, hass
):
    """De spreiding komt eromheen; ze verschuift het midden niet."""
    c = _opzet(make_coordinator, hass, spreiding=True)

    c._run_monte_carlo_simulation(NU, BLOK)

    det = c.monte_carlo_deterministisch_kwh
    assert c.monte_carlo_p10_deficit_kwh < det < c.monte_carlo_p90_deficit_kwh
    assert c.monte_carlo_median_deficit_kwh == pytest.approx(det, abs=0.35)


def test_een_tekort_zoals_op_7_oktober_geeft_een_echte_kans(make_coordinator, hass):
    """Deterministisch nét boven de beschikbare energie: dan is de kans
    geen 0% meer."""
    c = _opzet(make_coordinator, hass, spreiding=True)
    hass.states.set("sensor.available_energy", "4.5")

    c._run_monte_carlo_simulation(NU, BLOK)

    assert c.monte_carlo_deterministisch_kwh > 4.5
    # v5.47: de deterministische 4,5+ is inclusief 1,7 kWh lange horizon;
    # die kans staat sinds v5.47 apart. De stand is tot het blok.
    assert c.monte_carlo_kans_incl_lange_horizon_pct > 20
    assert (
        c.monte_carlo_shortfall_probability_percent
        <= c.monte_carlo_kans_incl_lange_horizon_pct
    )


def test_de_sensor_toont_beide_naast_elkaar(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        MonteCarloAdvisorySensor,
    )

    c = _opzet(make_coordinator, hass)
    c._run_monte_carlo_simulation(NU, BLOK)

    attrs = MonteCarloAdvisorySensor(c, "x").extra_state_attributes

    assert attrs["deterministisch_diepste_tekort_kwh"] == c.monte_carlo_deterministisch_kwh
    assert attrs["lange_horizon_extra_kwh"] == pytest.approx(1.7)


def test_stuurt_niets(make_coordinator, hass):
    c = _opzet(make_coordinator, hass, spreiding=True)

    c._run_monte_carlo_simulation(NU, BLOK)

    assert hass.services.calls == []
