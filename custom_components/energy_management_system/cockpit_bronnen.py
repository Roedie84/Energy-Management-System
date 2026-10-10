"""Welke entiteiten het cockpitdashboard leest (v5.71).

Het dashboard draait in de browser en kent de configuratie niet: welke
sensor de laadstand is, welke de P1-meter, welke de zon. En de eigen
entiteiten heten per installatie anders (soms met een ruimtenaam ervoor,
soms Engels). Deze module zet beide op een rij, zodat de kaart nooit een
entity-id hoeft te raden.

Bewust zonder Home Assistant-imports: los te testen.
"""
from __future__ import annotations

from .const import (
    CONF_AIRCO_CLIMATE_ENTITY,
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_BACKYARD_TEMPERATURE_SENSOR,
    CONF_BATTERY_MODULE_SOC_SENSORS,
    CONF_BATTERY_POWER_SENSOR,
    CONF_BATTERY_TOTAL_CAPACITY_SENSOR,
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_INKOOP_EUR_VANDAAG_SENSOR,
    CONF_INVERT_BATTERY_POWER_SIGN,
    CONF_LIVING_ROOM_TEMPERATURE_SENSOR,
    CONF_OPERATION_SELECT,
    CONF_PRICE_SENSOR,
    CONF_PV_POWER_SENSOR,
    CONF_SOC_SENSOR,
    CONF_SOLAR_ACTUAL_SENSOR,
    CONF_SOLAR_FORECAST_SENSOR,
    CONF_SOLAR_REMAINING_TODAY_SENSOR,
    CONF_SOLAR_TODAY_FORECAST_SENSOR,
    CONF_TERUGLEVER_EUR_VANDAAG_SENSOR,
    CONF_WATER_ACTIVE_USAGE_SENSOR,
)

# Sleutel op het dashboard -> configuratiesleutel.
EXTERNE_BRONNEN: dict[str, str] = {
    "soc": CONF_SOC_SENSOR,
    "beschikbaar": CONF_AVAILABLE_ENERGY_SENSOR,
    "capaciteit": CONF_BATTERY_TOTAL_CAPACITY_SENSOR,
    "accu_vermogen": CONF_BATTERY_POWER_SENSOR,
    "net": CONF_CONSUMPTION_POWER_SENSOR,
    "pv": CONF_PV_POWER_SENSOR,
    "zon_vandaag": CONF_SOLAR_TODAY_FORECAST_SENSOR,
    "zon_rest": CONF_SOLAR_REMAINING_TODAY_SENSOR,
    "zon_morgen": CONF_SOLAR_FORECAST_SENSOR,
    "zon_werkelijk": CONF_SOLAR_ACTUAL_SENSOR,
    "prijs": CONF_PRICE_SENSOR,
    "modus": CONF_OPERATION_SELECT,
    "inkoop_vandaag": CONF_INKOOP_EUR_VANDAAG_SENSOR,
    "teruglever_vandaag": CONF_TERUGLEVER_EUR_VANDAAG_SENSOR,
    "water": CONF_WATER_ACTIVE_USAGE_SENSOR,
    "airco": CONF_AIRCO_CLIMATE_ENTITY,
    "temp_binnen": CONF_LIVING_ROOM_TEMPERATURE_SENSOR,
    "temp_buiten": CONF_BACKYARD_TEMPERATURE_SENSOR,
}


def externe_bronnen(config: dict) -> dict:
    """De geconfigureerde entiteiten onder de namen die de kaart kent."""
    uit = {
        sleutel: config.get(conf)
        for sleutel, conf in EXTERNE_BRONNEN.items()
        if isinstance(config.get(conf), str) and config.get(conf)
    }
    modules = config.get(CONF_BATTERY_MODULE_SOC_SENSORS)
    if isinstance(modules, list) and modules:
        uit["modules_soc"] = [m for m in modules if isinstance(m, str)]
    # De Zendure meldt laden als negatief bij sommige installaties.
    uit["accu_omkeren"] = bool(config.get(CONF_INVERT_BATTERY_POWER_SIGN, False))
    return uit


def eigen_entiteiten(entry_id: str, registerregels) -> dict:
    """Eigen entiteiten op hun vaste sleutel (unique_id zonder entry-id).

    `registerregels`: (unique_id, entity_id)-paren van deze config entry.
    De unique_id verandert nooit; de entity-id kan de gebruiker hernoemen.
    """
    voorvoegsel = f"{entry_id}_"
    uit = {}
    for unique_id, entity_id in registerregels:
        if not isinstance(unique_id, str) or not unique_id.startswith(voorvoegsel):
            continue
        uit[unique_id[len(voorvoegsel):]] = entity_id
    return dict(sorted(uit.items()))
