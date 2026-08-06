"""Piekvermogen-tracking voor capaciteitstarieven (v0.63.101, gevraagd:
"zaken voor een typisch EMS welke we kunnen toevoegen"). Puur
informatief - stuurt niets aan. Gebruikt bewust de RUWE P1-meter-
aflezing, niet de gecorrigeerde huishoudverbruik-schatting.
"""
from datetime import datetime, timezone

DAY0 = datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc)


def _base_config(**overrides):
    config = {"consumption_power_sensor_entity": "sensor.p1"}
    config.update(overrides)
    return config


def test_tracks_the_highest_reading_today(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())

    hass.states.set("sensor.p1", "500")
    coordinator._update_peak_power_tracking(DAY0)
    hass.states.set("sensor.p1", "1200")
    coordinator._update_peak_power_tracking(DAY0)
    hass.states.set("sensor.p1", "800")
    coordinator._update_peak_power_tracking(DAY0)

    assert coordinator.peak_power_today_w == 1200


def test_negative_or_zero_readings_ignored(make_coordinator, hass):
    """Export (negative) or zero import must not count as a peak."""
    coordinator = make_coordinator(_base_config())

    hass.states.set("sensor.p1", "-300")
    coordinator._update_peak_power_tracking(DAY0)

    assert coordinator.peak_power_today_w == 0.0


def test_day_rollover_archives_yesterdays_peak(make_coordinator, hass):
    from datetime import timedelta

    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.p1", "1500")
    coordinator._update_peak_power_tracking(DAY0)

    next_day = DAY0 + timedelta(days=1)
    hass.states.set("sensor.p1", "300")
    coordinator._update_peak_power_tracking(next_day)

    assert len(coordinator.peak_power_daily_history) == 1
    assert coordinator.peak_power_daily_history[0]["peak_w"] == 1500.0
    assert coordinator.peak_power_today_w == 300


def test_month_rollover_archives_the_previous_month(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.p1", "2000")
    coordinator._update_peak_power_tracking(DAY0)

    next_month = DAY0.replace(month=9, day=1)
    hass.states.set("sensor.p1", "100")
    coordinator._update_peak_power_tracking(next_month)

    assert coordinator.peak_power_previous_month_w == 2000.0
    assert coordinator.peak_power_current_month_w == 100


def test_all_time_peak_tracks_the_highest_ever(make_coordinator, hass):
    from datetime import timedelta

    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.p1", "3000")
    coordinator._update_peak_power_tracking(DAY0)

    later = DAY0 + timedelta(days=40)  # a new month, lower reading
    hass.states.set("sensor.p1", "500")
    coordinator._update_peak_power_tracking(later)

    assert coordinator.peak_power_all_time_w == 3000
    assert coordinator.peak_power_all_time_date == DAY0.date().isoformat()


def test_history_capped_at_learning_window(make_coordinator, hass):
    from datetime import timedelta
    from custom_components.energy_management_system.const import (
        LEARNING_HISTORY_DAYS,
    )

    coordinator = make_coordinator(_base_config())
    now = DAY0
    for i in range(LEARNING_HISTORY_DAYS + 3):
        hass.states.set("sensor.p1", "500")
        coordinator._update_peak_power_tracking(now)
        now += timedelta(days=1)

    assert len(coordinator.peak_power_daily_history) == LEARNING_HISTORY_DAYS


def test_no_error_without_configured_sensor(make_coordinator, hass):
    coordinator = make_coordinator({})

    coordinator._update_peak_power_tracking(DAY0)

    assert coordinator.peak_power_today_w == 0.0
