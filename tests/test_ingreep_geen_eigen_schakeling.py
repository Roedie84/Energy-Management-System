"""Vijftig "handmatige ingrepen" die de integratie zelf deed (v3.99.5).

Uit de export van 2 september 20:19:

    handmatige_ingrepen   aantal 50, over drie dagen
    alle 20 getoonde      ems_wilde: smart_discharging of smart
                          werkelijk: manual
                          reden_ems: expensive_quarter

Dat laatste is intern tegenstrijdig: `expensive_quarter` BETEKENT
handmatig. De integratie had de accu dus zelf op handmatig gezet, en
merkte een ronde later dat hij op handmatig stond.

De oorzaak: `_volg_handmatige_ingrepen` loopt aan het eind van dezelfde
ronde waarin de opdracht is gegeven. De Zendure heeft dan de nieuwe stand
nog niet doorgegeven - dat duurt seconden tot een minuut - dus staat het
select nog op de vorige stand, en die verschilt van wat er net is
gevraagd. Met 68 wissels op een dag levert dat vijftig ingrepen op die
er geen zijn.

En sinds v3.82.0 geldt: drie verschillende dagen en er is een patroon.
Die drie dagen waren er. De integratie stond op het punt uit haar eigen
schakelingen een regel te leren over wat de bewoner wil.

Een verschil telt pas als het aanhoudt: langer dan de opdrachtcontrole
zelf nodig heeft om een opdracht na te kijken. En de vijftig die er
staan, gaan eruit - allemaal herkenbaar aan een reden die een andere
stand impliceert dan wat er "gewild" werd.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import (
    HANDMATIGE_INGREEP_MIN_DUUR_MINUTEN,
)

T0 = datetime(2026, 9, 2, 19, 48, tzinfo=timezone.utc)


def _opzet(c, hass, werkelijk, gewenst, reden):
    c.config = dict(c.config or {})
    c.config["operation_select_entity"] = "select.op"
    hass.states.set("select.op", werkelijk)
    c.last_applied_operation = gewenst
    c.last_reason = reden
    c.learning_only = False
    c.force_manual = False
    c.handmatige_ingrepen = []


def test_een_eigen_schakeling_is_geen_ingreep(make_coordinator, hass):
    """Het geval van 19:48: net smart_discharging gevraagd, select staat

    nog op manual van de vorige ronde.
    """
    c = make_coordinator({})
    _opzet(c, hass, werkelijk="manual", gewenst="smart_discharging", reden="discharging_window")

    c._volg_handmatige_ingrepen(T0)

    assert c.handmatige_ingrepen == []


def test_een_verschil_dat_aanhoudt_is_er_wel_een(make_coordinator, hass):
    c = make_coordinator({})
    _opzet(c, hass, werkelijk="manual", gewenst="smart_discharging", reden="discharging_window")

    c._volg_handmatige_ingrepen(T0)
    c._volg_handmatige_ingrepen(T0 + timedelta(minutes=HANDMATIGE_INGREEP_MIN_DUUR_MINUTEN + 1))

    assert len(c.handmatige_ingrepen) == 1


def test_een_verschil_dat_verdwijnt_telt_niet(make_coordinator, hass):
    """De Zendure haalt de opdracht na een minuut in."""
    c = make_coordinator({})
    _opzet(c, hass, werkelijk="manual", gewenst="smart_discharging", reden="discharging_window")
    c._volg_handmatige_ingrepen(T0)
    hass.states.set("select.op", "smart_discharging")
    c._volg_handmatige_ingrepen(T0 + timedelta(minutes=1))
    hass.states.set("select.op", "manual")
    c._volg_handmatige_ingrepen(T0 + timedelta(minutes=2))

    assert c.handmatige_ingrepen == []


def test_de_oude_valse_ingrepen_worden_opgeruimd(make_coordinator, hass):
    """Herkenbaar aan een reden die een andere stand impliceert dan wat

    er 'gewild' werd. Een echte ingreep - EMS wilde ontladen, de bewoner
    zette laden aan - blijft staan.
    """
    c = make_coordinator({})
    c.handmatige_ingrepen = [
        {"ems_wilde": "smart_discharging", "werkelijk": "manual", "reden_ems": "expensive_quarter"},
        {"ems_wilde": "smart", "werkelijk": "manual", "reden_ems": "expensive_quarter"},
        {"ems_wilde": "smart_discharging", "werkelijk": "manual", "reden_ems": "discharging_window",
         "richting": "laden"},
    ]

    c._ruim_valse_ingrepen_op()

    assert len(c.handmatige_ingrepen) == 1
    assert c.handmatige_ingrepen[0]["reden_ems"] == "discharging_window"
