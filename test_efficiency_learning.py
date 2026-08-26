"""Self-learned battery round-trip efficiency (v0.34.0) and its use in
discounting the expected-PV offset in the reserve calculation (v0.33.0).
"""
from datetime import datetime, timedelta, timezone

import pytest

DAY0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


def test_learns_efficiency_from_a_full_charge_discharge_cycle(make_coordinator, hass):
    """Een gesimuleerde slag met een bekend rendement hoort er precies
    uit te komen.

    v1.32.0: het verlies zit hier volledig aan de LAADkant (er gaat 1,0
    kWh in en er komt 0,8 kWh bij), en het ontladen is verliesvrij. De
    twee halve slagen horen dat apart terug te geven: 80% en 100%, samen
    80% heen en terug.

    Een slag meer dan voorheen, want een stuk wordt pas afgesloten als
    de accu omdraait - de laatste ontlading loopt bij het aflopen van de
    lus nog.
    """
    coordinator = make_coordinator(
        {
            "battery_power_sensor_entity": "sensor.batt",
            "available_energy_sensor_entity": "sensor.available",
        }
    )

    current = DAY0
    available = 5.0
    hass.states.set("sensor.available", str(available))
    hass.states.set("sensor.batt", "0")
    coordinator._update_battery_efficiency_learning(current)  # seed checkpoint

    step = timedelta(minutes=15)
    for _cycle in range(4):
        for _ in range(8):  # 2 hours charging at 1000W, 80% round-trip efficiency
            current += step
            hass.states.set("sensor.batt", "-1000")
            available += (1000 / 1000) * 0.25 * 0.80
            hass.states.set("sensor.available", str(round(available, 4)))
            coordinator._update_battery_efficiency_learning(current)
        for _ in range(8):  # 2 hours discharging everything back out at 800W
            current += step
            hass.states.set("sensor.batt", "800")
            available -= (800 / 1000) * 0.25
            hass.states.set("sensor.available", str(round(available, 4)))
            coordinator._update_battery_efficiency_learning(current)

    assert coordinator.learned_charge_efficiency_percent == 80.0
    assert coordinator.learned_discharge_efficiency_percent == 100.0
    assert coordinator.learned_battery_efficiency_percent == 80.0


def test_learned_efficiency_takes_priority_over_config_default(make_coordinator, hass):
    """Once enough samples exist, the learned value should be used
    instead of the manually configured guess."""
    coordinator = make_coordinator(
        {
            "solar_forecast_sensor_entity": "sensor.solcast",
            "battery_round_trip_efficiency_percent": 95.0,  # deliberately wrong
        }
    )
    coordinator.learned_efficiency_history = [80.0, 80.0, 80.0]

    detailed = [
        {
            "period_start": DAY0.replace(hour=h, minute=m),
            "pv_estimate": 2.0 if 9 <= h < 12 else 0.0,
        }
        for h in range(24)
        for m in (0, 30)
    ]
    hass.states.set("sensor.solcast", "10.0", {"detailedForecast": detailed})

    start = DAY0.replace(hour=9, minute=0)
    end = DAY0.replace(hour=12, minute=0)
    offset = coordinator._get_efficiency_discounted_pv_offset(start, end)

    # 6.0 kWh raw PV * learned 80% (not the configured 95%) = 4.8
    assert offset == pytest.approx(4.8)


def test_pv_hourly_bias_persists_partial_progress(make_coordinator, hass):
    """Regression test for the v0.31.1 bug: raw_pv_hourly_avg must return
    a value even for an hour with fewer samples than the confidence
    threshold, so partial progress survives a restart instead of being
    silently discarded (learned_pv_hourly_ratio correctly still hides it
    from live decisions until there's enough data)."""
    coordinator = make_coordinator({})
    coordinator.pv_hourly_bias_history[10] = [0.85]  # only 1 sample so far

    assert coordinator.learned_pv_hourly_ratio(10) is None  # not confident yet
    assert coordinator.raw_pv_hourly_avg(10) == 0.85  # but persisted for later


# --- v1.32.0: rendement per halve slag -------------------------------


def _accu(make_coordinator, hass):
    c = make_coordinator(
        {
            "battery_power_sensor_entity": "sensor.batt",
            "available_energy_sensor_entity": "sensor.available",
        }
    )
    hass.states.set("sensor.batt", "0")
    hass.states.set("sensor.available", "3.0")
    c._update_battery_efficiency_learning(DAY0)
    return c


