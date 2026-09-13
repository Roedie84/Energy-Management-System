"""De twee inleesroutines uit de recorder (v3.38.0).

Gevraagd: de resterende 12% dekking. Bij het uitsplitsen bleek dat twee
functies 160 van de 942 ongedekte regels in `coordinator.py` dragen:

    async_bootstrap_night_consumption_from_history   95 regels
    async_bootstrap_energy_history                   65 regels

Allebei draaien ze bij élke start en allebei vullen ze leergegevens die
daarna de reserveberekening in gaan. De derde van dat soort - de
zonvoorspelling - leverde bij het toetsen meteen een fout op die er
jaren in had gezeten. Deze twee waren daarom de moeite waard; de rest
van de ongedekte regels is een staart van 210 functies met twee à drie
regels foutafhandeling elk.
"""
import asyncio
import datetime
from types import SimpleNamespace

import pytest

from custom_components.energy_management_system import coordinator as mod
from custom_components.energy_management_system.const import (
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_GRID_EXPORT_ENERGY_SENSOR,
    CONF_GRID_IMPORT_ENERGY_SENSOR,
    CONF_PV_ENERGY_SENSOR,
)

NU = datetime.datetime(2026, 8, 20, 12, 0)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _State:
    def __init__(self, waarde, moment):
        self.state = str(waarde)
        self.last_changed = moment
        self.last_updated = moment


def _recorder(monkeypatch, per_entiteit, faalt=False, geen_module=False):
    import sys

    if geen_module:
        monkeypatch.setitem(
            sys.modules, "homeassistant.components.recorder", None
        )
    else:
        class _Instance:
            async def async_add_executor_job(self, func, *args):
                if faalt:
                    raise RuntimeError("recorder ligt eruit")
                return func(*args)

        monkeypatch.setitem(
            sys.modules,
            "homeassistant.components.recorder",
            SimpleNamespace(
                get_instance=lambda hass: _Instance(),
                history=SimpleNamespace(
                    get_significant_states=(
                        lambda hass, start, eind, ids, **kw: per_entiteit
                    )
                ),
            ),
        )
    monkeypatch.setattr(mod.dt_util, "now", lambda: NU)
    monkeypatch.setattr(mod.dt_util, "as_local", lambda d: d)
    if hasattr(mod.dt_util, "start_of_local_day"):
        monkeypatch.setattr(
            mod.dt_util, "start_of_local_day", lambda d=None: (
                datetime.datetime.combine(d, datetime.time()) if d else NU
            )
        )


# --- 1. het nachtverbruik --------------------------------------------


def _nachtmetingen(vermogen_w=250.0, dagen=10):
    """Elke nacht een P1-meting binnen het venster van 01:00-08:00."""
    metingen = []
    for d in range(1, dagen + 1):
        dag = (NU - datetime.timedelta(days=d)).date()
        for uur in (2, 4, 6):
            metingen.append(
                _State(
                    vermogen_w,
                    datetime.datetime.combine(dag, datetime.time(uur, 0)),
                )
            )
    return metingen


def test_the_night_baseline_is_read_from_history(
    make_coordinator, hass, monkeypatch
):
    """Zonder deze routine begint het nachtverbruik op nul en duurt het

    twee weken voor de reserveberekening iets weet.
    """
    c = make_coordinator({CONF_CONSUMPTION_POWER_SENSOR: "sensor.p1"})
    _recorder(monkeypatch, {"sensor.p1": _nachtmetingen()})

    _run(c.async_bootstrap_night_consumption_from_history())

    assert c.night_consumption_history
    assert all(0.2 < v < 0.3 for v in c.night_consumption_history)


def test_live_night_data_is_never_overwritten(
    make_coordinator, hass, monkeypatch
):
    c = make_coordinator({CONF_CONSUMPTION_POWER_SENSOR: "sensor.p1"})
    c.night_consumption_history = [0.19, 0.21]
    _recorder(monkeypatch, {"sensor.p1": _nachtmetingen()})

    _run(c.async_bootstrap_night_consumption_from_history())

    assert c.night_consumption_history == [0.19, 0.21]


