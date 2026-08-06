"""Coordinator implementing the Zendure price-based control loop.

Reads the raw quarter-hourly price forecast directly from a price sensor
such as Zonneplan ONE's `sensor.zonneplan_current_quarter_hourly_electricity_tariff`,
which exposes a `forecast` attribute shaped like:

    forecast:
      - start_date: "2026-07-30T09:00:00+00:00"
        end_date: "2026-07-30T09:15:00+00:00"
        price_tax_included: {amount: 2221788}
        price_tax_excluded: {amount: 1113307}
        sustainability_score: {permille: 1000}

From that raw forecast it derives, every UPDATE_INTERVAL_MINUTES minutes
and on every price-sensor update:
- whether "now" falls in one of the most expensive intervals of today,
- the start of the cheapest upcoming contiguous block of N hours,
- whether "now" falls in the discharging window: a fixed local hour
  (e.g. 01:00) on the same day as the cheapest block, running until the
  cheapest block starts.

While in the discharging window, it also samples the household
consumption sensor to learn a rolling average night-time power draw
(LEARNING_HISTORY_DAYS days), and combines that with a learned Solcast
forecast bias (from SolarForecastAccuracyTracker) to decide how many
"expensive quarters" are actually needed to bridge the night when little
solar is expected tomorrow.

A `learning_only` mode allows the integration to keep computing and
learning without ever sending commands to the Zendure entities - useful
to validate behaviour before trusting it with control.

A lock prevents overlapping runs (equivalent to `mode: restart` on the
original automation).
"""
from __future__ import annotations

import asyncio
import logging
import math
import statistics
import random
from datetime import date, datetime, timedelta

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    CHEAP_BLOCK_THRESHOLD_MARGIN_FRACTION,
    CHEAP_BLOCK_STABILITY_MARGIN_FRACTION,
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_EXPENSIVE_QUARTERS_COUNT,
    CONF_INVERT_BATTERY_POWER_SIGN,
    CONF_LOW_SOLAR_THRESHOLD_KWH,
    CONF_MANUAL_CHARGE_POWER,
    CONF_NEGATIVE_PRICE_CHARGE_POWER,
    CONF_SOLAR_POWER_LIMIT_ENTITY,
    CONF_BATTERY_ROUND_TRIP_EFFICIENCY,
    CONF_VACATION_CONSUMPTION_REDUCTION_PERCENT,
    DEFAULT_VACATION_CONSUMPTION_REDUCTION_PERCENT,
    DEFAULT_BATTERY_ROUND_TRIP_EFFICIENCY_PERCENT,
    CONF_DISHWASHER_POWER_SENSOR,
    CONF_DISHWASHER_READY_SENSOR,
    CONF_WASHING_MACHINE_POWER_SENSOR,
    CONF_WASHING_MACHINE_READY_SENSOR,
    CONF_QUOOKER_POWER_SENSOR,
    CONF_AIRCO_CLIMATE_ENTITY,
    CONF_SLAAPKAMER_CLIMATE_ENTITY,
    CONF_LIVING_ROOM_TEMPERATURE_SENSOR,
    CONF_LIVING_ROOM_HUMIDITY_SENSOR,
    CONF_LIVING_ROOM_SHUTTER_ENTITY_1,
    CONF_LIVING_ROOM_SHUTTER_ENTITY_2,
    CONF_OVEN_STATE_SENSOR,
    CONF_KOOKPLAAT_STATE_SENSOR,
    CONF_STEELSTOFZUIGER_SWITCH,
    CONF_STEELSTOFZUIGER_POWER_SENSOR,
    CONF_FIETSLADERS_SWITCH,
    CONF_FIETSLADERS_POWER_SENSOR,
    CONF_WATER_ACTIVE_USAGE_SENSOR,
    CONF_WATER_DAILY_TOTAL_SENSOR,
    CONF_WATER_TOTAL_USAGE_SENSOR,
    STEELSTOFZUIGER_COMPLETE_SUSTAINED_MINUTES,
    SCHEDULED_CHARGE_POLL_OFF_MINUTES,
    IDLE_POWER_HISTORY_LENGTH,
    LEARNED_THRESHOLD_MIN_SAMPLES,
    LEARNED_THRESHOLD_MARGIN_W,
    NILM_CUSUM_SLACK_FRACTION,
    NILM_CUSUM_ALARM_THRESHOLD,
    NILM_CUSUM_MAX_DAILY_CONTRIBUTION,
    NILM_CUSUM_RESET_STREAK_DAYS,
    NILM_CANDIDATE_COUNT_ATTENTION_THRESHOLD,
    BATTERY_CYCLES_TO_80_PERCENT_CAPACITY,
    NILM_PATTERN_EXCLUDED_KEYWORDS,
    NILM_DUPLICATE_MIN_SHARED_DAYS,
    NILM_DUPLICATE_TOLERANCE_FRACTION,
    NILM_TREND_RISING_THRESHOLD_PERCENT,
    NILM_TREND_FALLING_THRESHOLD_PERCENT,
    APPLIANCE_CYCLE_COMPLETE_SUSTAINED_MINUTES,
    WATER_USAGE_ACTIVE_THRESHOLD_L_PER_MIN,
    WATER_SESSION_COMPLETE_SUSTAINED_MINUTES,
    WATER_SESSION_HISTORY_LENGTH,
    WATER_SOFTENER_NIGHT_WINDOW_START_HOUR,
    WATER_SOFTENER_NIGHT_WINDOW_END_HOUR,
    FIETSLADERS_COMPLETE_THRESHOLD_W,
    QUOOKER_SUSTAINED_MINUTES,
    AIRCO_ACTIVE_HVAC_ACTIONS,
    SUSTAINED_HEAVY_LOAD_SOURCES,
    LIVING_ROOM_TEMP_BUCKET_SIZE_C,
    AIRCO_PREDICTION_LOOKAHEAD_MINUTES,
    AIRCO_PREDICTION_MIN_SAMPLES,
    AIRCO_PREDICTION_HISTORY_LENGTH,
    OUTDOOR_TEMP_BUCKET_SIZE_C,
    CLIMATE_RATE_HISTORY_LENGTH,
    CLIMATE_RATE_MIN_INTERVAL_HOURS,
    CLIMATE_RATE_MAX_INTERVAL_HOURS,
    CLIMATE_RATE_MIN_SAMPLES,
    CLIMATE_RATE_RELIABLE_SAMPLES,
    CLIMATE_FORECAST_HORIZON_HOURS,
    CLIMATE_FORECAST_FETCH_INTERVAL_MINUTES,
    CLIMATE_FORECAST_BIAS_HISTORY_LENGTH,
    CLIMATE_FORECAST_BIAS_MIN_SAMPLES,
    BACKYARD_TEMP_MAX_PLAUSIBLE_RATE_C_PER_HOUR,
    BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES,
    BACKYARD_TEMP_SPIKE_TOLERANCE_C,
    HOME_CONNECT_ACTIVE_STATES,
    CONF_APPLIANCE_NOTIFY_SERVICE,
    MODE_CHANGE_EMOJI,
    REASON_TO_MODE,
    APPLIANCE_RUNNING_POWER_THRESHOLD_W,
    CONSUMPTION_CORRECTION_SMOOTHING_SAMPLES,
    MAX_CONSUMPTION_CORRECTION_RATIO,
    MIN_CHARGED_KWH_FOR_EFFICIENCY_SAMPLE,
    MIN_PLAUSIBLE_EFFICIENCY_PERCENT,
    MAX_PLAUSIBLE_EFFICIENCY_PERCENT,
    CONF_MANUAL_DISCHARGE_POWER,
    CONF_BATTERY_TOTAL_CAPACITY_SENSOR,
    CONF_BATTERY_MIN_SOC_NUMBER,
    CONF_MANUAL_POWER_NUMBER,
    CONF_MIN_SOC_PERCENT,
    CONF_OPERATION_SELECT,
    CONF_FEEDIN_COST_EUR_PER_KWH,
    CONF_FEEDIN_PRICE_ATTRIBUTE,
    CONF_PRICE_ATTRIBUTE,
    CONF_SALDEREN_END_DATE,
    CONF_PRICE_SENSOR,
    CONF_PV_POWER_SENSOR,
    CONF_SOC_SENSOR,
    CONF_SOLAR_FORECAST_SENSOR,
    CONF_SOLAR_EXTENDED_FORECAST_SENSORS,
    CONF_SOLAR_TODAY_FORECAST_SENSOR,
    CONF_SOLAR_REMAINING_TODAY_SENSOR,
    DEFAULT_EXPENSIVE_QUARTERS_COUNT,
    DEFAULT_LOW_SOLAR_THRESHOLD_KWH,
    DEFAULT_MANUAL_CHARGE_POWER,
    DEFAULT_MANUAL_DISCHARGE_POWER,
    DEFAULT_MIN_SOC_PERCENT,
    DEFAULT_FEEDIN_COST_EUR_PER_KWH,
    DEFAULT_FEEDIN_PRICE_ATTRIBUTE,
    DEFAULT_PRICE_ATTRIBUTE,
    DEFAULT_SALDEREN_END_DATE,
    ENERGY_BRIDGE_SAFETY_MARGIN,
    DYNAMIC_DISCHARGE_RESERVE_MARGIN,
    EXTENDED_LOW_SOLAR_MARGIN_BONUS_PER_DAY,
    MIN_ACTIVE_SOLAR_PRODUCTION_W,
    LEARNING_HISTORY_DAYS,
    CUSUM_BASELINE_HISTORY_DAYS,
    CUSUM_MIN_HISTORY_FOR_REFERENCE,
    CUSUM_REFERENCE_EXCLUDE_RECENT_DAYS,
    CUSUM_SLACK_KW,
    CUSUM_ALARM_THRESHOLD_KW,
    CONF_KNMI_WEATHER_ENTITY,
    CONF_OPENWEATHERMAP_WEATHER_ENTITY,
    CONF_BACKYARD_TEMPERATURE_SENSOR,
    CONF_CO2_INTENSITY_SENSOR,
    WEATHER_ENSEMBLE_CLEAR_THRESHOLD_PERCENT,
    WEATHER_ENSEMBLE_OVERCAST_THRESHOLD_PERCENT,
    WEATHER_ENSEMBLE_UNDERPERFORM_RATIO,
    WEATHER_ENSEMBLE_OVERPERFORM_RATIO,
    WEATHER_ENSEMBLE_MIN_SOLCAST_KW,
    LOW_SOLAR_RELATIVE_FRACTION,
    LOW_SOLAR_FRACTION_LOW_SPREAD_THRESHOLD_PERCENT,
    LOW_SOLAR_FRACTION_HIGH_SPREAD_THRESHOLD_PERCENT,
    LOW_SOLAR_FRACTION_CONSISTENT,
    LOW_SOLAR_FRACTION_DEFAULT,
    LOW_SOLAR_FRACTION_UNRELIABLE,
    TEMP_CONSUMPTION_MIN_SAMPLES,
    EXPENSIVE_PRICE_THRESHOLD_FRACTION,
    EXPENSIVE_PRICE_THRESHOLD_FRACTION_LOW_SOLAR,
    SECONDARY_EXPENSIVE_PRICE_THRESHOLD_FRACTION,
    DEFAULT_NEGATIVE_PRICE_CHARGE_POWER,
    SOLAR_RAMP_DURATION_SECONDS,
    SOLAR_RAMP_STEPS,
    GRID_IMPORT_SHORTFALL_THRESHOLD_W,
    BATTERY_COOLING_FAN_UNAVAILABLE_STATES,
    BATTERY_MODULE_CELL_DELTA_ATTENTION_V,
    MIN_BATTERY_POWER_IDLE_W,
    BATTERY_MODULE_CELL_DELTA_SERIOUS_V,
    BATTERY_MODULE_CUSUM_SLACK_C,
    BATTERY_MODULE_CUSUM_SLACK_PERCENT,
    BATTERY_MODULE_CUSUM_SLACK_V,
    BATTERY_MODULE_CUSUM_THRESHOLD_C,
    BATTERY_MODULE_CUSUM_THRESHOLD_PERCENT,
    BATTERY_MODULE_CUSUM_THRESHOLD_V,
    BATTERY_MODULE_HISTORY_DAYS,
    BATTERY_MODULE_MIN_SAMPLES_PER_DAY,
    BATTERY_MODULE_SOC_BUCKET_SIZE_PERCENT,
    BATTERY_MODULE_SOC_SPREAD_ATTENTION_PERCENT,
    BATTERY_MODULE_TEMPERATURE_ATTENTION_C,
    BATTERY_MODULE_TEMPERATURE_SPREAD_ATTENTION_C,
    CONF_BATTERY_MODULE_CELL_VOLTAGE_MAX_SENSORS,
    CONF_BATTERY_MODULE_CELL_VOLTAGE_MIN_SENSORS,
    CONF_BATTERY_MODULE_POWER_SENSORS,
    CONF_BATTERY_MODULE_SOC_SENSORS,
    CONF_BATTERY_MODULE_TEMPERATURE_SENSORS,
    BATTERY_COOLING_HISTORY_LENGTH,
    BATTERY_COOLING_OFF_ABSOLUTE_C,
    BATTERY_COOLING_OFF_DELTA_C,
    BATTERY_COOLING_OFF_POWER_W,
    BATTERY_COOLING_ON_ABSOLUTE_C,
    BATTERY_COOLING_ON_DELTA_C,
    BATTERY_COOLING_ON_HIGH_POWER_TEMP_C,
    BATTERY_COOLING_ON_HIGH_POWER_W,
    BATTERY_COOLING_ON_POWER_DELTA_C,
    BATTERY_COOLING_ON_POWER_W,
    CONF_BATTERY_COOLING_FAN_SWITCH,
    CONF_BATTERY_COOLING_OUTDOOR_SENSOR,
    CONF_BATTERY_TEMPERATURE_SENSOR,
    MAX_HOUR_TRACKING_GAP_MINUTES,
    MEASUREMENT_QUALITY_MIN_SAMPLES,
    ENERGY_BALANCE_ERROR_HISTORY_LENGTH,
    ENERGY_BALANCE_ERROR_BAD_THRESHOLD_W,
    MEASUREMENT_QUALITY_GOOD_THRESHOLD,
    MEASUREMENT_QUALITY_DEGRADED_THRESHOLD,
    MIN_COST_BASIS_DELTA_KWH,
    FEEDIN_PREMIUM_EUR_PER_KWH,
    FEEDIN_PREMIUM_EUR_PER_KWH,
    MPC_HORIZON_HOURS,
    MPC_MIN_MARGIN_EUR_PER_KWH,
    LOW_SOLAR_EXTRA_DIP_MIN_MARGIN_EUR_PER_KWH,
    MONTE_CARLO_SIMULATIONS,
    MONTE_CARLO_MAX_HOURS,
    KALMAN_SOC_PROCESS_NOISE_KWH2,
    KALMAN_SOC_MEASUREMENT_NOISE_KWH2,
    KALMAN_PV_PROCESS_NOISE_W2,
    KALMAN_PV_MEASUREMENT_NOISE_W2,
    KALMAN_LOAD_PROCESS_NOISE_W2,
    KALMAN_LOAD_MEASUREMENT_NOISE_W2,
    DIGITAL_TWIN_HORIZON_HOURS,
    SHORTFALL_MARGIN_BONUS_PER_RECENT_DAY,
    EMERGENCY_LOW_BATTERY_KWH_THRESHOLD,
    RESERVE_EXCESS_RATIO_THRESHOLD,
    EXCESS_MARGIN_REDUCTION_PER_RECENT_DAY,
    MIN_TOTAL_MARGIN_BONUS_PERCENT,
    UNPROTECTED_AFTERMATH_MARGIN_PERCENT,
    MIN_SOLAR_HISTORY_FOR_DYNAMIC_THRESHOLD,
    OPTION_MANUAL,
    OPTION_SMART,
    OPTION_SMART_DISCHARGING,
    PRICE_SCALE_FACTOR,
    SOC_TAPER_BAND_PERCENT,
    UPDATE_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

# (interval start, interval end, price)
PriceEntry = tuple[datetime, datetime, float]


class _ChronologicalValueTracker:
    """Tracks the latest known float value from a chronologically sorted
    list of recorder states, as you advance forward through increasing
    target timestamps (a single forward pass, O(n) overall).
    """

    __slots__ = ("_states", "_idx", "_current")

    def __init__(self, states: list) -> None:
        self._states = states
        self._idx = 0
        self._current: float | None = None

    def value_at(self, target_dt: datetime) -> float | None:
        while self._idx < len(self._states):
            try:
                changed = dt_util.as_local(self._states[self._idx].last_changed)
            except (TypeError, ValueError):
                self._idx += 1
                continue
            if changed > target_dt:
                break
            try:
                self._current = float(self._states[self._idx].state)
            except (TypeError, ValueError):
                pass
            self._idx += 1
        return self._current


class _KalmanFilter1D:
    """Minimal scalar Kalman filter (v0.63.35) - no external dependency
    (numpy), appropriate for smoothing a single noisy live measurement
    over time with no explicit dynamics model beyond "the true value
    drifts a bit between updates" (process noise Q) and "the sensor
    reading is noisy" (measurement noise R). Advisory-only smoothing,
    used to display a filtered estimate alongside the raw reading -
    never fed into any decision.

    Standard scalar Kalman update:
        predict: P = P + Q
        update:  K = P / (P + R)
                 x = x + K * (measurement - x)
                 P = (1 - K) * P
    """

    def __init__(self, process_noise: float, measurement_noise: float) -> None:
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise
        self.estimate: float | None = None
        self.uncertainty: float = process_noise

    def update(self, measurement: float) -> float:
        if self.estimate is None:
            self.estimate = measurement
            self.uncertainty = self.measurement_noise
            return self.estimate

        predicted_uncertainty = self.uncertainty + self.process_noise
        gain = predicted_uncertainty / (predicted_uncertainty + self.measurement_noise)
        self.estimate = self.estimate + gain * (measurement - self.estimate)
        self.uncertainty = (1 - gain) * predicted_uncertainty
        return self.estimate


class EnergyManagementSystemCoordinator:
    """Runs the control loop that decides the Zendure operation mode."""

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        self.hass = hass
        self.config = config

        # Set from outside after construction (see __init__.py), used to
        # correct the raw solar forecast with a learned bias.
        self.solar_tracker = None

        # Replaces the old input_boolean.accu_laden_forceer_manual helper.
        self.force_manual: bool = False
        self.steelstofzuiger_override: bool = False
        self.fietsladers_override: bool = False
        # Appliance-ready notification toggle (v0.63.54, requested):
        # "Goedkoop moment voor de vaatwasser/wasmachine" - separate
        # from CONF_APPLIANCE_NOTIFY_SERVICE, which is shared by many
        # other notification types (mode-change, steelstofzuiger/
        # fietsladers-done, NILM anomaly, sluipverbruik) that shouldn't
        # all go silent just because this one specific suggestion isn't
        # wanted. Defaults on (unchanged behaviour) until turned off.
        self.appliance_ready_notifications_enabled: bool = True
        # v0.63.77, final confirmed decision after several real-world
        # reports: the entire "actively buy from the grid for a later
        # profitable quarter" mechanism (arbitrage-laden, v0.63.15-.76)
        # is removed - see `_should_capture_solar_instead_of_postponing`.
        # Only the live solar-surplus tracking remains, purely to avoid
        # wasting solar that's already there during smart_discharging.
        self.last_arbitrage_solar_surplus_w: float | None = None
        # If True: compute and learn everything as normal, but never send
        # commands to the Zendure entities. Set via a dedicated switch.
        self.learning_only: bool = False
        # If True: assume much lower household consumption (see
        # CONF_VACATION_CONSUMPTION_REDUCTION_PERCENT) and pause learning
        # from live consumption data, so the vacation period doesn't
        # pollute the learned "normal" profile. Set via a dedicated switch.
        self.vacation_mode: bool = False
        # Rolling buffer of recent live consumption readings (kW), used
        # to smooth the live-consumption correction (see
        # _get_smoothed_consumption_correction_ratio) against brief
        # spikes.
        self._recent_consumption_readings_kw: list[float] = []
        self._quooker_active_since: datetime | None = None
        self.last_heavy_load_source: str | None = None
        self._steelstofzuiger_complete_today: bool = False
        self._steelstofzuiger_complete_date: date | None = None
        self._steelstofzuiger_charge_started_at: datetime | None = None
        self._steelstofzuiger_below_threshold_since: datetime | None = None
        self._steelstofzuiger_ever_active_this_session: bool = False
        self._steelstofzuiger_next_poll_at: datetime | None = None
        self._steelstofzuiger_idle_power_history: list[float] = []
        self.steelstofzuiger_charge_duration_history: list[float] = []
        self.last_steelstofzuiger_action: str | None = None
        self._fietsladers_complete_today: bool = False
        self._fietsladers_complete_date: date | None = None
        self._fietsladers_charge_started_at: datetime | None = None
        self._fietsladers_below_threshold_since: datetime | None = None
        self._fietsladers_ever_active_this_session: bool = False
        self._fietsladers_next_poll_at: datetime | None = None
        self._fietsladers_idle_power_history: list[float] = []
        self.fietsladers_charge_duration_history: list[float] = []

        # Water-tabblad (v0.63.85) - puur informatief, stuurt nooit iets
        # aan en beïnvloedt de accu-beslissing op geen enkele manier.
        self._water_usage_state: str = "rustend"
        self._water_session_started_at: datetime | None = None
        self._water_below_threshold_since: datetime | None = None
        self._water_session_start_total_m3: float | None = None
        # v0.63.119: liters per sessie worden nu primair bepaald door
        # het DEBIET te integreren (L/min x verstreken minuten), in
        # plaats van uitsluitend het verschil van de cumulatieve
        # meterstand te nemen. Zie `_process_water_flow_sample`.
        self._water_session_liters_integrated: float = 0.0
        self._water_last_flow_l_per_min: float | None = None
        self._water_last_flow_sample_at: datetime | None = None
        # Losstaande dagteller: `water_session_history` bewaart maar de
        # laatste WATER_SESSION_HISTORY_LENGTH momenten voor weergave,
        # dus dáárop optellen levert structureel een te laag "verklaard"
        # dagtotaal op zodra er meer momenten op een dag zijn.
        self.water_sessions_today_l: float = 0.0
        self.water_sessions_today_count: int = 0
        self._water_sessions_day_key: date | None = None
        self._water_last_daily_total: float | None = None
        self.water_daily_total_l: float | None = None
        self.water_daily_history: list[float] = []
        self.water_session_history: list[dict] = []
        self.water_softener_last_regeneration: datetime | None = None
        self.last_fietsladers_action: str | None = None

        # Accu-koeling (v0.63.122) - overgenomen uit een losse
        # HA-automatisering, zie const.py.
        self.battery_cooling_state: dict = {}
        self.battery_cooling_last_change: datetime | None = None
        self.battery_cooling_history: list[dict] = []

        # Accu-modulegezondheid (v0.63.123). Per module een dict met
        # geleerde dag-historie en CUSUM-status per grootheid.
        self.battery_module_health: dict[str, dict] = {}
        self.battery_module_live: list[dict] = []
        self.battery_module_spread: dict = {}
        self._battery_module_day_key: date | None = None

        # -- Optional appliance awareness (informational only) --
        # Per hour-of-day, a rolling history of samples (1.0 = was
        # actively running, 0.0 = not) - used to learn which hours this
        # appliance is typically used, purely for insight (nothing here
        # ever controls the appliance itself).
        self.dishwasher_usage_hourly_history: dict[int, list[float]] = {}
        self.washing_machine_usage_hourly_history: dict[int, list[float]] = {}
        self._dishwasher_notified_date: date | None = None
        self._washing_machine_notified_date: date | None = None
        self.last_dishwasher_notification: str | None = None
        self.last_washing_machine_notification: str | None = None

        self.last_reason: str | None = None
        self._last_notified_mode_signature: tuple | None = None
        self.mode_change_log: list[dict] = []
        self.last_cheap_block_start: datetime | None = None
        self.last_cheap_block_end: datetime | None = None
        self.last_discharge_start: datetime | None = None
        self.last_is_expensive: bool = False
        self.last_effective_expensive_quarters_count: int | None = None
        self.last_max_sellable_quarters_by_capacity: int | None = None
        self.last_simulated_action: str | None = None
        self.last_expected_mode: str | None = None
        self.last_available_kwh: float | None = None
        self.last_needed_kwh_to_bridge: float | None = None
        self.last_needed_kwh_breakdown: dict = {}
        # v0.63.76, requested ("ik wil daarom ook altijd de tabel
        # zien"): the actual end-of-window used for the breakdown
        # above, so _build_needed_kwh_breakdown_table's "Periode" text
        # stays consistent with whatever reference window was actually
        # used (cheap_block_start, or the 24h fallback when there's no
        # meaningful upcoming cheap block).
        self.last_needed_kwh_breakdown_end_time: datetime | None = None
        self.last_has_enough_energy: bool | None = None
        self.energy_bridge_transition_log: list[dict] = []
        self.last_explanation: str = "Nog geen data verwerkt."
        self.last_soc_percent: float | None = None
        self.last_discharge_power_applied: float | None = None
        self.last_household_load_w: float | None = None
        self.last_discharge_floor_applied: bool = False
        self.discharge_floor_events: list[dict] = []
        self.last_expensive_tier: str | None = None
        self.last_expensive_price_threshold: float | None = None
        self.last_secondary_price_threshold: float | None = None
        self.last_low_solar_narrowed_threshold: bool = False
        self.last_price_priority_held_off: bool = False
        self.last_used_soc_taper_fallback: bool = False
        self.last_reserve_margin_breakdown: dict = {}
        self.last_winter_guard_suppressed_today: bool = False
        self.last_timeline: list[dict] = []
        self.last_transitions: list[dict] = []

        # -- Night consumption learning state --
        # Rolling history of average power (kW) measured during past
        # discharging windows, most recent last.
        self.night_consumption_history: list[float] = []
        self.was_bootstrapped_from_history: bool = False
        self._tracking_window_end: datetime | None = None
        self._window_energy_kwh: float = 0.0
        self._window_duration_hours: float = 0.0
        self._window_last_sample: datetime | None = None
        self._window_temp_samples: list[float] = []

        # -- Temperatuur-verbruik-regressie (v0.63.88, "eerst
        # observeren" - puur adviserend, stuurt de bestaande reserve-
        # berekening nog op geen enkele manier aan) --
        self.temp_consumption_history: list[dict] = []
        self.temp_consumption_prediction_error_history: list[float] = []
        self.last_temp_consumption_note: str | None = None

        # -- Full-day hourly consumption profile --
        # Learned continuously, all day every day (not just during the
        # discharge window), so that seasons with less predictable solar
        # (autumn/winter) still get an accurate consumption estimate even
        # when the bridging period extends into daytime hours.
        # Maps hour-of-day (0-23) -> rolling history of avg kW for that hour.
        self.hourly_consumption_profile: dict[int, list[float]] = {}
        self._current_tracked_hour: int | None = None
        self._hour_energy_kwh: float = 0.0
        self._hour_duration_hours: float = 0.0
        self._hour_last_sample: datetime | None = None

        # -- Per-hour PV forecast bias --
        # Continuously compares actual measured PV production (from a
        # live power sensor) against what Solcast forecasted for that
        # specific hour, learning a per-hour-of-day accuracy ratio -
        # more precise than a single flat daily bias, since Solcast may
        # e.g. systematically under-forecast mornings but over-forecast
        # afternoons for a given installation/orientation.
        # Maps hour-of-day (0-23) -> rolling history of (actual/forecast) ratios.
        self.pv_hourly_bias_history: dict[int, list[float]] = {}
        self._pv_current_tracked_hour: int | None = None
        self._pv_hour_energy_kwh: float = 0.0
        self._pv_hour_duration_hours: float = 0.0
        self._pv_hour_last_sample: datetime | None = None

        # -- Financial tracking --
        # Cumulative, persisted-across-restarts euro values. Deliberately
        # limited to the two actions with a clean, defensible calculation
        # (energy x price at that exact moment) rather than a vague "total
        # savings" figure that would require an unverifiable counterfactual
        # (what would have happened without this integration).
        self.total_discharge_value_eur: float = 0.0
        self.total_charge_cost_eur: float = 0.0
        # Battery cost-basis tracking (v0.63.24): a weighted-average
        # EUR/kWh cost basis for whatever energy currently sits in the
        # battery, updated on every charge (at the current dynamic price,
        # regardless of source - see below) and realised as savings on
        # every discharge (sold, or used to avoid an import). Valid under
        # a salderen (net-metering) contract, where feed-in pays the
        # same dynamic rate as import - so PV routed into the battery
        # instead of exported has exactly the same opportunity cost as
        # buying that energy from the grid at that moment. This equates
        # PV-charged and grid-charged energy into one model instead of
        # needing to track them separately (which isn't physically
        # possible anyway - the battery is one shared pool, not
        # per-source lots). Revisit this assumption if/when salderen
        # ends (currently contracted until 2026-12-31).
        self.battery_cost_basis_eur_per_kwh: float | None = None
        self._last_available_kwh_for_cost_basis: float | None = None
        self.total_battery_savings_eur: float = 0.0
        self.total_feedin_premium_eur: float = 0.0
        # v0.63.117: bron-/bestemmingssplitsing van de accu-doorvoer,
        # nodig zodra teruglevering en inkoop niet meer hetzelfde tarief
        # hebben (einde saldering). Ook los informatief: het maakt
        # zichtbaar hoeveel van de lading eigen PV-overschot was en
        # hoeveel netinkoop.
        self.salderen_active: bool = True
        self.current_feedin_value_eur_per_kwh: float | None = None
        self.feedin_import_spread_eur_per_kwh: float | None = None
        self.charge_pv_kwh_total: float = 0.0
        self.charge_grid_kwh_total: float = 0.0
        self.discharge_export_kwh_total: float = 0.0
        self.forgone_feedin_eur_total: float = 0.0
        # Kirchhoff energy-balance validation (v0.63.28).
        self._last_balance_check_time: datetime | None = None
        self._last_balance_check_available_kwh: float | None = None
        self.last_energy_balance_error_w: float | None = None
        self.energy_balance_error_history: list[float | None] = []
        self.sensor_health_score: float | None = None
        self.measurement_quality: str | None = None
        # CUSUM sluipverbruik-detectie (v0.63.29).
        self.baseline_load_history: list[float] = []
        self._cusum_check_date: date | None = None
        self._today_min_load_kw: float | None = None
        self.cusum_accumulator_kw: float = 0.0
        self.sluipverbruik_detected: bool = False
        self.sluipverbruik_estimated_drift_w: float | None = None
        self.sluipverbruik_reference_w: float | None = None
        # Weather ensemble cross-check (v0.63.30).
        self.weather_ensemble_cloud_cover_percent: float | None = None
        self.weather_ensemble_sources_used: list[str] = []
        self.weather_ensemble_label: str | None = None
        self.weather_ensemble_disagreement: str | None = None
        # Vaatwasser/wasmachine RUSTEND/ACTIEF/KLAAR-toestandsmachine
        # (v0.63.32).
        self._dishwasher_state: str = "rustend"
        self._dishwasher_cycle_started_at: datetime | None = None
        self._dishwasher_below_threshold_since: datetime | None = None
        self.dishwasher_cycle_duration_history: list[float] = []
        self._washing_machine_state: str = "rustend"
        self._washing_machine_cycle_started_at: datetime | None = None
        self._washing_machine_below_threshold_since: datetime | None = None
        self.washing_machine_cycle_duration_history: list[float] = []
        # MPC advisory engine (v0.63.33) - see coordinator method
        # docstring for the "advisory only, never controls" guarantee.
        self.mpc_planned_actions: list[dict] = []
        self.mpc_projected_total_profit_eur: float | None = None
        self.mpc_horizon_quarters_used: int = 0
        self.mpc_last_computed_at: datetime | None = None
        self.mpc_note: str | None = None
        # Monte Carlo advisory engine (v0.63.34).
        self.monte_carlo_median_deficit_kwh: float | None = None
        self.monte_carlo_p90_deficit_kwh: float | None = None
        self.monte_carlo_p10_deficit_kwh: float | None = None
        self.monte_carlo_shortfall_probability_percent: float | None = None
        self.monte_carlo_simulations_run: int = 0
        self.monte_carlo_hours_simulated: int = 0
        self.monte_carlo_note: str | None = None
        # Kalman filtering advisory engine (v0.63.35) - see
        # _KalmanFilter1D and _update_kalman_filters() for the "advisory
        # only, never fed into decisions" guarantee.
        self._kalman_soc = _KalmanFilter1D(
            KALMAN_SOC_PROCESS_NOISE_KWH2, KALMAN_SOC_MEASUREMENT_NOISE_KWH2
        )
        self._kalman_pv = _KalmanFilter1D(
            KALMAN_PV_PROCESS_NOISE_W2, KALMAN_PV_MEASUREMENT_NOISE_W2
        )
        self._kalman_load = _KalmanFilter1D(
            KALMAN_LOAD_PROCESS_NOISE_W2, KALMAN_LOAD_MEASUREMENT_NOISE_W2
        )
        self.kalman_soc_filtered_kwh: float | None = None
        self.kalman_soc_raw_kwh: float | None = None
        self.kalman_pv_filtered_w: float | None = None
        self.kalman_pv_raw_w: float | None = None
        self.kalman_load_filtered_w: float | None = None
        self.kalman_load_raw_w: float | None = None
        # Digital Twin advisory engine (v0.63.36).
        self.digital_twin_trajectory: list[dict] = []
        self.digital_twin_projected_profit_eur: float | None = None
        self.digital_twin_final_soc_kwh: float | None = None
        self.digital_twin_hours_simulated: int = 0
        self.digital_twin_note: str | None = None
        # NILM-achtige apparaat-auto-detectie (v0.63.39).
        self.nilm_unconfirmed_candidates: dict[str, dict] = {}
        self.nilm_confirmed_devices: dict[str, dict] = {}
        self.nilm_rejected_entities: list[str] = []
        # v0.63.118, gevraagd: "kun je hiervoor een zelfde optie maken
        # zodat ik ook dit kan afwijzen, en dit dan ook daadwerkelijk
        # niet meer terug komt als mogelijk duplicaat?" - paren die de
        # gebruiker heeft beoordeeld als "geen duplicaat". Opgeslagen
        # als richting-onafhankelijke sleutel ("<a>|<b>", alfabetisch
        # gesorteerd), zodat een omgedraaid paar niet alsnog terugkomt.
        # Bewust NIET opgeruimd als een van beide entiteiten tijdelijk
        # uit de bevestigde lijst verdwijnt: de gebruiker heeft een
        # oordeel gegeven en dat moet blijven gelden, ook als het
        # apparaat later opnieuw wordt bevestigd.
        self.nilm_dismissed_duplicate_pairs: list[str] = []
        # v0.63.66, reported: "State attributes ... exceed maximum size
        # of 16384 bytes" - with enough confirmed devices (each with its
        # own learned CUSUM history), nilm_confirmed_devices grew past
        # the recorder's per-entity attribute limit. The confirmed
        # devices list is user-curated and meant to persist for months,
        # so it can't just be truncated like the unconfirmed-candidates
        # preview (v0.63.45) without losing real data. Persisted instead
        # via a dedicated Store (a JSON file under .storage/, the same
        # mechanism restore_state itself uses) - entirely separate from
        # the recorder's state-history database and its size limit, so
        # there's no size ceiling here at all. The sensor's own exposed
        # attributes are still bounded for display (see
        # NilmConfirmedDevicesSensor), but that's now purely cosmetic -
        # the Store, not the entity's restored state, is the source of
        # truth for what actually gets restored on the next restart.
        self._nilm_confirmed_devices_store = Store(
            hass, version=1, key=f"{DOMAIN}_nilm_confirmed_devices"
        )
        # v0.63.115: expliciet bijhouden of de Store al van schijf is
        # gelezen, en of daar echte data in stond. Zonder deze twee
        # vlaggen moest `NilmConfirmedDevicesSensor.async_added_to_hass`
        # raden ("zijn de lijsten leeg? dan zal de Store wel leeg zijn
        # geweest") - en dat raden was structureel fout, omdat de
        # platforms in `async_setup_entry` werden opgezet VOORDAT de
        # Store werd geladen. Zie `_async_load_nilm_confirmed_devices_
        # store`'s docstring voor de volledige root cause.
        self._nilm_store_loaded = False
        self._nilm_store_had_data = False
        # Advisory readiness assessment (v0.63.40).
        self.advisory_readiness: dict[str, dict] = {}
        # Living-room-temperature airco activation predictor (v0.63.55).
        self.living_room_temp_bucket_history: dict[str, list[bool]] = {}
        self.living_room_temp_bucket_humidity: dict[str, list[float]] = {}
        self._temp_prediction_pending: list[dict] = []
        self.living_room_current_temp_c: float | None = None
        self.living_room_current_humidity_percent: float | None = None
        # Klimaat-tabblad: geleerde temperatuur-projectie (v0.63.56).
        self.climate_rate_history: dict[str, list[float]] = {}
        self._climate_anchor_temp_c: float | None = None
        self._climate_anchor_time: datetime | None = None
        self._climate_anchor_outdoor_bucket: str | None = None
        self._climate_anchor_shutter_state: str | None = None
        self._climate_anchor_airco_state: str | None = None
        self.climate_forecast_trajectory: list[dict] = []
        self.climate_forecast_note: str | None = None
        self.climate_shutter_state: str | None = None
        self.climate_airco_state: str | None = None
        self.climate_live_outdoor_temp_c: float | None = None
        self._climate_forecast_last_fetch: datetime | None = None
        self._climate_cached_forecast: list[tuple] | None = None
        # v0.63.120: de reden waarom de buitentemperatuur-voorspelling
        # ontbreekt, apart bewaard. De fetch is gethrottled (1x per 30
        # min), dus `climate_forecast_note` mocht daar niet meer de
        # enige drager van zijn - zie `_recompute_climate_trajectory`.
        self._climate_forecast_fetch_note: str | None = None
        self.climate_forecast_bias_history: list[float] = []
        # -- Uitschieter-filter achtertuinsensor (v0.63.96) --
        self._backyard_temp_last_accepted_c: float | None = None
        self._backyard_temp_last_accepted_at: datetime | None = None
        self._backyard_temp_spike_candidate_c: float | None = None
        self._backyard_temp_spike_since: datetime | None = None
        self.last_backyard_spike_filtered_note: str | None = None
        self._listeners: list = []
        self._last_cost_basis_calc_time: datetime | None = None
        self.last_charge_power_applied: float | None = None
        self.last_current_price_per_kwh: float | None = None
        self.last_projection_available_kwh: float | None = None
        self.last_projection_reserve_kwh: float | None = None
        # -- System health tracking (for sensor.system_status) --
        self.last_error: str | None = None
        self.last_error_time: datetime | None = None
        self.last_successful_update: datetime | None = None

        # -- Monthly summary (long-term trend, vs. the existing rolling
        # 7-day self-correction) --
        self._summary_month_key: int | None = None  # e.g. 202608 for Aug 2026
        self.current_month_discharge_value_eur: float = 0.0
        self.current_month_charge_cost_eur: float = 0.0
        self.current_month_shortfall_days: int = 0
        self.current_month_excess_days: int = 0
        self.current_month_days_tracked: int = 0

        # -- Piekvermogen-tracking (capaciteitstarief, v0.63.101) --
        # Nederlandse netbeheerders stappen steeds meer over op
        # tarieven gebaseerd op het hoogste piekvermogen (kW) i.p.v.
        # alleen kWh. Bewust op de gecorrigeerde consumptie-sensor
        # (netto netimport), niet op los batterij-/PV-vermogen.
        self.peak_power_today_w: float = 0.0
        self.peak_power_current_month_w: float = 0.0
        self.peak_power_previous_month_w: float | None = None
        self.peak_power_all_time_w: float = 0.0
        self.peak_power_all_time_date: str | None = None
        self.peak_power_daily_history: list[dict] = []
        self._peak_power_day_key: date | None = None
        self._peak_power_month_key: int | None = None

        # -- Tegenfeitelijke besparingsvergelijking (v0.63.101) --
        # "Als je dit systeem niet had, had je deze maand €X betaald;
        # nu betaalde je €Y." Bewust een specifieke tegenfeitelijke
        # situatie ("zelfde PV-opbrengst, maar geen accu-sturing") in
        # plaats van een vage "gemiddelde besparing" - reconstrueert
        # wat de P1-meter zou hebben getoond zonder de accu erbij
        # (P1 + accu-vermogen), en rekent dat tegen dezelfde prijs af.
        self.actual_cost_today_eur: float = 0.0
        self.counterfactual_cost_today_eur: float = 0.0
        self.actual_cost_current_month_eur: float = 0.0
        self.counterfactual_cost_current_month_eur: float = 0.0
        self.actual_cost_all_time_eur: float = 0.0
        self.counterfactual_cost_all_time_eur: float = 0.0
        self._counterfactual_last_sample: datetime | None = None
        self._counterfactual_day_key: date | None = None
        self._counterfactual_month_key: int | None = None

        # -- Zelfconsumptie-/zelfvoorzieningsratio (v0.63.101) --
        # Klassieke EMS-KPI's: welk deel van de eigen PV-productie wordt
        # zelf verbruikt (zelfconsumptie), en welk deel van het totale
        # verbruik wordt gedekt door eigen bronnen i.p.v. het net
        # (zelfvoorziening). Bijgehouden als cumulatieve kWh (vandaag),
        # de ratio's zelf worden er telkens live uit afgeleid.
        self.pv_production_today_kwh: float = 0.0
        self.pv_export_today_kwh: float = 0.0
        self.gross_consumption_today_kwh: float = 0.0
        self.grid_import_today_kwh: float = 0.0
        self._self_sufficiency_last_sample: datetime | None = None
        self._self_sufficiency_day_key: date | None = None

        # -- Accu-gezondheid: cyclus-telling (v0.63.101) --
        # Cumulatieve ontladen energie (kWh) - een "volledige cyclus" =
        # cumulatieve ontladen energie / accucapaciteit. Puur op basis
        # van ontladen (niet laden) energie, de gangbare conventie voor
        # cyclus-telling.
        self.battery_cumulative_discharged_kwh: float = 0.0
        self._battery_cycle_last_available_kwh: float | None = None
        self._battery_cycle_last_sample: datetime | None = None

        # -- CO2-intensiteit van het net (v0.63.101) --
        self.co2_emitted_today_kg: float = 0.0
        self.last_co2_intensity_g_per_kwh: float | None = None
        self._co2_last_sample: datetime | None = None
        self._co2_day_key: date | None = None
        self.previous_month_discharge_value_eur: float | None = None
        self.previous_month_charge_cost_eur: float | None = None
        self.previous_month_shortfall_days: int | None = None
        self.previous_month_excess_days: int | None = None
        self.previous_month_days_tracked: int | None = None

        # Tracked so diagnostics can flag "no progress despite enough
        # elapsed time" for the various learning mechanisms below,
        # instead of that only being caught by manually reading code.
        self.first_seen_date: date | None = None

        # -- Winter guard: don't manual-discharge after grid-charging today --
        # If the battery was force-charged from the grid today (low solar),
        # don't also manual-discharge at high prices that same day - that
        # energy was bought to cover the household, not to arbitrage.
        self._grid_charged_today: bool = False
        self._grid_charged_date: date | None = None
        self.last_extra_dip_margin_eur_per_kwh: float | None = None
        self.extra_dip_margin_history: list[float] = []
        self._extra_dip_margin_last_sample_date: date | None = None

        # -- Negative price handling --
        self._is_negative_price_active: bool = False
        self._solar_ramp_task = None

        # -- Self-learned battery round-trip efficiency --
        # Continuously track cumulative charged/discharged energy plus
        # the actual change in available (usable) energy, so the real
        # efficiency can be derived empirically instead of relying on a
        # guessed config value: charged_kwh * efficiency = discharged_kwh
        # + delta_available_kwh (energy that went in either came back out
        # again, or is still stored - what's missing is the loss).
        self.learned_efficiency_history: list[float] = []
        self._efficiency_cumulative_charged_kwh: float = 0.0
        self._efficiency_cumulative_discharged_kwh: float = 0.0
        self._efficiency_checkpoint_available_kwh: float | None = None
        self._efficiency_last_sample_time: datetime | None = None

        # -- Reserve shortfall detection & learning --
        # If net grid import happens during a period we believe should be
        # self-sufficient (smart_discharging / expensive quarter), the
        # reserve estimate for that day was too optimistic. Track this per
        # day, and learn a margin bonus if it keeps happening.
        #
        # v0.63.91, gevonden tijdens een diagnostiek-review: shortfall/
        # excess elk hadden een aparte "_history" (bool per dag) EN een
        # aparte "_dates" lijst (datum per dag), apart bijgehouden en
        # apart afgekapt - een structuur die op zich al correct in sync
        # bleef (beide worden altijd samen toegevoegd), maar wel
        # gevoelig is voor toekomstige, per-ongeluk-uit-sync-lopende
        # uitbreidingen. Nu één enkele lijst van dag-records
        # (datum + shortfall + excess samen, altijd atomisch
        # toegevoegd) - `reserve_shortfall_history`/`reserve_excess_
        # history`/`reserve_shortfall_dates`/`reserve_excess_dates`
        # blijven bestaan als afgeleide, berekende properties (zie
        # verderop) voor volledige achterwaartse compatibiliteit met
        # bestaande sensoren/diagnostiek-attributen.
        self.reserve_daily_records: list[dict] = []
        self._shortfall_detected_today: bool = False
        self._shortfall_check_date: date | None = None
        self._excess_detected_today: bool = False
        self._last_value_calc_time: datetime | None = None

        self._lock = asyncio.Lock()
        self._unsub_interval = None
        self._unsub_state = None
        self._unsub_water_state = None
        self._unsub_battery_cooling_state = None

    def register_listener(self, callback_fn) -> None:
        """Register a callback (e.g. entity.async_write_ha_state) to
        notify after each update tick completes (v0.63.48). Reported:
        the NILM confirm/reject slot buttons showed stale/empty data
        indefinitely - `ButtonEntity` doesn't poll by default (unlike
        `SensorEntity`, which is why every sensor in this integration
        refreshes fine without this), so without an explicit push their
        displayed name/attributes just froze at whatever they were the
        moment Home Assistant first wrote their state during setup.
        Same pattern already used by `SolarForecastAccuracyTracker` for
        the same reason.
        """
        self._listeners.append(callback_fn)

    def unregister_listener(self, callback_fn) -> None:
        if callback_fn in self._listeners:
            self._listeners.remove(callback_fn)

    def _notify_listeners(self) -> None:
        for listener in self._listeners:
            listener()

    @property
    def tracked_entities(self) -> list[str]:
        return [self.config[CONF_PRICE_SENSOR]]

    @property
    def reserve_shortfall_history(self) -> list[bool]:
        """Afgeleide, berekende view (v0.63.91) over `reserve_daily_
        records` - behouden voor achterwaartse compatibiliteit met
        bestaande sensoren/diagnostiek-attributen."""
        return [r["shortfall"] for r in self.reserve_daily_records]

    @property
    def reserve_shortfall_dates(self) -> list[str]:
        """Eén datum per dag in `reserve_daily_records` (niet alleen
        shortfall-dagen) - parallel aan `reserve_shortfall_history`,
        exact dezelfde semantiek als vóór v0.63.91."""
        return [r["date"] for r in self.reserve_daily_records]

    @property
    def reserve_excess_history(self) -> list[bool]:
        return [r["excess"] for r in self.reserve_daily_records]

    @property
    def reserve_excess_dates(self) -> list[str]:
        """Eén datum per dag - parallel aan `reserve_excess_history`,
        zelfde semantiek als `reserve_shortfall_dates` hierboven."""
        return [r["date"] for r in self.reserve_daily_records]

    @property
    def climate_forecast_learned_bias_c(self) -> float | None:
        """Geleerde bias-correctie (°C, additief) op de uurlijkse
        weersvoorspelling (v0.63.95), gebaseerd op vergelijking met de
        achtertuinsensor. Positief = voorspelling was te laag (de
        achtertuin was warmer dan voorspeld); negatief = voorspelling
        was te hoog. None zolang er nog niet genoeg samples zijn
        (`CLIMATE_FORECAST_BIAS_MIN_SAMPLES`) - een bias uit te weinig
        samples is zelf onbetrouwbaar.
        """
        if len(self.climate_forecast_bias_history) < CLIMATE_FORECAST_BIAS_MIN_SAMPLES:
            return None
        return round(
            sum(self.climate_forecast_bias_history)
            / len(self.climate_forecast_bias_history),
            1,
        )

    async def async_setup(self) -> None:
        """Start listening for updates and run once immediately - unless
        Home Assistant itself is still starting up, in which case wait
        for it to fully finish first.

        Without this, a fresh restart would have this integration query
        the price sensor's forecast immediately as part of its own setup,
        which can easily run *before* other integrations (e.g. the price
        sensor's own integration) have finished loading and populated
        their state - causing a spurious "No usable forecast entries"
        warning right at startup that clears itself up moments later once
        everything else has caught up.
        """
        await self.async_bootstrap_night_consumption_from_history()
        # v0.63.115: normaal al geladen in `async_setup_entry`, vóór de
        # platforms werden opgezet. Blijft hier staan als vangnet (o.a.
        # voor herladen van opties en voor tests die de coordinator
        # los opzetten); de load zelf is idempotent.
        await self.async_load_persisted_nilm_state()
        self._unsub_interval = async_track_time_interval(
            self.hass,
            self._handle_interval,
            timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )
        self._unsub_state = async_track_state_change_event(
            self.hass, self.tracked_entities, self._handle_state_change
        )
        # v0.63.98, gevraagd: "Wat gebeurt er als we naar live tikken
        # gaan?" - een aparte, live listener specifiek voor het
        # waterdebiet, los van de gewone 5-minuten-tick (zie
        # `_process_water_flow_sample`'s docstring voor de volledige
        # aanleiding/toelichting). Alleen relevant/mogelijk als er een
        # watersensor is geconfigureerd.
        water_active_entity = self.config.get(CONF_WATER_ACTIVE_USAGE_SENSOR)
        if water_active_entity:
            self._unsub_water_state = async_track_state_change_event(
                self.hass, [water_active_entity], self._handle_water_flow_change
            )
        # v0.63.122: accu-koeling reageert live, niet alleen op de
        # 5-minuten-tick. De vervangen automatisering draaide elke 2
        # minuten én op elke sensorwijziging; met alleen de tick zou de
        # ventilator merkbaar trager reageren dan de gebruiker gewend is,
        # juist bij een plotselinge belastingpiek.
        cooling_entities = [
            entity
            for entity in (
                self.config.get(CONF_BATTERY_TEMPERATURE_SENSOR),
                self.config.get(CONF_BATTERY_COOLING_OUTDOOR_SENSOR),
                self.config.get(CONF_BATTERY_POWER_SENSOR),
            )
            if entity
        ]
        if cooling_entities and self.config.get(CONF_BATTERY_COOLING_FAN_SWITCH):
            self._unsub_battery_cooling_state = async_track_state_change_event(
                self.hass, cooling_entities, self._handle_battery_cooling_change
            )
        if self.hass.state == CoreState.running:
            # Home Assistant is already fully up (e.g. this integration
            # was just installed/reloaded, not a cold boot) - safe to
            # fetch data right away.
            await self.async_update()
        else:
            self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, self._handle_hass_started
            )

    async def _handle_hass_started(self, _event: Event) -> None:
        """Run the first real update once Home Assistant has finished
        starting up, so every other integration has had a chance to load
        and populate its state first.
        """
        await self.async_update()

    async def async_bootstrap_night_consumption_from_history(self) -> None:
        """Best-effort: seed night_consumption_history from Home Assistant's
        existing recorder history, so learning doesn't start from zero.

        Since we don't know the exact discharge window for past days
        (that depends on price data we don't retroactively have), this
        approximates using a fixed 01:00-08:00 local-time window each day
        as a stand-in "night" period. If a battery and/or PV power sensor
        is configured, each P1 sample is corrected for what they mask
        from the true household load (see `_read_corrected_consumption_power`
        for the live equivalent). Never overwrites already-learned (live)
        data, and never raises - any failure just means normal day-by-day
        learning takes over.
        """
        need_night_bootstrap = not self.night_consumption_history
        # Bootstrap the hourly profile as long as ANY hour-of-day (0-23)
        # is still missing - not just when the whole dict is empty. This
        # matters once live learning has already filled in a handful of
        # hours (e.g. just the hours since the integration was last
        # updated): without this, the remaining ~20 empty hours would
        # never get backfilled from history at all.
        need_hourly_bootstrap = len(self.hourly_consumption_profile) < 24
        if not need_night_bootstrap and not need_hourly_bootstrap:
            return

        consumption_entity = self.config.get(CONF_CONSUMPTION_POWER_SENSOR)
        if not consumption_entity:
            return

        battery_entity = self.config.get(CONF_BATTERY_POWER_SENSOR)
        pv_entity = self.config.get(CONF_PV_POWER_SENSOR)
        invert_battery_sign = self.config.get(CONF_INVERT_BATTERY_POWER_SIGN, False)

        try:
            from homeassistant.components.recorder import get_instance, history
        except ImportError:
            _LOGGER.debug(
                "Recorder component not available, skipping night "
                "consumption history bootstrap"
            )
            return

        now = dt_util.now()
        start = now - timedelta(days=LEARNING_HISTORY_DAYS + 1)
        entities_to_fetch = [consumption_entity]
        if battery_entity:
            entities_to_fetch.append(battery_entity)
        if pv_entity:
            entities_to_fetch.append(pv_entity)

        def _fetch():
            return history.get_significant_states(
                self.hass, start, now, entities_to_fetch
            )

        try:
            recorder_instance = get_instance(self.hass)
            states_by_entity = await recorder_instance.async_add_executor_job(_fetch)
        except Exception as err:  # noqa: BLE001 - best effort, must never be fatal
            _LOGGER.warning(
                "Could not bootstrap night consumption learning from history: %s",
                err,
            )
            return

        p1_states = states_by_entity.get(consumption_entity, [])
        if not p1_states:
            _LOGGER.debug(
                "No historical states found for %s to bootstrap from",
                consumption_entity,
            )
            return

        battery_states = (
            sorted(states_by_entity.get(battery_entity, []), key=lambda s: s.last_changed)
            if battery_entity
            else []
        )
        pv_states = (
            sorted(states_by_entity.get(pv_entity, []), key=lambda s: s.last_changed)
            if pv_entity
            else []
        )
        battery_tracker = _ChronologicalValueTracker(battery_states)
        pv_tracker = _ChronologicalValueTracker(pv_states)

        by_day: dict[object, list[float]] = {}
        # (date, hour) -> list of corrected-power samples, used to build
        # the full 24-hour profile alongside the narrower night average.
        by_day_hour: dict[tuple, list[float]] = {}

        for state in p1_states:
            try:
                p1_value = float(state.state)
            except (TypeError, ValueError):
                continue
            try:
                local_dt = dt_util.as_local(state.last_changed)
            except (TypeError, ValueError):
                continue

            corrected_value = p1_value
            if battery_states:
                battery_value = battery_tracker.value_at(local_dt)
                if battery_value is not None:
                    if invert_battery_sign:
                        battery_value = -battery_value
                    corrected_value += battery_value
            if pv_states:
                pv_value = pv_tracker.value_at(local_dt)
                if pv_value is not None:
                    corrected_value += pv_value

            if 1 <= local_dt.hour < 8:
                by_day.setdefault(local_dt.date(), []).append(corrected_value)

            by_day_hour.setdefault((local_dt.date(), local_dt.hour), []).append(
                corrected_value
            )

        daily_averages: list[float] = []
        if need_night_bootstrap:
            for day in sorted(by_day.keys()):
                values = by_day[day]
                if values:
                    daily_averages.append(sum(values) / len(values) / 1000)

        if daily_averages:
            self.night_consumption_history = daily_averages[-LEARNING_HISTORY_DAYS:]
            self.was_bootstrapped_from_history = True
            corrections = []
            if battery_states:
                corrections.append("battery")
            if pv_states:
                corrections.append("PV")
            _LOGGER.info(
                "Bootstrapped night consumption learning from history: %s "
                "kW (approximate 01:00-08:00 window over the last %d days, "
                "corrections applied: %s)",
                [round(v, 3) for v in self.night_consumption_history],
                len(daily_averages),
                ", ".join(corrections) if corrections else "none",
            )

        # Build the full 24-hour profile from the same fetched data: for
        # each (day, hour) bucket, compute that day's average kW, then feed
        # it into the rolling per-hour history exactly like live learning.
        per_hour_daily_averages: dict[int, list[float]] = {}
        if need_hourly_bootstrap:
            for (day, hour), values in by_day_hour.items():
                if not values:
                    continue
                avg_kw = (sum(values) / len(values)) / 1000
                per_hour_daily_averages.setdefault(hour, []).append(avg_kw)

        if per_hour_daily_averages:
            for hour, day_values in per_hour_daily_averages.items():
                if not self.hourly_consumption_profile.get(hour):
                    self.hourly_consumption_profile[hour] = day_values[
                        -LEARNING_HISTORY_DAYS:
                    ]
            self.was_bootstrapped_from_history = True
            _LOGGER.info(
                "Bootstrapped full-day hourly consumption profile from "
                "history for %d hour-of-day buckets",
                len(per_hour_daily_averages),
            )

    async def async_unload(self) -> None:
        if self._unsub_interval:
            self._unsub_interval()
        if self._unsub_state:
            self._unsub_state()
        if self._unsub_water_state:
            self._unsub_water_state()
        if self._unsub_battery_cooling_state:
            self._unsub_battery_cooling_state()

    @callback
    def _handle_interval(self, _now) -> None:
        self.hass.async_create_task(self.async_update())

    @callback
    def _handle_state_change(self, _event: Event) -> None:
        self.hass.async_create_task(self.async_update())

    async def async_set_force_manual(self, value: bool) -> None:
        self.force_manual = value
        await self.async_update()

    async def async_set_steelstofzuiger_override(self, value: bool) -> None:
        self.steelstofzuiger_override = value
        await self.async_update()

    async def async_set_fietsladers_override(self, value: bool) -> None:
        self.fietsladers_override = value
        await self.async_update()

    async def async_set_appliance_ready_notifications_enabled(self, value: bool) -> None:
        self.appliance_ready_notifications_enabled = value
        await self.async_update()

    async def async_set_learning_only(self, value: bool) -> None:
        self.learning_only = value
        await self.async_update()

    @property
    def learned_night_consumption_kw(self) -> float | None:
        """Median power (kW) measured during past discharging windows -
        legacy fallback, only used when the hourly profile has no data
        for the relevant hour(s) (see `_get_dynamic_discharge_reserve_kwh`).

        Was a plain mean until v0.63.10 - missed in the v0.62.0 switch to
        median for the main hourly profile/PV bias, and demonstrably
        skewed by it: a single outlier night (2.121 kW against a ~0.2-0.4
        kW baseline on the rest) pulled this mean to 0.531 kW, roughly
        double what 6 of the 7 tracked nights actually looked like. Same
        fix, same rationale as v0.62.0: a single unusual night shouldn't
        meaningfully move a 7-day baseline.
        """
        if not self.night_consumption_history:
            return None
        return statistics.median(self.night_consumption_history)

    @property
    def learned_steelstofzuiger_duration_minutes(self) -> float | None:
        """Median charge-session duration (minutes) - informational only,
        for diagnostics/display. The actual on/off control uses the live
        power-threshold detection, not this estimate."""
        if not self.steelstofzuiger_charge_duration_history:
            return None
        return statistics.median(self.steelstofzuiger_charge_duration_history)

    @property
    def learned_fietsladers_duration_minutes(self) -> float | None:
        """Same as learned_steelstofzuiger_duration_minutes, for the
        e-bike chargers."""
        if not self.fietsladers_charge_duration_history:
            return None
        return statistics.median(self.fietsladers_charge_duration_history)

    @property
    def learned_dishwasher_cycle_duration_minutes(self) -> float | None:
        """Median cycle duration (minutes) from the RUSTEND/ACTIEF/KLAAR
        state machine (v0.63.32) - informational, and used for the
        rough "how far along" progress estimate on the sensor."""
        if not self.dishwasher_cycle_duration_history:
            return None
        return statistics.median(self.dishwasher_cycle_duration_history)

    @property
    def learned_washing_machine_cycle_duration_minutes(self) -> float | None:
        if not self.washing_machine_cycle_duration_history:
            return None
        return statistics.median(self.washing_machine_cycle_duration_history)

    # -- Forecast parsing -------------------------------------------------

    def _parse_forecast_datetime(self, value) -> datetime | None:
        """Parse a forecast entry's start/end into a datetime, accepting
        either an ISO string (the usual case) or an already-parsed
        datetime object (some integrations, or newer versions of the same
        integration, may expose these natively instead of as text -
        calling dt_util.parse_datetime() on a non-string silently fails,
        which previously caused every entry to be dropped and the whole
        forecast to look empty).
        """
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return dt_util.parse_datetime(value)
        return None

    def _get_forecast_entries(
        self, price_key_override: str | None = None
    ) -> list[PriceEntry]:
        """Read and parse the raw forecast attribute into (start, end, price) tuples.

        v0.63.117: `price_key_override` laat dezelfde parser een TWEEDE
        prijsreeks uit hetzelfde forecast-attribuut halen - concreet de
        kale marktprijs (`price_tax_excluded`) naast de normale
        inkoopprijs (`price_tax_included`). Na het einde van de
        saldering is dat het tarief waartegen teruglevering wordt
        afgerekend; zie `_get_feedin_value_per_kwh`.
        """
        state = self.hass.states.get(self.config[CONF_PRICE_SENSOR])
        if state is None:
            return []

        forecast = state.attributes.get("forecast")
        if not forecast:
            return []

        price_key = price_key_override or self.config.get(
            CONF_PRICE_ATTRIBUTE, DEFAULT_PRICE_ATTRIBUTE
        )
        entries: list[PriceEntry] = []

        for item in forecast:
            start_raw = item.get("start_date")
            end_raw = item.get("end_date")
            price_field = item.get(price_key)

            if start_raw is None or end_raw is None or price_field is None:
                continue

            # price_tax_included / price_tax_excluded are nested as
            # {"amount": <number>}. Fall back to a flat value in case a
            # different price sensor exposes it directly as a number.
            if isinstance(price_field, dict):
                price_raw = price_field.get("amount")
            else:
                price_raw = price_field
            if price_raw is None:
                continue

            start = self._parse_forecast_datetime(start_raw)
            end = self._parse_forecast_datetime(end_raw)
            if start is None or end is None:
                continue
            if start.tzinfo is None:
                start = start.replace(tzinfo=dt_util.UTC)
            if end.tzinfo is None:
                end = end.replace(tzinfo=dt_util.UTC)

            try:
                price = float(price_raw)
            except (TypeError, ValueError):
                continue

            entries.append((dt_util.as_local(start), dt_util.as_local(end), price))

        entries.sort(key=lambda entry: entry[0])
        return entries

    def _price_threshold_for_entries(
        self,
        day_entries: list[PriceEntry],
        narrow_for_low_solar: bool = False,
        fraction_override: float | None = None,
    ) -> float | None:
        """Dynamic "expensive" threshold for an arbitrary set of same-day
        price entries (top fraction of that day's price range). Shared by
        today's live decision and the multi-day timeline projection.

        `fraction_override` lets a caller compute a threshold at a
        different (typically wider/more lenient) fraction than the
        standard one - see `_get_secondary_expensive_price_threshold`.
        """
        if not day_entries:
            return None
        prices = [entry[2] for entry in day_entries]
        min_price, max_price = min(prices), max(prices)
        price_range = max_price - min_price
        if price_range <= 0:
            return None
        if fraction_override is not None:
            fraction = fraction_override
        else:
            fraction = (
                EXPENSIVE_PRICE_THRESHOLD_FRACTION_LOW_SOLAR
                if narrow_for_low_solar
                else EXPENSIVE_PRICE_THRESHOLD_FRACTION
            )
        return max_price - fraction * price_range

    def _get_secondary_expensive_price_threshold(
        self, entries: list[PriceEntry], now: datetime
    ) -> float | None:
        """A more lenient "worth selling if there's spare capacity"
        threshold for today - wider than the primary dynamic threshold
        (see `_get_expensive_price_threshold`), used only to fill
        headroom left unused after today's genuinely expensive (primary-
        tier) quarters are accounted for. Never applied on its own -
        always gated by `_get_spare_headroom_after_primary_tier_kwh`
        being > 0, so this can never eat into the reserve that protects
        tonight/tomorrow.
        """
        todays_entries = [entry for entry in entries if entry[0].date() == now.date()]
        return self._price_threshold_for_entries(
            todays_entries, fraction_override=SECONDARY_EXPENSIVE_PRICE_THRESHOLD_FRACTION
        )

    def _get_expensive_price_threshold(
        self, entries: list[PriceEntry], now: datetime
    ) -> float | None:
        """Dynamic "expensive" price threshold for today: the top fraction
        of today's actual price range, no fixed count of quarters. Narrowed
        (fewer quarters qualify) when little solar is expected, for extra
        caution. Returns None if there's no meaningful price spread today
        (flat prices - nothing is "more expensive" than anything else).
        """
        todays_entries = [entry for entry in entries if entry[0].date() == now.date()]
        return self._price_threshold_for_entries(
            todays_entries, narrow_for_low_solar=self._is_low_solar_expected()
        )

    def _is_expensive_now(
        self, entries: list[PriceEntry], now: datetime, threshold: float | None = None
    ) -> bool:
        """Is 'now' priced within the dynamic "expensive" threshold for
        today? No fixed count of quarters - self-adjusting to however many
        quarters actually clear the bar each day (see
        `_get_expensive_price_threshold`). How much is actually discharged
        is governed separately by the dynamic reserve check (see
        `_get_soc_scaled_discharge_power`), not by this classification.
        """
        todays_entries = [entry for entry in entries if entry[0].date() == now.date()]
        if not todays_entries:
            return False

        current_entry = next(
            (entry for entry in todays_entries if entry[0] <= now < entry[1]),
            None,
        )
        if current_entry is None:
            return False

        if threshold is None:
            threshold = self._get_expensive_price_threshold(entries, now)
        if threshold is None:
            return False

        return current_entry[2] >= threshold

    def _count_expensive_quarters_today(
        self, entries: list[PriceEntry], now: datetime
    ) -> int:
        """How many of today's quarters currently clear the dynamic
        "expensive" threshold, capped by how many the battery could
        physically ever discharge into (v0.63.27).

        Reported: on a day with a relatively flat price shape (one clear
        dip, a long "shoulder" of similarly-elevated prices above it),
        this raw count can run far higher than what the battery's usable
        capacity could ever actually sell into - e.g. 35 quarters (~8-9
        kWh at 1600W) against a battery with maybe 7,4 kWh available,
        making the number more confusing than informative.

        Usable discharge capacity = the Zendure's own reported total
        capacity, reduced by its own hardware minimum SoC (the device
        won't discharge below that regardless of what this integration
        asks for) - both read live, not configured statically, so this
        stays accurate if either ever changes (e.g. capacity fade from
        aging, or a manually adjusted min SoC). Falls back to the
        uncapped raw count if either entity isn't configured/available -
        same behaviour as before this version for anyone not using them.

        Deliberately doesn't also subtract the dynamic overnight reserve
        (that varies quarter to quarter and day to day) - this is a
        coarse physical sanity cap, not a precise sellable-today
        prediction; the actual decision logic (price-priority,
        `_is_worth_discharging_now`) already handles the precise
        quarter-by-quarter allocation.
        """
        threshold = self._get_expensive_price_threshold(entries, now)
        if threshold is None:
            return 0
        todays_entries = [entry for entry in entries if entry[0].date() == now.date()]
        raw_count = sum(1 for entry in todays_entries if entry[2] >= threshold)

        max_by_capacity = self._max_sellable_quarters_by_capacity()
        self.last_max_sellable_quarters_by_capacity = max_by_capacity
        if max_by_capacity is None:
            return raw_count
        return min(raw_count, max_by_capacity)

    def _max_sellable_quarters_by_capacity(self) -> int | None:
        """How many 15-minute quarters at manual_discharge_power the
        battery's usable capacity (total capacity minus its own hardware
        minimum SoC) could ever physically sustain. None if the two
        entities needed for this aren't configured/available.
        """
        usable_capacity_kwh = self._max_usable_battery_capacity_kwh()
        if usable_capacity_kwh is None:
            return None

        base_power = self.config.get(
            CONF_MANUAL_DISCHARGE_POWER, DEFAULT_MANUAL_DISCHARGE_POWER
        )
        energy_per_quarter_kwh = (base_power / 1000) * 0.25
        if energy_per_quarter_kwh <= 0:
            return None
        return int(usable_capacity_kwh / energy_per_quarter_kwh)

    def _read_sensor_float(self, entity_id: str | None) -> float | None:
        """Read a sensor's state as a float, automatically converting to
        kWh if it reports energy in Wh or MWh instead - without this, a
        sensor reporting in Wh (seen in practice: a SolarEdge yield
        sensor) gets misread as if the raw number were already kWh, off
        by a factor 1000. Only triggers for energy units (Wh/MWh) - power
        sensors (W) are unaffected, since their unit never matches those.
        """
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (None, "unknown", "unavailable"):
            return None
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return None

        unit = (state.attributes.get("unit_of_measurement") or "").strip().lower()
        if unit == "wh":
            return value / 1000
        if unit == "mwh":
            return value * 1000
        return value

    def _read_corrected_battery_power(self) -> float | None:
        """Battery power (W), sign-corrected: positive = discharging,
        negative = charging (matching the manual power number's
        convention). Returns None if no battery power sensor is
        configured or unavailable.
        """
        battery_entity = self.config.get(CONF_BATTERY_POWER_SENSOR)
        if not battery_entity:
            return None
        battery_power = self._read_sensor_float(battery_entity)
        if battery_power is None:
            return None
        if self.config.get(CONF_INVERT_BATTERY_POWER_SIGN, False):
            battery_power = -battery_power
        return battery_power

    def _update_battery_efficiency_learning(self, now: datetime) -> None:
        """Continuously learn the battery's real round-trip efficiency
        from actual charge/discharge energy, instead of relying solely on
        the configured guess.

        Energy balance: charged_kwh * efficiency = discharged_kwh +
        delta_available_kwh (whatever went in either came back out
        again, or is still stored - the gap between what went in and what
        came out-or-is-stored is the round-trip loss). Accumulates until
        enough charged energy has passed for a meaningful sample, then
        resets the checkpoint.
        """
        battery_power_w = self._read_corrected_battery_power()
        available_entity = self.config.get(CONF_AVAILABLE_ENERGY_SENSOR)
        available_kwh = (
            self._read_sensor_float(available_entity) if available_entity else None
        )

        if battery_power_w is None or available_kwh is None:
            return

        if self._efficiency_checkpoint_available_kwh is None:
            self._efficiency_checkpoint_available_kwh = available_kwh
            self._efficiency_last_sample_time = now
            return

        elapsed_hours = max(
            (now - self._efficiency_last_sample_time).total_seconds() / 3600, 0
        )
        self._efficiency_last_sample_time = now

        if elapsed_hours > 0:
            energy_kwh = (battery_power_w / 1000) * elapsed_hours
            if energy_kwh > 0:
                self._efficiency_cumulative_discharged_kwh += energy_kwh
            elif energy_kwh < 0:
                self._efficiency_cumulative_charged_kwh += -energy_kwh

        if (
            self._efficiency_cumulative_charged_kwh
            < MIN_CHARGED_KWH_FOR_EFFICIENCY_SAMPLE
        ):
            return

        delta_available_kwh = (
            available_kwh - self._efficiency_checkpoint_available_kwh
        )
        efficiency_percent = (
            (
                self._efficiency_cumulative_discharged_kwh
                + delta_available_kwh
            )
            / self._efficiency_cumulative_charged_kwh
        ) * 100

        if (
            MIN_PLAUSIBLE_EFFICIENCY_PERCENT
            <= efficiency_percent
            <= MAX_PLAUSIBLE_EFFICIENCY_PERCENT
        ):
            self.learned_efficiency_history.append(round(efficiency_percent, 1))
            self.learned_efficiency_history = self.learned_efficiency_history[
                -LEARNING_HISTORY_DAYS:
            ]
            _LOGGER.debug(
                "New battery efficiency sample: %.1f%% (charged=%.2f kWh, "
                "discharged=%.2f kWh, delta_available=%.2f kWh)",
                efficiency_percent,
                self._efficiency_cumulative_charged_kwh,
                self._efficiency_cumulative_discharged_kwh,
                delta_available_kwh,
            )
        else:
            _LOGGER.debug(
                "Discarding implausible battery efficiency sample: %.1f%% "
                "(likely a sensor glitch, not real - charged=%.2f kWh, "
                "discharged=%.2f kWh, delta_available=%.2f kWh)",
                efficiency_percent,
                self._efficiency_cumulative_charged_kwh,
                self._efficiency_cumulative_discharged_kwh,
                delta_available_kwh,
            )

        self._efficiency_cumulative_charged_kwh = 0.0
        self._efficiency_cumulative_discharged_kwh = 0.0
        self._efficiency_checkpoint_available_kwh = available_kwh

    @property
    def learned_battery_efficiency_percent(self) -> float | None:
        """Self-learned round-trip efficiency (%), as the median of
        recent samples (v0.63.10; was a plain mean, missed in the
        v0.62.0 switch to median elsewhere) - a single noisy
        charge/discharge cycle (partial cycle, measurement timing edge)
        shouldn't meaningfully move this, since it directly scales the
        safety-critical reserve calculation
        (`_get_efficiency_discounted_pv_offset`,
        `_estimate_worst_case_deficit_kwh`). None until enough samples
        exist - callers should fall back to the configured value in that
        case.
        """
        if len(self.learned_efficiency_history) < MIN_SOLAR_HISTORY_FOR_DYNAMIC_THRESHOLD:
            return None
        return statistics.median(self.learned_efficiency_history)

    def _update_single_appliance_usage_tracking(
        self, now: datetime, power_entity: str | None, history: dict[int, list[float]]
    ) -> None:
        """Record one sample (running / not running) for the current
        hour-of-day, for a single appliance. Purely informational - never
        used to control anything."""
        if not power_entity:
            return
        power_w = self._read_sensor_float(power_entity)
        if power_w is None:
            return
        sample = 1.0 if power_w >= APPLIANCE_RUNNING_POWER_THRESHOLD_W else 0.0
        bucket = history.setdefault(now.hour, [])
        bucket.append(sample)
        if len(bucket) > 500:  # keep it bounded - many samples/day add up over weeks
            del bucket[: len(bucket) - 500]

    def _update_appliance_usage_tracking(self, now: datetime) -> None:
        if self.vacation_mode:
            return  # atypical period - don't let it skew the learned pattern
        self._update_single_appliance_usage_tracking(
            now,
            self.config.get(CONF_DISHWASHER_POWER_SENSOR),
            self.dishwasher_usage_hourly_history,
        )
        self._update_single_appliance_usage_tracking(
            now,
            self.config.get(CONF_WASHING_MACHINE_POWER_SENSOR),
            self.washing_machine_usage_hourly_history,
        )

    def learned_appliance_usage_hours(
        self, history: dict[int, list[float]], threshold: float = 0.15
    ) -> list[int]:
        """Hours of the day (0-23) where this appliance is typically
        active at least `threshold` fraction of the time, sorted.
        Informational only.
        """
        typical_hours = []
        for hour, samples in history.items():
            if not samples:
                continue
            if sum(samples) / len(samples) >= threshold:
                typical_hours.append(hour)
        return sorted(typical_hours)

    def _check_and_notify_appliance_ready(
        self,
        now: datetime,
        is_currently_cheapest_block: bool,
    ) -> None:
        """If an appliance is ready to start (and not already running),
        and we're currently in today's cheapest price block, send one
        notification per appliance per day. Never starts anything itself
        - purely a suggestion for the person to act on.

        Gated by `appliance_ready_notifications_enabled` (v0.63.54,
        requested) - a dedicated on/off switch for just this
        notification type, independent of `appliance_notify_service`
        itself (shared by several other, unrelated notification types
        that should keep working even if this specific suggestion is
        unwanted).
        """
        if not self.appliance_ready_notifications_enabled:
            return
        notify_service = self.config.get(CONF_APPLIANCE_NOTIFY_SERVICE)

        self._notify_if_appliance_ready(
            now=now,
            is_currently_cheapest_block=is_currently_cheapest_block,
            ready_entity=self.config.get(CONF_DISHWASHER_READY_SENSOR),
            power_entity=self.config.get(CONF_DISHWASHER_POWER_SENSOR),
            last_notified_attr="_dishwasher_notified_date",
            message_attr="last_dishwasher_notification",
            appliance_label="vaatwasser",
            notify_service=notify_service,
        )
        self._notify_if_appliance_ready(
            now=now,
            is_currently_cheapest_block=is_currently_cheapest_block,
            ready_entity=self.config.get(CONF_WASHING_MACHINE_READY_SENSOR),
            power_entity=self.config.get(CONF_WASHING_MACHINE_POWER_SENSOR),
            last_notified_attr="_washing_machine_notified_date",
            message_attr="last_washing_machine_notification",
            appliance_label="wasmachine",
            notify_service=notify_service,
        )

    def _notify_if_appliance_ready(
        self,
        now: datetime,
        is_currently_cheapest_block: bool,
        ready_entity: str | None,
        power_entity: str | None,
        last_notified_attr: str,
        message_attr: str,
        appliance_label: str,
        notify_service: str | None,
    ) -> None:
        if not ready_entity or not is_currently_cheapest_block:
            return

        ready_state = self.hass.states.get(ready_entity)
        if ready_state is None or ready_state.state not in ("on", "true", "True"):
            return

        # Don't suggest starting something that's already running.
        if power_entity:
            power_w = self._read_sensor_float(power_entity)
            if power_w is not None and power_w >= APPLIANCE_RUNNING_POWER_THRESHOLD_W:
                return

        if getattr(self, last_notified_attr) == now.date():
            return  # already notified today for this appliance

        message = (
            f"De {appliance_label} staat klaar om te starten, en dit is nu "
            f"het goedkoopste moment van vandaag om 'm te draaien."
        )
        setattr(self, message_attr, message)
        setattr(self, last_notified_attr, now.date())

        self._dispatch_notification(
            notify_service=notify_service,
            title=f"Goedkoop moment voor de {appliance_label}",
            message=message,
            notification_id=f"ems_{appliance_label}_ready",
        )

    async def _async_update_scheduled_charge_appliance(
        self,
        now: datetime,
        is_currently_cheapest_block: bool,
        switch_entity: str | None,
        power_entity: str | None,
        complete_threshold_w: float,
        complete_today_attr: str,
        complete_date_attr: str,
        charge_started_attr: str,
        below_threshold_since_attr: str,
        duration_history_attr: str,
        last_action_attr: str,
        ever_active_this_session_attr: str,
        next_poll_attr: str,
        idle_history_attr: str,
        notify_title: str | None = None,
        notify_message: str | None = None,
        override_attr: str | None = None,
    ) -> None:
        """Shared logic (v0.63.13, generalised from the steelstofzuiger-
        only v0.63.12) for any appliance that should charge only during
        today's cheapest price block, year-round, and switch itself off
        once charging is genuinely complete (power draw sustained below
        the completion threshold for STEELSTOFZUIGER_COMPLETE_SUSTAINED_MINUTES
        - a brief dip in a charging curve shouldn't be mistaken for
        "done", same principle as the Quooker's sustained-active check,
        just inverted).

        State is kept in per-appliance attributes (passed in by name via
        `getattr`/`setattr`, same pattern already used by
        `_notify_if_appliance_ready`) rather than a shared dict, so each
        appliance's diagnostics/sensor stay simple, independently-named
        attributes instead of nested lookups.

        Unlike the dishwasher/washing machine appliance-awareness
        feature (informational only, v0.47.0), this one actually
        controls a switch entity. Charges at most once per day; once
        complete, stays off for the rest of the day even if still
        inside the cheap block. Respects learning_only (never actually
        flips the switch, only simulates) but is deliberately
        independent of force_manual - that switch is about the battery
        control loop specifically, not this.

        `override_attr` (v0.63.14): if that coordinator attribute is
        True, this appliance is left completely untouched - the person
        has taken manual control back, mirroring `force_manual` for the
        battery but scoped per appliance instead of one switch for
        everything.

        `ever_active_this_session_attr` + `next_poll_attr` (v0.63.37/
        .38): reported - the cheap block starts, the switch turns on,
        but the appliance (e-bikes, vacuum) isn't physically plugged in
        until later, still within the same cheap block.
        v0.63.37 fixed the false-"voltooid" bug this caused (sustained
        low power looked identical whether nothing was ever plugged in,
        or a real charge had genuinely finished) by tracking whether
        power ever actually crossed the threshold this session. But that
        fix left the switch ON continuously for however long nothing was
        detected - a follow-up fire-safety concern: a charger/inverter
        sitting energised, unattended, for potentially hours.
        v0.63.38 replaces "stay on and wait" with polling: on for one
        update tick (~5 min) to test for a load, back off for
        SCHEDULED_CHARGE_POLL_OFF_MINUTES (15 min) if nothing found,
        repeat - matching the reported "15-minuten controle-cyclus"
        suggestion. `charge_started_attr` is only set once genuine
        activity is actually confirmed, so the learned duration reflects
        real charging time, not time spent polling.

        `idle_history_attr` (v0.63.46): reported - the fixed
        `complete_threshold_w` guess doesn't reflect the appliance's
        real standby draw (observed 2W for the e-bike chargers, vs. the
        20W guess). Every power reading taken while the appliance is
        still believed idle (before genuine activity is confirmed this
        session) is a real idle/standby sample - once
        LEARNED_THRESHOLD_MIN_SAMPLES have accumulated, the completion
        threshold is derived from their median plus a safety margin
        (LEARNED_THRESHOLD_MARGIN_W) instead of the fixed guess. Falls
        back to `complete_threshold_w` until enough samples exist.
        """
        if not switch_entity:
            return
        if override_attr is not None and getattr(self, override_attr):
            setattr(self, last_action_attr, "overruled")
            return

        if getattr(self, complete_date_attr) != now.date():
            setattr(self, complete_today_attr, False)
            setattr(self, complete_date_attr, now.date())

        power_w = self._read_sensor_float(power_entity) if power_entity else None
        switch_state = self.hass.states.get(switch_entity)
        is_on = switch_state is not None and switch_state.state == "on"
        effective_threshold_w = self._get_learned_completion_threshold_w(
            idle_history_attr, complete_threshold_w
        )

        complete_today = getattr(self, complete_today_attr)
        should_charge = is_currently_cheapest_block and not complete_today

        if not should_charge:
            if is_on:
                await self._async_set_switch(switch_entity, turn_on=False)
                self._finish_scheduled_charge_session(
                    now,
                    charge_started_attr,
                    below_threshold_since_attr,
                    duration_history_attr,
                    completed=False,
                )
            setattr(self, next_poll_attr, None)
            setattr(
                self,
                last_action_attr,
                "voltooid_vandaag" if complete_today else "wacht_op_goedkoop_blok",
            )
            return

        ever_active = getattr(self, ever_active_this_session_attr)

        if not is_on:
            next_poll_at = getattr(self, next_poll_attr)
            if next_poll_at is not None and now < next_poll_at:
                # In the cooldown between poll attempts - stay off.
                setattr(self, last_action_attr, "wacht_op_apparaat")
                return
            # First attempt, or a fresh poll attempt after a cooldown -
            # turn on for one tick to test for a load.
            await self._async_set_switch(switch_entity, turn_on=True)
            setattr(self, below_threshold_since_attr, None)
            setattr(self, ever_active_this_session_attr, False)
            setattr(self, next_poll_attr, now + timedelta(minutes=UPDATE_INTERVAL_MINUTES))
            setattr(self, last_action_attr, "test_aan")
            return

        # Already on - a reading taken while still idle (before genuine
        # activity is confirmed) is a real idle/standby sample, feeding
        # the self-learned threshold. Recorded using *this* tick's
        # effective threshold (computed from *previous* ticks' learned
        # data), so a tick can't influence its own classification.
        if not ever_active and power_entity and power_w is not None:
            if power_w < effective_threshold_w:
                self._record_idle_power_sample(idle_history_attr, power_w)

        # Register genuine activity, regardless of what happens below -
        # a tick that crosses the threshold always counts, even the
        # very tick this evaluates.
        if power_entity and power_w is not None and power_w >= effective_threshold_w:
            if not ever_active:
                # Genuine charging just confirmed - start the duration
                # timer now, not from whenever polling first began.
                setattr(self, charge_started_attr, now)
            setattr(self, ever_active_this_session_attr, True)
            ever_active = True

        if not ever_active:
            # Still in the poll-test window - has it elapsed without
            # detecting anything?
            poll_deadline = getattr(self, next_poll_attr)
            if poll_deadline is not None and now >= poll_deadline:
                await self._async_set_switch(switch_entity, turn_on=False)
                setattr(
                    self,
                    next_poll_attr,
                    now + timedelta(minutes=SCHEDULED_CHARGE_POLL_OFF_MINUTES),
                )
                setattr(self, last_action_attr, "wacht_op_apparaat")
                return
            setattr(self, last_action_attr, "test_aan")
            return

        # Genuinely charging - watch for completion (sustained low power).
        if power_entity and power_w is not None and power_w < effective_threshold_w:
            since = getattr(self, below_threshold_since_attr)
            if since is None:
                since = now
                setattr(self, below_threshold_since_attr, since)
            elapsed_minutes = (now - since).total_seconds() / 60
            if elapsed_minutes >= STEELSTOFZUIGER_COMPLETE_SUSTAINED_MINUTES:
                await self._async_set_switch(switch_entity, turn_on=False)
                self._finish_scheduled_charge_session(
                    now,
                    charge_started_attr,
                    below_threshold_since_attr,
                    duration_history_attr,
                    completed=True,
                )
                setattr(self, complete_today_attr, True)
                setattr(self, next_poll_attr, None)
                setattr(self, last_action_attr, "voltooid")
                if notify_title and notify_message:
                    notify_service = self.config.get(CONF_APPLIANCE_NOTIFY_SERVICE)
                    if notify_service:
                        self._dispatch_notification(
                            notify_service=notify_service,
                            title=notify_title,
                            message=notify_message,
                            notification_id=f"ems_{last_action_attr}_complete",
                        )
                return
        else:
            setattr(self, below_threshold_since_attr, None)

        setattr(self, last_action_attr, "aan_het_laden")

    def _finish_scheduled_charge_session(
        self,
        now: datetime,
        charge_started_attr: str,
        below_threshold_since_attr: str,
        duration_history_attr: str,
        completed: bool,
    ) -> None:
        """Record how long a charge session ran, for the learned-duration
        history (median, same outlier-resistant approach as v0.62.0) -
        purely informational/diagnostic, not itself a decision input
        (the power-threshold detection above is the actual, more
        reliable signal for "is it done").
        """
        started_at = getattr(self, charge_started_attr)
        if started_at is None:
            return
        duration_minutes = (now - started_at).total_seconds() / 60
        if completed and duration_minutes > 0:
            history = getattr(self, duration_history_attr)
            history.append(round(duration_minutes, 1))
            setattr(self, duration_history_attr, history[-LEARNING_HISTORY_DAYS:])
        setattr(self, charge_started_attr, None)
        setattr(self, below_threshold_since_attr, None)

    def _get_learned_completion_threshold_w(
        self, idle_history_attr: str, fallback_w: float
    ) -> float:
        """Self-learned completion threshold (v0.63.46) - reported: the
        fixed guess (e.g. 20W for the e-bike chargers) doesn't reflect
        the appliance's real standby draw (observed 2W). Derives a
        threshold from the median of actually-observed idle/standby
        power readings plus a safety margin, once enough samples exist
        (LEARNED_THRESHOLD_MIN_SAMPLES); falls back to the configured
        fixed threshold otherwise. The margin
        (LEARNED_THRESHOLD_MARGIN_W, 5W) is a heuristic choice, not
        empirically validated per installation.
        """
        history = getattr(self, idle_history_attr, [])
        if len(history) < LEARNED_THRESHOLD_MIN_SAMPLES:
            return fallback_w
        idle_baseline_w = statistics.median(history)
        return idle_baseline_w + LEARNED_THRESHOLD_MARGIN_W

    def _record_idle_power_sample(self, idle_history_attr: str, power_w: float) -> None:
        history = getattr(self, idle_history_attr, [])
        history = history + [power_w]
        setattr(self, idle_history_attr, history[-IDLE_POWER_HISTORY_LENGTH:])

    async def _async_set_switch(self, entity_id: str, turn_on: bool) -> None:
        """Turn a switch entity on/off, unless in learning_only mode.
        Deliberately doesn't touch `last_simulated_action` - that field
        is shared with the battery decision tree's own learning_only
        simulation, which runs later in the same tick and would
        overwrite it. The caller's own last-action attribute already
        reflects the intended action either way.
        """
        if self.learning_only:
            _LOGGER.debug(
                "Learning-only mode: would turn %s %s",
                "on" if turn_on else "off",
                entity_id,
            )
            return
        await self.hass.services.async_call(
            "switch",
            "turn_on" if turn_on else "turn_off",
            {"entity_id": entity_id},
            blocking=True,
        )

    def _dispatch_notification(
        self,
        notify_service: str | None,
        title: str,
        message: str,
        notification_id: str,
    ) -> None:
        """Shared notification dispatch, used for both the appliance-ready
        suggestion (v0.47.0) and the mode/power-change notification
        (v0.63.8) - both reuse the same CONF_APPLIANCE_NOTIFY_SERVICE
        config option, so nothing extra needs to be set up for either.
        Falls back to a persistent notification in the HA UI if no
        notify service is configured.
        """
        service_domain, _, service_name = (
            notify_service or "persistent_notification.create"
        ).partition(".")
        try:
            if service_domain == "persistent_notification":
                self.hass.async_create_task(
                    self.hass.services.async_call(
                        "persistent_notification",
                        "create",
                        {
                            "title": title,
                            "message": message,
                            "notification_id": notification_id,
                        },
                    )
                )
            else:
                self.hass.async_create_task(
                    self.hass.services.async_call(
                        service_domain,
                        service_name,
                        {"message": message, "title": title},
                    )
                )
        except Exception:  # noqa: BLE001 - a failed notification must never crash the update
            _LOGGER.exception("Failed to send notification: %s", title)

    def _track_recent_consumption_reading(self, now: datetime) -> None:
        """Append the current live consumption reading (kW) to a short
        rolling buffer, used to smooth the live-consumption correction
        below - so a brief spike (a kettle, a few minutes of a washing
        machine's heating element) doesn't get treated the same as a
        sustained change (the airco running for a while), and can't
        single-handedly scale a 15+ hour estimate to an absurd value.
        """
        live_power_w = self._read_corrected_consumption_power()
        if live_power_w is None:
            return
        self._recent_consumption_readings_kw.append(live_power_w / 1000)
        self._recent_consumption_readings_kw = self._recent_consumption_readings_kw[
            -CONSUMPTION_CORRECTION_SMOOTHING_SAMPLES:
        ]

    def _update_quooker_tracking(self, now: datetime) -> None:
        """Track how long the Quooker's power draw has been continuously
        above the running threshold - a single brief tap (a minute or
        less) resets this, only a longer session (several taps back to
        back, or a long fill) counts as sustained (see
        QUOOKER_SUSTAINED_MINUTES)."""
        quooker_entity = self.config.get(CONF_QUOOKER_POWER_SENSOR)
        if not quooker_entity:
            self._quooker_active_since = None
            return
        power_w = self._read_sensor_float(quooker_entity)
        if power_w is not None and power_w >= APPLIANCE_RUNNING_POWER_THRESHOLD_W:
            if self._quooker_active_since is None:
                self._quooker_active_since = now
        else:
            self._quooker_active_since = None

    def _is_quooker_sustained_active(self, now: datetime) -> bool:
        if self._quooker_active_since is None:
            return False
        elapsed_minutes = (now - self._quooker_active_since).total_seconds() / 60
        return elapsed_minutes >= QUOOKER_SUSTAINED_MINUTES

    def _get_confirmed_heavy_load_source(self, now: datetime) -> str | None:
        """Is a known heavy load (vaatwasser, wasmachine, Quooker, airco,
        oven, kookplaat) genuinely, confirmably active right now? Returns
        the appliance label if so, else None - used to skip the median
        smoothing's built-in caution (see
        `_get_smoothed_consumption_correction_ratio`) for the live
        consumption correction. That caution exists specifically to
        protect against a brief spike that *might* be a real appliance
        but might also be a sensor glitch or a passing blip; if the
        appliance's own entity confirms it's genuinely running, there's
        no ambiguity left to protect against, so the live reading can be
        trusted immediately instead of waiting several update ticks
        (~15-20 min) for the median to catch up.

        Oven/kookplaat use their Home Connect `operation_state` sensor
        (state-based, no power sensor available) rather than a power
        threshold - see HOME_CONNECT_ACTIVE_STATES.

        Reported scenario: an autumn evening where the airco (heating)
        only runs some evenings, unpredictably - too irregular for the
        7-day learned profile (median, v0.62.0) to ever treat as normal,
        but a real load worth reacting to immediately on the nights it
        does run.
        """
        dishwasher_entity = self.config.get(CONF_DISHWASHER_POWER_SENSOR)
        if dishwasher_entity:
            power_w = self._read_sensor_float(dishwasher_entity)
            if power_w is not None and power_w >= APPLIANCE_RUNNING_POWER_THRESHOLD_W:
                return "vaatwasser"

        washing_machine_entity = self.config.get(CONF_WASHING_MACHINE_POWER_SENSOR)
        if washing_machine_entity:
            power_w = self._read_sensor_float(washing_machine_entity)
            if power_w is not None and power_w >= APPLIANCE_RUNNING_POWER_THRESHOLD_W:
                return "wasmachine"

        if self._is_quooker_sustained_active(now):
            return "quooker"

        airco_entity = self.config.get(CONF_AIRCO_CLIMATE_ENTITY)
        if airco_entity:
            state = self.hass.states.get(airco_entity)
            if state is not None:
                hvac_action = state.attributes.get("hvac_action")
                if hvac_action in AIRCO_ACTIVE_HVAC_ACTIONS:
                    return "airco"

        slaapkamer_entity = self.config.get(CONF_SLAAPKAMER_CLIMATE_ENTITY)
        if slaapkamer_entity:
            state = self.hass.states.get(slaapkamer_entity)
            if state is not None:
                hvac_action = state.attributes.get("hvac_action")
                if hvac_action in AIRCO_ACTIVE_HVAC_ACTIONS:
                    return "slaapkamer"

        oven_entity = self.config.get(CONF_OVEN_STATE_SENSOR)
        if oven_entity:
            state = self.hass.states.get(oven_entity)
            if state is not None and state.state.lower() in HOME_CONNECT_ACTIVE_STATES:
                return "oven"

        kookplaat_entity = self.config.get(CONF_KOOKPLAAT_STATE_SENSOR)
        if kookplaat_entity:
            state = self.hass.states.get(kookplaat_entity)
            if state is not None and state.state.lower() in HOME_CONNECT_ACTIVE_STATES:
                return "kookplaat"

        return None

    def _get_smoothed_consumption_correction_ratio(self, current_hour: int) -> float:
        """How much higher (if at all) recent live consumption has been
        running compared to the learned average for this hour - based
        on the *median* of a short rolling window (see
        `_track_recent_consumption_reading`), not the mean, and capped
        at a reasonable maximum so one glitchy reading can't produce a
        wildly inflated estimate. Returns 1.0 (no correction) if there
        isn't enough data, or live consumption isn't actually running
        higher than usual.

        Median rather than mean: found in the field that a single brief
        high-power event (an oven or a "Quooker"-style instant hot water
        tap, drawing ~2000W for just a minute or two while its heating
        element cycles) could land inside one 5-minute sample and skew
        the *mean* of 4 samples enough to double the correction ratio -
        disproportionately inflating a multi-hour reserve estimate for
        an event that used a trivial amount of actual energy. The median
        of e.g. [400, 400, 400, 2000] W is 400 (the outlier is ignored
        outright); a *genuinely* sustained change (like the airco
        running continuously) still shows up once at least half the
        window reflects the new level.

        v0.63.78, reported ("Basisverbruik ... schiet tussen ca. 16:00
        en 17:00 omhoog door koken etc."): a *confirmed* heavy load
        (`last_heavy_load_source`) used to bypass this median smoothing
        entirely for every appliance in that list, trusting the latest
        single reading directly - reasonable for airco/slaapkamer
        (heating/cooling can genuinely run for hours), but wrong for the
        inherently short-duration ones (oven, kookplaat, vaatwasser,
        wasmachine, Quooker): trusting a live cooking-session reading
        directly, then using that to scale the *entire remaining
        ~17-hour* bridging estimate, massively overstated the deficit
        for an event that would be over within the hour. Only
        `SUSTAINED_HEAVY_LOAD_SOURCES` (airco/slaapkamer) still bypass
        the smoothing now; the short-duration appliances fall through to
        the same median-smoothed path as an unconfirmed reading.
        """
        if not self._recent_consumption_readings_kw:
            return 1.0

        current_hour_learned_kw = self.learned_hourly_avg_kw(current_hour)
        if not current_hour_learned_kw or current_hour_learned_kw <= 0:
            return 1.0

        if self.last_heavy_load_source in SUSTAINED_HEAVY_LOAD_SOURCES:
            # v0.63.78, reported: "Basisverbruik ... schiet tussen ca.
            # 16:00 en 17:00 omhoog door koken etc." - a known heavy
            # consumer is confirmed active right now (see
            # _get_confirmed_heavy_load_source), so there's no ambiguity
            # left to protect against re: whether it's a real appliance
            # or just sensor noise - BUT only airco/slaapkamer (heating/
            # cooling) genuinely represents a *sustained*, multi-hour
            # elevated consumption level worth scaling the *entire*
            # remaining bridging period by. Oven/kookplaat/vaatwasser/
            # wasmachine/Quooker are all inherently short-duration (a
            # cooking session typically lasts well under an hour) -
            # trusting their current reading directly to scale a
            # ~17-hour overnight estimate massively overstated the
            # deficit, exactly during the one window (mid-evening
            # cooking) most likely to also coincide with wanting to
            # decide whether to actively charge. Falls through to the
            # normal median-smoothed path below for those, same
            # protection as an unconfirmed reading.
            smoothed_live_kw = self._recent_consumption_readings_kw[-1]
        else:
            sorted_readings = sorted(self._recent_consumption_readings_kw)
            mid = len(sorted_readings) // 2
            if len(sorted_readings) % 2 == 0:
                smoothed_live_kw = (sorted_readings[mid - 1] + sorted_readings[mid]) / 2
            else:
                smoothed_live_kw = sorted_readings[mid]

        if smoothed_live_kw <= current_hour_learned_kw:
            return 1.0

        ratio = smoothed_live_kw / current_hour_learned_kw
        capped_ratio = min(ratio, MAX_CONSUMPTION_CORRECTION_RATIO)
        if capped_ratio < ratio:
            _LOGGER.debug(
                "Smoothed live consumption correction ratio %.1fx capped "
                "to %.1fx - an uncapped ratio this large is more likely a "
                "sensor glitch than a genuine sustained change",
                ratio,
                capped_ratio,
            )
        return capped_ratio

    def _read_corrected_consumption_power(self) -> float | None:
        """Household consumption estimate (W), corrected for the battery
        and (optionally) solar production masking the true load on the
        grid meter.

        The P1/grid meter only sees net grid exchange: while the battery
        discharges, or the sun produces, part (or all) of the household
        load is covered without the grid meter seeing it - so P1 alone
        understates true consumption. Conversely, battery charging adds
        extra draw that P1 sees but isn't household load. Correcting for
        this, using the full energy balance at the connection point:

            consumption = grid_power + battery_power + pv_power

        where battery_power follows the manual power number's sign
        convention (positive = discharging, negative = charging), and
        pv_power is the live PV production (always >= 0).

        Both battery_power and pv_power are optional refinements - if
        configured, they're added; if not (or unavailable), this falls
        back to a less precise estimate that ignores them.
        """
        p1_power = self._read_sensor_float(
            self.config.get(CONF_CONSUMPTION_POWER_SENSOR)
        )
        if p1_power is None:
            return None

        corrected = p1_power

        battery_entity = self.config.get(CONF_BATTERY_POWER_SENSOR)
        if battery_entity:
            battery_power = self._read_sensor_float(battery_entity)
            if battery_power is not None:
                if self.config.get(CONF_INVERT_BATTERY_POWER_SIGN, False):
                    battery_power = -battery_power
                corrected += battery_power

        pv_entity = self.config.get(CONF_PV_POWER_SENSOR)
        if pv_entity:
            pv_power = self._read_sensor_float(pv_entity)
            if pv_power is not None:
                corrected += pv_power

        return corrected

    # -- Night consumption learning ---------------------------------------

    def _update_night_consumption_tracking(
        self, now: datetime, in_window: bool
    ) -> None:
        """Sample the consumption sensor while inside the discharging window,
        and finalize + learn from the window once it ends.
        """
        if in_window:
            if self._tracking_window_end != self.last_cheap_block_start:
                # A new window has started (or this is the first tick):
                # finalize whatever was being tracked before, then reset.
                self._finalize_night_consumption_window()
                self._tracking_window_end = self.last_cheap_block_start
                self._window_energy_kwh = 0.0
                self._window_duration_hours = 0.0
                self._window_last_sample = now
                self._window_temp_samples = []
                return

            if self._window_last_sample is None:
                self._window_last_sample = now
                return

            elapsed_hours = max(
                (now - self._window_last_sample).total_seconds() / 3600, 0
            )
            power_w = self._read_corrected_consumption_power()
            if power_w is not None and elapsed_hours > 0:
                self._window_energy_kwh += (power_w / 1000) * elapsed_hours
                self._window_duration_hours += elapsed_hours
            # v0.63.88, temperatuur-verbruik-regressie (uitgebreid
            # besproken, "eerst observeren" - puur adviserend, stuurt
            # nog niets aan): buitentemperatuur meesamplen tijdens
            # hetzelfde venster als het verbruik, voor de latere
            # temperatuur-vs-verbruik-regressie.
            outdoor_temp_c = self._get_live_outdoor_temp_c(now)
            if outdoor_temp_c is not None:
                self._window_temp_samples.append(outdoor_temp_c)
            self._window_last_sample = now
        else:
            if self._tracking_window_end is not None:
                self._finalize_night_consumption_window()

    @staticmethod
    def _compute_trend_summary(history: list[float]) -> dict | None:
        """Statistisch de meest verdedigbare manier om een genuine trend
        in een korte, ruizige tijdreeks te detecteren (v0.63.88,
        gevraagd: inzicht of nieuwe modellen/parameters nauwkeuriger/
        stabieler worden over tijd) - een gewone kleinste-kwadraten-
        regressielijn door de (dagindex, waarde)-punten, in plaats van
        simpelweg de nieuwste met de oudste waarde te vergelijken (te
        gevoelig voor één toevallig ruizig datapunt aan een van beide
        uiteinden). Gebruikt alle beschikbare punten.

        Het gerapporteerde %-verschil is het verschil dat de GEFITTE
        lijn impliceert van begin tot eind van het venster - niet de
        rauwe eindpunten zelf, die nog steeds ruis kunnen bevatten.

        Retourneert None bij minder dan 3 punten (te weinig voor een
        zinvolle trendlijn).
        """
        n = len(history)
        if n < 3:
            return None

        xs = list(range(n))
        x_mean = sum(xs) / n
        y_mean = sum(history) / n
        denominator = sum((x - x_mean) ** 2 for x in xs)
        if denominator == 0:
            return None
        numerator = sum(
            (x - x_mean) * (y - y_mean) for x, y in zip(xs, history)
        )
        slope = numerator / denominator
        intercept = y_mean - slope * x_mean
        fitted_start = intercept
        fitted_end = intercept + slope * (n - 1)

        if fitted_start == 0:
            percent_change = None
            richting = "stabiel"
        else:
            percent_change = round(
                100 * (fitted_end - fitted_start) / abs(fitted_start), 1
            )
            if abs(percent_change) < 5:
                richting = "stabiel"
            elif percent_change > 0:
                richting = "stijgend"
            else:
                richting = "dalend"

        return {
            "richting": richting,
            "verschil_procent": percent_change,
        }

    def _finalize_night_consumption_window(self) -> None:
        if self._window_duration_hours > 0:
            avg_power_kw = self._window_energy_kwh / self._window_duration_hours
            self.night_consumption_history.append(avg_power_kw)
            self.night_consumption_history = self.night_consumption_history[
                -LEARNING_HISTORY_DAYS:
            ]
            _LOGGER.debug(
                "Finished tracking a discharging window: %.2f kWh over "
                "%.2fh (avg %.0fW). Learned history now: %s",
                self._window_energy_kwh,
                self._window_duration_hours,
                avg_power_kw * 1000,
                self.night_consumption_history,
            )
            self._finalize_temp_consumption_regression(
                self._window_temp_samples, self._window_energy_kwh
            )

        self._tracking_window_end = None
        self._window_energy_kwh = 0.0
        self._window_duration_hours = 0.0
        self._window_last_sample = None
        self._window_temp_samples = []

    @staticmethod
    def _ols_fit(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
        """Gewone kleinste-kwadraten-regressie (slope, intercept) door
        (x, y)-puntenparen - de generieke rekenkern, hergebruikt door
        de temperatuur-verbruik-regressie (v0.63.88). Retourneert None
        bij minder dan 2 punten of als alle x-waarden identiek zijn
        (geen variatie om een lijn doorheen te trekken).
        """
        n = len(xs)
        if n < 2 or n != len(ys):
            return None
        x_mean = sum(xs) / n
        y_mean = sum(ys) / n
        denominator = sum((x - x_mean) ** 2 for x in xs)
        if denominator == 0:
            return None
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
        slope = numerator / denominator
        intercept = y_mean - slope * x_mean
        return slope, intercept

    def _predict_temp_consumption_kwh(self, temp_c: float) -> float | None:
        """Verwacht nachtverbruik (kWh) bij een gegeven buitentemperatuur,
        op basis van de tot nu toe geleerde (temperatuur, verbruik)-
        paren. None zolang er nog niet genoeg geschiedenis is
        (TEMP_CONSUMPTION_MIN_SAMPLES).
        """
        if len(self.temp_consumption_history) < TEMP_CONSUMPTION_MIN_SAMPLES:
            return None
        xs = [pair["temp_c"] for pair in self.temp_consumption_history]
        ys = [pair["kwh"] for pair in self.temp_consumption_history]
        fit = self._ols_fit(xs, ys)
        if fit is None:
            return None
        slope, intercept = fit
        return intercept + slope * temp_c

    def _finalize_temp_consumption_regression(
        self, temp_samples: list[float], window_energy_kwh: float
    ) -> None:
        """Temperatuur-verbruik-regressie voor extreme-koude-dagen
        (v0.63.88, uitgebreid besproken en ontworpen door de gebruiker
        na een analyse van 11 januari 2026 - het koudste etmaal van het
        jaar). Puur adviserend ("eerst observeren" - expliciet zo
        afgesproken): toont een verwachte-verbruik-schatting en of die
        schatting nauwkeuriger wordt over tijd, maar beïnvloedt de
        bestaande reserve-/dieptekort-berekening nog op geen enkele
        manier.

        Validatie-volgorde is bewust belangrijk: eerst wordt met de
        REEDS BESTAANDE geschiedenis (dus zonder de zojuist afgeronde
        nacht) voorspeld wat déze nacht had moeten kosten, en pas
        daarna wordt de nieuwe (temperatuur, verbruik)-paar toegevoegd -
        zo meet de nauwkeurigheids-geschiedenis een eerlijke,
        niet-lekkende validatie (voorspellen met wat toen al bekend
        was), niet een achteraf-passende schijnnauwkeurigheid.
        """
        if not temp_samples:
            self.last_temp_consumption_note = (
                "Geen buitentemperatuurmeting beschikbaar tijdens dit "
                "venster - geen sample toegevoegd."
            )
            return

        avg_temp_c = sum(temp_samples) / len(temp_samples)

        predicted_kwh = self._predict_temp_consumption_kwh(avg_temp_c)
        if predicted_kwh is not None and predicted_kwh > 0:
            error_percent = round(
                100 * (window_energy_kwh - predicted_kwh) / predicted_kwh, 1
            )
            self.temp_consumption_prediction_error_history.append(abs(error_percent))
            self.temp_consumption_prediction_error_history = (
                self.temp_consumption_prediction_error_history[-LEARNING_HISTORY_DAYS:]
            )
            self.last_temp_consumption_note = (
                f"Voorspeld {predicted_kwh:.2f} kWh bij {avg_temp_c:.1f}°C, "
                f"werkelijk {window_energy_kwh:.2f} kWh "
                f"(afwijking {error_percent:+.1f}%)."
            )
        else:
            self.last_temp_consumption_note = (
                f"Nog niet genoeg geschiedenis ({len(self.temp_consumption_history)}/"
                f"{TEMP_CONSUMPTION_MIN_SAMPLES}) voor een voorspelling deze nacht."
            )

        self.temp_consumption_history.append(
            {"temp_c": round(avg_temp_c, 1), "kwh": round(window_energy_kwh, 2)}
        )
        self.temp_consumption_history = self.temp_consumption_history[
            -LEARNING_HISTORY_DAYS:
        ]



    # -- Full-day hourly consumption profile ------------------------------

    def _update_hourly_consumption_profile(self, now: datetime) -> None:
        """Sample the corrected consumption continuously, all day every
        day, bucketed by hour-of-day (0-23). Unlike the discharge-window
        tracking above, this always runs regardless of mode, so the
        integration builds a full daily profile - useful in autumn/winter
        when the relevant bridging period may extend into daytime hours.
        """
        current_hour = now.hour

        if self._current_tracked_hour is None:
            self._current_tracked_hour = current_hour
            self._hour_last_sample = now
            return

        # A gap bigger than a normal update tick means either a restart
        # that lost the in-memory tracker (restored to a stale timestamp
        # - see HourlyConsumptionProfileSensor.async_added_to_hass,
        # v0.63.16) or a genuine outage. Either way, the elapsed time
        # can't be reliably attributed to a single power level - discard
        # the partial hour instead of polluting the average with it.
        if self._hour_last_sample is not None:
            gap_minutes = (now - self._hour_last_sample).total_seconds() / 60
            if gap_minutes > MAX_HOUR_TRACKING_GAP_MINUTES:
                self._hour_energy_kwh = 0.0
                self._hour_duration_hours = 0.0
                self._current_tracked_hour = current_hour
                self._hour_last_sample = now
                return

        power_w = self._read_corrected_consumption_power()

        if current_hour != self._current_tracked_hour:
            # Split the elapsed interval exactly at the hour boundary, so
            # the last few minutes before the transition are still
            # credited to the hour that's ending (instead of being lost).
            hour_boundary = now.replace(minute=0, second=0, microsecond=0)
            if self._hour_last_sample is not None and power_w is not None:
                elapsed_to_boundary = max(
                    (hour_boundary - self._hour_last_sample).total_seconds() / 3600, 0
                )
                self._hour_energy_kwh += (power_w / 1000) * elapsed_to_boundary
                self._hour_duration_hours += elapsed_to_boundary

            self._finalize_hourly_bucket()
            self._current_tracked_hour = current_hour

            elapsed_in_new_hour = max(
                (now - hour_boundary).total_seconds() / 3600, 0
            )
            if power_w is not None and elapsed_in_new_hour > 0:
                self._hour_energy_kwh = (power_w / 1000) * elapsed_in_new_hour
                self._hour_duration_hours = elapsed_in_new_hour
            else:
                self._hour_energy_kwh = 0.0
                self._hour_duration_hours = 0.0
            self._hour_last_sample = now
            return

        elapsed_hours = max((now - self._hour_last_sample).total_seconds() / 3600, 0)
        if power_w is not None and elapsed_hours > 0:
            self._hour_energy_kwh += (power_w / 1000) * elapsed_hours
            self._hour_duration_hours += elapsed_hours
        self._hour_last_sample = now

    def _finalize_hourly_bucket(self) -> None:
        if self._current_tracked_hour is not None and self._hour_duration_hours > 0:
            avg_power_kw = self._hour_energy_kwh / self._hour_duration_hours
            bucket = self.hourly_consumption_profile.setdefault(
                self._current_tracked_hour, []
            )
            bucket.append(avg_power_kw)
            self.hourly_consumption_profile[self._current_tracked_hour] = bucket[
                -LEARNING_HISTORY_DAYS:
            ]

        self._hour_energy_kwh = 0.0
        self._hour_duration_hours = 0.0

    def learned_hourly_avg_kw(self, hour: int) -> float | None:
        """Learned power (kW) for a given hour-of-day (0-23), as the
        *median* of the last LEARNING_HISTORY_DAYS daily averages - not
        the mean (v0.62.0). A single unusual day (e.g. the washing
        machine running three loads back-to-back) shouldn't meaningfully
        move a 7-day baseline; with a mean it still gets a 1/7 vote every
        day until it ages out a week later, while the median effectively
        ignores it outright unless it becomes the new normal (needs a
        majority of the window to agree). Genuine sustained shifts still
        come through once enough of the recent days reflect them - and
        the separate shortfall self-correction (margin bonus) already
        protects against the median trailing a real change too slowly.
        """
        values = self.hourly_consumption_profile.get(hour)
        if not values:
            return None
        return statistics.median(values)

    def previous_hourly_avg_kw(self, hour: int) -> float | None:
        """The learned value for this hour as it was *before* the most
        recent sample came in - i.e. excluding the last sample. Used to
        show a "previous vs current" trend on the dashboard for what is
        otherwise a continuously-updating rolling median with no single
        "previous value" of its own. None if there are fewer than 2
        samples (nothing meaningful to compare against yet).
        """
        values = self.hourly_consumption_profile.get(hour)
        if not values or len(values) < 2:
            return None
        previous_values = values[:-1]
        return statistics.median(previous_values)

    def _vacation_adjusted_kwh(self, kwh: float) -> float:
        """Scale down an estimated consumption amount while vacation mode
        is on - see the 'Vacation consumption reduction (%)' option.
        No-op when vacation mode is off.
        """
        if not self.vacation_mode:
            return kwh
        reduction_percent = float(
            self.config.get(
                CONF_VACATION_CONSUMPTION_REDUCTION_PERCENT,
                DEFAULT_VACATION_CONSUMPTION_REDUCTION_PERCENT,
            )
        )
        return kwh * (1 - reduction_percent / 100)

    def _estimate_consumption_kwh_for_period(
        self, start: datetime, end: datetime
    ) -> float | None:
        """Estimate total household energy consumption (kWh) over a period,
        using the learned per-hour profile - so it reflects the actual
        time-of-day mix (e.g. partly daytime in winter), instead of a
        single flat average.

        Corrected with a live-consumption scaling factor: if what's
        actually being drawn right now is higher than the learned average
        for this hour (e.g. the airco is running tonight), the whole
        remaining estimate is scaled up proportionally - a tonight-only
        spike wouldn't otherwise show up until it's baked into tomorrow's
        learned average, by which point it's too late to protect the
        reserve for this same night.

        Returns None if the profile doesn't yet have data for every hour
        the period spans, so the caller can fall back to a simpler
        estimate.
        """
        if end <= start:
            return 0.0

        total_kwh = 0.0
        cursor = start
        while cursor < end:
            hour_end = cursor.replace(minute=0, second=0, microsecond=0) + timedelta(
                hours=1
            )
            segment_end = min(hour_end, end)
            fraction_hours = (segment_end - cursor).total_seconds() / 3600

            avg_kw = self.learned_hourly_avg_kw(cursor.hour)
            if avg_kw is None:
                return None

            total_kwh += avg_kw * fraction_hours
            cursor = segment_end

        correction_ratio = self._get_smoothed_consumption_correction_ratio(start.hour)
        if correction_ratio != 1.0:
            _LOGGER.debug(
                "Smoothed live consumption correction: %.1fx - scaling up "
                "the remaining consumption estimate accordingly",
                correction_ratio,
            )
            total_kwh *= correction_ratio

        return self._vacation_adjusted_kwh(total_kwh)

    # -- Solcast hourly PV production forecast -----------------------------

    def _get_pv_forecast_entries(self) -> list[tuple[datetime, datetime, float]]:
        """Parse the Solcast "detailedForecast" attribute (today + tomorrow
        sensors, if configured) into a merged, chronologically sorted list
        of (start, end, kwh) tuples - the expected PV production for each
        half-hour interval.

        Solcast's `pv_estimate` is an average power in kW for that
        interval; multiplied by the interval's duration (in hours) to get
        the energy (kWh) produced during it.
        """
        entries: list[tuple[datetime, datetime, float]] = []

        for entity_id in (
            self.config.get(CONF_SOLAR_TODAY_FORECAST_SENSOR),
            self.config.get(CONF_SOLAR_FORECAST_SENSOR),
        ):
            if not entity_id:
                continue
            state = self.hass.states.get(entity_id)
            if state is None:
                continue
            items = state.attributes.get("detailedForecast") or state.attributes.get(
                "detailedHourly"
            )
            if not items:
                continue

            for item in items:
                period_start = item.get("period_start")
                pv_estimate_kw = item.get("pv_estimate")
                if period_start is None or pv_estimate_kw is None:
                    continue
                if not isinstance(period_start, datetime):
                    # Defensive: some setups might expose this as a string.
                    period_start = dt_util.parse_datetime(str(period_start))
                    if period_start is None:
                        continue
                if period_start.tzinfo is None:
                    period_start = period_start.replace(tzinfo=dt_util.UTC)
                period_start = dt_util.as_local(period_start)

                try:
                    pv_estimate_kw = float(pv_estimate_kw)
                except (TypeError, ValueError):
                    continue

                entries.append((period_start, pv_estimate_kw))

        if not entries:
            return []

        entries.sort(key=lambda e: e[0])

        # Derive each interval's end from the next entry's start (assume
        # the last one has the same duration as the previous interval).
        result: list[tuple[datetime, datetime, float]] = []
        for i, (start, pv_kw) in enumerate(entries):
            if i + 1 < len(entries):
                end = entries[i + 1][0]
            else:
                # Fall back to the typical interval length seen so far.
                prev_duration = (
                    result[-1][1] - result[-1][0] if result else timedelta(minutes=30)
                )
                end = start + prev_duration
            duration_hours = max((end - start).total_seconds() / 3600, 0)
            result.append((start, end, pv_kw * duration_hours))

        return result

    def _get_expected_pv_power_w(self, now: datetime) -> float | None:
        """Expected PV power (W) for this exact moment, from the Solcast
        `detailedForecast` (v0.63.71, requested: "hij kijkt naar het
        live PV opbrengst en niet naar de verwachtte zon"). Corrected by,
        in order of preference: (1) the live "remaining PV today"
        real-time correction ratio (v0.63.104, see
        `_get_pv_remaining_correction_ratio`'s docstring - reflects
        Solcast's own actually-observed-conditions adjustment for
        TODAY specifically), falling back to (2) the slower,
        long-term-learned per-hour Solcast bias ratio
        (`learned_pv_hourly_ratio`) if today's live correction isn't
        available.

        v0.63.104, gerapporteerd: "dit komt niet overeen met de
        werkelijkheid... het overschot is veel groter op dit moment" -
        deze functie gebruikte tot dan toe UITSLUITEND de trage,
        langetermijn-geleerde ratio, terwijl de tekortberekening
        elders (`_estimate_pv_kwh_for_period`) AL de veel actuelere,
        vandaag-specifieke live-correctie gebruikte - een inconsistentie
        tussen twee PV-schattingsfuncties in dezelfde codebase.  Op een
        dag die zonniger is dan het langetermijngemiddelde voor dit
        uur, gaf de oude aanpak stelselmatig een te lage verwachting -
        precies het gerapporteerde symptoom.

        Reported: a passing cloud momentarily dipping the *live* PV
        reading was flip-flopping the arbitrage/solar-capture decision
        between smart and manual every few minutes (2668W -> 1707W in 7
        minutes). Forecast-based instead of live-instantaneous is
        deliberately much more stable - it reflects what the sun is
        expected to do this half-hour on average, not a momentary dip,
        at the cost of not reacting to a genuinely sustained weather
        change until the next forecast interval. Returns None if no
        solar forecast sensor is configured, or "now" falls outside all
        known forecast intervals (e.g. it's night).
        """
        pv_entries = self._get_pv_forecast_entries()
        for start, end, kwh in pv_entries:
            if start <= now < end:
                duration_hours = (end - start).total_seconds() / 3600
                if duration_hours <= 0:
                    return None
                raw_kw = kwh / duration_hours
                remaining_ratio = self._get_pv_remaining_correction_ratio(
                    now, pv_entries
                )
                if remaining_ratio is not None:
                    corrected_kw = raw_kw * remaining_ratio
                else:
                    bias_ratio = self.learned_pv_hourly_ratio(now.hour)
                    corrected_kw = (
                        raw_kw * bias_ratio if bias_ratio is not None else raw_kw
                    )
                return max(0.0, corrected_kw * 1000)
        return None

    def _get_pv_remaining_correction_ratio(
        self, now: datetime, pv_entries: list[tuple[datetime, datetime, float]]
    ) -> float | None:
        """Compare the live "remaining PV today" Solcast sensor against the
        sum of our own detailedForecast entries for the rest of today, to
        derive a real-time correction ratio.

        This sensor is continuously updated by Solcast based on actually
        observed conditions (it counts down through the day), so it
        reflects "reality" more directly than the static detailedForecast
        snapshot. Using it as a scaling ratio lets today's estimate
        benefit from that live correction, while still being able to
        properly slice partial-day periods (which the raw sensor value
        alone can't do, since it only covers "all of the rest of today",
        not an arbitrary sub-window).
        """
        remaining_entity = self.config.get(CONF_SOLAR_REMAINING_TODAY_SENSOR)
        if not remaining_entity:
            return None

        remaining_value = self._read_sensor_float(remaining_entity)
        if remaining_value is None:
            return None

        today = now.date()
        today_end = datetime.combine(
            today, datetime.min.time(), tzinfo=now.tzinfo
        ) + timedelta(days=1)

        sum_today_remaining = 0.0
        for entry_start, entry_end, entry_kwh in pv_entries:
            if entry_start.date() != today or entry_end <= now:
                continue
            overlap_start = max(entry_start, now)
            overlap_end = min(entry_end, today_end)
            if overlap_end <= overlap_start:
                continue
            entry_duration = (entry_end - entry_start).total_seconds()
            if entry_duration <= 0:
                continue
            fraction = (overlap_end - overlap_start).total_seconds() / entry_duration
            sum_today_remaining += entry_kwh * fraction

        if sum_today_remaining <= 0.01:
            return None

        return remaining_value / sum_today_remaining

    def _estimate_pv_kwh_for_period(self, start: datetime, end: datetime) -> float:
        """Estimate expected PV production (kWh) over a period, from the
        Solcast hourly/half-hourly forecast.

        Today's portion is preferentially scaled using the live "remaining
        PV today" sensor (see `_get_pv_remaining_correction_ratio`), if
        configured - this benefits from Solcast's own real-time
        adjustment based on actual observed conditions. Any portion beyond
        today (e.g. tomorrow) falls back to the learned per-hour accuracy
        ratio, then the flatter daily forecast bias, then no correction.

        Returns 0.0 if no PV forecast sensor is configured or no data
        covers the period (i.e. "assume no solar" - the previous, more
        conservative behaviour).
        """
        if end <= start:
            return 0.0

        pv_entries = self._get_pv_forecast_entries()
        if not pv_entries:
            return 0.0

        daily_bias_percent = (
            self.solar_tracker.learned_bias_percent if self.solar_tracker else None
        )
        remaining_correction_ratio = self._get_pv_remaining_correction_ratio(
            start, pv_entries
        )
        today = start.date()

        total_kwh = 0.0
        for entry_start, entry_end, entry_kwh in pv_entries:
            overlap_start = max(entry_start, start)
            overlap_end = min(entry_end, end)
            if overlap_end <= overlap_start:
                continue
            entry_duration = (entry_end - entry_start).total_seconds()
            if entry_duration <= 0:
                continue
            overlap_fraction = (
                overlap_end - overlap_start
            ).total_seconds() / entry_duration
            segment_kwh = entry_kwh * overlap_fraction

            if entry_start.date() == today and remaining_correction_ratio is not None:
                segment_kwh *= remaining_correction_ratio
            else:
                hourly_ratio = self.learned_pv_hourly_ratio(entry_start.hour)
                if hourly_ratio is not None:
                    segment_kwh *= hourly_ratio
                elif daily_bias_percent is not None:
                    segment_kwh *= 1 + daily_bias_percent / 100

            total_kwh += segment_kwh

        return max(0.0, total_kwh)

    def _get_efficiency_discounted_pv_offset(
        self, start: datetime, end: datetime
    ) -> float:
        """Expected PV production for a period, discounted by the
        battery's round-trip efficiency - used specifically when this
        expected solar is being used to *offset* how much reserve/grid
        energy is needed.

        Solar that covers household load directly doesn't lose anything,
        but any of it routed through the battery (charged now, discharged
        later) loses some energy to round-trip conversion losses before
        it's usable again. Since we can't cleanly separate "direct" from
        "battery-routed" solar without a much more detailed simulation,
        applying the efficiency factor to the whole expected PV amount is
        a deliberately conservative simplification - slightly
        underestimates how much solar helps, rather than overestimating
        it (which would mean reserving less than actually needed).

        Prefers the self-learned efficiency (see
        `learned_battery_efficiency_percent`) once enough real
        charge/discharge samples exist, falling back to the configured
        guess otherwise.
        """
        expected_pv_kwh = self._estimate_pv_kwh_for_period(start, end)
        efficiency_percent = self.learned_battery_efficiency_percent
        if efficiency_percent is None:
            efficiency_percent = float(
                self.config.get(
                    CONF_BATTERY_ROUND_TRIP_EFFICIENCY,
                    DEFAULT_BATTERY_ROUND_TRIP_EFFICIENCY_PERCENT,
                )
            )
        return expected_pv_kwh * (efficiency_percent / 100)

    def _estimate_worst_case_deficit_kwh(
        self, start: datetime, end: datetime
    ) -> float | None:
        """The deepest cumulative shortfall reached at any point between
        start and end, hour by hour - not just the net balance at the
        end of the period.

        A simple net total (consumption - PV) over the whole bridging
        window can look fine on paper while still hiding a real overnight
        shortfall: solar credit is concentrated in daylight hours, so a
        big expected PV total for tomorrow doesn't help *tonight*, before
        it arrives. Walking hour by hour and tracking the running
        cumulative deficit (clamped at 0 - surplus daytime PV can't
        retroactively cover an earlier night's shortfall) finds the
        actual worst moment, typically just before sunrise, which is
        what the reserve genuinely needs to protect against.

        Returns None if the hourly consumption profile doesn't have data
        for every hour the period spans, so the caller can fall back to
        a simpler estimate.
        """
        if end <= start:
            return 0.0

        efficiency_percent = self.learned_battery_efficiency_percent
        if efficiency_percent is None:
            efficiency_percent = float(
                self.config.get(
                    CONF_BATTERY_ROUND_TRIP_EFFICIENCY,
                    DEFAULT_BATTERY_ROUND_TRIP_EFFICIENCY_PERCENT,
                )
            )
        efficiency_factor = efficiency_percent / 100

        # Live-consumption correction (same principle as
        # _estimate_consumption_kwh_for_period): if what's actually being
        # drawn right now is higher than the learned average for this
        # hour (e.g. the airco is running tonight), scale every hour's
        # consumption estimate in this walk-through by the same ratio -
        # a live spike is applied for the whole remaining window, not
        # just silently averaged away by historical data. This is what
        # makes the worst-case reserve responsive to what's actually
        # happening tonight, not just what usually happens. Smoothed
        # over a short rolling window and capped (see
        # _get_smoothed_consumption_correction_ratio) so a brief spike
        # can't scale a 15+ hour estimate to an absurd value.
        consumption_correction_ratio = self._get_smoothed_consumption_correction_ratio(
            start.hour
        )

        cumulative_deficit = 0.0
        max_deficit = 0.0
        cursor = start
        while cursor < end:
            hour_end = cursor.replace(minute=0, second=0, microsecond=0) + timedelta(
                hours=1
            )
            segment_end = min(hour_end, end)
            fraction_hours = (segment_end - cursor).total_seconds() / 3600

            avg_kw = self.learned_hourly_avg_kw(cursor.hour)
            if avg_kw is None:
                return None

            consumption_kwh = self._vacation_adjusted_kwh(
                avg_kw * fraction_hours * consumption_correction_ratio
            )
            pv_kwh = (
                self._estimate_pv_kwh_for_period(cursor, segment_end)
                * efficiency_factor
            )

            cumulative_deficit = max(0.0, cumulative_deficit + consumption_kwh - pv_kwh)
            max_deficit = max(max_deficit, cumulative_deficit)
            cursor = segment_end

        return max_deficit

    def _get_forecast_kwh_for_hour(self, target_date, hour: int) -> float | None:
        """Sum the Solcast-forecasted kWh for a specific hour on a
        specific date, from the currently available forecast entries.
        Returns None if no forecast data covers that hour.
        """
        pv_entries = self._get_pv_forecast_entries()
        if not pv_entries:
            return None

        hour_start = datetime.combine(target_date, datetime.min.time()).replace(
            hour=hour, tzinfo=pv_entries[0][0].tzinfo
        )
        hour_end = hour_start + timedelta(hours=1)

        total = 0.0
        found = False
        for entry_start, entry_end, entry_kwh in pv_entries:
            overlap_start = max(entry_start, hour_start)
            overlap_end = min(entry_end, hour_end)
            if overlap_end <= overlap_start:
                continue
            entry_duration = (entry_end - entry_start).total_seconds()
            if entry_duration <= 0:
                continue
            fraction = (overlap_end - overlap_start).total_seconds() / entry_duration
            total += entry_kwh * fraction
            found = True

        return total if found else None

    def _update_pv_hourly_bias_tracking(self, now: datetime) -> None:
        """Sample actual PV production continuously, all day, and compare
        each completed hour's actual output against what was forecasted
        for that hour - learning a per-hour-of-day accuracy ratio.
        """
        pv_entity = self.config.get(CONF_PV_POWER_SENSOR)
        if not pv_entity:
            return

        current_hour = now.hour

        if self._pv_current_tracked_hour is None:
            self._pv_current_tracked_hour = current_hour
            self._pv_hour_last_sample = now
            return

        # Same staleness guard as _update_hourly_consumption_profile.
        if self._pv_hour_last_sample is not None:
            gap_minutes = (now - self._pv_hour_last_sample).total_seconds() / 60
            if gap_minutes > MAX_HOUR_TRACKING_GAP_MINUTES:
                self._pv_hour_energy_kwh = 0.0
                self._pv_hour_duration_hours = 0.0
                self._pv_current_tracked_hour = current_hour
                self._pv_hour_last_sample = now
                return

        pv_power_w = self._read_sensor_float(pv_entity)

        if current_hour != self._pv_current_tracked_hour:
            # Split the elapsed interval exactly at the hour boundary (see
            # _update_hourly_consumption_profile for the same fix/rationale).
            hour_boundary = now.replace(minute=0, second=0, microsecond=0)
            if self._pv_hour_last_sample is not None and pv_power_w is not None:
                elapsed_to_boundary = max(
                    (hour_boundary - self._pv_hour_last_sample).total_seconds()
                    / 3600,
                    0,
                )
                self._pv_hour_energy_kwh += (pv_power_w / 1000) * elapsed_to_boundary
                self._pv_hour_duration_hours += elapsed_to_boundary

            self._finalize_pv_hourly_bucket(now)
            self._pv_current_tracked_hour = current_hour

            elapsed_in_new_hour = max(
                (now - hour_boundary).total_seconds() / 3600, 0
            )
            if pv_power_w is not None and elapsed_in_new_hour > 0:
                self._pv_hour_energy_kwh = (pv_power_w / 1000) * elapsed_in_new_hour
                self._pv_hour_duration_hours = elapsed_in_new_hour
            else:
                self._pv_hour_energy_kwh = 0.0
                self._pv_hour_duration_hours = 0.0
            self._pv_hour_last_sample = now
            return

        elapsed_hours = max(
            (now - self._pv_hour_last_sample).total_seconds() / 3600, 0
        )
        if pv_power_w is not None and elapsed_hours > 0:
            self._pv_hour_energy_kwh += (pv_power_w / 1000) * elapsed_hours
            self._pv_hour_duration_hours += elapsed_hours
        self._pv_hour_last_sample = now

    def _finalize_pv_hourly_bucket(self, now: datetime) -> None:
        if self._pv_current_tracked_hour is not None and self._pv_hour_duration_hours > 0:
            actual_kwh = self._pv_hour_energy_kwh
            # The hour that just completed is the previous local hour,
            # on the date it happened on (usually today, but handles the
            # 23:00 -> 00:00 rollover correctly too).
            completed_hour_date = (now - timedelta(hours=1)).date()
            forecast_kwh = self._get_forecast_kwh_for_hour(
                completed_hour_date, self._pv_current_tracked_hour
            )
            if forecast_kwh is not None and forecast_kwh > 0.01:
                ratio = actual_kwh / forecast_kwh
                bucket = self.pv_hourly_bias_history.setdefault(
                    self._pv_current_tracked_hour, []
                )
                bucket.append(ratio)
                self.pv_hourly_bias_history[self._pv_current_tracked_hour] = bucket[
                    -LEARNING_HISTORY_DAYS:
                ]
                _LOGGER.debug(
                    "PV hour %d: actual=%.3f kWh, forecast=%.3f kWh, "
                    "ratio=%.2f. Learned history: %s",
                    self._pv_current_tracked_hour,
                    actual_kwh,
                    forecast_kwh,
                    ratio,
                    self.pv_hourly_bias_history[self._pv_current_tracked_hour],
                )

        self._pv_hour_energy_kwh = 0.0
        self._pv_hour_duration_hours = 0.0

    def learned_pv_hourly_ratio(self, hour: int) -> float | None:
        """Learned (actual/forecast) ratio for a given hour-of-day (0-23),
        used for actual decisions/display. 1.0 = forecast matches reality,
        <1.0 = Solcast over-forecasts that hour, >1.0 = under-forecasts it.
        None if there isn't yet enough history to be confident (see
        MIN_SOLAR_HISTORY_FOR_DYNAMIC_THRESHOLD).

        Median rather than mean (v0.62.0), same rationale as
        `learned_hourly_avg_kw`: a single passing rain cloud during an
        otherwise sunny forecast shouldn't meaningfully move a 7-day
        baseline. Genuine seasonal drift is slow enough that a few days'
        lag in the median catching up doesn't matter in practice.

        For persistence across restarts, use `raw_pv_hourly_avg` instead -
        gating persistence on this same confidence threshold would mean
        any hour with 1-2 samples (not yet "confident") never gets saved
        at all, silently losing all partial progress on every restart.
        """
        values = self.pv_hourly_bias_history.get(hour)
        if not values or len(values) < MIN_SOLAR_HISTORY_FOR_DYNAMIC_THRESHOLD:
            return None
        return statistics.median(values)

    def previous_pv_hourly_ratio(self, hour: int) -> float | None:
        """The learned ratio for this hour as it was *before* the most
        recent sample came in - same principle as
        `previous_hourly_avg_kw`, for the "previous vs current" trend
        display. None if there are fewer than 2 samples.
        """
        values = self.pv_hourly_bias_history.get(hour)
        if not values or len(values) < 2:
            return None
        previous_values = values[:-1]
        return statistics.median(previous_values)

    def raw_pv_hourly_avg(self, hour: int) -> float | None:
        """Same value as `learned_pv_hourly_ratio` (median, v0.62.0), but
        without the minimum-sample-count gate - returns a value as soon
        as there's at least one sample. Used for persistence, so partial
        progress (1-2 samples) survives a restart instead of being
        silently discarded.
        """
        values = self.pv_hourly_bias_history.get(hour)
        if not values:
            return None
        return statistics.median(values)

    def _get_dynamic_discharge_reserve_kwh(
        self, now: datetime, cheap_block_start: datetime | None
    ) -> float | None:
        """How much energy (kWh) actually needs to stay in the battery
        right now: the estimated baseline household consumption until the
        cheap block, minus expected PV production over that period, plus
        a safety margin - instead of a flat SoC percentage.

        This deliberately does NOT also add a reservation for other
        upcoming expensive quarters today (unlike the energy bridge
        check's needed_kwh) - that reservation governs whether to
        postpone *charging*, whereas this governs how far we can safely
        *discharge* right now without dipping below what's needed for the
        rest of the bridge. Each expensive quarter checks this
        independently as it arrives.

        Returns None if there isn't enough information to compute this
        (no cheap block found, or no consumption estimate available) -
        callers should fall back to the flat SoC percentage in that case.
        """
        if cheap_block_start is None or now >= cheap_block_start:
            return None

        hours_until_cheap = max((cheap_block_start - now).total_seconds() / 3600, 0)
        if hours_until_cheap <= 0:
            return None

        needed_kwh = self._estimate_worst_case_deficit_kwh(now, cheap_block_start)
        if needed_kwh is None:
            needed_kwh = self._estimate_consumption_kwh_for_period(
                now, cheap_block_start
            )
            if needed_kwh is None:
                learned_kw = self.learned_night_consumption_kw
                if learned_kw is not None:
                    power_kw = learned_kw
                else:
                    power_w = self._read_corrected_consumption_power()
                    power_kw = power_w / 1000 if power_w is not None else None
                if power_kw is None:
                    return None
                needed_kwh = power_kw * hours_until_cheap

            expected_pv_kwh = self._get_efficiency_discounted_pv_offset(
                now, cheap_block_start
            )
            needed_kwh = max(0.0, needed_kwh - expected_pv_kwh)

        # Scale up the margin if an extended low-solar stretch is ahead -
        # less confidence the battery gets refilled quickly, so keep more
        # in reserve. consecutive_low_solar_days=0 -> base margin only;
        # each additional day adds a bonus. No separate artificial cap -
        # this is naturally bounded by how many extended-day forecast
        # sensors are actually configured (real data availability).
        consecutive_low_solar_days = self._count_consecutive_upcoming_low_solar_days()
        low_solar_bonus_percent = (
            consecutive_low_solar_days * EXTENDED_LOW_SOLAR_MARGIN_BONUS_PER_DAY
        )

        # Also learn from recent reality: if unexpected grid import kept
        # happening during periods we believed were self-sufficient, the
        # reserve has been running too tight - add a bonus proportional to
        # how often that's happened in the last LEARNING_HISTORY_DAYS.
        recent_shortfalls = sum(1 for v in self.reserve_shortfall_history if v)
        shortfall_bonus_percent = (
            recent_shortfalls * SHORTFALL_MARGIN_BONUS_PER_RECENT_DAY
        )

        # And the counterbalance: if the reserve has been running way
        # more conservative than needed (excess energy left over while
        # still postponing charging), reduce the margin - otherwise it
        # could only ever ratchet upward and get stuck too cautious,
        # missing out on legitimate selling opportunities.
        recent_excess_days = sum(1 for v in self.reserve_excess_history if v)
        excess_reduction_percent = (
            recent_excess_days * EXCESS_MARGIN_REDUCTION_PER_RECENT_DAY
        )

        # Structural extra buffer: once an expensive-quarter discharge
        # ends, control passes to 'smart' mode, where the Zendure's own
        # logic decides how much more to discharge for household use -
        # completely outside our reserve protection. We can sell down to
        # the reserve floor safely *during* the expensive quarter itself,
        # but can't stop the battery being drawn further below that floor
        # afterwards. This extra margin compensates for that structural
        # blind spot (found after a real incident: ~6.5 kWh was correctly
        # sold to the reserve floor, then the unprotected night finished
        # the job and ran the battery to empty).
        margin_bonus_percent = max(
            MIN_TOTAL_MARGIN_BONUS_PERCENT,
            low_solar_bonus_percent
            + shortfall_bonus_percent
            - excess_reduction_percent
            + UNPROTECTED_AFTERMATH_MARGIN_PERCENT,
        )
        margin = DYNAMIC_DISCHARGE_RESERVE_MARGIN + margin_bonus_percent / 100

        self.last_reserve_margin_breakdown = {
            "base_percent": round((DYNAMIC_DISCHARGE_RESERVE_MARGIN - 1) * 100, 1),
            "low_solar_bonus_percent": round(low_solar_bonus_percent, 1),
            "consecutive_low_solar_days": consecutive_low_solar_days,
            "shortfall_bonus_percent": round(shortfall_bonus_percent, 1),
            "recent_shortfall_days": recent_shortfalls,
            "excess_reduction_percent": round(excess_reduction_percent, 1),
            "recent_excess_days": recent_excess_days,
            "unprotected_aftermath_percent": round(
                UNPROTECTED_AFTERMATH_MARGIN_PERCENT, 1
            ),
            "total_percent": round((margin - 1) * 100, 1),
            "needed_kwh_before_margin": round(needed_kwh, 3),
            "reserve_kwh_after_margin": round(needed_kwh * margin, 3),
        }

        if margin_bonus_percent != 0:
            _LOGGER.debug(
                "Discharge reserve margin: base %.0f%% + %.0f%% (low-solar, "
                "%d day(s)) + %.0f%% (%d shortfall day(s)) - %.0f%% "
                "(%d excess day(s)) = %.0f%%",
                (DYNAMIC_DISCHARGE_RESERVE_MARGIN - 1) * 100,
                low_solar_bonus_percent,
                consecutive_low_solar_days,
                shortfall_bonus_percent,
                recent_shortfalls,
                excess_reduction_percent,
                recent_excess_days,
                (margin - 1) * 100,
            )

        return needed_kwh * margin

    def _should_capture_solar_instead_of_postponing(
        self, now: datetime, should_postpone_charging: bool
    ) -> bool:
        """v0.63.77, final confirmed decision after several rounds of
        real-world reports ("Manueel laden mag nooit als er later tegen
        dure uren wordt ontladen" / "winst gevende marge achterwege
        laten, gewoon smart opladen"): the entire "actively buy from the
        grid because a later, more expensive quarter makes it
        profitable" mechanism (arbitrage-laden, v0.63.15-.76) is removed
        completely. Confirmed explicitly: even when the reserve is
        genuinely insufficient to bridge the night, this function must
        NEVER trigger an active grid purchase any more - only the
        existing, separate `should_force_charge` (low solar expected
        during the cheap block) and `_is_emergency_low_battery` (SoC
        critically low) mechanisms remain as the safety net for a
        genuine shortfall, through their own, different criteria.
        Reasoning: for this installation's battery capacity, energy
        bought "for profit" never actually gets resold at a genuine
        profit in practice - it just ends up covering the night's own
        household load anyway, making the whole profit/margin framing
        moot.

        The only thing left of the original mechanism: don't let
        already-available solar surplus go to waste. Whenever
        `should_postpone_charging` is True (there's already enough
        reserve to bridge the night) and the fallback would be
        OPTION_SMART_DISCHARGING, that mode covers household load only
        and does NOT charge from surplus solar (confirmed with the
        person, v0.63.59/.60) - so any live solar surplus at all would
        otherwise just go unused. Returns True in that case so the
        caller applies plain OPTION_SMART instead, letting that mode's
        own P1-following capture the solar naturally, exactly like it
        already does whenever should_postpone_charging is False.

        Prefers the Solcast-based expected PV power for this exact
        moment (`_get_expected_pv_power_w`, v0.63.71, bias-corrected
        using the already-learned per-hour ratio) over the raw live PV
        reading, which a passing cloud could momentarily dip -
        flip-flopping this decision every few minutes. Falls back to
        the live reading if no solar forecast sensor is configured.
        """
        if not should_postpone_charging:
            return False

        pv_entity = self.config.get(CONF_PV_POWER_SENSOR)
        expected_pv_power_w = self._get_expected_pv_power_w(now)
        if expected_pv_power_w is not None:
            pv_power_w = expected_pv_power_w
        else:
            pv_power_w = self._read_sensor_float(pv_entity) if pv_entity else None
        household_load_w = self._read_corrected_consumption_power()
        solar_surplus_w = 0.0
        if pv_power_w is not None and household_load_w is not None:
            solar_surplus_w = max(0.0, pv_power_w - household_load_w)
        self.last_arbitrage_solar_surplus_w = round(solar_surplus_w, 1)

        return solar_surplus_w > 0

    def _is_emergency_low_battery(self) -> bool:
        """Is the battery critically low right now, AND is little solar
        expected to refill it soon? Deliberately scoped to the winter
        scenario: in summer, a critically low battery refills quickly from
        solar the next morning anyway (better handled by discharging less
        in the first place - see the live-consumption correction in
        `_estimate_consumption_kwh_for_period`), so an emergency grid
        top-up isn't needed or desirable there. In winter, with little
        solar in the outlook, a critically low battery risks running the
        household on grid power for an extended stretch, so a safety-net
        top-up makes sense.

        Prefers the SoC sensor (compared against the same configured
        minimum used elsewhere); falls back to a small absolute kWh
        buffer on the available-energy sensor if no SoC sensor is set.
        """
        if not self._is_low_solar_expected():
            return False

        soc_entity = self.config.get(CONF_SOC_SENSOR)
        if soc_entity:
            soc = self._read_sensor_float(soc_entity)
            if soc is not None:
                min_soc = float(
                    self.config.get(CONF_MIN_SOC_PERCENT, DEFAULT_MIN_SOC_PERCENT)
                )
                return soc <= min_soc

        available_entity = self.config.get(CONF_AVAILABLE_ENERGY_SENSOR)
        if available_entity:
            available_kwh = self._read_sensor_float(available_entity)
            if available_kwh is not None:
                return available_kwh <= EMERGENCY_LOW_BATTERY_KWH_THRESHOLD

        return False

    def _update_shortfall_detection(
        self,
        now: datetime,
        reason: str,
        available_kwh: float | None = None,
        needed_kwh: float | None = None,
    ) -> None:
        """Two-sided daily learning for the dynamic discharge reserve:

        - SHORTFALL: unexpected net grid import during a period this
          integration believes should be self-sufficient. Means the
          reserve estimate ran too tight - the learned margin goes UP.
        - EXCESS: available energy stayed far above what was actually
          needed while still in the "postpone charging" window. Means
          the reserve estimate was overly conservative - the learned
          margin goes DOWN. Without this side, the margin could only
          ever ratchet upward over time and get stuck too conservative,
          missing out on legitimate selling opportunities.

        Both are tracked per day (rolling LEARNING_HISTORY_DAYS window),
        and the net effect (shortfalls push up, excess days push down)
        is applied in `_get_dynamic_discharge_reserve_kwh`.
        """
        if self._shortfall_check_date != now.date():
            if self._shortfall_check_date is not None:
                self.reserve_daily_records.append(
                    {
                        "date": self._shortfall_check_date.isoformat(),
                        "shortfall": self._shortfall_detected_today,
                        "excess": self._excess_detected_today,
                    }
                )
                self.reserve_daily_records = self.reserve_daily_records[
                    -LEARNING_HISTORY_DAYS:
                ]
                # Also feed the monthly summary - a day just closed out.
                self.current_month_days_tracked += 1
                if self._shortfall_detected_today:
                    self.current_month_shortfall_days += 1
                if self._excess_detected_today:
                    self.current_month_excess_days += 1
            self._shortfall_detected_today = False
            self._excess_detected_today = False
            self._shortfall_check_date = now.date()

        self_sufficient_reasons = (
            "smart_discharging",
            "expensive_quarter",
            "expensive_quarter_soc_protected",
        )
        if reason not in self_sufficient_reasons:
            return

        if not self._shortfall_detected_today:
            grid_entity = self.config.get(CONF_CONSUMPTION_POWER_SENSOR)
            grid_power_w = self._read_sensor_float(grid_entity)
            if (
                grid_power_w is not None
                and grid_power_w > GRID_IMPORT_SHORTFALL_THRESHOLD_W
            ):
                self._shortfall_detected_today = True
                _LOGGER.warning(
                    "Unexpected grid import detected (%.0fW) during a "
                    "supposedly self-sufficient period (%s) - the reserve "
                    "estimate for today may have been too optimistic. This "
                    "will increase the learned safety margin if it keeps "
                    "happening.",
                    grid_power_w,
                    reason,
                )

        if (
            not self._excess_detected_today
            and available_kwh is not None
            and needed_kwh is not None
            and needed_kwh > 0.1
            and available_kwh >= needed_kwh * RESERVE_EXCESS_RATIO_THRESHOLD
        ):
            self._excess_detected_today = True
            _LOGGER.debug(
                "Reserve looks overly conservative today: %.2f kWh "
                "available vs only %.2f kWh actually needed (%s) - this "
                "will decrease the learned safety margin if it keeps "
                "happening.",
                available_kwh,
                needed_kwh,
                reason,
            )

    def _get_spare_headroom_after_primary_tier_kwh(
        self,
        entries: list[PriceEntry],
        now: datetime,
        headroom_kwh: float,
        discharge_power_w: float,
    ) -> float:
        """How much of the current headroom is left over after reserving
        enough for today's remaining genuinely-expensive (primary-tier)
        quarters still ahead of 'now'. Used to size the secondary,
        more-lenient tier - so it can never eat into what the real price
        peak still needs.
        """
        primary_threshold = self._get_expensive_price_threshold(entries, now)
        if primary_threshold is None:
            return 0.0

        todays_entries = [e for e in entries if e[0].date() == now.date()]
        remaining_primary = [
            e for e in todays_entries if e[2] >= primary_threshold and e[1] > now
        ]
        energy_per_quarter_kwh = (discharge_power_w / 1000) * 0.25
        primary_needed_kwh = len(remaining_primary) * energy_per_quarter_kwh
        return max(0.0, headroom_kwh - primary_needed_kwh)

    def _is_worth_discharging_at_secondary_tier(
        self,
        entries: list[PriceEntry],
        now: datetime,
        headroom_kwh: float,
        discharge_power_w: float,
    ) -> bool:
        """Is 'now' worth discharging at the wider, secondary price tier
        (see `_get_secondary_expensive_price_threshold`), using only
        *spare* headroom left over after today's remaining primary-tier
        (genuinely expensive) quarters are accounted for?

        Without this, headroom that's clearly more than today's real
        price peak needs goes unused on quarters that don't quite clear
        the strict threshold but are still meaningfully above the day's
        cheap baseline - "leaving money on the table" on days with
        abundant battery capacity (found via a live report: 8kWh
        available, only a single 15-minute quarter sold, while
        surrounding quarters at a only slightly lower price went
        untouched).

        Same price-priority principle as `_is_worth_discharging_now`,
        just applied to the secondary tier's candidates and spare
        headroom specifically, ranked purely by price so the best of the
        "not quite primary-tier" quarters win first.
        """
        secondary_threshold = self._get_secondary_expensive_price_threshold(
            entries, now
        )
        if secondary_threshold is None:
            return False

        # Find 'now's raw price directly (same scale as the thresholds
        # above, both derived from raw entry prices) - not
        # _get_current_price_per_kwh, which converts to €/kWh and would
        # silently compare mismatched units against the raw threshold.
        now_price_raw = next(
            (e[2] for e in entries if e[0] <= now < e[1]), None
        )
        if now_price_raw is None or now_price_raw < secondary_threshold:
            return False

        spare_headroom_kwh = self._get_spare_headroom_after_primary_tier_kwh(
            entries, now, headroom_kwh, discharge_power_w
        )
        if spare_headroom_kwh <= 0:
            return False

        primary_threshold = self._get_expensive_price_threshold(entries, now)
        todays_entries = [e for e in entries if e[0].date() == now.date()]
        secondary_candidates = [
            e
            for e in todays_entries
            if e[2] >= secondary_threshold
            and (primary_threshold is None or e[2] < primary_threshold)
            and e[1] > now
        ]
        if not secondary_candidates:
            return False

        secondary_candidates.sort(key=lambda e: e[2], reverse=True)

        energy_per_quarter_kwh = (discharge_power_w / 1000) * 0.25
        if energy_per_quarter_kwh <= 0:
            return False
        quarters_affordable = max(
            1, int(spare_headroom_kwh / energy_per_quarter_kwh)
        )

        top_slots = secondary_candidates[:quarters_affordable]
        return any(e[0] <= now < e[1] for e in top_slots)

    def _is_worth_discharging_now(
        self,
        entries: list[PriceEntry],
        now: datetime,
        headroom_kwh: float,
        discharge_power_w: float,
    ) -> bool:
        """Is 'now' worth spending discharge headroom on, given the other
        remaining expensive quarters today?

        Without this, headroom gets consumed chronologically - the first
        expensive quarters encountered "win", even if later quarters
        today are priced higher. This ranks all of today's remaining
        expensive quarters by price and only spends headroom on however
        many of the *priciest* ones it can actually sustain, holding back
        otherwise - so a long elevated-price evening with a genuine peak
        later on sells at the peak, not just whichever quarter happened
        to come first.
        """
        todays_entries = [e for e in entries if e[0].date() == now.date()]
        threshold = self._get_expensive_price_threshold(entries, now)
        if threshold is None:
            return True  # no meaningful ranking possible, don't block

        remaining_expensive = [
            e for e in todays_entries if e[2] >= threshold and e[1] > now
        ]
        if not remaining_expensive:
            return True

        remaining_expensive.sort(key=lambda e: e[2], reverse=True)

        energy_per_quarter_kwh = (discharge_power_w / 1000) * 0.25
        if energy_per_quarter_kwh <= 0:
            return True
        quarters_affordable = max(1, int(headroom_kwh / energy_per_quarter_kwh))

        top_slots = remaining_expensive[:quarters_affordable]
        return any(e[0] <= now < e[1] for e in top_slots)

    def _log_discharge_floor_event(
        self,
        now: datetime,
        household_load_w: float | None,
        headroom_scaled_w: float,
        applied_w: float,
        available_kwh: float,
        reserve_kwh: float,
    ) -> None:
        """Record it whenever the household-consumption floor (v0.59.0)
        actually raises the discharge power above what the reserve-based
        headroom scaling alone would have given - so a shared diagnostics
        export shows exactly when and how often this kicked in, without
        needing a separately-pulled sensor history graph.
        """
        self.last_discharge_floor_applied = True
        self.discharge_floor_events.append(
            {
                "at": now.isoformat(),
                "household_load_w": (
                    round(household_load_w, 1) if household_load_w is not None else None
                ),
                "headroom_scaled_w": round(headroom_scaled_w, 1),
                "applied_w": round(applied_w, 1),
                "available_kwh": round(available_kwh, 2),
                "reserve_kwh": round(reserve_kwh, 2),
            }
        )
        # Bounded history, same window as energy_bridge_transition_log.
        self.discharge_floor_events = self.discharge_floor_events[-50:]

    def _get_soc_scaled_discharge_power(
        self,
        base_power: float,
        now: datetime | None = None,
        cheap_block_start: datetime | None = None,
        entries: list[PriceEntry] | None = None,
    ) -> float | None:
        """Scale down the forced-discharge power to avoid over-draining
        the battery just to sell into an expensive quarter.

        Prefers a dynamic, energy-based reserve ("keep what I actually
        need for tonight + margin", see `_get_dynamic_discharge_reserve_kwh`)
        when an available-energy sensor and cheap-block context are
        present. Falls back to a flat SoC-percentage taper otherwise.

        When entries are provided, also checks whether 'now' ranks among
        the priciest remaining quarters the current headroom can actually
        sustain (see `_is_worth_discharging_now`) - so limited headroom
        goes to the genuine peak, not just whichever expensive quarter
        happens to come first chronologically.

        Returns the (possibly reduced) power, or None if there isn't
        enough headroom to discharge at all, or a better-priced quarter
        is still ahead today - in which case forced discharge should be
        skipped this tick (protect the battery / hold out for the peak,
        fall back to smart mode).
        """
        available_entity = self.config.get(CONF_AVAILABLE_ENERGY_SENSOR)
        if available_entity and now is not None:
            available_kwh = self._read_sensor_float(available_entity)
            reserve_kwh = self._get_dynamic_discharge_reserve_kwh(
                now, cheap_block_start
            )
            if available_kwh is not None and reserve_kwh is not None:
                self.last_used_soc_taper_fallback = False
                headroom_kwh = max(0.0, available_kwh - reserve_kwh)
                interval_hours = UPDATE_INTERVAL_MINUTES / 60
                max_power_w = (headroom_kwh / interval_hours) * 1000 if interval_hours > 0 else 0

                soc_entity = self.config.get(CONF_SOC_SENSOR)
                if soc_entity:
                    self.last_soc_percent = self._read_sensor_float(soc_entity)

                # Household-consumption floor: the reserve-based headroom
                # above protects tonight's deepest deficit, but during an
                # is_expensive quarter we're already committed to selling -
                # throttling the discharge below the live household load
                # just means the shortfall is bought back from the grid at
                # that same peak price, in the same quarter we just decided
                # was worth selling in. Reported live: house at ~340W,
                # headroom-scaled discharge only ~150W, ~190W imported at
                # the peak rate. So the discharge is never allowed to drop
                # below what the house is actually drawing right now -
                # capped by what's physically available this tick (can't
                # give out more than the battery currently holds) and by
                # base_power. This intentionally lets a tick dip below the
                # "ideal" reserve line when necessary; importing at the
                # peak price is worse than a slightly thinner reserve.
                household_load_w = self._read_corrected_consumption_power()
                self.last_household_load_w = (
                    round(household_load_w, 1) if household_load_w is not None else None
                )
                physical_ceiling_w = (
                    (available_kwh / interval_hours) * 1000
                    if interval_hours > 0
                    else 0
                )
                floor_w = 0.0
                if household_load_w is not None and household_load_w > 0:
                    floor_w = round(
                        min(household_load_w, physical_ceiling_w, base_power), 1
                    )
                self.last_discharge_floor_applied = False
                self.last_price_priority_held_off = False

                if max_power_w <= 0:
                    # v0.63.19: no headroom left to justify a forced,
                    # profitable sell - reported that forcing a manual
                    # command here (even just to match live load and
                    # avoid importing) is redundant with what 'smart'
                    # mode already does on its own: this setup's
                    # zendure-ha config P1-follows toward a small export
                    # target, which keeps net import near zero without
                    # any explicit command from this integration, and
                    # does so continuously rather than a fixed manual
                    # wattage that goes stale until the next 5-min tick.
                    # So: no headroom -> no manual command at all, let
                    # the caller fall through to smart mode (see
                    # `expensive_quarter_soc_protected`).
                    self.last_discharge_power_applied = None
                    _LOGGER.debug(
                        "Dynamic discharge reserve: available=%.2f kWh, "
                        "needed reserve=%.2f kWh - no headroom, skipping "
                        "forced discharge this tick (smart mode's own "
                        "P1-following already avoids import)",
                        available_kwh,
                        reserve_kwh,
                    )
                    return None

                if entries is not None and not self._is_worth_discharging_now(
                    entries, now, headroom_kwh, base_power
                ):
                    self.last_discharge_power_applied = None
                    self.last_price_priority_held_off = True
                    _LOGGER.debug(
                        "Holding off: limited headroom (%.2f kWh) is "
                        "better spent on a pricier quarter later today "
                        "than this one",
                        headroom_kwh,
                    )
                    return None

                # v0.63.18: reported that a continuously-scaled, throttled
                # discharge (e.g. 150W of a 1600W base_power) barely earns
                # anything - "1600W or nothing", not a trickle. The
                # affordability check above (_is_worth_discharging_now)
                # already establishes that headroom can sustain base_power
                # for this quarter (ranked among however many of today's
                # priciest remaining quarters the headroom affords, at
                # FULL base_power) - so once that passes, apply base_power
                # directly rather than re-throttling it down to whatever a
                # single-tick slice of headroom_kwh happens to allow. Only
                # applies when `entries` was actually given (i.e. the
                # affordability check above genuinely ran and passed) -
                # without it, there's no "this quarter is affordable"
                # signal to justify skipping the conservative per-tick
                # throttle, so that throttle is kept as the safe default.
                physical_ceiling_w = (
                    (available_kwh / interval_hours) * 1000
                    if interval_hours > 0
                    else 0
                )
                if entries is not None:
                    scaled = round(
                        max(floor_w, min(base_power, physical_ceiling_w)), 1
                    )
                else:
                    scaled = round(min(base_power, max(max_power_w, floor_w)), 1)
                self.last_discharge_power_applied = scaled
                if scaled < base_power:
                    if entries is None and floor_w > max_power_w:
                        self._log_discharge_floor_event(
                            now, household_load_w, max_power_w, scaled,
                            available_kwh, reserve_kwh,
                        )
                    _LOGGER.debug(
                        "Dynamic discharge reserve: available=%.2f kWh, "
                        "needed reserve=%.2f kWh - capped at %.0fW (base_power "
                        "is %.0fW)",
                        available_kwh,
                        reserve_kwh,
                        scaled,
                        base_power,
                    )
                return scaled

        # Fallback: flat SoC-percentage taper (no available-energy sensor,
        # or the dynamic reserve couldn't be computed this tick).
        self.last_used_soc_taper_fallback = True
        soc_entity = self.config.get(CONF_SOC_SENSOR)
        if not soc_entity:
            self.last_soc_percent = None
            self.last_discharge_power_applied = base_power
            return base_power

        soc = self._read_sensor_float(soc_entity)
        self.last_soc_percent = soc
        if soc is None:
            self.last_discharge_power_applied = base_power
            return base_power

        min_soc = float(self.config.get(CONF_MIN_SOC_PERCENT, DEFAULT_MIN_SOC_PERCENT))
        taper_start = min_soc + SOC_TAPER_BAND_PERCENT

        if soc <= min_soc:
            self.last_discharge_power_applied = None
            return None
        if soc >= taper_start:
            self.last_discharge_power_applied = base_power
            return base_power

        fraction = (soc - min_soc) / SOC_TAPER_BAND_PERCENT
        scaled = round(base_power * fraction, 1)
        self.last_discharge_power_applied = scaled
        _LOGGER.debug(
            "SoC protection (fallback): %.1f%% is between min (%.1f%%) and "
            "full power (%.1f%%) - scaling discharge from %.0fW to %.0fW",
            soc,
            min_soc,
            taper_start,
            base_power,
            scaled,
        )
        return scaled

    def _get_low_solar_relative_fraction(self) -> float:
        """De fractie van de geleerde "typische dag" die als "weinig
        zon" geldt - beweegt mee met hoe consistent de (bias-
        gecorrigeerde) voorspelling recent is gebleken (v0.63.87,
        uitgebreid besproken en ontworpen door de gebruiker).

        Consistente voorspellingen (lage spreiding) verdienen meer
        vertrouwen: een ruimere fractie, minder snel "laag"
        gealarmeerd. Wisselvallige voorspellingen (hoge spreiding)
        vragen om meer voorzichtigheid: een kleinere fractie, sneller
        "laag" gealarmeerd bij twijfel. Valt terug op de vaste
        standaardfractie zolang er nog niet genoeg samples zijn voor
        een betrouwbare standaarddeviatie.
        """
        stdev_percent = (
            self.solar_tracker.deviation_stdev_percent if self.solar_tracker else None
        )
        if stdev_percent is None:
            return LOW_SOLAR_RELATIVE_FRACTION
        if stdev_percent < LOW_SOLAR_FRACTION_LOW_SPREAD_THRESHOLD_PERCENT:
            return LOW_SOLAR_FRACTION_CONSISTENT
        if stdev_percent > LOW_SOLAR_FRACTION_HIGH_SPREAD_THRESHOLD_PERCENT:
            return LOW_SOLAR_FRACTION_UNRELIABLE
        return LOW_SOLAR_FRACTION_DEFAULT

    def _is_forecast_value_low(self, forecast_kwh_raw: float | None) -> bool:
        """Is a given raw daily forecast value (kWh) "low", bias-corrected
        and compared against a learned dynamic threshold when enough
        history exists, falling back to the fixed configured threshold
        otherwise. Shared logic used both for tomorrow's forecast and for
        the extended (day+3, day+4, ...) forecast sensors.
        """
        if forecast_kwh_raw is None:
            return False

        bias_percent = (
            self.solar_tracker.learned_bias_percent if self.solar_tracker else None
        )
        corrected_forecast_kwh = (
            forecast_kwh_raw * (1 + bias_percent / 100)
            if bias_percent is not None
            else forecast_kwh_raw
        )

        learned_typical_kwh = (
            self.solar_tracker.learned_typical_forecast_kwh
            if self.solar_tracker
            else None
        )
        if learned_typical_kwh is not None:
            threshold_kwh = learned_typical_kwh * self._get_low_solar_relative_fraction()
        else:
            threshold_kwh = float(
                self.config.get(
                    CONF_LOW_SOLAR_THRESHOLD_KWH, DEFAULT_LOW_SOLAR_THRESHOLD_KWH
                )
            )

        return corrected_forecast_kwh < threshold_kwh

    def _is_low_solar_expected(self) -> bool:
        """Is little solar yield expected tomorrow, based on the Solcast
        forecast sensor. Returns False if no forecast sensor is configured
        or its state can't be read (i.e. "assume normal/sufficient solar"
        by default).
        """
        forecast_entity = self.config.get(CONF_SOLAR_FORECAST_SENSOR)
        if not forecast_entity:
            return False
        return self._is_forecast_value_low(self._read_sensor_float(forecast_entity))

    def _count_consecutive_upcoming_low_solar_days(self) -> int:
        """How many consecutive days, starting from tomorrow, are expected
        to have low solar - using tomorrow's forecast sensor plus any
        configured extended (day+3, day+4, ...) forecast sensors, in
        order. Stops counting at the first day that's NOT low (i.e. "how
        many days until solar recovers").

        Used to scale up the dynamic discharge reserve margin: a longer
        cloudy stretch ahead means less confidence the battery will be
        quickly refilled by solar, so more caution is warranted about
        deep discharging tonight.
        """
        if not self._is_low_solar_expected():
            return 0

        count = 1
        extended_entities = self.config.get(CONF_SOLAR_EXTENDED_FORECAST_SENSORS) or []
        for entity_id in extended_entities:
            if not self._is_forecast_value_low(self._read_sensor_float(entity_id)):
                break
            count += 1

        return count

    def _compute_dynamic_discharge_start(
        self,
        entries: list[PriceEntry],
        now: datetime,
        cheap_block_start: datetime | None = None,
    ) -> datetime | None:
        """Start the discharging window right when today's expensive
        quarters end, instead of at a fixed clock hour.

        Uses the end of the last (chronologically latest) of today's
        quarters that clear the dynamic "expensive" threshold - but only
        among quarters *before* cheap_block_start. Without this bound, an
        unusual price shape (e.g. a solar-driven midday dip followed by a
        separate evening peak, so the day's cheapest block comes *before*
        its latest expensive quarter) would return a discharge_start
        *after* cheap_block_start, making the [discharge_start,
        cheap_block_start) smart_discharging window invalid/empty - so it
        would never show up at all, even though it should apply earlier
        that same day. Returns None if none are found for today (e.g. all
        prices are equal, or no data).
        """
        todays_entries = [entry for entry in entries if entry[0].date() == now.date()]
        if not todays_entries:
            return None

        threshold = self._get_expensive_price_threshold(entries, now)
        if threshold is None:
            return None

        expensive_entries = [
            e
            for e in todays_entries
            if e[2] >= threshold
            and (cheap_block_start is None or e[1] <= cheap_block_start)
        ]
        if not expensive_entries:
            return None

        return max(entry[1] for entry in expensive_entries)

    def _log_energy_transition(
        self,
        now: datetime,
        has_enough: bool,
        available_kwh: float,
        needed_kwh: float,
        cheap_block_start: datetime | None = None,
    ) -> None:
        """Record a log entry whenever the energy-bridge decision flips,
        so you can review afterwards exactly when and why it switched -
        without needing to watch it live.

        Includes cheap_block_start so a wild swing in needed_kwh between
        two nearby entries can be attributed with certainty to the target
        cheap block having changed (e.g. a near-tied candidate elsewhere
        that day taking over), instead of having to guess.
        """
        if self.last_has_enough_energy is None or self.last_has_enough_energy == has_enough:
            return

        self.energy_bridge_transition_log.append(
            {
                "at": now.isoformat(),
                "decision": "enough_to_postpone" if has_enough else "top_up_needed",
                "available_kwh": round(available_kwh, 2),
                "needed_kwh": round(needed_kwh, 2),
                "cheap_block_start": (
                    cheap_block_start.isoformat() if cheap_block_start else None
                ),
            }
        )
        # Keep a bounded amount of history (roughly the last ~10 days
        # worth of transitions, assuming a handful of flips per day).
        self.energy_bridge_transition_log = self.energy_bridge_transition_log[-50:]

    def _should_postpone_charging(
        self,
        entries: list[PriceEntry],
        now: datetime,
        cheap_block_start: datetime | None,
    ) -> bool:
        """Should we use smart_discharging (postpone charging, favour
        export) right now, ahead of the cheapest block?

        Prefers an energy-based decision: if the battery already has
        enough available energy to bridge the remaining time until the
        cheap block (plus a safety margin), there is no need to let the
        Zendure charge from possibly-expensive surplus now - postpone
        charging and keep exporting instead. Falls back to the older
        time-based rule (discharge from the end of today's expensive
        quarters) if no available-energy sensor is configured.
        """
        if cheap_block_start is None or now >= cheap_block_start:
            self.last_available_kwh = None
            self.last_needed_kwh_to_bridge = None
            self.last_has_enough_energy = None
            return False

        available_entity = self.config.get(CONF_AVAILABLE_ENERGY_SENSOR)
        available_kwh = (
            self._read_sensor_float(available_entity) if available_entity else None
        )
        if available_kwh is not None and available_kwh < 0:
            # Physically impossible - almost certainly sensor noise right
            # around empty. Clamp instead of letting a slightly-negative
            # reading skew the comparison below.
            available_kwh = 0.0

        if available_kwh is not None:
            hours_until_cheap = max(
                (cheap_block_start - now).total_seconds() / 3600, 0
            )

            # Prefer the learned hourly profile (accounts for the actual
            # time-of-day mix of the bridging period), falling back to the
            # flat night-average or a live reading if incomplete.
            baseline_consumption_kwh = self._estimate_consumption_kwh_for_period(
                now, cheap_block_start
            )

            # The reserve requirement itself uses the worst-case
            # cumulative deficit (v0.43.0), not a net balance over the
            # whole window - a net balance can look fine on paper
            # (abundant solar expected tomorrow) while still hiding a
            # real overnight shortfall before that solar actually
            # arrives. This was previously only wired into the
            # discharge-power cap, not this postpone-charging decision
            # itself - found via a live report showing "0.00 kWh
            # needed" purely because expected solar (5.78 kWh) slightly
            # exceeded flat baseline consumption (5.356 kWh), even
            # though nothing protects the hours before dawn
            # specifically.
            needed_kwh_raw = self._estimate_worst_case_deficit_kwh(
                now, cheap_block_start
            )
            if needed_kwh_raw is not None:
                power_kw = (
                    needed_kwh_raw / hours_until_cheap
                    if hours_until_cheap > 0
                    else None
                )
            else:
                learned_kw = self.learned_night_consumption_kw
                if learned_kw is not None:
                    power_kw = learned_kw
                else:
                    power_w = self._read_corrected_consumption_power()
                    power_kw = power_w / 1000 if power_w is not None else None
                needed_kwh_raw = (
                    power_kw * hours_until_cheap if power_kw is not None else None
                )

            # Kept purely as informational context in the breakdown
            # below (and the dashboard explanation text) - the
            # worst-case-deficit figure above is what actually drives
            # the decision now.
            if needed_kwh_raw is not None:
                expected_pv_kwh = self._get_efficiency_discounted_pv_offset(
                    now, cheap_block_start
                )

                needed_kwh = needed_kwh_raw * ENERGY_BRIDGE_SAFETY_MARGIN

                self.last_needed_kwh_breakdown = {
                    "basisverbruik_kwh": (
                        round(baseline_consumption_kwh, 3)
                        if baseline_consumption_kwh is not None
                        else None
                    ),
                    "verwachte_pv_kwh": round(expected_pv_kwh, 3),
                    "diepste_tekort_kwh": round(needed_kwh_raw, 3),
                    "veiligheidsmarge_procent": round(
                        (ENERGY_BRIDGE_SAFETY_MARGIN - 1) * 100, 1
                    ),
                }
            else:
                needed_kwh = None
                self.last_needed_kwh_breakdown = {}

            if needed_kwh is not None:
                # Hysteresis: require a clear enough margin before flipping
                # the decision, instead of comparing right at the exact
                # threshold - otherwise small sensor noise right around
                # the boundary (seen in practice: available_kwh flickering
                # between ~0 and slightly negative) causes rapid,
                # unhealthy switching back and forth every tick.
                buffer_kwh = max(0.15, needed_kwh * 0.10)
                if self.last_has_enough_energy is True:
                    # Was postponing - only give up once clearly short.
                    has_enough = available_kwh >= needed_kwh - buffer_kwh
                elif self.last_has_enough_energy is False:
                    # Was topping up - only postpone once clearly ahead.
                    has_enough = available_kwh >= needed_kwh + buffer_kwh
                else:
                    has_enough = available_kwh >= needed_kwh

                self._log_energy_transition(
                    now, has_enough, available_kwh, needed_kwh, cheap_block_start
                )

                self.last_available_kwh = available_kwh
                self.last_needed_kwh_to_bridge = needed_kwh
                self.last_has_enough_energy = has_enough

                _LOGGER.debug(
                    "Energy bridge check: available=%.2f kWh, needed=%.2f "
                    "kWh (over %.1fh + %.0f%% margin, source: %s) -> %s",
                    available_kwh,
                    needed_kwh,
                    hours_until_cheap,
                    (ENERGY_BRIDGE_SAFETY_MARGIN - 1) * 100,
                    "hourly profile" if needed_kwh_raw is not None else "flat/live",
                    "enough, postpone charging" if has_enough else "top up now",
                )
                return has_enough

        # Fallback: no available-energy sensor (or no consumption
        # estimate) configured - use the old time-based rule
        # (self.last_discharge_start is already computed for this tick).
        self.last_available_kwh = None
        self.last_needed_kwh_to_bridge = None
        self.last_has_enough_energy = None
        return (
            self.last_discharge_start is not None
            and self.last_discharge_start <= now
        )

    def _build_forecast_timeline(
        self,
        entries: list[PriceEntry],
        now: datetime,
        cheap_block_start: datetime | None,
        discharge_start: datetime | None,
        live_is_expensive: bool | None = None,
        live_should_postpone_charging: bool | None = None,
        live_should_capture_solar: bool = False,
        available_kwh: float | None = None,
        reserve_kwh: float | None = None,
    ) -> list[dict]:
        """Project the current logic forward over all known forecast data.

        This is an approximation: the real coordinator recomputes the
        cheapest block and discharge window fresh on every run, so this
        projection only reflects the currently known cheapest block/window
        for "today". Beyond that window, only each day's own quarters that
        clear that day's dynamic price threshold are still marked as
        expensive; everything else defaults to 'smart'.

        If available_kwh/reserve_kwh are provided, price-qualifying
        "expensive" quarters are also capped by a simulated running
        battery balance: once the projected available energy would drop
        to the reserve floor, further otherwise-"expensive" quarters are
        shown as 'smart' instead of 'manual' - matching what the live,
        reserve-aware discharge logic would actually do, instead of
        naively showing every price-qualifying quarter as a full-power
        discharge regardless of how much energy is actually available.
        This is what makes the schedule reflect actual live consumption,
        not just price.

        The interval containing "now" is overridden with the live,
        energy-aware decision (live_is_expensive/live_should_postpone_charging)
        when provided, so the table's current row always matches what the
        "Expected operation mode" sensor actually shows right now - only
        intervals further in the future remain a price-only projection
        (which can't know about live battery energy ahead of time).

        `live_should_capture_solar` (v0.63.70, reported: "verwacht schema"
        kept showing smart_discharging for the current interval even
        when the live decision was actually smart, via the
        arbitrage_solar_capture override, v0.63.60) - when True, further
        overrides the current interval to smart even though
        live_should_postpone_charging is True, matching that override.

        v0.63.77: the "arbitrage_charging" reason (an active grid
        purchase for profit) this used to also need to signal for is
        removed entirely - see `_should_capture_solar_instead_of_
        postponing`'s docstring. Manual mode is now only ever the
        result of `is_expensive` (expensive_quarter),
        `should_force_charge`, or `emergency_low_battery` - all already
        covered above.
        """
        today = now.date()
        by_date: dict = {}
        for entry in entries:
            if entry[1] <= now:
                continue
            by_date.setdefault(entry[0].date(), []).append(entry)

        discharge_power_w = self.config.get(
            CONF_MANUAL_DISCHARGE_POWER, DEFAULT_MANUAL_DISCHARGE_POWER
        )

        # Determine which "expensive" candidates actually make the cut,
        # simulating headroom consumption in *price-priority* order
        # (priciest quarters first) rather than chronologically - so a
        # long elevated-price stretch spends limited headroom on its
        # genuine peak, not just whichever quarter happens to come first.
        # Simulated once per day, using that day's own threshold.
        makes_the_cut: set = set()
        if available_kwh is not None and reserve_kwh is not None:
            for entry_date, day_entries in by_date.items():
                threshold = self._price_threshold_for_entries(day_entries)
                if threshold is None:
                    continue
                candidates = [e for e in day_entries if e[2] >= threshold]
                candidates.sort(key=lambda e: e[2], reverse=True)

                simulated_available = available_kwh
                for candidate in candidates:
                    if simulated_available <= reserve_kwh:
                        break
                    makes_the_cut.add(candidate[0])
                    duration_hours = (
                        candidate[1] - candidate[0]
                    ).total_seconds() / 3600
                    simulated_available -= (
                        discharge_power_w / 1000
                    ) * duration_hours

                # Secondary tier: if there's spare headroom left over
                # after the primary-tier candidates above, extend
                # eligibility to the wider, more lenient secondary
                # threshold too - same principle as the live decision's
                # _is_worth_discharging_at_secondary_tier (v0.58.0), so
                # the displayed schedule matches what will actually
                # happen instead of only reflecting the secondary tier
                # for "now" and showing 'smart' for identical future
                # quarters.
                if simulated_available > reserve_kwh:
                    secondary_threshold = self._price_threshold_for_entries(
                        day_entries,
                        fraction_override=SECONDARY_EXPENSIVE_PRICE_THRESHOLD_FRACTION,
                    )
                    if secondary_threshold is not None:
                        secondary_candidates = [
                            e
                            for e in day_entries
                            if secondary_threshold <= e[2] < threshold
                        ]
                        secondary_candidates.sort(
                            key=lambda e: e[2], reverse=True
                        )
                        for candidate in secondary_candidates:
                            if simulated_available <= reserve_kwh:
                                break
                            makes_the_cut.add(candidate[0])
                            duration_hours = (
                                candidate[1] - candidate[0]
                            ).total_seconds() / 3600
                            simulated_available -= (
                                discharge_power_w / 1000
                            ) * duration_hours
        else:
            # No energy context available - every price-qualifying quarter
            # makes the cut (old behaviour, price-only projection).
            for day_entries in by_date.values():
                threshold = self._price_threshold_for_entries(day_entries)
                if threshold is None:
                    continue
                for e in day_entries:
                    if e[2] >= threshold:
                        makes_the_cut.add(e[0])

        timeline: list[dict] = []
        for entry in entries:
            if entry[1] <= now:
                continue

            entry_date = entry[0].date()
            day_entries = by_date[entry_date]
            threshold = self._price_threshold_for_entries(day_entries)
            secondary_threshold = self._price_threshold_for_entries(
                day_entries,
                fraction_override=SECONDARY_EXPENSIVE_PRICE_THRESHOLD_FRACTION,
            )
            price_qualifies = (threshold is not None and entry[2] >= threshold) or (
                secondary_threshold is not None and entry[2] >= secondary_threshold
            )
            is_expensive = price_qualifies and entry[0] in makes_the_cut

            is_current_interval = entry[0] <= now < entry[1]

            if is_current_interval and live_is_expensive is not None:
                # Use the exact same live decision shown elsewhere, instead
                # of the price-only projection, for this one interval.
                is_expensive = live_is_expensive
                if is_expensive:
                    mode = OPTION_MANUAL
                elif live_should_postpone_charging and not live_should_capture_solar:
                    mode = OPTION_SMART_DISCHARGING
                else:
                    mode = OPTION_SMART
            elif is_expensive:
                mode = OPTION_MANUAL
            elif (
                discharge_start is not None
                and cheap_block_start is not None
                and discharge_start <= entry[0] < cheap_block_start
            ):
                mode = OPTION_SMART_DISCHARGING
            else:
                mode = OPTION_SMART

            timeline.append(
                {
                    "start": entry[0].isoformat(),
                    "end": entry[1].isoformat(),
                    "price_per_kwh": round(entry[2] / PRICE_SCALE_FACTOR, 4),
                    "mode": mode,
                    "is_expensive": is_expensive,
                }
            )

        return timeline

    @staticmethod
    def _collapse_timeline(timeline: list[dict]) -> list[dict]:
        """Collapse consecutive quarters with the same mode into blocks,
        for a much more readable overview (e.g. one row for an 8-hour
        smart_discharging period, instead of 32 quarter-hour rows).
        """
        blocks: list[dict] = []
        for item in timeline:
            if blocks and blocks[-1]["mode"] == item["mode"] and blocks[-1]["end"] == item["start"]:
                blocks[-1]["end"] = item["end"]
                blocks[-1]["max_price_per_kwh"] = max(
                    blocks[-1]["max_price_per_kwh"], item["price_per_kwh"]
                )
                blocks[-1]["min_price_per_kwh"] = min(
                    blocks[-1]["min_price_per_kwh"], item["price_per_kwh"]
                )
            else:
                blocks.append(
                    {
                        "start": item["start"],
                        "end": item["end"],
                        "mode": item["mode"],
                        "min_price_per_kwh": item["price_per_kwh"],
                        "max_price_per_kwh": item["price_per_kwh"],
                    }
                )
        return blocks

    async def _ramp_solar_power_limit(self, target_percent: float) -> None:
        """Gradually move the solar inverter's power limit (%) towards
        target_percent over SOLAR_RAMP_DURATION_SECONDS, in
        SOLAR_RAMP_STEPS steps - used to curtail production during
        negative prices and restore it afterwards, instead of an abrupt
        jump.
        """
        entity_id = self.config.get(CONF_SOLAR_POWER_LIMIT_ENTITY)
        if not entity_id:
            return

        current = self._read_sensor_float(entity_id)
        if current is None:
            current = 0.0 if target_percent >= 100 else 100.0

        step_duration = SOLAR_RAMP_DURATION_SECONDS / SOLAR_RAMP_STEPS
        step_size = (target_percent - current) / SOLAR_RAMP_STEPS

        try:
            for _ in range(SOLAR_RAMP_STEPS):
                current += step_size
                await self.hass.services.async_call(
                    "number",
                    "set_value",
                    {"entity_id": entity_id, "value": round(current, 1)},
                    blocking=True,
                )
                await asyncio.sleep(step_duration)
            # Ensure the exact final value, correcting any rounding drift.
            await self.hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": entity_id, "value": target_percent},
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001 - background task, must not crash silently
            _LOGGER.warning(
                "Error while ramping solar power limit (%s) towards %.0f%%: %s",
                entity_id,
                target_percent,
                err,
            )

    def _start_solar_ramp(self, target_percent: float) -> None:
        """Fire-and-forget the ramp as a background task, so it doesn't
        block the main coordinator update loop for
        SOLAR_RAMP_DURATION_SECONDS.
        """
        self._solar_ramp_task = self.hass.async_create_task(
            self._ramp_solar_power_limit(target_percent)
        )

    def _get_current_price_per_kwh(
        self, entries: list[PriceEntry], now: datetime
    ) -> float | None:
        """Price (€/kWh) for the interval containing 'now', or None if not found."""
        for start, end, price in entries:
            if start <= now < end:
                return price / PRICE_SCALE_FACTOR
        return None

    def _is_salderen_active(self, now: datetime) -> bool:
        """Geldt de salderingsregeling op dit moment nog? (v0.63.117)

        Salderen geldt tot en met `CONF_SALDEREN_END_DATE` (standaard
        2026-12-31); vanaf de dag erna niet meer. Configureerbaar in
        plaats van hard ingebakken, omdat politiek uitstel in het
        verleden al meermaals is voorgekomen - een verkeerd ingebakken
        datum zou stilzwijgend elk financieel getal in deze integratie
        scheeftrekken.

        Bij een onleesbare/ongeldige datum wordt bewust teruggevallen
        op "salderen actief". Dat is de conservatieve kant: het houdt
        het bestaande, bekende gedrag aan in plaats van ongemerkt over
        te schakelen op een heel ander waarderingsmodel door een typefout.
        """
        raw = self.config.get(CONF_SALDEREN_END_DATE, DEFAULT_SALDEREN_END_DATE)
        try:
            end_date = date.fromisoformat(str(raw))
        except (TypeError, ValueError):
            return True
        return now.date() <= end_date

    def _salderen_days_remaining(self) -> int | None:
        """Aantal dagen dat salderen nog geldt, of None bij een
        ongeldige/onleesbare datum (v0.63.117)."""
        raw = self.config.get(CONF_SALDEREN_END_DATE, DEFAULT_SALDEREN_END_DATE)
        try:
            end_date = date.fromisoformat(str(raw))
        except (TypeError, ValueError):
            return None
        return (end_date - dt_util.now().date()).days

    def _get_feedin_value_per_kwh(
        self, entries: list[PriceEntry], now: datetime
    ) -> float | None:
        """Wat één daadwerkelijk teruggeleverde kWh op dit moment
        opbrengt (€/kWh) - het hart van de saldering-overgang
        (v0.63.117).

        **Zolang salderen geldt**: teruglevering wordt weggestreept
        tegen inkoop, dus een teruggeleverde kWh is exact de
        inkoopprijs waard (inclusief energiebelasting en BTW), plus de
        vaste Zonneplan-terugleverpremie.

        **Na saldering**: dat wegstrepen vervalt. Je krijgt alleen nog
        het kale teruglevertarief - benaderd met de marktprijs zónder
        energiebelasting uit hetzelfde forecast-attribuut
        (`CONF_FEEDIN_PRICE_ATTRIBUTE`) - plus de premie, minus
        eventuele terugleverkosten (`CONF_FEEDIN_COST_EUR_PER_KWH`).
        Inkoop blijft wél belast, dus er ontstaat een flink gat tussen
        "kWh niet inkopen" en "kWh terugleveren". Precies dat gat maakt
        thuisopslag na saldering waardevoller.

        Kan onder nul uitkomen (negatieve marktprijs plus
        terugleverkosten) - dat wordt bewust NIET afgekapt op nul: bij
        een negatief terugleversaldo kóst terugleveren geld, en dat is
        een reëel signaal dat de financiële weergave hoort mee te nemen.
        """
        if self._is_salderen_active(now):
            import_price = self._get_current_price_per_kwh(entries, now)
            if import_price is None:
                return None
            return import_price + FEEDIN_PREMIUM_EUR_PER_KWH

        feedin_key = self.config.get(
            CONF_FEEDIN_PRICE_ATTRIBUTE, DEFAULT_FEEDIN_PRICE_ATTRIBUTE
        )
        feedin_entries = self._get_forecast_entries(price_key_override=feedin_key)
        market_price = self._get_current_price_per_kwh(feedin_entries, now)
        if market_price is None:
            # Het teruglever-attribuut ontbreekt op deze prijssensor -
            # niet gissen met de inkoopprijs (dat is precies de
            # aanname die na saldering niet meer klopt en de besparing
            # fors zou overschatten).
            return None
        feedin_cost = float(
            self.config.get(
                CONF_FEEDIN_COST_EUR_PER_KWH, DEFAULT_FEEDIN_COST_EUR_PER_KWH
            )
            or 0.0
        )
        return market_price + FEEDIN_PREMIUM_EUR_PER_KWH - feedin_cost

    def _split_discharge_export_vs_load(
        self, discharged_kwh: float, elapsed_hours: float
    ) -> tuple[float, float]:
        """Splitst een ontlading in (export_kwh, huisverbruik_kwh)
        (v0.63.117 - uitgetrokken uit twee plekken die exact dezelfde
        berekening dupliceerden, zodat ze niet uiteen kunnen lopen).

        Het deel dat het huisverbruik dekt is géén teruglevering: daar
        wordt inkoop mee vermeden. Alleen wat daarboven uitkomt gaat
        werkelijk het net op. Zonder verbruikssensor kan dat onderscheid
        niet gemaakt worden - dan wordt alles als huisverbruik geteld,
        de conservatieve kant (geen premie, geen terugleverwaarde).
        """
        if discharged_kwh <= 0 or elapsed_hours <= 0:
            return 0.0, max(0.0, discharged_kwh)
        household_load_w = self._read_corrected_consumption_power()
        if household_load_w is None:
            return 0.0, discharged_kwh
        discharge_rate_kw = discharged_kwh / elapsed_hours
        export_rate_kw = max(0.0, discharge_rate_kw - household_load_w / 1000)
        export_kwh = min(discharged_kwh, export_rate_kw * elapsed_hours)
        return export_kwh, discharged_kwh - export_kwh

    def _split_charge_pv_vs_grid(
        self, charged_kwh: float, elapsed_hours: float
    ) -> tuple[float, float]:
        """Splitst een lading in (pv_overschot_kwh, net_kwh) - v0.63.117.

        Spiegelbeeld van `_split_discharge_export_vs_load`, en het
        ontbrekende stuk waardoor de besparing tot nu toe systematisch
        werd overschat: PV-overschot dat in de accu gaat, zou anders
        zijn teruggeleverd. Die gederfde teruglevering (inclusief de
        premie) is de werkelijke kostprijs van die kWh - niet de kale
        inkoopprijs.

        PV-overschot = opwek minus huisverbruik, begrensd op wat er
        werkelijk geladen is. Zonder PV-sensor óf zonder verbruikssensor
        is dat onderscheid niet te maken; dan wordt alles als
        net-inkoop geteld. Dat is hier de conservatieve kant: het houdt
        de kostprijs op de (hogere) inkoopprijs en overschat de
        besparing dus niet.
        """
        if charged_kwh <= 0 or elapsed_hours <= 0:
            return 0.0, max(0.0, charged_kwh)
        pv_entity = self.config.get(CONF_PV_POWER_SENSOR)
        if not pv_entity:
            return 0.0, charged_kwh
        pv_power_w = self._read_sensor_float(pv_entity)
        household_load_w = self._read_corrected_consumption_power()
        if pv_power_w is None or household_load_w is None:
            return 0.0, charged_kwh
        surplus_kw = max(0.0, (pv_power_w - household_load_w) / 1000)
        pv_kwh = min(charged_kwh, surplus_kw * elapsed_hours)
        return pv_kwh, charged_kwh - pv_kwh

    @staticmethod
    def _grid_flow_cost_eur(
        power_w: float,
        elapsed_hours: float,
        import_price_eur_per_kwh: float,
        feedin_value_eur_per_kwh: float,
    ) -> float:
        """Kosten (positief) of opbrengst (negatief) van een netstroom
        over dit interval, met APARTE tarieven voor inkoop en
        teruglevering (v0.63.117).

        Positief vermogen = import (kost de inkoopprijs), negatief =
        export (levert de terugleverwaarde op). Onder saldering zijn
        die twee vrijwel gelijk; daarna niet meer, en dan is één tarief
        voor beide richtingen niet houdbaar.
        """
        kwh = (power_w / 1000) * elapsed_hours
        if kwh >= 0:
            return kwh * import_price_eur_per_kwh
        return kwh * feedin_value_eur_per_kwh

    def _update_feedin_regime(self, now: datetime, entries: list[PriceEntry]) -> None:
        """Houdt het huidige salderingsregime en de actuele
        terugleverwaarde bij voor weergave/diagnostiek (v0.63.117).
        Berekent zelf niets nieuws - leest alleen dezelfde helpers uit
        die de financiële boekingen ook gebruiken, zodat wat op het
        dashboard staat gegarandeerd hetzelfde is als waarmee gerekend
        wordt.
        """
        self.salderen_active = self._is_salderen_active(now)
        self.current_feedin_value_eur_per_kwh = self._get_feedin_value_per_kwh(
            entries, now
        )
        import_price = self._get_current_price_per_kwh(entries, now)
        if (
            import_price is not None
            and self.current_feedin_value_eur_per_kwh is not None
        ):
            self.feedin_import_spread_eur_per_kwh = round(
                import_price - self.current_feedin_value_eur_per_kwh, 4
            )
        else:
            self.feedin_import_spread_eur_per_kwh = None

    def _update_counterfactual_savings(
        self, now: datetime, entries: list[PriceEntry] | None = None
    ) -> None:
        """Tegenfeitelijke besparingsvergelijking (v0.63.101, gevraagd:
        "als je dit systeem niet had, had je deze maand €X betaald; nu
        betaalde je €Y").

        Reconstrueert per tick wat de netmeter zou hebben getoond
        ZONDER de accu erbij (dezelfde PV-opbrengst als nu, maar geen
        accu-sturing) - `p1_power + battery_power`, zelfde teken-
        conventie als `_read_corrected_consumption_power`. Rekent
        zowel de werkelijke als de tegenfeitelijke netstroom af tegen
        dezelfde, actuele dynamische prijs, en houdt het cumulatieve
        verschil bij op drie niveaus (vandaag, deze maand, all-time).

        Bewust een specifieke tegenfeitelijke situatie ("zelfde PV,
        geen accu-sturing") in plaats van een vage "gemiddelde
        besparing t.o.v. een vast tarief" - dat laatste zou een aparte,
        losse aanname over een vast tarief vereisen die niet uit
        bestaande sensoren is af te leiden. Puur informatief, stuurt
        niets aan.
        """
        p1_entity = self.config.get(CONF_CONSUMPTION_POWER_SENSOR)
        if not p1_entity:
            return
        p1_power_w = self._read_sensor_float(p1_entity)
        if p1_power_w is None:
            return
        price_per_kwh = self.last_current_price_per_kwh
        if price_per_kwh is None:
            return

        battery_power_w = 0.0
        battery_entity = self.config.get(CONF_BATTERY_POWER_SENSOR)
        if battery_entity:
            raw_battery = self._read_sensor_float(battery_entity)
            if raw_battery is not None:
                battery_power_w = raw_battery
                if self.config.get(CONF_INVERT_BATTERY_POWER_SIGN, False):
                    battery_power_w = -battery_power_w

        counterfactual_power_w = p1_power_w + battery_power_w

        today_key = now.date()
        if self._counterfactual_day_key != today_key:
            self._counterfactual_day_key = today_key
            self.actual_cost_today_eur = 0.0
            self.counterfactual_cost_today_eur = 0.0

        month_key = now.year * 100 + now.month
        if self._counterfactual_month_key is None:
            self._counterfactual_month_key = month_key
        elif month_key != self._counterfactual_month_key:
            self.actual_cost_current_month_eur = 0.0
            self.counterfactual_cost_current_month_eur = 0.0
            self._counterfactual_month_key = month_key

        if self._counterfactual_last_sample is None:
            self._counterfactual_last_sample = now
            return
        elapsed_hours = max(
            (now - self._counterfactual_last_sample).total_seconds() / 3600, 0
        )
        self._counterfactual_last_sample = now
        if elapsed_hours <= 0 or elapsed_hours > 1:
            # Grote hiaat (bijv. na een herstart) - niet met een
            # verouderd vermogen een uur lang doorrekenen.
            return

        # v0.63.117: import en export worden niet langer tegen dezelfde
        # prijs afgerekend. Onder saldering zijn ze (op de premie na)
        # wél gelijk, dus verandert er nu praktisch niets; na saldering
        # levert een teruggeleverde kWh veel minder op dan een
        # ingekochte kWh kost, en zou één tarief voor beide de
        # vergelijking fors scheeftrekken - juist in het voordeel van
        # "geen accu", omdat het tegenfeitelijke scenario per definitie
        # méér exporteert.
        feedin_value = self._get_feedin_value_per_kwh(entries or [], now)
        if feedin_value is None:
            feedin_value = price_per_kwh

        actual_cost_eur = self._grid_flow_cost_eur(
            p1_power_w, elapsed_hours, price_per_kwh, feedin_value
        )
        counterfactual_cost_eur = self._grid_flow_cost_eur(
            counterfactual_power_w, elapsed_hours, price_per_kwh, feedin_value
        )

        self.actual_cost_today_eur += actual_cost_eur
        self.counterfactual_cost_today_eur += counterfactual_cost_eur
        self.actual_cost_current_month_eur += actual_cost_eur
        self.counterfactual_cost_current_month_eur += counterfactual_cost_eur
        self.actual_cost_all_time_eur += actual_cost_eur
        self.counterfactual_cost_all_time_eur += counterfactual_cost_eur

    def _update_co2_tracking(self, now: datetime) -> None:
        """CO2-intensiteit van het net (v0.63.101, gevraagd: "zaken
        voor een typisch EMS welke we kunnen toevoegen"). Optioneel -
        alleen actief als een CO2-intensiteit-entiteit is geconfigureerd
        (bijv. ElectricityMaps, CO2 Signal). Houdt de geschatte
        uitstoot bij van geïmporteerde energie (g CO2/kWh op dat moment
        × geïmporteerde kWh), niet van totaal verbruik - energie die
        zelf via PV/accu wordt gedekt, importeert niets en stoot dus
        niets uit voor deze rekening. Puur informatief, stuurt niets
        aan.
        """
        co2_entity = self.config.get(CONF_CO2_INTENSITY_SENSOR)
        if not co2_entity:
            return
        co2_g_per_kwh = self._read_sensor_float(co2_entity)
        if co2_g_per_kwh is None:
            return
        self.last_co2_intensity_g_per_kwh = co2_g_per_kwh

        p1_entity = self.config.get(CONF_CONSUMPTION_POWER_SENSOR)
        if not p1_entity:
            return
        p1_power_w = self._read_sensor_float(p1_entity)
        if p1_power_w is None:
            return

        today_key = now.date()
        if self._co2_day_key != today_key:
            self._co2_day_key = today_key
            self.co2_emitted_today_kg = 0.0

        if self._co2_last_sample is None:
            self._co2_last_sample = now
            return
        elapsed_hours = max(
            (now - self._co2_last_sample).total_seconds() / 3600, 0
        )
        self._co2_last_sample = now
        if elapsed_hours <= 0 or elapsed_hours > 1:
            return

        import_kwh = (max(0.0, p1_power_w) / 1000) * elapsed_hours
        self.co2_emitted_today_kg += (import_kwh * co2_g_per_kwh) / 1000

    def _update_battery_cycle_tracking(self, now: datetime) -> None:
        """Accu-gezondheid: cyclus-telling en geschatte capaciteits-
        degradatie (v0.63.101, gevraagd: "zaken voor een typisch EMS
        welke we kunnen toevoegen").

        Houdt de cumulatieve ONTLADEN energie (kWh) bij - de gangbare
        conventie voor cyclus-telling (niet laden, om dubbeltelling via
        rendementsverlies te vermijden). Eén "volledige cyclus" =
        cumulatieve ontladen energie / accucapaciteit.

        BEWUST EN DUIDELIJK een ruwe schatting, geen gemeten waarde -
        zie `BATTERY_CYCLES_TO_80_PERCENT_CAPACITY`'s docstring. Puur
        informatief, stuurt niets aan.
        """
        battery_entity = self.config.get(CONF_BATTERY_POWER_SENSOR)
        if not battery_entity:
            return
        raw_battery = self._read_sensor_float(battery_entity)
        if raw_battery is None:
            return
        battery_power_w = raw_battery
        if self.config.get(CONF_INVERT_BATTERY_POWER_SIGN, False):
            battery_power_w = -battery_power_w

        if self._battery_cycle_last_sample is None:
            self._battery_cycle_last_sample = now
            return
        elapsed_hours = max(
            (now - self._battery_cycle_last_sample).total_seconds() / 3600, 0
        )
        self._battery_cycle_last_sample = now
        if elapsed_hours <= 0 or elapsed_hours > 1:
            return

        if battery_power_w > 0:  # ontladen (conventie: positief = ontladen)
            self.battery_cumulative_discharged_kwh += (
                battery_power_w / 1000
            ) * elapsed_hours

    @property
    def battery_estimated_full_cycles(self) -> float | None:
        capacity_entity = self.config.get(CONF_BATTERY_TOTAL_CAPACITY_SENSOR)
        if not capacity_entity:
            return None
        capacity_kwh = self._read_sensor_float(capacity_entity)
        if capacity_kwh is None or capacity_kwh <= 0:
            return None
        return round(self.battery_cumulative_discharged_kwh / capacity_kwh, 1)

    @property
    def battery_estimated_capacity_percent(self) -> float | None:
        """Ruwe, LINEAIRE schatting - geen gemeten waarde. Zie
        `BATTERY_CYCLES_TO_80_PERCENT_CAPACITY`'s docstring in const.py
        voor de aannames en beperkingen hiervan."""
        cycles = self.battery_estimated_full_cycles
        if cycles is None:
            return None
        degraded_fraction = min(
            1.0, cycles / BATTERY_CYCLES_TO_80_PERCENT_CAPACITY
        )
        return round(100 - degraded_fraction * 20, 1)

    def _update_self_sufficiency_tracking(self, now: datetime) -> None:
        """Zelfconsumptie-/zelfvoorzieningsratio (v0.63.101, gevraagd:
        "zaken voor een typisch EMS welke we kunnen toevoegen" -
        klassieke EMS-KPI's).

        - Zelfconsumptie: welk deel van de eigen PV-productie wordt
          zelf verbruikt, niet geëxporteerd naar het net.
          (pv_productie - pv_export) / pv_productie.
        - Zelfvoorziening: welk deel van het totale (bruto)verbruik
          wordt gedekt door eigen bronnen (PV + accu), niet
          geïmporteerd van het net.
          (bruto_verbruik - import) / bruto_verbruik.

        Bruto-verbruik is de gereconstrueerde "wat had ik verbruikt
        zonder PV/accu"-schatting (dezelfde formule als
        `_read_corrected_consumption_power`), niet de kale P1-aflezing.
        PV-export is het deel van de P1-aflezing dat negatief is
        (exporteren) - ongeacht of dat overschot via de accu ging of
        rechtstreeks, telt het net het pas als "geëxporteerd" zodra het
        de aansluiting daadwerkelijk verlaat. Puur informatief, stuurt
        niets aan.
        """
        p1_entity = self.config.get(CONF_CONSUMPTION_POWER_SENSOR)
        if not p1_entity:
            return
        p1_power_w = self._read_sensor_float(p1_entity)
        if p1_power_w is None:
            return

        today_key = now.date()
        if self._self_sufficiency_day_key != today_key:
            self._self_sufficiency_day_key = today_key
            self.pv_production_today_kwh = 0.0
            self.pv_export_today_kwh = 0.0
            self.gross_consumption_today_kwh = 0.0
            self.grid_import_today_kwh = 0.0

        if self._self_sufficiency_last_sample is None:
            self._self_sufficiency_last_sample = now
            return
        elapsed_hours = max(
            (now - self._self_sufficiency_last_sample).total_seconds() / 3600, 0
        )
        self._self_sufficiency_last_sample = now
        if elapsed_hours <= 0 or elapsed_hours > 1:
            return

        pv_power_w = 0.0
        pv_entity = self.config.get(CONF_PV_POWER_SENSOR)
        if pv_entity:
            raw_pv = self._read_sensor_float(pv_entity)
            if raw_pv is not None:
                pv_power_w = raw_pv

        gross_power_w = self._read_corrected_consumption_power()
        if gross_power_w is None:
            gross_power_w = p1_power_w

        self.pv_production_today_kwh += (pv_power_w / 1000) * elapsed_hours
        self.pv_export_today_kwh += (
            max(0.0, -p1_power_w) / 1000
        ) * elapsed_hours
        self.gross_consumption_today_kwh += (gross_power_w / 1000) * elapsed_hours
        self.grid_import_today_kwh += (
            max(0.0, p1_power_w) / 1000
        ) * elapsed_hours

    @property
    def self_consumption_ratio_percent(self) -> float | None:
        if self.pv_production_today_kwh <= 0:
            return None
        return round(
            100
            * (self.pv_production_today_kwh - self.pv_export_today_kwh)
            / self.pv_production_today_kwh,
            1,
        )

    @property
    def self_sufficiency_ratio_percent(self) -> float | None:
        if self.gross_consumption_today_kwh <= 0:
            return None
        return round(
            100
            * (self.gross_consumption_today_kwh - self.grid_import_today_kwh)
            / self.gross_consumption_today_kwh,
            1,
        )

    def _read_battery_cooling_inputs(self) -> tuple | None:
        """Leest de drie metingen die de koelbeslissing nodig heeft:
        (accutemperatuur, buitentemperatuur, |accuvermogen|) - v0.63.122.

        Geeft None terug zodra één ervan ontbreekt of onleesbaar is.

        **Bewuste afwijking van de oorspronkelijke automatisering.** Die
        gebruikte `states(...)|float(0)`, waardoor een onbeschikbare
        sensor stilzwijgend als 0 werd gelezen. Dat is hier gevaarlijk:
        valt de BUITENsensor weg, dan wordt buiten 0°C, is de delta
        ineens gelijk aan de volledige accutemperatuur, en springt de
        ventilator aan op basis van een meting die er niet is. Andersom
        levert een weggevallen ACCUsensor 0°C op, waardoor er juist
        nooit meer gekoeld wordt. Bij ontbrekende data verandert deze
        integratie de schakelaar daarom niet - de bestaande stand blijft
        staan, wat in beide richtingen de veilige keuze is.
        """
        temp_entity = self.config.get(CONF_BATTERY_TEMPERATURE_SENSOR)
        if not temp_entity:
            return None
        accu_c = self._read_sensor_float(temp_entity)
        if accu_c is None:
            return None

        outdoor_entity = self.config.get(CONF_BATTERY_COOLING_OUTDOOR_SENSOR)
        if outdoor_entity:
            buiten_c = self._read_sensor_float(outdoor_entity)
        else:
            # Geen eigen sensor opgegeven: hergebruik de al bestaande
            # live-buitentemperatuur (achtertuinsensor met uitschieter-
            # filter, anders de weerentiteit).
            buiten_c = self.climate_live_outdoor_temp_c
        if buiten_c is None:
            return None

        vermogen_w = self._read_corrected_battery_power()
        if vermogen_w is None:
            return None
        return accu_c, buiten_c, abs(vermogen_w)

    @staticmethod
    def _battery_cooling_should_turn_on(
        accu_c: float, buiten_c: float, vermogen_w: float
    ) -> str | None:
        """Welke van de vier aanzet-redenen geldt op dit moment, of None
        (v0.63.122). Geeft de reden terug in plaats van alleen True/
        False, zodat de melding en het dashboard kunnen tonen WAAROM er
        gekoeld wordt - bij vier mogelijke oorzaken is "aan" alleen niet
        genoeg om iets van te leren.
        """
        delta_c = accu_c - buiten_c
        if delta_c > BATTERY_COOLING_ON_DELTA_C:
            return (
                f"accu staat {delta_c:.1f}°C boven buiten "
                f"(meer dan {BATTERY_COOLING_ON_DELTA_C:.0f}°C)"
            )
        if accu_c > BATTERY_COOLING_ON_ABSOLUTE_C:
            return (
                f"accu is {accu_c:.1f}°C, boven de absolute grens van "
                f"{BATTERY_COOLING_ON_ABSOLUTE_C:.0f}°C"
            )
        if (
            vermogen_w > BATTERY_COOLING_ON_POWER_W
            and delta_c > BATTERY_COOLING_ON_POWER_DELTA_C
        ):
            return (
                f"{vermogen_w:.0f}W door de accu en al {delta_c:.1f}°C "
                "boven buiten"
            )
        if (
            vermogen_w > BATTERY_COOLING_ON_HIGH_POWER_W
            and accu_c > BATTERY_COOLING_ON_HIGH_POWER_TEMP_C
        ):
            return (
                f"zwaar belast ({vermogen_w:.0f}W) bij {accu_c:.1f}°C"
            )
        return None

    @staticmethod
    def _battery_cooling_should_turn_off(
        accu_c: float, buiten_c: float, vermogen_w: float
    ) -> bool:
        """Uitschakelen mag alleen als ALLE drie voorwaarden tegelijk
        gelden (v0.63.122) - één die terugvalt is niet genoeg, anders
        slaat de ventilator af terwijl een andere reden om te koelen nog
        staat. De drempels liggen bewust lager dan die voor aanzetten
        (hysterese), zodat er niet rond één grens gependeld wordt.
        """
        delta_c = accu_c - buiten_c
        return (
            delta_c < BATTERY_COOLING_OFF_DELTA_C
            and vermogen_w < BATTERY_COOLING_OFF_POWER_W
            and accu_c < BATTERY_COOLING_OFF_ABSOLUTE_C
        )

    def evaluate_battery_cooling(self) -> dict:
        """Bepaalt wat er met de koelventilator zou moeten gebeuren -
        puur rekenwerk, schakelt zelf niets (v0.63.122).

        Apart gehouden van het daadwerkelijk schakelen zodat de beslissing
        los te testen is en het dashboard hem kan tonen zonder iets in
        gang te zetten.
        """
        resultaat = {
            "actie": None,
            "reden": None,
            "accu_c": None,
            "buiten_c": None,
            "vermogen_w": None,
            "ventilator_aan": None,
        }
        fan_entity = self.config.get(CONF_BATTERY_COOLING_FAN_SWITCH)
        if not fan_entity:
            resultaat["reden"] = "Geen ventilatorschakelaar geconfigureerd."
            return resultaat

        metingen = self._read_battery_cooling_inputs()
        if metingen is None:
            resultaat["reden"] = (
                "Accutemperatuur, buitentemperatuur of accuvermogen is nu "
                "niet uitleesbaar - de ventilator wordt met rust gelaten."
            )
            return resultaat

        accu_c, buiten_c, vermogen_w = metingen
        resultaat.update(
            {
                "accu_c": round(accu_c, 1),
                "buiten_c": round(buiten_c, 1),
                "vermogen_w": round(vermogen_w, 0),
                "delta_c": round(accu_c - buiten_c, 1),
            }
        )

        fan_state = self.hass.states.get(fan_entity)
        huidige = getattr(fan_state, "state", None)
        if huidige in BATTERY_COOLING_FAN_UNAVAILABLE_STATES:
            resultaat["reden"] = (
                f"Ventilatorschakelaar {fan_entity} is niet uitleesbaar."
            )
            return resultaat
        aan = huidige == "on"
        resultaat["ventilator_aan"] = aan

        if not aan:
            reden = self._battery_cooling_should_turn_on(
                accu_c, buiten_c, vermogen_w
            )
            if reden:
                resultaat["actie"] = "aan"
                resultaat["reden"] = reden
            else:
                resultaat["reden"] = "Koeling niet nodig."
            return resultaat

        if self._battery_cooling_should_turn_off(accu_c, buiten_c, vermogen_w):
            resultaat["actie"] = "uit"
            resultaat["reden"] = (
                f"accu {accu_c:.1f}°C, nog maar "
                f"{accu_c - buiten_c:.1f}°C boven buiten en "
                f"{vermogen_w:.0f}W belasting"
            )
        else:
            resultaat["reden"] = "Blijft koelen."
        return resultaat

    async def _async_apply_battery_cooling(self) -> None:
        """Voert de uitkomst van `evaluate_battery_cooling` uit
        (v0.63.122).

        Respecteert `learning_only` en `force_manual` net als elke andere
        aansturing in deze integratie: staat er één van beide aan, dan
        rekent hij wél door (zodat het dashboard blijft kloppen) maar
        raakt hij de schakelaar niet aan.
        """
        besluit = self.evaluate_battery_cooling()
        self.battery_cooling_state = besluit
        if besluit["actie"] is None:
            return
        if self.learning_only or self.force_manual:
            besluit["reden"] = (
                f"{besluit['reden']} (niet uitgevoerd: "
                f"{'learning only' if self.learning_only else 'force manual'} "
                "staat aan)"
            )
            return

        fan_entity = self.config.get(CONF_BATTERY_COOLING_FAN_SWITCH)
        service = "turn_on" if besluit["actie"] == "aan" else "turn_off"
        try:
            await self.hass.services.async_call(
                "switch", service, {"entity_id": fan_entity}, blocking=True
            )
        except Exception as err:  # noqa: BLE001 - achtergrondtaak
            _LOGGER.warning(
                "Kon de accu-koelventilator (%s) niet %s: %s",
                fan_entity,
                service,
                err,
            )
            return

        self.battery_cooling_last_change = dt_util.now()
        self.battery_cooling_history.append(
            {
                "moment": self.battery_cooling_last_change.isoformat(),
                "actie": besluit["actie"],
                "reden": besluit["reden"],
                "accu_c": besluit["accu_c"],
                "buiten_c": besluit["buiten_c"],
                "vermogen_w": besluit["vermogen_w"],
            }
        )
        self.battery_cooling_history = self.battery_cooling_history[
            -BATTERY_COOLING_HISTORY_LENGTH:
        ]

        titel = (
            "🔋 Accu: koeling AAN" if besluit["actie"] == "aan"
            else "🔋 Accu: koeling UIT"
        )
        self._dispatch_notification(
            notify_service=self.config.get(CONF_APPLIANCE_NOTIFY_SERVICE),
            title=titel,
            message=(
                f"Accu {besluit['accu_c']}°C, buiten {besluit['buiten_c']}°C, "
                f"delta {besluit['delta_c']}°C, vermogen "
                f"{besluit['vermogen_w']:.0f}W — {besluit['reden']}."
            ),
            notification_id="ems_battery_cooling",
        )
        self._notify_listeners()

    def _read_battery_modules(self) -> list[dict]:
        """Leest per accumodule de beschikbare metingen (v0.63.123).

        De volgorde van de geconfigureerde lijsten bepaalt het
        modulenummer: de eerste entiteit in elke lijst hoort bij module
        1. Lijsten mogen van verschillende lengte zijn (bijv. wel
        celspanningen maar geen vermogen per module); ontbrekende
        metingen worden None.

        Levert altijd één dict per module op, ook als een enkele meting
        wegvalt - een tijdelijk onbereikbare sensor mag niet de hele
        module uit de weergave laten verdwijnen.
        """
        max_v = self.config.get(CONF_BATTERY_MODULE_CELL_VOLTAGE_MAX_SENSORS) or []
        min_v = self.config.get(CONF_BATTERY_MODULE_CELL_VOLTAGE_MIN_SENSORS) or []
        temps = self.config.get(CONF_BATTERY_MODULE_TEMPERATURE_SENSORS) or []
        socs = self.config.get(CONF_BATTERY_MODULE_SOC_SENSORS) or []
        powers = self.config.get(CONF_BATTERY_MODULE_POWER_SENSORS) or []

        aantal = max(len(max_v), len(min_v), len(temps), len(socs), len(powers))
        modules = []
        for index in range(aantal):
            def lees(lijst):
                if index >= len(lijst):
                    return None
                return self._read_sensor_float(lijst[index])

            cel_max = lees(max_v)
            cel_min = lees(min_v)
            delta_v = None
            if cel_max is not None and cel_min is not None:
                delta_v = round(cel_max - cel_min, 4)
            modules.append(
                {
                    "module": index + 1,
                    "cel_max_v": cel_max,
                    "cel_min_v": cel_min,
                    "cel_delta_v": delta_v,
                    "temperatuur_c": lees(temps),
                    "soc_percent": lees(socs),
                    "vermogen_w": lees(powers),
                }
            )
        return modules

    @staticmethod
    def _deviation_from_peers(waarden: list, index: int) -> float | None:
        """Afwijking van één module t.o.v. het gemiddelde van de ANDERE
        modules (v0.63.123).

        Bewust t.o.v. de andere modules en niet t.o.v. het gemiddelde
        inclusief zichzelf: bij drie modules trekt een uitschieter het
        gemiddelde waar hij zelf in zit met zich mee, waardoor zijn
        eigen afwijking structureel wordt onderschat (met n modules
        wordt de afwijking met factor (n-1)/n afgezwakt). Uitsluiten van
        zichzelf maakt de maat scherp en onafhankelijk van het aantal
        modules.

        Deze differentiële vergelijking is het hart van de
        modulebewaking: alle modules staan onder identieke
        omstandigheden (zelfde SoC, zelfde omgevingstemperatuur, zelfde
        belasting), dus alles wat ze gemeenschappelijk hebben valt weg
        en wat overblijft is een eigenschap van díe module. Dat maakt
        het ook ongevoelig voor de sterke SoC-afhankelijkheid van het
        celspanningsverschil bij LFP.
        """
        eigen = waarden[index]
        if eigen is None:
            return None
        anderen = [
            w for i, w in enumerate(waarden) if i != index and w is not None
        ]
        if not anderen:
            return None
        return eigen - (sum(anderen) / len(anderen))

    def _update_battery_module_health(self, now: datetime) -> None:
        """Verzamelt per module de live metingen en de afwijking t.o.v.
        de andere modules, en rondt aan het einde van de dag een
        mediaan-dagwaarde af per grootheid (v0.63.123).

        Mediaan en niet gemiddelde, consistent met de rest van dit
        project: één laadpiek of een moment met direct zonlicht op één
        module mag een dagwaarde niet verslepen.
        """
        modules = self._read_battery_modules()
        if not modules:
            self.battery_module_live = []
            return

        deltas = [m["cel_delta_v"] for m in modules]
        temps = [m["temperatuur_c"] for m in modules]
        socs = [m["soc_percent"] for m in modules]
        powers = [m["vermogen_w"] for m in modules]

        for index, module in enumerate(modules):
            module["cel_delta_afwijking_v"] = self._deviation_from_peers(deltas, index)
            module["temperatuur_afwijking_c"] = self._deviation_from_peers(temps, index)
            module["soc_afwijking_percent"] = self._deviation_from_peers(socs, index)
            module["vermogen_afwijking_w"] = self._deviation_from_peers(powers, index)
        self.battery_module_live = modules

        day_key = now.date()
        if self._battery_module_day_key is None:
            self._battery_module_day_key = day_key
        elif day_key != self._battery_module_day_key:
            self._finalize_battery_module_day()
            self._battery_module_day_key = day_key

        geldige_socs = [s for s in socs if s is not None]
        bucket = None
        if geldige_socs:
            gemiddelde_soc = sum(geldige_socs) / len(geldige_socs)
            bucket = str(
                int(gemiddelde_soc // BATTERY_MODULE_SOC_BUCKET_SIZE_PERCENT)
                * BATTERY_MODULE_SOC_BUCKET_SIZE_PERCENT
            )

        for module in modules:
            sleutel = str(module["module"])
            staat = self.battery_module_health.setdefault(
                sleutel,
                {
                    "dag_metingen": {},
                    "geschiedenis": {},
                    "cusum": {},
                    "soc_buckets": {},
                    "waarschuwingen": [],
                },
            )
            metingen = staat["dag_metingen"]
            for veld, waarde in (
                ("cel_delta_afwijking_v", module["cel_delta_afwijking_v"]),
                ("temperatuur_afwijking_c", module["temperatuur_afwijking_c"]),
                ("soc_afwijking_percent", module["soc_afwijking_percent"]),
                ("cel_delta_v", module["cel_delta_v"]),
                ("temperatuur_c", module["temperatuur_c"]),
            ):
                if waarde is not None:
                    metingen.setdefault(veld, []).append(waarde)

            # Absolute celdelta per SoC-bucket, puur ter referentie: bij
            # LFP hoort de delta aan de uiteinden hoger te liggen, dus
            # zonder die opsplitsing is een absolute waarde niet met
            # zichzelf over de tijd te vergelijken.
            if bucket is not None and module["cel_delta_v"] is not None:
                buckets = staat["soc_buckets"].setdefault(bucket, [])
                buckets.append(module["cel_delta_v"])
                staat["soc_buckets"][bucket] = buckets[-200:]

        self._evaluate_battery_module_warnings(modules)

    def _finalize_battery_module_day(self) -> None:
        """Sluit de dag af: mediaan per grootheid de geschiedenis in, en
        de CUSUM-drift bijwerken (v0.63.123)."""
        for staat in self.battery_module_health.values():
            metingen = staat.get("dag_metingen", {})
            for veld, waarden in metingen.items():
                if len(waarden) < BATTERY_MODULE_MIN_SAMPLES_PER_DAY:
                    continue
                mediaan = statistics.median(waarden)
                geschiedenis = staat["geschiedenis"].setdefault(veld, [])
                geschiedenis.append(round(mediaan, 4))
                staat["geschiedenis"][veld] = geschiedenis[
                    -BATTERY_MODULE_HISTORY_DAYS:
                ]
                self._update_battery_module_cusum(staat, veld, mediaan)
            staat["dag_metingen"] = {}

    @staticmethod
    def _battery_module_cusum_parameters(veld: str) -> tuple[float, float] | None:
        if veld == "cel_delta_afwijking_v":
            return BATTERY_MODULE_CUSUM_SLACK_V, BATTERY_MODULE_CUSUM_THRESHOLD_V
        if veld == "temperatuur_afwijking_c":
            return BATTERY_MODULE_CUSUM_SLACK_C, BATTERY_MODULE_CUSUM_THRESHOLD_C
        if veld == "soc_afwijking_percent":
            return (
                BATTERY_MODULE_CUSUM_SLACK_PERCENT,
                BATTERY_MODULE_CUSUM_THRESHOLD_PERCENT,
            )
        return None

    def _update_battery_module_cusum(
        self, staat: dict, veld: str, dagwaarde: float
    ) -> None:
        """Klassieke eenzijdige CUSUM op de dagelijkse afwijking
        (v0.63.123).

        Alleen op de AFWIJKINGS-grootheden, niet op de absolute waarden:
        die laatste hangen sterk van SoC en seizoen af en zouden een
        stroom van valse alarmen geven. Alleen positieve drift telt -
        een module die het juist béter doet dan de rest is geen
        probleem.
        """
        parameters = self._battery_module_cusum_parameters(veld)
        if parameters is None:
            return
        slack, drempel = parameters

        geschiedenis = staat["geschiedenis"].get(veld, [])
        if len(geschiedenis) < CUSUM_MIN_HISTORY_FOR_REFERENCE:
            return
        if len(geschiedenis) > CUSUM_REFERENCE_EXCLUDE_RECENT_DAYS:
            referentie_reeks = geschiedenis[:-CUSUM_REFERENCE_EXCLUDE_RECENT_DAYS]
        else:
            referentie_reeks = geschiedenis
        if not referentie_reeks:
            return
        referentie = statistics.median(referentie_reeks)

        cusum = staat["cusum"].setdefault(
            veld,
            {"accumulator": 0.0, "referentie": None, "drift": False, "streak": 0},
        )
        cusum["referentie"] = round(referentie, 4)

        bijdrage = (dagwaarde - referentie) - slack
        cusum["accumulator"] = max(0.0, cusum["accumulator"] + max(0.0, bijdrage))

        if dagwaarde <= referentie:
            cusum["streak"] = cusum.get("streak", 0) + 1
        else:
            cusum["streak"] = 0
        if cusum["accumulator"] > 0 and cusum["streak"] >= NILM_CUSUM_RESET_STREAK_DAYS:
            cusum["accumulator"] = 0.0
            cusum["drift"] = False

        if cusum["accumulator"] > drempel:
            cusum["drift"] = True
        cusum["accumulator"] = round(cusum["accumulator"], 4)

    def _evaluate_battery_module_warnings(self, modules: list[dict]) -> None:
        """Directe, absolute controles per module (v0.63.123).

        Los van de langzame CUSUM-drift: sommige dingen zijn nú relevant
        en hoeven niet op een trend van weken te wachten.
        """
        deltas = [m["cel_delta_v"] for m in modules if m["cel_delta_v"] is not None]
        temps = [m["temperatuur_c"] for m in modules if m["temperatuur_c"] is not None]
        socs = [m["soc_percent"] for m in modules if m["soc_percent"] is not None]

        for module in modules:
            sleutel = str(module["module"])
            staat = self.battery_module_health.setdefault(
                sleutel,
                {
                    "dag_metingen": {},
                    "geschiedenis": {},
                    "cusum": {},
                    "soc_buckets": {},
                    "waarschuwingen": [],
                },
            )
            waarschuwingen = []
            delta = module["cel_delta_v"]
            if delta is not None:
                if delta >= BATTERY_MODULE_CELL_DELTA_SERIOUS_V:
                    waarschuwingen.append(
                        f"celspanningsverschil {delta:.3f} V - fors uit balans"
                    )
                elif delta >= BATTERY_MODULE_CELL_DELTA_ATTENTION_V:
                    waarschuwingen.append(
                        f"celspanningsverschil {delta:.3f} V - hoger dan gebruikelijk"
                    )
            temperatuur = module["temperatuur_c"]
            if (
                temperatuur is not None
                and temperatuur >= BATTERY_MODULE_TEMPERATURE_ATTENTION_C
            ):
                waarschuwingen.append(f"celtemperatuur {temperatuur:.1f} °C")
            staat["waarschuwingen"] = waarschuwingen

        self.battery_module_spread = {
            "cel_delta_v": round(max(deltas) - min(deltas), 4) if deltas else None,
            "temperatuur_c": round(max(temps) - min(temps), 1) if temps else None,
            "soc_percent": round(max(socs) - min(socs), 1) if socs else None,
        }

    def get_battery_power_display(self) -> str:
        """Accuvermogen als leesbare tekst met RICHTING (v0.63.127,
        gerapporteerd: "Vermogen naar/van accu is niet inzichtelijk").

        Een kaal getal uit de vermogenssensor helpt niet: het teken
        alleen zegt niets zonder te weten welke conventie die sensor
        aanhoudt, en op een schematische kaart is "laden" of "ontladen"
        precies de informatie die je zoekt. Gebruikt
        `_read_corrected_battery_power` (positief = ontladen), dezelfde
        bron als de beslislogica, zodat kaart en besluit nooit iets
        anders kunnen beweren.

        Onder MIN_BATTERY_POWER_IDLE_W wordt het "rust" genoemd in plaats
        van een richting te suggereren die er niet is - een accu die
        stilstaat schommelt altijd een paar watt.
        """
        vermogen_w = self._read_corrected_battery_power()
        if vermogen_w is None:
            return "onbekend"
        if abs(vermogen_w) < MIN_BATTERY_POWER_IDLE_W:
            return "rust"
        richting = "ontladen" if vermogen_w > 0 else "laden"
        return f"{richting} {abs(vermogen_w):.0f} W"

    @staticmethod
    def format_moment_short(moment: datetime | None) -> str | None:
        """Kort, leesbaar tijdstip (v0.63.127, gerapporteerd: "de datum
        notatie is niet duidelijk").

        Een `state-label` op een picture-elements-kaart toont de ruwe
        attribuutwaarde en kan niet formatteren - er is geen sjabloon
        beschikbaar. De opmaak hoort dus hier te gebeuren, bij de bron,
        in plaats van op het dashboard. Levert bijvoorbeeld
        "wo 6 aug 12:48" op in plaats van
        "2026-08-06T12:48:28.434441+02:00".
        """
        if moment is None:
            return None
        lokaal = dt_util.as_local(moment)
        dagen = ["ma", "di", "wo", "do", "vr", "za", "zo"]
        maanden = [
            "jan", "feb", "mrt", "apr", "mei", "jun",
            "jul", "aug", "sep", "okt", "nov", "dec",
        ]
        return (
            f"{dagen[lokaal.weekday()]} {lokaal.day} "
            f"{maanden[lokaal.month - 1]} {lokaal:%H:%M}"
        )

    def get_battery_module_table(self) -> list[dict]:
        """Overzicht per module voor het dashboard (v0.63.123) - live
        waarden plus de status van de drift-detectie."""
        tabel = []
        for module in self.battery_module_live:
            staat = self.battery_module_health.get(str(module["module"]), {})
            cusum = staat.get("cusum", {})
            drift = [
                veld for veld, waarde in cusum.items() if waarde.get("drift")
            ]
            tabel.append(
                {
                    **module,
                    "waarschuwingen": staat.get("waarschuwingen", []),
                    "drift_op": drift,
                    "dagen_geleerd": max(
                        (len(v) for v in staat.get("geschiedenis", {}).values()),
                        default=0,
                    ),
                }
            )
        return tabel

    def _update_peak_power_tracking(self, now: datetime) -> None:
        """Piekvermogen-tracking voor capaciteitstarieven (v0.63.101,
        gevraagd: "zaken voor een typisch EMS welke we kunnen
        toevoegen" - Nederlandse netbeheerders stappen steeds meer over
        op tarieven gebaseerd op het hoogste piekvermogen (kW) i.p.v.
        alleen kWh, dus tijdig weten wanneer je richting een nieuw
        record gaat kan direct geld schelen).

        Houdt het hoogste gemeten netto-netimport-vermogen bij, op drie
        niveaus tegelijk (vandaag, deze maand, all-time) - puur
        informatief, stuurt niets aan. Bewust de RUWE P1/netmeter-
        aflezing (`CONF_CONSUMPTION_POWER_SENSOR` rechtstreeks), niet
        de elders gebruikte "gecorrigeerde" huishoudverbruik-schatting
        (`_read_corrected_consumption_power`, die batterij-/PV-bijdrage
        terugtelt om het WERKELIJKE huishoudverbruik te benaderen) - een
        capaciteitstarief wordt namelijk afgerekend op wat de netmeter
        zelf ziet, niet op het onderliggende huishoudverbruik. Als de
        accu op dit moment ontlaadt om het huishouden te dekken, ziet
        het net minder (of geen) import, en dát telt voor deze piek.
        """
        power_w = self._read_sensor_float(
            self.config.get(CONF_CONSUMPTION_POWER_SENSOR)
        )
        if power_w is None or power_w <= 0:
            # Negatief/nul = geen netimport (exporteren of PV dekt alles) -
            # geen piek om bij te houden op dit moment.
            return

        today_key = now.date()
        if self._peak_power_day_key != today_key:
            if self._peak_power_day_key is not None and self.peak_power_today_w > 0:
                self.peak_power_daily_history.append(
                    {
                        "date": self._peak_power_day_key.isoformat(),
                        "peak_w": round(self.peak_power_today_w, 1),
                    }
                )
                self.peak_power_daily_history = self.peak_power_daily_history[
                    -LEARNING_HISTORY_DAYS:
                ]
            self._peak_power_day_key = today_key
            self.peak_power_today_w = 0.0

        month_key = now.year * 100 + now.month
        if self._peak_power_month_key is None:
            self._peak_power_month_key = month_key
        elif month_key != self._peak_power_month_key:
            self.peak_power_previous_month_w = round(
                self.peak_power_current_month_w, 1
            )
            self.peak_power_current_month_w = 0.0
            self._peak_power_month_key = month_key

        if power_w > self.peak_power_today_w:
            self.peak_power_today_w = power_w
        if power_w > self.peak_power_current_month_w:
            self.peak_power_current_month_w = power_w
        if power_w > self.peak_power_all_time_w:
            self.peak_power_all_time_w = power_w
            self.peak_power_all_time_date = now.date().isoformat()

    def _check_monthly_rollover(self, now: datetime) -> None:
        """Detect a new calendar month starting, snapshotting the current
        month's totals into "previous month" before resetting - this is
        what makes a genuine month-over-month trend comparison possible,
        on top of the existing rolling 7-day self-correction (shortfall/
        excess margin, PV bias) which only ever looks at the recent
        past, not whether things are improving release over release.
        """
        month_key = now.year * 100 + now.month
        if self._summary_month_key is None:
            self._summary_month_key = month_key
            return
        if month_key == self._summary_month_key:
            return

        self.previous_month_discharge_value_eur = round(
            self.current_month_discharge_value_eur, 2
        )
        self.previous_month_charge_cost_eur = round(
            self.current_month_charge_cost_eur, 2
        )
        self.previous_month_shortfall_days = self.current_month_shortfall_days
        self.previous_month_excess_days = self.current_month_excess_days
        self.previous_month_days_tracked = self.current_month_days_tracked

        self.current_month_discharge_value_eur = 0.0
        self.current_month_charge_cost_eur = 0.0
        self.current_month_shortfall_days = 0
        self.current_month_excess_days = 0
        self.current_month_days_tracked = 0
        self._summary_month_key = month_key

    def _update_financial_tracking(
        self,
        now: datetime,
        entries: list[PriceEntry],
        reason: str,
        discharge_power_w: float | None,
        charge_power_w: float | None,
    ) -> None:
        """Accumulate the euro value of the two actions with a clean,
        defensible calculation: energy moved x price at that exact moment.

        Deliberately does NOT attempt a "total savings" figure, since that
        would require a counterfactual (what would have happened without
        this integration) that can't be honestly verified. This only
        tracks the direct monetary value of energy discharged during
        expensive quarters, and the direct cost of energy force-charged
        from the grid during a low-solar cheap block.

        v0.63.25: the discharge value now also includes the Zonneplan
        feed-in premium (`FEEDIN_PREMIUM_EUR_PER_KWH`) for whatever
        portion of the discharge is genuine net export - same
        export-vs-covers-load split as
        `_update_battery_cost_basis_and_savings`, kept consistent so
        this sensor's "directe waarde" claim is actually accurate, not
        just an approximation that ignores the premium entirely.
        """
        elapsed_hours = 0.0
        if self._last_value_calc_time is not None:
            elapsed_hours = max(
                (now - self._last_value_calc_time).total_seconds() / 3600, 0
            )
        self._last_value_calc_time = now

        if elapsed_hours <= 0:
            return

        current_price = self._get_current_price_per_kwh(entries, now)
        if current_price is None:
            return

        if reason == "expensive_quarter" and discharge_power_w:
            energy_kwh = (discharge_power_w / 1000) * elapsed_hours

            export_kwh, load_kwh = self._split_discharge_export_vs_load(
                energy_kwh, elapsed_hours
            )
            # v0.63.117: het geëxporteerde deel wordt gewaardeerd tegen
            # de werkelijke terugleverwaarde (onder saldering de
            # inkoopprijs plus premie; daarna het lage teruglevertarief),
            # het huisverbruik-deel tegen de vermeden inkoopprijs.
            feedin_value = self._get_feedin_value_per_kwh(entries, now)
            if feedin_value is None:
                export_kwh, load_kwh = 0.0, energy_kwh
                feedin_value = current_price

            feedin_premium_eur = export_kwh * FEEDIN_PREMIUM_EUR_PER_KWH
            value_eur = load_kwh * current_price + export_kwh * feedin_value
            self.total_discharge_value_eur += value_eur
            self.current_month_discharge_value_eur += value_eur
            self.total_feedin_premium_eur += feedin_premium_eur
        elif (
            reason
            in (
                "grid_charging_low_solar",
                "grid_charging_low_solar_extra_dip",
                "emergency_low_battery",
            )
            and charge_power_w
        ):
            energy_kwh = (abs(charge_power_w) / 1000) * elapsed_hours
            cost_eur = energy_kwh * current_price
            self.total_charge_cost_eur += cost_eur
            self.current_month_charge_cost_eur += cost_eur

    def _update_battery_cost_basis_and_savings(
        self, now: datetime, entries: list[PriceEntry]
    ) -> None:
        """Track a weighted-average EUR/kWh cost basis for whatever
        energy currently sits in the battery, and realise savings/
        earnings whenever that energy leaves - regardless of *why* it
        left (an explicit sell during expensive_quarter, or simply
        covering household load to avoid an import during smart/
        smart_discharging/emergency_low_battery/etc).

        Unlike `_update_financial_tracking` above (which deliberately
        avoids a "total savings" figure, since that needs an unverifiable
        counterfactual), this IS defensible: it only uses prices this
        integration actually observed at the exact moments energy
        entered and left the battery - not a hypothetical "what if there
        were no battery" scenario. reported: "wat bespaart de batterij" -
        both buy-low-sell-high arbitrage AND PV self-consumption should
        count, using one unified mechanism rather than two.

        v0.63.25: on the discharge side, splits out how much of the
        discharge was genuine net export to the grid (vs. just covering
        household load) - confirmed via web search that Zonneplan pays a
        fixed EUR/kWh feed-in premium (`FEEDIN_PREMIUM_EUR_PER_KWH`) on
        top of the market price for every kWh actually fed back,
        including from a battery (only the separate 10% "Zonnebonus"
        excludes battery-sourced feed-in, which this integration never
        claims anyway). Covering household load isn't feed-in at all, so
        gets no premium - only the value of the avoided import.

        v0.63.117 - TWEE wijzigingen, want deze docstring beschreef tot
        nu toe twee aannames die niet (meer) houdbaar zijn:

        1. **De laadkant is nu symmetrisch.** Tot v0.63.116 werd ELKE
           geladen kWh tegen de kale inkoopprijs geboekt, ook als het
           PV-overschot betrof dat anders was teruggeleverd. De premie
           werd bij export dus wél bijgeteld maar bij het opofferen van
           export nooit afgetrokken - een structurele, altijd
           dezelfde kant op werkende overschatting van de besparing.
           De lading wordt nu gesplitst in PV-overschot en net-inkoop
           (`_split_charge_pv_vs_grid`), elk tegen het juiste tarief.

        2. **Saldering is niet langer een vaste aanname.** Zolang
           salderen geldt, is teruglevering exact de inkoopprijs waard
           en valt alles samen zoals voorheen. Daarna niet meer: dan
           bepaalt `_get_feedin_value_per_kwh` een apart, veel lager
           teruglevertarief. De kostprijs hangt daardoor af van de
           BRON (PV-overschot vs. net) en de opbrengst van de
           BESTEMMING (huisverbruik vs. export). Per-bron-lots blijven
           onnodig: de accu is één gedeelde pool en alles loopt via
           dezelfde gewogen kostprijs.

        Deliberately doesn't try to distinguish "discharge that covered
        useful load/sale" from "discharge lost to internal battery
        self-discharge/standby losses" - both show up identically as an
        available_kwh decrease. A small simplification; self-discharge
        is typically a minor fraction of total throughput.
        """
        available_entity = self.config.get(CONF_AVAILABLE_ENERGY_SENSOR)
        if not available_entity:
            return
        available_kwh = self._read_sensor_float(available_entity)
        if available_kwh is None:
            return

        elapsed_hours = 0.0
        if self._last_cost_basis_calc_time is not None:
            elapsed_hours = max(
                (now - self._last_cost_basis_calc_time).total_seconds() / 3600, 0
            )
        self._last_cost_basis_calc_time = now

        if self._last_available_kwh_for_cost_basis is None:
            self._last_available_kwh_for_cost_basis = available_kwh
            return

        delta_kwh = available_kwh - self._last_available_kwh_for_cost_basis
        self._last_available_kwh_for_cost_basis = available_kwh

        if abs(delta_kwh) < MIN_COST_BASIS_DELTA_KWH:
            return

        current_price = self._get_current_price_per_kwh(entries, now)
        if current_price is None:
            return

        if delta_kwh > 0:
            # Geladen. v0.63.117: de kostprijs hangt af van de BRON.
            # Net-inkoop kost de inkoopprijs. PV-overschot kost de
            # gederfde teruglevering - onder saldering gelijk aan de
            # inkoopprijs plus de premie, daarna alleen nog het lage
            # teruglevertarief. Voorheen werd alles tegen de kale
            # inkoopprijs geboekt, waardoor de premie op PV-overschot
            # nooit werd afgetrokken terwijl die bij export wél werd
            # bijgeteld: een structurele, eenzijdige overschatting van
            # de besparing.
            pv_kwh, grid_kwh = self._split_charge_pv_vs_grid(
                delta_kwh, elapsed_hours
            )
            feedin_value = self._get_feedin_value_per_kwh(entries, now)
            if feedin_value is None:
                # Geen betrouwbare terugleverwaarde - alles tegen de
                # inkoopprijs boeken, de conservatieve kant (hogere
                # kostprijs, dus geen overschatte besparing).
                pv_kwh, grid_kwh = 0.0, delta_kwh
                feedin_value = current_price

            charge_cost_eur = grid_kwh * current_price + pv_kwh * feedin_value
            self.charge_pv_kwh_total += pv_kwh
            self.charge_grid_kwh_total += grid_kwh
            self.forgone_feedin_eur_total += pv_kwh * feedin_value

            effective_charge_price = charge_cost_eur / delta_kwh
            if self.battery_cost_basis_eur_per_kwh is None:
                self.battery_cost_basis_eur_per_kwh = effective_charge_price
            else:
                # Weight by whatever was already stored before this
                # charge - approximated by the available_kwh just before
                # this delta (available_kwh - delta_kwh).
                previous_kwh = max(0.0, available_kwh - delta_kwh)
                total_kwh = previous_kwh + delta_kwh
                self.battery_cost_basis_eur_per_kwh = (
                    self.battery_cost_basis_eur_per_kwh * previous_kwh
                    + charge_cost_eur
                ) / total_kwh
        else:
            # Discharged (sold, or used to cover load and avoid an
            # import) - realise the difference between what this energy
            # is worth right now and what it originally cost, if a cost
            # basis exists yet. Pre-existing energy with an unknown
            # origin (e.g. right after a fresh install) is skipped
            # rather than guessed at.
            #
            # v0.63.117: de opbrengst hangt af van de BESTEMMING. Het
            # deel dat huisverbruik dekt vermijdt inkoop en is dus de
            # (belaste) inkoopprijs waard. Het deel dat werkelijk het
            # net op gaat levert de terugleverwaarde op - onder
            # saldering gelijk aan de inkoopprijs plus premie (identiek
            # aan het oude gedrag), daarna fors lager.
            if self.battery_cost_basis_eur_per_kwh is not None:
                discharged_kwh = -delta_kwh

                export_kwh, load_kwh = self._split_discharge_export_vs_load(
                    discharged_kwh, elapsed_hours
                )
                feedin_value = self._get_feedin_value_per_kwh(entries, now)
                if feedin_value is None:
                    # Geen betrouwbare terugleverwaarde - alles
                    # waarderen als vermeden inkoop, zonder premie.
                    export_kwh, load_kwh = 0.0, discharged_kwh
                    feedin_value = current_price

                revenue_eur = load_kwh * current_price + export_kwh * feedin_value
                feedin_premium_eur = export_kwh * FEEDIN_PREMIUM_EUR_PER_KWH
                savings_eur = (
                    revenue_eur
                    - discharged_kwh * self.battery_cost_basis_eur_per_kwh
                )
                self.total_battery_savings_eur += savings_eur
                self.total_feedin_premium_eur += feedin_premium_eur
                self.discharge_export_kwh_total += export_kwh

    def _update_energy_balance_validation(self, now: datetime) -> None:
        """Kirchhoff-style internal-consistency check (v0.63.28): cross-
        checks the battery power sensor's own reading against what the
        available-energy sensor's rate of change *implies* the battery
        power must be, over this tick's interval. A genuine validation
        using only sensors already configured - not a new measurement,
        so it can't catch every possible fault (e.g. both sensors being
        wrong in a correlated way), but it does catch the common,
        practically useful cases: a stale/unavailable sensor, a wrong
        entity picked during setup, a unit mismatch, or a sign-convention
        error that `invert_battery_power_sign` should have corrected but
        didn't.

        available_kwh(now) - available_kwh(previous) over elapsed time
        gives the implied battery power (positive = discharging, matching
        `_read_corrected_battery_power`'s own convention) - some
        persistent gap against the measured value is *expected* (round-
        trip efficiency losses aren't zero), so this isn't a "should be
        exactly zero" check; it's a rolling health signal, not a hard
        alarm.

        `sensor_health_score` (0-100): fraction of the last
        ENERGY_BALANCE_ERROR_HISTORY_LENGTH samples that stayed within
        ENERGY_BALANCE_ERROR_BAD_THRESHOLD_W, with an unavailable-sensor
        sample counted as fully "bad" (a stale sensor is exactly the
        kind of fault this is meant to catch).
        `measurement_quality`: a coarser "goed"/"verminderd"/"slecht"
        label derived from that score, easier to glance at on a
        dashboard than a raw number.

        Does nothing (all fields stay None) if either sensor isn't
        configured - this is meant to be a bonus check when the data is
        already there, not a reason to ask for more sensors.
        """
        available_entity = self.config.get(CONF_AVAILABLE_ENERGY_SENSOR)
        battery_entity = self.config.get(CONF_BATTERY_POWER_SENSOR)
        if not available_entity or not battery_entity:
            return

        available_kwh = self._read_sensor_float(available_entity)
        measured_battery_power_w = self._read_corrected_battery_power()

        if self._last_balance_check_time is None:
            self._last_balance_check_time = now
            self._last_balance_check_available_kwh = available_kwh
            return

        elapsed_hours = (now - self._last_balance_check_time).total_seconds() / 3600
        prev_kwh = self._last_balance_check_available_kwh
        self._last_balance_check_time = now
        self._last_balance_check_available_kwh = available_kwh

        if available_kwh is None or measured_battery_power_w is None:
            # A missing reading is itself a health-relevant event (a
            # stale/unavailable sensor) - record it as a "bad" sample
            # rather than silently skipping.
            self._record_balance_sample(None)
            return

        if elapsed_hours <= 0 or elapsed_hours > MAX_HOUR_TRACKING_GAP_MINUTES / 60:
            # No baseline yet, or too large a gap (restart etc.) to
            # attribute reliably to a single rate - skip this sample
            # rather than record a misleading spike.
            return

        if prev_kwh is None:
            return

        delta_kwh = available_kwh - prev_kwh
        implied_battery_power_w = -(delta_kwh / elapsed_hours) * 1000
        error_w = implied_battery_power_w - measured_battery_power_w
        self.last_energy_balance_error_w = round(error_w, 1)
        self._record_balance_sample(abs(error_w))

    def _record_balance_sample(self, abs_error_w: float | None) -> None:
        """Append one sample (or None for a missing-sensor tick) to the
        rolling window and recompute the health score/quality label.
        """
        self.energy_balance_error_history.append(abs_error_w)
        self.energy_balance_error_history = self.energy_balance_error_history[
            -ENERGY_BALANCE_ERROR_HISTORY_LENGTH:
        ]

        total = len(self.energy_balance_error_history)
        if total < MEASUREMENT_QUALITY_MIN_SAMPLES:
            # v0.63.121: pas oordelen zodra er genoeg metingen zijn -
            # zie MEASUREMENT_QUALITY_MIN_SAMPLES. Vlak na een herstart
            # is het venster leeg, en één afwijkende meting leverde dan
            # "slecht (0.0%, 1 metingen)" op: statistisch betekenisloos,
            # maar het bracht de systeemstatus wel op "Aandacht
            # gewenst".
            self.sensor_health_score = None
            self.measurement_quality = None
            return

        good = sum(
            1
            for v in self.energy_balance_error_history
            if v is not None and v <= ENERGY_BALANCE_ERROR_BAD_THRESHOLD_W
        )
        self.sensor_health_score = round(100 * good / total, 1)

        if self.sensor_health_score >= MEASUREMENT_QUALITY_GOOD_THRESHOLD:
            self.measurement_quality = "goed"
        elif self.sensor_health_score >= MEASUREMENT_QUALITY_DEGRADED_THRESHOLD:
            self.measurement_quality = "verminderd"
        else:
            self.measurement_quality = "slecht"

    def _update_anomaly_detection(self, now: datetime) -> None:
        """CUSUM sluipverbruik-detectie (v0.63.29): tracks the
        household's daily "floor load" (the lowest corrected-consumption
        reading seen that day - phantom/standby loads dominate at that
        point, everything else is normally off) and runs a classic
        cumulative-sum control chart against it to catch a *sustained*
        upward drift, not a single noisy day.

        Deliberately uses a separate, longer history
        (CUSUM_BASELINE_HISTORY_DAYS = 30) from the adaptive
        LEARNING_HISTORY_DAYS = 7 window the rest of this integration
        uses for decisions - a 7-day rolling median would just quietly
        treat a slow creep as "the new normal" within a week, which is
        exactly the failure mode CUSUM is meant to catch. The reference
        excludes the most recent CUSUM_REFERENCE_EXCLUDE_RECENT_DAYS
        days, so a genuine ongoing drift isn't already baked into its
        own comparison baseline.

        CUSUM_SLACK_KW (20W) is a deliberate dead zone - small day-to-day
        noise doesn't accumulate. CUSUM_ALARM_THRESHOLD_KW (150W
        cumulative) means a small, gradual drift takes roughly a week of
        sustained deviation to alarm, while a sudden larger jump (e.g. a
        new always-on device) alarms within a couple of days - the
        standard CUSUM trade-off between sensitivity and false alarms.

        Paused during vacation_mode (artificially low readings would
        corrupt the reference, and could make the return to normal look
        like a false "spike" afterwards) - same principle as the hourly
        consumption profile's own vacation-mode pause.
        """
        if self.vacation_mode:
            return
        household_load_w = self._read_corrected_consumption_power()
        if household_load_w is None:
            return
        household_load_kw = household_load_w / 1000

        if self._cusum_check_date != now.date():
            if self._cusum_check_date is not None and self._today_min_load_kw is not None:
                self._finalize_baseline_load_day(self._today_min_load_kw)
            self._today_min_load_kw = household_load_kw
            self._cusum_check_date = now.date()
            return

        if self._today_min_load_kw is None or household_load_kw < self._today_min_load_kw:
            self._today_min_load_kw = household_load_kw

    def _finalize_baseline_load_day(self, floor_load_kw: float) -> None:
        self.baseline_load_history.append(round(floor_load_kw, 4))
        self.baseline_load_history = self.baseline_load_history[
            -CUSUM_BASELINE_HISTORY_DAYS:
        ]

        if len(self.baseline_load_history) < CUSUM_MIN_HISTORY_FOR_REFERENCE:
            return

        if len(self.baseline_load_history) > CUSUM_REFERENCE_EXCLUDE_RECENT_DAYS:
            reference_samples = self.baseline_load_history[
                :-CUSUM_REFERENCE_EXCLUDE_RECENT_DAYS
            ]
        else:
            reference_samples = self.baseline_load_history
        if not reference_samples:
            return

        reference_kw = statistics.median(reference_samples)
        self.sluipverbruik_reference_w = round(reference_kw * 1000, 1)

        deviation_kw = floor_load_kw - reference_kw - CUSUM_SLACK_KW
        self.cusum_accumulator_kw = max(0.0, self.cusum_accumulator_kw + deviation_kw)

        was_detected = self.sluipverbruik_detected
        self.sluipverbruik_detected = self.cusum_accumulator_kw >= CUSUM_ALARM_THRESHOLD_KW
        if self.sluipverbruik_detected:
            self.sluipverbruik_estimated_drift_w = round(
                (floor_load_kw - reference_kw) * 1000, 1
            )
            if not was_detected:
                # Edge-triggered (only on the False -> True transition) -
                # otherwise this would re-notify every single day the
                # drift stays elevated, which teaches the person to
                # ignore it rather than act on it.
                notify_service = self.config.get(CONF_APPLIANCE_NOTIFY_SERVICE)
                self._dispatch_notification(
                    notify_service=notify_service,
                    title="🔍 Mogelijk sluipverbruik gedetecteerd",
                    message=(
                        f"Het laagste dagelijkse verbruik ligt structureel "
                        f"~{self.sluipverbruik_estimated_drift_w:.0f}W hoger "
                        f"dan de langere-termijn-referentie "
                        f"({self.sluipverbruik_reference_w:.0f}W) - "
                        f"mogelijk een nieuw sluimerend apparaat. Gebaseerd "
                        f"op een aanhoudende trend, niet één losse nacht."
                    ),
                    notification_id="ems_sluipverbruik_detected",
                )

    def _update_weather_ensemble_check(self, now: datetime) -> None:
        """Weather ensemble cross-check (v0.63.30): compares live PV
        output against what Solcast's own forecast predicts for right
        now, alongside live cloud_coverage readings from independent
        weather sources (KNMI/OpenWeatherMap) - read from their HA
        `weather` entities, not a new API integration.

        Deliberately informational only, not wired into any decision:
        a genuine multi-source kWh yield ensemble would need panel
        orientation/tilt/kWp specs this integration doesn't collect, so
        this doesn't try to produce an alternate yield estimate. What it
        *can* honestly do: flag when live PV underperformance doesn't
        match what independent weather sources say the sky is doing
        right now (e.g. Solcast/the PV reading is low despite
        weather.knmi/weather.openweathermap both reporting clear skies -
        worth a look, could be a panel/inverter issue rather than
        weather) or the reverse (overperforming despite reported heavy
        cloud, less concerning but still worth noting for calibration).
        """
        knmi_entity = self.config.get(CONF_KNMI_WEATHER_ENTITY)
        owm_entity = self.config.get(CONF_OPENWEATHERMAP_WEATHER_ENTITY)
        source_entities = [e for e in (knmi_entity, owm_entity) if e]
        if not source_entities:
            return

        cloud_readings: list[float] = []
        sources_used: list[str] = []
        for entity_id in source_entities:
            state = self.hass.states.get(entity_id)
            if state is None:
                continue
            cloud_pct = state.attributes.get("cloud_coverage")
            if cloud_pct is None:
                continue
            try:
                cloud_readings.append(float(cloud_pct))
                sources_used.append(entity_id)
            except (TypeError, ValueError):
                continue

        if not cloud_readings:
            self.weather_ensemble_cloud_cover_percent = None
            self.weather_ensemble_sources_used = []
            self.weather_ensemble_label = None
            self.weather_ensemble_disagreement = None
            return

        avg_cloud_pct = sum(cloud_readings) / len(cloud_readings)
        self.weather_ensemble_cloud_cover_percent = round(avg_cloud_pct, 1)
        self.weather_ensemble_sources_used = sources_used

        if avg_cloud_pct < WEATHER_ENSEMBLE_CLEAR_THRESHOLD_PERCENT:
            self.weather_ensemble_label = "helder"
        elif avg_cloud_pct > WEATHER_ENSEMBLE_OVERCAST_THRESHOLD_PERCENT:
            self.weather_ensemble_label = "bewolkt"
        else:
            self.weather_ensemble_label = "half bewolkt"

        self.weather_ensemble_disagreement = None
        pv_entity = self.config.get(CONF_PV_POWER_SENSOR)
        if not pv_entity:
            return
        live_pv_w = self._read_sensor_float(pv_entity)
        if live_pv_w is None:
            return

        solcast_kw = None
        for start, end, kwh in self._get_pv_forecast_entries():
            if start <= now < end:
                interval_hours = (end - start).total_seconds() / 3600
                if interval_hours > 0:
                    solcast_kw = kwh / interval_hours
                break
        if solcast_kw is None or solcast_kw < WEATHER_ENSEMBLE_MIN_SOLCAST_KW:
            # Too close to zero (night, or Solcast itself predicts
            # almost nothing) - a ratio here would be noise, not signal.
            return

        ratio = (live_pv_w / 1000) / solcast_kw
        if (
            ratio < WEATHER_ENSEMBLE_UNDERPERFORM_RATIO
            and avg_cloud_pct < WEATHER_ENSEMBLE_CLEAR_THRESHOLD_PERCENT
        ):
            self.weather_ensemble_disagreement = (
                "PV presteert fors onder de Solcast-voorspelling, terwijl "
                "KNMI/OpenWeatherMap juist heldere lucht melden - "
                "mogelijk een paneel- of omvormer-kwestie, niet het weer."
            )
        elif (
            ratio > WEATHER_ENSEMBLE_OVERPERFORM_RATIO
            and avg_cloud_pct > WEATHER_ENSEMBLE_OVERCAST_THRESHOLD_PERCENT
        ):
            self.weather_ensemble_disagreement = (
                "PV presteert beter dan de Solcast-voorspelling, terwijl "
                "KNMI/OpenWeatherMap juist zware bewolking melden - geen "
                "probleem, maar wijkt af van wat verwacht werd."
            )

    def _update_appliance_state_machine(
        self,
        now: datetime,
        power_entity: str | None,
        state_attr: str,
        cycle_started_attr: str,
        below_threshold_since_attr: str,
        duration_history_attr: str,
        notify_title: str | None = None,
    ) -> None:
        """RUSTEND/ACTIEF/KLAAR-toestandsmachine (v0.63.32, "Optie 1" na
        overleg) - een eenvoudiger alternatief voor echte Markov-
        fasedetectie (vullen/wassen/spoelen/centrifugeren), die
        merk/model-specifieke vermogenspatronen zou vereisen waar geen
        trainingsdata voor is. Alleen aan/uit, geen fases.

        RUSTEND -> ACTIEF: vermogen komt boven
        APPLIANCE_RUNNING_POWER_THRESHOLD_W.
        ACTIEF -> KLAAR: vermogen blijft
        APPLIANCE_CYCLE_COMPLETE_SUSTAINED_MINUTES aanhoudend onder die
        drempel - dezelfde aanhoudend-laag-bevestigt-klaar-logica als de
        steelstofzuiger/fietsladers (v0.63.12/.13), maar met een ruimere
        marge (5 min i.p.v. 2) omdat een cyclus tussentijdse stille fases
        kan hebben (vullen, weken) die een kortere marge ten onrechte als
        "klaar" zou kunnen aanmerken.
        KLAAR -> ACTIEF: een nieuwe cyclus start direct door, zonder
        eerst terug naar RUSTEND te hoeven.

        Bij het afsluiten van een cyclus wordt de duur toegevoegd aan
        `duration_history_attr` (mediaan, LEARNING_HISTORY_DAYS-venster,
        zelfde uitschieter-resistente aanpak als elders) en - als
        geconfigureerd - een melding gestuurd.
        """
        if not power_entity:
            return
        power_w = self._read_sensor_float(power_entity)
        if power_w is None:
            return

        current_state = getattr(self, state_attr)

        if power_w >= APPLIANCE_RUNNING_POWER_THRESHOLD_W:
            setattr(self, below_threshold_since_attr, None)
            if current_state != "actief":
                setattr(self, cycle_started_attr, now)
                setattr(self, state_attr, "actief")
            return

        if current_state != "actief":
            return

        since = getattr(self, below_threshold_since_attr)
        if since is None:
            setattr(self, below_threshold_since_attr, now)
            return

        elapsed_minutes = (now - since).total_seconds() / 60
        if elapsed_minutes < APPLIANCE_CYCLE_COMPLETE_SUSTAINED_MINUTES:
            return

        started_at = getattr(self, cycle_started_attr)
        duration_minutes = None
        if started_at is not None:
            duration_minutes = (now - started_at).total_seconds() / 60
            if duration_minutes > 0:
                history = getattr(self, duration_history_attr)
                history.append(round(duration_minutes, 1))
                setattr(self, duration_history_attr, history[-LEARNING_HISTORY_DAYS:])

        setattr(self, state_attr, "klaar")
        setattr(self, below_threshold_since_attr, None)
        setattr(self, cycle_started_attr, None)

        if notify_title:
            notify_service = self.config.get(CONF_APPLIANCE_NOTIFY_SERVICE)
            if notify_service:
                duration_txt = (
                    f"ongeveer {duration_minutes:.0f} minuten"
                    if duration_minutes is not None
                    else "onbekende tijd"
                )
                self._dispatch_notification(
                    notify_service=notify_service,
                    title=notify_title,
                    message=f"Klaar na {duration_txt}.",
                    notification_id=f"ems_{state_attr}_cycle_done",
                )

    def _process_water_flow_sample(
        self, flow_l_per_min: float, now: datetime
    ) -> None:
        """Water-sessie-toestandsmachine (v0.63.85, herontworpen in
        v0.63.98 - gerapporteerd met ruwe geschiedenis: "in de tabel
        ontbreekt data" - van de 64 losse verbruiksstoten in de
        geschiedenis werd er maar 1 als sessie gelogd).

        Root cause: de oorspronkelijke, puur tick-gebaseerde detectie
        (elke 5 minuten het live debiet uitlezen) miste vrijwel alle
        korte stoten (vaak maar 15-90 seconden, bijv. handen wassen,
        toilet doorspoelen) - een 5-minuten-steekproef heeft simpelweg
        te weinig kans om zo'n kort venster te raken.

        Nu event-driven aangeroepen (v0.63.98,
        `_handle_water_flow_change`): een aparte listener
        (`async_track_state_change_event`) reageert direct op élke
        wijziging van de watersensor zelf, in plaats van te wachten op
        de volgende 5-minuten-tick - vangt zo vrijwel elke stoot,
        ongeacht hoe kort.

        Bewust géén pure event-driven aanpak voor de AFRONDING van een
        sessie: onderzoek van de ruwe sensorgeschiedenis liet gaten tot
        bijna 7 uur zien tussen updates zolang het debiet stil op 0
        staat - de sensor "hartslag"-t niet betrouwbaar bij rust. Deze
        functie wordt daarom zowel vanuit de listener (reactief, bij
        elke wijziging) ALS vanuit de gewone 5-minuten-tick
        (`_update_water_tracking`, als vangnet) aangeroepen met de dan
        actuele meting - zo kan een sessie nooit "vast blijven staan"
        wachtend op een event dat misschien uren niet komt.

        Puur de toestandsmachine zelf - leest geen entiteiten, ontvangt
        de meting + tijdstip als parameter, zodat dezelfde logica
        identiek werkt vanuit beide aanroeppunten.

        v0.63.119, gerapporteerd (derde keer): "dagtotaal (85 L) is een
        stuk hoger dan wat de geregistreerde gebruiksmomenten van
        vandaag verklaren (5 L)". De liters per moment kwamen tot nu toe
        uitsluitend uit het VERSCHIL van de cumulatieve meterstand
        tussen start en einde. Dat is zo nauwkeurig als de resolutie van
        die meter: bij een stand in m3 met twee decimalen is de kleinste
        waarneembare stap 10 liter, dus elke kraan-, toilet- of
        handen-was-stoot komt uit op precies 0,0 L. De momenten werden
        dan wel gelogd, maar met een volume van nul - en dan verklaart
        de som ervan inderdaad vrijwel niets van het dagtotaal.

        De liters worden nu primair bepaald door het DEBIET te
        integreren: bij elke meting wordt het vorige debiet
        vermenigvuldigd met de sindsdien verstreken tijd en opgeteld.
        Dat werkt op de resolutie van de debietsensor zelf (L/min) en is
        dus ongevoelig voor de stapgrootte van de meterstand. De
        meterstand-methode blijft als kruiscontrole behouden en wordt
        apart meegelogd, zodat een afwijking tussen beide zichtbaar is
        in plaats van stilzwijgend.

        Een te groot gat tussen twee metingen (bijv. na een herstart)
        wordt niet geïntegreerd - anders zou een achtergebleven debiet
        urenlang worden doorgerekend.
        """
        total_entity = self.config.get(CONF_WATER_TOTAL_USAGE_SENSOR)

        # --- debiet integreren over het interval sinds de vorige meting ---
        if (
            self._water_usage_state == "actief"
            and self._water_last_flow_l_per_min is not None
            and self._water_last_flow_sample_at is not None
        ):
            gap_minutes = (
                now - self._water_last_flow_sample_at
            ).total_seconds() / 60
            if 0 < gap_minutes <= MAX_HOUR_TRACKING_GAP_MINUTES:
                self._water_session_liters_integrated += (
                    self._water_last_flow_l_per_min * gap_minutes
                )
        self._water_last_flow_l_per_min = flow_l_per_min
        self._water_last_flow_sample_at = now

        if flow_l_per_min >= WATER_USAGE_ACTIVE_THRESHOLD_L_PER_MIN:
            self._water_below_threshold_since = None
            if self._water_usage_state != "actief":
                self._water_session_started_at = now
                self._water_usage_state = "actief"
                self._water_session_liters_integrated = 0.0
                if total_entity:
                    self._water_session_start_total_m3 = self._read_sensor_float(
                        total_entity
                    )
            return

        if self._water_usage_state != "actief":
            return

        if self._water_below_threshold_since is None:
            self._water_below_threshold_since = now
            return

        elapsed_minutes = (
            now - self._water_below_threshold_since
        ).total_seconds() / 60
        if elapsed_minutes < WATER_SESSION_COMPLETE_SUSTAINED_MINUTES:
            return

        started_at = self._water_session_started_at
        duration_minutes = None
        if started_at is not None:
            # Trek de aanhoudend-lage staart eraf - dat was geen
            # daadwerkelijk gebruik, slechts de bevestigingsmarge.
            duration_minutes = max(
                0.0,
                (now - started_at).total_seconds() / 60
                - WATER_SESSION_COMPLETE_SUSTAINED_MINUTES,
            )

        meter_liters = None
        if total_entity and self._water_session_start_total_m3 is not None:
            end_total_m3 = self._read_sensor_float(total_entity)
            if end_total_m3 is not None:
                meter_liters = max(
                    0.0,
                    (end_total_m3 - self._water_session_start_total_m3) * 1000,
                )

        # v0.63.119: het geïntegreerde debiet is leidend (ongevoelig
        # voor de stapgrootte van de meterstand); de meterstand blijft
        # als kruiscontrole beschikbaar. Zonder debietgeschiedenis valt
        # het terug op de meterstand, zodat er nooit minder informatie
        # is dan voorheen.
        integrated_liters = round(self._water_session_liters_integrated, 2)
        liters = integrated_liters if integrated_liters > 0 else meter_liters

        if duration_minutes is not None and duration_minutes > 0:
            is_waterontharder = started_at is not None and (
                WATER_SOFTENER_NIGHT_WINDOW_START_HOUR
                <= started_at.hour
                < WATER_SOFTENER_NIGHT_WINDOW_END_HOUR
            )
            self.water_session_history.append(
                {
                    "gestart": started_at.isoformat() if started_at else None,
                    "duur_minuten": round(duration_minutes, 1),
                    "liter": round(liters, 1) if liters is not None else None,
                    "liter_uit_meterstand": (
                        round(meter_liters, 1) if meter_liters is not None else None
                    ),
                    "waarschijnlijk_waterontharder": is_waterontharder,
                }
            )
            self.water_session_history = self.water_session_history[
                -WATER_SESSION_HISTORY_LENGTH:
            ]
            self._record_water_session_for_today(started_at, liters)
            if is_waterontharder:
                self.water_softener_last_regeneration = started_at

        self._water_usage_state = "rustend"
        self._water_below_threshold_since = None
        self._water_session_started_at = None
        self._water_session_start_total_m3 = None
        self._water_session_liters_integrated = 0.0

    def _record_water_session_for_today(
        self, started_at: datetime | None, liters: float | None
    ) -> None:
        """Losstaande dagteller voor afgeronde gebruiksmomenten
        (v0.63.119).

        `water_session_history` bewaart bewust maar de laatste
        WATER_SESSION_HISTORY_LENGTH momenten (weergave op het
        Water-tabblad). De diagnostiek-check telde daar de liters van
        vandaag uit op, waardoor het "verklaarde" dagtotaal structureel
        te laag uitviel zodra er méér momenten op een dag waren dan die
        lijst lang is - onafhankelijk van of de detectie zelf goed
        werkte. Deze teller loopt buiten dat venster om.
        """
        if started_at is None:
            return
        day_key = dt_util.as_local(started_at).date()
        if self._water_sessions_day_key != day_key:
            self._water_sessions_day_key = day_key
            self.water_sessions_today_l = 0.0
            self.water_sessions_today_count = 0
        self.water_sessions_today_count += 1
        if liters is not None:
            self.water_sessions_today_l = round(
                self.water_sessions_today_l + liters, 2
            )

    @callback
    def _handle_battery_cooling_change(self, event) -> None:
        """Live-evaluatie van de accu-koeling bij elke wijziging van de
        accutemperatuur, buitentemperatuur of het accuvermogen
        (v0.63.122).

        De vervangen automatisering had een eigen trigger op vermogen
        boven 500W gedurende 20 seconden. Die "for: 20s"-vertraging is
        hier niet nagebouwd: deze handler draait bij elke wijziging, en
        de hysterese in de uitschakelvoorwaarden voorkomt al dat een
        korte piek de ventilator laat pendelen. Wél een echte
        gedragswijziging, dus expliciet vermeld.
        """
        if event.data.get("new_state") is None:
            return
        self.hass.async_create_task(self._async_apply_battery_cooling())

    @callback
    def _handle_water_flow_change(self, event) -> None:
        """Live, event-driven water-sessie-detectie (v0.63.98,
        gevraagd: "Wat gebeurt er als we naar live tikken gaan?").
        Reageert direct op élke wijziging van de watersensor zelf, in
        plaats van te wachten op de volgende 5-minuten-tick - zie
        `_process_water_flow_sample`'s docstring voor de volledige
        toelichting/aanleiding.
        """
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        try:
            flow_l_per_min = float(new_state.state)
        except (TypeError, ValueError):
            return
        # v0.63.119: `last_changed` levert Home Assistant ALTIJD in UTC
        # aan, terwijl de tick-aanroep lokale tijd doorgeeft. Zonder
        # omrekening kreeg een sessie die via de listener startte een
        # UTC-tijdstip mee, met twee concrete gevolgen: (1) een moment
        # tussen middernacht en 02:00 lokaal werd opgeslagen met de
        # datum van GISTEREN en telde dus niet mee voor "vandaag", en
        # (2) het waterontharder-venster (0-6 uur) verschoof mee, zodat
        # een douche om 07:30 lokaal (05:30 UTC) onterecht als
        # waterontharder-regeneratie werd aangemerkt en een spoeling om
        # 01:15 lokaal juist niet. Zelfde soort fout als de
        # achtertuinsensor-tijdzonebug uit v0.63.93.
        now = dt_util.as_local(new_state.last_changed or dt_util.now())
        self._process_water_flow_sample(flow_l_per_min, now)

    def _update_water_tracking(self, now: datetime) -> None:
        """Water-tabblad (v0.63.85, gevraagd: "Meldingen/tracking zoals
        bij vaatwasser/wasmachine" - herzien naar "geen meldingen alleen
        een watertabblad met relevante info"). Puur informatief - stuurt
        nooit iets aan (geen accu-beslissing hangt hiervan af), en
        verstuurt bewust geen meldingen (expliciet zo gevraagd), in
        tegenstelling tot de vaatwasser/wasmachine-tracking waar dit op
        is gebaseerd.

        Twee onafhankelijke onderdelen:

        1. Dagelijks totaal + geschiedenis (voor trend): volgt de
           geconfigureerde "vandaag"-sensor (die zelf om middernacht
           reset, zoals bevestigd in de aangeleverde entiteitenlijst -
           `last_reset`/`next_reset`-attributen). Zodra de uitlezing
           lager is dan de vorige (de sensor is net gereset), wordt de
           laatst bekende waarde gearchiveerd als "gisteren se totaal".
           Geen eigen reset-logica nodig - leunt op de brondata.

        2. Losse gebruiksmomenten: v0.63.98, deze tick roept nog wel
           `_process_water_flow_sample` aan met de huidige meting -
           puur als vangnet (zie die functie's docstring). De
           daadwerkelijke, fijnmazige detectie gebeurt inmiddels
           live, event-driven via `_handle_water_flow_change`.

        v0.63.86, gevraagd ("wanneer hij zijn werk heeft gedaan en
        hoelang dat geleden is"): elk afgerond gebruiksmoment dat
        start binnen WATER_SOFTENER_NIGHT_WINDOW_START_HOUR/_END_HOUR
        (standaard middernacht-6u) wordt gemarkeerd als
        `waarschijnlijk_waterontharder` en bijgewerkt in
        `water_softener_last_regeneration` - er is geen betrouwbare
        manier om dit puur op debiet/duur te onderscheiden van ander
        gebruik (verschilt per merk/model, geen trainingsdata), maar
        niemand doucht of vult structureel een bad midden in de nacht,
        dus tijdstip alleen is hier al een betrouwbare indicator.
        """
        daily_entity = self.config.get(CONF_WATER_DAILY_TOTAL_SENSOR)
        if daily_entity:
            daily_total = self._read_sensor_float(daily_entity)
            if daily_total is not None:
                if (
                    self._water_last_daily_total is not None
                    and daily_total < self._water_last_daily_total - 0.01
                ):
                    self.water_daily_history.append(
                        round(self._water_last_daily_total, 2)
                    )
                    self.water_daily_history = self.water_daily_history[
                        -LEARNING_HISTORY_DAYS:
                    ]
                self._water_last_daily_total = daily_total
                self.water_daily_total_l = round(daily_total, 2)

        active_entity = self.config.get(CONF_WATER_ACTIVE_USAGE_SENSOR)
        if not active_entity:
            return
        flow_l_per_min = self._read_sensor_float(active_entity)
        if flow_l_per_min is None:
            return

        self._process_water_flow_sample(flow_l_per_min, now)

    def _compute_mpc_plan(self, now: datetime, entries: list[PriceEntry]) -> None:
        """MPC (Model Predictive Control) advisory engine (v0.63.33).

        ADVISORY ONLY - confirmed explicitly before building this: never
        sends a device command, never overrides `_async_apply_manual`/
        `_async_apply_operation` or any part of the existing, tested
        decision tree. Purely computes and exposes a projected
        charge/discharge plan for comparison.

        Algorithm: greedy interval pairing over the full available price
        forecast horizon (today + tomorrow, up to MPC_HORIZON_HOURS).
        Repeatedly matches the single cheapest remaining quarter with the
        single priciest remaining quarter and allocates a charge/
        discharge chunk between them (bounded by physical charge/
        discharge rate and remaining battery headroom), as long as the
        pair clears MPC_MIN_MARGIN_EUR_PER_KWH after efficiency losses.
        Stops as soon as the best remaining pair doesn't clear the
        margin - correct termination, since quarters are pre-sorted by
        price and no later pair could be more profitable than the
        current best remaining one.

        This is a well-established good heuristic for the storage-
        arbitrage problem, not a true linear-programming solve (no
        scipy/pulp dependency added, to keep a HACS integration
        lightweight) - individually inspectable allocation steps
        instead of an opaque solver's output.

        Deliberately PURE price arbitrage: does not model household
        consumption or PV production, and does not subtract the reserve
        the real decision tree protects for overnight bridging (that
        protection is that engine's job, already tested). This plan's
        projected profit is therefore a theoretical upper bound on
        arbitrage opportunity, not a literal recommendation - `mpc_note`
        states this plainly whenever a plan is produced.

        Requires `battery_total_capacity_sensor_entity` and
        `battery_min_soc_number_entity` (same fields as the v0.63.27
        capacity-aware "dure kwartieren" count) to know how much charge
        headroom exists - without them, no charge/discharge pairs can
        be evaluated (there's no way to know how much more could ever
        be stored), so the plan comes back empty with an explanatory
        note rather than a silently wrong guess.
        """
        self.mpc_last_computed_at = now
        self.mpc_planned_actions = []
        self.mpc_projected_total_profit_eur = None
        self.mpc_horizon_quarters_used = 0

        available_entity = self.config.get(CONF_AVAILABLE_ENERGY_SENSOR)
        if not available_entity:
            self.mpc_note = (
                "Geen available_energy_sensor_entity geconfigureerd - "
                "MPC kan geen plan berekenen zonder te weten hoeveel "
                "energie er nu beschikbaar is."
            )
            return
        available_kwh = self._read_sensor_float(available_entity)
        if available_kwh is None:
            self.mpc_note = "Beschikbare-energie-sensor niet uitleesbaar."
            return

        usable_capacity_kwh = self._max_usable_battery_capacity_kwh()
        if usable_capacity_kwh is None:
            self.mpc_note = (
                "Geen battery_total_capacity_sensor_entity/"
                "battery_min_soc_number_entity geconfigureerd - MPC kan "
                "niet bepalen hoeveel laadruimte er in totaal is, dus "
                "wordt er geen plan berekend (in plaats van te gokken)."
            )
            return

        horizon_end = now + timedelta(hours=MPC_HORIZON_HOURS)
        horizon_entries = [
            e for e in entries if e[0] >= now and e[0] < horizon_end
        ]
        if not horizon_entries:
            self.mpc_note = "Geen prijsdata binnen de horizon."
            return

        base_charge_power_w = abs(
            self.config.get(CONF_MANUAL_CHARGE_POWER, DEFAULT_MANUAL_CHARGE_POWER)
        )
        base_discharge_power_w = self.config.get(
            CONF_MANUAL_DISCHARGE_POWER, DEFAULT_MANUAL_DISCHARGE_POWER
        )
        efficiency_percent = self.learned_battery_efficiency_percent
        if efficiency_percent is None:
            efficiency_percent = float(
                self.config.get(
                    CONF_BATTERY_ROUND_TRIP_EFFICIENCY,
                    DEFAULT_BATTERY_ROUND_TRIP_EFFICIENCY_PERCENT,
                )
            )
        efficiency = efficiency_percent / 100

        quarters = []
        for start, end, raw_price in horizon_entries:
            interval_hours = (end - start).total_seconds() / 3600
            if interval_hours <= 0:
                continue
            quarters.append(
                {
                    "start": start,
                    "end": end,
                    "price": raw_price / PRICE_SCALE_FACTOR,
                    "charge_remaining_kwh": (base_charge_power_w / 1000)
                    * interval_hours,
                    "discharge_remaining_kwh": (base_discharge_power_w / 1000)
                    * interval_hours,
                    "net_charge_kwh": 0.0,
                    "net_discharge_kwh": 0.0,
                }
            )
        self.mpc_horizon_quarters_used = len(quarters)
        if not quarters:
            self.mpc_note = "Geen bruikbare kwartieren binnen de horizon."
            return

        cheap_order = sorted(range(len(quarters)), key=lambda i: quarters[i]["price"])
        expensive_order = sorted(
            range(len(quarters)), key=lambda i: -quarters[i]["price"]
        )

        remaining_headroom_kwh = max(0.0, usable_capacity_kwh - available_kwh)
        total_profit = 0.0
        ci, ei = 0, 0
        epsilon = 1e-6

        while (
            ci < len(cheap_order)
            and ei < len(expensive_order)
            and remaining_headroom_kwh > epsilon
        ):
            cheap_idx = cheap_order[ci]
            expensive_idx = expensive_order[ei]
            if cheap_idx == expensive_idx:
                # Same quarter can't be both a buy and a sell - try the
                # next-best on whichever side has more candidates left,
                # simplest correct tie-break: advance the cheap pointer.
                ci += 1
                continue

            cheap_q = quarters[cheap_idx]
            expensive_q = quarters[expensive_idx]
            margin = (efficiency * expensive_q["price"]) - cheap_q["price"]
            if margin < MPC_MIN_MARGIN_EUR_PER_KWH:
                # Sorted by price - no remaining pair can do better.
                break

            chunk_kwh = min(
                remaining_headroom_kwh,
                cheap_q["charge_remaining_kwh"],
                expensive_q["discharge_remaining_kwh"] / efficiency
                if efficiency > 0
                else 0.0,
            )
            if chunk_kwh <= epsilon:
                if cheap_q["charge_remaining_kwh"] <= epsilon:
                    ci += 1
                if expensive_q["discharge_remaining_kwh"] <= epsilon:
                    ei += 1
                continue

            cheap_q["charge_remaining_kwh"] -= chunk_kwh
            cheap_q["net_charge_kwh"] += chunk_kwh
            discharge_chunk_kwh = chunk_kwh * efficiency
            expensive_q["discharge_remaining_kwh"] -= discharge_chunk_kwh
            expensive_q["net_discharge_kwh"] += discharge_chunk_kwh
            remaining_headroom_kwh -= chunk_kwh

            total_profit += (
                discharge_chunk_kwh * expensive_q["price"]
                - chunk_kwh * cheap_q["price"]
            )

            if cheap_q["charge_remaining_kwh"] <= epsilon:
                ci += 1
            if expensive_q["discharge_remaining_kwh"] <= epsilon:
                ei += 1

        actions = []
        for q in quarters:
            if q["net_charge_kwh"] > epsilon:
                actions.append(
                    {
                        "start": q["start"].isoformat(),
                        "end": q["end"].isoformat(),
                        "action": "laden",
                        "price_eur_per_kwh": round(q["price"], 4),
                        "energy_kwh": round(q["net_charge_kwh"], 4),
                    }
                )
            elif q["net_discharge_kwh"] > epsilon:
                actions.append(
                    {
                        "start": q["start"].isoformat(),
                        "end": q["end"].isoformat(),
                        "action": "ontladen",
                        "price_eur_per_kwh": round(q["price"], 4),
                        "energy_kwh": round(q["net_discharge_kwh"], 4),
                    }
                )
        actions.sort(key=lambda a: a["start"])

        self.mpc_planned_actions = actions
        self.mpc_projected_total_profit_eur = round(total_profit, 4)
        self.mpc_note = (
            "Adviserend, puur prijsarbitrage - stuurt nooit een commando "
            "en overschrijft nooit de bestaande beslisboom. Houdt geen "
            "rekening met huishoudverbruik, PV-opwek, of de "
            "nachtreserve die de echte beslisboom apart beschermt; dit "
            "is een theoretisch maximum aan arbitrage-winst, geen "
            "letterlijke aanbeveling."
        )

    def _max_usable_battery_capacity_kwh(self) -> float | None:
        """Live-read usable battery capacity (kWh) = total capacity minus
        the Zendure's own hardware minimum SoC - shared calculation
        between the v0.63.27 capacity-aware "dure kwartieren" count and
        the MPC advisory engine (v0.63.33). None if either entity isn't
        configured/available.
        """
        total_capacity_entity = self.config.get(CONF_BATTERY_TOTAL_CAPACITY_SENSOR)
        min_soc_entity = self.config.get(CONF_BATTERY_MIN_SOC_NUMBER)
        if not total_capacity_entity or not min_soc_entity:
            return None
        total_capacity_kwh = self._read_sensor_float(total_capacity_entity)
        min_soc_percent = self._read_sensor_float(min_soc_entity)
        if total_capacity_kwh is None or min_soc_percent is None:
            return None
        return total_capacity_kwh * max(0.0, 1 - min_soc_percent / 100)

    def _run_monte_carlo_simulation(
        self, now: datetime, cheap_block_start: datetime | None
    ) -> None:
        """Monte Carlo advisory engine (v0.63.34).

        ADVISORY ONLY - confirmed explicitly for the whole batch of
        MPC/Monte Carlo/Kalman/Digital Twin/Database additions before
        building any of them: never sends a device command, never
        overrides the existing decision tree's own worst-case-deficit
        calculation (`_estimate_worst_case_deficit_kwh`) or the reserve
        margin it feeds. Purely computes and exposes a probability
        distribution for comparison.

        Bootstrap-resamples the same empirical history this integration
        already collects and trusts elsewhere - `hourly_consumption_profile`
        (per-hour daily consumption samples) and `pv_hourly_bias_history`
        (per-hour Solcast actual-vs-forecast ratio samples) - instead of
        inventing a new, unvalidated probability distribution (e.g. a
        Gaussian with a guessed standard deviation). Runs
        MONTE_CARLO_SIMULATIONS (1000) randomised trajectories of the
        exact same hour-by-hour "diepste tekort" walk the deterministic
        calculation does, each trajectory drawing one random historical
        sample per hour (with replacement) instead of using the median,
        producing a spread of plausible outcomes instead of one number.

        Deliberately doesn't invent occupancy or weather randomness on
        top - the PV bias history already implicitly reflects weather
        variability (that's *why* the actual/forecast ratio varies day
        to day), and there's no occupancy model in this integration (see
        the "waarom niet" discussion for the Occupancy Engine) to sample
        from.

        Horizon capped at MONTE_CARLO_MAX_HOURS (48) purely for
        performance - 1000 simulations x more hours than that would
        start to add meaningfully to a single 5-minute tick's compute
        time for no real accuracy gain (the deterministic reserve
        calculation already only looks as far as the next cheap block
        anyway).
        """
        self.monte_carlo_median_deficit_kwh = None
        self.monte_carlo_p90_deficit_kwh = None
        self.monte_carlo_p10_deficit_kwh = None
        self.monte_carlo_shortfall_probability_percent = None
        self.monte_carlo_simulations_run = 0
        self.monte_carlo_hours_simulated = 0

        if cheap_block_start is None or cheap_block_start <= now:
            self.monte_carlo_note = (
                "Geen (toekomstig) goedkoopste blok bekend om naartoe te "
                "simuleren."
            )
            return

        efficiency_percent = self.learned_battery_efficiency_percent
        if efficiency_percent is None:
            efficiency_percent = float(
                self.config.get(
                    CONF_BATTERY_ROUND_TRIP_EFFICIENCY,
                    DEFAULT_BATTERY_ROUND_TRIP_EFFICIENCY_PERCENT,
                )
            )
        efficiency_factor = efficiency_percent / 100

        segments = []
        cursor = now
        while cursor < cheap_block_start:
            hour_end = cursor.replace(
                minute=0, second=0, microsecond=0
            ) + timedelta(hours=1)
            segment_end = min(hour_end, cheap_block_start)
            fraction_hours = (segment_end - cursor).total_seconds() / 3600
            pv_base_kwh = self._estimate_pv_kwh_for_period(cursor, segment_end)
            segments.append((cursor.hour, fraction_hours, pv_base_kwh))
            cursor = segment_end
            if len(segments) >= MONTE_CARLO_MAX_HOURS:
                break

        if not segments:
            self.monte_carlo_note = "Geen kwartieren tussen nu en het goedkoopste blok."
            return
        self.monte_carlo_hours_simulated = len(segments)

        deepest_deficits = []
        for _ in range(MONTE_CARLO_SIMULATIONS):
            cumulative_deficit = 0.0
            max_deficit = 0.0
            for hour, fraction_hours, pv_base_kwh in segments:
                samples = self.hourly_consumption_profile.get(hour)
                if samples:
                    consumption_kw = random.choice(samples)
                else:
                    consumption_kw = self.learned_hourly_avg_kw(hour) or 0.0
                consumption_kwh = consumption_kw * fraction_hours

                bias_samples = self.pv_hourly_bias_history.get(hour)
                if bias_samples:
                    bias = random.choice(bias_samples)
                else:
                    bias = self.learned_pv_hourly_ratio(hour)
                    if bias is None:
                        bias = 1.0
                pv_kwh = pv_base_kwh * bias * efficiency_factor

                cumulative_deficit = max(
                    0.0, cumulative_deficit + consumption_kwh - pv_kwh
                )
                max_deficit = max(max_deficit, cumulative_deficit)
            deepest_deficits.append(max_deficit)

        deepest_deficits.sort()
        n = len(deepest_deficits)
        self.monte_carlo_simulations_run = n
        self.monte_carlo_median_deficit_kwh = round(deepest_deficits[n // 2], 3)
        self.monte_carlo_p90_deficit_kwh = round(
            deepest_deficits[min(n - 1, int(n * 0.9))], 3
        )
        self.monte_carlo_p10_deficit_kwh = round(
            deepest_deficits[min(n - 1, int(n * 0.1))], 3
        )

        available_entity = self.config.get(CONF_AVAILABLE_ENERGY_SENSOR)
        available_kwh = (
            self._read_sensor_float(available_entity) if available_entity else None
        )
        if available_kwh is not None:
            shortfall_count = sum(1 for d in deepest_deficits if d > available_kwh)
            self.monte_carlo_shortfall_probability_percent = round(
                100 * shortfall_count / n, 1
            )

        self.monte_carlo_note = (
            "Adviserend - vergelijkt het bestaande, deterministieke "
            "diepste-tekort-cijfer (mediaan-gebaseerd) met een "
            "kansverdeling uit 1000 gesimuleerde trajecten, elk "
            "getrokken uit de al bestaande, geleerde verbruiks- en "
            "PV-voorspellingsfout-geschiedenis. Stuurt nooit een "
            "commando en past de werkelijke reserve-marge niet aan."
        )

    def _update_kalman_filters(self) -> None:
        """Kalman filtering advisory engine (v0.63.35).

        ADVISORY ONLY - confirmed for the whole MPC/Monte Carlo/Kalman/
        Digital Twin/Database batch before building any of them: purely
        computes and exposes a smoothed estimate of three live,
        naturally noisy signals (available_kwh/SoC, live PV power, live
        household load) alongside their raw sensor readings, for
        comparison. Never fed into `_get_dynamic_discharge_reserve_kwh`,
        `_read_corrected_consumption_power`, or any other calculation
        the actual decision tree relies on - those keep using their own
        already-tested smoothing (e.g. the median-based consumption
        correction, v0.59.0/v0.62.0).

        Uses a minimal scalar Kalman filter per signal (see
        `_KalmanFilter1D`) rather than the fixed-window median smoothing
        used elsewhere - a genuinely different technique, weighting the
        previous estimate against the new measurement by their relative
        uncertainty (the Kalman gain) instead of a fixed sample window.
        Process/measurement noise values are heuristic, documented
        defaults (see const.py) - not empirically characterised against
        this specific installation's actual sensor noise, since that
        data doesn't exist.
        """
        available_entity = self.config.get(CONF_AVAILABLE_ENERGY_SENSOR)
        if available_entity:
            raw_kwh = self._read_sensor_float(available_entity)
            if raw_kwh is not None:
                self.kalman_soc_raw_kwh = raw_kwh
                self.kalman_soc_filtered_kwh = round(
                    self._kalman_soc.update(raw_kwh), 4
                )

        pv_entity = self.config.get(CONF_PV_POWER_SENSOR)
        if pv_entity:
            raw_pv_w = self._read_sensor_float(pv_entity)
            if raw_pv_w is not None:
                self.kalman_pv_raw_w = raw_pv_w
                self.kalman_pv_filtered_w = round(self._kalman_pv.update(raw_pv_w), 1)

        load_w = self._read_corrected_consumption_power()
        if load_w is not None:
            self.kalman_load_raw_w = load_w
            self.kalman_load_filtered_w = round(self._kalman_load.update(load_w), 1)

    def _run_digital_twin_simulation(self, now: datetime) -> None:
        """Digital Twin advisory engine (v0.63.36).

        ADVISORY ONLY - confirmed for the whole MPC/Monte Carlo/Kalman/
        Digital Twin/Database batch before building any of them: purely
        computes and exposes a simulated SoC/financial trajectory,
        never sends a device command, never overrides the real decision
        tree it's modelling.

        Deliberately reuses `self.last_timeline` (already computed every
        tick for the "Overzicht komende uren" dashboard table, complete
        with reserve-aware, price-priority-aware quarter classification
        - v0.40.0/v0.60.0) rather than re-deriving its own
        classification logic - a genuine twin of the real projection,
        not a second, potentially-diverging approximation of it. Walks
        that timeline forward, simulating what the SoC and running
        profit/cost would look like if the projected mode sequence
        actually played out:
        - `manual` (is_expensive quarters): discharge at
          manual_discharge_power, bounded by remaining SoC.
        - `smart` within the identified cheap block: charge at
          manual_charge_power, bounded by remaining capacity headroom.
        - Everything else (smart_discharging, smart outside the cheap
          block): no explicit SoC change in this simplified twin - same
          scope limitation as the MPC advisory engine (v0.63.33), no
          household consumption/PV net-load modelling.

        The natural comparison point: MPC's theoretical-optimum plan
        (v0.63.33) vs. this twin's projection of what *current* rule-
        based behaviour would actually achieve - the gap between them
        shows how much arbitrage headroom (if any) the current logic is
        already capturing.
        """
        self.digital_twin_trajectory = []
        self.digital_twin_projected_profit_eur = None
        self.digital_twin_final_soc_kwh = None
        self.digital_twin_hours_simulated = 0

        if not self.last_timeline:
            self.digital_twin_note = (
                "Nog geen tijdlijn-projectie beschikbaar om te simuleren."
            )
            return

        available_entity = self.config.get(CONF_AVAILABLE_ENERGY_SENSOR)
        if not available_entity:
            self.digital_twin_note = (
                "Geen available_energy_sensor_entity geconfigureerd - de "
                "twin heeft een startpunt nodig om vanaf te simuleren."
            )
            return
        soc_kwh = self._read_sensor_float(available_entity)
        if soc_kwh is None:
            self.digital_twin_note = "Beschikbare-energie-sensor niet uitleesbaar."
            return

        usable_capacity_kwh = self._max_usable_battery_capacity_kwh()
        discharge_power_w = self.config.get(
            CONF_MANUAL_DISCHARGE_POWER, DEFAULT_MANUAL_DISCHARGE_POWER
        )
        charge_power_w = abs(
            self.config.get(CONF_MANUAL_CHARGE_POWER, DEFAULT_MANUAL_CHARGE_POWER)
        )
        horizon_end = now + timedelta(hours=DIGITAL_TWIN_HORIZON_HOURS)

        trajectory = []
        total_profit_eur = 0.0
        hours_simulated = 0.0

        for entry in self.last_timeline:
            start = datetime.fromisoformat(entry["start"])
            end = datetime.fromisoformat(entry["end"])
            if start >= horizon_end:
                break
            interval_hours = (end - start).total_seconds() / 3600
            price = entry["price_per_kwh"]
            mode = entry["mode"]

            if mode == OPTION_MANUAL and entry["is_expensive"]:
                energy_kwh = min(soc_kwh, (discharge_power_w / 1000) * interval_hours)
                soc_kwh -= energy_kwh
                total_profit_eur += energy_kwh * price
            elif (
                mode == OPTION_SMART
                and self.last_cheap_block_start is not None
                and self.last_cheap_block_end is not None
                and self.last_cheap_block_start <= start < self.last_cheap_block_end
                and usable_capacity_kwh is not None
            ):
                headroom_kwh = max(0.0, usable_capacity_kwh - soc_kwh)
                energy_kwh = min(headroom_kwh, (charge_power_w / 1000) * interval_hours)
                soc_kwh += energy_kwh
                total_profit_eur -= energy_kwh * price
            # else (smart_discharging, or smart outside the cheap block):
            # no explicit SoC change in this simplified twin.

            trajectory.append(
                {"start": entry["start"], "mode": mode, "soc_kwh": round(soc_kwh, 3)}
            )
            hours_simulated += interval_hours

        self.digital_twin_trajectory = trajectory
        self.digital_twin_projected_profit_eur = round(total_profit_eur, 4)
        self.digital_twin_final_soc_kwh = round(soc_kwh, 3)
        self.digital_twin_hours_simulated = round(hours_simulated, 1)
        self.digital_twin_note = (
            "Adviserend - simuleert wat de bestaande, regelgebaseerde "
            "logica (dezelfde tijdlijn als 'Overzicht komende uren') aan "
            "SoC/financieel resultaat zou opleveren, als vergelijkingspunt "
            "naast het MPC-adviesplan (theoretisch optimum). Vereenvoudigd: "
            "geen huishoudverbruik/PV-modellering buiten het geïdentificeerde "
            "goedkoopste blok. Stuurt nooit een commando."
        )

    def _nilm_excluded_entity_ids(self) -> set[str]:
        """Entities already tracked elsewhere in this integration -
        never suggested as a "new" NILM candidate, to avoid double-
        counting the battery/PV/grid meter or an already-named
        appliance under a second identity.
        """
        keys = (
            CONF_BATTERY_POWER_SENSOR,
            CONF_PV_POWER_SENSOR,
            CONF_CONSUMPTION_POWER_SENSOR,
            CONF_DISHWASHER_POWER_SENSOR,
            CONF_WASHING_MACHINE_POWER_SENSOR,
            CONF_QUOOKER_POWER_SENSOR,
            CONF_STEELSTOFZUIGER_POWER_SENSOR,
            CONF_FIETSLADERS_POWER_SENSOR,
        )
        return {self.config[k] for k in keys if self.config.get(k)}

    @staticmethod
    def _is_nilm_pattern_excluded(entity_id: str, friendly_name: str) -> bool:
        """Structurele uitsluiting op naampatroon (v0.63.89, gevraagd:
        "alles waar fase 1 bij staat mag sowieso uitgesloten worden net
        als solaredge en zendure entiteiten") - een substring-match
        tegen zowel entity_id als friendly_name, kleine letters. Anders
        dan `_nilm_excluded_entity_ids()` (exacte match tegen specifiek
        geconfigureerde entiteiten), dit sluit hele categorieën uit
        zonder losse afwijzing per sub-fase-sensor of accu-/omvormer-
        signaal.
        """
        haystack = f"{entity_id} {friendly_name}".lower()
        return any(keyword in haystack for keyword in NILM_PATTERN_EXCLUDED_KEYWORDS)

    @staticmethod
    def _is_own_integration_entity(entity_id: str) -> bool:
        """True als deze entity_id bij deze integratie zelf hoort
        (v0.63.103, gerapporteerd: "elke keer terug krijg onbevestigde
        kandidaten na herstart" - deze integratie stelde inmiddels ook
        haar EIGEN, afgeleide sensoren voor als NILM-kandidaat, bijv.
        "Hourly consumption profile", "Piekvermogen"). Elke entity_id
        van deze integratie volgt het patroon
        sensor.<apparaat>_energy_management_system_<naam>, dus DOMAIN
        als substring is een betrouwbare, generieke uitsluiting die
        geen onderhoud per nieuwe sensor vereist.
        """
        return f"_{DOMAIN}_" in entity_id or entity_id.endswith(f"_{DOMAIN}")

    def _prune_nilm_pattern_excluded_entries(self) -> None:
        """Ruimt entiteiten op die al als kandidaat, bevestigd of
        afgewezen stonden vóórdat het naampatroon werd ingesteld
        (v0.63.89) - anders zou een structurele uitsluiting alleen
        NIEUW ontdekte entiteiten raken, niet wat er al in de lijsten
        stond. v0.63.103: ruimt nu ook eigen-integratie-sensoren op
        (zie `_is_own_integration_entity`).
        """
        for entity_id in list(self.nilm_unconfirmed_candidates.keys()):
            candidate = self.nilm_unconfirmed_candidates[entity_id]
            if self._is_own_integration_entity(entity_id) or self._is_nilm_pattern_excluded(
                entity_id, candidate.get("friendly_name", entity_id)
            ):
                del self.nilm_unconfirmed_candidates[entity_id]

        removed_confirmed = False
        for entity_id in list(self.nilm_confirmed_devices.keys()):
            device = self.nilm_confirmed_devices[entity_id]
            if self._is_own_integration_entity(entity_id) or self._is_nilm_pattern_excluded(
                entity_id, device.get("friendly_name", entity_id)
            ):
                del self.nilm_confirmed_devices[entity_id]
                removed_confirmed = True

        # Ook eerder afgewezen entiteiten die nu al patroon-uitgesloten
        # zijn, uit de aparte lijst verwijderen - overbodig geworden nu
        # de patroonmatch dat werk structureel doet, en houdt die lijst
        # klein en betekenisvol.
        pruned_rejected = [
            entity_id
            for entity_id in self.nilm_rejected_entities
            if not self._is_own_integration_entity(entity_id)
            and not self._is_nilm_pattern_excluded(entity_id, entity_id)
        ]
        rejected_changed = len(pruned_rejected) != len(self.nilm_rejected_entities)
        self.nilm_rejected_entities = pruned_rejected

        if removed_confirmed or rejected_changed:
            self.hass.async_create_task(
                self._async_save_nilm_confirmed_devices_store()
            )

    def _update_nilm_discovery(self, now: datetime) -> None:
        """NILM-like device auto-discovery (v0.63.39).

        NOT genuine NILM (blind disaggregation of a single aggregate
        power signal into individual appliance loads - a research-grade
        problem this integration has no training data for). Instead:
        discovers *existing* power-measuring sensor entities already in
        Home Assistant (smart plugs, appliances that report their own
        consumption) that aren't already tracked elsewhere in this
        integration, and lists them as unconfirmed candidates.

        Deliberately requires explicit human confirmation
        (`confirm_nilm_device`/`reject_nilm_device` services) before any
        drift-detection tracking begins - broad auto-discovery (any W/kW
        sensor) will pick up false positives (a random utility sensor
        that happens to report Watts, or this integration's own derived
        sensors), and confirming/rejecting is the only way to keep the
        confirmed list actually meaningful. Never influences any battery
        decision - purely informational (confirmed with the person
        before building this).

        v0.63.89: structural name-pattern exclusion ("fase 1"/"fase_1"/
        "solaredge"/"zendure") runs once per tick, before the discovery
        scan itself, pruning anything already in the candidate/
        confirmed/rejected lists that matches - so this reaches
        everything already present, not just newly-discovered entities
        going forward.
        """
        self._prune_nilm_pattern_excluded_entries()
        excluded = self._nilm_excluded_entity_ids()
        for state in self.hass.states.async_all():
            entity_id = getattr(state, "entity_id", None)
            if not entity_id or not entity_id.startswith("sensor."):
                continue
            if self._is_own_integration_entity(entity_id):
                continue
            if entity_id in excluded:
                continue
            if entity_id in self.nilm_confirmed_devices:
                continue
            if entity_id in self.nilm_rejected_entities:
                continue
            friendly_name = state.attributes.get("friendly_name", entity_id)
            if self._is_nilm_pattern_excluded(entity_id, friendly_name):
                continue
            unit = state.attributes.get("unit_of_measurement")
            if unit not in ("W", "kW"):
                continue
            power_w = self._read_sensor_float(entity_id)
            existing = self.nilm_unconfirmed_candidates.get(entity_id, {})
            self.nilm_unconfirmed_candidates[entity_id] = {
                "friendly_name": friendly_name,
                "current_power_w": power_w,
                "first_seen": existing.get("first_seen", now.date().isoformat()),
            }

    def confirm_nilm_device(self, entity_id: str) -> bool:
        """Move a discovered candidate to the confirmed list, starting
        per-device CUSUM drift-detection for it. Returns False if the
        entity isn't a currently-known candidate (e.g. a typo, or it's
        already confirmed/rejected).

        Notifies listeners immediately (v0.63.50) - reported: after
        pressing confirm/reject on one slot's button, its sibling button
        (the other action for that same slot) kept showing the old
        candidate until the next 5-minute update tick. A button press
        only writes *that one entity's* own state automatically; it
        doesn't know its slot-sibling exists. Since a slot's occupant
        can shift right after any confirm/reject (the next candidate
        moves in), every registered NILM button needs to refresh right
        away, not just the one that was pressed.

        Also persists to the dedicated Store (v0.63.66) - fire-and-
        forget, since this method itself isn't async and every caller
        (button presses, services) already triggers its own
        async_update() right after anyway.
        """
        candidate = self.nilm_unconfirmed_candidates.pop(entity_id, None)
        if candidate is None:
            return False
        self.nilm_confirmed_devices[entity_id] = {
            "friendly_name": candidate["friendly_name"],
            "confirmed_at": date.today().isoformat(),
            "daily_avg_history": [],
            "cusum_accumulator": 0.0,
            "anomaly_detected": False,
            "estimated_drift_percent": None,
            "reference_avg_w": None,
            "_today_sum": 0.0,
            "_today_count": 0,
            "_check_date": None,
        }
        self._notify_listeners()
        self.hass.async_create_task(self._async_save_nilm_confirmed_devices_store())
        return True

    def reject_nilm_device(self, entity_id: str) -> bool:
        """Permanently ignore a discovered candidate - never suggested
        again. Also removes it from the confirmed list, if it was
        confirmed earlier and the person changed their mind.

        Notifies listeners immediately - see `confirm_nilm_device`'s
        docstring for why (v0.63.50). Also persists to the dedicated
        Store (v0.63.66) - see `confirm_nilm_device`'s docstring.
        """
        self.nilm_unconfirmed_candidates.pop(entity_id, None)
        self.nilm_confirmed_devices.pop(entity_id, None)
        if entity_id not in self.nilm_rejected_entities:
            self.nilm_rejected_entities.append(entity_id)
        self._notify_listeners()
        self.hass.async_create_task(self._async_save_nilm_confirmed_devices_store())
        return True

    def unconfirm_nilm_device(self, entity_id: str) -> bool:
        """Removes a confirmed device and its entire learned CUSUM
        history (baseline, drift state, daily averages) so it can be
        re-discovered and re-confirmed fresh with a brand-new baseline
        (v0.63.68, requested: "hoe kan ik een NILM apparaat verwijderen
        en opnieuw beoordelen?") - e.g. the appliance itself changed
        (replaced, repaired) so its old learned baseline no longer
        applies.

        Deliberately different from `reject_nilm_device`: does NOT add
        the entity to `nilm_rejected_entities`, so the next discovery
        scan is free to surface it again as a fresh, unconfirmed
        candidate - unlike reject, which permanently blacklists it.
        Returns False if the entity wasn't actually a confirmed device.

        Notifies listeners immediately and persists to the dedicated
        Store, same as confirm/reject (v0.63.50/.66).
        """
        removed = self.nilm_confirmed_devices.pop(entity_id, None)
        if removed is None:
            return False
        self._notify_listeners()
        self.hass.async_create_task(self._async_save_nilm_confirmed_devices_store())
        return True

    @property
    def nilm_store_had_data(self) -> bool:
        """True zodra de Store van schijf is gelezen én daar echte
        bevestigde/afgewezen NILM-data in stond (v0.63.115). Dit is het
        enige betrouwbare signaal dat de Store de bron van waarheid is;
        "de lijsten in het geheugen zijn leeg" is dat NIET (die zijn óók
        leeg als de Store simpelweg nog niet gelezen is).
        """
        return self._nilm_store_had_data

    async def async_load_persisted_nilm_state(self) -> None:
        """Publieke ingang om de NILM-Store te laden (v0.63.115).

        Wordt in `async_setup_entry` aangeroepen VÓÓR
        `async_forward_entry_setups`, zodat de Store gegarandeerd
        gelezen is voordat `NilmConfirmedDevicesSensor.
        async_added_to_hass` draait. Zie
        `_async_load_nilm_confirmed_devices_store` voor waarom die
        volgorde cruciaal is.
        """
        await self._async_load_nilm_confirmed_devices_store()

    async def _async_load_nilm_confirmed_devices_store(self) -> None:
        """Loads confirmed NILM devices + rejected entities from the
        dedicated Store (v0.63.66) - see the `_nilm_confirmed_devices_
        store` init comment for why this exists separately from the
        entity's own restored HA state. Leaves existing in-memory state
        untouched if the Store is empty (e.g. a genuinely fresh install,
        or an existing install upgrading before this Store has ever been
        written - `NilmConfirmedDevicesSensor.async_added_to_hass`
        handles that one-time migration from the entity's restored
        state instead).

        v0.63.115, gerapporteerd (na v0.63.107): "keuzes voor NILM
        apparaten worden nog steeds niet opgeslagen, de onbevestigde
        lijst blijft terug komen na een herstart". ECHTE root cause,
        los van de knop-race van v0.63.107:

        `async_setup_entry` deed `async_forward_entry_setups(...)`
        VOORDAT `coordinator.async_setup()` (en dus deze load) draaide.
        Daardoor liep `NilmConfirmedDevicesSensor.async_added_to_hass`
        altijd met een nog volledig LEGE `nilm_confirmed_devices` /
        `nilm_rejected_entities`. Die methode gebruikte "leeg" als
        bewijs dat de Store leeg was, viel dus bij ELKE herstart terug
        op de eenmalig-bedoelde migratiepad vanuit de eigen herstelde
        entiteit-state - en die attributen zijn met opzet AFGEKAPT op
        NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT (20). Vervolgens schreef
        die methode dat afgekapte resultaat meteen terug naar de Store,
        waarmee de volledige, goede inhoud werd OVERSCHREVEN. Pas
        daarna las deze load de zojuist verminkte Store terug.

        Netto per herstart: bevestigde apparaten hard afgekapt op 20
        (de gebruiker zag exact 20), en afgewezen entiteiten óók op 20 -
        alles daarboven kwam terug als "onbevestigde kandidaat". Precies
        het gerapporteerde beeld.

        Deze load is nu idempotent (een tweede aanroep leest niet
        opnieuw over verser geheugen heen) en registreert expliciet of
        er echte data in de Store stond, zodat het migratiepad in de
        sensor niet meer hoeft te gissen.
        """
        if self._nilm_store_loaded:
            # Al gelezen (de load draait nu zowel vóór platform-setup
            # als vanuit async_setup) - niet nogmaals over geheugen
            # heen lezen dat inmiddels verser kan zijn.
            return
        stored = await self._nilm_confirmed_devices_store.async_load()
        self._nilm_store_loaded = True
        if not isinstance(stored, dict):
            return
        devices = stored.get("nilm_confirmed_devices")
        if isinstance(devices, dict):
            self.nilm_confirmed_devices = devices
            if devices:
                self._nilm_store_had_data = True
        rejected = stored.get("nilm_rejected_entities")
        if isinstance(rejected, list):
            self.nilm_rejected_entities = rejected
            if rejected:
                self._nilm_store_had_data = True
        # v0.63.118: beoordeelde duplicaatparen horen bij dezelfde
        # door de gebruiker gecureerde staat en gaan door dezelfde
        # Store - inclusief de volgorde-borging van v0.63.115.
        dismissed = stored.get("nilm_dismissed_duplicate_pairs")
        if isinstance(dismissed, list):
            self.nilm_dismissed_duplicate_pairs = dismissed
            if dismissed:
                self._nilm_store_had_data = True

    async def _async_save_nilm_confirmed_devices_store(self) -> None:
        """Persists confirmed NILM devices + rejected entities to the
        dedicated Store (v0.63.66)."""
        await self._nilm_confirmed_devices_store.async_save(
            {
                "nilm_confirmed_devices": self.nilm_confirmed_devices,
                "nilm_rejected_entities": self.nilm_rejected_entities,
                "nilm_dismissed_duplicate_pairs": (
                    self.nilm_dismissed_duplicate_pairs
                ),
            }
        )

    def get_nilm_devices_table(self) -> list[dict]:
        """Simple 3-column overview (naam, huidig vermogen, trend) of
        all confirmed NILM devices, requested for the dashboard
        (v0.63.51). Live power read fresh on every call; trend derived
        from the existing CUSUM tracking (v0.63.39) - no new tracking
        mechanism needed. Sorted by name for a stable, predictable
        display order.
        """
        rows = []
        for entity_id, device in sorted(
            self.nilm_confirmed_devices.items(),
            key=lambda item: item[1].get("friendly_name") or item[0],
        ):
            rows.append(
                {
                    "naam": device.get("friendly_name") or entity_id,
                    "huidig_vermogen_w": self._read_sensor_float(entity_id),
                    "trend": self._describe_nilm_trend(device),
                }
            )
        return rows

    def get_largest_known_consumer(self) -> str:
        """Welk bekend apparaat op dit moment het meeste verbruikt
        (v0.63.130, gerapporteerd: "in de visual is nu de zwaarste bron
        nog niet zichtbaar, mijn inziens is er altijd een zwaarste bron
        ook al zou die maar 10 W zijn").

        Terecht, en de oorzaak was een verkeerd gekozen bron: de kaart
        toonde `heavy_load_source`, en dat is een BESLISLOGICA-signaal.
        Dat geeft alleen iets terug als een specifiek zwaar apparaat
        (vaatwasser, wasmachine, Quooker, airco, oven, kookplaat)
        aantoonbaar draait, want het dient om de mediaan-voorzichtigheid
        van de verbruikscorrectie over te slaan. Het hoort dus meestal
        leeg te zijn - het label beloofde iets anders dan het attribuut
        betekende.

        Deze functie beantwoordt de werkelijke vraag: van alle apparaten
        met een eigen vermogensmeting (de bevestigde NILM-apparaten,
        v0.63.39) degene met het hoogste verbruik nu.

        Negatieve waarden worden overgeslagen: onder de bevestigde
        apparaten zitten ook productie-entiteiten (bijv. een
        omvormerkanaal dat -4 W teruglevert), en die zijn geen
        verbruiker. Hetzelfde geldt voor precies 0 W - "grootste
        verbruiker: 0 W" is geen informatie.

        Valt terug op het zwaar-apparaat-signaal als er geen enkel
        NILM-apparaat een bruikbare meting geeft, zodat een draaiende
        vaatwasser zonder bevestigde NILM-apparaten alsnog zichtbaar is.

        BEPERKING, bewust: dit ziet alleen apparaten die zelf hun
        vermogen meten. Is de werkelijk grootste verbruiker een apparaat
        zonder meting, dan staat die er niet bij - het is "de grootste
        BEKENDE verbruiker", niet "de grootste verbruiker".
        """
        beste_naam = None
        beste_vermogen = 0.0
        for rij in self.get_nilm_devices_table():
            vermogen = rij.get("huidig_vermogen_w")
            if vermogen is None or vermogen <= 0:
                continue
            if vermogen > beste_vermogen:
                beste_vermogen = vermogen
                beste_naam = rij["naam"]

        if beste_naam is not None:
            return f"{beste_naam} ({beste_vermogen:.0f} W)"

        if self.last_heavy_load_source:
            return str(self.last_heavy_load_source)
        return "geen gemeten apparaat actief"

    def get_nilm_duplicate_pairs(self) -> list[dict]:
        """Waarschijnlijke duplicaten onder bevestigde NILM-apparaten
        (v0.63.91, gevonden tijdens een diagnostiek-review: 5
        "Eetkamer lamp"-sensoren deelden een identieke vermogens-
        geschiedenis - vermoedelijk hetzelfde fysieke circuit onder
        meerdere HA-entiteiten).

        Vergelijkt elk paar bevestigde apparaten op basis van hun
        `daily_avg_history` over de gedeelde dagen: als alle gedeelde
        dagwaarden binnen
        `NILM_DUPLICATE_TOLERANCE_FRACTION` van elkaar liggen (en er
        genoeg gedeelde dagen zijn, `NILM_DUPLICATE_MIN_SHARED_DAYS`),
        is dat een sterke aanwijzing dat beide entiteiten hetzelfde
        onderliggende signaal meten. Puur informatief - stuurt niets
        aan, beslist niets automatisch.

        v0.63.118: paren die de gebruiker heeft beoordeeld als "geen
        duplicaat" worden overgeslagen (`nilm_dismissed_duplicate_
        pairs`). Zonder dat bleef een bewust geaccepteerd paar elke
        keer opnieuw opduiken zonder enige manier om het weg te
        krijgen - precies de aanleiding voor deze wijziging.
        """
        entities = sorted(self.nilm_confirmed_devices.keys())
        dismissed = set(self.nilm_dismissed_duplicate_pairs)
        pairs = []
        for i, entity_a in enumerate(entities):
            history_a = self.nilm_confirmed_devices[entity_a].get(
                "daily_avg_history"
            ) or []
            if len(history_a) < NILM_DUPLICATE_MIN_SHARED_DAYS:
                continue
            for entity_b in entities[i + 1 :]:
                if self._duplicate_pair_key(entity_a, entity_b) in dismissed:
                    continue
                history_b = self.nilm_confirmed_devices[entity_b].get(
                    "daily_avg_history"
                ) or []
                shared_len = min(len(history_a), len(history_b))
                if shared_len < NILM_DUPLICATE_MIN_SHARED_DAYS:
                    continue

                shared_a = history_a[-shared_len:]
                shared_b = history_b[-shared_len:]
                all_close = True
                for value_a, value_b in zip(shared_a, shared_b):
                    reference = max(abs(value_a), abs(value_b), 0.01)
                    if (
                        abs(value_a - value_b) / reference
                        > NILM_DUPLICATE_TOLERANCE_FRACTION
                    ):
                        all_close = False
                        break

                if all_close:
                    pairs.append(
                        {
                            "apparaat_1": (
                                self.nilm_confirmed_devices[entity_a].get(
                                    "friendly_name"
                                )
                                or entity_a
                            ),
                            "apparaat_2": (
                                self.nilm_confirmed_devices[entity_b].get(
                                    "friendly_name"
                                )
                                or entity_b
                            ),
                            "entity_id_1": entity_a,
                            "entity_id_2": entity_b,
                            "gedeelde_dagen": shared_len,
                        }
                    )
        return pairs

    @staticmethod
    def _duplicate_pair_key(entity_a: str, entity_b: str) -> str:
        """Richting-onafhankelijke sleutel voor een duplicaatpaar
        (v0.63.118). Alfabetisch gesorteerd, zodat (A,B) en (B,A)
        dezelfde sleutel opleveren - anders zou een beoordeeld paar
        alsnog terugkomen zodra de detectie de volgorde omdraait
        (bijvoorbeeld na een hernoeming die de sortering verandert).
        """
        first, second = sorted([entity_a, entity_b])
        return f"{first}|{second}"

    def get_nilm_duplicate_pair_at_slot(self, slot_index: int) -> dict | None:
        """Welk duplicaatpaar op dit moment dashboard-sleuf
        `slot_index` bezet (v0.63.118) - zelfde sleuf-principe als
        `get_nilm_candidate_at_slot`, om dezelfde reden: een statisch
        Lovelace-dashboard kan geen lijst van onbekende lengte met
        knoppen renderen. Volgorde is die van
        `get_nilm_duplicate_pairs()`, die zelf al deterministisch
        alfabetisch sorteert.
        """
        pairs = self.get_nilm_duplicate_pairs()
        if slot_index < 0 or slot_index >= len(pairs):
            return None
        return pairs[slot_index]

    def dismiss_nilm_duplicate_pair(self, entity_a: str, entity_b: str) -> bool:
        """Markeert een paar als "geen duplicaat" - het verdwijnt uit
        de lijst en komt nooit meer terug (v0.63.118, gevraagd: "dit
        dan ook daadwerkelijk niet meer terug komt als mogelijk
        duplicaat").

        Beide apparaten blijven gewoon bevestigd en getrackt; alleen de
        duplicaat-suggestie over dit specifieke paar verdwijnt. Geeft
        False terug als het paar al beoordeeld was, zodat een dubbele
        druk geen tweede opslag veroorzaakt.
        """
        key = self._duplicate_pair_key(entity_a, entity_b)
        if key in self.nilm_dismissed_duplicate_pairs:
            return False
        self.nilm_dismissed_duplicate_pairs.append(key)
        self._notify_listeners()
        self.hass.async_create_task(self._async_save_nilm_confirmed_devices_store())
        return True

    def confirm_nilm_duplicate_pair(self, entity_a: str, entity_b: str) -> bool:
        """Bevestigt dat een paar écht hetzelfde fysieke signaal meet,
        en handelt daar meteen naar (v0.63.118).

        De zinvolle actie bij een bevestigd duplicaat is er één van de
        twee permanent uitsluiten - anders blijft hetzelfde verbruik
        dubbel geteld worden in elke NILM-weergave. Uitgesloten wordt
        `entity_b`: de alfabetisch tweede van het paar, precies zoals
        het paar wordt getoond. De knop zet die naam ook in zijn eigen
        label, zodat vooraf zichtbaar is WELK apparaat verdwijnt -
        raden hoort hier niet bij.

        Hergebruikt bewust `reject_nilm_device`, zodat het uitgesloten
        apparaat ook echt op de zwarte lijst komt en niet bij de
        volgende scan terugkeert als verse kandidaat. Het paar
        verdwijnt daarmee vanzelf uit `get_nilm_duplicate_pairs()`
        (een van beide is geen bevestigd apparaat meer), dus een aparte
        registratie is niet nodig.
        """
        if entity_b not in self.nilm_confirmed_devices:
            return False
        return self.reject_nilm_device(entity_b)

    def get_missing_optional_features(self) -> list[dict]:
        """Overzicht van optionele, niet-verplichte sensoren die nog
        niet zijn geconfigureerd, met wat elk ontgrendelt (v0.63.105,
        gevraagd: "kun je een melding ergens op een geschikt dashboard
        plaatsen wanneer er 1 ontbreekt" - dit project heeft inmiddels
        veel optionele verbeteringen opgebouwd, elk pas actief zodra de
        bijbehorende entiteit is ingevuld, en dat is makkelijk te
        missen zonder een overzicht).

        Bewust een CURATED lijst (niet elke config-key) - alleen
        optionele sensoren die een zichtbare functie ontgrendelen,
        geen kernvereisten (prijs/accu/PV/verbruik/SoC, zonder welke de
        integratie sowieso niet zinvol kan draaien) en geen
        randfunctionaliteit zonder duidelijke gebruikerswaarde.
        """
        checks = [
            (
                CONF_BACKYARD_TEMPERATURE_SENSOR,
                "Achtertuin-temperatuursensor",
                "Nauwkeurigere live buitentemperatuur + geleerde "
                "bias-correctie op de weersvoorspelling (uitschieter-"
                "filter incluis).",
            ),
            (
                CONF_SOLAR_REMAINING_TODAY_SENSOR,
                "Solcast 'resterend vandaag'-sensor",
                "Live-gecorrigeerde zonverwachting i.p.v. een trage, "
                "langetermijn-gemiddelde schatting.",
            ),
            (
                CONF_CO2_INTENSITY_SENSOR,
                "CO2-intensiteit-sensor",
                "CO2-uitstoot-tracking op het EMS-KPI's-tabblad.",
            ),
            (
                CONF_BATTERY_TOTAL_CAPACITY_SENSOR,
                "Accu-totaalcapaciteit-sensor",
                "Accu-gezondheid: cyclus-telling en geschatte "
                "capaciteitsdegradatie.",
            ),
            (
                CONF_LIVING_ROOM_TEMPERATURE_SENSOR,
                "Woonkamertemperatuursensor",
                "Het hele Klimaat-tabblad (temperatuurprojectie, "
                "airco-verwachting).",
            ),
            (
                CONF_WATER_ACTIVE_USAGE_SENSOR,
                "Waterdebiet-sensor",
                "Het hele Water-tabblad (live debiet, gebruiksmomenten, "
                "waterontharder-detectie).",
            ),
            (
                CONF_APPLIANCE_NOTIFY_SERVICE,
                "Meldingsservice voor apparaten",
                "Meldingen bij vaatwasser/wasmachine klaar en NILM-"
                "anomalieën (mogelijk defecte apparaten).",
            ),
            (
                CONF_DISHWASHER_POWER_SENSOR,
                "Vaatwasser-vermogensensor",
                "Vaatwasser-tracking (cyclusduur, klaar-melding, "
                "gebruikspatroon).",
            ),
            (
                CONF_WASHING_MACHINE_POWER_SENSOR,
                "Wasmachine-vermogensensor",
                "Wasmachine-tracking (cyclusduur, klaar-melding, "
                "gebruikspatroon).",
            ),
        ]

        missing = [
            {"naam": naam, "ontgrendelt": ontgrendelt}
            for key, naam, ontgrendelt in checks
            if not self.config.get(key)
        ]

        # KNMI/OpenWeatherMap: één van beide is genoeg, dus een aparte
        # OR-check in plaats van de generieke lijst hierboven.
        if not self.config.get(CONF_KNMI_WEATHER_ENTITY) and not self.config.get(
            CONF_OPENWEATHERMAP_WEATHER_ENTITY
        ):
            missing.append(
                {
                    "naam": "Weerentiteit (KNMI of OpenWeatherMap)",
                    "ontgrendelt": (
                        "De buitentemperatuur-voorspelling voor de "
                        "Klimaat-projectie."
                    ),
                }
            )

        return missing

    def get_diagnostic_summary(self) -> dict:
        """Snelle gezondheidscheck-samenvatting (v0.63.91, gevraagd:
        "zijn er nog zaken om de integratie te verbeteren, bijvoorbeeld
        de diagnostiek gedetailleerder maken" - concreet ontstaan uit
        een eerdere sessie waarin 150+ diagnostiek-velden handmatig
        moesten worden doorlopen om te zien wat aandacht verdient).

        Verzamelt een korte lijst "aandachtspunten" op basis van
        bestaande, al berekende signalen (geen nieuwe metingen) - puur
        informatief, ter oriëntatie bij een diagnostiek-export, stuurt
        niets aan.

        v0.63.116: twee categorieën in plaats van één.
        `aandachtspunten` zijn zaken die daadwerkelijk actie of
        aandacht verdienen en die de systeemstatus naar "Aandacht
        gewenst" mogen brengen. `informatief` zijn observaties die
        weliswaar het vermelden waard zijn, maar niets zeggen over de
        gezondheid van deze integratie - die blijven zichtbaar maar
        laten de status op "OK" staan. Zonder dat onderscheid zou een
        permanente, bewust geaccepteerde observatie de status voor
        altijd op "Aandacht gewenst" zetten, waarmee het signaal zijn
        waarde verliest.
        """
        aandachtspunten = []
        informatief = []

        if (
            self.measurement_quality is not None
            and self.measurement_quality != "goed"
        ):
            aandachtspunten.append(
                f"Sensor-gezondheid: {self.measurement_quality} "
                f"({self.sensor_health_score}%, "
                f"{len(self.energy_balance_error_history)} metingen)."
            )

        possibly_defective = [
            device.get("friendly_name") or entity_id
            for entity_id, device in self.nilm_confirmed_devices.items()
            if device.get("anomaly_detected")
        ]
        if possibly_defective:
            aandachtspunten.append(
                f"{len(possibly_defective)} apparaat/apparaten mogelijk "
                f"defect: {', '.join(possibly_defective)}."
            )
            # v0.63.100, gevraagd: "kan dit eerder in diagnostiek worden
            # opgevangen" - context of het gedrag inmiddels alweer aan
            # het normaliseren is (op weg naar de auto-reset,
            # NILM_CUSUM_RESET_STREAK_DAYS), zodat direct duidelijk is
            # of een alarm vers/actief is of al bezig met zelfherstel -
            # zonder dat de gebruiker zelf de ruwe CUSUM-waarden hoeft
            # te interpreteren.
            for entity_id, device in self.nilm_confirmed_devices.items():
                if not device.get("anomaly_detected"):
                    continue
                streak = device.get("_normal_streak_days", 0)
                if streak > 0:
                    naam = device.get("friendly_name") or entity_id
                    resterend = max(0, NILM_CUSUM_RESET_STREAK_DAYS - streak)
                    aandachtspunten.append(
                        f"{naam}: {streak} dag(en) op rij weer normaal - "
                        f"herstelt vanzelf over nog {resterend} dag(en) "
                        "als dit aanhoudt."
                    )

        # v0.63.116, gevraagd: "de melding duplicaten zie ik niet als
        # een melding welke systeem status niet naar ok kan brengen".
        # Terecht: waarschijnlijke duplicaatparen zijn een OBSERVATIE
        # over de HA-installatie (twee entiteiten die hetzelfde fysieke
        # signaal meten), niet iets dat mis is met deze integratie of
        # met de accu-aansturing. Bovendien is het een permanente
        # toestand die de gebruiker bewust zo kan laten - dan zou de
        # systeemstatus voor altijd op "Aandacht gewenst" blijven staan
        # en daarmee waardeloos worden als signaal. Gaat daarom naar de
        # aparte `informatief`-lijst: nog steeds zichtbaar in
        # diagnostiek en op het dashboard, maar telt niet mee voor de
        # status.
        # v0.63.123: accu-modulegezondheid. Absolute waarschuwingen zijn
        # echte aandachtspunten; een aanhoudende drift t.o.v. de andere
        # modules ook - dat is juist het signaal dat maanden eerder komt
        # dan een merkbaar capaciteitsverlies.
        for module in self.get_battery_module_table():
            nummer = module.get("module")
            for waarschuwing in module.get("waarschuwingen", []):
                aandachtspunten.append(f"Accumodule {nummer}: {waarschuwing}.")
            if module.get("drift_op"):
                velden = ", ".join(module["drift_op"])
                aandachtspunten.append(
                    f"Accumodule {nummer} loopt aanhoudend uit de pas met de "
                    f"andere modules ({velden}) - dit is een trend over "
                    "meerdere dagen, geen momentopname."
                )

        spreiding = self.battery_module_spread or {}
        temp_spreiding = spreiding.get("temperatuur_c")
        if (
            temp_spreiding is not None
            and temp_spreiding >= BATTERY_MODULE_TEMPERATURE_SPREAD_ATTENTION_C
        ):
            aandachtspunten.append(
                f"Accumodules verschillen {temp_spreiding:.1f} °C in "
                "celtemperatuur - bij gelijke belasting wijst dat op een "
                "module met hogere inwendige weerstand."
            )
        soc_spreiding = spreiding.get("soc_percent")
        if (
            soc_spreiding is not None
            and soc_spreiding >= BATTERY_MODULE_SOC_SPREAD_ATTENTION_PERCENT
        ):
            aandachtspunten.append(
                f"Accumodules verschillen {soc_spreiding:.1f}% in SoC - een "
                "module komt niet meer mee met de rest."
            )

        duplicate_pairs = self.get_nilm_duplicate_pairs()
        if duplicate_pairs:
            informatief.append(
                f"{len(duplicate_pairs)} waarschijnlijke NILM-duplicaat"
                f"paar/paren gevonden (zie 'waarschijnlijke_duplicaten')."
            )

        recent_shortfalls = sum(1 for r in self.reserve_daily_records if r["shortfall"])
        if recent_shortfalls > 0:
            aandachtspunten.append(
                f"{recent_shortfalls} onverwachte tekort-dag(en) in de "
                f"laatste {len(self.reserve_daily_records)} dagen."
            )

        if self.sluipverbruik_detected:
            aandachtspunten.append(
                "Sluipverbruik-detectie staat aan: structurele stijging "
                "in het dagelijkse basisverbruik."
            )

        # v0.63.108, gevraagd: "kun je zien te detecteren in de
        # diagnose" - drie proactieve checks, elk direct terug te
        # voeren op een concreet gerapporteerd patroon uit deze en de
        # vorige sessie, zodat toekomstige vergelijkbare situaties
        # zichtbaar worden zonder dat de gebruiker ze eerst zelf hoeft
        # op te merken/rapporteren.

        # 1. Klimaat-projectie zonder ENKELE geleerde cel, ondanks dat
        # er al enige tijd is verstreken sinds de eerste opstart -
        # verklaart waarom "Korte termijn" en "Betrouwbaar" er
        # identiek uitzien (niets te onderscheiden zolang geen enkele
        # cel data heeft) zonder dat dit een regressie is.
        if self.config.get(CONF_LIVING_ROOM_TEMPERATURE_SENSOR):
            any_cell_with_data = any(
                len(history) > 0 for history in self.climate_rate_history.values()
            )
            if not any_cell_with_data and self.first_seen_date is not None:
                days_running = (dt_util.now().date() - self.first_seen_date).days
                if days_running >= 2:
                    aandachtspunten.append(
                        "Klimaat-projectie: nog geen enkele geleerde cel na "
                        f"{days_running} dagen - 'Korte termijn' en "
                        "'Betrouwbaar' tonen daardoor nog exact dezelfde, "
                        "bevroren temperatuur (geen bug, gewoon nog niets "
                        "om te onderscheiden)."
                    )

        # 2. Ongewoon groot aantal onbevestigde NILM-kandidaten - kan
        # duiden op een nog ontbrekend structureel uitsluitingspatroon
        # (zoals eerder SolarFlow/Solcast/fase 2-3/P1 meter bleken te
        # zijn) i.p.v. losse, individuele beoordeling.
        candidate_count = len(self.nilm_unconfirmed_candidates)
        if candidate_count >= NILM_CANDIDATE_COUNT_ATTENTION_THRESHOLD:
            aandachtspunten.append(
                f"{candidate_count} onbevestigde NILM-kandidaten - "
                "overweeg de patroon-uitsluiting te herzien in plaats "
                "van elk apparaat apart te beoordelen."
            )

        # 3. Waterverbruik: dagtotaal een stuk hoger dan wat de
        # geregistreerde gebruiksmomenten van vandaag bij elkaar
        # optellen - een resterend signaal dat er nog steeds
        # verbruiksstoten gemist worden, ook na de v0.63.98-fix (event-
        # driven detectie), bijv. als de listener om wat voor reden dan
        # ook niet actief is.
        if self.config.get(CONF_WATER_DAILY_TOTAL_SENSOR) and (
            self.water_daily_total_l is not None and self.water_daily_total_l >= 20
        ):
            today_str = dt_util.now().date().isoformat()
            # v0.63.119: primair de losstaande dagteller gebruiken -
            # die wordt niet begrensd door de weergavelijst van 20
            # momenten. De optelling over `water_session_history`
            # blijft als terugval voor een verse start (teller nog leeg
            # terwijl er wel al historie is, bijv. net na een herstart).
            sessions_today_liters = 0.0
            sessions_today_count = 0
            if (
                self._water_sessions_day_key is not None
                and self._water_sessions_day_key.isoformat() == today_str
            ):
                sessions_today_liters = self.water_sessions_today_l
                sessions_today_count = self.water_sessions_today_count
            else:
                # v0.63.121: de datum wordt nu uit de tijdstempel
                # GEPARSED en naar lokale tijd omgerekend, in plaats van
                # de eerste tien tekens als datum te lezen. Momenten die
                # vóór v0.63.119 door de listener zijn vastgelegd staan
                # namelijk in UTC in de geschiedenis (zichtbaar in een
                # diagnostiek-export: dezelfde lijst bevatte zowel
                # "+02:00" als "+00:00"), en een UTC-tijdstempel tussen
                # middernacht en 02:00 lokaal levert bij een simpele
                # tekstvergelijking de datum van GISTEREN op. Die oude
                # momenten blijven in de geschiedenis staan, dus zonder
                # deze omrekening blijft die scheefheid bestaan.
                for session in self.water_session_history:
                    gestart = session.get("gestart")
                    liter = session.get("liter")
                    if not gestart:
                        continue
                    moment = dt_util.parse_datetime(gestart)
                    if moment is None:
                        continue
                    if dt_util.as_local(moment).date().isoformat() != today_str:
                        continue
                    sessions_today_count += 1
                    if liter is not None:
                        sessions_today_liters += liter
            if sessions_today_liters < self.water_daily_total_l * 0.3:
                # v0.63.121: het aantal momenten erbij, plus een
                # richtinggevende conclusie. "Mogelijk worden stoten
                # gemist" was een gok die twee keer de verkeerde kant op
                # wees; het aantal momenten onderscheidt de twee
                # mogelijke oorzaken juist meteen van elkaar - weinig
                # momenten betekent dat de detectie ze mist, veel
                # momenten met weinig liters betekent dat de
                # VOLUMEBEPALING tekortschiet.
                if sessions_today_count <= 5:
                    duiding = (
                        f"er zijn maar {sessions_today_count} "
                        "gebruiksmoment(en) herkend, dus de detectie zelf "
                        "mist waarschijnlijk stoten (staat de debietsensor "
                        "wel live bij te werken?)"
                    )
                else:
                    duiding = (
                        f"er zijn wél {sessions_today_count} "
                        "gebruiksmomenten herkend, dus de detectie werkt - "
                        "het volume per moment valt te laag uit (vergelijk "
                        "'liter' met 'liter_uit_meterstand' in de "
                        "sessiegeschiedenis)"
                    )
                # v0.63.129, gevraagd: "dit mag geen aandachtspunt zijn,
                # ik ben me er van bewust". Terecht: dit is een
                # OBSERVATIE over de dekking van de waterdetectie, niet
                # iets dat mis is met de integratie of de accu-
                # aansturing. Het is bovendien een toestand die dagen
                # kan aanhouden zonder dat er iets te doen valt - dan
                # zou de systeemstatus permanent op "Aandacht gewenst"
                # blijven staan en zijn signaalwaarde verliezen, net als
                # bij de NILM-duplicaten in v0.63.116. Gaat daarom naar
                # `informatief`: onverkort zichtbaar, telt niet mee voor
                # de status.
                informatief.append(
                    f"Waterverbruik: dagtotaal ({self.water_daily_total_l:.0f} L) "
                    f"is een stuk hoger dan wat de geregistreerde "
                    f"gebruiksmomenten van vandaag verklaren "
                    f"({sessions_today_liters:.0f} L) - {duiding}."
                )

        # v0.63.117: het salderingsregime zichtbaar maken. Informatief,
        # niet als aandachtspunt - het is geen storing, maar het
        # verandert wel de betekenis van elk financieel getal, dus het
        # hoort niet stil te gebeuren.
        if not self.salderen_active:
            informatief.append(
                "Salderen is vervallen: teruglevering wordt nu apart "
                "(lager) gewaardeerd dan inkoop. PV-energie opslaan is "
                "daardoor voordeliger geworden; de beslislogica is "
                "hier nog niet op geherkalibreerd."
            )
            if self.current_feedin_value_eur_per_kwh is None:
                aandachtspunten.append(
                    "Salderen is vervallen, maar er is geen teruglever"
                    "tarief beschikbaar op de prijssensor - de financiële "
                    "cijfers vallen nu terug op de inkoopprijs en "
                    "overschatten daardoor de opbrengst van teruglevering."
                )
        elif self._salderen_days_remaining() is not None and (
            self._salderen_days_remaining() <= 60
        ):
            informatief.append(
                f"Salderen stopt over {self._salderen_days_remaining()} "
                "dag(en) - daarna wordt teruglevering apart gewaardeerd. "
                "Controleer het teruglevertarief en de terugleverkosten "
                "in de instellingen."
            )

        if self.last_error:
            aandachtspunten.append(f"Laatste fout: {self.last_error}")

        return {
            "status": "aandacht_gewenst" if aandachtspunten else "nominaal",
            "aandachtspunten": aandachtspunten,
            "informatief": informatief,
        }

    def get_live_narrative(self, now: datetime) -> str:
        """Lopend, samenhangend verhaal in gewone taal over wat de
        integratie op dit moment doet en waarom - over alle onderdelen
        heen (v0.63.97, gevraagd: "een tabblad wat live vertelt wat de
        gehele integratie doet... om mijzelf bewuster te maken wat er
        gebeurt op alle vlakken en mogelijk weer extra input aan jou
        kan geven").

        Puur informatief/samenvattend - herformuleert en combineert
        bestaande state uit meerdere onderdelen tot lopende tekst,
        berekent zelf niets nieuws en stuurt niets aan. Elk onderdeel
        (accu, apparaten, water, NILM, klimaat, aandachtspunten) heeft
        een eigen, apart testbare deelfunctie - samengevoegd tot één
        verhaal, in plaats van één grote, moeilijk te onderhouden
        tekstblok.
        """
        paragraphs = [self._narrate_battery_decision()]

        appliance_bit = self._narrate_appliances(now)
        if appliance_bit:
            paragraphs.append(appliance_bit)

        water_bit = self._narrate_water(now)
        if water_bit:
            paragraphs.append(water_bit)

        nilm_bit = self._narrate_nilm()
        if nilm_bit:
            paragraphs.append(nilm_bit)

        climate_bit = self._narrate_climate()
        if climate_bit:
            paragraphs.append(climate_bit)

        attention_bit = self._narrate_attention()
        if attention_bit:
            paragraphs.append(attention_bit)

        return " ".join(paragraphs)

    def _narrate_battery_decision(self) -> str:
        """Kern van het verhaal: hergebruikt de al bestaande, uitgebreide
        `last_explanation` (per beslisreden opgebouwd, zie de grote
        if/elif-keten verderop) - geen tekst dupliceren, gewoon
        hergebruiken als eerste alinea."""
        return self.last_explanation or "Nog geen data verwerkt."

    def _narrate_appliances(self, now: datetime) -> str | None:
        """Meldt welke gevolgde apparaten op dit moment een cyclus
        draaien, met hoelang al."""
        bits = []
        if self._dishwasher_state == "actief" and self._dishwasher_cycle_started_at:
            minutes = int(
                (now - self._dishwasher_cycle_started_at).total_seconds() / 60
            )
            bits.append(f"de vaatwasser draait al {minutes} minuten")
        if (
            self._washing_machine_state == "actief"
            and self._washing_machine_cycle_started_at
        ):
            minutes = int(
                (now - self._washing_machine_cycle_started_at).total_seconds() / 60
            )
            bits.append(f"de wasmachine draait al {minutes} minuten")
        if not bits:
            return None
        return "Ondertussen " + " en ".join(bits) + "."

    def _narrate_water(self, now: datetime) -> str | None:
        """Meldt actief waterverbruik of, bij rust, het dagtotaal."""
        if self._water_usage_state == "actief" and self._water_session_started_at:
            minutes = int(
                (now - self._water_session_started_at).total_seconds() / 60
            )
            return f"Er loopt water sinds {minutes} minuten geleden."
        if self.water_daily_total_l is not None:
            return f"Vandaag is er tot nu toe {self.water_daily_total_l:.0f} L water verbruikt."
        return None

    def _narrate_nilm(self) -> str | None:
        """Meldt openstaande NILM-kandidaten of recent gevonden
        mogelijke defecten - alleen als er iets te melden is."""
        bits = []
        candidate_count = len(self.nilm_unconfirmed_candidates)
        if candidate_count > 0:
            bits.append(
                f"er {'staat' if candidate_count == 1 else 'staan'} "
                f"{candidate_count} nog onbeoordeelde NILM-"
                f"{'kandidaat' if candidate_count == 1 else 'kandidaten'}"
            )
        defective = [
            d.get("friendly_name")
            for d in self.nilm_confirmed_devices.values()
            if d.get("anomaly_detected")
        ]
        if defective:
            bits.append(
                f"{len(defective)} apparaat/apparaten tonen mogelijk defect "
                f"gedrag ({', '.join(defective)})"
            )
        if not bits:
            return None
        return "Verder " + " en ".join(bits) + "."

    def _narrate_climate(self) -> str | None:
        """Meldt de klimaat-projectie-status, als die iets te melden
        heeft (bijv. nog niet genoeg data)."""
        if self.climate_forecast_note:
            return self.climate_forecast_note
        if self.climate_forecast_trajectory:
            eerste = self.climate_forecast_trajectory[0]
            return (
                f"De woonkamer wordt over een uur rond de "
                f"{eerste.get('kort_termijn_temp_c')}°C verwacht."
            )
        return None

    def _narrate_attention(self) -> str | None:
        """Sluit af met eventuele aandachtspunten uit de
        gezondheidscheck-samenvatting (v0.63.91) - hergebruikt, niet
        opnieuw berekend.

        v0.63.116: informatieve observaties (die de status niet naar
        "Aandacht gewenst" brengen) krijgen hier een eigen, duidelijk
        andere formulering - "Ter info" i.p.v. "Let op" - zodat ze
        zichtbaar blijven zonder als probleem te lezen. Zonder dit
        zouden ze uit het Live-verhaal verdwijnen zodra er verder niets
        aan de hand is.
        """
        summary = self.get_diagnostic_summary()
        delen = []
        if summary["aandachtspunten"]:
            delen.append("Let op: " + " ".join(summary["aandachtspunten"]))
        if summary["informatief"]:
            delen.append("Ter info: " + " ".join(summary["informatief"]))
        if not delen:
            return None
        return " ".join(delen)

    def _describe_nilm_trend(self, device: dict) -> str:
        """A lighter-weight, more granular trend label than
        `anomaly_detected` (which only fires on a *sustained* CUSUM
        breach, v0.63.39) - just compares the most recent daily average
        against the learned reference, so a modest move shows up well
        before it would ever reach the alarm threshold.

        v0.63.90, gevonden tijdens een diagnostiek-analyse (5 "Eetkamer
        lamp"-sensoren toonden "⚠️ aanhoudend stijgend (-0%) - mogelijk
        defect" - een negatief/nul percentage naast "stijgend"). De
        CUSUM-detector zelf is bewust eenzijdig (accumuleert alleen bij
        afwijkingen boven de referentie, geklemd op minimaal 0), dus
        "stijgend" is conceptueel altijd correct zodra het alarm
        afgaat - maar `estimated_drift_percent` is puur de afwijking
        van de LAATSTE dag, die toevallig rond nul kan liggen ook al
        was de OPGEBOUWDE geschiedenis (over meerdere eerdere dagen)
        wél voldoende om het alarm te triggeren. Een niet-positief
        getal naast "stijgend" tonen is dan misleidend/tegenstrijdig
        ogend - toon het percentage daarom alleen als het ook echt een
        stijging weergeeft.
        """
        reference_avg_w = device.get("reference_avg_w")
        history = device.get("daily_avg_history") or []
        if reference_avg_w is None or not history or reference_avg_w <= 0:
            return "onbekend (nog niet genoeg data)"

        latest_avg_w = history[-1]
        change_percent = 100 * (latest_avg_w - reference_avg_w) / reference_avg_w

        if device.get("anomaly_detected"):
            drift = device.get("estimated_drift_percent")
            drift_txt = f" ({drift:+.0f}%)" if drift is not None and drift > 0 else ""
            return f"⚠️ aanhoudend stijgend{drift_txt} - mogelijk defect"
        if change_percent >= NILM_TREND_RISING_THRESHOLD_PERCENT:
            return f"↗ licht stijgend ({change_percent:+.0f}%)"
        if change_percent <= -NILM_TREND_FALLING_THRESHOLD_PERCENT:
            return f"↘ dalend ({change_percent:+.0f}%)"
        return "→ stabiel"

    def get_nilm_candidate_at_slot(self, slot_index: int) -> str | None:
        """Which candidate entity_id currently occupies dashboard slot
        `slot_index` (0-based) - v0.63.41. Sorted alphabetically by
        entity_id for a deterministic, stable ordering (so a given
        candidate doesn't visibly jump between slots from one tick to
        the next just because dict iteration order shifted). Returns
        None if fewer candidates exist than that slot index.
        """
        sorted_ids = sorted(self.nilm_unconfirmed_candidates.keys())
        if slot_index < 0 or slot_index >= len(sorted_ids):
            return None
        return sorted_ids[slot_index]

    def _update_nilm_confirmed_devices(self, now: datetime) -> None:
        """Per-device daily-average tracking + CUSUM drift-detection for
        every confirmed NILM device - same principle as the household
        sluipverbruik detector (v0.63.29), but per device and
        percentage-based (device power levels vary too much for one
        fixed Watt slack/threshold to make sense across all of them).
        """
        any_finalized = False
        for entity_id, device in self.nilm_confirmed_devices.items():
            power_w = self._read_sensor_float(entity_id)

            check_date = device.get("_check_date")
            if check_date != now.date():
                if check_date is not None and device.get("_today_count", 0) > 0:
                    daily_avg_w = device["_today_sum"] / device["_today_count"]
                    self._finalize_nilm_device_day(entity_id, device, daily_avg_w)
                    any_finalized = True
                device["_today_sum"] = 0.0
                device["_today_count"] = 0
                device["_check_date"] = now.date()

            if power_w is not None:
                device["_today_sum"] = device.get("_today_sum", 0.0) + power_w
                device["_today_count"] = device.get("_today_count", 0) + 1

        if any_finalized:
            # v0.63.66: persist the newly-learned daily history/CUSUM
            # state to the dedicated Store, not just kept in memory.
            self.hass.async_create_task(
                self._async_save_nilm_confirmed_devices_store()
            )

    def _finalize_nilm_device_day(
        self, entity_id: str, device: dict, daily_avg_w: float
    ) -> None:
        history = device.setdefault("daily_avg_history", [])
        history.append(round(daily_avg_w, 2))
        device["daily_avg_history"] = history[-CUSUM_BASELINE_HISTORY_DAYS:]
        history = device["daily_avg_history"]

        if len(history) < CUSUM_MIN_HISTORY_FOR_REFERENCE:
            return
        if len(history) > CUSUM_REFERENCE_EXCLUDE_RECENT_DAYS:
            reference_samples = history[:-CUSUM_REFERENCE_EXCLUDE_RECENT_DAYS]
        else:
            reference_samples = history
        if not reference_samples:
            return

        reference_avg_w = statistics.median(reference_samples)
        if reference_avg_w <= 0:
            return
        device["reference_avg_w"] = round(reference_avg_w, 2)

        # v0.63.100: auto-reset bij aanhoudende, genuine terugkeer naar
        # normaal gedrag - zie NILM_CUSUM_RESET_STREAK_DAYS's docstring.
        # Bewust vóór het v0.63.99-plafond gemeten (de RUWE dagwaarde
        # t.o.v. de referentie, niet de al-geplafonneerde bijdrage) -
        # "normaal" betekent hier echt op of onder de referentie, niet
        # slechts "iets minder ver boven de marge".
        if daily_avg_w <= reference_avg_w:
            device["_normal_streak_days"] = device.get("_normal_streak_days", 0) + 1
        else:
            device["_normal_streak_days"] = 0

        if (
            device.get("cusum_accumulator", 0.0) > 0
            and device["_normal_streak_days"] >= NILM_CUSUM_RESET_STREAK_DAYS
        ):
            device["cusum_accumulator"] = 0.0
            device["anomaly_detected"] = False
            device["estimated_drift_percent"] = None
            _LOGGER.debug(
                "NILM CUSUM auto-reset voor %s: %d opeenvolgende dagen "
                "terug op/onder referentie (%.2fW)",
                entity_id,
                device["_normal_streak_days"],
                reference_avg_w,
            )
            return

        deviation_fraction = (
            (daily_avg_w - reference_avg_w) / reference_avg_w
            - NILM_CUSUM_SLACK_FRACTION
        )
        # v0.63.99: begrens de bijdrage van één enkele dag, zodat een
        # geïsoleerde uitschieter (zie de constante's docstring) het
        # alarm niet in zijn eentje kan laten afgaan - alleen negatieve
        # kant (te lage waarden) blijft ongeplafonneerd, want die trekt
        # de accumulator juist omlaag (nooit de oorzaak van een
        # onterecht alarm).
        deviation_fraction = min(
            deviation_fraction, NILM_CUSUM_MAX_DAILY_CONTRIBUTION
        )
        device["cusum_accumulator"] = max(
            0.0, device.get("cusum_accumulator", 0.0) + deviation_fraction
        )

        was_detected = device.get("anomaly_detected", False)
        device["anomaly_detected"] = (
            device["cusum_accumulator"] >= NILM_CUSUM_ALARM_THRESHOLD
        )
        if device["anomaly_detected"]:
            device["estimated_drift_percent"] = round(
                100 * (daily_avg_w - reference_avg_w) / reference_avg_w, 1
            )
            if not was_detected:
                notify_service = self.config.get(CONF_APPLIANCE_NOTIFY_SERVICE)
                if notify_service:
                    self._dispatch_notification(
                        notify_service=notify_service,
                        title=f"🔍 Mogelijk defect: {device['friendly_name']}",
                        message=(
                            f"Het verbruik van {device['friendly_name']} ligt "
                            f"structureel ~{device['estimated_drift_percent']:.0f}% "
                            f"hoger dan normaal - mogelijk een beginnend defect. "
                            f"Gebaseerd op een aanhoudende trend, niet één losse dag."
                        ),
                        notification_id=f"ems_nilm_anomaly_{entity_id}",
                    )

    def _update_living_room_airco_prediction(self, now: datetime) -> None:
        """Living-room-temperature airco activation predictor
        (v0.63.55, requested: "verwacht wanneer ik de airco aanzet").

        Genuine anticipation, not just "is the airco on right now" -
        uses the same "queue an observation, confirm it later"
        technique already established by `SolarForecastAccuracyTracker`
        (a prediction captured today, compared against tomorrow's
        actual yield): each living-room temperature reading is bucketed
        (LIVING_ROOM_TEMP_BUCKET_SIZE_C = 1°C bins) and queued with a
        deadline `AIRCO_PREDICTION_LOOKAHEAD_MINUTES` (60 min) later.
        Every tick, any still-open queued observation gets marked "seen
        active" the moment the airco is confirmed active (regardless of
        which tick that happens on, as long as it's before the
        deadline) - once the deadline passes, the observation is
        finalised as True/False into that bucket's learned history.

        Deliberately a SHORT, bounded rolling window per bucket
        (AIRCO_PREDICTION_HISTORY_LENGTH = 20 outcomes) rather than an
        ever-growing one - requested: spring/autumn conditions can swing
        day to day, so a bucket's learned probability should track
        recent behaviour, not get diluted by weeks-old data from a
        different regime (e.g. thermostat settings that have since
        changed).

        Humidity is tracked alongside per bucket purely as *context* for
        display (its own rolling average) - not a second bucketing
        dimension, which would fragment the already-limited sample count
        per cell too thinly to ever reach AIRCO_PREDICTION_MIN_SAMPLES.
        """
        temp_entity = self.config.get(CONF_LIVING_ROOM_TEMPERATURE_SENSOR)
        if not temp_entity:
            return
        temp_c = self._read_sensor_float(temp_entity)
        if temp_c is None:
            return
        # v0.63.92, gerapporteerd met screenshot: de live
        # woonkamertemperatuur toonde absurd veel decimalen
        # (24.1230773925781°C) op het dashboard, in tegenstelling tot
        # de buitentemperatuur (die al afgerond binnenkomt via de
        # weerentiteit). De onderliggende temperatuursensor rapporteert
        # zelf met hoge precisie (bijv. een Zigbee-sensor); hier
        # afronden op 1 decimaal, consistent met hoe elke andere
        # temperatuurweergave in deze integratie wordt getoond.
        self.living_room_current_temp_c = round(temp_c, 1)

        humidity_entity = self.config.get(CONF_LIVING_ROOM_HUMIDITY_SENSOR)
        humidity_percent = (
            self._read_sensor_float(humidity_entity) if humidity_entity else None
        )
        # v0.63.121, gezien in een diagnostiek-export:
        # 45.9213256835938%. Exact dezelfde klacht die in v0.63.92 voor
        # de TEMPERATUUR werd opgelost ("absurd veel decimalen"), maar
        # de luchtvochtigheid ernaast bleef toen ongemoeid - dezelfde
        # sensor, dezelfde hoge precisie, dus hetzelfde probleem. Hier
        # op 1 decimaal, consistent met elke andere weergave.
        self.living_room_current_humidity_percent = (
            round(humidity_percent, 1) if humidity_percent is not None else None
        )

        bucket_key = str(
            round(temp_c / LIVING_ROOM_TEMP_BUCKET_SIZE_C) * LIVING_ROOM_TEMP_BUCKET_SIZE_C
        )

        airco_active_now = self.last_heavy_load_source == "airco"

        # Mark every still-open pending observation "seen active" if the
        # airco is active on this tick - a queued observation from any
        # earlier tick (as long as its deadline hasn't passed yet) counts.
        if airco_active_now:
            for pending in self._temp_prediction_pending:
                pending["airco_seen_active"] = True

        # Finalise anything whose lookahead window has now elapsed.
        still_pending = []
        for pending in self._temp_prediction_pending:
            if now >= pending["deadline"]:
                history = self.living_room_temp_bucket_history.setdefault(
                    pending["bucket"], []
                )
                history.append(pending["airco_seen_active"])
                self.living_room_temp_bucket_history[pending["bucket"]] = history[
                    -AIRCO_PREDICTION_HISTORY_LENGTH:
                ]
            else:
                still_pending.append(pending)
        self._temp_prediction_pending = still_pending

        # Queue this tick's own observation.
        self._temp_prediction_pending.append(
            {
                "bucket": bucket_key,
                "deadline": now + timedelta(minutes=AIRCO_PREDICTION_LOOKAHEAD_MINUTES),
                "airco_seen_active": airco_active_now,
            }
        )

        if humidity_percent is not None:
            humidity_history = self.living_room_temp_bucket_humidity.setdefault(
                bucket_key, []
            )
            humidity_history.append(humidity_percent)
            self.living_room_temp_bucket_humidity[bucket_key] = humidity_history[
                -AIRCO_PREDICTION_HISTORY_LENGTH:
            ]

    def get_airco_activation_probability(self, bucket_key: str) -> dict:
        """Learned probability the airco activates within
        AIRCO_PREDICTION_LOOKAHEAD_MINUTES of a reading in this
        temperature bucket, plus sample count and readiness - used by
        both the sensor and (indirectly) the advisory-readiness table.
        """
        history = self.living_room_temp_bucket_history.get(bucket_key, [])
        humidity_history = self.living_room_temp_bucket_humidity.get(bucket_key, [])
        sample_count = len(history)
        result = {
            "bucket": bucket_key,
            "sample_count": sample_count,
            "probability_percent": None,
            "gemiddelde_luchtvochtigheid_percent": (
                round(sum(humidity_history) / len(humidity_history), 1)
                if humidity_history
                else None
            ),
            "voldoende_data": sample_count >= AIRCO_PREDICTION_MIN_SAMPLES,
        }
        if history:
            result["probability_percent"] = round(
                100 * sum(history) / len(history), 1
            )
        return result

    def _get_shutter_state_label(self) -> str | None:
        """Combines the two configured shutter (rolluik) entities into
        one label (v0.63.56) - "beide_dicht" (no solar gain through
        this room's windows), "gedeeltelijk" (one open, one closed), or
        "beide_open" (maximum solar gain potential). None if neither
        entity is configured or readable.
        """
        entity_1 = self.config.get(CONF_LIVING_ROOM_SHUTTER_ENTITY_1)
        entity_2 = self.config.get(CONF_LIVING_ROOM_SHUTTER_ENTITY_2)
        states = []
        for entity_id in (entity_1, entity_2):
            if not entity_id:
                continue
            state = self.hass.states.get(entity_id)
            if state is not None:
                states.append(state.state)
        if not states:
            return None
        open_count = sum(1 for s in states if s == "open")
        if open_count == len(states):
            return "beide_open"
        if open_count == 0:
            return "beide_dicht"
        return "gedeeltelijk"

    def _get_current_airco_state_label(self) -> str:
        """Uit/verwarmen/koelen op basis van `hvac_action` (v0.63.56) -
        meer granulair dan de bestaande grootverbruiker-detectie
        (die alleen "actief ja/nee" onderscheidt), omdat verwarmen en
        koelen tegenovergestelde effecten op de kamertemperatuur hebben.
        """
        airco_entity = self.config.get(CONF_AIRCO_CLIMATE_ENTITY)
        if not airco_entity:
            return "onbekend"
        state = self.hass.states.get(airco_entity)
        if state is None:
            return "onbekend"
        hvac_action = state.attributes.get("hvac_action")
        if hvac_action == "heating":
            return "verwarmen"
        if hvac_action == "cooling":
            return "koelen"
        return "uit"

    def _get_filtered_backyard_temp_c(self, now: datetime) -> float | None:
        """Uitschieter-gefilterde achtertuinsensor-meting (v0.63.96,
        gerapporteerd met grafiek: de sensor kan 's ochtends kort in
        direct zonlicht hangen, wat een plotselinge, kortstondige
        sprong veroorzaakt die niets met de werkelijke luchttemperatuur
        te maken heeft - de behuizing warmt zelf op).

        Een sprong die de plausibele afkoel/opwarm-snelheid van
        buitenlucht (`BACKYARD_TEMP_MAX_PLAUSIBLE_RATE_C_PER_HOUR`) ver
        overschrijdt, wordt niet meteen vertrouwd - de vorige,
        geaccepteerde waarde blijft gelden totdat de nieuwe waarde
        minstens `BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES` aanhoudt (binnen
        een kleine tolerantiemarge, `BACKYARD_TEMP_SPIKE_TOLERANCE_C`,
        zodat kleine meetruis de teller niet steeds laat resetten). Een
        kortstondige zonneflits zakt vanzelf terug voordat dit venster
        verstrijkt en wordt dan genegeerd; een echte, aanhoudende
        verandering (bijv. een koufront) wordt na dit venster alsnog
        geaccepteerd - dit filtert dus ruis, het bevriest de meting
        niet permanent.
        """
        backyard_entity = self.config.get(CONF_BACKYARD_TEMPERATURE_SENSOR)
        if not backyard_entity:
            return None
        raw_temp = self._read_sensor_float(backyard_entity)
        if raw_temp is None:
            return None

        if self._backyard_temp_last_accepted_c is None:
            self._backyard_temp_last_accepted_c = raw_temp
            self._backyard_temp_last_accepted_at = now
            return raw_temp

        elapsed_hours = max(
            (now - self._backyard_temp_last_accepted_at).total_seconds() / 3600,
            1 / 3600,  # avoid a division by ~0 on two ticks in the same second
        )
        implied_rate = (
            abs(raw_temp - self._backyard_temp_last_accepted_c) / elapsed_hours
        )

        if implied_rate <= BACKYARD_TEMP_MAX_PLAUSIBLE_RATE_C_PER_HOUR:
            # Plausible change - accept directly, no spike suspected.
            self._backyard_temp_last_accepted_c = raw_temp
            self._backyard_temp_last_accepted_at = now
            self._backyard_temp_spike_candidate_c = None
            self._backyard_temp_spike_since = None
            return raw_temp

        # Implausibly fast change - a suspected artifact (e.g. direct
        # sun hitting the sensor). Track it, but keep returning the
        # last trusted value until/unless it's confirmed sustained.
        if (
            self._backyard_temp_spike_candidate_c is not None
            and abs(raw_temp - self._backyard_temp_spike_candidate_c)
            <= BACKYARD_TEMP_SPIKE_TOLERANCE_C
        ):
            sustained_minutes = (
                now - self._backyard_temp_spike_since
            ).total_seconds() / 60
            if sustained_minutes >= BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES:
                # Sustained long enough - treat as a genuine change,
                # not a transient artifact.
                self._backyard_temp_last_accepted_c = raw_temp
                self._backyard_temp_last_accepted_at = now
                self._backyard_temp_spike_candidate_c = None
                self._backyard_temp_spike_since = None
                self.last_backyard_spike_filtered_note = None
                return raw_temp
        else:
            # A new (or first) spike candidate - start the confirmation
            # window.
            self._backyard_temp_spike_candidate_c = raw_temp
            self._backyard_temp_spike_since = now

        self.last_backyard_spike_filtered_note = (
            f"Uitschieter genegeerd: {raw_temp}°C wijkt te snel af van "
            f"{self._backyard_temp_last_accepted_c}°C (mogelijk kortstondig "
            "direct zonlicht op de sensor) - wordt pas vertrouwd als dit "
            f"{BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES} minuten aanhoudt."
        )
        return self._backyard_temp_last_accepted_c

    def _get_live_outdoor_temp_c(self, now: datetime) -> float | None:
        """Live buitentemperatuur (v0.63.56, uitgebreid in v0.63.95/.96).

        Voorkeursbron: een geconfigureerde eigen achtertuin-
        temperatuursensor (`CONF_BACKYARD_TEMPERATURE_SENSOR`) - een
        fysieke, lokale meting is nauwkeuriger voor de eigen locatie
        dan een regionale weerentiteit-schatting (gevraagd na een
        eerdere sessie waarin de weerentiteit een significante
        afwijking bleek te hebben). Loopt door `_get_filtered_
        backyard_temp_c` (v0.63.96) om kortstondige uitschieters
        (bijv. direct zonlicht op de sensor 's ochtends) eruit te
        filteren. Valt terug op de weerentiteiten (KNMI eerst, dan
        OpenWeatherMap - hergebruikt de al geconfigureerde Weather
        Ensemble-entiteiten, v0.63.30) als er geen achtertuinsensor is
        geconfigureerd of niet uitleesbaar is.
        """
        backyard_entity = self.config.get(CONF_BACKYARD_TEMPERATURE_SENSOR)
        if backyard_entity:
            filtered_temp = self._get_filtered_backyard_temp_c(now)
            if filtered_temp is not None:
                return filtered_temp

        for entity_id in (
            self.config.get(CONF_KNMI_WEATHER_ENTITY),
            self.config.get(CONF_OPENWEATHERMAP_WEATHER_ENTITY),
        ):
            if not entity_id:
                continue
            state = self.hass.states.get(entity_id)
            if state is None:
                continue
            temp = state.attributes.get("temperature")
            if temp is not None:
                try:
                    return float(temp)
                except (TypeError, ValueError):
                    continue
        return None

    @staticmethod
    def _outdoor_temp_bucket(temp_c: float) -> str:
        return str(round(temp_c / OUTDOOR_TEMP_BUCKET_SIZE_C) * OUTDOOR_TEMP_BUCKET_SIZE_C)

    def _climate_rate_key(
        self, outdoor_bucket: str, shutter_state: str, airco_state: str
    ) -> str:
        return f"{outdoor_bucket}|{shutter_state}|{airco_state}"

    def _update_climate_rate_learning(self, now: datetime) -> None:
        """Learns the living room's own rate of temperature change
        (°C/hour) as a function of (outdoor temperature bucket, shutter
        state, airco state) - v0.63.56, requested. Deliberately leaves
        cloud cover OUT as a separate learning dimension (confirmed with
        the person) - a full model (outdoor temp x shutter x cloud x
        airco) would produce hundreds of cells that would each need
        their own data, most staying "onvoldoende data" for months in a
        typical household.

        Short, bounded rolling window per cell (CLIMATE_RATE_HISTORY_
        LENGTH = 20), same principle as the airco-activation predictor
        above - spring/autumn conditions can swing day to day, so a
        cell's learned rate should track recent behaviour.

        Measured over roughly an hour (an "anchor" reading compared
        against the next one ~an hour later), not every 5-minute tick -
        a rate computed from tick-to-tick deltas would be numerically
        unstable for a physically slow-moving quantity like room
        temperature (typical sensor resolution ~0.1°C, divided by a tiny
        5/60h timespan amplifies noise into wildly swinging rates).
        Reads the living room temperature directly (not via
        `living_room_current_temp_c`, which is set by
        `_update_living_room_airco_prediction`) so this function stays
        independently correct and testable regardless of call order.
        """
        temp_entity = self.config.get(CONF_LIVING_ROOM_TEMPERATURE_SENSOR)
        temp_c = self._read_sensor_float(temp_entity) if temp_entity else None
        outdoor_temp_c = self._get_live_outdoor_temp_c(now)
        shutter_state = self._get_shutter_state_label()
        airco_state = self._get_current_airco_state_label()
        self.climate_shutter_state = shutter_state
        self.climate_airco_state = airco_state
        self.climate_live_outdoor_temp_c = outdoor_temp_c

        if temp_c is None or outdoor_temp_c is None or shutter_state is None:
            return

        if self._climate_anchor_time is None or self._climate_anchor_temp_c is None:
            self._set_climate_anchor(now, temp_c, outdoor_temp_c, shutter_state, airco_state)
            return

        elapsed_hours = (now - self._climate_anchor_time).total_seconds() / 3600

        if elapsed_hours > CLIMATE_RATE_MAX_INTERVAL_HOURS:
            # Restart-sized gap - don't attribute it to a single rate,
            # just start a fresh anchor from here.
            self._set_climate_anchor(now, temp_c, outdoor_temp_c, shutter_state, airco_state)
            return

        if elapsed_hours < CLIMATE_RATE_MIN_INTERVAL_HOURS:
            # Not enough time has passed yet for a stable measurement -
            # keep the current anchor, try again next tick.
            return

        rate_c_per_hour = (temp_c - self._climate_anchor_temp_c) / elapsed_hours
        key = self._climate_rate_key(
            self._climate_anchor_outdoor_bucket,
            self._climate_anchor_shutter_state,
            self._climate_anchor_airco_state,
        )
        history = self.climate_rate_history.setdefault(key, [])
        history.append(round(rate_c_per_hour, 3))
        self.climate_rate_history[key] = history[-CLIMATE_RATE_HISTORY_LENGTH:]

        self._set_climate_anchor(now, temp_c, outdoor_temp_c, shutter_state, airco_state)

    def _set_climate_anchor(
        self,
        now: datetime,
        temp_c: float,
        outdoor_temp_c: float,
        shutter_state: str,
        airco_state: str,
    ) -> None:
        self._climate_anchor_time = now
        self._climate_anchor_temp_c = temp_c
        self._climate_anchor_outdoor_bucket = self._outdoor_temp_bucket(outdoor_temp_c)
        self._climate_anchor_shutter_state = shutter_state
        self._climate_anchor_airco_state = airco_state

    def get_climate_rate(
        self, outdoor_bucket: str, shutter_state: str, airco_state: str
    ) -> dict:
        """Learned rate of living-room temperature change (°C/hour) for
        this combination, plus sample count and a two-tier reliability
        level (v0.63.57, requested): "indicatief" once
        CLIMATE_RATE_MIN_SAMPLES (5) exist, "betrouwbaar" only once
        CLIMATE_RATE_RELIABLE_SAMPLES (15) do.
        """
        key = self._climate_rate_key(outdoor_bucket, shutter_state, airco_state)
        history = self.climate_rate_history.get(key, [])
        sample_count = len(history)
        if sample_count >= CLIMATE_RATE_RELIABLE_SAMPLES:
            betrouwbaarheid = "betrouwbaar"
        elif sample_count >= CLIMATE_RATE_MIN_SAMPLES:
            betrouwbaarheid = "indicatief"
        else:
            betrouwbaarheid = "onvoldoende_data"
        return {
            "key": key,
            "sample_count": sample_count,
            "rate_c_per_hour": (
                round(statistics.median(history), 3) if history else None
            ),
            "betrouwbaarheid": betrouwbaarheid,
            "voldoende_data": sample_count >= CLIMATE_RATE_MIN_SAMPLES,
        }

    async def _async_fetch_hourly_outdoor_forecast(
        self, entity_id: str
    ) -> list[tuple[datetime, float]] | None:
        """Fetches the hourly outdoor temperature forecast via the
        `weather.get_forecasts` service (v0.63.56) - a genuinely
        different kind of call than anything else in this integration
        (needs `return_response=True`, unlike every other service call
        here, which are all fire-and-forget). Defensive: any failure
        (service missing, malformed response, an integration that uses
        different attribute names) is caught and treated as "no
        forecast available" rather than crashing the whole update tick.
        """
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": entity_id, "type": "hourly"},
                blocking=True,
                return_response=True,
            )
        except Exception:  # noqa: BLE001 - a forecast fetch must never crash the tick
            _LOGGER.exception(
                "Kon geen uurlijkse weersvoorspelling ophalen bij %s", entity_id
            )
            return None

        if not response or entity_id not in response:
            return None
        raw_forecast = response[entity_id].get("forecast")
        if not raw_forecast:
            return None

        entries = []
        for item in raw_forecast:
            temp = item.get("temperature")
            when = item.get("datetime")
            if temp is None or when is None:
                continue
            parsed_when = dt_util.parse_datetime(when) if isinstance(when, str) else when
            if parsed_when is None:
                continue
            # v0.63.93, gerapporteerd: "de temperature verwachting van
            # KNMI klopt niet in de tabellen" - bleek uiteindelijk twee
            # aparte dingen: (1) KNMI's eigen brondata week af van de
            # live meting (opgelost door over te stappen op een
            # nauwkeurigere weerentiteit), en (2) deze weerentiteit
            # rapporteert in UTC (+00:00) i.p.v. lokale tijd (+02:00
            # zoals KNMI toevallig deed) - zonder conversie zou de
            # getoonde "Uur"-kolom 2 uur achterlopen op de werkelijke
            # lokale tijd. Altijd expliciet naar lokale tijd converteren
            # bij het parsen, ongeacht welke tijdzone de brondata zelf
            # gebruikt - laat dit niet toevallig kloppen doordat één
            # specifieke bron nu net lokale tijd gebruikt.
            parsed_when = dt_util.as_local(parsed_when)
            try:
                entries.append((parsed_when, float(temp)))
            except (TypeError, ValueError):
                continue
        return entries or None

    async def _async_update_climate_forecast(self, now: datetime) -> None:
        """Klimaat-tabblad (v0.63.56/.57/.58): projects the living room
        temperature forward hour by hour, using the KNMI/OpenWeatherMap
        hourly outdoor-temperature forecast to drive the walk and the
        learned per-cell rate (see `_update_climate_rate_learning`) to
        translate outdoor conditions into indoor change. Shutter state
        and airco state are held CONSTANT at their current values for
        the whole projection (limitation, stated plainly) - there's no
        way to know what either will be doing in 6 hours.

        Two parallel projections per hour (v0.63.57, requested), not two
        separate models - just two different thresholds applied to the
        same learned rate:
        - `kort_termijn_temp_c`: applies the rate once
          CLIMATE_RATE_MIN_SAMPLES (5) samples exist - "indicatief",
          usable early even with still-thin data.
        - `betrouwbaar_temp_c`: only applies the rate once
          CLIMATE_RATE_RELIABLE_SAMPLES (15) do - a more conservative,
          slower-to-mature projection.
        Either series carries forward unchanged (not a guessed rate)
        for any hour below its own threshold, rather than silently
        compounding a made-up number forward through the 24-hour chain.

        v0.63.58, requested ("correctie op de actueel gemeten waarde"):
        split into two parts with two different cadences -
        `_async_maybe_refresh_outdoor_forecast` (this method) only
        RE-FETCHES the outdoor forecast at most once per
        CLIMATE_FORECAST_FETCH_INTERVAL_MINUTES (30 min, since that's a
        genuine `return_response=True` service call, not a cheap
        state-machine read, and hourly forecast data doesn't change
        meaningfully every 5 minutes anyway) - but
        `_recompute_climate_trajectory` (called every tick, cheap, no
        network/service call) always re-walks the projection from
        whatever the CURRENT live-measured temperature is, using the
        cached forecast. Without this split, the projection's starting
        point would drift stale for up to 30 minutes between fetches,
        even though the actual room temperature keeps changing in the
        meantime.
        """
        await self._async_maybe_refresh_outdoor_forecast(now)
        self._recompute_climate_trajectory(now)

    async def _async_maybe_refresh_outdoor_forecast(self, now: datetime) -> None:
        """Throttled fetch of the hourly outdoor-temperature forecast -
        see `_async_update_climate_forecast`'s docstring for why this is
        split from the (cheap, every-tick) trajectory recomputation.
        """
        if (
            self._climate_forecast_last_fetch is not None
            and (now - self._climate_forecast_last_fetch).total_seconds() / 60
            < CLIMATE_FORECAST_FETCH_INTERVAL_MINUTES
        ):
            return
        self._climate_forecast_last_fetch = now

        weather_entity = self.config.get(CONF_KNMI_WEATHER_ENTITY) or self.config.get(
            CONF_OPENWEATHERMAP_WEATHER_ENTITY
        )
        if not weather_entity:
            self._climate_cached_forecast = None
            # v0.63.120: de reden wordt nu OOK in een eigen veld
            # bewaard, zodat `_recompute_climate_trajectory` hem elke
            # tick opnieuw kan tonen - deze fetch draait immers maar
            # eens per 30 minuten.
            self._climate_forecast_fetch_note = (
                "Geen knmi_weather_entity/openweathermap_weather_entity "
                "geconfigureerd - geen buitentemperatuur-voorspelling "
                "beschikbaar om de projectie op te baseren."
            )
            self.climate_forecast_note = self._climate_forecast_fetch_note
            return

        forecast = await self._async_fetch_hourly_outdoor_forecast(weather_entity)
        if not forecast:
            self._climate_cached_forecast = None
            self._climate_forecast_fetch_note = (
                "Kon geen uurlijkse buitentemperatuur-voorspelling ophalen "
                f"bij {weather_entity}."
            )
            self.climate_forecast_note = self._climate_forecast_fetch_note
            return
        self._climate_cached_forecast = forecast
        self._climate_forecast_fetch_note = None

        # v0.63.95: bias-sample - vergelijk de eerstvolgende voorspelde
        # waarde met de actuele achtertuinsensor-meting op ditzelfde
        # moment. Alleen relevant/mogelijk als er een achtertuinsensor
        # is geconfigureerd (anders zou dit de weerentiteit tegen
        # zichzelf vergelijken, zinloos). Loopt door het uitschieter-
        # filter (v0.63.96) - anders zou een kortstondige zonneflits op
        # de sensor de bias-leerhistorie kunnen vervuilen.
        backyard_entity = self.config.get(CONF_BACKYARD_TEMPERATURE_SENSOR)
        if backyard_entity and forecast:
            backyard_temp = self._get_filtered_backyard_temp_c(now)
            if backyard_temp is not None:
                _, nearest_forecast_temp = forecast[0]
                deviation_c = backyard_temp - nearest_forecast_temp
                self.climate_forecast_bias_history.append(round(deviation_c, 2))
                self.climate_forecast_bias_history = self.climate_forecast_bias_history[
                    -CLIMATE_FORECAST_BIAS_HISTORY_LENGTH:
                ]

    def _recompute_climate_trajectory(self, now: datetime) -> None:
        """Re-walks the 24-hour projection from the CURRENT
        live-measured living room temperature, using whichever outdoor
        forecast is currently cached (see
        `_async_maybe_refresh_outdoor_forecast`). Cheap, no network/
        service call - safe to run every tick, so the projection's
        starting point is always corrected to the actual measured
        value, not just whenever the forecast happens to be re-fetched
        (v0.63.58, requested).
        """
        self.climate_forecast_trajectory = []

        temp_c = self.living_room_current_temp_c
        if temp_c is None:
            # v0.63.120, gerapporteerd met screenshot van een INGEVULD
            # configuratieveld: "Maar ze staan wel ingevuld?" - de oude
            # tekst gooide "niet geconfigureerd" en "niet uitleesbaar"
            # op één hoop, waardoor een tijdelijk onbereikbare sensor
            # eruitzag als een configuratiefout. Nu twee losse,
            # accurate meldingen, met de entity_id erbij zodat direct
            # te zien is WELKE sensor het betreft.
            temp_entity = self.config.get(CONF_LIVING_ROOM_TEMPERATURE_SENSOR)
            if not temp_entity:
                self.climate_forecast_note = (
                    "Geen woonkamertemperatuur-sensor geconfigureerd - vul "
                    "'living_room_temperature_sensor_entity' in bij "
                    "Configureren om de projectie te activeren."
                )
            else:
                self.climate_forecast_note = (
                    f"Woonkamertemperatuur-sensor {temp_entity} is "
                    "geconfigureerd maar op dit moment niet uitleesbaar "
                    "(status 'unknown'/'unavailable' of geen getal). De "
                    "projectie start automatisch zodra de sensor weer "
                    "een waarde geeft."
                )
            return

        if not self._climate_cached_forecast:
            # v0.63.120: de reden NIET meer overlaten aan wat de fetch
            # ooit heeft achtergelaten. Die draait maar eens per 30
            # minuten, dus op alle tussenliggende ticks bleef hier de
            # melding van een VORIGE situatie staan - concreet: nadat
            # de temperatuursensor eenmalig kort onbereikbaar was
            # (bijv. tijdens het opstarten), bleef "geen
            # living_room_temperature_sensor_entity geconfigureerd of
            # niet uitleesbaar" eeuwig staan, ook toen die sensor
            # allang weer prima werkte en de werkelijke oorzaak de
            # ontbrekende buitentemperatuur-voorspelling was. Een
            # verkeerde diagnose die de zoekrichting compleet verlegt.
            self.climate_forecast_note = self._climate_forecast_fetch_note or (
                "Nog geen buitentemperatuur-voorspelling opgehaald - de "
                "projectie verschijnt zodra die beschikbaar is."
            )
            return

        shutter_state = self.climate_shutter_state or "onbekend"
        airco_state = self.climate_airco_state or "onbekend"

        # v0.63.95: geleerde bias-correctie op de HELE voorspelling
        # (niet alleen het startpunt), gebaseerd op de achtertuinsensor
        # - zie `climate_forecast_learned_bias_c`'s docstring.
        bias_c = self.climate_forecast_learned_bias_c or 0.0

        kort_termijn_temp = temp_c
        betrouwbaar_temp = temp_c
        trajectory = []
        for hour_dt, raw_outdoor_temp_c in self._climate_cached_forecast[
            :CLIMATE_FORECAST_HORIZON_HOURS
        ]:
            outdoor_temp_c = raw_outdoor_temp_c + bias_c
            outdoor_bucket = self._outdoor_temp_bucket(outdoor_temp_c)
            rate = self.get_climate_rate(outdoor_bucket, shutter_state, airco_state)
            rate_value = rate["rate_c_per_hour"]

            if rate["betrouwbaarheid"] in ("indicatief", "betrouwbaar") and rate_value is not None:
                kort_termijn_temp = kort_termijn_temp + rate_value
            if rate["betrouwbaarheid"] == "betrouwbaar" and rate_value is not None:
                betrouwbaar_temp = betrouwbaar_temp + rate_value

            trajectory.append(
                {
                    "tijd": hour_dt.isoformat(),
                    "buitentemp_voorspeld_c": round(outdoor_temp_c, 1),
                    "kort_termijn_temp_c": round(kort_termijn_temp, 1),
                    "betrouwbaar_temp_c": round(betrouwbaar_temp, 1),
                    # v0.63.94, gerapporteerd met screenshot: "de 2
                    # tabellen lijken hetzelfde weer te geven" - beide
                    # dashboardtabellen lazen tot nu toe hetzelfde,
                    # ene "betrouwbaarheid"-veld (het niveau voor de
                    # SOEPELE kort_termijn-drempel, ≥5 metingen), ook
                    # in de tabel die specifiek ≥15 metingen belooft.
                    # Een cel met bijv. 8 metingen toonde daardoor
                    # "indicatief" in BEIDE tabellen, terwijl de
                    # strengere tabel daar "onvoldoende_data" hoort te
                    # tonen (8 < 15). Nu twee aparte velden: het
                    # bestaande "betrouwbaarheid" blijft ongewijzigd
                    # (voor de kort-termijn-tabel), en een nieuw
                    # "betrouwbaarheid_streng" specifiek voor de
                    # betrouwbare-tabel - alleen "betrouwbaar" als de
                    # ≥15-drempel echt gehaald is, anders altijd
                    # "onvoldoende_data" (nooit "indicatief" daar, dat
                    # zou alsnog de verkeerde indruk wekken).
                    "betrouwbaarheid": rate["betrouwbaarheid"],
                    "betrouwbaarheid_streng": (
                        "betrouwbaar"
                        if rate["betrouwbaarheid"] == "betrouwbaar"
                        else "onvoldoende_data"
                    ),
                    "aantal_metingen": rate["sample_count"],
                }
            )

        self.climate_forecast_trajectory = trajectory
        self.climate_forecast_note = (
            "Adviserend - rolluikstand en airco-status worden voor de "
            "hele projectie constant gehouden op de huidige stand "
            "(onbekend wat die over enkele uren zijn). 'kort_termijn_"
            "temp_c' toont al een indicatie vanaf 5 samples per cel, "
            "'betrouwbaar_temp_c' pas vanaf 15 - beide bevriezen op het "
            "voorgaande uur zolang hun eigen drempel niet is gehaald, "
            "in plaats van te gokken. De projectie wordt elke tick "
            "opnieuw verankerd aan de actueel gemeten "
            "woonkamertemperatuur (de onderliggende buitentemperatuur-"
            "voorspelling wordt wél maar om de "
            f"{CLIMATE_FORECAST_FETCH_INTERVAL_MINUTES} minuten ververst). "
            "Stuurt nooit een commando."
        )

    def _update_advisory_readiness(self, now: datetime) -> None:
        """Readiness assessment for the ten advisory-only modules
        (v0.63.40, uitgebreid met extra-dip-marge/temperatuur-regressie
        in v0.63.91) - reported: "kunnen we een advies afgeven wanneer
        betrouwbaar genoeg om er werkelijk iets mee te doen?"

        Important, deliberate honesty distinction kept throughout: for
        some modules (Kirchhoff, sluipverbruik, Monte Carlo, Kalman,
        NILM) there's a genuine data-maturity signal already being
        tracked (a sample count reaching its design threshold, or a
        Kalman filter's own uncertainty having converged) - "klaar"
        there means the underlying data is mature enough for the output
        to be meaningful. For three modules (Weather Ensemble, MPC,
        Digital Twin) there is NO mechanism comparing past predictions
        against what actually happened - "klaar" there would be a false
        claim of proven accuracy this integration hasn't earned. Those
        are labelled "structureel beschikbaar, nauwkeurigheid niet
        gevolgd" instead of a readiness status, so the distinction stays
        visible rather than papered over.
        """
        readiness: dict[str, dict] = {}

        # 1. Kirchhoff energiebalans-validatie - has its own rolling
        # sample count/score already.
        sample_count = len(self.energy_balance_error_history)
        if not self.config.get(CONF_AVAILABLE_ENERGY_SENSOR) or not self.config.get(
            CONF_BATTERY_POWER_SENSOR
        ):
            readiness["kirchhoff"] = {
                "status": "niet_geconfigureerd",
                "reden": "available_energy_sensor_entity en/of battery_power_sensor_entity ontbreken.",
            }
        elif sample_count < ENERGY_BALANCE_ERROR_HISTORY_LENGTH:
            readiness["kirchhoff"] = {
                "status": "onvoldoende_data",
                "reden": f"{sample_count}/{ENERGY_BALANCE_ERROR_HISTORY_LENGTH} metingen verzameld.",
            }
        elif (self.sensor_health_score or 0) >= MEASUREMENT_QUALITY_GOOD_THRESHOLD:
            readiness["kirchhoff"] = {
                "status": "klaar",
                "reden": f"Score {self.sensor_health_score}% over {sample_count} metingen.",
            }
        else:
            readiness["kirchhoff"] = {
                "status": "kwaliteit_te_laag",
                "reden": f"Score {self.sensor_health_score}% - sensoren zelf lijken inconsistent.",
            }

        # 2. CUSUM-sluipverbruik - reference needs the full window to
        # be mature, not just the minimum to compute anything at all.
        history_len = len(self.baseline_load_history)
        if history_len >= CUSUM_BASELINE_HISTORY_DAYS:
            readiness["sluipverbruik"] = {
                "status": "klaar",
                "reden": f"Volledige {CUSUM_BASELINE_HISTORY_DAYS}-dagen-referentie opgebouwd.",
            }
        elif history_len >= CUSUM_MIN_HISTORY_FOR_REFERENCE:
            readiness["sluipverbruik"] = {
                "status": "bijna_klaar",
                "reden": f"{history_len}/{CUSUM_BASELINE_HISTORY_DAYS} dagen - detecteert al, referentie nog niet volgroeid.",
            }
        else:
            readiness["sluipverbruik"] = {
                "status": "onvoldoende_data",
                "reden": f"{history_len}/{CUSUM_MIN_HISTORY_FOR_REFERENCE} dagen minimum.",
            }

        # 3. Weather Ensemble - no accuracy tracking exists.
        if self.weather_ensemble_sources_used:
            readiness["weather_ensemble"] = {
                "status": "structureel_beschikbaar",
                "reden": (
                    f"{len(self.weather_ensemble_sources_used)} bron(nen) actief - "
                    "nauwkeurigheid t.o.v. de werkelijkheid wordt niet bijgehouden."
                ),
            }
        else:
            readiness["weather_ensemble"] = {
                "status": "niet_geconfigureerd",
                "reden": "Geen knmi_weather_entity/openweathermap_weather_entity geconfigureerd.",
            }

        # 4. MPC - no accuracy tracking (plan vs realised outcome) exists.
        if self.mpc_horizon_quarters_used:
            readiness["mpc"] = {
                "status": "structureel_beschikbaar",
                "reden": (
                    f"Plant over {self.mpc_horizon_quarters_used} kwartieren - "
                    "nauwkeurigheid t.o.v. het daadwerkelijke resultaat wordt niet bijgehouden."
                ),
            }
        else:
            readiness["mpc"] = {
                "status": "niet_geconfigureerd",
                "reden": self.mpc_note or "Geen plan beschikbaar.",
            }

        # 5. Monte Carlo - depends on the same learned history as
        # sluipverbruik/Digital Twin; maturity = how many of the 24
        # hours have a full LEARNING_HISTORY_DAYS window of samples.
        mature_hours = sum(
            1
            for h in range(24)
            if len(self.hourly_consumption_profile.get(h, [])) >= LEARNING_HISTORY_DAYS
        )
        if mature_hours >= 24:
            readiness["monte_carlo"] = {
                "status": "klaar",
                "reden": "Alle 24 uren hebben een volledig geleerd verbruiksprofiel.",
            }
        elif mature_hours > 0:
            readiness["monte_carlo"] = {
                "status": "bijna_klaar",
                "reden": f"{mature_hours}/24 uren volledig geleerd.",
            }
        else:
            readiness["monte_carlo"] = {
                "status": "onvoldoende_data",
                "reden": "Nog geen enkel uur met een volledig geleerd profiel.",
            }

        # 6. Kalman filtering - each filter's own uncertainty, converged
        # once it has shrunk well below its starting point.
        converged = []
        for kf, label in (
            (self._kalman_soc, "soc"),
            (self._kalman_pv, "pv"),
            (self._kalman_load, "load"),
        ):
            if kf.estimate is None:
                continue
            starting_uncertainty = kf.measurement_noise
            if starting_uncertainty > 0 and kf.uncertainty <= starting_uncertainty * 0.5:
                converged.append(label)
        active_filters = sum(
            1
            for kf in (self._kalman_soc, self._kalman_pv, self._kalman_load)
            if kf.estimate is not None
        )
        if active_filters == 0:
            readiness["kalman"] = {
                "status": "niet_geconfigureerd",
                "reden": "Geen van de drie signalen (SoC/PV/verbruik) heeft nog een meting gehad.",
            }
        elif len(converged) == active_filters:
            readiness["kalman"] = {
                "status": "klaar",
                "reden": f"Alle {active_filters} actieve filters geconvergeerd.",
            }
        else:
            readiness["kalman"] = {
                "status": "bijna_klaar",
                "reden": f"{len(converged)}/{active_filters} filters geconvergeerd.",
            }

        # 7. Digital Twin - no accuracy tracking exists, same caveat as MPC.
        if self.digital_twin_trajectory:
            readiness["digital_twin"] = {
                "status": "structureel_beschikbaar",
                "reden": (
                    f"Simuleert over {self.digital_twin_hours_simulated} uur - "
                    "nauwkeurigheid t.o.v. het daadwerkelijke resultaat wordt niet bijgehouden."
                ),
            }
        else:
            readiness["digital_twin"] = {
                "status": "niet_geconfigureerd",
                "reden": self.digital_twin_note or "Geen simulatie beschikbaar.",
            }

        # 8. NILM - per confirmed device, same maturity logic as
        # sluipverbruik, summarised across all of them.
        if not self.nilm_confirmed_devices:
            readiness["nilm"] = {
                "status": "niet_geconfigureerd",
                "reden": "Nog geen apparaten bevestigd via confirm_nilm_device.",
            }
        else:
            mature_devices = sum(
                1
                for d in self.nilm_confirmed_devices.values()
                if len(d.get("daily_avg_history", [])) >= CUSUM_BASELINE_HISTORY_DAYS
            )
            total_devices = len(self.nilm_confirmed_devices)
            if mature_devices == total_devices:
                readiness["nilm"] = {
                    "status": "klaar",
                    "reden": f"Alle {total_devices} bevestigde apparaten hebben een volledige referentie.",
                }
            else:
                readiness["nilm"] = {
                    "status": "bijna_klaar",
                    "reden": f"{mature_devices}/{total_devices} bevestigde apparaten volledig volgroeid.",
                }

        # 9. Extra-dip-laadmarge (v0.63.87) - genuine maturity signal:
        # `_compute_trend_summary` zelf vereist minimaal 3 punten voor
        # een zinvolle trendlijn.
        margin_samples = len(self.extra_dip_margin_history)
        if margin_samples >= 3:
            readiness["extra_dip_marge"] = {
                "status": "klaar",
                "reden": f"{margin_samples} dagsamples - trend beschikbaar.",
            }
        elif margin_samples > 0:
            readiness["extra_dip_marge"] = {
                "status": "onvoldoende_data",
                "reden": f"{margin_samples}/3 dagsamples - nog geen trend.",
            }
        else:
            readiness["extra_dip_marge"] = {
                "status": "onvoldoende_data",
                "reden": (
                    "Nog geen enkele dag met een berekende marge (vereist "
                    "een weinig-zon-dag buiten het hoofdblok)."
                ),
            }

        # 10. Temperatuur-verbruik-regressie (v0.63.88) - genuine
        # maturity signal: TEMP_CONSUMPTION_MIN_SAMPLES nodig voordat
        # er überhaupt een voorspelling wordt gedaan.
        temp_samples = len(self.temp_consumption_history)
        if temp_samples >= TEMP_CONSUMPTION_MIN_SAMPLES:
            readiness["temperatuur_regressie"] = {
                "status": "klaar",
                "reden": f"{temp_samples} (temperatuur, verbruik)-paren geleerd.",
            }
        elif temp_samples > 0:
            readiness["temperatuur_regressie"] = {
                "status": "onvoldoende_data",
                "reden": f"{temp_samples}/{TEMP_CONSUMPTION_MIN_SAMPLES} nachten verzameld.",
            }
        else:
            readiness["temperatuur_regressie"] = {
                "status": "onvoldoende_data",
                "reden": "Nog geen enkele nacht met een gemeten (temperatuur, verbruik)-paar.",
            }

        self.advisory_readiness = readiness

    def _get_best_remaining_price_today_eur(
        self, entries: list[PriceEntry], now: datetime
    ) -> float | None:
        """Hoogste prijs (€/kWh) onder de resterende kwartieren van
        VANDAAG (tot middernacht) - gebruikt door de extra-dip-laad-
        marge-check (v0.63.87). Bewust begrensd tot vandaag, niet
        verder de nacht in: de winter-guard-vlag (waarvoor deze marge
        de poort is) reset zelf ook om middernacht, dus "later vandaag"
        is de enige relevante vergelijking hier.
        """
        end_of_today = datetime.combine(
            now.date(), datetime.max.time(), tzinfo=now.tzinfo
        )
        remaining_today = [
            entry for entry in entries if now <= entry[0] < end_of_today
        ]
        if not remaining_today:
            return None
        return max(entry[2] for entry in remaining_today) / PRICE_SCALE_FACTOR

    def _cheapest_block_range(
        self, entries: list[PriceEntry], now: datetime
    ) -> tuple[datetime | None, datetime | None]:
        """Find the natural cheap price valley around the cheapest upcoming
        interval, instead of searching for a fixed-duration window.

        Starts at the single cheapest upcoming interval, then expands
        outward (backward and forward) while contiguous neighbouring
        intervals stay within CHEAP_BLOCK_THRESHOLD_MARGIN_FRACTION of the
        price range above the minimum. This makes the block's width adapt
        to how wide the actual daily price dip is, instead of assuming a
        fixed number of hours.

        Includes hysteresis: if the previously selected cheap block is
        still upcoming and its price is within
        CHEAP_BLOCK_STABILITY_MARGIN_FRACTION of the newly found
        candidate, keeps the previous choice instead of switching. Found
        after a real incident: as time passes and which quarters count as
        "still upcoming" shifts, two near-tied candidates elsewhere in
        the day could otherwise flip which one "wins" from one tick to
        the next - each requiring a wildly different reserve (hours until
        a cheap block a few minutes away vs. one many hours away).
        """
        if not entries:
            return None, None

        upcoming = [entry for entry in entries if entry[1] > now]
        if not upcoming:
            return None, None

        prices = [entry[2] for entry in upcoming]
        min_price = min(prices)
        max_price = max(prices)
        price_range = max_price - min_price

        cheapest_idx = min(range(len(upcoming)), key=lambda i: upcoming[i][2])

        if (
            self.last_cheap_block_start is not None
            and price_range > 0
        ):
            previous_idx = next(
                (
                    i
                    for i, entry in enumerate(upcoming)
                    if entry[0] == self.last_cheap_block_start
                ),
                None,
            )
            if previous_idx is not None:
                previous_price = upcoming[previous_idx][2]
                new_price = upcoming[cheapest_idx][2]
                stability_margin = price_range * CHEAP_BLOCK_STABILITY_MARGIN_FRACTION
                if previous_price <= new_price + stability_margin:
                    cheapest_idx = previous_idx

        if price_range <= 0:
            # Flat prices: no meaningful valley, just use the single
            # cheapest (first) interval.
            return upcoming[cheapest_idx][0], upcoming[cheapest_idx][1]

        threshold = min_price + price_range * CHEAP_BLOCK_THRESHOLD_MARGIN_FRACTION

        start_idx = cheapest_idx
        while (
            start_idx > 0
            and upcoming[start_idx - 1][1] == upcoming[start_idx][0]
            and upcoming[start_idx - 1][2] <= threshold
        ):
            start_idx -= 1

        end_idx = cheapest_idx
        while (
            end_idx < len(upcoming) - 1
            and upcoming[end_idx + 1][0] == upcoming[end_idx][1]
            and upcoming[end_idx + 1][2] <= threshold
        ):
            end_idx += 1

        return upcoming[start_idx][0], upcoming[end_idx][1]

    # -- Control loop -------------------------------------------------

    async def async_update(self) -> None:
        """Recompute the desired mode and apply it if needed.

        Wrapped in a broad try/except that logs the full traceback -
        without this, an unexpected error anywhere in the update logic
        would previously vanish silently except for a content-free
        asyncio "Task exception was never retrieved" message, making it
        impossible to diagnose. The previous state remains in effect
        until the next successful update.

        Also records success/failure for `sensor.system_status`, so you
        can see at a glance whether the integration is actually working,
        without needing to check the Home Assistant logs yourself.
        """
        try:
            async with self._lock:
                await self._async_update_locked()
        except Exception as err:  # noqa: BLE001 - must never crash silently
            self.last_error = str(err)
            self.last_error_time = dt_util.now()
            _LOGGER.exception(
                "Unexpected error while updating Energy Management System "
                "- this update was skipped, the previous state remains in "
                "effect until the next successful one. Please share this "
                "traceback (and a diagnostics export) if you report this."
            )
        else:
            self.last_successful_update = dt_util.now()
        finally:
            # v0.63.48: notify registered listeners (entities that don't
            # poll, e.g. the NILM confirm/reject slot buttons) after
            # every attempt, success or failure, so their displayed
            # name/attributes never silently stay frozen - placed in a
            # `finally` specifically because _async_update_locked has
            # many early `return` points for different decision
            # branches, not one single exit.
            self._notify_listeners()

    @property
    def system_status(self) -> str:
        """A single, simple health status: 'OK' if the integration is
        actively working, or an explanation of what's wrong otherwise -
        so you don't have to check the Home Assistant logs yourself to
        notice something is off.

        v0.63.109, gevraagd: "misschien iets van een self-diagnose
        toevoegen zodat ik ook in de button relevante en dus systeem
        status ok niet klopt eigenlijk kan zien" - tot dan toe puur een
        TECHNISCHE health-check (crash/vastlopen), die "OK" toonde
        zelfs als `get_diagnostic_summary()` wél degelijk
        aandachtspunten had (bijv. 51 onbevestigde NILM-kandidaten,
        een mogelijk defect apparaat). Nu een derde, tussenliggende
        status: technisch prima draaiend, maar met inhoudelijke
        aandachtspunten - bewust apart van "Fout"/"Mogelijk
        vastgelopen" (die zijn ernstiger: de integratie zelf werkt dan
        niet correct, i.p.v. gewoon iets om even naar te kijken).
        """
        if (
            self.last_error_time is not None
            and (
                self.last_successful_update is None
                or self.last_error_time >= self.last_successful_update
            )
        ):
            return "Fout"

        if self.last_successful_update is not None:
            stale_after = timedelta(minutes=UPDATE_INTERVAL_MINUTES * 3)
            if dt_util.now() - self.last_successful_update > stale_after:
                return "Mogelijk vastgelopen"

        # v0.63.109: negeer specifiek het "Laatste fout"-aandachtspunt
        # hier - dat wordt al preciezer, tijdgevoelig afgedekt door de
        # "Fout"-check hierboven (die onderscheid maakt tussen een
        # RECENTE/actieve fout en een allang herstelde). Zonder dit
        # zou een oude, allang herstelde fout die enkel nog als
        # historisch "laatste fout"-veld blijft staan, hier onterecht
        # "Aandacht gewenst" tonen terwijl de integratie zelf allang
        # weer prima draait.
        overige_aandachtspunten = [
            p
            for p in self.get_diagnostic_summary()["aandachtspunten"]
            if not p.startswith("Laatste fout:")
        ]
        if overige_aandachtspunten:
            return "Aandacht gewenst"

        return "OK"

    def _update_needed_kwh_breakdown_for_display(
        self, now: datetime, cheap_block_start: datetime | None
    ) -> None:
        """Always (re)computes the "capacity expectations" breakdown
        shown in the explanation card (basisverbruik/verwachte zon/
        diepste tekort/veiligheidsmarge) - v0.63.76, requested ("ik wil
        daarom ook altijd de tabel zien").

        Previously this only ever got computed inside
        `_should_postpone_charging`'s own narrow "before today's cheap
        block" scope (`now < cheap_block_start`) - once past that point,
        or whenever there simply wasn't a cheap block identifiable
        (`cheap_block_start is None`), that function takes an early
        return without touching `last_needed_kwh_breakdown` at all, so
        it silently kept whatever stale value it had (often empty, e.g.
        right after a restart) - even though a decision like
        arbitrage_charging (reported, v0.63.73) can perfectly well be
        the live outcome in that same window, with no breakdown shown
        for it at all.

        Uses `cheap_block_start` as the reference end-of-window if it's
        meaningfully ahead of `now`; otherwise falls back to a generic
        24-hour outlook, so there's always something meaningful to show
        regardless of reason or timing. Deliberately independent of
        `_should_postpone_charging`'s own copy of this same computation
        (kept there unchanged, for its own decision-making) - this is
        purely for display, called unconditionally every tick.
        """
        target_time = (
            cheap_block_start
            if cheap_block_start is not None and cheap_block_start > now
            else now + timedelta(hours=24)
        )
        self.last_needed_kwh_breakdown_end_time = target_time

        baseline_consumption_kwh = self._estimate_consumption_kwh_for_period(
            now, target_time
        )
        needed_kwh_raw = self._estimate_worst_case_deficit_kwh(now, target_time)
        if needed_kwh_raw is None:
            hours = max((target_time - now).total_seconds() / 3600, 0)
            learned_kw = self.learned_night_consumption_kw
            if learned_kw is not None:
                power_kw = learned_kw
            else:
                power_w = self._read_corrected_consumption_power()
                power_kw = power_w / 1000 if power_w is not None else None
            needed_kwh_raw = power_kw * hours if power_kw is not None else None

        if needed_kwh_raw is None:
            self.last_needed_kwh_breakdown = {}
            return

        expected_pv_kwh = self._get_efficiency_discounted_pv_offset(now, target_time)
        self.last_needed_kwh_breakdown = {
            "basisverbruik_kwh": (
                round(baseline_consumption_kwh, 3)
                if baseline_consumption_kwh is not None
                else None
            ),
            "verwachte_pv_kwh": round(expected_pv_kwh, 3),
            "diepste_tekort_kwh": round(needed_kwh_raw, 3),
            "veiligheidsmarge_procent": round(
                (ENERGY_BRIDGE_SAFETY_MARGIN - 1) * 100, 1
            ),
        }

    def _build_needed_kwh_breakdown_table(self) -> str:
        """Render the diepste-tekort breakdown as a small Markdown table
        instead of a dense prose sentence - the explanation text is
        rendered as-is in a markdown card, so an actual table shows up as
        one. Explicitly states the period's start/end/duration too,
        instead of the vague "over de hele periode" wording, which was
        the actual point of confusion (reported: the numbers looked
        implausible until the exact period was reconstructed by hand).
        """
        b = self.last_needed_kwh_breakdown
        if not b:
            return ""

        now = dt_util.now()
        # v0.63.76: use the actual end-of-window this breakdown was
        # computed against (cheap_block_start, or the 24h fallback when
        # there wasn't a meaningful upcoming cheap block) - kept
        # consistent with `_update_needed_kwh_breakdown_for_display`.
        end_time = self.last_needed_kwh_breakdown_end_time
        if end_time is not None:
            duration = end_time - now
            total_minutes = max(0, int(duration.total_seconds() // 60))
            hours, minutes = divmod(total_minutes, 60)
            duration_txt = f"{hours}u{minutes:02d}m"
            period_txt = (
                f"nu ({now.strftime('%H:%M')}) → "
                f"{end_time.strftime('%H:%M')} ({duration_txt})"
            )
        else:
            period_txt = "onbekend"

        rows = [
            ("Periode", period_txt),
            ("Basisverbruik", f"{b.get('basisverbruik_kwh', '?')} kWh"),
            (
                "Verwachte zon (na rendementskorting)",
                f"{b.get('verwachte_pv_kwh', '?')} kWh",
            ),
            ("Diepste tekort onderweg", f"{b.get('diepste_tekort_kwh', '?')} kWh"),
            ("Veiligheidsmarge", f"+{b.get('veiligheidsmarge_procent', '?')}%"),
        ]
        lines = [
            "| Onderdeel | Waarde |",
            "|---|---|",
        ]
        lines.extend(f"| {label} | {value} |" for label, value in rows)
        return "\n".join(lines)

    def _finish_decision_tick(self, now: datetime) -> None:
        """Common tail for every branch of the decision tree that actually
        applied something to the device: correct last_expected_mode to
        match what was actually decided (see REASON_TO_MODE - it's set
        early from the price check alone, before headroom/SoC/price-
        priority checks can downgrade an "expensive, should discharge"
        guess back to smart, e.g. expensive_quarter_soc_protected), build
        the explanation text, then check whether the mode/power genuinely
        changed since the last tick and notify if so (see
        `_maybe_notify_mode_change`). Not used by the two branches that
        don't apply anything (no_forecast_data, force_manual) - those
        just build the explanation directly, since there's nothing the
        integration did to notify about.
        """
        self.last_expected_mode = REASON_TO_MODE.get(
            self.last_reason, self.last_expected_mode
        )
        self.last_explanation = self._build_explanation()
        self._maybe_notify_mode_change(now)

    def _maybe_notify_mode_change(self, now: datetime) -> None:
        """Send a notification whenever the mode or applied power the
        integration just sent to the Zendure genuinely changed since the
        last tick - reusing CONF_APPLIANCE_NOTIFY_SERVICE (the same
        setting already used for appliance-ready suggestions, v0.47.0),
        so nothing extra needs to be configured for this.

        Reported: on this setup, the Zendure device does nothing
        autonomous in 'smart' mode - every charge/discharge decision
        comes from this integration, so "the integration changed
        something" and "the battery's behaviour changed" are the same
        event here, worth surfacing directly rather than only readable
        indirectly via the mode/power entities.

        The signature is (reason, discharge power, charge power) so a
        change in applied wattage within the same reason (e.g. the
        household-consumption floor, v0.59.0, adjusting the discharge
        power tick to tick) also counts as a genuine change, not just a
        change of reason/mode. Skipped in learning_only mode (nothing
        was actually sent to the device) and on the very first tick
        after startup/reload (nothing yet to compare against - would
        otherwise fire a spurious notification on every restart).
        """
        if self.learning_only:
            return

        signature = (
            self.last_reason,
            self.last_discharge_power_applied,
            self.last_charge_power_applied,
        )
        if self._last_notified_mode_signature is None:
            self._last_notified_mode_signature = signature
            return
        if signature == self._last_notified_mode_signature:
            return
        self._last_notified_mode_signature = signature

        # Bounded log of every genuine change (v0.63.11), independent of
        # whether a notify service is configured - so a single
        # diagnostics export can reconstruct the whole day's mode
        # history, instead of needing an export pulled at exactly the
        # right moment (or a screenshot from the phone) each time.
        self.mode_change_log.append(
            {
                "at": now.isoformat(),
                "reason": self.last_reason,
                "expected_mode": self.last_expected_mode,
                "discharge_power_applied": self.last_discharge_power_applied,
                "charge_power_applied": self.last_charge_power_applied,
            }
        )
        self.mode_change_log = self.mode_change_log[-50:]

        notify_service = self.config.get(CONF_APPLIANCE_NOTIFY_SERVICE)
        if not notify_service:
            return

        emoji = MODE_CHANGE_EMOJI.get(self.last_reason, "🔄")
        power = (
            self.last_discharge_power_applied
            if self.last_discharge_power_applied is not None
            else self.last_charge_power_applied
        )
        power_txt = f"{power:.0f} W" if power is not None else "n.v.t."
        title = f"{emoji} Accu naar {self.last_expected_mode}"
        message = (
            f"🔌 Vermogen: {power_txt}\n"
            f"🕒 {now.strftime('%H:%M:%S')}\n\n"
            f"{self.last_explanation}"
        )
        self._dispatch_notification(
            notify_service=notify_service,
            title=title,
            message=message,
            notification_id="ems_mode_change",
        )

    def _build_explanation(self) -> str:
        """Build a plain-language (Dutch) explanation of the current
        decision, so you can read in the dashboard what the integration
        is doing and why - without having to piece together raw sensor
        values yourself.
        """
        if self.force_manual:
            return (
                "De 'Force manual'-schakelaar staat aan: de integratie doet nu "
                "niets en laat de Zendure ongemoeid - jij hebt zelf de controle."
            )

        reason = self.last_reason
        parts: list[str] = []

        if reason == "no_forecast_data":
            parts.append(
                "Er kon geen bruikbare prijsvoorspelling gevonden worden op de "
                "geconfigureerde prijssensor. Controleer of die sensor bestaat "
                "en een geldig 'forecast'-attribuut heeft."
            )

        elif reason == "expensive_quarter":
            power = self.last_discharge_power_applied
            power_txt = f"{power:.0f}W" if power else "het ingestelde vermogen"
            tier_txt = (
                "de ruimere secundaire laag (top 45% van de dagprijsrange, "
                "alleen omdat er toch nog vrije ruimte over was)"
                if self.last_expensive_tier == "secondary"
                else "de strikte primaire drempel (top 20% van de "
                "dagprijsrange)"
            )
            parts.append(
                f"Dit kwartier haalt {tier_txt}, dus de accu ontlaadt nu "
                f"actief op {power_txt} om van de hoge prijs te profiteren."
            )
            if self.last_household_load_w is not None and self.last_discharge_floor_applied:
                parts.append(
                    f"Let op: het vermogen is opgehoogd tot minstens je "
                    f"huidige huisverbruik ({self.last_household_load_w:.0f}W), "
                    f"zodat er niet alsnog tegen de piekprijs wordt "
                    f"geïmporteerd."
                )
            if self.last_soc_percent is not None:
                parts.append(f"Huidige accu-SoC: {self.last_soc_percent:.0f}%.")

        elif reason == "expensive_quarter_soc_protected":
            if self.last_price_priority_held_off:
                parts.append(
                    "Dit kwartier is duur genoeg, maar de beperkte "
                    "beschikbare energie wordt bewust bewaard voor een nog "
                    "duurder kwartier later vandaag (prijs-prioriteit) - "
                    "dus blijft de Zendure voor nu op 'smart' staan in "
                    "plaats van al te verkopen."
                )
            elif self.last_used_soc_taper_fallback:
                soc_txt = (
                    f"{self.last_soc_percent:.0f}%"
                    if self.last_soc_percent is not None
                    else "onbekend"
                )
                parts.append(
                    f"Dit zou een duur kwartier zijn om te ontladen, maar de "
                    f"accu-SoC ({soc_txt}) is te laag om dat te "
                    f"rechtvaardigen. Daarom blijft de Zendure op 'smart' "
                    f"staan in plaats van geforceerd te ontladen."
                )
            else:
                available_txt = (
                    f"{self.last_available_kwh:.2f} kWh"
                    if self.last_available_kwh is not None
                    else "onbekend"
                )
                parts.append(
                    f"Dit zou een duur kwartier zijn om te ontladen, maar de "
                    f"nachtreserve-berekening laat geen ruimte over: alle "
                    f"beschikbare energie ({available_txt}) is al nodig om "
                    f"de rest van de nacht te overbruggen. Daarom blijft de "
                    f"Zendure op 'smart' staan (die regelt zelf verder, "
                    f"zonder onze reserve te verkleinen) in plaats van "
                    f"geforceerd te ontladen."
                )

        elif reason == "grid_charging_low_solar":
            parts.append(
                "Er wordt weinig zon verwacht, dus tijdens dit goedkoopste "
                "moment van de dag wordt er actief bijgeladen vanaf het net "
                "(manual, negatief vermogen) in plaats van te wachten op zon."
            )

        elif reason == "grid_charging_low_solar_extra_dip":
            margin_txt = (
                f"{self.last_extra_dip_margin_eur_per_kwh:.3f} €/kWh"
                if self.last_extra_dip_margin_eur_per_kwh is not None
                else "onbekend"
            )
            parts.append(
                "Er wordt weinig zon verwacht vandaag, en dit is een aparte, "
                "losse prijsdip buiten het hoofd-goedkope blok - maar "
                "aantoonbaar voordeliger dan wachten tot het duurste "
                f"resterende moment vandaag (marge, na rendementsverlies: "
                f"{margin_txt}). Daarom wordt er nu ook actief bijgeladen "
                "vanaf het net. Deze energie wordt vandaag niet meer "
                "verkocht (winter-guard)."
            )

        elif reason == "emergency_low_battery":
            soc_txt = (
                f"{self.last_soc_percent:.0f}%"
                if self.last_soc_percent is not None
                else "kritiek laag"
            )
            parts.append(
                f"NOODLADEN: de accu staat op {soc_txt}, te kritiek om te "
                f"wachten tot het goedkoopste blok. De integratie laadt nu "
                f"actief bij vanaf het net, ook al is dit niet het "
                f"goedkoopste moment - beter een klein beetje duurder laden "
                f"dan de accu helemaal leeg laten lopen."
            )

        elif reason == "negative_price":
            power_txt = (
                f"{abs(self.last_charge_power_applied):.0f}W"
                if self.last_charge_power_applied is not None
                else "het ingestelde vermogen"
            )
            parts.append(
                f"De energieprijs is nu negatief: de accu laadt actief op "
                f"{power_txt} (je wordt betaald om te verbruiken), en de "
                f"zonnepanelen worden geleidelijk afgeregeld om niet tegen "
                f"een negatieve prijs terug te leveren."
            )

        elif reason == "arbitrage_solar_capture":
            solar_txt = (
                f"{self.last_arbitrage_solar_surplus_w:.0f}W"
                if self.last_arbitrage_solar_surplus_w is not None
                else "onbekend"
            )
            parts.append(
                f"Er is nu een verwacht zonoverschot van {solar_txt} - "
                f"zonder ingrijpen zou 'laden uitstellen' "
                f"(smart_discharging) dat overschot laten liggen, want "
                f"die modus dekt alleen het huishoudverbruik en laadt "
                f"niet bij vanuit zon. De accu staat daarom nu gewoon in "
                f"smart-modus, die het zonoverschot vanzelf opvangt via "
                f"P1-volgend laden. Wordt nooit actief van het net "
                f"bijgekocht - alleen zon die er al is, wordt "
                f"vastgelegd."
            )

        elif reason == "discharging_window":
            if self.last_has_enough_energy is not None and self.last_available_kwh is not None:
                needed_txt = (
                    f"{self.last_needed_kwh_to_bridge:.2f}"
                    if self.last_needed_kwh_to_bridge is not None
                    else "onbekend"
                )
                parts.append(
                    f"De accu heeft nu {self.last_available_kwh:.2f} kWh "
                    f"beschikbaar - genoeg om de resterende tijd tot het "
                    f"goedkoopste blok te overbruggen (geschat nodig: "
                    f"{needed_txt} kWh). Daarom wordt laden uitgesteld: de "
                    f"accu dekt het huishoudverbruik zelf (0 op de meter), "
                    f"zonder actief te verkopen (smart_discharging)."
                )
            else:
                parts.append(
                    "Het is nog vóór het goedkoopste blok, dus laden wordt "
                    "uitgesteld: de accu dekt het huishoudverbruik zelf (0 "
                    "op de meter), zonder actief te verkopen "
                    "(smart_discharging)."
                )

        elif reason == "default_smart":
            if self.last_has_enough_energy is False:
                needed_txt = (
                    f"{self.last_needed_kwh_to_bridge:.2f}"
                    if self.last_needed_kwh_to_bridge is not None
                    else "onbekend"
                )
                avail_txt = (
                    f"{self.last_available_kwh:.2f}"
                    if self.last_available_kwh is not None
                    else "onbekend"
                )
                parts.append(
                    f"De accu heeft niet genoeg beschikbare energie "
                    f"({avail_txt} kWh) om zowel het basisverbruik als de "
                    f"nog-komende dure kwartieren van vandaag te overbruggen "
                    f"(geschat nodig: {needed_txt} kWh), dus mag de Zendure "
                    f"nu zelf bijladen (smart-modus)."
                )
            else:
                price_txt = (
                    f"€{self.last_current_price_per_kwh:.3f}/kWh"
                    if self.last_current_price_per_kwh is not None
                    else "onbekend"
                )
                if self.last_expensive_price_threshold is not None:
                    threshold_txt = f"€{self.last_expensive_price_threshold:.3f}/kWh"
                    low_solar_txt = (
                        " (vandaag extra streng, want er wordt weinig zon "
                        "verwacht)"
                        if self.last_low_solar_narrowed_threshold
                        else ""
                    )
                    parts.append(
                        f"Er is nu geen speciale reden om in te grijpen: de "
                        f"huidige prijs ({price_txt}) haalt de drempel voor "
                        f"'duur' vandaag ({threshold_txt}{low_solar_txt}) "
                        f"niet, en het goedkoopste blok is al gaande of "
                        f"voorbij. De Zendure regelt dit zelf (smart-modus)."
                    )
                    if self.last_secondary_price_threshold is not None:
                        parts.append(
                            f"Ook de ruimere secundaire drempel "
                            f"(€{self.last_secondary_price_threshold:.3f}/kWh, "
                            f"top 45%) wordt niet gehaald."
                        )
                else:
                    parts.append(
                        "Er is nu geen speciale reden om in te grijpen: de "
                        "prijs is niet bijzonder hoog, en het goedkoopste "
                        "blok is al gaande of voorbij. De Zendure regelt dit "
                        "zelf (smart-modus)."
                    )
                if self.last_winter_guard_suppressed_today:
                    parts.append(
                        "Let op: er is vandaag al bijgeladen vanaf het net "
                        "bij weinig zon (winter-guard), dus eventuele dure "
                        "kwartieren worden vandaag bewust niet verkocht - "
                        "dat zou anders met verlies zijn."
                    )

        else:
            parts.append(f"Onbekende reden: {reason}.")

        # v0.63.22: shown for every reason where it's meaningful context
        # (reported: only visible for discharging_window before this -
        # the underlying data was already fresh every tick regardless of
        # reason, `_should_postpone_charging` runs early and
        # unconditionally, this was purely a text-building gap). Not
        # shown for no_forecast_data (nothing to compute a reserve
        # against) or when the breakdown itself is empty.
        if reason not in ("no_forecast_data",) and self.last_needed_kwh_breakdown:
            parts.append(
                "Diepste-tekort-berekening (het echte dieptepunt onderweg, "
                "niet zomaar het eindsaldo):\n\n"
                + self._build_needed_kwh_breakdown_table()
                + "\n\n"
            )

        recent_shortfalls = sum(1 for v in self.reserve_shortfall_history if v)
        if recent_shortfalls > 0:
            parts.append(
                f"Let op: de afgelopen {LEARNING_HISTORY_DAYS} dagen kwam het "
                f"{recent_shortfalls}x voor dat er onverwacht stroom van het net "
                f"kwam terwijl de accu genoeg had moeten hebben - de "
                f"veiligheidsmarge is daardoor automatisch verhoogd."
            )

        if self.learning_only:
            parts.append(
                "Let op: 'Learning only' staat aan - dit wordt alleen berekend "
                "en gesimuleerd, er wordt niets echt naar de Zendure gestuurd."
            )

        return " ".join(parts)

    async def _async_update_locked(self) -> None:
        now = dt_util.now()
        if self.first_seen_date is None:
            self.first_seen_date = now.date()
        entries = self._get_forecast_entries()

        if not entries:
            _LOGGER.warning(
                "No usable forecast entries found on %s (check that the "
                "'forecast' attribute exists and the selected price "
                "attribute (%s) is present on its items)",
                self.config[CONF_PRICE_SENSOR],
                self.config.get(CONF_PRICE_ATTRIBUTE, DEFAULT_PRICE_ATTRIBUTE),
            )
            self.last_reason = "no_forecast_data"
            self._last_value_calc_time = now
            self.last_explanation = self._build_explanation()
            return

        cheap_block_start, cheap_block_end = self._cheapest_block_range(entries, now)
        self.last_cheap_block_start = cheap_block_start
        self.last_cheap_block_end = cheap_block_end

        effective_count = self._count_expensive_quarters_today(entries, now)
        is_expensive = self._is_expensive_now(entries, now)

        # Stash the threshold context behind is_expensive/is_expensive_tier
        # so _build_explanation can say *why* - not just *that* - a
        # quarter did or didn't qualify (reported: guessing "probably
        # because of low solar" when it was actually just a below-
        # threshold price, or vice versa). Converted to EUR/kWh right
        # away, same scale as last_current_price_per_kwh.
        primary_threshold_raw = self._get_expensive_price_threshold(entries, now)
        self.last_expensive_price_threshold = (
            primary_threshold_raw / PRICE_SCALE_FACTOR
            if primary_threshold_raw is not None
            else None
        )
        self.last_low_solar_narrowed_threshold = self._is_low_solar_expected()

        # Always compute the time-based discharge_start for the timeline
        # projection (it can't know about live battery energy for future
        # intervals), even though the live decision below may use the
        # energy-based check instead.
        self.last_discharge_start = self._compute_dynamic_discharge_start(
            entries, now, cheap_block_start
        )

        # Should we postpone charging (smart_discharging) ahead of the
        # cheapest block? Prefers an energy-based check (is there already
        # enough available battery energy to bridge the remaining time?),
        # falling back to the time-based rule if no energy sensor is set.
        #
        # No special-case override for "the sun is currently producing"
        # here (removed in v0.37.0, was added in v0.25.0 on a mistaken
        # assumption): on this Zendure hardware, smart_discharging doesn't
        # block/waste solar - it routes it straight to export instead of
        # into the battery, and the battery only covers consumption
        # spikes. Solar is used productively either way; only the
        # destination (export vs. storage) differs, which is exactly what
        # the price-driven decision below should determine.
        should_postpone_charging = self._should_postpone_charging(
            entries, now, cheap_block_start
        )
        # v0.63.70/.77: evaluate the solar-capture check early, purely
        # so the schedule projection below can reflect it too - this
        # state (last_arbitrage_solar_surplus_w) gets safely recomputed
        # again later in this same tick, when the real decision is made.
        # v0.63.77: the "actively buy from the grid" branch that used to
        # live here (arbitrage_charging) is removed entirely - see
        # `_should_capture_solar_instead_of_postponing`'s docstring.
        self.last_current_price_per_kwh = self._get_current_price_per_kwh(
            entries, now
        )
        live_should_capture_solar = self._should_capture_solar_instead_of_postponing(
            now, should_postpone_charging
        )
        # v0.63.76, requested ("ik wil daarom ook altijd de tabel
        # zien"): always (re)compute the capacity-expectations
        # breakdown for the explanation card, regardless of reason or
        # of whether _should_postpone_charging's own narrow "before the
        # cheap block" scope was even reached this tick.
        self._update_needed_kwh_breakdown_for_display(now, cheap_block_start)
        self._update_battery_cost_basis_and_savings(now, entries)
        self._update_energy_balance_validation(now)
        self._update_anomaly_detection(now)
        self._update_weather_ensemble_check(now)
        self._update_appliance_state_machine(
            now,
            power_entity=self.config.get(CONF_DISHWASHER_POWER_SENSOR),
            state_attr="_dishwasher_state",
            cycle_started_attr="_dishwasher_cycle_started_at",
            below_threshold_since_attr="_dishwasher_below_threshold_since",
            duration_history_attr="dishwasher_cycle_duration_history",
            notify_title="🍽️ Vaatwasser klaar",
        )
        self._update_appliance_state_machine(
            now,
            power_entity=self.config.get(CONF_WASHING_MACHINE_POWER_SENSOR),
            state_attr="_washing_machine_state",
            cycle_started_attr="_washing_machine_cycle_started_at",
            below_threshold_since_attr="_washing_machine_below_threshold_since",
            duration_history_attr="washing_machine_cycle_duration_history",
            notify_title="🧺 Wasmachine klaar",
        )
        self._compute_mpc_plan(now, entries)
        self._run_monte_carlo_simulation(now, cheap_block_start)
        self._update_kalman_filters()

        # Pause consumption-related learning during vacation mode, so the
        # unusually low readings don't pollute the learned "normal"
        # profile - it would otherwise take a while to recover after
        # coming back. PV bias and battery efficiency learning are
        # unaffected by household consumption, so those keep learning
        # normally throughout.
        if not self.vacation_mode:
            self._update_night_consumption_tracking(now, should_postpone_charging)
            self._update_hourly_consumption_profile(now)
        self._update_pv_hourly_bias_tracking(now)
        self._update_battery_efficiency_learning(now)
        self._check_monthly_rollover(now)
        self._update_appliance_usage_tracking(now)
        self._update_quooker_tracking(now)
        self._update_water_tracking(now)
        self._update_peak_power_tracking(now)
        self._update_battery_module_health(now)
        await self._async_apply_battery_cooling()
        self._update_feedin_regime(now, entries)
        self._update_counterfactual_savings(now, entries)
        self._update_self_sufficiency_tracking(now)
        self._update_battery_cycle_tracking(now)
        self._update_co2_tracking(now)
        self.last_heavy_load_source = self._get_confirmed_heavy_load_source(now)
        self._track_recent_consumption_reading(now)
        self._update_living_room_airco_prediction(now)
        self._update_climate_rate_learning(now)
        await self._async_update_climate_forecast(now)

        is_currently_cheapest_block = (
            cheap_block_start is not None
            and cheap_block_end is not None
            and cheap_block_start <= now < cheap_block_end
        )
        self._check_and_notify_appliance_ready(now, is_currently_cheapest_block)
        await self._async_update_scheduled_charge_appliance(
            now,
            is_currently_cheapest_block,
            switch_entity=self.config.get(CONF_STEELSTOFZUIGER_SWITCH),
            power_entity=self.config.get(CONF_STEELSTOFZUIGER_POWER_SENSOR),
            complete_threshold_w=APPLIANCE_RUNNING_POWER_THRESHOLD_W,
            complete_today_attr="_steelstofzuiger_complete_today",
            complete_date_attr="_steelstofzuiger_complete_date",
            charge_started_attr="_steelstofzuiger_charge_started_at",
            below_threshold_since_attr="_steelstofzuiger_below_threshold_since",
            duration_history_attr="steelstofzuiger_charge_duration_history",
            last_action_attr="last_steelstofzuiger_action",
            ever_active_this_session_attr="_steelstofzuiger_ever_active_this_session",
            next_poll_attr="_steelstofzuiger_next_poll_at",
            idle_history_attr="_steelstofzuiger_idle_power_history",
            notify_title="🧹 Steelstofzuiger opgeladen",
            notify_message="De steelstofzuiger is klaar met laden en de lader is uitgeschakeld.",
            override_attr="steelstofzuiger_override",
        )
        await self._async_update_scheduled_charge_appliance(
            now,
            is_currently_cheapest_block,
            switch_entity=self.config.get(CONF_FIETSLADERS_SWITCH),
            power_entity=self.config.get(CONF_FIETSLADERS_POWER_SENSOR),
            complete_threshold_w=FIETSLADERS_COMPLETE_THRESHOLD_W,
            complete_today_attr="_fietsladers_complete_today",
            complete_date_attr="_fietsladers_complete_date",
            charge_started_attr="_fietsladers_charge_started_at",
            below_threshold_since_attr="_fietsladers_below_threshold_since",
            duration_history_attr="fietsladers_charge_duration_history",
            last_action_attr="last_fietsladers_action",
            ever_active_this_session_attr="_fietsladers_ever_active_this_session",
            next_poll_attr="_fietsladers_next_poll_at",
            idle_history_attr="_fietsladers_idle_power_history",
            notify_title="🚲 Fietsen opgeladen",
            notify_message="De fietsladers zijn uitgeschakeld omdat de accu's vol zijn.",
            override_attr="fietsladers_override",
        )

        self.last_is_expensive = is_expensive
        self.last_effective_expensive_quarters_count = effective_count
        projection_reserve_kwh = self._get_dynamic_discharge_reserve_kwh(
            now, cheap_block_start
        )
        # Read fresh directly, rather than relying on self.last_available_kwh -
        # that's only populated when _should_postpone_charging's energy-based
        # check actually runs this tick, which isn't guaranteed (e.g. outside
        # the relevant decision window). Without this, the schedule
        # projection's headroom-based capping (see _build_forecast_timeline)
        # would silently fall back to the uncapped price-only projection
        # whenever last_available_kwh happened to be stale/None, showing a
        # misleadingly long "manual" block regardless of actual battery
        # capacity.
        projection_available_kwh = self._read_sensor_float(
            self.config.get(CONF_AVAILABLE_ENERGY_SENSOR)
        )
        if projection_available_kwh is not None and projection_available_kwh < 0:
            projection_available_kwh = 0.0
        self.last_projection_available_kwh = projection_available_kwh
        self.last_projection_reserve_kwh = projection_reserve_kwh
        self.last_timeline = self._build_forecast_timeline(
            entries,
            now,
            cheap_block_start,
            self.last_discharge_start,
            live_is_expensive=is_expensive,
            live_should_postpone_charging=should_postpone_charging,
            live_should_capture_solar=live_should_capture_solar,
            available_kwh=projection_available_kwh,
            reserve_kwh=projection_reserve_kwh,
        )
        self.last_transitions = self._collapse_timeline(self.last_timeline)
        self._run_digital_twin_simulation(now)
        self._update_nilm_discovery(now)
        self._update_nilm_confirmed_devices(now)
        self._update_advisory_readiness(now)

        # What the pure price/solar logic wants, independent of
        # force_manual or learning_only - lets you graph this against the
        # actual Zendure mode to see when/why they diverge.
        # Should we actively force-charge from the grid (manual, negative
        # power) during the cheapest block itself? Only when little solar
        # is expected - otherwise the Zendure's own smart charging from PV
        # surplus during the cheap block is left in charge, as before.
        in_cheap_block = (
            cheap_block_start is not None
            and cheap_block_end is not None
            and cheap_block_start <= now < cheap_block_end
        )
        is_low_solar = self._is_low_solar_expected()
        should_force_charge = in_cheap_block and is_low_solar

        self.last_expected_mode = (
            OPTION_MANUAL
            if (is_expensive or should_force_charge)
            else (OPTION_SMART_DISCHARGING if should_postpone_charging else OPTION_SMART)
        )

        if self.force_manual:
            # Explicit manual override: leave the Zendure mode untouched.
            self.last_reason = "force_manual"
            self.last_simulated_action = None
            self._update_financial_tracking(now, entries, self.last_reason, None, None)
            self.last_explanation = self._build_explanation()
            return

        # Negative price handling: takes priority over everything else
        # (except an explicit force_manual override, handled above).
        # Charge the battery hard and curtail solar production - exporting
        # or even just running the panels is actively costing money at a
        # negative price. Restore both when the price turns positive again.
        current_price_per_kwh = self._get_current_price_per_kwh(entries, now)
        self.last_current_price_per_kwh = current_price_per_kwh
        is_negative_price = (
            current_price_per_kwh is not None and current_price_per_kwh < 0
        )

        if is_negative_price:
            if not self._is_negative_price_active:
                self._is_negative_price_active = True
                self._start_solar_ramp(0.0)
            charge_power = self.config.get(
                CONF_NEGATIVE_PRICE_CHARGE_POWER, DEFAULT_NEGATIVE_PRICE_CHARGE_POWER
            )
            await self._async_apply_manual(charge_power)
            self.last_reason = "negative_price"
            self.last_charge_power_applied = charge_power
            self._update_financial_tracking(
                now, entries, self.last_reason, None, charge_power
            )
            self._finish_decision_tick(now)
            return

        if self._is_negative_price_active:
            # Price just turned positive again - restore the panels, then
            # fall through to the normal decision logic below (whichever
            # mode it determines now takes over, as requested).
            self._is_negative_price_active = False
            self._start_solar_ramp(100.0)

        # Winter guard: if the battery was force-charged from the grid
        # today (low solar), don't also manual-discharge at high prices
        # that same day - that energy was bought to cover the household
        # through a low-solar stretch, not to arbitrage. Reset the flag
        # once a new day starts.
        if self._grid_charged_date != now.date():
            self._grid_charged_today = False
            self._grid_charged_date = now.date()
            self.last_winter_guard_suppressed_today = False

        expensive_tier = "primary" if is_expensive else None
        self.last_secondary_price_threshold = None

        if is_expensive and self._grid_charged_today:
            self.last_winter_guard_suppressed_today = True
            _LOGGER.debug(
                "Suppressing expensive_quarter discharge: the battery was "
                "already grid-charged today (low solar) - selling that "
                "same energy back would just be a loss, not arbitrage."
            )
            is_expensive = False
            expensive_tier = None

        # Secondary tier: if 'now' doesn't clear the strict, primary
        # dynamic threshold, check whether there's genuinely *spare*
        # headroom left over after today's remaining genuinely-expensive
        # quarters are accounted for - and if so, whether 'now' is worth
        # selling at the wider, more lenient secondary threshold instead.
        # Without this, a day with abundant available energy could leave
        # meaningfully-above-average quarters untouched purely because
        # they don't clear the strict top-tier cutoff, even though there
        # was clearly no risk in selling more (found via a live report:
        # 8kWh available, only a single 15-minute quarter sold, while
        # surrounding quarters at only a slightly lower price went
        # unused). Never applies if the winter guard above already
        # suppressed selling today, or while grid-charged.
        if not is_expensive and not self._grid_charged_today:
            secondary_threshold_raw = self._get_secondary_expensive_price_threshold(
                entries, now
            )
            self.last_secondary_price_threshold = (
                secondary_threshold_raw / PRICE_SCALE_FACTOR
                if secondary_threshold_raw is not None
                else None
            )
            secondary_available_entity = self.config.get(CONF_AVAILABLE_ENERGY_SENSOR)
            secondary_available_kwh = (
                self._read_sensor_float(secondary_available_entity)
                if secondary_available_entity
                else None
            )
            if secondary_available_kwh is not None and secondary_available_kwh > 0:
                secondary_reserve_kwh = self._get_dynamic_discharge_reserve_kwh(
                    now, cheap_block_start
                )
                if secondary_reserve_kwh is not None:
                    secondary_headroom_kwh = max(
                        0.0, secondary_available_kwh - secondary_reserve_kwh
                    )
                    secondary_discharge_power = self.config.get(
                        CONF_MANUAL_DISCHARGE_POWER, DEFAULT_MANUAL_DISCHARGE_POWER
                    )
                    if self._is_worth_discharging_at_secondary_tier(
                        entries, now, secondary_headroom_kwh, secondary_discharge_power
                    ):
                        is_expensive = True
                        expensive_tier = "secondary"

        self.last_expensive_tier = expensive_tier

        if is_expensive:
            discharge_power = self.config.get(
                CONF_MANUAL_DISCHARGE_POWER, DEFAULT_MANUAL_DISCHARGE_POWER
            )
            scaled_power = self._get_soc_scaled_discharge_power(
                discharge_power, now, cheap_block_start, entries
            )
            if scaled_power is None and self._is_emergency_low_battery():
                # SoC too low to discharge - and critically low, not just
                # "protected". Don't just sit in smart mode hoping for the
                # best (that's exactly what failed in the reported
                # incident) - actively top up instead.
                charge_power = self.config.get(
                    CONF_MANUAL_CHARGE_POWER, DEFAULT_MANUAL_CHARGE_POWER
                )
                await self._async_apply_manual(charge_power)
                self.last_reason = "emergency_low_battery"
                self._grid_charged_today = True
                self.last_charge_power_applied = charge_power
                self._update_financial_tracking(
                    now, entries, self.last_reason, None, charge_power
                )
                self._update_shortfall_detection(now, self.last_reason, self.last_available_kwh, self.last_needed_kwh_to_bridge)
                self._finish_decision_tick(now)
                return
            if scaled_power is None:
                # SoC too low to justify forced export - protect the
                # battery and let the Zendure's own smart mode take over.
                await self._async_apply_operation(OPTION_SMART)
                self.last_reason = "expensive_quarter_soc_protected"
            else:
                await self._async_apply_manual(scaled_power)
                self.last_reason = "expensive_quarter"
            self._update_financial_tracking(
                now, entries, self.last_reason, scaled_power, None
            )
            self._update_shortfall_detection(now, self.last_reason, self.last_available_kwh, self.last_needed_kwh_to_bridge)
            self._finish_decision_tick(now)
            return

        if should_force_charge:
            charge_power = self.config.get(
                CONF_MANUAL_CHARGE_POWER, DEFAULT_MANUAL_CHARGE_POWER
            )
            await self._async_apply_manual(charge_power)
            self.last_reason = "grid_charging_low_solar"
            self._grid_charged_today = True
            self.last_charge_power_applied = charge_power
            self._update_financial_tracking(
                now, entries, self.last_reason, None, charge_power
            )
            self._update_shortfall_detection(now, self.last_reason, self.last_available_kwh, self.last_needed_kwh_to_bridge)
            self._finish_decision_tick(now)
            return

        # Extra-dip laden op weinig-zon-dagen (v0.63.87, uitgebreid
        # besproken en ontworpen door de gebruiker). Buiten het
        # hoofdblok (should_force_charge hierboven al niet gevuurd),
        # maar alleen relevant wanneer het al een weinig-zon-dag is
        # (dezelfde genuine behoefte als het hoofdblok) - een aparte,
        # losse prijsdip elders vandaag die aantoonbaar voordeliger is
        # dan het duurste resterende moment, na rendementsverlies.
        # Bewust GEEN `not self._grid_charged_today`-poort: op een
        # weinig-zon-dag heeft het hoofdblok (vroeg op de dag) die vlag
        # vrijwel altijd al gezet, dus zo'n poort zou dit mechanisme in
        # de praktijk onbereikbaar maken. De vlag is bedoeld om later
        # VERKOPEN te onderdrukken (winter-guard), niet om verder LADEN
        # te blokkeren - meer bijladen wanneer aantoonbaar voordelig is
        # blijft prima, ongeacht of er die dag al eerder is bijgeladen.
        # Bewust GEEN rendement-check op het hoofdblok zelf (expliciet
        # zo gevraagd - dat is al per definitie het goedkoopste moment
        # van de dag) - alleen hier, waar dit een echte
        # winst-vergelijking is, niet een gegarandeerde-behoefte-check.
        self.last_extra_dip_margin_eur_per_kwh = None
        if is_low_solar and not in_cheap_block:
            efficiency_percent = self.learned_battery_efficiency_percent
            if efficiency_percent is None:
                efficiency_percent = float(
                    self.config.get(
                        CONF_BATTERY_ROUND_TRIP_EFFICIENCY,
                        DEFAULT_BATTERY_ROUND_TRIP_EFFICIENCY_PERCENT,
                    )
                )
            efficiency = efficiency_percent / 100
            best_remaining_price_eur = self._get_best_remaining_price_today_eur(
                entries, now
            )
            if best_remaining_price_eur is not None and current_price_per_kwh is not None:
                margin_eur_per_kwh = (
                    efficiency * best_remaining_price_eur
                ) - current_price_per_kwh
                self.last_extra_dip_margin_eur_per_kwh = round(margin_eur_per_kwh, 4)
                # v0.63.88, gevraagd: inzicht of de marge over tijd
                # groter/kleiner wordt. Eén sample per dag (niet elke
                # tick - de marge wordt elke tick herberekend zolang de
                # voorwaarden gelden, dat zou de geschiedenis met
                # bijna-identieke waarden overspoelen).
                if self._extra_dip_margin_last_sample_date != now.date():
                    self._extra_dip_margin_last_sample_date = now.date()
                    self.extra_dip_margin_history.append(
                        self.last_extra_dip_margin_eur_per_kwh
                    )
                    self.extra_dip_margin_history = self.extra_dip_margin_history[
                        -LEARNING_HISTORY_DAYS:
                    ]
                if margin_eur_per_kwh >= LOW_SOLAR_EXTRA_DIP_MIN_MARGIN_EUR_PER_KWH:
                    charge_power = self.config.get(
                        CONF_MANUAL_CHARGE_POWER, DEFAULT_MANUAL_CHARGE_POWER
                    )
                    await self._async_apply_manual(charge_power)
                    self.last_reason = "grid_charging_low_solar_extra_dip"
                    self._grid_charged_today = True
                    self.last_charge_power_applied = charge_power
                    self._update_financial_tracking(
                        now, entries, self.last_reason, None, charge_power
                    )
                    self._update_shortfall_detection(now, self.last_reason, self.last_available_kwh, self.last_needed_kwh_to_bridge)
                    self._finish_decision_tick(now)
                    return

        # Emergency top-up: the battery is critically low right now,
        # regardless of price timing. Don't passively wait for the cheap
        # block to arrive - that's exactly what failed in the reported
        # incident (the shortage was visible hours in advance, but nothing
        # intervened outside the cheap block until the battery was empty).
        if self._is_emergency_low_battery():
            charge_power = self.config.get(
                CONF_MANUAL_CHARGE_POWER, DEFAULT_MANUAL_CHARGE_POWER
            )
            await self._async_apply_manual(charge_power)
            self.last_reason = "emergency_low_battery"
            self._grid_charged_today = True
            self.last_charge_power_applied = charge_power
            self._update_financial_tracking(
                now, entries, self.last_reason, None, charge_power
            )
            self._update_shortfall_detection(now, self.last_reason, self.last_available_kwh, self.last_needed_kwh_to_bridge)
            self._finish_decision_tick(now)
            return

        if self._should_capture_solar_instead_of_postponing(now, should_postpone_charging):
            # v0.63.60/.77, reported ('moet naar smart niet naar
            # manual', then final confirmed decision to remove the
            # active-buying mechanism entirely) - solar surplus alone
            # would otherwise be wasted by smart_discharging (the plain
            # postpone fallback), which doesn't capture surplus solar at
            # all. No active grid purchase is ever made here any more -
            # just don't let that free solar go to waste by staying in
            # smart_discharging. Plain OPTION_SMART's own P1-following
            # captures it naturally, exactly like it always does when
            # should_postpone_charging is False - no manual command
            # involved.
            await self._async_apply_operation(OPTION_SMART)
            self.last_reason = "arbitrage_solar_capture"
            self._update_financial_tracking(now, entries, self.last_reason, None, None)
            self._update_shortfall_detection(now, self.last_reason, self.last_available_kwh, self.last_needed_kwh_to_bridge)
            self._finish_decision_tick(now)
            return

        if should_postpone_charging:
            await self._async_apply_operation(OPTION_SMART_DISCHARGING)
            self.last_reason = "discharging_window"
            self._update_financial_tracking(now, entries, self.last_reason, None, None)
            self._update_shortfall_detection(now, self.last_reason, self.last_available_kwh, self.last_needed_kwh_to_bridge)
            self._finish_decision_tick(now)
            return

        await self._async_apply_operation(OPTION_SMART)
        self.last_reason = "default_smart"
        self._update_financial_tracking(now, entries, self.last_reason, None, None)
        self._update_shortfall_detection(now, self.last_reason, self.last_available_kwh, self.last_needed_kwh_to_bridge)
        self._finish_decision_tick(now)

    async def _async_apply_operation(self, option: str) -> None:
        """Set the Zendure operation mode, unless in learning_only mode."""
        if self.learning_only:
            self.last_simulated_action = f"would set operation to '{option}'"
            _LOGGER.debug("Learning-only mode: %s", self.last_simulated_action)
            return
        self.last_simulated_action = None
        await self.hass.services.async_call(
            "select",
            "select_option",
            {
                "entity_id": self.config[CONF_OPERATION_SELECT],
                "option": option,
            },
            blocking=True,
        )

    async def _async_apply_manual(self, power: float) -> None:
        """Set manual mode with the given power, unless in learning_only
        mode. Positive power discharges, negative charges (matching the
        Zendure manual power number's own sign convention).
        """
        if self.learning_only:
            self.last_simulated_action = (
                f"would set operation to '{OPTION_MANUAL}' with power {power}W"
            )
            _LOGGER.debug("Learning-only mode: %s", self.last_simulated_action)
            return
        self.last_simulated_action = None
        await self.hass.services.async_call(
            "select",
            "select_option",
            {
                "entity_id": self.config[CONF_OPERATION_SELECT],
                "option": OPTION_MANUAL,
            },
            blocking=True,
        )
        await self.hass.services.async_call(
            "number",
            "set_value",
            {
                "entity_id": self.config[CONF_MANUAL_POWER_NUMBER],
                "value": power,
            },
            blocking=True,
        )
