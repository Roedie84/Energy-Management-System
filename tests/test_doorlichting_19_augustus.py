"""Wat de volledige doorlichting van 19 augustus opleverde (v3.29.0).

Gevraagd: "controleer de volledige integratie op zaken welke niet
kloppen, beter kunnen, etc etc" en daarna "alle zaken welke je kunt
oplossen graag nu oplossen".

Elke toets hieronder hoort bij één bevinding uit die doorlichting, met
de cijfers uit de export van 11:22 erbij.
"""
from datetime import date, datetime, timedelta

import pytest

from custom_components.energy_management_system.const import (
    BATTERY_CALENDAR_MIN_DAYS,
    DEFAULT_BATTERY_CALENDAR_YEARS,
    ENERGY_DAY_EXPORT_WITHOUT_PV_MAX_KWH,
    PERSISTED_PLAIN_FIELDS,
)
from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)


# --- 1. Slijtage: de cycli raken niet op, de kalender wel -------------


class _Slijtage:

    def instelling(self, sleutel, standaard):
        """v3.56.0: de standaard geldt ook bij een opgeslagen None."""
        waarde = (self.config or {}).get(sleutel)
        return standaard if waarde is None else waarde
    """Zijn installatie: 3 modules, 8,64 kWh, 86,3 kWh in 18 dagen."""

    config = {
        "battery_module_temperature_sensor_entities": ["a", "b", "c"],
        "battery_module_price_eur": 729.0,
        "battery_cycle_life": 6000,
        "battery_total_capacity_sensor_entity": "sensor.capaciteit",
    }
    battery_cumulative_discharged_kwh = 86.32
    first_seen_date = date(2026, 8, 1)
    learned_battery_efficiency_percent = 84.5
    charge_efficiency_history = [1]
    discharge_efficiency_history = [1]

    def _read_sensor_float(self, entity_id):
        return 8.64

    def effective_min_soc_percent(self):
        return 10.0

    _gemeten_jaardoorzet_kwh = C._gemeten_jaardoorzet_kwh
    get_wear_cost_overview = C.get_wear_cost_overview


def test_the_calendar_binds_before_the_cycles(monkeypatch):
    """86,3 kWh in 18 dagen is ruwweg 1.750 kWh per jaar. Bij 51.840 kWh

    cyclusdoorzet duurt dat dertig jaar - zo lang gaat geen accu mee.
    """
    from custom_components.energy_management_system import coordinator as mod

    class _Klok:
        @staticmethod
        def now():
            return datetime(2026, 8, 19, 12, 0)

    monkeypatch.setattr(mod, "dt_util", _Klok)

    overzicht = _Slijtage().get_wear_cost_overview()

    assert overzicht["bindende_grens"] == "kalender"
    assert overzicht["cyclus_doorzet_kwh"] == 51840
    # De oude uitkomst blijft zichtbaar om naast te leggen.
    assert overzicht["slijtage_ct_per_kwh_cycli"] == pytest.approx(4.22, abs=0.05)
    # En de nieuwe ligt ruim twee keer hoger.
    assert overzicht["slijtage_ct_per_kwh"] > 2 * 4.22


def test_a_short_history_does_not_get_to_double_the_wear(monkeypatch):
    """Een schatting uit vijf dagen die de slijtage kan verdubbelen,

    hoort niet mee te tellen.
    """
    from custom_components.energy_management_system import coordinator as mod

    class _Klok:
        @staticmethod
        def now():
            return datetime(2026, 8, 5, 12, 0)

    monkeypatch.setattr(mod, "dt_util", _Klok)
    obj = _Slijtage()
    obj.first_seen_date = date(2026, 8, 1)

    assert obj._gemeten_jaardoorzet_kwh() is None
    assert obj.get_wear_cost_overview()["bindende_grens"] == "cycli"


def test_the_threshold_days_are_a_real_number():
    assert BATTERY_CALENDAR_MIN_DAYS >= 7
    assert 5 <= DEFAULT_BATTERY_CALENDAR_YEARS <= 25


# --- 2. Kosten en saldo zijn twee grootheden -------------------------


class _Reeks:
    energy_daily_history: list = []
    schedule_persisted_state_save = staticmethod(lambda: None)
    _migreer_dagreeks_kosten = C._migreer_dagreeks_kosten


def test_an_old_live_row_gets_its_balance_moved():
    """Tot v3.29.0 schreef het afsluiten van een dag het SALDO onder

    `kosten_eur`, terwijl ingelezen dagen daar de meterstand dragen. Bij
    elkaar opgeteld stond de jaarkolom op € 241,60.
    """
    obj = _Reeks()
    obj.energy_daily_history = [
        # ingelezen dag: meterstand, geen tegenfeit
        {"datum": "2026-08-14", "kosten_eur": 0.068, "zonder_sturing_eur": None},
        # live dag van vóór v3.29.0: saldo onder kosten_eur
        {"datum": "2026-08-18", "kosten_eur": -0.0399, "zonder_sturing_eur": -0.0343},
    ]

    obj._migreer_dagreeks_kosten()

    ingelezen, live = obj.energy_daily_history
    assert ingelezen["kosten_eur"] == 0.068
    assert "netto_eur" not in ingelezen
    assert live["netto_eur"] == -0.0399
    assert live["kosten_eur"] is None


