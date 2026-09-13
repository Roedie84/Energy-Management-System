"""Unified reserve_daily_records structuur (v0.63.91, gevonden tijdens
een diagnostiek-review): shortfall/excess-tracking was voorheen vier
losse lijsten (history/dates per stuk) - nu één atomisch bijgewerkte
lijst van dag-records, met de oude vier namen als afgeleide, read-only
properties voor achterwaartse compatibiliteit.
"""
from datetime import datetime, timezone

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def test_derived_properties_reflect_the_unified_records(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.reserve_daily_records = [
        {"date": "2026-08-01", "shortfall": False, "excess": True},
        {"date": "2026-08-02", "shortfall": True, "excess": False},
    ]

    assert coordinator.reserve_shortfall_history == [False, True]
    assert coordinator.reserve_shortfall_dates == ["2026-08-01", "2026-08-02"]
    assert coordinator.reserve_excess_history == [True, False]
    assert coordinator.reserve_excess_dates == ["2026-08-01", "2026-08-02"]


def test_update_shortfall_detection_appends_one_atomic_record(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._shortfall_check_date = DAY0.date()
    coordinator._shortfall_detected_today = True
    coordinator._excess_detected_today = False

    next_day = DAY0.replace(day=5)
    coordinator._update_shortfall_detection(
        next_day, reason="default_smart", available_kwh=None, needed_kwh=None
    )

    assert len(coordinator.reserve_daily_records) == 1
    record = coordinator.reserve_daily_records[0]
    assert record["date"] == DAY0.date().isoformat()
    assert record["shortfall"] is True
    assert record["excess"] is False


def test_history_capped_at_learning_window(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        LEARNING_HISTORY_DAYS,
    )
    from datetime import timedelta

    coordinator = make_coordinator({})
    coordinator._shortfall_check_date = DAY0.date()
    for i in range(LEARNING_HISTORY_DAYS + 3):
        coordinator._update_shortfall_detection(
            DAY0 + timedelta(days=i + 1),
            reason="default_smart",
            available_kwh=None,
            needed_kwh=None,
        )

    assert len(coordinator.reserve_daily_records) == LEARNING_HISTORY_DAYS


def test_merge_reserve_daily_records_first_restore_defaults_other_field(
    make_coordinator, hass
):
    """When only one sensor's data has restored so far, the field it
    doesn't own must default to False, not error or stay missing."""
    from custom_components.energy_management_system.sensor import (
        _merge_reserve_daily_records,
    )

    result = _merge_reserve_daily_records(
        existing_records=[],
        dates=["2026-08-01", "2026-08-02"],
        shortfall_values=[False, True],
    )

    assert result == [
        {"date": "2026-08-01", "shortfall": False, "excess": False},
        {"date": "2026-08-02", "shortfall": True, "excess": False},
    ]


def test_merge_reserve_daily_records_second_restore_fills_in_without_overwriting(
    make_coordinator, hass
):
    """The second sensor's restore must merge into what the first
    already restored, not overwrite/duplicate it - regardless of which
    sensor happens to restore first (HA doesn't guarantee the order)."""
    from custom_components.energy_management_system.sensor import (
        _merge_reserve_daily_records,
    )

    after_first = _merge_reserve_daily_records(
        existing_records=[],
        dates=["2026-08-01", "2026-08-02"],
        shortfall_values=[False, True],
    )
    after_second = _merge_reserve_daily_records(
        after_first,
        dates=["2026-08-01", "2026-08-02"],
        excess_values=[True, False],
    )

    assert after_second == [
        {"date": "2026-08-01", "shortfall": False, "excess": True},
        {"date": "2026-08-02", "shortfall": True, "excess": False},
    ]


def test_merge_reserve_daily_records_works_regardless_of_restore_order(
    make_coordinator, hass
):
    """Restoring excess first, then shortfall, must produce the exact
    same merged result as the reverse order."""
    from custom_components.energy_management_system.sensor import (
        _merge_reserve_daily_records,
    )

    after_first = _merge_reserve_daily_records(
        existing_records=[],
        dates=["2026-08-01", "2026-08-02"],
        excess_values=[True, False],
    )
    after_second = _merge_reserve_daily_records(
        after_first,
        dates=["2026-08-01", "2026-08-02"],
        shortfall_values=[False, True],
    )

    assert after_second == [
        {"date": "2026-08-01", "shortfall": False, "excess": True},
        {"date": "2026-08-02", "shortfall": True, "excess": False},
    ]
