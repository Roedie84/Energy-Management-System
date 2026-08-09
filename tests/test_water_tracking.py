"""Water-tabblad (v0.63.85, gevraagd: "Meldingen/tracking zoals bij
vaatwasser/wasmachine" - herzien naar "geen meldingen alleen een
watertabblad met relevante info"). Puur informatief, stuurt nooit iets
aan en beïnvloedt de accu-beslissing op geen enkele manier.
"""
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 8, 5, tzinfo=timezone.utc)


def _base_config(**overrides):
    config = {
        "water_active_usage_sensor_entity": "sensor.water_active",
        "water_daily_total_sensor_entity": "sensor.water_daily",
        "water_total_usage_sensor_entity": "sensor.water_total",
    }
    config.update(overrides)
    return config


def test_daily_total_tracked_directly(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.water_daily", "12.5")

    coordinator._update_water_tracking(DAY0)

    assert coordinator.water_daily_total_l == 12.5


def test_daily_total_archived_on_reset(make_coordinator, hass):
    """When the 'today' sensor itself resets (value drops), the
    previous value must be archived into the daily history."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.water_daily", "180.0")
    coordinator._update_water_tracking(DAY0)

    hass.states.set("sensor.water_daily", "0.4")  # reset just happened
    coordinator._update_water_tracking(DAY0 + timedelta(hours=1))

    assert coordinator.water_daily_history == [180.0]
    assert coordinator.water_daily_total_l == 0.4


def test_daily_history_capped_at_learning_window(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        LEARNING_HISTORY_DAYS,
    )

    coordinator = make_coordinator(_base_config())
    now = DAY0
    for day in range(LEARNING_HISTORY_DAYS + 3):
        hass.states.set("sensor.water_daily", str(100.0 + day))
        coordinator._update_water_tracking(now)
        now += timedelta(days=1)
        hass.states.set("sensor.water_daily", "0.0")
        coordinator._update_water_tracking(now)

    assert len(coordinator.water_daily_history) == LEARNING_HISTORY_DAYS


def test_session_detected_and_logged(make_coordinator, hass):
    """A sustained flow above the threshold, followed by a sustained
    drop below it, must be logged as a completed usage session."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.water_total", "10.000")

    now = DAY0
    hass.states.set("sensor.water_active", "8.0")  # above threshold
    coordinator._update_water_tracking(now)
    assert coordinator._water_usage_state == "actief"

    now += timedelta(minutes=5)
    hass.states.set("sensor.water_active", "8.0")
    coordinator._update_water_tracking(now)

    # Flow drops - starts the completion timer.
    now += timedelta(minutes=1)
    hass.states.set("sensor.water_active", "0.0")
    hass.states.set("sensor.water_total", "10.045")  # 45 liters used
    coordinator._update_water_tracking(now)
    assert coordinator._water_usage_state == "actief"  # not yet confirmed done

    # Sustained low flow for the completion window.
    now += timedelta(minutes=3)
    coordinator._update_water_tracking(now)

    assert coordinator._water_usage_state == "rustend"
    assert len(coordinator.water_session_history) == 1
    session = coordinator.water_session_history[0]
    # v0.63.119: de liters komen nu primair uit het GEINTEGREERDE
    # debiet, niet meer uit het verschil van de meterstand. Hier stroomt
    # 8 L/min gedurende 6 minuten = 48 L; de meterstand rapporteert 45 L
    # (zijn eigen afronding). Beide worden vastgelegd, zodat een
    # afwijking zichtbaar is in plaats van stilzwijgend.
    assert session["liter"] == 48.0
    assert session["liter_uit_meterstand"] == 45.0
    assert session["duur_minuten"] > 0


def test_brief_dip_does_not_end_the_session(make_coordinator, hass):
    """A brief dip below the threshold (shorter than the completion
    window) must not end the session - the flow resuming should just
    continue the same session."""
    coordinator = make_coordinator(_base_config())

    now = DAY0
    hass.states.set("sensor.water_active", "8.0")
    coordinator._update_water_tracking(now)
    started_at = coordinator._water_session_started_at

    now += timedelta(minutes=1)
    hass.states.set("sensor.water_active", "0.0")
    coordinator._update_water_tracking(now)

    now += timedelta(seconds=30)  # well under the completion window
    hass.states.set("sensor.water_active", "8.0")
    coordinator._update_water_tracking(now)

    assert coordinator._water_usage_state == "actief"
    assert coordinator._water_session_started_at == started_at
    assert coordinator.water_session_history == []


