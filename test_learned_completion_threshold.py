"""Self-learned completion threshold for scheduled-charge appliances
(v0.63.46). Reported: the fixed FIETSLADERS_COMPLETE_THRESHOLD_W guess
(20W) doesn't reflect the real observed standby draw (2W) - the
threshold is now derived from the appliance's own observed idle power
readings instead of a fixed guess, falling back to the configured fixed
threshold until enough samples exist.
"""
import asyncio
from datetime import datetime, timezone

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _base_config(**overrides):
    config = {
        "price_sensor_entity": "sensor.price",
        "price_attribute": "price_tax_included",
        "operation_select_entity": "select.op",
        "manual_power_number_entity": "number.pow",
        "fietsladers_switch_entity": "switch.fietsladers",
        "fietsladers_power_sensor_entity": "sensor.fietsladers_vermogen",
    }
    config.update(overrides)
    return config


def _call_update(coordinator, now):
    return coordinator._async_update_scheduled_charge_appliance(
        now,
        is_currently_cheapest_block=True,
        switch_entity="switch.fietsladers",
        power_entity="sensor.fietsladers_vermogen",
        complete_threshold_w=20.0,
        complete_today_attr="_fietsladers_complete_today",
        complete_date_attr="_fietsladers_complete_date",
        charge_started_attr="_fietsladers_charge_started_at",
        below_threshold_since_attr="_fietsladers_below_threshold_since",
        duration_history_attr="fietsladers_charge_duration_history",
        last_action_attr="last_fietsladers_action",
        ever_active_this_session_attr="_fietsladers_ever_active_this_session",
        next_poll_attr="_fietsladers_next_poll_at",
        idle_history_attr="_fietsladers_idle_power_history",
    )


def test_falls_back_to_fixed_threshold_without_enough_samples(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())

    threshold = coordinator._get_learned_completion_threshold_w(
        "_fietsladers_idle_power_history", 20.0
    )

    assert threshold == 20.0


def test_learns_a_much_lower_threshold_from_observed_standby_draw(
    make_coordinator, hass
):
    coordinator = make_coordinator(_base_config())
    coordinator._fietsladers_idle_power_history = [2.0, 2.0, 2.0, 2.0, 2.0, 2.0]

    threshold = coordinator._get_learned_completion_threshold_w(
        "_fietsladers_idle_power_history", 20.0
    )

    # median(2.0) + 5W margin = 7.0, far below the old fixed 20W guess.
    assert threshold == 7.0
    assert threshold < 20.0


def test_idle_history_is_bounded(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    for i in range(50):
        coordinator._record_idle_power_sample(
            "_fietsladers_idle_power_history", float(i)
        )

    assert len(coordinator._fietsladers_idle_power_history) == 20


def test_idle_samples_recorded_during_poll_test_window(make_coordinator, hass):
    """Full tick: readings taken while the switch is on but nothing is
    genuinely charging yet should feed the idle-power history."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("switch.fietsladers", "on")
    hass.states.set("sensor.fietsladers_vermogen", "2")

    async def run():
        for _ in range(6):
            await _call_update(coordinator, DAY0)

    asyncio.run(run())

    assert len(coordinator._fietsladers_idle_power_history) >= 1
    assert all(v == 2.0 for v in coordinator._fietsladers_idle_power_history)


def test_genuine_charging_still_detected_against_the_learned_threshold(
    make_coordinator, hass
):
    """Once a low learned threshold is in effect, real charging power
    (hundreds of watts) should still clearly cross it and register as
    genuinely active."""
    coordinator = make_coordinator(_base_config())
    coordinator._fietsladers_idle_power_history = [2.0] * 6  # learned threshold ~7W
    hass.states.set("switch.fietsladers", "on")
    hass.states.set("sensor.fietsladers_vermogen", "300")

    asyncio.run(_call_update(coordinator, DAY0))

    assert coordinator._fietsladers_ever_active_this_session is True
    assert coordinator.last_fietsladers_action == "aan_het_laden"
