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
    assert coordinator.last_steelstofzuiger_action == "laden_gestart"


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
    turn off and mark complete for the rest of the day."""
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("switch.steelstofzuiger", "off")
    hass.states.set("sensor.steelstofzuiger_vermogen", "80")

    coordinator = make_coordinator(_base_config())

    async def run():
        with_now(coordinator, DAY0.replace(hour=12, minute=0))
        await coordinator._async_update_locked()

        # Now "on" - simulate the switch having actually turned on, and
        # power dropping to standby (charge complete).
        hass.states.set("switch.steelstofzuiger", "on")
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
    assert coordinator.steelstofzuiger_charge_duration_history == [13.0]


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
    assert coordinator.last_steelstofzuiger_action == "laden_gestart"


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
    hass.states.set("sensor.fietsladers_vermogen", "18")

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

        with_now(coordinator, DAY0.replace(hour=12, minute=3))
        await coordinator._async_update_locked()

    asyncio.run(run())

    assert coordinator.last_fietsladers_action == "voltooid"


def test_fietsladers_sends_notification_on_completion(make_coordinator, hass):
    forecast = make_price_forecast(DAY0, _flat_price_with_cheap_block)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("switch.fietsladers", "on")
    hass.states.set("sensor.fietsladers_vermogen", "5")

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

        with_now(coordinator, DAY0.replace(hour=12, minute=3))
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
    assert coordinator.last_steelstofzuiger_action == "laden_gestart"
    assert coordinator.last_fietsladers_action == "laden_gestart"


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
    assert coordinator.last_fietsladers_action == "laden_gestart"
