"""Monthly summary (v0.56.0): genuine month-over-month trend, on top of
the existing rolling 7-day self-correction which only ever looks at the
recent past.
"""
from datetime import datetime, timezone


def test_first_run_sets_the_month_without_a_rollover(make_coordinator):
    coordinator = make_coordinator({})
    now = datetime(2026, 7, 15, tzinfo=timezone.utc)

    coordinator._check_monthly_rollover(now)

    assert coordinator.previous_month_discharge_value_eur is None


def test_rollover_snapshots_current_into_previous_and_resets(make_coordinator):
    coordinator = make_coordinator({})
    end_of_july = datetime(2026, 7, 31, hour=23, tzinfo=timezone.utc)
    coordinator._check_monthly_rollover(end_of_july)

    coordinator.current_month_discharge_value_eur = 45.50
    coordinator.current_month_charge_cost_eur = 12.30
    coordinator.current_month_shortfall_days = 2
    coordinator.current_month_excess_days = 5
    coordinator.current_month_days_tracked = 31

    start_of_august = datetime(2026, 8, 1, tzinfo=timezone.utc)
    coordinator._check_monthly_rollover(start_of_august)

    assert coordinator.previous_month_discharge_value_eur == 45.5
    assert coordinator.previous_month_charge_cost_eur == 12.3
    assert coordinator.previous_month_shortfall_days == 2
    assert coordinator.previous_month_excess_days == 5
    assert coordinator.previous_month_days_tracked == 31

    assert coordinator.current_month_discharge_value_eur == 0.0
    assert coordinator.current_month_charge_cost_eur == 0.0
    assert coordinator.current_month_shortfall_days == 0
    assert coordinator.current_month_excess_days == 0
    assert coordinator.current_month_days_tracked == 0


def test_no_rollover_within_the_same_month(make_coordinator):
    coordinator = make_coordinator({})
    coordinator._check_monthly_rollover(datetime(2026, 8, 1, tzinfo=timezone.utc))
    coordinator.current_month_discharge_value_eur = 20.0

    coordinator._check_monthly_rollover(datetime(2026, 8, 15, tzinfo=timezone.utc))

    assert coordinator.current_month_discharge_value_eur == 20.0
    assert coordinator.previous_month_discharge_value_eur is None


def test_financial_tracking_feeds_the_current_month_totals(make_coordinator, hass):
    from conftest import make_price_forecast

    day0 = datetime(2026, 8, 2, tzinfo=timezone.utc)
    forecast = make_price_forecast(day0, lambda h, m: 3_500_000)
    hass.states.set("sensor.price", "0", {"forecast": forecast})

    coordinator = make_coordinator(
        {"price_sensor_entity": "sensor.price", "price_attribute": "price_tax_included"}
    )
    entries = coordinator._get_forecast_entries()
    now = day0.replace(hour=19, minute=0)

    from datetime import timedelta

    coordinator._last_value_calc_time = now - timedelta(minutes=15)
    coordinator._update_financial_tracking(
        now, entries, "expensive_quarter", discharge_power_w=1600, charge_power_w=None
    )

    assert coordinator.current_month_discharge_value_eur > 0
    assert coordinator.total_discharge_value_eur == coordinator.current_month_discharge_value_eur
