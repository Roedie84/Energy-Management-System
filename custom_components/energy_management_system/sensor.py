"""Sensor entities exposing the Energy Management System coordinator's internal state
(the "debug card") and the Solcast vs. actual PV yield comparison.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DEFAULT_NAME, DOMAIN, LEARNING_HISTORY_DAYS

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
        return {"explanation": self._coordinator.last_explanation}


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
        return {
            "profile": profile_kw,
            "profile_watts": profile_watts,
            "previous_profile_watts": previous_profile_watts,
            "hours_with_data": len(profile_kw),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        raw_profile = last_state.attributes.get("profile")
        if not isinstance(raw_profile, dict):
            return
        restored: dict[int, list[float]] = {}
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
            "hours_with_data": len(profile),
            "hours_with_confident_data": len(profile_confident),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        raw_profile = last_state.attributes.get("profile")
        if not isinstance(raw_profile, dict):
            return
        restored: dict[int, list[float]] = {}
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
