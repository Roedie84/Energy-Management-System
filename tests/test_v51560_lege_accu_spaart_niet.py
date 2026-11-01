"""v5.156.0 - een lege accu spaart niets in het kwartierplan (gemeld Ruud 01-11).

01-11 21:02 kwam "De planning voorziet al een half uur geen kwartieren meer
waarin 't huus aan het net hunk", terwijl de accu op 10 % (0,00 kWh
bruikbaar) stond en het huis de hele avond van het net draaide. Het plan
had alle kwartieren tot het blok op "sparen" gezet, en een spaarkwartier
telde nooit als tekort.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import PRICE_SCALE_FACTOR

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 1, 21, 0, tzinfo=TZ)


def _entries():
    t, uit = NU, []
    while t < NU + timedelta(hours=6):
        uit.append((t, t + timedelta(minutes=15), 0.45 * PRICE_SCALE_FACTOR))
        t += timedelta(minutes=15)
    return uit


def _plan(make_coordinator, inhoud, zon=0.0):
    c = make_coordinator({})
    c.smart_charging_supported = lambda: True
    entries = _entries()
    gespaard = {s for s, _e, _p in entries}
    c._get_forecast_entries = lambda *a, **k: entries
    c._read_sensor_float = lambda *a, **k: 10.0
    c.beschikbare_energie_kwh = lambda: inhoud
    c.effective_min_soc_percent = lambda: 0
    c._estimate_pv_kwh_for_period = lambda *a, **k: zon
    c._verbruik_met_terugval = lambda *a, **k: 0.15
    c._plan_netregels = lambda *a, **k: {"gespaard": gespaard, "blok": (None, None)}
    c._plan_verkoopruimte = lambda *a, **k: None
    c._plan_laadt = lambda *a, **k: 0.0
    c._plan_dip_laadt = lambda *a, **k: 0.0
    return c._bouw_kwartierplan(NU)


def test_lege_accu_telt_als_tekort(make_coordinator, hass):
    plan = _plan(make_coordinator, 0.0)
    assert plan
    for r in plan:
        assert "sparen" not in r["modus"], (r["start"], r["modus"])
        assert r["tekort"] is True, r["start"]


def test_met_lading_blijft_het_sparen(make_coordinator, hass):
    """Wat er wel in zit wordt gewoon bewaard, zoals voorheen."""
    plan = _plan(make_coordinator, 2.0)
    assert all("sparen" in r["modus"] for r in plan)
    assert not any(r["tekort"] for r in plan)


def test_lege_accu_met_zonoverschot_geen_tekort(make_coordinator, hass):
    """Dekt de zon het huis, dan is er ook zonder accu geen tekort."""
    plan = _plan(make_coordinator, 0.0, zon=0.3)
    assert not any(r["tekort"] for r in plan)


def test_lege_accu_die_vult_gaat_weer_sparen(make_coordinator, hass):
    """Vult de zon de lege accu, dan spaart het plan de kwartieren daarna."""
    plan = _plan(make_coordinator, 0.0, zon=0.3)
    assert "sparen" not in plan[0]["modus"]
    assert any("sparen" in r["modus"] for r in plan[1:])
