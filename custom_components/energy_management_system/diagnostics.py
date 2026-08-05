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

from .const import (
    DOMAIN,
    APPLIANCE_RUNNING_POWER_THRESHOLD_W,
    FIETSLADERS_COMPLETE_THRESHOLD_W,
)

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


def _build_raw_pv_forecast_snapshot(coordinator) -> dict[str, Any]:
    """Raw Solcast half-hour forecast entries (start/end/kwh), bounded to
    roughly the next 48 hours - lets you verify the PV forecast itself
    against the integration's own processed numbers (basisverbruik/
    verwachte_pv_kwh in the explanation breakdown table, v0.61.2)
    without a separate trip to Ontwikkelaarshulpmiddelen each time.
    """
    try:
        entries = coordinator._get_pv_forecast_entries()
    except Exception:  # noqa: BLE001 - diagnostics must never crash on this
        return {"note": "Could not read the PV forecast entries.", "entries": []}

    return {
        "note": (
            "Raw Solcast half-hour entries (start, end, kwh for that "
            "interval), bounded to the next ~48 hours."
        ),
        "entries": [
            {
                "start": _iso(start),
                "end": _iso(end),
                "kwh": round(kwh, 4),
            }
            for start, end, kwh in entries[:96]
        ],
    }


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


def _hours_with_data(getter) -> int:
    return sum(1 for hour in range(24) if getter(hour) is not None)


