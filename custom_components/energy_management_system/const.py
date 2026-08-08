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

# Achtertuin-temperatuursensor (v0.63.95, gevraagd: "zijn er zaken
# waardoor ik de voorspelling kan verbeteren" - de gebruiker heeft een
# eigen fysieke buitentemperatuursensor, nauwkeuriger voor de eigen
# locatie dan een regionale weerentiteit). Optioneel - zonder
# configuratie blijft alles exact zoals voorheen (weerentiteit als
# enige bron, geen bias-correctie).
CONF_BACKYARD_TEMPERATURE_SENSOR = "backyard_temperature_sensor_entity"

# CO2-intensiteit van het net (v0.63.101, gevraagd: "zaken voor een
# typisch EMS welke we kunnen toevoegen"). Optioneel - een externe
# entiteit zoals ElectricityMaps of CO2 Signal die de actuele
# CO2-intensiteit van het net rapporteert (g CO2/kWh). Zonder
# configuratie blijft alles exact zoals voorheen.
CONF_CO2_INTENSITY_SENSOR = "co2_intensity_sensor_entity"
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

# Maximale bijdrage die ÉÉN dag aan de CUSUM-accumulator mag leveren
# (v0.63.99, gevraagd tijdens een diagnostiek-review: CV-ketel en 5
# "Eetkamer lamp"-sensoren bleven aanhoudend "mogelijk defect" tonen).
# Gevonden: een enkele, geïsoleerde uitschieterdag (bijv. 45W tegen een
# referentie van 6,2W, mogelijk een eenmalige gebeurtenis zoals extra
# warmwaterverbruik) leverde zonder plafond een ONGEPLAFONNEERDE
# bijdrage van >6 in één klap - ver boven de alarmdrempel (1,0) - en
# liet het alarm daardoor langdurig afgaan, ook al was het structurele
# gemiddelde over de hele periode maar +2,4%. Dit plafond zorgt dat een
# geïsoleerde uitschieter maximaal de helft van de alarmdrempel in één
# klap kan bijdragen - een structurele, aanhoudende afwijking (die dag
# na dag boven de marge blijft) bouwt de accumulator nog steeds normaal
# op en laat het alarm terecht afgaan; een eenmalige uitschieter niet
# meer in zijn eentje.
NILM_CUSUM_MAX_DAILY_CONTRIBUTION = 0.5

# Auto-reset bij aanhoudende terugkeer naar normaal gedrag (v0.63.100,
# gevraagd: "kan dit live zelf oplossen" - het plafond hierboven
# voorkomt toekomstige uitschieter-gestuurde alarmen, maar een al
# opgebouwde, verouderde accumulator (van vóór het plafond, of van een
# structurele periode die inmiddels echt voorbij is) bouwt via de
# normale, kleine dagelijkse afbouw extreem traag af - doorgerekend
# voor het gerapporteerde CV-ketel-scenario zou dat bijna 90 dagen
# duren. Zodra een apparaat dit aantal opeenvolgende dagen ACHTEREEN
# een genuine terugkeer naar normaal laat zien (dagwaarde op of onder
# de referentie, niet slechts "iets minder ver boven de marge" - dus
# vóór het NILM_CUSUM_MAX_DAILY_CONTRIBUTION-plafond wordt toegepast),
# wordt de accumulator direct volledig gereset in plaats van traag te
# laten wegebben. Bewust een paar dagen vereist (niet na 1 dag al
# resetten) om te voorkomen dat een kortstondige dip het alarm
# onterecht meteen wegneemt terwijl het probleem zelf nog speelt.
NILM_CUSUM_RESET_STREAK_DAYS = 5

# Drempel voor de "ongewoon veel onbevestigde kandidaten"-aandachtspunt
# in de diagnostiek-samenvatting (v0.63.108, gevraagd: "kun je zien te
# detecteren in de diagnose" - naar aanleiding van 51 onbevestigde
# kandidaten die eerder deze sessie een reeks structurele
# uitsluitingspatronen bleek te missen). Bewust een aantal, geen
# poging tot precisie - puur een signaal om even naar te kijken.
NILM_CANDIDATE_COUNT_ATTENTION_THRESHOLD = 15

# Accu-gezondheid over de lange termijn: cyclus-telling en geschatte
# capaciteitsdegradatie (v0.63.101, gevraagd: "zaken voor een typisch
# EMS welke we kunnen toevoegen"). Bewust en duidelijk een RUWE
# SCHATTING, geen gemeten waarde - deze integratie heeft geen manier om
# de werkelijke accucapaciteit te meten, alleen een generiek,
# lineair model op basis van het aantal volledige cycli. Standaard-
# aanname (4000 cycli tot 80% capaciteit) is representatief voor
# LFP-chemie (zoals de Zendure SolarFlow-serie), maar KAN afwijken van
# de daadwerkelijke cel-specificaties - vandaar altijd nadrukkelijk
# gelabeld als schatting in de UI.
BATTERY_CYCLES_TO_80_PERCENT_CAPACITY = 4000

# Structurele NILM-uitsluitingspatronen (v0.63.89, gevraagd: "alles
# waar fase 1 bij staat mag sowieso uitgesloten worden net als
# solaredge en zendure entiteiten"; uitgebreid in v0.63.103, gerapporteerd:
# "elke keer terug krijg onbevestigde kandidaten na herstart" - bleek de
# batterij zelf onder de merknaam "SolarFlow" (niet "zendure") te
# verschijnen in entity-namen, plus Solcast-voorspellingssensoren en
# gespiegelde accu-signalen ("... (omgekeerd)") die als losse
# "apparaten" werden voorgesteld; verder uitgebreid in v0.63.106,
# gerapporteerd: "Solar Production entiteiten en P1 meter vermogen
# mogen sowieso uitgesloten worden" - "fase 1" bleek niet "fase 2"/
# "fase 3" te dekken (P1 meter Vermogen fase 3 glipte erdoor), en een
# ANDERE zon-voorspellingsintegratie ("Solar production forecast",
# andere naamgeving dan "solcast") werd nog niet herkend). Substring-
# match (kleine letters) tegen zowel de entity_id als de friendly_name
# - anders dan `_nilm_excluded_entity_ids()` (exacte match tegen
# specifiek geconfigureerde entiteiten), dit is een structurele,
# patroon-gebaseerde uitsluiting die geen losse afwijzing per sub-
# fase-sensor of accu-/omvormer-signaal meer vereist.
NILM_PATTERN_EXCLUDED_KEYWORDS = (
    "fase 1",
    "fase_1",
    "fase 2",
    "fase_2",
    "fase 3",
    "fase_3",
    "solaredge",
    "zendure",
    "solarflow",
    "solcast",
    "solar production",
    "p1 meter",
    "(omgekeerd)",
)

# NILM-duplicaatdetectie (v0.63.91, gevraagd na een diagnostiek-review
# waarbij 5 "Eetkamer lamp"-sensoren identieke vermogensgeschiedenis
# bleken te delen - vermoedelijk hetzelfde fysieke circuit onder
# meerdere HA-entiteiten). Twee bevestigde apparaten worden als
# waarschijnlijk duplicaat gemarkeerd als hun dagelijkse-gemiddelde-
# geschiedenis over minimaal dit aantal gedeelde dagen steeds binnen
# de relatieve tolerantie van elkaar ligt.
NILM_DUPLICATE_MIN_SHARED_DAYS = 3
NILM_DUPLICATE_TOLERANCE_FRACTION = 0.02

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

# v0.63.118: hetzelfde sleuf-principe voor waarschijnlijke
# duplicaatparen. Eén sleuf, om dezelfde reden als hierboven: een paar
# toont TWEE apparaatnamen naast elkaar, dus de beschikbare breedte is
# hier nog schaarser dan bij een losse kandidaat.
NILM_DUPLICATE_DASHBOARD_SLOT_COUNT = 1

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

# Geleerde bias-correctie op de weersvoorspelling (v0.63.95, gevraagd:
# "zijn er zaken waardoor ik de voorspelling kan verbeteren" - de
# gebruiker heeft een eigen achtertuin-temperatuursensor). Elke keer
# dat de uurlijkse voorspelling ververst wordt (om de
# CLIMATE_FORECAST_FETCH_INTERVAL_MINUTES), wordt de eerste
# (dichtstbijzijnde) voorspelde waarde vergeleken met de actuele
# achtertuinsensor-meting op datzelfde moment - dat verschil (°C,
# additief, niet procentueel: temperatuur kent geen natuurlijke
# nulpuntschaal waarop een percentage zinvol is) wordt bijgehouden in
# een rollend venster en toegepast op de HELE 24-uurs-voorspelling,
# niet alleen het startpunt - corrigeert zo systematisch voor een
# structurele afwijking van de geconfigureerde weerbron/locatie.
CLIMATE_FORECAST_BIAS_HISTORY_LENGTH = 100
CLIMATE_FORECAST_BIAS_MIN_SAMPLES = 5

# Uitschieter-filter voor de achtertuinsensor (v0.63.96, gerapporteerd
# met grafiek: de sensor kan 's ochtends kort in direct zonlicht
# hangen, wat een plotselinge, kortstondige sprong in de gemeten
# temperatuur veroorzaakt - de behuizing warmt zelf op, los van de
# werkelijke luchttemperatuur). Een sprong die de plausibele
# afkoel/opwarm-snelheid van buitenlucht ver overschrijdt, wordt pas
# vertrouwd als hij minstens dit aantal minuten aanhoudt - een
# kortstondige zonneflits zakt vanzelf weer terug voordat dit venster
# verstrijkt en wordt dan genegeerd; een echte, aanhoudende
# temperatuurverandering (bijv. een koufront) wordt na dit venster
# alsnog geaccepteerd.
BACKYARD_TEMP_MAX_PLAUSIBLE_RATE_C_PER_HOUR = 4.0
BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES = 45
# Marge waarbinnen een nieuwe uitschietende meting als "dezelfde
# uitschieter" telt (i.p.v. een compleet nieuwe, aparte gebeurtenis) -
# zodat kleine meetruis tijdens het wachten op bevestiging de teller
# niet steeds laat resetten.
BACKYARD_TEMP_SPIKE_TOLERANCE_C = 1.0

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

