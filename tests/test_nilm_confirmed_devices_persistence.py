"""NILM confirmed-devices persistence + attribute size cap (v0.63.66).

Reported: "State attributes for sensor...nilm_bevestigde_apparaten
exceed maximum size of 16384 bytes" - with enough confirmed devices
(each with its own learned CUSUM history, plus the tabel attribute),
this sensor grew past the recorder's per-entity attribute limit.

Unlike the unconfirmed-candidates preview (v0.63.45), this data is
user-curated and meant to persist for months - it can't just be
truncated in the entity's own restored HA state without losing real
data. Persistence now goes through a dedicated Store (a JSON file,
entirely separate from the recorder's size-limited state-history
database), while the sensor's own exposed attributes are still bounded
for display only.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT,
)
from custom_components.energy_management_system.sensor import (
    NilmConfirmedDevicesSensor,
)

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _confirm_many_devices(coordinator, count):
    for i in range(count):
        entity_id = f"sensor.apparaat_{i:03d}"
        coordinator.nilm_confirmed_devices[entity_id] = {
            "friendly_name": f"Apparaat {i:03d}",
            "confirmed_at": "2026-08-01",
            "daily_avg_history": [10.0] * 30,
            "cusum_accumulator": 0.0,
            "anomaly_detected": False,
            "estimated_drift_percent": None,
            "reference_avg_w": 10.0,
            "_today_sum": 0.0,
            "_today_count": 0,
            "_check_date": None,
        }


def test_apparaten_attribute_bounded_when_over_the_limit(make_coordinator, hass):
    coordinator = make_coordinator({})
    _confirm_many_devices(coordinator, NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT + 20)

    sensor = NilmConfirmedDevicesSensor(coordinator, "entry1")

    assert len(sensor.extra_state_attributes["apparaten"]) == (
        NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT
    )
    assert sensor.extra_state_attributes["totaal_aantal"] == (
        NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT + 20
    )
    assert "diagnostiek" in sensor.extra_state_attributes["note"].lower()


def test_native_value_reflects_true_total_even_when_bounded(make_coordinator, hass):
    coordinator = make_coordinator({})
    _confirm_many_devices(coordinator, NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT + 20)

    sensor = NilmConfirmedDevicesSensor(coordinator, "entry1")

    assert sensor.native_value == NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT + 20


def test_tabel_attribute_also_bounded(make_coordinator, hass):
    coordinator = make_coordinator({})
    _confirm_many_devices(coordinator, NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT + 20)

    sensor = NilmConfirmedDevicesSensor(coordinator, "entry1")

    assert len(sensor.extra_state_attributes["tabel"]) <= (
        NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT
    )


def test_small_list_shown_in_full_no_truncation_note(make_coordinator, hass):
    coordinator = make_coordinator({})
    _confirm_many_devices(coordinator, 3)

    sensor = NilmConfirmedDevicesSensor(coordinator, "entry1")

    assert len(sensor.extra_state_attributes["apparaten"]) == 3
    assert "diagnostiek" not in sensor.extra_state_attributes["note"].lower()


def test_confirming_a_device_saves_to_the_store(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.nilm_unconfirmed_candidates["sensor.koelkast"] = {
        "friendly_name": "Koelkast",
        "current_power_w": 82.0,
    }

    async def run():
        coordinator.confirm_nilm_device("sensor.koelkast")
        await asyncio.sleep(0)

    asyncio.run(run())

    stored = hass._fake_store_backing.get(
        "energy_management_system_nilm_confirmed_devices"
    )
    assert stored is not None
    assert "sensor.koelkast" in stored["nilm_confirmed_devices"]


def test_rejecting_saves_to_the_store(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.nilm_unconfirmed_candidates["sensor.koelkast"] = {
        "friendly_name": "Koelkast",
        "current_power_w": 82.0,
    }

    async def run():
        coordinator.reject_nilm_device("sensor.koelkast")
        await asyncio.sleep(0)

    asyncio.run(run())

    stored = hass._fake_store_backing.get(
        "energy_management_system_nilm_confirmed_devices"
    )
    assert stored is not None
    assert "sensor.koelkast" in stored["nilm_rejected_entities"]


def test_load_from_store_populates_coordinator_state(make_coordinator, hass):
    coordinator = make_coordinator({})
    _confirm_many_devices(coordinator, NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT + 30)
    asyncio.run(coordinator._async_save_nilm_confirmed_devices_store())

    fresh_coordinator = make_coordinator({})
    fresh_coordinator._nilm_confirmed_devices_store = (
        coordinator._nilm_confirmed_devices_store
    )
    asyncio.run(fresh_coordinator._async_load_nilm_confirmed_devices_store())

    assert len(fresh_coordinator.nilm_confirmed_devices) == (
        NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT + 30
    )


def test_load_leaves_state_untouched_when_store_is_empty(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.nilm_confirmed_devices["sensor.existing"] = {"friendly_name": "X"}

    asyncio.run(coordinator._async_load_nilm_confirmed_devices_store())

    assert "sensor.existing" in coordinator.nilm_confirmed_devices


def test_sensor_migrates_from_restored_state_when_store_empty(make_coordinator, hass):
    """One-time migration path for installs upgrading from before the
    Store existed."""

    class _FakeLastState:
        attributes = {
            "apparaten": {"sensor.oud_apparaat": {"friendly_name": "Oud apparaat"}},
            "rejected_entities": ["sensor.genegeerd"],
        }

    coordinator = make_coordinator({})
    sensor = NilmConfirmedDevicesSensor(coordinator, "entry1")

    async def get_last_state():
        return _FakeLastState()

    sensor.async_get_last_state = get_last_state
    asyncio.run(sensor.async_added_to_hass())

    assert "sensor.oud_apparaat" in coordinator.nilm_confirmed_devices
    assert "sensor.genegeerd" in coordinator.nilm_rejected_entities
    stored = hass._fake_store_backing.get(
        "energy_management_system_nilm_confirmed_devices"
    )
    assert "sensor.oud_apparaat" in stored["nilm_confirmed_devices"]


def test_sensor_does_not_migrate_when_store_already_has_data(make_coordinator, hass):
    """If the Store already had data (loaded during coordinator.
    async_setup(), simulated here directly), the entity's restored
    state must NOT override it."""

    class _FakeLastState:
        attributes = {
            "apparaten": {
                "sensor.stale": {"friendly_name": "Stale (should not win)"}
            },
        }

    coordinator = make_coordinator({})
    coordinator.nilm_confirmed_devices["sensor.from_store"] = {
        "friendly_name": "From store"
    }
    sensor = NilmConfirmedDevicesSensor(coordinator, "entry1")

    async def get_last_state():
        return _FakeLastState()

    sensor.async_get_last_state = get_last_state
    asyncio.run(sensor.async_added_to_hass())

    assert "sensor.from_store" in coordinator.nilm_confirmed_devices
    assert "sensor.stale" not in coordinator.nilm_confirmed_devices


def test_finalizing_a_device_day_saves_to_the_store(make_coordinator, hass):
    coordinator = make_coordinator({})
    hass.states.set("sensor.koelkast", "10")
    coordinator.nilm_confirmed_devices["sensor.koelkast"] = {
        "friendly_name": "Koelkast",
        "confirmed_at": "2026-08-01",
        "daily_avg_history": [],
        "cusum_accumulator": 0.0,
        "anomaly_detected": False,
        "estimated_drift_percent": None,
        "reference_avg_w": None,
        "_today_sum": 50.0,
        "_today_count": 5,
        "_check_date": DAY0.date(),
    }

    async def run():
        coordinator._update_nilm_confirmed_devices(DAY0 + timedelta(days=1))
        await asyncio.sleep(0)

    asyncio.run(run())

    stored = hass._fake_store_backing.get(
        "energy_management_system_nilm_confirmed_devices"
    )
    assert stored is not None
    assert stored["nilm_confirmed_devices"]["sensor.koelkast"]["daily_avg_history"]


def test_unconfirm_removes_device_without_blacklisting(make_coordinator, hass):
    """v0.63.68, requested ('hoe kan ik een NILM apparaat verwijderen
    en opnieuw beoordelen?') - unlike reject_nilm_device, this must NOT
    add the entity to nilm_rejected_entities, so a future discovery
    scan is free to surface it again as a fresh candidate."""
    coordinator = make_coordinator({})
    coordinator.nilm_confirmed_devices["sensor.oude_koelkast"] = {
        "friendly_name": "Oude koelkast",
        "daily_avg_history": [80.0, 82.0],
    }

    result = coordinator.unconfirm_nilm_device("sensor.oude_koelkast")

    assert result is True
    assert "sensor.oude_koelkast" not in coordinator.nilm_confirmed_devices
    assert "sensor.oude_koelkast" not in coordinator.nilm_rejected_entities


def test_unconfirm_returns_false_when_not_confirmed(make_coordinator, hass):
    coordinator = make_coordinator({})

    result = coordinator.unconfirm_nilm_device("sensor.niet_bevestigd")

    assert result is False


def test_unconfirmed_device_reappears_as_a_fresh_candidate(make_coordinator, hass):
    """Confirms the actual point of this feature: after unconfirm, the
    device is eligible for discovery again (unlike after reject)."""
    from datetime import datetime, timezone

    coordinator = make_coordinator({})
    hass.states.set(
        "sensor.oude_koelkast",
        "80",
        {"unit_of_measurement": "W", "friendly_name": "Oude koelkast"},
    )
    coordinator.nilm_confirmed_devices["sensor.oude_koelkast"] = {
        "friendly_name": "Oude koelkast",
        "daily_avg_history": [80.0, 82.0],
    }

    coordinator.unconfirm_nilm_device("sensor.oude_koelkast")
    coordinator._update_nilm_discovery(datetime(2026, 8, 4, tzinfo=timezone.utc))

    assert "sensor.oude_koelkast" in coordinator.nilm_unconfirmed_candidates


def test_unconfirm_saves_to_the_store(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.nilm_confirmed_devices["sensor.oude_koelkast"] = {
        "friendly_name": "Oude koelkast",
        "daily_avg_history": [80.0, 82.0],
    }

    async def run():
        coordinator.unconfirm_nilm_device("sensor.oude_koelkast")
        await asyncio.sleep(0)

    asyncio.run(run())

    stored = hass._fake_store_backing.get(
        "energy_management_system_nilm_confirmed_devices"
    )
    assert stored is not None
    assert "sensor.oude_koelkast" not in stored["nilm_confirmed_devices"]
