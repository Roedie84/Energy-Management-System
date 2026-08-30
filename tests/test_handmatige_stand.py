"""Twee knoppen om de accu met de hand aan te sturen (v3.77.0).

Gevraagd: "Ik zou hier graag 2 buttons bij hebben - Manual 2000W laden
en Smart_charge. Dit zorgt ervoor dat ik de Zendure app niet meer nodig
heb. Tevens wanneer 1 van deze buttons actief is moet de learning button
ingeschakeld worden, bij uitschakeling weer uit. Als hij manueel is
geschakeld wil ik elk heel uur een herinnering. Wanneer de accu 100% is
mogen de buttons door de integratie worden uitgeschakeld en de learning
button ook uit."

Vier dingen die bij elkaar horen, en één valkuil: de leermodus is ook
een eigen schakelaar van de gebruiker. Had die al aangestaan, dan mag
hij straks niet stilzwijgend uitgezet worden.
"""
from datetime import datetime, timedelta

import pytest

from custom_components.energy_management_system.const import (
    HANDMATIGE_STAND_HERINNERING_MINUTEN,
    HANDMATIGE_STAND_LADEN,
    HANDMATIGE_STAND_SMART_CHARGE,
    HANDMATIG_LAADVERMOGEN_W,
)

NU = datetime(2026, 8, 30, 11, 0)


def _run(coro):
    import asyncio

    return asyncio.new_event_loop().run_until_complete(coro)


def _coordinator(make_coordinator):
    c = make_coordinator({})
    c._async_apply_manual = _volg(c, "manual")
    c._async_apply_operation = _volg(c, "operation")
    return c


def _volg(c, soort):
    c.aangeroepen = getattr(c, "aangeroepen", [])

    async def _f(waarde):
        c.aangeroepen.append((soort, waarde))

    return _f


# --- de accu krijgt de stand -----------------------------------------


