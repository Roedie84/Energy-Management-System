"""v5.149.0: een herstart wist de lopende NILM-dag niet meer.

Gevonden bij "CV-ketel mogelijk defect (+61 %)": EMS rekende 29-10 een
daggemiddelde van 13,56 W, de recorder 9,89 W. De laatste herstart was
om 15:54 en de Store werd alleen om middernacht weggeschreven, dus de
dag begon na de herstart opnieuw bij nul en bestond alleen nog uit de
avond (met het stoken) zonder de zuinige nacht.
"""
import asyncio
import json
from datetime import date, datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    NILM_MIN_SAMPLES_FOR_DAY,
)

CV = "sensor.cv_ketel_vermogen"
DAG = datetime(2026, 10, 29, 0, 0, tzinfo=timezone.utc)


def _apparaat():
    return {
        "friendly_name": "CV-ketel Vermogen",
        "confirmed_at": "2026-08-05",
        "daily_avg_history": [8.4] * 20,
        "cusum_accumulator": 0.0,
        "anomaly_detected": False,
        "estimated_drift_percent": None,
        "reference_avg_w": 8.4,
        "_today_sum": 0.0,
        "_today_count": 0,
        "_check_date": None,
    }


def _json_rondje(hass):
    """Zoals de echte Store: via JSON, een datum wordt tekst."""
    sleutel = "energy_management_system_nilm_confirmed_devices"
    ruw = hass._fake_store_backing[sleutel]
    hass._fake_store_backing[sleutel] = json.loads(json.dumps(ruw, default=str))


def _meet(coordinator, hass, watt, van, minuten):
    hass.states.set(CV, str(watt))
    for n in range(minuten):
        coordinator._update_nilm_confirmed_devices(van + timedelta(minutes=n))


def test_datum_uit_de_store_wordt_weer_een_datum(make_coordinator):
    c = make_coordinator({})
    assert c._nilm_datum("2026-10-29") == date(2026, 10, 29)
    assert c._nilm_datum(date(2026, 10, 29)) == date(2026, 10, 29)
    assert c._nilm_datum(datetime(2026, 10, 29, 5, tzinfo=timezone.utc)) == date(
        2026, 10, 29
    )
    assert c._nilm_datum(None) is None
    assert c._nilm_datum("onzin") is None


def test_herstart_midden_op_de_dag_houdt_de_ochtend(make_coordinator, hass):
    oud = make_coordinator({})
    oud.nilm_confirmed_devices[CV] = _apparaat()
    oud._nilm_store_loaded = True
    # Nacht en ochtend: 6 W, 15 uur lang.
    _meet(oud, hass, 6.0, DAG, 15 * 60)
    asyncio.run(oud._bewaar_nilm_lopende_dag())
    _json_rondje(hass)

    nieuw = make_coordinator({})
    nieuw._nilm_confirmed_devices_store = oud._nilm_confirmed_devices_store
    asyncio.run(nieuw._async_load_nilm_confirmed_devices_store())
    apparaat = nieuw.nilm_confirmed_devices[CV]
    assert apparaat["_check_date"] == DAG.date()
    assert apparaat["_today_count"] == 15 * 60

    # Avond na de herstart: 20 W, 9 uur lang, dan middernacht.
    _meet(nieuw, hass, 20.0, DAG + timedelta(hours=15), 9 * 60)
    nieuw._update_nilm_confirmed_devices(DAG + timedelta(days=1))

    dagcijfer = apparaat["daily_avg_history"][-1]
    # (15*6 + 9*20) / 24 = 11,25 W - niet 20 W zoals alleen de avond.
    assert abs(dagcijfer - 11.25) < 0.01


def test_herstart_over_middernacht_rondt_gisteren_af(make_coordinator, hass):
    oud = make_coordinator({})
    oud.nilm_confirmed_devices[CV] = _apparaat()
    oud._nilm_store_loaded = True
    _meet(oud, hass, 9.0, DAG, max(NILM_MIN_SAMPLES_FOR_DAY, 23 * 60))
    asyncio.run(oud._bewaar_nilm_lopende_dag())
    _json_rondje(hass)

    nieuw = make_coordinator({})
    nieuw._nilm_confirmed_devices_store = oud._nilm_confirmed_devices_store
    asyncio.run(nieuw._async_load_nilm_confirmed_devices_store())
    nieuw._update_nilm_confirmed_devices(DAG + timedelta(days=1, minutes=5))

    apparaat = nieuw.nilm_confirmed_devices[CV]
    assert apparaat["daily_avg_history"][-1] == 9.0
    assert apparaat["_check_date"] == (DAG + timedelta(days=1)).date()
    assert apparaat["_today_count"] == 1


def test_niet_wegschrijven_voordat_de_store_gelezen_is(make_coordinator, hass):
    c = make_coordinator({})
    c._nilm_store_loaded = False
    asyncio.run(c._bewaar_nilm_lopende_dag())
    assert "energy_management_system_nilm_confirmed_devices" not in getattr(
        hass, "_fake_store_backing", {}
    )


def test_elk_uur_wegschrijven(make_coordinator, hass):
    c = make_coordinator({})
    c.nilm_confirmed_devices[CV] = _apparaat()
    hass.states.set(CV, "8")
    voor = len(hass.created_tasks)
    for n in range(120):
        c._update_nilm_confirmed_devices(DAG + timedelta(minutes=n))
    opslagen = [
        t for t in hass.created_tasks[voor:]
        if "save_nilm" in getattr(t, "__qualname__", "")
    ]
    # Uur 00 en uur 01: twee keer, niet 120 keer.
    assert len(opslagen) == 2
    for t in opslagen:
        t.close()


def test_afsluiten_schrijft_de_lopende_dag_weg(make_coordinator, hass):
    c = make_coordinator({})
    c.nilm_confirmed_devices[CV] = _apparaat()
    c._nilm_store_loaded = True
    _meet(c, hass, 7.0, DAG, 30)
    asyncio.run(c._bij_afsluiten(None))
    opgeslagen = hass._fake_store_backing[
        "energy_management_system_nilm_confirmed_devices"
    ]
    assert opgeslagen["nilm_confirmed_devices"][CV]["_today_count"] == 30
