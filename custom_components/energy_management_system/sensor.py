"""Sensor entities exposing the Energy Management System coordinator's internal state
(the "debug card") and the Solcast vs. actual PV yield comparison.
"""
from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DEFAULT_NAME,
    DOMAIN,
    LEARNING_HISTORY_DAYS,
    NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT,
    APPLIANCE_RUNNING_POWER_THRESHOLD_W,
    CONF_WATER_ACTIVE_USAGE_SENSOR,
    FIETSLADERS_COMPLETE_THRESHOLD_W,
)

ATTR_PREDICTED_KWH = "predicted_kwh"
ATTR_ACTUAL_KWH = "actual_kwh"
ATTR_COMPARED_DATE = "compared_date"
ATTR_PENDING_PREDICTED_KWH = "pending_predicted_kwh"
ATTR_PENDING_PREDICTED_DATE = "pending_predicted_date"
ATTR_DEVIATION_HISTORY = "deviation_history"
ATTR_LEARNED_BIAS_PERCENT = "learned_bias_percent"
ATTR_FORECAST_VALUE_HISTORY = "forecast_value_history"
ATTR_LEARNED_TYPICAL_FORECAST_KWH = "learned_typical_forecast_kwh"
ATTR_CONSUMPTION_HISTORY = "history_kw"
ATTR_SAMPLE_COUNT = "sample_count"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    tracker = hass.data[DOMAIN][f"{entry.entry_id}_solar_tracker"]

    entities: list[SensorEntity] = [
        CheapestBlockStartSensor(coordinator, entry.entry_id),
        CurrentPricePerKwhSensor(coordinator, entry.entry_id),
        DischargeWindowStartSensor(coordinator, entry.entry_id),
        EffectiveExpensiveQuartersSensor(coordinator, entry.entry_id),
        LastDecisionReasonSensor(coordinator, entry.entry_id),
        SystemStatusSensor(coordinator, entry.entry_id),
        MonthlySummarySensor(coordinator, entry.entry_id),
        ExplanationSensor(coordinator, entry.entry_id),
        SimulatedActionSensor(coordinator, entry.entry_id),
        LearnedNightConsumptionSensor(coordinator, entry.entry_id),
        HourlyConsumptionProfileSensor(coordinator, entry.entry_id),
        PvHourlyBiasSensor(coordinator, entry.entry_id),
        UpcomingTimelineSensor(coordinator, entry.entry_id),
        ExpectedOperationModeSensor(coordinator, entry.entry_id),
        EnergyBridgeCheckSensor(coordinator, entry.entry_id),
        BatteryProtectionSensor(coordinator, entry.entry_id),
        DischargeValueSensor(coordinator, entry.entry_id),
        ChargeCostSensor(coordinator, entry.entry_id),
        BatterySavingsSensor(coordinator, entry.entry_id),
        EnergyBalanceHealthSensor(coordinator, entry.entry_id),
        SluipverbruikSensor(coordinator, entry.entry_id),
        WeatherEnsembleSensor(coordinator, entry.entry_id),
        DishwasherCycleStateSensor(coordinator, entry.entry_id),
        WashingMachineCycleStateSensor(coordinator, entry.entry_id),
        MpcAdvisorySensor(coordinator, entry.entry_id),
        MonteCarloAdvisorySensor(coordinator, entry.entry_id),
        KalmanFilterAdvisorySensor(coordinator, entry.entry_id),
        DigitalTwinAdvisorySensor(coordinator, entry.entry_id),
        NilmUnconfirmedCandidatesSensor(coordinator, entry.entry_id),
        NilmConfirmedDevicesSensor(coordinator, entry.entry_id),
        AdvisoryReadinessSensor(coordinator, entry.entry_id),
        LivingRoomAircoPredictionSensor(coordinator, entry.entry_id),
        ClimateForecastSensor(coordinator, entry.entry_id),
        WaterUsageSensor(coordinator, entry.entry_id),
        ReserveShortfallSensor(coordinator, entry.entry_id),
        ReserveExcessSensor(coordinator, entry.entry_id),
        LearnedBatteryEfficiencySensor(coordinator, entry.entry_id),
        ApplianceUsageHoursSensor(
            coordinator,
            entry.entry_id,
            "dishwasher",
            "Dishwasher typical usage hours",
            "mdi:dishwasher",
        ),
        ApplianceReadyNotificationSensor(
            coordinator,
            entry.entry_id,
            "dishwasher",
            "Dishwasher last notification",
            "mdi:bell-outline",
        ),
        ApplianceUsageHoursSensor(
            coordinator,
            entry.entry_id,
            "washing_machine",
            "Washing machine typical usage hours",
            "mdi:washing-machine",
        ),
        ApplianceReadyNotificationSensor(
            coordinator,
            entry.entry_id,
            "washing_machine",
            "Washing machine last notification",
            "mdi:bell-outline",
        ),
        SteelstofzuigerStatusSensor(coordinator, entry.entry_id),
        FietsladersStatusSensor(coordinator, entry.entry_id),
    ]

    if tracker.enabled:
        entities.append(PvForecastAccuracySensor(tracker, entry.entry_id))

    async_add_entities(entities)


