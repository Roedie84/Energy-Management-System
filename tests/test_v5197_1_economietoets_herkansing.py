"""v5.197.1 (H-EMS-20): de economietoets stempelt niet zonder parameters.

Dagcontrole 09-11: de nachten naar 4-7 november bleven 'bijladen loonde' en
telden als tekortdag. v5.193.0 stempelde de toets ook als rendement of
slijtage (nog) ontbrak; dan kwam er nooit een tweede poging. Een replay op het
echte dagverloop met de echte parameters gaf 5, 6 en 7 nov economisch.
"""
from custom_components.energy_management_system.const import ECONOMIETOETS_VERSIE, TEKORT_REDEN_LOONDE
from tests.test_v5193_laadnachten_economisch import _c, _records, _verloop


def test_zonder_slijtage_niet_stempelen(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _records(c, _verloop({20, 21, 22}, prijs_vrij=39.7))
    c.get_wear_cost_overview = lambda: {}
    assert c._toets_laadnachten_op_economie() == 0
    assert "economietoets" not in c.reserve_daily_records[0]
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 4.2}
    assert c._toets_laadnachten_op_economie() == 1
    assert c.reserve_daily_records[0]["tekort_soort"] == "economisch"


def test_oude_stempel_wordt_opnieuw_getoetst(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _records(c, _verloop({20, 21, 22}, prijs_vrij=39.7))
    c.reserve_daily_records[0]["economietoets"] = "v5.193"
    assert c._toets_laadnachten_op_economie() == 1
    assert c.reserve_daily_records[0]["economietoets"] == ECONOMIETOETS_VERSIE


def test_planning_krijgt_de_echte_reden(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _records(c, _verloop({20, 21, 22}, prijs_vrij=15.0))
    c._herleid_laadnacht = lambda dag: ("planning", "0,6 kWh verkocht onder de reserve")
    c._toets_laadnachten_op_economie()
    r = c.reserve_daily_records[0]
    assert r["tekort_soort"] == "planning" and r["tekort_reden"] != TEKORT_REDEN_LOONDE
