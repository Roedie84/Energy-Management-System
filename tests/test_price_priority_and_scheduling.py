"""Price-priority discharge allocation (v0.40.0) and the discharge_start
/ cheap_block_start ordering fix (v0.39.0) for unusual price shapes
(e.g. a solar-driven midday dip followed by a later evening peak).
"""
import asyncio
from datetime import datetime, timedelta, timezone

from conftest import make_price_forecast

DAY0 = datetime(2026, 8, 2, tzinfo=timezone.utc)


def test_limited_headroom_goes_to_the_priciest_quarters_first(make_coordinator, hass):
    """A long, gradually-peaking evening stretch with only enough
    headroom for ~2 quarters should discharge during the price peak,
    not whichever quarter comes first chronologically."""
    evening_prices = [
        3170, 3200, 3250, 3300, 3350, 3400, 3450, 3500, 3550, 3600,
        3620, 3630, 3637, 3600, 3550, 3500, 3450, 3400, 3350, 3300,
    ]
    idx = {"i": 0}

    def price_fn(hour, minute):
        if 18 <= hour < 23 or (hour == 23 and minute < 45):
            price = evening_prices[idx["i"] % len(evening_prices)] * 1000
            idx["i"] += 1
            return price
        if 9 <= hour < 12:
            return 1_300_000
        return 2_300_000

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "200")
    hass.states.set("sensor.available_kwh", "3.925")

    config = {
        "price_sensor_entity": "sensor.price",
        "price_attribute": "price_tax_included",
        "operation_select_entity": "select.op",
        "manual_power_number_entity": "number.pow",
        "manual_discharge_power": 1600,
        "consumption_power_sensor_entity": "sensor.p1",
        "available_energy_sensor_entity": "sensor.available_kwh",
    }
    coordinator = make_coordinator(config)

    from custom_components.energy_management_system import coordinator as coord_mod

    async def run():
        # Relatively cheap edge of the peak (0.317) - should hold off.
        coord_mod.dt_util.now = lambda: DAY0.replace(hour=18, minute=30)
        await coordinator._async_update_locked()
        early_reason = coordinator.last_reason
        early_power = coordinator.last_discharge_power_applied

        # Near the true peak (0.363) - should discharge at full power.
        coord_mod.dt_util.now = lambda: DAY0.replace(hour=20, minute=27)
        await coordinator._async_update_locked()
        peak_reason = coordinator.last_reason
        peak_power = coordinator.last_discharge_power_applied

        assert early_power in (None, 0)
        assert early_reason != "expensive_quarter" or early_power in (None, 0)
        assert peak_reason == "expensive_quarter"
        assert peak_power == 1600

    asyncio.run(run())


def test_discharge_start_never_lands_after_cheap_block_start(make_coordinator, hass):
    """Regression test for the v0.39.0 bug: an unusual price shape (cheap
    midday dip followed by a later evening peak) used to produce a
    discharge_start *after* cheap_block_start, making the
    smart_discharging window an invalid, always-empty range."""
    coordinator = make_coordinator({})

    def price_fn(hour, minute):
        if 14 <= hour < 17 or (hour == 17 and minute == 0):
            return 1_300_000  # midday cheap dip (e.g. solar oversupply)
        if 18 <= hour < 23 or (hour == 23 and minute < 45):
            return 3_400_000  # evening peak, *after* the cheap dip
        return 2_200_000

    forecast_entries = []
    for hour in range(24):
        for minute in (0, 15, 30, 45):
            start = DAY0.replace(hour=hour, minute=minute)
            forecast_entries.append((start, start + timedelta(minutes=15), price_fn(hour, minute)))

    now = DAY0.replace(hour=10, minute=0)
    cheap_block_start = DAY0.replace(hour=14, minute=0)

    discharge_start = coordinator._compute_dynamic_discharge_start(
        forecast_entries, now, cheap_block_start
    )

    if discharge_start is not None:
        assert discharge_start <= cheap_block_start
