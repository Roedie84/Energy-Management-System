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
    # v3.99.13: de detector leest `last_expected_mode` (uit
    # REASON_TO_MODE); de opzet zet hem zoals de beslissing dat zou doen.
    from custom_components.energy_management_system.const import REASON_TO_MODE

    c.last_expected_mode = REASON_TO_MODE.get(reden, gewenst)
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


# --- v3.99.9: vergelijken met wat de EMS WIL, niet met wat hij stuurde --
#
# Vier nieuwe "ingrepen" op 3 september, ondanks de drie minuten:
#
#     19:48  wilde smart_discharging  werkelijk manual  reden expensive_quarter
#
# Nog steeds tegenstrijdig. `gewenst` komt uit `last_applied_operation`:
# de laatste opdracht die VERSTUURD is. Kiest de EMS handmatig terwijl de
# accu al op handmatig staat, dan wordt er niets verstuurd en blijft dat
# veld op de vorige opdracht staan - smart_discharging. De detector
# vergelijkt dan de accu (handmatig, correct) met een opdracht van
# minuten geleden.
#
# Wat de EMS wil, staat in de reden. Die is altijd van deze ronde.


def test_de_reden_wint_van_de_verstuurde_opdracht(make_coordinator, hass):
    c = make_coordinator({})
    _opzet(c, hass, werkelijk="manual", gewenst="smart_discharging", reden="expensive_quarter")

    c._volg_handmatige_ingrepen(T0)
    c._volg_handmatige_ingrepen(T0 + timedelta(minutes=5))

    assert c.handmatige_ingrepen == []


def test_een_echte_ingreep_tegen_de_reden_telt_wel(make_coordinator, hass):
    """EMS wil huis dekken (slim), bewoner zet handmatig laden aan."""
    c = make_coordinator({})
    _opzet(c, hass, werkelijk="manual", gewenst="smart_discharging", reden="discharging_window")

    c._volg_handmatige_ingrepen(T0)
    c._volg_handmatige_ingrepen(T0 + timedelta(minutes=5))

    assert len(c.handmatige_ingrepen) == 1


# --- v3.99.13: twee vertaaltabellen, en de code gebruikte de verkeerde --
#
# 6 september, vier nieuwe "ingrepen":
#
#     18:33  wilde manual  werkelijk smart  reden expensive_quarter_soc_protected
#
# `expensive_quarter_soc_protected` past de SLIMME stand toe (de
# laadstand is te laag om handmatig te verkopen). REASON_TO_MODE weet
# dat. De tekstheuristiek `_modus_bij_beslissing` - "expensive" staat
# erin, dus handmatig - niet. En om 00:03: `solar_capture_deferred`, dat
# in geen van beide stond.


def test_soc_protected_is_de_slimme_stand(make_coordinator, hass):
    c = make_coordinator({})
    _opzet(c, hass, werkelijk="smart", gewenst="manual", reden="expensive_quarter_soc_protected")
    c.last_expected_mode = "smart"

    c._volg_handmatige_ingrepen(T0)
    c._volg_handmatige_ingrepen(T0 + timedelta(minutes=5))

    assert c.handmatige_ingrepen == []


def test_elke_reden_heeft_een_stand():
    """Ontbreekt een reden in REASON_TO_MODE, dan blijft
    `last_expected_mode` op de vorige ronde staan en vergelijkt de
    detector met een stand van een andere reden."""
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    from custom_components.energy_management_system.const import (
        REASON_TO_MODE,
        REDENEN_ZONDER_STAND,
    )

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    redenen = set(re.findall(r'last_reason = "(\w+)"', bron))

    ontbreekt = redenen - set(REASON_TO_MODE) - set(REDENEN_ZONDER_STAND)
    assert not ontbreekt, sorted(ontbreekt)


def test_de_opruiming_kent_de_echte_tabel(make_coordinator, hass):
    c = make_coordinator({})
    c.handmatige_ingrepen = [
        {"ems_wilde": "manual", "werkelijk": "smart", "reden_ems": "expensive_quarter_soc_protected"},
        {"ems_wilde": "smart", "werkelijk": "smart_discharging", "reden_ems": "solar_capture_deferred"},
        {"ems_wilde": "smart_discharging", "werkelijk": "manual", "reden_ems": "discharging_window", "richting": "laden"},
    ]

    c._ruim_valse_ingrepen_op()

    assert [r["reden_ems"] for r in c.handmatige_ingrepen] == ["discharging_window"]
