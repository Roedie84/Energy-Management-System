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


def test_the_fan_stops_when_the_battery_is_truly_idle():
    """v3.33.0: de stilstandgrens is van 300 naar 100 W gegaan.

    De nacht van 19 op 20 augustus liet zien dat 300 te hoog was: de
    ventilator ging zes keer uit bij 194 tot 290 W, en elke keer stond
    de omvormer binnen een half uur weer op 27 graden. Bij die vermogens
    is er dus wel degelijk een warmtebron.

    Bij écht nul watt klopte het wel: 20 augustus 08:57 uit bij 20
    graden en 0 W, en daarna bleef hij uit.
    """
    assert _uit(20.0, 15.9, 0.0) is True
    assert _uit(23.0, 16.5, 60.0) is True


def test_a_working_battery_no_longer_stops_the_fan():
    """De zes uitschakelingen van die nacht, met hun echte belasting."""
    for accu, buiten, watt in (
        (24.0, 15.7, 283.0),
        (23.0, 15.3, 272.0),
        (23.0, 14.7, 231.0),
        (23.0, 14.5, 281.0),
        (23.0, 14.5, 194.0),
        (23.0, 14.3, 290.0),
    ):
        assert _uit(accu, buiten, watt) is False, f"{accu} bij {watt}W"


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

    # v3.33.0: met de grens op 100 W valt 08:31 er ook buiten - daar
    # ging 159 W door de accu, en dat is geen stilstand. De drie die
    # overblijven draaiden op 87, 39 en 0 W.
    assert stopt == ["09:47", "10:49", "15:37"]


# --- de dagportie ----------------------------------------------------


class _MetTeller(_Kaal):
    """De harde bovengrens op de goedkope tak (v3.33.0)."""

    def __init__(self):
        self.goedkope_koeling_teller = 0
        self.goedkope_koeling_teldag = None
        self._goedkope_koeling_gemeld = False
        self.verstuurd = []

    def _dispatch_notification(self, **kwargs):
        self.verstuurd.append(kwargs)

    _goedkope_koeling_op_slot = C._goedkope_koeling_op_slot


def test_the_cheap_branch_has_a_daily_ration():
    """Drie keer heb ik aan drempels gedraaid om het pendelen te stoppen,

    en drie keer kwam het in een andere vorm terug. De oorzaak zit niet
    in de drempel maar in de installatie: bij 200 tot 430 W klimt de
    omvormer binnen een half uur van 23 naar 27 graden, en dan is elke
    hysterese te smal.
    """
    from custom_components.energy_management_system.const import (
        BATTERY_COOLING_OPPORTUNITY_MAX_PER_DAG,
    )

    obj = _MetTeller()
    nu = datetime(2026, 8, 20, 6, 0)

    assert obj._goedkope_koeling_op_slot(nu) is False

    obj.goedkope_koeling_teller = BATTERY_COOLING_OPPORTUNITY_MAX_PER_DAG

    assert obj._goedkope_koeling_op_slot(nu) is True


def test_the_ration_resets_at_midnight():
    obj = _MetTeller()
    obj.goedkope_koeling_teldag = datetime(2026, 8, 19).date()
    obj.goedkope_koeling_teller = 9

    assert obj._goedkope_koeling_op_slot(datetime(2026, 8, 20, 0, 5)) is False
    assert obj.goedkope_koeling_teller == 0


def test_it_says_why_the_fan_stays_off():
    """Een ventilator die zonder uitleg stilligt, is niet van een storing

    te onderscheiden.
    """
    obj = _MetTeller()
    obj.goedkope_koeling_teller = 9
    obj.goedkope_koeling_teldag = datetime(2026, 8, 20).date()

    obj._goedkope_koeling_op_slot(datetime(2026, 8, 20, 6, 0))

    assert len(obj.verstuurd) == 1
    assert obj.verstuurd[0]["kind"] == "koeling_te_scherp"
    assert "drempel" in obj.verstuurd[0]["message"]


def test_the_warning_comes_once_a_day():
    obj = _MetTeller()
    obj.goedkope_koeling_teller = 9
    obj.goedkope_koeling_teldag = datetime(2026, 8, 20).date()

    for _ in range(5):
        obj._goedkope_koeling_op_slot(datetime(2026, 8, 20, 6, 0))

    assert len(obj.verstuurd) == 1


def test_the_ration_survives_a_restart():
    """Anders is de bovengrens te omzeilen door de integratie te

    herladen.
    """
    from custom_components.energy_management_system.const import (
        PERSISTED_DATE_FIELDS,
        PERSISTED_PLAIN_FIELDS,
    )

    assert "goedkope_koeling_teller" in PERSISTED_PLAIN_FIELDS
    assert "goedkope_koeling_teldag" in PERSISTED_DATE_FIELDS


def test_protection_is_never_rationed():
    """Boven 35 graden gaat het om de omvormer, niet om centen."""
    obj = _Kaal()

    assert obj._is_goedkope_koelreden(42.0, 15.8) is False
    assert obj._is_goedkope_koelreden(36.0, 15.0) is False