# --- Einde salderen (v0.63.117) ---
# Tot en met de salderingsdatum levert een teruggeleverde kWh exact
# hetzelfde op als een ingekochte kWh kost (de teruglevering wordt
# weggestreept tegen de inkoop, inclusief energiebelasting en BTW).
# Daarna vervalt dat: teruglevering wordt dan afgerekend tegen een
# apart, veel lager teruglevertarief - de energiebelasting krijg je er
# niet meer via de saldering "terug". Dat verandert de economie van de
# accu fundamenteel: PV-energie in de accu stoppen kost dan niet langer
# de volle inkoopprijs aan gederfde teruglevering, maar slechts het
# lage teruglevertarief - waardoor opslaan juist veel aantrekkelijker
# wordt dan onder saldering.
#
# `CONF_SALDEREN_END_DATE` is de LAATSTE dag waarop salderen nog geldt
# (ISO-datum). Configureerbaar, niet hard ingebakken, omdat politiek
# uitstel/vervroeging in het verleden al meerdere keren is voorgekomen.
CONF_SALDEREN_END_DATE = "salderen_end_date"
DEFAULT_SALDEREN_END_DATE = "2026-12-31"

# Welk attribuut van de prijssensor het teruglevertarief NA saldering
# benadert. Standaard de kale marktprijs zonder energiebelasting
# (`price_tax_excluded`) - dat is precies het deel dat je na saldering
# nog vergoed krijgt, terwijl inkoop wél belast blijft.
CONF_FEEDIN_PRICE_ATTRIBUTE = "feedin_price_attribute"
DEFAULT_FEEDIN_PRICE_ATTRIBUTE = PRICE_ATTRIBUTE_EXCL_TAX

# Vaste terugleverkosten per teruggeleverde kWh (EUR/kWh), na saldering
# door veel leveranciers in rekening gebracht. Wordt van de
# terugleverwaarde afgetrokken. Standaard 0 - de gebruiker vult in wat
# het eigen contract zegt, dit is niet te raden.
CONF_FEEDIN_COST_EUR_PER_KWH = "feedin_cost_eur_per_kwh"
DEFAULT_FEEDIN_COST_EUR_PER_KWH = 0.0

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
# v0.63.121, twee keer waargenomen in de praktijk: "slecht (0.0%, 1
# metingen)" en "verminderd (50.0%, 2 metingen)". Bij zo weinig
# metingen zegt dat percentage niets - één ongelukkige meting maakt het
# meteen 0% of 50%, en dat trok de systeemstatus onterecht omlaag. Het
# venster loopt vlak na elke herstart onvermijdelijk door die fase
# heen. Onder deze drempel wordt er dus GEEN oordeel geveld (score en
# label blijven leeg) in plaats van een oordeel dat toevallig klopt.
MEASUREMENT_QUALITY_MIN_SAMPLES = 10

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

# --- Accu-koeling (v0.63.122) ---------------------------------------
# Overgenomen uit een losse HA-automatisering ("Accu: Temperatuurbeheer
# Thuisaccu (Buiten) - PRO v9") die de gebruiker zelf had uitgewerkt en
# getuned. Tot v0.63.121 stond die bewust BUITEN deze integratie om de
# complexiteit te beperken; op verzoek alsnog geïntegreerd - "het heeft
# mijn inziens toch met de accu te maken", en dat klopt: het is de enige
# aansturing die direct met de accu samenhangt.
#
# De drempels hieronder zijn EXACT die van de automatisering. Er zit
# bewust hysterese tussen aan- en uitschakelen (delta 5 vs 2, accu 35 vs
# 33, vermogen 500 vs 300): zonder die marge zou de ventilator rond een
# enkele drempel blijven pendelen.
CONF_BATTERY_TEMPERATURE_SENSOR = "battery_temperature_sensor_entity"
CONF_BATTERY_COOLING_FAN_SWITCH = "battery_cooling_fan_switch_entity"
# Optioneel: een eigen buitentemperatuursensor specifiek voor deze
# vergelijking. Leeg laten betekent terugvallen op de al bestaande
# live-buitentemperatuur (achtertuinsensor, anders de weerentiteit).
CONF_BATTERY_COOLING_OUTDOOR_SENSOR = "battery_cooling_outdoor_sensor_entity"

# AANZETTEN zodra één van deze vier waar is:
#   1. accu staat meer dan 5°C boven buiten
BATTERY_COOLING_ON_DELTA_C = 5.0
#   2. accu is absoluut te warm
BATTERY_COOLING_ON_ABSOLUTE_C = 35.0
#   3. noemenswaardig laden/ontladen én accu al 2°C boven buiten
BATTERY_COOLING_ON_POWER_W = 500.0
BATTERY_COOLING_ON_POWER_DELTA_C = 2.0
#   4. zwaar laden/ontladen én accu al boven 30°C
BATTERY_COOLING_ON_HIGH_POWER_W = 1500.0
BATTERY_COOLING_ON_HIGH_POWER_TEMP_C = 30.0

# UITZETTEN alleen als ALLE drie tegelijk gelden - één voorwaarde die
# terugvalt is niet genoeg, anders slaat de ventilator af terwijl er nog
# een andere reden is om te blijven koelen.
BATTERY_COOLING_OFF_DELTA_C = 2.0
BATTERY_COOLING_OFF_POWER_W = 300.0
BATTERY_COOLING_OFF_ABSOLUTE_C = 33.0

# Toestanden waarin de ventilatorschakelaar niets zinnigs zegt - dan
# wordt er niet geschakeld (niet gokken op "hij zal wel uit staan").
BATTERY_COOLING_FAN_UNAVAILABLE_STATES = {"unknown", "unavailable", None}

# Hoeveel aan/uit-schakelingen van de koelventilator bewaard blijven
# voor het dashboard/de diagnostiek.
BATTERY_COOLING_HISTORY_LENGTH = 20

# --- Accu-modulegezondheid (v0.63.123) -------------------------------
# Per accumodule zijn er metingen beschikbaar die iets zeggen over de
# gezondheid van dat specifieke pakket: hoogste/laagste celspanning,
# hoogste celtemperatuur, SoC en vermogen.
#
# Bewust LIJSTEN in plaats van losse velden per module: de volgorde
# bepaalt het modulenummer (eerste entiteit = module 1). Dat schaalt naar
# elk aantal modules zonder dat de configuratie per uitbreiding moet
# worden aangepast - een SolarFlow 2400 AC heeft er drie, maar dat is
# geen aanname die hier hoort te staan.
CONF_BATTERY_MODULE_CELL_VOLTAGE_MAX_SENSORS = (
    "battery_module_cell_voltage_max_sensor_entities"
)
CONF_BATTERY_MODULE_CELL_VOLTAGE_MIN_SENSORS = (
    "battery_module_cell_voltage_min_sensor_entities"
)
CONF_BATTERY_MODULE_TEMPERATURE_SENSORS = (
    "battery_module_temperature_sensor_entities"
)
CONF_BATTERY_MODULE_SOC_SENSORS = "battery_module_soc_sensor_entities"
CONF_BATTERY_MODULE_POWER_SENSORS = "battery_module_power_sensor_entities"

# Celspanningsverschil (hoogste - laagste) binnen één module. Bij LFP is
# dit dé standaardindicator voor balans/veroudering: loopt het verschil
# structureel op, dan blijft er een cel achter. Absolute drempels zijn
# HEURISTIEK, geen fabrieksspecificatie - een gezond, gebalanceerd pakket
# blijft er in het vlakke midden ruim onder, en aanhoudende waarden
# hierboven verdienen aandacht (niet: zijn direct gevaarlijk).
BATTERY_MODULE_CELL_DELTA_ATTENTION_V = 0.10
BATTERY_MODULE_CELL_DELTA_SERIOUS_V = 0.20

# Absolute celtemperatuur waarboven het vermelden waard is.
BATTERY_MODULE_TEMPERATURE_ATTENTION_C = 40.0

# Onderlinge spreiding tussen modules. Diagnostisch sterker dan welke
# absolute waarde ook: de modules draaien onder identieke
# omstandigheden, dus een structureel verschil is een eigenschap van die
# ene module en niet van het weer, de SoC of de belasting.
BATTERY_MODULE_TEMPERATURE_SPREAD_ATTENTION_C = 5.0
BATTERY_MODULE_SOC_SPREAD_ATTENTION_PERCENT = 10.0

# LFP heeft een vlakke spanningscurve in het midden en steile uiteinden,
# waardoor het celspanningsverschil sterk SoC-afhankelijk is. De
# DIFFERENTIELE vergelijking (module t.o.v. het gemiddelde van alle
# modules op hetzelfde moment) heeft daar geen last van - alle modules
# zitten immers op vrijwel dezelfde SoC. De absolute delta wordt daarom
# per SoC-bucket bijgehouden, puur voor weergave/referentie.
BATTERY_MODULE_SOC_BUCKET_SIZE_PERCENT = 10

# Minimaal aantal metingen op een dag voordat die dag als geldig
# datapunt telt - anders zou een herstart vlak voor middernacht een
# dagwaarde op basis van twee metingen in de leergeschiedenis zetten.
BATTERY_MODULE_MIN_SAMPLES_PER_DAY = 20

# CUSUM-drift op de dagelijkse mediaan van de afwijking t.o.v. de andere
# modules. Slack = de normale, onschuldige ruis die genegeerd wordt;
# alleen wat daarboven uitkomt telt op. Drempel = waar het een melding
# wordt. Per grootheid apart, want de eenheden verschillen.
BATTERY_MODULE_CUSUM_SLACK_V = 0.005
BATTERY_MODULE_CUSUM_THRESHOLD_V = 0.05
BATTERY_MODULE_CUSUM_SLACK_C = 0.5
BATTERY_MODULE_CUSUM_THRESHOLD_C = 5.0
BATTERY_MODULE_CUSUM_SLACK_PERCENT = 0.5
BATTERY_MODULE_CUSUM_THRESHOLD_PERCENT = 5.0

# Hoeveel dagen geleerde geschiedenis per module/grootheid.
BATTERY_MODULE_HISTORY_DAYS = 60

# Onder dit vermogen wordt de accu als "in rust" beschouwd voor de
# WEERGAVE (v0.63.127) - een stilstaande accu schommelt altijd een paar
# watt, en dan "laden 3 W" tonen suggereert een richting die er niet is.
# Puur cosmetisch; raakt geen enkele beslissing.
MIN_BATTERY_POWER_IDLE_W = 25.0

# Hoeveel het geïntegreerde debiet van de meterstand mag afwijken
# voordat de volumebepaling als verdacht geldt (v0.63.132). Ruim
# genomen: de meterstand heeft zelf een resolutie van ongeveer een liter,
# dus bij korte stoten is een verschil van tientallen procenten normaal
# zonder dat er iets mis is.
WATER_VOLUME_AGREEMENT_TOLERANCE = 0.25

