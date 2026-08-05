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


def test_button_name_shows_the_candidate_directly(make_coordinator, hass):
    """v0.63.43: the entity's own name should contain the candidate's
    name/power, so nothing needs cross-referencing against a separate
    table - reported: a static generic label plus a table got
    truncated and unusable on a narrow dashboard."""
    from custom_components.energy_management_system.button import (
        NilmConfirmCandidateButton,
        NilmRejectCandidateButton,
    )

    coordinator = make_coordinator({})
    _seed_two_candidates(hass, coordinator)

    confirm_button = NilmConfirmCandidateButton(coordinator, "entry1", slot=0)
    reject_button = NilmRejectCandidateButton(coordinator, "entry1", slot=0)

    assert "A-apparaat" in confirm_button.name
    assert "20" in confirm_button.name  # its power, 20W
    assert "A-apparaat" in reject_button.name


def test_button_name_for_an_empty_slot(make_coordinator, hass):
    from custom_components.energy_management_system.button import (
        NilmConfirmCandidateButton,
    )

    coordinator = make_coordinator({})
    button = NilmConfirmCandidateButton(coordinator, "entry1", slot=0)

    assert "leeg" in button.name.lower()


def test_has_entity_name_is_off_to_avoid_device_prefix_truncation(
    make_coordinator, hass
):
    """v0.63.47, reported: with has_entity_name on, Home Assistant
    prefixes the display name with the device name ("Energy Management
    System ..."), which truncated to just "E..." in a narrow name
    column - defeating the point of showing the candidate directly in
    the name."""
    from custom_components.energy_management_system.button import (
        NilmConfirmCandidateButton,
        NilmRejectCandidateButton,
    )

    coordinator = make_coordinator({})
    confirm_button = NilmConfirmCandidateButton(coordinator, "entry1", slot=0)
    reject_button = NilmRejectCandidateButton(coordinator, "entry1", slot=0)

    assert getattr(confirm_button, "_attr_has_entity_name", False) is False
    assert getattr(reject_button, "_attr_has_entity_name", False) is False


def test_button_registers_as_a_coordinator_listener_on_added(make_coordinator, hass):
    """v0.63.48, reported: slots stayed empty/stale indefinitely.
    ButtonEntity doesn't poll by default, so without an explicit push
    the button's displayed name/attributes never refreshed. Confirms
    the button registers `async_write_ha_state` as a coordinator
    listener when added to hass."""
    import asyncio

    from custom_components.energy_management_system.button import (
        NilmConfirmCandidateButton,
    )

    coordinator = make_coordinator({})
    button = NilmConfirmCandidateButton(coordinator, "entry1", slot=0)

    asyncio.run(button.async_added_to_hass())

    assert button.async_write_ha_state in coordinator._listeners


def test_button_unregisters_on_removal(make_coordinator, hass):
    import asyncio

    from custom_components.energy_management_system.button import (
        NilmConfirmCandidateButton,
    )

    coordinator = make_coordinator({})
    button = NilmConfirmCandidateButton(coordinator, "entry1", slot=0)

    asyncio.run(button.async_added_to_hass())
    asyncio.run(button.async_will_remove_from_hass())

    assert button.async_write_ha_state not in coordinator._listeners


def test_coordinator_notifies_listeners_even_on_an_early_return(make_coordinator, hass):
    """The real _async_update_locked has many early `return` points for
    different decision branches - notification must happen regardless
    of which one fires, via the `finally` in async_update()."""
    import asyncio

    coordinator = make_coordinator({})
    calls = []
    coordinator.register_listener(lambda: calls.append(1))

    async def fake_locked():
        return  # simulates an early-return decision branch

    coordinator._async_update_locked = fake_locked
    asyncio.run(coordinator.async_update())

    assert calls == [1]


def test_coordinator_notifies_listeners_even_after_an_exception(make_coordinator, hass):
    import asyncio

    coordinator = make_coordinator({})
    calls = []
    coordinator.register_listener(lambda: calls.append(1))

    async def broken_locked():
        raise ValueError("boom")

    coordinator._async_update_locked = broken_locked
    asyncio.run(coordinator.async_update())

    assert calls == [1]
