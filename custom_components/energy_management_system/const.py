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
CONF_SOLAR_FORECAST_SENSOR = "solar_forecast_sensor_entity"
CONF_SOLAR_ACTUAL_SENSOR = "solar_actual_sensor_entity"
CONF_CONSUMPTION_POWER_SENSOR = "consumption_power_sensor_entity"
CONF_BATTERY_POWER_SENSOR = "battery_power_sensor_entity"
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

# Once at least this many days of forecast history are known, the "low
# solar" threshold is derived from the installation's own learned typical
# forecast instead of the fixed CONF_LOW_SOLAR_THRESHOLD_KWH fallback.
MIN_SOLAR_HISTORY_FOR_DYNAMIC_THRESHOLD = 3
# "Low" = below this fraction of the learned typical forecast.
LOW_SOLAR_RELATIVE_FRACTION = 0.4

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

# Zonneplan's raw "amount" values are scaled by this factor to get €/kWh
# (e.g. 3728480 / 10_000_000 = 0.372848 €/kWh).
PRICE_SCALE_FACTOR = 10_000_000

UPDATE_INTERVAL_MINUTES = 15

# Zendure operation modes (select.select_option values)
OPTION_SMART = "smart"
OPTION_SMART_DISCHARGING = "smart_discharging"
OPTION_MANUAL = "manual"
