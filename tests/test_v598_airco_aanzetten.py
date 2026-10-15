"""v5.98.0: de airco-verwachting leert op het AANZETTEN, niet op de compressor.

Gemeld: "EMS moet voor inschakelen airco alleen kijken wanneer deze wordt
aangezet." Stond de airco op "heat" en sloeg de compressor af en weer aan,
dan telde dat als "aangezet" (21 °C: 64,7 %).
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    AIRCO_LEER_VERSIE,
    CONF_AIRCO_CLIMATE_ENTITY,
)

NU = datetime(2026, 10, 14, 18, 40, tzinfo=timezone.utc)
CONFIG = {
    "living_room_temperature_sensor_entity": "sensor.kamer",
    "living_room_humidity_sensor_entity": "sensor.vocht",
    CONF_AIRCO_CLIMATE_ENTITY: "climate.woonkamer",
}


def _ronde(c, hass, moment, temp_c, stand="off", compressor=False):
    hass.states.set("sensor.kamer", str(temp_c), {"unit_of_measurement": "°C"})
    hass.states.set("sensor.vocht", "50", {"unit_of_measurement": "%"})
    hass.states.set("climate.woonkamer", stand,
                    {"hvac_action": "heating" if compressor else ("idle" if stand != "off" else "off")})
    c.last_heavy_load_source = "airco" if compressor else None
    c._update_living_room_airco_prediction(moment)


def _verse(make_coordinator):
    c = make_coordinator(dict(CONFIG))
    c.living_room_temp_bucket_history = {}
    c.living_room_temp_bucket_humidity = {}
    c.living_room_temp_bucket_direction = {}
    c._temp_prediction_pending = []
    c.airco_bakje_laatste_start = {}
    c.airco_door_ems = False
    return c


def test_thermostaat_aan_af_telt_niet(make_coordinator, hass):
    c = _verse(make_coordinator)
    # 3 uur op "heat" bij 21 °C, compressor elke 10 min aan/af
    for m in range(0, 181):
        _ronde(c, hass, NU + timedelta(minutes=m), 21.0, stand="heat",
               compressor=(m // 10) % 2 == 0)
    assert c.living_room_temp_bucket_history.get("21.0", []) == []
    assert c._temp_prediction_pending == []


def test_aanzetten_telt_met_richting(make_coordinator, hass):
    c = _verse(make_coordinator)
    _ronde(c, hass, NU, 19.0)                                   # uit: waarneming start
    _ronde(c, hass, NU + timedelta(minutes=20), 19.0, stand="heat")  # aangezet, compressor nog stil
    _ronde(c, hass, NU + timedelta(minutes=61), 19.5, stand="heat", compressor=True)
    assert c.living_room_temp_bucket_history["19.0"] == [True]
    assert c.living_room_temp_bucket_direction["19.0"] == ["verwarmen"]


def test_uit_blijft_uit(make_coordinator, hass):
    c = _verse(make_coordinator)
    for m in range(0, 61):
        _ronde(c, hass, NU + timedelta(minutes=m), 18.0)
    assert c.living_room_temp_bucket_history["18.0"] == [False]


def test_leren_opnieuw():
    assert AIRCO_LEER_VERSIE == 4
