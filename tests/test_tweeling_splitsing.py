"""De tweelingfout gesplitst in nacht en dag (v3.45.0).

Gemeten op 21 augustus, de dag na de reparatie van v3.35.1:

    47 vergelijkingen zonder zon   gemiddeld +0,90 kWh
    13 vergelijkingen met zon      gemiddeld +2,16 kWh

De simulatie zelf is nauwkeurig geworden; wat er overdag bij komt is de
zonverwachting, die op wisselvallige dagen 28 tot 50% te hoog ligt. Twee
dagen later stond het totaal op 1,56 kWh en zag het eruit als een
verslechterende tweeling - terwijl het de voorspelling was die het
slechter deed.

Zonder deze splitsing is dat niet te zien, en dan wordt er gerepareerd
aan het verkeerde.
"""
from custom_components.energy_management_system.const import (
    DIGITAL_TWIN_ZON_DREMPEL_KWH,
)


def _vul(c, zonder, met):
    c.digital_twin_accuracy_history = (
        [{"fout_kwh": f, "met_zon": False} for f in zonder]
        + [{"fout_kwh": f, "met_zon": True} for f in met]
    )
    return c


def test_the_split_names_the_forecast_as_the_cause(make_coordinator, hass):
    """De gemeten verhouding van 21 augustus."""
    c = _vul(make_coordinator({}), [0.9] * 47, [2.16] * 13)

    uit = c.get_digital_twin_error_split()

    assert uit["zonder_zon"]["fout_kwh"] == 0.9
    assert uit["met_zon"]["fout_kwh"] == 2.16
    assert "zonverwachting" in uit["duiding"]
    assert "niet van het model" in uit["duiding"]


def test_an_even_split_points_at_the_model(make_coordinator, hass):
    """Liggen nacht en dag dicht bij elkaar, dan zit de fout in de

    simulatie zelf - en dan helpt sleutelen aan de voorspelling niet.
    """
    c = _vul(make_coordinator({}), [0.8] * 20, [0.9] * 20)

    uit = c.get_digital_twin_error_split()

    assert "in de simulatie zelf" in uit["duiding"]


def test_without_both_kinds_it_says_so(make_coordinator, hass):
    c = _vul(make_coordinator({}), [0.9] * 10, [])

    uit = c.get_digital_twin_error_split()

    assert uit["met_zon"]["fout_kwh"] is None
    assert "nodig" in uit["duiding"]


def test_old_comparisons_without_a_label_are_counted(make_coordinator, hass):
    """De reeks die er nu in staat draagt het kenmerk nog niet; dat mag

    niet stilzwijgend als "nacht" tellen.
    """
    c = make_coordinator({})
    c.digital_twin_accuracy_history = [
        {"fout_kwh": 1.2},
        {"fout_kwh": 0.8, "met_zon": False},
        {"fout_kwh": 2.4, "met_zon": True},
    ]

    uit = c.get_digital_twin_error_split()

    assert uit["nog_zonder_kenmerk"] == 1
    assert uit["zonder_zon"]["aantal"] == 1
    assert uit["met_zon"]["aantal"] == 1


def test_an_empty_history_does_not_crash(make_coordinator, hass):
    c = make_coordinator({})
    c.digital_twin_accuracy_history = []

    uit = c.get_digital_twin_error_split()

    assert uit["vergelijkingen"] == 0


def test_the_threshold_is_a_real_amount_of_sun():
    """Een halve kilowattuur over zes uur is het punt waarop de zon

    meetelbaar wordt; daaronder meet je de simulatie zelf.
    """
    assert 0.1 <= DIGITAL_TWIN_ZON_DREMPEL_KWH <= 2.0
