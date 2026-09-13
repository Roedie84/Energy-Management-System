"""De ongeteste helft van `solar_forecast.py` (v3.36.0).

Gevraagd naar aanleiding van de dekkingsmeting: 55% van dit bestand werd
door geen enkele test uitgevoerd, en het stuurt wél mee - de geleerde
bias gaat rechtstreeks de reserveberekening in.

Het grootste blanco stuk is `async_bootstrap_from_history`: 128 regels
die bij elke installatie en elke herstart draaien en die de leergegevens
vullen uit de recorder. Precies het soort code dat zelden faalt en dan
in stilte iets verkeerds neerzet.

Niet omdat er iets vermoed werd, maar omdat niemand er ooit naar keek.
"""
import asyncio
import datetime
from types import SimpleNamespace

import pytest

import custom_components.energy_management_system.solar_forecast as sfm
from custom_components.energy_management_system.const import (
    CONF_SOLAR_ACTUAL_SENSOR,
    CONF_SOLAR_FORECAST_SENSOR,
)
from custom_components.energy_management_system.solar_forecast import (
    MAX_REASONABLE_DAILY_FORECAST_KWH,
)

NU = datetime.datetime(2026, 8, 20, 12, 0)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _tracker(hass, **config):
    basis = {
        CONF_SOLAR_FORECAST_SENSOR: "sensor.solcast_morgen",
        CONF_SOLAR_ACTUAL_SENSOR: "sensor.solaredge_vandaag",
    }
    basis.update(config)
    return sfm.SolarForecastAccuracyTracker(hass, basis)


class _State:
    """Zo min mogelijk van een Home Assistant-toestand."""

    def __init__(self, waarde, moment):
        self.state = str(waarde)
        self.last_changed = moment


def _dag(offset: int, uur: int, minuut: int = 0) -> datetime.datetime:
    return datetime.datetime(2026, 8, 20 - offset, uur, minuut)


def _neppe_recorder(monkeypatch, per_entiteit, faalt=False):
    """Zet een recorder neer die `per_entiteit` teruggeeft."""

    class _Instance:
        async def async_add_executor_job(self, func, *args):
            if faalt:
                raise RuntimeError("recorder ligt eruit")
            return func(*args)

    nep = SimpleNamespace(
        get_instance=lambda hass: _Instance(),
        history=SimpleNamespace(
            get_significant_states=lambda hass, start, eind, ids: per_entiteit
        ),
    )
    import sys

    monkeypatch.setitem(
        sys.modules, "homeassistant.components.recorder", nep
    )
    monkeypatch.setattr(sfm.dt_util, "now", lambda: NU)
    monkeypatch.setattr(sfm.dt_util, "as_local", lambda d: d)


# --- 1. de gelukkige weg ---------------------------------------------


def _zeven_dagen():
    """Zeven dagen waarin de voorspelling steeds 10% te hoog stond."""
    voorspeld, werkelijk = [], []
    for offset in range(1, 8):
        # De voorspelling wordt de avond ervóór om 20:00 vastgelegd.
        voorspeld.append(_State(20.0, _dag(offset + 1, 20, 5)))
        # De werkelijke opbrengst staat om 23:59 op de meter.
        werkelijk.append(_State(18.0, _dag(offset, 23, 30)))
    return {
        "sensor.solcast_morgen": voorspeld,
        "sensor.solaredge_vandaag": werkelijk,
    }


def test_history_is_read_into_the_learning_data(hass, monkeypatch):
    """Zonder deze routine begint elke installatie op nul en duurt het

    twee weken voor er iets geleerd is.
    """
    _neppe_recorder(monkeypatch, _zeven_dagen())
    t = _tracker(hass)
    hass.states.set("sensor.solaredge_vandaag", "18.0")

    _run(t.async_bootstrap_from_history())

    assert t.was_bootstrapped_from_history is True
    assert t.forecast_value_history
    assert t.deviation_history
    # 18 tegen 20 voorspeld is 10% te hoog voorspeld.
    assert all(abs(v + 10.0) < 0.5 for v in t.deviation_history)


