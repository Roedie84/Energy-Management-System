"""v5.202.0: het berekende airco-vermogen zichtbaar.

Ruud 09-11: "Waar zie ik nu het berekende airco vermogen?" - akkoord op een
sensor, de airco-tegel in de cockpit en de diagnose.
"""
from pathlib import Path

from custom_components.energy_management_system.const import CONF_AIRCO_CLIMATE_ENTITY
from custom_components.energy_management_system.sensor import AircoVermogenSensor

PAKKET = Path(__file__).parent.parent / "custom_components" / "energy_management_system"


def test_sensor_uit_de_frequentie(make_coordinator, hass):
    c = make_coordinator({CONF_AIRCO_CLIMATE_ENTITY: "climate.woonkamer"})
    hass.states.set("sensor.woonkamer_compressor_frequency", "30.0", {"unit_of_measurement": "Hz"})
    c._airco_bronnen = {"frequentie": "sensor.woonkamer_compressor_frequency"}
    info = c.get_airco_vermogen()
    assert info["bron"] == "compressorfrequentie"
    assert info["vermogen_w"] == round(31.4 * 30 - 238)
    assert info["omrekening_geleerd"] is False
    s = AircoVermogenSensor(c, "e")
    assert s.native_value == info["vermogen_w"]
    assert "vermogen_w" not in s.extra_state_attributes
    assert s._attr_unique_id == "e_airco_vermogen"


def test_zonder_bronnen_geen_waarde(make_coordinator, hass):
    c = make_coordinator({})
    assert c.get_airco_vermogen()["vermogen_w"] is None


def test_cockpit_en_diagnose():
    bron = (PAKKET / "sensor.py").read_text()
    assert 'bronnen["airco_w"] = eigen["airco_vermogen"]' in bron
    assert '"airco_vermogen": _veilig("get_airco_vermogen"' in (PAKKET / "diagnostics.py").read_text()


def test_cockpit_toont_airco_nu():
    """v5.202.1: airco_w werd geladen maar nergens getoond."""
    js = (PAKKET / "www" / "ems-cockpit.js").read_text()
    assert 'this._s("airco_w")' in js and '"Airco nu"' in js
