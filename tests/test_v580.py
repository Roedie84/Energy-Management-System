"""v5.80 (akkoord Ruud 10-10 20:15): de accubesparing ~2x te hoog.

Gemeten 01-10..09-10: het kostprijsmodel steeg € 5,23, de eigen afrekening
(5-min P1/Zendure/PV x kwartierprijs, met de accu-inhoud) was ≈ € 2,57. Het
model boekte de VOORRAAD (gelijkstroomkant): laden kostte alleen de
opgeslagen kWh, ontladen leverde de hele daling op. Het rondreisverlies
(~84%) zat nergens in. Nu aan de wisselstroomkant.
"""
from datetime import datetime, timedelta, timezone

import pytest

TZ = timezone(timedelta(hours=2))
T0 = datetime(2026, 10, 5, 12, 0, tzinfo=TZ)


def _c(make_coordinator, hass, prijzen, accu_w, huis_w=2500.0, meting=True):
    c = make_coordinator({"available_energy_sensor_entity": "sensor.beschikbaar",
                          "salderen_end_date": "2026-12-31"})
    stand = {"accu": 0.0, "prijs": 0.13}
    c._read_corrected_battery_power = lambda: stand["accu"] if meting else None
    c._read_corrected_consumption_power = lambda: huis_w
    c._get_current_price_per_kwh = lambda entries, now: stand["prijs"]
    c._get_feedin_value_per_kwh = lambda entries, now: stand["prijs"] + 0.02
    c.total_battery_savings_eur = 0.0
    c.battery_cost_basis_eur_per_kwh = None
    c._last_available_kwh_for_cost_basis = None

    def ronde(t, beschikbaar):
        hass.states.set("sensor.beschikbaar", str(beschikbaar))
        c._update_battery_cost_basis_and_savings(t, [])

    return c, stand, ronde


def _cyclus(c, stand, ronde, laad_w=-2180.0, ontlaad_w=1840.0):
    """30 min laden tegen 13 ct (1,0 kWh opgeslagen), 30 min ontladen tegen
    35 ct (1,0 kWh uit de voorraad)."""
    ronde(T0, 2.0)
    stand["accu"] = laad_w
    for m in range(1, 31):
        ronde(T0 + timedelta(minutes=m), 2.0 if m < 30 else 3.0)
    stand["accu"], stand["prijs"] = ontlaad_w, 0.35
    for m in range(31, 61):
        ronde(T0 + timedelta(minutes=m), 3.0 if m < 60 else 2.0)


def test_het_rondreisverlies_telt_mee(make_coordinator, hass):
    c, stand, ronde = _c(make_coordinator, hass, None, None)
    _cyclus(c, stand, ronde)
    # in 1,09 kWh tegen 13 ct -> kostprijs 0,1417 per opgeslagen kWh
    assert c.battery_cost_basis_eur_per_kwh == pytest.approx(1.09 * 0.13, abs=0.002)
    # uit 0,92 kWh tegen 35 ct, min 1,0 kWh tegen de kostprijs
    assert c.total_battery_savings_eur == pytest.approx(0.92 * 0.35 - 1.09 * 0.13, abs=0.003)
    # het oude model: 0,35 - 0,13 = 0,22 - 22% te hoog in dit geval
    assert c.total_battery_savings_eur < 0.22 * 0.85


def test_zon_kost_onder_salderen_de_kwartierprijs(make_coordinator, hass):
    """PV-overschot in de accu: gemiste teruglevering, kwartierprijs + premie."""
    c, stand, ronde = _c(make_coordinator, hass, None, None, huis_w=200.0)
    c.config["pv_power_sensor_entity"] = "sensor.pv"
    hass.states.set("sensor.pv", "3000")
    stand["prijs"] = 0.25
    ronde(T0, 2.0)
    stand["accu"] = -2180.0
    for m in range(1, 31):
        ronde(T0 + timedelta(minutes=m), 2.0 if m < 30 else 3.0)
    assert c.battery_cost_basis_eur_per_kwh == pytest.approx(1.09 * 0.27, abs=0.003)


def test_zonder_meting_het_geleerde_halve_rendement(make_coordinator, hass):
    c, stand, ronde = _c(make_coordinator, hass, None, None, meting=False)
    c.charge_efficiency_history = [92.0] * 10
    c.discharge_efficiency_history = [91.0] * 10
    _cyclus(c, stand, ronde)
    assert c.battery_cost_basis_eur_per_kwh == pytest.approx(0.13 / 0.92, abs=0.002)
    assert c.total_battery_savings_eur == pytest.approx(0.91 * 0.35 - 0.13 / 0.92, abs=0.003)


def test_een_onmogelijke_meting_wordt_begrensd(make_coordinator, hass):
    """Vermogenssensor zegt 3x zoveel als de voorraad: niet geloofd."""
    c, stand, ronde = _c(make_coordinator, hass, None, None)
    _cyclus(c, stand, ronde, laad_w=-6000.0, ontlaad_w=100.0)
    # laden hooguit voorraad / 0,75, ontladen minstens voorraad x 0,75
    assert c.battery_cost_basis_eur_per_kwh <= 0.13 / 0.75 + 1e-6


def test_verlies_blijft_zichtbaar(make_coordinator, hass):
    """Ontladen in een goedkoper kwartier dan de kostprijs: de sensor daalt."""
    c, stand, ronde = _c(make_coordinator, hass, None, None)
    ronde(T0, 2.0)
    stand["accu"], stand["prijs"] = -2180.0, 0.30
    for m in range(1, 31):
        ronde(T0 + timedelta(minutes=m), 2.0 if m < 30 else 3.0)
    stand["accu"], stand["prijs"] = 1840.0, 0.30
    for m in range(31, 61):
        ronde(T0 + timedelta(minutes=m), 3.0 if m < 60 else 2.0)
    assert c.total_battery_savings_eur < 0


def test_de_sensor_legt_de_rekenwijze_uit(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import BatterySavingsSensor

    c = make_coordinator({})
    attrs = BatterySavingsSensor(c, "x").extra_state_attributes
    assert "rondreis" in attrs["rekenwijze"] or "verlies" in attrs["rekenwijze"]
    assert "zonder sturing" in attrs["verschil_met_besparing_zonder_sturing"]
