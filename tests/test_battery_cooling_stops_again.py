"""De ventilator gaat óók weer uit (v3.26.1).

Gemeten aan de export van 19 augustus 08:09. Twee dingen tegelijk waar:

1. Het pendelen van v3.23.1 is echt weg. De laatste schakeling van de
   schakelgeschiedenis is 18 augustus 21:15, de export is elf uur later,
   en daartussen staat niets. De twintig regels in die geschiedenis zijn
   van een OUDERE versie: élke "uit" gebeurde onder de 32 graden zonder
   dat de goedkope koeling werd ontzien, en dat is het gedrag van vóór
   v3.14.0. Twee regels sluiten v3.14.0 ook uit - 11:49 bij 30,0 graden
   met 14,7 verschil en 14:37 bij 31,0 met 13,4 - want die had toen
   moeten doordraaien.

2. Maar hij gaat nu ook nooit meer uit. Bij een drempel van 25 ligt de
   ondergrens op 20, en de accu stond die nacht op 23,0 met 16,5 buiten
   en 114 W. Die 20 graden komt nooit.

De reparatie kijkt naar de warmtebron in plaats van naar de thermometer:
de omvormer wordt warm van WERK. Staat de accu onder de aanzetdrempel én
gaat er bijna niets doorheen, dan is er niets te koelen. Gaat er wél
vermogen doorheen, dan draait hij door - op 18 augustus 19:45 stond de
accu op 23 graden met 1623 W, en een half uur later op 31.

Uitzetten mag alleen met een rem op het opnieuw aanzetten, anders is het
pendelen meteen terug: een half uur na uitschakelen stond de omvormer
weer op 27 bij nul watt.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system.const import (
    BATTERY_COOLING_OPPORTUNITY_IDLE_W,
    BATTERY_COOLING_OPPORTUNITY_REST_MINUTES,
    CONF_BATTERY_COOLING_OPPORTUNITY_C,
)
from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)

sys.path.insert(0, str(Path(pkg.__file__).parent))


class _Kaal:
    """Alleen de koelbeslissing, zonder de rest van de coordinator."""

    config = {CONF_BATTERY_COOLING_OPPORTUNITY_C: 25.0}
    _koelen_is_goedkoop = C._koelen_is_goedkoop
    _goedkope_koeling_nog_zinvol = C._goedkope_koeling_nog_zinvol
    _is_goedkope_koelreden = C._is_goedkope_koelreden


def _uit(accu, buiten, vermogen):
    return C._battery_cooling_should_turn_off(
        _Kaal(), accu, buiten, vermogen
    )


# --- de nachtstand uit de export -------------------------------------


def test_the_fan_stops_on_the_measured_night_reading():
    """19 augustus 08:09: accu 23,0 met 16,5 buiten en 114 W, ventilator

    al elf uur aan. Onder de aanzetdrempel van 25 en vrijwel geen
    vermogen - er is niets dat warmte maakt.
    """
    assert _uit(23.0, 16.5, 114.0) is True


def test_it_keeps_running_while_the_battery_is_working():
    """18 augustus 19:45: accu 23,0 maar 1623 W erdoorheen, en een half

    uur later stond de omvormer op 31. Uitzetten op dát moment is
    precies verkeerd.
    """
    assert _uit(23.0, 18.9, 1623.0) is False


def test_the_load_limit_is_what_decides_it():
    """Dezelfde temperatuur, alleen het vermogen verschilt."""
    grens = BATTERY_COOLING_OPPORTUNITY_IDLE_W

    assert _uit(23.0, 16.5, grens - 1) is True
    assert _uit(23.0, 16.5, grens + 1) is False


def test_above_the_threshold_the_load_does_not_matter():
    """Boven de aanzetdrempel valt er nog te koelen, ook bij een stille

    accu - anders stopt hij midden in zijn werk.
    """
    assert _uit(27.0, 15.0, 0.0) is False
    assert _uit(30.0, 15.3, 0.0) is False


def test_the_protective_rules_are_untouched():
    """Boven 32 graden verandert er niets; koelen is daar bescherming."""
    assert _uit(34.0, 26.5, 0.0) is False
    assert _uit(42.0, 15.8, 0.0) is False


# --- de rem op het opnieuw aanzetten ---------------------------------


class _MetKlok(_Kaal):
    _cooling_switch_too_recent = C._cooling_switch_too_recent


def test_restarting_a_quiet_fan_waits_two_hours():
    """Zonder rem is het pendelen terug: een half uur na uitschakelen

    stond de omvormer weer op 27 graden bij nul watt.
    """
    obj = _MetKlok()
    nu = datetime(2026, 8, 18, 10, 18)
    obj.battery_cooling_last_change = nu - timedelta(minutes=31)

    assert obj._cooling_switch_too_recent(
        nu, aanzetten=True, grens_minuten=BATTERY_COOLING_OPPORTUNITY_REST_MINUTES
    ) is True

    obj.battery_cooling_last_change = nu - timedelta(minutes=121)

    assert obj._cooling_switch_too_recent(
        nu, aanzetten=True, grens_minuten=BATTERY_COOLING_OPPORTUNITY_REST_MINUTES
    ) is False


def test_a_loaded_battery_does_not_wait_that_long():
    """Komt er wél belasting, dan is er een echte reden en geldt de

    gewone rusttijd van een half uur.
    """
    obj = _MetKlok()
    nu = datetime(2026, 8, 18, 11, 19)
    obj.battery_cooling_last_change = nu - timedelta(minutes=31)

    assert obj._cooling_switch_too_recent(nu, aanzetten=True) is False


def test_only_the_cheap_branch_waits():
    """Boven 35 graden gaat het om bescherming van de omvormer, en die

    wacht nergens op.
    """
    obj = _Kaal()

    assert obj._is_goedkope_koelreden(27.0, 15.0) is True
    assert obj._is_goedkope_koelreden(42.0, 15.8) is False


# --- de gemeten dag opnieuw afgespeeld -------------------------------

# De twintig schakelingen van 18 augustus, met de meting die er op dat
# moment bij hoorde. Dit is GEEN warmtemodel: de temperaturen zijn
# ontstaan onder de oude regels. Het punt is dat dezelfde cijfers niet
# langer elk half uur een schakeling opleveren.
GEMETEN = [
    ("08:31", 23.0, 14.4, 159.0),
    ("09:17", 27.0, 14.8, 95.0),
    ("09:47", 21.0, 14.9, 87.0),
    ("10:18", 27.0, 15.0, 0.0),
    ("10:49", 23.0, 15.2, 39.0),
    ("11:19", 29.0, 15.7, 2015.0),
    ("11:49", 30.0, 15.3, 2021.0),
    ("12:19", 42.0, 15.8, 2038.0),
    ("14:37", 31.0, 17.6, 948.0),
    ("15:07", 33.0, 17.9, 136.0),
    ("15:37", 24.0, 17.7, 0.0),
    ("16:40", 31.0, 18.4, 1034.0),
    ("17:10", 27.0, 20.2, 341.0),
    ("17:54", 32.0, 19.6, 754.0),
    ("18:24", 26.0, 19.8, 207.0),
    ("19:15", 31.0, 19.0, 76.0),
    ("19:45", 23.0, 18.9, 1623.0),
    ("20:15", 31.0, 18.6, 1628.0),
    ("20:45", 26.0, 18.4, 291.0),
    ("21:15", 34.0, 17.7, 1631.0),
]


def test_the_measured_day_stops_far_less_often():
    """Tien uitschakelingen stonden er in de geschiedenis. Zes daarvan

    hadden nooit mogen gebeuren: de accu deed op dat moment werk, of
    stond boven de aanzetdrempel.
    """
    stopt = [
        moment
        for moment, accu, buiten, watt in GEMETEN
        if _uit(accu, buiten, watt)
    ]

    assert stopt == ["08:31", "09:47", "10:49", "15:37"]
