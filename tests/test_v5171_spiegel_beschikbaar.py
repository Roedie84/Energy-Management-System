"""L-EMS-056 - de spiegel Beschikbare energie vergelijkt niet meer ruw met
gecorrigeerd. Gemeten 02-11 23:30: `fout 1` door 0,576 tegen 0,025 kWh."""
from pathlib import Path
from tests._coordinator_bron import coordinator_bron


def _coord(make_coordinator, gemeten, sprong):
    c = make_coordinator({"available_energy_sensor_entity": "sensor.beschikbaar"})
    c._read_sensor_float = lambda *a, **k: gemeten
    c.module_leeg_correctie_kwh = lambda: sprong
    return c


def test_modulesprong_gaat_van_de_meting_af(make_coordinator, hass):
    c = _coord(make_coordinator, 0.576, 0.551)
    assert round(c._beschikbaar_voor_spiegel("sensor.beschikbaar"), 3) == 0.025


def test_negatieve_meting_is_niets_bruikbaar(make_coordinator, hass):
    assert _coord(make_coordinator, -0.576, 0.0)._beschikbaar_voor_spiegel("s") == 0.0


def test_geen_module_laag_laat_de_meting_staan(make_coordinator, hass):
    assert _coord(make_coordinator, 2.3, 0.0)._beschikbaar_voor_spiegel("s") == 2.3


def test_geen_meting_blijft_geen_meting(make_coordinator, hass):
    assert _coord(make_coordinator, None, 0.5)._beschikbaar_voor_spiegel("s") is None


def test_de_tak_gebruikt_de_gecorrigeerde_lezing():
    bron = coordinator_bron()
    assert "self.last_available_kwh = self._read_sensor_float(" not in bron
    assert "self.last_available_kwh = self._beschikbaar_voor_spiegel(" in bron
