"""Tracks the accuracy of the Solcast PV forecast against actual solar yield.

Two separate moments each day:
1. Around 20:00 (well before midnight), captures the current Solcast
   "forecast for tomorrow" value, to be compared 24 hours later. This is
   deliberately NOT done at midnight itself, since some Solcast/forecast
   sensors "roll over" right around midnight (today's forecast becomes
   the new "today", a fresh "tomorrow" forecast starts from a
   near-empty/transitional value) - capturing at 20:00 avoids catching
   that transition and grabbing an unstable or near-zero value.
2. Just before midnight (23:59:50), compares the forecast captured the
   previous evening against the actual measured yield of today (about to
   reset at midnight), and stores the resulting deviation.

This is purely diagnostic: it does not influence charge/discharge
decisions, it only exposes a sensor entity.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import (
    CONF_SOLAR_ACTUAL_SENSOR,
    CONF_SOLAR_FORECAST_SENSOR,
    LEARNING_HISTORY_DAYS,
    MIN_SOLAR_HISTORY_FOR_DYNAMIC_THRESHOLD,
)

_LOGGER = logging.getLogger(__name__)

# Compare just before midnight, so the "actual" sensor is read right
# before it resets for the new day.
COMPARE_HOUR = 23
COMPARE_MINUTE = 59
COMPARE_SECOND = 50

# Capture "tomorrow's forecast" well before midnight, to avoid the
# forecast sensor's own day-rollover/reset moment.
FORECAST_CAPTURE_HOUR = 20
FORECAST_CAPTURE_MINUTE = 0
FORECAST_CAPTURE_SECOND = 0

# A deviation this large almost certainly means the forecast was captured
# during a sensor's day-rollover/reset transition (or some other glitch),
# not a genuine forecast miss - even a very bad Solcast day wouldn't
# reasonably be off by more than this. Treated as an invalid outlier.
MAX_REASONABLE_DEVIATION_PERCENT = 200.0


def _read_float(hass: HomeAssistant, entity_id: str | None) -> float | None:
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in (None, "unknown", "unavailable"):
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


class SolarForecastAccuracyTracker:
    """Compares yesterday's Solcast forecast to today's realized PV yield."""

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        self.hass = hass
        self.config = config

        # The forecast captured on the previous day, predicting the date below.
        self.pending_predicted_kwh: float | None = None
        self.pending_predicted_date: date | None = None

        # Result of the most recent comparison.
        self.last_predicted_kwh: float | None = None
        self.last_actual_kwh: float | None = None
        self.last_deviation_percent: float | None = None
        self.last_compared_date: date | None = None

        # Rolling history of deviation percentages, used to learn a
        # systematic bias in the Solcast forecast for this installation.
        self.deviation_history: list[float] = []

        # Rolling history of the raw forecast values themselves, used to
        # learn a "typical" forecast for this installation (and from that,
        # a dynamic "low solar" threshold).
        self.forecast_value_history: list[float] = []

        # Whether history was recovered from the recorder on startup
        # (informational only, shown as a diagnostic attribute).
        self.was_bootstrapped_from_history: bool = False

        self._unsub_compare = None
        self._unsub_capture = None
        self._listeners: list = []

    def register_listener(self, callback_fn) -> None:
        """Register a callback to notify (e.g. entity.async_write_ha_state)."""
        self._listeners.append(callback_fn)

    def unregister_listener(self, callback_fn) -> None:
        if callback_fn in self._listeners:
            self._listeners.remove(callback_fn)

    def _notify_listeners(self) -> None:
        for listener in self._listeners:
            listener()

    @property
    def enabled(self) -> bool:
        return bool(
            self.config.get(CONF_SOLAR_FORECAST_SENSOR)
            and self.config.get(CONF_SOLAR_ACTUAL_SENSOR)
        )

    @property
    def learned_bias_percent(self) -> float | None:
        """Rolling average deviation (%) over the last LEARNING_HISTORY_DAYS,
        ignoring implausible outliers (see MAX_REASONABLE_DEVIATION_PERCENT).

        A positive value means Solcast has been under-forecasting for this
        installation (actual yield higher than predicted); negative means
        it has been over-forecasting.
        """
        valid = [
            v
            for v in self.deviation_history
            if abs(v) <= MAX_REASONABLE_DEVIATION_PERCENT
        ]
        if not valid:
            return None
        return round(sum(valid) / len(valid), 1)

    @property
    def learned_typical_forecast_kwh(self) -> float | None:
        """Rolling average raw forecast (kWh) over the last LEARNING_HISTORY_DAYS.

        Returns None until MIN_SOLAR_HISTORY_FOR_DYNAMIC_THRESHOLD samples
        are available, so callers can fall back to a fixed default until
        there is enough data to learn from.
        """
        if len(self.forecast_value_history) < MIN_SOLAR_HISTORY_FOR_DYNAMIC_THRESHOLD:
            return None
        return sum(self.forecast_value_history) / len(self.forecast_value_history)

    async def async_setup(self) -> None:
        if not self.enabled:
            return
        await self.async_bootstrap_from_history()
        self._unsub_compare = async_track_time_change(
            self.hass,
            self._handle_compare,
            hour=COMPARE_HOUR,
            minute=COMPARE_MINUTE,
            second=COMPARE_SECOND,
        )
        self._unsub_capture = async_track_time_change(
            self.hass,
            self._handle_forecast_capture,
            hour=FORECAST_CAPTURE_HOUR,
            minute=FORECAST_CAPTURE_MINUTE,
            second=FORECAST_CAPTURE_SECOND,
        )

    async def async_bootstrap_from_history(self) -> None:
        """Best-effort: seed forecast_value_history and deviation_history
        from Home Assistant's existing recorder history, so learning
        doesn't have to start from zero after installing/updating.

        Never raises - if the recorder isn't available, or anything goes
        wrong reading history, this silently does nothing and normal
        day-by-day learning takes over from here. Never overwrites
        already-learned (live) data.
        """
        if self.forecast_value_history or self.deviation_history:
            return

        forecast_entity = self.config.get(CONF_SOLAR_FORECAST_SENSOR)
        actual_entity = self.config.get(CONF_SOLAR_ACTUAL_SENSOR)

        try:
            from homeassistant.components.recorder import get_instance, history
        except ImportError:
            _LOGGER.debug(
                "Recorder component not available, skipping solar history bootstrap"
            )
            return

        now = dt_util.now()
        start = now - timedelta(days=LEARNING_HISTORY_DAYS + 2)

        def _fetch():
            return history.get_significant_states(
                self.hass, start, now, [forecast_entity, actual_entity]
            )

        try:
            recorder_instance = get_instance(self.hass)
            states_by_entity = await recorder_instance.async_add_executor_job(_fetch)
        except Exception as err:  # noqa: BLE001 - best effort, must never be fatal
            _LOGGER.warning(
                "Could not bootstrap solar forecast learning from history: %s", err
            )
            return

        forecast_states = states_by_entity.get(forecast_entity, [])
        actual_states = states_by_entity.get(actual_entity, [])
        if not forecast_states or not actual_states:
            _LOGGER.debug(
                "No historical states found for %s / %s to bootstrap from",
                forecast_entity,
                actual_entity,
            )
            return

        def _value_at_or_before(states, target: datetime) -> float | None:
            best: float | None = None
            for state in states:
                try:
                    changed = dt_util.as_local(state.last_changed)
                except (TypeError, ValueError):
                    continue
                if changed <= target:
                    try:
                        best = float(state.state)
                    except (TypeError, ValueError):
                        continue
            return best

        forecast_values: list[float] = []
        deviations: list[float] = []

        for day_offset in range(LEARNING_HISTORY_DAYS, 0, -1):
            target_day = (now - timedelta(days=day_offset)).date()
            predicted_at = dt_util.as_local(
                datetime.combine(
                    target_day - timedelta(days=1), datetime.min.time()
                )
            ).replace(
                hour=FORECAST_CAPTURE_HOUR,
                minute=FORECAST_CAPTURE_MINUTE,
                second=FORECAST_CAPTURE_SECOND,
            )
            actual_at = dt_util.as_local(
                datetime.combine(target_day, datetime.min.time())
            ).replace(hour=COMPARE_HOUR, minute=COMPARE_MINUTE, second=COMPARE_SECOND)

            predicted = _value_at_or_before(forecast_states, predicted_at)
            actual = _value_at_or_before(actual_states, actual_at)

            if predicted is None:
                continue
            forecast_values.append(predicted)

            if actual is not None and predicted:
                deviation = round((actual - predicted) / predicted * 100, 1)
                if abs(deviation) <= MAX_REASONABLE_DEVIATION_PERCENT:
                    deviations.append(deviation)

        if forecast_values:
            self.forecast_value_history = forecast_values[-LEARNING_HISTORY_DAYS:]
        if deviations:
            self.deviation_history = deviations[-LEARNING_HISTORY_DAYS:]

        if forecast_values or deviations:
            self.was_bootstrapped_from_history = True
            _LOGGER.info(
                "Bootstrapped solar forecast learning from history: %d "
                "forecast samples, %d deviation samples",
                len(self.forecast_value_history),
                len(self.deviation_history),
            )

    async def async_unload(self) -> None:
        if self._unsub_compare:
            self._unsub_compare()
        if self._unsub_capture:
            self._unsub_capture()

    @callback
    def _handle_compare(self, _now) -> None:
        self.hass.async_create_task(self._async_handle_compare())

    async def _async_handle_compare(self) -> None:
        """Compare the forecast captured this evening (around 20:00) for
        today, against the actual, about-to-reset yield of today.
        """
        today = dt_util.now().date()

        if (
            self.pending_predicted_kwh is not None
            and self.pending_predicted_date == today
        ):
            actual = _read_float(self.hass, self.config.get(CONF_SOLAR_ACTUAL_SENSOR))
            if actual is not None:
                self.last_predicted_kwh = self.pending_predicted_kwh
                self.last_actual_kwh = actual
                self.last_compared_date = today
                if self.pending_predicted_kwh:
                    self.last_deviation_percent = round(
                        (actual - self.pending_predicted_kwh)
                        / self.pending_predicted_kwh
                        * 100,
                        1,
                    )
                    if abs(self.last_deviation_percent) <= MAX_REASONABLE_DEVIATION_PERCENT:
                        self.deviation_history.append(self.last_deviation_percent)
                        self.deviation_history = self.deviation_history[
                            -LEARNING_HISTORY_DAYS:
                        ]
                    else:
                        _LOGGER.warning(
                            "Ignoring implausible forecast deviation of %.1f%% "
                            "(predicted %.2f kWh, actual %.2f kWh) - likely "
                            "captured during a sensor reset/rollover",
                            self.last_deviation_percent,
                            self.pending_predicted_kwh,
                            actual,
                        )
                else:
                    self.last_deviation_percent = None
            else:
                _LOGGER.warning(
                    "Could not read actual solar yield from %s for the "
                    "daily forecast comparison",
                    self.config.get(CONF_SOLAR_ACTUAL_SENSOR),
                )

        self._notify_listeners()

    @callback
    def _handle_forecast_capture(self, _now) -> None:
        self.hass.async_create_task(self._async_handle_forecast_capture())

    async def _async_handle_forecast_capture(self) -> None:
        """Capture the current Solcast "forecast for tomorrow" value,
        well before midnight, so it reflects a stable, fully-updated
        forecast rather than a value caught mid-rollover.
        """
        today = dt_util.now().date()

        forecast_value = _read_float(
            self.hass, self.config.get(CONF_SOLAR_FORECAST_SENSOR)
        )
        if forecast_value is not None:
            self.pending_predicted_kwh = forecast_value
            self.pending_predicted_date = today + timedelta(days=1)
            self.forecast_value_history.append(forecast_value)
            self.forecast_value_history = self.forecast_value_history[
                -LEARNING_HISTORY_DAYS:
            ]
        else:
            _LOGGER.warning(
                "Could not read Solcast forecast from %s to store for "
                "tomorrow's comparison",
                self.config.get(CONF_SOLAR_FORECAST_SENSOR),
            )

        self._notify_listeners()
