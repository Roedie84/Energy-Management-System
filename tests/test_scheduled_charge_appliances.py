"""Scheduled-charge appliance control (v0.63.12/v0.63.13): charges only
during today's cheapest price block, year-round, instead of a fixed
clock window - and turns itself off once charging is genuinely complete
(sustained low power draw), not on a guessed duration. Shared logic
between the steelstofzuiger and the e-bike chargers (fietsladers).
"""
import asyncio
from datetime import datetime, timedelta, timezone

from conftest import make_price_forecast

DAY0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _flat_price_with_cheap_block(hour, minute):
    if 12 <= hour < 16:
        return 1_300_000
    return 2_500_000


def _base_config(**overrides):
    config = {
        "price_sensor_entity": "sensor.price",
        "price_attribute": "price_tax_included",
        "operation_select_entity": "select.op",
        "manual_power_number_entity": "number.pow",
        "manual_discharge_power": 1600,
        "steelstofzuiger_switch_entity": "switch.steelstofzuiger",
        "steelstofzuiger_power_sensor_entity": "sensor.steelstofzuiger_vermogen",
    }
    config.update(overrides)
    return config


def with_now(coordinator, when: datetime) -> None:
    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: when


def _switch_calls(hass):
    return [c for c in hass.services.calls if c[0] == "switch"]


