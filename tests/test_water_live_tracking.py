"""Live, event-driven water-sessie-detectie (v0.63.98, gevraagd: "Wat
gebeurt er als we naar live tikken gaan?" - naar aanleiding van
aangeleverde ruwe geschiedenis waaruit bleek dat de oude, puur
tick-gebaseerde detectie (elke 5 minuten) vrijwel alle korte
verbruiksstoten miste, omdat een steekproef elke 5 minuten simpelweg
te weinig kans heeft een stoot van 15-90 seconden te raken).

Hybride ontwerp: een aparte listener reageert direct op elke wijziging
van de watersensor (vangt elke stoot nauwkeurig), terwijl de gewone
5-minuten-tick als vangnet blijft draaien voor de AFRONDING van een
sessie (onderzoek van de ruwe sensorgeschiedenis liet gaten tot bijna
7 uur zien tussen updates zolang het debiet stil op 0 staat - de
sensor "hartslag"-t niet betrouwbaar bij rust).
"""
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 8, 6, tzinfo=timezone.utc)


class _FakeNewState:
    def __init__(self, state, last_changed):
        self.state = state
        self.last_changed = last_changed


class _FakeEvent:
    def __init__(self, new_state):
        self.data = {"new_state": new_state}


def _base_config(**overrides):
    config = {
        "water_active_usage_sensor_entity": "sensor.water_active",
        "water_daily_total_sensor_entity": "sensor.water_daily",
        "water_total_usage_sensor_entity": "sensor.water_total",
    }
    config.update(overrides)
    return config


def test_event_listener_catches_a_brief_burst_the_tick_would_miss(
    make_coordinator, hass
):
    """The core scenario from the reported issue: a burst lasting only
    20 seconds - far shorter than the 5-minute tick interval - must
    still be detected via the event listener."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.water_total", "10.000")

    start = DAY0
    coordinator._handle_water_flow_change(
        _FakeEvent(_FakeNewState("8.0", start))
    )
    assert coordinator._water_usage_state == "actief"

    end = start + timedelta(seconds=20)
    hass.states.set("sensor.water_total", "10.003")  # 3 liters used
    coordinator._handle_water_flow_change(
        _FakeEvent(_FakeNewState("0.0", end))
    )
    # Not yet finalized - still within the completion window.
    assert coordinator._water_usage_state == "actief"

    # Sustained low, confirmed via a later event.
    confirm = end + timedelta(minutes=3)
    coordinator._handle_water_flow_change(
        _FakeEvent(_FakeNewState("0.0", confirm))
    )

    assert coordinator._water_usage_state == "rustend"
    assert len(coordinator.water_session_history) == 1
    session = coordinator.water_session_history[0]
    assert session["liter"] == 3.0


def test_tick_still_finalizes_a_session_without_any_further_events(
    make_coordinator, hass
):
    """The safety net: if the sensor genuinely stops publishing events
    (confirmed to happen for hours in the raw history), the regular
    5-minute tick must still be able to finalize a stalled session."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.water_total", "5.000")

    coordinator._handle_water_flow_change(
        _FakeEvent(_FakeNewState("6.0", DAY0))
    )
    assert coordinator._water_usage_state == "actief"

    # No more events come in at all - only the regular tick runs,
    # reading the now-idle live state.
    hass.states.set("sensor.water_active", "0.0")
    hass.states.set("sensor.water_total", "5.050")

    tick_time = DAY0 + timedelta(minutes=1)
    coordinator._update_water_tracking(tick_time)
    assert coordinator._water_usage_state == "actief"  # not yet confirmed

    tick_time2 = DAY0 + timedelta(minutes=5)
    coordinator._update_water_tracking(tick_time2)

    assert coordinator._water_usage_state == "rustend"
    assert len(coordinator.water_session_history) == 1


def test_invalid_state_value_ignored_gracefully(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())

    coordinator._handle_water_flow_change(
        _FakeEvent(_FakeNewState("unavailable", DAY0))
    )

    assert coordinator._water_usage_state == "rustend"


def test_no_new_state_ignored_gracefully(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())

    coordinator._handle_water_flow_change(_FakeEvent(None))

    assert coordinator._water_usage_state == "rustend"


def test_listener_registered_only_when_water_sensor_configured(make_coordinator, hass):
    import asyncio

    coordinator_with = make_coordinator(
        _base_config(price_sensor_entity="sensor.price")
    )
    asyncio.run(coordinator_with.async_setup())
    assert coordinator_with._unsub_water_state is not None
    asyncio.run(coordinator_with.async_unload())


def test_listener_not_registered_without_water_sensor(make_coordinator, hass):
    import asyncio

    coordinator_without = make_coordinator({"price_sensor_entity": "sensor.price"})
    asyncio.run(coordinator_without.async_setup())
    assert coordinator_without._unsub_water_state is None
    asyncio.run(coordinator_without.async_unload())
