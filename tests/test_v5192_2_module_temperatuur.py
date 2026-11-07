"""v5.192.2: een vaste temperatuurafwijking van ~1 °C is geen 'uit de pas'.

07-11: cockpit meldde accumodule 1 (01029) en 3 (02093) als "loopt aanhoudend
uit de pas (temperatuur_afwijking_c)". Module 1 zit structureel ~1 °C warmer
(bij de omvormer); celspanning en SoC liepen gelijk. Temperatuur telt pas vanaf
BATTERY_MODULE_TEMPERATURE_MATERIEEL_C.
"""
from custom_components.energy_management_system.const import BATTERY_MODULE_TEMPERATURE_MATERIEEL_C as GRENS


def _staat(veld):
    return {"cusum": {veld: {"drift": True}}, "geschiedenis": {}}


def test_een_graad_warmer_telt_niet(make_coordinator):
    c = make_coordinator({})
    live = {"module": 1, "temperatuur_afwijking_c": 1.5, "cel_delta_v": 0.01}
    assert c._module_drift_velden("1", _staat("temperatuur_afwijking_c"), live) == []


def test_flink_warmer_telt_wel(make_coordinator):
    c = make_coordinator({})
    live = {"module": 1, "temperatuur_afwijking_c": GRENS + 1, "cel_delta_v": 0.01}
    assert c._module_drift_velden("1", _staat("temperatuur_afwijking_c"), live) == ["temperatuur_afwijking_c"]


def test_kouder_telt_ook(make_coordinator):
    c = make_coordinator({})
    live = {"module": 3, "temperatuur_afwijking_c": -(GRENS + 0.5)}
    assert c._module_drift_velden("3", _staat("temperatuur_afwijking_c"), live) == ["temperatuur_afwijking_c"]


def test_andere_velden_ongemoeid(make_coordinator):
    c = make_coordinator({})
    live = {"module": 1, "temperatuur_afwijking_c": 0.5}
    staat = {"cusum": {"soc_afwijking_percent": {"drift": True}}, "geschiedenis": {}}
    assert c._module_drift_velden("1", staat, live) == ["soc_afwijking_percent"]