def test_low_flow_below_threshold_never_starts_a_session(make_coordinator, hass):
    """A trivial flow below the active threshold (e.g. sensor noise)
    must never start a session at all."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.water_active", "0.3")

    coordinator._update_water_tracking(DAY0)

    assert coordinator._water_usage_state == "rustend"


def test_no_tracking_without_configured_sensors(make_coordinator, hass):
    """Nothing happens at all if no water sensors are configured -
    must not error."""
    coordinator = make_coordinator({})

    coordinator._update_water_tracking(DAY0)

    assert coordinator.water_daily_total_l is None
    assert coordinator.water_session_history == []


def test_sensor_exposes_current_flow_and_trend(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import WaterUsageSensor

    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.water_active", "6.5")
    coordinator.water_daily_total_l = 220.0
    coordinator.water_daily_history = [180.0, 200.0, 190.0]

    sensor = WaterUsageSensor(coordinator, "entry1")

    assert sensor.native_value == 6.5
    attrs = sensor.extra_state_attributes
    assert attrs["vandaag_liter"] == 220.0
    assert attrs["gemiddeld_liter_per_dag"] == 190.0
    assert attrs["trend_procent"] > 0  # today is above average


def test_sensor_restores_history_after_restart(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import WaterUsageSensor

    coordinator = make_coordinator(_base_config())
    sensor = WaterUsageSensor(coordinator, "entry1")

    class _FakeLastState:
        attributes = {
            "geschiedenis_liter_per_dag": [150.0, 160.0],
            "recente_gebruiksmomenten": [
                {"gestart": "2026-08-04T20:00:00+00:00", "duur_minuten": 8.0, "liter": 60.0}
            ],
            "vandaag_liter": 42.0,
        }

    async def get_last_state():
        return _FakeLastState()

    sensor.async_get_last_state = get_last_state

    import asyncio

    asyncio.run(sensor.async_added_to_hass())

    assert coordinator.water_daily_history == [150.0, 160.0]
    assert coordinator.water_daily_total_l == 42.0
    assert len(coordinator.water_session_history) == 1


def test_night_session_marked_as_softener(make_coordinator, hass):
    """A completed usage session starting within the night window must
    be marked as the water softener and update the 'last regeneration'
    timestamp.

    v1.18.0: de drempel vraagt nu 40 liter EN 15 minuten. Tien minuten
    op 5 L/min is vijftig liter maar te kort - een echte regeneratie
    duurt twintig tot zestig minuten. Vandaar 25 minuten.
    """
    coordinator = make_coordinator(_base_config())

    now = DAY0.replace(hour=3, minute=0)  # well within the night window
    hass.states.set("sensor.water_active", "5.0")
    coordinator._update_water_tracking(now)

    now += timedelta(minutes=25)
    hass.states.set("sensor.water_active", "0.0")
    coordinator._update_water_tracking(now)

    now += timedelta(minutes=3)
    coordinator._update_water_tracking(now)

    assert len(coordinator.water_session_history) == 1
    session = coordinator.water_session_history[0]
    assert session["waarschijnlijk_waterontharder"] is True
    assert coordinator.water_softener_last_regeneration == DAY0.replace(
        hour=3, minute=0
    )


def test_daytime_session_not_marked_as_softener(make_coordinator, hass):
    """A session starting during normal waking hours (e.g. a shower)
    must NOT be marked as the softener."""
    coordinator = make_coordinator(_base_config())

    now = DAY0.replace(hour=8, minute=0)
    hass.states.set("sensor.water_active", "8.0")
    coordinator._update_water_tracking(now)

    now += timedelta(minutes=5)
    hass.states.set("sensor.water_active", "0.0")
    coordinator._update_water_tracking(now)

    now += timedelta(minutes=3)
    coordinator._update_water_tracking(now)

    assert len(coordinator.water_session_history) == 1
    assert coordinator.water_session_history[0]["waarschijnlijk_waterontharder"] is False
    assert coordinator.water_softener_last_regeneration is None


def test_sensor_exposes_softener_timestamp(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import WaterUsageSensor

    coordinator = make_coordinator(_base_config())
    coordinator.water_softener_last_regeneration = DAY0.replace(hour=3)

    sensor = WaterUsageSensor(coordinator, "entry1")

    assert (
        sensor.extra_state_attributes["waterontharder_laatste_regeneratie"]
        == DAY0.replace(hour=3).isoformat()
    )


def test_sensor_restores_softener_timestamp(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import WaterUsageSensor

    coordinator = make_coordinator(_base_config())
    sensor = WaterUsageSensor(coordinator, "entry1")

    class _FakeLastState:
        attributes = {
            "waterontharder_laatste_regeneratie": "2026-08-04T03:00:00+00:00",
        }

    async def get_last_state():
        return _FakeLastState()

    sensor.async_get_last_state = get_last_state

    import asyncio

    asyncio.run(sensor.async_added_to_hass())

    assert coordinator.water_softener_last_regeneration == datetime(
        2026, 8, 4, 3, 0, 0, tzinfo=timezone.utc
    )