def _build_learning_health(coordinator, solar_tracker, now: datetime) -> dict[str, Any]:
    """Explicit, automated health check for every learning/history
    mechanism - flags "no progress despite enough elapsed time" so this
    kind of issue is visible directly in the exported JSON, instead of
    only being caught by manually reading the code (see the
    pv_hourly_bias persistence bug found in v0.31.1 - this section exists
    specifically so that class of bug is easier to catch next time).
    """
    days_since_install = (
        (now.date() - coordinator.first_seen_date).days
        if coordinator.first_seen_date
        else None
    )

    def _flag(condition_ok: bool, hint: str) -> str:
        return "OK" if condition_ok else f"SUSPICIOUS: {hint}"

    installed_long_enough_for_days = (
        days_since_install is not None and days_since_install >= 2
    )
    installed_long_enough_for_hours = (
        days_since_install is not None and days_since_install >= 4
    )

    hourly_consumption_hours = _hours_with_data(coordinator.learned_hourly_avg_kw)
    pv_hourly_raw_hours = _hours_with_data(coordinator.raw_pv_hourly_avg)
    pv_hourly_confident_hours = _hours_with_data(coordinator.learned_pv_hourly_ratio)

    checks: dict[str, Any] = {
        "hourly_consumption_profile": {
            "hours_with_data": hourly_consumption_hours,
            "flag": _flag(
                hourly_consumption_hours > 0 or not installed_long_enough_for_hours,
                "0/24 hours filled despite being installed for "
                f"{days_since_install} day(s) - check consumption_power_sensor_entity "
                "is configured and readable, and that the coordinator is actually "
                "running (not stuck on force_manual or a setup error).",
            ),
        },
        "night_consumption_history": {
            "entries": len(coordinator.night_consumption_history),
            "flag": _flag(
                len(coordinator.night_consumption_history) > 0
                or not installed_long_enough_for_days,
                "No entries despite being installed for "
                f"{days_since_install} day(s) - legacy fallback, only "
                "fills during an actual discharging window.",
            ),
        },
        "pv_hourly_bias": {
            "hours_with_any_data": pv_hourly_raw_hours,
            "hours_with_confident_data": pv_hourly_confident_hours,
            "flag": _flag(
                pv_hourly_raw_hours > 0 or not installed_long_enough_for_hours,
                "0/24 hours have ANY data (not even 1 sample) despite "
                f"being installed for {days_since_install} day(s) - check "
                "pv_power_sensor_entity and the solar forecast sensors are "
                "configured and readable. If this ever shows >0 hours_with_any_data "
                "but the sensor's own 'profile' attribute in Home Assistant is "
                "empty, that's the persistence bug fixed in v0.31.1 recurring - "
                "check the sensor's async_added_to_hass restore logic.",
            ),
        },
        "battery_efficiency_learning": {
            "samples": len(coordinator.learned_efficiency_history),
            "learned_percent": coordinator.learned_battery_efficiency_percent,
            "flag": _flag(
                len(coordinator.learned_efficiency_history) > 0
                or not installed_long_enough_for_days,
                "0 efficiency samples despite being installed for "
                f"{days_since_install} day(s) - check battery_power_sensor_entity "
                "and available_energy_sensor_entity are both configured and "
                "readable (both are required for this to learn anything).",
            ),
        },
    }

    if solar_tracker is not None:
        checks["solar_forecast_accuracy"] = {
            "forecast_value_history_entries": len(
                solar_tracker.forecast_value_history
            ),
            "deviation_history_entries": len(solar_tracker.deviation_history),
            "flag": _flag(
                len(solar_tracker.forecast_value_history) > 0
                or not installed_long_enough_for_days,
                "No forecast_value_history entries despite being "
                f"installed for {days_since_install} day(s) - check "
                "solar_forecast_sensor_entity is configured, readable, and "
                "that its value looks like a plausible daily kWh total "
                "(not e.g. a peak-power sensor - see the "
                "MAX_REASONABLE_DAILY_FORECAST_KWH sanity check).",
            ),
        }

    return {
        "days_since_install": days_since_install,
        "checks": checks,
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    solar_tracker = hass.data[DOMAIN].get(f"{entry.entry_id}_solar_tracker")

    config = {**entry.data, **entry.options}

    diagnostics: dict[str, Any] = {
        "config": config,
        "learning_health": _build_learning_health(
            coordinator, solar_tracker, datetime.now()
        ),
        "coordinator": {
            "first_seen_date": _iso(coordinator.first_seen_date),
            "force_manual": coordinator.force_manual,
            "steelstofzuiger_override": coordinator.steelstofzuiger_override,
            "fietsladers_override": coordinator.fietsladers_override,
            "appliance_ready_notifications_enabled": (
                coordinator.appliance_ready_notifications_enabled
            ),
            "last_arbitrage_solar_surplus_w": (
                coordinator.last_arbitrage_solar_surplus_w
            ),
            "learning_only": coordinator.learning_only,
            "water_daily_total_l": coordinator.water_daily_total_l,
            "water_daily_history": coordinator.water_daily_history,
            "water_session_history": coordinator.water_session_history,
            "water_softener_last_regeneration": _iso(
                coordinator.water_softener_last_regeneration
            ),
            "last_extra_dip_margin_eur_per_kwh": coordinator.last_extra_dip_margin_eur_per_kwh,
            "extra_dip_margin_history": coordinator.extra_dip_margin_history,
            "temp_consumption_history": coordinator.temp_consumption_history,
            "temp_consumption_prediction_error_history": (
                coordinator.temp_consumption_prediction_error_history
            ),
            "last_temp_consumption_note": coordinator.last_temp_consumption_note,
            "last_reason": coordinator.last_reason,
            "last_explanation": coordinator.last_explanation,
            "last_current_price_per_kwh": coordinator.last_current_price_per_kwh,
            "last_projection_available_kwh": coordinator.last_projection_available_kwh,
            "last_projection_reserve_kwh": coordinator.last_projection_reserve_kwh,
            "system_status": coordinator.system_status,
            "last_error": coordinator.last_error,
            "last_error_time": (
                coordinator.last_error_time.isoformat()
                if coordinator.last_error_time
                else None
            ),
            "last_successful_update": (
                coordinator.last_successful_update.isoformat()
                if coordinator.last_successful_update
                else None
            ),
            "vacation_mode": coordinator.vacation_mode,
            "dishwasher_usage_hours_with_data": len(
                coordinator.dishwasher_usage_hourly_history
            ),
            "dishwasher_typical_usage_hours": coordinator.learned_appliance_usage_hours(
                coordinator.dishwasher_usage_hourly_history
            ),
            "last_dishwasher_notification": coordinator.last_dishwasher_notification,
            "last_heavy_load_source": coordinator.last_heavy_load_source,
            "last_steelstofzuiger_action": coordinator.last_steelstofzuiger_action,
            "steelstofzuiger_charge_duration_history": (
                coordinator.steelstofzuiger_charge_duration_history
            ),
            "learned_steelstofzuiger_duration_minutes": (
                coordinator.learned_steelstofzuiger_duration_minutes
            ),
            "steelstofzuiger_idle_power_history_w": (
                coordinator._steelstofzuiger_idle_power_history
            ),
            "steelstofzuiger_learned_completion_threshold_w": (
                coordinator._get_learned_completion_threshold_w(
                    "_steelstofzuiger_idle_power_history",
                    APPLIANCE_RUNNING_POWER_THRESHOLD_W,
                )
            ),
            "last_fietsladers_action": coordinator.last_fietsladers_action,
            "fietsladers_charge_duration_history": (
                coordinator.fietsladers_charge_duration_history
            ),
            "learned_fietsladers_duration_minutes": (
                coordinator.learned_fietsladers_duration_minutes
            ),
            "fietsladers_idle_power_history_w": (
                coordinator._fietsladers_idle_power_history
            ),
            "fietsladers_learned_completion_threshold_w": (
                coordinator._get_learned_completion_threshold_w(
                    "_fietsladers_idle_power_history",
                    FIETSLADERS_COMPLETE_THRESHOLD_W,
                )
            ),
            "washing_machine_usage_hours_with_data": len(
                coordinator.washing_machine_usage_hourly_history
            ),
            "washing_machine_typical_usage_hours": (
                coordinator.learned_appliance_usage_hours(
                    coordinator.washing_machine_usage_hourly_history
                )
            ),
            "last_washing_machine_notification": (
                coordinator.last_washing_machine_notification
            ),
            "current_month_discharge_value_eur": round(
                coordinator.current_month_discharge_value_eur, 2
            ),
            "current_month_charge_cost_eur": round(
                coordinator.current_month_charge_cost_eur, 2
            ),
            "current_month_shortfall_days": coordinator.current_month_shortfall_days,
            "current_month_excess_days": coordinator.current_month_excess_days,
            "previous_month_discharge_value_eur": coordinator.previous_month_discharge_value_eur,
            "previous_month_charge_cost_eur": coordinator.previous_month_charge_cost_eur,
            "previous_month_shortfall_days": coordinator.previous_month_shortfall_days,
            "previous_month_excess_days": coordinator.previous_month_excess_days,
            "last_expected_mode": coordinator.last_expected_mode,
            "last_simulated_action": coordinator.last_simulated_action,
            "last_is_expensive": coordinator.last_is_expensive,
            "last_effective_expensive_quarters_count": (
                coordinator.last_effective_expensive_quarters_count
            ),
            "last_max_sellable_quarters_by_capacity": (
                coordinator.last_max_sellable_quarters_by_capacity
            ),
            "last_cheap_block_start": _iso(coordinator.last_cheap_block_start),
            "last_cheap_block_end": _iso(coordinator.last_cheap_block_end),
            "last_discharge_start": _iso(coordinator.last_discharge_start),
            "last_soc_percent": coordinator.last_soc_percent,
            "last_discharge_power_applied": coordinator.last_discharge_power_applied,
            "last_household_load_w": coordinator.last_household_load_w,
            "last_discharge_floor_applied": coordinator.last_discharge_floor_applied,
            "discharge_floor_events": coordinator.discharge_floor_events,
            "last_expensive_tier": coordinator.last_expensive_tier,
            "mode_change_log": coordinator.mode_change_log,
            "last_expensive_price_threshold": coordinator.last_expensive_price_threshold,
            "last_secondary_price_threshold": coordinator.last_secondary_price_threshold,
            "last_low_solar_narrowed_threshold": (
                coordinator.last_low_solar_narrowed_threshold
            ),
            "last_price_priority_held_off": coordinator.last_price_priority_held_off,
            "last_used_soc_taper_fallback": coordinator.last_used_soc_taper_fallback,
            "last_reserve_margin_breakdown": coordinator.last_reserve_margin_breakdown,
            "last_winter_guard_suppressed_today": (
                coordinator.last_winter_guard_suppressed_today
            ),
            "last_charge_power_applied": coordinator.last_charge_power_applied,
            "last_available_kwh": coordinator.last_available_kwh,
            "last_needed_kwh_to_bridge": coordinator.last_needed_kwh_to_bridge,
            "last_needed_kwh_breakdown": coordinator.last_needed_kwh_breakdown,
            "last_has_enough_energy": coordinator.last_has_enough_energy,
            "energy_bridge_transition_log": coordinator.energy_bridge_transition_log,
            "grid_charged_today": coordinator._grid_charged_today,
            "is_negative_price_active": coordinator._is_negative_price_active,
            "reserve_shortfall_history": coordinator.reserve_shortfall_history,
            "reserve_shortfall_dates": coordinator.reserve_shortfall_dates,
            "shortfall_detected_today_so_far": (
                coordinator._shortfall_detected_today
            ),
            "reserve_excess_history": coordinator.reserve_excess_history,
            "reserve_excess_dates": coordinator.reserve_excess_dates,
            "excess_detected_today_so_far": coordinator._excess_detected_today,
            "total_discharge_value_eur": round(
                coordinator.total_discharge_value_eur, 4
            ),
            "total_charge_cost_eur": round(coordinator.total_charge_cost_eur, 4),
            "total_battery_savings_eur": round(
                coordinator.total_battery_savings_eur, 4
            ),
            "battery_cost_basis_eur_per_kwh": (
                round(coordinator.battery_cost_basis_eur_per_kwh, 4)
                if coordinator.battery_cost_basis_eur_per_kwh is not None
                else None
            ),
            "last_energy_balance_error_w": coordinator.last_energy_balance_error_w,
            "energy_balance_error_history": (
                coordinator.energy_balance_error_history
            ),
            "sensor_health_score": coordinator.sensor_health_score,
            "measurement_quality": coordinator.measurement_quality,
            "sluipverbruik_detected": coordinator.sluipverbruik_detected,
            "sluipverbruik_estimated_drift_w": (
                coordinator.sluipverbruik_estimated_drift_w
            ),
            "sluipverbruik_reference_w": coordinator.sluipverbruik_reference_w,
            "cusum_accumulator_kw": round(coordinator.cusum_accumulator_kw, 4),
            "baseline_load_history": coordinator.baseline_load_history,
            "weather_ensemble_cloud_cover_percent": (
                coordinator.weather_ensemble_cloud_cover_percent
            ),
            "weather_ensemble_sources_used": coordinator.weather_ensemble_sources_used,
            "weather_ensemble_label": coordinator.weather_ensemble_label,
            "weather_ensemble_disagreement": (
                coordinator.weather_ensemble_disagreement
            ),
            "dishwasher_state": coordinator._dishwasher_state,
            "dishwasher_cycle_duration_history": (
                coordinator.dishwasher_cycle_duration_history
            ),
            "learned_dishwasher_cycle_duration_minutes": (
                coordinator.learned_dishwasher_cycle_duration_minutes
            ),
            "washing_machine_state": coordinator._washing_machine_state,
            "washing_machine_cycle_duration_history": (
                coordinator.washing_machine_cycle_duration_history
            ),
            "learned_washing_machine_cycle_duration_minutes": (
                coordinator.learned_washing_machine_cycle_duration_minutes
            ),
            "mpc_planned_actions": coordinator.mpc_planned_actions,
            "mpc_projected_total_profit_eur": (
                coordinator.mpc_projected_total_profit_eur
            ),
            "mpc_horizon_quarters_used": coordinator.mpc_horizon_quarters_used,
            "mpc_note": coordinator.mpc_note,
            "monte_carlo_median_deficit_kwh": (
                coordinator.monte_carlo_median_deficit_kwh
            ),
            "monte_carlo_p90_deficit_kwh": coordinator.monte_carlo_p90_deficit_kwh,
            "monte_carlo_p10_deficit_kwh": coordinator.monte_carlo_p10_deficit_kwh,
            "monte_carlo_shortfall_probability_percent": (
                coordinator.monte_carlo_shortfall_probability_percent
            ),
            "monte_carlo_simulations_run": coordinator.monte_carlo_simulations_run,
            "monte_carlo_hours_simulated": coordinator.monte_carlo_hours_simulated,
            "monte_carlo_note": coordinator.monte_carlo_note,
            "kalman_soc_filtered_kwh": coordinator.kalman_soc_filtered_kwh,
            "kalman_soc_raw_kwh": coordinator.kalman_soc_raw_kwh,
            "kalman_pv_filtered_w": coordinator.kalman_pv_filtered_w,
            "kalman_pv_raw_w": coordinator.kalman_pv_raw_w,
            "kalman_load_filtered_w": coordinator.kalman_load_filtered_w,
            "kalman_load_raw_w": coordinator.kalman_load_raw_w,
            "digital_twin_projected_profit_eur": (
                coordinator.digital_twin_projected_profit_eur
            ),
            "digital_twin_final_soc_kwh": coordinator.digital_twin_final_soc_kwh,
            "digital_twin_hours_simulated": coordinator.digital_twin_hours_simulated,
            "digital_twin_note": coordinator.digital_twin_note,
            "nilm_unconfirmed_candidates": coordinator.nilm_unconfirmed_candidates,
            "nilm_confirmed_devices": coordinator.nilm_confirmed_devices,
            "nilm_rejected_entities": coordinator.nilm_rejected_entities,
            "nilm_devices_table": coordinator.get_nilm_devices_table(),
            "advisory_readiness": coordinator.advisory_readiness,
            "living_room_current_temp_c": coordinator.living_room_current_temp_c,
            "living_room_current_humidity_percent": (
                coordinator.living_room_current_humidity_percent
            ),
            "living_room_temp_bucket_history": (
                coordinator.living_room_temp_bucket_history
            ),
            "climate_rate_history": coordinator.climate_rate_history,
            "climate_forecast_trajectory": coordinator.climate_forecast_trajectory,
            "climate_forecast_note": coordinator.climate_forecast_note,
            "climate_shutter_state": coordinator.climate_shutter_state,
            "climate_airco_state": coordinator.climate_airco_state,
            "climate_live_outdoor_temp_c": coordinator.climate_live_outdoor_temp_c,
            "total_feedin_premium_eur": round(
                coordinator.total_feedin_premium_eur, 4
            ),
            "learned_battery_efficiency_percent": (
                coordinator.learned_battery_efficiency_percent
            ),
            "learned_efficiency_history": coordinator.learned_efficiency_history,
            "night_consumption_history_kw": coordinator.night_consumption_history,
            "learned_night_consumption_kw": coordinator.learned_night_consumption_kw,
            "hourly_consumption_profile_kw": {
                str(hour): coordinator.learned_hourly_avg_kw(hour)
                for hour in range(24)
                if coordinator.learned_hourly_avg_kw(hour) is not None
            },
            "pv_hourly_bias_profile_confident": {
                str(hour): coordinator.learned_pv_hourly_ratio(hour)
                for hour in range(24)
                if coordinator.learned_pv_hourly_ratio(hour) is not None
            },
            "pv_hourly_bias_profile_raw": {
                str(hour): coordinator.raw_pv_hourly_avg(hour)
                for hour in range(24)
                if coordinator.raw_pv_hourly_avg(hour) is not None
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
    diagnostics["pv_forecast_raw"] = _build_raw_pv_forecast_snapshot(coordinator)
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