# --- Digital Twin: nauwkeurigheidsmeting (v1.0.1) --------------------
# Tot nu toe stond bij de Digital Twin "nauwkeurigheid t.o.v. het
# daadwerkelijke resultaat wordt niet bijgehouden" - eerlijk, maar het
# kan wél: de twin voorspelt een SoC, en die is later gewoon na te meten.
#
# Techniek: dezelfde "leg een voorspelling vast, controleer 'm later"
# aanpak als de zonvoorspelling-tracker. Er wordt niet bij elke tick een
# voorspelling weggeschreven - dat zou binnen een dag honderden sterk
# overlappende metingen opleveren die allemaal vrijwel hetzelfde zeggen.
DIGITAL_TWIN_ACCURACY_HORIZON_HOURS = 6
DIGITAL_TWIN_ACCURACY_QUEUE_INTERVAL_MINUTES = 60

# Een voorspelling die door een herstart of hiaat pas veel te laat wordt
# afgerekend, zegt niets meer over het moment waarvoor ze bedoeld was.
DIGITAL_TWIN_ACCURACY_MAX_LATE_MINUTES = 45

# Hoeveel afgeronde vergelijkingen bewaard blijven, en hoeveel er nodig
# zijn voordat er een oordeel wordt geveld. Zelfde principe als
# MEASUREMENT_QUALITY_MIN_SAMPLES: liever geen oordeel dan een oordeel
# op twee metingen.
DIGITAL_TWIN_ACCURACY_HISTORY_LENGTH = 60
DIGITAL_TWIN_ACCURACY_MIN_SAMPLES = 8

# De gemiddelde absolute fout wordt afgezet tegen de BRUIKBARE
# accucapaciteit, niet tegen een vast aantal kWh - een fout van 1 kWh
# betekent iets heel anders bij een accu van 2 kWh dan bij een van 7,5.
DIGITAL_TWIN_ACCURACY_GOOD_FRACTION = 0.10
DIGITAL_TWIN_ACCURACY_USABLE_FRACTION = 0.20

# --- Weather Ensemble: overeenstemmingsmeting (v1.0.2) ---------------
# De ensemble meldt de ACTUELE bewolking, geen voorspelling - "hoe
# nauwkeurig is de voorspelling" is hier dus de verkeerde vraag. Wat wél
# te meten valt: zegt de ensemble iets dat klopt met wat de panelen
# werkelijk doen? Elke geldige waarneming (overdag, met een zinvolle
# Solcast-verwachting) wordt geclassificeerd als "eens" of "oneens", en
# daarvan wordt het slagingspercentage bijgehouden.
#
# Hergebruikt exact dezelfde drempels als de bestaande
# onenigheids-signalering - één definitie, geen tweede die ernaast kan
# gaan lopen.
WEATHER_ENSEMBLE_AGREEMENT_HISTORY_LENGTH = 200
WEATHER_ENSEMBLE_AGREEMENT_MIN_SAMPLES = 20

# Boven dit percentage overeenstemming heet de ensemble betrouwbaar,
# daaronder tot de tweede drempel bruikbaar. Ruim genomen: bewolking en
# PV-opbrengst hangen samen maar zijn niet hetzelfde, dus perfecte
# overeenstemming hoort niet verwacht te worden.
WEATHER_ENSEMBLE_AGREEMENT_GOOD_PERCENT = 80.0
WEATHER_ENSEMBLE_AGREEMENT_USABLE_PERCENT = 60.0

# --- Volledige toestandspersistentie (v1.0.4) ------------------------
# Gevraagd: "algeheel geen verliezen na een herstart". Een inventarisatie
# van alle 286 attributen in de coordinator liet zien dat het overgrote
# deel elke tick opnieuw wordt berekend (last_*, projecties, live
# metingen) - dat verliezen is onschadelijk. Maar een deel is echt
# OPGEBOUWD, en dat verdween tot v1.0.3 bij elke herstart.
#
# Bewust één gedeelde Store in plaats van tientallen losse
# RestoreEntity-paden. Twee lessen uit dit project komen daarin samen:
# entiteit-attributen hebben een recorder-limiet van 16 KB (v0.63.66),
# en de laadvolgorde moet vóór platform-setup liggen (v0.63.115).
#
# Bewust een EXPLICIETE lijst en niet "alles opslaan": een per-tick
# berekende waarde terugzetten zou een verouderde momentopname tonen
# alsof die actueel is, wat erger is dan hem opnieuw laten berekenen.

# Gewone JSON-waarden (getallen, lijsten, dicts).
PERSISTED_PLAIN_FIELDS = (
    # Geleerde/opgebouwde geschiedenis
    "battery_module_health",
    "energy_balance_error_history",
    "energy_balance_method_version",
    "mode_change_log",
    "discharge_floor_events",
    "dishwasher_cycle_duration_history",
    "dishwasher_usage_hourly_history",
    "washing_machine_cycle_duration_history",
    "washing_machine_usage_hourly_history",
    "living_room_temp_bucket_humidity",
    "battery_cooling_history",
    "kalman_divergence_history",
    # v1.3.1: de geleerde blootstellingsrichting van de achtertuinsensor.
    # Vijf flitsen zijn nodig voordat die iets doet; zonder bewaren zou
    # die telling na elke herstart opnieuw beginnen.
    "backyard_sun_exposure_azimuths",
    # v1.5.2: twintig waarnemingen bij daglicht per bron voordat er iets
    # te zeggen valt. Zonder bewaren zou die telling na elke herstart
    # opnieuw beginnen.
    "weather_source_agreement",
    # v1.4.0: het PV-installatieprofiel bouwt over WEKEN op (vijf
    # heldere dagen voor een eerste schatting, twintig voor een
    # betrouwbare). Zonder bewaren zou die telling na elke herstart
    # opnieuw beginnen en nooit iets opleveren.
    "pv_peak_azimuth_history",
    # v1.8.0: dagtotalen stroom en gas. Zonder bewaren zou er nooit een
    # week-, maand- of jaarcijfer ontstaan.
    "daily_cost_history",
    # v1.9.0: de dagsamenvattingen. Het beslislogboek bewust NIET: dat
    # is een momentopname van twee dagen die na een herstart weinig
    # waarde meer heeft, en het zou de opslag met honderden regels per
    # herstart belasten.
    "daily_report_history",
    # v1.8.2: welke sensor hoe vaak wegviel. Zonder bewaren zou de
    # melding na een herstart weer generiek worden, terwijl de
    # foutreeks zelf wél bewaard blijft.
    "balance_missing_by_entity",
    "pv_azimuth_performance",
    # Meldingen (v1.2.0): de aan/uit-standen zijn een gebruikerskeuze en
    # mogen bij een herstart niet terugspringen naar de standaard. De
    # verzendmomenten horen er ook bij, anders zou het dempingsvenster na
    # elke herstart opnieuw beginnen en kon dezelfde melding alsnog
    # meteen weer afgaan.
    "notification_enabled",
    "notification_last_sent",
    "notification_history",
    "notifications_master_enabled",
    # v1.5.1: welke modules al klaar waren, zodat alleen de OVERGANG
    # wordt gemeld. Zonder bewaren zou elke herstart die overgang
    # opnieuw melden.
    "previously_ready_modules",
    # v1.6.2: welke toestandsmeldingen actief zijn. Zonder bewaren zou
    # een herstart als "opgelost" gelden en meteen een herstelmelding
    # sturen voor een probleem dat nog gewoon speelt.
    "notification_active_conditions",
    # Cumulatieve financiële en KPI-tellers
    "actual_cost_today_eur",
    "actual_cost_current_month_eur",
    "actual_cost_all_time_eur",
    "counterfactual_cost_today_eur",
    "counterfactual_cost_current_month_eur",
    "counterfactual_cost_all_time_eur",
    "charge_pv_kwh_total",
    "charge_grid_kwh_total",
    "discharge_export_kwh_total",
    "forgone_feedin_eur_total",
    "co2_emitted_today_kg",
    "pv_production_today_kwh",
    "pv_export_today_kwh",
    "gross_consumption_today_kwh",
    "grid_import_today_kwh",
    "peak_power_today_w",
    "water_sessions_today_l",
    "water_sessions_today_count",
)

# Datum-sleutels van de dag/maand-rollovers. Zonder deze zouden de
# "vandaag"-tellers hierboven wél terugkomen maar bij de eerstvolgende
# tick meteen worden gewist, omdat de coordinator dan denkt dat er een
# nieuwe dag is begonnen - dan was het terugzetten zinloos geweest.
PERSISTED_DATE_FIELDS = (
    "_water_sessions_day_key",
    "_battery_module_day_key",
    "_peak_power_day_key",
    "_counterfactual_day_key",
    "_self_sufficiency_day_key",
    "_co2_day_key",
)

PERSISTED_INT_FIELDS = (
    "_peak_power_month_key",
    "_counterfactual_month_key",
    "_summary_month_key",
)

PERSISTED_DATETIME_FIELDS = (
    "battery_cooling_last_change",
)

# De opslag wordt vertraagd weggeschreven: een tick kan meerdere velden
# raken, en bij een live listener (water, accu-koeling) zelfs meermaals
# per minuut. Zonder vertraging zou dat onnodig veel schrijfacties naar
# de SD-kaart/SSD opleveren.
PERSISTED_STATE_SAVE_DELAY_SECONDS = 30

# Minimale ABSOLUTE afwijking voordat iets überhaupt een uitschieter kan
# zijn (v1.0.6, gerapporteerd: "Uitschieter genegeerd: 24.3°C wijkt te
# snel af van 24.7°C").
#
# De snelheidstoets alleen is onbruikbaar op korte intervallen: bij een
# tick van 5 minuten komt 0,4 °C neer op 4,8 °C/uur en overschrijdt
# daarmee BACKYARD_TEMP_MAX_PLAUSIBLE_RATE_C_PER_HOUR - terwijl 0,4 °C
# gewoon meetruis is. Hoe korter het interval, hoe absurder: over één
# minuut is zelfs 0,07 °C al "te snel". Een zonneflits herken je aan een
# GROTE sprong in korte tijd, dus beide voorwaarden moeten gelden.
#
# 1,5 °C is ruim boven de ruis van een typische buitensensor en ruim
# onder de sprong die direct zonlicht op de behuizing veroorzaakt.
BACKYARD_TEMP_SPIKE_MIN_DEVIATION_C = 1.5

