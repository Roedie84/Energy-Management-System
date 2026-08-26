"""Secondary price tier (v0.58.0): sell during quarters that don't
clear the strict primary threshold, but do clear a wider secondary
threshold, using only *spare* headroom left over after today's
remaining genuinely-expensive (primary-tier) quarters are accounted
for. Found via a live report: 8kWh available, only a single 15-minute
quarter sold at the strict threshold, while surrounding quarters at a
only slightly lower price went unused despite clearly abundant
capacity.
"""
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 8, 3, tzinfo=timezone.utc)


def _build_entries(prices: dict, default_price: float = 0.25):
    entries = []
    for hour in range(24):
        for minute in (0, 15, 30, 45):
            price = prices.get((hour, minute), default_price)
            start = DAY0.replace(hour=hour, minute=minute)
            entries.append((start, start + timedelta(minutes=15), price * 1_000_000))
    return entries


def _narrow_peak_prices():
    prices = {}
    for hour in range(9, 12):
        for minute in (0, 15, 30, 45):
            prices[(hour, minute)] = 0.15
    for hour in range(18, 21):
        for minute in (0, 15, 30, 45):
            prices[(hour, minute)] = 0.36  # just under the primary threshold
    prices[(19, 45)] = 0.4177  # the one genuine peak quarter
    return prices


def test_secondary_tier_used_when_headroom_is_abundant(make_coordinator):
    coordinator = make_coordinator({"manual_discharge_power": 1600})
    entries = _build_entries(_narrow_peak_prices())
    now = DAY0.replace(hour=18, minute=15)  # priced at 0.36, below the primary bar

    assert coordinator._is_worth_discharging_at_secondary_tier(
        entries, now, headroom_kwh=2.83, discharge_power_w=1600
    ) is True


def test_secondary_tier_not_used_when_headroom_is_needed_for_the_real_peak(
    make_coordinator,
):
    coordinator = make_coordinator({"manual_discharge_power": 1600})
    entries = _build_entries(_narrow_peak_prices())
    now = DAY0.replace(hour=18, minute=15)

    assert coordinator._is_worth_discharging_at_secondary_tier(
        entries, now, headroom_kwh=0.4, discharge_power_w=1600
    ) is False


def test_secondary_tier_never_applies_below_its_own_wider_threshold(
    make_coordinator,
):
    """Even with abundant headroom, a genuinely cheap/normal-priced
    quarter must never qualify - only ones above the wider secondary
    bar."""
    coordinator = make_coordinator({"manual_discharge_power": 1600})
    entries = _build_entries(_narrow_peak_prices())
    now = DAY0.replace(hour=9, minute=0)  # priced at 0.15 - today's cheap block

    assert coordinator._is_worth_discharging_at_secondary_tier(
        entries, now, headroom_kwh=10.0, discharge_power_w=1600
    ) is False


def test_spare_headroom_is_zero_when_primary_tier_already_needs_it_all(
    make_coordinator,
):
    coordinator = make_coordinator({"manual_discharge_power": 1600})
    prices = {}
    for hour in range(18, 21):
        for minute in (0, 15, 30, 45):
            prices[(hour, minute)] = 0.40  # every one of these clears the primary bar
    entries = _build_entries(prices, default_price=0.20)
    now = DAY0.replace(hour=17, minute=45)

    spare = coordinator._get_spare_headroom_after_primary_tier_kwh(
        entries, now, headroom_kwh=1.0, discharge_power_w=1600
    )
    assert spare == 0.0
