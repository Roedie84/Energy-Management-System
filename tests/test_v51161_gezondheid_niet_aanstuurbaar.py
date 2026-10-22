"""v5.116.1: sensor-gezondheid telt niet mee terwijl de accu niet aanstuurbaar is.

Meldronde 22-10: tijdens de Zendure-time-outs (10:49-12:35, EMS 4x "niet
aanstuurbaar") zakte de sensor-gezondheid van 95 naar 75 % en bleef dat
uren - een tweede LET OP voor dezelfde storing.
"""
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc)
STAP = 35


def _config():
    return {
        "available_energy_sensor_entity": "sensor.available_energy",
        "battery_power_sensor_entity": "sensor.battery_power",
    }


def _tick(c, hass, now, beschikbaar, vermogen):
    hass.states.set("sensor.available_energy",
                    "unavailable" if beschikbaar is None else f"{beschikbaar:.4f}")
    hass.states.set("sensor.battery_power",
                    "unavailable" if vermogen is None else str(vermogen))
    c._update_energy_balance_validation(now)


def test_uitval_tijdens_niet_aanstuurbaar_telt_niet(make_coordinator, hass):
    c = make_coordinator(_config())
    c.aansturing_onbereikbaar = {"reden": "time-out", "sinds": DAY0.isoformat()}
    now = DAY0
    for _ in range(6):
        now += timedelta(minutes=5)
        _tick(c, hass, now, None, None)
    assert c.energy_balance_error_history == []
    assert c.balance_missing_by_entity == {}


def test_uitval_zonder_melding_telt_wel(make_coordinator, hass):
    c = make_coordinator(_config())
    c._started_at = DAY0 - timedelta(hours=5)
    _tick(c, hass, DAY0, None, None)
    assert c.energy_balance_error_history == [None]
    assert c.balance_missing_by_entity


def test_geen_vergelijking_over_de_storing_heen(make_coordinator, hass):
    """Anker vóór de storing, accu bewoog tijdens de storing: na herstel
    mag het eerste interval niet de storing overspannen."""
    c = make_coordinator(_config())
    now = DAY0
    _tick(c, hass, now, 6.0, 1000)
    # storing: niet aanstuurbaar, waarden staan stil/oud
    c.aansturing_onbereikbaar = {"reden": "time-out", "sinds": now.isoformat()}
    for _ in range(4):
        now += timedelta(minutes=10)
        _tick(c, hass, now, 6.0, 1000)
    assert c._last_balance_check_time is None
    # herstel: nieuw anker, daarna een kloppende beweging
    c.aansturing_onbereikbaar = {"reden": None, "sinds": None}
    now += timedelta(minutes=5)
    _tick(c, hass, now, 5.0, 1000)
    assert c._last_balance_check_time == now
    now += timedelta(minutes=STAP)
    _tick(c, hass, now, 5.0 - 1000 * STAP / 60 / 1000, 1000)
    assert len(c.energy_balance_error_history) == 1
    assert c.energy_balance_error_history[0] < 50
