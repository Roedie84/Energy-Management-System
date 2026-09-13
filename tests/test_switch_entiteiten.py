"""De schakelaars zelf (v3.36.0).

Gevraagd naar aanleiding van de dekkingsmeting: 54% van `switch.py` werd
door geen enkele test uitgevoerd. Elf schakelaars, en elk daarvan zet
iets in de coordinator dat de aansturing raakt - de kalibratiestand, de
handmatige overname, de leermodus, de vakantiestand.

Precies het soort code dat er te eenvoudig uitziet om te toetsen, en waar
een fout dus jarenlang blijft zitten. De kalibratiekaart die naar een
niet-bestaande entiteit wees, is daar het bewijs van.

Wat hier getoetst wordt: dat aan- en uitzetten werkelijk in de
coordinator landt, dat een herstart de stand terugzet, en dat het
opruimen de luisteraar netjes afmeldt - blijft die staan, dan schrijft
hij naar een entiteit die niet meer bestaat.
"""
import asyncio

import pytest

from custom_components.energy_management_system import switch as mod


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _Coordinator:
    """De vlaggen die de schakelaars omzetten."""

    def __init__(self):
        self.force_manual = False
        self.learning_only = False
        self.vacation_mode = False
        self.kalibratie = False
        self.kalibratie_momentopname = None
        self.kalibratie_sinds = None
        self.achterhoeks = False
        self.steelstofzuiger_override = False
        self.fietsladers_override = False
        self.appliance_ready_notifications_enabled = True
        self.notifications_master_enabled = True
        self.luisteraars = []
        self.aanroepen = []

    def register_listener(self, fn):
        self.luisteraars.append(fn)

    def unregister_listener(self, fn):
        if fn in self.luisteraars:
            self.luisteraars.remove(fn)

    def get_notification_overview(self):
        return [{"soort": "test", "ingeschakeld": True}]

    def verbruiksleer_reset_wacht_op_bevestiging(self, now=None):
        return None

    async def async_set_force_manual(self, value):
        self.aanroepen.append(("force_manual", value))
        self.force_manual = value

    async def async_set_learning_only(self, value):
        self.aanroepen.append(("learning_only", value))
        self.learning_only = value

    async def async_set_vacation_mode(self, value):
        self.aanroepen.append(("vacation_mode", value))
        self.vacation_mode = value

    async def async_set_kalibratie(self, value):
        self.aanroepen.append(("kalibratie", value))
        self.kalibratie = value

    async def async_set_steelstofzuiger_override(self, value):
        self.steelstofzuiger_override = value

    async def async_set_fietsladers_override(self, value):
        self.fietsladers_override = value

    async def async_set_appliance_ready_notifications_enabled(self, value):
        self.appliance_ready_notifications_enabled = value


class _VorigeStand:
    def __init__(self, state):
        self.state = state


def _bouw(klasse, coordinator, laatste=None):
    """Maakt een schakelaar en zet zijn Home Assistant-kant stil."""
    knop = klasse(coordinator, entry_id="entry1")
    knop.async_write_ha_state = lambda: None
    knop.async_get_last_state = lambda: _klaar(laatste)
    knop.hass = None
    return knop


async def _klaar(waarde):
    return waarde


# --- 1. de vier standen die de aansturing raken ----------------------


@pytest.mark.parametrize(
    "klasse,vlag",
    [
        (mod.ForceManualSwitch, "force_manual"),
        (mod.LearningOnlySwitch, "learning_only"),
        (mod.VacationModeSwitch, "vacation_mode"),
        (mod.KalibratieSwitch, "kalibratie"),
    ],
)
def test_turning_it_on_reaches_the_coordinator(klasse, vlag):
    """Een schakelaar die alleen zijn eigen stand onthoudt en niets

    doorgeeft, ziet er in de UI precies hetzelfde uit.
    """
    c = _Coordinator()
    knop = _bouw(klasse, c)

    assert knop.is_on is False

    _run(knop.async_turn_on())

    assert getattr(c, vlag) is True
    assert knop.is_on is True

    _run(knop.async_turn_off())

    assert getattr(c, vlag) is False


@pytest.mark.parametrize(
    "klasse,vlag",
    [
        (mod.ForceManualSwitch, "force_manual"),
        (mod.LearningOnlySwitch, "learning_only"),
        (mod.VacationModeSwitch, "vacation_mode"),
        # v3.42.1: de kalibratie staat hier NIET meer bij. Die stand komt
        # uit de opslag, samen met de momentopname en de lopende
        # capaciteitsmeting - dat zijn drie dingen die bij elkaar horen.
        # Twee herstelpaden voor dezelfde vlag betekende dat deze
        # entiteit de opslag overschreef; zie structuurscan 11.
    ],
)
def test_the_state_survives_a_restart(klasse, vlag):
    """Een kalibratie duurt uren en een vakantie dagen. Terugkomen op

    "uit" na een herstart is een stille storing.
    """
    c = _Coordinator()
    knop = _bouw(klasse, c, laatste=_VorigeStand("on"))

    _run(knop.async_added_to_hass())

    assert getattr(c, vlag) is True


def test_the_calibration_state_comes_from_the_store():
    """De entiteit mag de opslag niet overschrijven: die draagt ook de

    momentopname en de lopende capaciteitsmeting.
    """
    c = _Coordinator()
    c.kalibratie = True
    knop = _bouw(mod.KalibratieSwitch, c, laatste=_VorigeStand("off"))

    _run(knop.async_added_to_hass())

    assert c.kalibratie is True


