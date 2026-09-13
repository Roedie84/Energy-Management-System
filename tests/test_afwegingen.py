"""Welke voorwaarden waren FALSE? (v3.89.0)

Gevraagd bij de duivelsadvocaat-audit: "Kan ik zien welke voorwaarden
FALSE waren? Welke beslissingen zijn niet reproduceerbaar?"

Het antwoord was nee. Er zijn zestien beslisredenen in een vaste
volgorde, en de gekozen reden werd vastgelegd - maar niet waarom de
vijftien andere afvielen. Bij `expensive_quarter` was niet te zien of
`emergency_low_battery` op een haar na niet aansloeg.

Dat maakt een beslissing achteraf onverklaarbaar, en het is de enige
manier waarop de rest van de auditvragen ooit te beantwoorden is.
"""
from datetime import datetime

import pytest

NU = datetime(2026, 8, 31, 20, 0)


def test_a_reasoning_is_recorded(make_coordinator, hass):
    c = make_coordinator({})
    c._is_emergency_low_battery = lambda: False

    c._noteer_ontlaadafwegingen(1600.0, 1600.0)

    namen = [a["voorwaarde"] for a in c._afwegingen_deze_ronde]
    assert "genoeg lading om te ontladen" in namen
    assert "genoeg eigen verbruik" in namen
    assert "accu kritiek laag" in namen


def test_it_says_why_not_just_whether(make_coordinator, hass):
    """Een waar/onwaar zonder reden verklaart niets."""
    c = make_coordinator({})
    c._is_emergency_low_battery = lambda: False

    c._noteer_ontlaadafwegingen(None, None)

    reserve = next(
        a
        for a in c._afwegingen_deze_ronde
        if a["voorwaarde"] == "genoeg lading om te ontladen"
    )
    assert reserve["waar"] is False
    assert "reserve" in reserve["waarom"]


def test_capped_by_own_load_is_distinguished(make_coordinator, hass):
    """Viel het vermogen weg door een lage stand, of door te weinig eigen

    verbruik? De uitkomst is dezelfde, de reden niet.
    """
    c = make_coordinator({})
    c._is_emergency_low_battery = lambda: False

    capped = c._noteer_ontlaadafwegingen(1600.0, None)

    assert capped is True
    verbruik = next(
        a
        for a in c._afwegingen_deze_ronde
        if a["voorwaarde"] == "genoeg eigen verbruik"
    )
    assert verbruik["waar"] is False


def test_the_emergency_threshold_is_visible(make_coordinator, hass):
    """Bij `expensive_quarter` was niet te zien of

    `emergency_low_battery` op een haar na niet aansloeg. Nu wel.
    """
    c = make_coordinator({})
    c._is_emergency_low_battery = lambda: True

    c._noteer_ontlaadafwegingen(None, None)

    nood = next(
        a
        for a in c._afwegingen_deze_ronde
        if a["voorwaarde"] == "accu kritiek laag"
    )
    assert nood["waar"] is True
    assert "noodgrens" in nood["waarom"]


# --- het bewaren ----------------------------------------------------


def test_they_are_kept_when_the_decision_is_done(make_coordinator, hass):
    c = make_coordinator({})
    c._is_emergency_low_battery = lambda: False
    c._noteer_ontlaadafwegingen(1600.0, 1600.0)

    c._finish_decision_tick(NU)

    assert len(c.laatste_afwegingen) == 3
    assert c.laatste_afwegingen_moment is not None


def test_the_next_round_starts_clean(make_coordinator, hass):
    """Anders stapelen de afwegingen van elke ronde op elkaar."""
    c = make_coordinator({})
    c._is_emergency_low_battery = lambda: False
    c._noteer_ontlaadafwegingen(1600.0, 1600.0)
    c._finish_decision_tick(NU)

    assert c._afwegingen_deze_ronde == []


def test_a_round_without_reasoning_keeps_the_previous(
    make_coordinator, hass
):
    """Niet elke tak toetst deze drie voorwaarden. Dan blijft staan wat

    er was, in plaats van een lege lijst te tonen.
    """
    c = make_coordinator({})
    c.laatste_afwegingen = [{"voorwaarde": "eerder", "waar": True, "waarom": "x"}]

    c._finish_decision_tick(NU)

    assert c.laatste_afwegingen[0]["voorwaarde"] == "eerder"


# --- het overzicht --------------------------------------------------


def test_the_overview_is_empty_at_first(make_coordinator, hass):
    c = make_coordinator({})

    assert c.get_afwegingen()["beschikbaar"] is False


def test_the_overview_names_the_chosen_reason(make_coordinator, hass):
    c = make_coordinator({})
    c._is_emergency_low_battery = lambda: False
    c._noteer_ontlaadafwegingen(1600.0, 1600.0)
    c._finish_decision_tick(NU)
    c.last_reason = "expensive_quarter"

    overzicht = c.get_afwegingen()

    assert overzicht["reden"] == "expensive_quarter"
    assert len(overzicht["afwegingen"]) == 3


def test_it_reaches_the_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert '"afwegingen"' in bron
