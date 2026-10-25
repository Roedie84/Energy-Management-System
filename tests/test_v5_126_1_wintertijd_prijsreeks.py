"""v5.126.1 (L-EMS-036): de wintertijdnacht houdt alle honderd kwartieren.

Leerronde 24-10 19:40: de kwartierplanning voor 25-10 had 95 rijen in plaats
van 100 (02:30 werd gevolgd door 03:00). De prijsbron gaf er wel 100. Oorzaak:
binnen één zoneinfo-tijdzone negeert Python `fold` bij ==, hash en aftrekken.
02:00 zomertijd en 02:00 wintertijd telden daardoor als dubbele (vier
kwartieren weg) en het kwartier 02:45 zomertijd - 02:00 wintertijd kreeg een
duur van -45 minuten (door het plan overgeslagen).

De testomgeving zet `dt_util.as_local` standaard op "niets omrekenen"; hier
staat hij op de echte Europe/Amsterdam, zoals in Home Assistant.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

import custom_components.energy_management_system.coordinator as coord
from custom_components.energy_management_system.const import PRICE_SCALE_FACTOR

AMS = ZoneInfo("Europe/Amsterdam")


def _echte_klok(monkeypatch):
    def as_local(value):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(AMS)

    monkeypatch.setattr(coord.dt_util, "as_local", as_local)


def _wintertijdnacht():
    """24-10 22:00 CEST t/m 25-10 23:45 CET, zoals Zonneplan hem geeft:
    zoneinfo-tijdstippen, de herhaalde klokuren met fold=1."""
    begin = datetime(2026, 10, 24, 20, 0, tzinfo=timezone.utc)
    reeks = []
    for i in range(26 * 4 + 4):
        s = (begin + timedelta(minutes=15 * i)).astimezone(AMS)
        e = (begin + timedelta(minutes=15 * (i + 1))).astimezone(AMS)
        reeks.append({
            "start_date": s, "end_date": e,
            "price_tax_included": {"amount": 1_200_000 + i * 1000},
        })
    return reeks


@pytest.fixture
def c(make_coordinator, hass, monkeypatch):
    _echte_klok(monkeypatch)
    hass.states.set("sensor.price", "0", {"forecast": _wintertijdnacht()})
    return make_coordinator({"price_sensor_entity": "sensor.price"})


def test_alle_kwartieren_van_25_oktober_blijven(c):
    entries = c._get_forecast_entries()
    op_25 = [e for e in entries if e[0].date().isoformat() == "2026-10-25"]
    assert len(op_25) == 100
    assert c.prijsreeks_bevindingen["dubbele"] == []
    assert c.prijsreeks_bevindingen["gaten"] == []


def test_elk_kwartier_duurt_vijftien_minuten_en_de_reeks_loopt_op(c):
    entries = c._get_forecast_entries()
    for start, einde, _p in entries:
        assert einde - start == timedelta(minutes=15)
    for (a, _, _), (b, _, _) in zip(entries, entries[1:]):
        assert b - a == timedelta(minutes=15)
        assert b > a


def test_kloktijd_blijft_lokaal(c):
    entries = c._get_forecast_entries()
    labels = [e[0].strftime("%H:%M") for e in entries
              if e[0].date().isoformat() == "2026-10-25"][:16]
    assert labels[8:16] == ["02:00", "02:15", "02:30", "02:45",
                            "02:00", "02:15", "02:30", "02:45"]


def test_het_tweede_0245_heeft_zijn_eigen_prijs(c):
    entries = c._get_forecast_entries()
    # 02:50 wintertijd = 01:50 UTC
    nu = datetime(2026, 10, 25, 1, 50, tzinfo=timezone.utc).astimezone(AMS)
    huidig = [e for e in entries if e[0] <= nu < e[1]]
    assert len(huidig) == 1
    assert huidig[0][0].utcoffset() == timedelta(hours=1)
    # en 02:50 zomertijd (00:50 UTC) vindt het eerste
    nu = datetime(2026, 10, 25, 0, 50, tzinfo=timezone.utc).astimezone(AMS)
    huidig = [e for e in entries if e[0] <= nu < e[1]]
    assert len(huidig) == 1
    assert huidig[0][0].utcoffset() == timedelta(hours=2)


def test_een_echte_dubbele_blijft_gevangen(c, hass):
    reeks = _wintertijdnacht()
    reeks.insert(5, dict(reeks[4]))
    hass.states.set("sensor.price", "0", {"forecast": reeks})
    entries = c._get_forecast_entries()
    assert len(c.prijsreeks_bevindingen["dubbele"]) == 1
    assert len(entries) == len(reeks) - 1


def test_controle_ziet_het_herhaalde_klokuur_niet_als_dubbele(make_coordinator, hass):
    """De oude toets liet dit open ('of eerste == tweede')."""
    c = make_coordinator({})
    eerste = datetime(2026, 10, 25, 2, 30, tzinfo=AMS, fold=0)
    tweede = datetime(2026, 10, 25, 2, 30, tzinfo=AMS, fold=1)
    bevindingen = c._controleer_prijsreeks([
        (eerste, eerste + timedelta(minutes=15), 0.25),
        (tweede, tweede + timedelta(minutes=15), 0.30),
    ])
    assert bevindingen["dubbele"] == []
