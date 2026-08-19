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
import statistics
from datetime import date, datetime, timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import (
    CONF_SOLAR_ACTUAL_SENSOR,
    CONF_SOLAR_FORECAST_SENSOR,
    LEARNING_HISTORY_DAYS,
    MIN_SOLAR_HISTORY_FOR_DYNAMIC_THRESHOLD,
    MIN_SOLAR_HISTORY_FOR_SPREAD_BASED_FRACTION,
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

# A daily PV forecast this high almost certainly means the wrong Solcast
# sensor was configured (e.g. a peak-power sensor in W, or a sensor with
# a name containing "piek", instead of the daily total in kWh) - even a
# large residential installation wouldn't reasonably forecast more than
# this per day. Values above this are treated as invalid and ignored,
# rather than silently corrupting the learned history.
MAX_REASONABLE_DAILY_FORECAST_KWH = 100.0


def _read_float(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Read a sensor's state as a float, automatically converting to kWh
    if the sensor reports a different energy unit (Wh or MWh) - without
    this, a sensor reporting in Wh (e.g. some SolarEdge integrations) gets
    misread as if the raw number were already kWh, off by a factor 1000.
    """
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
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


class SolarForecastAccuracyTracker:
    """Compares yesterday's Solcast forecast to today's realized PV yield."""

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        self.hass = hass
        self.config = config

        # The forecast captured on the previous day, predicting the date below.
        self.pending_predicted_kwh: float | None = None
        self.pending_predicted_date: date | None = None
        # v1.20.3: de vastlegging van 20:00 gaat eerst hierheen. Zij
        # kwam VOOR de vergelijking van 23:59 en overschreef precies de
        # waarde die vergeleken moest worden - waardoor de dagelijkse
        # vergelijking nooit lukte. In zeven opeenvolgende exports stond
        # `last_compared_date` dan ook op None.
        self.next_predicted_kwh: float | None = None
        self.next_predicted_date: date | None = None

        # Result of the most recent comparison.
        self.last_predicted_kwh: float | None = None
        self.last_actual_kwh: float | None = None
        self.last_deviation_percent: float | None = None
        self.last_compared_date: date | None = None

        # Rolling history of deviation percentages, used to learn a
        # systematic bias in the Solcast forecast for this installation.
        self.deviation_history: list[float] = []
        self.deviation_stdev_history: list[float] = []

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

    def _bruikbare_afwijkingen(self) -> list[float]:
        return [
            v
            for v in self.deviation_history
            if abs(v) <= MAX_REASONABLE_DEVIATION_PERCENT
        ]

    @property
    def learned_bias_percent(self) -> float | None:
        """De MEDIANE afwijking (%) over de laatste LEARNING_HISTORY_DAYS,
        met onmogelijke uitschieters eruit (zie
        MAX_REASONABLE_DEVIATION_PERCENT).

        Positief betekent dat Solcast voor deze installatie te laag
        voorspelt (meer opbrengst dan voorspeld); negatief te hoog.

        v3.28.0: mediaan in plaats van gemiddelde. Gemeten over zeven
        dagen in augustus: vier dagen binnen 4,7% en drie dagen 41 tot
        55% te hoog voorspeld. Het gemiddelde van die zeven is -22,6% en
        wordt volledig door die drie bepaald.

        Als vlakke correctie op alles maakte dat een heldere dag die
        klopte 22% te laag, zonder de bewolkte dagen te dekken.
        Nagerekend over dezelfde zeven dagen (fout na correctie):

            zonder correctie        gemiddeld 22,6%   mediaan 4,7%
            gemiddelde-bias -22,6%  gemiddeld 29,6%   mediaan 27,3%
            mediaan-bias -4,7%      gemiddeld 21,9%   mediaan 4,0%

        De correctie die er stond maakte het slechter dan helemaal niet
        corrigeren. Bij een ECHTE verschuiving - élke dag ongeveer even
        ver omlaag - lopen mediaan en gemiddelde vanzelf samen, dus die
        blijft gewoon geleerd worden.
        """
        valid = self._bruikbare_afwijkingen()
        if not valid:
            return None
        return round(statistics.median(valid), 1)

    @property
    def mean_bias_percent(self) -> float | None:
        """Het oude gemiddelde, bewaard om naast de mediaan te kunnen

        leggen (v3.28.0). Lopen die twee ver uiteen, dan zijn het twee
        soorten dagen en niet één verschuiving - en dat is precies wat
        de duiding op de meetkwaliteitskaart moet weten.
        """
        valid = self._bruikbare_afwijkingen()
        if not valid:
            return None
        return round(sum(valid) / len(valid), 1)

    @property
    def deviation_stdev_percent(self) -> float | None:
        """Standard deviation (%) of the same recent deviation history
        used for `learned_bias_percent` - a measure of how CONSISTENT
        the (bias-corrected) forecast has been, not just its average
        direction/magnitude (v0.63.87, uitgebreid besproken en
        ontworpen door de gebruiker).

        Used to scale `LOW_SOLAR_RELATIVE_FRACTION`: a low spread means
        the forecast can be trusted more (a wider fraction, less
        cautious); a high spread means the forecast has been
        unreliable, warranting more caution (a narrower fraction).

        Returns None until MIN_SOLAR_HISTORY_FOR_SPREAD_BASED_FRACTION
        valid samples are available (a stdev from very few samples is
        itself unreliable), so callers can fall back to the fixed
        default fraction until there is enough data to learn from.
        """
        valid = [
            v
            for v in self.deviation_history
            if abs(v) <= MAX_REASONABLE_DEVIATION_PERCENT
        ]
        if len(valid) < MIN_SOLAR_HISTORY_FOR_SPREAD_BASED_FRACTION:
            return None
        return round(statistics.pstdev(valid), 1)

    @property
    def learned_typical_forecast_kwh(self) -> float | None:
        """Rolling average raw forecast (kWh) over the last LEARNING_HISTORY_DAYS,
        ignoring implausible outliers (see MAX_REASONABLE_DAILY_FORECAST_KWH -
        e.g. leftover values from a previously misconfigured sensor).

        Returns None until MIN_SOLAR_HISTORY_FOR_DYNAMIC_THRESHOLD valid
        samples are available, so callers can fall back to a fixed default
        until there is enough data to learn from.
        """
        valid = [
            v
            for v in self.forecast_value_history
            if v <= MAX_REASONABLE_DAILY_FORECAST_KWH
        ]
        if len(valid) < MIN_SOLAR_HISTORY_FOR_DYNAMIC_THRESHOLD:
            return None
        return sum(valid) / len(valid)

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
        already-learned (live) *valid* data - but if the existing history
        is entirely implausible (e.g. leftover values from a previously
        misconfigured sensor - see MAX_REASONABLE_DAILY_FORECAST_KWH /
        MAX_REASONABLE_DEVIATION_PERCENT), this bootstraps fresh from
        history instead of leaving it stuck on garbage forever.
        """
        valid_existing_forecast = [
            v
            for v in self.forecast_value_history
            if v <= MAX_REASONABLE_DAILY_FORECAST_KWH
        ]
        valid_existing_deviation = [
            v
            for v in self.deviation_history
            if abs(v) <= MAX_REASONABLE_DEVIATION_PERCENT
        ]
        need_forecast_bootstrap = not valid_existing_forecast
        need_deviation_bootstrap = not valid_existing_deviation
        if not need_forecast_bootstrap and not need_deviation_bootstrap:
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

        # Auto-convert to kWh if the actual-yield sensor reports in a
        # different energy unit (e.g. Wh) - assumes the unit doesn't
        # change over the lookback period, using its current unit as a
        # stand-in for what it was historically.
        actual_unit = (
            self.hass.states.get(actual_entity).attributes.get(
                "unit_of_measurement", ""
            )
            if self.hass.states.get(actual_entity)
            else ""
        ) or ""
        actual_unit = actual_unit.strip().lower()
        if actual_unit == "wh":
            actual_unit_factor = 0.001
        elif actual_unit == "mwh":
            actual_unit_factor = 1000.0
        else:
            actual_unit_factor = 1.0

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
            if actual is not None:
                actual *= actual_unit_factor

            if predicted is None or predicted > MAX_REASONABLE_DAILY_FORECAST_KWH:
                continue
            forecast_values.append(predicted)

            if actual is not None and predicted:
                deviation = round((actual - predicted) / predicted * 100, 1)
                if abs(deviation) <= MAX_REASONABLE_DEVIATION_PERCENT:
                    deviations.append(deviation)

        if need_forecast_bootstrap and forecast_values:
            self.forecast_value_history = forecast_values[-LEARNING_HISTORY_DAYS:]
        if need_deviation_bootstrap and deviations:
            self.deviation_history = deviations[-LEARNING_HISTORY_DAYS:]

        if (need_forecast_bootstrap and forecast_values) or (
            need_deviation_bootstrap and deviations
        ):
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
                        # v0.63.88, gevraagd: inzicht of het model/de
                        # parameter nauwkeuriger wordt over tijd. Sample
                        # de spreidingsmaat zelf eenmaal per dag in een
                        # eigen, rollend venster - zo kan een trend
                        # (wordt de voorspelling consistenter of juist
                        # wisselvalliger?) worden getoond, los van het
                        # gemiddelde/de systematische bias zelf.
                        stdev_sample = self.deviation_stdev_percent
                        if stdev_sample is not None:
                            self.deviation_stdev_history.append(stdev_sample)
                            self.deviation_stdev_history = self.deviation_stdev_history[
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

        # v1.20.3: pas NA de vergelijking de vastlegging van vanavond
        # doorschuiven. Voorheen schreef de vastlegging van 20:00 direct
        # in `pending`, en die kwam VOOR de vergelijking van 23:59 -
        # precies de waarde die vergeleken moest worden werd dus gewist.
        #
        # Gevolg: de dagelijkse vergelijking lukte nooit. In zeven
        # opeenvolgende exports stond `last_compared_date` op None, en
        # de zeven afwijkingen kwamen allemaal uit de bootstrap uit de
        # historie - niet uit één enkele live vergelijking.
        if self.next_predicted_date is not None:
            self.pending_predicted_kwh = self.next_predicted_kwh
            self.pending_predicted_date = self.next_predicted_date
            self.next_predicted_kwh = None
            self.next_predicted_date = None

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
        was_rejected_as_implausible = False
        if forecast_value is not None and forecast_value > MAX_REASONABLE_DAILY_FORECAST_KWH:
            _LOGGER.warning(
                "Ignoring implausible Solcast forecast of %.1f kWh from %s - "
                "this looks like the wrong sensor is configured (e.g. a peak "
                "power sensor instead of the daily total kWh forecast). "
                "Check the configured 'solar_forecast_sensor_entity'.",
                forecast_value,
                self.config.get(CONF_SOLAR_FORECAST_SENSOR),
            )
            forecast_value = None
            was_rejected_as_implausible = True

        if forecast_value is not None:
            # v1.20.3: niet direct in `pending` - dat zou de waarde van
            # vandaag wissen voordat die om 23:59 vergeleken is.
            self.next_predicted_kwh = forecast_value
            self.next_predicted_date = today + timedelta(days=1)
            self.forecast_value_history.append(forecast_value)
            self.forecast_value_history = self.forecast_value_history[
                -LEARNING_HISTORY_DAYS:
            ]
        elif not was_rejected_as_implausible:
            _LOGGER.warning(
                "Could not read Solcast forecast from %s to store for "
                "tomorrow's comparison",
                self.config.get(CONF_SOLAR_FORECAST_SENSOR),
            )

        self._notify_listeners()