def _loop(c, hass, start_tijd, voorraad, vermogen_w, stappen, rendement=1.0):
    """Laat de accu een tijd dezelfde kant op gaan."""
    tijd = start_tijd
    for _ in range(stappen):
        tijd += timedelta(minutes=5)
        hass.states.set("sensor.batt", str(vermogen_w))
        stap = abs(vermogen_w) / 1000 * (5 / 60)
        if vermogen_w < 0:
            voorraad += stap * rendement
        else:
            voorraad -= stap / rendement
        hass.states.set("sensor.available", str(round(voorraad, 4)))
        c._update_battery_efficiency_learning(tijd)
    return tijd, voorraad


def test_the_two_halves_are_measured_apart(make_coordinator, hass):
    """Gevonden in de export van 11 augustus: zeven metingen van 56,4 tot
    97,6%. De oude formule sloot het venster zodra er genoeg geladen was
    - dus midden in een lading of midden in een ontlading.

    Hier verliest het laden 10% en het ontladen 5%. Dat hoort apart
    zichtbaar te zijn, niet als één mengsel.
    """
    c = _accu(make_coordinator, hass)
    tijd, voorraad = DAY0, 3.0
    for _ in range(4):
        tijd, voorraad = _loop(c, hass, tijd, voorraad, -2000, 24, rendement=0.90)
        tijd, voorraad = _loop(c, hass, tijd, voorraad, 1600, 30, rendement=0.95)

    assert c.learned_charge_efficiency_percent == pytest.approx(90.0, abs=0.5)
    assert c.learned_discharge_efficiency_percent == pytest.approx(95.0, abs=0.5)
    assert c.learned_battery_efficiency_percent == pytest.approx(85.5, abs=1.0)


def test_a_short_burst_is_ignored(make_coordinator, hass):
    """De voorraadsensor meldt in stappen van 1% (0,086 kWh). Onder een
    paar kWh meet je afronding in plaats van rendement."""
    c = _accu(make_coordinator, hass)
    tijd, voorraad = DAY0, 3.0
    # Een half uur laden is 1,0 kWh - te weinig.
    tijd, voorraad = _loop(c, hass, tijd, voorraad, -2000, 6, rendement=0.90)
    _loop(c, hass, tijd, voorraad, 1600, 6, rendement=0.95)

    assert c.charge_efficiency_history == []


def test_a_gap_in_the_readings_voids_the_segment(make_coordinator, hass):
    """Zit er een gat, dan is er onderweg energie gelopen die niet is
    geteld."""
    c = _accu(make_coordinator, hass)
    tijd, voorraad = _loop(c, hass, DAY0, 3.0, -2000, 20, rendement=0.90)

    # Een uur stilte, daarna verder alsof er niets gebeurd is.
    tijd += timedelta(hours=1)
    hass.states.set("sensor.batt", "1600")
    c._update_battery_efficiency_learning(tijd)

    assert c.charge_efficiency_history == []


def test_an_impossible_reading_is_discarded(make_coordinator, hass):
    """Meer eruit dan erin kan niet; dat is een meetfout."""
    c = _accu(make_coordinator, hass)
    tijd, voorraad = DAY0, 3.0
    # De voorraad groeit harder dan er vermogen in gaat.
    _loop(c, hass, tijd, voorraad, -2000, 24, rendement=1.4)

    assert c.charge_efficiency_history == []


def test_the_overview_shows_both_sides(make_coordinator, hass):
    c = _accu(make_coordinator, hass)
    c.charge_efficiency_history = [92.0, 91.0, 93.0]
    c.discharge_efficiency_history = [96.0, 95.0, 97.0]

    overzicht = c.get_efficiency_overview()

    assert overzicht["laadrendement_procent"] == 92.0
    assert overzicht["ontlaadrendement_procent"] == 96.0
    assert overzicht["heen_en_terug_procent"] == 88.3
    assert overzicht["methode"] == "per halve slag"


def test_the_old_method_remains_as_fallback(make_coordinator, hass):
    """Een verse installatie mag niet zonder waarde komen te zitten."""
    c = _accu(make_coordinator, hass)
    c.learned_efficiency_history = [88.0, 90.0, 92.0]

    assert c.learned_battery_efficiency_percent == 90.0
    assert c.get_efficiency_overview()["methode"].startswith("oude methode")


def test_the_measurements_survive_a_restart():
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "charge_efficiency_history" in PERSISTED_PLAIN_FIELDS
    assert "discharge_efficiency_history" in PERSISTED_PLAIN_FIELDS
