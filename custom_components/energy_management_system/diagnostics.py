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

import logging
from datetime import date, datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    APPLIANCE_RUNNING_POWER_THRESHOLD_W,
    FIETSLADERS_COMPLETE_THRESHOLD_W,
)

_LOGGER = logging.getLogger(__name__)

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

    # v1.19.3, gemeld: "De diagnostiek blijft nu een text file, wordt
    # geen json, dit suggereert dat daar nu ook iets fout gaat?"
    #
    # Terechte conclusie. Deze functie was één grote dict-expressie:
    # gooit één aanroep een fout, dan mislukt de HELE export en krijg je
    # een foutpagina in plaats van een bestand.
    #
    # Dat is precies het verkeerde moment om te falen - de export is het
    # gereedschap dat je nodig hebt WANNEER er iets stuk is. Dezelfde
    # vorm als het attributenblok in v1.19.1, en dezelfde oplossing: elk
    # onderdeel apart, en een fout wordt zichtbaar in plaats van fataal.
    def _veilig(naam: str, functie):
        try:
            resultaat = functie()
        except Exception as fout:  # noqa: BLE001
            _LOGGER.exception("Diagnostiek: %s kon niet worden opgehaald", naam)
            # v1.29.0, gemeld: "Dat er een txt wordt gemaakt is een
            # error, ik had daar graag een melding van verwacht zoals
            # eerder afgesproken."
            #
            # Deze afscherming ving de fout al netjes op, maar hield hem
            # ook stil: het mislukte onderdeel kreeg een {"fout": ...} in
            # de export en verder gebeurde er niets. Wie de export niet
            # regel voor regel leest, merkt er niets van.
            #
            # Nu belandt hij in `internal_failures`, en dat veld stuurt
            # sinds deze versie een melding.
            coordinator.internal_failures[f"diagnostiek:{naam}"] = (
                f"{type(fout).__name__}: {fout}"
            )
            return {"fout": f"{type(fout).__name__}: {fout}"}
        coordinator.internal_failures.pop(f"diagnostiek:{naam}", None)
        return resultaat

    diagnostics: dict[str, Any] = {
        "config": config,
        "diagnostic_summary": _veilig("get_diagnostic_summary", coordinator.get_diagnostic_summary),
        "missing_optional_features": _veilig("get_missing_optional_features", coordinator.get_missing_optional_features),
        # v1.28.0, gemeld: "Tevens is de diagnostiek weer een txt i.p.v.
        # json."
        #
        # Twee fouten in deze ene regel. `datetime.now()` geeft een tijd
        # ZONDER tijdzone, terwijl alles binnen de integratie er wel een
        # heeft. Draait er op dat moment een vaatwasser of wasmachine,
        # dan rekent het verhaal `nu - starttijd` uit en gooit Python
        # "can't subtract offset-naive and offset-aware datetimes".
        #
        # En die aanroep stond als enige NIET in `_veilig`, dus die fout
        # sloopte de hele export: Home Assistant geeft dan een foutpagina
        # terug en de browser bewaart die als .txt. Precies zoals in
        # v1.19.3, alleen bleven deze twee regels toen staan.
        #
        # Dat het maar soms gebeurde, past bij de oorzaak: alleen als er
        # net een apparaat draaide. De vaatwasser draait hier meestal
        # tussen 13 en 15 uur.
        "live_narrative": _veilig(
            "get_live_narrative",
            lambda: coordinator.get_live_narrative(dt_util.now()),
        ),
        "ems_kpis": {
            "peak_power_today_w": coordinator.peak_power_today_w,
            "peak_power_current_month_w": coordinator.peak_power_current_month_w,
            "peak_power_previous_month_w": coordinator.peak_power_previous_month_w,
            "peak_power_all_time_w": coordinator.peak_power_all_time_w,
            "peak_power_all_time_date": coordinator.peak_power_all_time_date,
            "peak_power_daily_history": coordinator.peak_power_daily_history,
            "actual_cost_today_eur": coordinator.actual_cost_today_eur,
            "counterfactual_cost_today_eur": coordinator.counterfactual_cost_today_eur,
            "actual_cost_current_month_eur": coordinator.actual_cost_current_month_eur,
            "counterfactual_cost_current_month_eur": (
                coordinator.counterfactual_cost_current_month_eur
            ),
            "actual_cost_all_time_eur": coordinator.actual_cost_all_time_eur,
            "counterfactual_cost_all_time_eur": (
                coordinator.counterfactual_cost_all_time_eur
            ),
            "self_consumption_ratio_percent": (
                coordinator.self_consumption_ratio_percent
            ),
            "self_sufficiency_ratio_percent": (
                coordinator.self_sufficiency_ratio_percent
            ),
            "pv_production_today_kwh": coordinator.pv_production_today_kwh,
            "pv_export_today_kwh": coordinator.pv_export_today_kwh,
            "gross_consumption_today_kwh": coordinator.gross_consumption_today_kwh,
            "grid_import_today_kwh": coordinator.grid_import_today_kwh,
            "battery_cumulative_discharged_kwh": (
                coordinator.battery_cumulative_discharged_kwh
            ),
            "battery_estimated_full_cycles": (
                coordinator.battery_estimated_full_cycles
            ),
            "battery_estimated_capacity_percent": (
                coordinator.battery_estimated_capacity_percent
            ),
            "co2_emitted_today_kg": coordinator.co2_emitted_today_kg,
            "last_co2_intensity_g_per_kwh": (
                coordinator.last_co2_intensity_g_per_kwh
            ),
        },
        "learning_health": _veilig(
            "learning_health",
            lambda: _build_learning_health(
                coordinator, solar_tracker, dt_util.now()
            ),
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
            "persisted_state_snapshot": _veilig(
                "persisted_state_snapshot", coordinator._collect_persisted_state
            ),
            "weather_ensemble_readings": coordinator.weather_ensemble_readings,
            "weather_ensemble_spread_percent": (
                coordinator.weather_ensemble_spread_percent
            ),
            # v1.9.0: het verloop binnen de dag en de patronen erover
            # heen. Zonder deze twee is een export een momentopname en
            # valt er weinig uit af te leiden over wat er 's nachts
            # gebeurde.
            "decision_log": coordinator.decision_log,
            "daily_report_history": coordinator.daily_report_history,
            "energy_cost_overview": _veilig("get_energy_cost_overview", coordinator.get_energy_cost_overview),
            "daily_cost_history": coordinator.daily_cost_history,
            "self_evaluation": _veilig("get_self_evaluation", coordinator.get_self_evaluation),
            "gacs_assessment": _veilig("get_gacs_assessment", coordinator.get_gacs_assessment),
            # v1.14.3: de bron van de dagopwek. Zonder dit veld is in
            # een export niet na te gaan of de kWh-meter uit v1.9.1
            # daadwerkelijk wordt gebruikt of dat er nog wordt
            # geïntegreerd.
            "pv_production_source": coordinator.pv_production_source,
            # v1.16.3: controleert of het dashboard naar bestaande,
            # gevulde entiteiten verwijst. Tien van de veertien
            # problemen op één dag zaten in die laag, en die was in de
            # export niet zichtbaar.
            # v1.17.2: hoe betrouwbaar de PV-voorspelling per dag is,
            # niet alleen de gemiddelde bias.
            # v1.18.2, gevraagd: "Alles wat je gebouwd hebt vandaag moet
            # in de diagnostiek herleidbaar zijn zodat we na delen van de
            # diagnostiek eventueel kunnen corrigeren."
            #
            # Zeven onderdelen van vandaag stonden er nog niet in. Zonder
            # die velden is een gemeld probleem alleen op een screenshot
            # te zien, en dat is precies wat er vandaag telkens misging.
            "topic_summaries": _veilig("get_topic_summaries", coordinator.get_topic_summaries),
            "presence_overview": _veilig("get_presence_overview", coordinator.get_presence_overview),
            # v1.19.4: onderdelen die zichzelf niet konden berekenen.
            "internal_failures": coordinator.internal_failures,
            # v1.22.0: het uitstelplan voor zonopvang.
            "solar_defer_plan": coordinator.last_solar_defer_plan,
            # v1.23.0: mag er verkocht worden, en waarom wel of niet?
            "sell_check": coordinator.last_sell_check,
            # v1.55.0: accu tegen net.
            "battery_vs_grid": coordinator.last_battery_vs_grid,
            # v1.23.4: de werkelijke ondergrens waarop alles rust, en de
            # eerste voorspelling per kwartier. Zonder die twee is niet
            # na te gaan waarom een SoC-percentage is wat het is, of
            # waarom een kwartier als gewijzigd geldt.
            "effective_min_soc_percent": _veilig(
                "effective_min_soc_percent",
                coordinator.effective_min_soc_percent,
            ),
            "quarter_plan_first_seen": coordinator.quarter_plan_first_seen,
            # v1.31.0: het volledige rapport, ook de dagen die het
            # dashboard niet toont.
            # v1.32.0: rendement per halve slag.
            # v1.37.0: klopt het prijsattribuut, dus zit de belasting erin?
            "price_attribute_check": _veilig(
                "get_price_attribute_check", coordinator.get_price_attribute_check
            ),
            "efficiency_overview": _veilig(
                "get_efficiency_overview", coordinator.get_efficiency_overview
            ),
            # v1.38.0: de proefstand - kandidaten die meerekenen maar
            # niets sturen.
            # v1.47.0: ingangen die er zijn maar niets leveren.
            # v1.52.0: de besparing gecorrigeerd voor wat er nog in de
            # accu zit.
            "savings_correction": _veilig(
                "get_savings_correction", coordinator.get_savings_correction
            ),
            # v1.58.0: draaiende noodlopen en hoe lang al.
            # v1.59.0: wat veroudering versnelt.
            # v1.60.0: waarom doet de aansturing dit nu.
            # v1.61.0: gepland witgoed dat in de reserve meetelt.
            "planned_appliances": _veilig(
                "get_planned_appliance_load",
                coordinator.get_planned_appliance_load,
            ),
            "why_now": _veilig("get_why_now", coordinator.get_why_now),
            "aging_drivers": _veilig(
                "get_aging_drivers", coordinator.get_aging_drivers
            ),
            "fallback_overview": _veilig(
                "get_fallback_overview", coordinator.get_fallback_overview
            ),
            "input_health": _veilig(
                "get_input_health", coordinator.get_input_health
            ),
            "pending_overview": _veilig(
                "get_pending_overview", coordinator.get_pending_overview
            ),
            "proefstand": _veilig("get_proefstand", coordinator.get_proefstand),
            "wear_cost": _veilig(
                "get_wear_cost_overview", coordinator.get_wear_cost_overview
            ),
            "plan_review": _veilig("get_plan_review", coordinator.get_plan_review),
            "plan_snapshot": coordinator.plan_snapshot,
            "quarter_plan_summary": _veilig(
                "quarter_plan_summary", coordinator.get_quarter_plan_summary
            ),
            # v1.22.2: de verwachte planning per kwartier, met SoC.
            "quarter_plan": _veilig(
                "quarter_plan", coordinator.get_quarter_plan
            ),
            # v1.21.0: welke koelapparaten een temperatuurmarge krijgen.
            "cooling_temperature_margins": {
                gegevens.get("friendly_name") or entity_id: {
                    "marge_procent": gegevens.get("temperatuurmarge_procent"),
                    "temperatuurdagen": len(
                        gegevens.get("outdoor_temp_history") or []
                    ),
                }
                for entity_id, gegevens in (
                    coordinator.nilm_confirmed_devices or {}
                ).items()
                if gegevens.get("temperatuurmarge_procent")
            },
            # v1.20.2: is de bewolking gewogen, en welke bron gaf bij
            # grote onenigheid de doorslag?
            "weather_ensemble_weighted": coordinator.weather_ensemble_weighted,
            "weather_ensemble_chosen_source": (
                coordinator.weather_ensemble_chosen_source
            ),
            "expansion_advice": _veilig("get_expansion_advice", coordinator.get_expansion_advice),
            "presence_week_profile": coordinator.presence_week_profile,
            # v1.26.0: de VOLLEDIGE tijdlijn - het dashboard toont er 30,
            # maar juist voor het achteraf controleren moet alles in de
            # export staan.
            "presence_timeline": _veilig(
                "get_presence_timeline", coordinator.get_presence_timeline
            ),
            "presence_day_totals": _veilig(
                "get_presence_day_totals", coordinator.get_presence_day_totals
            ),
            "water_source_profiles": coordinator.water_source_profiles,
            "water_source_overview": _veilig("get_water_source_overview", coordinator.get_water_source_overview),
            "living_room_temp_bucket_direction": (
                coordinator.living_room_temp_bucket_direction
            ),
            "battery_discharge_today_kwh": (
                coordinator.battery_discharge_today_kwh
            ),
            "battery_module_rest_spread_c": (
                _veilig("module_rest_spread", coordinator._module_temperature_spread_at_rest)
            ),
            "pv_forecast_quality": _veilig("get_pv_forecast_quality", coordinator.get_pv_forecast_quality),
            # v1.17.8: wordt de voorspelling ook echt gecorrigeerd, of
            # alleen gemeten?
            "pv_correction_status": _veilig("get_pv_correction_status", coordinator.get_pv_correction_status),
            "dashboard_health": _veilig("get_dashboard_health", coordinator.get_dashboard_health),
            "stalled_series": _veilig("get_stalled_series_report", coordinator.get_stalled_series_report),
            "plausibility_warnings": _veilig("get_plausibility_warnings", coordinator.get_plausibility_warnings),
            "sensor_health_breakdown": _veilig("get_sensor_health_breakdown", coordinator.get_sensor_health_breakdown),
            "zonneplan_cost_comparison": (
                _veilig("get_zonneplan_cost_comparison", coordinator.get_zonneplan_cost_comparison)
            ),
            "weather_source_reliability": (
                _veilig("get_weather_source_reliability", coordinator.get_weather_source_reliability)
            ),
            "solar_forecast_health": _veilig("get_solar_forecast_health", coordinator.get_solar_forecast_health),
            "low_solar_margin": _veilig("get_low_solar_margin", coordinator.get_low_solar_margin),
            "pv_installation_profile": _veilig("get_pv_installation_profile", coordinator.get_pv_installation_profile),
            "pv_peak_azimuth_history": coordinator.pv_peak_azimuth_history,
            "reliability_overview": _veilig("get_reliability_overview", coordinator.get_reliability_overview),
            "sun_elevation_degrees": _veilig("get_sun_elevation_degrees", coordinator.get_sun_elevation_degrees),
            "is_daylight": coordinator.is_daylight_now(),
            "notifications": _veilig("get_notification_overview", coordinator.get_notification_overview),
            "notification_history": coordinator.notification_history,
            "notifications_master_enabled": (
                coordinator.notifications_master_enabled
            ),
            "sensor_cadence": _veilig("get_sensor_cadence_report", coordinator.get_sensor_cadence_report),
            "kalman_divergence": _veilig("get_kalman_divergence_status", coordinator.get_kalman_divergence_status),
            "weather_ensemble_agreement": (
                _veilig("get_weather_ensemble_agreement_status", coordinator.get_weather_ensemble_agreement_status)
            ),
            "digital_twin_accuracy": _veilig("get_digital_twin_accuracy_status", coordinator.get_digital_twin_accuracy_status),
            "digital_twin_accuracy_history": (
                coordinator.digital_twin_accuracy_history
            ),
            "battery_module_live": coordinator.battery_module_live,
            "battery_module_health": coordinator.battery_module_health,
            "battery_module_spread": coordinator.battery_module_spread,
            "battery_cooling_state": coordinator.battery_cooling_state,
            "battery_cooling_history": coordinator.battery_cooling_history,
            "water_daily_total_l": coordinator.water_daily_total_l,
            # v0.63.119: losstaande dagteller, niet begrensd door de
            # weergavelijst van 20 momenten - dit is wat de
            # "verklaart maar X L"-check nu gebruikt.
            "water_sessions_today_l": coordinator.water_sessions_today_l,
            "water_sessions_today_count": coordinator.water_sessions_today_count,
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
            # v1.37.2: het veld hierboven is een bijproduct van de
            # ontlaadberekening en staat op None zodra de tick eerder
            # eindigt - in de export van 11 augustus 11:21 was dat zo,
            # midden in het goedkope blok. De gemeten stand hoort er dan
            # nog steeds te staan.
            "accustand_procent": _veilig(
                "accustand_procent", coordinator.accustand_procent
            ),
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
            # v0.63.117 - salderingsregime en teruglever-waardering.
            "salderen_active": coordinator.salderen_active,
            "salderen_end_date": coordinator.config.get("salderen_end_date"),
            "current_feedin_value_eur_per_kwh": (
                coordinator.current_feedin_value_eur_per_kwh
            ),
            "feedin_import_spread_eur_per_kwh": (
                coordinator.feedin_import_spread_eur_per_kwh
            ),
            "charge_pv_kwh_total": coordinator.charge_pv_kwh_total,
            "charge_grid_kwh_total": coordinator.charge_grid_kwh_total,
            "discharge_export_kwh_total": coordinator.discharge_export_kwh_total,
            "forgone_feedin_eur_total": coordinator.forgone_feedin_eur_total,
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
            "nilm_dismissed_duplicate_pairs": (
                coordinator.nilm_dismissed_duplicate_pairs
            ),
            "nilm_devices_table": _veilig("get_nilm_devices_table", coordinator.get_nilm_devices_table),
            "nilm_duplicate_pairs": _veilig("get_nilm_duplicate_pairs", coordinator.get_nilm_duplicate_pairs),
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
            "climate_forecast_learned_bias_c": coordinator.climate_forecast_learned_bias_c,
            "climate_forecast_bias_history": coordinator.climate_forecast_bias_history,
            "last_backyard_spike_filtered_note": coordinator.last_backyard_spike_filtered_note,
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
            # v1.22.1: de losse kwartierprijzen, niet alleen de
            # samengevoegde blokken met min en max.
            #
            # Bij het narekenen van het uitstelplan bleek dit een gat:
            # de integratie kent de prijzen tot morgen middernacht, maar
            # de export toonde voor een hele dag maar drie blokken met
            # "0,1267 - 0,3505". Daarmee valt niet na te gaan WANNEER de
            # prijs hoog is, en dat is nu juist waar het plan op stuurt.
            "price_forecast_quarters": _veilig(
                "price_forecast_quarters",
                lambda: [
                    {
                        "start": _iso(start),
                        "end": _iso(einde),
                        "price_per_kwh": round(prijs, 5),
                    }
                    for start, einde, prijs in (
                        coordinator._get_forecast_entries() or []
                    )
                ],
            ),
        },
    }

    if solar_tracker is not None:
        diagnostics["solar_forecast_tracker"] = {
            "enabled": solar_tracker.enabled,
            "last_predicted_kwh": solar_tracker.last_predicted_kwh,
            "last_actual_kwh": solar_tracker.last_actual_kwh,
            "last_deviation_percent": solar_tracker.last_deviation_percent,
            "last_compared_date": _iso(solar_tracker.last_compared_date),
            # v1.20.3: staat de vastlegging van vanavond klaar?
            "next_predicted_kwh": solar_tracker.next_predicted_kwh,
            "next_predicted_date": _iso(solar_tracker.next_predicted_date),
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
    # v1.28.0: ook deze twee liepen buiten de afscherming om. Elke
    # aanroep in deze functie hoort erin te zitten - de export is juist
    # het gereedschap dat je nodig hebt wanneer er iets stuk is.
    diagnostics["pv_forecast_raw"] = _veilig(
        "pv_forecast_raw", lambda: _build_raw_pv_forecast_snapshot(coordinator)
    )
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
        "entities": _veilig(
            "system_scan", lambda: _scan_relevant_entities(hass, already_configured)
        ),
    }

    # v1.19.4, gemeld: de download gaf een "500 Internal Server Error".
    #
    # De afscherming van v1.19.3 ving fouten in de AANROEPEN, maar Home
    # Assistant serialiseert het resultaat pas daarna. Zit er ergens een
    # waarde in die JSON niet aankan - een datum, een set, een object -
    # dan mislukt dat alsnog, en dan krijg je een foutpagina in plaats
    # van een bestand.
    #
    # Dat is niet vooraf uit te sluiten: er gaan meer dan tweehonderd
    # velden doorheen, en één ervan hoeft maar een verkeerd type te
    # hebben. Daarom nu een laatste stap die alles wat JSON niet kent
    # omzet naar tekst. Liever een leesbare tekenreeks dan geen bestand.
    return _json_veilig(diagnostics)


def _json_veilig(waarde: Any) -> Any:
    """Maakt een waarde gegarandeerd serialiseerbaar (v1.19.4).

    Bekende typen blijven zichzelf; al het overige wordt tekst. De
    diagnostiek is het gereedschap dat je nodig hebt WANNEER er iets
    stuk is - dan mag hij niet zelf omvallen op een type dat niemand
    had voorzien.
    """
    if waarde is None or isinstance(waarde, (bool, int, float, str)):
        return waarde
    if isinstance(waarde, (datetime, date)):
        return waarde.isoformat()
    if isinstance(waarde, dict):
        return {str(sleutel): _json_veilig(x) for sleutel, x in waarde.items()}
    if isinstance(waarde, (list, tuple, set)):
        return [_json_veilig(x) for x in waarde]
    return str(waarde)
