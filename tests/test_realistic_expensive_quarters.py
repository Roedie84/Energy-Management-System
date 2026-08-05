"""Realistic, capacity-aware "expensive quarters" count (v0.63.27).

Reported: on a day with a relatively flat price shape, the raw count of
quarters clearing the dynamic threshold ran to 35 (~8.75h at
manual_discharge_power) against a battery with only ~7.4 kWh usable -
physically impossible, making the number confusing rather than useful.
Capped by the Zendure's own reported total capacity and hardware
minimum SoC (both read live, not configured statically).
"""
from datetime import datetime, timezone

from conftest import make_price_forecast

DAY0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _many_expensive_quarters_price_fn(hour, minute):
    """35 quarters (8h45m) at/above the dynamic threshold, 1 cheap dip."""
    if 9 <= hour < 12:
        return 1_000_000  # cheapest block
    if hour in (13, 14, 15, 16, 17, 18, 19, 20, 21):
        return 3_800_000  # 9 hours = 36 quarters clearing the threshold
    return 2_500_000


def _base_config(**overrides):
    config = {
        "price_sensor_entity": "sensor.price",
        "price_attribute": "price_tax_included",
        "manual_discharge_power": 1600,
    }
    config.update(overrides)
    return config


def test_raw_count_uncapped_without_capacity_sensors(make_coordinator, hass):
    """No regression for anyone not using the new fields - same as
    before this version."""
    forecast = make_price_forecast(DAY0, _many_expensive_quarters_price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})

    coordinator = make_coordinator(_base_config())
    entries = coordinator._get_forecast_entries()
    now = DAY0.replace(hour=13, minute=0)

    count = coordinator._count_expensive_quarters_today(entries, now)
    assert count == 36
    assert coordinator.last_max_sellable_quarters_by_capacity is None


def test_count_capped_by_usable_capacity(make_coordinator, hass):
    """Reproduces the reported scenario: ~7.4 kWh usable capacity at
    1600W caps the count at 18 quarters (7.4 / 0.4 = 18.5 -> 18), far
    below the raw 36 that clear the price threshold."""
    forecast = make_price_forecast(DAY0, _many_expensive_quarters_price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.total_capacity", "7.4")
    hass.states.set("number.min_soc", "0")

    coordinator = make_coordinator(
        _base_config(
            battery_total_capacity_sensor_entity="sensor.total_capacity",
            battery_min_soc_number_entity="number.min_soc",
        )
    )
    entries = coordinator._get_forecast_entries()
    now = DAY0.replace(hour=13, minute=0)

    count = coordinator._count_expensive_quarters_today(entries, now)
    assert count == 18
    assert coordinator.last_max_sellable_quarters_by_capacity == 18


def test_hardware_min_soc_reduces_usable_capacity(make_coordinator, hass):
    """The Zendure's own hardware minimum SoC further reduces usable
    capacity - e.g. a 10% min SoC on an 8 kWh battery leaves 7.2 kWh
    usable, not the full 8."""
    forecast = make_price_forecast(DAY0, _many_expensive_quarters_price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.total_capacity", "8.0")
    hass.states.set("number.min_soc", "10")

    coordinator = make_coordinator(
        _base_config(
            battery_total_capacity_sensor_entity="sensor.total_capacity",
            battery_min_soc_number_entity="number.min_soc",
        )
    )
    entries = coordinator._get_forecast_entries()
    now = DAY0.replace(hour=13, minute=0)

    # Usable = 8.0 * 0.90 = 7.2 kWh -> 7.2 / 0.4 = 18 quarters exactly.
    count = coordinator._count_expensive_quarters_today(entries, now)
    assert count == 18


def test_raw_count_used_when_it_is_the_smaller_number(make_coordinator, hass):
    """A day with genuinely few expensive quarters (fewer than the
    battery could sustain) isn't artificially inflated - min() picks
    whichever is smaller."""
    def price_fn(hour, minute):
        if hour == 19:
            return 4_500_000
        if 9 <= hour < 12:
            return 1_500_000
        return 2_500_000

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.total_capacity", "20.0")  # a big battery
    hass.states.set("number.min_soc", "0")

    coordinator = make_coordinator(
        _base_config(
            battery_total_capacity_sensor_entity="sensor.total_capacity",
            battery_min_soc_number_entity="number.min_soc",
        )
    )
    entries = coordinator._get_forecast_entries()
    now = DAY0.replace(hour=19, minute=15)

    # Only 4 quarters (hour 19) clear the threshold; capacity could
    # sustain far more (50 quarters), so the raw 4 wins.
    assert coordinator._count_expensive_quarters_today(entries, now) == 4


def test_missing_one_of_the_two_entities_falls_back_to_raw_count(
    make_coordinator, hass
):
    forecast = make_price_forecast(DAY0, _many_expensive_quarters_price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.total_capacity", "7.4")
    # min_soc entity not configured at all.

    coordinator = make_coordinator(
        _base_config(battery_total_capacity_sensor_entity="sensor.total_capacity")
    )
    entries = coordinator._get_forecast_entries()
    now = DAY0.replace(hour=13, minute=0)

    assert coordinator._count_expensive_quarters_today(entries, now) == 36
