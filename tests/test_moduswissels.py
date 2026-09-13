"""Hoe vaak wisselt de accu van modus? (v3.87.0)

Gevraagd bij de doorlichting: "Hoe wordt voorkomen dat de batterij te
vaak schakelt tussen modi? Welke hysterese wordt gebruikt? Wat is de
minimale tijd dat een gekozen modus actief blijft?"

Het antwoord op alle drie was: die is er niet. Er is hysterese op de
keuze van het goedkoopste blok en op de koeling, maar niets houdt de
modus zelf vast.

Dit meet alleen. Een minimale duur inbouwen zou een noodzakelijke
omschakeling kunnen tegenhouden - een prijspiek, een accu die leegloopt
- en dan kost die rem geld op precies de momenten dat het telt. Eerst
meten, dan pas sturen: dezelfde volgorde als bij elke kandidaat op de
proefstand.
"""
from datetime import datetime, timedelta

import pytest

from custom_components.energy_management_system.const import (
    MODUSWISSEL_DREMPEL_PER_UUR,
)

NU = datetime(2026, 8, 31, 12, 0)


def _wissel(c, modus, moment):
    c.last_expected_mode = modus
    c.last_reason = "toets"
    c._record_decision_log(moment)


def test_a_switch_is_recorded(make_coordinator, hass):
    c = make_coordinator({})

    _wissel(c, "smart", NU)
    _wissel(c, "manual", NU + timedelta(minutes=5))

    assert len(c.moduswissels) == 1


def test_staying_put_is_not_a_switch(make_coordinator, hass):
    c = make_coordinator({})

    for i in range(5):
        _wissel(c, "smart", NU + timedelta(minutes=5 * i))

    assert c.moduswissels == []


def test_a_restart_is_not_a_switch(make_coordinator, hass):
    """Gemeten in de export van 30 augustus 20:42: het beslislogboek had

    één regel met `modus: null`, geschreven op de eerste ronde na de
    herstart voordat de beslisboom had gedraaid. Zou die meetellen, dan
    lijkt elke herstart op een moduswisseling.
    """
    c = make_coordinator({})
    c.last_expected_mode = None
    c.last_reason = None
    c._record_decision_log(NU)

    _wissel(c, "smart", NU + timedelta(minutes=5))

    assert c.moduswissels == []


def test_the_log_line_is_still_written(make_coordinator, hass):
    """Sinds v1.30.0 legt het logboek bewust ook onvolledige rondes vast,

    en daar ligt een toets op. Alleen de TELLING slaat ze over.
    """
    c = make_coordinator({})

    c._record_decision_log(NU)

    assert len(c.decision_log) == 1


# --- het overzicht ---------------------------------------------------


def test_without_switches_it_says_so(make_coordinator, hass):
    c = make_coordinator({})

    assert c.get_moduswissels()["beschikbaar"] is False


def test_frequent_switching_is_flagged(make_coordinator, hass):
    """Elke ronde duurt een paar minuten en de prijzen liggen per

    kwartier vast, dus vaker wisselen komt ergens anders vandaan.
    """
    from homeassistant.util import dt as dt_util

    c = make_coordinator({})
    nu = dt_util.now()
    c.moduswissels = [
        (nu - timedelta(minutes=5 * i)).isoformat()
        for i in range(MODUSWISSEL_DREMPEL_PER_UUR + 2)
    ]

    overzicht = c.get_moduswissels()

    assert overzicht["te_vaak"] is True
    assert overzicht["laatste_uur"] > MODUSWISSEL_DREMPEL_PER_UUR


def test_calm_switching_is_fine(make_coordinator, hass):
    from homeassistant.util import dt as dt_util

    c = make_coordinator({})
    nu = dt_util.now()
    c.moduswissels = [
        (nu - timedelta(hours=3 * i)).isoformat() for i in range(4)
    ]

    assert c.get_moduswissels()["te_vaak"] is False


def test_it_only_measures(make_coordinator, hass):
    """Geen rem: die kan een noodzakelijke omschakeling tegenhouden."""
    import ast
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    boom = ast.parse(inspect.getsource(C.get_moduswissels).lstrip())
    aanroepen = {
        n.func.attr
        for n in ast.walk(boom)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }

    assert "_async_apply_operation" not in aanroepen
    assert "_async_apply_manual" not in aanroepen
