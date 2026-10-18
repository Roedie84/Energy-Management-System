"""v5.99.12: smart_discharging dekt alleen het huis en slaat geen zon op.

Gemeld: "de Zendure zelf staat op slim ontladen, dat is alleen het huis
ondersteunen en niet het kleine beetje PV opslaan". De namen zeiden
"ontladen"; nu zeggen ze wat de stand doet.
"""
from custom_components.energy_management_system.const import MODUS_KORTE_NAAM
from custom_components.energy_management_system.planvolging import _stand_tekst


def test_korte_naam_zegt_zon_niet_opslaan():
    assert "zon niet opslaan" in MODUS_KORTE_NAAM["smart_discharging"]


def test_planvolging_zegt_zon_niet_opslaan():
    assert "zon niet opslaan" in _stand_tekst("smart_discharging")
    assert _stand_tekst("smart") == "slim"
