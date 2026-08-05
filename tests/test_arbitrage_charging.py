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


def test_no_arbitrage_without_a_profitable_margin_and_no_switch_needed(
    make_coordinator, hass
):
    """v0.63.65, requested ('ik denk dat arbitrage er helemaal uit
    kan'): there's no separate enable/disable switch any more - the
    margin check itself is what decides whether this fires, always
    active by default. A flat/no-margin price shape should still not
    trigger arbitrage, with no switch involved at all."""
    coordinator = make_coordinator(
        _base_config(price_sensor_entity="sensor.price")
    )
    forecast = make_price_forecast(DAY0, lambda hour, minute: 2_500_000)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "200")
    hass.states.set("sensor.available_energy", "8.0")

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason != "arbitrage_charging"


def test_no_switch_entity_exists_any_more(make_coordinator, hass):
    """v0.63.65, requested ('ik denk dat arbitrage er helemaal uit
    kan') - the ArbitrageChargingSwitch entity has been removed
    entirely; this is standard behaviour now, not a toggle."""
    from custom_components.energy_management_system import switch as switch_mod

    assert not hasattr(switch_mod, "ArbitrageChargingSwitch")


def test_arbitrage_charges_when_profitable_and_enabled(make_coordinator, hass):
    coordinator = _make_ready_coordinator(make_coordinator, hass)

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason == "arbitrage_charging"
    assert coordinator.last_charge_power_applied == -2000.0
    assert coordinator.last_arbitrage_margin_eur_per_kwh > 0.03


def test_reported_scenario_small_grid_gap_still_commands_full_target(
    make_coordinator, hass
):
    """v0.63.72, exact reported field scenario: 1707W solar surplus,
    2000W target, leaving only a 293W grid gap. Confirmed with the
    person that commanding just that 293W gap (the old behaviour)
    resulted in the battery charging at ONLY 293W total - wasting the
    1707W of solar instead of combining it, worse than doing nothing.
    Must command the full 2000W target instead."""
    coordinator = _make_ready_coordinator(
        make_coordinator, hass, pv_power_sensor_entity="sensor.pv"
    )
    # 1707W solar surplus (household load 0W, P1 shows a 1707W export).
    hass.states.set("sensor.p1", "-1707")
    hass.states.set("sensor.pv", "1707")

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason == "arbitrage_charging"
    assert coordinator.last_charge_power_applied == -2000.0
    assert coordinator.last_arbitrage_grid_power_w == 293.0


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

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason != "arbitrage_charging"


def test_solar_surplus_fully_covers_target_no_grid_purchase(make_coordinator, hass):
    """Solar-first (reported): if live PV surplus already covers the
    desired charge rate AND the fallback here would be OPTION_SMART
    (should_postpone_charging=False), arbitrage must NOT force manual
    mode - let the existing smart-mode solar self-consumption handle
    it."""
    coordinator = _make_ready_coordinator(
        make_coordinator, hass, pv_power_sensor_entity="sensor.pv"
    )
    # True household consumption stays at the 200W baseline; with 2500W
    # solar, the P1 meter would show a ~2300W export.
    hass.states.set("sensor.p1", "-2300")
    hass.states.set("sensor.pv", "2500")  # comfortably above the 2000W target

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason != "arbitrage_charging"
    assert coordinator.last_arbitrage_grid_power_w == 0.0


def test_solar_surplus_fully_covers_target_but_would_otherwise_be_wasted(
    make_coordinator, hass
):
    """v0.63.59/.60, reported ('accu wordt weer ingesteld op
    smart_discharging terwijl ik juist wil doorladen', daarna: 'moet
    naar smart niet naar manual'): confirmed with the person that
    smart_discharging does NOT charge from surplus solar (unlike
    OPTION_SMART) - so when the fallback here would be
    smart_discharging (should_postpone_charging=True), a solar surplus
    that fully covers the desired rate must NOT be waved off the same
    way - it would otherwise go completely unused. v0.63.60: rather
    than forcing a manual charge, this returns None (no active grid
    purchase needed - solar alone covers it) and signals via
    `_arbitrage_wants_smart_over_postpone` that the caller should use
    plain OPTION_SMART instead of OPTION_SMART_DISCHARGING, letting
    that mode's own P1-following capture the solar naturally.

    Calls `_get_arbitrage_charge_power` directly with
    should_postpone_charging=True, rather than through the full update
    cycle - isolates this specific decision from the (unrelated) worst-
    case-deficit reserve calculation that decides should_postpone_
    charging itself in production.
    """
    coordinator = _make_ready_coordinator(
        make_coordinator, hass, pv_power_sensor_entity="sensor.pv"
    )
    hass.states.set("sensor.p1", "-2300")
    hass.states.set("sensor.pv", "2500")  # comfortably above the 2000W target

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    entries = coordinator._get_forecast_entries()
    now = DAY0.replace(hour=13, minute=0)
    coordinator.last_current_price_per_kwh = 0.217  # normally set by a full tick

    result = coordinator._get_arbitrage_charge_power(
        entries, now, should_postpone_charging=True
    )

    assert result is None
    assert coordinator._arbitrage_wants_smart_over_postpone is True