def test_the_migration_runs_only_once():
    """Een tweede ronde mag het bedrag niet nog eens verplaatsen."""
    obj = _Reeks()
    obj.energy_daily_history = [
        {"datum": "2026-08-18", "kosten_eur": -0.04, "zonder_sturing_eur": -0.03},
    ]

    obj._migreer_dagreeks_kosten()
    obj._migreer_dagreeks_kosten()

    assert obj.energy_daily_history[0]["netto_eur"] == -0.04


# --- 3. Een dag die verdwijnt, laat een spoor achter -----------------


class _Opruiming:
    dagreeks_verwijderd: list = []
    energy_daily_history: list = []
    schedule_persisted_state_save = staticmethod(lambda: None)
    _energiedag_is_onzin = staticmethod(C._energiedag_is_onzin)
    _waarom_dag_onzin = staticmethod(C._waarom_dag_onzin)
    _weer_onmogelijke_dagen = C._weer_onmogelijke_dagen


def test_a_removed_day_is_written_down():
    """16 augustus ontbrak in de reeks, tussen 15 en 17 in. Niet door een

    storing maar door deze opruiming - alleen stond dat nergens.
    """
    obj = _Opruiming()
    obj.dagreeks_verwijderd = []
    obj.energy_daily_history = [
        {"datum": "2026-08-15", "opwek_kwh": 9.3, "export_kwh": 2.3},
        {"datum": "2026-08-16", "opwek_kwh": 0.0, "export_kwh": 11.8},
        {"datum": "2026-08-17", "opwek_kwh": 9.4, "export_kwh": 3.3},
    ]

    obj._weer_onmogelijke_dagen()

    assert [r["datum"] for r in obj.energy_daily_history] == [
        "2026-08-15",
        "2026-08-17",
    ]
    assert obj.dagreeks_verwijderd[0]["datum"] == "2026-08-16"
    assert "teruglevering" in obj.dagreeks_verwijderd[0]["reden"]


def test_the_export_without_pv_guard_is_finally_used():
    """De constante stond sinds v2.2.2 in const.py en werd nergens

    gelezen.
    """
    onmogelijk = {
        "datum": "2026-08-16",
        "opwek_kwh": 0.0,
        "export_kwh": ENERGY_DAY_EXPORT_WITHOUT_PV_MAX_KWH + 1,
        "accu_ontladen_kwh": 12.0,
    }

    assert C._energiedag_is_onzin(onmogelijk) is True


def test_a_normal_day_survives():
    goed = {
        "datum": "2026-08-14",
        "opwek_kwh": 20.98,
        "export_kwh": 12.04,
        "verbruik_kwh": 9.16,
        "accu_ontladen_kwh": 7.54,
    }

    assert C._energiedag_is_onzin(goed) is False


# --- 4. Water als aanwezigheidsbewijs --------------------------------


class _Water:

    def instelling(self, sleutel, standaard):
        """v3.56.0: de standaard geldt ook bij een opgeslagen None."""
        waarde = (self.config or {}).get(sleutel)
        return standaard if waarde is None else waarde
    config = {"water_active_usage_sensor_entity": "sensor.kraan"}
    _stromend_water = C._stromend_water
    stroom = 0.0

    def _read_sensor_float(self, entity_id):
        return self.stroom


def test_running_water_counts_as_someone_being_there():
    """De toelichting bij de constante beschreef dit gedrag al sinds de

    bouw van de waterregistratie, maar hij werd nergens gelezen. Precies
    het geval waarvoor het bedoeld was: een leeg huis waar om de dag
    iemand de dieren komt verzorgen.
    """
    obj = _Water()
    obj.stroom = 2.0

    assert obj._stromend_water() is True


def test_a_dripping_tap_is_not_a_person():
    obj = _Water()
    obj.stroom = 0.1

    assert obj._stromend_water() is False


def test_without_a_water_sensor_nothing_changes():
    obj = _Water()
    obj.config = {}

    assert obj._stromend_water() is False


# --- 5. De meetfrequentie overleeft een herstart ---------------------


def test_the_cadence_counter_is_kept():
    """Vier sensoren stonden na zes herstarts nog steeds op 23/30, omdat

    de teller bij elke start opnieuw begon. Wie vaak bijwerkt, krijgt dat
    oordeel dan nooit te zien.
    """
    assert "sensor_cadence" in PERSISTED_PLAIN_FIELDS
