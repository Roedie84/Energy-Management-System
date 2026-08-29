"""Er blijft altijd 5% in de accu (v3.71.0).

Gevraagd: "Graag ook zorgen dat er 5% accu extra inblijft, dus minder
aan het net verkopen."

Aanleiding: drie ochtenden op rij een lege accu. Op 28 augustus:

    accu ontladen        7,52 kWh
    waarvan naar het NET 3,82 kWh
    daarna teruggekocht 10,54 kWh

De bestaande verkooptoets rekent uit hoeveel het huis nodig heeft tot
het goedkope blok, en dat is een VOORSPELLING. Klopt die niet - een
bewolkte dag, een wasmachine die er niet in zat - dan is de accu alsnog
leeg.

Deze bodem staat daar bovenop en is geen voorspelling maar een vaste
marge.
"""
from datetime import datetime

import pytest

from custom_components.energy_management_system.const import (
    VERKOOP_BODEM_FRACTIE,
)

NU = datetime(2026, 8, 29, 20, 0)


def _coordinator(make_coordinator, beschikbaar, nodig=0.0, capaciteit=7.78):
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: capaciteit
    c.beschikbare_energie_kwh = lambda: beschikbaar
    c._estimate_worst_case_deficit_kwh = lambda *a, **k: nodig
    return c, beschikbaar


def test_the_floor_blocks_a_sale_the_forecast_would_allow(
    make_coordinator, hass
):
    """Het geval waar het om gaat: de voorspelling zegt dat er niets

    nodig is, en dan gaat de laatste kilowattuur alsnog het net op.
    """
    c, beschikbaar = _coordinator(make_coordinator, beschikbaar=0.30, nodig=0.0)

    uitkomst = c.may_sell_now(NU, beschikbaar)

    assert uitkomst["mag_verkopen"] is False
    assert uitkomst["bodem_kwh"] == pytest.approx(7.78 * VERKOOP_BODEM_FRACTIE)


def test_above_the_floor_selling_is_still_allowed(make_coordinator, hass):
    """Vijf procent is een bodem, geen rem op alles."""
    c, beschikbaar = _coordinator(make_coordinator, beschikbaar=5.0, nodig=0.0)

    uitkomst = c.may_sell_now(NU, beschikbaar)

    assert uitkomst["mag_verkopen"] is True
    assert uitkomst["vrij_te_verkopen_kwh"] == pytest.approx(
        5.0 - 7.78 * VERKOOP_BODEM_FRACTIE, abs=0.01
    )


def test_the_deficit_still_wins_when_it_is_larger(make_coordinator, hass):
    """De bodem vervangt de bestaande toets niet - hij staat eronder.

    De diepste-tekortwandeling loopt alleen als er een goedkoop blok in
    zicht is; zonder dat valt er niets te overbruggen.
    """
    from datetime import timedelta

    c, beschikbaar = _coordinator(make_coordinator, beschikbaar=5.0, nodig=4.0)
    c.last_cheap_block_start = NU + timedelta(hours=10)

    uitkomst = c.may_sell_now(NU, beschikbaar)

    assert uitkomst["nodig_voor_woning_kwh"] > 7.78 * VERKOOP_BODEM_FRACTIE + 0.1
    assert uitkomst["bodem_bindend"] is False


def test_the_floor_is_reported_when_it_binds(make_coordinator, hass):
    """Wie leest waarom er niet verkocht wordt, hoort te zien of dat de

    voorspelling was of de bodem.
    """
    c, beschikbaar = _coordinator(make_coordinator, beschikbaar=5.0, nodig=0.0)

    assert c.may_sell_now(NU, beschikbaar)["bodem_bindend"] is True


def test_without_a_known_capacity_nothing_changes(make_coordinator, hass):
    """Geen capaciteit betekent geen bodem - dan is de bestaande toets

    het enige dat er is, en dat is beter dan een verzonnen grens.
    """
    c, beschikbaar = _coordinator(make_coordinator, beschikbaar=5.0, nodig=0.0)
    c.bruikbare_capaciteit_kwh = lambda: None

    uitkomst = c.may_sell_now(NU, beschikbaar)

    assert uitkomst["mag_verkopen"] is True
    assert uitkomst["bodem_kwh"] == 0


def test_five_percent_is_about_an_hour_of_base_load():
    """De afweging achter het getal: genoeg voor ruim een uur basislast,

    klein genoeg om de arbitrage niet te verstikken.
    """
    bodem_kwh = 7.78 * VERKOOP_BODEM_FRACTIE
    basislast_kw = 0.25

    assert 1.0 <= bodem_kwh / basislast_kw <= 2.5
