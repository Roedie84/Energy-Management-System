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
CONF_BATTERY_TOTAL_CAPACITY_SENSOR = "battery_total_capacity_sensor_entity"
CONF_BATTERY_MIN_SOC_NUMBER = "battery_min_soc_number_entity"
CONF_MANUAL_CHARGE_POWER = "manual_charge_power"
CONF_NEGATIVE_PRICE_CHARGE_POWER = "negative_price_charge_power"
CONF_SOLAR_POWER_LIMIT_ENTITY = "solar_power_limit_entity"
CONF_KNMI_WEATHER_ENTITY = "knmi_weather_entity"
CONF_OPENWEATHERMAP_WEATHER_ENTITY = "openweathermap_weather_entity"
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
CONF_SLAAPKAMER_CLIMATE_ENTITY = "slaapkamer_climate_entity"
CONF_LIVING_ROOM_TEMPERATURE_SENSOR = "living_room_temperature_sensor_entity"
CONF_LIVING_ROOM_HUMIDITY_SENSOR = "living_room_humidity_sensor_entity"
CONF_LIVING_ROOM_SHUTTER_ENTITY_1 = "living_room_shutter_entity_1"
CONF_LIVING_ROOM_SHUTTER_ENTITY_2 = "living_room_shutter_entity_2"
CONF_OVEN_STATE_SENSOR = "oven_state_sensor_entity"
CONF_KOOKPLAAT_STATE_SENSOR = "kookplaat_state_sensor_entity"
CONF_STEELSTOFZUIGER_SWITCH = "steelstofzuiger_switch_entity"
CONF_STEELSTOFZUIGER_POWER_SENSOR = "steelstofzuiger_power_sensor_entity"
CONF_FIETSLADERS_SWITCH = "fietsladers_switch_entity"
CONF_FIETSLADERS_POWER_SENSOR = "fietsladers_power_sensor_entity"
CONF_APPLIANCE_NOTIFY_SERVICE = "appliance_notify_service"

# Water-tabblad (v0.63.85, gevraagd: "Meldingen/tracking zoals bij
# vaatwasser/wasmachine" - herzien naar "geen meldingen alleen een
# watertabblad met relevante info"). Puur informatief, stuurt nooit
# iets aan en beïnvloedt de accu-beslissing op geen enkele manier.
CONF_WATER_ACTIVE_USAGE_SENSOR = "water_active_usage_sensor_entity"
CONF_WATER_DAILY_TOTAL_SENSOR = "water_daily_total_sensor_entity"
CONF_WATER_TOTAL_USAGE_SENSOR = "water_total_usage_sensor_entity"

