"""v5.126.1 (L-EMS-035): de stand van 'PV hourly forecast bias' leest het UTC-uur.

Leerronde 24-10 15:40 (zomertijd, +2): de sensor gaf 0,487 - de factor onder
sleutel 15 (17:00 lokaal) - terwijl om 13:00 UTC de factor 0,823 gold. De
profielsleutels zijn sinds v5.24 UTC-uren; alleen de stand gebruikte nog het
klokuur. De verwachting zelf (_utc_uur) rekende al goed.
"""
from datetime import datetime, timedelta, timezone

import custom_components.energy_management_system.coordinator as coord
import custom_components.energy_management_system.sensor as sensor_mod

ZOMERTIJD = timezone(timedelta(hours=2))
WINTERTIJD = timezone(timedelta(hours=1))


def _sensor(coordinator):
    return sensor_mod.PvHourlyBiasSensor(coordinator, "entry1")


def _klok(monkeypatch, moment):
    monkeypatch.setattr(sensor_mod.dt_util, "now", lambda: moment)
    monkeypatch.setattr(coord.dt_util, "now", lambda: moment)


def test_stand_volgt_het_utc_uur_in_de_zomertijd(make_coordinator, hass, monkeypatch):
    c = make_coordinator({})
    c.pv_hourly_bias_history = {13: [0.823] * 7, 15: [0.487] * 7}
    _klok(monkeypatch, datetime(2026, 10, 24, 15, 41, tzinfo=ZOMERTIJD))
    assert _sensor(c).native_value == 0.823


def test_stand_volgt_het_utc_uur_in_de_wintertijd(make_coordinator, hass, monkeypatch):
    c = make_coordinator({})
    c.pv_hourly_bias_history = {13: [0.823] * 7, 14: [0.6] * 7}
    _klok(monkeypatch, datetime(2026, 10, 26, 14, 10, tzinfo=WINTERTIJD))
    assert _sensor(c).native_value == 0.823


def test_geen_geleerde_factor_geeft_none(make_coordinator, hass, monkeypatch):
    c = make_coordinator({})
    c.pv_hourly_bias_history = {15: [0.487] * 7}
    _klok(monkeypatch, datetime(2026, 10, 24, 15, 41, tzinfo=ZOMERTIJD))
    assert _sensor(c).native_value is None
