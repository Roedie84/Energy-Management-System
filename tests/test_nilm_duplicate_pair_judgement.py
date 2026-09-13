"""Duplicaatparen kunnen worden beoordeeld en blijven weg (v0.63.118).

Gevraagd: "NILM apparaten kan ik bevestigen danwel negeren, dit kan nog
niet met de waarschijnlijke duplicaten - kun je hiervoor een zelfde
optie maken zodat ik ook dit kan afwijzen, en dit dan ook daadwerkelijk
niet meer terug komt als mogelijk duplicaat?"

Twee acties, spiegelbeeld van confirm/reject bij losse apparaten:
- bevestigen: het is echt hetzelfde signaal -> tweede apparaat wordt
  permanent uitgesloten, zodat hetzelfde verbruik niet dubbel geteld
  blijft worden;
- negeren: het is GEEN duplicaat -> het paar verdwijnt permanent uit de
  suggesties, beide apparaten blijven gewoon bestaan.

De nadruk in de klacht ligt op "daadwerkelijk niet meer terug komt",
dus de herstart-borging is hier het belangrijkste.
"""
import asyncio

from custom_components.energy_management_system.button import (
    NilmConfirmDuplicateButton,
    NilmDismissDuplicateButton,
)

STORE_KEY = "energy_management_system_nilm_confirmed_devices"
HISTORY = [1.0, 1.0, 1.0, 1.0]


def _device(naam):
    return {
        "friendly_name": naam,
        "daily_avg_history": list(HISTORY),
        "anomaly_detected": False,
    }


def _with_pair(coordinator):
    coordinator.nilm_confirmed_devices = {
        "sensor.lamp_a": _device("Lamp A"),
        "sensor.lamp_b": _device("Lamp B"),
    }
    return coordinator


def test_duplicate_pair_is_detected_before_judgement(make_coordinator, hass):
    coordinator = _with_pair(make_coordinator({}))

    assert len(coordinator.get_nilm_duplicate_pairs()) == 1


def test_dismissing_removes_the_pair_from_the_list(make_coordinator, hass):
    coordinator = _with_pair(make_coordinator({}))

    coordinator.dismiss_nilm_duplicate_pair("sensor.lamp_a", "sensor.lamp_b")

    assert coordinator.get_nilm_duplicate_pairs() == []


def test_dismissing_keeps_both_devices_confirmed(make_coordinator, hass):
    """Afwijzen betekent 'geen duplicaat', niet 'weg met een apparaat'."""
    coordinator = _with_pair(make_coordinator({}))

    coordinator.dismiss_nilm_duplicate_pair("sensor.lamp_a", "sensor.lamp_b")

    assert "sensor.lamp_a" in coordinator.nilm_confirmed_devices
    assert "sensor.lamp_b" in coordinator.nilm_confirmed_devices
    assert coordinator.nilm_rejected_entities == []


def test_dismissal_is_direction_independent(make_coordinator, hass):
    """Omgedraaide volgorde mag het paar niet laten terugkomen."""
    coordinator = _with_pair(make_coordinator({}))

    coordinator.dismiss_nilm_duplicate_pair("sensor.lamp_b", "sensor.lamp_a")

    assert coordinator.get_nilm_duplicate_pairs() == []


def test_dismissing_twice_is_a_no_op(make_coordinator, hass):
    coordinator = _with_pair(make_coordinator({}))

    eerste = coordinator.dismiss_nilm_duplicate_pair("sensor.lamp_a", "sensor.lamp_b")
    tweede = coordinator.dismiss_nilm_duplicate_pair("sensor.lamp_a", "sensor.lamp_b")

    assert eerste is True
    assert tweede is False
    assert len(coordinator.nilm_dismissed_duplicate_pairs) == 1


def test_dismissal_is_saved_to_the_store(make_coordinator, hass):
    coordinator = _with_pair(make_coordinator({}))

    async def run():
        coordinator.dismiss_nilm_duplicate_pair("sensor.lamp_a", "sensor.lamp_b")
        await asyncio.sleep(0)

    asyncio.run(run())

    stored = hass._fake_store_backing[STORE_KEY]
    assert stored["nilm_dismissed_duplicate_pairs"] == ["sensor.lamp_a|sensor.lamp_b"]


def test_dismissed_pair_does_not_return_after_a_restart(make_coordinator, hass):
    """De kern van de klacht."""
    coordinator = _with_pair(make_coordinator({}))

    async def run():
        coordinator.dismiss_nilm_duplicate_pair("sensor.lamp_a", "sensor.lamp_b")
        await asyncio.sleep(0)

    asyncio.run(run())

    verse = _with_pair(make_coordinator({}))
    asyncio.run(verse.async_load_persisted_nilm_state())

    assert verse.get_nilm_duplicate_pairs() == []


def test_dismissal_survives_five_restarts(make_coordinator, hass):
    coordinator = _with_pair(make_coordinator({}))

    async def run():
        coordinator.dismiss_nilm_duplicate_pair("sensor.lamp_a", "sensor.lamp_b")
        await asyncio.sleep(0)

    asyncio.run(run())

    for _ in range(5):
        coordinator = _with_pair(make_coordinator({}))
        asyncio.run(coordinator.async_load_persisted_nilm_state())

    assert coordinator.get_nilm_duplicate_pairs() == []


