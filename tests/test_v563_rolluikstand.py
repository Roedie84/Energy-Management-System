"""v5.63: de klimaatprojectie leest de echte rolluikstand (current_position)."""

from custom_components.energy_management_system.coordinator import (
    rolluiklabel,
    rolluikstand_procent,
)

from test_climate_tab import _base_config


def test_stand_uit_positie():
    assert rolluikstand_procent("open", {"current_position": 20}) == 20
    assert rolluikstand_procent("open", {"current_position": 100}) == 100
    assert rolluikstand_procent("closed", {"current_position": 0}) == 0


def test_zonder_positie_zoals_voorheen():
    assert rolluikstand_procent("open", {}) == 100
    assert rolluikstand_procent("closed", {}) == 0
    # voorheen telde alleen "open" als open
    assert rolluikstand_procent("opening", {}) == 0
    assert rolluikstand_procent("closing", None) == 0


def test_onbeschikbaar_telt_niet():
    assert rolluikstand_procent("unavailable", {"current_position": 50}) is None
    assert rolluikstand_procent("unknown", {}) is None


def test_ongeldige_positie_valt_terug_op_toestand():
    assert rolluikstand_procent("open", {"current_position": "x"}) == 100
    assert rolluikstand_procent("closed", {"current_position": 150}) == 0


def test_labels():
    assert rolluiklabel(100) == "beide_open"
    assert rolluiklabel(90) == "beide_open"
    assert rolluiklabel(89.9) == "gedeeltelijk"
    assert rolluiklabel(50) == "gedeeltelijk"
    assert rolluiklabel(10) == "beide_dicht"
    assert rolluiklabel(0) == "beide_dicht"


def _coord(make_coordinator, hass, p1, p2, s1="open", s2="open"):
    hass.states.set("cover.rolluik_achter", s1, {"current_position": p1} if p1 is not None else {})
    hass.states.set("cover.rolluik_voor", s2, {"current_position": p2} if p2 is not None else {})
    return make_coordinator(_base_config())


def test_gekalibreerd_bijna_dicht_is_niet_open(make_coordinator, hass):
    c = _coord(make_coordinator, hass, 20, 20)
    assert c._get_shutter_state_label() == "gedeeltelijk"


def test_gekalibreerd_helemaal_open(make_coordinator, hass):
    c = _coord(make_coordinator, hass, 100, 95)
    assert c._get_shutter_state_label() == "beide_open"


def test_gekalibreerd_bijna_dicht_telt_als_dicht(make_coordinator, hass):
    c = _coord(make_coordinator, hass, 5, 0, "open", "closed")
    assert c._get_shutter_state_label() == "beide_dicht"


def test_een_onbeschikbaar_telt_de_ander(make_coordinator, hass):
    c = _coord(make_coordinator, hass, 100, None, "open", "unavailable")
    assert c._get_shutter_state_label() == "beide_open"


def test_beide_onbeschikbaar_geeft_none(make_coordinator, hass):
    c = _coord(make_coordinator, hass, None, None, "unavailable", "unavailable")
    assert c._get_shutter_state_label() is None
