"""v5.187.2: de kostprijs van de accu-inhoud op de grondslag van het waardeplan.

Gemeld 05-11 09:06: cockpit "in accu 0 ct betaald · EMS 59 ct" voor opgeslagen
zon. Het kostprijsmodel telde zon tegen de prijs incl. belasting (47,6 ct)
terwijl het plan tijdens de saldering met jaaroverschot rekent met de prijs
zonder belastingdeel. Ruud 09:20: gelijktrekken, en vanaf 01-01-2027 vanzelf
zonder saldering. De kasprijs ("betaald") blijft wat er werkelijk betaald is.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_PV_POWER_SENSOR,
)

DAY0 = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)
from custom_components.energy_management_system.const import PRICE_SCALE_FACTOR  # noqa: E402

PRIJZEN = [(DAY0 - timedelta(hours=1), DAY0 + timedelta(hours=12), 0.476 * PRICE_SCALE_FACTOR)]


def _c(make_coordinator, hass, korting, terug, bron="zon"):
    c = make_coordinator({
        CONF_AVAILABLE_ENERGY_SENSOR: "sensor.beschikbaar",
        CONF_CONSUMPTION_POWER_SENSOR: "sensor.p1",
        CONF_PV_POWER_SENSOR: "sensor.pv",
    })
    c._salderingskorting_eur = lambda now: korting
    c._get_feedin_value_per_kwh = lambda entries, now: terug
    c._accu_ac_kwh = lambda richting, kwh: kwh
    if bron == "zon":
        c._split_charge_pv_vs_grid = lambda ac, uren: (ac, 0.0)
    else:
        c._split_charge_pv_vs_grid = lambda ac, uren: (0.0, ac)
    hass.states.set("sensor.pv", "2000")
    hass.states.set("sensor.p1", "0")
    hass.states.set("sensor.beschikbaar", "1.0")
    c._update_battery_cost_basis_and_savings(DAY0, PRIJZEN)
    hass.states.set("sensor.beschikbaar", "1.5")
    c._update_battery_cost_basis_and_savings(DAY0 + timedelta(minutes=15), PRIJZEN)
    return c


def test_zon_tijdens_saldering_met_overschot_zonder_belastingdeel(make_coordinator, hass):
    # terugleverwaarde onder saldering = 0,476 + 0,02; korting 0,1108
    c = _c(make_coordinator, hass, 0.1108, 0.496)
    assert abs(c.battery_cost_basis_eur_per_kwh - (0.496 - 0.1108)) < 1e-6
    assert c.battery_cash_basis_eur_per_kwh == 0.0  # zon is gratis


def test_na_saldering_terugleverwaarde_zonder_korting(make_coordinator, hass):
    # vanaf 2027: korting 0 (saldering voorbij), zon = kale terugleverwaarde
    c = _c(make_coordinator, hass, 0.0, 0.09)
    assert abs(c.battery_cost_basis_eur_per_kwh - 0.09) < 1e-6


def test_netlading_kostprijs_marginaal_kasprijs_werkelijk(make_coordinator, hass):
    c = _c(make_coordinator, hass, 0.1108, 0.496, bron="net")
    assert abs(c.battery_cost_basis_eur_per_kwh - (0.476 - 0.1108)) < 1e-6
    assert abs(c.battery_cash_basis_eur_per_kwh - 0.476) < 1e-6
