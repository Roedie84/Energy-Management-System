"""De nieuwe bronnen, gekoppeld aan de coördinator (v5.14)."""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 21, 14, 0, tzinfo=timezone.utc)


def _met(c, **config):
    c.config = dict(c.config or {})
    c.config.update(config)
    return c


# --- instraling ---------------------------------------------------------


def test_een_instralingsmonster_per_tien_minuten(make_coordinator, hass):
    c = _met(
        make_coordinator({}),
        irradiance_sensor_entity="sensor.straling",
        pv_power_sensor_entity="sensor.pv",
    )
    hass.states.set("sensor.straling", "284")
    hass.states.set("sensor.pv", "1383")
    c.get_sun_elevation_degrees = lambda: 31.0
    c.get_sun_azimuth_degrees = lambda: 222.0
    c.instraling_verhouding = {}

    c._meet_instraling(NU)
    c._meet_instraling(NU + timedelta(minutes=5))     # te snel
    c._meet_instraling(NU + timedelta(minutes=11))

    assert len(c.instraling_verhouding["220"]) == 2
    assert c.instraling_verhouding["220"][0] == pytest.approx(1383 / 284, abs=0.01)


def test_zonder_instralingssensor_gebeurt_er_niets(make_coordinator, hass):
    c = make_coordinator({})
    c.instraling_verhouding = {}

    c._meet_instraling(NU)

    assert c.instraling_verhouding == {}


# --- ventilator ---------------------------------------------------------


def test_het_ventilatorverbruik_wordt_per_dag_opgeteld(make_coordinator, hass):
    c = _met(
        make_coordinator({}),
        battery_cooling_fan_power_sensor_entity="sensor.fan",
    )
    c.ventilator_kwh_per_dag = {}
    c._ventilator_vermogens_aan = []
    hass.states.set("sensor.fan", "40")

    moment = NU
    for _ in range(61):              # een uur, elke minuut
        c._meet_ventilator(moment)
        moment += timedelta(minutes=1)

    assert c.ventilator_kwh_per_dag[NU.date().isoformat()] == pytest.approx(0.04, abs=0.001)
    assert c.ventilator_vermogen_aan_w() == 40.0


def test_de_koeltekst_noemt_het_gemeten_vermogen(make_coordinator, hass):
    """Niet meer "een paar watt" - de stekker stond op 325 kWh."""
    c = make_coordinator({})
    c._ventilator_vermogens_aan = [40.0, 41.0, 39.0]

    assert c._ventilator_omschrijving() == "40 W ventilator"


def test_zonder_meting_blijft_de_koeltekst_neutraal(make_coordinator, hass):
    c = make_coordinator({})
    c._ventilator_vermogens_aan = []

    assert c._ventilator_omschrijving() == "de ventilator"


# --- verwarmen ----------------------------------------------------------


def test_het_verwarmingsadvies_leest_de_gasprijs(make_coordinator, hass):
    c = _met(make_coordinator({}), gas_price_sensor_entity="sensor.gas")
    hass.states.set("sensor.gas", "1.7427")
    c.huidige_prijs_eur_per_kwh = lambda now=None: 0.2371
    c._get_live_outdoor_temp_c = lambda now: 12.0

    assert c.get_verwarmingsadvies()["advies"] == "airco"


# --- twee zonvoorspellingen ---------------------------------------------


def test_de_tweede_voorspelling_komt_in_het_voorspellingsverloop(make_coordinator, hass):
    c = _met(
        make_coordinator({}),
        second_pv_forecast_today_sensor_entity="sensor.fs",
    )
    hass.states.set("sensor.fs", "9.4")
    c.voorspellingsverloop = {}
    c.pv_production_today_kwh = 0.2
    c._estimate_pv_kwh_for_period = lambda a, b, **kw: 13.8
    c.voorspelde_zon_vandaag_kwh = lambda now=None: (14.0, "vastgelegd")

    c.noteer_voorspellingsverloop(NU.replace(hour=8))

    assert c.voorspellingsverloop[NU.date().isoformat()]["8"]["tweede_dagvoorspelling_kwh"] == 9.4


def test_het_ensemble_legt_beide_naast_de_opbrengst(make_coordinator, hass, monkeypatch):
    import custom_components.energy_management_system.coordinator as mod

    monkeypatch.setattr(mod.dt_util, "now", lambda: NU)
    c = make_coordinator({})
    c.voorspellingsverloop = {
        f"2026-09-{d:02d}": {"8": {"dagvoorspelling_kwh": 14.0, "tweede_dagvoorspelling_kwh": 10.0}}
        for d in range(10, 20)
    }
    c.energy_daily_history = [
        {"datum": f"2026-09-{d:02d}", "opwek_kwh": 10.0} for d in range(10, 20)
    ]
    c.voorspelde_zon_vandaag_kwh = lambda now=None: (14.0, "vastgelegd")

    uit = c.get_pv_ensemble()

    assert uit["dagen"] == 10
    assert uit["beste"] == "tweede"


def test_de_nieuwe_bronnen_staan_in_de_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()
    for functie in (
        "get_pv_ensemble",
        "get_instraling_analyse",
        "get_verwarmingsadvies",
        "get_ventilator_verbruik",
    ):
        assert functie in bron, functie


def test_de_uitkomsten_staan_op_de_sensoren(make_coordinator, hass):
    """Zichtbaar in Home Assistant zelf, niet alleen in de export - als
    attribuut op een sensor waar ze inhoudelijk bij horen, zodat er geen
    nieuwe entiteiten bij komen."""
    from custom_components.energy_management_system import sensor as s

    c = make_coordinator({})
    paren = (
        (s.ClimateForecastSensor, "verwarmingsadvies"),
        (s.PvHourlyBiasSensor, "tweede_voorspelling"),
        (s.PvInstallationProfileSensor, "instraling_per_richting"),
        (s.BatteryCoolingSensor, "ventilatorverbruik"),
    )
    for klasse, attribuut in paren:
        sensor = klasse(c, "x")
        assert attribuut in sensor.extra_state_attributes, (klasse.__name__, attribuut)
