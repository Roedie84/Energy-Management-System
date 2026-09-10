"""De reserve-uitsplitsing veroudert niet meer (v4.9).

Gemeld met een schermafdruk van de aandachtspunten, tijdens het
goedkope blok van 09:30 tot 17:30:

    Eén reserve: Er is een tweede reservedefinitie ingeslopen:
    verkooptoets wijkt af van de sturing. Dat was de fout van v3.92 tot
    v4.1.

De zelfcontrole had gelijk dát ze uiteenliepen, maar niet waarom. In
het goedkope blok geeft de reserve `None` terug (`now >=
cheap_block_start`) en schrijft ze geen nieuwe uitsplitsing - dus bleef
`last_reserve_margin_breakdown` de waarde van vóór half tien vasthouden.
De verkooptoets ziet hetzelfde blok, komt op de bodem uit, en dan
vergelijkt de controle een verouderd getal met een vers getal.

Twee dingen: de uitsplitsing wordt leeggemaakt als er geen reserve is -
een dashboard dat een reserve toont die niet meer geldt, is erger dan
een leeg vak - en de zelfcontrole zwijgt als er geen blok in zicht is.

Dit is dezelfde klasse als de kijkvelden van v3.92: een veld dat alleen
in één tak wordt gezet en nooit gewist.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 10, 11, 0, tzinfo=timezone.utc)
BLOK = datetime(2026, 9, 10, 9, 30, tzinfo=timezone.utc)


def _in_het_blok(c, hass):
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.last_cheap_block_start = BLOK
    c.last_cheap_block_end = BLOK + timedelta(hours=8)
    c.last_reserve_margin_breakdown = {"reserve_kwh_after_margin": 3.92, "total_percent": 50.0}


def test_de_uitsplitsing_wordt_leeggemaakt(make_coordinator, hass):
    c = make_coordinator({})
    _in_het_blok(c, hass)

    reserve = c._get_dynamic_discharge_reserve_kwh(NU, BLOK)

    assert reserve is None
    assert c.last_reserve_margin_breakdown == {}


def test_zonder_bewaren_blijft_de_uitsplitsing_staan(make_coordinator, hass):
    """De lezers (brug, verkooptoets, planning) mogen hem niet wissen."""
    c = make_coordinator({})
    _in_het_blok(c, hass)
    voor = dict(c.last_reserve_margin_breakdown)

    c._get_dynamic_discharge_reserve_kwh(NU, BLOK, bewaar=False)

    assert c.last_reserve_margin_breakdown == voor


def test_de_zelfcontrole_zwijgt_zonder_blok(make_coordinator, hass):
    from custom_components.energy_management_system import coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator({})
    c.last_cheap_block_start = BLOK          # al begonnen
    c.last_reserve_margin_breakdown = {}
    c.last_needed_kwh_to_bridge = None
    c.last_sell_check = {"nodig_voor_woning_kwh": 1.296}

    uit = c.zelfcontrole_een_reserve()

    assert uit["in_orde"] is True
    assert "geen reserve" in uit["uitleg"].lower() or "geen blok" in uit["uitleg"].lower()


def test_de_zelfcontrole_meldt_nog_steeds_een_echt_verschil(make_coordinator, hass):
    from custom_components.energy_management_system import coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator({})
    c.last_cheap_block_start = NU + timedelta(hours=8)
    c.last_reserve_margin_breakdown = {"reserve_kwh_after_margin": 6.13}
    c.last_needed_kwh_to_bridge = 4.42
    c.last_sell_check = {"nodig_voor_woning_kwh": 6.13}

    uit = c.zelfcontrole_een_reserve()

    assert uit["in_orde"] is False
    assert "brug" in uit["afwijkend"]
