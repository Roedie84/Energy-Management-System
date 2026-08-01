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
from datetime import date, datetime, timedelta

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
    CHEAP_BLOCK_THRESHOLD_MARGIN_FRACTION,
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_EXPENSIVE_QUARTERS_COUNT,
    CONF_INVERT_BATTERY_POWER_SIGN,
    CONF_LOW_SOLAR_THRESHOLD_KWH,
    CONF_MANUAL_CHARGE_POWER,
    CONF_NEGATIVE_PRICE_CHARGE_POWER,
    CONF_SOLAR_POWER_LIMIT_ENTITY,
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
    DEFAULT_NEGATIVE_PRICE_CHARGE_POWER,
    SOLAR_RAMP_DURATION_SECONDS,
    SOLAR_RAMP_STEPS,
    GRID_IMPORT_SHORTFALL_THRESHOLD_W,
    SHORTFALL_MARGIN_BONUS_PER_RECENT_DAY,
    EMERGENCY_LOW_BATTERY_KWH_THRESHOLD,
    RESERVE_EXCESS_RATIO_THRESHOLD,
    EXCESS_MARGIN_REDUCTION_PER_RECENT_DAY,
    MIN_TOTAL_MARGIN_BONUS_PERCENT,
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
        # If True: compute and learn everything as normal, but never send
        # commands to the Zendure entities. Set via a dedicated switch.
        self.learning_only: bool = False

        self.last_reason: str | None = None
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
        self.last_charge_power_applied: float | None = None

        # -- Winter guard: don't manual-discharge after grid-charging today --
        # If the battery was force-charged from the grid today (low solar),
        # don't also manual-discharge at high prices that same day - that
        # energy was bought to cover the household, not to arbitrage.
        self._grid_charged_today: bool = False
        self._grid_charged_date: date | None = None

        # -- Negative price handling --
        self._is_negative_price_active: bool = False
        self._solar_ramp_task = None

        # -- Reserve shortfall detection & learning --
        # If net grid import happens during a period we believe should be
        # self-sufficient (smart_discharging / expensive quarter), the
        # reserve estimate for that day was too optimistic. Track this per
        # day, and learn a margin bonus if it keeps happening.
        self.reserve_shortfall_history: list[bool] = []
        self._shortfall_detected_today: bool = False
        self._shortfall_check_date: date | None = None
        self.reserve_excess_history: list[bool] = []
        self._excess_detected_today: bool = False
        self._last_value_calc_time: datetime | None = None

        self._lock = asyncio.Lock()
        self._unsub_interval = None
        self._unsub_state = None

    @property
    def tracked_entities(self) -> list[str]:
        return [self.config[CONF_PRICE_SENSOR]]

    async def async_setup(self) -> None:
        """Start listening for updates and run once immediately."""
        await self.async_bootstrap_night_consumption_from_history()
        self._unsub_interval = async_track_time_interval(
            self.hass,
            self._handle_interval,
            timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )
        self._unsub_state = async_track_state_change_event(
            self.hass, self.tracked_entities, self._handle_state_change
        )
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

    async def async_set_learning_only(self, value: bool) -> None:
        self.learning_only = value
        await self.async_update()

    @property
    def learned_night_consumption_kw(self) -> float | None:
        """Rolling average power (kW) measured during past discharging windows."""
        if not self.night_consumption_history:
            return None
        return sum(self.night_consumption_history) / len(
            self.night_consumption_history
        )

    # -- Forecast parsing -------------------------------------------------

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

            start = dt_util.parse_datetime(start_raw)
            end = dt_util.parse_datetime(end_raw)
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
        self, day_entries: list[PriceEntry], narrow_for_low_solar: bool = False
    ) -> float | None:
        """Dynamic "expensive" threshold for an arbitrary set of same-day
        price entries (top fraction of that day's price range). Shared by
        today's live decision and the multi-day timeline projection.
        """
        if not day_entries:
            return None
        prices = [entry[2] for entry in day_entries]
        min_price, max_price = min(prices), max(prices)
        price_range = max_price - min_price
        if price_range <= 0:
            return None
        fraction = (
            EXPENSIVE_PRICE_THRESHOLD_FRACTION_LOW_SOLAR
            if narrow_for_low_solar
            else EXPENSIVE_PRICE_THRESHOLD_FRACTION
        )
        return max_price - fraction * price_range

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
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (None, "unknown", "unavailable"):
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

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
        """Learned average power (kW) for a given hour-of-day (0-23)."""
        values = self.hourly_consumption_profile.get(hour)
        if not values:
            return None
        return sum(values) / len(values)

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

        current_hour_learned_kw = self.learned_hourly_avg_kw(start.hour)
        if current_hour_learned_kw and current_hour_learned_kw > 0:
            live_power_w = self._read_corrected_consumption_power()
            if live_power_w is not None and live_power_w > 0:
                live_kw = live_power_w / 1000
                if live_kw > current_hour_learned_kw:
                    correction_ratio = live_kw / current_hour_learned_kw
                    _LOGGER.debug(
                        "Live consumption (%.0fW) is %.1fx the learned "
                        "average for this hour (%.0fW) - scaling up the "
                        "remaining consumption estimate accordingly",
                        live_power_w,
                        correction_ratio,
                        current_hour_learned_kw * 1000,
                    )
                    total_kwh *= correction_ratio

        return total_kwh

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
        """Learned (actual/forecast) ratio for a given hour-of-day (0-23).
        1.0 = forecast matches reality, <1.0 = Solcast over-forecasts that
        hour, >1.0 = Solcast under-forecasts it. None if not enough data yet.
        """
        values = self.pv_hourly_bias_history.get(hour)
        if not values or len(values) < MIN_SOLAR_HISTORY_FOR_DYNAMIC_THRESHOLD:
            return None
        return sum(values) / len(values)

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

        needed_kwh = self._estimate_consumption_kwh_for_period(now, cheap_block_start)
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

        expected_pv_kwh = self._estimate_pv_kwh_for_period(now, cheap_block_start)
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

        margin_bonus_percent = max(
            MIN_TOTAL_MARGIN_BONUS_PERCENT,
            low_solar_bonus_percent + shortfall_bonus_percent - excess_reduction_percent,
        )
        margin = DYNAMIC_DISCHARGE_RESERVE_MARGIN + margin_bonus_percent / 100

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
                self.reserve_excess_history.append(self._excess_detected_today)
                self.reserve_excess_history = self.reserve_excess_history[
                    -LEARNING_HISTORY_DAYS:
                ]
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

    def _get_soc_scaled_discharge_power(
        self,
        base_power: float,
        now: datetime | None = None,
        cheap_block_start: datetime | None = None,
    ) -> float | None:
        """Scale down the forced-discharge power to avoid over-draining
        the battery just to sell into an expensive quarter.

        Prefers a dynamic, energy-based reserve ("keep what I actually
        need for tonight + margin", see `_get_dynamic_discharge_reserve_kwh`)
        when an available-energy sensor and cheap-block context are
        present. Falls back to a flat SoC-percentage taper otherwise.

        Returns the (possibly reduced) power, or None if there isn't
        enough headroom to discharge at all - in which case forced
        discharge should be skipped entirely (protect the battery, fall
        back to smart mode).
        """
        available_entity = self.config.get(CONF_AVAILABLE_ENERGY_SENSOR)
        if available_entity and now is not None:
            available_kwh = self._read_sensor_float(available_entity)
            reserve_kwh = self._get_dynamic_discharge_reserve_kwh(
                now, cheap_block_start
            )
            if available_kwh is not None and reserve_kwh is not None:
                headroom_kwh = max(0.0, available_kwh - reserve_kwh)
                interval_hours = UPDATE_INTERVAL_MINUTES / 60
                max_power_w = (headroom_kwh / interval_hours) * 1000 if interval_hours > 0 else 0

                soc_entity = self.config.get(CONF_SOC_SENSOR)
                if soc_entity:
                    self.last_soc_percent = self._read_sensor_float(soc_entity)

                if max_power_w <= 0:
                    self.last_discharge_power_applied = None
                    _LOGGER.debug(
                        "Dynamic discharge reserve: available=%.2f kWh, "
                        "needed reserve=%.2f kWh - no headroom, skipping "
                        "forced discharge this tick",
                        available_kwh,
                        reserve_kwh,
                    )
                    return None

                scaled = round(min(base_power, max_power_w), 1)
                self.last_discharge_power_applied = scaled
                if scaled < base_power:
                    _LOGGER.debug(
                        "Dynamic discharge reserve: available=%.2f kWh, "
                        "needed reserve=%.2f kWh - scaling discharge from "
                        "%.0fW to %.0fW to protect the reserve",
                        available_kwh,
                        reserve_kwh,
                        base_power,
                        scaled,
                    )
                return scaled

        # Fallback: flat SoC-percentage taper (no available-energy sensor,
        # or the dynamic reserve couldn't be computed this tick).
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
        self, entries: list[PriceEntry], now: datetime
    ) -> datetime | None:
        """Start the discharging window right when today's expensive
        quarters end, instead of at a fixed clock hour.

        Uses the end of the last (chronologically latest) of today's
        quarters that clear the dynamic "expensive" threshold. Returns
        None if none are found for today (e.g. all prices are equal, or
        no data).
        """
        todays_entries = [entry for entry in entries if entry[0].date() == now.date()]
        if not todays_entries:
            return None

        threshold = self._get_expensive_price_threshold(entries, now)
        if threshold is None:
            return None

        expensive_entries = [e for e in todays_entries if e[2] >= threshold]
        if not expensive_entries:
            return None

        return max(entry[1] for entry in expensive_entries)

    def _log_energy_transition(
        self, now: datetime, has_enough: bool, available_kwh: float, needed_kwh: float
    ) -> None:
        """Record a log entry whenever the energy-bridge decision flips,
        so you can review afterwards exactly when and why it switched -
        without needing to watch it live.
        """
        if self.last_has_enough_energy is None or self.last_has_enough_energy == has_enough:
            return

        self.energy_bridge_transition_log.append(
            {
                "at": now.isoformat(),
                "decision": "enough_to_postpone" if has_enough else "top_up_needed",
                "available_kwh": round(available_kwh, 2),
                "needed_kwh": round(needed_kwh, 2),
            }
        )
        # Keep a bounded amount of history (roughly the last ~10 days
        # worth of transitions, assuming a handful of flips per day).
        self.energy_bridge_transition_log = self.energy_bridge_transition_log[-50:]

    def _estimate_upcoming_discharge_kwh(
        self,
        entries: list[PriceEntry],
        now: datetime,
        cheap_block_start: datetime,
    ) -> float:
        """Energy (kWh) that will be actively discharged during today's
        remaining quarters that clear the dynamic "expensive" threshold,
        before the cheap block starts, at the configured (uncapped)
        discharge power.

        This is added on top of the baseline consumption estimate in the
        energy bridge check, so the battery reserves enough to execute
        those profitable discharges at full power - instead of only
        reserving enough for household consumption and then having the
        dynamic reserve check taper the discharge when the expensive
        quarter actually arrives.
        """
        todays_entries = [e for e in entries if e[0].date() == now.date()]
        if not todays_entries:
            return 0.0

        threshold = self._get_expensive_price_threshold(entries, now)
        if threshold is None:
            return 0.0

        upcoming_expensive = [
            e
            for e in todays_entries
            if e[2] >= threshold and now <= e[0] < cheap_block_start
        ]
        if not upcoming_expensive:
            return 0.0

        discharge_power_w = self.config.get(
            CONF_MANUAL_DISCHARGE_POWER, DEFAULT_MANUAL_DISCHARGE_POWER
        )
        total_hours = sum(
            (end - start).total_seconds() / 3600 for start, end, _ in upcoming_expensive
        )
        return (discharge_power_w / 1000) * total_hours

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

        if available_kwh is not None:
            hours_until_cheap = max(
                (cheap_block_start - now).total_seconds() / 3600, 0
            )

            # Prefer the learned hourly profile (accounts for the actual
            # time-of-day mix of the bridging period), falling back to the
            # flat night-average or a live reading if incomplete.
            needed_kwh_raw = self._estimate_consumption_kwh_for_period(
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

            # Subtract expected PV production during the bridging window -
            # solar coming online soon reduces how much the battery/grid
            # actually needs to cover.
            baseline_consumption_kwh = needed_kwh_raw
            if needed_kwh_raw is not None:
                expected_pv_kwh = self._estimate_pv_kwh_for_period(
                    now, cheap_block_start
                )
                needed_kwh_raw = max(0.0, needed_kwh_raw - expected_pv_kwh)

                # Also reserve enough to execute today's remaining
                # expensive-quarter discharges at full power - otherwise
                # the battery might look "sufficient" for household use
                # but come up short (SoC-protection tapering the payout)
                # when the actual price peak arrives later today.
                upcoming_discharge_kwh = self._estimate_upcoming_discharge_kwh(
                    entries, now, cheap_block_start
                )
                needed_kwh_raw += upcoming_discharge_kwh

                needed_kwh = needed_kwh_raw * ENERGY_BRIDGE_SAFETY_MARGIN

                self.last_needed_kwh_breakdown = {
                    "basisverbruik_kwh": round(baseline_consumption_kwh, 3),
                    "verwachte_pv_kwh": round(expected_pv_kwh, 3),
                    "reservering_dure_kwartieren_kwh": round(upcoming_discharge_kwh, 3),
                    "veiligheidsmarge_procent": round(
                        (ENERGY_BRIDGE_SAFETY_MARGIN - 1) * 100, 1
                    ),
                }
            else:
                needed_kwh = None
                self.last_needed_kwh_breakdown = {}

            if needed_kwh is not None:
                has_enough = available_kwh >= needed_kwh

                self._log_energy_transition(now, has_enough, available_kwh, needed_kwh)

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
        simulated_available = available_kwh

        timeline: list[dict] = []
        for entry in entries:
            if entry[1] <= now:
                continue

            entry_date = entry[0].date()
            day_entries = by_date[entry_date]
            threshold = self._price_threshold_for_entries(day_entries)
            is_expensive = threshold is not None and entry[2] >= threshold

            is_current_interval = entry[0] <= now < entry[1]

            # Cap price-qualifying "expensive" quarters by the simulated
            # running balance, so a long stretch of nominally-expensive
            # quarters doesn't get shown as an unbounded full-power
            # discharge once there's no realistic energy left for it.
            if (
                is_expensive
                and not is_current_interval
                and simulated_available is not None
                and reserve_kwh is not None
            ):
                if simulated_available <= reserve_kwh:
                    is_expensive = False
                else:
                    duration_hours = (entry[1] - entry[0]).total_seconds() / 3600
                    simulated_available -= (discharge_power_w / 1000) * duration_hours

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
            self.total_discharge_value_eur += energy_kwh * current_price
        elif (
            reason in ("grid_charging_low_solar", "emergency_low_battery")
            and charge_power_w
        ):
            energy_kwh = (abs(charge_power_w) / 1000) * elapsed_hours
            self.total_charge_cost_eur += energy_kwh * current_price

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
        """Recompute the desired mode and apply it if needed."""
        async with self._lock:
            await self._async_update_locked()

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
            parts.append(
                f"Dit kwartier hoort bij de {self.last_effective_expensive_quarters_count} "
                f"duurste van vandaag, dus de accu ontlaadt nu actief op "
                f"{power_txt} om van de hoge prijs te profiteren."
            )
            if self.last_soc_percent is not None:
                parts.append(f"Huidige accu-SoC: {self.last_soc_percent:.0f}%.")

        elif reason == "expensive_quarter_soc_protected":
            soc_txt = (
                f"{self.last_soc_percent:.0f}%"
                if self.last_soc_percent is not None
                else "onbekend"
            )
            parts.append(
                f"Dit zou een duur kwartier zijn om te ontladen, maar de "
                f"accu-SoC ({soc_txt}) is te laag om dat te rechtvaardigen. "
                f"Daarom blijft de Zendure op 'smart' staan in plaats van "
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
                    f"{needed_txt} kWh). Daarom wordt laden uitgesteld en "
                    f"krijgt teruglevering nu voorrang (smart_discharging)."
                )
                b = self.last_needed_kwh_breakdown
                if b:
                    parts.append(
                        f"Opsplitsing van die {needed_txt} kWh: "
                        f"{b.get('basisverbruik_kwh', '?')} kWh basisverbruik, "
                        f"minus {b.get('verwachte_pv_kwh', '?')} kWh verwachte zon, "
                        f"plus {b.get('reservering_dure_kwartieren_kwh', '?')} kWh "
                        f"reservering voor nog-komende dure kwartieren vandaag, "
                        f"met {b.get('veiligheidsmarge_procent', '?')}% "
                        f"veiligheidsmarge erover."
                    )
            else:
                parts.append(
                    "Het is nog vóór het goedkoopste blok, dus laden wordt "
                    "uitgesteld en teruglevering krijgt voorrang "
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
                b = self.last_needed_kwh_breakdown
                if b:
                    parts.append(
                        f"Opsplitsing: {b.get('basisverbruik_kwh', '?')} kWh "
                        f"basisverbruik, minus {b.get('verwachte_pv_kwh', '?')} "
                        f"kWh verwachte zon, plus "
                        f"{b.get('reservering_dure_kwartieren_kwh', '?')} kWh "
                        f"reservering voor dure kwartieren."
                    )
            else:
                parts.append(
                    "Er is nu geen speciale reden om in te grijpen: de prijs "
                    "is niet bijzonder hoog, en het goedkoopste blok is al "
                    "gaande of voorbij. De Zendure regelt dit zelf "
                    "(smart-modus)."
                )

        else:
            parts.append(f"Onbekende reden: {reason}.")

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

        # Always compute the time-based discharge_start for the timeline
        # projection (it can't know about live battery energy for future
        # intervals), even though the live decision below may use the
        # energy-based check instead.
        self.last_discharge_start = self._compute_dynamic_discharge_start(
            entries, now
        )

        # Should we postpone charging (smart_discharging) ahead of the
        # cheapest block? Prefers an energy-based check (is there already
        # enough available battery energy to bridge the remaining time?),
        # falling back to the time-based rule if no energy sensor is set.
        should_postpone_charging = self._should_postpone_charging(
            entries, now, cheap_block_start
        )

        # Never postpone charging while the sun is actually producing right
        # now - that solar is free and perishable (this exact moment's
        # output is lost/exported at a mediocre value if not captured now),
        # unlike grid charging which can genuinely wait for a cheaper
        # moment. Let "smart" (the Zendure's own logic) capture it instead.
        pv_entity = self.config.get(CONF_PV_POWER_SENSOR)
        if pv_entity and should_postpone_charging:
            current_pv_power_w = self._read_sensor_float(pv_entity)
            if (
                current_pv_power_w is not None
                and current_pv_power_w > MIN_ACTIVE_SOLAR_PRODUCTION_W
            ):
                _LOGGER.debug(
                    "Overriding smart_discharging: %.0fW of solar is "
                    "currently being produced - letting smart mode capture "
                    "it instead of postponing charging",
                    current_pv_power_w,
                )
                should_postpone_charging = False

        self._update_night_consumption_tracking(now, should_postpone_charging)
        self._update_hourly_consumption_profile(now)
        self._update_pv_hourly_bias_tracking(now)

        self.last_is_expensive = is_expensive
        self.last_effective_expensive_quarters_count = effective_count
        projection_reserve_kwh = self._get_dynamic_discharge_reserve_kwh(
            now, cheap_block_start
        )
        self.last_timeline = self._build_forecast_timeline(
            entries,
            now,
            cheap_block_start,
            self.last_discharge_start,
            live_is_expensive=is_expensive,
            live_should_postpone_charging=should_postpone_charging,
            available_kwh=self.last_available_kwh,
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
            self.last_explanation = self._build_explanation()
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

        if is_expensive and self._grid_charged_today:
            _LOGGER.debug(
                "Suppressing expensive_quarter discharge: the battery was "
                "already grid-charged today (low solar) - selling that "
                "same energy back would just be a loss, not arbitrage."
            )
            is_expensive = False

        if is_expensive:
            discharge_power = self.config.get(
                CONF_MANUAL_DISCHARGE_POWER, DEFAULT_MANUAL_DISCHARGE_POWER
            )
            scaled_power = self._get_soc_scaled_discharge_power(
                discharge_power, now, cheap_block_start
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
                self.last_explanation = self._build_explanation()
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
            self.last_explanation = self._build_explanation()
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
            self.last_explanation = self._build_explanation()
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
            self.last_explanation = self._build_explanation()
            return

        if should_postpone_charging:
            await self._async_apply_operation(OPTION_SMART_DISCHARGING)
            self.last_reason = "discharging_window"
            self._update_financial_tracking(now, entries, self.last_reason, None, None)
            self._update_shortfall_detection(now, self.last_reason, self.last_available_kwh, self.last_needed_kwh_to_bridge)
            self.last_explanation = self._build_explanation()
            return

        await self._async_apply_operation(OPTION_SMART)
        self.last_reason = "default_smart"
        self._update_financial_tracking(now, entries, self.last_reason, None, None)
        self._update_shortfall_detection(now, self.last_reason, self.last_available_kwh, self.last_needed_kwh_to_bridge)
        self.last_explanation = self._build_explanation()

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