def test_the_hourly_profile_is_filled_from_the_same_history(
    make_coordinator, hass, monkeypatch
):
    """Dezelfde metingen dragen ook het uurprofiel; twee keer inlezen zou

    zonde zijn.
    """
    c = make_coordinator({CONF_CONSUMPTION_POWER_SENSOR: "sensor.p1"})
    _recorder(monkeypatch, {"sensor.p1": _nachtmetingen()})

    _run(c.async_bootstrap_night_consumption_from_history())

    assert c.hourly_consumption_profile


def test_without_a_p1_sensor_nothing_happens(
    make_coordinator, hass, monkeypatch
):
    c = make_coordinator({})
    _recorder(monkeypatch, {})

    _run(c.async_bootstrap_night_consumption_from_history())

    assert c.night_consumption_history == []


def test_a_broken_recorder_never_breaks_the_start(
    make_coordinator, hass, monkeypatch
):
    """Deze routine draait tijdens het opstarten."""
    c = make_coordinator({CONF_CONSUMPTION_POWER_SENSOR: "sensor.p1"})
    _recorder(monkeypatch, {"sensor.p1": _nachtmetingen()}, faalt=True)

    _run(c.async_bootstrap_night_consumption_from_history())

    assert c.night_consumption_history == []


def test_no_recorder_component_at_all(make_coordinator, hass, monkeypatch):
    c = make_coordinator({CONF_CONSUMPTION_POWER_SENSOR: "sensor.p1"})
    _recorder(monkeypatch, {}, geen_module=True)

    _run(c.async_bootstrap_night_consumption_from_history())

    assert c.night_consumption_history == []


def test_empty_history_leaves_it_empty(make_coordinator, hass, monkeypatch):
    c = make_coordinator({CONF_CONSUMPTION_POWER_SENSOR: "sensor.p1"})
    _recorder(monkeypatch, {"sensor.p1": []})

    _run(c.async_bootstrap_night_consumption_from_history())

    assert c.night_consumption_history == []


def test_unreadable_samples_are_skipped(
    make_coordinator, hass, monkeypatch
):
    """`unavailable` staat vol in elke recorder; één zo'n regel mag de

    hele nacht niet bederven.
    """
    c = make_coordinator({CONF_CONSUMPTION_POWER_SENSOR: "sensor.p1"})
    metingen = _nachtmetingen()
    metingen.insert(
        0,
        _State(
            "unavailable",
            datetime.datetime.combine(
                (NU - datetime.timedelta(days=1)).date(), datetime.time(3, 0)
            ),
        ),
    )
    _recorder(monkeypatch, {"sensor.p1": metingen})

    _run(c.async_bootstrap_night_consumption_from_history())

    assert all(isinstance(v, float) for v in c.night_consumption_history)


# --- 2. de energiedagreeks -------------------------------------------


def _statistieken(per_dag, dagen=8, start=100.0):
    """Langetermijnstatistieken: een oplopende `sum` per dag.

    De dagreeks leest deze, niet de losse toestanden - een verschil dat
    deze toets aan het licht bracht.
    """
    rijen, stand = [], start
    for d in range(dagen, 0, -1):
        dag = datetime.datetime.combine(
            (NU - datetime.timedelta(days=d)).date(), datetime.time()
        )
        rijen.append({"start": dag.timestamp(), "sum": stand})
        stand += per_dag
    return rijen


def _energieconfig():
    return {
        CONF_PV_ENERGY_SENSOR: "sensor.opwek",
        CONF_GRID_IMPORT_ENERGY_SENSOR: "sensor.afname",
        CONF_GRID_EXPORT_ENERGY_SENSOR: "sensor.teruglevering",
    }


def _energiehistorie():
    return {
        "sensor.opwek": _statistieken(20.0),
        "sensor.afname": _statistieken(2.0),
        "sensor.teruglevering": _statistieken(10.0),
    }


def _statistiekrecorder(monkeypatch, rijen, faalt=False):
    import sys

    class _Instance:
        async def async_add_executor_job(self, func, *args):
            if faalt:
                raise RuntimeError("recorder ligt eruit")
            return func(*args)

    stats = SimpleNamespace(
        get_metadata=lambda hass, statistic_ids=None: {
            i: (1, {"unit_of_measurement": "kWh"}) for i in (statistic_ids or [])
        },
        statistics_during_period=lambda *a, **k: rijen,
    )
    monkeypatch.setitem(
        sys.modules,
        "homeassistant.components.recorder",
        SimpleNamespace(get_instance=lambda hass: _Instance()),
    )
    monkeypatch.setitem(
        sys.modules, "homeassistant.components.recorder.statistics", stats
    )
    monkeypatch.setattr(mod.dt_util, "now", lambda: NU)
    monkeypatch.setattr(
        mod.dt_util,
        "start_of_local_day",
        lambda d=None: datetime.datetime.combine(
            d if d else NU.date(), datetime.time()
        ),
        raising=False,
    )


