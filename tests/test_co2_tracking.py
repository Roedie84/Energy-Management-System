"""CO2-intensiteit van het net (v0.63.101, gevraagd: "zaken voor een
typisch EMS welke we kunnen toevoegen"). Optioneel, puur informatief.
"""
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 8, 6, 18, 0, tzinfo=timezone.utc)


def _base_config(**overrides):
    config = {
        "co2_intensity_sensor_entity": "sensor.co2",
        "consumption_power_sensor_entity": "sensor.p1",
    }
    config.update(overrides)
    return config


def test_first_tick_only_seeds(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.co2", "300")
    hass.states.set("sensor.p1", "1000")

    coordinator._update_co2_tracking(DAY0)

    assert coordinator.co2_emitted_today_kg == 0.0
    assert coordinator.last_co2_intensity_g_per_kwh == 300


def test_emissions_accumulate_from_import(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.co2", "300")  # g CO2/kWh
    hass.states.set("sensor.p1", "1000")  # 1kW import
    coordinator._update_co2_tracking(DAY0)

    coordinator._update_co2_tracking(DAY0 + timedelta(hours=1))

    # 1 kWh imported * 300 g/kWh = 300g = 0.3 kg
    assert round(coordinator.co2_emitted_today_kg, 3) == 0.3


def test_export_does_not_count_as_emissions(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.co2", "300")
    hass.states.set("sensor.p1", "-500")  # exporting
    coordinator._update_co2_tracking(DAY0)

    coordinator._update_co2_tracking(DAY0 + timedelta(hours=1))

    assert coordinator.co2_emitted_today_kg == 0.0


def test_day_rollover_resets_daily_total(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.co2", "300")
    hass.states.set("sensor.p1", "1000")
    coordinator._update_co2_tracking(DAY0)
    coordinator._update_co2_tracking(DAY0 + timedelta(hours=1))
    assert coordinator.co2_emitted_today_kg > 0

    next_day = DAY0 + timedelta(days=1)
    coordinator._update_co2_tracking(next_day)

    assert coordinator.co2_emitted_today_kg == 0.0


def test_no_error_without_configured_sensor(make_coordinator, hass):
    coordinator = make_coordinator({})

    coordinator._update_co2_tracking(DAY0)

    assert coordinator.co2_emitted_today_kg == 0.0
    assert coordinator.last_co2_intensity_g_per_kwh is None