def test_other_pairs_are_unaffected_by_a_dismissal(make_coordinator, hass):
    """Afwijzen mag alleen dat ene paar raken, niet alles."""
    coordinator = make_coordinator({})
    coordinator.nilm_confirmed_devices = {
        "sensor.lamp_a": _device("Lamp A"),
        "sensor.lamp_b": _device("Lamp B"),
        "sensor.lamp_c": _device("Lamp C"),
    }
    assert len(coordinator.get_nilm_duplicate_pairs()) == 3

    coordinator.dismiss_nilm_duplicate_pair("sensor.lamp_a", "sensor.lamp_b")

    resterend = coordinator.get_nilm_duplicate_pairs()
    assert len(resterend) == 2
    sleutels = {(p["entity_id_1"], p["entity_id_2"]) for p in resterend}
    assert ("sensor.lamp_a", "sensor.lamp_b") not in sleutels


def test_confirming_excludes_the_second_device(make_coordinator, hass):
    coordinator = _with_pair(make_coordinator({}))

    resultaat = coordinator.confirm_nilm_duplicate_pair(
        "sensor.lamp_a", "sensor.lamp_b"
    )

    assert resultaat is True
    assert "sensor.lamp_a" in coordinator.nilm_confirmed_devices
    assert "sensor.lamp_b" not in coordinator.nilm_confirmed_devices
    assert "sensor.lamp_b" in coordinator.nilm_rejected_entities
    assert coordinator.get_nilm_duplicate_pairs() == []


def test_confirming_blacklists_so_it_is_not_rediscovered(make_coordinator, hass):
    """Het uitgesloten apparaat mag niet terugkomen als verse kandidaat."""
    from datetime import datetime, timezone

    coordinator = _with_pair(make_coordinator({}))
    hass.states.set(
        "sensor.lamp_b",
        "5",
        {"unit_of_measurement": "W", "friendly_name": "Lamp B"},
    )

    coordinator.confirm_nilm_duplicate_pair("sensor.lamp_a", "sensor.lamp_b")
    coordinator._update_nilm_discovery(datetime(2026, 8, 6, tzinfo=timezone.utc))

    assert "sensor.lamp_b" not in coordinator.nilm_unconfirmed_candidates


def test_confirming_an_unknown_device_returns_false(make_coordinator, hass):
    coordinator = _with_pair(make_coordinator({}))

    assert (
        coordinator.confirm_nilm_duplicate_pair("sensor.lamp_a", "sensor.bestaat_niet")
        is False
    )


def test_slot_lookup_returns_none_when_nothing_to_judge(make_coordinator, hass):
    coordinator = make_coordinator({})

    assert coordinator.get_nilm_duplicate_pair_at_slot(0) is None


def test_slot_lookup_returns_the_pair(make_coordinator, hass):
    coordinator = _with_pair(make_coordinator({}))

    paar = coordinator.get_nilm_duplicate_pair_at_slot(0)

    assert paar["entity_id_1"] == "sensor.lamp_a"
    assert paar["entity_id_2"] == "sensor.lamp_b"


def test_dismiss_button_names_both_devices(make_coordinator, hass):
    coordinator = _with_pair(make_coordinator({}))
    knop = NilmDismissDuplicateButton(coordinator, "entry1", 0)

    assert "Lamp A" in knop.name
    assert "Lamp B" in knop.name


def test_confirm_button_names_the_device_that_disappears(make_coordinator, hass):
    """Vooraf zichtbaar WELK apparaat verdwijnt - niet laten raden."""
    coordinator = _with_pair(make_coordinator({}))
    knop = NilmConfirmDuplicateButton(coordinator, "entry1", 0)

    assert "Lamp B" in knop.name


def test_empty_slot_buttons_say_so(make_coordinator, hass):
    coordinator = make_coordinator({})

    assert "leeg" in NilmDismissDuplicateButton(coordinator, "entry1", 0).name
    assert "leeg" in NilmConfirmDuplicateButton(coordinator, "entry1", 0).name


def test_dismiss_button_press_uses_the_displayed_pair(make_coordinator, hass):
    """v0.63.107-les: druk op wat er GETOOND is, niet op een verse
    opvraag - anders beoordeelt de gebruiker een ander paar dan hij zag.
    """
    coordinator = _with_pair(make_coordinator({}))
    knop = NilmDismissDuplicateButton(coordinator, "entry1", 0)
    knop.name  # weergave legt het paar vast

    # De sleuf verschuift ondertussen naar een heel ander paar.
    coordinator.nilm_confirmed_devices = {
        "sensor.aaa": _device("Aaa"),
        "sensor.zzz": _device("Zzz"),
    }

    asyncio.run(knop.async_press())

    assert coordinator.nilm_dismissed_duplicate_pairs == [
        "sensor.lamp_a|sensor.lamp_b"
    ]


def test_confirm_button_press_uses_the_displayed_pair(make_coordinator, hass):
    coordinator = _with_pair(make_coordinator({}))
    knop = NilmConfirmDuplicateButton(coordinator, "entry1", 0)
    knop.name

    asyncio.run(knop.async_press())

    assert "sensor.lamp_b" in coordinator.nilm_rejected_entities


def test_buttons_have_stable_entity_ids(make_coordinator, hass):
    """Het gebundelde dashboard spreekt deze entity_ids hard aan."""
    coordinator = make_coordinator({})

    assert NilmConfirmDuplicateButton(coordinator, "entry1", 0).entity_id == (
        "button.woonkamer_energy_management_system_nilm_duplicaat_1_bevestigen"
    )
    assert NilmDismissDuplicateButton(coordinator, "entry1", 0).entity_id == (
        "button.woonkamer_energy_management_system_nilm_duplicaat_1_negeren"
    )



def test_the_duplicate_buttons_still_exist(make_coordinator, hass):
    """v1.12.0: de dashboardtabel met duplicaten is vervallen (te druk),
    maar de knoppen om een paar te beoordelen moeten blijven bestaan -
    anders is een gemeld duplicaat niet meer af te handelen."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "button.py").read_text()

    assert "duplicate" in bron.lower()
