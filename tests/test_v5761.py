"""v5.76.1 (akkoord Ruud): de bootstraps lezen een P1-bron die wél in de
recorder staat.

`sensor.hw_p1_vermogen` (REST, elke seconde) staat bewust buiten de recorder.
Het nachtverbruik en de sluipverbruikvloer leerden daardoor na een herstart
niets uit de historie. Nu: eerst de ingestelde sensor, dan een optionele
instelling, dan het totaal bij de ingestelde fasesensoren
(`sensor.p1_meter_active_power`), en de gekozen bron staat erbij.
"""
import asyncio
import datetime
import sys
from datetime import date, datetime as dt, time, timedelta, timezone
from types import SimpleNamespace

import pytest

from custom_components.energy_management_system import coordinator as mod

TZ = timezone(timedelta(hours=2))
CONFIG = {
    "consumption_power_sensor_entity": "sensor.hw_p1_vermogen",
    "phase_power_sensor_entities": [
        "sensor.p1_meter_active_power_l1",
        "sensor.p1_meter_active_power_l2",
        "sensor.p1_meter_active_power_l3",
    ],
}


def test_de_bronnen_op_volgorde(make_coordinator, hass):
    hass.states.set("sensor.p1_meter_active_power", "2093")
    c = make_coordinator(dict(CONFIG))
    assert c._p1_historiebronnen() == ["sensor.hw_p1_vermogen", "sensor.p1_meter_active_power"]


def test_een_ingestelde_terugvalbron_gaat_voor_de_afgeleide(make_coordinator, hass):
    hass.states.set("sensor.p1_meter_active_power", "2093")
    c = make_coordinator({**CONFIG, "p1_history_sensor_entity": "sensor.p1_eigen"})
    assert c._p1_historiebronnen() == [
        "sensor.hw_p1_vermogen", "sensor.p1_eigen", "sensor.p1_meter_active_power",
    ]


def test_geen_afgeleide_bron_als_hij_niet_bestaat(make_coordinator, hass):
    c = make_coordinator(dict(CONFIG))
    assert c._p1_historiebronnen() == ["sensor.hw_p1_vermogen"]


def _statistieken(p1, dagen=10):
    rijen = {p1: []}
    t = dt(2026, 10, 10, 0, 0, tzinfo=TZ) - timedelta(days=dagen)
    while t < dt(2026, 10, 10, 0, 0, tzinfo=TZ):
        rijen[p1].append({"start": t, "mean": 140.0 if 2 <= t.hour < 5 else 400.0})
        t += timedelta(minutes=5)
    return rijen


def _recorder(monkeypatch, statistieken=None, staten=None):
    class _Instance:
        async def async_add_executor_job(self, func, *args):
            return func(*args)

    monkeypatch.setitem(sys.modules, "homeassistant.components.recorder", SimpleNamespace(
        get_instance=lambda hass: _Instance(),
        history=SimpleNamespace(get_significant_states=lambda hass, s, e, ids, **k: staten or {}),
    ))
    monkeypatch.setitem(sys.modules, "homeassistant.components.recorder.statistics", SimpleNamespace(
        get_metadata=lambda hass, statistic_ids=None: {},
        statistics_during_period=lambda *a, **k: statistieken or {}))
    monkeypatch.setattr(mod.dt_util, "now", lambda: dt(2026, 10, 10, 13, 0, tzinfo=TZ))
    monkeypatch.setattr(mod.dt_util, "start_of_local_day",
                        lambda d: dt.combine(d, time(), tzinfo=TZ), raising=False)


def test_de_vloer_valt_terug_op_de_vastgelegde_p1(make_coordinator, hass, monkeypatch):
    """Zoals live: geen statistieken van hw_p1_vermogen, wel van het totaal."""
    hass.states.set("sensor.p1_meter_active_power", "2093")
    c = make_coordinator(dict(CONFIG))
    _recorder(monkeypatch, statistieken=_statistieken("sensor.p1_meter_active_power"))

    assert asyncio.run(c.async_bootstrap_vloer_uit_recorder()) == 10

    assert c.sluipverbruik_reference_w == 140.0
    assert c.vloer_bootstrap["p1_bron"] == "sensor.p1_meter_active_power"
    bron = c.p1_historiebron["vloerverbruik"]
    assert bron["teruggevallen"] is True and bron["ingesteld"] == "sensor.hw_p1_vermogen"


def test_de_ingestelde_sensor_gaat_voor_als_hij_historie_heeft(make_coordinator, hass, monkeypatch):
    hass.states.set("sensor.p1_meter_active_power", "2093")
    c = make_coordinator(dict(CONFIG))
    rijen = {**_statistieken("sensor.p1_meter_active_power"), **_statistieken("sensor.hw_p1_vermogen")}
    _recorder(monkeypatch, statistieken=rijen)

    asyncio.run(c.async_bootstrap_vloer_uit_recorder())

    assert c.p1_historiebron["vloerverbruik"]["bron"] == "sensor.hw_p1_vermogen"
    assert c.p1_historiebron["vloerverbruik"]["teruggevallen"] is False


class _State:
    def __init__(self, waarde, moment):
        self.state = str(waarde)
        self.last_changed = moment
        self.last_updated = moment


def test_het_nachtverbruik_valt_terug_op_de_vastgelegde_p1(make_coordinator, hass, monkeypatch):
    hass.states.set("sensor.p1_meter_active_power", "2093")
    c = make_coordinator(dict(CONFIG))
    nu = dt(2026, 10, 10, 13, 0, tzinfo=TZ)
    staten = {
        "sensor.hw_p1_vermogen": [_State(200, nu - timedelta(hours=1))],  # alleen de beginstand
        "sensor.p1_meter_active_power": [
            _State(250, dt.combine((nu - timedelta(days=d)).date(), time(u, m), tzinfo=TZ))
            for d in range(1, 9) for u in range(0, 24) for m in (0, 20, 40)
        ],
    }
    _recorder(monkeypatch, staten=staten)

    asyncio.run(c.async_bootstrap_night_consumption_from_history())

    assert c.p1_historiebron["nachtverbruik"]["bron"] == "sensor.p1_meter_active_power"
    assert c.night_consumption_history
    assert c.night_consumption_history[-1] == pytest.approx(0.25, abs=0.01)
