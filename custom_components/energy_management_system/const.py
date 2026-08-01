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

# How far (as a fraction of the day's price range above the minimum) the
# cheap block is allowed to extend when detecting its natural width.
CHEAP_BLOCK_THRESHOLD_MARGIN_FRACTION = 0.2

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

# Zonneplan's raw "amount" values are scaled by this factor to get €/kWh
# (e.g. 3728480 / 10_000_000 = 0.372848 €/kWh).
PRICE_SCALE_FACTOR = 10_000_000

UPDATE_INTERVAL_MINUTES = 15

# Zendure operation modes (select.select_option values)
OPTION_SMART = "smart"
OPTION_SMART_DISCHARGING = "smart_discharging"
OPTION_MANUAL = "manual"