# --- Kalman: levert filteren hier eigenlijk iets op? (v1.0.7) --------
# Gevraagd n.a.v. "Kalman filtering — klaar — alle 3 filters
# geconvergeerd": doen we hier actief iets mee, en wat zou het
# betekenen als wel?
#
# "Geconvergeerd" zegt alleen dat de interne onzekerheid van het filter
# is uitgezakt - niet dat de gefilterde waarde BETER is dan de ruwe. Er
# was geen enkel cijfer dat die vraag kon beantwoorden. Deze meting
# levert dat cijfer: hoeveel wijkt gefilterd af van ruw, over tijd?
#
# Is die afwijking verwaarloosbaar, dan is filteren zinloos en is de
# discussie klaar. Is ze groot, dan pas is de vervolgvraag interessant -
# en dan nog uitsluitend asymmetrisch (zie README), want een
# achterlopende SoC-schatting die MEER energie voorspiegelt dan er is,
# is precies het faalpatroon waar de tekort-reserve tegen beschermt.
KALMAN_DIVERGENCE_HISTORY_LENGTH = 500
KALMAN_DIVERGENCE_MIN_SAMPLES = 50

# Onder dit percentage van de typische signaalgrootte is het verschil
# tussen ruw en gefilterd te klein om er iets aan te hebben.
KALMAN_DIVERGENCE_NEGLIGIBLE_PERCENT = 1.0
KALMAN_DIVERGENCE_MEANINGFUL_PERCENT = 5.0

# --- Beslislogica na het einde van saldering (v1.1.0) ----------------
# Tot en met de salderingsdatum verandert er NIETS: alle logica hieronder
# hangt achter `_is_salderen_active(now)` en is tot die tijd volledig
# inert. Dat is bewust, en er zijn tests die het vastleggen.
#
# Waarom het daarna wél moet veranderen: onder saldering levert een
# teruggeleverde kWh evenveel op als een ingekochte kost, dus is het om
# het even of je energie exporteert of zelf verbruikt. Daarna niet meer -
# exporteren levert het lage teruglevertarief op, terwijl diezelfde kWh
# thuis de volle (belaste) inkoopprijs bespaart. Dat verschil is de kern
# van alle keuzes hieronder.

# Hoeveel het huisverbruik hoogstens overschreden mag worden bij
# geforceerd ontladen na saldering. Precies op het verbruik mikken zou
# door meetruis en de vertraging van de omvormer steeds een beetje
# export of import opleveren; een kleine marge houdt de aansturing rustig
# zonder structureel te exporteren.
POST_SALDEREN_DISCHARGE_OVERSHOOT_W = 150.0

# Onder dit vermogen heeft geforceerd ontladen geen zin meer: de
# omvormer-verliezen wegen dan zwaarder dan de vermeden inkoop, en de
# accu leegtrekken voor een handvol watts kost meer dan het oplevert.
POST_SALDEREN_MIN_USEFUL_DISCHARGE_W = 100.0

# Minimaal zonoverschot voordat opvangen voorrang krijgt op verkopen.
# Ruim boven meetruis: bij een paar watt zou de beslissing heen en weer
# gaan tussen opvangen en ontladen.
POST_SALDEREN_MIN_SURPLUS_TO_CAPTURE_W = 150.0

# --- Klimaat: terugval voor de indicatieve reeks (v1.1.2) -----------
# Gerapporteerd: "Maar korte termijn zou toch op relatief korte termijn
# een indicatie geven?" Terecht - "indicatief" belooft juist snel iets,
# en dat gebeurde niet.
#
# Oorzaak: de celruimte is buitentemperatuur x rolluikstand x
# airco-status = 252 mogelijke cellen. Na vijf dagen draaien hadden er
# zes enige data en haalde er precies één de drempel van vijf metingen.
# De projectie loopt 24 uur vooruit langs telkens een ander
# buitentemperatuur-vakje, dus vrijwel elk uur viel terug op "bevriezen".
#
# De STRENGE reeks ("betrouwbaar") blijft exact zoals hij was - dat is
# juist zijn bestaansreden. De INDICATIEVE reeks mag terugvallen op een
# grovere samenvatting, want "indicatief" betekent nu eenmaal niet
# "bewezen voor precies deze combinatie".
#
# Volgorde van terugvallen, van dichtbij naar ver:
#   1. exact deze cel
#   2. naburige buitentemperatuur (+/- 1 bucket), zelfde rolluik + airco
#   3. zelfde buitentemperatuur, elke rolluik-/airco-stand
#   4. alles
# Stap 2 gaat bewust vóór stap 3: de rolluikstand bepaalt hoeveel zon er
# binnenvalt en heeft daarmee meer invloed op de opwarmsnelheid dan twee
# graden verschil buiten.
CLIMATE_RATE_NEIGHBOUR_BUCKETS = 1

# Minimale beweging van de beschikbare-energiesensor voordat de
# Kirchhoff-balanscheck iets te toetsen heeft (v1.1.3).
#
# Die sensor werkt veel trager bij dan de tick van vijf minuten. Stond
# hij stil, dan kwam het afgeleide accuvermogen op 0 uit terwijl de accu
# werkelijk vermogen leverde - en werd precies dat vermogen als "fout"
# geteld. Dat is geen sensorstoring maar een verschil in meetfrequentie.
# Staat de sensor stil, dan is er niets te controleren: geen slechte
# meting, maar géén meting.
ENERGY_BALANCE_MIN_DELTA_KWH = 0.005

# --- Meetfrequentie van bronsensoren (v1.1.4) ------------------------
# Gevraagd: "Had je dit eerder kunnen afvangen als de diagnostiek beter
# was?" Ja. De export toonde de UITKOMST (sensor-gezondheid 21%, een
# reeks foutwaarden) maar nergens hoe vaak elke bronsensor eigenlijk
# bijwerkt. Precies dat getal maakte het verschil tussen "de sensoren
# spreken elkaar tegen" en "de sensoren meten op een ander tempo" - en
# alleen de tweede was waar.
#
# Wordt nu per sensor bijgehouden: hoeveel ticks er zijn geweest en bij
# hoeveel daarvan de waarde daadwerkelijk veranderde. Een sensor die bij
# 10% van de ticks beweegt, is meteen herkenbaar als traag.
SENSOR_CADENCE_HISTORY_LENGTH = 300
SENSOR_CADENCE_MIN_SAMPLES = 30

# Onder dit percentage bewegingen heet een sensor traag ten opzichte van
# de tick - niet fout, maar wel iets waar afgeleide tempo's rekening mee
# moeten houden.
SENSOR_CADENCE_SLOW_PERCENT = 40.0

# --- Kirchhoff: minimuminterval tegen kwantisatieruis (v1.1.6) ------
# Gerapporteerd na de fix van v1.1.3: score nog steeds 20%. De
# resterende fouten lagen rond 880-1175 W, en dat bleek geen toeval.
#
# De beschikbare-energiesensor stapt in hele SoC-procenten. Bij ~7,7 kWh
# is dat ~0,077 kWh per stap. Zo'n stap over een interval van vijf
# minuten komt neer op ~920 W afgeleid vermogen - terwijl de drempel op
# 300 W ligt. De meting werd dus niet begrensd door de sensoren maar door
# de RESOLUTIE van de sensor gedeeld door een kort interval.
#
# v1.1.3 loste het stilstandsprobleem op, maar liet een beweging van
# 0,005 kWh al meetellen: ver onder één stap. Daardoor werd feitelijk
# elke stap meteen afgerekend, met de kwantisatieruis als uitkomst.
#
# Oplossing: hetzelfde principe als het klimaat-tempo, dat al over een
# anker van ~1 uur meet met exact deze redenering ("een tempo uit
# tick-tot-tick-verschillen is numeriek instabiel"). Over 30 minuten komt
# diezelfde stap uit op ~155 W en valt hij ruim binnen de drempel.
ENERGY_BALANCE_MIN_INTERVAL_MINUTES = 30

# Eigen bovengrens, los van MAX_HOUR_TRACKING_GAP_MINUTES (20 min): die
# is bedoeld voor energie-integratie en zou hier - lager dan het
# minimum - betekenen dat er nooit meer iets gemeten wordt.
ENERGY_BALANCE_MAX_INTERVAL_MINUTES = 120

# De meetmethode is tussen v1.1.2 en v1.1.6 twee keer wezenlijk
# veranderd. Oude metingen zijn met een andere methode tot stand gekomen
# en zeggen niets over de huidige; ze blijven anders in het venster van
# 20 hangen en drukken de score omlaag zonder dat er iets mis is. Bij een
# verandering van dit nummer wordt de geschiedenis eenmalig gewist.
ENERGY_BALANCE_METHOD_VERSION = 3

# Vanaf hoeveel procentpunt verschil tussen de weerbronnen het
# gemiddelde te weinig zegt om op te varen (v1.1.8). Twee bronnen die
# 0% en 51% melden geven precies hetzelfde gemiddelde als twee keer 25%,
# terwijl het eerste geval betekent dat er iets mis is met een bron.
WEATHER_ENSEMBLE_SPREAD_ATTENTION_PERCENT = 40.0

