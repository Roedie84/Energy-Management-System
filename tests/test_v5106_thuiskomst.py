"""v5.106.0 - thuiskomst bevestigen: de hond zet het huis niet op "thuis".

Gemeld 20-10 13:58 (screenshot "Thuis sinds 13:54 · beweging 4 min
geleden"): "Waarschijnlijk heeft de hond een rondje door de kamer gelopen,
ik weet zeker dat er niemand thuis is, hoe kunnen we dit borgen?" en "zo
waterdicht mogelijk". Gemeten: alleen de woonkamerradar, 22 seconden.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from custom_components.energy_management_system import thuiskomst as T
from custom_components.energy_management_system.const import (
    CONF_DISHWASHER_POWER_SENSOR,
    CONF_PRESENCE_LIGHT_ENTITIES,
    CONF_PRESENCE_MOTION_SENSORS,
    CONF_WATER_ACTIVE_USAGE_SENSOR,
)

NU = datetime(2026, 10, 20, 11, 53, 32, tzinfo=timezone.utc)


# --- de poort zelf -----------------------------------------------------------

def test_de_hond_22_seconden_voor_de_radar_is_geen_thuiskomst():
    p = T.ThuiskomstPoort()
    p.aan("binary_sensor.ultimatesensor_occupancy", "radar", NU)
    p.aan("binary_sensor.ultimatesensor_zone_1_occupancy", "radar", NU + timedelta(seconds=6))
    p.uit("binary_sensor.ultimatesensor_occupancy", NU + timedelta(seconds=22))
    p.uit("binary_sensor.ultimatesensor_zone_1_occupancy", NU + timedelta(seconds=23))
    assert p.bevestigd(NU + timedelta(seconds=30)) is None


def test_een_deur_bevestigt_ook_achteraf_tien_minuten():
    p = T.ThuiskomstPoort()
    p.deur(NU)
    assert p.bevestigd(NU + timedelta(minutes=9)) == "deur open"
    assert p.bevestigd(NU + timedelta(minutes=11)) is None


def test_een_hond_die_lang_voor_de_radar_ligt_telt_niet():
    p = T.ThuiskomstPoort()
    p.aan("binary_sensor.radar", "radar", NU)
    assert p.bevestigd(NU + timedelta(minutes=14)) is None


def test_aanhoudend_op_twee_plekken_is_wel_thuiskomst():
    p = T.ThuiskomstPoort()
    p.aan("binary_sensor.radar", "radar", NU)
    p.uit("binary_sensor.radar", NU + timedelta(minutes=3))
    p.aan("binary_sensor.gang", "gang", NU + timedelta(minutes=4))
    assert p.bevestigd(NU + timedelta(minutes=5)) is None          # 4 min samen
    assert "aanhoudende beweging" in p.bevestigd(NU + timedelta(minutes=6))


def test_deursensor_herkennen():
    assert T.is_deur("binary_sensor.deur_sensor_voordeur_contact", "door")
    assert T.is_deur("binary_sensor.iets_contact", "opening")
    assert T.is_deur("binary_sensor.deur_sensor_achterdeur_contact", None)
    assert not T.is_deur("binary_sensor.ultimatesensor_occupancy", "occupancy")
    assert not T.is_deur("binary_sensor.raam_keuken_contact", "window")


# --- in de coordinator -----------------------------------------------------

class _Staat:
    def __init__(self, entity_id, state, attributes=None, parent_id=None):
        self.entity_id = entity_id
        self.state = state
        self.attributes = attributes or {}
        self.context = SimpleNamespace(parent_id=parent_id)


class _Event:
    def __init__(self, entity_id, oud, nieuw, attributes=None):
        self.data = {"entity_id": entity_id, "old_state": _Staat(entity_id, oud),
                     "new_state": _Staat(entity_id, nieuw, attributes)}


RADAR = "binary_sensor.ultimatesensor_occupancy"
DEUR = "binary_sensor.deur_sensor_voordeur_contact"


def _leeg_huis(make_coordinator, hass, extra=None):
    c = make_coordinator({CONF_PRESENCE_MOTION_SENSORS: [RADAR, DEUR], **(extra or {})})
    hass.states.set(DEUR, "off", {"device_class": "door"})
    hass.states.set(RADAR, "off", {"device_class": "occupancy"})
    c.presence_state = "weg"
    c.last_motion_at = None
    return c


def test_de_hond_zet_het_lege_huis_niet_op_thuis(make_coordinator, hass):
    c = _leeg_huis(make_coordinator, hass)
    c._handle_motion_event(_Event(RADAR, "off", "on", {"device_class": "occupancy"}))
    assert c.presence_state == "weg"
    assert c.last_motion_at is None and RADAR not in c.presence_last_seen
    genegeerd = c.get_presence_overview()["thuiskomst"]["genegeerd"]
    assert genegeerd and "geen deur" in genegeerd[0]["reden"]


def test_wie_door_de_deur_komt_is_thuis(make_coordinator, hass):
    c = _leeg_huis(make_coordinator, hass)
    c._handle_motion_event(_Event(DEUR, "off", "on", {"device_class": "door"}))
    assert c.presence_state == "thuis"
    c._handle_motion_event(_Event(RADAR, "off", "on", {"device_class": "occupancy"}))
    assert c.presence_state == "thuis" and c.last_motion_at is not None


def test_eerst_de_deur_dan_beweging_binnen_tien_minuten(make_coordinator, hass):
    c = _leeg_huis(make_coordinator, hass)
    c._thuiskomst.deur(datetime.now(timezone.utc) - timedelta(minutes=3))
    c._handle_motion_event(_Event(RADAR, "off", "on", {"device_class": "occupancy"}))
    assert c.presence_state == "thuis"
    assert c._thuiskomst.laatste_reden == "deur open"


def test_wie_al_thuis_is_merkt_niets(make_coordinator, hass):
    c = _leeg_huis(make_coordinator, hass)
    c.presence_state = "thuis"
    c._handle_motion_event(_Event(RADAR, "off", "on", {"device_class": "occupancy"}))
    assert c.last_motion_at is not None and RADAR in c.presence_last_seen


def test_water_van_de_vaatwasser_is_geen_thuiskomst(make_coordinator, hass):
    c = _leeg_huis(make_coordinator, hass, {CONF_WATER_ACTIVE_USAGE_SENSOR: "sensor.water",
                                            CONF_DISHWASHER_POWER_SENSOR: "sensor.vaatwasser"})
    hass.states.set("sensor.water", "6", {"unit_of_measurement": "L/min"})
    hass.states.set("sensor.vaatwasser", "1900", {"unit_of_measurement": "W"})
    assert c._stromend_water() and c._water_van_apparaat()
    hass.states.set("sensor.vaatwasser", "0.4", {"unit_of_measurement": "W"})
    assert not c._water_van_apparaat()


def test_een_lamp_van_een_automatisering_is_geen_thuiskomst(make_coordinator, hass):
    c = _leeg_huis(make_coordinator, hass, {CONF_PRESENCE_LIGHT_ENTITIES: ["light.plafond"]})
    hass.states._values["light.plafond"] = _Staat("light.plafond", "on", parent_id="automation-ctx")
    assert c._brandend_licht() is not None and not c._licht_met_de_hand()
    hass.states._values["light.plafond"] = _Staat("light.plafond", "on", parent_id=None)
    assert c._licht_met_de_hand()
