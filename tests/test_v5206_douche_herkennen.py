"""v5.206.0: een douchebeurt herkennen aan de ketel TIJDENS het tappen.

Ruud 10-11 14:35: "misschien alleen de herkenning van een douchebeurt
optimaliseren?" De bron werd bepaald bij het afsluiten van de sessie, twee
minuten na het laatste water; de ketel staat dan weer op 6 W. Gemeten 01-11
t/m 10-11: zes tot zeven beurten van 45-140 liter met de ketel op ~170 W, geen
ervan als douche geboekt; wel drie kranen van 5-11 liter.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_QUOOKER_POWER_SENSOR,
    WATER_SHOWER_MIN_LITERS,
)

KETEL = "sensor.cv_ketel_vermogen"
T = datetime(2026, 11, 8, 18, 45, tzinfo=timezone(timedelta(hours=1)))


def _c(make_coordinator, hass):
    c = make_coordinator({CONF_QUOOKER_POWER_SENSOR: "sensor.qk"})
    c.nilm_confirmed_devices = {KETEL: {"friendly_name": "CV-ketel Vermogen"}}
    hass.states.set(KETEL, "6.4")
    hass.states.set("sensor.qk", "0")
    return c


def _sessie(c, hass, minuten, debiet, ketel_w):
    """Water loopt `minuten` lang; de ketel staat aan tot het water stopt."""
    t = T
    c._process_water_flow_sample(debiet, t)
    hass.states.set(KETEL, str(ketel_w))
    for _ in range(minuten * 2):
        t += timedelta(seconds=30)
        c._process_water_flow_sample(debiet, t)
    hass.states.set(KETEL, "6.4")          # ketel uit zodra het water stopt
    for _ in range(6):
        t += timedelta(seconds=30)
        c._process_water_flow_sample(0.0, t)
    return c.water_session_history[-1]


def test_douche_herkend_terwijl_ketel_bij_afsluiten_uit_is(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    s = _sessie(c, hass, 10, 6.0, 170)
    assert s["bron"] == "douche", s
    assert 55 <= s["liter"] <= 65
    assert c._water_session_bron_max == {}      # schoon voor de volgende sessie


def test_zonder_ketel_geen_douche(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    s = _sessie(c, hass, 10, 6.0, 6.4)
    assert s["bron"] != "douche"


def test_lange_kraan_met_weinig_water_is_geen_douche(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    s = _sessie(c, hass, 5, 1.7, 170)       # 8,5 liter in 5 minuten
    assert s["liter"] < WATER_SHOWER_MIN_LITERS
    assert s["bron"] == "warm water kort"


def test_vorige_sessie_telt_niet_mee(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _sessie(c, hass, 10, 6.0, 170)
    s = _sessie(c, hass, 10, 6.0, 6.4)
    assert s["bron"] != "douche"
