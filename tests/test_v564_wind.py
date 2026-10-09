"""v5.64: wind in de klimaatprojectie en vooruit verwarmen met de airco.

Gevraagd 09-10: "Ook de windrichting is denk ik van belang?" en daarna
"Beide bouwen": wind in de projectie, en de airco vooruit aanzetten als de
projectie zegt dat het binnen een uur te koud wordt.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import airco_sturing, klimaat_wind

NU = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)


# --- de module -------------------------------------------------------------

def test_eenheden_worden_km_per_uur():
    assert klimaat_wind.naar_kmh(10, "m/s") == 36.0
    assert klimaat_wind.naar_kmh(20, "km/h") == 20.0
    assert klimaat_wind.naar_kmh(20, None) == 20.0
    assert klimaat_wind.naar_kmh("x", "km/h") is None


def test_windsleutel_kalm_telt_niet():
    assert klimaat_wind.windsleutel(5, 220) is None
    assert klimaat_wind.windsleutel(15, 220) == "zuidwest|matig"
    assert klimaat_wind.windsleutel(30, 60) == "noordoost|hard"
    assert klimaat_wind.windsleutel(30, None) is None


def test_correctie_pas_vanaf_vijf_metingen():
    r = {}
    for _ in range(4):
        klimaat_wind.leer_residu(r, "oost|hard", -0.2)
    assert klimaat_wind.correctie(r, "oost|hard")["c_per_uur"] is None
    klimaat_wind.leer_residu(r, "oost|hard", -0.3)
    c = klimaat_wind.correctie(r, "oost|hard")
    assert c["c_per_uur"] == -0.2 and not c["betrouwbaar"]


def test_historie_is_begrensd():
    r = {}
    for i in range(50):
        klimaat_wind.leer_residu(r, "oost|hard", i / 100)
    assert len(r["oost|hard"]) == klimaat_wind.WIND_HISTORIE


# --- het besluit ------------------------------------------------------------

def _besluit(**extra):
    basis = dict(
        woonkamer_c=19.4, aanwezigheid="thuis", aanzet_c=19.0, doel_c=21.0,
        advies="airco", handmatig=False, airco_stand="off", door_ems_aan=False,
        setpunten_gezien=5, setpunten_nodig=5,
    )
    basis.update(extra)
    return airco_sturing.besluit(**basis)


def test_zonder_vooruitblik_als_voorheen():
    assert _besluit()["actie"] == "niets"


def test_vooruit_verwarmen_als_het_binnen_een_uur_te_koud_wordt():
    uit = _besluit(vooruit={"verwacht_c": 18.8, "wind": "oost 30 km/h"})
    assert uit["actie"] == "verwarmen"
    assert "Vooruit" in uit["tekst"] and "oost 30 km/h" in uit["redenen_tekst"]


def test_vooruit_niet_als_de_verwachting_warm_genoeg_is():
    assert _besluit(vooruit={"verwacht_c": 19.2})["actie"] == "niets"


def test_vooruit_niet_als_niemand_thuis_is():
    uit = _besluit(aanwezigheid="weg", vooruit={"verwacht_c": 18.0})
    assert uit["actie"] == "niets"


def test_vooruit_niet_als_gas_goedkoper_is():
    assert _besluit(advies="gas", vooruit={"verwacht_c": 18.0})["actie"] == "niets"


def test_onnauwkeurige_projectie_staat_in_de_redenen():
    uit = _besluit(vooruit={"verwacht_c": None, "reden": "projectie nog niet nauwkeurig genoeg"})
    assert uit["actie"] == "niets" and "nauwkeurig" in uit["redenen_tekst"]


# --- de coördinator ---------------------------------------------------------

def test_vooruitblik_vereist_een_nauwkeurige_projectie(make_coordinator):
    c = make_coordinator({})
    c.climate_forecast_trajectory = [
        {"tijd": NU.isoformat(), "kort_termijn_temp_c": 18.7, "betrouwbaarheid": "indicatief"}
    ]
    c.get_klimaat_projectie_kwaliteit = lambda: {"beschikbaar": True, "gemiddelde_afwijking_c": 0.8}
    assert c._airco_vooruitblik()["verwacht_c"] is None
    c.get_klimaat_projectie_kwaliteit = lambda: {"beschikbaar": True, "gemiddelde_afwijking_c": 0.3}
    assert c._airco_vooruitblik()["verwacht_c"] == 18.7
    c.get_klimaat_projectie_kwaliteit = lambda: {"beschikbaar": False}
    assert c._airco_vooruitblik()["verwacht_c"] is None


def test_windresidu_alleen_met_airco_uit_en_genoeg_celmetingen(make_coordinator):
    c = make_coordinator({})
    c.klimaat_wind_residuen = {}
    c.climate_rate_history = {"cel": [-0.1] * 6}
    c._klimaat_anker_wind = (30.0, 90.0)
    c._climate_anchor_airco_state = "verwarmen"
    c._leer_windresidu("cel", -0.5)
    assert c.klimaat_wind_residuen == {}
    c._climate_anchor_airco_state = "uit"
    c._leer_windresidu("cel", -0.5)
    assert c.klimaat_wind_residuen == {"oost|hard": [-0.4]}
    c.climate_rate_history = {"cel": [-0.1] * 2}
    c._leer_windresidu("cel", -0.5)
    assert c.klimaat_wind_residuen == {"oost|hard": [-0.4]}


def test_windcorrectie_per_uur_uit_de_voorspelling(make_coordinator):
    c = make_coordinator({})
    c.klimaat_wind_residuen = {"oost|hard": [-0.3] * 6}
    c._klimaat_wind_per_uur = {NU.strftime("%Y-%m-%dT%H"): (30.0, 90.0)}
    w = c._windcorrectie(NU, "uit")
    assert w["c_per_uur"] == -0.3 and w["label"] == "oost 30 km/h"
    assert c._windcorrectie(NU, "verwarmen")["c_per_uur"] is None
    assert c._windcorrectie(NU + timedelta(hours=3), "uit")["c_per_uur"] is None


def test_voorspelde_wind_wordt_onthouden(make_coordinator, hass):
    c = make_coordinator({})
    hass.states.set("weather.thuis", "rainy", {"wind_speed_unit": "m/s"})
    c._onthoud_voorspelde_wind(
        [{"datetime": NU.isoformat(), "wind_speed": 10, "wind_bearing": 45}], "weather.thuis"
    )
    (waarde,) = c._klimaat_wind_per_uur.values()
    assert waarde == (36.0, 45)


def test_ems_aanzet_leert_niet_mee(make_coordinator, hass):
    """Anders leert het EMS van zichzelf: vooruit aanzetten bij 19,4 zou de
    aanzettemperatuur naar 19,5 duwen, en dan weer verder."""
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["living_room_temperature_sensor_entity"] = "sensor.kamer"
    c.living_room_temp_bucket_history = {}
    hass.states.set("sensor.kamer", "19.4", {"unit_of_measurement": "°C"})
    c.last_heavy_load_source = None
    c._update_living_room_airco_prediction(NU)
    assert c._temp_prediction_pending
    c.airco_door_ems = True
    c.last_heavy_load_source = "airco"
    c._update_living_room_airco_prediction(NU + timedelta(minutes=10))
    c._update_living_room_airco_prediction(NU + timedelta(minutes=70))
    assert c.living_room_temp_bucket_history.get("19.5") in (None, [])


def test_wind_wordt_bewaard():
    from custom_components.energy_management_system.const import PERSISTED_PLAIN_FIELDS

    assert "klimaat_wind_residuen" in PERSISTED_PLAIN_FIELDS