def test_live_data_is_never_overwritten(hass, monkeypatch):
    """Wat er live geleerd is, is meer waard dan wat er uit de recorder

    komt.
    """
    _neppe_recorder(monkeypatch, _zeven_dagen())
    t = _tracker(hass)
    t.forecast_value_history = [15.0, 16.0]
    t.deviation_history = [-2.0, -3.0]

    _run(t.async_bootstrap_from_history())

    assert t.forecast_value_history == [15.0, 16.0]
    assert t.deviation_history == [-2.0, -3.0]
    assert t.was_bootstrapped_from_history is False


def test_garbage_history_is_replaced(hass, monkeypatch):
    """Blijft er onzin van een verkeerd ingestelde sensor staan, dan zit

    de integratie daar voorgoed aan vast - vandaar deze uitzondering op
    de vorige regel.
    """
    _neppe_recorder(monkeypatch, _zeven_dagen())
    t = _tracker(hass)
    t.forecast_value_history = [MAX_REASONABLE_DAILY_FORECAST_KWH + 500]
    t.deviation_history = [9999.0]

    _run(t.async_bootstrap_from_history())

    assert t.forecast_value_history != [MAX_REASONABLE_DAILY_FORECAST_KWH + 500]
    assert t.was_bootstrapped_from_history is True


# --- 2. de eenheid van de opbrengstsensor ----------------------------


@pytest.mark.parametrize(
    "eenheid,factor", [("Wh", 0.001), ("MWh", 1000.0), ("kWh", 1.0), ("", 1.0)]
)
def test_the_yield_unit_is_converted(hass, monkeypatch, eenheid, factor):
    """Een opbrengstsensor in Wh levert anders afwijkingen van -99,9%."""
    gegevens = {
        "sensor.solcast_morgen": [
            _State(20.0, _dag(offset + 1, 20, 5)) for offset in range(1, 8)
        ],
        "sensor.solaredge_vandaag": [
            _State(18.0 / factor, _dag(offset, 23, 30)) for offset in range(1, 8)
        ],
    }
    _neppe_recorder(monkeypatch, gegevens)
    t = _tracker(hass)
    hass.states.set(
        "sensor.solaredge_vandaag",
        "18.0",
        {"unit_of_measurement": eenheid},
    )

    _run(t.async_bootstrap_from_history())

    assert t.deviation_history
    assert all(abs(v + 10.0) < 1.0 for v in t.deviation_history), (
        f"{eenheid} werd niet omgerekend: {t.deviation_history}"
    )


# --- 3. wat er mis kan gaan ------------------------------------------


def test_a_broken_recorder_never_breaks_the_start(hass, monkeypatch):
    """Deze routine draait tijdens het opstarten. Een fout hier mag de

    integratie niet meenemen.
    """
    _neppe_recorder(monkeypatch, _zeven_dagen(), faalt=True)
    t = _tracker(hass)

    _run(t.async_bootstrap_from_history())

    assert t.was_bootstrapped_from_history is False


def test_no_recorder_at_all_is_fine(hass, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "homeassistant.components.recorder", None)
    monkeypatch.setattr(sfm.dt_util, "now", lambda: NU)
    t = _tracker(hass)

    _run(t.async_bootstrap_from_history())

    assert t.deviation_history == []


def test_empty_history_leaves_everything_alone(hass, monkeypatch):
    _neppe_recorder(
        monkeypatch,
        {"sensor.solcast_morgen": [], "sensor.solaredge_vandaag": []},
    )
    t = _tracker(hass)

    _run(t.async_bootstrap_from_history())

    assert t.was_bootstrapped_from_history is False


def test_unreadable_states_are_skipped(hass, monkeypatch):
    """`unavailable` en `unknown` staan vol in elke recorder."""
    gegevens = {
        "sensor.solcast_morgen": [
            _State("unavailable", _dag(3, 20, 5)),
            _State(20.0, _dag(2, 20, 5)),
        ],
        "sensor.solaredge_vandaag": [
            _State("unknown", _dag(2, 23, 30)),
            _State(18.0, _dag(1, 23, 30)),
        ],
    }
    _neppe_recorder(monkeypatch, gegevens)
    t = _tracker(hass)

    _run(t.async_bootstrap_from_history())

    assert all(isinstance(v, float) for v in t.forecast_value_history)
    assert all(isinstance(v, float) for v in t.deviation_history)


