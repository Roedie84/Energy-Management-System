"""v5.28.5 - een lopend blok blijft het blok, en laden in de goedkoopste kwartieren.

Gemeld op 4 oktober: "Waarom straks bij duurdere goedkope uren wel manueel
laden en nu niet??" Om 13:22 sprong het blok naar morgen 12:30 (de prijzen
van morgen waren binnen); de sturing gebruikte daarna de dipregel, terwijl
het plan de middag nog als blok zag en wel laadde - en dat om 14:45 tegen
21,9 ct, met 18,5 ct om 14:00.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import PRICE_SCALE_FACTOR

TZ = timezone(timedelta(hours=2))
DAG = datetime(2026, 10, 4, tzinfo=TZ)


def _prijs(dag, uur, minuut):
    t = uur + minuut / 60
    if 12.5 <= t < 15.25:
        return 18.5 if t == 14.0 else 19.8
    return 41.0 if 18 <= t < 23 else 33.0


def _entries():
    uit = []
    for d in (0, 1):
        for i in range(96):
            b = DAG + timedelta(days=d, minutes=15 * i)
            ct = _prijs(d, b.hour, b.minute) - (1.0 if d == 1 else 0.0)   # morgen goedkoper
            uit.append((b, b + timedelta(minutes=15), ct / 100 * PRICE_SCALE_FACTOR))
    return uit


def test_het_lopende_blok_uit_de_prijzen_van_vandaag(make_coordinator, hass):
    c = make_coordinator({})
    c.last_cheap_block_start = c.last_cheap_block_end = None       # na een herstart
    entries = _entries()
    nu = DAG.replace(hour=13, minute=22)
    nieuw = c._cheapest_block_range(entries, nu)
    assert nieuw[0].date() == (DAG + timedelta(days=1)).date()      # zonder reparatie: morgen
    blok = c._lopend_blok(nu, *nieuw, entries)
    assert blok[0] <= nu < blok[1]
    assert blok[0].date() == DAG.date()


def test_een_laat_duur_kwartier_wordt_geen_blok(make_coordinator, hass):
    c = make_coordinator({})
    c.last_cheap_block_start = c.last_cheap_block_end = None
    entries = _entries()
    nu = DAG.replace(hour=23, minute=30)
    nieuw = c._cheapest_block_range(entries, nu)
    assert c._lopend_blok(nu, *nieuw, entries) == nieuw


def test_het_onthouden_blok_blijft_tot_het_eindigt(make_coordinator, hass):
    c = make_coordinator({})
    c.last_cheap_block_start = DAG.replace(hour=12, minute=30)
    c.last_cheap_block_end = DAG.replace(hour=15, minute=15)
    morgen = (DAG + timedelta(days=1)).replace(hour=12, minute=30)
    assert c._lopend_blok(DAG.replace(hour=14), morgen, morgen + timedelta(hours=3))[0] == DAG.replace(hour=12, minute=30)
    assert c._lopend_blok(DAG.replace(hour=15, minute=15), morgen, morgen + timedelta(hours=3))[0] == morgen


def test_laden_wacht_op_de_goedkoopste_kwartieren(make_coordinator, hass):
    c = make_coordinator({"manual_charge_power": -2400})
    entries = _entries()
    c._get_forecast_entries = lambda *a, **k: entries
    nodig = DAG.replace(hour=19).isoformat()
    duur = c._laad_op_goedkoopste(DAG.replace(hour=13), {"laden": True, "prijs_nu_eur": 0.198, "gat_kwh": 0.6, "nodig_vanaf": nodig})
    goedkoop = c._laad_op_goedkoopste(DAG.replace(hour=14), {"laden": True, "prijs_nu_eur": 0.185, "gat_kwh": 0.6, "nodig_vanaf": nodig})
    assert duur["laden"] is False and "goedkopere" in duur["reden"]
    assert goedkoop["laden"] is True


def test_niet_lonend_blijft_niet_lonend(make_coordinator, hass):
    c = make_coordinator({})
    regel = {"laden": False, "reden": "loont niet"}
    assert c._laad_op_goedkoopste(DAG, regel) is regel


def test_de_laadregel_geeft_het_moment_waarop_de_lading_nodig_is(make_coordinator, hass):
    c = make_coordinator({})
    later = [(0.41, DAG.replace(hour=19)), (0.40, DAG.replace(hour=20))]
    r = c._laadregel(prijs_nu=0.185, beschikbaar=0.2, ruimte=3.0, later=later, rendement=84.6,
                     slijtage_ct=11.26, per_kwartier=0.6, zonoverschot=lambda tot: 0.0)
    assert r["nodig_vanaf"] == DAG.replace(hour=19).isoformat()


def test_beslissing_en_plan_gebruiken_dezelfde_stap():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    assert "return self._laad_op_goedkoopste(now, uit)" in bron
    assert "regel = self._laad_op_goedkoopste(einde - timedelta(minutes=15), regel)" in bron
