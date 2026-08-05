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
from datetime import date, datetime, timedelta

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
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
    CONF_OVEN_STATE_SENSOR,
    CONF_KOOKPLAAT_STATE_SENSOR,
    CONF_STEELSTOFZUIGER_SWITCH,
    CONF_STEELSTOFZUIGER_POWER_SENSOR,
    CONF_FIETSLADERS_SWITCH,
    CONF_FIETSLADERS_POWER_SENSOR,
    STEELSTOFZUIGER_COMPLETE_SUSTAINED_MINUTES,
    FIETSLADERS_COMPLETE_THRESHOLD_W,
    QUOOKER_SUSTAINED_MINUTES,
    AIRCO_ACTIVE_HVAC_ACTIONS,
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
    CONF_MANUAL_POWER_NUMBER,
    CONF_MIN_SOC_PERCENT,
    CONF_OPERATION_SELECT,
    CONF_PRICE_ATTRIBUTE,
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
    DEFAULT_PRICE_ATTRIBUTE,
    ENERGY_BRIDGE_SAFETY_MARGIN,
    DYNAMIC_DISCHARGE_RESERVE_MARGIN,
    EXTENDED_LOW_SOLAR_MARGIN_BONUS_PER_DAY,
    MIN_ACTIVE_SOLAR_PRODUCTION_W,
    LEARNING_HISTORY_DAYS,
    LOW_SOLAR_RELATIVE_FRACTION,
    EXPENSIVE_PRICE_THRESHOLD_FRACTION,
    EXPENSIVE_PRICE_THRESHOLD_FRACTION_LOW_SOLAR,
    SECONDARY_EXPENSIVE_PRICE_THRESHOLD_FRACTION,
    DEFAULT_NEGATIVE_PRICE_CHARGE_POWER,
    SOLAR_RAMP_DURATION_SECONDS,
    SOLAR_RAMP_STEPS,
    GRID_IMPORT_SHORTFALL_THRESHOLD_W,
    MAX_HOUR_TRACKING_GAP_MINUTES,
    MIN_COST_BASIS_DELTA_KWH,
    FEEDIN_PREMIUM_EUR_PER_KWH,
    FEEDIN_PREMIUM_EUR_PER_KWH,
    MIN_ARBITRAGE_MARGIN_EUR_PER_KWH,
    MIN_ARBITRAGE_GRID_POWER_W,
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
        self.arbitrage_charging_enabled: bool = False
        self.last_arbitrage_margin_eur_per_kwh: float | None = None
        self.last_arbitrage_solar_surplus_w: float | None = None
        self.last_arbitrage_grid_power_w: float | None = None
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
        self.steelstofzuiger_charge_duration_history: list[float] = []
        self.last_steelstofzuiger_action: str | None = None
        self._fietsladers_complete_today: bool = False
        self._fietsladers_complete_date: date | None = None
        self._fietsladers_charge_started_at: datetime | None = None
        self._fietsladers_below_threshold_since: datetime | None = None
        self.fietsladers_charge_duration_history: list[float] = []
        self.last_fietsladers_action: str | None = None

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
        self.last_simulated_action: str | None = None
        self.last_expected_mode: str | None = None
        self.last_available_kwh: float | None = None
        self.last_needed_kwh_to_bridge: float | None = None
        self.last_needed_kwh_breakdown: dict = {}
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
        self.reserve_shortfall_history: list[bool] = []
        self.reserve_shortfall_dates: list[str] = []
        self._shortfall_detected_today: bool = False
        self._shortfall_check_date: date | None = None
        self.reserve_excess_history: list[bool] = []
        self.reserve_excess_dates: list[str] = []
        self._excess_detected_today: bool = False
        self._last_value_calc_time: datetime | None = None

        self._lock = asyncio.Lock()
        self._unsub_interval = None
        self._unsub_state = None

    @property
    def tracked_entities(self) -> list[str]:
        return [self.config[CONF_PRICE_SENSOR]]

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
        self._unsub_interval = async_track_time_interval(
            self.hass,
            self._handle_interval,
            timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )
        self._unsub_state = async_track_state_change_event(
            self.hass, self.tracked_entities, self._handle_state_change
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

    async def async_set_arbitrage_charging_enabled(self, value: bool) -> None:
        self.arbitrage_charging_enabled = value
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

    def _get_forecast_entries(self) -> list[PriceEntry]:
        """Read and parse the raw forecast attribute into (start, end, price) tuples."""
        state = self.hass.states.get(self.config[CONF_PRICE_SENSOR])
        if state is None:
            return []

        forecast = state.attributes.get("forecast")
        if not forecast:
            return []

        price_key = self.config.get(CONF_PRICE_ATTRIBUTE, DEFAULT_PRICE_ATTRIBUTE)
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
        "expensive" threshold - informational only (shown in
        sensor.effective_expensive_quarters), not used to limit discharge.
        """
        threshold = self._get_expensive_price_threshold(entries, now)
        if threshold is None:
            return 0
        todays_entries = [entry for entry in entries if entry[0].date() == now.date()]
        return sum(1 for entry in todays_entries if entry[2] >= threshold)

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
        - purely a suggestion for the person to act on."""
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
        notify_title: str | None = None,
        notify_message: str | None = None,
        override_attr: str | None = None,
    ) -> None:
        """Shared logic (v0.63.13, generalised from the steelstofzuiger-
        only v0.63.12) for any appliance that should charge only during
        today's cheapest price block, year-round, and switch itself off
        once charging is genuinely complete (power draw sustained below
        `complete_threshold_w` for STEELSTOFZUIGER_COMPLETE_SUSTAINED_MINUTES
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
            setattr(
                self,
                last_action_attr,
                "voltooid_vandaag" if complete_today else "wacht_op_goedkoop_blok",
            )
            return

        if not is_on:
            await self._async_set_switch(switch_entity, turn_on=True)
            setattr(self, charge_started_attr, now)
            setattr(self, below_threshold_since_attr, None)
            setattr(self, last_action_attr, "laden_gestart")
            return

        # Already on and inside the cheap block - watch for completion.
        if power_entity and power_w is not None and power_w < complete_threshold_w:
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
        """
        if not self._recent_consumption_readings_kw:
            return 1.0

        current_hour_learned_kw = self.learned_hourly_avg_kw(current_hour)
        if not current_hour_learned_kw or current_hour_learned_kw <= 0:
            return 1.0

        if self.last_heavy_load_source is not None:
            # A known heavy consumer is confirmed active right now (see
            # _get_confirmed_heavy_load_source) - no ambiguity left to
            # protect against, so trust the latest live reading directly
            # instead of waiting for the median of several ticks to
            # catch up. Still capped below like the median path.
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
            self._window_last_sample = now
        else:
            if self._tracking_window_end is not None:
                self._finalize_night_consumption_window()

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

        self._tracking_window_end = None
        self._window_energy_kwh = 0.0
        self._window_duration_hours = 0.0
        self._window_last_sample = None

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

    def _get_best_remaining_sell_price_today_eur(
        self, entries: list[PriceEntry], now: datetime
    ) -> float | None:
        """Highest price (EUR/kWh) among today's still-upcoming quarters -
        the best-case sale this bought energy could realistically be
        sold into later today. None if there's no more price data left
        today."""
        todays_remaining = [
            e for e in entries if e[0].date() == now.date() and e[0] >= now
        ]
        if not todays_remaining:
            return None
        return max(e[2] for e in todays_remaining) / PRICE_SCALE_FACTOR

    def _get_arbitrage_charge_power(
        self, entries: list[PriceEntry], now: datetime
    ) -> float | None:
        """How much to actively buy from the grid right now, purely
        because a known, more expensive quarter is still coming later
        today and buying now is profitable even after round-trip losses
        (reported: 'nu tegen 21 ct niet laden en dan vanavond wat meer
        tegen dure uren ontladen' - the margin was being left on the
        table). Returns None if arbitrage charging is disabled, not
        profitable right now, or the live solar surplus already covers
        the desired charge rate on its own.

        Deliberately solar-first (reported: 'tijdens goedkope uren
        vooral zonne-energie blijft opslaan'): only tops up the *gap*
        between the desired charge rate and whatever live PV surplus is
        already available - if solar alone already covers it, this
        returns None and the existing smart-mode P1-following captures
        that solar itself, same as it always has. Only steps in with
        grid power for the shortfall.
        """
        if not self.arbitrage_charging_enabled:
            return None
        if self.last_current_price_per_kwh is None:
            return None

        best_sell_price = self._get_best_remaining_sell_price_today_eur(entries, now)
        if best_sell_price is None:
            return None

        efficiency_percent = self.learned_battery_efficiency_percent
        if efficiency_percent is None:
            efficiency_percent = float(
                self.config.get(
                    CONF_BATTERY_ROUND_TRIP_EFFICIENCY,
                    DEFAULT_BATTERY_ROUND_TRIP_EFFICIENCY_PERCENT,
                )
            )
        efficiency_factor = efficiency_percent / 100

        projected_net_eur_per_kwh = (
            efficiency_factor * best_sell_price
        ) - self.last_current_price_per_kwh
        self.last_arbitrage_margin_eur_per_kwh = round(projected_net_eur_per_kwh, 4)
        if projected_net_eur_per_kwh < MIN_ARBITRAGE_MARGIN_EUR_PER_KWH:
            return None

        target_power_w = abs(
            self.config.get(CONF_MANUAL_CHARGE_POWER, DEFAULT_MANUAL_CHARGE_POWER)
        )

        pv_entity = self.config.get(CONF_PV_POWER_SENSOR)
        pv_power_w = self._read_sensor_float(pv_entity) if pv_entity else None
        household_load_w = self._read_corrected_consumption_power()
        solar_surplus_w = 0.0
        if pv_power_w is not None and household_load_w is not None:
            solar_surplus_w = max(0.0, pv_power_w - household_load_w)
        self.last_arbitrage_solar_surplus_w = round(solar_surplus_w, 1)

        grid_power_w = max(0.0, target_power_w - solar_surplus_w)
        self.last_arbitrage_grid_power_w = round(grid_power_w, 1)
        if grid_power_w < MIN_ARBITRAGE_GRID_POWER_W:
            # Solar surplus already covers (most of) the desired rate -
            # let the existing smart-mode P1-following capture it
            # itself, rather than disrupting it for a trickle of grid
            # power.
            return None

        return grid_power_w

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
                self.reserve_shortfall_history.append(self._shortfall_detected_today)
                self.reserve_shortfall_history = self.reserve_shortfall_history[
                    -LEARNING_HISTORY_DAYS:
                ]
                self.reserve_shortfall_dates.append(
                    self._shortfall_check_date.isoformat()
                )
                self.reserve_shortfall_dates = self.reserve_shortfall_dates[
                    -LEARNING_HISTORY_DAYS:
                ]
                self.reserve_excess_history.append(self._excess_detected_today)
                self.reserve_excess_history = self.reserve_excess_history[
                    -LEARNING_HISTORY_DAYS:
                ]
                self.reserve_excess_dates.append(
                    self._shortfall_check_date.isoformat()
                )
                self.reserve_excess_dates = self.reserve_excess_dates[
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
            threshold_kwh = learned_typical_kwh * LOW_SOLAR_RELATIVE_FRACTION
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
                elif live_should_postpone_charging:
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

            export_kwh = 0.0
            discharge_rate_kw = discharge_power_w / 1000
            household_load_w = self._read_corrected_consumption_power()
            if household_load_w is not None:
                export_rate_kw = max(0.0, discharge_rate_kw - household_load_w / 1000)
                export_kwh = min(energy_kwh, export_rate_kw * elapsed_hours)

            feedin_premium_eur = export_kwh * FEEDIN_PREMIUM_EUR_PER_KWH
            value_eur = energy_kwh * current_price + feedin_premium_eur
            self.total_discharge_value_eur += value_eur
            self.current_month_discharge_value_eur += value_eur
            self.total_feedin_premium_eur += feedin_premium_eur
        elif (
            reason in ("grid_charging_low_solar", "emergency_low_battery")
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

        Requires a salderen (net-metering) contract to be valid: under
        salderen, feed-in pays the same dynamic rate as import, so PV
        routed into the battery instead of exported has exactly the same
        opportunity cost as buying that energy from the grid at that
        moment - equating PV-charged and grid-charged energy into one
        cost basis, without needing to track per-source lots (which
        isn't physically possible anyway - the battery is one shared
        pool). Revisit if/when salderen ends.

        v0.63.25: on the discharge side, also splits out how much of the
        discharge was genuine net export to the grid (vs. just covering
        household load) - confirmed via web search that Zonneplan pays a
        fixed EUR/kWh feed-in premium (`FEEDIN_PREMIUM_EUR_PER_KWH`) on
        top of the market price for every kWh actually fed back,
        including from a battery (only the separate 10% "Zonnebonus"
        excludes battery-sourced feed-in, which this integration never
        claims anyway). Covering household load isn't feed-in at all, so
        gets no premium - only the value of the avoided import. The
        export portion is approximated as (discharge rate - household
        load) over this tick's interval, using the live corrected
        consumption reading; deliberately doesn't yet apply on the
        *charging* side (the opportunity-cost-of-diverted-PV question),
        a further refinement if wanted.

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
            # Charged (from any source) - fold into the weighted-average
            # cost basis at today's price.
            if self.battery_cost_basis_eur_per_kwh is None:
                self.battery_cost_basis_eur_per_kwh = current_price
            else:
                # Weight by whatever was already stored before this
                # charge - approximated by the available_kwh just before
                # this delta (available_kwh - delta_kwh).
                previous_kwh = max(0.0, available_kwh - delta_kwh)
                total_kwh = previous_kwh + delta_kwh
                self.battery_cost_basis_eur_per_kwh = (
                    self.battery_cost_basis_eur_per_kwh * previous_kwh
                    + current_price * delta_kwh
                ) / total_kwh
        else:
            # Discharged (sold, or used to cover load and avoid an
            # import) - realise the difference between today's price and
            # what this energy originally cost, if a cost basis exists
            # yet. Pre-existing energy with an unknown origin (e.g. right
            # after a fresh install) is skipped rather than guessed at.
            if self.battery_cost_basis_eur_per_kwh is not None:
                discharged_kwh = -delta_kwh

                export_kwh = 0.0
                if elapsed_hours > 0:
                    discharge_rate_kw = discharged_kwh / elapsed_hours
                    household_load_w = self._read_corrected_consumption_power()
                    if household_load_w is not None:
                        export_rate_kw = max(
                            0.0, discharge_rate_kw - household_load_w / 1000
                        )
                        export_kwh = min(
                            discharged_kwh, export_rate_kw * elapsed_hours
                        )

                feedin_premium_eur = export_kwh * FEEDIN_PREMIUM_EUR_PER_KWH
                savings_eur = (
                    discharged_kwh
                    * (current_price - self.battery_cost_basis_eur_per_kwh)
                    + feedin_premium_eur
                )
                self.total_battery_savings_eur += savings_eur
                self.total_feedin_premium_eur += feedin_premium_eur

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

    @property
    def system_status(self) -> str:
        """A single, simple health status: 'OK' if the integration is
        actively working, or an explanation of what's wrong otherwise -
        so you don't have to check the Home Assistant logs yourself to
        notice something is off.
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

        return "OK"

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
        cheap_block_start = self.last_cheap_block_start
        if cheap_block_start is not None:
            duration = cheap_block_start - now
            total_minutes = max(0, int(duration.total_seconds() // 60))
            hours, minutes = divmod(total_minutes, 60)
            duration_txt = f"{hours}u{minutes:02d}m"
            period_txt = (
                f"nu ({now.strftime('%H:%M')}) → "
                f"{cheap_block_start.strftime('%H:%M')} ({duration_txt})"
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

        elif reason == "arbitrage_charging":
            power_txt = (
                f"{abs(self.last_charge_power_applied):.0f}W"
                if self.last_charge_power_applied is not None
                else "het ingestelde vermogen"
            )
            margin_txt = (
                f"€{self.last_arbitrage_margin_eur_per_kwh:.3f}/kWh"
                if self.last_arbitrage_margin_eur_per_kwh is not None
                else "onbekend"
            )
            solar_txt = (
                f"{self.last_arbitrage_solar_surplus_w:.0f}W"
                if self.last_arbitrage_solar_surplus_w is not None
                else "0W"
            )
            parts.append(
                f"Arbitrage-laden: er komt later vandaag een duurder "
                f"kwartier, dus wordt er nu actief bijgekocht op "
                f"{power_txt} - geschatte nettowinst na laad/ontlaad-"
                f"verlies: {margin_txt}. Live zonoverschot ({solar_txt}) "
                f"wordt eerst benut; alleen het gat wordt van het net "
                f"gekocht."
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
        self._update_battery_cost_basis_and_savings(now, entries)

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
        self.last_heavy_load_source = self._get_confirmed_heavy_load_source(now)
        self._track_recent_consumption_reading(now)

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
            available_kwh=projection_available_kwh,
            reserve_kwh=projection_reserve_kwh,
        )
        self.last_transitions = self._collapse_timeline(self.last_timeline)

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

        arbitrage_power = self._get_arbitrage_charge_power(entries, now)
        if arbitrage_power is not None:
            await self._async_apply_manual(-arbitrage_power)
            self.last_reason = "arbitrage_charging"
            # Deliberately does NOT set _grid_charged_today: the winter
            # guard exists to stop selling energy bought out of
            # necessity at a loss - this purchase is the opposite, made
            # *because* a known, more profitable sale is coming later
            # today. Suppressing that sale would defeat the entire
            # point of buying now.
            self.last_charge_power_applied = -arbitrage_power
            self._update_financial_tracking(
                now, entries, self.last_reason, None, -arbitrage_power
            )
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
