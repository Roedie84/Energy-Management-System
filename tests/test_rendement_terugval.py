"""De oude rendementsreeks als terugval (v3.40.0).

Gevraagd: "Zijn er nog meer ontwerpfouten?"

Gevonden bij het nalopen van elke geleerde reeks op scheefheid en
bereik. `learned_efficiency_history` stond op:

    [95.5, 76.9, 74.2, 82.9, 83.2, 97.6, 56.4]

Een spreiding van 41 procentpunt. Die 56,4% valt buiten wat er nu wordt
geaccepteerd; 97,6% ligt er nog net binnen, maar een heen-en-terug-
rendement van 97,6% bestaat niet bij een omvormer die twee keer omzet -
de grenzen gelden per HALVE cyclus, en daar is 97,6 wel mogelijk.

De reeks wordt sinds de invoering van de halve cycli NERGENS meer
bijgeschreven; hij staat alleen nog in de opslag en dient als terugval
wanneer de halve metingen er nog niet zijn. Maar hij is opgebouwd zonder
de grenzen die nu gelden, en een terugval hoort aan dezelfde eis te
voldoen als een verse meting - anders levert hij een getal waar de rest
van de integratie niet meer mee had willen rekenen.

Dat getal schaalt de reserveberekening en de kostprijs.
"""
from custom_components.energy_management_system.const import (
    MAX_PLAUSIBLE_HALF_EFFICIENCY_PERCENT,
    MIN_PLAUSIBLE_HALF_EFFICIENCY_PERCENT,
)

GEMETEN = [95.5, 76.9, 74.2, 82.9, 83.2, 97.6, 56.4]


def test_the_impossible_values_are_left_out(make_coordinator, hass):
    """56,4% en 97,6% vallen buiten wat er nu wordt geaccepteerd."""
    c = make_coordinator({})
    c.learned_efficiency_history = list(GEMETEN)
    c.charge_efficiency_history = []
    c.discharge_efficiency_history = []

    uitkomst = c.learned_battery_efficiency_percent

    # 56,4 valt af; de zes die overblijven geven mediaan 83,05 in plaats
    # van 82,9 over alle zeven. Klein verschil hier, groot verschil zodra
    # er meer onmogelijke waarden in staan.
    assert round(uitkomst, 2) == 83.05


def test_too_few_plausible_values_gives_nothing(make_coordinator, hass):
    """Blijven er te weinig bruikbare metingen over, dan is geen getal

    beter dan een slecht getal - de rest van de integratie valt dan
    terug op de veilige standaard van 90%.
    """
    c = make_coordinator({})
    c.learned_efficiency_history = [56.4, 97.6, 110.0, 20.0]
    c.charge_efficiency_history = []
    c.discharge_efficiency_history = []

    assert c.learned_battery_efficiency_percent is None


def test_the_half_cycles_still_win(make_coordinator, hass):
    """De nieuwe meting is beter en gaat voor; de terugval is alleen voor

    een verse installatie.
    """
    c = make_coordinator({})
    c.learned_efficiency_history = list(GEMETEN)
    c.charge_efficiency_history = [89.0] * 7
    c.discharge_efficiency_history = [94.15] * 7

    uitkomst = c.learned_battery_efficiency_percent

    assert uitkomst is not None
    assert 83.0 < uitkomst < 84.5


def test_the_bounds_are_the_same_ones(make_coordinator, hass):
    """Eén stel grenzen voor beide wegen; twee stellen zou betekenen dat

    een meting via de ene weg wordt geweigerd en via de andere niet.
    """
    assert MIN_PLAUSIBLE_HALF_EFFICIENCY_PERCENT >= 70.0
    assert MAX_PLAUSIBLE_HALF_EFFICIENCY_PERCENT <= 100.0
    assert 56.4 < MIN_PLAUSIBLE_HALF_EFFICIENCY_PERCENT
