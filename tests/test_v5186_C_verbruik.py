"""v5.186.0 spoor C - de verbruiksverwachting.

31. Witgoed niet dubbel: het uurprofiel (gemiddelde, v5.74) bevat het
    gemiddelde witgoed; gepland/lopend witgoed kwam daar bovenop.
32. De live correctie tegen het uur van NU, niet het uur van het kwartier.
33. De reserve heeft een eigen correctiebudget, ook binnen een plan.
34. Klimaat-extra's ook in de planenergie.
35. Airco: gemiddelde i.p.v. mediaan; niet dubbel met de live correctie.
37. Een uur telt pas in het profiel vanaf 45 gemeten minuten.
42. Witgoed in de droogfase blokkeert de airco-correctie niet meer.
Klein: de correctiemetingen hebben een tijdstempel.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import airco_ritme as R
from custom_components.energy_management_system import coordinator as mod
from custom_components.energy_management_system.const import (
    CONSUMPTION_CORRECTION_MAX_EXTRA_KWH,
    LOPEND_APPARAAT_VASTE_POST_KWH,
)

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 4, 21, 0, tzinfo=TZ)   # woensdag


@pytest.fixture
def klok(monkeypatch):
    def zet(moment):
        monkeypatch.setattr(mod.dt_util, "now", lambda: moment)
    zet(NU)
    return zet


def _witgoed(make_coordinator, hass, vaat_w=0.0):
    c = make_coordinator({
        "dishwasher_power_sensor_entity": "sensor.vaat",
        "washing_machine_power_sensor_entity": "sensor.was",
    })
    hass.states.set("sensor.vaat", str(vaat_w))
    hass.states.set("sensor.was", "0")
    return c


# --- 37: een gedeeltelijk uur --------------------------------------------


def test_een_kwartier_na_een_herstart_telt_niet(make_coordinator):
    c = make_coordinator({})
    c._current_tracked_hour = 12
    c._hour_energy_kwh, c._hour_duration_hours = 0.2, 20 / 60
    c._finalize_hourly_bucket(NU)
    assert c.hourly_consumption_profile.get(12) is None
    assert c._hour_duration_hours == 0.0


def test_drie_kwartier_telt_wel(make_coordinator):
    c = make_coordinator({})
    c._current_tracked_hour = 12
    c._hour_energy_kwh, c._hour_duration_hours = 0.3, 0.75
    c._finalize_hourly_bucket(NU)
    assert c.hourly_consumption_profile[12] == [pytest.approx(0.4)]


# --- 31: het witgoedaandeel ------------------------------------------------


def test_het_witgoed_wordt_in_de_pas_bijgehouden(make_coordinator, hass):
    c = _witgoed(make_coordinator, hass, vaat_w=1200.0)
    c._current_tracked_hour = 20
    c._tel_uurenergie(1500.0, 1.0)          # huis 1,5 kW, waarvan 1,2 vaatwasser
    c._finalize_hourly_bucket(NU)
    assert c.hourly_consumption_profile[20] == [pytest.approx(1.5)]
    assert c.witgoed_uuraandeel["vaatwasser-20"] == [pytest.approx(1.2)]
    assert c.witgoed_uuraandeel["wasmachine-20"] == [0.0]


def test_het_witgoed_is_nooit_meer_dan_het_huis(make_coordinator, hass):
    c = _witgoed(make_coordinator, hass, vaat_w=3000.0)
    c._current_tracked_hour = 20
    c._tel_uurenergie(1000.0, 1.0)
    c._finalize_hourly_bucket(NU)
    assert c.witgoed_uuraandeel["vaatwasser-20"] == [pytest.approx(1.0)]


def test_fractie_alleen_over_de_dagen_met_een_aandeel(make_coordinator, hass):
    """Overgang: de oude dagen (zonder aandeel) tellen niet als witgoed."""
    c = _witgoed(make_coordinator, hass)
    c.hourly_consumption_profile = {20: [0.4] * 6 + [1.6]}
    c.witgoed_uuraandeel = {"vaatwasser-20": [1.2]}     # alleen de laatste dag
    assert c._witgoed_fractie("vaatwasser", 20) == pytest.approx(1.2 / 1.6)
    c.witgoed_uuraandeel = {"vaatwasser-20": [0.0, 1.2]}
    assert c._witgoed_fractie("vaatwasser", 20) == pytest.approx(1.2 / 2.0)


def test_aandeel_gaat_eraf_als_het_apparaat_apart_telt(make_coordinator, hass, klok):
    c = _witgoed(make_coordinator, hass)
    c.hourly_consumption_profile = {h: [0.4, 0.6] for h in range(24)}
    c.witgoed_uuraandeel = {"vaatwasser-22": [0.0, 0.2]}   # 0,2 van 1,0 kWh
    moment = NU.replace(hour=22)
    c._bekend_witgoed = lambda: frozenset()
    assert c._basis_uur_kw(22, moment) == pytest.approx(0.5)
    c._bekend_witgoed = lambda: frozenset({"vaatwasser"})
    assert c._basis_uur_kw(22, moment) == pytest.approx(0.5 * 0.8)
    # verder dan de planningshorizon blijft het aandeel staan
    assert c._basis_uur_kw(22, moment + timedelta(days=2)) == pytest.approx(0.5)


def test_geplande_vaatwasser_telt_een_keer(make_coordinator, hass, klok):
    """Het geval van punt 31: profiel met het gemiddelde witgoed + gepland."""
    c = _witgoed(make_coordinator, hass)
    c.hourly_consumption_profile = {h: [0.3] * 6 + [1.5] for h in range(24)}
    c.witgoed_uuraandeel = {f"vaatwasser-{h}": [0.0] * 6 + [1.2] for h in range(24)}
    c.geplande_witgoed_kwh_in_periode = lambda a, b: 1.2 if a <= NU.replace(hour=22) < b else 0.0
    c.lopend_witgoed_kwh_in_periode = lambda a, b: 0.0
    c._get_smoothed_consumption_correction_ratio = lambda uur: 1.0
    a, b = NU.replace(hour=22), NU.replace(hour=23)
    c._bekend_witgoed = lambda: frozenset()
    oud = c._estimate_consumption_kwh_for_period(a, b)
    c._bekend_witgoed = lambda: frozenset({"vaatwasser"})
    nieuw = c._estimate_consumption_kwh_for_period(a, b)
    gemiddeld = (0.3 * 6 + 1.5) / 7
    assert oud == pytest.approx(gemiddeld + 1.2)
    assert nieuw == pytest.approx(gemiddeld - 1.2 / 7 + 1.2)


def test_bekend_witgoed_uit_planning_en_lopend(make_coordinator):
    c = make_coordinator({})
    c.get_planned_appliance_load = lambda now=None: {"apparaten": [{"apparaat": "wasmachine", "kwh": 0.9}]}
    c._dishwasher_state, c._dishwasher_cycle_started_at = "actief", NU
    assert c._bekend_witgoed() == frozenset({"wasmachine", "vaatwasser"})


def test_lopend_witgoed_telt_ook_buiten_de_wandeling(make_coordinator, klok):
    c = make_coordinator({})
    c.verbruik_uur_kw = lambda uur, moment=None: 0.4
    c._get_smoothed_consumption_correction_ratio = lambda uur: 1.0
    c.geplande_witgoed_kwh_in_periode = lambda a, b: 0.0
    c.lopend_witgoed_kwh_in_periode = lambda a, b: 0.7
    assert c._estimate_consumption_kwh_for_period(NU, NU + timedelta(hours=1)) == pytest.approx(1.1)


def test_vaste_post_oven_alleen_boven_het_koken_in_het_profiel(make_coordinator, klok):
    c = make_coordinator({})
    profiel = {h: 0.25 for h in range(24)}
    profiel[21] = 0.85                       # koken zit in het uur van 21:00
    c.verbruik_uur_kw = lambda uur, moment=None: profiel[uur]
    c.last_heavy_load_source = "oven"
    c._vaste_post_bron = c._vaste_post_tot = None
    c._dishwasher_state = c._washing_machine_state = None
    post = LOPEND_APPARAAT_VASTE_POST_KWH["oven"]
    totaal = c.lopend_witgoed_kwh_in_periode(NU, NU + timedelta(hours=2))
    assert totaal == pytest.approx(post - 0.6)
    # zonder volledig profiel de hele post
    c.verbruik_uur_kw = lambda uur, moment=None: None
    assert c.lopend_witgoed_kwh_in_periode(NU, NU + timedelta(hours=2)) == pytest.approx(post)


# --- 32: de verhouding van NU ---------------------------------------------


def test_verhouding_tegen_het_uur_van_nu(make_coordinator, klok):
    """Reviewer: 21:00 live 0,55 kW = het profiel van 21:00; voor een kwartier
    van 23:00 (profiel 0,30) gaf de oude code 1,8x."""
    c = make_coordinator({})
    prof = {h: 0.3 for h in range(24)}
    prof.update({21: 0.55, 22: 0.45, 23: 0.30})
    c.hourly_consumption_profile = {h: [v] * 7 for h, v in prof.items()}
    c._recent_consumption_readings_kw = [0.55] * 4
    c.last_heavy_load_source = None
    assert c._get_smoothed_consumption_correction_ratio() == 1.0
    a = NU.replace(hour=23)
    assert c._estimate_consumption_kwh_for_period(a, a + timedelta(minutes=15)) == pytest.approx(0.075)


def test_verhouding_gebruikt_het_dagtype(make_coordinator, klok):
    c = make_coordinator({})
    c.hourly_consumption_profile = {21: [0.30] * 7}
    c.daytype_consumption_profile = {"werkdag-21": [0.60] * 5}
    c._recent_consumption_readings_kw = [0.60] * 4
    c.last_heavy_load_source = None
    assert c._get_smoothed_consumption_correction_ratio() == 1.0


def test_correctiemetingen_vervallen_op_tijd(make_coordinator, klok):
    c = make_coordinator({})
    c._recent_consumption_readings_kw = []
    c._read_corrected_consumption_power = lambda: 2000.0
    c._track_recent_consumption_reading(NU - timedelta(minutes=50))
    c._read_corrected_consumption_power = lambda: 400.0
    c._track_recent_consumption_reading(NU)
    assert c._recent_consumption_readings_kw == [0.4]


# --- 42: droogfase en de airco ----------------------------------------------


def test_droogfase_is_geen_zwaar_verbruik(make_coordinator, hass):
    c = _witgoed(make_coordinator, hass, vaat_w=25.0)
    assert c._get_confirmed_heavy_load_source(NU) is None
    hass.states.set("sensor.vaat", "1800")
    assert c._get_confirmed_heavy_load_source(NU) == "vaatwasser"


def test_airco_gaat_voor(make_coordinator, hass):
    from custom_components.energy_management_system.const import CONF_AIRCO_CLIMATE_ENTITY

    c = _witgoed(make_coordinator, hass, vaat_w=1800.0)
    c.config[CONF_AIRCO_CLIMATE_ENTITY] = "climate.airco"
    c._airco_draait = lambda ent: ent == "climate.airco"
    assert c._get_confirmed_heavy_load_source(NU) == "airco"


# --- 35: airco ----------------------------------------------------------------


def test_airco_extra_tegen_het_gemiddelde():
    r = R.leeg()
    for i in range(5):
        R.noteer_uur(r, 19, 0.8 if i < 3 else 0.0)
    nu = datetime(2026, 10, 20, 18, 0, tzinfo=TZ)
    uit = R.gebruik_kwh(r, nu, nu + timedelta(hours=2))
    # verwacht 0,8 (kans 0,6), al in het profiel het gemiddelde 0,48
    assert uit["extra_kwh"] == pytest.approx(0.32, abs=1e-3)
    assert R.profiel_kwh(r, nu, nu + timedelta(hours=2)) == pytest.approx(0.48)


def test_zekere_airco_niet_in_de_live_correctie(make_coordinator):
    c = make_coordinator({})
    c._recent_consumption_readings_kw = []
    c._read_corrected_consumption_power = lambda: 1400.0
    c._airco_vermogen_w = lambda: 1000.0
    c._airco_zeker_meegeteld = lambda now: True
    c._track_recent_consumption_reading(NU)
    assert c._recent_consumption_readings_kw == [pytest.approx(0.4)]
    c._airco_zeker_meegeteld = lambda now: False
    c._track_recent_consumption_reading(NU)
    assert c._recent_consumption_readings_kw[-1] == pytest.approx(1.4)


def test_zekere_airco_gebruikt_de_mediaan(make_coordinator, klok):
    c = make_coordinator({})
    c.hourly_consumption_profile = {21: [0.4] * 7}
    c._recent_consumption_readings_kw = [0.4, 0.4, 0.4, 2.0]
    c.last_heavy_load_source = "airco"
    c._airco_zeker_meegeteld = lambda now: False
    assert c._get_smoothed_consumption_correction_ratio() > 1.0     # laatste meting direct
    c._airco_zeker_meegeteld = lambda now: True
    assert c._get_smoothed_consumption_correction_ratio() == 1.0


def test_airco_zeker_alleen_met_een_uit_tijd(make_coordinator, klok):
    c = make_coordinator({})
    c._airco_vermogen_w = lambda: 900.0
    c.instelling = lambda sleutel, standaard=None: "23:00"
    assert c._airco_zeker_meegeteld(NU) is True
    c.instelling = lambda sleutel, standaard=None: ""
    assert c._airco_zeker_meegeteld(NU) is False
    c._airco_vermogen_w = lambda: 10.0
    assert c._airco_zeker_meegeteld(NU) is False


# --- 33: de reserve heeft een eigen budget ----------------------------------


def test_reserve_binnen_een_leeg_planbudget_gelijk(make_coordinator):
    c = make_coordinator({})
    gezien = []

    def bereken(now, blok, bewaar=True):
        gezien.append(c._correctie_uit_budget(1.0))
        return 1.0

    c._bereken_dynamische_reserve_kwh = bereken
    c._ronde_stempel = lambda: None
    with c._gedeeld_correctiebudget():
        c._correctie_uit_budget(CONSUMPTION_CORRECTION_MAX_EXTRA_KWH)   # plan op
        c._get_dynamic_discharge_reserve_kwh(NU, NU + timedelta(hours=8), bewaar=False)
        assert c._correctie_uit_budget(1.0) == 0.0                      # plan blijft op
    assert gezien == [1.0]
    assert getattr(c, "_correctie_budget", None) is None


# --- 34: klimaat-extra's in de planenergie -----------------------------------


def test_klimaat_extra_per_kwartier_verdeeld(make_coordinator, klok):
    c = make_coordinator({})
    c._airco_gebruik_extra_kwh = lambda a, b: {"uren": [
        {"begin": NU.replace(hour=22).isoformat(), "kwh": 0.4},
    ]}
    c._airco_ochtend_extra_kwh = lambda a, b: {"extra_kwh": 0.0}
    c._temperatuur_extra_kwh = lambda a, b, al=0.0: {"extra_kwh": 0.0}
    a = NU.replace(hour=22, minute=15)
    assert c._klimaat_extra_kwh_in(a, a + timedelta(minutes=15)) == pytest.approx(0.1)
    assert c._klimaat_extra_kwh_in(NU, NU + timedelta(minutes=15)) == 0.0


def test_temperatuurmodel_per_nacht(make_coordinator, klok):
    c = make_coordinator({})
    c._airco_gebruik_extra_kwh = lambda a, b: {"uren": []}
    c._airco_ochtend_extra_kwh = lambda a, b: {"extra_kwh": 0.0}
    vensters = []

    def temp(a, b, al=0.0):
        vensters.append((a, b))
        return {"extra_kwh": 0.9}

    c._temperatuur_extra_kwh = temp
    totaal = c._klimaat_extra_kwh_in(NU, NU + timedelta(hours=37))
    assert vensters[0] == (NU.replace(hour=22), NU.replace(hour=7) + timedelta(days=1))
    assert totaal == pytest.approx(0.9 * len(vensters))
    # gelijk over de nacht: een uur van de eerste nacht is 1/9
    a = NU.replace(hour=23)
    assert c._klimaat_extra_kwh_in(a, a + timedelta(hours=1)) == pytest.approx(0.1)


def test_waardeplan_kwartier_telt_de_klimaat_extra_mee():
    bron = (mod.Path(mod.__file__).parent / "waardeplan_sturing.py").read_text()
    assert "self._klimaat_extra_kwh_in(van, eind)" in bron


def test_waardeplan_cache_in_utc():
    bron = (mod.Path(mod.__file__).parent / "waardeplan_sturing.py").read_text()
    assert "utc = now.astimezone(timezone.utc)" in bron
