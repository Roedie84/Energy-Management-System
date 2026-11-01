"""v5.155.1: een afrondingsstap van de laadstand zonder accustroom boekt niets.

Gemeld 01-11: de beschikbare energie sprong de hele nacht elke ~8 min
1,382 <-> 1,267 kWh (SoC 22/21 %) bij 0 W accuvermogen. Elke heen-en-terug
boekte in het kostprijsmodel een rondreisverlies dat er niet was
(~EUR 0,08 per uur).
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_PV_POWER_SENSOR,
)

DAY0 = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)
PRIJZEN = [(DAY0 - timedelta(hours=1), DAY0 + timedelta(hours=12), 0.44)]


def _coordinator(make_coordinator, hass, met_vermogen=True):
    config = {
        CONF_AVAILABLE_ENERGY_SENSOR: "sensor.beschikbaar",
        CONF_CONSUMPTION_POWER_SENSOR: "sensor.p1",
        CONF_PV_POWER_SENSOR: "sensor.pv",
    }
    if met_vermogen:
        config[CONF_BATTERY_POWER_SENSOR] = "sensor.accu"
    c = make_coordinator(config)
    c.battery_cost_basis_eur_per_kwh = 0.4956
    hass.states.set("sensor.pv", "0")
    hass.states.set("sensor.p1", "300")
    hass.states.set("sensor.accu", "0")
    hass.states.set("sensor.beschikbaar", "1.3824")
    return c


def _wiebel(c, hass, rondes=12):
    now = DAY0
    c._update_battery_cost_basis_and_savings(now, PRIJZEN)
    for i in range(rondes):
        now += timedelta(minutes=2)
        hass.states.set("sensor.beschikbaar", "1.2672")
        c._update_battery_cost_basis_and_savings(now, PRIJZEN)
        now += timedelta(minutes=6)
        hass.states.set("sensor.beschikbaar", "1.3824")
        c._update_battery_cost_basis_and_savings(now, PRIJZEN)
    return now


def test_wiebelen_zonder_stroom_boekt_niets(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    besparing = c.total_battery_savings_eur
    _wiebel(c, hass)
    assert c.total_battery_savings_eur == besparing
    assert c.battery_cost_basis_eur_per_kwh == 0.4956
    assert c.charge_grid_kwh_total == 0


def test_zonder_vermogenssensor_zoals_voorheen(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, met_vermogen=False)
    besparing = c.total_battery_savings_eur
    _wiebel(c, hass, rondes=3)
    assert c.total_battery_savings_eur < besparing


def test_echte_ontlading_wordt_geboekt(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    now = DAY0
    c._update_battery_cost_basis_and_savings(now, PRIJZEN)
    hass.states.set("sensor.accu", "800")  # 800 W ontladen
    for _ in range(10):
        now += timedelta(minutes=1)
        c._update_battery_cost_basis_and_savings(now, PRIJZEN)
    # 800 W x 10 min = 0,133 kWh AC; voorraad daalt 1 stap.
    hass.states.set("sensor.beschikbaar", "1.2672")
    now += timedelta(minutes=1)
    besparing = c.total_battery_savings_eur
    c._update_battery_cost_basis_and_savings(now, PRIJZEN)
    assert c.total_battery_savings_eur != besparing
    assert c._last_available_kwh_for_cost_basis == 1.2672


def test_zelfontlading_wordt_later_alsnog_geboekt(make_coordinator, hass):
    """Het ijkpunt blijft staan: een blijvende daling zonder stroom telt mee
    bij de volgende echte beweging."""
    c = _coordinator(make_coordinator, hass)
    now = DAY0
    c._update_battery_cost_basis_and_savings(now, PRIJZEN)
    hass.states.set("sensor.beschikbaar", "1.2672")
    now += timedelta(minutes=5)
    c._update_battery_cost_basis_and_savings(now, PRIJZEN)
    assert c._last_available_kwh_for_cost_basis == 1.3824

    hass.states.set("sensor.accu", "600")
    for _ in range(12):
        now += timedelta(minutes=1)
        c._update_battery_cost_basis_and_savings(now, PRIJZEN)
    hass.states.set("sensor.beschikbaar", "1.1520")
    now += timedelta(minutes=1)
    c._update_battery_cost_basis_and_savings(now, PRIJZEN)
    assert c._last_available_kwh_for_cost_basis == 1.1520


def test_grote_sprong_zonder_stroom_wordt_geboekt(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    now = DAY0
    c._update_battery_cost_basis_and_savings(now, PRIJZEN)
    hass.states.set("sensor.beschikbaar", "0.9")
    now += timedelta(minutes=5)
    besparing = c.total_battery_savings_eur
    c._update_battery_cost_basis_and_savings(now, PRIJZEN)
    assert c.total_battery_savings_eur != besparing
    assert c._last_available_kwh_for_cost_basis == 0.9
