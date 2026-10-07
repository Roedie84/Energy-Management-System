"""Het plan rekent met het blok dat de sturing op dat moment kent (v5.33).

Gemeten over 30 dagen (plantoetsing, plan van 08:00): verkocht mediaan
68% minder dan gepland, 5 van de 30 dagen binnen de marge, en het plan
voorspelde een laagste stand van 10-17% waar het werkelijk 35-66% werd.

De oorzaak: het plan nam voor elk kwartier het goedkope blok van NU. Om
08:00 is dat het middagblok van vandaag; voor een kwartier om 18:30 ligt
dat blok al achter het kwartier, en dan gold alleen de bodem (1,3 kWh). De
sturing kent om 18:30 het blok van morgen en houdt de reserve tot dan vast.
Het plan verkocht dus wat de sturing nooit zou verkopen.
"""
from datetime import datetime, timedelta, timezone

import pytest

TZ = timezone.utc
DAG = datetime(2026, 10, 7, tzinfo=TZ)
NU = DAG.replace(hour=8)
BLOK = DAG.replace(hour=11, minute=15)
BLOK_EIND = DAG.replace(hour=13)


def _prijzen(tot_dag_eind=True, met_morgen=False):
    """Kwartieren van 08:00 tot middernacht: dal 11:15-13:00, dure avond,
    en een iets lagere nacht. Met `met_morgen` ook morgen, met een dal om
    12:00."""
    reeks = []
    t = NU
    eind = DAG + timedelta(days=2 if met_morgen else 1)
    while t < eind:
        uur = t.hour + t.minute / 60
        if BLOK <= t < BLOK_EIND:
            p = 0.30
        elif t.date() > DAG.date() and 12 <= uur < 13:
            p = 0.298
        elif 17 <= uur < 21:
            p = 0.45
        else:
            p = 0.36 if uur < 22 else 0.33
        reeks.append((t, t + timedelta(minutes=15), int(p * 10_000_000)))
        t += timedelta(minutes=15)
    return reeks


def _opzet(c):
    c.last_cheap_block_start = BLOK
    c.last_cheap_block_end = BLOK_EIND
    c.bruikbare_capaciteit_kwh = lambda: 7.8
    c._estimate_worst_case_deficit_kwh = lambda nu, tot: 3.0


def test_zonder_prijzen_van_morgen_geldt_het_blok_een_etmaal_later(make_coordinator, hass):
    c = make_coordinator({})
    _opzet(c)
    avond = DAG.replace(hour=18, minute=30)

    assert c._volgend_blok_voor(_prijzen(), avond) == BLOK + timedelta(days=1)


def test_met_prijzen_van_morgen_geldt_het_dal_van_morgen(make_coordinator, hass):
    c = make_coordinator({})
    _opzet(c)
    avond = DAG.replace(hour=18, minute=30)

    assert c._volgend_blok_voor(_prijzen(met_morgen=True), avond) == (
        DAG + timedelta(days=1)
    ).replace(hour=12)


def test_de_avondreserve_is_niet_meer_alleen_de_bodem(make_coordinator, hass):
    c = make_coordinator({})
    _opzet(c)
    avond = DAG.replace(hour=18, minute=30)
    bodem = c._reserve_bodem_kwh()

    oud = c._planning_reserve_kwh(avond, {})  # zonder prijzen: oude gedrag
    nieuw = c._planning_reserve_kwh(avond, {}, _prijzen())
    sturing = c._get_dynamic_discharge_reserve_kwh(
        avond, BLOK + timedelta(days=1), bewaar=False
    )

    assert oud == pytest.approx(bodem)
    assert nieuw == pytest.approx(max(bodem, sturing), abs=0.001)
    assert nieuw > bodem


def test_binnen_het_lopende_blok_blijft_het_de_bodem(make_coordinator, hass):
    """De sturing houdt het lopende blok vast (v5.28.5); daar is geen
    reserve, want er wordt geladen."""
    c = make_coordinator({})
    _opzet(c)

    assert c._planning_reserve_kwh(
        DAG.replace(hour=12), {}, _prijzen()
    ) == pytest.approx(c._reserve_bodem_kwh())


def test_voor_het_blok_verandert_er_niets(make_coordinator, hass):
    c = make_coordinator({})
    _opzet(c)
    ochtend = DAG.replace(hour=9)

    assert c._planning_reserve_kwh(ochtend, {}, _prijzen()) == pytest.approx(
        c._planning_reserve_kwh(ochtend, {})
    )


def test_de_dalzoeker_van_de_sturing_houdt_zijn_hysterese(make_coordinator, hass):
    """`stabiel=False` is alleen voor de planning; de sturing van nu houdt
    het vorige blok vast als het bijna even goedkoop is."""
    c = make_coordinator({})
    reeks = _prijzen(met_morgen=True)
    c.last_cheap_block_start = BLOK
    start, _eind = c._cheapest_block_range(reeks, NU)
    assert start == BLOK
    start, _eind = c._cheapest_block_range(reeks, NU, stabiel=False)
    assert start == (DAG + timedelta(days=1)).replace(hour=12)
