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
    coordinator.last_used_soc_taper_fallback = True
    coordinator.last_soc_percent = 12.0

    text = coordinator._build_explanation()

    assert "12" in text
    assert "prijs-prioriteit" not in text


def test_soc_protected_explains_reserve_exhaustion_not_soc(make_coordinator):
    """v0.63.20: with the dynamic reserve branch (not the flat SoC-taper
    fallback), the real cause is the reserve calculation leaving no
    room - not a literally-low SoC (reported: 88% SoC labelled as 'too
    low', which is misleading at that level)."""
    coordinator = make_coordinator({})
    coordinator.last_reason = "expensive_quarter_soc_protected"
    coordinator.last_price_priority_held_off = False
    coordinator.last_used_soc_taper_fallback = False
    coordinator.last_soc_percent = 88.0
    coordinator.last_available_kwh = 6.83

    text = coordinator._build_explanation()

    assert "nachtreserve" in text
    assert "6.83" in text
    assert "accu-SoC" not in text


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


def test_breakdown_table_shown_for_reasons_other_than_discharging_window(
    make_coordinator,
):
    """v0.63.22: reported that the diepste-tekort-breakdown table only
    ever showed up for discharging_window, even though the underlying
    data (last_needed_kwh_breakdown) is computed fresh every tick
    regardless of which reason ultimately fires - purely a text-building
    gap, now shown for every reason where the data exists."""
    coordinator = make_coordinator({})
    coordinator.last_reason = "expensive_quarter"
    coordinator.last_expensive_tier = "primary"
    coordinator.last_discharge_power_applied = 1600.0
    coordinator.last_needed_kwh_breakdown = {
        "basisverbruik_kwh": 3.719,
        "verwachte_pv_kwh": 1.652,
        "diepste_tekort_kwh": 3.719,
        "veiligheidsmarge_procent": 15.0,
    }

    text = coordinator._build_explanation()

    assert "| Onderdeel | Waarde |" in text
    assert "3.719 kWh" in text


def test_no_breakdown_table_without_data(make_coordinator):
    coordinator = make_coordinator({})
    coordinator.last_reason = "negative_price"
    coordinator.last_charge_power_applied = -2000.0
    coordinator.last_needed_kwh_breakdown = {}

    text = coordinator._build_explanation()

    assert "Onderdeel" not in text


def test_discharging_window_shows_breakdown_as_a_markdown_table(make_coordinator, monkeypatch):
    """v0.61.2: the vague 'over de hele periode' prose is replaced by an
    actual table, with the exact period (start, end, duration) spelled
    out - reported as confusing since the numbers only made sense after
    manually reconstructing the period length by hand."""
    import custom_components.energy_management_system.coordinator as coord_mod
    from datetime import datetime, timedelta, timezone

    coordinator = make_coordinator({})
    coordinator.last_reason = "discharging_window"
    coordinator.last_has_enough_energy = True
    coordinator.last_available_kwh = 1.47
    coordinator.last_needed_kwh_to_bridge = 0.0
    now = datetime(2026, 8, 4, 8, 32, 41, tzinfo=timezone.utc)
    coordinator.last_cheap_block_start = now + timedelta(hours=2, minutes=57)
    coordinator.last_needed_kwh_breakdown_end_time = coordinator.last_cheap_block_start
    coordinator.last_needed_kwh_breakdown = {
        "basisverbruik_kwh": 1.415,
        "verwachte_pv_kwh": 3.805,
        "diepste_tekort_kwh": 0.0,
        "veiligheidsmarge_procent": 15.0,
    }
    monkeypatch.setattr(coord_mod.dt_util, "now", lambda: now)

    text = coordinator._build_explanation()

    assert "| Onderdeel | Waarde |" in text
    assert "|---|---|" in text
    assert "| Periode |" in text
    assert "2u57m" in text
    assert "1.415 kWh" in text
    assert "3.805 kWh" in text
    assert "+15.0%" in text
    # No blank line between the header, separator, and rows.
    lines = text.split("\n")
    table_start = lines.index("| Onderdeel | Waarde |")
    assert lines[table_start + 1] == "|---|---|"
    assert lines[table_start + 2].startswith("| Periode |")


def test_default_smart_not_enough_energy_shows_breakdown_table(make_coordinator, monkeypatch):
    import custom_components.energy_management_system.coordinator as coord_mod
    from datetime import datetime, timezone

    coordinator = make_coordinator({})
    coordinator.last_reason = "default_smart"
    coordinator.last_has_enough_energy = False
    coordinator.last_available_kwh = 0.5
    coordinator.last_needed_kwh_to_bridge = 2.0
    coordinator.last_cheap_block_start = None
    coordinator.last_needed_kwh_breakdown = {
        "basisverbruik_kwh": 2.0,
        "verwachte_pv_kwh": 0.0,
        "diepste_tekort_kwh": 2.0,
        "veiligheidsmarge_procent": 15.0,
    }
    monkeypatch.setattr(
        coord_mod.dt_util,
        "now",
        lambda: datetime(2026, 8, 4, 23, 0, 0, tzinfo=timezone.utc),
    )

    text = coordinator._build_explanation()

    assert "| Onderdeel | Waarde |" in text
    assert "onbekend" in text  # no cheap_block_start -> period unknown


def test_arbitrage_solar_capture_has_a_real_explanation(make_coordinator):
    """v0.63.66, reported: 'Onbekende reden: arbitrage_solar_capture' -
    this reason label (introduced in v0.63.60) was never wired into the
    explanation-text generator, so it fell through to the generic
    unknown-reason fallback instead of explaining what actually
    happened."""
    coordinator = make_coordinator({})
    coordinator.last_reason = "arbitrage_solar_capture"
    coordinator.last_arbitrage_solar_surplus_w = 1033.0

    text = coordinator._build_explanation()

    assert "onbekende reden" not in text.lower()
    assert "1033" in text
    assert "smart" in text.lower()
