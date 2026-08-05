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


def test_confirming_immediately_notifies_the_sibling_reject_button(
    make_coordinator, hass
):
    """v0.63.50, reported: after pressing confirm/reject on one slot's
    button, the sibling button (the other action for that same slot)
    kept showing the old candidate until the next 5-minute update tick
    - a button press only auto-writes its own state, not its sibling's.
    Confirm the coordinator now pushes an immediate refresh to every
    registered listener when a candidate is confirmed/rejected."""
    coordinator = make_coordinator({})
    _seed_two_candidates(hass, coordinator)

    calls = []
    coordinator.register_listener(lambda: calls.append(1))

    coordinator.confirm_nilm_device("sensor.a_apparaat")

    assert calls == [1]


def test_rejecting_immediately_notifies_all_registered_listeners(
    make_coordinator, hass
):
    coordinator = make_coordinator({})
    _seed_two_candidates(hass, coordinator)

    calls = []
    coordinator.register_listener(lambda: calls.append("a"))
    coordinator.register_listener(lambda: calls.append("b"))

    coordinator.reject_nilm_device("sensor.b_apparaat")

    assert calls == ["a", "b"]


def test_slot_sibling_shows_the_shifted_candidate_right_after_a_press(
    make_coordinator, hass
):
    """End-to-end: two confirm-button instances for the same slot both
    reflect the shift immediately after one of them (or the reject
    button) is pressed - not just the one that was pressed."""
    from custom_components.energy_management_system.button import (
        NilmConfirmCandidateButton,
        NilmRejectCandidateButton,
    )

    coordinator = make_coordinator({})
    _seed_two_candidates(hass, coordinator)

    confirm_slot0 = NilmConfirmCandidateButton(coordinator, "entry1", slot=0)
    reject_slot0 = NilmRejectCandidateButton(coordinator, "entry1", slot=0)
    assert confirm_slot0.extra_state_attributes["kandidaat_entity_id"] == (
        "sensor.a_apparaat"
    )
    assert reject_slot0.extra_state_attributes["kandidaat_entity_id"] == (
        "sensor.a_apparaat"
    )

    asyncio.run(reject_slot0.async_press())

    # Both buttons for slot 0 must now reflect the shifted candidate -
    # neither is "stale" just because it wasn't the one pressed.
    assert confirm_slot0.extra_state_attributes["kandidaat_entity_id"] == (
        "sensor.b_apparaat"
    )
    assert reject_slot0.extra_state_attributes["kandidaat_entity_id"] == (
        "sensor.b_apparaat"
    )


def test_confirm_button_has_a_stable_entity_id_regardless_of_name(
    make_coordinator, hass
):
    """v0.63.74/.79, reported ('kan niet beoordelen afwijzen etc van
    nieuwe apparaten' - nothing rendered under 'Bevestigen / negeren' at
    all, twice: v0.63.74's _attr_suggested_object_id fix turned out to
    not be a real Home Assistant attribute): without an explicit,
    directly-set entity_id, Home Assistant would derive the entity_id
    from this entity's DYNAMIC `name` property at first registration,
    producing an unpredictable entity_id that never matched what the
    bundled dashboard hardcodes. entity_id must be stable and based
    purely on the fixed slot number, never on whatever candidate
    currently occupies it.
    """
    from custom_components.energy_management_system.button import (
        NilmConfirmCandidateButton,
    )

    coordinator = make_coordinator({})
    # Populate slot 0 with a real candidate - the entity_id must NOT
    # reflect this at all.
    hass.states.set(
        "sensor.koelkast",
        "82",
        {"unit_of_measurement": "W", "friendly_name": "Koelkast"},
    )
    coordinator._update_nilm_discovery(
        __import__("datetime").datetime(2026, 8, 4, tzinfo=__import__("datetime").timezone.utc)
    )
    button = NilmConfirmCandidateButton(coordinator, "entry1", slot=0)

    assert button.entity_id == (
        "button.woonkamer_energy_management_system_nilm_kandidaat_1_bevestigen"
    )
    # The dynamic name may show the candidate, but the entity_id must not.
    assert "koelkast" not in button.entity_id.lower()


def test_reject_button_has_a_stable_entity_id(make_coordinator, hass):
    from custom_components.energy_management_system.button import (
        NilmRejectCandidateButton,
    )

    coordinator = make_coordinator({})
    button = NilmRejectCandidateButton(coordinator, "entry1", slot=2)

    assert button.entity_id == (
        "button.woonkamer_energy_management_system_nilm_kandidaat_3_negeren"
    )


def test_unique_id_bumped_to_force_a_fresh_registration(make_coordinator, hass):
    """v0.63.80/.81, reported ('Je kunt enkel 0 van de 16 entiteiten
    verwijderen', then still showing a "_2"-suffixed entity_id even
    after deleting the v1 entities) - Home Assistant blocks manually
    deleting entities still actively provided by a loaded integration,
    and even a restart alone wouldn't re-apply a new entity_id for an
    already-registered unique_id (the registry looks up the existing
    entry by unique_id first). Once a "_2"-deduplicated entity_id gets
    assigned for a given unique_id, that's permanent - it never
    upgrades back to the plain name later. The unique_id must carry a
    "_v3" suffix so Home Assistant has no matching registry entry at
    all and genuinely re-registers these buttons fresh."""
    from custom_components.energy_management_system.button import (
        NilmConfirmCandidateButton,
        NilmRejectCandidateButton,
    )

    coordinator = make_coordinator({})
    confirm = NilmConfirmCandidateButton(coordinator, "entry1", slot=0)
    reject = NilmRejectCandidateButton(coordinator, "entry1", slot=0)

    assert confirm._attr_unique_id.endswith("_v3")
    assert reject._attr_unique_id.endswith("_v3")
    assert confirm._attr_unique_id != reject._attr_unique_id


def test_all_16_slot_entity_ids_are_unique_and_match_the_dashboard(
    make_coordinator, hass
):
    """Confirms the entity_ids exactly match what the bundled dashboard
    YAML hardcodes (button.woonkamer_energy_management_system_
    nilm_kandidaat_N_bevestigen/negeren)."""
    import asyncio as aio

    from custom_components.energy_management_system.button import async_setup_entry
    from custom_components.energy_management_system.const import DOMAIN

    coordinator = make_coordinator({})
    hass.data = {DOMAIN: {"entry1": coordinator}}

    class _FakeEntry:
        entry_id = "entry1"

    added = []

    def fake_add_entities(entities):
        added.extend(entities)

    aio.run(async_setup_entry(hass, _FakeEntry(), fake_add_entities))

    entity_ids = [
        e.entity_id
        for e in added
        if getattr(e, "entity_id", None) is not None
        and "nilm_kandidaat" in e.entity_id
    ]

    assert len(entity_ids) == len(set(entity_ids)) == 16
    for slot in range(1, 9):
        assert (
            f"button.woonkamer_energy_management_system_nilm_kandidaat_"
            f"{slot}_bevestigen" in entity_ids
        )
        assert (
            f"button.woonkamer_energy_management_system_nilm_kandidaat_"
            f"{slot}_negeren" in entity_ids
        )
