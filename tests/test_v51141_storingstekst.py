"""v5.114.1: waar is de storing? Korte tekst achter de status.

Gevraagd 21-10 15:35 (screenshot met "Storing" in de kop): "waar is de
storing? Graag korte tekst achter de storingsmelding". De reden stond alleen
in een attribuut, en als instellingssleutel ("price_sensor_entity").
"""
from pathlib import Path
from types import SimpleNamespace

from custom_components.energy_management_system.coordinator import EnergyManagementSystemCoordinator as C

JS = (Path(__file__).resolve().parent.parent / "custom_components" / "energy_management_system"
      / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def test_koppelingnaam_is_de_entiteitnaam():
    c = object.__new__(C)
    staten = {"sensor.prijs": SimpleNamespace(state="unavailable",
                                              attributes={"friendly_name": "Zonneplan kwartiertarief"})}
    c.hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: staten.get(e)))
    assert c._koppelingnaam({"instelling": "price_sensor_entity", "entiteit": "sensor.prijs"}) == "Zonneplan kwartiertarief"
    assert c._koppelingnaam({"instelling": "x", "entiteit": "sensor.weg"}) == "sensor.weg"
    assert c._koppelingnaam({"instelling": "x"}) == "x"


def test_prijsbron_weg_met_buffer_is_let_op():
    bron = (Path(__file__).resolve().parent.parent / "custom_components" / "energy_management_system"
            / "coordinator.py").read_text(encoding="utf-8")
    deel = bron[bron.index("    def _ems_status(self)"):bron.index('return "STORING", f"noodzakelijke koppeling weg')]
    assert "if self._prijs_uit_cache and all(" in deel and "laatst bekende prijzen in gebruik" in deel


def test_cockpit_zet_de_reden_achter_de_status():
    assert '<span class="chip-reden"' in JS and 'attr(cockpit, "reden")' in JS
    assert ".chip-reden {" in JS
