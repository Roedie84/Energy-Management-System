"""Dynamic "expensive quarter" price threshold (v0.27.0+).

A quarter is "expensive" if its price falls within the top fraction of
the day's own price range - no fixed count of quarters, self-adjusting
to however many quarters actually clear the bar each day.
"""
from datetime import datetime, timezone

from conftest import make_price_forecast

DAY0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


def test_dynamic_threshold_uses_top_fraction_of_range(make_coordinator, hass):
    """Only quarters within the top 20% of today's price range should
    count as 'expensive' - not a fixed count."""

    def price_fn(hour, minute):
        if hour == 19:
            return 4_500_000  # 0.45 EUR/kWh - the day's peak
        if hour == 20:
            return 3_800_000  # 0.38 EUR/kWh - below the dynamic threshold
        if 9 <= hour < 12:
            return 1_500_000  # 0.15 EUR/kWh - today's cheapest
        return 2_500_000  # 0.25 EUR/kWh - a normal quarter

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})

    coordinator = make_coordinator(
        {"price_sensor_entity": "sensor.price", "price_attribute": "price_tax_included"}
    )
    entries = coordinator._get_forecast_entries()

    now_1915 = DAY0.replace(hour=19, minute=15)
    now_2015 = DAY0.replace(hour=20, minute=15)
    now_1300 = DAY0.replace(hour=13, minute=0)

    # threshold = max - 0.20 * (max - min) = 0.45 - 0.20*0.30 = 0.39
    assert coordinator._is_expensive_now(entries, now_1915) is True
    assert coordinator._is_expensive_now(entries, now_2015) is False  # 0.38 < 0.39
    assert coordinator._is_expensive_now(entries, now_1300) is False  # normal price


def test_effective_expensive_quarter_count_reflects_the_bar(make_coordinator, hass):
    """The informational count sensor should match how many quarters
    actually clear the dynamic threshold, not a hardcoded number."""

    def price_fn(hour, minute):
        if hour == 19:
            return 4_500_000
        if 9 <= hour < 12:
            return 1_500_000
        return 2_500_000

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})

    coordinator = make_coordinator(
        {"price_sensor_entity": "sensor.price", "price_attribute": "price_tax_included"}
    )
    entries = coordinator._get_forecast_entries()
    now = DAY0.replace(hour=19, minute=15)

    # Only hour 19 (4 quarters) clears the threshold in this price shape.
    assert coordinator._count_expensive_quarters_today(entries, now) == 4
