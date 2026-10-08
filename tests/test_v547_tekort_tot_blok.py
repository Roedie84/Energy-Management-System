"""Tekort tot het blok en na het blok apart gerapporteerd (v5.47, L-EMS-006).

Gemeld op 8 oktober ~10:00: Monte Carlo 96-100% en "verwacht tekort tot het
goedkope blok 1,14 kWh", terwijl er tot het blok van 12:15 juist ~1,4 kWh
overbleef. Oorzaak: beide rekenden met `needed_kwh_before_margin`, en daar zit
sinds v3.99.18 de lange horizon in (`lange_horizon_extra_kwh`) - energie die
NA het laadblok nodig is en in dat blok wordt bijgeladen. Live 08-10 ~10:00:
nodig 2,47 waarvan 2,468 lange horizon, beschikbaar ~1,47.

Alleen rapportage: de reserve en de sturing veranderen niet.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 10, 7, 18, 24, tzinfo=timezone.utc)
BLOK = datetime(2026, 10, 8, 10, 15, tzinfo=timezone.utc)


def _c(make_coordinator, hass):
    c = make_coordinator({"available_energy_sensor_entity": "sensor.available_energy"})
    c._live_tekortvolging_onvolledig = lambda begin: None
    return c


# --- verwacht_tekort -------------------------------------------------------

def test_het_geval_van_8_oktober_geeft_geen_tekort_tot_het_blok(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    c.last_reserve_margin_breakdown = {
        "needed_kwh_before_margin": 2.47,
        "lange_horizon_extra_kwh": 2.468,
    }
    c.beschikbare_energie_kwh = lambda: 1.47

    v = c.verwacht_tekort()

    assert v["tekort_kwh"] == 0.0
    assert v["verwacht_tekort_tot_blok_kwh"] == 0.0
    assert v["verwacht_tekort_na_blok_kwh"] == pytest.approx(1.0, abs=0.01)
    assert v["nodig_tot_blok_kwh"] == 0.0
    assert v["nodig_na_blok_kwh"] == pytest.approx(2.47, abs=0.01)
    assert v["tekort_soort"] is None


def test_een_echt_tekort_tot_het_blok_blijft_zichtbaar(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    c.last_reserve_margin_breakdown = {
        "needed_kwh_before_margin": 6.0,
        "lange_horizon_extra_kwh": 1.5,
    }
    c.beschikbare_energie_kwh = lambda: 4.0

    v = c.verwacht_tekort()

    assert v["verwacht_tekort_tot_blok_kwh"] == 0.5
    assert v["tekort_kwh"] == 0.5
    assert v["verwacht_tekort_na_blok_kwh"] == 1.5
    assert v["tekort_soort"] is not None


def test_zonder_lange_horizon_verandert_er_niets(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    c.last_reserve_margin_breakdown = {"needed_kwh_before_margin": 6.11}
    c.beschikbare_energie_kwh = lambda: 5.0

    v = c.verwacht_tekort()

    assert v["tekort_kwh"] == 1.11
    assert v["verwacht_tekort_na_blok_kwh"] == 0.0


def test_de_informatieve_regel_noemt_het_tekort_tot_het_blok(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    c.last_reserve_margin_breakdown = {
        "needed_kwh_before_margin": 2.47,
        "lange_horizon_extra_kwh": 2.468,
    }
    c.beschikbare_energie_kwh = lambda: 1.47
    c._vol_voor_nacht = True

    _aandacht, info = c._tekortnachten_meldingen()

    assert not any("Verwacht tekort tot het goedkope blok" in p for p in info)


# --- de nachtmelding -------------------------------------------------------

def _verstuurd(c):
    gestuurd = []
    c._dispatch_notification = lambda **kw: gestuurd.append(kw.get("kind"))
    return gestuurd


def _situatie(c, beschikbaar, ruw, lange):
    c.last_available_kwh = beschikbaar
    c.last_reserve_margin_breakdown = {
        "needed_kwh_before_margin": ruw,
        "lange_horizon_extra_kwh": lange,
        "reserve_kwh_after_margin": ruw * 1.5,
    }
    c.notification_active_conditions = ["battery_wont_last_night"]


def test_de_nachtmelding_telt_de_lange_horizon_niet(make_coordinator, hass):
    """Actief (hysterese: tekort > 0 houdt hem aan) - met alleen een tekort
    na het blok is er geen nachttekort en gaat hij niet opnieuw af."""
    c = make_coordinator({})
    _situatie(c, beschikbaar=1.47, ruw=2.47, lange=2.468)
    gestuurd = _verstuurd(c)

    c._evaluate_new_notifications(datetime(2026, 10, 7, 23, 0, tzinfo=timezone.utc))

    assert "battery_wont_last_night" not in gestuurd


def test_de_nachtmelding_ziet_een_tekort_tot_het_blok(make_coordinator, hass):
    c = make_coordinator({})
    _situatie(c, beschikbaar=1.0, ruw=4.0, lange=1.0)
    gestuurd = _verstuurd(c)

    c._evaluate_new_notifications(datetime(2026, 10, 7, 23, 0, tzinfo=timezone.utc))

    assert "battery_wont_last_night" in gestuurd


# --- Monte Carlo -----------------------------------------------------------

def _mc(make_coordinator, hass, beschikbaar):
    c = make_coordinator({"available_energy_sensor_entity": "sensor.available_energy"})
    hass.states.set("sensor.available_energy", str(beschikbaar))
    for h in range(24):
        c.hourly_consumption_profile[h] = [0.3] * 7
        c.pv_hourly_bias_history[h] = [1.0] * 7
    c._get_smoothed_consumption_correction_ratio = lambda h: 1.0
    c.regelverschuiving_kw = lambda: 0.0
    c._estimate_pv_kwh_for_period = lambda s, e, veilig=False: 0.0
    c.last_cheap_block_start = BLOK
    c._lange_reserve_extra_kwh = 3.0
    return c


def test_monte_carlo_stand_is_de_kans_tot_het_blok(make_coordinator, hass):
    c = _mc(make_coordinator, hass, beschikbaar=0)
    c._run_monte_carlo_simulation(NU, BLOK)
    tot_blok = c.monte_carlo_deterministisch_tot_blok_kwh
    assert tot_blok is not None and tot_blok > 0
    # Genoeg voor de nacht, niet voor het deel na het blok.
    hass.states.set("sensor.available_energy", str(tot_blok + 1.0))

    c._run_monte_carlo_simulation(NU, BLOK)

    assert c.monte_carlo_shortfall_probability_percent == 0.0
    assert c.monte_carlo_kans_incl_lange_horizon_pct == 100.0
    assert c.monte_carlo_mediaan_tot_blok_kwh == pytest.approx(tot_blok, abs=0.001)
    assert c.monte_carlo_median_deficit_kwh == pytest.approx(tot_blok + 3.0, abs=0.001)


def test_de_sensor_toont_beide_kansen(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        MonteCarloAdvisorySensor,
    )

    c = _mc(make_coordinator, hass, beschikbaar=100)
    c._run_monte_carlo_simulation(NU, BLOK)
    s = MonteCarloAdvisorySensor(c, "x")
    a = s.extra_state_attributes

    assert s.native_value == a["tekortkans_tot_blok_pct"] == 0.0
    assert a["tekortkans_incl_lange_horizon_pct"] == 0.0
    assert "tot het goedkoopste blok" in a["basis"]
    assert "lange_horizon" in a["basis"]
    assert a["mediaan_diepste_tekort_tot_blok_kwh"] is not None
    assert "verwacht_tekort_tot_blok_kwh" in a["verwacht_tekort"]


# --- kalibratie 22:00 ------------------------------------------------------

def test_de_stand_van_22_uur_is_tot_het_blok(make_coordinator, hass):
    c = _mc(make_coordinator, hass, beschikbaar=0)
    c._run_monte_carlo_simulation(NU, BLOK)
    hass.states.set(
        "sensor.available_energy", str(c.monte_carlo_deterministisch_tot_blok_kwh + 1.0)
    )
    avond = datetime(2026, 10, 7, 22, 4, tzinfo=timezone.utc)
    blok = avond + timedelta(hours=12)
    c.last_cheap_block_start = blok

    c._run_monte_carlo_simulation(avond, blok)

    stand = c.mc_22u_per_avond["2026-10-07"]
    assert stand["basis"] == "tot_blok"
    assert stand["kans_pct"] == c.monte_carlo_shortfall_probability_percent
    assert stand["kans_incl_lange_horizon_pct"] == c.monte_carlo_kans_incl_lange_horizon_pct


def test_de_kalibratie_slaat_oude_standen_over(make_coordinator, hass):
    """Een stand van v5.45/v5.46 telde de lange horizon mee: 100% voor een
    nacht die het blok ruim haalde. Die vergelijking is niet eerlijk."""
    c = make_coordinator({})
    c.reserve_daily_records = [
        {"date": "2026-10-08", "shortfall": False, "mc_22u": {"kans_pct": 100.0}},
        {"date": "2026-10-09", "shortfall": False, "mc_22u": {"kans_pct": 5.0, "basis": "tot_blok"}},
    ]

    k = c.get_mc_kalibratie_22u()

    assert k["nachten"] == 1
    assert k["brier"] == pytest.approx(0.0025, abs=0.001)
    assert k["nachten_oude_basis_uitgesloten"] == 1


def test_de_reserve_zelf_verandert_niet(make_coordinator, hass):
    """Harde regel: de lange horizon blijft in de reserve van de sturing."""
    c = _mc(make_coordinator, hass, beschikbaar=5)

    c._get_dynamic_discharge_reserve_kwh(NU, BLOK)
    u = c.last_reserve_margin_breakdown

    assert u["lange_horizon_extra_kwh"] == 3.0
    tot, na = c._nodig_tot_en_na_blok_kwh()
    assert tot + na == pytest.approx(u["needed_kwh_before_margin"], abs=0.001)
