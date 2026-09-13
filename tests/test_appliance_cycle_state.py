"""RUSTEND/ACTIEF/KLAAR-toestandsmachine voor vaatwasser/wasmachine
(v0.63.32, "Optie 1"): geen fase-detectie (vullen/wassen/spoelen/
centrifugeren) - vereist merk/model-specifieke trainingsdata die er
niet is. Wel: aan/uit-status + geleerde cyclusduur, met dezelfde
aanhoudend-laag-bevestigt-klaar-logica als de steelstofzuiger/
fietsladers, maar met een ruimere marge (5 min i.p.v. 2) voor
tussentijdse stille fases.
"""
import asyncio
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _base_config(**overrides):
    config = {
        "dishwasher_power_sensor_entity": "sensor.vaatwasser_vermogen",
        "washing_machine_power_sensor_entity": "sensor.wasmachine_vermogen",
    }
    config.update(overrides)
    return config


def test_starts_rustend(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    assert coordinator._dishwasher_state == "rustend"


def test_transitions_to_actief_above_threshold(make_coordinator, hass):
    hass.states.set("sensor.vaatwasser_vermogen", "80")
    coordinator = make_coordinator(_base_config())

    coordinator._update_appliance_state_machine(
        DAY0,
        power_entity="sensor.vaatwasser_vermogen",
        state_attr="_dishwasher_state",
        cycle_started_attr="_dishwasher_cycle_started_at",
        below_threshold_since_attr="_dishwasher_below_threshold_since",
        duration_history_attr="dishwasher_cycle_duration_history",
    )

    assert coordinator._dishwasher_state == "actief"
    assert coordinator._dishwasher_cycle_started_at == DAY0


def test_brief_pause_below_threshold_does_not_finish_the_cycle(make_coordinator, hass):
    """A short quiet phase (e.g. a fill/soak pause) under
    APPLIANCE_CYCLE_COMPLETE_SUSTAINED_MINUTES (5 min) shouldn't be
    mistaken for 'klaar'."""
    coordinator = make_coordinator(_base_config())

    def run(power_w, when):
        hass.states.set("sensor.vaatwasser_vermogen", str(power_w))
        coordinator._update_appliance_state_machine(
            when,
            power_entity="sensor.vaatwasser_vermogen",
            state_attr="_dishwasher_state",
            cycle_started_attr="_dishwasher_cycle_started_at",
            below_threshold_since_attr="_dishwasher_below_threshold_since",
            duration_history_attr="dishwasher_cycle_duration_history",
        )

    run(80, DAY0)
    run(0, DAY0 + timedelta(minutes=3))  # brief pause, under 5 min
    run(80, DAY0 + timedelta(minutes=4))  # active again

    assert coordinator._dishwasher_state == "actief"
    assert coordinator.dishwasher_cycle_duration_history == []


def test_sustained_low_power_finishes_the_cycle_and_learns_duration(
    make_coordinator, hass
):
    coordinator = make_coordinator(_base_config())

    def run(power_w, when):
        hass.states.set("sensor.vaatwasser_vermogen", str(power_w))
        coordinator._update_appliance_state_machine(
            when,
            power_entity="sensor.vaatwasser_vermogen",
            state_attr="_dishwasher_state",
            cycle_started_attr="_dishwasher_cycle_started_at",
            below_threshold_since_attr="_dishwasher_below_threshold_since",
            duration_history_attr="dishwasher_cycle_duration_history",
        )

    run(80, DAY0)
    run(0, DAY0 + timedelta(minutes=90))
    run(0, DAY0 + timedelta(minutes=96))  # 6 min sustained low - past the 5 min mark

    assert coordinator._dishwasher_state == "klaar"
    assert coordinator.dishwasher_cycle_duration_history == [96.0]
    assert coordinator.learned_dishwasher_cycle_duration_minutes == 96.0


def test_new_cycle_starts_directly_from_klaar(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    coordinator._dishwasher_state = "klaar"

    coordinator._update_appliance_state_machine(
        DAY0,
        power_entity="sensor.vaatwasser_vermogen",
        state_attr="_dishwasher_state",
        cycle_started_attr="_dishwasher_cycle_started_at",
        below_threshold_since_attr="_dishwasher_below_threshold_since",
        duration_history_attr="dishwasher_cycle_duration_history",
    )
    hass.states.set("sensor.vaatwasser_vermogen", "80")
    coordinator._update_appliance_state_machine(
        DAY0,
        power_entity="sensor.vaatwasser_vermogen",
        state_attr="_dishwasher_state",
        cycle_started_attr="_dishwasher_cycle_started_at",
        below_threshold_since_attr="_dishwasher_below_threshold_since",
        duration_history_attr="dishwasher_cycle_duration_history",
    )

    assert coordinator._dishwasher_state == "actief"


def test_dishwasher_and_washing_machine_are_independent(make_coordinator, hass):
    hass.states.set("sensor.vaatwasser_vermogen", "80")
    hass.states.set("sensor.wasmachine_vermogen", "0")

    coordinator = make_coordinator(_base_config())
    coordinator._update_appliance_state_machine(
        DAY0,
        power_entity="sensor.vaatwasser_vermogen",
        state_attr="_dishwasher_state",
        cycle_started_attr="_dishwasher_cycle_started_at",
        below_threshold_since_attr="_dishwasher_below_threshold_since",
        duration_history_attr="dishwasher_cycle_duration_history",
    )
    coordinator._update_appliance_state_machine(
        DAY0,
        power_entity="sensor.wasmachine_vermogen",
        state_attr="_washing_machine_state",
        cycle_started_attr="_washing_machine_cycle_started_at",
        below_threshold_since_attr="_washing_machine_below_threshold_since",
        duration_history_attr="washing_machine_cycle_duration_history",
    )

    assert coordinator._dishwasher_state == "actief"
    assert coordinator._washing_machine_state == "rustend"


def test_no_power_entity_does_nothing(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._update_appliance_state_machine(
        DAY0,
        power_entity=None,
        state_attr="_dishwasher_state",
        cycle_started_attr="_dishwasher_cycle_started_at",
        below_threshold_since_attr="_dishwasher_below_threshold_since",
        duration_history_attr="dishwasher_cycle_duration_history",
    )
    assert coordinator._dishwasher_state == "rustend"


def test_notification_sent_when_cycle_finishes(make_coordinator, hass):
    coordinator = make_coordinator(
        _base_config(appliance_notify_service="notify.mobile_app_test")
    )

    async def run():
        hass.states.set("sensor.vaatwasser_vermogen", "80")
        coordinator._update_appliance_state_machine(
            DAY0,
            power_entity="sensor.vaatwasser_vermogen",
            state_attr="_dishwasher_state",
            cycle_started_attr="_dishwasher_cycle_started_at",
            below_threshold_since_attr="_dishwasher_below_threshold_since",
            duration_history_attr="dishwasher_cycle_duration_history",
            notify_title="🍽️ Vaatwasser klaar",
        )
        hass.states.set("sensor.vaatwasser_vermogen", "0")
        coordinator._update_appliance_state_machine(
            DAY0 + timedelta(minutes=90),
            power_entity="sensor.vaatwasser_vermogen",
            state_attr="_dishwasher_state",
            cycle_started_attr="_dishwasher_cycle_started_at",
            below_threshold_since_attr="_dishwasher_below_threshold_since",
            duration_history_attr="dishwasher_cycle_duration_history",
            notify_title="🍽️ Vaatwasser klaar",
        )
        coordinator._update_appliance_state_machine(
            DAY0 + timedelta(minutes=96),
            power_entity="sensor.vaatwasser_vermogen",
            state_attr="_dishwasher_state",
            cycle_started_attr="_dishwasher_cycle_started_at",
            below_threshold_since_attr="_dishwasher_below_threshold_since",
            duration_history_attr="dishwasher_cycle_duration_history",
            notify_title="🍽️ Vaatwasser klaar",
        )
        await asyncio.sleep(0)

    asyncio.run(run())

    notify_calls = [c for c in hass.services.calls if c[0] == "notify"]
    assert len(notify_calls) == 1
    assert "Vaatwasser klaar" in notify_calls[0][2]["title"]
