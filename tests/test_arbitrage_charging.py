"""Arbitrage charging (v0.63.15): actively buy from the grid during a
cheap quarter specifically because a known, more expensive quarter is
still coming later today, when the projected net return (after
round-trip efficiency losses) clears a minimum margin. Solar-first:
only tops up the gap between the desired charge rate and live PV
surplus, so it doesn't compete with the existing smart-mode solar
self-consumption.

Reported field scenario: 21ct now, ~36-39ct later this evening, with
88.2% learned efficiency - clearing the margin easily
(0.882 * 0.39 - 0.217 = ~0.127 EUR/kWh profit).
"""
import asyncio
from datetime import datetime, timezone

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
    }
    config.update(overrides)
    return config


def with_now(coordinator, when: datetime) -> None:
    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: when


def _make_ready_coordinator(make_coordinator, hass, **config_overrides):
    forecast = make_price_forecast(DAY0, _price_fn_cheap_now_expensive_later)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "200")
    hass.states.set("sensor.available_energy", "8.0")  # plenty - not the reason
    coordinator = make_coordinator(_base_config(**config_overrides))
    coordinator.learned_efficiency_history = [88.2] * 7
    return coordinator


def test_no_arbitrage_when_disabled(make_coordinator, hass):
    coordinator = _make_ready_coordinator(make_coordinator, hass)
    coordinator.arbitrage_charging_enabled = False

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason != "arbitrage_charging"


def test_arbitrage_charges_when_profitable_and_enabled(make_coordinator, hass):
    coordinator = _make_ready_coordinator(make_coordinator, hass)
    coordinator.arbitrage_charging_enabled = True

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason == "arbitrage_charging"
    assert coordinator.last_charge_power_applied == -2000.0
    assert coordinator.last_arbitrage_margin_eur_per_kwh > 0.03


def test_no_arbitrage_when_margin_too_small(make_coordinator, hass):
    """Same-ish prices all day (tiny spread) - the round-trip loss eats
    any theoretical margin, shouldn't trigger."""
    def flat_price(hour, minute):
        return 2_500_000

    forecast = make_price_forecast(DAY0, flat_price)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "200")
    hass.states.set("sensor.available_energy", "8.0")

    coordinator = make_coordinator(_base_config())
    coordinator.learned_efficiency_history = [88.2] * 7
    coordinator.arbitrage_charging_enabled = True

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason != "arbitrage_charging"


def test_solar_surplus_fully_covers_target_no_grid_purchase(make_coordinator, hass):
    """Solar-first (reported): if live PV surplus already covers the
    desired charge rate, arbitrage must NOT force manual mode - let the
    existing smart-mode solar self-consumption handle it."""
    coordinator = _make_ready_coordinator(
        make_coordinator, hass, pv_power_sensor_entity="sensor.pv"
    )
    # True household consumption stays at the 200W baseline; with 2500W
    # solar, the P1 meter would show a ~2300W export.
    hass.states.set("sensor.p1", "-2300")
    hass.states.set("sensor.pv", "2500")  # comfortably above the 2000W target
    coordinator.arbitrage_charging_enabled = True

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason != "arbitrage_charging"
    assert coordinator.last_arbitrage_grid_power_w == 0.0


def test_solar_surplus_partially_covers_only_buys_the_gap(make_coordinator, hass):
    coordinator = _make_ready_coordinator(
        make_coordinator, hass, pv_power_sensor_entity="sensor.pv"
    )
    # Zero baseline consumption + 800W solar -> P1 shows an 800W export.
    hass.states.set("sensor.p1", "-800")
    hass.states.set("sensor.pv", "800")  # 800W surplus, target is 2000W
    coordinator.arbitrage_charging_enabled = True

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason == "arbitrage_charging"
    # 2000W target - 800W solar surplus = 1200W from the grid
    assert coordinator.last_charge_power_applied == -1200.0


def test_arbitrage_does_not_set_grid_charged_today_flag(make_coordinator, hass):
    """Must not trigger the winter guard - that would suppress the very
    sale this purchase was made for."""
    coordinator = _make_ready_coordinator(make_coordinator, hass)
    coordinator.arbitrage_charging_enabled = True

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason == "arbitrage_charging"
    assert coordinator._grid_charged_today is False


def test_arbitrage_overrides_postpone_charging(make_coordinator, hass):
    """Reported scenario: there's already enough available energy to
    bridge to the cheap block (which would otherwise mean
    smart_discharging/postpone) - arbitrage should still fire when
    profitable, since 'enough to bridge' and 'profitable to buy more'
    are independent questions."""
    coordinator = _make_ready_coordinator(make_coordinator, hass)
    coordinator.hourly_consumption_profile = {h: [0.3] for h in range(24)}
    coordinator.arbitrage_charging_enabled = True

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason == "arbitrage_charging"


def test_no_arbitrage_without_more_price_data_today(make_coordinator, hass):
    """No remaining price data today at all (edge case, e.g. very end of
    day with nothing left to compare against) - must not crash, must
    not trigger."""
    coordinator = _make_ready_coordinator(make_coordinator, hass)
    coordinator.arbitrage_charging_enabled = True

    with_now(coordinator, DAY0.replace(hour=23, minute=59))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason != "arbitrage_charging"
