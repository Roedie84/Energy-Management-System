"""Niet schrijven naar een accu die offline is (v3.46.0).

Gemeld: "Ik krijg telkens deze melding van de integratie: Zendure - No
devices online, not possible to start the operation. Als ik de app op
learn only zet niet."

Die melding komt van de Zendure-integratie, niet van deze. Hij
verschijnt zodra EMS naar de modus- of vermogensentiteit schrijft
terwijl Zendure geen verbinding met de accu heeft. In leermodus schrijft
EMS niets, dus dan blijft het stil - het probleem is er dan nog steeds,
alleen onzichtbaar.

Elke ronde tegen een dode entiteit aan schrijven levert niets op behalve
een foutmelding per ronde. Wie zijn accu twee uur offline heeft, krijgt
er honderd.
"""
import asyncio

import pytest

from custom_components.energy_management_system.const import (
    CONF_MANUAL_POWER_NUMBER,
    CONF_OPERATION_SELECT,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _config():
    return {
        CONF_OPERATION_SELECT: "select.zendure_manager_operation",
        CONF_MANUAL_POWER_NUMBER: "number.zendure_manager_manual_power",
    }


def _online(hass):
    hass.states.set("select.zendure_manager_operation", "smart")
    hass.states.set("number.zendure_manager_manual_power", "0")


def _offline(hass, welke="select.zendure_manager_operation"):
    _online(hass)
    hass.states.set(welke, "unavailable")


# --- de bewaking zelf ------------------------------------------------


def test_an_available_battery_is_written_to(make_coordinator, hass):
    c = make_coordinator(_config())
    _online(hass)

    assert c._aansturing_bereikbaar() is None


@pytest.mark.parametrize("stand", ["unavailable", "unknown"])
def test_an_unavailable_mode_entity_blocks_the_write(
    make_coordinator, hass, stand
):
    c = make_coordinator(_config())
    _online(hass)
    hass.states.set("select.zendure_manager_operation", stand)

    reden = c._aansturing_bereikbaar()

    assert reden is not None
    assert "geen verbinding" in reden


def test_the_power_number_counts_too(make_coordinator, hass):
    """Beide entiteiten worden beschreven; één die wegvalt is genoeg."""
    c = make_coordinator(_config())
    _offline(hass, "number.zendure_manager_manual_power")

    assert c._aansturing_bereikbaar() is not None


def test_a_missing_state_object_does_not_block(make_coordinator, hass):
    """Vlak na het opstarten staat een entiteit soms nog niet in de

    toestandsmachine terwijl hij straks prima werkt. Alleen een
    uitdrukkelijk `unavailable` telt.
    """
    c = make_coordinator(_config())

    assert c._aansturing_bereikbaar() is None


# --- er wordt werkelijk niet geschreven ------------------------------


def test_no_service_call_while_the_battery_is_offline(
    make_coordinator, hass
):
    c = make_coordinator(_config())
    _offline(hass)
    hass.services.calls.clear()

    _run(c._async_apply_manual(1500))

    geschreven = [
        x for x in hass.services.calls if x[0] in ("select", "number")
    ]
    assert geschreven == []


def test_the_write_happens_again_once_it_is_back(make_coordinator, hass):
    c = make_coordinator(_config())
    _offline(hass)
    _run(c._async_apply_manual(1500))

    _online(hass)
    hass.services.calls.clear()
    _run(c._async_apply_manual(1500))

    geschreven = [
        x for x in hass.services.calls if x[0] in ("select", "number")
    ]
    assert geschreven


# --- en het wordt één keer gemeld ------------------------------------


def test_it_is_reported_once_not_once_per_round(make_coordinator, hass):
    """De aanleiding was juist een stroom foutmeldingen. Een oplossing

    die er zelf een stroom van maakt, is geen oplossing.
    """
    c = make_coordinator(_config())
    _offline(hass)

    for _ in range(5):
        _run(c._async_apply_manual(1500))

    assert c.aansturing_onbereikbaar["reden"] is not None
    eerste = c.aansturing_onbereikbaar["sinds"]

    _run(c._async_apply_manual(1500))

    assert c.aansturing_onbereikbaar["sinds"] == eerste


def test_it_is_not_an_internal_failure(make_coordinator, hass):
    """Een accu die offline is, is geen fout van deze integratie. Aan

    `internal_failures` hangt de kritieke melding "onderdeel van de
    integratie faalt", en die zou hier het verkeerde verhaal vertellen.
    """
    c = make_coordinator(_config())
    _offline(hass)

    _run(c._async_apply_manual(1500))

    assert "aansturing_onbereikbaar" not in c.internal_failures


def test_the_outage_clears_when_it_is_back(make_coordinator, hass):
    c = make_coordinator(_config())
    _offline(hass)
    _run(c._async_apply_manual(1500))

    _online(hass)
    c._aansturing_bereikbaar()

    assert c.aansturing_onbereikbaar["reden"] is None
    assert c.aansturing_onbereikbaar["sinds"] is None
