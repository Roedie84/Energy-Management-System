"""Eén reserve (v4.1).

Gevraagd: "Alles oplossen wat noodzakelijk is, ook al kost het veel
tijd. Standpunt is en blijft dat het uiteindelijk een perfect EMS dient
te worden."

Bovenaan de lijst stond: drie berekeningen voor "hoeveel moet er in de
accu blijven", elk met een eigen marge:

    reserve       diepste tekort + witgoed + lange horizon, marge 62%,
                  bodem, gekapt          -> 6,13 kWh
    brug          diepste tekort x 1,15, eigen buffer   -> 4,42 kWh
    verkooptoets  diepste tekort x margefactor, bodem  -> 6,34 kWh
    planning      diepste tekort x max(factor, 1,25), bodem

Op 7 september 16:37 stonden twee van die getallen een minuut na
elkaar in twee meldingen: 17,96 en 13,44. Elke dode zone van deze week
was symptoombestrijding van een reserve die van plek tot plek en van
ronde tot ronde verschilt.

Vanaf nu is er een definitie: `_get_dynamic_discharge_reserve_kwh`. De
brug, de verkooptoets en de planning lezen die. Ze mogen er hun eigen
hysterese omheen leggen; het getal is hetzelfde.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 9, 16, 37, tzinfo=timezone.utc)
BLOK = NU + timedelta(hours=20)


def _opzet(c, hass, diepste=6.0, beschikbaar=5.5):
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.beschikbare_energie_kwh = lambda: beschikbaar
    c._estimate_worst_case_deficit_kwh = lambda now, tot: diepste
    c.last_cheap_block_start = BLOK
    c.last_cheap_block_end = BLOK + timedelta(hours=2)
    c.config = dict(c.config or {})
    c.config["available_energy_sensor_entity"] = "sensor.avail"
    hass.states.set("sensor.avail", str(beschikbaar))
    c._verkoop_geblokkeerd_door_reserve = False
    c._verkoop_dicht_sinds = None


def test_drie_lezers_een_getal(make_coordinator, hass):
    c = make_coordinator({})
    _opzet(c, hass)

    reserve = c._get_dynamic_discharge_reserve_kwh(NU, BLOK)
    verkoop = c.may_sell_now(NU)["nodig_voor_woning_kwh"]
    c._should_postpone_charging([(BLOK, BLOK + timedelta(hours=2), 500)], NU, BLOK)
    brug = c.last_needed_kwh_to_bridge
    planning = c._planning_reserve_kwh(NU, {})

    assert verkoop == pytest.approx(reserve, abs=0.01)
    assert brug == pytest.approx(reserve, abs=0.01)
    assert planning == pytest.approx(reserve, abs=0.01)


def test_de_lezers_schrijven_de_uitsplitsing_niet(make_coordinator, hass):
    """Alleen de sturing schrijft `last_reserve_margin_breakdown`; een

    planningskwartier van morgenmiddag mag de uitsplitsing van nu niet
    overschrijven.
    """
    c = make_coordinator({})
    _opzet(c, hass)
    c._get_dynamic_discharge_reserve_kwh(NU, BLOK)
    voor = dict(c.last_reserve_margin_breakdown)

    c._planning_reserve_kwh(NU + timedelta(hours=10), {})
    c.may_sell_now(NU)

    assert c.last_reserve_margin_breakdown == voor


def test_geen_reserve_zonder_blok_dan_de_bodem(make_coordinator, hass):
    c = make_coordinator({})
    _opzet(c, hass)
    c.last_cheap_block_start = None

    assert c.may_sell_now(NU)["nodig_voor_woning_kwh"] == pytest.approx(c._reserve_bodem_kwh(), abs=0.01)
    assert c._planning_reserve_kwh(NU, {}) == pytest.approx(c._reserve_bodem_kwh(), abs=0.01)


def test_de_brug_houdt_zijn_eigen_hysterese(make_coordinator, hass):
    """Dezelfde reserve, maar de brug beslist met een buffer van 10%:

    net eronder is nog "genoeg" zolang hij al genoeg had.
    """
    c = make_coordinator({})
    _opzet(c, hass, diepste=3.0, beschikbaar=6.0)
    c._should_postpone_charging([(BLOK, BLOK + timedelta(hours=2), 500)], NU, BLOK)
    assert c.last_has_enough_energy is True
    reserve = c.last_needed_kwh_to_bridge

    hass.states.set("sensor.avail", str(reserve - 0.05 * reserve))
    c._should_postpone_charging([(BLOK, BLOK + timedelta(hours=2), 500)], NU, BLOK)
    assert c.last_has_enough_energy is True
