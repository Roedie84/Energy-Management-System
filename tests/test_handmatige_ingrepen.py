"""Vastleggen wanneer de accu anders staat dan EMS wilde (v3.75.0).

Gevraagd: "Maar als ik iets manueel doe kan dat toch juist een leer voor
de integratie zijn?"

Terecht, en dat zat er niet in. Alle bestaande metingen vergelijken
alternatieven die de integratie ZELF had kunnen kiezen; een ingreep van
buitenaf is een derde optie die nergens werd opgemerkt.

De aanleiding: op 30 augustus is de accu handmatig op laden gezet omdat
het pas na tweeën zou opklaren en de planning de avond niet zou halen.
Dat is een oordeel dat de integratie niet had.

Dit legt alleen VAST. Geen patroon, geen conclusie, geen sturing.
"""
from datetime import datetime, timedelta

import pytest

from custom_components.energy_management_system.const import (
    CONF_OPERATION_SELECT,
    HANDMATIGE_INGREPEN_MIN_VOOR_PATROON,
)

NU = datetime(2026, 8, 30, 11, 0)


def _coordinator(make_coordinator, hass, werkelijk, gewenst):
    c = make_coordinator({CONF_OPERATION_SELECT: "select.modus"})
    hass.states.set("select.modus", werkelijk)
    c.last_applied_operation = gewenst
    return c


# --- de ingreep van 30 augustus --------------------------------------


def test_a_manual_change_is_recorded(make_coordinator, hass):
    """EMS wilde `smart`, de accu staat op `manual` omdat er handmatig

    is bijgeladen.
    """
    c = _coordinator(make_coordinator, hass, "manual", "smart")

    c._volg_handmatige_ingrepen(NU)

    assert len(c.handmatige_ingrepen) == 1
    regel = c.handmatige_ingrepen[0]
    assert regel["ems_wilde"] == "smart"
    assert regel["werkelijk"] == "manual"


def test_the_circumstances_are_recorded_too(make_coordinator, hass):
    """Daar zit de mogelijke regel in: bij welke prijs, welke accustand

    en hoeveel verwachte zon greep de gebruiker in?
    """
    c = _coordinator(make_coordinator, hass, "manual", "smart")
    c.voorspelde_zon_vandaag_kwh = lambda now=None: (10.2, "toets")

    c._volg_handmatige_ingrepen(NU)

    regel = c.handmatige_ingrepen[0]
    for sleutel in (
        "accustand_procent",
        "beschikbaar_kwh",
        "prijs_nu_ct",
        "duurste_vandaag_ct",
        "verwachte_zon_kwh",
        "reden_ems",
    ):
        assert sleutel in regel
    assert regel["verwachte_zon_kwh"] == 10.2


def test_matching_modes_record_nothing(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, "smart", "smart")

    c._volg_handmatige_ingrepen(NU)

    assert c.handmatige_ingrepen == []


# --- één regel per periode -------------------------------------------


def test_one_line_per_period_not_per_round(make_coordinator, hass):
    """Anders staat er na een middag handmatig laden honderd keer

    hetzelfde.
    """
    c = _coordinator(make_coordinator, hass, "manual", "smart")

    for minuut in range(0, 120, 5):
        c._volg_handmatige_ingrepen(NU + timedelta(minutes=minuut))

    assert len(c.handmatige_ingrepen) == 1


def test_a_new_period_is_recorded_again(make_coordinator, hass):
    """Terug naar normaal en dan opnieuw ingrijpen is een tweede

    waarneming.
    """
    c = _coordinator(make_coordinator, hass, "manual", "smart")
    c._volg_handmatige_ingrepen(NU)

    hass.states.set("select.modus", "smart")
    c._volg_handmatige_ingrepen(NU + timedelta(hours=3))

    hass.states.set("select.modus", "manual")
    c._volg_handmatige_ingrepen(NU + timedelta(hours=4))

    assert len(c.handmatige_ingrepen) == 2


# --- wanneer er niets te vergelijken valt ----------------------------


def test_without_a_desired_mode_nothing_is_recorded(
    make_coordinator, hass
):
    """Vlak na het opstarten, of in leermodus waarin EMS niets schrijft."""
    c = _coordinator(make_coordinator, hass, "manual", None)

    c._volg_handmatige_ingrepen(NU)

    assert c.handmatige_ingrepen == []


def test_an_unavailable_entity_records_nothing(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, "unavailable", "smart")

    c._volg_handmatige_ingrepen(NU)

    assert c.handmatige_ingrepen == []


# --- geen conclusies -------------------------------------------------


def test_it_draws_no_conclusion_from_one_case(make_coordinator, hass):
    """Eén waarneming is geen patroon, en deze week is het vijf keer

    misgegaan dat er iets werd gebouwd op grond van één geval.
    """
    c = _coordinator(make_coordinator, hass, "manual", "smart")
    c._volg_handmatige_ingrepen(NU)

    overzicht = c.get_handmatige_ingrepen()

    assert overzicht["aantal"] == 1
    assert overzicht["genoeg_voor_een_patroon"] is False


def test_enough_cases_says_so(make_coordinator, hass):
    c = make_coordinator({})
    c.handmatige_ingrepen = [
        {"moment": "x"} for _ in range(HANDMATIGE_INGREPEN_MIN_VOOR_PATROON)
    ]

    assert c.get_handmatige_ingrepen()["genoeg_voor_een_patroon"] is True


def test_it_steers_nothing(make_coordinator, hass):
    import ast
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    for fn in (C._volg_handmatige_ingrepen, C.get_handmatige_ingrepen):
        boom = ast.parse(inspect.getsource(fn).lstrip())
        aanroepen = {
            n.func.attr
            for n in ast.walk(boom)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }
        assert "_async_apply_operation" not in aanroepen
        assert "_async_apply_manual" not in aanroepen


def test_it_reaches_the_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert '"handmatige_ingrepen"' in bron
