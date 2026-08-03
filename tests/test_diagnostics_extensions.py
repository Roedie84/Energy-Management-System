"""Diagnostics export includes the vacation mode and appliance-awareness
fields, and remains JSON-serializable (v0.47.0)."""
import asyncio
import json

from custom_components.energy_management_system.const import DOMAIN


class _FakeConfigEntry:
    data = {}
    options = {}
    entry_id = "entry1"


def test_diagnostics_includes_vacation_and_appliance_fields(make_coordinator, hass):
    from custom_components.energy_management_system import diagnostics as diag_mod

    coordinator = make_coordinator(
        {
            "dishwasher_power_sensor_entity": "sensor.vaatwasser_vermogen",
            "dishwasher_ready_sensor_entity": "binary_sensor.vaatwasser_remote_start",
        }
    )
    coordinator.dishwasher_usage_hourly_history[19] = [1.0, 1.0, 0.0]
    coordinator.last_dishwasher_notification = "Test notification"
    coordinator.vacation_mode = True

    hass.data = {DOMAIN: {"entry1": coordinator}}

    result = asyncio.run(
        diag_mod.async_get_config_entry_diagnostics(hass, _FakeConfigEntry())
    )
    c = result["coordinator"]

    assert c["vacation_mode"] is True
    assert c["dishwasher_usage_hours_with_data"] == 1
    assert c["dishwasher_typical_usage_hours"] == [19]
    assert c["last_dishwasher_notification"] == "Test notification"

    # Must remain JSON-serializable end to end - this is what would have
    # caught the earlier "State attributes exceed maximum size" class of
    # bug if any new field had accidentally included a large raw list.
    json.dumps(result)
