"""NILM unconfirmed-candidates sensor attribute size cap (v0.63.45).

Reported: with the broad "any W/kW sensor" discovery scope, the full
candidates dict can exceed Home Assistant's 16KB per-attribute recorder
limit, which then silently drops the attribute entirely instead of
truncating it. The sensor now exposes a bounded preview instead of the
raw dict - the underlying discovery/confirm/reject functionality itself
is unaffected by this cap.
"""
from datetime import datetime, timezone

from custom_components.energy_management_system.const import (
    NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT,
)
from custom_components.energy_management_system.sensor import (
    NilmUnconfirmedCandidatesSensor,
)

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _seed_many_candidates(hass, coordinator, count):
    for i in range(count):
        entity_id = f"sensor.apparaat_{i:03d}"
        hass.states.set(
            entity_id,
            "10",
            {"unit_of_measurement": "W", "friendly_name": f"Apparaat {i}"},
        )
    coordinator._update_nilm_discovery(DAY0)


def test_native_value_shows_the_true_total_even_when_over_the_preview_limit(
    make_coordinator, hass
):
    coordinator = make_coordinator({})
    _seed_many_candidates(hass, coordinator, NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT + 15)

    sensor = NilmUnconfirmedCandidatesSensor(coordinator, "entry1")

    assert sensor.native_value == NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT + 15
    assert sensor.extra_state_attributes["totaal_aantal"] == (
        NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT + 15
    )


def test_attribute_preview_bounded_when_over_the_limit(make_coordinator, hass):
    coordinator = make_coordinator({})
    _seed_many_candidates(hass, coordinator, NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT + 15)

    sensor = NilmUnconfirmedCandidatesSensor(coordinator, "entry1")

    assert len(sensor.extra_state_attributes["kandidaten"]) == (
        NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT
    )
    assert "diagnostiek" in sensor.extra_state_attributes["note"].lower()


def test_attribute_shows_everything_when_under_the_limit(make_coordinator, hass):
    coordinator = make_coordinator({})
    _seed_many_candidates(hass, coordinator, 3)

    sensor = NilmUnconfirmedCandidatesSensor(coordinator, "entry1")

    assert len(sensor.extra_state_attributes["kandidaten"]) == 3
    assert "diagnostiek" not in sensor.extra_state_attributes["note"].lower()


def test_preview_is_the_alphabetically_first_candidates(make_coordinator, hass):
    """Same deterministic ordering as the dashboard confirm/reject
    slots, so the preview and the slots stay consistent with each
    other."""
    coordinator = make_coordinator({})
    _seed_many_candidates(hass, coordinator, NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT + 5)

    sensor = NilmUnconfirmedCandidatesSensor(coordinator, "entry1")
    preview_ids = sorted(sensor.extra_state_attributes["kandidaten"].keys())

    assert preview_ids == sorted(coordinator.nilm_unconfirmed_candidates.keys())[
        :NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT
    ]


def test_attribute_size_stays_well_under_the_recorder_limit(make_coordinator, hass):
    """A rough but meaningful regression guard: even with a large
    number of discovered candidates, the serialised attribute stays
    comfortably under Home Assistant's 16KB recorder limit."""
    import json

    coordinator = make_coordinator({})
    _seed_many_candidates(hass, coordinator, 500)

    sensor = NilmUnconfirmedCandidatesSensor(coordinator, "entry1")
    serialised = json.dumps(sensor.extra_state_attributes)

    assert len(serialised.encode("utf-8")) < 16384
