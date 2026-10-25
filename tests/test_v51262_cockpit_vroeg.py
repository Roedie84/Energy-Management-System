"""v5.126.2: het cockpitscript wordt als eerste geregistreerd.

Gemeld 25-10: "Energy Cockpit geeft nu vaak configuratie fout". Het script
werd pas aan het eind van de setup geserveerd; een dashboard dat eerder
opende kreeg een 404 en bleef op "Configuratiefout".
"""

from pathlib import Path

import custom_components.energy_management_system as pkg

BRON = (Path(pkg.__file__).parent / "__init__.py").read_text(encoding="utf-8")


def test_cockpit_voor_alles_in_de_setup():
    setup = BRON[BRON.index("async def async_setup_entry"):]
    cockpit = setup.index("async_registreer_cockpit(hass")
    assert cockpit < setup.index("EnergyManagementSystemCoordinator(hass, config)")
    assert cockpit < setup.index("async_load_persisted_state()")
    assert cockpit < setup.index("async_forward_entry_setups(")


def test_cockpit_maar_een_keer_geregistreerd():
    assert BRON.count("await async_registreer_cockpit(") == 1
