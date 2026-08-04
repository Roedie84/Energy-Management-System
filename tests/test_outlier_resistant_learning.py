"""Median-based learning for the 7-day hourly consumption profile and PV
hourly bias (v0.62.0), replacing a simple mean.

Reported scenario: a single unusual day - the washing machine running
several loads back-to-back, or a passing rain cloud during an otherwise
sunny forecast - shouldn't meaningfully move a 7-day baseline. With a
mean, that one day still gets a 1/7 vote every day until it ages out a
week later. With a median, a single outlier is effectively ignored
unless it becomes the new normal (a majority of the window has to
agree) - while a genuine sustained change still comes through once
enough recent days reflect it.
"""


def test_single_outlier_day_barely_moves_the_consumption_median(make_coordinator):
    coordinator = make_coordinator({})
    # Six normal days at ~300W, one outlier day (heavy laundry) at 900W.
    coordinator.hourly_consumption_profile[9] = [
        0.30, 0.31, 0.29, 0.30, 0.32, 0.30, 0.90,
    ]

    median = coordinator.learned_hourly_avg_kw(9)
    mean = sum(coordinator.hourly_consumption_profile[9]) / 7

    assert median == 0.30  # the outlier has zero effect
    assert mean > 0.38  # for comparison: a mean would have been dragged up


def test_single_outlier_day_barely_moves_the_pv_bias_median(make_coordinator):
    coordinator = make_coordinator({})
    # Six sunny days with ratio ~1.0, one cloudy day with ratio 0.2.
    coordinator.pv_hourly_bias_history[12] = [
        1.02, 0.98, 1.0, 1.01, 0.99, 1.0, 0.2,
    ]

    median = coordinator.learned_pv_hourly_ratio(12)
    mean = sum(coordinator.pv_hourly_bias_history[12]) / 7

    assert median == 1.0
    assert mean < 0.9  # for comparison: a mean would have dropped noticeably


def test_genuine_sustained_change_still_comes_through_in_the_median(make_coordinator):
    """A real behaviour change (not a one-off) - once a majority of the
    7-day window reflects it, the median moves too, just a few days
    later than a mean would have."""
    coordinator = make_coordinator({})
    # 3 old low days, then 4 new consistently higher days (majority).
    coordinator.hourly_consumption_profile[14] = [
        0.30, 0.30, 0.30, 0.60, 0.60, 0.60, 0.60,
    ]

    assert coordinator.learned_hourly_avg_kw(14) == 0.60


def test_change_not_yet_a_majority_does_not_move_the_median(make_coordinator):
    """Only 3 of 7 days reflect a new level - not yet a majority, so the
    median stays at the old level (unlike a mean, which would already
    have shifted partway)."""
    coordinator = make_coordinator({})
    coordinator.hourly_consumption_profile[14] = [
        0.30, 0.30, 0.30, 0.30, 0.60, 0.60, 0.60,
    ]

    assert coordinator.learned_hourly_avg_kw(14) == 0.30


def test_previous_hourly_avg_kw_uses_median_too(make_coordinator):
    """The 'previous vs current' trend comparison must use the same
    aggregation as the current value, or the two aren't apples-to-apples."""
    coordinator = make_coordinator({})
    coordinator.hourly_consumption_profile[9] = [
        0.30, 0.31, 0.29, 0.30, 0.32, 0.30, 0.90,
    ]

    assert coordinator.previous_hourly_avg_kw(9) == 0.30


def test_night_consumption_outlier_barely_moves_the_median(make_coordinator):
    """v0.63.10: the legacy night-consumption fallback was missed in the
    v0.62.0 switch to median - reproduces the exact field scenario from a
    diagnostics export (mean was pulled to 0.531 kW, roughly double what
    6 of 7 tracked nights actually looked like, by a single 2.121 kW
    outlier night)."""
    coordinator = make_coordinator({})
    coordinator.night_consumption_history = [
        0.407, 0.274, 0.217, 0.166, 0.254, 0.276, 2.121,
    ]

    median = coordinator.learned_night_consumption_kw
    mean = sum(coordinator.night_consumption_history) / 7

    assert median == 0.274
    assert mean > 0.5  # for comparison: the old (buggy) mean behaviour


def test_battery_efficiency_outlier_barely_moves_the_median(make_coordinator):
    """Same fix, same rationale, for learned_battery_efficiency_percent -
    a single noisy charge/discharge cycle shouldn't meaningfully move a
    value that directly scales the safety-critical reserve calculation."""
    coordinator = make_coordinator({})
    coordinator.learned_efficiency_history = [
        93.3, 93.6, 84.9, 84.7, 92.0, 92.9, 75.9,
    ]

    median = coordinator.learned_battery_efficiency_percent
    mean = sum(coordinator.learned_efficiency_history) / 7

    assert median == 92.0
    assert abs(median - mean) > 3  # the outlier meaningfully drags the mean down
