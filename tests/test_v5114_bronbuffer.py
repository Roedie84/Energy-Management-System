"""v5.114.0: bronnen die even wegvallen houden hun laatste geldige waarde.

Gevraagd 21-10 15:10: "Kan dit voor meer bronnen zijn? Als het er niet is is
het er niet, maar als het er wel is geweest tijdelijk in buffer/cache
opslaan?"
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from custom_components.energy_management_system.bronbuffer import Bronbuffer
from custom_components.energy_management_system.const import PERSISTED_FIELDS
from custom_components.energy_management_system.coordinator import EnergyManagementSystemCoordinator as C

TZ = timezone(timedelta(hours=2))
NU = datetime(2026, 10, 21, 15, 0, tzinfo=TZ)


def _st(state, **attrs):
    return SimpleNamespace(state=state, attributes=attrs)


def test_dagwaarde_tot_middernacht():
    b = Bronbuffer(regels={"sensor.solcast_morgen": ("dag", 0)})
    b.lees("sensor.solcast_morgen", _st("12.5", detailedForecast=[1, 2], friendly_name="x"), NU)
    uit = b.lees("sensor.solcast_morgen", _st("unavailable"), NU + timedelta(hours=8))
    assert uit.state == "12.5" and uit.attributes == {"detailedForecast": [1, 2]} and uit.uit_buffer
    assert "sensor.solcast_morgen" in b.in_gebruik
    # na middernacht is "morgen" van gisteren niet meer geldig
    weg = b.lees("sensor.solcast_morgen", None, NU + timedelta(hours=10))
    assert weg is None and "sensor.solcast_morgen" not in b.in_gebruik


def test_minuten_en_herstel():
    b = Bronbuffer(regels={"sensor.rest": ("minuten", 60)})
    b.lees("sensor.rest", _st("3.1"), NU)
    assert b.lees("sensor.rest", _st("unknown"), NU + timedelta(minutes=59)).state == "3.1"
    assert b.lees("sensor.rest", _st("unknown"), NU + timedelta(minutes=61)).state == "unknown"
    vers = _st("2.0")
    assert b.lees("sensor.rest", vers, NU + timedelta(minutes=70)) is vers


def test_metingen_nooit():
    b = Bronbuffer(regels={})
    b.lees("sensor.accu_vermogen", _st("500"), NU)
    assert b.lees("sensor.accu_vermogen", _st("unavailable"), NU).state == "unavailable"
    assert b.opslag == {}


def test_regels_uit_de_configuratie():
    r = C._bron_regels({"solar_forecast_sensor_entity": "sensor.morgen",
                        "solar_extended_forecast_sensor_entities": ["sensor.d3", "sensor.d4"],
                        "solar_remaining_today_sensor_entity": "sensor.rest",
                        "co2_intensity_sensor_entity": "sensor.co2",
                        "gas_price_sensor_entity": "sensor.gas",
                        "battery_power_sensor_entity": "sensor.accu"})
    assert r["sensor.morgen"] == ("dag", 0) and r["sensor.d4"] == ("dag", 0) and r["sensor.gas"] == ("dag", 0)
    assert r["sensor.rest"] == ("minuten", 60) and r["sensor.co2"] == ("minuten", 120)
    assert "sensor.accu" not in r


def test_read_sensor_float_valt_terug(monkeypatch):
    from homeassistant.util import dt as dt_util

    monkeypatch.setattr(dt_util, "now", lambda *a: NU, raising=False)
    c = object.__new__(C)
    c.config = {"solar_forecast_sensor_entity": "sensor.morgen"}
    staten = {"sensor.morgen": _st("14.2", unit_of_measurement="kWh")}
    c.hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: staten.get(e)))
    assert c._read_sensor_float("sensor.morgen") == 14.2
    staten["sensor.morgen"] = _st("unavailable")
    assert c._read_sensor_float("sensor.morgen") == 14.2
    assert c.bronbuffer_opslag["sensor.morgen"]["state"] == "14.2"


def test_bewaard_en_export():
    assert PERSISTED_FIELDS["bronbuffer_opslag"] == {"type": "plain"}
    b = Bronbuffer(regels={"s": ("dag", 0)})
    b.lees("s", _st("1"), NU)
    n = Bronbuffer()
    n.herstel(b.export())
    assert n.opslag["s"]["state"] == "1"


def test_uurprijzen_als_kwartieren_met_patroon(monkeypatch):
    from homeassistant.util import dt as dt_util

    nu = datetime(2026, 10, 21, 10, 50, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "now", lambda *a: nu, raising=False)
    c = object.__new__(C)
    c.config = {"price_sensor_entity": "sensor.prijs"}
    c.hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: None))
    c.instelling = lambda k, d=None: d
    c.prijs_forecast_cache = None
    c.prijsgeschiedenis = {"2026-10-21T16": 0.40}
    c._prijs_kwartiervorm = {"18:0": -0.02, "18:1": -0.01, "18:2": 0.01, "18:3": 0.02}   # 16 UTC = 18 lokaal
    e = c._get_forecast_entries()
    prijzen = [round(x[2] / 10_000_000, 4) for x in e]
    assert prijzen == [0.38, 0.39, 0.41, 0.42]
