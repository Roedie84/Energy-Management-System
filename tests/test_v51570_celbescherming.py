"""v5.157.0 - celbescherming stuurt (akkoord Ruud 02-11).

Gemeld 01-11: om 19:32 stond module 4 op 2,80 V en de melding zei "Nu
bijladen, ongeacht de prijs", maar de sturing deed niets; de accu bleef de
hele nacht op zijn ondergrens. Nu laadt het EMS een kleine buffer bij in het
goedkoopste kwartier binnen het venster, en houdt die vast.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CELBESCHERMING_BUFFER_KWH,
    CELBESCHERMING_VRIJ_KWH,
    OPTION_SMART_CHARGING,
    PRICE_SCALE_FACTOR,
    REASON_REGISTRY,
    REDENEN_BEWUSTE_NETAFNAME,
)

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 1, 19, 32, tzinfo=TZ)


def _c(make_coordinator, cel_v=2.80, inhoud=0.0, prijzen=None):
    c = make_coordinator({})
    c.battery_module_live = [
        {"module": 1, "cel_min_v": 3.2, "cel_max_v": 3.22},
        {"module": 4, "cel_min_v": cel_v, "cel_max_v": cel_v + 0.02},
    ]
    c._inhoud = inhoud
    c.beschikbare_energie_kwh = lambda: c._inhoud
    # Kwartieren vanaf 19:30; goedkoopste om 23:45 (40,5 ct).
    prijzen = prijzen or {datetime(2026, 11, 1, 23, 45, tzinfo=TZ): 0.405}
    entries, t = [], datetime(2026, 11, 1, 19, 30, tzinfo=TZ)
    while t < NU + timedelta(hours=12):
        entries.append((t, t + timedelta(minutes=15), prijzen.get(t, 0.45) * PRICE_SCALE_FACTOR))
        t += timedelta(minutes=15)
    c._get_forecast_entries = lambda *a, **k: entries
    return c


def test_boven_de_startgrens_niets(make_coordinator, hass):
    c = _c(make_coordinator, cel_v=2.95)
    assert c.celbeschermingsbesluit(NU)["actie"] is None


def test_eerst_houden_dan_laden_in_het_goedkoopste_kwartier(make_coordinator, hass):
    c = _c(make_coordinator)
    b = c.celbeschermingsbesluit(NU)
    assert b["actie"] == "houden"
    assert b["laden_om"].startswith("2026-11-01T23:45")
    assert c.celbeschermingsbesluit(datetime(2026, 11, 1, 23, 45, tzinfo=TZ))["actie"] == "laden"


def test_tijdstip_ligt_vast(make_coordinator, hass):
    """Een later nog goedkoper kwartier schuift het laden niet op."""
    c = _c(make_coordinator, prijzen={
        datetime(2026, 11, 1, 23, 45, tzinfo=TZ): 0.405,
        datetime(2026, 11, 2, 4, 0, tzinfo=TZ): 0.30,
    })
    c.celbeschermingsbesluit(NU)
    assert c.celbeschermingsbesluit(datetime(2026, 11, 1, 23, 50, tzinfo=TZ))["actie"] == "laden"


def test_stopt_bij_de_buffer_en_houdt_hem_vast(make_coordinator, hass):
    c = _c(make_coordinator)
    c.celbeschermingsbesluit(NU)
    laat = datetime(2026, 11, 1, 23, 50, tzinfo=TZ)
    c._inhoud = CELBESCHERMING_BUFFER_KWH
    assert c.celbeschermingsbesluit(laat)["actie"] == "houden"
    # Boven de buffer: gewone sturing, die mag tot de buffer ontladen.
    c._inhoud = CELBESCHERMING_BUFFER_KWH + 0.4
    assert c.celbeschermingsbesluit(laat)["actie"] is None
    c._inhoud = CELBESCHERMING_BUFFER_KWH - 0.05
    assert c.celbeschermingsbesluit(laat)["actie"] == "houden"


def test_vervalt_als_de_accu_weer_gevuld_is(make_coordinator, hass):
    c = _c(make_coordinator)
    c.celbeschermingsbesluit(NU)
    c._inhoud = CELBESCHERMING_VRIJ_KWH
    assert c.celbeschermingsbesluit(NU + timedelta(hours=16))["actie"] is None
    assert c._celbescherming is None


def test_zonder_prijzen_meteen_laden(make_coordinator, hass):
    c = _c(make_coordinator)
    c._get_forecast_entries = lambda *a, **k: []
    assert c.celbeschermingsbesluit(NU)["actie"] == "laden"


def test_toepassen_laden_en_houden(make_coordinator, hass):
    c = _c(make_coordinator)
    toegepast = []

    async def manual(w):
        toegepast.append(("manual", w))

    async def stand(s):
        toegepast.append(("stand", s))

    c._async_apply_manual = manual
    c._async_apply_operation = stand
    c._update_financial_tracking = lambda *a, **k: None
    c._update_shortfall_detection = lambda *a, **k: None
    c._finish_decision_tick = lambda *a, **k: None
    assert asyncio.run(c._celbescherming_als_nodig(NU, [])) is True
    assert c.last_reason == "celbescherming_houden"
    assert toegepast[-1] == ("stand", OPTION_SMART_CHARGING)
    assert asyncio.run(c._celbescherming_als_nodig(datetime(2026, 11, 1, 23, 45, tzinfo=TZ), [])) is True
    assert c.last_reason == "celbescherming_laden"
    assert toegepast[-1][0] == "manual"
    regels = " · ".join(c._waarom_celbescherming("celbescherming_laden"))
    assert "2.80 V" in regels


def test_redenen_geregistreerd(make_coordinator, hass):
    for reden in ("celbescherming_laden", "celbescherming_houden"):
        assert reden in REASON_REGISTRY
        assert reden in REDENEN_BEWUSTE_NETAFNAME
