"""v5.194.0: kalibratie aan = het EMS regelt alles.

Gevraagd 08-11: "als ik kalibratie aanzet moet het EMS alles fixen". Tot nu
stuurde het EMS in de kalibratiestand niets (de gebruiker laadde met de hand).
Nu: laden op het handmatige laadvermogen tot vol, een uur bovenin houden voor
het balanceren, dan de stand uit en de gewone sturing terug.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import KALIBRATIE_HOUD_MIN, KALIBRATIE_MAX_UREN

T0 = datetime(2026, 11, 8, 10, 45, tzinfo=timezone.utc)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _c(make_coordinator, hass, soc):
    c = make_coordinator({"battery_soc_sensor_entity": "sensor.soc"})
    hass.states.set("sensor.soc", str(soc))
    geschreven = []

    async def _manual(power):
        geschreven.append(power)
        return True
    c._async_apply_manual = _manual
    meldingen = []
    c._dispatch_notification = lambda **k: meldingen.append(k)
    c.handmatig_laadvermogen_w = lambda: 2400.0
    _run(c.async_set_kalibratie(True, T0))
    return c, geschreven, meldingen


def test_laadt_zelf_op_vol_vermogen(make_coordinator, hass):
    c, geschreven, _ = _c(make_coordinator, hass, 10)
    assert _run(c._kalibratie_ronde(T0 + timedelta(minutes=1))) is True
    assert geschreven == [-2400.0] and c.kalibratie_fase == "laden"


def test_vol_dan_een_uur_vasthouden_en_zelf_uit(make_coordinator, hass):
    c, geschreven, meldingen = _c(make_coordinator, hass, 100)
    assert _run(c._kalibratie_ronde(T0)) is True
    assert c.kalibratie_fase == "vasthouden" and c.kalibratie
    assert _run(c._kalibratie_ronde(T0 + timedelta(minutes=KALIBRATIE_HOUD_MIN - 1))) is True
    assert _run(c._kalibratie_ronde(T0 + timedelta(minutes=KALIBRATIE_HOUD_MIN))) is False
    assert c.kalibratie is False and c.kalibratie_fase == "klaar"
    assert meldingen and "afgerond" in meldingen[-1]["title"]


def test_niet_vol_na_max_uren_stopt(make_coordinator, hass):
    c, _, meldingen = _c(make_coordinator, hass, 60)
    assert _run(c._kalibratie_ronde(T0 + timedelta(hours=KALIBRATIE_MAX_UREN))) is False
    assert c.kalibratie is False and "afgebroken" in meldingen[-1]["title"]


def test_uitleg_noemt_wat_het_ems_doet(make_coordinator, hass):
    c, _, _ = _c(make_coordinator, hass, 40)
    _run(c._kalibratie_ronde(T0))
    assert "laadt de accu" in c._build_explanation()