# --- Meldingen: register en schakelaars (v1.2.0) --------------------
# Gevraagd: "Ik wil nog een tabblad waar ik meldingen in en uit kan
# schakelen, dus je mag meerdere meldingen maken voor mijn iPhone, echter
# wil ik ze wel aan/uit kunnen zetten" - en daarna: "zoveel mogelijk
# relevante meldingen toevoegen".
#
# Tot nu toe hingen alle zeven bestaande meldingen aan één configuratie-
# veld: alles aan of alles uit. Elke melding krijgt nu een eigen
# schakelaar.
#
# Twee ontwerpkeuzes die het verschil maken tussen bruikbaar en
# wegswipen:
#
# 1. ALLEEN de bestaande zeven staan standaard AAN. Al het nieuwe begint
#    UIT. Twintig meldingen die zichzelf aanzetten is een garantie dat er
#    binnen een week niets meer van gelezen wordt - en dan is de hele
#    functie waardeloos.
# 2. Elke melding heeft een eigen DEMPINGSVENSTER. Vooral modus-
#    wijzigingen en sluipverbruik kunnen anders meerdere keren per uur
#    afgaan.
#
# Velden per melding: sleutel, label, uitleg, standaard aan/uit,
# dempingsvenster in minuten.
NOTIFICATION_TYPES: tuple[tuple[str, str, str, bool, int], ...] = (
    # --- bestaand gedrag, blijft standaard aan ---
    (
        "appliance_cheap_moment",
        "Goedkoop moment voor vaatwasser/wasmachine",
        "Wanneer een goedkoop prijsblok begint en het apparaat klaarstaat.",
        True,
        60,
    ),
    (
        "appliance_ready",
        "Apparaat klaar",
        "Wanneer de vaatwasser of wasmachine zijn cyclus heeft afgerond.",
        True,
        5,
    ),
    (
        "battery_cooling",
        "Accu-koeling aan/uit",
        "Wanneer de koelventilator van de thuisaccu schakelt.",
        True,
        15,
    ),
    (
        "sluipverbruik",
        "Mogelijk sluipverbruik",
        "Wanneer het basisverbruik structureel is opgelopen.",
        True,
        720,
    ),
    (
        "device_drift",
        "Mogelijk defect apparaat",
        "Wanneer een bevestigd NILM-apparaat aanhoudend meer verbruikt.",
        True,
        1440,
    ),
    (
        "mode_change",
        "Modus gewijzigd",
        "Wanneer de accu van bedrijfsmodus wisselt. Kan bij wisselende "
        "prijzen meerdere keren per dag afgaan.",
        True,
        30,
    ),
    # --- nieuw, standaard uit ---
    (
        "battery_wont_last_night",
        "Accu haalt de nacht niet",
        "Wanneer de verwachte overnachtingsbehoefte groter is dan wat er "
        "in de accu zit.",
        False,
        180,
    ),
    (
        "battery_full_with_sun",
        "Accu vol terwijl de zon nog schijnt",
        "Zonoverschot dat niet meer opgeslagen kan worden - een moment om "
        "een apparaat aan te zetten.",
        False,
        120,
    ),
    (
        "low_soc_before_peak",
        "Lage accustand vlak voor de avondpiek",
        "Wanneer er weinig in de accu zit terwijl het duurste blok "
        "eraan komt.",
        False,
        180,
    ),
    (
        "cheap_block_soon",
        "Goedkoopste blok begint bijna",
        "Een kwartier voordat het goedkoopste blok van vandaag begint.",
        False,
        120,
    ),
    (
        "negative_prices",
        "Negatieve prijzen op komst",
        "Wanneer er vandaag kwartieren met een negatieve prijs zijn.",
        False,
        720,
    ),
    (
        "exceptional_peak_price",
        "Uitzonderlijk duur kwartier vandaag",
        "Wanneer de dagpiek ver boven het gebruikelijke ligt.",
        False,
        720,
    ),
    (
        "solar_underperforming",
        "Zonopbrengst blijft achter",
        "Wanneer de opbrengst structureel onder de voorspelling blijft - "
        "kan op vervuiling of een storing wijzen.",
        False,
        360,
    ),
    (
        "low_solar_day",
        "Weinig-zon-dag herkend",
        "Zodat duidelijk is waarom er buiten het goedkope blok wordt "
        "bijgeladen.",
        False,
        720,
    ),
    (
        "sensor_unavailable",
        "Sensor valt weg",
        "Wanneer een geconfigureerde sensor onbereikbaar wordt.",
        False,
        120,
    ),
    (
        "integration_error",
        "Integratie loopt vast",
        "Wanneer er een fout optreedt die de aansturing kan blokkeren.",
        False,
        60,
    ),
    (
        "battery_module_drift",
        "Accumodule loopt uit de pas",
        "Wanneer een van de accumodules structureel afwijkt van de andere.",
        False,
        1440,
    ),
    (
        "module_became_ready",
        "Adviesmodule is klaar",
        "Wanneer een module genoeg data heeft verzameld om betrouwbaar te "
        "zijn.",
        False,
        1440,
    ),
    (
        "pv_orientation_mismatch",
        "PV-oriëntatie wijkt af van de opgegeven waarde",
        "Wanneer de afgeleide piekrichting structureel afwijkt van wat je "
        "hebt ingevuld - kan wijzen op beschaduwing, vervuiling of een "
        "uitgevallen streng.",
        False,
        1440,
    ),
    (
        "cost_mismatch",
        "Kostenberekening wijkt af van de afrekening",
        "Wanneer de eigen kostenberekening structureel afwijkt van wat "
        "Zonneplan werkelijk in rekening brengt.",
        False,
        720,
    ),
    (
        "daily_summary",
        "Dagoverzicht",
        "Een samenvatting van de dag: besparing, opbrengst, verbruik.",
        False,
        720,
    ),
    (
        "monthly_summary",
        "Maandoverzicht",
        "Een samenvatting aan het begin van een nieuwe maand.",
        False,
        1440,
    ),
)

# Hoeveel verzendmomenten bewaard blijven voor het tabblad.
# Hoeveel verzendmomenten bewaard blijven. Verhoogd in v1.6.3: met
# tweeëntwintig soorten en herstelmeldingen erbij was vijftig krap - een
# drukke dag vulde de lijst en duwde de melding waar je naar zocht er
# alweer uit.
NOTIFICATION_HISTORY_LENGTH = 200

# --- Eén betrouwbaarheidsschaal (v1.3.0) -----------------------------
# Gevraagd: "ik wil dit eigenlijk voor vele data welke wordt gecreeerd,
# hoe betrouwbaar is de gegenereerde data".
#
# Een inventarisatie liet zien dat er VIJF woordenlijsten naast elkaar
# bestonden voor in wezen dezelfde vraag: klaar/bijna_klaar/... voor de
# adviesmodules, goed/verminderd/slecht voor de sensor-gezondheid,
# betrouwbaar/indicatief voor de klimaatprojectie,
# verwaarloosbaar/klein/noemenswaardig voor de Kalman-divergentie, en
# volgt_de_tick/traag voor de meetfrequentie. Daardoor was in één
# oogopslag niet te zien waar je op kon varen.
#
# Zes niveaus. Vier daarvan vormen een oplopende ladder; de andere twee
# staan er bewust buiten omdat ze iets anders zeggen dan "meer of minder
# rijp".
RELIABILITY_NOT_CONFIGURED = "niet_geconfigureerd"
RELIABILITY_INSUFFICIENT = "onvoldoende_data"
RELIABILITY_INDICATIVE = "indicatief"
RELIABILITY_RELIABLE = "betrouwbaar"
RELIABILITY_UNRELIABLE = "onbetrouwbaar"
RELIABILITY_UNVERIFIABLE = "niet_toetsbaar"

# De ladder, van laag naar hoog. `niet_geconfigureerd` en
# `niet_toetsbaar` staan hier bewust NIET in: het eerste betekent "er is
# niets", het tweede "er valt principieel niets tegen af te zetten". Ze
# op de ladder zetten zou suggereren dat ze met wachten beter worden, en
# dat is precies de verwarring die het oude "structureel_beschikbaar"
# opriep.
RELIABILITY_LADDER = (
    RELIABILITY_INSUFFICIENT,
    RELIABILITY_INDICATIVE,
    RELIABILITY_RELIABLE,
)

RELIABILITY_LABELS = {
    RELIABILITY_NOT_CONFIGURED: (
        "⚪ niet geconfigureerd",
        "De benodigde sensor of instelling ontbreekt - er wordt niets "
        "berekend.",
    ),
    RELIABILITY_INSUFFICIENT: (
        "⏳ onvoldoende data",
        "Wordt nog verzameld. Er staat wel een getal, maar daar valt nog "
        "niet op te varen.",
    ),
    RELIABILITY_INDICATIVE: (
        "🟡 indicatief",
        "Bruikbaar als richting, maar nog niet genoeg onderbouwd om op te "
        "sturen.",
    ),
    RELIABILITY_RELIABLE: (
        "✅ betrouwbaar",
        "Genoeg data verzameld, of aantoonbaar nauwkeurig gebleken.",
    ),
    RELIABILITY_UNRELIABLE: (
        "⚠️ onbetrouwbaar",
        "Wél gemeten, en te ver naast de werkelijkheid gebleken. Niet op "
        "sturen.",
    ),
    RELIABILITY_UNVERIFIABLE: (
        "🔵 niet toetsbaar",
        "Werkt en rekent, maar er is geen werkelijkheid om het tegen af te "
        "zetten. Wachten maakt dit niet beter.",
    ),
}

# Vertaling van de oude woordenlijsten naar de schaal. Bewust een
# vertaling en geen hernoeming: de interne sleutels blijven zoals ze
# zijn, zodat bestaande dashboards, automatiseringen en tests blijven
# werken. Wat de gebruiker ziet is voortaan wél overal hetzelfde.
RELIABILITY_ALIASES = {
    # adviesmodules
    "klaar": RELIABILITY_RELIABLE,
    "bijna_klaar": RELIABILITY_INDICATIVE,
    "onvoldoende_data": RELIABILITY_INSUFFICIENT,
    "kwaliteit_te_laag": RELIABILITY_UNRELIABLE,
    "structureel_beschikbaar": RELIABILITY_UNVERIFIABLE,
    "niet_geconfigureerd": RELIABILITY_NOT_CONFIGURED,
    # sensor-gezondheid
    "goed": RELIABILITY_RELIABLE,
    "verminderd": RELIABILITY_INDICATIVE,
    "slecht": RELIABILITY_UNRELIABLE,
    # klimaatprojectie
    "betrouwbaar": RELIABILITY_RELIABLE,
    "indicatief": RELIABILITY_INDICATIVE,
    # Kalman-divergentie: dit is GEEN kwaliteitsoordeel over een getal
    # maar een meting of filteren iets zou opleveren. "Verwaarloosbaar"
    # betekent hier dat er niets te winnen valt, niet dat de data slecht
    # is - vandaar niet_toetsbaar in plaats van een ladderniveau.
    "verwaarloosbaar": RELIABILITY_UNVERIFIABLE,
    "klein": RELIABILITY_UNVERIFIABLE,
    "noemenswaardig": RELIABILITY_UNVERIFIABLE,
    # meetfrequentie
    "volgt_de_tick": RELIABILITY_RELIABLE,
    "traag": RELIABILITY_INDICATIVE,
}

# --- Zonnestand (v1.3.0) ---------------------------------------------
# Gevraagd: "Ik heb de sun integratie in HA, kan dit nog helpen bij
# verbeteringen?"
#
# De belangrijkste toepassing repareert een fout uit v1.1.9. Daar wordt
# de meetfrequentie van de PV-sensor overgeslagen als die op nul staat,
# omdat de nacht het cijfer vertekende. Maar dat gebruikt de sensor ZELF
# als criterium: hangt de SolarEdge-koppeling er midden op de dag uit,
# dan is de waarde 0, concludeert de code "geen zon dus terecht stil",
# en blijft de storing volledig onzichtbaar.
#
# Met de zonnestand klopt het wel: staat de zon boven de horizon, dan
# HOORT die sensor te bewegen, en een storing valt meteen op.
CONF_SUN_ELEVATION_SENSOR = "sun_elevation_sensor_entity"
CONF_SUN_PHASE_SENSOR = "sun_phase_sensor_entity"

