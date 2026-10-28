"""v5.142.1: de balanscheck rekent met het geleerde laad-/ontlaadrendement.

Meldronde 28-10: tijdens netladen (2,0-2,3 kW AC, laadrendement 80 %)
steeg de voorraad met ~1,8 kW; de fout van ~460 W lag boven de drempel
van 300 W en de sensor-gezondheid zakte elke laadmiddag naar 70 %.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    MEASUREMENT_QUALITY_MIN_SAMPLES,
    MIN_HALF_EFFICIENCY_SAMPLES,
)

DAY0 = datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc)
STAP = 35


def _config():
    return {
        "available_energy_sensor_entity": "sensor.available_energy",
        "battery_power_sensor_entity": "sensor.battery_power",
    }


def _laden(coordinator, hass, rendement):
    """2300 W AC laden; de voorraad stijgt met 2300 x 0,80 W over 35 min."""
    if rendement is not None:
        coordinator.charge_efficiency_history = [rendement] * MIN_HALF_EFFICIENCY_SAMPLES
        coordinator.discharge_efficiency_history = [90.0] * MIN_HALF_EFFICIENCY_SAMPLES
    hass.states.set("sensor.available_energy", "3.0")
    hass.states.set("sensor.battery_power", "-2300")
    coordinator._update_energy_balance_validation(DAY0)
    coordinator.energy_balance_error_history = [0.0] * (MEASUREMENT_QUALITY_MIN_SAMPLES - 1)
    stijging = 2.3 * 0.80 * STAP / 60
    hass.states.set("sensor.available_energy", f"{3.0 + stijging:.4f}")
    coordinator._update_energy_balance_validation(DAY0 + timedelta(minutes=STAP))


def test_netladen_met_geleerd_rendement_is_geen_fout(make_coordinator, hass):
    c = make_coordinator(_config())
    _laden(c, hass, 80.0)
    assert abs(c.last_energy_balance_error_w) < 5
    assert c.sensor_health_score == 100.0


def test_zonder_geleerd_rendement_gedrag_als_voorheen(make_coordinator, hass):
    c = make_coordinator(_config())
    _laden(c, hass, None)
    assert abs(c.last_energy_balance_error_w - 460) < 5
    assert c.sensor_health_score < 100.0


def test_ontladen_deelt_door_ontlaadrendement(make_coordinator, hass):
    c = make_coordinator(_config())
    c.charge_efficiency_history = [80.0] * MIN_HALF_EFFICIENCY_SAMPLES
    c.discharge_efficiency_history = [90.0] * MIN_HALF_EFFICIENCY_SAMPLES
    assert abs(c._balans_verwacht_voorraadvermogen_w(1800.0) - 2000.0) < 0.01
    assert abs(c._balans_verwacht_voorraadvermogen_w(-2000.0) + 1600.0) < 0.01
    assert c._balans_verwacht_voorraadvermogen_w(0.0) == 0.0


def test_rendement_begrensd(make_coordinator, hass):
    c = make_coordinator(_config())
    c.charge_efficiency_history = [40.0] * MIN_HALF_EFFICIENCY_SAMPLES
    c.discharge_efficiency_history = [130.0] * MIN_HALF_EFFICIENCY_SAMPLES
    # laden hooguit 25 % verlies, ontladen hooguit 100 %
    assert abs(c._balans_verwacht_voorraadvermogen_w(-1000.0) + 750.0) < 0.01
    assert abs(c._balans_verwacht_voorraadvermogen_w(1000.0) - 1000.0) < 0.01


def test_echte_fout_blijft_zichtbaar(make_coordinator, hass):
    """Sensor zegt stil, voorraad daalt hard: nog steeds fout."""
    c = make_coordinator(_config())
    c.charge_efficiency_history = [80.0] * MIN_HALF_EFFICIENCY_SAMPLES
    c.discharge_efficiency_history = [90.0] * MIN_HALF_EFFICIENCY_SAMPLES
    hass.states.set("sensor.available_energy", "3.0")
    hass.states.set("sensor.battery_power", "0")
    c._update_energy_balance_validation(DAY0)
    hass.states.set("sensor.available_energy", "2.0")
    c._update_energy_balance_validation(DAY0 + timedelta(minutes=STAP))
    assert c.last_energy_balance_error_w > 1000
