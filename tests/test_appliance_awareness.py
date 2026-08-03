"""Optional appliance awareness (v0.47.0): learn typical usage hours and
send a one-per-day notification when an appliance is ready to start
during the day's cheapest price block. Never controls the appliance
itself.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from conftest import make_price_forecast

DAY0 = datetime(2026, 8, 2, tzinfo=timezone.utc)


def _two_day_forecast():
    def price_fn(hour, minute):
        if 9 <= hour < 12:
            return 1_300_000
        if 18 <= hour < 22:
            return 3_600_000
        return 2_500_000

    entries = []
    for day_offset in range(2):
        entries += make_price_forecast(DAY0 + timedelta(days=day_offset), price_fn)
    return entries


def _base_config():
    return {
        "price_sensor_entity": "sensor.price",
        "price_attribute": "price_tax_included",
        "operation_select_entity": "select.op",
        "manual_power_number_entity": "number.pow",
        "consumption_power_sensor_entity": "sensor.p1",
        "dishwasher_power_sensor_entity": "sensor.vaatwasser_vermogen",
        "dishwasher_ready_sensor_entity": "binary_sensor.vaatwasser_remote_start",
    }


def test_no_notification_outside_the_cheapest_block(make_coordinator, hass):
    hass.states.set("sensor.price", "0", {"forecast": _two_day_forecast()})
    hass.states.set("sensor.p1", "200")
    hass.states.set("sensor.vaatwasser_vermogen", "0")
    hass.states.set("binary_sensor.vaatwasser_remote_start", "on")

    coordinator = make_coordinator(_base_config())

    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: DAY0.replace(hour=14, minute=0)
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_dishwasher_notification is None


def test_notification_when_ready_during_cheapest_block(make_coordinator, hass):
    hass.states.set("sensor.price", "0", {"forecast": _two_day_forecast()})
    hass.states.set("sensor.p1", "200")
    hass.states.set("sensor.vaatwasser_vermogen", "0")
    hass.states.set("binary_sensor.vaatwasser_remote_start", "on")

    coordinator = make_coordinator(_base_config())

    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: DAY0.replace(hour=9, minute=15)
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_dishwasher_notification is not None
    assert "vaatwasser" in coordinator.last_dishwasher_notification.lower()


def test_no_duplicate_notification_same_day(make_coordinator, hass):
    hass.states.set("sensor.price", "0", {"forecast": _two_day_forecast()})
    hass.states.set("sensor.p1", "200")
    hass.states.set("sensor.vaatwasser_vermogen", "0")
    hass.states.set("binary_sensor.vaatwasser_remote_start", "on")

    coordinator = make_coordinator(_base_config())

    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: DAY0.replace(hour=9, minute=15)
    asyncio.run(coordinator._async_update_locked())
    first_notified_date = coordinator._dishwasher_notified_date

    coord_mod.dt_util.now = lambda: DAY0.replace(hour=9, minute=30)
    asyncio.run(coordinator._async_update_locked())

    assert coordinator._dishwasher_notified_date == first_notified_date


def test_no_notification_when_appliance_already_running(make_coordinator, hass):
    hass.states.set("sensor.price", "0", {"forecast": _two_day_forecast()})
    hass.states.set("sensor.p1", "200")
    hass.states.set("sensor.vaatwasser_vermogen", "1200")  # already running
    hass.states.set("binary_sensor.vaatwasser_remote_start", "on")

    coordinator = make_coordinator(_base_config())

    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: DAY0.replace(hour=9, minute=15)
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_dishwasher_notification is None


def test_usage_tracking_records_running_state_per_hour(make_coordinator, hass):
    hass.states.set("sensor.vaatwasser_vermogen", "1200")  # running

    coordinator = make_coordinator(
        {"dishwasher_power_sensor_entity": "sensor.vaatwasser_vermogen"}
    )
    now = DAY0.replace(hour=19, minute=0)
    coordinator._update_appliance_usage_tracking(now)

    assert coordinator.dishwasher_usage_hourly_history[19] == [1.0]


def test_usage_tracking_paused_during_vacation_mode(make_coordinator, hass):
    hass.states.set("sensor.vaatwasser_vermogen", "1200")

    coordinator = make_coordinator(
        {"dishwasher_power_sensor_entity": "sensor.vaatwasser_vermogen"}
    )
    coordinator.vacation_mode = True
    now = DAY0.replace(hour=19, minute=0)
    coordinator._update_appliance_usage_tracking(now)

    assert coordinator.dishwasher_usage_hourly_history == {}


def test_learned_usage_hours_reflects_frequency(make_coordinator):
    coordinator = make_coordinator({})
    # Hour 19: ran in 3 of 4 samples (75%) - should count as typical.
    coordinator.dishwasher_usage_hourly_history[19] = [1.0, 1.0, 1.0, 0.0]
    # Hour 10: ran in 1 of 10 samples (10%) - below the default 15% bar.
    coordinator.dishwasher_usage_hourly_history[10] = [1.0] + [0.0] * 9

    typical = coordinator.learned_appliance_usage_hours(
        coordinator.dishwasher_usage_hourly_history
    )

    assert 19 in typical
    assert 10 not in typical
