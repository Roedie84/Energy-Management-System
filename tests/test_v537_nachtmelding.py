"""Nachtmelding, Monte Carlo zonder prijzen voor morgen, tekort in kWh (v5.37).

Gemeten op 7 oktober:
- "accu haalt de nacht niet" om 00:00 en 07:48, terwijl de accu de ochtend
  zonder netimport haalde;
- de Monte-Carlo-tekortkans stond 's middags op unknown ("geen toekomstig
  goedkoopste blok bekend");
- de tekortdagen waren alleen een telling, niet de omvang.
"""
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

from custom_components.energy_management_system.const import (
    MONTE_CARLO_TERUGVAL_UUR,
    NACHT_TEKORT_AANHOUDEND_MIN,
)


def _om(uur, minuut=0):
    return dt_util.now().replace(hour=uur, minute=minuut, second=0, microsecond=0)


# --- nachtmelding -----------------------------------------------------------


def test_een_kort_tekort_meldt_nog_niet(make_coordinator, hass):
    c = make_coordinator({})
    assert not c._nacht_tekort_melden(_om(23), 1.0, 0.5, False)


def test_een_aanhoudend_tekort_meldt_wel(make_coordinator, hass):
    c = make_coordinator({})
    start = _om(22)
    c._nacht_tekort_melden(start, 1.0, 0.5, False)
    later = start + timedelta(minutes=NACHT_TEKORT_AANHOUDEND_MIN)
    assert c._nacht_tekort_melden(later, 1.0, 0.5, False)


def test_een_onderbroken_tekort_begint_opnieuw(make_coordinator, hass):
    c = make_coordinator({})
    start = _om(22)
    c._nacht_tekort_melden(start, 1.0, 0.5, False)
    c._nacht_tekort_melden(start + timedelta(minutes=10), 0.1, 0.5, False)
    later = start + timedelta(minutes=NACHT_TEKORT_AANHOUDEND_MIN)
    assert not c._nacht_tekort_melden(later, 1.0, 0.5, False)


def test_na_zessen_geen_nieuwe_melding(make_coordinator, hass):
    c = make_coordinator({})
    c._nacht_tekort_sinds = _om(7)
    assert not c._nacht_tekort_melden(_om(7, 48), 2.0, 0.5, False)


def test_een_actieve_melding_houdt_de_hysterese(make_coordinator, hass):
    c = make_coordinator({})
    assert c._nacht_tekort_melden(_om(8), 0.1, 0.5, True)
    assert not c._nacht_tekort_melden(_om(8), 0.0, 0.5, True)


# --- Monte Carlo zonder prijzen voor morgen ---------------------------------


def test_de_terugval_horizon_is_het_volgende_negen_uur():
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    middag = datetime(2026, 10, 7, 13, 0)
    assert C._monte_carlo_terugval_horizon(middag) == datetime(
        2026, 10, 8, MONTE_CARLO_TERUGVAL_UUR, 0
    )
    vroeg = datetime(2026, 10, 7, 5, 0)
    assert C._monte_carlo_terugval_horizon(vroeg) == datetime(
        2026, 10, 7, MONTE_CARLO_TERUGVAL_UUR, 0
    )


def test_zonder_goedkoopste_blok_wordt_toch_gesimuleerd(make_coordinator, hass):
    c = make_coordinator({})
    nu = _om(13)
    c._run_monte_carlo_simulation(nu, None)

    assert c.monte_carlo_hours_simulated > 0
    assert "onbekend" in c.monte_carlo_horizon_basis


# --- tekort in kWh ----------------------------------------------------------


def test_de_vergelijking_toont_ook_de_omvang(make_coordinator, hass):
    c = make_coordinator({})
    c.reserve_daily_records = [
        {"shortfall": True, "tekortnacht_kwh": 0.8},
        {"shortfall": False, "tekortnacht_kwh": 0.0},
        {"shortfall": True, "tekortnacht_kwh": 1.25},
    ]
    v = c.get_monte_carlo_vergelijking()
    assert v["tekort_kwh_laatste_7"] == 2.05
    assert v["tekort_kwh_per_nacht"] == [0.8, 0.0, 1.25]
