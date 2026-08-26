"""Verkopen loont niet meer vanzelf (v3.42.0).

Op 31 december 2026 vervalt de saldering. Dan wordt een teruggeleverde
kWh niet meer weggestreept tegen een ingekochte: je krijgt het kale
tarief terwijl inkoop belast blijft.

De machinerie daarvoor ligt er sinds v1.1.0 -
`_get_feedin_value_per_kwh` rekent beide werelden al uit - maar de
verkoopcheck gebruikte hem niet. Die vroeg alleen "houdt de woning het
tot het goedkope blok?" en ging er stilzwijgend van uit dat verkopen
verder gratis geld is. Precies die aanname klapt om.

Deze rem is tot 1 januari 2027 volledig inert, en dat wordt hier
vastgelegd: vandaag mag er niets veranderen.
"""
from datetime import datetime, timedelta

import pytest

from custom_components.energy_management_system.const import (
    CONF_SALDEREN_END_DATE,
)

ONDER_SALDERING = datetime(2026, 8, 20, 14, 0)
NA_SALDERING = datetime(2027, 1, 15, 14, 0)


def _prijzen(start: datetime, prijzen):
    return [
        {
            "start": (start + timedelta(hours=i)).isoformat(),
            "end": (start + timedelta(hours=i + 1)).isoformat(),
            "price_per_kwh": p,
        }
        for i, p in enumerate(prijzen)
    ]


def _stel_in(c, nu, prijzen, teruglever, rendement=94.0, slijtage=10.9):
    c.config = dict(c.config)
    c.config[CONF_SALDEREN_END_DATE] = "2026-12-31"
    c._get_forecast_entries = lambda **kw: _prijzen(nu, prijzen)
    c._get_feedin_value_per_kwh = lambda entries, now: teruglever
    c.get_wear_cost_overview = lambda: {
        "beschikbaar": True,
        "slijtage_ct_per_kwh": slijtage,
    }
    c.charge_efficiency_history = [rendement] * 7
    c.discharge_efficiency_history = [100.0] * 7
    return c


# --- tot 1 januari verandert er niets --------------------------------


def test_the_brake_is_inert_while_saldering_lasts(make_coordinator, hass):
    """Vandaag mag deze rem niets doen, hoe scheef de verhouding ook

    staat.
    """
    c = _stel_in(
        make_coordinator({}), ONDER_SALDERING, [0.05, 0.40], teruglever=0.02
    )

    assert c._verkoop_loont_na_saldering(ONDER_SALDERING) is None


# --- daarna wel ------------------------------------------------------


def test_selling_cheap_while_expensive_is_coming_is_blocked(
    make_coordinator, hass
):
    """Het geval waar het om gaat: nu 2 ct terugleveren terwijl er

    vanavond 40 ct inkoop aankomt.
    """
    c = _stel_in(
        make_coordinator({}), NA_SALDERING, [0.05, 0.40], teruglever=0.02
    )

    oordeel = c._verkoop_loont_na_saldering(NA_SALDERING)

    assert oordeel is not None
    assert oordeel["mag_verkopen"] is False
    assert "saldering" in oordeel["reden"]


def test_a_good_feed_in_price_still_allows_selling(make_coordinator, hass):
    """Is de terugleverprijs hoog genoeg, dan mag verkopen gewoon - deze

    rem is geen verbod op verkopen.
    """
    c = _stel_in(
        make_coordinator({}), NA_SALDERING, [0.05, 0.12], teruglever=0.30
    )

    assert c._verkoop_loont_na_saldering(NA_SALDERING) is None


def test_the_wear_cost_is_part_of_the_sum(make_coordinator, hass):
    """Een kWh vasthouden kost slijtage; zonder die post lijkt

    vasthouden altijd beter dan het is.
    """
    duur = _stel_in(
        make_coordinator({}), NA_SALDERING, [0.05, 0.30], teruglever=0.24,
        slijtage=1.0,
    )
    oordeel_lage_slijtage = duur._verkoop_loont_na_saldering(NA_SALDERING)

    goedkoop = _stel_in(
        make_coordinator({}), NA_SALDERING, [0.05, 0.30], teruglever=0.24,
        slijtage=10.9,
    )
    oordeel_hoge_slijtage = goedkoop._verkoop_loont_na_saldering(NA_SALDERING)

    # Bij lage slijtage loont vasthouden; bij hoge niet meer.
    assert oordeel_lage_slijtage is not None
    assert oordeel_hoge_slijtage is None


# --- en wat er ontbreekt mag nooit tot een gok leiden ----------------


def test_without_a_feed_in_price_nothing_is_decided(make_coordinator, hass):
    """Ontbreekt het teruglever-attribuut op de prijssensor, dan is

    gissen met de inkoopprijs precies de aanname die na saldering niet
    meer klopt.
    """
    c = _stel_in(
        make_coordinator({}), NA_SALDERING, [0.05, 0.40], teruglever=None
    )

    assert c._verkoop_loont_na_saldering(NA_SALDERING) is None


def test_without_prices_nothing_is_decided(make_coordinator, hass):
    c = _stel_in(make_coordinator({}), NA_SALDERING, [], teruglever=0.02)

    assert c._verkoop_loont_na_saldering(NA_SALDERING) is None


def test_the_numbers_are_all_in_the_answer(make_coordinator, hass):
    """Wie leest waarom er niet verkocht wordt, moet het kunnen

    narekenen.
    """
    c = _stel_in(
        make_coordinator({}), NA_SALDERING, [0.05, 0.40], teruglever=0.02
    )

    oordeel = c._verkoop_loont_na_saldering(NA_SALDERING)

    for veld in (
        "opbrengst_verkopen_eur_per_kwh",
        "waarde_vasthouden_eur_per_kwh",
        "duurste_prijs_later_eur_per_kwh",
    ):
        assert veld in oordeel
