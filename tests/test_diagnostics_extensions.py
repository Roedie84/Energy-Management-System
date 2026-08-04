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


def test_diagnostics_includes_mode_change_log(make_coordinator, hass):
    """v0.63.11: every genuine mode/power change lands in a bounded log,
    independent of whether a notify service is configured - so a single
    diagnostics export can reconstruct the day's mode history."""
    import asyncio as _asyncio
    from datetime import datetime, timezone

    from conftest import make_price_forecast
    from custom_components.energy_management_system import diagnostics as diag_mod
    from custom_components.energy_management_system import coordinator as coord_mod

    DAY0 = datetime(2026, 8, 1, tzinfo=timezone.utc)

    def price_fn(hour, minute):
        if hour == 13 and minute == 0:
            return -500_000
        return 2_500_000

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "200")

    coordinator = make_coordinator(
        {
            "price_sensor_entity": "sensor.price",
            "price_attribute": "price_tax_included",
            "operation_select_entity": "select.op",
            "manual_power_number_entity": "number.pow",
            "manual_discharge_power": 1600,
            "negative_price_charge_power": -2000,
        }
    )

    async def run():
        coord_mod.dt_util.now = lambda: DAY0.replace(hour=12, minute=45)
        await coordinator._async_update_locked()
        coord_mod.dt_util.now = lambda: DAY0.replace(hour=13, minute=0)
        await coordinator._async_update_locked()

    _asyncio.run(run())

    hass.data = {DOMAIN: {"entry1": coordinator}}
    result = _asyncio.run(
        diag_mod.async_get_config_entry_diagnostics(hass, _FakeConfigEntry())
    )
    log = result["coordinator"]["mode_change_log"]

    assert len(log) == 1
    assert log[0]["reason"] == "negative_price"
    assert log[0]["charge_power_applied"] == -2000
    json.dumps(result)


def test_diagnostics_includes_dated_shortfall_and_excess_history(
    make_coordinator, hass
):
    """v0.63.11: the boolean history alone doesn't say *which* days had
    a shortfall/excess - a parallel dates list fills that gap."""
    from custom_components.energy_management_system import diagnostics as diag_mod
    import asyncio as _asyncio

    coordinator = make_coordinator({})
    coordinator.reserve_shortfall_history = [False, True]
    coordinator.reserve_shortfall_dates = ["2026-08-02", "2026-08-03"]
    coordinator.reserve_excess_history = [True]
    coordinator.reserve_excess_dates = ["2026-08-03"]

    hass.data = {DOMAIN: {"entry1": coordinator}}
    result = _asyncio.run(
        diag_mod.async_get_config_entry_diagnostics(hass, _FakeConfigEntry())
    )
    c = result["coordinator"]

    assert c["reserve_shortfall_dates"] == ["2026-08-02", "2026-08-03"]
    assert c["reserve_excess_dates"] == ["2026-08-03"]
    json.dumps(result)


def test_diagnostics_includes_raw_pv_forecast(make_coordinator, hass):
    """v0.63.11: raw Solcast half-hour entries, to verify the forecast
    itself against the integration's processed numbers without a
    separate trip to Ontwikkelaarshulpmiddelen."""
    from datetime import datetime, timezone
    import asyncio as _asyncio

    from custom_components.energy_management_system import diagnostics as diag_mod

    coordinator = make_coordinator(
        {"solar_forecast_sensor_entity": "sensor.solcast"}
    )
    hass.states.set(
        "sensor.solcast",
        "5.0",
        {
            "detailedForecast": [
                {
                    "period_start": datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc),
                    "pv_estimate": 2.0,
                },
                {
                    "period_start": datetime(2026, 8, 4, 12, 30, tzinfo=timezone.utc),
                    "pv_estimate": 1.5,
                },
            ]
        },
    )

    hass.data = {DOMAIN: {"entry1": coordinator}}
    result = _asyncio.run(
        diag_mod.async_get_config_entry_diagnostics(hass, _FakeConfigEntry())
    )
    entries = result["pv_forecast_raw"]["entries"]

    assert len(entries) == 2
    assert entries[0]["kwh"] == 1.0  # 2.0 kW * 0.5h
    json.dumps(result)
