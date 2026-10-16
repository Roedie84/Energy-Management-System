"""v5.99.5: een even onbeschikbare airco is geen ontbrekende hvac_action.

Gemeld 16-10 09:47: Repairs "1 ingang(en) leveren niet wat ze horen te leveren
... Airco: hvac_action" - de Daikin was 2 minuten weggevallen.
"""
from custom_components.energy_management_system.const import CONF_AIRCO_CLIMATE_ENTITY


def _namen(c):
    return [g["naam"] for g in c.get_input_health()]


def test_onbeschikbare_airco_geen_gebrek(make_coordinator, hass):
    c = make_coordinator({CONF_AIRCO_CLIMATE_ENTITY: "climate.woonkamer"})
    hass.states.set("climate.woonkamer", "unavailable", {})
    assert "Airco: hvac_action" not in _namen(c)


def test_beschikbaar_zonder_hvac_action_wel_gebrek(make_coordinator, hass):
    c = make_coordinator({CONF_AIRCO_CLIMATE_ENTITY: "climate.woonkamer"})
    hass.states.set("climate.woonkamer", "heat", {})
    assert "Airco: hvac_action" in _namen(c)


def test_met_hvac_action_geen_gebrek(make_coordinator, hass):
    c = make_coordinator({CONF_AIRCO_CLIMATE_ENTITY: "climate.woonkamer"})
    hass.states.set("climate.woonkamer", "off", {"hvac_action": "off"})
    assert "Airco: hvac_action" not in _namen(c)
