"""Constants for the Energy Management System integration."""

DOMAIN = "energy_management_system"
DEFAULT_NAME = "Energy Management System"

# Config / options keys
CONF_OPERATION_SELECT = "operation_select_entity"
CONF_MANUAL_POWER_NUMBER = "manual_power_number_entity"
CONF_PRICE_SENSOR = "price_sensor_entity"
CONF_PRICE_ATTRIBUTE = "price_attribute"
CONF_EXPENSIVE_QUARTERS_COUNT = "expensive_quarters_count"
CONF_MANUAL_DISCHARGE_POWER = "manual_discharge_power"
CONF_MANUAL_CHARGE_POWER = "manual_charge_power"
CONF_NEGATIVE_PRICE_CHARGE_POWER = "negative_price_charge_power"
CONF_SOLAR_POWER_LIMIT_ENTITY = "solar_power_limit_entity"
CONF_BATTERY_ROUND_TRIP_EFFICIENCY = "battery_round_trip_efficiency_percent"
CONF_VACATION_CONSUMPTION_REDUCTION_PERCENT = "vacation_consumption_reduction_percent"

# Optional appliance-awareness (informational learning + a "ready to
# start, and it's cheap now" notification - never controls the
# appliance itself).
CONF_DISHWASHER_POWER_SENSOR = "dishwasher_power_sensor_entity"
CONF_DISHWASHER_READY_SENSOR = "dishwasher_ready_sensor_entity"
CONF_WASHING_MACHINE_POWER_SENSOR = "washing_machine_power_sensor_entity"
CONF_WASHING_MACHINE_READY_SENSOR = "washing_machine_ready_sensor_entity"
CONF_QUOOKER_POWER_SENSOR = "quooker_power_sensor_entity"
CONF_AIRCO_CLIMATE_ENTITY = "airco_climate_entity"
CONF_OVEN_STATE_SENSOR = "oven_state_sensor_entity"
CONF_KOOKPLAAT_STATE_SENSOR = "kookplaat_state_sensor_entity"
CONF_STEELSTOFZUIGER_SWITCH = "steelstofzuiger_switch_entity"
CONF_STEELSTOFZUIGER_POWER_SENSOR = "steelstofzuiger_power_sensor_entity"
CONF_FIETSLADERS_SWITCH = "fietsladers_switch_entity"
CONF_FIETSLADERS_POWER_SENSOR = "fietsladers_power_sensor_entity"
CONF_APPLIANCE_NOTIFY_SERVICE = "appliance_notify_service"

# Emoji shown in the mode/power-change notification title (v0.63.8), one
# per possible coordinator.last_reason value - see _maybe_notify_mode_change.
MODE_CHANGE_EMOJI = {
    "expensive_quarter": "💰⬇️",
    "expensive_quarter_soc_protected": "🛡️",
    "grid_charging_low_solar": "⚡⬆️",
    "emergency_low_battery": "🚨",
    "negative_price": "🎁⬆️",
    "discharging_window": "⏳",
    "arbitrage_charging": "📈⬆️",
    "default_smart": "🤖",
    "no_forecast_data": "⚠️",
}
CONF_SOLAR_FORECAST_SENSOR = "solar_forecast_sensor_entity"
CONF_SOLAR_TODAY_FORECAST_SENSOR = "solar_today_forecast_sensor_entity"
CONF_SOLAR_REMAINING_TODAY_SENSOR = "solar_remaining_today_sensor_entity"
CONF_SOLAR_EXTENDED_FORECAST_SENSORS = "solar_extended_forecast_sensor_entities"
CONF_SOLAR_ACTUAL_SENSOR = "solar_actual_sensor_entity"
CONF_CONSUMPTION_POWER_SENSOR = "consumption_power_sensor_entity"
CONF_BATTERY_POWER_SENSOR = "battery_power_sensor_entity"
CONF_INVERT_BATTERY_POWER_SIGN = "invert_battery_power_sign"
CONF_PV_POWER_SENSOR = "pv_power_sensor_entity"
CONF_AVAILABLE_ENERGY_SENSOR = "available_energy_sensor_entity"
CONF_SOC_SENSOR = "battery_soc_sensor_entity"
CONF_MIN_SOC_PERCENT = "min_soc_percent"
# Fallback threshold, only used until enough learning history exists to
# derive a dynamic "low solar" threshold from the installation's own data.
CONF_LOW_SOLAR_THRESHOLD_KWH = "low_solar_threshold_kwh"