def test_switch_turns_on_at_the_start_of_the_cheapest_block(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("switch.steelstofzuiger", "off")
    hass.states.set("sensor.steelstofzuiger_vermogen", "80")

    coordinator = make_coordinator(_base_config())

    with_now(coordinator, DAY0.replace(hour=12, minute=0))
    asyncio.run(coordinator._async_update_locked())

    calls = _switch_calls(hass)
    assert len(calls) == 1
    assert calls[0][1] == "turn_on"
    assert calls[0][2]["entity_id"] == "switch.steelstofzuiger"
    assert coordinator.last_steelstofzuiger_action == "test_aan"


def test_switch_stays_off_outside_the_cheap_block(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("switch.steelstofzuiger", "off")
    hass.states.set("sensor.steelstofzuiger_vermogen", "0")

    coordinator = make_coordinator(_base_config())

    with_now(coordinator, DAY0.replace(hour=9, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert _switch_calls(hass) == []
    assert coordinator.last_steelstofzuiger_action == "wacht_op_goedkoop_blok"


def test_switch_turns_off_once_charging_completes(make_coordinator, hass):
    """Power sustained below the running threshold for
    STEELSTOFZUIGER_COMPLETE_SUSTAINED_MINUTES means the charge is done -
    turn off and mark complete for the rest of the day. Requires a
    genuine active reading first (v0.63.37) - see
    test_never_marks_complete_without_ever_being_active below for the
    reported bug this distinction fixes."""
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("switch.steelstofzuiger", "off")
    hass.states.set("sensor.steelstofzuiger_vermogen", "80")

    coordinator = make_coordinator(_base_config())

    async def run():
        with_now(coordinator, DAY0.replace(hour=12, minute=0))
        await coordinator._async_update_locked()  # turns on

        # Switch is now genuinely on and drawing real power - registers
        # as a genuine active session.
        hass.states.set("switch.steelstofzuiger", "on")
        with_now(coordinator, DAY0.replace(hour=12, minute=5))
        await coordinator._async_update_locked()
        assert coordinator.last_steelstofzuiger_action == "aan_het_laden"

        # Now power drops to standby (charge complete).
        hass.states.set("sensor.steelstofzuiger_vermogen", "2")
        with_now(coordinator, DAY0.replace(hour=12, minute=10))
        await coordinator._async_update_locked()
        assert coordinator.last_steelstofzuiger_action == "aan_het_laden"

        with_now(coordinator, DAY0.replace(hour=12, minute=13))
        await coordinator._async_update_locked()

    asyncio.run(run())

    calls = _switch_calls(hass)
    assert calls[-1][1] == "turn_off"
    assert coordinator.last_steelstofzuiger_action == "voltooid"
    assert coordinator._steelstofzuiger_complete_today is True
    # Duration is measured from when charging was genuinely confirmed
    # (12:05, once power crossed the threshold) - not from the initial
    # test-poll tick (12:00) - so 12:13-12:05 = 8 minutes, not 13.
    assert coordinator.steelstofzuiger_charge_duration_history == [8.0]


def test_stays_off_for_the_rest_of_the_day_once_complete(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("switch.steelstofzuiger", "off")

    coordinator = make_coordinator(_base_config())
    coordinator._steelstofzuiger_complete_today = True
    coordinator._steelstofzuiger_complete_date = DAY0.date()

    with_now(coordinator, DAY0.replace(hour=13, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert _switch_calls(hass) == []
    assert coordinator.last_steelstofzuiger_action == "voltooid_vandaag"


def test_complete_flag_resets_on_a_new_day(make_coordinator, hass):
    forecast_day0 = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast_day0})
    hass.states.set("switch.steelstofzuiger", "off")
    hass.states.set("sensor.steelstofzuiger_vermogen", "80")

    coordinator = make_coordinator(_base_config())
    coordinator._steelstofzuiger_complete_today = True
    coordinator._steelstofzuiger_complete_date = DAY0.date()

    day1 = DAY0 + timedelta(days=1)
    forecast_day1 = make_price_forecast(day1, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast_day1})

    with_now(coordinator, day1.replace(hour=12, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator._steelstofzuiger_complete_today is False
    assert _switch_calls(hass)[0][1] == "turn_on"


def test_no_action_without_configured_switch(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})

    coordinator = make_coordinator(
        {
            "price_sensor_entity": "sensor.price",
            "price_attribute": "price_tax_included",
            "operation_select_entity": "select.op",
            "manual_power_number_entity": "number.pow",
            "manual_discharge_power": 1600,
        }
    )

    with_now(coordinator, DAY0.replace(hour=12, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert _switch_calls(hass) == []


def test_learning_only_mode_never_touches_the_switch(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("switch.steelstofzuiger", "off")
    hass.states.set("sensor.steelstofzuiger_vermogen", "80")

    coordinator = make_coordinator(_base_config())
    coordinator.learning_only = True

    with_now(coordinator, DAY0.replace(hour=12, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert _switch_calls(hass) == []
    assert coordinator.last_steelstofzuiger_action == "test_aan"


def test_learned_duration_uses_median(make_coordinator):
    coordinator = make_coordinator({})
    coordinator.steelstofzuiger_charge_duration_history = [40.0, 42.0, 41.0, 39.0, 90.0]

    assert coordinator.learned_steelstofzuiger_duration_minutes == 41.0


def test_fietsladers_uses_its_own_20w_threshold(make_coordinator, hass):
    """v0.63.13: the e-bike chargers use a 20W completion threshold
    (reported), not the shared 15W APPLIANCE_RUNNING_POWER_THRESHOLD_W.
    18W is below the fietsladers-specific 20W cutoff but *above* the
    shared 15W one - if the wrong threshold were applied, this would
    never be detected as complete."""
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("switch.fietsladers", "on")
    hass.states.set("sensor.fietsladers_vermogen", "25")  # above 20W, genuinely active

    coordinator = make_coordinator(
        _base_config(
            fietsladers_switch_entity="switch.fietsladers",
            fietsladers_power_sensor_entity="sensor.fietsladers_vermogen",
        )
    )

    async def run():
        with_now(coordinator, DAY0.replace(hour=12, minute=0))
        await coordinator._async_update_locked()
        hass.states.set("switch.fietsladers", "on")

        hass.states.set("sensor.fietsladers_vermogen", "18")
        with_now(coordinator, DAY0.replace(hour=12, minute=3))
        await coordinator._async_update_locked()

        with_now(coordinator, DAY0.replace(hour=12, minute=6))
        await coordinator._async_update_locked()

    asyncio.run(run())

    assert coordinator.last_fietsladers_action == "voltooid"


def test_fietsladers_sends_notification_on_completion(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("switch.fietsladers", "on")
    hass.states.set("sensor.fietsladers_vermogen", "300")  # genuinely charging

    coordinator = make_coordinator(
        _base_config(
            fietsladers_switch_entity="switch.fietsladers",
            fietsladers_power_sensor_entity="sensor.fietsladers_vermogen",
            appliance_notify_service="notify.mobile_app_test",
        )
    )

    async def run():
        with_now(coordinator, DAY0.replace(hour=12, minute=0))
        await coordinator._async_update_locked()  # switch turns on
        hass.states.set("switch.fietsladers", "on")

        hass.states.set("sensor.fietsladers_vermogen", "5")
        with_now(coordinator, DAY0.replace(hour=12, minute=3))
        await coordinator._async_update_locked()  # seeds below_threshold_since

        with_now(coordinator, DAY0.replace(hour=12, minute=6))
        await coordinator._async_update_locked()  # sustained low -> complete

    asyncio.run(run())

    notify_calls = [c for c in hass.services.calls if c[0] == "notify"]
    assert len(notify_calls) == 1
    assert "Fietsen opgeladen" in notify_calls[0][2]["title"]
    assert coordinator.last_fietsladers_action == "voltooid"


def test_steelstofzuiger_and_fietsladers_are_independent(make_coordinator, hass):
    """Both scheduled-charge appliances run through the same shared
    helper - confirm one's state doesn't bleed into the other's."""
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("switch.steelstofzuiger", "off")
    hass.states.set("sensor.steelstofzuiger_vermogen", "80")
    hass.states.set("switch.fietsladers", "off")
    hass.states.set("sensor.fietsladers_vermogen", "60")

    coordinator = make_coordinator(
        _base_config(
            fietsladers_switch_entity="switch.fietsladers",
            fietsladers_power_sensor_entity="sensor.fietsladers_vermogen",
        )
    )

    with_now(coordinator, DAY0.replace(hour=12, minute=0))
    asyncio.run(coordinator._async_update_locked())

    calls = _switch_calls(hass)
    turned_on = {c[2]["entity_id"] for c in calls if c[1] == "turn_on"}
    assert turned_on == {"switch.steelstofzuiger", "switch.fietsladers"}
    assert coordinator.last_steelstofzuiger_action == "test_aan"
    assert coordinator.last_fietsladers_action == "test_aan"


def test_steelstofzuiger_override_leaves_the_switch_untouched(make_coordinator, hass):
    """v0.63.14: with the override switch on, the integration never
    touches the steelstofzuiger switch, even during the cheapest block."""
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("switch.steelstofzuiger", "off")
    hass.states.set("sensor.steelstofzuiger_vermogen", "80")

    coordinator = make_coordinator(_base_config())
    coordinator.steelstofzuiger_override = True

    with_now(coordinator, DAY0.replace(hour=12, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert _switch_calls(hass) == []
    assert coordinator.last_steelstofzuiger_action == "overruled"


def test_fietsladers_override_leaves_the_switch_untouched(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("switch.fietsladers", "off")
    hass.states.set("sensor.fietsladers_vermogen", "60")

    coordinator = make_coordinator(
        _base_config(
            fietsladers_switch_entity="switch.fietsladers",
            fietsladers_power_sensor_entity="sensor.fietsladers_vermogen",
        )
    )
    coordinator.fietsladers_override = True

    with_now(coordinator, DAY0.replace(hour=12, minute=0))
    asyncio.run(coordinator._async_update_locked())

    calls = _switch_calls(hass)
    turned = {c[2]["entity_id"] for c in calls}
    assert "switch.fietsladers" not in turned
    assert coordinator.last_fietsladers_action == "overruled"


def test_override_on_one_appliance_does_not_affect_the_other(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("switch.steelstofzuiger", "off")
    hass.states.set("sensor.steelstofzuiger_vermogen", "80")
    hass.states.set("switch.fietsladers", "off")
    hass.states.set("sensor.fietsladers_vermogen", "60")

    coordinator = make_coordinator(
        _base_config(
            fietsladers_switch_entity="switch.fietsladers",
            fietsladers_power_sensor_entity="sensor.fietsladers_vermogen",
        )
    )
    coordinator.steelstofzuiger_override = True

    with_now(coordinator, DAY0.replace(hour=12, minute=0))
    asyncio.run(coordinator._async_update_locked())

    calls = _switch_calls(hass)
    turned_on = {c[2]["entity_id"] for c in calls if c[1] == "turn_on"}
    assert turned_on == {"switch.fietsladers"}
    assert coordinator.last_steelstofzuiger_action == "overruled"
    assert coordinator.last_fietsladers_action == "test_aan"


def test_never_marks_complete_without_ever_being_active(make_coordinator, hass):
    """v0.63.37/.38, reproduces the exact reported scenario: the cheap
    block starts and the switch turns on, but the e-bikes aren't
    physically plugged in until 2 hours later, still within the same
    cheap block. Without genuine activity ever being registered,
    sustained low power must NOT be mistaken for 'finished' - and
    (v0.63.38, fire-safety follow-up) the switch must not just sit on
    continuously for those 2 hours either - it polls (on briefly, off
    for a cooldown) instead of staying energised unattended."""
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("switch.fietsladers", "off")
    hass.states.set("sensor.fietsladers_vermogen", "3")  # standby, nothing plugged in

    coordinator = make_coordinator(
        _base_config(
            fietsladers_switch_entity="switch.fietsladers",
            fietsladers_power_sensor_entity="sensor.fietsladers_vermogen",
        )
    )

    async def run():
        # Cheap block starts (12:00-16:00 per _flat_price_with_cheap_block).
        # Poll attempt 1: on for a short test window.
        with_now(coordinator, DAY0.replace(hour=12, minute=0))
        await coordinator._async_update_locked()
        assert coordinator.last_fietsladers_action == "test_aan"
        hass.states.set("switch.fietsladers", "on")

        # 5 minutes later, still nothing plugged in - the test window
        # has elapsed, so it goes back off for a cooldown instead of
        # sitting on indefinitely (fire-safety) or falsely declaring
        # "voltooid" (the v0.63.37 bug).
        with_now(coordinator, DAY0.replace(hour=12, minute=5))
        await coordinator._async_update_locked()
        assert coordinator.last_fietsladers_action == "wacht_op_apparaat"
        assert coordinator._fietsladers_complete_today is False
        hass.states.set("switch.fietsladers", "off")

        # Still within the cooldown 10 minutes later - stays off.
        with_now(coordinator, DAY0.replace(hour=12, minute=10))
        await coordinator._async_update_locked()
        assert coordinator.last_fietsladers_action == "wacht_op_apparaat"

        # 2 hours later, still within the same cheap block, the bikes
        # finally get plugged in - a fresh poll attempt starts...
        with_now(coordinator, DAY0.replace(hour=14, minute=0))
        await coordinator._async_update_locked()
        assert coordinator.last_fietsladers_action == "test_aan"
        hass.states.set("switch.fietsladers", "on")

        # ...and this time it detects genuine load.
        hass.states.set("sensor.fietsladers_vermogen", "300")
        with_now(coordinator, DAY0.replace(hour=14, minute=2))
        await coordinator._async_update_locked()
        assert coordinator.last_fietsladers_action == "aan_het_laden"

    asyncio.run(run())

    # No completion was ever falsely marked before the bikes were
    # actually plugged in.
    assert coordinator._fietsladers_complete_today is False


def test_poll_cycle_matches_reported_15_minute_suggestion(make_coordinator, hass):
    """v0.63.38: confirms the poll/cooldown timing directly - roughly a
    5-minute 'on' test window followed by a 15-minute cooldown, matching
    the reported '15 minuten controle cyclus' suggestion, instead of
    sitting on continuously while nothing is plugged in."""
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("switch.steelstofzuiger", "off")
    hass.states.set("sensor.steelstofzuiger_vermogen", "0")  # nothing plugged in

    coordinator = make_coordinator(_base_config())

    async def run():
        with_now(coordinator, DAY0.replace(hour=12, minute=0))
        await coordinator._async_update_locked()
        hass.states.set("switch.steelstofzuiger", "on")

        with_now(coordinator, DAY0.replace(hour=12, minute=5))
        await coordinator._async_update_locked()
        assert coordinator.last_steelstofzuiger_action == "wacht_op_apparaat"
        hass.states.set("switch.steelstofzuiger", "off")

        # Still cooling down at +10 min from the poll ending (15 min
        # cooldown hasn't elapsed yet).
        with_now(coordinator, DAY0.replace(hour=12, minute=15))
        await coordinator._async_update_locked()
        assert coordinator.last_steelstofzuiger_action == "wacht_op_apparaat"

        # Cooldown elapsed - a fresh poll attempt.
        with_now(coordinator, DAY0.replace(hour=12, minute=20))
        await coordinator._async_update_locked()
        assert coordinator.last_steelstofzuiger_action == "test_aan"

    asyncio.run(run())

    calls = _switch_calls(hass)
    turn_ons = [c for c in calls if c[1] == "turn_on"]
    turn_offs = [c for c in calls if c[1] == "turn_off"]
    # Two separate poll attempts (on/off/on), not one continuous "on".
    assert len(turn_ons) == 2
    assert len(turn_offs) == 1
