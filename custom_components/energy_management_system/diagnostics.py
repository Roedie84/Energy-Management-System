"""Diagnostics support for Energy Management System.

Adds a "Download diagnostics" button to the integration's page in Home
Assistant (Instellingen -> Apparaten & Diensten -> Energy Management
System -> drie puntjes), producing a JSON file with the current
configuration and all learned/internal state. Meant to be shared for
debugging/optimizing the integration - it does not contain secrets, only
entity references and learned numeric history.

Also includes a bounded scan of the wider Home Assistant instance for
entities that could be relevant to expanding this into a fuller,
usage-aware EMS (other energy/power sensors, climate/appliance entities,
lighting, occupancy/motion sensors, and illuminance/lux sensors) - not a
full dump of everything, to avoid pulling in unrelated things like
cameras, locks, or media players.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

# Domains that are inherently relevant to an EMS, regardless of naming.
# "light" is included to help correlate lighting usage with occupancy
# patterns - useful context for a smarter, usage-aware EMS.
RELEVANT_DOMAINS = {"climate", "humidifier", "light"}

# device_class values worth surfacing even outside those domains.
# motion/occupancy/presence -> occupancy patterns; illuminance -> lux
# sensors, useful to cross-check against solar forecast/actual data and
# to understand daylight-driven lighting/appliance usage.
RELEVANT_DEVICE_CLASSES = {
    "power",
    "energy",
    "battery",
    "monetary",
    "motion",
    "occupancy",
    "presence",
    "illuminance",
}

# Keywords (in entity_id or friendly_name) hinting at shiftable appliances
# or other EMS-relevant equipment, based on what's come up in this
# integration's own development (dishwasher, washing machine, EV, etc.).
RELEVANT_KEYWORDS = (
    "vaatwasser",
    "wasmachine",
    "droger",
    "airco",
    "warmtepomp",
    "boiler",
    "laadpaal",
    "dishwasher",
    "washer",
    "dryer",
    "heatpump",
    "ev_charger",
    "wallbox",
)


def _iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _scan_relevant_entities(
    hass: HomeAssistant, already_configured: set[str]
) -> list[dict[str, Any]]:
    """Bounded scan of Home Assistant entities that could be relevant for
    expanding this EMS. Not every result is necessarily useful - this is
    meant as a starting point to spot new possibilities, not an automatic
    recommendation.
    """
    results: list[dict[str, Any]] = []

    for state in hass.states.async_all():
        entity_id = state.entity_id
        domain = entity_id.split(".", 1)[0]
        device_class = state.attributes.get("device_class")
        friendly_name = state.attributes.get("friendly_name", "") or ""
        unit = state.attributes.get("unit_of_measurement")

        is_relevant = (
            domain in RELEVANT_DOMAINS
            or device_class in RELEVANT_DEVICE_CLASSES
            or any(kw in entity_id.lower() for kw in RELEVANT_KEYWORDS)
            or any(kw in friendly_name.lower() for kw in RELEVANT_KEYWORDS)
        )
        if not is_relevant:
            continue

        results.append(
            {
                "entity_id": entity_id,
                "domain": domain,
                "device_class": device_class,
                "unit_of_measurement": unit,
                "friendly_name": friendly_name,
                "state": state.state,
                "already_used_by_this_integration": entity_id in already_configured,
            }
        )

    return sorted(results, key=lambda item: item["entity_id"])


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    solar_tracker = hass.data[DOMAIN].get(f"{entry.entry_id}_solar_tracker")

    config = {**entry.data, **entry.options}

    diagnostics: dict[str, Any] = {
        "config": config,
        "coordinator": {
            "force_manual": coordinator.force_manual,
            "learning_only": coordinator.learning_only,
            "last_reason": coordinator.last_reason,
            "last_expected_mode": coordinator.last_expected_mode,
            "last_simulated_action": coordinator.last_simulated_action,
            "last_is_expensive": coordinator.last_is_expensive,
            "last_effective_expensive_quarters_count": (
                coordinator.last_effective_expensive_quarters_count
            ),
            "last_cheap_block_start": _iso(coordinator.last_cheap_block_start),
            "last_cheap_block_end": _iso(coordinator.last_cheap_block_end),
            "last_discharge_start": _iso(coordinator.last_discharge_start),
            "last_soc_percent": coordinator.last_soc_percent,
            "last_discharge_power_applied": coordinator.last_discharge_power_applied,
            "last_charge_power_applied": coordinator.last_charge_power_applied,
            "last_available_kwh": coordinator.last_available_kwh,
            "last_needed_kwh_to_bridge": coordinator.last_needed_kwh_to_bridge,
            "last_needed_kwh_breakdown": coordinator.last_needed_kwh_breakdown,
            "last_has_enough_energy": coordinator.last_has_enough_energy,
            "energy_bridge_transition_log": coordinator.energy_bridge_transition_log,
            "grid_charged_today": coordinator._grid_charged_today,
            "is_negative_price_active": coordinator._is_negative_price_active,
            "reserve_shortfall_history": coordinator.reserve_shortfall_history,
            "shortfall_detected_today_so_far": (
                coordinator._shortfall_detected_today
            ),
            "total_discharge_value_eur": round(
                coordinator.total_discharge_value_eur, 4
            ),
            "total_charge_cost_eur": round(coordinator.total_charge_cost_eur, 4),
            "night_consumption_history_kw": coordinator.night_consumption_history,
            "learned_night_consumption_kw": coordinator.learned_night_consumption_kw,
            "hourly_consumption_profile_kw": {
                str(hour): coordinator.learned_hourly_avg_kw(hour)
                for hour in range(24)
                if coordinator.learned_hourly_avg_kw(hour) is not None
            },
            "pv_hourly_bias_profile": {
                str(hour): coordinator.learned_pv_hourly_ratio(hour)
                for hour in range(24)
                if coordinator.learned_pv_hourly_ratio(hour) is not None
            },
            "was_bootstrapped_from_history": (
                coordinator.was_bootstrapped_from_history
            ),
            "upcoming_transitions": coordinator.last_transitions,
        },
    }

    if solar_tracker is not None:
        diagnostics["solar_forecast_tracker"] = {
            "enabled": solar_tracker.enabled,
            "last_predicted_kwh": solar_tracker.last_predicted_kwh,
            "last_actual_kwh": solar_tracker.last_actual_kwh,
            "last_deviation_percent": solar_tracker.last_deviation_percent,
            "last_compared_date": _iso(solar_tracker.last_compared_date),
            "deviation_history_percent": solar_tracker.deviation_history,
            "learned_bias_percent": solar_tracker.learned_bias_percent,
            "forecast_value_history_kwh": solar_tracker.forecast_value_history,
            "learned_typical_forecast_kwh": (
                solar_tracker.learned_typical_forecast_kwh
            ),
            "pending_predicted_kwh": solar_tracker.pending_predicted_kwh,
            "pending_predicted_date": _iso(solar_tracker.pending_predicted_date),
            "was_bootstrapped_from_history": (
                solar_tracker.was_bootstrapped_from_history
            ),
        }

    already_configured = {
        value for value in config.values() if isinstance(value, str) and "." in value
    }
    diagnostics["system_scan"] = {
        "note": (
            "Bounded scan of Home Assistant entities that could be "
            "relevant for expanding this EMS into a usage-aware system: "
            "energy/power/battery sensors, climate entities, lighting, "
            "occupancy/motion sensors, illuminance (lux) sensors, and "
            "common shiftable-appliance keywords. This is a starting "
            "point for discussion, not an automatic recommendation - not "
            "everything listed here is necessarily useful or safe to "
            "wire up."
        ),
        "entities": _scan_relevant_entities(hass, already_configured),
    }

    return diagnostics
