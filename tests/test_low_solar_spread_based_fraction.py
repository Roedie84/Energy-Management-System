"""Spreidingsgebaseerde LOW_SOLAR_RELATIVE_FRACTION (v0.63.87, uitgebreid
besproken en ontworpen door de gebruiker).

De fractie die bepaalt of de geleerde "typische dag" als "weinig zon"
geldt was voorheen een vaste 40% - nu beweegt die mee met hoe
CONSISTENT de (bias-gecorrigeerde) voorspelling recent is gebleken,
via de standaarddeviatie van de al bestaande `deviation_history`.
"""
import statistics as _statistics

from custom_components.energy_management_system.solar_forecast import (
    SolarForecastAccuracyTracker,
)


def _make_tracker(hass, deviations):
    tracker = SolarForecastAccuracyTracker(hass, {})
    tracker.deviation_history = deviations
    return tracker


def test_deviation_stdev_none_without_enough_samples(hass):
    """Fewer than MIN_SOLAR_HISTORY_FOR_SPREAD_BASED_FRACTION valid
    samples must return None - a stdev from too few samples is itself
    unreliable."""
    tracker = _make_tracker(hass, [5.0, -3.0, 4.0])  # only 3 samples

    assert tracker.deviation_stdev_percent is None


def test_deviation_stdev_computed_with_enough_samples(hass):
    deviations = [5.0, -5.0, 5.0, -5.0, 5.0]  # 5 samples, stdev = 5.0
    tracker = _make_tracker(hass, deviations)

    expected = round(_statistics.pstdev(deviations), 1)
    assert tracker.deviation_stdev_percent == expected


def test_deviation_stdev_ignores_implausible_outliers(hass):
    """A single wildly implausible value (e.g. a leftover misconfigured
    sensor reading) must be excluded, matching learned_bias_percent's
    existing outlier handling."""
    from custom_components.energy_management_system.solar_forecast import (
        MAX_REASONABLE_DEVIATION_PERCENT,
    )

    plausible = [2.0, -2.0, 3.0, -3.0, 2.0]
    deviations = plausible + [MAX_REASONABLE_DEVIATION_PERCENT + 500]
    tracker = _make_tracker(hass, deviations)

    expected = round(_statistics.pstdev(plausible), 1)
    assert tracker.deviation_stdev_percent == expected


def test_fraction_falls_back_to_default_without_enough_history(make_coordinator, hass):
    """Without enough deviation samples, the coordinator must fall back
    to the fixed 0.4 default fraction."""
    coordinator = make_coordinator({})
    coordinator.solar_tracker = SolarForecastAccuracyTracker(hass, {})
    coordinator.solar_tracker.deviation_history = [5.0, -3.0]  # too few

    assert coordinator._get_low_solar_relative_fraction() == 0.4


def test_fraction_widens_for_consistent_forecasts(make_coordinator, hass):
    """Low spread (< 10%) - the forecast has been consistent, so the
    fraction widens to 0.6 (more trust, less caution)."""
    coordinator = make_coordinator({})
    coordinator.solar_tracker = SolarForecastAccuracyTracker(hass, {})
    # Low spread: all deviations close together.
    coordinator.solar_tracker.deviation_history = [2.0, 3.0, 2.5, 3.5, 2.0]

    assert coordinator._get_low_solar_relative_fraction() == 0.6


def test_fraction_narrows_for_unreliable_forecasts(make_coordinator, hass):
    """High spread (> 25%) - the forecast has been unreliable, so the
    fraction narrows to 0.3 (more caution)."""
    coordinator = make_coordinator({})
    coordinator.solar_tracker = SolarForecastAccuracyTracker(hass, {})
    # High spread: deviations swing wildly.
    coordinator.solar_tracker.deviation_history = [40.0, -35.0, 30.0, -40.0, 35.0]

    assert coordinator._get_low_solar_relative_fraction() == 0.3


def test_fraction_stays_default_for_moderate_spread(make_coordinator, hass):
    """Spread between 10% and 25% - keeps the existing, cautious 0.4
    default."""
    coordinator = make_coordinator({})
    coordinator.solar_tracker = SolarForecastAccuracyTracker(hass, {})
    coordinator.solar_tracker.deviation_history = [15.0, -15.0, 15.0, -15.0, 15.0]

    assert coordinator._get_low_solar_relative_fraction() == 0.4


def test_low_solar_expected_uses_the_dynamic_fraction(make_coordinator, hass):
    """End-to-end: a consistent forecast history widens the fraction,
    which can change whether a given forecast value counts as "low"
    compared to the fixed 40% baseline."""
    coordinator = make_coordinator({})
    coordinator.solar_tracker = SolarForecastAccuracyTracker(hass, {})
    coordinator.solar_tracker.deviation_history = [2.0, 3.0, 2.5, 3.5, 2.0]
    coordinator.solar_tracker.forecast_value_history = [10.0, 10.0, 10.0]

    # learned_typical_kwh = 10.0, fraction = 0.6 -> threshold = 6.0 kWh
    assert coordinator._is_forecast_value_low(6.5) is False  # above 6.0
    assert coordinator._is_forecast_value_low(5.5) is True  # below 6.0
