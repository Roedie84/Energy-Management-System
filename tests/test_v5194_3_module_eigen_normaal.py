"""v5.194.3: temperatuur tegen de eigen normaal van de module.

08-11 13:45: cockpit meldde module 1 (01029, +4,5 °C) en 3 (02093, -3 °C) als
uit de pas. Ruud: logisch, module 1 zit direct onder de omvormer. Een vaste
plek-afwijking is geen drift; alleen een verschuiving tegenover de eigen
referentie (dagmediaan, niet het moment) van minstens de drempel telt.
"""
from custom_components.energy_management_system.const import BATTERY_MODULE_TEMPERATURE_MATERIEEL_C as GRENS

V = "temperatuur_afwijking_c"


def _staat(ref, reeks):
    return {"cusum": {V: {"drift": True, "referentie": ref}}, "geschiedenis": {V: reeks}}


def test_vaste_plek_bij_de_omvormer_telt_niet(make_coordinator):
    c = make_coordinator({})
    live = {"module": 1, V: 4.5}   # moment onder belasting
    assert c._module_drift_velden("1", _staat(3.0, [3.2, 3.5, 3.8]), live) == []


def test_echt_warmer_dan_eigen_normaal_telt(make_coordinator):
    c = make_coordinator({})
    live = {"module": 1, V: 5.0}
    assert c._module_drift_velden("1", _staat(1.0, [2.0, 3.5, 4.5]), live) == [V]


def test_zonder_geschiedenis_het_moment(make_coordinator):
    c = make_coordinator({})
    staat = {"cusum": {V: {"drift": True, "referentie": None}}, "geschiedenis": {}}
    assert c._module_drift_velden("3", staat, {"module": 3, V: -1.0}) == []
    assert c._module_drift_velden("3", staat, {"module": 3, V: -(GRENS + 1)}) == [V]