# Emoji shown in the mode/power-change notification title (v0.63.8), one
# per possible coordinator.last_reason value - see _maybe_notify_mode_change.
# Maps the final coordinator.last_reason (decided only after headroom/
# SoC/price-priority checks run) to the mode that was actually applied
# this tick - used to correct last_expected_mode after the fact (v0.63.20).
# last_expected_mode is set early, from the price check alone, before
# those later checks can downgrade an "expensive, should discharge"
# guess back to smart - without this correction, the displayed
# "Verwachte modus" could disagree with what was actually decided.
MODE_CHANGE_EMOJI = {
    "expensive_quarter": "💰⬇️",
    "expensive_quarter_soc_protected": "🛡️",
    "grid_charging_low_solar": "⚡⬆️",
    "grid_charging_low_solar_extra_dip": "⚡🔎",
    "emergency_low_battery": "🚨",
    "negative_price": "🎁⬆️",
    "discharging_window": "⏳",
    "arbitrage_solar_capture": "☀️",
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

# CUSUM sluipverbruik-detectie (v0.63.29): detects a sustained shift in
# the household's daily "floor load" (lowest consumption reading of the
# day - phantom/standby loads dominate there), distinct from the
# adaptive LEARNING_HISTORY_DAYS window used for actual decisions.
# CUSUM needs a longer, more stable reference to detect a *gradual*
# drift that a 7-day rolling median would just quietly absorb as "the
# new normal".
CUSUM_BASELINE_HISTORY_DAYS = 30
CUSUM_MIN_HISTORY_FOR_REFERENCE = 10
CUSUM_REFERENCE_EXCLUDE_RECENT_DAYS = 5
CUSUM_SLACK_KW = 0.02
CUSUM_ALARM_THRESHOLD_KW = 0.15

# Weather ensemble cross-check (v0.63.30): compares live PV output
# against Solcast's own forecast for right now (already computable from
# existing data) alongside live cloud_coverage readings from independent
# weather sources (KNMI/OpenWeatherMap, read from their HA `weather`
# entities - not a new API integration, just entities the person already
# has). A pure informational cross-check, not wired into any decision:
# building a genuine multi-source kWh yield ensemble would need panel
# orientation/tilt/kWp specs this integration doesn't collect.
WEATHER_ENSEMBLE_CLEAR_THRESHOLD_PERCENT = 30.0
WEATHER_ENSEMBLE_OVERCAST_THRESHOLD_PERCENT = 70.0
WEATHER_ENSEMBLE_UNDERPERFORM_RATIO = 0.5
WEATHER_ENSEMBLE_OVERPERFORM_RATIO = 1.3
WEATHER_ENSEMBLE_MIN_SOLCAST_KW = 0.2
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
#
# v0.63.87, uitgebreid besproken en ontworpen door de gebruiker: deze
# fractie is niet langer vast, maar beweegt mee met hoe CONSISTENT de
# (bias-gecorrigeerde) voorspelling recent is gebleken - een
# standaarddeviatie van `deviation_history` (al bestaande, ruwe
# afwijkingsdata, tot nu toe alleen gebruikt voor het gemiddelde/de
# systematische bias). Consistente voorspellingen verdienen meer
# vertrouwen (een ruimere fractie, minder snel "laag" gealarmeerd);
# wisselvallige voorspellingen vragen om meer voorzichtigheid (een
# kleinere fractie, sneller "laag" gealarmeerd bij twijfel). Bewust
# vaste, uitlegbare niveaus (net als de rest van deze integratie) in
# plaats van een continue formule - drie simpele stappen, geen
# "black box".
LOW_SOLAR_RELATIVE_FRACTION = 0.4  # terugval zonder genoeg spreidingsdata
LOW_SOLAR_FRACTION_LOW_SPREAD_THRESHOLD_PERCENT = 10.0
LOW_SOLAR_FRACTION_HIGH_SPREAD_THRESHOLD_PERCENT = 25.0
LOW_SOLAR_FRACTION_CONSISTENT = 0.6  # stdev < 10%: vertrouw ruimer
LOW_SOLAR_FRACTION_DEFAULT = 0.4  # stdev 10-25%: huidige, voorzichtige standaard
LOW_SOLAR_FRACTION_UNRELIABLE = 0.3  # stdev > 25%: extra conservatief
# Minimaal aantal samples voor een zinvolle standaarddeviatie - iets
# hoger dan MIN_SOLAR_HISTORY_FOR_DYNAMIC_THRESHOLD zelf, voor een
# stabielere spreidingsschatting (2 samples geven een zeer ruizige
# stdev).
MIN_SOLAR_HISTORY_FOR_SPREAD_BASED_FRACTION = 5

# Temperatuur-verbruik-regressie voor extreme-koude-dagen (v0.63.88,
# uitgebreid besproken en ontworpen door de gebruiker na een analyse
# van 11 januari 2026 - het koudste etmaal van het jaar). Puur
# adviserend ("eerst observeren", expliciet zo afgesproken) - toont een
# verwachte-verbruik-schatting en of die nauwkeuriger wordt over tijd,
# maar beïnvloedt de bestaande reserve-/dieptekort-berekening nog op
# geen enkele manier. Minimaal aantal (temperatuur, verbruik)-paren
# voordat er een voorspelling wordt gedaan - een regressie door te
# weinig punten is zelf onbetrouwbaar.
TEMP_CONSUMPTION_MIN_SAMPLES = 4

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

# Scheduled-charge appliance polling (v0.63.38). Reported fire-safety
# concern: with v0.63.37's "wait for the device" fix, the switch stayed
# continuously ON for however long nothing was plugged in - potentially
# hours, keeping a charger/inverter needlessly energised unattended.
# Instead of staying on continuously while nothing is detected, the
# switch now polls: on briefly to test for a load, back off for a
# cooldown if nothing found, repeat - matching the reported "15-minuten
# controle-cyclus" suggestion. The "on" test window is naturally one
# update tick (~5 min, UPDATE_INTERVAL_MINUTES) - no separate constant
# needed for that half of the cycle.
SCHEDULED_CHARGE_POLL_OFF_MINUTES = 15

# Self-learned completion threshold for scheduled-charge appliances
# (v0.63.46). Reported: the fixed FIETSLADERS_COMPLETE_THRESHOLD_W
# guess (20W) doesn't reflect the real standby draw (observed 2W) -
# instead of assuming a fixed threshold, learn the actual idle/standby
# power from readings taken during the poll-test window (switch on,
# nothing genuinely charging yet - see _async_update_scheduled_charge_
# appliance), and derive a threshold from it with a safety margin.
# Falls back to the configured fixed threshold until enough idle
# samples have been collected.
IDLE_POWER_HISTORY_LENGTH = 20
LEARNED_THRESHOLD_MIN_SAMPLES = 5
LEARNED_THRESHOLD_MARGIN_W = 5.0

# NILM-achtige apparaat-auto-detectie (v0.63.39). Geen "echte" NILM
# (blinde disaggregatie van één geaggregeerd vermogenssignaal, een
# onderzoeksmatig vraagstuk zonder trainingsdata) - ontdekt bestaande
# vermogen-sensoren (W/kW) in Home Assistant die nog niet elders
# geconfigureerd zijn, en past na expliciete bevestiging door de
# gebruiker dezelfde CUSUM-drift-detectie toe als sluipverbruik
# (v0.63.29), maar per apparaat en percentage-gebaseerd (vermogensniveaus
# verschillen te veel tussen apparaten voor een vaste Watt-drempel).
NILM_CUSUM_SLACK_FRACTION = 0.10
NILM_CUSUM_ALARM_THRESHOLD = 1.0

# Structurele NILM-uitsluitingspatronen (v0.63.89, gevraagd: "alles
# waar fase 1 bij staat mag sowieso uitgesloten worden net als
# solaredge en zendure entiteiten"). Substring-match (kleine letters)
# tegen zowel de entity_id als de friendly_name - anders dan
# `_nilm_excluded_entity_ids()` (exacte match tegen specifiek
# geconfigureerde entiteiten), dit is een structurele, patroon-
# gebaseerde uitsluiting die geen losse afwijzing per sub-fase-sensor
# of accu-/omvormer-signaal meer vereist.
NILM_PATTERN_EXCLUDED_KEYWORDS = ("fase 1", "fase_1", "solaredge", "zendure")

# NILM devices overview table trend labels (v0.63.51). A lighter-weight,
# more granular signal than the anomaly_detected flag (which only fires
# on a *sustained* CUSUM breach) - just compares the most recent daily
# average against the reference, so a modest upward/downward move shows
# up in the table well before it would ever cross the alarm threshold.
NILM_TREND_RISING_THRESHOLD_PERCENT = 5.0
NILM_TREND_FALLING_THRESHOLD_PERCENT = 5.0

# NILM dashboard confirm/reject slots (v0.63.41): a fixed number of
# button pairs, since a static Lovelace YAML dashboard (no extra HACS
# frontend card assumed) can't dynamically render one button per
# candidate for an unknown-length, changing list. Each slot shows
# whichever candidate currently occupies that position in a
# deterministic (alphabetically sorted by entity_id) ordering.
#
# v0.63.83, requested ("1 optie tonen is voldoende, als de 1e beoordeeld
# is verschijnt de 2e automatisch"): reduced from 8 to 1 - beoordeling
# happens one candidate at a time anyway, and a single slot gives each
# card much more width to show the full candidate name/power without
# truncation (reported: "nog niet de volledige naam leesbaar" with 8
# slots crammed two-per-row). Confirming/rejecting the current slot
# still automatically shifts the next candidate into view, exactly as
# before - only the number of simultaneously visible slots changed.
NILM_DASHBOARD_SLOT_COUNT = 1

# NILM sensor attribute size cap (v0.63.45). Reported: with the broad
# "any W/kW sensor" discovery scope, the full unconfirmed-candidates
# dict can exceed Home Assistant's 16KB per-attribute recorder limit
# (particularly likely with e.g. the Zendure integration's own
# granular per-pack power sensors) - the recorder then silently drops
# the attribute entirely rather than truncating it, so a bounded
# preview is needed instead of the raw full dict. The functional
# discovery/confirm/reject logic itself is NOT limited by this - only
# what the sensor's own state attribute exposes. The full list remains
# available via diagnostics (not subject to the recorder's limit).
NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT = 20

# Markov-achtige RUSTEND/ACTIEF/KLAAR-toestandsmachine voor vaatwasser/
# wasmachine (v0.63.32, "Optie 1" - geen fase-detectie, daarvoor
# ontbreekt trainingsdata per merk/model). Ruimere marge dan de
# steelstofzuiger/fietsladers-detectie (2 min), want een cyclus kan
# tussentijds stille fases hebben (vullen, weken) die langer duren dan
# een korte lading opladen - een te korte marge zou een cyclus
# halverwege ten onrechte als "klaar" kunnen markeren.
APPLIANCE_CYCLE_COMPLETE_SUSTAINED_MINUTES = 5

# Water-tabblad (v0.63.85). Bewust een lage drempel - de gebruiker wil
# juist volledig inzicht ("wat het verbruikt"), inclusief kleinere
# kranen en de nachtelijke waterontharder-regeneratie (een relatief kort,
# herkenbaar debiet-patroon, ongeveer 1x per 2 weken). Ruis (een kortere
# stroomonderbreking tijdens dezelfde douche/bad-sessie) wordt opgevangen
# door WATER_SESSION_COMPLETE_SUSTAINED_MINUTES hieronder, net als bij de
# vaatwasser/wasmachine-detectie.
WATER_USAGE_ACTIVE_THRESHOLD_L_PER_MIN = 1.0

# Hoeveel minuten het debiet aanhoudend onder de drempel moet blijven
# voordat een gebruiksmoment als afgerond wordt beschouwd - korter dan
# de vaatwasser/wasmachine-marge (5 min): watergebruik heeft doorgaans
# geen tussentijdse stille fases zoals een wasprogramma, dus een kortere
# marge onderscheidt losse momenten (kraan, toilet, douche) beter van
# elkaar in plaats van ze onterecht samen te voegen.
WATER_SESSION_COMPLETE_SUSTAINED_MINUTES = 2

# Hoeveel recente, afgeronde gebruiksmomenten getoond worden op het
# Water-tabblad (Onderdeel/Waarde-achtige lijst, nieuwste eerst).
WATER_SESSION_HISTORY_LENGTH = 20

# Waterontharder-regeneratie herkennen (v0.63.86, gevraagd: "wanneer
# hij zijn werk heeft gedaan en hoelang dat geleden is"). Er is geen
# betrouwbare manier om dit te onderscheiden van ander gebruik puur op
# basis van debiet/duur (dat verschilt per merk/model, en er is geen
# trainingsdata voor). In plaats daarvan: elk gebruiksmoment dat
# start binnen dit nachtelijke venster wordt aangemerkt als de
# waterontharder - niemand doucht of vult een bad structureel midden
# in de nacht, dus tijdstip alleen is hier al een betrouwbare
# indicator. Bewust een ruim venster (middernacht tot 6 uur) zodat een
# regeneratie op een net-iets-ander tijdstip niet gemist wordt.
WATER_SOFTENER_NIGHT_WINDOW_START_HOUR = 0
WATER_SOFTENER_NIGHT_WINDOW_END_HOUR = 6

# The e-bike chargers draw more standby power than the generic
# APPLIANCE_RUNNING_POWER_THRESHOLD_W (15W) would allow for a clean
# "done" signal (reported: 20W is the right cutoff for this specific
# charger), hence its own threshold rather than reusing the shared one.
FIETSLADERS_COMPLETE_THRESHOLD_W = 20.0

# hvac_action values that mean the climate entity's compressor/heating
# element is actually drawing power right now - 'idle' and 'off' don't
# count (thermostat satisfied / unit switched off).
AIRCO_ACTIVE_HVAC_ACTIONS = {"heating", "cooling"}

# v0.63.78, reported ("Basisverbruik ... schiet tussen ca. 16:00 en
# 17:00 omhoog door koken etc."): of the confirmed-heavy-load sources
# in _get_confirmed_heavy_load_source, only these two represent a
# genuinely *sustained*, potentially multi-hour elevated consumption
# level worth trusting immediately (bypassing the median smoothing) to
# scale an entire remaining bridging-period estimate. The others
# (oven, kookplaat, vaatwasser, wasmachine, quooker) are all inherently
# short-duration - trusting their live reading directly for a
# multi-hour projection would overstate it for an event that's over
# within the hour.
SUSTAINED_HEAVY_LOAD_SOURCES = {"airco", "slaapkamer"}

# Living-room-temperature airco activation predictor (v0.63.55,
# requested): "wanneer ik de airco aanzet" - a genuine anticipatory
# indicator, not just a live correlation. Uses the same "queue an
# observation, confirm it later" technique as
# SolarForecastAccuracyTracker (pending_predicted_kwh -> compared the
# next day) - each living-room-temperature reading is bucketed and
# queued, then AIRCO_PREDICTION_LOOKAHEAD_MINUTES later it's finalised
# as True/False depending on whether the airco was confirmed active at
# any point during that window. Deliberately a SHORT rolling window per
# bucket (not a long, season-spanning one) - requested: spring/autumn
# conditions can swing day to day, so a bucket's learned probability
# should track recent behaviour, not get diluted by weeks-old data from
# a different regime.
LIVING_ROOM_TEMP_BUCKET_SIZE_C = 1.0
AIRCO_PREDICTION_LOOKAHEAD_MINUTES = 60
AIRCO_PREDICTION_MIN_SAMPLES = 5
AIRCO_PREDICTION_HISTORY_LENGTH = 20

# Klimaat-tabblad: geleerde woonkamertemperatuur-projectie (v0.63.56,
# requested). Bewust vereenvoudigd t.o.v. een volledig model (buitentemp
# x rolluikstand x bewolking x airco-status zou honderden cellen
# opleveren die elk apart genoeg data nodig hebben) - bewolking is
# expliciet WEGGELATEN als aparte leerdimensie (bevestigd met de
# gebruiker), maar de buitentemperatuur-vóórspelling van KNMI/
# OpenWeatherMap wordt wel gebruikt om de projectie uur voor uur door
# te rekenen. Geleerd: de verandersnelheid (°C/uur) van de
# woonkamertemperatuur, per combinatie van buitentemperatuur-bucket x
# rolluikstand (beide_dicht/gedeeltelijk/beide_open) x airco-status
# (uit/verwarmen/koelen). Kort, glijdend venster per cel (zelfde
# principe als de airco-verwachting hierboven) - reageert snel op
# veranderend weer, niet seizoensgebonden.
OUTDOOR_TEMP_BUCKET_SIZE_C = 2.0
CLIMATE_RATE_HISTORY_LENGTH = 20
# A rate computed from 5-minute-tick deltas would be numerically
# unstable (typical sensor resolution ~0.1C, divided by a tiny 5/60h
# timespan amplifies noise into wildly swinging rates) for a physically
# slow-moving quantity like room temperature - so the rate is measured
# over roughly an hour, not every tick. CLIMATE_RATE_MAX_INTERVAL_HOURS
# guards against a restart-sized gap being misread as one huge "hour".
CLIMATE_RATE_MIN_INTERVAL_HOURS = 0.9
CLIMATE_RATE_MAX_INTERVAL_HOURS = 3.0
CLIMATE_RATE_MIN_SAMPLES = 5
# Two-tier reliability (v0.63.57, requested): "indicatief" (>=
# CLIMATE_RATE_MIN_SAMPLES, 5) shows a first-pass estimate even with
# still-thin data; "betrouwbaar" (>= CLIMATE_RATE_RELIABLE_SAMPLES, 15)
# requires substantially more confirmed samples before being shown as
# the more confident projection. Both tiers are computed in parallel
# for the same forecast, not two separate models.
CLIMATE_RATE_RELIABLE_SAMPLES = 15
CLIMATE_FORECAST_HORIZON_HOURS = 24
CLIMATE_FORECAST_FETCH_INTERVAL_MINUTES = 30

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

# Battery cost-basis tracking (v0.63.24): the smallest available_kwh
# change (kWh) between ticks that counts as a genuine charge/discharge
# event, rather than sensor noise/rounding jitter - below this, the
# weighted-average cost basis isn't updated and no savings are realised.
MIN_COST_BASIS_DELTA_KWH = 0.01

# Zonneplan's "Zonnebonus" (v0.63.25, confirmed via web search - not
# assumed): a fixed EUR/kWh premium on top of the day-ahead market price
# for every kWh genuinely fed back to the grid, on top of/outside your
# saldeerbereik. Unconditional (unlike the separate 10% bonus on top of
# that, which explicitly excludes feed-in sourced from a home battery -
# irrelevant here since we never apply it). Only applies to the portion
# of a discharge that's genuine net export - not the portion that
# simply covers household load (no feed-in happens there at all).
FEEDIN_PREMIUM_EUR_PER_KWH = 0.02

# In-progress hourly-bucket tracking (v0.63.16) restores across a
# restart, but only within this gap - a longer gap (real outage, not a
# quick update-restart) makes the accumulated partial-hour energy
# unreliable (assumes a single power level held for the whole gap), so
# it's discarded and tracking starts fresh instead.
MAX_HOUR_TRACKING_GAP_MINUTES = 20

# Kirchhoff energy-balance validation (v0.63.28): cross-checks the
# battery power sensor's own reading against what the available-energy
# sensor's rate of change *implies* the battery power must be - a
# genuine internal-consistency check using only sensors already
# configured, not a new measurement. A rolling window of recent
# per-tick errors feeds a 0-100 sensor_health_score.
ENERGY_BALANCE_ERROR_HISTORY_LENGTH = 20
ENERGY_BALANCE_ERROR_BAD_THRESHOLD_W = 300.0
MEASUREMENT_QUALITY_GOOD_THRESHOLD = 80
MEASUREMENT_QUALITY_DEGRADED_THRESHOLD = 50

# v0.63.15-.76: "arbitrage-laden" used to actively buy from the grid
# during a cheap quarter for a known, later, more expensive quarter -
# removed entirely in v0.63.77, final confirmed decision after several
# real-world reports. The battery never actively buys from the grid for
# this reason any more, only captures live solar surplus that would
# otherwise be wasted during smart_discharging - the margin/grid-power
# thresholds that used to gate the (now-removed) grid-purchase decision
# are no longer needed.

# MPC (Model Predictive Control) advisory engine (v0.63.33). Advisory
# ONLY - computes a projected charge/discharge plan over the available
# price forecast horizon and exposes it for comparison, but NEVER sends
# a device command and NEVER overrides the existing, battle-tested
# decision tree (confirmed explicitly before building this).
#
# Algorithm: greedy interval pairing over the full forecast horizon
# (today + tomorrow, whatever's available) - sort quarters by price,
# repeatedly match the cheapest remaining quarter with the priciest
# remaining quarter and allocate a charge/discharge chunk between them
# (bounded by physical rate and remaining capacity headroom) as long as
# it clears MPC_MIN_MARGIN_EUR_PER_KWH after efficiency losses. This is
# a well-known good heuristic for the storage-arbitrage problem, not a
# true linear-programming solve - no new dependency (e.g. scipy) is
# introduced for a HACS integration to stay lightweight, and the
# heuristic's steps stay individually inspectable, unlike an opaque
# solver's output.
MPC_HORIZON_HOURS = 48
MPC_MIN_MARGIN_EUR_PER_KWH = 0.03

# Extra-dip laden op weinig-zon-dagen (v0.63.87, uitgebreid besproken en
# ontworpen door de gebruiker). Sinds v0.63.77 laadt het systeem tijdens
# een weinig-zon-dag alleen nog gedwongen bij binnen het ene, hoofd-
# goedkope blok van de dag (`should_force_charge`) - een aparte, losse
# prijsdip elders die dag (buiten dat blok) werd volledig genegeerd,
# ook al zou bijladen daar aantoonbaar voordeliger zijn dan wachten.
# Bewust géén algemene comeback van het verwijderde arbitrage-
# mechanisme (dat was altijd actief, ongeacht behoefte) - dit vuurt
# uitsluitend wanneer `_is_low_solar_expected()` al `True` is (dus de
# accu toch al gedwongen van het net bijlaadt vanwege een genuine
# behoefte), en gebruikt dezelfde rendement-gecorrigeerde marge-check
# als het oude mechanisme. Bewust géén rendement-check op het
# hoofdblok zelf (expliciet zo gevraagd) - dat blijft ongewijzigd,
# want dat is per definitie al het goedkoopste moment van de dag.
LOW_SOLAR_EXTRA_DIP_MIN_MARGIN_EUR_PER_KWH = 0.03

# Monte Carlo advisory engine (v0.63.34). Advisory ONLY - never sends a
# device command, never overrides the existing decision tree. Bootstrap-
# resamples the empirical distributions already collected for
# consumption (hourly_consumption_profile) and PV forecast bias
# (pv_hourly_bias_history) to run many randomised trajectories of the
# same "diepste tekort" walk the deterministic reserve calculation
# already does (_estimate_worst_case_deficit_kwh), producing a
# probability distribution instead of a single point estimate.
MONTE_CARLO_SIMULATIONS = 1000
MONTE_CARLO_MAX_HOURS = 48

# Kalman filtering advisory engine (v0.63.35). Advisory ONLY - a smoothed
# estimate shown alongside the raw sensor reading, never fed into any
# decision (which keep using their own already-tested smoothing, e.g.
# the median-based consumption correction). Process noise (Q, how much
# the true value is expected to drift between 5-minute ticks) and
# measurement noise (R, how noisy the raw sensor reading is believed to
# be) are heuristic, documented defaults per signal - not empirically
# characterised against real sensor noise data, since that data doesn't
# exist for this installation. A higher Q relative to R makes the
# filter track changes faster (trusts new measurements more); a higher
# R relative to Q makes it smoother but slower to react.
KALMAN_SOC_PROCESS_NOISE_KWH2 = 0.0004  # available_kwh drifts modestly tick to tick
KALMAN_SOC_MEASUREMENT_NOISE_KWH2 = 0.0009
KALMAN_PV_PROCESS_NOISE_W2 = 2500.0  # live PV can swing quickly (clouds)
KALMAN_PV_MEASUREMENT_NOISE_W2 = 10000.0
KALMAN_LOAD_PROCESS_NOISE_W2 = 400.0
KALMAN_LOAD_MEASUREMENT_NOISE_W2 = 2500.0

# Digital Twin advisory engine (v0.63.36). Advisory ONLY - simulates
# forward in time what the *existing* rule-based logic would do (using
# the same primary-expensive-quarter threshold and cheapest-block
# identification already computed elsewhere), as a complement to MPC's
# theoretical-optimum plan - the gap between the two shows how much
# headroom (if any) exists between current behaviour and the arbitrage
# ceiling. Deliberately a simplification (doesn't replicate SoC-taper,
# the household floor, or price-priority partial allocation - those
# live only in the real decision tree, this is a twin, not a full
# duplicate) - documented plainly wherever the result is shown.
DIGITAL_TWIN_HORIZON_HOURS = 48

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

# Maps the final coordinator.last_reason (decided only after headroom/
# SoC/price-priority checks run) to the mode that was actually applied
# this tick - used to correct last_expected_mode after the fact
# (v0.63.20). last_expected_mode is set early, from the price check
# alone, before those later checks can downgrade an "expensive, should
# discharge" guess back to smart - without this correction, the
# displayed "Verwachte modus" could disagree with what was actually
# decided.
REASON_TO_MODE = {
    "expensive_quarter": OPTION_MANUAL,
    "expensive_quarter_soc_protected": OPTION_SMART,
    "negative_price": OPTION_MANUAL,
    "emergency_low_battery": OPTION_MANUAL,
    "grid_charging_low_solar": OPTION_MANUAL,
    "grid_charging_low_solar_extra_dip": OPTION_MANUAL,
    "discharging_window": OPTION_SMART_DISCHARGING,
    "arbitrage_solar_capture": OPTION_SMART,
    "default_smart": OPTION_SMART,
}