def test_the_day_series_is_read_from_history(
    make_coordinator, hass, monkeypatch
):
    c = make_coordinator(_energieconfig())
    _statistiekrecorder(monkeypatch, _energiehistorie())

    _run(c.async_bootstrap_energy_history())

    assert c.energy_daily_history


def test_a_broken_recorder_leaves_the_series_alone(
    make_coordinator, hass, monkeypatch
):
    c = make_coordinator(_energieconfig())
    _statistiekrecorder(monkeypatch, _energiehistorie(), faalt=True)

    _run(c.async_bootstrap_energy_history())

    assert c.energy_daily_history == []


def test_without_any_energy_meters_nothing_is_read(
    make_coordinator, hass, monkeypatch
):
    c = make_coordinator({})
    _recorder(monkeypatch, {})

    _run(c.async_bootstrap_energy_history())

    assert c.energy_daily_history == []


def test_a_live_day_is_never_replaced_by_history(
    make_coordinator, hass, monkeypatch
):
    """Een dag die live is afgesloten draagt cijfers die de statistieken

    niet hebben - de tegenfeitelijke kosten bijvoorbeeld.
    """
    c = make_coordinator(_energieconfig())
    dag = (NU - datetime.timedelta(days=3)).date().isoformat()
    c.energy_daily_history = [
        {"datum": dag, "opwek_kwh": 99.0, "zonder_sturing_eur": -1.0}
    ]
    _statistiekrecorder(monkeypatch, _energiehistorie())

    _run(c.async_bootstrap_energy_history())

    bestaand = [r for r in c.energy_daily_history if r["datum"] == dag]
    assert bestaand[0]["opwek_kwh"] == 99.0


def test_the_series_stays_in_date_order(
    make_coordinator, hass, monkeypatch
):
    """Een bijgehaald gat hoort op zijn eigen plek; zonder sorteren staat

    16 augustus tussen de dagen van juli.
    """
    c = make_coordinator(_energieconfig())
    _statistiekrecorder(monkeypatch, _energiehistorie())

    _run(c.async_bootstrap_energy_history())

    data = [r["datum"] for r in c.energy_daily_history]
    assert data == sorted(data)


# --- 3. de capaciteitsmeting van de kalibratie -----------------------


def test_the_calibration_measurement_only_runs_when_calibrating(
    make_coordinator, hass
):
    c = make_coordinator({})
    c.kalibratie = False
    c.kalibratie_meting = {"begin_soc": 5.0, "kwh_in": 1.0}

    c._meet_kalibratiecapaciteit(NU, 50.0)

    assert c.kalibratie_meting is None


def test_the_measurement_needs_enough_of_the_scale(make_coordinator, hass):
    """Van 60 naar 100 procent is een halve meting; de afrondingsfout op

    de laadstand weegt dan te zwaar.
    """
    c = make_coordinator({})
    c.kalibratie = True
    c.kalibratie_meting = {
        "begin_soc": 60.0,
        "begin": NU.isoformat(),
        "kwh_in": 3.0,
        "laatste": NU.isoformat(),
    }

    c._meet_kalibratiecapaciteit(NU + datetime.timedelta(minutes=5), 99.0)

    assert "gemeten_capaciteit_kwh" not in c.kalibratie_meting


def test_a_gap_in_time_adds_nothing(make_coordinator, hass):
    """Na een herstart of een gat valt er niets af te leiden - anders

    telt één sprong van uren als een uur laden.
    """
    c = make_coordinator({})
    c.kalibratie = True
    c.kalibratie_meting = {
        "begin_soc": 5.0,
        "begin": NU.isoformat(),
        "kwh_in": 2.0,
        "laatste": (NU - datetime.timedelta(hours=6)).isoformat(),
    }

    c._meet_kalibratiecapaciteit(NU, 60.0)

    assert c.kalibratie_meting["kwh_in"] == 2.0
