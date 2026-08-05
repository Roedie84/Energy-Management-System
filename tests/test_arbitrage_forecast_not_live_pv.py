"""Arbitrage/solar-capture decisions now prefer the Solcast-based
expected PV power over the raw live reading (v0.63.71, requested:
"hij kijkt naar het live PV opbrengst en niet naar de verwachtte
zon"). Reported: a passing cloud momentarily dipped the live PV
reading (2668W -> 1707W within 7 minutes), flip-flopping the decision
between smart and manual mode every few minutes.
"""
from datetime import datetime, timedelta, timezone

from conftest import make_price_forecast

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _price_fn_cheap_now_expensive_later(hour, minute):
    if hour < 14:
        return 2_170_000  # 0.217 EUR/kWh - "now"
    if 19 <= hour < 22:
        return 3_900_000  # 0.39 EUR/kWh - later tonight
    return 2_500_000


def _base_config(**overrides):
    config = {
        "price_sensor_entity": "sensor.price",
        "price_attribute": "price_tax_included",
        "operation_select_entity": "select.op",
        "manual_power_number_entity": "number.pow",
        "manual_discharge_power": 1600,
        "manual_charge_power": -2000,
        "available_energy_sensor_entity": "sensor.available_energy",
        "consumption_power_sensor_entity": "sensor.p1",
        "pv_power_sensor_entity": "sensor.pv",
        "solar_forecast_sensor_entity": "sensor.solcast",
    }
    config.update(overrides)
    return config


def with_now(coordinator, when: datetime) -> None:
    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: when


def _detailed_forecast_at(now, pv_estimate_kw, duration_minutes=30):
    """A few half-hour-aligned forecast entries covering `now`, so
    _get_pv_forecast_entries can infer interval durations."""
    interval_start = now.replace(
        minute=0 if now.minute < 30 else 30, second=0, microsecond=0
    )
    return [
        {
            "period_start": interval_start - timedelta(minutes=duration_minutes),
            "pv_estimate": pv_estimate_kw,
        },
        {"period_start": interval_start, "pv_estimate": pv_estimate_kw},
        {
            "period_start": interval_start + timedelta(minutes=duration_minutes),
            "pv_estimate": pv_estimate_kw,
        },
    ]


def test_get_expected_pv_power_reads_the_current_interval(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    now = DAY0.replace(hour=13, minute=10)
    hass.states.set(
        "sensor.solcast",
        "0",
        {"detailedForecast": _detailed_forecast_at(now, pv_estimate_kw=2.5)},
    )

    result = coordinator._get_expected_pv_power_w(now)

    assert result == 2500.0


def test_get_expected_pv_power_applies_learned_bias(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    now = DAY0.replace(hour=13, minute=10)
    hass.states.set(
        "sensor.solcast",
        "0",
        {"detailedForecast": _detailed_forecast_at(now, pv_estimate_kw=2.0)},
    )
    # Solcast systematically under-forecasts this hour by learned ratio 1.2.
    coordinator.pv_hourly_bias_history[13] = [1.2, 1.2, 1.2]

    result = coordinator._get_expected_pv_power_w(now)

    assert result == 2400.0


def test_get_expected_pv_power_none_without_forecast_sensor(make_coordinator, hass):
    coordinator = make_coordinator(_base_config(solar_forecast_sensor_entity=None))

    result = coordinator._get_expected_pv_power_w(DAY0.replace(hour=13))

    assert result is None


def test_arbitrage_uses_forecast_not_live_reading(make_coordinator, hass):
    """The core regression: a live PV dip must NOT flip the decision
    when the Solcast forecast still shows a comfortable surplus."""
    forecast = make_price_forecast(DAY0, _price_fn_cheap_now_expensive_later)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    coordinator = make_coordinator(_base_config())
    coordinator.learned_efficiency_history = [88.2] * 7

    now = DAY0.replace(hour=15, minute=30)
    # A cloud passed: live PV genuinely dipped to 300W, so the true
    # household load (200W) is now barely covered, netting a small
    # 100W export on the P1 meter (200W load - 300W live PV = -100W).
    hass.states.set("sensor.pv", "300")
    hass.states.set("sensor.p1", "-100")
    hass.states.set("sensor.available_energy", "8.0")
    # ...but the Solcast forecast for this exact half-hour still expects
    # a healthy 2.5kW - comfortably above the 2000W target, since a
    # brief cloud doesn't change the half-hour's average estimate.
    hass.states.set(
        "sensor.solcast",
        "0",
        {"detailedForecast": _detailed_forecast_at(now, pv_estimate_kw=2.5)},
    )

    with_now(coordinator, now)
    entries = coordinator._get_forecast_entries()
    coordinator.last_current_price_per_kwh = 0.217

    result = coordinator._get_arbitrage_charge_power(
        entries, now, should_postpone_charging=False
    )

    # Forecast (2500W) - true household load (200W) = 2300W surplus,
    # comfortably above the 2000W target - no grid purchase needed,
    # unlike what the noisy, dipped live reading (300W, only a 0W
    # surplus once corrected) would have implied.
    assert result is None
    assert coordinator.last_arbitrage_solar_surplus_w == 2300.0


def test_arbitrage_falls_back_to_live_reading_without_forecast(make_coordinator, hass):
    """No solar forecast sensor configured at all - must still fall
    back to the live reading, exactly like before this change."""
    forecast = make_price_forecast(DAY0, _price_fn_cheap_now_expensive_later)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "-800")
    hass.states.set("sensor.available_energy", "8.0")
    coordinator = make_coordinator(_base_config(solar_forecast_sensor_entity=None))
    coordinator.learned_efficiency_history = [88.2] * 7

    now = DAY0.replace(hour=15, minute=30)
    hass.states.set("sensor.pv", "800")  # 800W surplus, target is 2000W

    with_now(coordinator, now)
    entries = coordinator._get_forecast_entries()
    coordinator.last_current_price_per_kwh = 0.217

    result = coordinator._get_arbitrage_charge_power(
        entries, now, should_postpone_charging=False
    )

    # v0.63.72: commands the full 2000W target (hardware combines solar
    # + grid automatically), not just the 1200W grid gap.
    assert result == 2000.0
    assert coordinator.last_arbitrage_solar_surplus_w == 800.0
    assert coordinator.last_arbitrage_grid_power_w == 1200.0
