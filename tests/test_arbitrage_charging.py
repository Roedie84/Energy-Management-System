"""v0.63.77, final confirmed decision after several rounds of real-world
reports: the entire "actively buy from the grid because a later, more
expensive quarter makes it profitable" mechanism (arbitrage-laden,
v0.63.15-.76) is removed completely - even when the reserve is
genuinely insufficient to bridge the night. Only the existing, separate
`should_force_charge` and `_is_emergency_low_battery` mechanisms remain
as the safety net for a genuine shortfall.

The only thing left: don't let already-available solar surplus go to
waste during smart_discharging - see
`_should_capture_solar_instead_of_postponing`.
"""
import asyncio
from datetime import datetime, timezone

from conftest import make_price_forecast

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _price_fn_cheap_now_expensive_later(hour, minute):
    if hour < 14:
        return 2_170_000
    if 19 <= hour < 22:
        return 3_900_000
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
    hass.states.set("sensor.available_energy", "8.0")
    coordinator = make_coordinator(_base_config(**config_overrides))
    coordinator.learned_efficiency_history = [88.2] * 7
    return coordinator


def test_no_switch_entity_exists_any_more(make_coordinator, hass):
    """v0.63.65/.77 - there is no toggle for this behaviour at all, in
    any form."""
    from custom_components.energy_management_system import switch as switch_mod

    assert not hasattr(switch_mod, "ArbitrageChargingSwitch")


def test_no_function_ever_buys_from_the_grid_for_this_reason(make_coordinator, hass):
    """v0.63.77: the old _get_arbitrage_charge_power (which used to
    return a manual charge power for an active grid purchase) is gone
    entirely - confirms there's no way for this mechanism to ever
    result in a grid purchase any more, even indirectly."""
    coordinator = make_coordinator({})

    assert not hasattr(coordinator, "_get_arbitrage_charge_power")


def test_never_manual_even_with_a_profitable_margin_and_insufficient_reserve(
    make_coordinator, hass
):
    """The core, final regression: even with a genuinely profitable
    margin AND should_postpone_charging=False (insufficient reserve),
    the reason must never be an active grid purchase. Uses the
    established _should_postpone_charging monkeypatch technique to
    reliably force the "insufficient reserve" scenario."""
    coordinator = _make_ready_coordinator(make_coordinator, hass)

    def fake_should_postpone(entries, now, cheap_block_start):
        return False

    coordinator._should_postpone_charging = fake_should_postpone

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason != "arbitrage_charging"
    assert coordinator.last_reason == "default_smart"


def test_no_solar_capture_signal_when_reserve_is_sufficient_and_no_solar(
    make_coordinator, hass
):
    coordinator = _make_ready_coordinator(make_coordinator, hass)

    def fake_should_postpone(entries, now, cheap_block_start):
        return True

    coordinator._should_postpone_charging = fake_should_postpone

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason == "discharging_window"


def test_solar_still_captured_via_smart_when_reserve_is_sufficient(
    make_coordinator, hass
):
    """Even though a grid purchase is never allowed, existing solar
    surplus should still be captured via smart mode instead of wasted
    by smart_discharging - the v0.63.60 behaviour, now the only thing
    this mechanism ever does."""
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


def test_solar_capture_resolves_to_smart_mode(make_coordinator, hass):
    """v0.63.66 regression check, still relevant: REASON_TO_MODE must
    correctly resolve arbitrage_solar_capture to smart."""
    coordinator = make_coordinator(_base_config())
    coordinator.last_expected_mode = "smart_discharging"
    coordinator.last_reason = "arbitrage_solar_capture"

    coordinator._finish_decision_tick(DAY0)

    assert coordinator.last_expected_mode == "smart"


def test_no_capture_signal_without_any_solar(make_coordinator, hass):
    coordinator = make_coordinator({})

    result = coordinator._should_capture_solar_instead_of_postponing(
        DAY0, should_postpone_charging=True
    )

    assert result is False


def test_no_capture_signal_when_not_postponing(make_coordinator, hass):
    """Whenever should_postpone_charging is False, there's no
    smart_discharging to protect solar from in the first place - the
    tree's own default_smart already captures it."""
    coordinator = make_coordinator(
        _base_config(pv_power_sensor_entity="sensor.pv")
    )
    hass.states.set("sensor.p1", "-800")
    hass.states.set("sensor.pv", "800")

    result = coordinator._should_capture_solar_instead_of_postponing(
        DAY0, should_postpone_charging=False
    )

    assert result is False