class PvForecastAccuracySensor(SensorEntity, RestoreEntity):
    """Deviation (%) between yesterday's Solcast forecast and today's actual yield."""

    _attr_has_entity_name = True
    _attr_name = "PV forecast accuracy"
    _attr_icon = "mdi:solar-power-variant"
    _attr_native_unit_of_measurement = "%"

    def __init__(self, tracker, entry_id: str) -> None:
        self._tracker = tracker
        self._attr_unique_id = f"{entry_id}_pv_forecast_accuracy"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float | None:
        return self._tracker.last_deviation_percent

    @property
    def extra_state_attributes(self) -> dict:
        return {
            ATTR_PREDICTED_KWH: self._tracker.last_predicted_kwh,
            ATTR_ACTUAL_KWH: self._tracker.last_actual_kwh,
            ATTR_COMPARED_DATE: (
                self._tracker.last_compared_date.isoformat()
                if self._tracker.last_compared_date
                else None
            ),
            ATTR_PENDING_PREDICTED_KWH: self._tracker.pending_predicted_kwh,
            ATTR_PENDING_PREDICTED_DATE: (
                self._tracker.pending_predicted_date.isoformat()
                if self._tracker.pending_predicted_date
                else None
            ),
            ATTR_DEVIATION_HISTORY: self._tracker.deviation_history,
            ATTR_LEARNED_BIAS_PERCENT: self._tracker.learned_bias_percent,
            ATTR_FORECAST_VALUE_HISTORY: self._tracker.forecast_value_history,
            ATTR_LEARNED_TYPICAL_FORECAST_KWH: self._tracker.learned_typical_forecast_kwh,
            "bootstrapped_from_history": self._tracker.was_bootstrapped_from_history,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state is not None:
            attrs = last_state.attributes
            try:
                self._tracker.last_predicted_kwh = _to_float(
                    attrs.get(ATTR_PREDICTED_KWH)
                )
                self._tracker.last_actual_kwh = _to_float(attrs.get(ATTR_ACTUAL_KWH))
                self._tracker.last_deviation_percent = _to_float(last_state.state)
                self._tracker.last_compared_date = _to_date(
                    attrs.get(ATTR_COMPARED_DATE)
                )
                self._tracker.pending_predicted_kwh = _to_float(
                    attrs.get(ATTR_PENDING_PREDICTED_KWH)
                )
                self._tracker.pending_predicted_date = _to_date(
                    attrs.get(ATTR_PENDING_PREDICTED_DATE)
                )
                history = attrs.get(ATTR_DEVIATION_HISTORY)
                if isinstance(history, list):
                    self._tracker.deviation_history = [float(v) for v in history]
                forecast_history = attrs.get(ATTR_FORECAST_VALUE_HISTORY)
                if isinstance(forecast_history, list):
                    self._tracker.forecast_value_history = [
                        float(v) for v in forecast_history
                    ]

                # v0.63.17: last_deviation_percent restores from the
                # sensor's own last STATE STRING, which is "unknown"
                # whenever no comparison had (yet) completed at the
                # moment of the previous shutdown - including the
                # perfectly ordinary case of the very first restart
                # after setup. Restoring "unknown" -> None every time is
                # self-perpetuating: even once deviation_history has real
                # entries from later, successful daily comparisons, this
                # field keeps coming back empty on every subsequent
                # restart, since it never restores FROM deviation_history
                # itself. Fall back to the most recent entry there if the
                # direct restore came up empty, so a single early
                # "unknown" moment doesn't leave the display stuck
                # indefinitely once real data exists.
                if (
                    self._tracker.last_deviation_percent is None
                    and self._tracker.deviation_history
                ):
                    self._tracker.last_deviation_percent = (
                        self._tracker.deviation_history[-1]
                    )
            except (TypeError, ValueError):
                pass

        self._tracker.register_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._tracker.unregister_listener(self.async_write_ha_state)
        await super().async_will_remove_from_hass()


def _to_float(value) -> float | None:
    if value is None or value in ("unknown", "unavailable", ""):
        return None
    return float(value)


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


class _CoordinatorDiagnosticSensor(SensorEntity):
    """Base class for the read-only debug/diagnostic sensors."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str, unique_suffix: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }


class CheapestBlockStartSensor(_CoordinatorDiagnosticSensor):
    """Start of the cheapest upcoming price block, as last calculated.

    The block's width is now detected dynamically (natural valley width),
    see the `end` attribute for where it currently ends.
    """

    _attr_name = "Cheapest block start"
    _attr_icon = "mdi:cash-clock"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "cheapest_block_start")

    @property
    def native_value(self) -> datetime | None:
        return self._coordinator.last_cheap_block_start

    @property
    def extra_state_attributes(self) -> dict:
        end = self._coordinator.last_cheap_block_end
        return {"end": end.isoformat() if end else None}


class CurrentPricePerKwhSensor(_CoordinatorDiagnosticSensor):
    """The price (EUR/kWh) the integration itself last computed for
    'now', straight from the same forecast data used for every decision -
    compare this directly against the price sensor's own live state to
    check they agree (e.g. if you suspect a parsing or timing mismatch).
    """

    _attr_name = "Current price used by integration"
    _attr_icon = "mdi:cash-sync"
    _attr_native_unit_of_measurement = "EUR/kWh"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "current_price_used")

    @property
    def native_value(self) -> float | None:
        value = self._coordinator.last_current_price_per_kwh
        return round(value, 4) if value is not None else None


class DischargeWindowStartSensor(_CoordinatorDiagnosticSensor):
    """Start of tonight's discharging window: the moment today's expensive
    quarters end, running until the cheapest block begins."""

    _attr_name = "Discharge window start"
    _attr_icon = "mdi:battery-arrow-down"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "discharge_window_start")

    @property
    def native_value(self) -> datetime | None:
        return self._coordinator.last_discharge_start


class EffectiveExpensiveQuartersSensor(_CoordinatorDiagnosticSensor):
    """How many expensive quarters are currently used (possibly reduced
    from the configured normal count due to a low solar forecast)."""

    _attr_name = "Effective expensive quarters"
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "effective_expensive_quarters")

    @property
    def native_value(self) -> int | None:
        return self._coordinator.last_effective_expensive_quarters_count


class LastDecisionReasonSensor(_CoordinatorDiagnosticSensor):
    """Why the coordinator picked its most recent mode."""

    _attr_name = "Last decision reason"
    _attr_icon = "mdi:comment-question-outline"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "last_decision_reason")

    @property
    def native_value(self) -> str | None:
        return self._coordinator.last_reason


class SystemStatusSensor(_CoordinatorDiagnosticSensor):
    """A single, simple health status for the integration itself: 'OK'
    if it's actively working, or an explanation of what's wrong
    otherwise - so a problem shows up directly on the dashboard instead
    of only in the Home Assistant logs.
    """

    _attr_name = "System status"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "system_status")

    @property
    def native_value(self) -> str:
        return self._coordinator.system_status

    @property
    def icon(self) -> str:
        status = self._coordinator.system_status
        if status == "OK":
            return "mdi:check-circle-outline"
        if status == "Fout":
            return "mdi:alert-circle-outline"
        return "mdi:help-circle-outline"

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "last_error": self._coordinator.last_error,
            "last_error_time": (
                self._coordinator.last_error_time.isoformat()
                if self._coordinator.last_error_time
                else None
            ),
            "last_successful_update": (
                self._coordinator.last_successful_update.isoformat()
                if self._coordinator.last_successful_update
                else None
            ),
        }


class MonthlySummarySensor(_CoordinatorDiagnosticSensor, RestoreEntity):
    """Genuine month-over-month trend, on top of the existing rolling
    7-day self-correction (which only ever looks at the recent past,
    not whether things are improving release over release).

    State is this month's net result (discharge value minus charge
    cost) so far; attributes carry the full comparison against last
    month.
    """

    _attr_name = "Monthly summary"
    _attr_icon = "mdi:calendar-month-outline"
    _attr_native_unit_of_measurement = "EUR"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "monthly_summary")

    @property
    def native_value(self) -> float:
        net = (
            self._coordinator.current_month_discharge_value_eur
            - self._coordinator.current_month_charge_cost_eur
        )
        return round(net, 2)

    @property
    def extra_state_attributes(self) -> dict:
        c = self._coordinator
        previous_net = None
        if (
            c.previous_month_discharge_value_eur is not None
            and c.previous_month_charge_cost_eur is not None
        ):
            previous_net = round(
                c.previous_month_discharge_value_eur
                - c.previous_month_charge_cost_eur,
                2,
            )
        return {
            "current_month_discharge_value_eur": round(
                c.current_month_discharge_value_eur, 2
            ),
            "current_month_charge_cost_eur": round(
                c.current_month_charge_cost_eur, 2
            ),
            "current_month_shortfall_days": c.current_month_shortfall_days,
            "current_month_excess_days": c.current_month_excess_days,
            "current_month_days_tracked": c.current_month_days_tracked,
            "previous_month_discharge_value_eur": c.previous_month_discharge_value_eur,
            "previous_month_charge_cost_eur": c.previous_month_charge_cost_eur,
            "previous_month_shortfall_days": c.previous_month_shortfall_days,
            "previous_month_excess_days": c.previous_month_excess_days,
            "previous_month_days_tracked": c.previous_month_days_tracked,
            "previous_month_net_eur": previous_net,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        attrs = last_state.attributes
        try:
            c = self._coordinator
            c.current_month_discharge_value_eur = float(
                attrs.get("current_month_discharge_value_eur", 0.0)
            )
            c.current_month_charge_cost_eur = float(
                attrs.get("current_month_charge_cost_eur", 0.0)
            )
            c.current_month_shortfall_days = int(
                attrs.get("current_month_shortfall_days", 0)
            )
            c.current_month_excess_days = int(
                attrs.get("current_month_excess_days", 0)
            )
            c.current_month_days_tracked = int(
                attrs.get("current_month_days_tracked", 0)
            )
            if attrs.get("previous_month_discharge_value_eur") is not None:
                c.previous_month_discharge_value_eur = float(
                    attrs["previous_month_discharge_value_eur"]
                )
            if attrs.get("previous_month_charge_cost_eur") is not None:
                c.previous_month_charge_cost_eur = float(
                    attrs["previous_month_charge_cost_eur"]
                )
            if attrs.get("previous_month_shortfall_days") is not None:
                c.previous_month_shortfall_days = int(
                    attrs["previous_month_shortfall_days"]
                )
            if attrs.get("previous_month_excess_days") is not None:
                c.previous_month_excess_days = int(
                    attrs["previous_month_excess_days"]
                )
            if attrs.get("previous_month_days_tracked") is not None:
                c.previous_month_days_tracked = int(
                    attrs["previous_month_days_tracked"]
                )
        except (TypeError, ValueError):
            pass


class ExplanationSensor(_CoordinatorDiagnosticSensor):
    """Plain-language (Dutch) explanation of what the integration is
    doing right now and why - so you can read in the dashboard what's
    happening without piecing together raw sensor values yourself.

    Home Assistant limits sensor *states* to 255 characters, so the state
    is truncated if needed; the full, untruncated text is always in the
    `explanation` attribute (use that in a markdown card for the complete
    text).
    """

    _attr_name = "Explanation"
    _attr_icon = "mdi:text-box-outline"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "explanation")

    @property
    def native_value(self) -> str | None:
        text = self._coordinator.last_explanation
        if text is None:
            return None
        return text if len(text) <= 255 else text[:252] + "..."

    @property
    def extra_state_attributes(self) -> dict:
        # Crucial values behind the current decision, exposed as their own
        # flat attributes (not just baked into the text) so a markdown
        # card can render a scannable icon summary above the full
        # explanation, instead of the person having to parse the prose or
        # go hunting across several other entities to piece it together.
        return {
            "explanation": self._coordinator.last_explanation,
            "last_successful_update": (
                self._coordinator.last_successful_update.isoformat()
                if self._coordinator.last_successful_update
                else None
            ),
            "force_manual": self._coordinator.force_manual,
            "expected_mode": self._coordinator.last_expected_mode,
            "current_price_per_kwh": self._coordinator.last_current_price_per_kwh,
            "expensive_price_threshold": (
                self._coordinator.last_expensive_price_threshold
            ),
            "secondary_price_threshold": (
                self._coordinator.last_secondary_price_threshold
            ),
            "effective_expensive_quarters_count": (
                self._coordinator.last_effective_expensive_quarters_count
            ),
            "heavy_load_source": self._coordinator.last_heavy_load_source,
        }


class SimulatedActionSensor(_CoordinatorDiagnosticSensor):
    """What the coordinator would have done, while learning_only is on.

    Empty/None when learning_only is off (since commands are actually sent).
    """

    _attr_name = "Simulated action"
    _attr_icon = "mdi:flask-outline"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "simulated_action")

    @property
    def native_value(self) -> str | None:
        return self._coordinator.last_simulated_action


class ExpectedOperationModeSensor(_CoordinatorDiagnosticSensor):
    """What the pure price/solar logic currently wants (smart,
    smart_discharging, or manual) - independent of force_manual or
    learning_only overrides.

    Compare this against the actual Zendure operation select entity in a
    history graph to see when/why they diverge (e.g. during force_manual,
    learning_only, or a manual user override).
    """

    _attr_name = "Expected operation mode"
    _attr_icon = "mdi:brain"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "expected_operation_mode")

    @property
    def native_value(self) -> str | None:
        return self._coordinator.last_expected_mode


class EnergyBridgeCheckSensor(_CoordinatorDiagnosticSensor, RestoreEntity):
    """Does the battery already have enough available energy to bridge
    the remaining time until the cheapest block, so charging can be
    postponed (smart_discharging) instead of letting the Zendure charge
    now (smart)?

    None/unavailable when no available-energy sensor is configured, or
    outside the relevant window (e.g. currently in an expensive quarter,
    or the cheap block has already started).

    Also keeps a log of the last transitions (when the decision flipped),
    so you can review afterwards whether the switch happened at a
    sensible moment - without needing to watch it live.
    """

    _attr_name = "Energy bridge check"
    _attr_icon = "mdi:battery-clock"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "energy_bridge_check")

    @property
    def native_value(self) -> str | None:
        result = self._coordinator.last_has_enough_energy
        if result is None:
            return None
        return "enough_to_postpone" if result else "top_up_needed"

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "available_kwh": self._coordinator.last_available_kwh,
            "needed_kwh": self._coordinator.last_needed_kwh_to_bridge,
            "transition_log": self._coordinator.energy_bridge_transition_log,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            log = last_state.attributes.get("transition_log")
            if isinstance(log, list):
                self._coordinator.energy_bridge_transition_log = log[-50:]


class BatteryProtectionSensor(_CoordinatorDiagnosticSensor):
    """Shows the SoC-based scaling applied to the forced discharge power
    during expensive quarters (taper down to 0 as SoC nears the
    configured minimum, to avoid over-draining the battery).
    """

    _attr_name = "Battery protection"
    _attr_icon = "mdi:battery-heart-variant"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "battery_protection")

    @property
    def native_value(self) -> float | None:
        return self._coordinator.last_discharge_power_applied

    @property
    def extra_state_attributes(self) -> dict:
        return {"soc_percent": self._coordinator.last_soc_percent}


class SteelstofzuigerStatusSensor(_CoordinatorDiagnosticSensor, RestoreEntity):
    """Status of the steelstofzuiger charge-during-cheapest-block control
    (v0.63.12) - None/unavailable if `steelstofzuiger_switch_entity`
    isn't configured.

    RestoreEntity (v0.63.64, gap found while auditing today's changes
    for persistence) - `idle_power_history_w` (the self-learned
    completion threshold's underlying samples, v0.63.46) and
    `duration_history_minutes` (the learned charge duration, pre-
    existing) were both being silently reset to empty on every restart,
    since this sensor previously only extended the non-restoring
    diagnostic base class.
    """

    _attr_name = "Steelstofzuiger status"
    _attr_icon = "mdi:vacuum"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "steelstofzuiger_status")

    @property
    def native_value(self) -> str | None:
        return self._coordinator.last_steelstofzuiger_action

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "duration_history_minutes": (
                self._coordinator.steelstofzuiger_charge_duration_history
            ),
            "learned_duration_minutes": (
                self._coordinator.learned_steelstofzuiger_duration_minutes
            ),
            "idle_power_history_w": (
                self._coordinator._steelstofzuiger_idle_power_history
            ),
            "learned_completion_threshold_w": (
                self._coordinator._get_learned_completion_threshold_w(
                    "_steelstofzuiger_idle_power_history",
                    APPLIANCE_RUNNING_POWER_THRESHOLD_W,
                )
            ),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        idle_history = last_state.attributes.get("idle_power_history_w")
        if isinstance(idle_history, list):
            self._coordinator._steelstofzuiger_idle_power_history = [
                float(v) for v in idle_history
            ]
        duration_history = last_state.attributes.get("duration_history_minutes")
        if isinstance(duration_history, list):
            self._coordinator.steelstofzuiger_charge_duration_history = [
                float(v) for v in duration_history
            ]


class FietsladersStatusSensor(_CoordinatorDiagnosticSensor, RestoreEntity):
    """Mirror of SteelstofzuigerStatusSensor, for the e-bike chargers
    (v0.63.13). RestoreEntity (v0.63.64) - see SteelstofzuigerStatusSensor's
    docstring for why.
    """

    _attr_name = "Fietsladers status"
    _attr_icon = "mdi:bike"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "fietsladers_status")

    @property
    def native_value(self) -> str | None:
        return self._coordinator.last_fietsladers_action

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "duration_history_minutes": (
                self._coordinator.fietsladers_charge_duration_history
            ),
            "learned_duration_minutes": (
                self._coordinator.learned_fietsladers_duration_minutes
            ),
            "idle_power_history_w": (
                self._coordinator._fietsladers_idle_power_history
            ),
            "learned_completion_threshold_w": (
                self._coordinator._get_learned_completion_threshold_w(
                    "_fietsladers_idle_power_history",
                    FIETSLADERS_COMPLETE_THRESHOLD_W,
                )
            ),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        idle_history = last_state.attributes.get("idle_power_history_w")
        if isinstance(idle_history, list):
            self._coordinator._fietsladers_idle_power_history = [
                float(v) for v in idle_history
            ]
        duration_history = last_state.attributes.get("duration_history_minutes")
        if isinstance(duration_history, list):
            self._coordinator.fietsladers_charge_duration_history = [
                float(v) for v in duration_history
            ]


class DischargeValueSensor(SensorEntity, RestoreEntity):
    """Cumulative euro value of energy discharged during expensive
    quarters (energy x price at that exact moment). Persisted across
    restarts.

    Deliberately NOT called "savings", since that would imply a
    counterfactual (what would have happened without this integration)
    that can't be honestly verified. This is the direct monetary value
    of the discharge/export action itself.
    """

    _attr_has_entity_name = True
    _attr_name = "Discharge value (expensive quarters)"
    _attr_icon = "mdi:cash-plus"
    _attr_native_unit_of_measurement = "€"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = "total_increasing"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_discharge_value"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float:
        return round(self._coordinator.total_discharge_value_eur, 4)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            try:
                self._coordinator.total_discharge_value_eur = float(last_state.state)
            except (TypeError, ValueError):
                pass


class ChargeCostSensor(SensorEntity, RestoreEntity):
    """Cumulative euro cost of energy force-charged from the grid during
    a low-solar cheap block (energy x price at that exact moment).
    Persisted across restarts.
    """

    _attr_has_entity_name = True
    _attr_name = "Charge cost (grid charging)"
    _attr_icon = "mdi:cash-minus"
    _attr_native_unit_of_measurement = "€"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = "total_increasing"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_charge_cost"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float:
        return round(self._coordinator.total_charge_cost_eur, 4)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            try:
                self._coordinator.total_charge_cost_eur = float(last_state.state)
            except (TypeError, ValueError):
                pass


class BatterySavingsSensor(SensorEntity, RestoreEntity):
    """Cumulative EUR realised by the battery, using a weighted-average
    cost-basis model (v0.63.24): every kWh that enters the battery is
    valued at the dynamic price at that moment (regardless of source -
    valid under a salderen/net-metering contract, where PV routed into
    the battery instead of exported has the same opportunity cost as
    buying that energy from the grid right then). Every kWh that leaves
    - sold during an expensive quarter, or simply used to cover
    household load and avoid an import - realises the difference between
    today's price and its original cost basis.

    v0.63.25: also includes Zonneplan's fixed EUR/kWh feed-in premium
    (confirmed via web search) for the portion of a discharge that's
    genuine net export to the grid - not the portion that just covers
    household load, which isn't feed-in at all.

    Unlike DischargeValueSensor/ChargeCostSensor above (deliberately NOT
    called "savings", since a counterfactual can't be verified), this one
    genuinely can be called savings: it only uses prices this integration
    actually observed at the moments energy entered and left the
    battery, not a hypothetical "no battery" scenario. Can decrease as
    well as increase (a discharge below cost basis realises a loss), so
    uses `state_class: total` rather than `total_increasing`.
    """

    _attr_has_entity_name = True
    _attr_name = "Battery savings (cost-basis model)"
    _attr_icon = "mdi:piggy-bank-outline"
    _attr_native_unit_of_measurement = "€"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = "total"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_battery_savings"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float:
        return round(self._coordinator.total_battery_savings_eur, 4)

    @property
    def extra_state_attributes(self) -> dict:
        basis = self._coordinator.battery_cost_basis_eur_per_kwh
        return {
            "cost_basis_eur_per_kwh": round(basis, 4) if basis is not None else None,
            "total_feedin_premium_eur": round(
                self._coordinator.total_feedin_premium_eur, 4
            ),
            "note": (
                "Geldig zolang salderen actief is (contract tot en met "
                "2026-12-31) - teruglevering betaalt dan hetzelfde "
                "dynamische tarief als inkoop, dus zon-geladen en "
                "net-geladen energie krijgen dezelfde kostprijs. Bevat "
                "de Zonneplan-terugleverpremie (€0,02/kWh) op het deel "
                "van een ontlading dat echt teruggeleverd wordt (niet "
                "op het deel dat alleen eigen verbruik dekt) - de "
                "aparte 10%-Zonnebonus geldt niet voor accu-teruglevering "
                "en wordt hier dan ook nooit meegerekend."
            ),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        try:
            self._coordinator.total_battery_savings_eur = float(last_state.state)
        except (TypeError, ValueError):
            pass
        basis = last_state.attributes.get("cost_basis_eur_per_kwh")
        if basis is not None:
            try:
                self._coordinator.battery_cost_basis_eur_per_kwh = float(basis)
            except (TypeError, ValueError):
                pass
        premium = last_state.attributes.get("total_feedin_premium_eur")
        if premium is not None:
            try:
                self._coordinator.total_feedin_premium_eur = float(premium)
            except (TypeError, ValueError):
                pass


class EnergyBalanceHealthSensor(SensorEntity):
    """Kirchhoff-style internal-consistency check (v0.63.28): cross-
    checks the battery power sensor against what the available-energy
    sensor's rate of change implies the battery power must be. A
    genuine validation using only sensors already configured - catches
    a stale/unavailable sensor, a wrong entity, a unit mismatch, or a
    sign-convention issue, not a completely new measurement.

    Not a RestoreEntity - this is a live rolling health signal about the
    last ENERGY_BALANCE_ERROR_HISTORY_LENGTH ticks, not a cumulative
    total; restoring stale history from before a restart would be
    actively misleading about *current* sensor health.
    """

    _attr_has_entity_name = True
    _attr_name = "Sensor health score"
    _attr_icon = "mdi:pulse"
    _attr_native_unit_of_measurement = "%"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_sensor_health_score"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float | None:
        return self._coordinator.sensor_health_score

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "measurement_quality": self._coordinator.measurement_quality,
            "last_energy_balance_error_w": (
                self._coordinator.last_energy_balance_error_w
            ),
            "sample_count": len(self._coordinator.energy_balance_error_history),
            "note": (
                "Vergelijkt het batterijvermogen-sensor met wat de "
                "verandering in beschikbare energie impliceert. Een "
                "structurele afwijking is deels verwacht "
                "(laad/ontlaad-rendementsverlies is niet 0) - dit is een "
                "signaal, geen harde foutmelding."
            ),
        }


class SluipverbruikSensor(SensorEntity, RestoreEntity):
    """CUSUM-gebaseerde detectie van een structurele stijging in het
    dagelijkse "vloer"-verbruik (v0.63.29) - de laagste
    gecorrigeerd-verbruik-meting van de dag, waar sluimer-/
    stand-by-verbruik domineert. Een cumulatieve-som-controlekaart
    (CUSUM) vangt een *aanhoudende* afwijking, niet een losse
    uitschieter - precies het soort verschuiving dat het gewone,
    7-dagen-mediaan-lerende uurprofiel juist stilzwijgend als "de nieuwe
    norm" zou opnemen binnen een week.

    Is wel een RestoreEntity (in tegenstelling tot de
    EnergyBalanceHealthSensor) - de onderliggende 30-dagen-geschiedenis
    en CUSUM-accumulator zijn juist bedoeld om over een lange periode
    op te bouwen, dat mag een herstart niet steeds resetten.
    """

    _attr_has_entity_name = True
    _attr_name = "Sluipverbruik-detectie"
    _attr_icon = "mdi:chart-line-variant"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_sluipverbruik"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> str:
        return "gedetecteerd" if self._coordinator.sluipverbruik_detected else "normaal"

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "geschat_verschil_w": self._coordinator.sluipverbruik_estimated_drift_w,
            "referentie_vloerverbruik_w": self._coordinator.sluipverbruik_reference_w,
            "cusum_accumulator_kw": round(self._coordinator.cusum_accumulator_kw, 4),
            "baseline_load_history": self._coordinator.baseline_load_history,
            "dagen_geschiedenis": len(self._coordinator.baseline_load_history),
            "note": (
                "Vergelijkt het laagste dagelijkse verbruik (meestal "
                "diep in de nacht) met een langere-termijn-referentie "
                "(30 dagen). Een geleidelijke stijging die een week "
                "aanhoudt wordt gemeld; losse hoge nachten niet."
            ),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        attrs = last_state.attributes
        try:
            raw_history = attrs.get("baseline_load_history")
            if isinstance(raw_history, list):
                self._coordinator.baseline_load_history = [
                    float(v) for v in raw_history
                ]
            self._coordinator.cusum_accumulator_kw = float(
                attrs.get("cusum_accumulator_kw", 0.0) or 0.0
            )
        except (TypeError, ValueError):
            pass
        self._coordinator.sluipverbruik_detected = last_state.state == "gedetecteerd"


class WeatherEnsembleSensor(SensorEntity):
    """Weather ensemble cross-check (v0.63.30): live cloud_coverage from
    independent weather sources (KNMI/OpenWeatherMap, read from HA
    `weather` entities the person already has - not a new API
    integration), alongside a flag for when live PV output disagrees
    with what those sources say the sky is doing.

    Deliberately not a genuine multi-source kWh yield ensemble - that
    would need panel orientation/tilt/kWp specs this integration doesn't
    collect. Not a RestoreEntity - a live cross-check, not a cumulative
    total.
    """

    _attr_has_entity_name = True
    _attr_name = "Weather ensemble (bewolkingsgraad)"
    _attr_icon = "mdi:weather-partly-cloudy"
    _attr_native_unit_of_measurement = "%"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_weather_ensemble"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float | None:
        return self._coordinator.weather_ensemble_cloud_cover_percent

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "label": self._coordinator.weather_ensemble_label,
            "sources_used": self._coordinator.weather_ensemble_sources_used,
            "disagreement": self._coordinator.weather_ensemble_disagreement,
            "note": (
                "Live bewolkingsgraad van KNMI/OpenWeatherMap, geen "
                "vervangende kWh-opbrengstschatting - daarvoor zijn "
                "paneelgegevens (oriëntatie/hellingshoek/wattpiek) nodig "
                "die deze integratie niet verzamelt. 'disagreement' "
                "vergelijkt live PV-vermogen met de Solcast-voorspelling "
                "voor dit moment, naast wat de bewolkingsgraad zegt."
            ),
        }


class _ApplianceCycleStateSensor(SensorEntity, RestoreEntity):
    """Shared base for the dishwasher/washing-machine RUSTEND/ACTIEF/
    KLAAR state (v0.63.32, "Optie 1" na overleg - geen fase-detectie).
    Restores the learned cycle-duration history across a restart, same
    as the scheduled-charge appliances (v0.63.12).
    """

    _state_attr = ""
    _duration_history_attr = ""
    _learned_duration_property = ""

    def __init__(self, coordinator, entry_id: str, unique_suffix: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> str:
        return getattr(self._coordinator, self._state_attr)

    @property
    def extra_state_attributes(self) -> dict:
        history = getattr(self._coordinator, self._duration_history_attr)
        learned = getattr(self._coordinator, self._learned_duration_property)
        progress_percent = None
        if self.native_value == "actief" and learned:
            started_attr = self._state_attr.replace("_state", "_cycle_started_at")
            started_at = getattr(self._coordinator, started_attr, None)
            if started_at is not None:
                from homeassistant.util import dt as dt_util

                elapsed_min = (dt_util.now() - started_at).total_seconds() / 60
                progress_percent = round(min(100, 100 * elapsed_min / learned), 0)
        return {
            "geleerde_cyclusduur_minuten": (
                round(learned, 1) if learned is not None else None
            ),
            "geschatte_voortgang_procent": progress_percent,
            "cyclusduur_geschiedenis": history,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        raw_history = last_state.attributes.get("cyclusduur_geschiedenis")
        if isinstance(raw_history, list):
            try:
                setattr(
                    self._coordinator,
                    self._duration_history_attr,
                    [float(v) for v in raw_history],
                )
            except (TypeError, ValueError):
                pass
        if last_state.state in ("rustend", "actief", "klaar"):
            setattr(self._coordinator, self._state_attr, last_state.state)


class DishwasherCycleStateSensor(_ApplianceCycleStateSensor):
    """RUSTEND/ACTIEF/KLAAR voor de vaatwasser."""

    _attr_has_entity_name = True
    _attr_name = "Vaatwasser cyclus-status"
    _attr_icon = "mdi:dishwasher"
    _state_attr = "_dishwasher_state"
    _duration_history_attr = "dishwasher_cycle_duration_history"
    _learned_duration_property = "learned_dishwasher_cycle_duration_minutes"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "dishwasher_cycle_state")


class WashingMachineCycleStateSensor(_ApplianceCycleStateSensor):
    """RUSTEND/ACTIEF/KLAAR voor de wasmachine."""

    _attr_has_entity_name = True
    _attr_name = "Wasmachine cyclus-status"
    _attr_icon = "mdi:washing-machine"
    _state_attr = "_washing_machine_state"
    _duration_history_attr = "washing_machine_cycle_duration_history"
    _learned_duration_property = "learned_washing_machine_cycle_duration_minutes"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "washing_machine_cycle_state")


class MpcAdvisorySensor(SensorEntity):
    """MPC (Model Predictive Control) advisory engine (v0.63.33).

    ADVISORY ONLY - never sends a device command, never overrides the
    existing decision tree (confirmed explicitly before building this).
    Shows a projected charge/discharge plan (greedy interval pairing
    over the available price forecast horizon, pure arbitrage - no
    household load/PV/reserve modelling) for comparison only.

    Not a RestoreEntity - a fresh plan is computed every tick from live
    forecast data; a restored stale plan would be actively misleading.
    """

    _attr_has_entity_name = True
    _attr_name = "MPC advies (prijsarbitrage-plan)"
    _attr_icon = "mdi:chart-timeline-variant"
    _attr_native_unit_of_measurement = "€"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_mpc_advisory"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float | None:
        return self._coordinator.mpc_projected_total_profit_eur

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "geplande_acties": self._coordinator.mpc_planned_actions,
            "aantal_kwartieren_in_horizon": (
                self._coordinator.mpc_horizon_quarters_used
            ),
            "laatst_berekend": (
                self._coordinator.mpc_last_computed_at.isoformat()
                if self._coordinator.mpc_last_computed_at
                else None
            ),
            "note": self._coordinator.mpc_note,
        }


class MonteCarloAdvisorySensor(SensorEntity):
    """Monte Carlo advisory engine (v0.63.34).

    ADVISORY ONLY - never sends a device command, never overrides the
    existing deterministic worst-case-deficit calculation or reserve
    margin. Bootstrap-resamples the already-collected empirical history
    (hourly_consumption_profile, pv_hourly_bias_history) to run 1000
    randomised trajectories of the same hour-by-hour "diepste tekort"
    walk, producing a probability distribution for comparison.

    Not a RestoreEntity - a fresh batch of simulations is run every
    tick from live forecast/history data; a restored stale distribution
    would be actively misleading.
    """

    _attr_has_entity_name = True
    _attr_name = "Monte Carlo risico (tekortkans)"
    _attr_icon = "mdi:dice-multiple-outline"
    _attr_native_unit_of_measurement = "%"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_monte_carlo_advisory"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float | None:
        return self._coordinator.monte_carlo_shortfall_probability_percent

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "mediaan_diepste_tekort_kwh": (
                self._coordinator.monte_carlo_median_deficit_kwh
            ),
            "p90_diepste_tekort_kwh": self._coordinator.monte_carlo_p90_deficit_kwh,
            "p10_diepste_tekort_kwh": self._coordinator.monte_carlo_p10_deficit_kwh,
            "aantal_simulaties": self._coordinator.monte_carlo_simulations_run,
            "uren_gesimuleerd": self._coordinator.monte_carlo_hours_simulated,
            "note": self._coordinator.monte_carlo_note,
        }


class KalmanFilterAdvisorySensor(SensorEntity):
    """Kalman filtering advisory engine (v0.63.35).

    ADVISORY ONLY - a smoothed estimate of three live, naturally noisy
    signals (available_kwh/SoC, live PV power, live household load)
    shown alongside their raw sensor readings, never fed into any
    decision (which keep using their own already-tested smoothing).

    Not a RestoreEntity - each filter's internal state (estimate,
    uncertainty) already persists naturally in the coordinator instance
    across ticks; restoring it across a full HA restart would resume
    filtering from a stale point rather than cleanly re-seeding from the
    next live reading, and the smoothing converges again within a few
    ticks regardless.
    """

    _attr_has_entity_name = True
    _attr_name = "Kalman filtering (SoC/PV/verbruik)"
    _attr_icon = "mdi:chart-bell-curve-cumulative"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_kalman_filtering"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> str:
        return (
            "actief"
            if self._coordinator.kalman_soc_filtered_kwh is not None
            or self._coordinator.kalman_pv_filtered_w is not None
            or self._coordinator.kalman_load_filtered_w is not None
            else "geen data"
        )

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "soc_gefilterd_kwh": self._coordinator.kalman_soc_filtered_kwh,
            "soc_ruw_kwh": self._coordinator.kalman_soc_raw_kwh,
            "pv_gefilterd_w": self._coordinator.kalman_pv_filtered_w,
            "pv_ruw_w": self._coordinator.kalman_pv_raw_w,
            "verbruik_gefilterd_w": self._coordinator.kalman_load_filtered_w,
            "verbruik_ruw_w": self._coordinator.kalman_load_raw_w,
            "note": (
                "Adviserend - een gladgestreken schatting naast de "
                "ruwe sensorwaarde, nooit meegenomen in enige "
                "beslissing (die gebruiken hun eigen, al beproefde "
                "gladstrijkmethode). Proces-/meetruis-parameters zijn "
                "onderbouwde standaardwaarden, niet empirisch bepaald "
                "voor deze specifieke installatie."
            ),
        }


class DigitalTwinAdvisorySensor(SensorEntity):
    """Digital Twin advisory engine (v0.63.36).

    ADVISORY ONLY - simulates forward what the *existing* rule-based
    logic (via self.last_timeline, already computed for the "Overzicht
    komende uren" dashboard table) would do to the SoC/financial
    outcome. Never sends a device command, never overrides the real
    decision tree it's modelling. Natural comparison point: MPC's
    theoretical-optimum plan (v0.63.33) vs. this twin's projection of
    what current rule-based behaviour would actually achieve.

    Not a RestoreEntity - a fresh simulation is run every tick from the
    live timeline; a restored stale trajectory would be actively
    misleading.
    """

    _attr_has_entity_name = True
    _attr_name = "Digital Twin (gesimuleerde SoC/winst)"
    _attr_icon = "mdi:cube-outline"
    _attr_native_unit_of_measurement = "€"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_digital_twin"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float | None:
        return self._coordinator.digital_twin_projected_profit_eur

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "gesimuleerd_eind_soc_kwh": self._coordinator.digital_twin_final_soc_kwh,
            "uren_gesimuleerd": self._coordinator.digital_twin_hours_simulated,
            "traject": self._coordinator.digital_twin_trajectory,
            "note": self._coordinator.digital_twin_note,
        }


class NilmUnconfirmedCandidatesSensor(SensorEntity):
    """NILM-like device auto-discovery: unconfirmed candidates
    (v0.63.39).

    NOT genuine NILM - discovers *existing* power-measuring sensor
    entities in Home Assistant that aren't already tracked elsewhere in
    this integration. Requires explicit confirmation via the
    `energy_management_system.confirm_nilm_device` /
    `reject_nilm_device` services before any drift-detection tracking
    begins - purely informational, never influences any battery
    decision.

    Not a RestoreEntity - candidates are rediscovered fresh every tick;
    a candidate that's meanwhile been confirmed/rejected should
    disappear from this list immediately, not linger from a restored
    stale state.
    """

    _attr_has_entity_name = True
    _attr_name = "NILM onbevestigde kandidaten"
    _attr_icon = "mdi:magnify-scan"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_nilm_unconfirmed"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> int:
        return len(self._coordinator.nilm_unconfirmed_candidates)

    @property
    def extra_state_attributes(self) -> dict:
        """Bounded preview (v0.63.45) - the raw full dict can exceed
        Home Assistant's 16KB per-attribute recorder limit with the
        broad discovery scope (reported), which silently drops the
        attribute entirely rather than truncating it. Shows the first
        NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT candidates (sorted
        alphabetically, same order as the dashboard slots), plus the
        true total count and a pointer to diagnostics for the rest -
        the discovery/confirm/reject logic itself isn't limited by
        this, only what this one sensor's attribute exposes.
        """
        all_candidates = self._coordinator.nilm_unconfirmed_candidates
        preview_ids = sorted(all_candidates.keys())[
            :NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT
        ]
        preview = {eid: all_candidates[eid] for eid in preview_ids}
        truncated = len(all_candidates) > len(preview)
        return {
            "kandidaten": preview,
            "totaal_aantal": len(all_candidates),
            "note": (
                "Bevestig een kandidaat met de service "
                "energy_management_system.confirm_nilm_device "
                "(entity_id als parameter), of negeer 'm permanent met "
                "energy_management_system.reject_nilm_device."
                + (
                    f" Dit attribuut toont een voorbeeld van de eerste "
                    f"{NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT} (van "
                    f"{len(all_candidates)} totaal) - de volledige lijst "
                    f"staat in de diagnostiek-export (Instellingen → "
                    f"Apparaten → Energy Management System → "
                    f"Diagnostische gegevens downloaden)."
                    if truncated
                    else ""
                )
            ),
        }


class NilmConfirmedDevicesSensor(SensorEntity, RestoreEntity):
    """NILM-like device auto-discovery: confirmed devices, with per-
    device CUSUM drift-detection (v0.63.39) - same principle as the
    household sluipverbruik detector (v0.63.29), but per device and
    percentage-based (device power levels vary too much for one fixed
    Watt threshold). Purely informational, never influences any
    battery decision.

    v0.63.66, reported: "State attributes ... exceed maximum size of
    16384 bytes" - with enough confirmed devices (each with its own
    learned CUSUM history, plus the v0.63.51 `tabel` attribute), this
    grew past the recorder's per-entity attribute limit. Unlike the
    unconfirmed-candidates preview (v0.63.45), this data can't just be
    truncated in the entity's own restored state without losing real,
    months-in-the-making data - so persistence now goes through a
    dedicated Store (`coordinator._nilm_confirmed_devices_store`, a
    JSON file under .storage/, entirely separate from the recorder's
    size-limited state-history database) instead. The bounded preview
    below is now purely cosmetic (avoids the recorder warning and a
    huge history entry) - it no longer has to carry the full data for
    restore purposes.

    Still a RestoreEntity, but only as a one-time migration path for
    installs upgrading from before the Store existed - see
    `async_added_to_hass`.
    """

    _attr_has_entity_name = True
    _attr_name = "NILM bevestigde apparaten"
    _attr_icon = "mdi:devices"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_nilm_confirmed"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> int:
        return len(self._coordinator.nilm_confirmed_devices)

    @property
    def extra_state_attributes(self) -> dict:
        all_devices = self._coordinator.nilm_confirmed_devices
        preview_ids = sorted(
            all_devices.keys(),
            key=lambda eid: all_devices[eid].get("friendly_name") or eid,
        )[:NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT]
        preview = {eid: all_devices[eid] for eid in preview_ids}
        truncated = len(all_devices) > len(preview)

        anomalies = [
            data["friendly_name"]
            for data in all_devices.values()
            if data.get("anomaly_detected")
        ][:NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT]

        tabel = self._coordinator.get_nilm_devices_table()

        return {
            "apparaten": preview,
            "tabel": tabel[:NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT],
            "mogelijke_defecten": anomalies,
            "rejected_entities": self._coordinator.nilm_rejected_entities[
                :NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT
            ],
            "totaal_aantal": len(all_devices),
            "note": (
                "De volledige, opgeslagen apparatenlijst leeft in een "
                "aparte Store (niet in dit attribuut) en gaat nooit "
                "verloren bij een herstart, ongeacht wat hieronder wordt "
                "getoond."
                + (
                    f" Dit attribuut toont slechts een voorbeeld van de "
                    f"eerste {NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT} (van "
                    f"{len(all_devices)} totaal) - de volledige lijst "
                    f"staat in de diagnostiek-export (Instellingen → "
                    f"Apparaten → Energy Management System → "
                    f"Diagnostische gegevens downloaden)."
                    if truncated
                    else ""
                )
            ),
        }

    async def async_added_to_hass(self) -> None:
        """One-time migration path (v0.63.66) for installs upgrading
        from before the dedicated Store existed. The Store is loaded
        much earlier, during `coordinator.async_setup()` - by the time
        this runs, `nilm_confirmed_devices` is already populated from it
        if it had anything. Only falls back to this entity's own
        restored HA state if the Store was genuinely empty, then
        immediately persists that into the Store so this fallback is
        never needed again on a subsequent restart.
        """
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            if not self._coordinator.nilm_confirmed_devices:
                raw_devices = last_state.attributes.get("apparaten")
                if isinstance(raw_devices, dict) and raw_devices:
                    self._coordinator.nilm_confirmed_devices = dict(raw_devices)
            if not self._coordinator.nilm_rejected_entities:
                raw_rejected = last_state.attributes.get("rejected_entities")
                if isinstance(raw_rejected, list) and raw_rejected:
                    self._coordinator.nilm_rejected_entities = list(raw_rejected)
        await self._coordinator._async_save_nilm_confirmed_devices_store()


class AdvisoryReadinessSensor(SensorEntity):
    """Readiness assessment for the eight advisory-only modules
    (Kirchhoff, sluipverbruik, Weather Ensemble, MPC, Monte Carlo,
    Kalman, Digital Twin, NILM) - v0.63.40, reported: "kunnen we een
    advies afgeven wanneer betrouwbaar genoeg om er werkelijk iets mee
    te doen?"

    Deliberate honesty distinction: modules with a genuine data-
    maturity signal get a real readiness status
    ("klaar"/"bijna_klaar"/"onvoldoende_data"/"kwaliteit_te_laag").
    Modules with no mechanism comparing past predictions to what
    actually happened (Weather Ensemble, MPC, Digital Twin) get
    "structureel_beschikbaar" instead - never a false claim of proven
    accuracy this integration hasn't earned.

    Not a RestoreEntity - recomputed fresh every tick from live state.
    """

    _attr_has_entity_name = True
    _attr_name = "Advies-gereedheid (8 modules)"
    _attr_icon = "mdi:clipboard-check-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_advisory_readiness"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> int:
        return sum(
            1
            for m in self._coordinator.advisory_readiness.values()
            if m.get("status") == "klaar"
        )

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "modules": self._coordinator.advisory_readiness,
            "note": (
                "'klaar' = genoeg data verzameld om de uitkomst te "
                "vertrouwen. 'structureel_beschikbaar' = werkt, maar er "
                "is geen mechanisme dat de voorspelling ooit tegen de "
                "werkelijkheid legt - géén bewezen nauwkeurigheid, dus "
                "bewust nooit als 'klaar' gelabeld."
            ),
        }


class LivingRoomAircoPredictionSensor(SensorEntity, RestoreEntity):
    """Living-room-temperature airco activation predictor (v0.63.55,
    requested: "verwacht wanneer ik de airco aanzet").

    Genuine anticipation, not just "is the airco on right now" - uses
    the same "queue an observation, confirm it later" technique as the
    PV-forecast-accuracy tracker. Each living-room temperature reading
    is bucketed (1°C bins) and, 60 minutes later, confirmed True/False
    depending on whether the airco was seen active at any point during
    that window - learned per bucket, over a short rolling window (not
    a long/seasonal one), since spring/autumn conditions can swing day
    to day.

    Is a RestoreEntity - the learned per-bucket history is meant to
    build up over weeks, a restart shouldn't reset that.
    """

    _attr_has_entity_name = True
    _attr_name = "Airco-verwachting (woonkamertemperatuur)"
    _attr_icon = "mdi:thermometer-lines"
    _attr_native_unit_of_measurement = "°C"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_living_room_airco_prediction"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float | None:
        return self._coordinator.living_room_current_temp_c

    @property
    def extra_state_attributes(self) -> dict:
        temp_c = self._coordinator.living_room_current_temp_c
        bucket_key = None
        current = {
            "bucket": None,
            "sample_count": 0,
            "probability_percent": None,
            "gemiddelde_luchtvochtigheid_percent": None,
            "voldoende_data": False,
        }
        if temp_c is not None:
            from .const import LIVING_ROOM_TEMP_BUCKET_SIZE_C

            bucket_key = str(
                round(temp_c / LIVING_ROOM_TEMP_BUCKET_SIZE_C)
                * LIVING_ROOM_TEMP_BUCKET_SIZE_C
            )
            current = self._coordinator.get_airco_activation_probability(bucket_key)
        return {
            "huidige_luchtvochtigheid_percent": (
                self._coordinator.living_room_current_humidity_percent
            ),
            "huidige_bucket": bucket_key,
            "kans_airco_binnen_1_uur_procent": current["probability_percent"],
            "aantal_metingen_deze_bucket": current["sample_count"],
            "voldoende_data": current["voldoende_data"],
            "alle_buckets": self._coordinator.living_room_temp_bucket_history,
            "note": (
                "Bij de huidige woonkamertemperatuur: hoe vaak is de "
                "airco historisch binnen het uur na een meting op deze "
                "temperatuur aangeslagen? Kort, glijdend venster per "
                "bucket (niet seizoensgebonden) - reageert dus snel op "
                "veranderend weer in lente/herfst. Puur informatief, "
                "stuurt nooit iets aan."
            ),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        raw_buckets = last_state.attributes.get("alle_buckets")
        if isinstance(raw_buckets, dict):
            self._coordinator.living_room_temp_bucket_history = {
                str(k): [bool(v) for v in vals]
                for k, vals in raw_buckets.items()
            }


class ClimateForecastSensor(SensorEntity, RestoreEntity):
    """Klimaat-tabblad: geleerde woonkamertemperatuur-projectie
    (v0.63.56/.57/.58, requested).

    Leert de verandersnelheid (°C/uur) van de woonkamertemperatuur per
    combinatie van buitentemperatuur-bucket x rolluikstand x
    airco-status (bewust zonder bewolking als aparte dimensie - te veel
    cellen). Projecteert 24 uur vooruit met de KNMI/OpenWeatherMap-
    buitentemperatuur-voorspelling, in twee parallelle reeksen:
    "kort_termijn" (indicatief, al vanaf 5 samples per cel) en
    "betrouwbaar" (pas vanaf 15 samples) - allebei bevriezen op het
    voorgaande uur zolang hun eigen drempel niet is gehaald.

    De projectie wordt elke tick opnieuw verankerd aan de actueel
    gemeten temperatuur (v0.63.58) - alleen het ophalen van de
    buitentemperatuur-voorspelling zelf is (om prestatieredenen)
    begrensd tot eens per 30 minuten.

    Puur informatief, stuurt nooit een commando. Wél een RestoreEntity
    - het geleerde snelheidsmodel per cel moet weken kunnen opbouwen,
    dat mag een herstart niet resetten.
    """

    _attr_has_entity_name = True
    _attr_name = "Klimaat-projectie (woonkamertemperatuur)"
    _attr_icon = "mdi:home-thermometer-outline"
    _attr_native_unit_of_measurement = "°C"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_climate_forecast"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float | None:
        return self._coordinator.living_room_current_temp_c

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "buitentemperatuur_live_c": self._coordinator.climate_live_outdoor_temp_c,
            "rolluikstand": self._coordinator.climate_shutter_state,
            "airco_status": self._coordinator.climate_airco_state,
            "traject": self._coordinator.climate_forecast_trajectory,
            "geleerde_cellen": self._coordinator.climate_rate_history,
            "note": self._coordinator.climate_forecast_note,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        raw_cells = last_state.attributes.get("geleerde_cellen")
        if isinstance(raw_cells, dict):
            self._coordinator.climate_rate_history = {
                str(k): [float(v) for v in vals] for k, vals in raw_cells.items()
            }


class WaterUsageSensor(SensorEntity, RestoreEntity):
    """Water-tabblad (v0.63.85, gevraagd: "Meldingen/tracking zoals bij
    vaatwasser/wasmachine" - herzien naar "geen meldingen alleen een
    watertabblad met relevante info"). Puur informatief, stuurt nooit
    iets aan en beïnvloedt de accu-beslissing op geen enkele manier.

    Toont het huidige debiet (live) als state, en als attributen: het
    dagelijkse totaal, een geschiedenis van eerdere dagen (voor trend),
    en een lijst van recente, losse gebruiksmomenten (start, duur,
    geschat volume) - inclusief bijvoorbeeld de nachtelijke
    waterontharder-regeneratie (herkenbaar aan tijdstip, v0.63.86 - zie
    `_update_water_tracking`'s docstring). Het tijdstip van de laatst
    herkende regeneratie is apart als attribuut beschikbaar, zodat het
    dashboard eenvoudig kan tonen wanneer en hoe lang geleden dat was
    (via HA's eigen `relative_time()`-functie).

    Wél een RestoreEntity - de dag-geschiedenis en recente
    gebruiksmomenten moeten een herstart overleven, net als de andere
    leer-/trackinggeschiedenissen in deze integratie.
    """

    _attr_has_entity_name = True
    _attr_name = "Waterverbruik"
    _attr_icon = "mdi:water"
    _attr_native_unit_of_measurement = "L/min"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_water_usage"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float | None:
        active_entity = self._coordinator.config.get(CONF_WATER_ACTIVE_USAGE_SENSOR)
        if not active_entity:
            return None
        return self._coordinator._read_sensor_float(active_entity)

    @property
    def extra_state_attributes(self) -> dict:
        history = self._coordinator.water_daily_history
        gemiddeld_l = round(statistics.median(history), 1) if history else None
        vandaag_l = self._coordinator.water_daily_total_l
        trend = None
        if vandaag_l is not None and gemiddeld_l is not None and gemiddeld_l > 0:
            trend = round(100 * (vandaag_l - gemiddeld_l) / gemiddeld_l, 1)
        last_regen = self._coordinator.water_softener_last_regeneration
        return {
            "vandaag_liter": vandaag_l,
            "gemiddeld_liter_per_dag": gemiddeld_l,
            "trend_procent": trend,
            "geschiedenis_liter_per_dag": history,
            "recente_gebruiksmomenten": list(
                reversed(self._coordinator.water_session_history)
            ),
            "waterontharder_laatste_regeneratie": (
                last_regen.isoformat() if last_regen is not None else None
            ),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        raw_history = last_state.attributes.get("geschiedenis_liter_per_dag")
        if isinstance(raw_history, list):
            self._coordinator.water_daily_history = [float(v) for v in raw_history]
        raw_sessions = last_state.attributes.get("recente_gebruiksmomenten")
        if isinstance(raw_sessions, list):
            self._coordinator.water_session_history = list(reversed(raw_sessions))
        raw_vandaag = last_state.attributes.get("vandaag_liter")
        if raw_vandaag is not None:
            self._coordinator.water_daily_total_l = float(raw_vandaag)
        raw_regen = last_state.attributes.get("waterontharder_laatste_regeneratie")
        if raw_regen:
            try:
                self._coordinator.water_softener_last_regeneration = (
                    datetime.fromisoformat(raw_regen)
                )
            except (TypeError, ValueError):
                pass


class ReserveShortfallSensor(SensorEntity, RestoreEntity):
    """Tracks days where unexpected grid import happened during a period
    the integration believed should be self-sufficient (smart_discharging
    or an expensive-quarter discharge) - meaning the dynamic discharge
    reserve estimate for that day was too optimistic.

    State is the count of shortfall days in the last LEARNING_HISTORY_DAYS
    (used to self-correct the reserve margin - see
    `_get_dynamic_discharge_reserve_kwh`); the `history` attribute shows
    the raw True/False per day. Persisted across restarts.
    """

    _attr_has_entity_name = True
    _attr_name = "Reserve shortfall days"
    _attr_icon = "mdi:battery-alert-variant-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_reserve_shortfall"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> int:
        return sum(1 for v in self._coordinator.reserve_shortfall_history if v)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "history": self._coordinator.reserve_shortfall_history,
            "history_dates": self._coordinator.reserve_shortfall_dates,
            "detected_today_so_far": self._coordinator._shortfall_detected_today,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        raw_history = last_state.attributes.get("history")
        if isinstance(raw_history, list):
            self._coordinator.reserve_shortfall_history = [
                bool(v) for v in raw_history
            ]
        raw_dates = last_state.attributes.get("history_dates")
        if isinstance(raw_dates, list):
            self._coordinator.reserve_shortfall_dates = [str(v) for v in raw_dates]


class ReserveExcessSensor(SensorEntity, RestoreEntity):
    """Mirror of ReserveShortfallSensor: tracks days where the dynamic
    discharge reserve was overly conservative (available energy stayed
    far above what was actually needed while still postponing charging).

    Without this counterbalance, the learned reserve margin could only
    ever increase over time (from shortfall days) and get stuck too
    cautious, missing out on legitimate selling opportunities. Persisted
    across restarts.
    """

    _attr_has_entity_name = True
    _attr_name = "Reserve excess days"
    _attr_icon = "mdi:battery-high"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_reserve_excess"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> int:
        return sum(1 for v in self._coordinator.reserve_excess_history if v)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "history": self._coordinator.reserve_excess_history,
            "history_dates": self._coordinator.reserve_excess_dates,
            "detected_today_so_far": self._coordinator._excess_detected_today,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        raw_history = last_state.attributes.get("history")
        if isinstance(raw_history, list):
            self._coordinator.reserve_excess_history = [
                bool(v) for v in raw_history
            ]
        raw_dates = last_state.attributes.get("history_dates")
        if isinstance(raw_dates, list):
            self._coordinator.reserve_excess_dates = [str(v) for v in raw_dates]


class LearnedBatteryEfficiencySensor(SensorEntity, RestoreEntity):
    """Self-learned battery round-trip efficiency (%), derived from
    actual charge/discharge energy plus the real change in available
    energy - instead of relying solely on the configured guess.

    State is the average of recent samples (used automatically in the PV
    offset calculation once enough samples exist - see
    `learned_battery_efficiency_percent`); the `history` attribute shows
    each individual sample. Persisted across restarts.
    """

    _attr_has_entity_name = True
    _attr_name = "Learned battery efficiency"
    _attr_icon = "mdi:battery-sync"
    _attr_native_unit_of_measurement = "%"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_learned_battery_efficiency"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float | None:
        value = self._coordinator.learned_battery_efficiency_percent
        return round(value, 1) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict:
        return {"history": self._coordinator.learned_efficiency_history}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        raw_history = last_state.attributes.get("history")
        if isinstance(raw_history, list):
            try:
                self._coordinator.learned_efficiency_history = [
                    float(v) for v in raw_history
                ]
            except (TypeError, ValueError):
                pass


class ApplianceUsageHoursSensor(SensorEntity, RestoreEntity):
    """Informational only: the hours of the day this appliance is
    typically active, learned from its power sensor. Never used to
    control anything - purely so you (or a future automation) can see
    the pattern."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator, entry_id: str, appliance_key: str, name: str, icon: str
    ) -> None:
        self._coordinator = coordinator
        self._appliance_key = appliance_key
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{entry_id}_{appliance_key}_usage_hours"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    def _history(self) -> dict:
        return getattr(
            self._coordinator, f"{self._appliance_key}_usage_hourly_history"
        )

    @property
    def native_value(self) -> int:
        return len(self._coordinator.learned_appliance_usage_hours(self._history()))

    @property
    def extra_state_attributes(self) -> dict:
        # Store a compact per-hour average for persistence, not the raw
        # sample lists (which can grow to hundreds of samples per hour -
        # easily exceeding the recorder's 16KB attribute limit, the exact
        # issue fixed for the schedule sensor in v0.40.2).
        history = self._history()
        compact_averages = {
            str(hour): round(sum(samples) / len(samples), 3)
            for hour, samples in history.items()
            if samples
        }
        return {
            "typical_hours": self._coordinator.learned_appliance_usage_hours(history),
            "hours_with_data": len(history),
            "hourly_averages": compact_averages,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        compact_averages = last_state.attributes.get("hourly_averages")
        if isinstance(compact_averages, dict):
            try:
                # Restore as a single representative sample per hour -
                # loses fine-grained history but keeps the learned
                # pattern intact after a restart, within a tiny footprint.
                restored = {
                    int(hour): [float(avg)] for hour, avg in compact_averages.items()
                }
                setattr(
                    self._coordinator,
                    f"{self._appliance_key}_usage_hourly_history",
                    restored,
                )
            except (TypeError, ValueError):
                pass


class ApplianceReadyNotificationSensor(SensorEntity):
    """Informational only: the most recent 'ready to start during the
    cheapest block' notification for this appliance, if any today."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator, entry_id: str, appliance_key: str, name: str, icon: str
    ) -> None:
        self._coordinator = coordinator
        self._appliance_key = appliance_key
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{entry_id}_{appliance_key}_last_notification"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> str:
        value = getattr(
            self._coordinator, f"last_{self._appliance_key}_notification"
        )
        return value or "Geen"


class LearnedNightConsumptionSensor(SensorEntity, RestoreEntity):
    """Rolling average power (kW) measured during past discharging windows.

    This is also where the learned history is persisted across Home
    Assistant restarts.
    """

    _attr_has_entity_name = True
    _attr_name = "Learned night consumption"
    _attr_icon = "mdi:chart-line"
    _attr_native_unit_of_measurement = "W"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_learned_night_consumption"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float | None:
        # Stored/learned internally in kW (used for kWh math elsewhere);
        # displayed in W for readability.
        value = self._coordinator.learned_night_consumption_kw
        return round(value * 1000) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict:
        return {
            ATTR_CONSUMPTION_HISTORY: [
                round(v, 3) for v in self._coordinator.night_consumption_history
            ],
            ATTR_SAMPLE_COUNT: len(self._coordinator.night_consumption_history),
            "bootstrapped_from_history": self._coordinator.was_bootstrapped_from_history,
            "first_seen_date": (
                self._coordinator.first_seen_date.isoformat()
                if self._coordinator.first_seen_date
                else None
            ),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            history = last_state.attributes.get(ATTR_CONSUMPTION_HISTORY)
            if isinstance(history, list):
                try:
                    self._coordinator.night_consumption_history = [
                        float(v) for v in history
                    ][-LEARNING_HISTORY_DAYS:]
                except (TypeError, ValueError):
                    pass
            first_seen_raw = last_state.attributes.get("first_seen_date")
            if first_seen_raw:
                try:
                    self._coordinator.first_seen_date = date.fromisoformat(
                        first_seen_raw
                    )
                except (TypeError, ValueError):
                    pass


class HourlyConsumptionProfileSensor(SensorEntity, RestoreEntity):
    """Learned average power (kW) per hour-of-day (0-23), sampled
    continuously all day every day - so seasons with less predictable
    solar (autumn/winter) still get an accurate consumption estimate,
    even when the relevant bridging period extends into daytime hours.

    State is the current hour's learned average; the full profile is in
    the `profile` attribute. Persisted across restarts.
    """

    _attr_has_entity_name = True
    _attr_name = "Hourly consumption profile"
    _attr_icon = "mdi:chart-bell-curve"
    _attr_native_unit_of_measurement = "W"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_hourly_consumption_profile"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float | None:
        # Stored/learned internally in kW (used for kWh math elsewhere);
        # displayed in W for readability.
        current_hour = datetime.now().hour
        value = self._coordinator.learned_hourly_avg_kw(current_hour)
        return round(value * 1000) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict:
        # "profile" stays in kW (used to restore state after a restart -
        # do not change its scale). "profile_watts" is a display-friendly
        # copy in whole Watts for dashboards.
        profile_kw = {
            str(hour): round(self._coordinator.learned_hourly_avg_kw(hour), 3)
            for hour in range(24)
            if self._coordinator.learned_hourly_avg_kw(hour) is not None
        }
        profile_watts = {
            hour: round(value * 1000) for hour, value in profile_kw.items()
        }
        # The average as it was before the most recent sample - lets the
        # dashboard show a "previous vs current" trend for what is
        # otherwise a continuously-updating rolling average.
        previous_profile_watts = {
            str(hour): round(self._coordinator.previous_hourly_avg_kw(hour) * 1000)
            for hour in range(24)
            if self._coordinator.previous_hourly_avg_kw(hour) is not None
        }
        # Full underlying per-day sample lists (v0.60.1) - restoring just
        # the collapsed average after a restart gives previous_hourly_avg_kw
        # nothing genuine to compare against, so the "Verschil" column was
        # showing +0 for every hour right after every restart, only
        # recovering hour-by-hour as each hour-of-day's boundary was next
        # crossed (up to ~24h later). Persisting the raw lists lets the
        # real day-to-day trend survive a restart intact.
        profile_history = {
            str(hour): [round(v, 3) for v in values]
            for hour, values in self._coordinator.hourly_consumption_profile.items()
            if values
        }
        # In-progress (not-yet-finalised) current-hour accumulation
        # (v0.63.16) - without this, every restart discards whatever of
        # the current hour had already been sampled, and a brand new
        # sample only gets appended to profile_history once a FULL,
        # uninterrupted hour elapses. With frequent restarts (e.g.
        # during active development, one update per few minutes), that
        # can mean no new sample ever lands - profile_history stays
        # frozen at whatever it was, so "Verschil" stays +0 indefinitely,
        # not just right after a restart.
        in_progress = {
            "hour": self._coordinator._current_tracked_hour,
            "energy_kwh": round(self._coordinator._hour_energy_kwh, 4),
            "duration_hours": round(self._coordinator._hour_duration_hours, 4),
            "last_sample": (
                self._coordinator._hour_last_sample.isoformat()
                if self._coordinator._hour_last_sample
                else None
            ),
        }
        return {
            "profile": profile_kw,
            "profile_watts": profile_watts,
            "previous_profile_watts": previous_profile_watts,
            "profile_history": profile_history,
            "in_progress": in_progress,
            "hours_with_data": len(profile_kw),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return

        raw_in_progress = last_state.attributes.get("in_progress")
        if isinstance(raw_in_progress, dict) and raw_in_progress.get("hour") is not None:
            try:
                self._coordinator._current_tracked_hour = int(raw_in_progress["hour"])
                self._coordinator._hour_energy_kwh = float(
                    raw_in_progress.get("energy_kwh") or 0.0
                )
                self._coordinator._hour_duration_hours = float(
                    raw_in_progress.get("duration_hours") or 0.0
                )
                last_sample_raw = raw_in_progress.get("last_sample")
                if last_sample_raw:
                    self._coordinator._hour_last_sample = datetime.fromisoformat(
                        last_sample_raw
                    )
            except (TypeError, ValueError):
                pass

        # Prefer the full per-day history (v0.60.1) when present - it
        # restores the genuine trend intact. Falls back to the old
        # single-average duplication for state saved by a pre-v0.60.1
        # version (upgrade path), which only restores a flat "no change
        # yet" starting point.
        raw_history = last_state.attributes.get("profile_history")
        if isinstance(raw_history, dict):
            restored: dict[int, list[float]] = {}
            for hour_str, values in raw_history.items():
                try:
                    hour = int(hour_str)
                    parsed = [float(v) for v in values]
                except (TypeError, ValueError):
                    continue
                if parsed:
                    # v0.63.21: collapse a leading duplicate pair - the
                    # tell-tale signature of the old pre-v0.60.1
                    # duplicate-seed restore (v0.56.1). Two identical
                    # "votes" for the same old value keep outvoting a
                    # single genuine new sample in the median (v0.62.0),
                    # e.g. [x, x, y] medians to x either way - a real,
                    # different y never becomes visible as a "Verschil"
                    # until enough further samples build a majority
                    # against the duplicate. One-time cleanup: [x, x, y]
                    # -> [x, y], so the very next genuine sample already
                    # shows a real trend, same as the original single-
                    # value-seed design intended.
                    if len(parsed) >= 2 and parsed[0] == parsed[1]:
                        parsed = parsed[1:]
                    restored[hour] = parsed[-LEARNING_HISTORY_DAYS:]
            if restored:
                self._coordinator.hourly_consumption_profile = restored
                return

        raw_profile = last_state.attributes.get("profile")
        if not isinstance(raw_profile, dict):
            return
        restored = {}
        for hour_str, avg_value in raw_profile.items():
            try:
                hour = int(hour_str)
                # Store the restored average twice, not once - a single
                # restored value gives previous_hourly_avg_kw nothing to
                # compare against (needs >=2 samples), so the "Verschil"
                # trend column would show "-" for every hour right after
                # every restart until enough new samples came in. Two
                # identical entries mean "previous == current" (shown as
                # "->" no change) immediately, and the very next real
                # sample already produces a genuine trend.
                restored[hour] = [float(avg_value), float(avg_value)]
            except (TypeError, ValueError):
                continue
        if restored:
            self._coordinator.hourly_consumption_profile = restored


class PvHourlyBiasSensor(SensorEntity, RestoreEntity):
    """Learned (actual/forecast) ratio per hour-of-day (0-23) for the
    Solcast PV forecast - more precise than the single flat daily bias,
    since Solcast may e.g. systematically under-forecast mornings but
    over-forecast afternoons for a given installation/orientation.

    State is the current hour's learned ratio (1.0 = forecast matches
    reality); the full profile is in the `profile` attribute. Persisted
    across restarts.
    """

    _attr_has_entity_name = True
    _attr_name = "PV hourly forecast bias"
    _attr_icon = "mdi:weather-partly-cloudy"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_pv_hourly_bias"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float | None:
        current_hour = datetime.now().hour
        value = self._coordinator.learned_pv_hourly_ratio(current_hour)
        return round(value, 3) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict:
        # "profile" is used to restore state after a restart - built from
        # the RAW average (no minimum-sample gate), so partial progress
        # (1-2 samples for an hour) survives a restart instead of being
        # silently discarded. "profile_confident" is the display-friendly
        # version, only showing hours with enough history to be used in
        # actual decisions (see learned_pv_hourly_ratio).
        profile = {
            str(hour): round(self._coordinator.raw_pv_hourly_avg(hour), 3)
            for hour in range(24)
            if self._coordinator.raw_pv_hourly_avg(hour) is not None
        }
        profile_confident = {
            str(hour): round(self._coordinator.learned_pv_hourly_ratio(hour), 3)
            for hour in range(24)
            if self._coordinator.learned_pv_hourly_ratio(hour) is not None
        }
        # The ratio as it was before the most recent sample - lets the
        # dashboard show a "previous vs current" trend, same principle as
        # HourlyConsumptionProfileSensor.previous_profile_watts.
        previous_profile = {
            str(hour): round(self._coordinator.previous_pv_hourly_ratio(hour), 3)
            for hour in range(24)
            if self._coordinator.previous_pv_hourly_ratio(hour) is not None
        }
        return {
            "profile": profile,
            "profile_confident": profile_confident,
            "previous_profile": previous_profile,
            "profile_history": {
                str(hour): [round(v, 3) for v in values]
                for hour, values in self._coordinator.pv_hourly_bias_history.items()
                if values
            },
            "in_progress": {
                "hour": self._coordinator._pv_current_tracked_hour,
                "energy_kwh": round(self._coordinator._pv_hour_energy_kwh, 4),
                "duration_hours": round(
                    self._coordinator._pv_hour_duration_hours, 4
                ),
                "last_sample": (
                    self._coordinator._pv_hour_last_sample.isoformat()
                    if self._coordinator._pv_hour_last_sample
                    else None
                ),
            },
            "hours_with_data": len(profile),
            "hours_with_confident_data": len(profile_confident),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return

        # In-progress current-hour accumulation (v0.63.16) - see
        # HourlyConsumptionProfileSensor for the full rationale.
        raw_in_progress = last_state.attributes.get("in_progress")
        if isinstance(raw_in_progress, dict) and raw_in_progress.get("hour") is not None:
            try:
                self._coordinator._pv_current_tracked_hour = int(
                    raw_in_progress["hour"]
                )
                self._coordinator._pv_hour_energy_kwh = float(
                    raw_in_progress.get("energy_kwh") or 0.0
                )
                self._coordinator._pv_hour_duration_hours = float(
                    raw_in_progress.get("duration_hours") or 0.0
                )
                last_sample_raw = raw_in_progress.get("last_sample")
                if last_sample_raw:
                    self._coordinator._pv_hour_last_sample = datetime.fromisoformat(
                        last_sample_raw
                    )
            except (TypeError, ValueError):
                pass

        # Prefer the full per-day history (v0.60.1) - see
        # HourlyConsumptionProfileSensor for the full rationale. Falls
        # back to the old single-ratio duplication for state saved by a
        # pre-v0.60.1 version.
        raw_history = last_state.attributes.get("profile_history")
        if isinstance(raw_history, dict):
            restored: dict[int, list[float]] = {}
            for hour_str, values in raw_history.items():
                try:
                    hour = int(hour_str)
                    parsed = [float(v) for v in values]
                except (TypeError, ValueError):
                    continue
                if parsed:
                    # v0.63.21: same leading-duplicate cleanup as
                    # HourlyConsumptionProfileSensor - see there for the
                    # full rationale.
                    if len(parsed) >= 2 and parsed[0] == parsed[1]:
                        parsed = parsed[1:]
                    restored[hour] = parsed[-LEARNING_HISTORY_DAYS:]
            if restored:
                self._coordinator.pv_hourly_bias_history = restored
                return

        raw_profile = last_state.attributes.get("profile")
        if not isinstance(raw_profile, dict):
            return
        restored = {}
        for hour_str, ratio_value in raw_profile.items():
            try:
                hour = int(hour_str)
                # Same principle as HourlyConsumptionProfileSensor: store
                # the restored ratio twice so previous_pv_hourly_ratio has
                # something to compare against right after a restart,
                # instead of showing "-" until a new sample comes in.
                restored[hour] = [float(ratio_value), float(ratio_value)]
            except (TypeError, ValueError):
                continue
        if restored:
            self._coordinator.pv_hourly_bias_history = restored


class UpcomingTimelineSensor(_CoordinatorDiagnosticSensor):
    """Table/list of upcoming intervals: time, expected mode, and price.

    Covers everything currently known from the price forecast (typically
    ~24-36 hours ahead, depending on what the price sensor provides). This
    is a projection based on the currently known cheapest block and
    discharge window; see the coordinator's `_build_forecast_timeline` for
    the exact assumptions and limitations.
    """

    _attr_name = "Upcoming schedule"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "upcoming_schedule")

    @property
    def native_value(self) -> int:
        """Number of upcoming intervals in the timeline (state is a count;
        use the 'transitions' attribute for the actual table)."""
        return len(self._coordinator.last_timeline)

    @property
    def extra_state_attributes(self) -> dict:
        # Only the collapsed 'transitions' (one entry per block, not per
        # 15-minute quarter) - the full per-quarter timeline can easily
        # exceed the recorder's 16KB attribute size limit (up to ~192
        # quarters over 48h of forecast data), causing history storage
        # for this entity to silently fail. Nothing else reads
        # 'timeline' (the dashboard only uses 'transitions'), so it's
        # dropped here entirely rather than trimmed.
        return {
            "transitions": self._coordinator.last_transitions,
        }
