"""v5.113.2: de laatst bekende prijzen bij een storing van de prijsbron.

Gemeld 21-10 14:58: "Kwartierprijzen waren bekend, maar schijnbaar na een
bepaald tijdstip niet meer. Waarom niet in de cache opgeslagen?"
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from homeassistant.util import dt as dt_util

from custom_components.energy_management_system.const import PERSISTED_FIELDS
from custom_components.energy_management_system.coordinator import EnergyManagementSystemCoordinator as C


def _reeks(begin, n):
    return [{"start_date": (begin + timedelta(minutes=15 * i)).isoformat(),
             "end_date": (begin + timedelta(minutes=15 * (i + 1))).isoformat(),
             "price_tax_included": {"amount": 3_000_000 + i}} for i in range(n)]


def _c(attrs):
    c = object.__new__(C)
    c.config = {"price_sensor_entity": "sensor.prijs"}
    toestand = SimpleNamespace(attributes=attrs) if attrs is not None else None
    c.hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: toestand))
    c.instelling = lambda k, d=None: d
    c.prijs_forecast_cache = None
    return c


def test_storing_gebruikt_de_laatste_reeks(monkeypatch):
    nu = datetime(2026, 10, 21, 12, 50, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "now", lambda *a: nu, raising=False)
    begin = nu.replace(minute=0) - timedelta(hours=10)
    c = _c({"forecast": _reeks(begin, 4 * 34)})          # tot en met morgen
    goed = c._get_forecast_entries()
    assert len(goed) == 136 and c.prijs_forecast_cache["sensor"] == "sensor.prijs"
    # Zonneplan onbereikbaar: sensor zonder forecast
    c.hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: SimpleNamespace(attributes={})))
    uit_cache = c._get_forecast_entries()
    assert uit_cache and all(e[1] > dt_util.as_local(nu) for e in uit_cache)
    assert len(uit_cache) == 136 - 43                     # alleen wat nog komt
    assert c._prijs_uit_cache is True
    # ook als de sensor helemaal weg is
    c.hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: None))
    assert len(c._get_forecast_entries()) == 93


def test_verlopen_cache_telt_niet(monkeypatch):
    nu = datetime(2026, 10, 21, 12, 50, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "now", lambda *a: nu, raising=False)
    c = _c({})
    c.prijs_forecast_cache = {"sensor": "sensor.prijs", "om": "x",
                              "forecast": _reeks(nu - timedelta(days=2), 8)}
    assert c._get_forecast_entries() == []


def test_bewaard_over_een_herstart():
    assert PERSISTED_FIELDS["prijs_forecast_cache"] == {"type": "plain"}


def test_zonder_cache_de_prijsgeschiedenis(monkeypatch):
    nu = datetime(2026, 10, 21, 12, 50, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "now", lambda *a: nu, raising=False)
    c = _c({})
    c.prijsgeschiedenis = {f"2026-10-21T{h:02d}": 0.30 for h in range(24)}
    c.prijsgeschiedenis.update({f"2026-10-22T{h:02d}": 0.25 for h in range(22)})
    e = c._get_forecast_entries()
    assert len(e) == 12 + 22 and round(e[-1][2] / 10_000_000, 2) == 0.25
