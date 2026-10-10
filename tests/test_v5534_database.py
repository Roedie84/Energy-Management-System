"""v5.53.4: de cockpit (15 KB per ronde) bewaarde zijn attributen nog in de
database; nu geen, zoals de andere zware sensoren sinds v5.34. En "Zendure
lokaal meelezen" bewaart alleen de kerngetallen.
"""
from custom_components.energy_management_system import sensor as s
from custom_components.energy_management_system.const import GEEN_ATTRIBUTEN_IN_RECORDER


def test_cockpit_bewaart_geen_attributen():
    assert s.CockpitSensor._unrecorded_attributes == GEEN_ATTRIBUTEN_IN_RECORDER


def test_zendure_lokaal_alleen_kerngetallen():
    # v5.76 - BEWUST GEWIJZIGD: alle attributen buiten de recorder; ook de
    # kerngetallen gaven elke 30 s een nieuwe attribuutrij.
    weg = s.ZendureLokaalSensor._unrecorded_attributes
    assert weg == frozenset({"*"})
