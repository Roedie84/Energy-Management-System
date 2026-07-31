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
from datetime import datetime, timedelta

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
    CHEAP_BLOCK_THRESHOLD_MARGIN_FRACTION,
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_EXPENSIVE_QUARTERS_COUNT,
    CONF_LOW_SOLAR_THRESHOLD_KWH,
    CONF_MANUAL_CHARGE_POWER,
    CONF_MANUAL_DISCHARGE_POWER,
    CONF_MANUAL_POWER_NUMBER,
    CONF_MIN_SOC_PERCENT,
    CONF_OPERATION_SELECT,
    CONF_PRICE_ATTRIBUTE,
    CONF_PRICE_SENSOR,
    CONF_SOC_SENSOR,
    CONF_SOLAR_FORECAST_SENSOR,
    DEFAULT_EXPENSIVE_QUARTERS_COUNT,
    DEFAULT_LOW_SOLAR_THRESHOLD_KWH,
    DEFAULT_MANUAL_CHARGE_POWER,
    DEFAULT_MANUAL_DISCHARGE_POWER,
    DEFAULT_MIN_SOC_PERCENT,
    DEFAULT_PRICE_ATTRIBUTE,
    ENERGY_BRIDGE_SAFETY_MARGIN,
    LEARNING_HISTORY_DAYS,
    LOW_SOLAR_RELATIVE_FRACTION,
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
        self.last_has_enough_energy: bool | None = None
        self.energy_bridge_transition_log: list[dict] = []
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
        as a stand-in "night" period. Never overwrites already-learned
        (live) data, and never raises - any failure just means normal
        day-by-day learning takes over from here.
        """
        if self.night_consumption_history:
            return

        consumption_entity = self.config.get(CONF_CONSUMPTION_POWER_SENSOR)
        if not consumption_entity:
            return

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

        def _fetch():
            return history.get_significant_states(
                self.hass, start, now, [consumption_entity]
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

        states = states_by_entity.get(consumption_entity, [])
        if not states:
            _LOGGER.debug(
                "No historical states found for %s to bootstrap from",
                consumption_entity,
            )
            return

        by_day: dict[object, list[float]] = {}
        for state in states:
            try:
                value = float(state.state)
            except (TypeError, ValueError):
                continue
            try:
                local_dt = dt_util.as_local(state.last_changed)
            except (TypeError, ValueError):
                continue
            if 1 <= local_dt.hour < 8:
                by_day.setdefault(local_dt.date(), []).append(value)

        daily_averages: list[float] = []
        for day in sorted(by_day.keys()):
            values = by_day[day]
            if values:
                daily_averages.append(sum(values) / len(values) / 1000)

        if daily_averages:
            self.night_consumption_history = daily_averages[-LEARNING_HISTORY_DAYS:]
            self.was_bootstrapped_from_history = True
            _LOGGER.info(
                "Bootstrapped night consumption learning from history: %s "
                "kW (approximate 01:00-08:00 window over the last %d days)",
                [round(v, 3) for v in self.night_consumption_history],
                len(daily_averages),
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

    def _is_expensive_now(
        self, entries: list[PriceEntry], now: datetime, count: int | None = None
    ) -> bool:
        """Is 'now' one of the most expensive intervals of today?"""
        todays_entries = [entry for entry in entries if entry[0].date() == now.date()]
        if not todays_entries:
            return False

        current_entry = next(
            (entry for entry in todays_entries if entry[0] <= now < entry[1]),
            None,
        )
        if current_entry is None:
            return False

        if count is None:
            count = int(
                self.config.get(
                    CONF_EXPENSIVE_QUARTERS_COUNT, DEFAULT_EXPENSIVE_QUARTERS_COUNT
                )
            )
        count = max(1, count)
        most_expensive = sorted(todays_entries, key=lambda e: e[2], reverse=True)[
            :count
        ]
        return any(entry[0] == current_entry[0] for entry in most_expensive)

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

    # -- Night consumption learning ---------------------------------------

    def _update_night_consumption_tracking(
        self, now: datetime, in_window: bool
    ) -> None:
        """Sample the consumption sensor while inside the discharging window,
        and finalize + learn from the window once it ends.
        """
        consumption_entity = self.config.get(CONF_CONSUMPTION_POWER_SENSOR)

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
            power_w = self._read_sensor_float(consumption_entity)
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

    def _get_soc_scaled_discharge_power(self, base_power: float) -> float | None:
        """Scale down the forced-discharge power as SoC gets low, to avoid
        over-draining the battery just to sell into an expensive quarter.

        Returns the (possibly reduced) power, or None if SoC is at/below
        the configured minimum - in which case forced discharge should be
        skipped entirely (protect the battery, fall back to smart mode).
        """
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
            "SoC protection: %.1f%% is between min (%.1f%%) and full power "
            "(%.1f%%) - scaling discharge from %.0fW to %.0fW",
            soc,
            min_soc,
            taper_start,
            base_power,
            scaled,
        )
        return scaled

    def _is_low_solar_expected(self) -> bool:
        """Is little solar yield expected (tomorrow / today), based on the
        Solcast forecast sensor - bias-corrected and compared against a
        learned dynamic threshold when enough history exists, falling
        back to the fixed configured threshold otherwise.

        Returns False if no forecast sensor is configured or its state
        can't be read (i.e. "assume normal/sufficient solar" by default).
        """
        forecast_entity = self.config.get(CONF_SOLAR_FORECAST_SENSOR)
        if not forecast_entity:
            return False

        forecast_kwh_raw = self._read_sensor_float(forecast_entity)
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

    def _effective_expensive_quarters_count(
        self, now: datetime, cheap_block_start: datetime | None
    ) -> int:
        """Reduce the expensive-quarters count when little solar is expected
        tomorrow, based on how much energy is needed to bridge the time
        until the battery starts charging again (the cheapest block).

        Uses the learned rolling-average night consumption when available
        (falling back to a live sensor reading otherwise), and corrects the
        raw solar forecast with the learned Solcast bias for this
        installation, when known.
        """
        normal_count = max(
            1,
            int(
                self.config.get(
                    CONF_EXPENSIVE_QUARTERS_COUNT, DEFAULT_EXPENSIVE_QUARTERS_COUNT
                )
            ),
        )

        forecast_entity = self.config.get(CONF_SOLAR_FORECAST_SENSOR)
        consumption_entity = self.config.get(CONF_CONSUMPTION_POWER_SENSOR)
        if not forecast_entity or not consumption_entity or cheap_block_start is None:
            return normal_count

        if not self._is_low_solar_expected():
            return normal_count

        learned_kw = self.learned_night_consumption_kw
        if learned_kw is not None:
            power_kw = learned_kw
        else:
            power_w = self._read_sensor_float(consumption_entity)
            if power_w is None or power_w <= 0:
                return normal_count
            power_kw = power_w / 1000

        hours_until_solar = max((cheap_block_start - now).total_seconds() / 3600, 0)
        if hours_until_solar <= 0:
            return normal_count

        discharge_power_w = self.config.get(
            CONF_MANUAL_DISCHARGE_POWER, DEFAULT_MANUAL_DISCHARGE_POWER
        )
        quarter_energy_kwh = (discharge_power_w / 1000) * 0.25
        if quarter_energy_kwh <= 0:
            return normal_count

        expected_consumption_kwh = power_kw * hours_until_solar
        needed_quarters = max(
            1, math.ceil(expected_consumption_kwh / quarter_energy_kwh)
        )

        reduced_count = min(needed_quarters, normal_count)
        _LOGGER.debug(
            "Low solar forecast detected: reducing expensive quarters "
            "from %d to %d (expected consumption %.2f kWh over %.1fh at "
            "%.0fW, %s)",
            normal_count,
            reduced_count,
            expected_consumption_kwh,
            hours_until_solar,
            power_kw * 1000,
            "learned average" if learned_kw is not None else "live reading",
        )
        return reduced_count

    def _normal_expensive_quarters_count(self) -> int:
        return max(
            1,
            int(
                self.config.get(
                    CONF_EXPENSIVE_QUARTERS_COUNT, DEFAULT_EXPENSIVE_QUARTERS_COUNT
                )
            ),
        )

    def _compute_dynamic_discharge_start(
        self, entries: list[PriceEntry], now: datetime, effective_count: int
    ) -> datetime | None:
        """Start the discharging window right when today's expensive
        quarters end, instead of at a fixed clock hour.

        Uses the end of the last (chronologically latest) of today's
        expensive quarters. Returns None if no expensive quarters are
        found for today (e.g. all prices are equal, or no data).
        """
        todays_entries = [entry for entry in entries if entry[0].date() == now.date()]
        if not todays_entries:
            return None

        most_expensive = sorted(todays_entries, key=lambda e: e[2], reverse=True)[
            :effective_count
        ]
        if not most_expensive:
            return None

        return max(entry[1] for entry in most_expensive)

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

    def _should_postpone_charging(
        self,
        entries: list[PriceEntry],
        now: datetime,
        cheap_block_start: datetime | None,
        effective_count: int,
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
            learned_kw = self.learned_night_consumption_kw
            if learned_kw is not None:
                power_kw = learned_kw
            else:
                power_w = self._read_sensor_float(
                    self.config.get(CONF_CONSUMPTION_POWER_SENSOR)
                )
                power_kw = power_w / 1000 if power_w is not None else None

            if power_kw is not None:
                needed_kwh = power_kw * hours_until_cheap * ENERGY_BRIDGE_SAFETY_MARGIN
                has_enough = available_kwh >= needed_kwh

                self._log_energy_transition(now, has_enough, available_kwh, needed_kwh)

                self.last_available_kwh = available_kwh
                self.last_needed_kwh_to_bridge = needed_kwh
                self.last_has_enough_energy = has_enough

                _LOGGER.debug(
                    "Energy bridge check: available=%.2f kWh, needed=%.2f "
                    "kWh (over %.1fh at %.0fW + %.0f%% margin) -> %s",
                    available_kwh,
                    needed_kwh,
                    hours_until_cheap,
                    power_kw * 1000,
                    (ENERGY_BRIDGE_SAFETY_MARGIN - 1) * 100,
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
        effective_count: int,
    ) -> list[dict]:
        """Project the current logic forward over all known forecast data.

        This is an approximation: the real coordinator recomputes the
        cheapest block and discharge window fresh on every run, so this
        projection only reflects the currently known cheapest block/window
        for "today". Beyond that window, only each day's own expensive
        quarters are still marked; everything else defaults to 'smart'.
        The effective (possibly solar-reduced) count is only applied to
        today's date, matching the live decision logic.
        """
        today = now.date()
        by_date: dict = {}
        for entry in entries:
            if entry[1] <= now:
                continue
            by_date.setdefault(entry[0].date(), []).append(entry)

        timeline: list[dict] = []
        for entry in entries:
            if entry[1] <= now:
                continue

            entry_date = entry[0].date()
            day_entries = by_date[entry_date]
            count = (
                effective_count
                if entry_date == today
                else self._normal_expensive_quarters_count()
            )
            most_expensive = sorted(day_entries, key=lambda e: e[2], reverse=True)[
                :count
            ]
            is_expensive = any(e[0] == entry[0] for e in most_expensive)

            if is_expensive:
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
            return

        cheap_block_start, cheap_block_end = self._cheapest_block_range(entries, now)
        self.last_cheap_block_start = cheap_block_start
        self.last_cheap_block_end = cheap_block_end

        effective_count = self._effective_expensive_quarters_count(
            now, cheap_block_start
        )
        is_expensive = self._is_expensive_now(entries, now, count=effective_count)

        # Always compute the time-based discharge_start for the timeline
        # projection (it can't know about live battery energy for future
        # intervals), even though the live decision below may use the
        # energy-based check instead.
        self.last_discharge_start = self._compute_dynamic_discharge_start(
            entries, now, effective_count
        )

        # Should we postpone charging (smart_discharging) ahead of the
        # cheapest block? Prefers an energy-based check (is there already
        # enough available battery energy to bridge the remaining time?),
        # falling back to the time-based rule if no energy sensor is set.
        should_postpone_charging = self._should_postpone_charging(
            entries, now, cheap_block_start, effective_count
        )
        self._update_night_consumption_tracking(now, should_postpone_charging)

        self.last_is_expensive = is_expensive
        self.last_effective_expensive_quarters_count = effective_count
        self.last_timeline = self._build_forecast_timeline(
            entries, now, cheap_block_start, self.last_discharge_start, effective_count
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
            return

        if is_expensive:
            discharge_power = self.config.get(
                CONF_MANUAL_DISCHARGE_POWER, DEFAULT_MANUAL_DISCHARGE_POWER
            )
            scaled_power = self._get_soc_scaled_discharge_power(discharge_power)
            if scaled_power is None:
                # SoC too low to justify forced export - protect the
                # battery and let the Zendure's own smart mode take over.
                await self._async_apply_operation(OPTION_SMART)
                self.last_reason = "expensive_quarter_soc_protected"
            else:
                await self._async_apply_manual(scaled_power)
                self.last_reason = "expensive_quarter"
            return

        if should_force_charge:
            charge_power = self.config.get(
                CONF_MANUAL_CHARGE_POWER, DEFAULT_MANUAL_CHARGE_POWER
            )
            await self._async_apply_manual(charge_power)
            self.last_reason = "grid_charging_low_solar"
            return

        if should_postpone_charging:
            await self._async_apply_operation(OPTION_SMART_DISCHARGING)
            self.last_reason = "discharging_window"
            return

        await self._async_apply_operation(OPTION_SMART)
        self.last_reason = "default_smart"

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