# Boven deze hoogte gaat er noemenswaardig zonlicht op de panelen vallen.
# Bewust laag: het gaat er niet om of er veel opbrengst is, maar of de
# sensor überhaupt zou moeten bewegen.
SUN_DAYLIGHT_MIN_ELEVATION_DEGREES = 3.0

# `sun.sun` als vangnet wanneer er geen eigen sensor is geconfigureerd -
# die entiteit zit standaard in Home Assistant en vereist geen opzet.
SUN_FALLBACK_ENTITY = "sun.sun"

# --- Uitschieter-filter en de zonnestand (v1.3.1) --------------------
# Het filter op de achtertuinsensor bestaat expliciet voor "kortstondig
# direct zonlicht op de sensor". Tot nu toe wist het niet of de zon
# überhaupt scheen: een temperatuursprong om drie uur 's nachts kreeg
# dezelfde behandeling, inclusief de melding dat het mogelijk zonlicht
# was. Dat is aantoonbaar onjuist, en het kostte 45 minuten wachten voor
# een verandering die vrijwel zeker echt weer was.
#
# Staat de zon onder de horizon, dan kan een sprong geen zonneflits zijn.
# Voorzichtig blijven is nog steeds verstandig - een langsrijdende auto,
# een openslaande deur - maar veel korter.
BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES_NO_SUN = 10

# Als de zon wél schijnt maar ver buiten de richting staat waarin deze
# sensor eerder flitsen liet zien, is een sprong ook minder verdacht.
# De blootstellingsrichting wordt GELEERD uit waar de flitsen vandaan
# kwamen - de integratie weet immers niet waar de sensor hangt, en dat
# vragen zou een configuratieveld opleveren dat niemand goed invult.
BACKYARD_SUN_EXPOSURE_MIN_SAMPLES = 5
BACKYARD_SUN_EXPOSURE_MARGIN_DEGREES = 45.0
BACKYARD_SUN_EXPOSURE_HISTORY_LENGTH = 40

# --- PV-installatieprofiel (v1.4.0) ----------------------------------
# Gevraagd: "kun je nu ook zelf een berekening maken voor de verwachtte
# azimuth en andere relevante informatie hoe mijn PV installatie
# geinstalleerd ligt".
#
# Dat kan, want de zon vertelt het. Het vermogen piekt op het moment dat
# de zon recht voor de panelen staat, dus de zon-azimut bij de dagpiek
# is een directe schatting van de paneelrichting. En de verhouding
# tussen werkelijke en verwachte opbrengst per windrichting laat zien
# waar er beschaduwing is.
#
# HELLINGSHOEK is bewust NIET afgeleid. Dat vraagt maanden aan
# seizoensvariatie of aannames over instraling die deze integratie niet
# kan controleren, en een getal geven dat er zomaar 15 graden naast zit
# is erger dan geen getal.

# Alleen dagen meetellen waarop de opbrengst dicht genoeg bij de
# verwachting lag. Op een dag met wisselende bewolking ligt de piek waar
# het toevallig opklaarde, en dat zegt niets over de daklijn.
PV_GEOMETRY_MIN_CLEARNESS_RATIO = 0.7

# Vakjes van 10 graden azimut voor de beschaduwingskaart. Fijner maakt
# de vakjes te dun bezet; grover verbergt een smalle schoorsteenschaduw.
PV_GEOMETRY_AZIMUTH_BUCKET_DEGREES = 10

# Onder deze verhouding werkelijk/verwacht heet een windrichting
# structureel beschaduwd. Ruim genomen: Solcast weet niets van jouw
# specifieke daklijn, dus een deel van de afwijking is normaal.
PV_GEOMETRY_SHADING_RATIO = 0.6
PV_GEOMETRY_BUCKET_MIN_SAMPLES = 20

# Hoeveel dagen piekrichting bewaard blijven, en hoeveel er nodig zijn
# voor een uitspraak.
PV_GEOMETRY_HISTORY_DAYS = 60
PV_GEOMETRY_MIN_DAYS = 5
PV_GEOMETRY_RELIABLE_DAYS = 20

# Boven deze spreiding in de gevonden piekrichtingen is er waarschijnlijk
# meer dan één dakvlak - bij één vlak liggen de dagelijkse pieken dicht
# bij elkaar.
PV_GEOMETRY_MULTI_ORIENTATION_SPREAD_DEGREES = 40.0

# --- Opgegeven PV-oriëntatie als ijkpunt (v1.4.1) --------------------
# De afgeleide oriëntatie is pas nuttig als je hem ergens tegen kunt
# houden. Wie zelf weet welke kant zijn panelen op liggen, kan dat hier
# invullen; de integratie meldt dan wanneer haar eigen afleiding daarvan
# afwijkt.
#
# Dat is meer dan een controle op de methode. Verschuift de afgeleide
# piekrichting later weg van de opgegeven waarde terwijl die niet is
# veranderd, dan wijst dat op iets fysieks: een boom die is uitgegroeid,
# vervuiling op een deel van het vlak, of een uitgevallen streng.
CONF_PV_ACTUAL_AZIMUTH_DEGREES = "pv_actual_azimuth_degrees"
CONF_PV_ACTUAL_TILT_DEGREES = "pv_actual_tilt_degrees"

# Vanaf hoeveel graden verschil het het melden waard is. Bewust ruim:
# een luchtfoto-schatting van de eigenaar heeft zelf ook speling.
PV_ORIENTATION_MISMATCH_DEGREES = 25.0

# Bij een FLAUWE hellingshoek is de opbrengstcurve veel breder en ligt
# het piekmoment minder scherp vast - het schommelt dan per dag sterk.
# Onder deze hoek wordt de tolerantie daarom opgerekt, anders zou een
# vlakke opstelling voortdurend "afwijkend" melden terwijl er niets aan
# de hand is.
PV_SHALLOW_TILT_DEGREES = 20.0
PV_SHALLOW_TILT_EXTRA_TOLERANCE_DEGREES = 15.0

# --- Zelfcontrole op de zonvoorspelling (v1.5.0) ---------------------
# Gevraagd: "Neem je dit zelf mee in een diagnostiek, zodat je dit zelf
# detecteert wanneer dit niet correct is" - naar aanleiding van het
# handmatig vergelijken van `last_deviation_percent` met
# `learned_bias_percent`.
#
# De geleerde bias haalt de systematische afwijking eruit. Wat daarna
# overblijft hoort dagruis te zijn, rond nul. Blijven de recente dagen
# structureel aan één kant van die bias hangen, dan is er iets veranderd
# aan de installatie zelf: vervuiling, een uitgevallen streng, of een
# boom die is uitgegroeid. Dat is precies het soort langzame
# verslechtering dat je met het blote oog mist.
SOLAR_BIAS_DRIFT_MIN_DAYS = 5
SOLAR_BIAS_DRIFT_ATTENTION_PERCENT = 15.0

# Hoe dicht een dag bij de weinig-zon-drempel mag liggen voordat het het
# vermelden waard is. Vandaag zat op ~70% van typisch, vlak op de grens -
# en dat was nergens te zien, waardoor niet te beoordelen viel of het
# uitblijven van extra-dip-laden terecht was.
LOW_SOLAR_BORDERLINE_MARGIN = 0.10

# --- Zonneplan-kostensensoren automatisch vinden (v1.6.0) ------------
# Gevraagd: "Ik wil de entiteiten niet zelf invullen, deze moeten
# automatisch uit de zonneplan integratie gehaald worden zonder manuele
# config."
#
# Dat kan, want de prijssensor is al geconfigureerd en die verraadt het
# voorvoegsel. De rest wordt daaruit afgeleid.
#
# Twee valkuilen die de opzet bepalen:
#
# 1. De integratie levert entity_id's in TWEE talen door elkaar -
#    `sensor.zonneplan_electricity_delivery_costs_today` naast
#    `sensor.zonneplan_elektriciteitsleveringskosten_deze_maand`. Welke
#    je krijgt hangt af van wanneer de entiteit is aangemaakt en welke
#    taal er toen actief was. Er moeten dus meerdere kandidaten per
#    waarde geprobeerd worden.
# 2. Veel van deze sensoren staan STANDAARD UIT in Home Assistant. Een
#    ontbrekende sensor is dus normaal en mag nooit een foutmelding
#    opleveren - hooguit een regel die zegt dat er meer mogelijk is als
#    je hem inschakelt.
#
# Per doel een lijst kandidaat-achtervoegsels, in volgorde van voorkeur.
ZONNEPLAN_COST_CANDIDATES = {
    "afname_vandaag": (
        "electricity_delivery_costs_today",
        "afname_vandaag",
        "elektriciteitsleveringskosten_vandaag",
    ),
    "teruglevering_vandaag": (
        "electricity_production_costs_today",
        "teruglevering_vandaag",
        "elektriciteitsproductiekosten_vandaag",
    ),
    "afname_deze_maand": (
        "elektriciteitsleveringskosten_deze_maand",
        "electricity_delivery_costs_this_month",
        "afname_deze_maand",
    ),
    "teruglevering_deze_maand": (
        "elektriciteitsproductiekosten_deze_maand",
        "electricity_production_costs_this_month",
        "teruglevering_deze_maand",
    ),
    "gemiddelde_afnameprijs_vandaag": (
        "afname_gemiddelde_prijs_per_kwh_vandaag",
        "electricity_delivery_average_price_today",
    ),
    # v1.7.0: gas. Zonneplan levert bij deze installatie ook gas, en
    # zonder die post zijn de energiekosten maar half zichtbaar.
    #
    # LET OP: voor gas bestaat alleen een DAGtotaal, geen maand- of
    # jaarvariant zoals bij stroom. Dat is geen omissie hier maar een
    # beperking van de integratie zelf, en het hoort zichtbaar te zijn
    # in plaats van weggemoffeld.
    "gas_vandaag": (
        "gas_delivery_costs_today",
        "gas_afname_vandaag",
        "gasleveringskosten_vandaag",
    ),
    "gemiddelde_teruglverprijs_vandaag": (
        "teruglevering_gemiddelde_prijs_per_kwh_vandaag",
        "electricity_production_average_price_today",
    ),
}

# Vanaf welk verschil tussen onze eigen berekening en de werkelijke
# afrekening het het melden waard is. Ruim: de kostensensor werkt maar
# eens per uur bij en telt netbeheerkosten anders mee, dus een deel van
# het verschil is normaal.
ZONNEPLAN_COST_MISMATCH_EUR = 0.50
ZONNEPLAN_COST_MISMATCH_FRACTION = 0.15

