"""Diagnostics support for Energy Management System.

Adds a "Download diagnostics" button to the integration's page in Home
Assistant (Instellingen -> Apparaten & Diensten -> Energy Management
System -> drie puntjes), producing a JSON file with the current
configuration and all learned/internal state. Meant to be shared for
debugging/optimizing the integration - it does not contain secrets, only
entity references and learned numeric history.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


def _iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value is not None else None


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    solar_tracker = hass.data[DOMAIN].get(f"{entry.entry_id}_solar_tracker")

    diagnostics: dict[str, Any] = {
        "config": {**entry.data, **entry.options},
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
            "last_available_kwh": coordinator.last_available_kwh,
            "last_needed_kwh_to_bridge": coordinator.last_needed_kwh_to_bridge,
            "last_has_enough_energy": coordinator.last_has_enough_energy,
            "energy_bridge_transition_log": coordinator.energy_bridge_transition_log,
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

    return diagnostics
