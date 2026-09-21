"""Vier bevindingen, gevonden door live in Home Assistant mee te kijken
(v5.11).

Voor het eerst niet via een export maar via de connector. Wat dat
opleverde:

1. `Accu-gezondheid (geschat)` stond op 34,3 - zonder eenheid. Dat leest
   als "34% gezond", en zo las ik het zelf ook. Het is een aantal
   volledige CYCLI. En het klopte niet eens: de Zendure meldt
   `Totaal geleverd: 1768,70 kWh`, dus ongeveer 205 cycli. Het EMS telde
   er 34, omdat het pas begon te tellen bij de installatie.

2. Vier EMS-sensoren op `unknown`. Alle vier terecht leeg in die
   situatie, maar `unknown` ziet er in Home Assistant uit als kapot. Voor
   de twee tekstsensoren staat er nu waarom.

3. `Model- en parameternauwkeurigheid: Venster van 0,3 uur is te kort`.
   Het nachtelijke ontlaadvenster werd niet bewaard. Een herstart
   halverwege gooide het deel vóór de herstart weg, en het restant was
   te kort om iets te leren. Met de reeks versies van deze week was dat
   vaak.

4. Twee reeksen konden NOOIT betrouwbaar worden. Het nachtverbruik en de
   ontlaadreserve worden op 7 afgekapt (`LEARNING_HISTORY_DAYS`), maar de
   betrouwbaarheidskaart eiste er 14. Ze bleven voor altijd op "7, 
   betrouwbaar vanaf 14" staan - dezelfde klasse als de ijklijn van v4.13.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 21, 15, 35, tzinfo=timezone.utc)


# --- 1. de cycli --------------------------------------------------------


def test_de_cycli_komen_uit_de_levenslange_teller_van_de_accu(make_coordinator, hass):
    """1768,7 kWh geleverd bij 8,64 kWh is ongeveer 205 cycli - niet de
    34 die het EMS sinds zijn installatie telde."""
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["battery_total_capacity_sensor_entity"] = "sensor.cap"
    c.config["battery_discharge_energy_sensor_entity"] = "sensor.geleverd"
    hass.states.set("sensor.cap", "8.64", {"unit_of_measurement": "kWh"})
    hass.states.set("sensor.geleverd", "1768.70", {"unit_of_measurement": "kWh"})
    c.battery_cumulative_discharged_kwh = 296.0

    assert c.battery_estimated_full_cycles == pytest.approx(204.7, abs=0.1)
    assert c.battery_cycli_bron() == "levenslange teller van de accu"


def test_zonder_die_teller_de_eigen_telling(make_coordinator, hass):
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["battery_total_capacity_sensor_entity"] = "sensor.cap"
    hass.states.set("sensor.cap", "8.64", {"unit_of_measurement": "kWh"})
    c.battery_cumulative_discharged_kwh = 296.0

    assert c.battery_estimated_full_cycles == pytest.approx(34.3, abs=0.1)
    assert "sinds de installatie" in c.battery_cycli_bron()


def test_de_sensor_heeft_een_eenheid():
    """Zonder eenheid las 34,3 als een percentage gezondheid."""
    from custom_components.energy_management_system.sensor import BatteryHealthSensor

    assert BatteryHealthSensor._attr_native_unit_of_measurement == "cycli"
    # de naam blijft bewust staan - de entity_id wordt ervan afgeleid en het
    # dashboard verwijst ernaar; hernoemen brak dat in de eerste poging
    assert BatteryHealthSensor._attr_name == "Accu-gezondheid (geschat)"


# --- 2. unknown ---------------------------------------------------------


def test_de_energiebrug_zegt_waarom_hij_leeg_is(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import EnergyBridgeCheckSensor as EnergyBridgeSensor

    c = make_coordinator({})
    c.last_has_enough_energy = None
    s = EnergyBridgeSensor(c, "x")

    assert s.native_value == "geen_blok_in_zicht"


def test_de_gesimuleerde_actie_zegt_waarom_hij_leeg_is(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import SimulatedActionSensor

    c = make_coordinator({})
    c.last_simulated_action = None
    c.learning_only = False
    s = SimulatedActionSensor(c, "x")

    assert s.native_value == "leermodus_uit"


# --- 3. het nachtvenster ------------------------------------------------


def test_het_ontlaadvenster_overleeft_een_herstart():
    from custom_components.energy_management_system.const import PERSISTED_FIELDS

    for veld in (
        "_tracking_window_end",
        "_window_energy_kwh",
        "_window_duration_hours",
        "_window_temp_samples",
    ):
        assert veld in PERSISTED_FIELDS, veld


def test_na_een_herstart_loopt_hetzelfde_venster_door(make_coordinator, hass):
    """Het gemeten geval: een herstart midden in het venster. Nu blijft het
    deel van vóór de herstart staan."""
    blok = NU + timedelta(hours=10)
    bron = make_coordinator({})
    bron._tracking_window_end = blok
    bron._window_energy_kwh = 1.8
    bron._window_duration_hours = 5.5
    bron._window_temp_samples = [14.0, 13.5]

    verse = make_coordinator({})
    verse._apply_persisted_state(bron._collect_persisted_state())
    verse.last_cheap_block_start = blok
    verse._read_corrected_consumption_power = lambda: 300.0
    verse._get_live_outdoor_temp_c = lambda now: 13.0

    verse._update_night_consumption_tracking(NU, in_window=True)

    # hetzelfde venster: niet afgesloten, de opgebouwde uren blijven staan
    assert verse._window_duration_hours == pytest.approx(5.5)
    assert verse._window_energy_kwh == pytest.approx(1.8)


def test_het_gat_tijdens_de_herstart_telt_niet_mee(make_coordinator, hass):
    """Wat er verbruikt is terwijl Home Assistant uit stond, weet niemand -
    dat hoort er niet bij verzonnen te worden."""
    from custom_components.energy_management_system.const import PERSISTED_FIELDS

    assert "_window_last_sample" not in PERSISTED_FIELDS


# --- 4. reeksen die nooit betrouwbaar konden worden ---------------------


def test_het_nachtverbruik_kan_betrouwbaar_worden(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        LEARNING_HISTORY_DAYS,
        RELIABILITY_RELIABLE,
    )

    c = make_coordinator({})
    c.night_consumption_history = [0.27] * LEARNING_HISTORY_DAYS

    regel = next(
        r for r in c.get_reliability_overview() if r["naam"] == "Nachtverbruik"
    )

    assert regel["niveau"] == RELIABILITY_RELIABLE


def test_de_ontlaadreserve_kan_betrouwbaar_worden(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        LEARNING_HISTORY_DAYS,
        RELIABILITY_RELIABLE,
    )

    c = make_coordinator({})
    c.reserve_daily_records = [
        {"date": f"2026-09-{d:02d}", "shortfall": False, "excess": False}
        for d in range(10, 10 + LEARNING_HISTORY_DAYS)
    ]

    regel = next(
        r for r in c.get_reliability_overview()
        if r["naam"].startswith("Ontlaadreserve")
    )

    assert regel["niveau"] == RELIABILITY_RELIABLE


def test_geen_drempel_boven_de_opslaggrens():
    """De ratel: een betrouwbaarheidsdrempel die hoger ligt dan wat er
    bewaard wordt, is een meting die nooit klaar kan zijn. Dat gebeurde
    twee keer (nachtverbruik, ontlaadreserve) en eerder bij de ijklijn."""
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    for veld in ("night_consumption_history", "reserve_shortfall_history"):
        m = re.search(
            r"len\(self\." + veld + r"[^)]*\)[^,]*,\s*\w+,\s*(\w+)", bron
        )
        assert m, veld
        assert m.group(1) in ("LEARNING_HISTORY_DAYS",) or int(m.group(1)) <= 7, (
            veld,
            m.group(1),
        )