def test_charging_applies_2000_watt(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    _run(c.async_set_handmatige_stand(HANDMATIGE_STAND_LADEN, NU))

    assert ("manual", -HANDMATIG_LAADVERMOGEN_W) in c.aangeroepen
    assert c.handmatige_stand == HANDMATIGE_STAND_LADEN


def test_smart_charge_applies_that_mode(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    _run(c.async_set_handmatige_stand(HANDMATIGE_STAND_SMART_CHARGE, NU))

    assert ("operation", "smart_charging") in c.aangeroepen


def test_the_two_modes_exclude_each_other(make_coordinator, hass):
    """De accu kan maar in één stand staan."""
    c = _coordinator(make_coordinator)

    _run(c.async_set_handmatige_stand(HANDMATIGE_STAND_LADEN, NU))
    _run(c.async_set_handmatige_stand(HANDMATIGE_STAND_SMART_CHARGE, NU))

    assert c.handmatige_stand == HANDMATIGE_STAND_SMART_CHARGE


# --- de leermodus, en de valkuil -------------------------------------


def test_it_switches_learning_on(make_coordinator, hass):
    """Anders vecht de aansturing van EMS er elke ronde tegenin."""
    c = _coordinator(make_coordinator)
    c.learning_only = False

    _run(c.async_set_handmatige_stand(HANDMATIGE_STAND_LADEN, NU))

    assert c.learning_only is True


def test_it_switches_learning_back_off(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c.learning_only = False

    _run(c.async_set_handmatige_stand(HANDMATIGE_STAND_LADEN, NU))
    _run(c.async_set_handmatige_stand(None, NU))

    assert c.learning_only is False


def test_a_learning_mode_the_user_set_himself_stays_on(
    make_coordinator, hass
):
    """DE VALKUIL. Had de gebruiker de leermodus zelf al aan, dan mag

    deze schakelaar hem niet stilzwijgend uitzetten - dan zou een
    handmatige laadsessie ongemerkt de aansturing weer aanzetten.
    """
    c = _coordinator(make_coordinator)
    c.learning_only = True

    _run(c.async_set_handmatige_stand(HANDMATIGE_STAND_LADEN, NU))
    _run(c.async_set_handmatige_stand(None, NU))

    assert c.learning_only is True


# --- de herinnering per uur ------------------------------------------


def test_a_reminder_every_hour(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c.accustand_procent = lambda: 40.0
    meldingen = []
    c._dispatch_notification = lambda **kw: meldingen.append(kw)

    _run(c.async_set_handmatige_stand(HANDMATIGE_STAND_LADEN, NU))
    _run(c._volg_handmatige_stand(NU + timedelta(minutes=30)))
    assert meldingen == []

    _run(
        c._volg_handmatige_stand(
            NU + timedelta(minutes=HANDMATIGE_STAND_HERINNERING_MINUTEN + 1)
        )
    )
    assert len(meldingen) == 1
    assert "handmatig" in meldingen[0]["title"].lower()


def test_no_reminder_when_nothing_is_manual(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    meldingen = []
    c._dispatch_notification = lambda **kw: meldingen.append(kw)

    _run(c._volg_handmatige_stand(NU))

    assert meldingen == []


# --- vol is klaar ----------------------------------------------------


def test_a_full_battery_switches_it_off(make_coordinator, hass):
    """"Wanneer de accu 100% is mogen de buttons door de integratie

    worden uitgeschakeld en de learning button ook uit."
    """
    c = _coordinator(make_coordinator)
    c.learning_only = False
    c._dispatch_notification = lambda **kw: None

    _run(c.async_set_handmatige_stand(HANDMATIGE_STAND_LADEN, NU))
    c.accustand_procent = lambda: 100.0
    _run(c._volg_handmatige_stand(NU + timedelta(minutes=5)))

    assert c.handmatige_stand is None
    assert c.learning_only is False


def test_an_almost_full_battery_keeps_going(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c._dispatch_notification = lambda **kw: None
    c.accustand_procent = lambda: 98.0

    _run(c.async_set_handmatige_stand(HANDMATIGE_STAND_LADEN, NU))
    _run(c._volg_handmatige_stand(NU + timedelta(minutes=5)))

    assert c.handmatige_stand == HANDMATIGE_STAND_LADEN


def test_a_full_battery_says_so(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    meldingen = []
    c._dispatch_notification = lambda **kw: meldingen.append(kw)

    _run(c.async_set_handmatige_stand(HANDMATIGE_STAND_LADEN, NU))
    c.accustand_procent = lambda: 100.0
    _run(c._volg_handmatige_stand(NU + timedelta(minutes=5)))

    assert any("vol" in m["title"].lower() for m in meldingen)


# --- de schakelaars zelf ---------------------------------------------


def test_both_switches_exist():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "switch.py").read_text()

    assert "HandmatigeStandSwitch" in bron
    # v3.79.0: het vermogen staat in een ATTRIBUUT, niet in de naam.
    # Home Assistant leidt de entity_id af van de weergavenaam als de
    # entiteit al bestond, en dan ontstaat `..._handmatig_laden_2000_w`.
    assert "Handmatig laden" in bron
    assert "Handmatig laden 2000 W" not in bron
    assert "Handmatig smart charge" in bron


def test_the_wattage_is_an_attribute_not_a_name():
    """Dat getal hoort in de knop, niet in de identiteit: wijzigt het

    ooit, dan klopt elke verwijzing niet meer.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    map_ = Path(pkg.__file__).parent
    bron = (map_ / "switch.py").read_text()
    sjabloon = (map_ / "dashboard_template.yaml").read_text()

    assert '"vermogen_w"' in bron
    # En de kaart leest het daar, met een terugval.
    assert "state_attr(e, 'vermogen_w')" in sjabloon


def test_the_switches_do_not_survive_a_restart():
    """Bewust geen herstel: anders staat de accu na een herstart uren

    later nog handmatig te laden zonder dat iemand er nog aan denkt - en
    dat is precies wat er op 28 augustus een halve dag gebeurde.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "switch.py").read_text()
    kop = bron.index("class HandmatigeStandSwitch")
    staart = bron[kop : bron.index("class AchterhoeksSwitch")]

    assert "async_get_last_state" not in staart