# --- Herstelmeldingen (v1.6.2) ---------------------------------------
# Gerapporteerd: "Er is nu een melding verstuurd dat een sensor niet
# uitleesbaar is, maar er komt geen melding wanneer de sensor weer
# uitleesbaar is."
#
# Terecht, en het geldt breder dan die ene. Sommige meldingen beschrijven
# een TOESTAND die aanhoudt - een sensor die wegvalt, kosten die
# uiteenlopen, een module die uit de pas loopt. Zonder herstelmelding
# blijf je in het ongewisse: is het opgelost, of is de melding gewoon
# gedempt? Dat is precies het soort onzekerheid waardoor mensen
# meldingen gaan negeren.
#
# Meldingen die een GEBEURTENIS beschrijven (apparaat klaar, goedkoop
# blok begint, dagoverzicht) horen hier bewust niet bij: daar valt niets
# aan te herstellen.
NOTIFICATION_RECOVERY_KINDS = {
    "sensor_unavailable": (
        "✅ Sensor is weer uitleesbaar",
        "Alle geconfigureerde sensoren geven weer een waarde.",
    ),
    "integration_error": (
        "✅ Integratie draait weer",
        "De fout is verholpen; de aansturing werkt weer normaal.",
    ),
    "cost_mismatch": (
        "✅ Kostenberekening klopt weer",
        "De eigen berekening en de Zonneplan-afrekening liggen weer "
        "dicht bij elkaar.",
    ),
    "solar_underperforming": (
        "✅ Zonopbrengst is weer op niveau",
        "De opbrengst ligt weer in lijn met de voorspelling.",
    ),
    "pv_orientation_mismatch": (
        "✅ PV-oriëntatie komt weer overeen",
        "De afgeleide piekrichting ligt weer binnen de tolerantie van de "
        "opgegeven waarde.",
    ),
    "battery_module_drift": (
        "✅ Accumodules lopen weer gelijk",
        "Geen enkele module wijkt nog structureel af van de andere.",
    ),
    "battery_wont_last_night": (
        "✅ Accu haalt de nacht weer",
        "Er is weer genoeg opgeslagen om tot het goedkope blok te "
        "overbruggen.",
    ),
}

# --- Aanlooptijd na een herstart (v1.6.6) ----------------------------
# Gerapporteerd: "Het uitvallen komt door een herstart (start relatief
# traag op), misschien deze melding iets vertragen?"
#
# Terecht. Sensoren zijn na een herstart even weg omdat de bijbehorende
# integratie nog aan het opstarten is - dat is normaal, geen storing. Een
# melding sturen over iets dat binnen een minuut vanzelf goed komt,
# leert je die meldingen te negeren, en dan mis je de keer dat het wél
# echt misgaat.
#
# Alleen meldingen die over de BESCHIKBAARHEID van iets gaan wachten;
# een prijspiek of een apparaat dat klaar is heeft hier niets mee te
# maken.
STARTUP_GRACE_SECONDS = 180
STARTUP_GRACE_KINDS = ("sensor_unavailable", "integration_error")

# --- Dagkosten-geschiedenis en trends (v1.8.0) -----------------------
# Gevraagd: "Graag ook voor gas, week, maand en jaar cijfers. Voor zowel
# gas als electra wil ik ook een soort dagelijkse/wekelijkse trend zien.
# Iets als meer verbruikt dan gister, minder verbruikt dan vorige week.
# Dit wil ik dan in % zien."
#
# Zonneplan levert voor gas alleen een DAGtotaal - geen maand of jaar,
# anders dan bij stroom. Die worden hier dus zelf opgebouwd uit de
# dagtotalen.
#
# BELANGRIJK ONTWERPPUNT: trends rusten uitsluitend op VOLTOOIDE dagen.
# "Vandaag tot nu toe" vergelijken met een volledige gisteren geeft de
# hele dag een negatieve trend die om middernacht vanzelf verdwijnt -
# om 10:00 sta je op een derde van je dagverbruik en dat leest als "65%
# minder", terwijl er niets aan de hand is. Zo'n cijfer is erger dan
# geen cijfer, want je gaat er conclusies aan verbinden.
#
# Vandaag wordt daarom apart getoond, zonder trend.
DAILY_COST_HISTORY_DAYS = 400

# Onder dit bedrag zegt een procentuele verandering niets: van 2 cent
# naar 4 cent is "+100%" en dat is pure ruis.
COST_TREND_MIN_EUR = 0.20

# --- Dagrapportage voor diagnostiek (v1.9.0) -------------------------
# Gevraagd: "Ik wil nu elke dag met je het diagnostiek file delen, is
# deze voldoende gevuld zodat je elke dag kunt verbeteren?"
#
# De export toonde tot nu toe de HUIDIGE stand. Wat er om 03:00 gebeurde
# was alleen zichtbaar als het toevallig in een bewaarde reeks stond. Bij
# de analyses van vandaag miste ik daardoor: op welke tijdstippen de
# sensoruitvallen zaten, hoe de SoC over de dag verliep, en of een
# beslissing uitpakte zoals verwacht.
#
# Twee lagen:
#  - een BESLISLOGBOEK per tick: het verloop binnen de dag
#  - een DAGSAMENVATTING: om patronen over dagen heen te zien
#
# Ruim bemeten; de gebruiker gaf expliciet aan dat bestandsgrootte geen
# bezwaar is.
DECISION_LOG_LENGTH = 600          # ~2 dagen bij een tick van 5 minuten
DAILY_REPORT_HISTORY_DAYS = 30

# --- PV-opwek uit de meterstand (v1.9.1) -----------------------------
# Gemeld: "Dagrapport geeft aan opwek 12.9 kWh terwijl mijn PV
# installatie zegt 13.5 kWh" - 4,4% verschil, te veel voor ruis.
#
# Oorzaak: de dagopwek werd geINTEGREERD uit het vermogen (vermogen x
# tijd, elke tick). Dat neemt aan dat het vermogen tussen twee metingen
# constant was. De SolarEdge-vermogenssensor werkt maar eens per 15-20
# minuten bij (blijkt uit het meetfrequentie-rapport), dus een
# verouderde waarde wordt over drie ticks bevroren - en pieken tussen de
# metingen door vallen weg. De omvormer meet continu en telt ze wél mee,
# vandaar de structurele onderschatting.
#
# Oplossing: als er een cumulatieve energiemeter beschikbaar is, het
# DAGVERSCHIL daarvan gebruiken. Die telt tussen onze metingen door
# gewoon door. Integreren blijft de terugval voor wie zo'n meter niet
# heeft.
CONF_PV_ENERGY_SENSOR = "pv_energy_sensor_entity"

# Een meterstand hoort te stijgen. Daalt hij, dan is de omvormer
# herstart of de teller teruggezet; dan is het verschil betekenisloos en
# wordt de dag opnieuw geijkt in plaats van een negatieve opwek te
# boeken.
PV_ENERGY_METER_RESET_TOLERANCE_KWH = 0.01

# Minimaal volume voordat een nachtelijk gebruiksmoment een regeneratie
# van de waterontharder kan zijn (v1.9.2).
#
# Gemeld: "Was geen regeneratie van die zie ruim >10 liter zijn." Een
# moment van 3,1 liter om 00:28 werd als regeneratie aangemerkt, puur
# omdat het binnen het nachtvenster viel. Maar 's nachts wordt er ook
# gewoon doorgespoeld of een glas water getapt, en dat is geen
# regeneratie.
#
# Het tijdvenster alleen is dus geen bewijs; het volume is de
# onderscheidende eigenschap. Bewust op 10 liter: dat is de ondergrens
# die de gebruiker uit ervaring noemde, en ruim boven normaal nachtelijk
# gebruik.
WATER_SOFTENER_MIN_LITERS = 10.0

# Hoe lang na middernacht de kostenvergelijking wordt overgeslagen
# (v1.9.3). Gemeld: om 00:02 kwam "eigen berekening is 1,53 € hoger dan
# Zonneplan", en om 00:04 alweer "klopt weer".
#
# Geen rekenfout: onze dagteller springt om 00:00 naar nul, die van
# Zonneplan een paar minuten later. Zolang de twee niet gelijk staan is
# elke vergelijking betekenisloos - en een melding die zichzelf binnen
# twee minuten intrekt, leert je meldingen te negeren.
#
# Ruim genomen, want de kostensensor werkt maar ongeveer per uur bij.
ZONNEPLAN_ROLLOVER_GRACE_MINUTES = 30

# Hoeveel tekort er moet zijn voordat "accu haalt de nacht niet" afgaat
# (v1.9.3). In één nacht ging die melding zeven keer af, telkens gevolgd
# door "haalt de nacht weer" binnen enkele minuten. De tekorten:
# 0,21 - 0,03 - 0,01 - 0,09 - 0,03 - 0,06 kWh. Vijf van de zes binnen 1%
# van de drempel.
#
# Dat is geen waarschuwing maar geruis rond een grens. De schatting van
# de overbruggingsbehoefte heeft zelf een onnauwkeurigheid van enkele
# procenten, dus een tekort van 0,01 kWh zegt niets. Er moet een echt
# gat zijn voordat het het melden waard is - en de accu laadt sowieso
# bij als het nodig is, dus de melding is informatief en niet urgent.
BATTERY_NIGHT_SHORTFALL_MIN_KWH = 0.5
BATTERY_NIGHT_SHORTFALL_MIN_FRACTION = 0.10

# --- Plausibiliteitsscan op de eigen waarden (v1.9.5) ----------------
# Gevraagd: "Heb je de diagnostiek nu zo goed nagekeken dat daar niets
# meer uit te herleiden valt?" Eerlijke antwoord: nee. De export heeft
# ~200 velden en er zijn er handmatig veertig echt bekeken.
#
# Het rendement van 8290% viel pas op toen de HELE lijst werd uitgeprint
# in plaats van alleen de statussen. Zo'n fout - een getal dat fysiek
# onmogelijk is - hoort de integratie zelf te vinden, niet iemand die
# toevallig goed kijkt.
#
# Per veldsoort een bereik dat niet overschreden KAN worden zonder dat er
# iets mis is. Bewust ruim: het gaat om onmogelijke waarden, niet om
# ongebruikelijke.
PLAUSIBILITY_RULES = (
    # (naamfragment, minimum, maximum, omschrijving)
    ("_percent", -100.0, 200.0, "percentage"),
    ("_procent", -100.0, 200.0, "percentage"),
    ("_ratio_percent", 0.0, 100.0, "aandeel"),
    ("efficiency_percent", 0.0, 100.0, "rendement"),
    ("_soc_percent", 0.0, 100.0, "laadtoestand"),
    ("_kwh", -1000.0, 10000.0, "energie"),
    ("_eur", -100000.0, 100000.0, "bedrag"),
    ("_w", -100000.0, 100000.0, "vermogen"),
)

