"""v5.99.7: het moment van "klaar" blijft over een herstart.

Gemeld 16-10 11:31: tablet "Vaatwasser klaar · leeghalen · sinds 11:15",
terwijl hij op 15-10 om 15:48 klaar was. last_changed verspringt bij elke
herstart; het dashboard rekende daarmee.
"""
from datetime import timedelta

from test_appliance_cycle_state import DAY0, _base_config


def _run(c, hass, w, when):
    hass.states.set("sensor.vaatwasser_vermogen", str(w))
    c._update_appliance_state_machine(
        when, power_entity="sensor.vaatwasser_vermogen", state_attr="_dishwasher_state",
        cycle_started_attr="_dishwasher_cycle_started_at",
        below_threshold_since_attr="_dishwasher_below_threshold_since",
        duration_history_attr="dishwasher_cycle_duration_history",
    )


def test_klaar_sinds_wordt_vastgelegd_en_getoond(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import DishwasherCycleStateSensor

    c = make_coordinator(_base_config())
    _run(c, hass, 80, DAY0)
    _run(c, hass, 0, DAY0 + timedelta(minutes=50))
    _run(c, hass, 0, DAY0 + timedelta(minutes=56))
    assert c._dishwasher_state == "klaar"
    eind = DAY0 + timedelta(minutes=56)
    assert c.cyclus_klaar_sinds["_dishwasher_state"] == eind.isoformat()
    s = DishwasherCycleStateSensor(c, "e")
    assert s.extra_state_attributes["klaar_sinds"] == eind.isoformat()


def test_klaar_sinds_leeg_als_niet_klaar(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import DishwasherCycleStateSensor

    c = make_coordinator(_base_config())
    c.cyclus_klaar_sinds["_dishwasher_state"] = DAY0.isoformat()
    _run(c, hass, 80, DAY0 + timedelta(hours=1))
    assert DishwasherCycleStateSensor(c, "e").extra_state_attributes["klaar_sinds"] is None
