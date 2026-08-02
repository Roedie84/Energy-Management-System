"""Automatic Wh/MWh -> kWh unit conversion (v0.38.0).

Found via a real SolarEdge yield sensor reporting in Wh while the
integration assumed everything was already kWh - a factor 1000 error
that silently broke the Solcast accuracy comparison for weeks.
"""


def test_wh_sensor_is_converted_to_kwh(make_coordinator, hass):
    hass.states.set("sensor.yield_today", "1694.0", {"unit_of_measurement": "Wh"})
    coordinator = make_coordinator({})
    assert coordinator._read_sensor_float("sensor.yield_today") == 1.694


def test_kwh_sensor_is_left_unchanged(make_coordinator, hass):
    hass.states.set("sensor.available", "18.4", {"unit_of_measurement": "kWh"})
    coordinator = make_coordinator({})
    assert coordinator._read_sensor_float("sensor.available") == 18.4


def test_power_sensor_in_watts_is_unaffected(make_coordinator, hass):
    """A power sensor's unit ('W') must never be mistaken for the energy
    unit 'Wh' - only an exact 'wh'/'mwh' match should trigger conversion."""
    hass.states.set("sensor.p1", "300", {"unit_of_measurement": "W"})
    coordinator = make_coordinator({})
    assert coordinator._read_sensor_float("sensor.p1") == 300.0


def test_sensor_without_unit_attribute_is_unaffected(make_coordinator, hass):
    hass.states.set("sensor.soc", "42", {})
    coordinator = make_coordinator({})
    assert coordinator._read_sensor_float("sensor.soc") == 42.0


def test_mwh_sensor_is_converted_to_kwh(make_coordinator, hass):
    hass.states.set("sensor.big_battery", "0.005", {"unit_of_measurement": "MWh"})
    coordinator = make_coordinator({})
    assert coordinator._read_sensor_float("sensor.big_battery") == 5.0
