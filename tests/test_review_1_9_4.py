"""Bevindingen uit de volledige diagnostiek-controle (v1.9.4).

Gevraagd: "Graag het hele diagnostiek bestand nu nakijken alvorens ik een
nieuwe versie installeer."
"""
from custom_components.energy_management_system.const import (
    CONF_PRICE_SENSOR,
)


def test_the_efficiency_is_not_converted_twice(make_coordinator, hass):
    """Het overzicht toonde 8290% terwijl `learning_health` in dezelfde
    export 82,9 meldde.

    In v1.3.0 stond hier een vermenigvuldiging met 100, gebaseerd op een
    testwaarde van 0,85 - maar `learned_battery_efficiency_percent` geeft
    wel degelijk een percentage. De test die dat vastlegde gebruikte
    dezelfde verkeerde aanname, dus hij ving de fout niet.
    """
    c = make_coordinator({})
    c.learned_efficiency_history = [82.9] * 8

    rij = next(
        r for r in c.get_reliability_overview() if r["naam"] == "Accu-rendement"
    )

    assert rij["waarde"] == 82.9
    assert rij["waarde"] < 100


def test_the_efficiency_stays_a_plausible_percentage(make_coordinator, hass):
    """Een rendement boven 100% is fysiek onmogelijk - dat hoort nooit
    uit dit veld te komen, ongeacht de invoer."""
    c = make_coordinator({})

    for waarde in (75.0, 82.9, 95.0):
        c.learned_efficiency_history = [waarde] * 8
        rij = next(
            r
            for r in c.get_reliability_overview()
            if r["naam"] == "Accu-rendement"
        )
        assert 0 < rij["waarde"] <= 100, waarde


def test_the_gas_amount_is_rounded(make_coordinator, hass):
    """De rauwe Zonneplan-waarde heeft zeven decimalen (0,0466657 €); in
    een kostenoverzicht is dat ruis."""
    c = make_coordinator({CONF_PRICE_SENSOR: "sensor.zonneplan_tariff"})
    hass.states.set("sensor.zonneplan_electricity_delivery_costs_today", "0.04")
    hass.states.set("sensor.zonneplan_gas_delivery_costs_today", "0.0466657")

    kosten = c._huidige_dagkosten()

    assert kosten["gas_eur"] == 0.05


def test_no_gas_stays_none(make_coordinator, hass):
    """Afronden mag geen nul maken van een ontbrekende waarde - nul
    suggereert dat er niets verbruikt is."""
    c = make_coordinator({CONF_PRICE_SENSOR: "sensor.zonneplan_tariff"})
    hass.states.set("sensor.zonneplan_electricity_delivery_costs_today", "0.04")

    assert c._huidige_dagkosten()["gas_eur"] is None
