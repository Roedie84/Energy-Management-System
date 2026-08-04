"""The dashboard's plain-language explanation text (v0.61.0) now states
*why* a quarter did or didn't qualify as expensive - price vs. threshold,
whether low solar narrowed the threshold, whether winter-guard suppressed
a sale, and whether an 'expensive_quarter_soc_protected' outcome was
actually a SoC protection or a price-priority hold-off (previously always
worded as SoC protection, even when the real cause was something else -
reported as confusing/misleading after v0.60.0 added the distinction as
a coordinator field but not yet in the explanation text).
"""


def test_default_smart_explains_price_vs_threshold(make_coordinator):
    coordinator = make_coordinator({})
    coordinator.last_reason = "default_smart"
    coordinator.last_has_enough_energy = True
    coordinator.last_current_price_per_kwh = 0.339
    coordinator.last_expensive_price_threshold = 0.378
    coordinator.last_low_solar_narrowed_threshold = False

    text = coordinator._build_explanation()

    assert "0.339" in text or "0,339" in text
    assert "0.378" in text or "0,378" in text
    assert "niet" in text  # doesn't clear the threshold


def test_default_smart_mentions_low_solar_narrowing(make_coordinator):
    coordinator = make_coordinator({})
    coordinator.last_reason = "default_smart"
    coordinator.last_has_enough_energy = True
    coordinator.last_current_price_per_kwh = 0.339
    coordinator.last_expensive_price_threshold = 0.42
    coordinator.last_low_solar_narrowed_threshold = True

    text = coordinator._build_explanation()

    assert "weinig zon" in text


def test_default_smart_mentions_winter_guard_suppression(make_coordinator):
    coordinator = make_coordinator({})
    coordinator.last_reason = "default_smart"
    coordinator.last_has_enough_energy = True
    coordinator.last_current_price_per_kwh = 0.339
    coordinator.last_expensive_price_threshold = 0.378
    coordinator.last_winter_guard_suppressed_today = True

    text = coordinator._build_explanation()

    assert "winter-guard" in text or "netgeladen" in text or "bijgeladen" in text


def test_default_smart_falls_back_without_threshold_data(make_coordinator):
    """No price spread today (threshold is None) - still gives a
    sensible generic explanation instead of crashing or showing 'None'."""
    coordinator = make_coordinator({})
    coordinator.last_reason = "default_smart"
    coordinator.last_has_enough_energy = True
    coordinator.last_current_price_per_kwh = 0.30
    coordinator.last_expensive_price_threshold = None

    text = coordinator._build_explanation()

    assert "None" not in text
    assert "speciale reden" in text


def test_soc_protected_distinguishes_price_priority_from_real_soc_protection(
    make_coordinator,
):
    coordinator = make_coordinator({})
    coordinator.last_reason = "expensive_quarter_soc_protected"
    coordinator.last_price_priority_held_off = True
    coordinator.last_soc_percent = 80.0  # ample SoC - not actually the issue

    text = coordinator._build_explanation()

    assert "prijs-prioriteit" in text
    assert "SoC" not in text or "accu-SoC" not in text  # doesn't wrongly blame SoC


def test_soc_protected_still_explains_genuine_soc_protection(make_coordinator):
    coordinator = make_coordinator({})
    coordinator.last_reason = "expensive_quarter_soc_protected"
    coordinator.last_price_priority_held_off = False
    coordinator.last_soc_percent = 12.0

    text = coordinator._build_explanation()

    assert "12" in text
    assert "prijs-prioriteit" not in text


def test_expensive_quarter_mentions_secondary_tier(make_coordinator):
    coordinator = make_coordinator({})
    coordinator.last_reason = "expensive_quarter"
    coordinator.last_expensive_tier = "secondary"
    coordinator.last_discharge_power_applied = 1600.0

    text = coordinator._build_explanation()

    assert "secundaire" in text


def test_expensive_quarter_mentions_household_floor_when_applied(make_coordinator):
    coordinator = make_coordinator({})
    coordinator.last_reason = "expensive_quarter"
    coordinator.last_expensive_tier = "primary"
    coordinator.last_discharge_power_applied = 340.0
    coordinator.last_household_load_w = 340.0
    coordinator.last_discharge_floor_applied = True

    text = coordinator._build_explanation()

    assert "340" in text
