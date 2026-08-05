"""NILM confirm/reject dashboard buttons (v0.63.41): a fixed number of
slot-pairs (NILM_DASHBOARD_SLOT_COUNT), since a static Lovelace
dashboard can't render one button per candidate for an unknown-length,
changing list. Each slot shows/acts on whichever candidate currently
occupies that alphabetically-sorted position.
"""
import asyncio
from datetime import datetime, timezone

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _seed_two_candidates(hass, coordinator):
    hass.states.set(
        "sensor.b_apparaat",
        "40",
        {"unit_of_measurement": "W", "friendly_name": "B-apparaat"},
    )
    hass.states.set(
        "sensor.a_apparaat",
        "20",
        {"unit_of_measurement": "W", "friendly_name": "A-apparaat"},
    )
    coordinator._update_nilm_discovery(DAY0)


def test_slot_shows_the_alphabetically_first_candidate(make_coordinator, hass):
    from custom_components.energy_management_system.button import (
        NilmConfirmCandidateButton,
    )

    coordinator = make_coordinator({})
    _seed_two_candidates(hass, coordinator)

    button = NilmConfirmCandidateButton(coordinator, "entry1", slot=0)

    assert button.extra_state_attributes["kandidaat_entity_id"] == "sensor.a_apparaat"
    assert button.extra_state_attributes["kandidaat_naam"] == "A-apparaat"


def test_empty_slot_shows_no_candidate(make_coordinator, hass):
    from custom_components.energy_management_system.button import (
        NilmConfirmCandidateButton,
    )

    coordinator = make_coordinator({})
    button = NilmConfirmCandidateButton(coordinator, "entry1", slot=0)

    assert button.extra_state_attributes["kandidaat_entity_id"] is None


def test_confirm_button_confirms_the_slotted_candidate(make_coordinator, hass):
    from custom_components.energy_management_system.button import (
        NilmConfirmCandidateButton,
    )

    coordinator = make_coordinator({})
    _seed_two_candidates(hass, coordinator)

    button = NilmConfirmCandidateButton(coordinator, "entry1", slot=0)
    asyncio.run(button.async_press())

    assert "sensor.a_apparaat" in coordinator.nilm_confirmed_devices
    assert "sensor.a_apparaat" not in coordinator.nilm_unconfirmed_candidates


def test_reject_button_rejects_the_slotted_candidate(make_coordinator, hass):
    from custom_components.energy_management_system.button import (
        NilmRejectCandidateButton,
    )

    coordinator = make_coordinator({})
    _seed_two_candidates(hass, coordinator)

    button = NilmRejectCandidateButton(coordinator, "entry1", slot=1)
    asyncio.run(button.async_press())

    assert "sensor.b_apparaat" in coordinator.nilm_rejected_entities
    assert "sensor.b_apparaat" not in coordinator.nilm_unconfirmed_candidates


def test_pressing_an_empty_slot_does_nothing(make_coordinator, hass):
    from custom_components.energy_management_system.button import (
        NilmConfirmCandidateButton,
    )

    coordinator = make_coordinator({})
    button = NilmConfirmCandidateButton(coordinator, "entry1", slot=0)

    asyncio.run(button.async_press())  # must not raise

    assert coordinator.nilm_confirmed_devices == {}


def test_slots_shift_after_a_candidate_is_confirmed(make_coordinator, hass):
    from custom_components.energy_management_system.button import (
        NilmConfirmCandidateButton,
    )

    coordinator = make_coordinator({})
    _seed_two_candidates(hass, coordinator)

    slot0 = NilmConfirmCandidateButton(coordinator, "entry1", slot=0)
    slot1 = NilmConfirmCandidateButton(coordinator, "entry1", slot=1)
    assert slot0.extra_state_attributes["kandidaat_entity_id"] == "sensor.a_apparaat"
    assert slot1.extra_state_attributes["kandidaat_entity_id"] == "sensor.b_apparaat"

    asyncio.run(slot0.async_press())  # confirms sensor.a_apparaat

    # sensor.b_apparaat should now have shifted into slot 0.
    assert slot0.extra_state_attributes["kandidaat_entity_id"] == "sensor.b_apparaat"
    assert slot1.extra_state_attributes["kandidaat_entity_id"] is None


def test_setup_registers_all_slot_buttons(make_coordinator, hass):
    import asyncio as aio

    from custom_components.energy_management_system.button import async_setup_entry
    from custom_components.energy_management_system.const import (
        DOMAIN,
        NILM_DASHBOARD_SLOT_COUNT,
    )

    coordinator = make_coordinator({})
    hass.data = {DOMAIN: {"entry1": coordinator}}

    class _FakeEntry:
        entry_id = "entry1"

    added = []

    def fake_add_entities(entities):
        added.extend(entities)

    aio.run(async_setup_entry(hass, _FakeEntry(), fake_add_entities))

    # 1 test-notification button + (confirm+reject) x N slots.
    assert len(added) == 1 + 2 * NILM_DASHBOARD_SLOT_COUNT
