"""Verkopen stopt als de planning een tekort voorziet (v3.43.0).

Gevraagd: "Als ik een melding krijg dat de accu de nacht niet haalt, moet
hij toch eigenlijk ook het manual terugleveren stoppen? Of zie ik dat
verkeerd?"

Niet verkeerd. Gemeten op 20 augustus 20:06 en 20:43: de planning meldde
kritiek "vier kwartieren waarin de accu niets meer kan leveren, morgen
06:30-07:30", en tegelijk stonden er acht kwartieren verkopen gepland
tussen 20:45 en 23:00 - van 69% naar 35% laadstand.

Beide kloppen op zichzelf. `may_sell_now` kijkt tot het volgende
goedkope blok; de tekortmelding kijkt de hele planning door. Maar het is
één accu, en dan is dit één hand die geeft en één die het weer wegneemt.
"""
from datetime import datetime

import pytest

from custom_components.energy_management_system.const import (
    PLAN_SHORTFALL_ALERT_MIN_QUARTERS,
)

NU = datetime(2026, 8, 20, 20, 45)


def _coordinator(make_coordinator, tekorten, perioden=None):
    c = make_coordinator({})
    c.last_plan_shortfall = {
        "kwartieren": tekorten,
        "perioden": perioden or ["morgen 06:30-07:30"],
    }
    return c


def test_a_planned_shortfall_stops_selling(make_coordinator, hass):
    """Het gemeten geval: vier tekortkwartieren morgenvroeg, terwijl er

    vanavond acht kwartieren verkoop stonden gepland.
    """
    c = _coordinator(make_coordinator, 4)

    oordeel = c.may_sell_now(NU, 6.65)

    assert oordeel["mag_verkopen"] is False
    assert oordeel["methode"] == "planning voorziet een tekort"
    assert "06:30" in oordeel["reden"]


def test_the_reason_says_where_the_energy_would_have_to_come_from(
    make_coordinator, hass
):
    """Wie leest waarom er niet verkocht wordt, moet de redenering

    kunnen volgen.
    """
    c = _coordinator(make_coordinator, 5)

    oordeel = c.may_sell_now(NU, 6.65)

    assert "van het net" in oordeel["reden"]
    assert oordeel["tekort_kwartieren"] == 5


def test_a_single_quarter_does_not_stop_selling(make_coordinator, hass):
    """Dezelfde ondergrens als de melding zelf. Bij één kwartier is het

    geen tekort maar een planning die precies uitkomt - de reden staat
    uitgeschreven bij PLAN_SHORTFALL_ALERT_MIN_QUARTERS, na 75 meldingen
    waarvan 47 op één dag.
    """
    c = _coordinator(make_coordinator, PLAN_SHORTFALL_ALERT_MIN_QUARTERS - 1)

    oordeel = c.may_sell_now(NU, 6.65)

    assert oordeel["methode"] != "planning voorziet een tekort"


def test_without_a_known_shortfall_nothing_changes(make_coordinator, hass):
    """Een verse start heeft nog geen planning doorgerekend; dan mag deze

    rem niets doen.
    """
    c = make_coordinator({})

    oordeel = c.may_sell_now(NU, 6.65)

    assert oordeel["methode"] != "planning voorziet een tekort"


def test_the_brake_reads_a_stored_value_not_a_fresh_plan():
    """De eerste versie riep `get_quarter_plan_summary` aan vanuit deze

    toets. Dat bouwt honderdtien kwartieren opnieuw op bij élke ronde,
    en een fout daarin breekt dan de aansturing - de volledige
    tick-toets viel er meteen over om.
    """
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    bron = inspect.getsource(C.may_sell_now)

    assert "last_plan_shortfall" in bron
    # De naam mag in de toelichting staan - daar legt hij juist uit
    # waarom het zo niet moet - maar er mag geen aanroep staan.
    assert "self.get_quarter_plan_summary(" not in bron
