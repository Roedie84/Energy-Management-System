"""v5.127.2: geen nieuwe netlading vanaf 95 % accustand.

Gemeld zondag 25-10 16:24 (wintertijd, CET): cockpit "Accu laadt 2,2 kW,
gepland ontladen 0,5 kW". Het EMS zette om 16:24:43 manual -2400. Oorzaak:
de accu zakte om 16:24:12 van 98 naar 97 %. Het goedkope blok (16:00-17:15,
16:15 = 14,2 ct, het goedkoopste kwartier van de horizon) liep; de
hysterese van v5.95 (97 % van het BRUIKBARE deel, boven 10 % ondergrens)
zag 97 % op de sensor als 96,7 % en liet een nieuwe lading toe; de laadregel
vond de avond (25-30 ct) duurder en laadde 2,4 kW. Om 16:30 (15,6 ct, niet
meer het goedkoopste kwartier) weer smart. De herstarts van 15:54 en 16:09
waren toeval: het blok na de herstart (16:00-17:15) had hetzelfde einde.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    LAADBLOK_HERLAAD_SOC_PROCENT,
    PRICE_SCALE_FACTOR,
)

CET = timezone(timedelta(hours=1))
DAG = datetime(2026, 10, 25, tzinfo=CET)
NU = DAG.replace(hour=16, minute=24, second=43)
OCHTENDBLOK = DAG.replace(hour=10, minute=45)


def _ct(b: datetime) -> float:
    t = b.hour + b.minute / 60
    if b.date() == DAG.date():
        if 10.75 <= t < 16.0:
            return 15.0
        if 16.25 <= t < 16.5:
            return 14.2            # het goedkoopste kwartier
        if 16.0 <= t < 17.25:
            return 15.6
        if 17.25 <= t < 21.5:
            return 28.0            # avond: verkopen
        return 20.0
    if 1.75 <= t < 5.0:
        return 14.7                # morgen de nacht
    return 22.0 if t < 7 or t >= 9 else 48.0


def _entries():
    uit = []
    for i in range(2 * 96):
        b = DAG + timedelta(minutes=15 * i)
        uit.append((b, b + timedelta(minutes=15), _ct(b) / 100 * PRICE_SCALE_FACTOR))
    return uit


def _live(make_coordinator, soc, vorige="default_smart", beschikbaar=10.0, ruimte=0.35):
    """De beslissing met de getallen van 16:24:43 en een laadregel die loont."""
    c = make_coordinator({})
    entries = _entries()
    c._get_forecast_entries = lambda: entries
    c.huidige_prijs_eur_per_kwh = lambda: 0.142
    c._resterende_laadruimte_kwh = lambda: ruimte
    c.beschikbare_energie_kwh = lambda: beschikbaar
    c.accustand_procent = lambda: soc
    c._laadkosten_ct = lambda: 4.22
    c._balanceer_laadbesluit = lambda *a, **k: None
    c._verwacht_zonoverschot_kwh = lambda *a, **k: 0.0
    c._zon_vol_om = lambda *a, **k: None
    c._goedkoopste_laadmomenten = lambda *a, **k: True
    c.last_reason = vorige
    return c


BLOK = (DAG.replace(hour=16), DAG.replace(hour=17, minute=15))


def test_drempel_95():
    assert LAADBLOK_HERLAAD_SOC_PROCENT == 95.0


def test_regel(make_coordinator):
    h = make_coordinator({})._accu_te_vol_voor_netladen
    assert h(97.0, False) is True
    assert h(95.0, False) is True
    assert h(94.9, False) is False
    assert h(98.0, True) is False      # lopende lading laadt door
    assert h(None, False) is False     # onbekend: geen grens


def test_oude_hysterese_liet_97_procent_door(make_coordinator):
    # 10,0 van 10,35 kWh bruikbaar = 96,6 % < 97 %: de v5.95-toets greep niet.
    c = _live(make_coordinator, soc=None)
    uit = c.laadbesluit_uit_het_net(NU, *BLOK)
    assert uit["laden"] is True        # zo ging het om 16:24:43


def test_bij_97_procent_geen_nieuwe_netlading(make_coordinator):
    c = _live(make_coordinator, soc=97.0)
    uit = c.laadbesluit_uit_het_net(NU, *BLOK)
    assert uit["laden"] is False
    assert uit["hysterese"] is True
    assert "97%" in uit["reden"]


def test_lopende_lading_laadt_door(make_coordinator):
    c = _live(make_coordinator, soc=97.0, vorige="grid_charging_profitable")
    assert c.laadbesluit_uit_het_net(NU, *BLOK)["laden"] is True


def test_onder_95_procent_ongewijzigd(make_coordinator):
    c = _live(make_coordinator, soc=80.0, beschikbaar=7.0, ruimte=3.35)
    assert c.laadbesluit_uit_het_net(NU, *BLOK)["laden"] is True


def test_balanceerlading_gaat_voor(make_coordinator):
    c = _live(make_coordinator, soc=97.0)
    c._balanceer_laadbesluit = lambda *a, **k: {"laden": True, "soort": "balanceren"}
    assert c.laadbesluit_uit_het_net(NU, *BLOK)["laden"] is True


def test_herstart_rond_het_blok_met_volle_accu(make_coordinator, hass):
    """Herstart om 16:09: blok uit de prijzen, ochtendblok bewaard, accu 97 %."""
    c = _live(make_coordinator, soc=97.0)
    c._apply_persisted_state({"_gekozen_blok_start": OCHTENDBLOK.isoformat()})
    c.last_cheap_block_start = c.last_cheap_block_end = None   # niet bewaard
    entries = _entries()
    nieuw = c._cheapest_block_range(entries, NU)
    blok = c._lopend_blok(NU, *nieuw, entries)
    assert blok[0] <= NU < blok[1]                    # het blok loopt
    assert blok[1] == DAG.replace(hour=17, minute=15)
    uit = c.laadbesluit_uit_het_net(NU, *blok)
    assert uit["laden"] is False
    assert uit["hysterese"] is True


def test_herstart_zonder_volle_accu_laadt_wel(make_coordinator, hass):
    # Gedrag onder 95 % blijft: na de herstart beslist de laadregel gewoon.
    c = _live(make_coordinator, soc=60.0, beschikbaar=5.2, ruimte=5.15)
    c._apply_persisted_state({"_gekozen_blok_start": OCHTENDBLOK.isoformat()})
    c.last_cheap_block_start = c.last_cheap_block_end = None
    entries = _entries()
    blok = c._lopend_blok(NU, *c._cheapest_block_range(entries, NU), entries)
    assert c.laadbesluit_uit_het_net(NU, *blok)["laden"] is True


def _plan(make_coordinator):
    c = make_coordinator({})
    c._verwacht_zonoverschot_kwh = lambda *a, **k: 0.0
    c._zon_vol_om = lambda *a, **k: None
    c._goedkoopste_laadmomenten = lambda *a, **k: True
    regels = {
        "slijtage_ct": 4.22, "rendement": 83.9, "salderen": True,
        "reeks": [(b, _ct(b) / 100) for b, _e, _p in _entries()],
        "laadde_vorig": False, "blok": BLOK,
    }
    return c, regels


def test_plan_toopt_een_volle_accu_niet_bij(make_coordinator):
    c, regels = _plan(make_coordinator)
    min_soc = c.effective_min_soc_percent()
    bruikbaar = 10.35
    soc_97 = bruikbaar * (97 - min_soc) / (100 - min_soc)
    assert soc_97 < 0.97 * bruikbaar                 # oude toets liet hem door
    einde = DAG.replace(hour=16, minute=30)
    assert c._plan_laadt(regels, einde, 0.142, soc_97, bruikbaar, 0.6, 0.6) == 0.0


def test_plan_laadt_onder_95_procent_zoals_voorheen(make_coordinator):
    c, regels = _plan(make_coordinator)
    einde = DAG.replace(hour=16, minute=30)
    assert c._plan_laadt(regels, einde, 0.142, 5.0, 10.35, 0.6, 0.6) > 0.0


def test_plan_lopende_lading_laadt_door(make_coordinator):
    c, regels = _plan(make_coordinator)
    regels["laadde_vorig"] = True
    min_soc = c.effective_min_soc_percent()
    soc_97 = 10.35 * (97 - min_soc) / (100 - min_soc)
    einde = DAG.replace(hour=16, minute=30)
    assert c._plan_laadt(regels, einde, 0.142, soc_97, 10.35, 0.6, 0.6) > 0.0