DEFAULT_LOW_SOLAR_THRESHOLD_KWH = 5.0
LEARNING_HISTORY_DAYS = 7
DEFAULT_MIN_SOC_PERCENT = 15.0
# Discharge power tapers linearly to 0 over this many percentage points
# above the configured minimum SoC (e.g. min=15%, band=15 -> full power
# from 30% and up, scaling down to 0 between 30% and 15%, none below 15%).
SOC_TAPER_BAND_PERCENT = 15.0

# Safety margin applied when deciding whether the currently available
# battery energy is enough to bridge until the cheap block starts (e.g.
# 1.15 = require 15% more than the bare estimated need).
ENERGY_BRIDGE_SAFETY_MARGIN = 1.15

# Margin applied specifically to the dynamic (energy-based) discharge
# reserve during expensive quarters - "keep at least what I actually need
# for tonight, plus this buffer", as opposed to a flat SoC percentage.
DYNAMIC_DISCHARGE_RESERVE_MARGIN = 1.10

# Below this live PV power (W), solar production is considered
# negligible/noise - above it, we consider the sun "actively producing"
# for the purpose of not postponing charging (see coordinator.py).
MIN_ACTIVE_SOLAR_PRODUCTION_W = 50

# For each additional consecutive day (beyond tomorrow) that's expected
# to have low solar, add this many extra percentage points to the
# dynamic discharge reserve margin - a longer cloudy stretch means less
# confidence the battery will be quickly refilled, so be more cautious
# about deep discharging. Naturally bounded by how many extended-day
# forecast sensors are configured (real data availability), not an
# arbitrary separate cap.
EXTENDED_LOW_SOLAR_MARGIN_BONUS_PER_DAY = 5.0

# Once at least this many days of forecast history are known, the "low
# solar" threshold is derived from the installation's own learned typical
# forecast instead of the fixed CONF_LOW_SOLAR_THRESHOLD_KWH fallback.
MIN_SOLAR_HISTORY_FOR_DYNAMIC_THRESHOLD = 3
# "Low" = below this fraction of the learned typical forecast.
LOW_SOLAR_RELATIVE_FRACTION = 0.4

# Dynamic "expensive quarter" threshold: a quarter counts as expensive if
# its price is within this fraction of today's price *range* from the
# day's maximum - no fixed count of quarters, self-adjusting to however
# many quarters actually clear the bar each day. Narrowed (fewer quarters
# qualify) when little solar is expected, for extra caution.
EXPENSIVE_PRICE_THRESHOLD_FRACTION = 0.20
EXPENSIVE_PRICE_THRESHOLD_FRACTION_LOW_SOLAR = 0.08

# A wider, more lenient "worth selling if there's spare capacity"
# threshold - only used to fill headroom left unused after today's
# genuinely expensive (primary-tier) quarters are accounted for. Never
# applied by itself; see _get_secondary_expensive_price_threshold.
SECONDARY_EXPENSIVE_PRICE_THRESHOLD_FRACTION = 0.45

# How far (as a fraction of the day's price range above the minimum) the
# cheap block is allowed to extend when detecting its natural width.
CHEAP_BLOCK_THRESHOLD_MARGIN_FRACTION = 0.2

# Hysteresis for the cheapest-block selection: keep the previously
# chosen cheap block instead of switching to a newly found candidate,
# as long as its price is within this fraction of today's price range
# of the new candidate. Prevents flip-flopping between two near-tied
# candidates elsewhere in the day as time passes and which quarters
# still count as "upcoming" shifts.
CHEAP_BLOCK_STABILITY_MARGIN_FRACTION = 0.05

# Price attribute options, matching the Zonneplan ONE "forecast" list items:
# {"start_date": ..., "end_date": ..., "price_tax_included": {"amount": ...},
#  "price_tax_excluded": {"amount": ...}, "sustainability_score": {...}}
PRICE_ATTRIBUTE_INCL_TAX = "price_tax_included"
PRICE_ATTRIBUTE_EXCL_TAX = "price_tax_excluded"
PRICE_ATTRIBUTE_OPTIONS = [PRICE_ATTRIBUTE_INCL_TAX, PRICE_ATTRIBUTE_EXCL_TAX]

