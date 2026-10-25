"""v5.127.0 - telefoons tellen mee als extra "thuis", nooit als "weg".

Gevraagd 25-10 (screenshot "Thuis sinds 08:52"): "Ik ben al behoorlijk
veel weggeweest" en daarna "Mijn telefoon (Ruud) mee laten tellen",
gekozen: alleen als extra 'thuis'.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from custom_components.energy_management_system.const import (
    CONF_PRESENCE_MOTION_SENSORS,
    CONF_PRESENCE_PERSON_ENTITIES,
)

RADAR = "binary_sensor.ultimatesensor_occupancy"
RUUD = "person.ruud_maarse"
MIDDAG = datetime(2026, 10, 25, 13, 0, tzinfo=timezone.utc)


class _Event:
    def __init__(self, entity_id, oud, nieuw):
        mk = lambda s: SimpleNamespace(entity_id=entity_id, state=s,
                                       attributes={"device_class": "occupancy"},
                                       context=SimpleNamespace(parent_id=None))
        self.data = {"entity_id": entity_id, "old_state": mk(oud), "new_state": mk(nieuw)}


def _huis(make_coordinator, hass, telefoon_staat):
    c = make_coordinator({CONF_PRESENCE_MOTION_SENSORS: [RADAR],
                          CONF_PRESENCE_PERSON_ENTITIES: [RUUD]})
    hass.states.set(RADAR, "off", {"device_class": "occupancy"})
    hass.states.set(RUUD, telefoon_staat, {"friendly_name": "Ruud Maarse"})
    return c


def test_telefoon_thuis_houdt_het_huis_op_thuis(make_coordinator, hass):
    c = _huis(make_coordinator, hass, "home")
    c.presence_state = "thuis"
    c.last_motion_at = MIDDAG - timedelta(minutes=90)
    c._update_presence(MIDDAG)
    assert c.presence_state == "thuis"
    assert c._aanleiding_aanwezigheid(MIDDAG, "weg").startswith("telefoon thuis")


def test_telefoon_in_een_andere_zone_zegt_niets(make_coordinator, hass):
    c = _huis(make_coordinator, hass, "Thuis Yvonne")
    c.presence_state = "thuis"
    c.last_motion_at = MIDDAG - timedelta(minutes=90)
    c._update_presence(MIDDAG)
    assert c.presence_state == "weg"


def test_telefoon_weg_maakt_een_bezet_huis_niet_leeg(make_coordinator, hass):
    c = _huis(make_coordinator, hass, "not_home")
    c.presence_state = "thuis"
    c.last_motion_at = MIDDAG - timedelta(minutes=2)
    c._update_presence(MIDDAG)
    assert c.presence_state == "thuis"


def test_telefoon_op_het_nachtkastje_maakt_van_de_nacht_geen_thuis(make_coordinator, hass):
    c = _huis(make_coordinator, hass, "home")
    nacht = datetime(2026, 10, 25, 23, 30, tzinfo=timezone.utc).astimezone()
    nacht = nacht.replace(hour=23, minute=30)
    c.presence_state = "slaapt"
    c.last_motion_at = nacht - timedelta(minutes=60)
    c._update_presence(nacht)
    assert c.presence_state == "slaapt"


def test_telefoon_thuis_bevestigt_de_thuiskomst(make_coordinator, hass):
    c = _huis(make_coordinator, hass, "home")
    c.presence_state = "weg"
    c.last_motion_at = None
    c._handle_motion_event(_Event(RADAR, "off", "on"))
    assert c.presence_state == "thuis"
    assert c._thuiskomst.laatste_reden.startswith("telefoon thuis")


def test_zonder_telefoon_blijft_de_hond_buiten(make_coordinator, hass):
    c = _huis(make_coordinator, hass, "not_home")
    c.presence_state = "weg"
    c.last_motion_at = None
    c._handle_motion_event(_Event(RADAR, "off", "on"))
    assert c.presence_state == "weg"


def test_overzicht_toont_de_telefoons(make_coordinator, hass):
    c = _huis(make_coordinator, hass, "Thuis Yvonne")
    tel = c.get_presence_overview()["telefoons"]
    assert tel and tel[0]["staat"] == "Thuis Yvonne" and tel[0]["thuis"] is False