def test_solar_surplus_fully_covers_target_and_smart_mode_would_capture_it(
    make_coordinator, hass
):
    """Mirror of the above with should_postpone_charging=False - the
    original solar-first deferral must still hold when the fallback is
    OPTION_SMART, which does capture solar surplus on its own."""
    coordinator = _make_ready_coordinator(
        make_coordinator, hass, pv_power_sensor_entity="sensor.pv"
    )
    hass.states.set("sensor.p1", "-2300")
    hass.states.set("sensor.pv", "2500")

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    entries = coordinator._get_forecast_entries()
    now = DAY0.replace(hour=13, minute=0)
    coordinator.last_current_price_per_kwh = 0.217

    result = coordinator._get_arbitrage_charge_power(
        entries, now, should_postpone_charging=False
    )

    assert result is None
    assert coordinator._arbitrage_wants_smart_over_postpone is False


def test_solar_surplus_partially_covers_the_full_target_is_still_commanded(
    make_coordinator, hass
):
    """v0.63.72, confirmed with the person: manual mode on this hardware
    is NOT solar-aware - commanding just the grid gap (the old
    behaviour) resulted in the battery charging at ONLY that gap total,
    wasting the solar surplus instead of combining it. Confirmed the
    fix: commanding the FULL target results in the hardware correctly
    sourcing solar first and grid for the remainder."""
    coordinator = _make_ready_coordinator(
        make_coordinator, hass, pv_power_sensor_entity="sensor.pv"
    )
    # Zero baseline consumption + 800W solar -> P1 shows an 800W export.
    hass.states.set("sensor.p1", "-800")
    hass.states.set("sensor.pv", "800")  # 800W surplus, target is 2000W

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason == "arbitrage_charging"
    # Commands the full 2000W target, not just the 1200W grid gap - the
    # hardware combines the 800W solar + 1200W grid to reach it.
    assert coordinator.last_charge_power_applied == -2000.0
    # The grid-only estimate is still tracked, just no longer commanded.
    assert coordinator.last_arbitrage_grid_power_w == 1200.0


def test_arbitrage_does_not_set_grid_charged_today_flag(make_coordinator, hass):
    """Must not trigger the winter guard - that would suppress the very
    sale this purchase was made for."""
    coordinator = _make_ready_coordinator(make_coordinator, hass)

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason == "arbitrage_charging"
    assert coordinator._grid_charged_today is False


def test_no_arbitrage_when_enough_reserve_to_bridge_the_night(make_coordinator, hass):
    """v0.63.73, explicitly stated: 'Als er voldoende capaciteit is voor
    overbruggen van de nacht ... mag de accu NIET manual gaan
    bijladen, alleen op smart'. This reverses the old v0.63.15 premise
    (previously tested by this same test under a different name/
    docstring: 'enough to bridge' and 'profitable to buy more' are
    independent questions, buy anyway) - a real grid purchase for
    profit alone, while there's already enough reserve, is no longer
    allowed at all, no matter how favourable the margin.

    Uses the same should_postpone_charging monkeypatch technique
    established in test_schedule_solar_capture_override.py - found
    there that this fixture's price/reserve combination doesn't
    reliably produce should_postpone_charging=True on its own through
    the real reserve calculation.
    """
    coordinator = _make_ready_coordinator(make_coordinator, hass)

    def fake_should_postpone(entries, now, cheap_block_start):
        return True

    coordinator._should_postpone_charging = fake_should_postpone

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason != "arbitrage_charging"


