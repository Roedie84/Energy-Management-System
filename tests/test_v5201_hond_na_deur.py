"""v5.201.0: na een deur alleen de radar (de hond) - dan weg.

Ruud 09-11 15:00: "binary_sensor.ultimatesensor_occupancy detecteert
waarschijnlijk vaak de hond, hierdoor onterecht thuis". 14:28 gang, voordeur,
daarna alleen de woonkamer-radar: de één-plek-regel greep niet omdat een deur
in het venster hem blokkeerde.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_PRESENCE_MOTION_SENSORS,
    CONF_PRESENCE_PERSON_ENTITIES,
    PRESENCE_EEN_PLEK_NA_DEUR_MINUTEN,
)

RADAR = "binary_sensor.ultimatesensor_occupancy"
GANG = "binary_sensor.gang_beweging"
DEUR = "binary_sensor.deur_sensor_voordeur_contact"
RUUD = "person.ruud_maarse"
NU = datetime(2026, 11, 9, 14, 0, tzinfo=timezone.utc)


def _huis(make_coordinator, hass, telefoon="Ruud Werk"):
    c = make_coordinator({CONF_PRESENCE_MOTION_SENSORS: [RADAR, GANG, DEUR],
                          CONF_PRESENCE_PERSON_ENTITIES: [RUUD]})
    hass.states.set(RADAR, "on", {"device_class": "occupancy"})
    hass.states.set(GANG, "off", {"device_class": "motion"})
    hass.states.set(DEUR, "off", {"device_class": "door"})
    hass.states.set(RUUD, telefoon, {"friendly_name": "Ruud Maarse"})
    c.presence_state = "thuis"
    return c


def _gezien(c, **minuten):
    c.presence_last_seen = {
        {"gang": GANG, "deur": DEUR, "radar": RADAR}[k]: (NU - timedelta(minutes=m)).isoformat()
        for k, m in minuten.items()
    }
    c.last_motion_at = NU - timedelta(minutes=min(minuten.values()))


def test_vertrek_daarna_alleen_de_hond_is_weg(make_coordinator, hass):
    c = _huis(make_coordinator, hass)
    _gezien(c, gang=31, deur=30, radar=1)
    c._update_presence(NU)
    assert c.presence_state == "weg"
    assert "na de deur" in c._aanleiding_aanwezigheid(NU, "thuis")


def test_vlak_na_de_deur_nog_niet(make_coordinator, hass):
    c = _huis(make_coordinator, hass)
    _gezien(c, gang=11, deur=PRESENCE_EEN_PLEK_NA_DEUR_MINUTEN - 10, radar=1)
    c._update_presence(NU)
    assert c.presence_state == "thuis"


def test_thuiskomst_gang_na_de_deur_blijft_thuis(make_coordinator, hass):
    c = _huis(make_coordinator, hass)
    _gezien(c, deur=30, gang=29, radar=1)
    c._update_presence(NU)
    assert c.presence_state == "thuis"


def test_telefoon_thuis_blijft_thuis(make_coordinator, hass):
    c = _huis(make_coordinator, hass, telefoon="home")
    _gezien(c, gang=31, deur=30, radar=1)
    c._update_presence(NU)
    assert c.presence_state == "thuis"
