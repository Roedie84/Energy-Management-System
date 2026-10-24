"""v5.126.0 (L-EMS-034) - na een herstart komt een blok van vandaag niet terug
als het blok van morgen al gekozen was.

Leerronde 24-10: op 23-10 kwam direct na een herstart een laadblok van vandaag
terug, terwijl dat van morgen al vastlag (≈ € 0,19, accu werd niet vol).
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    PERSISTED_FIELDS,
    PRICE_SCALE_FACTOR,
)

TZ = timezone(timedelta(hours=2))
DAG = datetime(2026, 10, 23, tzinfo=TZ)
MORGEN_BLOK = (DAG + timedelta(days=1)).replace(hour=12, minute=30)


def _entries():
    # Vandaag: dal 13:30-15:15 (pas begonnen NA de prijzen van morgen),
    # morgen: een dieper dal 12:30-15:15.
    uit = []
    for d in (0, 1):
        for i in range(96):
            b = DAG + timedelta(days=d, minutes=15 * i)
            t = b.hour + b.minute / 60
            if d == 0:
                ct = 19.8 if 13.5 <= t < 15.25 else 33.0
            else:
                ct = 15.0 if 12.5 <= t < 15.25 else 33.0
            uit.append((b, b + timedelta(minutes=15), ct / 100 * PRICE_SCALE_FACTOR))
    return uit


def _na_herstart(c):
    c.last_cheap_block_start = c.last_cheap_block_end = None


def test_veld_wordt_bewaard():
    assert PERSISTED_FIELDS["_gekozen_blok_start"]["type"] == "datetime"


def test_morgen_gekozen_dan_komt_vandaag_niet_terug(make_coordinator, hass):
    c = make_coordinator({})
    c._apply_persisted_state({"_gekozen_blok_start": MORGEN_BLOK.isoformat()})
    _na_herstart(c)
    entries = _entries()
    nu = DAG.replace(hour=14)
    nieuw = c._cheapest_block_range(entries, nu)
    assert nieuw[0] == MORGEN_BLOK
    assert c._lopend_blok(nu, *nieuw, entries) == nieuw


def test_zonder_onthouden_keuze_blijft_het_lopende_blok(make_coordinator, hass):
    # Gedrag van v5.28.5 ongewijzigd: niets bewaard -> blok van vandaag.
    c = make_coordinator({})
    _na_herstart(c)
    c._gekozen_blok_start = None
    entries = _entries()
    nu = DAG.replace(hour=14)
    blok = c._lopend_blok(nu, *c._cheapest_block_range(entries, nu), entries)
    assert blok[0].date() == DAG.date() and blok[0] <= nu < blok[1]


def test_vandaag_gekozen_blijft_het_lopende_blok(make_coordinator, hass):
    # Het bewaarde blok was dat van vandaag (al begonnen): dat komt terug.
    c = make_coordinator({})
    c._gekozen_blok_start = DAG.replace(hour=13, minute=30)
    _na_herstart(c)
    entries = _entries()
    nu = DAG.replace(hour=14)
    blok = c._lopend_blok(nu, *c._cheapest_block_range(entries, nu), entries)
    assert blok == (DAG.replace(hour=13, minute=30), DAG.replace(hour=15, minute=15))


def test_normale_blokkeuze_ongewijzigd(make_coordinator, hass):
    c = make_coordinator({})
    c._gekozen_blok_start = MORGEN_BLOK
    entries = _entries()
    # Een onthouden lopend blok blijft het blok tot het eindigt.
    c.last_cheap_block_start = DAG.replace(hour=13, minute=30)
    c.last_cheap_block_end = DAG.replace(hour=15, minute=15)
    nu = DAG.replace(hour=14)
    assert c._lopend_blok(nu, MORGEN_BLOK, MORGEN_BLOK + timedelta(hours=3), entries)[0] == DAG.replace(hour=13, minute=30)
    # 's Ochtends, vóór alles: het nieuwe blok.
    _na_herstart(c)
    vroeg = DAG.replace(hour=8)
    nieuw = c._cheapest_block_range(entries, vroeg)
    assert c._lopend_blok(vroeg, *nieuw, entries) == nieuw


def test_kapotte_opslag_valt_terug(make_coordinator, hass):
    c = make_coordinator({})
    c._gekozen_blok_start = datetime(2026, 10, 24, 12, 30)   # zonder tijdzone
    _na_herstart(c)
    entries = _entries()
    nu = DAG.replace(hour=14)
    blok = c._lopend_blok(nu, *c._cheapest_block_range(entries, nu), entries)
    assert blok[0].date() == DAG.date()
