"""Waarschuwen als de leermodus blijft staan (v3.84.0).

Gemeld: "Maar er wordt niet geladen??" - terwijl de export gaf:

    leermodus              True
    last_simulated_action  "would set operation to 'smart'"

Die stond uren aan, en de analyse meldde "geen bijzonderheden". Dat
klopte: leermodus is een geldige stand, geen fout. Maar hij was aangezet
door de handmatige knop en bleef staan toen die uitging - want de knop
draait alleen terug wat hij ZELF heeft gezet, en de gebruiker had hem
oorspronkelijk aangezet.

Gevolg: een halve dag geen aansturing, met prijzen die naar 39 ct
liepen. De herinnering uit v3.77.0 geldt alleen zolang de handmatige knop
aan staat; blijft alleen de leermodus over, dan zwijgt alles.
"""
from datetime import datetime, timedelta

import pytest

from custom_components.energy_management_system.const import (
    LEERMODUS_HERINNERING_UREN,
    LEERMODUS_WAARSCHUWING_UREN,
)

NU = datetime(2026, 8, 30, 19, 0)


def _run(coro):
    import asyncio

    return asyncio.new_event_loop().run_until_complete(coro)


def _coordinator(make_coordinator, uren_aan):
    c = make_coordinator({})
    c.learning_only = True
    c.leermodus_sinds = NU - timedelta(hours=uren_aan)
    c._duurste_prijs_vandaag_ct = lambda now: 38.8
    return c


def test_a_long_learning_mode_is_reported(make_coordinator, hass):
    c = _coordinator(make_coordinator, LEERMODUS_WAARSCHUWING_UREN + 1)
    meldingen = []
    c._dispatch_notification = lambda **kw: meldingen.append(kw)

    _run(c._waarschuw_bij_lange_leermodus(NU))

    assert len(meldingen) == 1
    assert "leermodus" in meldingen[0]["title"].lower()
    assert "38.8" in meldingen[0]["message"]


def test_a_short_one_is_not(make_coordinator, hass):
    """Een leermodus van een half uur is normaal bij het instellen."""
    c = _coordinator(make_coordinator, 0.5)
    meldingen = []
    c._dispatch_notification = lambda **kw: meldingen.append(kw)

    _run(c._waarschuw_bij_lange_leermodus(NU))

    assert meldingen == []


def test_nothing_when_it_is_off(make_coordinator, hass):
    c = make_coordinator({})
    c.learning_only = False
    meldingen = []
    c._dispatch_notification = lambda **kw: meldingen.append(kw)

    _run(c._waarschuw_bij_lange_leermodus(NU))

    assert meldingen == []


def test_it_repeats_but_not_every_round(make_coordinator, hass):
    c = _coordinator(make_coordinator, LEERMODUS_WAARSCHUWING_UREN + 1)
    meldingen = []
    c._dispatch_notification = lambda **kw: meldingen.append(kw)

    _run(c._waarschuw_bij_lange_leermodus(NU))
    _run(c._waarschuw_bij_lange_leermodus(NU + timedelta(minutes=30)))
    assert len(meldingen) == 1

    _run(
        c._waarschuw_bij_lange_leermodus(
            NU + timedelta(hours=LEERMODUS_HERINNERING_UREN + 0.1)
        )
    )
    assert len(meldingen) == 2


def test_the_clock_resets_when_it_goes_off(make_coordinator, hass):
    c = _coordinator(make_coordinator, 10)

    _run(c.async_set_learning_only(False))

    assert c.leermodus_sinds is None


def test_it_is_attention_not_critical():
    """De verzameling kritieke soorten stond al op negen, met in de toets

    de regel: "als er tien soorten kritiek zijn, is er geen enkele meer
    kritiek."

    Deze hoort er ook niet: de leermodus is een stand die de gebruiker
    zelf heeft gekozen, niet iets dat stuk is.
    """
    from custom_components.energy_management_system.const import (
        LOG_PRIORITEITEN,
        LOG_PRIO_KRITIEK,
    )

    assert LOG_PRIORITEITEN["leermodus_lang_aan"] != LOG_PRIO_KRITIEK


def test_it_runs_every_round():
    """Een waarschuwing die nergens wordt aangeroepen, waarschuwt niets -

    en dat was precies de toestand toen deze functie half af was.
    """
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    # De ronde-taken staan in `_finish_decision_tick`.
    bron = inspect.getsource(C._finish_decision_tick)

    assert bron.count("_waarschuw_bij_lange_leermodus") == 1