def test_an_implausible_forecast_day_is_skipped(hass, monkeypatch):
    """Een piekvermogenssensor in plaats van een dagtotaal levert getallen

    die er niet horen te staan.
    """
    gegevens = {
        "sensor.solcast_morgen": [
            _State(MAX_REASONABLE_DAILY_FORECAST_KWH + 1000, _dag(2, 20, 5)),
        ],
        "sensor.solaredge_vandaag": [_State(18.0, _dag(1, 23, 30))],
    }
    _neppe_recorder(monkeypatch, gegevens)
    t = _tracker(hass)

    _run(t.async_bootstrap_from_history())

    assert t.forecast_value_history == []


# --- 4. afsluiten ----------------------------------------------------


def test_unloading_lets_go_of_both_clocks(hass):
    """Twee tijdklokken die na een herlaad blijven lopen, vergelijken

    daarna tegen een coordinator die niet meer bestaat.
    """
    t = _tracker(hass)
    opgezegd = []
    t._unsub_compare = lambda: opgezegd.append("vergelijk")
    t._unsub_capture = lambda: opgezegd.append("vastleggen")

    _run(t.async_unload())

    assert sorted(opgezegd) == ["vastleggen", "vergelijk"]


def test_unloading_without_clocks_is_harmless(hass):
    t = _tracker(hass)

    _run(t.async_unload())


def test_a_disabled_tracker_sets_up_nothing(hass, monkeypatch):
    """Zonder sensoren hoeft er niets te draaien."""
    t = sfm.SolarForecastAccuracyTracker(hass, {})

    _run(t.async_setup())

    assert t._unsub_compare is None
    assert t._unsub_capture is None


# --- 5. het uitlezen zelf --------------------------------------------


@pytest.mark.parametrize(
    "waarde,eenheid,verwacht",
    [
        ("18.0", "kWh", 18.0),
        ("18000", "Wh", 18.0),
        ("0.018", "MWh", 18.0),
        ("18.0", None, 18.0),
        ("unavailable", "kWh", None),
        ("unknown", "kWh", None),
        ("geen getal", "kWh", None),
    ],
)
def test_reading_a_yield_sensor(hass, waarde, eenheid, verwacht):
    """Een opbrengstsensor in Wh die als kWh gelezen wordt, zit er een

    factor duizend naast - en dan lijkt elke dag een ramp.
    """
    kenmerken = {"unit_of_measurement": eenheid} if eenheid else {}
    hass.states.set("sensor.opbrengst", waarde, kenmerken)

    assert sfm._read_float(hass, "sensor.opbrengst") == verwacht


def test_reading_a_sensor_that_does_not_exist(hass):
    assert sfm._read_float(hass, "sensor.bestaat_niet") is None
    assert sfm._read_float(hass, None) is None


# --- 6. de luisteraars -----------------------------------------------


def test_listeners_are_called_and_can_leave(hass):
    """De sensorentiteiten hangen hieraan; blijft een afgemelde

    luisteraar staan, dan schrijft die naar een entiteit die weg is.
    """
    t = _tracker(hass)
    geroepen = []

    def _een():
        geroepen.append("een")

    def _twee():
        geroepen.append("twee")

    t.register_listener(_een)
    t.register_listener(_twee)
    t._notify_listeners()

    assert sorted(geroepen) == ["een", "twee"]

    t.unregister_listener(_een)
    geroepen.clear()
    t._notify_listeners()

    assert geroepen == ["twee"]


def test_unregistering_something_unknown_is_harmless(hass):
    t = _tracker(hass)

    t.unregister_listener(lambda: None)


# --- 7. de dagelijkse vastlegging ------------------------------------


def test_an_implausible_forecast_is_not_stored(hass, monkeypatch):
    """Gemeld in v1.20.x: een piekvermogenssensor in plaats van het

    dagtotaal. Zonder deze grens leert de integratie van 4.500 kWh zon.
    """
    monkeypatch.setattr(sfm.dt_util, "now", lambda: NU)
    t = _tracker(hass)
    hass.states.set(
        "sensor.solcast_morgen",
        str(MAX_REASONABLE_DAILY_FORECAST_KWH + 1),
        {"unit_of_measurement": "kWh"},
    )

    _run(t._async_handle_forecast_capture())

    assert t.forecast_value_history == []
    assert t.next_predicted_kwh is None


