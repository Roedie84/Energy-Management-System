"""v5.195.1: de kalibratie zet zichzelf uit zonder de ronde te laten vastlopen.

08-11 16:02 zette `_kalibratie_ronde` de stand uit via `async_set_kalibratie`,
die `async_update` aanroept en op `self._lock` wacht - het slot dat de lopende
ronde zelf vasthoudt. Het EMS stond daardoor van 16:02 tot de herstart van
09-11 05:23 stil ("Mogelijk vastgelopen"). De ronde moet nu binnen het slot
gewoon afdraaien.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import KALIBRATIE_HOUD_MIN, KALIBRATIE_MAX_UREN

T0 = datetime(2026, 11, 8, 15, 1, tzinfo=timezone.utc)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _c(make_coordinator, hass, soc):
    c = make_coordinator({"battery_soc_sensor_entity": "sensor.soc"})
    hass.states.set("sensor.soc", str(soc))

    async def _manual(power):
        return True
    c._async_apply_manual = _manual
    meldingen = []
    c._dispatch_notification = lambda **k: meldingen.append(k)
    c.handmatig_laadvermogen_w = lambda: 2400.0
    _run(c.async_set_kalibratie(True, T0 - timedelta(hours=4)))
    return c, meldingen


async def _binnen_het_slot(c, now):
    async with c._lock:
        return await asyncio.wait_for(c._kalibratie_ronde(now), timeout=2)


def test_vasthouden_klaar_binnen_het_slot(make_coordinator, hass):
    c, meldingen = _c(make_coordinator, hass, 100)
    c.kalibratie_vol_sinds = T0.isoformat()
    klaar = _run(_binnen_het_slot(c, T0 + timedelta(minutes=KALIBRATIE_HOUD_MIN)))
    assert klaar is False
    assert c.kalibratie is False and c.kalibratie_fase == "klaar"
    assert c.kalibratie_sinds is None and c.kalibratie_vol_sinds is None
    assert "afgerond" in meldingen[-1]["title"]


def test_afbreken_binnen_het_slot(make_coordinator, hass):
    c, meldingen = _c(make_coordinator, hass, 60)
    c.kalibratie_sinds = (T0 - timedelta(hours=KALIBRATIE_MAX_UREN)).isoformat()
    assert _run(_binnen_het_slot(c, T0)) is False
    assert c.kalibratie is False and c.kalibratie_fase == "afgebroken"
    assert "afgebroken" in meldingen[-1]["title"]


def test_opslag_direct_gepland(make_coordinator, hass):
    c, _ = _c(make_coordinator, hass, 100)
    c.kalibratie_vol_sinds = T0.isoformat()
    voor = len(hass.created_tasks)
    _run(_binnen_het_slot(c, T0 + timedelta(minutes=KALIBRATIE_HOUD_MIN)))
    assert len(hass.created_tasks) > voor


def test_ronde_roept_geen_async_update_aan(make_coordinator, hass):
    c, _ = _c(make_coordinator, hass, 100)
    c.kalibratie_vol_sinds = T0.isoformat()

    async def _verboden():
        raise AssertionError("async_update vanuit de ronde = deadlock op self._lock")
    c.async_update = _verboden
    assert _run(c._kalibratie_ronde(T0 + timedelta(minutes=KALIBRATIE_HOUD_MIN))) is False
