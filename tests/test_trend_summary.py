"""Gedeelde trend-samenvatting (v0.63.88, gevraagd: inzicht of nieuwe
modellen/parameters nauwkeuriger/stabieler worden over tijd) - een
kleinste-kwadraten-regressielijn door een korte tijdreeks, gebruikt
door meerdere nieuwe metrics (spreidingsgebaseerde fractie, extra-dip-
marge, temperatuur-regressie-nauwkeurigheid).
"""


def test_too_few_points_returns_none(make_coordinator, hass):
    coordinator = make_coordinator({})

    assert coordinator._compute_trend_summary([1.0, 2.0]) is None


def test_flat_history_is_stable(make_coordinator, hass):
    coordinator = make_coordinator({})

    result = coordinator._compute_trend_summary([10.0, 10.0, 10.0, 10.0])

    assert result["richting"] == "stabiel"


def test_clear_upward_trend_detected(make_coordinator, hass):
    coordinator = make_coordinator({})

    result = coordinator._compute_trend_summary([10.0, 12.0, 14.0, 16.0, 18.0])

    assert result["richting"] == "stijgend"
    assert result["verschil_procent"] > 5


def test_clear_downward_trend_detected(make_coordinator, hass):
    coordinator = make_coordinator({})

    result = coordinator._compute_trend_summary([18.0, 16.0, 14.0, 12.0, 10.0])

    assert result["richting"] == "dalend"
    assert result["verschil_procent"] < -5


def test_single_mid_series_outlier_does_not_flip_a_flat_trend(make_coordinator, hass):
    """A regression line is far less sensitive to a single noisy point
    in the MIDDLE of the series (low leverage there) than to the same
    kind of noise right at an endpoint (which does have high leverage
    in ordinary least squares - a well-known property, not something
    this helper tries to correct for)."""
    coordinator = make_coordinator({})

    # Flat around 10, except one noisy spike in the middle.
    history = [10.0, 10.0, 10.0, 40.0, 10.0, 10.0, 10.0]

    result = coordinator._compute_trend_summary(history)

    assert result["richting"] == "stabiel"
