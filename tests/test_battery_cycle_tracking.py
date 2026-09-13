"""Accu-gezondheid: cyclus-telling en geschatte capaciteitsdegradatie
(v0.63.101, gevraagd: "zaken voor een typisch EMS welke we kunnen
toevoegen"). Bewust en duidelijk een ruwe schatting, geen gemeten
waarde.
"""
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


def _base_config(**overrides):
    config = {"battery_power_sensor_entity": "sensor.battery"}
    config.update(overrides)
    return config


def test_first_tick_only_seeds(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.battery", "1000")  # discharging

    coordinator._update_battery_cycle_tracking(DAY0)

    assert coordinator.battery_cumulative_discharged_kwh == 0.0


def test_discharge_accumulates(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.battery", "1000")
    coordinator._update_battery_cycle_tracking(DAY0)

    coordinator._update_battery_cycle_tracking(DAY0 + timedelta(hours=1))

    assert coordinator.battery_cumulative_discharged_kwh == 1.0


def test_charging_does_not_count_toward_cycles(make_coordinator, hass):
    """Only discharge counts toward cycle-counting - the standard
    convention, avoiding double-counting via round-trip losses."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.battery", "-1000")  # charging
    coordinator._update_battery_cycle_tracking(DAY0)

    coordinator._update_battery_cycle_tracking(DAY0 + timedelta(hours=1))

    assert coordinator.battery_cumulative_discharged_kwh == 0.0


def test_estimated_full_cycles_uses_capacity_sensor(make_coordinator, hass):
    coordinator = make_coordinator(
        _base_config(battery_total_capacity_sensor_entity="sensor.capacity")
    )
    hass.states.set("sensor.capacity", "5.0")
    coordinator.battery_cumulative_discharged_kwh = 20000.0  # 4000 cycles

    assert coordinator.battery_estimated_full_cycles == 4000.0


def test_estimated_full_cycles_none_without_capacity_sensor(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    coordinator.battery_cumulative_discharged_kwh = 100.0

    assert coordinator.battery_estimated_full_cycles is None


def test_estimated_capacity_percent_at_zero_cycles(make_coordinator, hass):
    coordinator = make_coordinator(
        _base_config(battery_total_capacity_sensor_entity="sensor.capacity")
    )
    hass.states.set("sensor.capacity", "5.0")
    coordinator.battery_cumulative_discharged_kwh = 0.0

    assert coordinator.battery_estimated_capacity_percent == 100.0


def test_estimated_capacity_percent_at_expected_end_of_life(make_coordinator, hass):
    """v3.66.0: dezelfde cyclusverwachting als de slijtageberekening.

    Er stonden er twee voor dezelfde grootheid - 4000 uit v0.63.101 en
    6000 uit v3.5.0 - allebei "cycli tot 80% restcapaciteit". Deze
    schatting rekende de accu daardoor anderhalf keer zo snel af als de
    slijtageberekening.
    """
    from custom_components.energy_management_system.const import (
        DEFAULT_BATTERY_CYCLE_LIFE,
    )

    coordinator = make_coordinator(
        _base_config(battery_total_capacity_sensor_entity="sensor.capacity")
    )
    hass.states.set("sensor.capacity", "5.0")
    coordinator.battery_cumulative_discharged_kwh = (
        DEFAULT_BATTERY_CYCLE_LIFE * 5.0
    )

    assert coordinator.battery_estimated_capacity_percent == 80.0


def test_the_configured_cycle_life_is_followed(make_coordinator, hass):
    """Wie zijn eigen cyclusaantal invult, hoort dat ook hier terug te

    zien - anders rekent de ene helft van de integratie met de opgave
    van de fabrikant en de andere met een generieke aanname.
    """
    from custom_components.energy_management_system.const import (
        CONF_BATTERY_CYCLE_LIFE,
    )

    coordinator = make_coordinator(
        _base_config(
            battery_total_capacity_sensor_entity="sensor.capacity",
            **{CONF_BATTERY_CYCLE_LIFE: 3000},
        )
    )
    hass.states.set("sensor.capacity", "5.0")
    coordinator.battery_cumulative_discharged_kwh = 3000 * 5.0

    assert coordinator.battery_estimated_capacity_percent == 80.0


def test_estimated_capacity_percent_never_drops_below_the_model_floor(
    make_coordinator, hass
):
    """Far beyond the modelled cycle count must clamp at 80%, not
    extrapolate into an implausible negative/very-low estimate."""
    from custom_components.energy_management_system.const import (
        BATTERY_CYCLES_TO_80_PERCENT_CAPACITY,
    )

    coordinator = make_coordinator(
        _base_config(battery_total_capacity_sensor_entity="sensor.capacity")
    )
    hass.states.set("sensor.capacity", "5.0")
    coordinator.battery_cumulative_discharged_kwh = (
        BATTERY_CYCLES_TO_80_PERCENT_CAPACITY * 5.0 * 3
    )

    assert coordinator.battery_estimated_capacity_percent == 80.0


def test_no_error_without_configured_sensor(make_coordinator, hass):
    coordinator = make_coordinator({})

    coordinator._update_battery_cycle_tracking(DAY0)

    assert coordinator.battery_cumulative_discharged_kwh == 0.0