def test_a_normal_forecast_is_stored_for_tomorrow(hass, monkeypatch):
    monkeypatch.setattr(sfm.dt_util, "now", lambda: NU)
    t = _tracker(hass)
    hass.states.set(
        "sensor.solcast_morgen", "18.2", {"unit_of_measurement": "kWh"}
    )

    _run(t._async_handle_forecast_capture())

    assert t.forecast_value_history == [18.2]
    assert t.next_predicted_kwh == 18.2
    assert t.next_predicted_date == NU.date() + datetime.timedelta(days=1)


def test_an_unreadable_forecast_stores_nothing(hass, monkeypatch):
    monkeypatch.setattr(sfm.dt_util, "now", lambda: NU)
    t = _tracker(hass)
    hass.states.set("sensor.solcast_morgen", "unavailable")

    _run(t._async_handle_forecast_capture())

    assert t.forecast_value_history == []


# --- 8. de avondvergelijking -----------------------------------------


def test_a_rollover_deviation_is_thrown_away(hass, monkeypatch):
    """Wordt er vergeleken op het moment dat de dagteller net op nul is

    gesprongen, dan komt er een afwijking van bijna -100% uit. Die zou
    de geleerde correctie voor twee weken bederven.
    """
    monkeypatch.setattr(sfm.dt_util, "now", lambda: NU)
    t = _tracker(hass)
    t.pending_predicted_kwh = 20.0
    t.pending_predicted_date = NU.date()
    hass.states.set(
        "sensor.solaredge_vandaag", "0.0", {"unit_of_measurement": "kWh"}
    )

    _run(t._async_handle_compare())

    assert t.deviation_history == []


def test_a_normal_day_is_learned(hass, monkeypatch):
    monkeypatch.setattr(sfm.dt_util, "now", lambda: NU)
    t = _tracker(hass)
    t.pending_predicted_kwh = 20.0
    t.pending_predicted_date = NU.date()
    hass.states.set(
        "sensor.solaredge_vandaag", "18.0", {"unit_of_measurement": "kWh"}
    )

    _run(t._async_handle_compare())

    assert t.deviation_history == [-10.0]
    assert t.last_compared_date == NU.date()


def test_an_unreadable_yield_learns_nothing(hass, monkeypatch):
    monkeypatch.setattr(sfm.dt_util, "now", lambda: NU)
    t = _tracker(hass)
    t.pending_predicted_kwh = 20.0
    t.pending_predicted_date = NU.date()
    hass.states.set("sensor.solaredge_vandaag", "unavailable")

    _run(t._async_handle_compare())

    assert t.deviation_history == []


# --- 9. de dynamische drempel ----------------------------------------


def test_the_typical_forecast_needs_enough_days(hass):
    """Onder het minimum geeft hij niets terug in plaats van een

    gemiddelde over twee dagen.
    """
    t = _tracker(hass)
    t.forecast_value_history = [20.0, 21.0]

    assert t.learned_typical_forecast_kwh is None


def test_the_typical_forecast_ignores_nonsense(hass):
    t = _tracker(hass)
    t.forecast_value_history = [20.0] * 10 + [
        MAX_REASONABLE_DAILY_FORECAST_KWH + 900
    ]

    assert t.learned_typical_forecast_kwh == 20.0


def test_a_genuinely_dark_day_is_still_learned(hass, monkeypatch):
    """De rollover-grens mag geen echte winterdag wegfilteren: was er

    maar 0,3 kWh voorspeld, dan is nul een echte uitkomst.
    """
    monkeypatch.setattr(sfm.dt_util, "now", lambda: NU)
    t = _tracker(hass)
    t.pending_predicted_kwh = 0.3
    t.pending_predicted_date = NU.date()
    hass.states.set(
        "sensor.solaredge_vandaag", "0.0", {"unit_of_measurement": "kWh"}
    )

    _run(t._async_handle_compare())

    assert t.deviation_history == [-100.0]


def test_the_lower_bound_could_never_fire_before(hass):
    """De aanleiding, als getal: een afwijking kan aan de onderkant nooit

    verder gaan dan -100%, dus een grens van 200% vuurt daar nooit -
    terwijl de melding erbij wél over een sensor-rollover sprak.
    """
    assert sfm.MAX_REASONABLE_DEVIATION_PERCENT > 100.0
    assert sfm.ROLLOVER_MIN_FORECAST_KWH > sfm.ROLLOVER_MAX_ACTUAL_KWH
