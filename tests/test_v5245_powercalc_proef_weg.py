"""v5.245.0 - de Powercalc-proef is eruit (Ruud 19-11: "als iets niet wordt gebruikt kan het eruit").

De proef uit v3.97.0 mat of het aftrekken van Powercalc-schattingen het
residu voor de apparaatherkenning rustiger maakt. Er is nooit een besluit op
gevolgd en niets gebruikte de uitkomst. De herkenning van losse
Powercalc-sensoren als sluipverbruiker (v5.135.1) blijft.
"""
from pathlib import Path

import custom_components.energy_management_system as pkg

MAP = Path(pkg.__file__).parent


def test_de_proef_is_weg():
    for bestand in ("coordinator.py", "const.py", "diagnostics.py", "sensor.py"):
        bron = (MAP / bestand).read_text(encoding="utf-8")
        for weg in ("powercalc_paren", "get_powercalc_proef", "_update_powercalc_proef", "POWERCALC_MIN_METINGEN",
                    "powercalc-proef", "Powercalc als NILM-hulp"):
            assert weg not in bron, (bestand, weg)


def test_losse_powercalc_sensoren_tellen_nog_als_sluipverbruiker():
    bron = (MAP / "coordinator.py").read_text(encoding="utf-8")
    assert "def _is_losse_powercalc(" in bron and "self._is_losse_powercalc(entiteit" in bron


def test_een_oude_opgeslagen_reeks_breekt_het_laden_niet(make_coordinator, hass):
    """Wie van een oudere versie komt, heeft `powercalc_paren` nog in de opslag."""
    c = make_coordinator({})
    assert not hasattr(c, "powercalc_paren")
    from custom_components.energy_management_system import const
    assert "powercalc_paren" not in (MAP / "const.py").read_text(encoding="utf-8")
    assert not [n for n in dir(const) if n.startswith("POWERCALC_")]
