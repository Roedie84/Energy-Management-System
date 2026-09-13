"""Een kWh uit de accu heeft een prijs (v1.55.0).

Gevraagd: "het kan dus zijn dat de prijs op gegeven moment 's nachts zo
laag is dat stroom van het net goedkoper is in de nacht, hoe gaat de
integratie daar nu mee om?"

Tot nu toe: niet. In `smart` voedt de accu het huis met wat hij heeft,
zonder te vragen of dat op dat moment verstandig is. Er was ook geen
modus om iets anders te doen - `smart_charging` ontbrak.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_OPERATION_SELECT,
    OPTION_SMART,
    OPTION_SMART_CHARGING,
    PRICE_SCALE_FACTOR,
)

NU = datetime(2026, 8, 12, 3, 0, tzinfo=timezone.utc)
ALLE_MODI = ["manual", "smart", "smart_discharging", "smart_charging"]


def _coordinator(make_coordinator, hass, netprijs, modi=ALLE_MODI):
    c = make_coordinator({CONF_OPERATION_SELECT: "select.op"})
    hass.states.set("select.op", "smart", {"options": modi})
    # De gemeten cijfers van 11 augustus.
    c.battery_cost_basis_eur_per_kwh = 0.2175
    # Het rendement is een berekende eigenschap; die voeden we via de
    # reeks waar hij zelf uit leest.
    c.learned_efficiency_history = [82.9] * 5
    c.get_wear_cost_overview = lambda: {
        "beschikbaar": True,
        "slijtage_ct_per_kwh": 4.7,
    }
    entries = [
        (NU, NU + timedelta(minutes=15), netprijs * PRICE_SCALE_FACTOR)
    ]
    return c, entries


# --- de vergelijking -------------------------------------------------


def test_a_cheap_night_holds_the_battery(make_coordinator, hass):
    """Een kWh uit de accu kost 21,75 ct gekocht, gedeeld door 82,9%
    rendement plus 4,7 ct slijtage: ruim 31 ct. Staat de nachtprijs op
    12 ct, dan is die kWh van het net halen goedkoper - en houd je de
    accu vol voor de ochtendpiek.
    """
    c, entries = _coordinator(make_coordinator, hass, netprijs=0.12)

    assert c._net_is_goedkoper_dan_de_accu(NU, entries) is True
    assert c.last_battery_vs_grid["accu_eur_per_kwh"] > 0.30


def test_a_normal_price_leaves_it_alone(make_coordinator, hass):
    """Bij 38 ct is de accu ruimschoots de goedkoopste bron."""
    c, entries = _coordinator(make_coordinator, hass, netprijs=0.38)

    assert c._net_is_goedkoper_dan_de_accu(NU, entries) is False


def test_a_hair_of_difference_does_not_flip(make_coordinator, hass):
    """Zonder marge zou een verschil van een halve cent de modus elke
    tick heen en weer laten schakelen, en dat is slechter dan de
    verkeerde keuze even volhouden."""
    c, entries = _coordinator(make_coordinator, hass, netprijs=0.3)
    accu = 0.2175 / 0.829 + 0.047

    net_net_eronder = round(accu - 0.01, 4)
    c2, entries2 = _coordinator(make_coordinator, hass, netprijs=net_net_eronder)

    assert c2._net_is_goedkoper_dan_de_accu(NU, entries2) is False


# --- de grendels -----------------------------------------------------


def test_without_the_mode_nothing_happens(make_coordinator, hass):
    """Een accu die `smart_charging` niet kent, zou stil in smart
    blijven hangen terwijl de planning iets anders belooft."""
    c, entries = _coordinator(
        make_coordinator,
        hass,
        netprijs=0.12,
        modi=["manual", "smart", "smart_discharging"],
    )

    assert c.smart_charging_supported() is False
    assert c._net_is_goedkoper_dan_de_accu(NU, entries) is False


def test_without_measured_numbers_nothing_happens(make_coordinator, hass):
    """Liever geen ingreep dan een ingreep op een geraden kostprijs."""
    c, entries = _coordinator(make_coordinator, hass, netprijs=0.12)
    c.battery_cost_basis_eur_per_kwh = None

    assert c._net_is_goedkoper_dan_de_accu(NU, entries) is False


def test_without_a_wear_figure_nothing_happens(make_coordinator, hass):
    c, entries = _coordinator(make_coordinator, hass, netprijs=0.12)
    c.get_wear_cost_overview = lambda: {"beschikbaar": False}

    assert c._net_is_goedkoper_dan_de_accu(NU, entries) is False


# --- de modus zelf ---------------------------------------------------


def test_an_unknown_mode_falls_back_and_is_reported(make_coordinator, hass):
    """Valkuil 2 uit de overdracht: een term die de accu niet kent wordt
    stil genegeerd, en dan staat de accu ergens anders dan de integratie
    denkt."""
    import asyncio

    c = make_coordinator({CONF_OPERATION_SELECT: "select.op"})
    hass.states.set("select.op", "smart", {"options": ["manual", "smart"]})

    asyncio.run(c._async_apply_operation(OPTION_SMART_CHARGING))

    gezet = [x for x in hass.services.calls if x[0] == "select"]
    assert gezet[-1][2]["option"] == OPTION_SMART
    assert "modus_niet_beschikbaar" in c.internal_failures


def test_a_known_mode_is_applied_as_is(make_coordinator, hass):
    import asyncio

    c = make_coordinator({CONF_OPERATION_SELECT: "select.op"})
    hass.states.set("select.op", "smart", {"options": ALLE_MODI})

    asyncio.run(c._async_apply_operation(OPTION_SMART_CHARGING))

    gezet = [x for x in hass.services.calls if x[0] == "select"]
    assert gezet[-1][2]["option"] == OPTION_SMART_CHARGING
    assert "modus_niet_beschikbaar" not in c.internal_failures


def test_an_entity_that_is_not_loaded_yet_is_not_blocked(
    make_coordinator, hass
):
    """Niet te controleren is iets anders dan afwezig. Tijdens het
    opstarten bestaat de entiteit nog niet, en blokkeren zou een
    werkende installatie stilzetten om een controle die zelf niets
    weet."""
    c = make_coordinator({CONF_OPERATION_SELECT: "select.op"})

    assert c.operation_option_available(OPTION_SMART) is True
    # Maar er wordt niets nieuws op gebouwd zolang het onzeker is.
    assert c.smart_charging_supported() is False


# --- v1.62.0: de vergelijking stuurt niets meer ----------------------


def test_the_comparison_no_longer_switches_modes():
    """Gemeld op 12 augustus 11:56, met `smart_charging` in bedrijf:
    "er is voldoende zonne energie, ook als de accu tijdelijk ontlaadt
    voor bijvoorbeeld het hogere vermogen van de wasmachine."

    Drie fouten in één beslissing:

    1. Bij zonoverschot is de keuze niet accu-tegen-net maar
       ZON-tegen-net, en zon is gratis.
    2. De vergelijking gebruikte de kostprijs van energie die er AL in
       zat; wat er op dat moment in ging was gratis zon.
    3. `smart_charging` zet ook de PIEKBUFFER uit. Bij een wasmachine
       van 2000 W met 1500 W zon moet het verschil van het net komen,
       terwijl de accu op 35% stond. Gemeten piek 2199 W tegen 1600 W
       ontlaadvermogen.

    De derde geldt ook 's nachts en is met deze modus niet op te lossen.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    # v3.77.0: de BESLISSING mag er niet naartoe schakelen; de
    # gebruiker wel.
    #
    # Deze toets verbood `smart_charging` in de hele codebase, en dat
    # was juist zolang alleen de integratie die stand kon zetten. Sinds
    # de handmatige schakelaars is er een tweede weg: de gebruiker die
    # er bewust voor kiest, met de leermodus aan en een herinnering per
    # uur.
    #
    # Het bezwaar uit v1.62.0 gold de AUTOMATISCHE keuze - drie fouten
    # in één beslissing. Een bewuste ingreep is iets anders, en die
    # wordt bovendien vastgelegd als handmatige stand.
    import ast
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    beslissers = [
        naam
        for naam in dir(C)
        if naam.startswith(("_beslis", "_bepaal", "_net_is_goedkoper"))
        or naam in ("_async_update_locked",)
    ]
    code = "\n".join(
        "\n".join(
            r.split("#")[0]
            for r in inspect.getsource(getattr(C, naam)).splitlines()
        )
        for naam in beslissers
    )

    assert "_async_apply_operation(OPTION_SMART_CHARGING)" not in code
    assert 'last_reason = "grid_cheaper_than_battery"' not in code


def test_the_comparison_is_still_measured(make_coordinator, hass):
    """De vraag blijft meetbaar - juist in de winter, als de accu uit het
    net laadt, wordt hij interessant."""
    c, entries = _coordinator(make_coordinator, hass, netprijs=0.12)

    c._net_is_goedkoper_dan_de_accu(NU, entries)

    assert c.last_battery_vs_grid["net_goedkoper"] is True


def test_it_is_still_computed_every_tick():
    """Zonder aanroep in de tick blijft `battery_vs_grid` leeg en is de
    vraag niet meer te volgen."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    code = "\n".join(r.split("#")[0] for r in bron.splitlines())

    assert "self._net_is_goedkoper_dan_de_accu(now, entries)" in code