DEFAULT_PRICE_ATTRIBUTE = PRICE_ATTRIBUTE_INCL_TAX
DEFAULT_EXPENSIVE_QUARTERS_COUNT = 4
DEFAULT_MANUAL_DISCHARGE_POWER = 1600
DEFAULT_MANUAL_CHARGE_POWER = -2000
DEFAULT_NEGATIVE_PRICE_CHARGE_POWER = -2000

# Typical Li-ion home battery round-trip efficiency, if not overridden.
# Applied to discount how much expected solar production actually reduces
# the discharge reserve need - solar routed through the battery (rather
# than covering household load directly) loses some energy to round-trip
# conversion losses before it's usable again.
DEFAULT_BATTERY_ROUND_TRIP_EFFICIENCY_PERCENT = 90.0

# How much lower than normal household consumption is assumed to be
# while vacation mode is on (e.g. 60 -> use only 40% of the normal
# estimate). A conservative default - actual vacation consumption varies
# a lot by household (some appliances still run, heating/cooling may
# still be needed), so this errs on the side of not under-reserving.
DEFAULT_VACATION_CONSUMPTION_REDUCTION_PERCENT = 60.0

# A power reading above this (W) counts as "the appliance is actively
# running" for usage-pattern learning and the ready-to-start check.
# Deliberately above typical standby draw (a few W) to avoid false
# positives from an idle-but-powered appliance.
APPLIANCE_RUNNING_POWER_THRESHOLD_W = 15.0

# Smoothing for the live-consumption correction (see
# _get_smoothed_consumption_correction_ratio): average over this many
# recent samples (at the ~5 minute update interval, this is roughly
# 15-25 minutes) instead of a single instantaneous reading, so a brief
# spike doesn't scale a 15+ hour reserve estimate to an absurd value.
CONSUMPTION_CORRECTION_SMOOTHING_SAMPLES = 4

# Even after smoothing, cap the correction ratio at this multiple of the
# learned average - an uncapped ratio beyond this is more likely a
# sensor glitch than a genuine sustained change like the airco running.
MAX_CONSUMPTION_CORRECTION_RATIO = 5.0

# Heavy-load awareness (v0.63.0): when a known heavy consumer (vaatwasser,
# wasmachine, Quooker, airco) is *confirmed* active via its own entity,
# the median smoothing's built-in caution above is no longer needed - it
# exists specifically to protect against a brief spike that MIGHT be one
# of these appliances but might also be a sensor glitch. With external
# confirmation there's no ambiguity left, so the live reading is trusted
# immediately instead of waiting several update ticks for the median to
# catch up. The Quooker still needs its own sustained-duration check
# (below): a single brief tap is exactly the kind of noise the median
# smoothing was originally built to ignore (v0.57.0) - only a longer
# session counts as a genuine, immediately-actionable load.
QUOOKER_SUSTAINED_MINUTES = 2

# How long the steelstofzuiger's power draw must stay below
# APPLIANCE_RUNNING_POWER_THRESHOLD_W before the charge is considered
# complete (mirror of QUOOKER_SUSTAINED_MINUTES - a brief dip in a
# charging curve shouldn't be mistaken for "done"). Shared by every
# scheduled-charge appliance (v0.63.13).
STEELSTOFZUIGER_COMPLETE_SUSTAINED_MINUTES = 2

# The e-bike chargers draw more standby power than the generic
# APPLIANCE_RUNNING_POWER_THRESHOLD_W (15W) would allow for a clean
# "done" signal (reported: 20W is the right cutoff for this specific
# charger), hence its own threshold rather than reusing the shared one.
FIETSLADERS_COMPLETE_THRESHOLD_W = 20.0

# hvac_action values that mean the climate entity's compressor/heating
# element is actually drawing power right now - 'idle' and 'off' don't
# count (thermostat satisfied / unit switched off).
AIRCO_ACTIVE_HVAC_ACTIONS = {"heating", "cooling"}

