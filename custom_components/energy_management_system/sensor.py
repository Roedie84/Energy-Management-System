"""Sensor entities exposing the Energy Management System coordinator's internal state
(the "debug card") and the Solcast vs. actual PV yield comparison.
"""
from __future__ import annotations

import logging

import statistics
from datetime import date, datetime, timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import (
    RELIABILITY_LABELS,
    RELIABILITY_RELIABLE,
    DEFAULT_NAME,
    DOMAIN,
    LEARNING_HISTORY_DAYS,
    NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT,
    APPLIANCE_RUNNING_POWER_THRESHOLD_W,
    CONF_WATER_ACTIVE_USAGE_SENSOR,
    FIETSLADERS_COMPLETE_THRESHOLD_W,
)

_LOGGER = logging.getLogger(__name__)

ATTR_PREDICTED_KWH = "predicted_kwh"
ATTR_ACTUAL_KWH = "actual_kwh"
ATTR_COMPARED_DATE = "compared_date"
ATTR_PENDING_PREDICTED_KWH = "pending_predicted_kwh"
# v1.20.3: de vastlegging van 20:00 wacht hier tot de vergelijking van
# 23:59 klaar is. Zonder bewaren zou een herstart tussen 20:00 en 23:59
# de voorspelling van morgen kwijtraken.
ATTR_NEXT_PREDICTED_KWH = "next_predicted_kwh"
ATTR_NEXT_PREDICTED_DATE = "next_predicted_date"
ATTR_PENDING_PREDICTED_DATE = "pending_predicted_date"
ATTR_DEVIATION_HISTORY = "deviation_history"
ATTR_DEVIATION_STDEV_HISTORY = "deviation_stdev_history"
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
        BatteryCoolingSensor(coordinator, entry.entry_id),
        BatteryModuleHealthSensor(coordinator, entry.entry_id),
        DigitalTwinAccuracySensor(coordinator, entry.entry_id),
        ReliabilityOverviewSensor(coordinator, entry.entry_id),
        GacsAssessmentSensor(coordinator, entry.entry_id),
        PvInstallationProfileSensor(coordinator, entry.entry_id),
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
        PeakPowerSensor(coordinator, entry.entry_id),
        CounterfactualSavingsSensor(coordinator, entry.entry_id),
        SelfSufficiencySensor(coordinator, entry.entry_id),
        SelfConsumptionSensor(coordinator, entry.entry_id),
        BatteryHealthSensor(coordinator, entry.entry_id),
        CO2IntensitySensor(coordinator, entry.entry_id),
        MissingOptionalFeaturesSensor(coordinator, entry.entry_id),
        HouseholdConsumptionSensor(coordinator, entry.entry_id),
        ModelTrendInsightSensor(coordinator, entry.entry_id),
        LiveNarrativeSensor(coordinator, entry.entry_id),
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
            ATTR_NEXT_PREDICTED_KWH: self._tracker.next_predicted_kwh,
            ATTR_NEXT_PREDICTED_DATE: (
                self._tracker.next_predicted_date.isoformat()
                if self._tracker.next_predicted_date
                else None
            ),
            ATTR_PENDING_PREDICTED_DATE: (
                self._tracker.pending_predicted_date.isoformat()
                if self._tracker.pending_predicted_date
                else None
            ),
            ATTR_DEVIATION_HISTORY: self._tracker.deviation_history,
            ATTR_DEVIATION_STDEV_HISTORY: self._tracker.deviation_stdev_history,
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
                self._tracker.next_predicted_kwh = _to_float(
                    attrs.get(ATTR_NEXT_PREDICTED_KWH)
                )
                self._tracker.next_predicted_date = _to_date(
                    attrs.get(ATTR_NEXT_PREDICTED_DATE)
                )
                history = attrs.get(ATTR_DEVIATION_HISTORY)
                if isinstance(history, list):
                    self._tracker.deviation_history = [float(v) for v in history]
                stdev_history = attrs.get(ATTR_DEVIATION_STDEV_HISTORY)
                if isinstance(stdev_history, list):
                    self._tracker.deviation_stdev_history = [
                        float(v) for v in stdev_history
                    ]
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
        if status == "Aandacht gewenst":
            return "mdi:alert-outline"
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
            # v0.63.127, gerapporteerd: "de datum notatie is niet
            # duidelijk" - de ruwe ISO-tijdstempel stond onleesbaar op de
            # grafische kaart. Een state-label kan niet formatteren, dus
            # dat hoort hier te gebeuren.
            "last_successful_update_short": (
                self._coordinator.format_moment_short(
                    self._coordinator.last_successful_update
                )
            ),
            # v0.63.109, gevraagd: "systeem status ok niet klopt
            # eigenlijk kan zien" - de volledige aandachtspunten-lijst
            # rechtstreeks op deze sensor, zodat "Aandacht gewenst" ook
            # meteen laat zien WAT er aandacht verdient, zonder apart
            # naar het Live-tabblad of diagnostiek te hoeven.
            "aandachtspunten": self._coordinator.get_diagnostic_summary()[
                "aandachtspunten"
            ],
            # v0.63.116: observaties die bewust GEEN invloed hebben op
            # de systeemstatus (bijv. waarschijnlijke NILM-duplicaten -
            # een eigenschap van de HA-installatie, niet van deze
            # integratie). Apart attribuut zodat het dashboard ze
            # anders kan tonen dan echte aandachtspunten.
            "informatief": self._coordinator.get_diagnostic_summary()[
                "informatief"
            ],
            # v1.2.0: voor het Meldingen-tabblad.
            # v1.6.3: dertig in plaats van vijftien, en mét het
            # bericht - de titel alleen zegt niet WELKE sensor wegviel.
            "meldingen_historie": self._coordinator.notification_history[-30:],
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
            # v0.63.127: kant-en-klaar geformatteerd, omdat een
            # state-label op de picture-elements-kaart de ruwe waarde
            # toont en niet kan formatteren.
            "last_successful_update_short": (
                self._coordinator.format_moment_short(
                    self._coordinator.last_successful_update
                )
            ),
            "accu_vermogen_weergave": self._coordinator.get_battery_power_display(),
            # v0.63.130: de grootste BEKENDE verbruiker nu. Apart van
            # `heavy_load_source`, dat een beslislogica-signaal is en
            # meestal leeg hoort te zijn.
            "grootste_verbruiker": self._coordinator.get_largest_known_consumer(),
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
    cost-basis model (v0.63.24). Every kWh that enters the battery is
    valued at the cost of its SOURCE, and every kWh that leaves at the
    value of its DESTINATION.

    v0.63.117: source/destination now genuinely matter. Until v0.63.116
    every charged kWh was booked at the plain import price, which was
    only defensible while salderen made feed-in worth exactly the import
    price - and even then it silently ignored the feed-in premium on
    diverted PV, overstating savings. Now: grid-charged energy costs the
    import price, PV surplus costs the forgone feed-in; discharge that
    covers household load is worth the avoided import price, discharge
    that genuinely exports is worth the feed-in tariff. Under salderen
    those collapse back together, so the historical figures stay
    comparable.

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
            # v0.63.117: bron-/bestemmingssplitsing, nodig zodra
            # teruglevering en inkoop niet meer hetzelfde tarief hebben.
            "salderen_actief": self._coordinator.salderen_active,
            "teruglever_waarde_eur_per_kwh": (
                round(self._coordinator.current_feedin_value_eur_per_kwh, 4)
                if self._coordinator.current_feedin_value_eur_per_kwh is not None
                else None
            ),
            "geladen_uit_pv_kwh": round(self._coordinator.charge_pv_kwh_total, 3),
            "geladen_uit_net_kwh": round(self._coordinator.charge_grid_kwh_total, 3),
            "ontladen_naar_net_kwh": round(
                self._coordinator.discharge_export_kwh_total, 3
            ),
            "gederfde_teruglevering_eur": round(
                self._coordinator.forgone_feedin_eur_total, 4
            ),
            "note": (
                "Elke kWh die de accu ingaat krijgt de kostprijs van zijn "
                "BRON: netinkoop de inkoopprijs, PV-overschot de gederfde "
                "teruglevering. Elke kWh die eruit gaat krijgt de waarde "
                "van zijn BESTEMMING: eigen verbruik de vermeden "
                "inkoopprijs, teruglevering het teruglevertarief. Zolang "
                "salderen geldt zijn die twee vrijwel gelijk (inkoop = "
                "teruglevering); daarna loopt het uiteen en wordt "
                "PV-energie opslaan juist voordeliger. Bevat de "
                "Zonneplan-terugleverpremie (€0,02/kWh) op werkelijk "
                "teruggeleverde kWh - de aparte 10%-Zonnebonus geldt niet "
                "voor accu-teruglevering en wordt nooit meegerekend."
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


class WeatherEnsembleSensor(SensorEntity, RestoreEntity):
    """Weather ensemble cross-check (v0.63.30): live cloud_coverage from
    independent weather sources (KNMI/OpenWeatherMap, read from HA
    `weather` entities the person already has - not a new API
    integration), alongside a flag for when live PV output disagrees
    with what those sources say the sky is doing.

    Deliberately not a genuine multi-source kWh yield ensemble - that
    would need panel orientation/tilt/kWp specs this integration doesn't
    collect.

    v1.0.2: WEL een RestoreEntity geworden. De bewolkingsgraad zelf is
    een momentopname, maar de overeenstemmingsgeschiedenis eronder is
    dat niet: er zijn twintig waarnemingen BIJ DAGLICHT nodig voordat er
    een oordeel volgt, en die worden alleen verzameld als de zon schijnt
    en Solcast iets noemenswaardigs verwacht. Zonder herstel zou elke
    herstart die telling terugzetten - dezelfde fout die de
    NILM-persistentie in v0.63.115 zo lang verborgen hield.
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
            # v1.3.0: het kale label ("helder") zei niets over hoeveel
            # waarde je eraan moet hechten. Gerapporteerd bij 25,4%
            # terwijl het buiten dichtbewolkt was: beide bronnen waren
            # het met elkaar eens en allebei oneens met de werkelijkheid.
            "label_met_betrouwbaarheid": (
                self._label_met_betrouwbaarheid()
            ),
            "sources_used": self._coordinator.weather_ensemble_sources_used,
            # v1.1.8: het gemiddelde alleen verbergt een meningsverschil
            # - 0% en 51% geeft hetzelfde cijfer als twee keer 25%.
            "metingen_per_bron": self._coordinator.weather_ensemble_readings,
            "spreiding_percent": (
                self._coordinator.weather_ensemble_spread_percent
            ),
            # v1.5.2: hoe vaak elke bron afzonderlijk klopt met wat de
            # panelen doen. Het gemiddelde meten zegt niets over WELKE
            # bron deugt.
            "betrouwbaarheid_per_bron": (
                self._coordinator.get_weather_source_reliability()
            ),
            "disagreement": self._coordinator.weather_ensemble_disagreement,
            # v1.0.2: hoe vaak deze bronnen het eens blijken met wat de
            # panelen werkelijk doen.
            **self._coordinator.get_weather_ensemble_agreement_status(),
            "overeenstemming_historie": (
                self._coordinator.weather_ensemble_agreement_history
            ),
            "note": (
                "Live bewolkingsgraad van KNMI/OpenWeatherMap, geen "
                "vervangende kWh-opbrengstschatting - daarvoor zijn "
                "paneelgegevens (oriëntatie/hellingshoek/wattpiek) nodig "
                "die deze integratie niet verzamelt. 'disagreement' "
                "vergelijkt live PV-vermogen met de Solcast-voorspelling "
                "voor dit moment, naast wat de bewolkingsgraad zegt. "
                "'overeenstemming_percent' houdt bij hoe vaak die twee het "
                "eens waren - de vraag 'hoe nauwkeurig is de voorspelling' "
                "past hier niet, want dit is een actuele meting en geen "
                "verwachting."
            ),
        }

    def _label_met_betrouwbaarheid(self) -> str | None:
        label = self._coordinator.weather_ensemble_label
        if label is None:
            return None
        status = self._coordinator.get_weather_ensemble_agreement_status()
        percentage = status.get("overeenstemming_percent")
        if percentage is None:
            return f"{label} (betrouwbaarheid nog onbekend)"
        return f"{label} (bronnen kloppen in {percentage:.0f}% van de gevallen)"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        historie = last_state.attributes.get("overeenstemming_historie")
        if isinstance(historie, list) and historie:
            self._coordinator.weather_ensemble_agreement_history = [
                bool(waarde) for waarde in historie
            ]


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
            # v1.0.7: levert filteren hier eigenlijk iets op? "Alle
            # filters geconvergeerd" zei alleen dat de onzekerheid was
            # uitgezakt, niet dat de gefilterde waarde beter is.
            "levert_filteren_iets_op": (
                self._coordinator.get_kalman_divergence_status()
            ),
            "note": (
                "Adviserend - een gladgestreken schatting naast de "
                "ruwe sensorwaarde, nooit meegenomen in enige "
                "beslissing (die gebruiken hun eigen, al beproefde "
                "gladstrijkmethode). Proces-/meetruis-parameters zijn "
                "onderbouwde standaardwaarden, niet empirisch bepaald "
                "voor deze specifieke installatie. "
                "'levert_filteren_iets_op' meet per signaal hoeveel "
                "gefilterd van ruw afwijkt, als percentage van de "
                "signaalgrootte - is dat verwaarloosbaar, dan valt er met "
                "filteren niets te winnen."
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
            # v0.63.118: aantal paren dat de gebruiker al heeft
            # beoordeeld als "geen duplicaat" - zodat zichtbaar is dat
            # een verdwenen suggestie een bewuste keuze was en niet
            # stilletjes wegviel.
            "afgewezen_duplicaatparen": len(
                self._coordinator.nilm_dismissed_duplicate_pairs
            ),
            "waarschijnlijke_duplicaten": self._coordinator.get_nilm_duplicate_pairs(),
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
        before the platforms are set up (v0.63.115) - by the time this
        runs, `nilm_confirmed_devices` is already populated from it if
        it had anything. Only falls back to this entity's own restored
        HA state if the Store was genuinely empty, then immediately
        persists that into the Store so this fallback is never needed
        again on a subsequent restart.

        v0.63.115, gerapporteerd: "keuzes voor NILM apparaten worden
        nog steeds niet opgeslagen, de onbevestigde lijst blijft terug
        komen na een herstart". Deze methode was de plek waar de data
        daadwerkelijk verminkt werd. Drie dingen zijn hier veranderd,
        elk afzonderlijk genoeg om herhaling te voorkomen:

        1. Het migratiepad draait alleen nog als de Store aantoonbaar
           NIETS bevatte (`coordinator.nilm_store_had_data`), niet meer
           als de lijsten in het geheugen "toevallig leeg" zijn - die
           waren namelijk altijd leeg, omdat de platforms vóór de
           Store-load werden opgezet.
        2. Afgewezen entiteiten worden nu SAMENGEVOEGD (union) in
           plaats van vervangen, zodat een afgekapt attribuut nooit
           meer entries kan wégnemen.
        3. Er wordt alleen naar de Store geschreven als de migratie
           daadwerkelijk iets heeft hersteld. Een onvoorwaardelijke
           schrijfactie hier was precies wat de volledige Store
           overschreef met een kopie van maximaal
           NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT (20) items.
        """
        await super().async_added_to_hass()
        if self._coordinator.nilm_store_had_data:
            # De Store is de bron van waarheid en is al ingeladen -
            # deze entiteit-state (bewust afgekapt voor weergave) mag
            # er onder geen beding overheen.
            return

        last_state = await self.async_get_last_state()
        migrated = False
        if last_state is not None:
            if not self._coordinator.nilm_confirmed_devices:
                raw_devices = last_state.attributes.get("apparaten")
                if isinstance(raw_devices, dict) and raw_devices:
                    self._coordinator.nilm_confirmed_devices = dict(raw_devices)
                    migrated = True
            raw_rejected = last_state.attributes.get("rejected_entities")
            if isinstance(raw_rejected, list) and raw_rejected:
                existing = self._coordinator.nilm_rejected_entities
                added = [eid for eid in raw_rejected if eid not in existing]
                if added:
                    self._coordinator.nilm_rejected_entities = existing + added
                    migrated = True
        if migrated:
            await self._coordinator._async_save_nilm_confirmed_devices_store()


class AdvisoryReadinessSensor(SensorEntity):
    """Readiness assessment for the ten advisory-only modules
    (Kirchhoff, sluipverbruik, Weather Ensemble, MPC, Monte Carlo,
    Kalman, Digital Twin, NILM, extra-dip-marge, temperatuur-regressie)
    - v0.63.40, uitgebreid met de laatste twee in v0.63.91, reported:
    "kunnen we een advies afgeven wanneer betrouwbaar genoeg om er
    werkelijk iets mee te doen?"

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
    _attr_name = "Advies-gereedheid (10 modules)"
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
    # v1.17.6: de naam suggereerde een temperatuur en de sensor gaf er
    # ook een - namelijk de huidige woonkamertemperatuur, wat de
    # temperatuursensor al toont. Nu de KANS dat de airco binnen een uur
    # aangaat, wat het leermechanisme uit v0.63.55 al die tijd al
    # berekende.
    _attr_name = "Airco-verwachting (kans binnen 1 uur)"
    _attr_icon = "mdi:air-conditioner"
    _attr_native_unit_of_measurement = "%"
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
        """De KANS dat de airco binnen een uur aangaat (v1.17.6).

        Gemeld: "Wat zegt dit nu? Ik dacht dat hier de verwachting in %
        of de airco aan zou gaan of niet."

        Terecht: de sensor heet "Airco-verwachting" maar gaf de huidige
        woonkamertemperatuur terug - hetzelfde getal dat de
        temperatuursensor al toont. De verwachting zat in het attribuut
        `probability_percent` en werd nergens getoond.

        Het leermechanisme uit v0.63.55 doet precies wat er gevraagd
        werd: elke temperatuurmeting wordt in een bin van 1°C gezet en
        krijgt een uur de tijd; gaat de airco in dat uur aan, dan telt
        die waarneming als "ja" voor die bin. Alleen kwam het antwoord
        niet in beeld.
        """
        temp_c = self._coordinator.living_room_current_temp_c
        if temp_c is None:
            return None
        from .const import LIVING_ROOM_TEMP_BUCKET_SIZE_C

        bucket_key = str(
            round(temp_c / LIVING_ROOM_TEMP_BUCKET_SIZE_C)
            * LIVING_ROOM_TEMP_BUCKET_SIZE_C
        )
        return self._coordinator.get_airco_activation_probability(bucket_key)[
            "probability_percent"
        ]

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
            # v1.17.6: alle geleerde bins, zodat zichtbaar is BIJ WELKE
            # temperatuur je ingrijpt - niet alleen de huidige.
            "geleerde_buckets": {
                sleutel: self._coordinator.get_airco_activation_probability(sleutel)
                for sleutel in sorted(
                    self._coordinator.living_room_temp_bucket_history,
                    key=lambda x: float(x),
                )
            },
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
            # v1.1.1: welke entiteit die waarde levert. Het dashboard
            # noemde hardgecodeerd "KNMI/OpenWeatherMap", ook nadat de
            # achtertuinsensor in v0.63.95 de voorkeursbron werd.
            "buitentemperatuur_bron": (
                self._coordinator.climate_live_outdoor_source
            ),
            # v1.3.1: waar de achtertuinsensor blijkt bloot te staan aan
            # direct zonlicht, geleerd uit eerdere flitsen.
            "achtertuin_zon_blootstelling_azimut": (
                self._coordinator.backyard_sun_exposure_azimuths
            ),
            "rolluikstand": self._coordinator.climate_shutter_state,
            "airco_status": self._coordinator.climate_airco_state,
            "traject": self._coordinator.climate_forecast_trajectory,
            "geleerde_cellen": self._coordinator.climate_rate_history,
            "note": self._coordinator.climate_forecast_note,
            # v0.63.95, gevraagd: "zijn er zaken waardoor ik de
            # voorspelling kan verbeteren" - geleerde bias-correctie op
            # de weersvoorspelling t.o.v. de achtertuinsensor.
            "voorspelling_bias_c": self._coordinator.climate_forecast_learned_bias_c,
            "achtertuinsensor_uitschieter_genegeerd": (
                self._coordinator.last_backyard_spike_filtered_note
            ),
            "voorspelling_bias_geschiedenis": (
                self._coordinator.climate_forecast_bias_history
            ),
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
        raw_bias_history = last_state.attributes.get("voorspelling_bias_geschiedenis")
        if isinstance(raw_bias_history, list):
            self._coordinator.climate_forecast_bias_history = [
                float(v) for v in raw_bias_history
            ]


class HouseholdConsumptionSensor(SensorEntity):
    """Werkelijk huishoudverbruik (v0.63.111, gevraagd na een
    naamgevingsverwarring rond de bestaande "Huidig verbruik"-tegel op
    het Overzicht-tabblad, die in werkelijkheid de RUWE P1-meter-
    aflezing toont - netto netimport/export, kan negatief zijn bij
    exporteren, en is dus NIET hetzelfde als het werkelijke
    huishoudverbruik).

    Hergebruikt `_read_corrected_consumption_power()` (dezelfde
    formule als HA's eigen Energiedashboard: P1 + accu + PV, met
    dezelfde teken-conventie/inversie-instelling als elders in deze
    integratie) - altijd >= 0, het daadwerkelijke vermogen dat het
    huishouden op dit moment verbruikt, ongeacht of dat via het net,
    de accu of PV wordt gedekt. Puur informatief, stuurt niets aan.
    """

    _attr_has_entity_name = True
    _attr_name = "Huishoudverbruik (werkelijk)"
    _attr_icon = "mdi:home-lightning-bolt-outline"
    _attr_native_unit_of_measurement = "W"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_household_consumption"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float | None:
        power_w = self._coordinator._read_corrected_consumption_power()
        return round(power_w, 1) if power_w is not None else None

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "note": (
                "Werkelijk verbruik (P1 + accu + PV samen, dezelfde "
                "formule als HA's eigen Energiedashboard) - altijd >= 0, "
                "in tegenstelling tot de kale P1-meter-aflezing die "
                "negatief kan zijn bij exporteren."
            ),
        }


class MissingOptionalFeaturesSensor(SensorEntity):
    """Overzicht van optionele, niet-geconfigureerde sensoren (v0.63.105,
    gevraagd: "kun je een melding ergens op een geschikt dashboard
    plaatsen wanneer er 1 ontbreekt"). Puur informatief, stuurt niets
    aan.

    State = aantal ontbrekende optionele functies. Niet een
    RestoreEntity - recomputed vers elke tick uit de huidige config,
    net als de Advies-gereedheid-sensor.
    """

    _attr_has_entity_name = True
    _attr_name = "Optionele functies nog niet geconfigureerd"
    _attr_icon = "mdi:puzzle-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_missing_optional_features"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> int:
        return len(self._coordinator.get_missing_optional_features())

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "ontbrekend": self._coordinator.get_missing_optional_features(),
        }


class CO2IntensitySensor(SensorEntity):
    """CO2-intensiteit van het net (v0.63.101, gevraagd: "zaken voor
    een typisch EMS welke we kunnen toevoegen"). Puur informatief,
    stuurt niets aan. Alleen actief als een CO2-intensiteit-entiteit is
    geconfigureerd (bijv. ElectricityMaps, CO2 Signal).

    State = geschatte uitstoot vandaag (kg) van geïmporteerde energie.
    Niet een RestoreEntity - een "vandaag"-metriek, zelfde afweging als
    de zelfvoorzieningsratio-sensor.
    """

    _attr_has_entity_name = True
    _attr_name = "CO2-uitstoot vandaag"
    _attr_icon = "mdi:molecule-co2"
    _attr_native_unit_of_measurement = "kg"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_co2_intensity"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float:
        return round(self._coordinator.co2_emitted_today_kg, 2)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "huidige_intensiteit_g_per_kwh": (
                self._coordinator.last_co2_intensity_g_per_kwh
            ),
            "note": (
                "Alleen de CO2-uitstoot van geïmporteerde energie - "
                "energie die zelf via PV/accu wordt gedekt importeert "
                "niets en stoot dus niets uit voor deze rekening."
            ),
        }


class BatteryHealthSensor(SensorEntity, RestoreEntity):
    """Accu-gezondheid: cyclus-telling en geschatte capaciteits-
    degradatie (v0.63.101, gevraagd: "zaken voor een typisch EMS welke
    we kunnen toevoegen"). Puur informatief, stuurt niets aan.

    State = geschat aantal volledige cycli. BEWUST EN DUIDELIJK een
    ruwe schatting, geen gemeten waarde - zie
    `BATTERY_CYCLES_TO_80_PERCENT_CAPACITY`'s docstring in const.py.
    RestoreEntity - de cumulatieve ontladen energie is een levenslange
    teller, moet een herstart overleven.
    """

    _attr_has_entity_name = True
    _attr_name = "Accu-gezondheid (geschat)"
    _attr_icon = "mdi:battery-heart-variant"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_battery_health"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float | None:
        return self._coordinator.battery_estimated_full_cycles

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "cumulatief_ontladen_kwh": round(
                self._coordinator.battery_cumulative_discharged_kwh, 2
            ),
            "geschatte_resterende_capaciteit_procent": (
                self._coordinator.battery_estimated_capacity_percent
            ),
            "note": (
                "Ruwe schatting, GEEN gemeten waarde - deze integratie kan "
                "de werkelijke accucapaciteit niet meten. Lineair model op "
                "basis van cyclusaantal, aangenomen 80% capaciteit na "
                "4000 volledige cycli (representatief voor LFP-chemie, "
                "kan afwijken van de daadwerkelijke celspecificaties)."
            ),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        raw = last_state.attributes.get("cumulatief_ontladen_kwh")
        if raw is not None:
            self._coordinator.battery_cumulative_discharged_kwh = float(raw)


class SelfConsumptionSensor(SensorEntity):
    """Zelfconsumptieratio als eigen sensor (v1.21.4).

    Gemeld: de grafiek achter de zelfconsumptie-tegel toonde de
    zelfvoorziening (97,4%) in plaats van de zelfconsumptie (9,1%).

    De oorzaak zat in de opzet: zelfconsumptie stond als ATTRIBUUT op de
    zelfvoorzieningssensor, en de tegel verwees dus naar diezelfde
    entiteit. Home Assistant toont dan de geschiedenis van de
    hoofdwaarde - een andere grootheid dan de tegel liet zien.

    Twee klassieke EMS-KPI's die verschillende dingen meten horen ook
    ieder hun eigen geschiedenis te hebben. Het attribuut blijft bestaan
    voor wie het al gebruikte.
    """

    _attr_has_entity_name = True
    _attr_name = "Zelfconsumptieratio"
    _attr_icon = "mdi:solar-power-variant-outline"
    _attr_native_unit_of_measurement = "%"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_self_consumption"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float | None:
        return self._coordinator.self_consumption_ratio_percent

    @property
    def extra_state_attributes(self) -> dict:
        c = self._coordinator
        return {
            "opwek_vandaag_kwh": round(c.pv_production_today_kwh or 0, 2),
            "teruglevering_vandaag_kwh": round(c.pv_export_today_kwh or 0, 2),
            "accu_ontladen_vandaag_kwh": round(
                c.battery_discharge_today_kwh or 0, 2
            ),
            "toelichting": (
                "Welk deel van de opgewekte zon zelf is gebruikt - "
                "rechtstreeks of via de accu. Teruglevering die uit de accu "
                "komt telt niet als zon-export (v1.16.9)."
            ),
        }

    async def async_added_to_hass(self) -> None:
        self._coordinator.register_listener(self.async_write_ha_state)


class SelfSufficiencySensor(SensorEntity):
    """Zelfconsumptie-/zelfvoorzieningsratio (v0.63.101, gevraagd:
    "zaken voor een typisch EMS welke we kunnen toevoegen" - klassieke
    EMS-KPI's). Puur informatief, stuurt niets aan.

    State = zelfvoorzieningsratio vandaag (%); zelfconsumptie staat als
    apart attribuut. Niet een RestoreEntity - een "vandaag"-metriek die
    toch elke dag weer bij 0 begint; een herstart halverwege de dag
    kost hooguit een beetje precisie voor die ene dag.
    """

    _attr_has_entity_name = True
    _attr_name = "Zelfvoorzieningsratio"
    _attr_icon = "mdi:home-battery-outline"
    _attr_native_unit_of_measurement = "%"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_self_sufficiency"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float | None:
        return self._coordinator.self_sufficiency_ratio_percent

    @property
    def extra_state_attributes(self) -> dict:
        c = self._coordinator
        return {
            "zelfconsumptie_procent": c.self_consumption_ratio_percent,
            "pv_productie_vandaag_kwh": round(c.pv_production_today_kwh, 2),
            "pv_export_vandaag_kwh": round(c.pv_export_today_kwh, 2),
            "bruto_verbruik_vandaag_kwh": round(c.gross_consumption_today_kwh, 2),
            "net_import_vandaag_kwh": round(c.grid_import_today_kwh, 2),
            "note": (
                "Zelfconsumptie = welk deel van de eigen PV-productie zelf "
                "verbruikt wordt (niet geëxporteerd). Zelfvoorziening = "
                "welk deel van het totale verbruik gedekt wordt door eigen "
                "bronnen (PV + accu), niet geïmporteerd van het net."
            ),
        }


class CounterfactualSavingsSensor(SensorEntity, RestoreEntity):
    """Tegenfeitelijke besparingsvergelijking (v0.63.101, gevraagd:
    "als je dit systeem niet had, had je deze maand €X betaald; nu
    betaalde je €Y"). Puur informatief, stuurt niets aan.

    State = geschatte besparing vandaag (tegenfeitelijke kosten minus
    werkelijke kosten). RestoreEntity - maand/all-time-totalen moeten
    een herstart overleven.
    """

    _attr_has_entity_name = True
    _attr_name = "Besparing t.o.v. zonder accu-sturing"
    _attr_icon = "mdi:cash-check"
    _attr_native_unit_of_measurement = "EUR"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_counterfactual_savings"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float:
        return round(
            self._coordinator.counterfactual_cost_today_eur
            - self._coordinator.actual_cost_today_eur,
            2,
        )

    @property
    def extra_state_attributes(self) -> dict:
        c = self._coordinator
        return {
            # v1.6.0: de werkelijke afrekening van Zonneplan naast onze
            # eigen berekening. De entiteiten worden automatisch
            # gevonden - geen configuratie nodig.
            "zonneplan_vergelijking": c.get_zonneplan_cost_comparison(),
            # v1.8.0: week/maand/jaar en trends voor stroom én gas.
            "energiekosten_overzicht": c.get_energy_cost_overview(),
            "werkelijke_kosten_vandaag_eur": round(c.actual_cost_today_eur, 2),
            "tegenfeitelijke_kosten_vandaag_eur": round(
                c.counterfactual_cost_today_eur, 2
            ),
            "werkelijke_kosten_deze_maand_eur": round(
                c.actual_cost_current_month_eur, 2
            ),
            "tegenfeitelijke_kosten_deze_maand_eur": round(
                c.counterfactual_cost_current_month_eur, 2
            ),
            "besparing_deze_maand_eur": round(
                c.counterfactual_cost_current_month_eur
                - c.actual_cost_current_month_eur,
                2,
            ),
            "werkelijke_kosten_all_time_eur": round(c.actual_cost_all_time_eur, 2),
            "tegenfeitelijke_kosten_all_time_eur": round(
                c.counterfactual_cost_all_time_eur, 2
            ),
            "besparing_all_time_eur": round(
                c.counterfactual_cost_all_time_eur - c.actual_cost_all_time_eur, 2
            ),
            "note": (
                "Tegenfeitelijk scenario: zelfde PV-opbrengst als nu, maar "
                "geen accu-sturing (accu-vermogen bij de netmeter-aflezing "
                "opgeteld) - beide scenario's tegen dezelfde dynamische "
                "prijs afgerekend."
            ),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        attrs = last_state.attributes
        c = self._coordinator
        mapping = {
            "werkelijke_kosten_vandaag_eur": "actual_cost_today_eur",
            "tegenfeitelijke_kosten_vandaag_eur": "counterfactual_cost_today_eur",
            "werkelijke_kosten_deze_maand_eur": "actual_cost_current_month_eur",
            "tegenfeitelijke_kosten_deze_maand_eur": (
                "counterfactual_cost_current_month_eur"
            ),
            "werkelijke_kosten_all_time_eur": "actual_cost_all_time_eur",
            "tegenfeitelijke_kosten_all_time_eur": (
                "counterfactual_cost_all_time_eur"
            ),
        }
        for attr_name, coordinator_field in mapping.items():
            raw = attrs.get(attr_name)
            if raw is not None:
                setattr(c, coordinator_field, float(raw))


class PeakPowerSensor(SensorEntity, RestoreEntity):
    """Piekvermogen-tracking voor capaciteitstarieven (v0.63.101,
    gevraagd: "zaken voor een typisch EMS welke we kunnen toevoegen").

    Nederlandse netbeheerders stappen steeds meer over op tarieven
    gebaseerd op het hoogste piekvermogen (kW) i.p.v. alleen kWh - deze
    sensor houdt het hoogste gemeten netto-netimport-vermogen bij op
    drie niveaus (vandaag, deze maand, all-time). Puur informatief,
    stuurt niets aan.

    v0.63.110, gerapporteerd met screenshot: "Piekvermogen verbruik
    klopt niet, het standaard energie dashboard van Home Assistant
    zelf geeft aan dat het huidige verbruik al 247W is" - bleek geen
    bug: HA's eigen "Stroomverbruik" berekent het TOTALE
    huishoudverbruik (P1 + accu + PV samen, dezelfde formule als
    `_read_corrected_consumption_power`), terwijl deze sensor bewust
    alleen de NETIMPORT via de P1-meter volgt (relevant voor
    capaciteitstarief - dat wordt afgerekend op wat het net zelf ziet,
    niet op het onderliggende huishoudverbruik). Die kan legitiem veel
    lager zijn als de accu/zon het grootste deel van het verbruik
    dekt. Naam en beschrijving verduidelijkt om dit verschil expliciet
    te maken, zodat dit niet als bug oogt.

    RestoreEntity - all-time/maand-records moeten een herstart
    overleven.
    """

    _attr_has_entity_name = True
    _attr_name = "Piekvermogen (netimport)"
    _attr_icon = "mdi:chart-bell-curve"
    _attr_native_unit_of_measurement = "W"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_peak_power"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float:
        return round(self._coordinator.peak_power_today_w, 1)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "deze_maand_w": round(self._coordinator.peak_power_current_month_w, 1),
            "vorige_maand_w": (
                round(self._coordinator.peak_power_previous_month_w, 1)
                if self._coordinator.peak_power_previous_month_w is not None
                else None
            ),
            "all_time_w": round(self._coordinator.peak_power_all_time_w, 1),
            "all_time_datum": self._coordinator.peak_power_all_time_date,
            "dag_geschiedenis": self._coordinator.peak_power_daily_history,
            "note": (
                "Volgt de netimport via de P1-meter, niet het totale "
                "huishoudverbruik - kan lager zijn dan wat het HA-"
                "energiedashboard toont als de accu/zon een deel van "
                "het verbruik dekt."
            ),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        attrs = last_state.attributes
        raw_month = attrs.get("deze_maand_w")
        if raw_month is not None:
            self._coordinator.peak_power_current_month_w = float(raw_month)
        raw_prev_month = attrs.get("vorige_maand_w")
        if raw_prev_month is not None:
            self._coordinator.peak_power_previous_month_w = float(raw_prev_month)
        raw_all_time = attrs.get("all_time_w")
        if raw_all_time is not None:
            self._coordinator.peak_power_all_time_w = float(raw_all_time)
        raw_all_time_date = attrs.get("all_time_datum")
        if raw_all_time_date:
            self._coordinator.peak_power_all_time_date = raw_all_time_date
        raw_history = attrs.get("dag_geschiedenis")
        if isinstance(raw_history, list):
            self._coordinator.peak_power_daily_history = raw_history


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
            # v0.63.132: de dagteller is een gewoon geheugenveld en staat
            # na een herstart op nul, terwijl de geschiedenis hierboven
            # wél is hersteld. Zonder deze herbouw valt de
            # diagnostiek-check terug op de optelling over de
            # weergavelijst van 20 - precies wat die teller moest
            # vervangen.
            self._coordinator.rebuild_water_session_day_counter()
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


class LiveNarrativeSensor(SensorEntity):
    """Lopend, samenhangend verhaal in gewone taal (v0.63.97, gevraagd:
    "een tabblad wat live vertelt wat de gehele integratie doet... om
    mijzelf bewuster te maken wat er gebeurt op alle vlakken en
    mogelijk weer extra input aan jou kan geven").

    Combineert bestaande state van meerdere onderdelen (accu-beslissing,
    apparaten, water, NILM, klimaat, aandachtspunten) tot één lopend
    verhaal - zie `get_live_narrative`. Puur informatief/samenvattend,
    stuurt niets aan.

    Niet een RestoreEntity - recomputed vers elke tick uit levende
    state, net als de Advies-gereedheid-sensor.
    """

    _attr_has_entity_name = True
    _attr_name = "Wat doet de integratie nu"
    _attr_icon = "mdi:text-box-outline"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_live_narrative"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> str:
        narrative = self._coordinator.get_live_narrative(dt_util.now())
        # HA-sensorstatussen zijn begrensd tot 255 tekens - de volledige
        # tekst staat altijd in het "verhaal"-attribuut hieronder.
        return narrative[:255]

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "verhaal": self._coordinator.get_live_narrative(dt_util.now()),
        }


class ModelTrendInsightSensor(SensorEntity, RestoreEntity):
    """Model-/parameternauwkeurigheid over tijd (v0.63.88, gevraagd:
    "wel wil ik allerlei waardes welke je nu hebt toegevoegd ook
    inzicht zien op het dashboard met trends... en wat het verschil in
    % over tijd is dus of het model/parameter nauwkeuriger wordt").

    Bundelt de trend (richting + %-verschil, via
    `_compute_trend_summary` - een kleinste-kwadraten-regressielijn
    door elke tijdreeks, statistisch robuuster dan een nieuwste-vs-
    oudste-vergelijking) van drie nieuwe metrics uit deze release:

    1. Spreiding van de zonvoorspelling (`deviation_stdev_history`) -
       wordt de voorspelling consistenter (dalend = beter) of juist
       wisselvalliger (stijgend) over tijd?
    2. Extra-dip-laadmarge (`extra_dip_margin_history`) - hoeveel
       marge is er typisch beschikbaar op weinig-zon-dagen, en
       verandert dat?
    3. Temperatuur-verbruik-regressie-nauwkeurigheid
       (`temp_consumption_prediction_error_history`) - wordt de
       voorspelling van het nachtverbruik op basis van
       buitentemperatuur nauwkeuriger over tijd (dalend = beter)?

    Puur informatief - stuurt niets aan. Wél een RestoreEntity, zodat
    de onderliggende geschiedenissen (bijgehouden op de coordinator,
    niet hier) een herstart overleven via dezelfde restore-aanpak als
    elders in deze integratie.
    """

    _attr_has_entity_name = True
    _attr_name = "Model- en parameternauwkeurigheid"
    _attr_icon = "mdi:chart-line-variant"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_model_trend_insight"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> str:
        return self._coordinator.last_temp_consumption_note or "onbekend"

    @property
    def extra_state_attributes(self) -> dict:
        coordinator = self._coordinator
        return {
            "zon_voorspelling_spreiding_procent": (
                coordinator.solar_tracker.deviation_stdev_percent
                if coordinator.solar_tracker
                else None
            ),
            "zon_voorspelling_spreiding_trend": coordinator._compute_trend_summary(
                coordinator.solar_tracker.deviation_stdev_history
                if coordinator.solar_tracker
                else []
            ),
            "extra_dip_marge_eur_per_kwh": coordinator.last_extra_dip_margin_eur_per_kwh,
            "extra_dip_marge_geschiedenis": coordinator.extra_dip_margin_history,
            "extra_dip_marge_trend": coordinator._compute_trend_summary(
                coordinator.extra_dip_margin_history
            ),
            "temperatuur_regressie_note": coordinator.last_temp_consumption_note,
            "temperatuur_regressie_paren": coordinator.temp_consumption_history,
            "temperatuur_regressie_nauwkeurigheid_geschiedenis": (
                coordinator.temp_consumption_prediction_error_history
            ),
            "temperatuur_regressie_nauwkeurigheid_trend": coordinator._compute_trend_summary(
                coordinator.temp_consumption_prediction_error_history
            ),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        raw_pairs = last_state.attributes.get("temperatuur_regressie_paren")
        if isinstance(raw_pairs, list):
            self._coordinator.temp_consumption_history = raw_pairs
        raw_note = last_state.attributes.get("temperatuur_regressie_note")
        if raw_note:
            self._coordinator.last_temp_consumption_note = raw_note
        raw_error_history = last_state.attributes.get(
            "temperatuur_regressie_nauwkeurigheid_geschiedenis"
        )
        if isinstance(raw_error_history, list):
            try:
                self._coordinator.temp_consumption_prediction_error_history = [
                    float(v) for v in raw_error_history
                ]
            except (TypeError, ValueError):
                pass
        raw_margin = last_state.attributes.get("extra_dip_marge_eur_per_kwh")
        if raw_margin is not None:
            try:
                self._coordinator.last_extra_dip_margin_eur_per_kwh = float(raw_margin)
            except (TypeError, ValueError):
                pass
        raw_margin_history = last_state.attributes.get("extra_dip_marge_geschiedenis")
        if isinstance(raw_margin_history, list):
            try:
                self._coordinator.extra_dip_margin_history = [
                    float(v) for v in raw_margin_history
                ]
            except (TypeError, ValueError):
                pass


def _merge_reserve_daily_records(
    existing_records: list[dict],
    dates: list,
    shortfall_values: list | None = None,
    excess_values: list | None = None,
) -> list[dict]:
    """Merge restored shortfall/excess data into a single, atomic list
    of daily records (v0.63.91) - needed because two separate sensors
    (ReserveShortfallSensor, ReserveExcessSensor) each restore their own
    half of the data, in an order HA doesn't guarantee. Whichever
    sensor's `async_added_to_hass` runs first creates each day's record
    (defaulting the field it doesn't have to False); the second
    restores by matching date and fills in its own field, rather than
    overwriting what the first already restored.
    """
    by_date = {r["date"]: dict(r) for r in existing_records}
    for i, raw_date in enumerate(dates):
        date_str = str(raw_date)
        record = by_date.get(
            date_str, {"date": date_str, "shortfall": False, "excess": False}
        )
        if shortfall_values is not None and i < len(shortfall_values):
            record["shortfall"] = bool(shortfall_values[i])
        if excess_values is not None and i < len(excess_values):
            record["excess"] = bool(excess_values[i])
        by_date[date_str] = record

    ordered_dates = [str(d) for d in dates] + [
        r["date"] for r in existing_records if r["date"] not in [str(d) for d in dates]
    ]
    return [by_date[d] for d in ordered_dates if d in by_date]


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
        raw_dates = last_state.attributes.get("history_dates")
        if not isinstance(raw_history, list) or not isinstance(raw_dates, list):
            return
        self._coordinator.reserve_daily_records = _merge_reserve_daily_records(
            self._coordinator.reserve_daily_records,
            raw_dates,
            shortfall_values=raw_history,
        )


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
        raw_dates = last_state.attributes.get("history_dates")
        if not isinstance(raw_history, list) or not isinstance(raw_dates, list):
            return
        self._coordinator.reserve_daily_records = _merge_reserve_daily_records(
            self._coordinator.reserve_daily_records,
            raw_dates,
            excess_values=raw_history,
        )


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
    # v1.21.5, gemeld: "Tevens een nachtverbruik van 400W? Mijns
    # inziens moet dit meer zijn, lijkt wel een uurwaarde?"
    #
    # De twijfel was terecht, maar anders dan verwacht. Het getal klopt
    # - het is een VERMOGEN, geen dagtotaal - maar de naam niet: er
    # wordt gemeten over het ONTLAADVENSTER (vanaf het moment dat de
    # accu gaat leveren tot het goedkope laadblok), dus avond én nacht
    # samen.
    #
    # Het geleerde uurprofiel laat 's nachts 200-290 W zien en 's avonds
    # 300-380 W. De 403 W past bij een venster dat zwaarder op de avond
    # leunt, en dat klopt: 's avonds is de prijs hoog, dus dan ontlaadt
    # de accu.
    _attr_name = "Gemiddeld vermogen in het ontlaadvenster"
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
            # v1.21.5: zeggen wat er gemeten wordt, want "403 W" leek te
            # hoog voor een nacht - terwijl het venster ook de avond
            # bevat, waar het verbruik hoger ligt.
            "toelichting": (
                "Gemiddeld vermogen over het ontlaadvenster: vanaf het "
                "moment dat de accu gaat leveren tot het goedkope "
                "laadblok. Dat is avond én nacht samen, dus hoger dan "
                "het verbruik in de kleine uurtjes alleen."
            ),
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
        # v1.48.0: `datetime.now()` volgt de tijdzone van het PROCES, niet
        # die van Home Assistant. Draait HA in een container op UTC - wat
        # gebruikelijk is - dan wees dit 's zomers twee uur verkeerd, en
        # las deze sensor het verbruiksprofiel van het verkeerde uur af.
        # Dezelfde soort fout als de tijdzoneloze tijd in de diagnostiek
        # (v1.28.0), alleen viel deze nergens om: hij gaf gewoon een
        # plausibel getal van het verkeerde uur.
        current_hour = dt_util.now().hour
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
        # v1.48.0: zie hierboven - de tijdzone van Home Assistant, niet
        # die van het proces.
        current_hour = dt_util.now().hour
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


class BatteryCoolingSensor(SensorEntity):
    """Accu-koelventilator: huidige stand + waarom (v0.63.122).

    Overgenomen uit een losse HA-automatisering die de gebruiker zelf had
    getuned. Deze sensor toont niet alleen of de ventilator aan staat,
    maar ook WELKE van de vier aanzet-redenen geldt - met vier mogelijke
    oorzaken zegt "aan" alleen te weinig om iets van te leren, en dat is
    precies wat de losse automatisering ook al met een melding probeerde
    op te lossen.
    """

    _attr_has_entity_name = True
    _attr_name = "Accu-koeling"
    _attr_icon = "mdi:fan"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_battery_cooling"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> str:
        state = self._coordinator.battery_cooling_state or {}
        aan = state.get("ventilator_aan")
        if aan is None:
            return "niet actief"
        return "koelt" if aan else "uit"

    @property
    def extra_state_attributes(self) -> dict:
        state = dict(self._coordinator.battery_cooling_state or {})
        laatste = self._coordinator.battery_cooling_last_change
        state["laatste_wijziging"] = laatste.isoformat() if laatste else None
        state["geschiedenis"] = self._coordinator.battery_cooling_history[-10:]
        return state


class BatteryModuleHealthSensor(SensorEntity):
    """Gezondheid per accumodule (v0.63.123).

    Anders dan `battery_estimated_capacity_percent` (een LINEAIRE
    schatting afgeleid uit cyclustelling, geen meting) rust deze sensor
    volledig op werkelijke metingen per module: celspanningsverschil,
    celtemperatuur, SoC en vermogen.

    De kern is de DIFFERENTIELE vergelijking - elke module tegen het
    gemiddelde van de andere. Alle modules draaien onder identieke
    omstandigheden, dus alles wat ze gemeenschappelijk hebben (SoC,
    omgevingstemperatuur, belasting) valt weg en wat overblijft is een
    eigenschap van die ene module. Dat lost meteen het lastigste
    probleem op: bij LFP is het celspanningsverschil sterk
    SoC-afhankelijk, wat een absolute waarde onvergelijkbaar maakt over
    de tijd.

    De toestand is het aantal modules dat aandacht verdient, zodat een
    "0" op het dashboard meteen zegt dat alles in orde is.
    """

    _attr_has_entity_name = True
    _attr_name = "Accu-modulegezondheid"
    _attr_icon = "mdi:battery-heart-variant"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_battery_module_health"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> int:
        tabel = self._coordinator.get_battery_module_table()
        return sum(
            1 for m in tabel if m.get("waarschuwingen") or m.get("drift_op")
        )

    @property
    def extra_state_attributes(self) -> dict:
        tabel = self._coordinator.get_battery_module_table()
        return {
            "modules": tabel,
            "aantal_modules": len(tabel),
            "spreiding": self._coordinator.battery_module_spread,
            "note": (
                "Elke module wordt vergeleken met het gemiddelde van de "
                "ANDERE modules op hetzelfde moment. Omdat ze onder "
                "identieke omstandigheden draaien (zelfde SoC, zelfde "
                "omgeving, zelfde belasting) valt alles wat ze delen weg "
                "en blijft alleen over wat eigen is aan die module. De "
                "dagelijkse mediaan van die afwijking gaat door een "
                "CUSUM-drifttest, die pas aanslaat bij een AANHOUDENDE "
                "afwijking - niet bij een enkele afwijkende dag. "
                "Celspanningsverschil is bij LFP sterk SoC-afhankelijk "
                "(vlak in het midden, steil aan de uiteinden), daarom "
                "wordt de absolute waarde per SoC-bucket bewaard en de "
                "trendbewaking op de differentiële waarde gedaan."
            ),
        }


class DigitalTwinAccuracySensor(SensorEntity, RestoreEntity):
    """Gemeten nauwkeurigheid van de Digital Twin (v1.0.1).

    Tot v1.0.0 stond er bij deze module "nauwkeurigheid t.o.v. het
    daadwerkelijke resultaat wordt niet bijgehouden". Eerlijk, maar het
    kan wél: de twin voorspelt een SoC, en die is later gewoon na te
    meten. Dezelfde "leg een voorspelling vast, controleer 'm later"-
    techniek als de zonvoorspelling-tracker.

    RestoreEntity, en dat is hier geen luxe: er zijn acht afgeronde
    vergelijkingen nodig voordat er een oordeel volgt, en die worden per
    uur vastgelegd met een horizon van zes uur. Zonder herstel zou elke
    herstart de meting terugzetten naar nul en zou het oordeel bij
    frequent herstarten nooit verschijnen - precies de fout die de
    NILM-persistentie in v0.63.115 zo lang verborgen hield.

    De toestand is de gemiddelde absolute afwijking in kWh, of leeg
    zolang er te weinig vergelijkingen zijn.
    """

    _attr_has_entity_name = True
    _attr_name = "Digital Twin nauwkeurigheid"
    _attr_icon = "mdi:target-variant"
    _attr_native_unit_of_measurement = "kWh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_digital_twin_accuracy"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> float | None:
        return self._coordinator.digital_twin_accuracy_mae_kwh

    @property
    def extra_state_attributes(self) -> dict:
        status = self._coordinator.get_digital_twin_accuracy_status()
        return {
            **status,
            "openstaande_voorspellingen": len(
                self._coordinator._digital_twin_pending
            ),
            "vergelijkingen": self._coordinator.digital_twin_accuracy_history[-10:],
            # Volledige lijsten voor het herstel na een herstart - de
            # "vergelijkingen" hierboven zijn slechts een voorbeeld voor
            # weergave.
            "volledige_historie": self._coordinator.digital_twin_accuracy_history,
            "openstaand": self._coordinator._digital_twin_pending,
            "note": (
                "De twin voorspelt de accu-inhoud een aantal uur vooruit; "
                "op dat moment wordt de voorspelling tegen de werkelijke "
                "meting gehouden. Een voorspelling die door een herstart "
                "te laat aan de beurt komt wordt weggegooid in plaats van "
                "alsnog afgerekend - die zou een fout meten die niets met "
                "het model te maken heeft. De afwijking wordt afgezet "
                "tegen de bruikbare accucapaciteit, want 1 kWh betekent "
                "iets anders bij een kleine dan bij een grote accu."
            ),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        historie = last_state.attributes.get("volledige_historie")
        if isinstance(historie, list) and historie:
            self._coordinator.digital_twin_accuracy_history = list(historie)
        openstaand = last_state.attributes.get("openstaand")
        if isinstance(openstaand, list) and openstaand:
            self._coordinator._digital_twin_pending = list(openstaand)


class ReliabilityOverviewSensor(SensorEntity):
    """Alle betrouwbaarheidsoordelen op één plek, in één taal (v1.3.0).

    Gevraagd: "hoe betrouwbaar is de gegenereerde data" - voor alle
    gegenereerde data, niet alleen de bewolkingsgraad.

    Er bestonden vijf woordenlijsten naast elkaar voor in wezen dezelfde
    vraag. Deze sensor zet ze allemaal om naar één schaal en vult de
    geleerde waarden aan die tot v1.2.0 helemaal geen oordeel hadden -
    zoals het accu-rendement, dat wél meerekent in de
    extra-dip-laadbeslissing maar nergens liet zien of het op zeven of op
    zeventig metingen rustte.

    De toestand is het aantal regels dat "betrouwbaar" is, zodat in één
    getal te zien is hoe ver de integratie is ingeleerd.
    """

    _attr_has_entity_name = True
    _attr_name = "Betrouwbaarheid gegenereerde data"
    _attr_icon = "mdi:shield-check-outline"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_reliability_overview"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> int:
        return sum(
            1
            for rij in self._coordinator.get_reliability_overview()
            if rij["niveau"] == RELIABILITY_RELIABLE
        )

    @property
    def extra_state_attributes(self) -> dict:
        rijen = self._coordinator.get_reliability_overview()
        per_niveau: dict[str, int] = {}
        for rij in rijen:
            per_niveau[rij["niveau"]] = per_niveau.get(rij["niveau"], 0) + 1
        return {
            "regels": rijen,
            "totaal": len(rijen),
            "per_niveau": per_niveau,
            "schaal": {
                niveau: uitleg for niveau, (_, uitleg) in RELIABILITY_LABELS.items()
            },
            "note": (
                "Deze schaal meet DATA-RIJPHEID, behalve waar een echte "
                "nauwkeurigheidsmeting bestaat (Digital Twin, "
                "weerensemble, sensor-gezondheid) - daar telt die meting. "
                "Veel metingen betekent dus niet automatisch dat een "
                "waarde klopt, alleen dat er genoeg is verzameld om er "
                "iets van te vinden. 'Niet toetsbaar' betekent dat er "
                "principieel niets is om tegen af te zetten; wachten "
                "maakt dat niet beter."
            ),
        }


class PvInstallationProfileSensor(SensorEntity):
    """Wat de zon verraadt over hoe de panelen liggen (v1.4.0).

    Gevraagd: "kun je nu ook zelf een berekening maken voor de
    verwachtte azimuth en andere relevante informatie hoe mijn PV
    installatie geinstalleerd ligt".

    Het vermogen piekt wanneer de zon recht voor de panelen staat, dus
    de zon-azimut op dat moment is een directe schatting van de
    paneelrichting. En de verhouding tussen werkelijke en verwachte
    opbrengst per windrichting laat zien waar er beschaduwing zit -
    een boom, een schoorsteen, een dakkapel.

    Bewust GEEN hellingshoek: die vraagt maanden aan seizoensvariatie of
    aannames over instraling die deze integratie niet kan controleren.
    Een getal geven dat er zomaar vijftien graden naast zit is erger dan
    geen getal.
    """

    _attr_has_entity_name = True
    _attr_name = "PV-installatieprofiel"
    _attr_icon = "mdi:solar-panel-large"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_pv_installation_profile"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> str:
        profiel = self._coordinator.get_pv_installation_profile()
        azimut = profiel.get("geschatte_azimut")
        if azimut is None:
            return "nog niet bepaald"
        return f"{azimut:.0f}° ({profiel.get('windrichting')})"

    @property
    def extra_state_attributes(self) -> dict:
        profiel = self._coordinator.get_pv_installation_profile()
        return {
            **profiel,
            "note": (
                "De oriëntatie wordt afgeleid uit waar de zon stond op het "
                "moment van de dagpiek, gemiddeld over dagen die helder "
                "genoeg waren - op een dag met wisselende bewolking ligt "
                "de piek waar het toevallig opklaarde. De "
                "beschaduwingskaart vergelijkt per windrichting de "
                "werkelijke opbrengst met de Solcast-verwachting; een "
                "richting die structureel achterblijft verraadt een "
                "obstakel. Hellingshoek wordt bewust niet geschat - "
                "daarvoor is deze data niet toereikend."
            ),
        }


class GacsAssessmentSensor(SensorEntity):
    """Zelfbeoordeling tegen de vier functionele GACS-eisen (v1.10.0).

    Nadrukkelijk GEEN nalevingsbewijs. De GACS-verplichting geldt voor
    utiliteitsgebouwen zonder woonfunctie met een verwarmings- of
    koelinstallatie boven 290 kW - een woning valt daar per definitie
    buiten.

    Wat dit wél is: een spiegel. De vier eisen uit het Besluit Bouwwerken
    Leefomgeving beschrijven wat een gebouwautomatiseringssysteem moet
    kunnen, en die eisen zijn even zinnig voor een woning. De derde -
    de beheerder informeren over verbetermogelijkheden - was hier het
    zwakst ingevuld, en dat is precies wat deze sensor toevoegt.

    De toestand is het aantal verbetermogelijkheden.
    """

    _attr_has_entity_name = True
    _attr_name = "GACS-zelfbeoordeling"
    _attr_icon = "mdi:clipboard-check-outline"

    # v1.25.0: deze sensor draagt de tekst voor een stuk of tien
    # dashboardpagina's. Met 36 planregels stond hij al op ruim 21 kB,
    # en Home Assistant slaat de attributen van een toestand boven 16 kB
    # niet meer op - er kwam een waarschuwing in het logboek en de
    # database hield niets bij. Nu de planning zoveel regels telt als er
    # prijzen zijn, wordt dat alleen maar erger.
    #
    # Bewaren hoeft ook niet: de kaarten lezen de huidige toestand, niet
    # de geschiedenis. Wat hier staat wordt elke tick opnieuw berekend.
    # Buiten de recorder houden lost het op zonder dat er iets verdwijnt
    # wat iemand terugkijkt.
    _unrecorded_attributes = frozenset(
        {
            "samenvattingen",
            "pv_voorspelkwaliteit",
            "pv_correctie",
            "aanwezigheid",
            "uitbreidingsadvies",
            "weerbronnen",
            "zon_uitstelplan",
            "kwartierplanning",
            "verkooptoets",
            "reservemarge",
            "zelfconsumptie",
            "perioden",
            "accu_tegen_net",
            "kwartier_samenvatting",
            "plantoetsing",
            "rendement",
            "prijstoets",
            "besparingscorrectie",
            "proefstand",
            "terugvallen",
            "zonstand",
            "buitensensor",
            "zelfcontrole",
            "logboek",
            "gezondheid",
            "veroudering",
            "waarom_nu",
            "gepland_witgoed",
            "zon_vandaag",
            "weerbron_vergelijking",
            "nog_niet_bepaald",
        }
    )

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_gacs_assessment"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def native_value(self) -> int:
        return len(self._coordinator.get_improvement_suggestions())

    @property
    def extra_state_attributes(self) -> dict:
        """Alle samenvattingen, elk apart afgeschermd (v1.19.1).

        Gemeld: alle acht tegels onder "Status per onderwerp" toonden
        tegelijk "Nog geen gegevens" - wat niet kan, want ze lezen
        verschillende onderwerpen.

        De oorzaak zat in de vorm: dit blok was één dict-expressie. Gooit
        één van de aanroepen een fout, dan mislukt het HELE blok en heeft
        Home Assistant geen enkel attribuut meer. Alle tegels vallen dan
        tegelijk terug op hun vangnettekst.

        Vandaag zijn er vijf aanroepen aan dit blok toegevoegd; elke
        toevoeging vergrootte de kans dat álles wegvalt op een fout in
        één onderdeel. Nu wordt elk deel apart opgehaald: wat werkt komt
        door, en wat faalt levert een leesbare foutmelding op in plaats
        van stilte.
        """
        attributen: dict = {}
        for sleutel, functie in (
            ("samenvattingen", self._coordinator.get_topic_summaries),
            ("pv_voorspelkwaliteit", self._coordinator.get_pv_forecast_quality),
            ("pv_correctie", self._coordinator.get_pv_correction_status),
            ("aanwezigheid", self._coordinator.get_presence_overview),
            ("uitbreidingsadvies", self._coordinator.get_expansion_advice),
            ("weerbronnen", self._coordinator.get_weather_source_overview),
            ("zon_uitstelplan", lambda: self._coordinator.last_solar_defer_plan),
            ("kwartierplanning", self._coordinator.get_quarter_plan_compact),
            ("verkooptoets", lambda: self._coordinator.last_sell_check),
            ("reservemarge", self._coordinator.get_reserve_margin_overview),
            ("zelfconsumptie", self._coordinator.get_self_consumption_overview),
            ("perioden", self._coordinator.get_period_overview),
            ("accu_tegen_net", lambda: self._coordinator.last_battery_vs_grid),
            ("kwartier_samenvatting", self._coordinator.get_quarter_plan_summary),
            # v1.31.0: plan tegen werkelijkheid.
            ("plantoetsing", self._coordinator.get_plan_review),
            ("rendement", self._coordinator.get_efficiency_overview),
            ("prijstoets", self._coordinator.get_price_attribute_check),
            ("besparingscorrectie", self._coordinator.get_savings_correction),
            ("proefstand", self._coordinator.get_proefstand),
            ("terugvallen", self._coordinator.get_fallback_overview),
            ("zonstand", self._coordinator.get_sun_position_check),
            ("buitensensor", self._coordinator.get_outdoor_sensor_check),
            ("zelfcontrole", self._coordinator.get_consistency_checks),
            ("logboek", self._coordinator.get_event_log),
            ("gezondheid", self._coordinator.get_integration_health),
            ("veroudering", self._coordinator.get_aging_drivers),
            ("waarom_nu", self._coordinator.get_why_now),
            ("gepland_witgoed", self._coordinator.get_planned_appliance_load),
            ("zon_vandaag", self._coordinator.get_solar_today),
            (
                "weerbron_vergelijking",
                lambda: (
                    self._coordinator.get_weather_source_reliability().get(
                        "_vergelijking"
                    )
                    or {}
                ),
            ),
            ("nog_niet_bepaald", self._coordinator.get_pending_overview),
        ):
            try:
                attributen[sleutel] = functie()
                # v1.29.0: ook weer opruimen als het wél lukt. Zonder dit
                # blijft een fout van weken geleden voor altijd staan en
                # gaat de herstelmelding nooit af.
                self._coordinator.internal_failures.pop(sleutel, None)
            except Exception as fout:  # noqa: BLE001
                # Bewust breed: welke fout het ook is, de andere
                # onderdelen horen gewoon door te komen. En de fout hoort
                # zichtbaar te zijn, niet alleen in het logboek.
                _LOGGER.exception("Kon %s niet berekenen", sleutel)
                attributen[sleutel] = {"fout": f"{type(fout).__name__}: {fout}"}
                # v1.19.4: ook vastleggen, zodat het als aandachtspunt
                # verschijnt. Afschermen zonder melden laat een storing
                # stil doorlopen.
                self._coordinator.internal_failures[sleutel] = (
                    f"{type(fout).__name__}: {fout}"
                )
        try:
            attributen.update(self._coordinator.get_gacs_assessment())
            self._coordinator.internal_failures.pop("gacs_beoordeling", None)
        except Exception as fout:  # noqa: BLE001
            _LOGGER.exception("Kon de GACS-beoordeling niet berekenen")
            attributen["gacs_fout"] = f"{type(fout).__name__}: {fout}"
            self._coordinator.internal_failures["gacs_beoordeling"] = (
                f"{type(fout).__name__}: {fout}"
            )
        return {
            **attributen,
            "note": (
                "De vier eisen komen uit het Besluit Bouwwerken "
                "Leefomgeving (art. 3.145/3.146). Voor woningen geldt geen "
                "verplichting; dit is een zelfbeoordeling om te zien waar "
                "een systeem sterk en zwak staat."
            ),
        }