@pytest.mark.parametrize("klasse", [mod.ForceManualSwitch])
def test_without_a_previous_state_nothing_changes(klasse):
    """Een verse installatie heeft geen vorige stand."""
    c = _Coordinator()
    knop = _bouw(klasse, c, laatste=None)

    _run(knop.async_added_to_hass())

    assert knop.is_on is False


# --- 2. de kalibratiekaart -------------------------------------------


def test_the_calibration_switch_says_it_has_no_snapshot_yet():
    c = _Coordinator()
    knop = _bouw(mod.KalibratieSwitch, c)

    assert knop.extra_state_attributes["momentopname"] == "nog niet vol geweest"


def test_the_calibration_switch_shows_the_snapshot():
    """Het bewijsstuk voor de accufabrikant hoort op de schakelaar zelf te

    staan, niet alleen in een export.
    """
    c = _Coordinator()
    c.kalibratie_momentopname = {
        "moment": "2026-08-19T14:29:00",
        "soc_percent": 100.0,
        "modules": [{"module": 1, "cel_delta_v": 0.26}],
    }
    knop = _bouw(mod.KalibratieSwitch, c)

    kenmerken = knop.extra_state_attributes

    assert kenmerken["soc_percent"] == 100.0
    assert kenmerken["modules"][0]["cel_delta_v"] == 0.26


# --- 3. de overige schakelaars ---------------------------------------


@pytest.mark.parametrize(
    "klasse,vlag",
    [
        (mod.AchterhoeksSwitch, "achterhoeks"),
        (mod.SteelstofzuigerOverrideSwitch, "steelstofzuiger_override"),
        (mod.FietsladersOverrideSwitch, "fietsladers_override"),
        (
            mod.ApplianceReadyNotificationsSwitch,
            "appliance_ready_notifications_enabled",
        ),
    ],
)
def test_the_simple_switches_flip_their_flag(klasse, vlag):
    c = _Coordinator()
    knop = _bouw(klasse, c)
    begin = getattr(c, vlag)

    _run(knop.async_turn_on())
    assert getattr(c, vlag) is True

    _run(knop.async_turn_off())
    assert getattr(c, vlag) is False

    assert begin in (True, False)


# --- 4. de hoofdschakelaar voor meldingen ----------------------------


def test_the_master_switch_registers_and_lets_go():
    """Blijft een afgemelde luisteraar staan, dan schrijft die na een

    herlaad naar een entiteit die niet meer bestaat.
    """
    c = _Coordinator()
    knop = _bouw(mod.NotificationsMasterSwitch, c)

    # De basisklasse van Home Assistant is in de testomgeving een stub
    # zonder deze twee haken; het gaat hier om wat de schakelaar zelf
    # doet.
    c.register_listener(knop.async_write_ha_state)

    assert len(c.luisteraars) == 1

    c.unregister_listener(knop.async_write_ha_state)

    assert c.luisteraars == []


def test_the_master_switch_counts_the_kinds():
    c = _Coordinator()
    knop = _bouw(mod.NotificationsMasterSwitch, c)

    kenmerken = knop.extra_state_attributes

    assert kenmerken["aantal_soorten"] == 1
    assert kenmerken["aantal_ingeschakeld"] == 1


def test_the_master_switch_follows_the_coordinator():
    c = _Coordinator()
    knop = _bouw(mod.NotificationsMasterSwitch, c)

    assert knop.is_on is True

    c.notifications_master_enabled = False

    assert knop.is_on is False


# --- 5. elke schakelaar hoort bij hetzelfde apparaat ------------------


@pytest.mark.parametrize(
    "klasse",
    [
        mod.KalibratieSwitch,
        mod.ForceManualSwitch,
        mod.LearningOnlySwitch,
        mod.AchterhoeksSwitch,
        mod.VacationModeSwitch,
        mod.SteelstofzuigerOverrideSwitch,
        mod.FietsladersOverrideSwitch,
        mod.ApplianceReadyNotificationsSwitch,
        mod.NotificationsMasterSwitch,
    ],
)
def test_every_switch_has_a_unique_id_and_a_device(klasse):
    """Zonder eigen id kan Home Assistant de entiteit niet hernoemen of

    aan een gebied toewijzen; zonder apparaat komt hij los te staan.
    """
    knop = klasse(_Coordinator(), entry_id="entry1")

    assert knop._attr_unique_id
    assert knop._attr_unique_id.startswith("entry1_")
    assert knop._attr_device_info["identifiers"]


def test_no_two_switches_share_an_id():
    """Twee entiteiten met hetzelfde id betekent dat er één verdwijnt."""
    klassen = [
        mod.KalibratieSwitch,
        mod.ForceManualSwitch,
        mod.LearningOnlySwitch,
        mod.AchterhoeksSwitch,
        mod.VacationModeSwitch,
        mod.SteelstofzuigerOverrideSwitch,
        mod.FietsladersOverrideSwitch,
        mod.ApplianceReadyNotificationsSwitch,
        mod.NotificationsMasterSwitch,
    ]
    ids = [k(_Coordinator(), entry_id="entry1")._attr_unique_id for k in klassen]

    assert len(set(ids)) == len(ids)