# Home Connect's BSH.Common.EnumType.OperationState, lowercased as HA
# exposes it. Only 'run' means the appliance is actually drawing power
# right now - 'ready'/'delayedstart' are scheduled-but-idle, 'pause' has
# the heating element off mid-cycle, 'finished'/'inactive' are done.
HOME_CONNECT_ACTIVE_STATES = {"run"}

# Minimum cumulative charged energy (kWh) before computing a new
# efficiency sample - avoids noisy estimates from tiny amounts of energy
# where sensor rounding/timing errors dominate.
MIN_CHARGED_KWH_FOR_EFFICIENCY_SAMPLE = 1.0

# Sanity bounds for a single efficiency sample (%) - outside this range is
# almost certainly a measurement glitch (e.g. a sensor reset, a missed
# reading), not a real efficiency value, and gets discarded.
MIN_PLAUSIBLE_EFFICIENCY_PERCENT = 50.0
MAX_PLAUSIBLE_EFFICIENCY_PERCENT = 100.0

# Ramp duration/steps for gradually curtailing/restoring the solar
# inverter's power limit around negative-price periods.
SOLAR_RAMP_DURATION_SECONDS = 30
SOLAR_RAMP_STEPS = 10

# Above this net grid import (W), during a period the integration
# believes should be self-sufficient (smart_discharging / expensive
# quarter), counts as an unexpected shortfall - the reserve estimate for
# that day turned out too optimistic. Set above typical sensor noise.
GRID_IMPORT_SHORTFALL_THRESHOLD_W = 100.0

# Arbitrage charging (v0.63.15): buy from the grid during a cheap
# quarter specifically because a known, more expensive quarter is still
# coming later today - only worthwhile if the projected net return
# clears this minimum margin (EUR/kWh) after round-trip losses, as a
# buffer against price-forecast/efficiency-estimate uncertainty.
MIN_ARBITRAGE_MARGIN_EUR_PER_KWH = 0.03

# Below this, forcing manual mode just to top up a trickle isn't worth
# disrupting the Zendure's own solar-following smart mode for.
MIN_ARBITRAGE_GRID_POWER_W = 100.0

# For each of the last LEARNING_HISTORY_DAYS days that had a detected
# shortfall, add this many extra percentage points to the dynamic
# discharge reserve margin - self-correcting if the reserve estimate has
# been running too tight. No separate cap (same philosophy as the
# multi-day low-solar margin): naturally bounded by the rolling window.
SHORTFALL_MARGIN_BONUS_PER_RECENT_DAY = 5.0

# Fallback threshold (kWh) for the emergency low-battery charge trigger,
# used only when no SoC sensor is configured (SoC% is preferred - see
# _is_emergency_low_battery). Keeps a small buffer above absolute zero.
EMERGENCY_LOW_BATTERY_KWH_THRESHOLD = 0.3

# If available energy stays at/above this multiple of what was actually
# needed while still in a "self-sufficient" window, the reserve looks
# overly conservative that day - counterbalances the shortfall-based
# margin increase, so the learned margin isn't a one-way ratchet.
RESERVE_EXCESS_RATIO_THRESHOLD = 3.0
EXCESS_MARGIN_REDUCTION_PER_RECENT_DAY = 3.0

# Floor for the total learned margin bonus (can go negative once excess
# days accumulate, but never below this - always keep at least this much
# safety margin over the raw estimate).
MIN_TOTAL_MARGIN_BONUS_PERCENT = -5.0

# Structural extra buffer: an expensive-quarter discharge is only
# protected by the reserve *during* that action - once control passes to
# 'smart' mode afterwards, the battery can be drawn further down for
# household use with no reserve protection at all. This flat extra margin
# compensates for that blind spot (added after a real incident where the
# reserve was technically respected during the expensive quarter, but the
# unprotected night afterwards still ran the battery to empty).
UNPROTECTED_AFTERMATH_MARGIN_PERCENT = 15.0

# Zonneplan's raw "amount" values are scaled by this factor to get €/kWh
# (e.g. 3728480 / 10_000_000 = 0.372848 €/kWh).
PRICE_SCALE_FACTOR = 10_000_000

UPDATE_INTERVAL_MINUTES = 5

# Zendure operation modes (select.select_option values)
OPTION_SMART = "smart"
OPTION_SMART_DISCHARGING = "smart_discharging"
OPTION_MANUAL = "manual"
