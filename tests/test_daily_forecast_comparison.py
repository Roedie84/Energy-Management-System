"""De dagelijkse PV-vergelijking lukte nooit (v1.20.3).

Gevonden bij het doorlichten van zeven opeenvolgende exports:
`last_compared_date` stond in állemaal op None, en `deviation_history`
bleef op precies zeven waarden staan. Die zeven kwamen uit
`async_bootstrap_from_history` - niet uit één enkele live vergelijking.

De oorzaak zit in de volgorde:

- 20:00 legt "de voorspelling voor morgen" vast
- 23:59 vergelijkt, als `pending_predicted_date` gelijk is aan vandaag

Maar de vastlegging van 20:00 schreef direct in `pending`. Op 10 augustus
om 20:00 werd `pending` dus 11 augustus, en om 23:59 klopte de datum niet
meer met vandaag. De waarde die vergeleken moest worden was op dat moment
al overschreven.

Gevolg: de PV-voorspelling leerde niet bij van wat er werkelijk gebeurde.
De uurcorrecties liepen wél door - die hebben een eigen, per-uur pad.
"""
import asyncio
import datetime

import custom_components.energy_management_system.solar_forecast as sfm
from custom_components.energy_management_system.const import (
    CONF_SOLAR_ACTUAL_SENSOR,
    CONF_SOLAR_FORECAST_SENSOR,
)


def _tracker(hass):
    return sfm.SolarForecastAccuracyTracker(
        hass,
        {
            CONF_SOLAR_FORECAST_SENSOR: "sensor.solcast_morgen",
            CONF_SOLAR_ACTUAL_SENSOR: "sensor.solaredge_vandaag",
        },
    )


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _op(monkeypatch, jaar, maand, dag, uur, minuut):
    monkeypatch.setattr(
        sfm.dt_util,
        "now",
        lambda: datetime.datetime(jaar, maand, dag, uur, minuut),
    )


# --- de keten over twee dagen ----------------------------------------


def test_a_full_two_day_cycle_completes(hass, monkeypatch):
    """Het gerapporteerde geval van begin tot eind."""
    t = _tracker(hass)

    hass.states.set("sensor.solcast_morgen", "18.2")
    _op(monkeypatch, 2026, 8, 9, 20, 0)
    _run(t._async_handle_forecast_capture())
    _op(monkeypatch, 2026, 8, 9, 23, 59)
    _run(t._async_handle_compare())

    # Na de eerste avond staat de voorspelling voor 10 augustus klaar.
    assert t.pending_predicted_date == datetime.date(2026, 8, 10)

    hass.states.set("sensor.solcast_morgen", "20.0")
    _op(monkeypatch, 2026, 8, 10, 20, 0)
    _run(t._async_handle_forecast_capture())

    # De vastlegging van vanavond mag `pending` niet wissen.
    assert t.pending_predicted_date == datetime.date(2026, 8, 10)
    assert t.next_predicted_date == datetime.date(2026, 8, 11)

    hass.states.set("sensor.solaredge_vandaag", "16.1")
    _op(monkeypatch, 2026, 8, 10, 23, 59)
    _run(t._async_handle_compare())

    assert t.last_compared_date == datetime.date(2026, 8, 10)
    assert t.last_deviation_percent == -11.5


def test_the_deviation_history_grows(hass, monkeypatch):
    """De kern van de vondst: de reeks bleef op zeven staan."""
    t = _tracker(hass)
    hass.states.set("sensor.solcast_morgen", "18.2")
    _op(monkeypatch, 2026, 8, 9, 20, 0)
    _run(t._async_handle_forecast_capture())
    _op(monkeypatch, 2026, 8, 9, 23, 59)
    _run(t._async_handle_compare())
    hass.states.set("sensor.solaredge_vandaag", "16.1")
    _op(monkeypatch, 2026, 8, 10, 23, 59)

    _run(t._async_handle_compare())

    assert len(t.deviation_history) == 1


def test_the_capture_promotes_only_after_comparing(hass, monkeypatch):
    """Andersom - eerst doorschuiven, dan vergelijken - zou de fout
    terugbrengen."""
    t = _tracker(hass)
    hass.states.set("sensor.solcast_morgen", "18.2")
    _op(monkeypatch, 2026, 8, 9, 20, 0)
    _run(t._async_handle_forecast_capture())

    assert t.pending_predicted_kwh is None
    assert t.next_predicted_kwh == 18.2


def test_nothing_pending_is_harmless(hass, monkeypatch):
    """Een verse installatie heeft nog niets om te vergelijken."""
    t = _tracker(hass)
    _op(monkeypatch, 2026, 8, 10, 23, 59)

    _run(t._async_handle_compare())

    assert t.last_compared_date is None


# --- borging ---------------------------------------------------------


def test_the_new_fields_survive_a_restart():
    """Een herstart tussen 20:00 en 23:59 zou anders de voorspelling van
    morgen kwijtraken."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "sensor.py").read_text()

    assert "ATTR_NEXT_PREDICTED_KWH" in bron
    assert "ATTR_NEXT_PREDICTED_DATE" in bron
    assert "next_predicted_kwh = _to_float" in bron


def test_it_is_in_the_export():
    """Zonder deze velden is niet te zien of de keten loopt - precies
    het gat dat deze vondst zo lang verborgen hield."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "next_predicted_kwh" in bron
    assert "next_predicted_date" in bron
