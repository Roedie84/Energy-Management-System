"""Kwam de opdracht aan bij de accu? (v3.87.0)

Gevraagd bij de doorlichting: "Hoe wordt gecontroleerd dat een verzonden
commando daadwerkelijk is uitgevoerd?"

Het antwoord was: dat gebeurde niet. Er werd gecontroleerd of de
entiteit BEREIKBAAR was vóór het schrijven, maar nooit of de stand
daarna werkelijk was veranderd.

Dat is geen theoretisch gat. Op 30 augustus zette de knop "Handmatig
laden" de accu niet, en dat bleef een halve dag onopgemerkt - de
integratie dacht dat ze stuurde terwijl de accu op `smart` bleef staan.
"""
from datetime import datetime, timedelta

import pytest

from custom_components.energy_management_system.const import (
    OPDRACHT_BEVESTIGING_SECONDEN,
)

NU = datetime(2026, 8, 31, 10, 0)
LATER = NU + timedelta(seconds=OPDRACHT_BEVESTIGING_SECONDEN + 10)

# De wachttijd loopt op een MONOTONE teller, niet op de klok: een
# tijdstip draagt een tijdzone, en gaan die ooit uiteenlopen dan valt de
# hele controle om. In de toets geven we die teller expliciet mee.
T0 = 1000.0
T_LATER = T0 + OPDRACHT_BEVESTIGING_SECONDEN + 10


def _coordinator(make_coordinator, hass, staat):
    c = make_coordinator({})
    hass.states.set("select.modus", staat)
    c._dispatch_notification = lambda **kw: c.meldingen.append(kw)
    c.meldingen = []
    return c


# --- de kern -------------------------------------------------------


def test_an_ignored_command_is_reported(make_coordinator, hass):
    """Het geval van 30 augustus: er wordt `manual` geschreven en de accu

    blijft op `smart` staan.
    """
    c = _coordinator(make_coordinator, hass, "smart")
    c._noteer_opdracht("select.modus", "manual", "modus", nu_seconden=T0)

    c.controleer_opdrachten(LATER, nu_seconden=T_LATER)

    assert len(c.meldingen) == 1
    assert "opdracht" in c.meldingen[0]["title"].lower()
    assert c.opdracht_bevestigingen["mislukt"] == 1


def test_an_accepted_command_is_silent(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, "manual")
    c._noteer_opdracht("select.modus", "manual", "modus", nu_seconden=T0)

    c.controleer_opdrachten(LATER, nu_seconden=T_LATER)

    assert c.meldingen == []
    assert c.opdracht_bevestigingen["gelukt"] == 1


def test_it_waits_before_judging(make_coordinator, hass):
    """Een apparaat heeft even nodig om te reageren; te snel oordelen

    geeft valse meldingen.
    """
    c = _coordinator(make_coordinator, hass, "smart")
    c._noteer_opdracht("select.modus", "manual", "modus", nu_seconden=T0)

    c.controleer_opdrachten(NU, nu_seconden=T0 + 10)

    assert c.meldingen == []
    assert c.opdracht_bevestigingen["mislukt"] == 0


# --- getallen ------------------------------------------------------


def test_a_power_value_is_compared_numerically(make_coordinator, hass):
    """`-2000` en `-2000.0` zijn hetzelfde getal maar niet dezelfde

    tekenreeks.
    """
    c = _coordinator(make_coordinator, hass, "smart")
    hass.states.set("number.vermogen", "-2000.0")
    c._noteer_opdracht("number.vermogen", -2000, "handmatig vermogen", nu_seconden=T0)

    c.controleer_opdrachten(LATER, nu_seconden=T_LATER)

    assert c.opdracht_bevestigingen["gelukt"] == 1


def test_a_wrong_power_is_reported(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, "smart")
    hass.states.set("number.vermogen", "0")
    c._noteer_opdracht("number.vermogen", -2000, "handmatig vermogen", nu_seconden=T0)

    c.controleer_opdrachten(LATER, nu_seconden=T_LATER)

    assert c.opdracht_bevestigingen["mislukt"] == 1


# --- wat er NIET gebeurt -------------------------------------------


def test_an_unavailable_entity_is_not_blamed(make_coordinator, hass):
    """Onbereikbaar wordt elders al gemeld; twee meldingen over hetzelfde

    is er een te veel.
    """
    c = _coordinator(make_coordinator, hass, "unavailable")
    c._noteer_opdracht("select.modus", "manual", "modus", nu_seconden=T0)

    c.controleer_opdrachten(LATER, nu_seconden=T_LATER)

    assert c.meldingen == []


def test_it_does_not_retry(make_coordinator, hass):
    """Bewust geen automatische herhaling. Een opdracht die niet aankomt,

    komt meestal niet aan omdat er iets anders mis is - de app die
    tegenstuurt, een apparaat in standby. Blind herhalen maakt dat
    erger.
    """
    import ast
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    boom = ast.parse(inspect.getsource(C.controleer_opdrachten).lstrip())
    aanroepen = {
        n.func.attr
        for n in ast.walk(boom)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }

    assert "_async_apply_operation" not in aanroepen
    assert "_async_apply_manual" not in aanroepen


def test_each_command_is_judged_once(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, "smart")
    c._noteer_opdracht("select.modus", "manual", "modus", nu_seconden=T0)

    c.controleer_opdrachten(LATER, nu_seconden=T_LATER)
    c.controleer_opdrachten(LATER, nu_seconden=T_LATER + 300)

    assert c.opdracht_bevestigingen["mislukt"] == 1


# --- het overzicht -------------------------------------------------


def test_the_overview_reports_the_ratio(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, "manual")
    for _ in range(3):
        c._noteer_opdracht("select.modus", "manual", "modus", nu_seconden=T0)
        c.controleer_opdrachten(LATER, nu_seconden=T_LATER)
    hass.states.set("select.modus", "smart")
    c._noteer_opdracht("select.modus", "manual", "modus", nu_seconden=T0)
    c.controleer_opdrachten(LATER, nu_seconden=T_LATER)

    overzicht = c.get_opdrachtcontrole()

    assert overzicht["gelukt"] == 3
    assert overzicht["mislukt"] == 1
    assert overzicht["aandeel_gelukt_procent"] == 75.0


def test_both_the_mode_and_the_power_are_checked():
    """Op 30 augustus stond de modus goed maar deed het vermogen niets."""
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    bron = inspect.getsource(C._async_apply_manual)

    assert bron.count("_noteer_opdracht") == 2
