"""The capacity-expectations breakdown table must always be available
for the explanation card, regardless of reason or of whether
_should_postpone_charging's own narrow "before the cheap block" scope
was reached (v0.63.76, requested: "ik wil daarom ook altijd de tabel
zien").

Reported: with should_postpone_charging genuinely False (arbitrage_
charging fired due to insufficient reserve), the breakdown table was
completely missing from the explanation card - _should_postpone_
charging only ever populated it inside its own "now < cheap_block_
start" scope.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from conftest import make_price_forecast

DAY0 = datetime(2026, 8, 5, tzinfo=timezone.utc)


def _price_fn_cheap_now_expensive_later(hour, minute):
    if hour < 16:
        return 1_300_000
    return 3_900_000


def with_now(coordinator, when: datetime) -> None:
    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: when


def test_breakdown_populated_when_arbitrage_charging_fires(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _price_fn_cheap_now_expensive_later)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "200")
    hass.states.set("sensor.available_energy", "0.5")  # genuinely low

    coordinator = make_coordinator(
        {
            "price_sensor_entity": "sensor.price",
            "price_attribute": "price_tax_included",
            "operation_select_entity": "select.op",
            "manual_power_number_entity": "number.pow",
            "manual_discharge_power": 1600,
            "manual_charge_power": -2000,
            "available_energy_sensor_entity": "sensor.available_energy",
            "consumption_power_sensor_entity": "sensor.p1",
        }
    )
    coordinator.learned_efficiency_history = [88.2] * 7
    coordinator.hourly_consumption_profile = {h: [0.3] for h in range(24)}

    with_now(coordinator, DAY0.replace(hour=15, minute=30))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason == "arbitrage_charging"
    assert coordinator.last_needed_kwh_breakdown != {}
    assert "Onderdeel" in coordinator.last_explanation


def test_breakdown_uses_24h_fallback_when_no_cheap_block_ahead(
    make_coordinator, hass
):
    """When _should_postpone_charging never even reaches its own "now <
    cheap_block_start" scope (e.g. cheap_block_start is None or already
    passed), the display breakdown must still compute something
    meaningful using a 24h outlook, rather than staying empty."""
    coordinator = make_coordinator({})
    now = DAY0.replace(hour=12, minute=0)

    coordinator._update_needed_kwh_breakdown_for_display(now, None)

    assert coordinator.last_needed_kwh_breakdown_end_time == now + timedelta(hours=24)


def test_breakdown_uses_cheap_block_start_when_meaningfully_ahead(
    make_coordinator, hass
):
    coordinator = make_coordinator({})
    now = DAY0.replace(hour=12, minute=0)
    cheap_block_start = now + timedelta(hours=3)

    coordinator._update_needed_kwh_breakdown_for_display(now, cheap_block_start)

    assert coordinator.last_needed_kwh_breakdown_end_time == cheap_block_start


def test_breakdown_falls_back_when_cheap_block_start_already_passed(
    make_coordinator, hass
):
    coordinator = make_coordinator({})
    now = DAY0.replace(hour=12, minute=0)
    cheap_block_start = now - timedelta(hours=2)  # already in the past

    coordinator._update_needed_kwh_breakdown_for_display(now, cheap_block_start)

    assert coordinator.last_needed_kwh_breakdown_end_time == now + timedelta(hours=24)


def test_period_text_matches_the_end_time_actually_used(make_coordinator, hass):
    import custom_components.energy_management_system.coordinator as coord_mod

    coordinator = make_coordinator({})
    now = DAY0.replace(hour=12, minute=0)
    coordinator.hourly_consumption_profile = {h: [0.3] for h in range(24)}
    coord_mod.dt_util.now = lambda: now

    coordinator._update_needed_kwh_breakdown_for_display(now, None)
    text = coordinator._build_needed_kwh_breakdown_table()

    assert "24u00m" in text