def test_arbitrage_still_fires_when_reserve_is_genuinely_insufficient(
    make_coordinator, hass
):
    """The other half of the same rule: 'Is er te weinig om de nacht te
    overbruggen dan mag hij manual bijladen' - when
    should_postpone_charging is False (genuinely not enough reserve)
    and the margin is profitable, arbitrage charging must still fire
    normally."""
    coordinator = _make_ready_coordinator(make_coordinator, hass)

    def fake_should_postpone(entries, now, cheap_block_start):
        return False

    coordinator._should_postpone_charging = fake_should_postpone

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason == "arbitrage_charging"


def test_solar_still_captured_via_smart_when_reserve_is_sufficient(
    make_coordinator, hass
):
    """Even though a grid purchase is no longer allowed when reserve is
    sufficient, existing solar surplus should still be captured via
    smart mode instead of wasted by smart_discharging - the
    v0.63.60 behaviour, now the only thing this branch ever does."""
    coordinator = _make_ready_coordinator(
        make_coordinator, hass, pv_power_sensor_entity="sensor.pv"
    )
    hass.states.set("sensor.p1", "-800")
    hass.states.set("sensor.pv", "800")

    def fake_should_postpone(entries, now, cheap_block_start):
        return True

    coordinator._should_postpone_charging = fake_should_postpone

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason == "arbitrage_solar_capture"


def test_solar_capture_signal_switches_to_smart_not_manual(make_coordinator, hass):
    """v0.63.60, reported ('moet naar smart niet naar manual'): when
    _get_arbitrage_charge_power signals _arbitrage_wants_smart_over_
    postpone (solar surplus would otherwise be wasted under
    smart_discharging), the full decision tick must apply OPTION_SMART
    - not force a manual charge - with a distinct reason label.

    Monkeypatches both _should_postpone_charging (to force the
    should_postpone_charging=True precondition directly, rather than
    depending on a realistic reserve/cheap-block scenario that turned
    out not to reliably produce it with this fixture's price shape)
    and _get_arbitrage_charge_power (to isolate this decision-tree
    branch from the unrelated live solar-surplus arithmetic already
    covered by the unit tests above).
    """
    coordinator = _make_ready_coordinator(make_coordinator, hass)

    def fake_should_postpone(entries, now, cheap_block_start):
        return True

    def fake_get_arbitrage_charge_power(entries, now, should_postpone_charging):
        coordinator._arbitrage_wants_smart_over_postpone = should_postpone_charging
        return None

    coordinator._should_postpone_charging = fake_should_postpone
    coordinator._get_arbitrage_charge_power = fake_get_arbitrage_charge_power

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason == "arbitrage_solar_capture"
    apply_operation_calls = [
        c for c in hass.services.calls if c[0] == "select" and c[1] == "select_option"
    ]
    assert apply_operation_calls[-1][2]["option"] == "smart"


def test_no_arbitrage_without_more_price_data_today(make_coordinator, hass):
    """No remaining price data today at all (edge case, e.g. very end of
    day with nothing left to compare against) - must not crash, must
    not trigger."""
    coordinator = _make_ready_coordinator(make_coordinator, hass)

    with_now(coordinator, DAY0.replace(hour=23, minute=59))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason != "arbitrage_charging"


def test_arbitrage_solar_capture_resolves_to_smart_mode(make_coordinator, hass):
    """v0.63.66, reported: 'Verwachting zegt nog steeds smart discharge'
    - REASON_TO_MODE had no entry for 'arbitrage_solar_capture'
    (introduced in v0.63.60), so _finish_decision_tick's .get(...,
    self.last_expected_mode) fallback silently kept whatever mode was
    expected on a PREVIOUS tick (e.g. smart_discharging) instead of
    correctly resolving to smart for this reason."""
    from custom_components.energy_management_system import coordinator as coord_mod

    coordinator = make_coordinator(_base_config())
    coordinator.last_expected_mode = "smart_discharging"  # stale, from a prior tick
    coordinator.last_reason = "arbitrage_solar_capture"

    coord_mod.dt_util.now = lambda: DAY0
    coordinator._finish_decision_tick(DAY0)

    assert coordinator.last_expected_mode == "smart"
