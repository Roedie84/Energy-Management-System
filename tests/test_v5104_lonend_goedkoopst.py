"""v5.104.0 - de goedkoopste kwartieren voor de lading die LOONT, niet voor het hele gat.

Gemeld 19-10 (12:47, screenshot van de laadplanning): "Dit is toch een rare
verdeling, goedkoopste kwartieren worden niet allemaal benut." Het plan laadde
12:45-13:30 (33,7 / 33,0 / 32,5 ct) en 13:45, maar niet 13:30 en 14:00
(32,4 ct). Het gat was groter dan er goedkopere kwartieren waren, dus laadde
12:45 mee; maar lonend was maar een paar kWh, en die horen in de goedkoopste.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import PRICE_SCALE_FACTOR

TZ = timezone(timedelta(hours=2))
DAG = datetime(2026, 10, 19, tzinfo=TZ)

# De prijzen van 19-10 vanaf 12:45 (ct), zoals in de kwartierplanning.
PRIJZEN = [33.7, 33.0, 32.5, 32.4, 32.4, 32.4, 32.6, 33.1, 33.6, 34.2, 34.3, 35.7, 39.1,
           34.5, 38.3, 40.4, 42.0, 40.9, 43.0, 44.1, 46.3, 45.0, 45.7, 46.0, 47.6, 46.5,
           44.2, 39.9, 37.9, 38.6, 39.2, 37.3, 34.0, 38.7, 36.1, 34.8, 32.9, 38.5, 36.1,
           34.9, 34.5, 34.8, 33.8, 32.7, 33.1]
BEGIN = DAG.replace(hour=12, minute=45)
BLOK_EIND = DAG.replace(hour=15, minute=30)


def _entries():
    return [
        (BEGIN + timedelta(minutes=15 * i), BEGIN + timedelta(minutes=15 * (i + 1)),
         ct / 100 * PRICE_SCALE_FACTOR)
        for i, ct in enumerate(PRIJZEN)
    ]


def _later():
    return sorted(
        ((ct / 100, BEGIN + timedelta(minutes=15 * i))
         for i, ct in enumerate(PRIJZEN) if BEGIN + timedelta(minutes=15 * i) >= BLOK_EIND),
        key=lambda paar: paar[0], reverse=True,
    )


def _regel(c, prijs_ct, beschikbaar=2.5):
    return c._laadregel(prijs_nu=prijs_ct / 100, beschikbaar=beschikbaar, ruimte=6.0,
                        later=_later(), rendement=85.2, slijtage_ct=2.0,
                        per_kwartier=0.4, zonoverschot=lambda tot: 0.0)


def _kwartier(i):
    return BEGIN + timedelta(minutes=15 * i)


def test_de_laadregel_zegt_hoeveel_lading_loont(make_coordinator, hass):
    c = make_coordinator({})
    r = _regel(c, 33.7)
    assert r["laden"] is True
    # Vanaf het 7e duurste kwartier: 44,2 / 44,1 / 43,0 / 42,0 x 85,2% - 2 > 33,7; 40,9 niet.
    assert r["lonend_kwh"] == 1.6
    assert r["gat_kwh"] == 6.0                                  # het gat is veel groter


def test_het_dure_kwartier_wacht_op_de_goedkoopste(make_coordinator, hass):
    c = make_coordinator({"manual_charge_power": -2400})
    c._get_forecast_entries = lambda *a, **k: _entries()
    besluit = c._laad_op_goedkoopste(_kwartier(0), _regel(c, 33.7))
    assert besluit["laden"] is False
    assert "goedkopere" in besluit["reden"]


def test_het_goedkoopste_kwartier_laadt(make_coordinator, hass):
    c = make_coordinator({"manual_charge_power": -2400})
    c._get_forecast_entries = lambda *a, **k: _entries()
    assert c._laad_op_goedkoopste(_kwartier(3), _regel(c, 32.4))["laden"] is True


def test_zonder_lonend_blijft_het_gat_de_maat(make_coordinator, hass):
    c = make_coordinator({"manual_charge_power": -2400})
    c._get_forecast_entries = lambda *a, **k: _entries()
    regel = {"laden": True, "prijs_nu_eur": 0.337, "gat_kwh": 6.0,
             "nodig_vanaf": BLOK_EIND.isoformat()}
    # 10 kwartieren nodig, maar 8 goedkopere tot het blokeinde: nu laden.
    assert c._laad_op_goedkoopste(_kwartier(0), regel)["laden"] is True