# --- GACS-zelfbeoordeling (v1.10.0) ----------------------------------
# Gevraagd naar aanleiding van de RVO-pagina over het
# Gebouwautomatiserings- en controlesysteem: "Ja graag uitwerken, met een
# nieuw tabblad voor GACS zodat ik hier in het bedrijfsleven van kan
# leren."
#
# BELANGRIJK: voor een woning geldt de GACS-verplichting NIET. Die geldt
# voor utiliteitsgebouwen zonder woonfunctie boven 290 kW verwarmings- of
# koelvermogen. Dit tabblad is dus geen nalevingsbewijs maar een spiegel:
# hoe verhoudt deze integratie zich tot de vier functionele eisen uit het
# Besluit Bouwwerken Leefomgeving?
#
# Die vier eisen, letterlijk uit de wettekst samengevat:
GACS_REQUIREMENTS = (
    (
        "monitoring",
        "Verbruik permanent controleren, bijhouden, analyseren én bijsturen",
        "Het systeem moet het energieverbruik continu volgen en er ook "
        "daadwerkelijk op kunnen ingrijpen.",
    ),
    (
        "efficiency",
        "Energie-efficiëntie toetsen en rendementsverliezen opsporen",
        "Niet alleen meten wat er gebeurt, maar ook beoordelen of het goed "
        "gaat en verliezen herkennen.",
    ),
    (
        "advies",
        "De beheerder informeren over verbetermogelijkheden",
        "De zwakste eis voor de meeste systemen: melden dát er iets is, is "
        "iets anders dan vertellen wat je eraan kunt doen.",
    ),
    (
        "interoperabiliteit",
        "Communiceren en samenwerken met andere bouwsystemen",
        "Met opslag, zonnepanelen, laadpalen en installaties van andere "
        "fabrikanten.",
    ),
)

# Drempels waarboven een verbetervoorstel de moeite waard is. Bewust
# terughoudend: een lijst met twintig adviezen leest niemand, en dan is
# juist de eis waar dit voor bedoeld is niet ingevuld.
GACS_EFFICIENCY_ADVICE_PERCENT = 85.0
GACS_SELF_CONSUMPTION_ADVICE_PERCENT = 60.0

# --- Aanlooptijd en aanhoudende uitval (v1.11.0) ---------------------
# Gemeld: "sensor.zendure_manager_available_kwh heeft langer nodig om op
# te starten... Ik wil dat na een herstart niet mee telt in analyses van
# sensor kwaliteit en de melding ook pas laten komen als hij ECHT
# onbeschikbaar zou zijn."
#
# In een export stond de score op 70% ("verminderd") terwijl alle
# veertien werkelijke vergelijkingen binnen de marge vielen; de zes
# `None`-waarden stonden aaneengesloten aan het eind van de reeks - de
# opstartperiode. De Zendure-integratie had simpelweg nog geen waarde
# toen deze coordinator al draaide.
#
# Tijdens de aanloop wordt er nu HELEMAAL niets geregistreerd: niet als
# goede meting en niet als slechte. Geen meting is eerlijker dan een
# slechte meting, en het alternatief - als "goed" tellen - zou een echte
# storing vlak na een herstart verbergen.
#
# Ruimer dan de melddrempel van drie minuten: de score kijkt terug over
# twintig metingen, dus daar weegt een verkeerde registratie veel langer
# door.
SENSOR_STARTUP_GRACE_MINUTES = 10

# Hoe lang een sensor onbeschikbaar moet blijven voordat het een echte
# storing heet. Een enkele gemiste uitlezing is normaal; pas als het
# aanhoudt is er iets aan de hand.
SENSOR_UNAVAILABLE_CONFIRM_MINUTES = 15

# --- Stilstaande geleerde waarden opsporen (v1.11.1) -----------------
# Gevraagd: "kijken naar alle waarden welke gegenereerd worden en
# mogelijk niet goed werken doordat ze lang stilstaan of juist al zo
# betrouwbaar zijn dat ze niet meer wijzigen."
#
# Dat is precies het onderscheid dat nergens te maken viel. In een export
# stond `steelstofzuiger_idle_power_history_w` op acht keer 0,0 - een
# ruststroom van nul is volstrekt plausibel, maar het is niet te
# onderscheiden van een meting die stilletjes is gestopt. Beide zien er
# in de export identiek uit.
#
# De oplossing is niet oordelen maar MELDEN dat het niet te beoordelen
# is, met het aantal metingen erbij: acht identieke waarden zegt weinig,
# tachtig identieke waarden bij een grootheid die hoort te fluctueren
# zegt veel.
STALLED_SERIES_MIN_SAMPLES = 8

# Reeksen waarvan een constante waarde NORMAAL is: ruststroom van een
# lader die niets doet, een teller die alleen bij een gebeurtenis
# beweegt. Die horen niet als verdacht gemeld te worden.
#
# Bewust een expliciete lijst: wie hier iets aan toevoegt moet kunnen
# uitleggen waarom stilstand daar te verwachten is, in plaats van dat het
# stilzwijgend meeglipt.
# Werkbuffers die zichzelf legen zijn GEEN geleerde reeksen. In v1.14.3
# zijn underscore-velden meegenomen om
# `_steelstofzuiger_idle_power_history` te vinden; daarmee kwamen ook de
# buffers binnen. `_balance_power_samples` verzamelt accuvermogens tussen
# twee balanscontroles en wordt daarna geleegd - 27x -0,0 W betekent
# daar gewoon "de accu stond stil", geen gestopte meting.
#
# Herkenbaar aan de naam: een reeks die iets LEERT heet `_history` of
# `_records`; een buffer heet `_samples` of `_buffer`.
STALLED_SERIES_WORKING_BUFFERS = ("_samples", "_buffer", "_queue")

STALLED_SERIES_CONSTANT_IS_NORMAL = (
    # v1.14.3: zonder "_w", want de interne velden heten
    # `_steelstofzuiger_idle_power_history`. Het fragment moet op de
    # ECHTE naam passen, niet op de naam zoals die in de export staat -
    # daar wordt "_w" pas toegevoegd.
    "idle_power_history",
    "charge_duration_history",
)

# --- Ondergrens voor drift-detectie (v1.12.3) ------------------------
# In een export stonden vijf van de 38 apparaten als "mogelijk defect",
# waaronder een televisie met referentie 0,79 W en een diepvries met
# 0,85 W. De gemelde drift van -24% en -15% komt daar neer op een
# verschil van 0,19 respectievelijk 0,13 watt.
#
# Een PROCENTUELE drempel is bij zulke kleine vermogens betekenisloos:
# meetruis van een tiende watt is al vijftien procent. Vijf meldingen
# waarvan er drie over tienden van watts gaan, leert je ze te negeren -
# en dan mis je de koelkast die echt stukgaat.
NILM_DRIFT_MIN_REFERENCE_W = 5.0

# Daarnaast moet het ABSOLUTE verschil de moeite waard zijn. Een
# apparaat van 10 W dat 30% meer verbruikt is 3 watt - dat is geen
# beginnend defect maar ruis.
NILM_DRIFT_MIN_ABSOLUTE_W = 5.0

# --- Zelfevaluatie (v1.14.0) -----------------------------------------
# Gevraagd: "Kun je een mechanisme bedenken waardoor de integratie
# zichzelf verbetert? Dus tips geeft welke verbetermogelijkheden er
# zijn."
#
# Wat WEL kan: achteraf toetsen of een keuze goed uitpakte. De integratie
# bewaart per dag of de reserve tekortschoot of juist ruim was, welke
# beslissingen zijn genomen, en wat dat kostte. Daaruit valt af te leiden
# of een instelling structureel verkeerd staat - dat is meetbaar, geen
# giswerk.
#
# Wat NIET gebeurt: zelf ingrijpen. De reserveberekening is eerder
# expliciet afgeschermd, en een systeem dat ongevraagd zijn eigen
# veiligheidsmarges verlaagt is precies wat je niet wilt. Voorstellen
# ja, uitvoeren nee.
SELF_EVAL_MIN_DAYS = 14

# Bij hoeveel overschot-dagen zonder één tekort de reserve structureel te
# ruim staat. Bewust hoog: één rustige week zegt niets, en te snel
# adviseren de marge te verlagen is gevaarlijker dan te laat.
SELF_EVAL_RESERVE_TOO_WIDE_RATIO = 0.9

# Een adviesmodule die na zoveel dagen nog niets heeft opgeleverd, doet
# vermoedelijk niets - of mist een sensor die niemand heeft opgemerkt.
SELF_EVAL_IDLE_MODULE_DAYS = 30

# --- Interne codes leesbaar maken (v1.16.2) --------------------------
# Gevraagd na een reeks kapotte kaarten: "Vooral kijken of er nog meer
# zaken gerepareerd dienen te worden."
#
# Bij een systematische controle bleken drie sensoren interne codes te
# tonen: "expensive_quarter", "wacht_op_goedkoop_blok". Prima als waarde
# in de logica - daar wordt op vergeleken - maar op een Nederlands
# dashboard zegt het niets.
#
# Dezelfde fout als bij de energie-check (v1.15.9), die
# "enough_to_postpone" toonde. Vertalen gebeurt in de WEERGAVE, niet in
# de sensor: de codes blijven de interne waarheid.
DECISION_REASON_LABELS = {
    "arbitrage_solar_capture": "zonoverschot opvangen",
    "default_smart": "standaard slim laden",
    "discharging_window": "ontladen in duur blok",
    "emergency_low_battery": "noodladen bij lage accu",
    "expensive_quarter": "duur kwartier",
    "expensive_quarter_no_own_load": "duur kwartier, geen eigen verbruik",
    "expensive_quarter_soc_protected": "duur kwartier, accu beschermd",
    "force_manual": "handmatig overschreven",
    "grid_charging_low_solar": "bijladen bij weinig zon",
    "grid_charging_low_solar_extra_dip": "bijladen bij extra prijsdip",
    "negative_price": "negatieve prijs",
    "no_forecast_data": "geen prijsvoorspelling",
    "post_salderen_solar_capture": "zon opvangen na saldering",
}

APPLIANCE_STATE_LABELS = {
    "wacht_op_goedkoop_blok": "wacht op goedkoop blok",
    "voltooid_vandaag": "vandaag al geladen",
    "aan_het_laden": "aan het laden",
}
