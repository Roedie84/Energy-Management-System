"""De uitersten uit de doorlichting (v3.88.0).

Gevraagd: "Wat gebeurt er bij -€0,20/kWh? Bij €1,50? Bij 100% SOC? Bij
0%? Bij 0W PV? Bij 10 kW woningverbruik? Als alle sensoren unavailable
worden?"

Negen vragen, en op geen ervan lag een toets. Dat is de categorie die
niet opvalt tot hij zich voordoet - en dan meestal op een dag dat het
duur is.
"""
from datetime import datetime, timedelta

import pytest

from custom_components.energy_management_system.const import (
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_PV_POWER_SENSOR,
    CONF_SOC_SENSOR,
    PRICE_SCALE_FACTOR,
)

NU = datetime(2026, 8, 31, 12, 0)


def _coordinator(make_coordinator, hass):
    c = make_coordinator(
        {
            CONF_SOC_SENSOR: "sensor.soc",
            CONF_AVAILABLE_ENERGY_SENSOR: "sensor.beschikbaar",
            CONF_BATTERY_POWER_SENSOR: "sensor.accu",
            CONF_CONSUMPTION_POWER_SENSOR: "sensor.p1",
            CONF_PV_POWER_SENSOR: "sensor.pv",
        }
    )
    hass.states.set("sensor.soc", "50")
    hass.states.set("sensor.beschikbaar", "3.9")
    hass.states.set("sensor.accu", "0")
    hass.states.set("sensor.p1", "300")
    hass.states.set("sensor.pv", "0")
    return c


def _prijzen(c, reeks):
    c._get_forecast_entries = lambda **kw: [
        (
            NU + timedelta(minutes=15 * i),
            NU + timedelta(minutes=15 * (i + 1)),
            p * PRICE_SCALE_FACTOR,
        )
        for i, p in enumerate(reeks)
    ]


# --- prijzen aan de uitersten ---------------------------------------


def test_a_negative_price_does_not_break_anything(make_coordinator, hass):
    """Bij -20 ct betaalt het net JOU om te verbruiken."""
    c = _coordinator(make_coordinator, hass)
    _prijzen(c, [-0.20, -0.15, 0.10, 0.30])

    prijs = c.huidige_prijs_eur_per_kwh(NU)

    assert prijs == pytest.approx(-0.20)
    # En de duurste prijs die nog komt is gewoon te vinden.
    assert c._duurste_prijs_vandaag_ct(NU) == pytest.approx(30.0)


def test_an_extreme_price_does_not_break_anything(make_coordinator, hass):
    """150 ct per kWh - zeldzaam, maar niet onmogelijk."""
    c = _coordinator(make_coordinator, hass)
    _prijzen(c, [0.30, 1.50, 0.40])

    assert c._duurste_prijs_vandaag_ct(NU) == pytest.approx(150.0)


def test_all_prices_equal_is_handled(make_coordinator, hass):
    """Een vlakke dag: er valt niets te arbitreren, en dat mag geen

    deling door nul geven.
    """
    c = _coordinator(make_coordinator, hass)
    _prijzen(c, [0.25] * 8)

    assert c.huidige_prijs_eur_per_kwh(NU) == pytest.approx(0.25)


# --- de accu aan de uitersten ---------------------------------------


def test_a_full_battery_reports_full(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    hass.states.set("sensor.soc", "100")

    assert c.accustand_procent() == 100.0


def test_an_empty_battery_reports_empty(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    hass.states.set("sensor.soc", "0")

    assert c.accustand_procent() == 0.0


def test_an_impossible_soc_is_caught_by_the_self_test(
    make_coordinator, hass
):
    """Boven de 100% kan niet uit een geldige berekening komen - de

    zelftoets van v3.65.0 hoort dat te melden.
    """
    c = _coordinator(make_coordinator, hass)
    c.accustand_procent = lambda: 130.0

    namen = [b["naam"] for b in c.get_zelftoets()]

    assert "Accustand buiten bereik" in namen


# --- verbruik en zon aan de uitersten -------------------------------


def test_no_sun_at_all(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    hass.states.set("sensor.pv", "0")

    assert c._read_sensor_float("sensor.pv") == 0.0


def test_a_ten_kilowatt_load(make_coordinator, hass):
    """Kookplaat, oven en Quooker tegelijk. De accu kan 1600 W leveren,

    dus de rest komt van het net - dat mag geen fout geven.
    """
    c = _coordinator(make_coordinator, hass)
    hass.states.set("sensor.p1", "10000")

    assert c._read_corrected_consumption_power() >= 10000


# --- alles weg -------------------------------------------------------


def test_every_sensor_unavailable(make_coordinator, hass):
    """Het scenario waar niets meer te lezen valt. Er mag dan niets

    gestuurd worden, en er mag zeker niet gegokt worden.
    """
    c = _coordinator(make_coordinator, hass)
    for entiteit in (
        "sensor.soc", "sensor.beschikbaar", "sensor.accu",
        "sensor.p1", "sensor.pv",
    ):
        hass.states.set(entiteit, "unavailable")

    assert c.accustand_procent() is None
    assert c._read_corrected_battery_power() is None
    assert c._read_corrected_consumption_power() is None

    # En de aansturing weigert te schrijven zodra de bedieningsentiteit
    # zelf ook weg is - dat is de grendel uit v3.46.0.
    from custom_components.energy_management_system.const import (
        CONF_OPERATION_SELECT,
    )

    c.config[CONF_OPERATION_SELECT] = "select.modus"
    hass.states.set("select.modus", "unavailable")

    assert c._aansturing_bereikbaar() is not None


def test_a_sensor_returning_text(make_coordinator, hass):
    """Sommige integraties melden "on" of "idle" waar een getal hoort."""
    c = _coordinator(make_coordinator, hass)
    hass.states.set("sensor.soc", "idle")

    assert c.accustand_procent() is None


def test_a_genuine_zero_is_not_missing_data(make_coordinator, hass):
    """Nul is een geldige meting: 's nachts levert de zon niets, en dat

    is iets anders dan een sensor die wegviel.
    """
    c = _coordinator(make_coordinator, hass)
    hass.states.set("sensor.pv", "0.0")

    assert c._read_sensor_float("sensor.pv") == 0.0
    assert c._read_sensor_float("sensor.pv") is not None
