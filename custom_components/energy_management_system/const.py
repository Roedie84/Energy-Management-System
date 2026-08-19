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
# --- Wanneer is een uurverhouding betekenisvol? (v2.4.0) -------------
# Gevraagd: "Kun je diepgaand uitzoeken hoe we de PV voorspelling beter
# kunnen maken?"
#
# De grootste vondst zat niet in de voorspelling zelf maar in de
# CORRECTIE. De drempel stond op 0,01 kWh - tien wattuur - en een
# verhouding uit zulke getallen is ruis: 0,02 gedeeld door 0,06 geeft
# 0,33, terwijl de absolute fout 0,04 kWh is.
#
# Gemeten uurprofiel op deze installatie:
#
#     6h -> 0,334    7h -> 0,856    8h -> 0,385
#     19h -> 0,589   20h -> 0,226
#
# Zeven uur tussen zes en acht in breekt elk patroon; dat is ruis. En
# die factoren werden toegepast, waardoor de ochtend- en
# avondvoorspelling met een factor drie werd gedrukt.
#
# Bij een tiende kWh weegt een meetfout van enkele wattuur nog maar
# enkele procenten door.
# --- Wanneer is een goedkoop blok een melding waard? (v2.5.0) --------
# Gemeld om 16:45: "Om 17:00 begint 't goedkoopste blok van vandage" -
# terwijl het dagminimum om 13:00 op 16,4 ct lag en 17:00 op 30,7 ct.
#
# De melding klopte binnen zijn eigen logica: het blok is het goedkoopste
# dat er nog RESTEERT. Maar om kwart voor vijf is dat alleen nog de
# avond, en dan is "een goed moment voor apparaten die kunnen wachten"
# precies het verkeerde advies.
#
# Onder de dagmediaan is het blok werkelijk goedkoop. Daarboven zegt de
# melding alleen dat de rest van de dag nóg duurder is, en dat is geen
# reden om de vaatwasser aan te zetten.
CHEAP_BLOCK_ALERT_MAX_OF_MEDIAN = 1.0

# --- Wanneer is een piek een waarschuwing waard? (v2.7.0) ------------
# Gemeld: drie keer dezelfde melding op een ochtend, en het "duurste
# blok" schoof telkens op - om 05:15 begon het om 08:15, om 06:15 om
# 09:15, om 09:15 om 09:30. Dat is geen vaste gebeurtenis maar een
# horizon die meebeweegt.
#
# Om 09:15 melden dat om 09:30 de piek begint, met de accu op 11%, is
# nutteloos: er valt in een kwartier niets meer bij te laden.
#
# Een uur geeft bij 2000 W laadvermogen 2 kWh - een kwart van de accu, en
# genoeg om een piek van een uur te overbruggen. Ruimer nemen zou een
# melding van 1 uur 28 vooraf wegfilteren, en die is wél bruikbaar.
PEAK_ALERT_MIN_HOURS_AHEAD = 1.0

# En het blok moet er ook werkelijk uitspringen. Op 17 augustus liep de
# prijs van 29,7 tot 38,9 ct over de hele dag; 37,1 zat nauwelijks boven
# de mediaan van 34,5. Bij zo'n vlak verloop is "het duurste blok" een
# dun begrip en levert bijladen weinig op.
PEAK_ALERT_MIN_OF_MEDIAN = 1.15

# --- Vasthouden voor morgen (v2.6.0) ---------------------------------
# Gevraagd: "Houdt de integratie ook rekening met bijvoorbeeld minder PV
# energie morgen en daardoor meer te behouden in plaats van
# terugleveren?"
#
# Deels. De reserve kijkt tot het eerstvolgende goedkope blok, en
# redeneert dan: daar kan ik bijladen. De vraag erachter is een andere:
# is deze kWh MORGEN meer waard dan wat hij nu opbrengt?
#
# Eerst meten, dan pas sturen - dezelfde route als de slijtagekosten.
# --- Verder vooruitkijken bij de reserve (v3.10.0) -------------------
# Gevraagd: "Het gaat er mij vooral om dat er niet gewacht wordt tot een
# duur kwartier om extra bij te laden. De integratie moet ruim vooruit
# kijken."
#
# Terecht. Op 18 augustus rekende de reserve tot 16:45 - het
# eerstvolgende goedkope blok. Daarna kwam de avondpiek van 37,4 ct, en
# die telde niet mee bij de vraag hoeveel er in dat blok van 28,9 ct
# geladen moest worden.
#
# Eerst meten wat het verschil zou zijn, dan pas sturen.
# --- Bijkopen bij een verwacht tekort (v3.11.0) ----------------------
# Gevraagd: "Maar wat als het rendabel is om bij te kopen wanneer er niet
# genoeg PV energie is?"
#
# Een andere vraag dan arbitrage. Je koopt niet om te verkopen, je koopt
# om niet LATER duurder te moeten kopen.
#
# Zou sturen via `manual` met een POSITIEF vermogen - net zoals het
# ontladen in dure kwartieren met een negatief vermogen gaat. Maar eerst
# meten.
# Hoe dicht bij de ondergrens een planning "krap" heet (v3.24.0).
#
# Gevraagd na een dag met 42,9% minder zon: de bijkoop-kandidaat stond op
# nul metingen omdat hij alleen bij een BECIJFERD tekort mat - en dat was
# er niet, want de reserve had het opgevangen.
#
# Tien procentpunt boven de ondergrens is krap genoeg om te zeggen dat
# een kWh erbij verschil had gemaakt, en ruim genoeg om niet elke dag af
# te gaan.
BIJKOOP_KRAPPE_MARGE_PROCENT = 10.0

# De werkelijke netlading, per ronde gemeten (v3.25.0).
#
# Gevraagd: "maar er is vandaag toch wel degelijk bijgekocht?" - en dat
# klopte. Er ging 6,90 kWh de accu in, waarvan tussen de 2,02 en 5,93 kWh
# van het net. Op dagniveau is dat niet scherper te krijgen.
NETLADING_HISTORY_LENGTH = 400

BIJKOOP_HISTORY_LENGTH = 300
BIJKOOP_MIN_METINGEN = 30

LANGE_RESERVE_HISTORY_LENGTH = 300
LANGE_RESERVE_MIN_METINGEN = 50

LANGERE_HORIZON_HISTORY_LENGTH = 200
LANGERE_HORIZON_MIN_METINGEN = 20

PV_HOURLY_BIAS_MIN_KWH = 0.10

# Grenzen waarbuiten een bewaarde verhouding niet van een echte
# voorspelfout kan komen. Drie keer zoveel opwek als voorspeld, of een
# derde, gebeurt bij een redelijke voorspelling niet - behalve bij een
# deling door bijna nul.
#
# Nodig omdat er geen manier is om achteraf te zien uit welke getallen
# een bewaarde verhouding kwam.
# --- Onzekerheid van de voorspelling (v2.4.0) ------------------------
# Solcast levert naast de verwachting een tiende- en
# negentigste-percentiel. Liggen die ver uit elkaar, dan is het een dag
# met wisselende bewolking.
#
# De gemeten cijfers wijzen die kant op: mediane fout 2,7%, gemiddelde
# 10,8%, slechtste dag 41,6%. De meeste dagen kloppen prima; een paar
# zitten er volledig naast. Een betere gemiddelde correctie helpt daar
# niet - die maakt de goede dagen slechter zonder de slechte te redden.
# v2.5.0: geen losse velden nodig - Solcast levert `estimate10` en
# `estimate90` als ATTRIBUTEN op de bestaande voorspellingssensor, en
# zelfs per half uur in `detailedForecast`. Twee extra velden laten
# instellen die nergens naar wijzen is erger dan geen veld.

# Boven deze bandbreedte (als deel van de verwachting) geldt de dag als
# onzeker. Veertig procent betekent dat p10 en p90 bijvoorbeeld 12 en 20
# kWh zijn bij een verwachting van 20 - dan valt er weinig op te
# rekenen.
PV_SPREAD_UNCERTAIN_FRACTION = 0.40

# Hoeveel extra reservemarge zo'n dag oplevert. Loopt mee in de
# BESTAANDE zelfcorrigerende marge, zodat er niet weer twee reserves
# naast elkaar ontstaan - dat kostte v1.86.0 tot en met v1.88.0.
PV_SPREAD_MARGIN_BONUS_PERCENT = 10.0

# --- De band zelf leren ijken (v2.8.0) -------------------------------
# Gevraagd: "Is de spreiding op de verwachting niet heeeeel erg groot?
# Wat zegt dit nog?" - en daarna: "Ik wil dat de integratie dit zelf
# leert, en bepaalt aan de hand van beschikbare data."
#
# Terecht. Op 17 augustus liep de voorspelling van 2,4 tot 18,3 kWh op
# een verwachting van 9,8 - een factor zeven. Zo'n band zegt op zichzelf
# niets, en een vaste drempel van 40% met een vaste bonus van 10
# procentpunt is dan een aanname en geen meting.
#
# Nu wordt per dag vastgelegd WAAR in de band de werkelijke opwek viel.
# Daaruit volgt vanzelf hoe betrouwbaar de onderkant is.
# --- Regressiewoud voor de zonvoorspelling (v2.9.0) ------------------
# Gevraagd: "Is verder optimaliseren middels een Random Forest Regressor
# nog een idee?" - en na mijn bezwaren: "Proberen kan altijd toch?"
#
# Terecht. De bezwaren gingen over scikit-learn (numpy en scipy erbij,
# zo'n 100 MB op een Raspberry Pi), niet over de techniek. Een woud voor
# tweehonderd waarnemingen is in gewoon Python te schrijven.
#
# Wat blijft: met zo weinig gegevens leert een woud de metingen uit zijn
# hoofd. Daarom wordt getoetst op dagen die het NIET heeft gezien.
PV_MODEL_MAX_SAMPLES = 3000
PV_MODEL_MIN_SAMPLES = 150
PV_MODEL_MIN_DAGEN = 20

# Onder deze winst is het de moeite niet: een woud is niet uit te leggen,
# en dat is een echte prijs. Vijf procent minder fout weegt daar niet
# tegenop.
PV_MODEL_MIN_WINST_PROCENT = 10.0

PV_BAND_HISTORY_DAYS = 120

# Onder dit aantal dagen zegt de verdeling te weinig; dan blijft alles
# bij het oude.
PV_BAND_MIN_DAGEN = 14

# Welke positie in de band als veilig geldt: die op vier van de vijf
# gemeten dagen werd gehaald.
PV_BAND_SAFE_QUANTILE = 0.20

# Hoe ver de marge mag oplopen. Zonder plafond zou een dag met een
# extreem brede band de hele accu blokkeren.
PV_SPREAD_MARGIN_MAX_PERCENT = 25.0

PV_HOURLY_BIAS_MIN_RATIO = 0.40
PV_HOURLY_BIAS_MAX_RATIO = 2.50

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
# v1.81.0: een venster korter dan dit zegt niets over het nachtverbruik.
# Gemeld: "Voorspeld 0.33 kWh bij 30.3°C, werkelijk 1.92 kWh (afwijking
# +476.4%)." Beide metingen van die nacht kwamen uit afgebroken
# vensters - het ene van bijna niets, het andere van een paar uur.
TEMP_CONSUMPTION_MIN_HOURS = 2.0

TEMP_CONSUMPTION_MIN_SAMPLES = 4

# Dynamic "expensive quarter" threshold: a quarter counts as expensive if
# its price is within this fraction of today's price *range* from the
# day's maximum - no fixed count of quarters, self-adjusting to however
# many quarters actually clear the bar each day. Narrowed (fewer quarters
# qualify) when little solar is expected, for extra caution.
EXPENSIVE_PRICE_THRESHOLD_FRACTION = 0.20
EXPENSIVE_PRICE_THRESHOLD_FRACTION_LOW_SOLAR = 0.08

# --- Vangnet tegen één uitschieter (v1.54.0) -------------------------
# Gemeld op 12 augustus, de dag van de zonsverduistering: "De integratie
# geeft nu maar 2 dure kwartieren door de piek, maar waarschijnlijk kan
# er toch meer ontladen worden."
#
# Klopt. De drempel hierboven is de bovenste 20% van de PRIJSRANGE, en
# die range wordt opgerekt door één extreme piek:
#
#   68,9 - 0,20 x (68,9 - 12,1) = 57,5 ct
#
# Alleen 19:45 (68,9) en 20:00 (61,8) haalden dat. Kwartieren van 43 tot
# 51 ct - anderhalf keer de mediaan van 30,7 - telden niet mee, puur
# omdat de eclipspiek de meetlat omhoog trok.
#
# De verdeling kent dat probleem niet: een mediaan verschuift nauwelijks
# van één uitschieter. Maar een mediaandrempel alléén werkt weer niet op
# een vlakke dag - op 11 augustus (13-38 ct) haalt geen enkel kwartier
# 1,4x de mediaan, terwijl de range-drempel er terecht 17 aanwijst.
#
# Daarom allebei, en de RUIMSTE wint. De range doet het werk op een
# gewone dag; de mediaan beperkt de schade als één piek de range
# oprekt. Nagerekend:
#
#   11 aug (vlak):      range 33 ct -> 17 kw | mediaan 42 ct ->  0 kw
#   12 aug (eclips):    range 58 ct ->  2 kw | mediaan 43 ct ->  6 kw
#
# Met de laagste van de twee: 17 respectievelijk 6. Beide dagen goed.
EXPENSIVE_PRICE_MEDIAN_MULTIPLIER = 1.4

# Onder deze spreiding is er geen sprake van een uitschieter en blijft
# de range-drempel gewoon leidend; de mediaanmaat wordt dan niet eens
# berekend.
EXPENSIVE_PRICE_OUTLIER_MIN_RANGE_EUR = 0.15

# En alleen als de piek echt een uitschieter IS. Zonder deze voorwaarde
# zou de mediaanmaat ook gewone dagen soepeler maken, en daar is niets
# mis mee gegaan - de eis is dat de hoogste prijs minstens twee keer de
# mediaan is.
#
#   12 augustus (eclips): 68,9 tegen 30,7 = 2,24x -> ingrijpen
#   11 augustus (vlak):   37,8 tegen 30,2 = 1,25x -> ongemoeid laten
EXPENSIVE_PRICE_OUTLIER_MEDIAN_RATIO = 2.0

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

# --- Toets op het prijsattribuut (v1.37.0) ---------------------------
# Gevraagd: "Neem je alles gerelateerd aan de kwartier prijzen van
# zonneplan mee incl tax/btw?"
#
# Ja - maar dat was een antwoord uit de code, geen meting. Zonneplan
# levert zelf de gemiddelde afnameprijs van vandaag; die stond al in de
# export als gevonden entiteit en werd nergens gebruikt.
#
# Speling op het bereik, want de dag is nog niet voorbij en de
# gemiddelde prijs loopt een uur achter.
PRICE_ATTRIBUTE_CHECK_MARGIN_EUR = 0.02
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

# --- Hoe ver reikt de live correctie? (v1.68.0) ----------------------
# Gemeld: "Nee: 34 kwartier(en) aan het net - morgen 01:00-09:30.
# Laagste 10%, eind 10%, EUR -2.0 over 31 uur."
#
# Om 16:30 werd er gekookt, dus de correctie zat op zijn maximum van
# 5,0x - en die werd toegepast op de hele planning van 31 uur. Het plan
# rekende met 1,26 tot 1,38 kW terwijl het geleerde profiel 0,20 tot
# 0,41 kW zegt, en concludeerde dat de accu om 01:00 leeg zou zijn.
#
# Dat de airco nu draait, zegt iets over het komende uur. Dat je om half
# vijf kookt, zegt niets over 03:00 vannacht.
CONSUMPTION_CORRECTION_FULL_HOURS = 1.0
CONSUMPTION_CORRECTION_FADE_HOURS = 4.0

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

# --- Rendement per halve slag (v1.32.0) ------------------------------
# Gevonden in de export van 11 augustus: zeven metingen van 56,4 tot
# 97,6% met een mediaan van 82,9, terwijl Ruud zelf 90,8% mat. Een
# spreiding van veertig procentpunt betekent niet dat de accu wisselt,
# maar dat er iets anders gemeten wordt dan rendement.
#
# De oude formule was (ontladen + verschil in voorraad) / geladen, en
# die klopt alleen als het venster op een HELE slag eindigt. Het venster
# sloot zodra er genoeg geladen was - dus midden in een lading, midden in
# een ontlading, waar het uitkwam. Halverwege het laden meet je zo de
# LAADkant, halverwege het ontladen iets daartussenin.
#
# Nu twee losse metingen, elk over een stuk waarin de accu maar een kant
# op gaat:
#
#   laadrendement    = toename voorraad / wat erin ging
#   ontlaadrendement = wat eruit kwam / afname voorraad
#   heen en terug    = laadrendement x ontlaadrendement
#
# Precies wat gevraagd werd: "volgens mij is het simpel te berekenen
# middels laad en ontlaad vermogen en beschikbaar vermogen".

# Onder dit vermogen telt de accu als stilstaand; anders zou elke rimpel
# rond nul een stuk afbreken.
EFFICIENCY_IDLE_POWER_W = 50.0

# De voorraadsensor meldt in stappen van 1% (0,086 kWh bij deze accu).
# Onder deze hoeveelheid is die stap alleen al enkele procenten van de
# uitkomst, en dan meet je afronding in plaats van rendement.
EFFICIENCY_SEGMENT_MIN_KWH = 1.5

# Zit er een gat in de metingen, dan is er onderweg energie gelopen die
# niet is geteld. Zo'n stuk is waardeloos.
#
# Drie keer de tick (5 min) plus wat speling: een gemiste ronde mag,
# een storing van een half uur niet. Precies op de tick zetten zou elk
# stuk afbreken zodra een tick een seconde later valt.
EFFICIENCY_SEGMENT_MAX_GAP_MINUTES = 20.0

# Twintig metingen per kant: genoeg om een mediaan op te bouwen zonder
# dat een accu van een half jaar geleden blijft meepraten.
EFFICIENCY_HALF_HISTORY = 20

# Per halve slag is minder dan 70% onmogelijk; dat is een meetfout.
MIN_PLAUSIBLE_HALF_EFFICIENCY_PERCENT = 70.0
MAX_PLAUSIBLE_HALF_EFFICIENCY_PERCENT = 100.0

# Onder dit aantal metingen per kant geen uitspraak - dan blijft de oude
# schatting gelden.
MIN_HALF_EFFICIENCY_SAMPLES = 3

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

# --- Contractjaar (v1.90.0) ------------------------------------------
# Gevraagd: "Tevens lijkt het me handig dat de start van mijn contract
# bij Zonneplan ingevoerd kan worden zodat ik precies het gebeuren voor
# mijn contract jaar kan zien."
#
# Een energiecontract loopt zelden gelijk met het kalenderjaar, en de
# afrekening gaat over het contractjaar. Zonder deze datum vergelijk je
# appels met de jaaropgave.
CONF_CONTRACT_START_DATE = "contract_start_date"

# --- Dagreeks voor zelfconsumptie over langere perioden (v1.90.0) ----
# Gevraagd: "Misschien zelfconsumptie per dag/week/maand/jaar?"
#
# En daar zit een tweede reden onder. De zelfconsumptie per DAG rekent
# af op de kalenderdag: zon die gisteren in de accu ging en vannacht
# wordt verkocht, telt vandaag als export terwijl hij bij de opwek van
# gisteren hoort. Op 14 augustus 08:23 stond er 0,109 kWh opwek tegen
# 0,448 kWh export - allemaal uit de accu van gisteren.
#
# Over een week of langer valt die daggrens weg. Vierhonderd dagen is
# genoeg voor een volledig contractjaar plus wat marge.
ENERGY_DAILY_HISTORY_DAYS = 400

# Onder deze opwek in een periode valt er geen zinnig aandeel te
# berekenen. Gemeld: "Zelfconsumptie klopt niet? staat op unknown?" - op
# 14 augustus 08:23 stond er 0,109 kWh opwek tegen 0,448 kWh export, en
# daar rolt geen betekenisvol percentage uit.
SELF_CONSUMPTION_MIN_PV_KWH = 0.5

# --- Eenheden van statistieken (v1.93.0) -----------------------------
# Gemeld: "De data is onreeel - Opwek 131548 kWh over een week." Dat is
# een factor duizend: de bronsensor levert wattuur en de code nam
# kilowattuur aan. Statistieken dragen hun eigen eenheid; die moet
# gelezen worden in plaats van geraden.
ENERGY_UNIT_TO_KWH = {
    "kWh": 1.0,
    "Wh": 0.001,
    "MWh": 1000.0,
}

# Een dag met meer dan dit is geen meting maar een meterwissel of een
# teller die opnieuw begon. Ruim boven wat een woonhuis met zonnepanelen
# ooit haalt.
ENERGY_DAY_SANITY_MAX_KWH = 500.0

# Fors terugleveren zonder opwek kan niet (v2.6.1). De grens ligt niet
# op nul: 's nachts uit de accu verkopen bij nul opwek is normaal. Maar
# tien kilowattuur is dat niet - dat was een dag die onder de verkeerde
# datum werd afgesloten, met een al gewiste opwekteller.
ENERGY_DAY_EXPORT_WITHOUT_PV_MAX_KWH = 8.0

# Teruglevering zonder opwek en zonder accu-ontlading kan niet - die
# energie moet ergens vandaan komen. Boven deze drempel is het geen
# meetruis maar een dag die met al gewiste tellers is afgesloten.
ENERGY_DAY_MIN_SOURCE_KWH = 0.5

# Welke inleesronde een bewaarde dag heeft geschreven (v1.94.0).
#
# Gemeld na de reparatie van v1.93.0: de tabel stond nog steeds op
# 131548 kWh per week. Die versie repareerde het INLEZEN, maar de reeks
# was al bewaard en wordt alleen aangevuld VOOR de oudste bekende dag.
#
# Zonder merkteken valt niet te zien welke dagen uit een kapotte ronde
# komen. Verhoog dit getal zodra er iets aan het inlezen verandert; dan
# worden de oude regels weggegooid en opnieuw opgehaald.
# --- Eigen logregels in de export (v3.4.0) ---------------------------
# Alles wat deze integratie via `_LOGGER.warning` of `_LOGGER.exception`
# wegschrijft, verdwijnt in het logboek van Home Assistant - en dat zit
# niet in de diagnostiek-export.
#
# Dat kostte deze week echt tijd: de NameError die het inlezen van de
# geschiedenis bij ELKE start liet omvallen, stond alleen in het logboek.
# Het duurde drie diagnostieken en twee versies voordat die boven water
# kwam.
# --- Gemeten capaciteit in de reserve (v3.5.0) -----------------------
# Uit een externe review: "Je leert al rendement en gezondheid. De
# volgende stap: nominaal 8,64 kWh, gemeten 7,95 kWh, degradatie 8% - en
# automatisch de reserveberekening aanpassen."
#
# Terecht. De reserve rekende met de NOMINALE capaciteit. Levert de accu
# feitelijk minder, dan wordt er gerekend op energie die er niet is.
CAPACITY_MEASURE_WINDOW_DAYS = 30

# Een meting die meer dan een derde onder nominaal ligt is eerder een
# meetfout dan een versleten accu. Daar mag de reserve niet op gaan
# rekenen - dan zou een verkeerd uitgelezen sensor de hele accu
# blokkeren.
CAPACITY_MEASURE_MIN_FRACTION = 0.65

EIGEN_LOG_REGELS = 100

# Hoe ver de wijzigingsmomenten van de bronbestanden uit elkaar mogen
# liggen (v3.4.0).
#
# Gemeld op 17 augustus: een koelmelding met de oude tekst, terwijl de
# reparatie was opgeleverd. Tijdens de GitHub-storing van die middag (50%
# foutkans op downloads) kan een installatie half aankomen: het ene
# bestand nieuw, het andere oud.
#
# Een normale installatie schrijft alle bestanden binnen enkele minuten.
# Een uur is ruim genoeg voor een trage schijf en streng genoeg om een
# half aangekomen update te zien.
INSTALL_FILE_SPREAD_MAX_HOURS = 1.0

ENERGY_BOOTSTRAP_VERSION = 3

# --- Leest de buitensensor plausibel? (v1.96.0) ----------------------
# Gevonden bij de eindcontrole: de verouderingsdrijvers legden 41,7 graden
# buiten vast, en in de koelgeschiedenis staan 35,4 en 35,9. Voor Lochem
# onwaarschijnlijk hoog.
#
# De sensor is een Hue-bewegingsmelder die in de zon hangt. Die leest bij
# direct zonlicht makkelijk vijf tot tien graden te hoog - geen
# uitschieter maar een aanhoudende afwijking, dus het piekfilter ziet er
# niets van.
#
# Vier graden boven de weerbron is meer dan meetruis en minder dan wat
# een sensor in de volle zon laat zien; daartussen zit de grens.
OUTDOOR_SENSOR_BIAS_WARN_C = 4.0
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

# --- Instelbaar interval (v2.2.0) ------------------------------------
# Gevraagd: "instelbaar maken", nadat de gemeten rondeduur uitkwam op
# 48,6 ms - 0,016% van de tijd bij vijf minuten.
#
# In SECONDEN, want minuten zijn te grof zodra je onder de minuut wilt.
# De ondergrens is niet willekeurig: bij 48,6 ms per ronde is tien
# seconden 0,5% belasting en een seconde 4,9% - dat laatste zit tegen de
# grens van vijf procent aan waarboven Home Assistant merkbaar op deze
# integratie staat te wachten.
#
# Vijf seconden laat ruimte voor een tragere ronde op een dag met een
# volle prijsreeks, zonder dat de gebruiker daar zelf op hoeft te letten.
CONF_UPDATE_INTERVAL_SECONDS = "update_interval_seconds"
UPDATE_INTERVAL_MIN_SECONDS = 5
UPDATE_INTERVAL_MAX_SECONDS = 3600

# Zendure operation modes (select.select_option values)
OPTION_SMART = "smart"
OPTION_SMART_DISCHARGING = "smart_discharging"

# v1.55.0: zon opnemen, niets afgeven - de tegenhanger van
# smart_discharging, die de integratie tot nu toe niet kende.
#
# Gemeld: "er is ook een operation mode smart-charge, deze laadt alleen
# zonne energie maar geeft niet terug aan de woning", en daarna
# gecorrigeerd naar de exacte waarde: manual, smart, smart_discharging,
# smart_charging.
#
# Zonder deze modus moest de aansturing altijd kiezen tussen "voed het
# huis" (smart) en "doe niets met de zon" (manual op 0 W). Dat is precies
# waarom een goedkope nacht niet te benutten was: de accu leegt op een
# moment dat van het net halen goedkoper is, en de enige uitweg zette
# ook de zonopname stil.
OPTION_SMART_CHARGING = "smart_charging"

# Marge op de vergelijking accu-tegen-net. Zonder marge zou een verschil
# van een halve cent de modus elke tick heen en weer laten schakelen, en
# dat is slechter dan de verkeerde keuze even volhouden.
GRID_CHEAPER_MARGIN_EUR = 0.02

# --- Knop "Nu laden" (v1.56.0) ---------------------------------------
# Gevraagd: "als ik weet dat ik veel ga gebruiken is een button die
# overschakelt naar smart (en automatische reset na 2 uur bijvoorbeeld)
# een idee?"
#
# Loopt tot het einde van het uitstelvenster, met deze ondergrens. Twee
# uur alleen zou op een dag met uitstel tot 13:00 betekenen dat het
# uitstel om 10:00 hervat en je alsnog met een halfvolle accu zit.
NU_LADEN_MIN_HOURS = 2

# --- Hoe lang draait een noodloop al? (v1.58.0) ----------------------
# Er zijn 28 terugvalpaden en geen enkele meet hoe lang hij al actief is.
# De azimut viel terug op sun.sun, kreeg niets, en het
# installatieprofiel stond tien dagen op "0/5 heldere dagen" zonder dat
# iets aansloeg.
#
# Een dag terugval is ruis - een sensor die even zweeg. Boven deze grens
# is het een storing die niemand heeft gezien.
FALLBACK_ALERT_HOURS = 24.0

# --- Wat veroudering versnelt (v1.59.0) ------------------------------
# Van een degradatiemodel afgezien: capaciteitsverlies is enkele
# procenten per JAAR en de capaciteitssensor is zelf een schatting die
# met de temperatuur meebeweegt. Uit elf dagen valt daar niets uit af te
# leiden, en een curve die er wetenschappelijk uitziet met
# onverifieerbare aannames is erger dan geen curve.
#
# Wat wél kan is de OORZAKEN meten. Van lithium-ijzerfosfaat is bekend
# dat lang op hoge stand staan en hoge celtemperatuur de veroudering
# versnellen - en dat is vandaag al meetbaar.
AGING_HIGH_SOC_PERCENT = 90.0
AGING_LOW_SOC_PERCENT = 15.0
AGING_HIGH_TEMPERATURE_C = 30.0

# Een gat betekent dat we niet weten wat er tussendoor gebeurde; dan
# liever niets tellen dan gokken.
AGING_MAX_GAP_HOURS = 0.5

# --- "Waarom doe je dit nu?" (v1.60.0) -------------------------------
# Gevraagd: "Kun je in de integratie nog een eigen AI maken, die zaken
# als 'Waarom laad je nu? -> Omdat tussen 16:00 en 19:00 de prijs 31
# cent hoger ligt, er slechts 4,2 kWh zon wordt verwacht...' kan
# toelichten, en dan niet alleen het bovenstaande voorbeeld maar voor
# alles?"
#
# Geen taalmodel. Het besluit is deterministisch - er is een exacte
# regel die zei wat er moest gebeuren - dus een gegenereerde verklaring
# kan er náást zitten zonder dat iemand het merkt. Elke regel komt uit
# een waarde die de beslissing daadwerkelijk nam.
#
# Drie regels, net als in het voorbeeld. Meer leest niemand, en de
# vierde reden is per definitie de minst belangrijke.
WHY_MAX_REASONS = 3

# Onder deze resterende laadruimte geldt de accu als vol. Gemeld:
# "Zonoverschot gaat de accu in? Kan niet want die is vol :)" - de
# uitleg beweerde dat het overschot werd opgevangen terwijl er niets
# meer bij kon. Een kwartier laden op 2000 W is 0,5 kWh; daaronder is er
# in de praktijk geen ruimte meer.
SOLAR_CAPTURE_FULL_MARGIN_KWH = 0.3

# --- Klopt de uitgelezen zonstand? (v1.71.0) -------------------------
# Gevraagd: "Kunnen we op een of andere manier verifieren dat de azimuth
# correct wordt uitgelezen?"
#
# De zon draait 15 graden per uur, dus een aflezing van een paar minuten
# oud loopt al een halve graad achter. De berekening zelf is nauwkeurig
# tot ongeveer een tiende graad. Vijf graden is ruim genoeg om normale
# vertraging door te laten en scherp genoeg om een verkeerde sensor te
# herkennen.
#
# Nagerekend op de melding van 12 augustus 17:30: gemeten 248,05 tegen
# 252,9 berekend voor Lochem - 4,9 graden, precies wat een aflezing van
# een paar minuten eerder oplevert.
SUN_AZIMUTH_TOLERANCE_DEGREES = 5.0

# --- Gepland witgoed in de planning (v1.61.0) ------------------------
# Gevraagd: "Nu weet ik zelf dat er morgen 2 wasmachines en een
# vaatwasser zullen draaien, hoe gaat de integratie daar mee om?"
#
# Niet. De reserve rekent met het geleerde uurprofiel (0,20-0,51 kW);
# drie machines zijn samen 4 a 5 kWh, meer dan de helft van de bruikbare
# accu. Dat verbruik zat nergens in de planning, dus rekenden de
# kwartierplanning, de tekortkwartieren en de verkooptoets allemaal te
# laag.
#
# Home Connect weet het wel: `number.vaatwasser_begin_relatief` en
# `sensor.wasmachine_programma_eindtijd` dragen het geplande moment.
# Uitlezen, niet bedienen - die grens blijft staan.
CONF_DISHWASHER_START_IN = "dishwasher_start_in_entity"
CONF_WASHING_MACHINE_END_AT = "washing_machine_end_at_entity"

# Wat een cyclus kost, zolang er nog niets gemeten is. Zodra de
# energy_import-teller een hele cyclus heeft gezien, wordt dat de
# waarde - schatten is een noodgreep, geen uitgangspunt.
DEFAULT_DISHWASHER_CYCLE_KWH = 1.0
DEFAULT_WASHING_MACHINE_CYCLE_KWH = 0.8

# Verder vooruit dan dit is de planning zelf niet betrouwbaar genoeg om
# er een geplande cyclus in te hangen.
APPLIANCE_PLAN_MAX_HOURS = 24.0

# Hoeveel vermogensmetingen er van een lopende cyclus worden bewaard.
# Bij een tick van vijf minuten is 60 gelijk aan vijf uur - ruim genoeg
# voor de langste wasbeurt, en klein genoeg om niet in de weg te zitten.
APPLIANCE_POWER_SAMPLE_LIMIT = 60

# --- Terugrekenen vanaf een eindtijd (v1.70.0) -----------------------
# Gemeld: "wasmachine heeft inderdaad alleen een eindtijd."
#
# Die eindtijd als moment nemen legt het verbruik uren te laat: bij een
# programma dat om 07:00 klaar is en anderhalf uur duurt, wordt het
# water rond 05:30 verwarmd. Voor een reserve die de nacht moet
# overbruggen valt dat verbruik dan net buiten het venster.
#
# De cyclusduur wordt al geleerd, maar die reeks bevat ook korte
# fragmenten (bij deze installatie 8 en 10 minuten tussen echte cycli
# van 60 tot 80). Onder deze grens is de geleerde duur niet te
# vertrouwen en blijft de eindtijd staan, mét kanttekening - een duur
# verzinnen is erger dan een moment dat een uur naast zit.
APPLIANCE_MIN_PLAUSIBLE_CYCLE_MINUTES = 30.0

# De vraag boven het antwoord, per beslisreden - "Waarom laad je nu?"
# leest anders dan "Waarom verkoop je nu?", en dat verschil is het halve
# antwoord.
WHY_QUESTIONS = {
    "expensive_quarter": "Waarom verkoop je nu?",
    "expensive_quarter_no_own_load": "Waarom verkoop je nu?",
    "expensive_quarter_soc_protected": "Waarom verkoop je nu niet?",
    "solar_capture_deferred": "Waarom laad je nu nog niet?",
    "grid_cheaper_than_battery": "Waarom gebruik je de accu nu niet?",
    "grid_charging_low_solar": "Waarom laad je nu uit het net?",
    "grid_charging_low_solar_extra_dip": "Waarom laad je nu uit het net?",
    "discharging_window": "Waarom ontlaad je nu?",
    "emergency_low_battery": "Waarom laad je met spoed?",
    "negative_price": "Waarom laad je nu hard?",
    "arbitrage_solar_capture": "Waarom laad je nu?",
    "post_salderen_solar_capture": "Waarom laad je nu?",
    "force_manual": "Waarom doet de aansturing niets?",
    "kalibratie": "Waarom doet de aansturing niets?",
    "no_forecast_data": "Waarom gebeurt er niets?",
    "default_smart": "Waarom doet de accu dit nu?",
}
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
CONF_BATTERY_COOLING_OPPORTUNITY_C = "battery_cooling_opportunity_c"
CONF_BATTERY_COOLING_FAN_SWITCH = "battery_cooling_fan_switch_entity"
# Optioneel: een eigen buitentemperatuursensor specifiek voor deze
# vergelijking. Leeg laten betekent terugvallen op de al bestaande
# live-buitentemperatuur (achtertuinsensor, anders de weerentiteit).
CONF_BATTERY_COOLING_OUTDOOR_SENSOR = "battery_cooling_outdoor_sensor_entity"

# AANZETTEN zodra één van deze vier waar is:
#   1. accu staat meer dan 5°C boven buiten
# --- Wat de ventilator afzuigt: de OMVORMER (v1.80.0) ----------------
# Gemeld: "Ventilatoren zuigen af van de omvormer" en "dat is de juiste
# temperatuur van de omvormer".
#
# Dat legt een fout bloot die dieper zat dan de drempels. De redenering
# in dit blok stond letterlijk op CELtemperatuur: "lithium-ijzerfosfaat
# komt boven ongeveer 35 graden in het gebied waar veroudering
# versnelt". Maar de sensor die de koeling aanstuurt is
# `solarflow_2400_ac_hyper_tmp` - de omvormer. Vermogenselektronica
# draait routinematig boven de 60 graden zonder enig probleem.
#
# Alle absolute drempels waren dus op de verkeerde grootheid geijkt. De
# ventilator sloeg aan bij 25 tot 29 graden omvormertemperatuur, en dat
# is voor een omvormer volstrekt normaal.
#
# In de eigen geschiedenis van vier dagen: tien aanzetmomenten, allemaal
# tussen 25 en 29 graden. Met een ondergrens van 35 vervallen ze
# alle tien - terwijl de 38 graden van 13 augustus (2062 W laden, 32
# graden buiten) wel gewoon gekoeld wordt.
#
# LET OP: 35 en 50 zijn SCHATTINGEN. Zendure publiceert niet bij welke
# temperatuur de hyper terugregelt, en er is geen sensor die dat meldt.
# De eigen reeks loopt van 24 tot 38 graden en is te kort om er een
# grens uit af te leiden. Wat wél vaststaat is de fysica: een ventilator
# kan niet onder de buitentemperatuur koelen, en daar zijn de
# verschilregels op gebaseerd.

# Onder deze omvormertemperatuur valt er niets te winnen.
BATTERY_COOLING_MIN_ABSOLUTE_C = 35.0
# Met hysterese, want de sensor meldt hele graden.
BATTERY_COOLING_STOP_BELOW_C = 32.0

# Zo warm dat er onvoorwaardelijk gekoeld wordt, wat het verschil met
# buiten ook is. Ruim boven alles wat deze installatie ooit heeft laten
# zien (38), als vangnet.
BATTERY_COOLING_ON_ABSOLUTE_C = 50.0
# En blijven draaien tot hij daar duidelijk onder zit.
BATTERY_COOLING_OFF_ABSOLUTE_C = 45.0

# De verschilregels: hierop is de fysica van toepassing en niet de
# aanname over veroudering. Een ventilator kan niet onder de
# buitentemperatuur koelen; onder een paar graden verschil is er dus
# weinig te halen.
# --- Koelen als het goedkoop is (v3.6.0) -----------------------------
# Gemeld: "De accu moet meer gekoeld worden, hij is nu 31 graden en de
# buitentemperatuur is veel lager."
#
# Terecht. De drempel van 35 graden beschermt de OMVORMER - die regelt
# pas terug als hij warm wordt. Maar bij 31 graden met 14 buiten is er
# zeventien graden koeling te halen voor een ventilator van een paar
# watt, en dan is wachten tot 35 zonde.
#
# De cellen stonden op dat moment op 21 tot 23 graden, ruim onder de
# drempel waarboven LFP versneld veroudert. Er was dus geen alarm - maar
# koelen dat bijna niets kost en meetbaar veroudering scheelt, is de
# moeite waard.
#
# Onder deze grens wordt er sowieso niet gekoeld: dan is er niets te
# winnen, hoe koud het buiten ook is.
BATTERY_COOLING_OPPORTUNITY_MIN_C = 28.0

# En dan alleen als er genoeg verschil met buiten is om het zinvol te
# maken. Twaalf graden is ruim: de ventilator haalt er dan in enkele
# minuten meerdere graden af, zoals de metingen van 17 augustus laten
# zien (35 naar 26 in een half uur).
BATTERY_COOLING_OPPORTUNITY_DELTA_C = 12.0

# Hoeveel graden ONDER de aanzetdrempel de goedkope koeling doorgaat
# (v3.14.0).
#
# Gemeld: acht schakelingen in zes uur, netjes op de klok van de
# minimale looptijd. De regel uit v3.6.0 zette de ventilator aan bij 27
# graden, waarna de gewone uitschakelregel hem meteen weer wilde stoppen
# omdat 27 onder de 32 ligt. Aan bij 27, uit bij 27 - dat is geen
# hysterese maar een tegenstelling.
#
# Vijf graden is ruim: de ventilator haalt er in een half uur zes tot
# acht af, zoals de metingen laten zien (27 naar 21).
BATTERY_COOLING_OPPORTUNITY_HYSTERESE_C = 5.0

# Hoeveel verschil met buiten er nog nodig is om DOOR te gaan (v3.23.1).
#
# Gemeld: negen schakelingen in zes uur, ook na de hysterese van
# v3.14.0. De oorzaak was dat ik dezelfde delta-eis van 12 graden
# gebruikte voor aanzetten én voor doorgaan.
#
# Zodra de ventilator zijn werk doet zakt het verschil: 33 naar 24 bij
# 17,7 buiten is nog maar 6,3 graden. Dan stopt hij, warmt de omvormer
# weer op, en begint het opnieuw. De regel die pendelen moest voorkomen
# veroorzaakte het.
#
# Doorgaan vraagt minder dan beginnen: er valt nog steeds iets te halen
# zolang er vier graden verschil is.
BATTERY_COOLING_OPPORTUNITY_KEEP_DELTA_C = 4.0

# Wanneer de goedkope koeling niets meer te koelen HEEFT (v3.26.1).
#
# Gemeten 18/19 augustus: na de reparatie van v3.23.1 verdween het
# pendelen - elf uur achter elkaar geen enkele schakeling - maar de
# ventilator ging ook nooit meer uit. Bij een drempel van 25 stopt hij
# pas onder de 20, en de accu staat 's nachts op 23 met 16 buiten. Die
# stand wordt nooit bereikt.
#
# De omvormer wordt warm van WERK. Staat de accu onder de aanzetdrempel
# én gaat er nauwelijks vermogen doorheen, dan is er geen warmtebron en
# valt er niets te koelen. Boven die stroomgrens blijft hij draaien,
# ook onder de drempel - want dan zit de warmte er wél aan te komen.
BATTERY_COOLING_OPPORTUNITY_IDLE_W = 300.0

# Hoe lang de goedkope koeling wacht voor hij opnieuw begint (v3.26.1).
#
# Uitzetten mag alleen als er ook een rem op het opnieuw aanzetten zit,
# anders keert het pendelen terug: op 18 augustus stond de omvormer een
# half uur na uitschakelen weer op 27 graden bij nul watt belasting.
#
# Twee uur bij een stille accu. Komt er wél belasting, dan geldt de
# gewone rusttijd van een half uur - dan is er een echte reden.
BATTERY_COOLING_OPPORTUNITY_REST_MINUTES = 120.0

# Boven deze temperatuur koelt de ventilator ALTIJD (v3.15.0).
#
# Gemeld: "Koelen mag niets te maken hebben met goedkoop of dure prijzen,
# hij moet wanneer nodig altijd koelen."
#
# Prijzen raakten de koeling al nergens. Maar in leermodus of bij
# handmatige overname werd de ventilator niet geschakeld, ook niet bij
# een te warme accu.
#
# Voor de accusturing is dat terecht - die schakelaars zeggen "raak mijn
# accu niet aan". Maar een ventilator laadt of ontlaadt niets; hij
# beschermt alleen.
#
# Deze grens ligt bij de gewone aanzetdrempel: daaronder is koelen een
# optimalisatie die mag wijken, daarboven is het bescherming die voorgaat.
BATTERY_COOLING_PROTECT_ALWAYS_C = 35.0

BATTERY_COOLING_ON_DELTA_C = 5.0
BATTERY_COOLING_OFF_DELTA_C = 2.0

# Warmte in een omvormer schaalt met het vermogen dat erdoorheen gaat -
# dit is de meest betekenisvolle regel van de vier.
BATTERY_COOLING_ON_POWER_W = 500.0
BATTERY_COOLING_ON_POWER_DELTA_C = 2.0
BATTERY_COOLING_OFF_POWER_W = 300.0

BATTERY_COOLING_ON_HIGH_POWER_W = 1500.0
BATTERY_COOLING_ON_HIGH_POWER_TEMP_C = 40.0

# Boven deze temperatuur blijft de ventilator draaien ongeacht het
# verschil met buiten - zolang er tenminste iets te koelen valt.
BATTERY_COOLING_KEEP_RUNNING_ABOVE_C = 42.0

# --- Minimale loop- en rusttijd (v1.99.0) ----------------------------
# Gevonden bij de controle van 15 augustus: de ventilator pendelde die
# nacht DERTIEN keer tussen 31 en 35 graden, om de twintig minuten.
#
# Dat is geen sensorruis - de hysterese van v1.76.0 vangt dat al. Het is
# echt thermisch pendelen: de ventilator koelt de omvormer in enkele
# minuten van 35 naar 31, waarna hij weer opwarmt. Het systeem is dus
# sneller dan de band tussen 32 en 35 breed is.
#
# Een bredere band zou betekenen dat de omvormer onnodig warm wordt
# gehouden. Een minimale loop- en rusttijd is de gebruikelijke oplossing
# bij ventilatoren en compressoren: hij lost het pendelen op zonder aan
# de temperatuurgrenzen te sleutelen.
#
# Twintig minuten is de gemeten cyclusduur; dertig zit daar net boven en
# halveert het aantal schakelingen ruwweg.
BATTERY_COOLING_MIN_RUNTIME_MINUTES = 30.0
BATTERY_COOLING_MIN_REST_MINUTES = 30.0

# --- Zelfcontrole (v2.0.0) -------------------------------------------
# Gevraagd: "Kun je dit soort zaken ook live in de integratie analyseren
# (...) zodat ik live kan zien dat een berekening ofzo niet klopt."
#
# Twee ticks missen kan; een half uur stilte niet.
CONSISTENCY_TICK_STALE_MINUTES = 20.0

# --- Hoe zwaar is een ronde? (v2.1.0) --------------------------------
# Gevraagd: "Nu wordt alle data om de 5 minuten gerefreshed, wat als we
# naar live gaan? Hoe belastend is dat?"
#
# Niet te schatten zonder te meten - in een testomgeving zonder echte
# prijzen bouwt de kwartierplanning niet, en dat is juist het zwaarste
# deel. Dus meet de integratie het zelf.
TICK_DURATION_HISTORY_LENGTH = 100

# Boven dit aandeel van de tijd staat Home Assistant te vaak op deze
# integratie te wachten. Vijf procent is streng genoeg om ruimte te laten
# voor alle andere integraties.
TICK_MAX_DUTY_FRACTION = 0.05

# Los van het AANDEEL van de tijd telt ook de duur van één ronde: zolang
# die loopt staat de event loop stil. Gemeten op deze installatie: 5613
# ms voor de eerste ronde na een herstart - twintig keer meer dan
# verwacht.
#
# Boven een seconde is dat merkbaar voor de rest van Home Assistant,
# ongeacht hoe vaak het gebeurt.
TICK_MAX_STALL_MS = 1000.0

# Hoeveel metingen per onderdeel worden bewaard.
TICK_PART_HISTORY_LENGTH = 50

# De ventilator schakelde in de nacht van 15 augustus dertien keer,
# ongeveer om de twintig minuten.
#
# v2.0.3: over een VENSTER, niet vanaf middernacht. Gemeld: "18
# schakelingen vandaag" - dat telde ook de uren van voor de minimale
# looptijd uit v1.99.0, die die middag pas was geinstalleerd. Een
# controle die terugkijkt naar een periode waarin de reparatie nog niet
# draaide, meldt een probleem dat al opgelost is.
#
# Zes uur is lang genoeg om pendelen te zien en kort genoeg om snel te
# merken dat het over is. Bij een minimale loop- en rusttijd van een half
# uur zijn er hoogstens twaalf schakelingen in zes uur mogelijk; zes is
# dus ruim boven normaal en onder het maximum.
COOLING_SWITCH_WINDOW_HOURS = 6.0
CONSISTENCY_MAX_COOLING_SWITCHES_PER_WINDOW = 6

# --- Logboek met drie prioriteiten (v2.1.0) --------------------------
# Gevraagd: "Misschien een soort logboek? Waarbij ik live besluiten, en
# allerlei zaken kan zien? Dit in 3 prio's definieren, en bij een
# kritische melding een melding naar mijn iPhone?"
#
# De bouwstenen lagen er al, maar verspreid over vier losse reeksen:
# modusveranderingen, meldingen, koelschakelingen en energiebrug. Het
# logboek voegt ze samen op moment, zodat je één tijdlijn hebt.
#
# Bewust GEEN vijfde reeks die alles nog eens apart bijhoudt: dan kunnen
# de twee uit elkaar gaan lopen, en dat is precies waar het deze week een
# paar keer misging.
LOG_PRIO_KRITIEK = "kritiek"
LOG_PRIO_AANDACHT = "aandacht"
LOG_PRIO_INFO = "info"

# Welke gebeurtenis welke prioriteit krijgt. Kritiek betekent: er gaat
# geld of comfort verloren, of de integratie doet iets anders dan
# bedoeld. Aandacht: het vraagt een beslissing maar niet nu. Info: het
# hoort erbij en is achteraf nuttig.
LOG_PRIORITEITEN = {
    # Kritiek - hier gaat iets mis.
    "interne_fout": LOG_PRIO_KRITIEK,
    "proefstand_rijp": LOG_PRIO_INFO,
    "zelfcontrole": LOG_PRIO_KRITIEK,
    "plan_tekort": LOG_PRIO_KRITIEK,
    "battery_wont_last_night": LOG_PRIO_KRITIEK,
    "sensor_unavailable": LOG_PRIO_KRITIEK,
    "integration_error": LOG_PRIO_KRITIEK,
    "low_soc_before_peak": LOG_PRIO_KRITIEK,
    # v3.27.1: gevraagd "melding wanneer accu in kalibratie modus 100%
    # bereikt, indien mogelijk kritisch". Kritiek is hier de juiste
    # soort: de kalibratie is klaar en er moet iets GEBEUREN - stand
    # uit, ondergrens terug. Blijft die melding in de wachtrij hangen,
    # dan staat de sturing uren onnodig stil.
    "kalibratie_vol": LOG_PRIO_KRITIEK,
    # Aandacht - het vraagt een beslissing.
    "plan_verkoop_geblokkeerd": LOG_PRIO_AANDACHT,
    "battery_module_drift": LOG_PRIO_AANDACHT,
    "device_drift": LOG_PRIO_AANDACHT,
    "solar_underperforming": LOG_PRIO_AANDACHT,
    "pv_orientation_mismatch": LOG_PRIO_AANDACHT,
    "vakantie_beweging": LOG_PRIO_AANDACHT,
    "sluipverbruik": LOG_PRIO_AANDACHT,
    "terugval": LOG_PRIO_AANDACHT,
    "exceptional_peak_price": LOG_PRIO_AANDACHT,
    "cost_mismatch": LOG_PRIO_AANDACHT,
    # Info - het hoort erbij.
    "mode_change": LOG_PRIO_INFO,
    "plan_uitstel": LOG_PRIO_INFO,
    "plan_tekort_hersteld": LOG_PRIO_INFO,
    "battery_cooling": LOG_PRIO_INFO,
    "appliance_ready": LOG_PRIO_INFO,
    "energiebrug": LOG_PRIO_INFO,
    "battery_full_with_sun": LOG_PRIO_INFO,
    "cheap_block_soon": LOG_PRIO_INFO,
    "negative_prices": LOG_PRIO_INFO,
    "low_solar_day": LOG_PRIO_INFO,
    "module_became_ready": LOG_PRIO_INFO,
    "appliance_cheap_moment": LOG_PRIO_INFO,
    "daily_summary": LOG_PRIO_INFO,
    "monthly_summary": LOG_PRIO_INFO,
    "besluit": LOG_PRIO_INFO,
}

# Hoeveel regels het logboek toont. Meer dan dit leest niemand, en de
# onderliggende reeksen bewaren het toch al.
LOG_MAX_REGELS = 120

# --- Integratiegezondheid (v2.2.0) -----------------------------------
# Voorgesteld: een gezondheidsscore van 0-100% op basis van
# API-beschikbaarheid, updatefrequentie, aantal fouten en
# dataconsistentie.
#
# De vier ONDERDELEN zijn goed gekozen en alle vier meetbaar. Het
# samenvoegen tot één percentage is dat niet: dat vraagt wegingen die
# nergens vandaan komen. Is 90% beschikbaarheid met perfecte consistentie
# beter of slechter dan 100% beschikbaarheid met een rekenfout? Elk
# antwoord daarop is verzonnen.
#
# Dezelfde afweging als bij de eerder afgevallen netkwaliteitsscore. Wat
# hier wel kan: de vier onderdelen apart tonen, elk met een eigen
# oordeel, en de STATUS laten bepalen door de slechtste. Een ketting is
# zo sterk als de zwakste schakel, en dat is geen aanname maar een
# definitie.
HEALTH_STATUS_GOED = "goed"
HEALTH_STATUS_AANDACHT = "aandacht"
HEALTH_STATUS_SLECHT = "slecht"

# Een sensor die bij minder dan dit deel van de rondes beweegt, levert
# geen bruikbaar tempo meer.
HEALTH_MIN_CADENCE_PERCENT = 20.0

# Meer dan dit aantal ticks zonder geslaagde ronde is een storing.
HEALTH_MAX_MISSED_TICKS = 3

# UITZETTEN alleen als ALLE drie tegelijk gelden - één voorwaarde die
# terugvalt is niet genoeg, anders slaat de ventilator af terwijl er nog
# een andere reden is om te blijven koelen. De waarden staan hierboven,
# bij hun tegenhangers.
#
# v1.80.0: hier stond een tweede, oudere set die de nieuwe overschreef -
# de reden waarom `KEEP_RUNNING_ABOVE` op 30 bleef staan terwijl er 42
# hoorde te gelden.

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

# --- Waar die drempels wél en niet gelden (v1.64.0) ------------------
# Gemeld: "Accumodule 1: celspanningsverschil 0.190 V - hoger dan
# gebruikelijk. Dit lijkt een standaard iets te zijn, gebeurt altijd
# nabij laden rond 100% SOC."
#
# Klopt, en het staat drie regels hierboven al in de code: LFP heeft een
# vlakke curve in het midden en STEILE UITEINDEN, waardoor het
# celspanningsverschil sterk SoC-afhankelijk is. Daarvoor zijn de
# SoC-vakken ooit aangelegd - maar de waarschuwing gebruikte gewoon de
# vaste drempel.
#
# De eigen metingen bevestigen het: module 1 staat in het vak van 70%
# op 0,00 tot 0,03 V. Diezelfde module meldt 0,190 V bij een volle accu.
# Dat is geen onbalans maar natuurkunde.
#
# Buiten dit bereik gelden de absolute drempels niet meer. De
# DIFFERENTIELE vergelijking (module tegen de andere modules op hetzelfde
# moment) blijft wél gelden - die heeft geen last van de SoC, want alle
# modules zitten op vrijwel dezelfde stand.
BATTERY_MODULE_FLAT_SOC_MIN_PERCENT = 20.0
BATTERY_MODULE_FLAT_SOC_MAX_PERCENT = 90.0

# In de steile uiteinden wordt vergeleken met wat voor DEZE module in
# DIT SoC-vak gebruikelijk is. Boven de mediaan plus deze marge is het
# alsnog het vermelden waard.
BATTERY_MODULE_BUCKET_DELTA_MARGIN_V = 0.08

# Onder dit aantal metingen in een vak zegt de mediaan te weinig; dan
# liever niets melden dan een drempel op drie waarnemingen.
BATTERY_MODULE_BUCKET_MIN_SAMPLES = 20

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
# Vanaf welke laadstand een kalibratie als "vol" telt (v3.27.0).
#
# De BMS balanceert bovenin. Precies 100% halen sommige pakketten nooit,
# en wachten op een getal dat niet komt levert geen meting op.
KALIBRATIE_VOL_PERCENT = 99.0

PERSISTED_PLAIN_FIELDS = (
    # v3.27.0: de kalibratiestand en de momentopname bovenin. Een
    # kalibratie duurt uren; een herstart halverwege mag hem niet
    # stilzwijgend afbreken, en de meting op vol mag niet verdwijnen.
    "kalibratie",
    "kalibratie_momentopname",
    # v1.16.5, gemeld: "Vandaag: 0.0 kWh opgewekt" terwijl de omvormer
    # 15,5 kWh had geproduceerd.
    #
    # De dagsleutel en `pv_production_today_kwh` werden wél bewaard, maar
    # het IJKPUNT van de kWh-meter niet. Na een herstart klopt de
    # dagsleutel dus - geen dagwissel, geen reset - maar
    # `_pv_energy_meter_day_start` is None, waarna
    # `_verwerk_pv_meterstand` opnieuw ijkt op de huidige meterstand. De
    # opwek wordt dan meterstand min huidige stand = 0,0, en dat
    # overschrijft de bewaarde waarde.
    #
    # Zonder ijkpunt is een cumulatieve meter waardeloos: je weet niet
    # meer waar de dag begon.
    "_pv_energy_meter_day_start",
    "_pv_energy_meter_last",
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
    # v1.18.1: verwarmen of koelen per bin. Zonder bewaren zou na elke
    # herstart onbekend zijn welke kant de airco op ging.
    "living_room_temp_bucket_direction",
    # v1.18.2: het weekprofiel van aanwezigheid. Zonder bewaren zou elke
    # herstart het leren opnieuw laten beginnen.
    "presence_week_profile",
    # v1.20.5: welke sensor wanneer als laatste bewoog. Zonder bewaren
    # is de tabel na elke herstart leeg, terwijl juist die tabel moet
    # verklaren waarom de status is wat hij is.
    "presence_last_seen",
    # v1.26.0: het verloop thuis/weg/slaapt. Een tabel die na elke
    # herstart leeg is, valt niet achteraf te controleren - en dat is
    # precies waarvoor hij gevraagd werd.
    # v1.56.0: tot wanneer de knop "Nu laden" loopt. Een eindtijd, geen
    # teller - anders zet een herstart de klok terug op de volle
    # looptijd.
    "nu_laden_tot",
    "nu_laden_omslag",
    # v1.58.0: hoe lang een terugval al draait. Bij elke herstart
    # opnieuw beginnen zou "al drie dagen" onmogelijk maken - en dat is
    # precies het getal waar het om gaat.
    "fallback_since",
    # v1.59.0: de dagreeks van verouderingsdrijvers.
    "veroudering_history",
    "langere_horizon_history",
    "lange_reserve_history",
    "bijkoop_history",
    "netlading_vandaag_kwh",
    "netlading_kosten_eur",
    "netlading_history",
    "_eerder_rijpe_kandidaten",
    "pv_band_history",
    "pv_model_samples",
    # v1.90.0: de dagreeks waar zelfconsumptie per week/maand/jaar op
    # rust.
    "energy_daily_history",
    # v1.98.0: de stand van de laatste tick, zodat een herstart vlak voor
    # middernacht de dag niet met lege tellers afsluit.
    "_energiedagstand",
    # v2.3.0: de stand van de kostenmeter bij dagbegin, zodat "vandaag"
    # de aangroei toont en niet het totaal-ooit.
    "_kosten_meter_dagbegin",
    # v1.61.0: wat een cyclus werkelijk kostte, per apparaat gemeten.
    "appliance_cycle_kwh",
    "_appliance_cycle_history",
    "presence_timeline",
    # v1.30.0: de staat zelf ook. Zonder dat begint elke herstart op
    # "onbekend" en schrijft de eerste tick een nieuwe regel in de
    # tijdlijn, ook al is er niets veranderd.
    "presence_state",
    # v1.30.0: waarmee de rode "was ..."-markering wordt bepaald. Ging
    # verloren bij elke herstart, waarna elke wijziging weer als
    # "eerste voorspelling" gold.
    "quarter_plan_first_seen",
    # v1.31.0: het rapport plan-tegen-werkelijkheid. Juist dit mag geen
    # herstart verliezen - het gaat over dagen, niet over een tick.
    "charge_efficiency_history",
    "discharge_efficiency_history",
    # v1.38.0: de proefstand. Deze reeksen zijn het hele punt van
    # kandidaten die zich eerst moeten bewijzen - na een herstart
    # opnieuw beginnen zou dat onmogelijk maken.
    "daytype_consumption_profile",
    "capacity_trend_history",
    "price_shape_history",
    "proefstand_ledger",
    # --- v1.43.0 -----------------------------------------------------
    # Gevraagd: "Wordt nu echt alle data opgeslagen, zodat een herstart
    # nergens meer invloed op heeft?" Nagerekend, en het antwoord was
    # nee. Deze stonden er nog niet in:
    #
    # Beslissingen die JIJ hebt genomen. Een afgewezen dubbelpaar
    # opnieuw voorgeschoteld krijgen na elke herstart is het ergste van
    # de drie - dan doet wegklikken er niet toe.
    "nilm_dismissed_duplicate_pairs",
    # Apparaten die nog in de gaten worden gehouden maar nog niet
    # bevestigd zijn. Bevestigde apparaten werden al bewaard; de
    # kandidaten begonnen elke keer opnieuw.
    "nilm_unconfirmed_candidates",
    # Welke kraan of welk apparaat bij welk waterverbruik hoort.
    "water_source_profiles",
    # Maandtellers. Deze lopen per definitie over dagen; een herstart
    # halverwege de maand gooide ze op nul en daarmee ook het
    # maandoverzicht.
    "current_month_discharge_value_eur",
    "current_month_charge_cost_eur",
    "current_month_shortfall_days",
    "current_month_excess_days",
    "current_month_days_tracked",
    # De dagteller en de dagrapportage.
    "battery_discharge_today_kwh",
    "_daily_report_counters",
    # Welke planningswaarschuwing er al uit is. Zonder dit begint elke
    # herstart met een schone lei en gaat "Accu haalt de nacht mogelijk
    # niet" opnieuw af - te zien in de export van 11 augustus, waar hij
    # om 14:30, 15:31 en 16:31 langskwam.
    "_last_plan_alert",
    # v1.52.0: de accustand bij het begin van de dag, voor de correctie
    # op de dagbesparing. Gaat die verloren, dan valt de correctie weg op
    # precies de dagen waarop er herstart is.
    "_savings_day_start_available_kwh",
    # --- v1.49.0 -----------------------------------------------------
    # De dagstand van de PV-geometrie. `_finalize_pv_geometry_day` sluit
    # de dag af zodra de datum wisselt - maar na een herstart staat de
    # piek op 0 en wordt de dag stilzwijgend weggegooid. Met een herstart
    # ná de middagpiek is de rest van de dag bovendien te donker om als
    # "helder" door te komen, en telt die dag dus nooit mee.
    #
    # Dat maakt "0/5 heldere dagen" op een strakblauwe dag een
    # zelfvervullende voorspelling: elke versie die je installeert wist
    # de dag waarop gemeten werd.
    "_pv_geometry_day_peak_w",
    "_pv_geometry_day_peak_azimuth",
    "_pv_geometry_day_expected_peak_w",
    "plan_review_history",
    "plan_snapshot",
    # v1.74.0: de eindstand van de lopende dag, zodat een herstart vlak
    # voor middernacht de toetsing niet met lege tellers laat rekenen.
    "_plan_review_dagstand",
    # v1.20.0: wanneer er doorgaans naar bed wordt gegaan. Zonder
    # bewaren begint het leren na elke herstart opnieuw.
    "bedtime_history",
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
    "_notification_history_last",
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
    # v1.90.0: de dagreeks voor de zelfconsumptie over een week.
    "pv_daily_history",
    # v1.76.0: de export gesplitst in zon en accu, per tick gemeten.
    "solar_export_today_kwh",
    "battery_export_today_kwh",
    "gross_consumption_today_kwh",
    "grid_import_today_kwh",
    "grid_charge_today_kwh",
    "peak_power_today_w",
    "water_sessions_today_l",
    "water_sessions_today_count",
)

# Datum-sleutels van de dag/maand-rollovers. Zonder deze zouden de
# "vandaag"-tellers hierboven wél terugkomen maar bij de eerstvolgende
# tick meteen worden gewist, omdat de coordinator dan denkt dat er een
# nieuwe dag is begonnen - dan was het terugzetten zinloos geweest.
PERSISTED_DATE_FIELDS = (
    # v1.74.0: bij welke dag de plantoetsing staat. Zonder dit veld
    # begon elke herstart met een lege sleutel en werd de momentopname
    # van vanochtend weggegooid. Als DATUM bewaard, niet als tekst -
    # anders is de vergelijking met `now.date()` altijd ongelijk.
    "_plan_review_day_key",
    # v1.49.0: bij welke dag de piekgegevens hierboven horen.
    "_pv_geometry_day_key",
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
    # v1.30.0, gevraagd: "Let op alle gecreeerde data dient na een
    # herstart niet verloren te gaan."
    #
    # Deze twee stonden er niet in, en dat is te zien in de tijdlijn van
    # 11 augustus: de hele nacht "weg" terwijl er iemand lag te slapen.
    # De slaapherkenning kijkt of de slaapsensor de LAATSTE beweging
    # was; na een herstart was `last_bedtime_motion_at` leeg en kon die
    # vraag niet meer beantwoord worden. Wie al in bed ligt, loopt niet
    # opnieuw langs die sensor.
    "last_motion_at",
    "last_bedtime_motion_at",
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
    # v1.23.4: meldingen over de planning. Alleen wat er werkelijk toe
    # doet - elke moduswissel zou tientallen berichten per dag opleveren,
    # en dan zet je ze uit precies wanneer je ze nodig hebt.
    (
        "plan_tekort",
        "Accu haalt de nacht mogelijk niet",
        "Wanneer de kwartierplanning voorziet dat de accu leegraakt en de "
        "woning aan het net komt te hangen.",
        True,
        60,
    ),
    (
        "plan_uitstel",
        "Zon opvangen uitgesteld",
        "Wanneer de accu bewust later gaat laden omdat de zon straks "
        "goedkoper is, of wanneer dat weer stopt.",
        False,
        30,
    ),
    (
        "plan_verkoop_geblokkeerd",
        "Verkopen geblokkeerd voor de woning",
        "Wanneer er niet verkocht wordt omdat de eigen woning die energie "
        "nodig heeft.",
        False,
        120,
    ),
    # v1.20.1, gevraagd: "Als de vakantieknop actief is moeten er
    # meldingen bij beweging worden gestuurd (maximaal 1 per 5 minuten,
    # welke sensor beweging heeft gedetecteerd)."
    #
    # De demping staat op 5 minuten zoals gevraagd. Zonder die rem
    # levert één passage door een gang tientallen berichten op, en dan
    # zet je de melding uit - precies wanneer je hem wilt hebben.
    (
        "vakantie_beweging",
        "Beweging tijdens vakantiestand",
        "Wanneer een bewegingssensor afgaat terwijl de vakantiestand aan "
        "staat.",
        True,
        5,
    ),
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
        "proefstand_rijp",
        "Een kandidaat is klaar om mee te doen",
        "Wanneer een proefstandkandidaat van 'meet nog' naar 'klaar om mee "
        "te doen' springt - dus meting én winst zijn allebei becijferd.",
        True,
        1440,
    ),
    (
        "zelfcontrole",
        "Zelfcontrole vond een fout",
        "Wanneer twee getallen die elkaar moeten kloppen dat niet doen - "
        "een rekenfout of een teller die niet meeloopt.",
        True,
        120,
    ),
    (
        "battery_cooling",
        "Accu-koeling aan/uit",
        "Wanneer de koelventilator van de thuisaccu schakelt.",
        True,
        15,
    ),
    (
        "kalibratie_vol",
        "Kalibratie: accu is vol",
        "Wanneer de accu tijdens een kalibratie de 100% haalt. Kritiek, "
        "dus hij doorbreekt de stille stand van de telefoon.",
        True,
        60,
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
    # v1.29.0, gemeld: "Dat er een txt wordt gemaakt is een error, ik had
    # daar graag een melding van verwacht zoals eerder afgesproken."
    #
    # Terecht, en dit is de tweede keer. In v1.19.4 was de vraag "ik had
    # nu ook ergens een melding verwacht dat het systeem niet correct
    # functioneert", en toen heb ik er een AANDACHTSPUNT van gemaakt -
    # een regel op een dashboardpagina waar je naartoe moet klikken. Dat
    # is geen melding.
    #
    # Deze staat standaard AAN, tegen de regel in dat nieuwe meldingen
    # uit beginnen. Die regel gaat over ruis; dit gaat over een
    # integratie die stiekem half werkt. Hetzelfde argument als bij
    # "Accu haalt de nacht mogelijk niet".
    (
        "interne_fout",
        "Onderdeel van de integratie faalt",
        "Wanneer een onderdeel zichzelf niet kan berekenen - bijvoorbeeld "
        "wanneer de diagnostiek-export mislukt en als tekstbestand "
        "binnenkomt.",
        True,
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

# --- Azimut van de zon (v1.45.0) -------------------------------------
# Gemeld: "Vandaag was een mega zonnige dag: PV-installatieprofiel
# (oriëntatie) 0/5 heldere dagen verzameld."
#
# Het lag niet aan de bewolking. De azimut werd UITSLUITEND uit `sun.sun`
# gelezen, terwijl de zonshoogte wel een eigen instelbare sensor had.
# Ontbreekt dat attribuut - bijvoorbeeld omdat de zonstand van een eigen
# integratie komt - dan viel de hele leerroutine elke tick meteen stil:
# geen piekrichting, geen prestatie per windrichting, en dus eeuwig 0/5
# zonder dat er iets over bewolking te zeggen viel.
#
# Zelfde opzet als de zonshoogte: eigen sensor eerst, `sun.sun` als
# vangnet.
CONF_SUN_AZIMUTH_SENSOR = "sun_azimuth_sensor_entity"
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
    "interne_fout": (
        "✅ Alle onderdelen rekenen weer",
        "Geen enkel onderdeel meldt nog een fout; de diagnostiek-export "
        "hoort weer een JSON-bestand te geven.",
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

# --- kWh-meters voor de geschiedenis (v1.92.0) -----------------------
# Gevraagd: "Historische cijfers kun je toch meenemen?"
#
# Ja - Home Assistant houdt van elke energiesensor
# langetermijnstatistieken bij, per uur en jaren terug. Maar alleen van
# METERS (kWh, total_increasing); een vermogenssensor zou per uur
# geintegreerd moeten worden en dat wordt een schatting. Deze cijfers
# moeten naast een jaarafrekening kunnen liggen, dus dat is niet goed
# genoeg.
CONF_GRID_IMPORT_ENERGY_SENSOR = "grid_import_energy_sensor_entity"
CONF_GRID_EXPORT_ENERGY_SENSOR = "grid_export_energy_sensor_entity"

# --- Meer meters voor de geschiedenis (v1.97.0) ----------------------
# Gevraagd bij een screenshot waarop accu, kosten, CO2 en besparing nul
# stonden voor de langere perioden: "deze kunnen toch ook met data uit
# geschiedenis worden bepaald?"
#
# Deels. Wat een METER heeft, kan uit de statistieken:
#   - accu-ontlading: `sensor.zendure_export` of vergelijkbaar
#   - kosten: `sensor.zonneplan_electricity_delivery_costs_today` of de
#     kostensensor van de P1-meter
#
# CO2 volgt uit de al ingelezen netafname maal de intensiteit; daar is
# geen aparte meter voor nodig.
#
# BESPARING kan niet. Dat is het verschil met een tegenfeitelijke wereld
# zonder aansturing, en die is nooit ergens vastgelegd. Terugrekenen zou
# historische kwartierprijzen vragen die de prijssensor niet bewaart -
# en een geschat verschil naast echte cijfers zetten is erger dan een
# leeg vakje.
CONF_BATTERY_DISCHARGE_ENERGY_SENSOR = "battery_discharge_energy_sensor_entity"
CONF_COST_ENERGY_SENSOR = "cost_energy_sensor_entity"

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
    # v1.22.0: zon opvangen bewust uitgesteld naar een goedkoper uur.
    "solar_capture_deferred": "Zon opvangen uitgesteld (betere prijs nu)",
    # v1.55.0: de accu vasthouden omdat het net op dit moment goedkoper
    # is dan wat een kWh uit de accu kost.
    "grid_cheaper_than_battery": "net goedkoper dan de accu (accu vasthouden)",
    "arbitrage_solar_capture": "zonoverschot opvangen",
    "default_smart": "standaard slim laden",
    "discharging_window": "ontladen in duur blok",
    "emergency_low_battery": "noodladen bij lage accu",
    "expensive_quarter": "duur kwartier",
    "expensive_quarter_no_own_load": "duur kwartier, geen eigen verbruik",
    "expensive_quarter_soc_protected": "duur kwartier, accu beschermd",
    "force_manual": "handmatig overschreven",
    "kalibratie": "kalibratie van de accu",
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

# --- Ondergrens voor de zelfconsumptie (v1.16.8) ---------------------
# Uit een ochtendexport: opwek 0,215 kWh, export 0,56 kWh, zelfconsumptie
# 0,0%. Rekenkundig klopt dat - de begrenzing uit v1.9.2 kapt de export
# op de dagopwek, dus (0,215 - 0,215) / 0,215 = 0 - maar inhoudelijk is
# het misleidend: het suggereert dat er niets van de zon zelf wordt
# gebruikt.
#
# De werkelijkheid is dat de accu vannacht meer verkocht dan de zon die
# ochtend opwekte. Over een fractie van een kilowattuur valt geen zinnig
# aandeel te berekenen; het antwoord hoort dan "nog niet te zeggen" te
# zijn in plaats van een getal dat als slecht nieuws leest.
#
# Een halve kilowattuur is ruwweg een half uur zon op een heldere dag -
# genoeg om de verhouding betekenis te geven.
SELF_CONSUMPTION_MIN_PRODUCTION_KWH = 0.5

# --- Opeenvolgende tekorten (v1.16.8) --------------------------------
# Uit een export: tekorten op 7 en 8 augustus, twee dagen achter elkaar.
# De zelfevaluatie uit v1.14.0 zag dat niet, want die vraagt veertien
# dagen voordat ze iets zegt.
#
# Dat is verdedigbaar voor een VERHOUDING - vijf dagen zegt weinig over
# of de marge structureel te krap staat. Maar twee opeenvolgende
# tekorten is een patroon, geen ruis: het betekent dat er twee nachten
# op rij tegen de ochtendprijs is bijgekocht. Daar wil je nu van weten,
# niet over negen dagen.
RESERVE_CONSECUTIVE_SHORTFALL_ALERT = 2

# --- Werkstand van de accu (v1.16.9) ---------------------------------
# Gemeld: "Er is nog een betere weg,
# sensor.zendure_manager_operation_state" - met een screenshot waarop
# die sensor "Laden", "Ontladen" en "Inactief" toont.
#
# Dat is inderdaad beter dan het TEKEN van een vermogenssensor
# interpreteren. Bij deze installatie staat `invert_battery_power_sign`
# op True, en of dat klopt is uit een export niet vast te stellen -
# `measured_battery_power_w` stond op None. Een tekenfout zou laden als
# ontladen tellen, en dat werkt door in de zelfconsumptie.
#
# De accu zegt zelf wat hij doet. Geen interpretatie nodig.
CONF_BATTERY_STATE_SENSOR = "battery_state_sensor_entity"

# Waarden die "ontladen" betekenen. Zendure levert Nederlandse labels,
# maar een andere merk of taalinstelling kan afwijken - vandaar een
# lijst in plaats van één vergelijking.
# v1.21.4: exacte waarden in plaats van deelwoorden. "ontladen" bevat
# "laden", dus een deelwoordvergelijking maakte de uitkomst afhankelijk
# van de volgorde waarin er wordt getoetst - een valkuil die stilzwijgend
# omkeert zodra iemand die volgorde wijzigt.
#
# En de lijst was te kort: Zendure meldt afhankelijk van taal en firmware
# ook "standby", "idle" of Engelse termen. Een onbekende waarde telt nu
# als "niet ontladen", wat veiliger is dan gokken.
BATTERY_STATE_DISCHARGING = (
    "ontladen",
    "discharging",
    "discharge",
    "output",
)
BATTERY_STATE_CHARGING = (
    "laden",
    "opladen",
    "charging",
    "charge",
    "input",
)

# Bekend én expliciet "doet niets". Zonder deze lijst zou "Inactief"
# terugvallen op het vermogensteken, en dat meldt bij een ruststroom van
# een paar honderd watt ten onrechte ontlading.
BATTERY_STATE_IDLE = ("inactief", "idle", "standby", "stop", "gestopt")

# --- Waterontharder: realistische drempel (v1.18.0) ------------------
# Gemeld: "Ik weet zeker dat de waterontharder nog niet heeft
# geregenereerd, misschien de drempel anders leggen?"
#
# De drempel stond op 10 liter. Een echte regeneratie spoelt de harslaag
# met pekel en spoelt na: typisch 50 tot 200 liter, over 20 tot 60
# minuten. Tien liter haalt een wc-spoeling plus een kraan al.
#
# In de bewaarde geschiedenis staan sessies van 12,8 L in 2,5 minuten en
# 8,0 L in 4,5 minuten - duidelijk huishoudelijk verbruik dat tegen de
# oude drempel aan zat.
#
# Twee eisen samen, want volume alleen is niet genoeg: een regeneratie
# is óók traag. Een snelle sessie van 40 liter is eerder een bad of een
# lekkage.
WATER_SOFTENER_MIN_LITERS = 40.0
WATER_SOFTENER_MIN_DURATION_MINUTES = 15.0

# --- Waterverbruik toewijzen aan een bron (v1.18.0) ------------------
# Gevraagd: "Tevens is het volgens mij mogelijk om te detecteren waar
# water voor is gebruikt. Vaatwasser aan = water naar vaatwasser,
# wasmachine aan = water naar wasmachine. Ketel aan en waterverbruik
# langer dan 3 minuten is douchen, korter dan 3 minuten is
# tandenpoetsen. Quooker aan + waterverbruik is keuken."
#
# Dezelfde gedachte als NILM: een signaal dat toevallig samenvalt met
# waterverbruik zegt waarschijnlijk waar dat water heen ging. En net als
# bij NILM is een vermoeden geen zekerheid, dus komt er een
# bevestig/verwerp-mechanisme bij.
# De CV-ketel hoeft niet apart geconfigureerd te worden: die staat al
# bij de bevestigde NILM-apparaten (`sensor.cv_ketel_vermogen`,
# referentie 6,3 W). Gevraagd: "CV ketel kan toch op basis van het
# vermogen dat je al weet?" - klopt, en dat scheelt een instelling die
# fout ingevuld kan worden.
#
# Herkend aan de naam, want de entity_id verschilt per installatie.
WATER_BOILER_NAME_HINTS = ("cv-ketel", "cv ketel", "ketel", "boiler")

# Boven dit vermogen doet de ketel echt iets. De referentie in ruststand
# is een paar watt; warm water vragen tilt hem naar honderden.
WATER_BOILER_ACTIVE_W = 50.0

# Hoe lang een apparaat vóór of tijdens een watersessie actief moet zijn
# geweest om als bron te gelden. Een vaatwasser die tien minuten eerder
# aansloeg, vult nu.
WATER_SOURCE_MATCH_WINDOW_MINUTES = 10

# Ketel aan: langer dan dit is douchen, korter is tandenpoetsen of
# handen wassen.
WATER_SHOWER_MIN_DURATION_MINUTES = 3.0

# Een wc-spoeling is opvallend constant van volume - dat is juist wat
# hem herkenbaar maakt. De marge is ruim genoeg voor een spaarknop en
# voor verschillende reservoirs.
WATER_TOILET_TYPICAL_LITERS = 6.0
WATER_TOILET_TOLERANCE_LITERS = 2.5
WATER_TOILET_MAX_DURATION_MINUTES = 2.0

# Bevestigde toewijzingen per bron, voor het leren. Kort venster: het
# gaat om herkennen, niet om een archief.
WATER_SOURCE_HISTORY_LENGTH = 30

# --- Aanwezigheid uit bewegingssensoren (v1.18.2) --------------------
# Gevraagd: "Ook zijn er meerdere bewegingssensoren in huis aanwezig, ik
# wil dat je daarmee analyseert of er iemand thuis is of niet. Ook daar
# kun je van leren lijkt me."
#
# Bewust een instelbare lijst en geen automatische herkenning: van de
# twintig bewegingsachtige entiteiten in deze installatie zijn er
# meerdere BUITEN (deurbel, tuin, schuur). Die slaan aan als de kat
# langsloopt en zeggen niets over of er iemand thuis is. Welke sensor
# binnen hangt, weet alleen de bewoner.
CONF_PRESENCE_MOTION_SENSORS = "presence_motion_sensor_entities"

# Na hoeveel minuten zonder beweging het huis als leeg geldt. Ruim
# genomen: stilzitten op de bank of slapen is geen afwezigheid, en een
# te korte drempel zou 's nachts elk uur "niemand thuis" melden.
PRESENCE_ABSENCE_AFTER_MINUTES = 45

# Per kwartier van de week wordt bijgehouden hoe vaak er iemand thuis
# was. Een week is de natuurlijke cyclus: werkdagen verschillen van het
# weekend, en 's ochtends van 's avonds.
PRESENCE_HISTORY_WEEKS = 6

# Onder dit aantal waarnemingen per kwartier geen uitspraak doen - twee
# weken zegt nog niets over een vast patroon.
PRESENCE_MIN_OBSERVATIONS = 3

# --- Nachtvenster (v1.30.0) -----------------------------------------
# Gemeld: "Ik ging om 23:15 slapen, was snachts wel een tijdje wakker" -
# en de tijdlijn zei van 23:15 tot de ochtend "weg".
#
# Binnen dit venster geldt stilte als slapen in plaats van afwezigheid,
# MITS er net nog iemand thuis was. Ruim genomen: wie om 22:30 naar bed
# gaat hoort erin te vallen, en wie om 06:30 opstaat maakt vanzelf weer
# beweging.
PRESENCE_NIGHT_START_HOUR = 22
PRESENCE_NIGHT_END_HOUR = 7

# --- Tijdlijn van aanwezigheid (v1.26.0) ----------------------------
# Gevraagd: "Tevens in dit overzicht een 'time table' Thuis, weg slapen
# of iets dergelijks zodat ik achteraf kan controleren of het klopt."
#
# Het percentage per halfuur zegt wat er GEMIDDELD gebeurt; om te
# controleren of de afleiding klopt heb je het verloop zelf nodig - wat
# stond er wanneer, hoe lang, en welke sensor was de aanleiding.
#
# Alleen OVERGANGEN vastleggen. De staat wordt elke tick opnieuw
# bepaald; elke tick wegschrijven levert 288 regels per dag op die
# allemaal hetzelfde zeggen.
PRESENCE_TIMELINE_LENGTH = 120

# Blokjes korter dan dit tellen als flikkering en worden samengevoegd
# met wat eraan voorafging. Zonder deze regel staat er bij één beweging
# midden in de nacht "slaapt - thuis - slaapt" in de tabel, en dat maakt
# hem onleesbaar terwijl er niets is gebeurd.
#
# v1.78.0: van 5 naar 10 minuten. In de tijdlijn van 13 augustus staat
# een blok van precies 5 minuten "weg" tussen twee keer "thuis" - net te
# lang om samengevoegd te worden. Zulke flikkeringen horen weg te vallen.
PRESENCE_TIMELINE_MIN_MINUTES = 10

# Hoeveel regels het dashboard toont. De rest blijft bewaard en staat in
# de diagnostiek-export; een tabel van 120 regels leest niemand, en de
# attributen van deze sensor hebben een grens (zie v1.25.0).
PRESENCE_TIMELINE_SHOWN = 30

# --- Nachtvenster van de waterontharder instelbaar (v1.19.6) --------
# Gemeld: "Dit was overdag, ik weet dat de waterontharder het meestal
# tussen 02:00 en 05:00 doet."
#
# Belangrijke correctie: ik stond op het punt het nachtvenster te laten
# vallen, omdat een sessie van 114 liter in 17 minuten om 10:26 aan alle
# volume- en duureisen voldeed. Die kwam niet van de ontharder maar van
# een bad of de tuin - en zonder venster was dat als regeneratie geteld.
#
# Het venster is dus juist WEL het onderscheidende kenmerk. Wat wel
# beter kan: het staat vast op 00:00-06:00, terwijl deze ontharder
# tussen 02:00 en 05:00 draait. Een bad om 23:30 valt nu binnen het
# venster, met de werkelijke tijden erbuiten.
#
# Instelbaar dus, want de bewoner weet wanneer zijn ontharder draait en
# de integratie niet.
CONF_WATER_SOFTENER_START_HOUR = "water_softener_start_hour"
CONF_WATER_SOFTENER_END_HOUR = "water_softener_end_hour"

# --- Slapen herkennen (v1.20.0) --------------------------------------
# Gemeld: "Als de overloop sensor als laatste beweging heeft gedetecteerd
# 's avonds/'s nachts zijn we wel thuis maar slapen we."
#
# Scherp onderscheid. Zonder dat kenmerk ziet stilte er hetzelfde uit,
# terwijl "niemand thuis" en "iedereen slaapt" tegengestelde situaties
# zijn: bij afwezigheid mag alles uit, bij slapen moet de nachtreserve
# juist kloppen en loopt het basisverbruik gewoon door.
#
# Welke sensor de overgang markeert, weet alleen de bewoner - een
# overloop, een trap, een slaapkamer. Vandaar instelbaar.
CONF_PRESENCE_BEDTIME_SENSOR = "presence_bedtime_sensor_entity"

# Buiten deze uren telt de overloop niet als naar bed gaan; overdag loop
# je er ook langs.
PRESENCE_BEDTIME_EARLIEST_HOUR = 20
PRESENCE_BEDTIME_LATEST_HOUR = 5

# Hoe lang na de laatste beweging op de slaapsensor het als slapen
# geldt. Ruim, want een nacht duurt langer dan de gewone
# afwezigheidsdrempel.
PRESENCE_SLEEP_WINDOW_HOURS = 12

# --- Aanwezigheid: sneller en met bron (v1.20.1) ---------------------
# Gevraagd: "Ik wil sneller zien of er iemand wel of niet aanwezig is.
# Ook wil ik een tabel met welke sensor als laatst gedetecteerd heeft.
# Als de vakantieknop actief is moeten er meldingen bij beweging worden
# gestuurd (maximaal 1 per 5 minuten, welke sensor beweging heeft
# gedetecteerd). Als de televisie aan is, kan dit ook als aanwezig
# worden gekenmerkt."
#
# De drempel van 45 minuten was gekozen om stilzitten op de bank niet
# als afwezigheid te tellen. Met de tv als extra signaal is die reden
# grotendeels weg: wie stil op de bank zit, kijkt meestal tv. Daarom nu
# een veel kortere drempel.
#
# v1.78.0, gemeld: "De aanwezigheid sensor wijzigt te snel naar weg,
# misschien de tijd voor analyse verlengen?"
#
# Eerst een verkeerde verklaring van mijn kant: ik dacht dat iemand naar
# de douche kon lopen zonder langs een sensor te komen. Weerlegd - "als
# je de doucheruimte in loopt loop je langs de bewegingssensor op de
# overloop". Het gaat dus niet om ontbrekende dekking maar puur om de
# lengte van de stilte.
#
# De eigen tijdlijn van vier dagen wijst de drempel aan. Van de 24
# weg-blokken duurden er ACHT precies vijf tot zeven minuten - dat is
# geflikker, geen vertrek. Daarboven zit een gat, en pas bij een kwartier
# beginnen de echte blokken:
#
#   drempel 10 min ->  1 van de 24 blokken vervalt
#   drempel 15 min ->  8
#   drempel 20 min -> 10
#   drempel 25 min -> 13
#   drempel 45 min -> 18
#
# De aanname achter de tien minuten was: "wie stil zit, kijkt tv". Die
# gaat 's avonds op de bank op, maar niet 's ochtends: de blokken van
# 07:00-07:49 en 07:00-07:34 vielen precies in het uur na het opstaan.
#
# Twintig minuten haalt het geflikker weg en laat de blokken van twintig
# minuten en langer staan - die kunnen een echt vertrek zijn. Instelbaar,
# want hoe lang stilte normaal is hangt van het huis en de sensoren af.
PRESENCE_ABSENCE_AFTER_MINUTES_FAST = 20
CONF_PRESENCE_ABSENCE_MINUTES = "presence_absence_minutes"

# Hoeveel bewegingen er per sensor worden onthouden voor de tabel.
PRESENCE_LAST_SEEN_LENGTH = 12

# Tv aan telt als aanwezig - ongeacht hoe lang er niemand langs een
# sensor liep.
CONF_PRESENCE_TV_ENTITY = "presence_tv_entity"

# --- Lampen als aanwezigheidssignaal (v1.36.0) -----------------------
# Gevraagd: "Voor aanwezigheids detectie, kan ook nog gekeken naar
# lampen of heb ik dat niet goed?"
#
# Klopt, dat gebeurde nog niet - terwijl de systeemscan de lampen al
# WEL verzamelde, met als reden "useful context for a smarter,
# usage-aware EMS". Ze stonden er dus wel in en werden nergens gebruikt.
#
# Een brandende lamp is hetzelfde soort signaal als de tv: het zegt
# niets over BEWEGING, maar wel dat er iemand is. Twee dingen om op te
# letten, en daarom een eigen lijst in plaats van "alle lampen":
#
# 1. Alleen lampen BINNEN. Een buitenlamp of tuinverlichting op een
#    tijdklok brandt elke winteravond en zou het huis permanent bewoond
#    verklaren.
# 2. Tijdens de VAKANTIESTAND tellen ze niet mee. De eigen automatisering
#    "Vakantie Rolluiken + Verlichting" zet lampen juist aan om
#    aanwezigheid na te bootsen; die als bewijs van aanwezigheid nemen
#    is een cirkelredenering - en het zou de inbraakmelding smoren,
#    precies wanneer je hem nodig hebt.
CONF_PRESENCE_LIGHT_ENTITIES = "presence_light_entities"

# --- Stromend water telt als aanwezig (v1.78.0) ----------------------
# Gemeld: "De aanwezigheid sensor wijzigt te snel naar weg."
#
# De langste stiltes vallen waar geen bewegingssensor hangt: de badkamer
# en het toilet. Precies daar loopt water - en die sensor is er al, voor
# het waterverbruik. Hij werd alleen niet voor aanwezigheid gebruikt.
#
# Sterker signaal dan een lamp: water loopt niet vanzelf, en er is geen
# tijdklok die het aanzet. Vandaar dat het ook tijdens de vakantiestand
# blijft tellen, in tegenstelling tot de verlichting.
PRESENCE_WATER_MIN_LITERS_PER_MINUTE = 0.5

# Bij vakantiestand: melding bij beweging, maar hoogstens één per vijf
# minuten. Zonder die rem levert een sensor in een gang tientallen
# berichten op bij één passage.
PRESENCE_INTRUSION_COOLDOWN_MINUTES = 5

# --- Weerbronnen wegen naar betrouwbaarheid (v1.20.2) ----------------
# Gemeld: "De bewolking nakijken, het is nu bijna onbewolkt" - terwijl
# de integratie 62% toonde, het gemiddelde van 78,1% en 46,0%.
#
# Die twee bronnen zijn niet even goed: over 200 waarnemingen kwam
# openweathermap in 90,5% van de gevallen overeen met wat de panelen
# deden, forecast_thuis in 81,5%. Een plat gemiddelde weegt ze even
# zwaar en trekt de uitkomst richting de slechtste bron.
#
# Onder dit aantal waarnemingen blijft het een gewoon gemiddelde: dan is
# er niets om betrouwbaar op te wegen.
WEATHER_WEIGHT_MIN_OBSERVATIONS = 50

# Bij dit verschil tussen bronnen is middelen niet zinvol meer: het
# gemiddelde past dan bij geen van beide. Gemeten geval: 78,1% tegen
# 46,0% - dat is geen ruis maar onenigheid, en dan hoort de bron te
# winnen die het aantoonbaar vaker bij het rechte eind heeft.
WEATHER_DISAGREEMENT_PREFER_BEST_PP = 25.0

# Hoeveel betrouwbaarder die bron dan minstens moet zijn. Zonder marge
# zou een toevallig verschil van een half procent al de doorslag geven.
WEATHER_BEST_SOURCE_MIN_LEAD_PP = 5.0

# --- Prijzen voor het uitbreidingsadvies (v1.20.6) -------------------
# Opgegeven: omvormer 374 euro, accumodule 729 euro, beide inclusief btw
# (Zendure SolarFlow 2400 AC met AB3000X, 2880 Wh).
#
# Eerder werd met 959 euro voor de omvormer gerekend - dat bleek de
# bundelprijs met module. Een losse omvormer is minder dan de helft
# daarvan, en dat verandert de afweging wezenlijk: vermogen bijkopen is
# veel goedkoper dan capaciteit.
#
# Instelbaar, want prijzen veranderen en verschillen per leverancier.
CONF_BATTERY_MODULE_PRICE_EUR = "battery_module_price_eur"
CONF_BATTERY_INVERTER_PRICE_EUR = "battery_inverter_price_eur"
DEFAULT_BATTERY_MODULE_PRICE_EUR = 729.0
DEFAULT_BATTERY_INVERTER_PRICE_EUR = 374.0

# Capaciteit van één AB3000X.
BATTERY_MODULE_CAPACITY_KWH = 2.88

# --- Slijtagekosten per kWh (v1.38.0) --------------------------------
# Gevraagd: "Zijn er nog meer typische EMS dingen welke we kunnen
# toevoegen?" Dit was punt 1 van vijf: de cyclustelling bestond al,
# maar wat een cyclus KOST zat nergens in een afweging.
#
# Rekening met de echte prijzen: 3 x 729 euro over de bruikbare
# capaciteit (7,74 kWh) en het aantal cycli dat de fabrikant belooft.
#
# Let op waar dit WEL en NIET telt. Ontladen naar het huis of naar het
# net is dezelfde slijtage, dus daartussen kiest het niets. Waar het wél
# telt is de vraag of energie überhaupt door de accu moet: zon direct
# terugleveren kost niets, zon opslaan en later gebruiken kost een halve
# slag heen en een halve terug.
#
# Zendure geeft 6000 cycli tot 80% restcapaciteit voor de AB3000X.
# Instelbaar, want dat getal is een belofte van de fabrikant en geen
# meting - en het wordt vanzelf toetsbaar zodra de gezondheidstrend
# erbij komt (punt 4).
CONF_BATTERY_CYCLE_LIFE = "battery_cycle_life"
DEFAULT_BATTERY_CYCLE_LIFE = 6000

# Onder deze marge is doorzetten door de accu het niet waard: de
# slijtage plus het rendementsverlies eet de winst op. Puur informatief
# zolang er niets op wordt gestuurd.
WEAR_COST_MIN_MARGIN_EUR = 0.02

# --- Proefstand (v1.38.0) --------------------------------------------
# Gevraagd: "Misschien eerst integreren totdat ze daadwerkelijk gaan
# meebewegen? Dus een extra onzichtbaar tabblad waar waardes zichtbaar
# zijn hoe betrouwbaar etc."
#
# Precies de goede volgorde, en dezelfde die bij de plantoetsing werkte:
# eerst meten, dan pas sturen. Vijf kandidaten rekenen mee en sturen
# niets; wie zich bewijst gaat mee in de besluitvorming - één tegelijk,
# zodat bij een afwijking te zien is welke het deed.
CAPACITY_TREND_HISTORY_DAYS = 400
PRICE_SHAPE_HISTORY_DAYS = 60

# Onder dit aantal waarnemingen per uur zegt een mediaan niets.
PROEFSTAND_MIN_SAMPLES = 3
# En onder dit aantal uren is het beeld te mager om iets over de dag te
# zeggen.
PROEFSTAND_MIN_HOURS = 12
# Capaciteitsverlies is enkele procenten per jaar; een korte reeks zegt
# niets.
PROEFSTAND_MIN_TREND_DAYS = 30
# Onder dit verschil is het splitsen van het verbruiksprofiel het niet
# waard: dan verlies je aan waarnemingen wat je aan scherpte wint.
PROEFSTAND_DAYTYPE_MIN_DIFF_PERCENT = 10.0
# Boven deze spreiding verschilt de prijsvorm te veel per dag om op te
# bouwen.
PROEFSTAND_SHAPE_MAX_SPREAD = 0.25

# Hoeveel dagen aan boekingen worden bewaard. Gevraagd: "Dan dus ook
# aangeven wat het opgeleverd zou hebben als ze wel zouden sturen."
# Zonder bedrag is "betrouwbaar" geen argument om iets aan te zetten.
PROEFSTAND_LEDGER_DAYS = 120

# --- VERVALLEN in v1.75.0 --------------------------------------------
# Hier stond `POST_SALDEREN_BARE_SHARE = 0.23`: het kale tarief als vast
# DEEL van de belaste prijs.
#
# Die aanname klopte niet. Energiebelasting plus BTW is een vast BEDRAG
# per kWh - bij deze aansluiting 11,1 ct - en geen vast percentage. Bij
# 30 ct belast is kaal 19 ct (63%), bij 13 ct is kaal 1,9 ct (15%). Eén
# breuk kan dat niet vangen.
#
# Daardoor meldde de proefstand "EUR 0,61 in plaats van EUR 3,90" - een
# daling van 84%, terwijl het met de gemeten cijfers 37% is.
#
# Het bedrag wordt nu gemeten: het verschil tussen `price_tax_included`
# en `price_tax_excluded` uit dezelfde sensor.

# --- Meetuitval uitsluiten van de referentie (v1.21.0) ---------------
# Gemeld: het verbruik van koelkast/diepvries hangt af van de
# buitentemperatuur, want ze staan in een warme schuur.
#
# Dat klopt, maar er zat een groter probleem onder. De dagreeks van de
# diepvries wisselt tussen 0,8 W en 90 W: dertien dagen onder 5 W,
# twaalf dagen boven 60 W. Een dagGEMIDDELDE van 0,8 W betekent dat de
# compressor die hele dag niet draaide - voor een gevulde diepvries
# onmogelijk. Dat zijn dagen waarop de meter niets doorgaf.
#
# De mediaan over álle dagen belandde daardoor op 19,68 W, precies
# tussen beide groepen in. Vandaar de melding "+57,4% drift" terwijl
# 40,8 W gewoon een normale dag is.
#
# Dagen onder deze fractie van de mediaan van de actieve dagen tellen
# niet mee voor de referentie. Ruim gekozen: een koelkast die 's winters
# minder draait moet nog wel meetellen.
CUSUM_DROPOUT_FRACTION_OF_ACTIVE = 0.15

# --- Buitentemperatuur meewegen bij koeling (v1.21.0) ----------------
# Een koelkast in een schuur werkt harder als het buiten warm is. Zonder
# die correctie leest een warme week als een defect.
#
# Herkend aan de naam, want welke apparaten koelen weet de bewoner - en
# die namen staan al in de bevestigde apparaten.
COOLING_DEVICE_NAME_HINTS = (
    "koelkast",
    "diepvries",
    "vriezer",
    "vrieskist",
    "fridge",
    "freezer",
)

# Per graad buitentemperatuur boven het referentiepunt mag het verbruik
# met dit percentage stijgen zonder dat het drift heet. Vuistregel uit
# de koeltechniek: rond 3% per graad temperatuurverschil.
COOLING_DRIFT_PERCENT_PER_DEGREE = 3.0

# Onder dit aantal dagen met een temperatuurmeting geen correctie
# toepassen; dan is er niets om op te baseren.
COOLING_TEMP_MIN_DAYS = 5

# --- Fabrieksgrenzen SolarFlow 2400 AC (v1.21.1) ---------------------
# Uit de gebruikershandleiding (V1.2, 2025-03-31), sectie 9:
#
#   Max. In-/Uitgangsvermogen (net) : 2400 W
#   Accu laden/ontladen             : 2400 W / 2600 W max
#   Accuspanning                    : 37,5 - 54,75 V
#   Bedrijfstemperatuur             : -20 tot 60 °C
#   Maximaal 6 x AB3000X            : 17,28 kWh
#
# En de voorwaarde die het advies eerder ten onrechte "gratis" noemde:
# "De omvormer is ingesteld op een standaard uitgangsvermogen van 800W.
# Als u dit limiet wilt overschrijden, laat dan een gecertificeerde
# elektricien uw locatie bezoeken... Na verificatie kunt u via de
# Zendure-app aanvragen om het vermogen naar 2400W te verhogen."
#
# Nut voor de integratie: weten wat er nog aan kop zit, zonder te
# suggereren dat het zomaar kan.
SOLARFLOW_MAX_GRID_POWER_W = 2400.0
SOLARFLOW_DEFAULT_GRID_POWER_W = 800.0
SOLARFLOW_MAX_BATTERY_CHARGE_W = 2400.0
SOLARFLOW_MAX_MODULES = 6
SOLARFLOW_OPERATING_TEMP_MIN_C = -20.0
SOLARFLOW_OPERATING_TEMP_MAX_C = 60.0

# --- Bewust begrensd vermogen (v1.21.2) ------------------------------
# Gemeld: "Let wel op dat ik handmatig begrensd heb op 2000W laden 1600W
# ontladen."
#
# Het advies zag alleen dat 1600 en 2000 onder de fabrieksgrens van 2400
# liggen, en raadde aan ze te verhogen. Dat is ongefundeerd: het zijn
# bewuste keuzes, en de redenen daarvoor kent de integratie niet - de
# groep in de meterkast, cellen sparen, geluid van de ventilatoren, of
# gewoon marge willen houden.
#
# Advies geven waar iemand al een afweging heeft gemaakt is hinderlijk
# en ondermijnt de rest van het advies. Vandaar een instelling die zegt:
# deze grenzen zijn zo bedoeld, laat ze met rust.
CONF_POWER_LIMITS_INTENTIONAL = "power_limits_intentional"

# --- Genoeg metingen voor een dagoordeel (v1.21.3) -------------------
# Gemeld via de export: de diepvries meldde "-98,8% drift, mogelijk
# defect" op basis van VIJF metingen. Bij een tick van vijf minuten is
# dat 25 minuten - de integratie was net herstart, en een compressor die
# in dat kwartier net niet draaide geeft een laag gemiddelde.
#
# De uitvalfilter uit v1.21.0 werkt op de GESCHIEDENIS; de dag die nog
# loopt werd zonder ondergrens meegewogen. Eén meting volstond.
#
# Een halve dag aan metingen is nodig voordat een dagcijfer iets zegt
# over een apparaat dat in cycli werkt. Bij vijf minuten per tick zijn
# dat ruim acht uur.
NILM_MIN_SAMPLES_FOR_DAY = 100

# --- Koelapparaten meten als aan/uit (v1.50.0) -----------------------
# Gevraagd: "Het is toch simpelweg, aan/uit? Wordt er rekening gehouden
# met de buitentemp?"
#
# Allebei raak. Een diepvries is geen apparaat met een verbruik maar een
# compressor die aan- en uitslaat; het DAGGEMIDDELDE is het product van
# twee heel verschillende dingen:
#
#   daggemiddelde = vermogen tijdens draaien x aandeel van de dag draaiend
#
# Die twee door elkaar meten maakt het onmogelijk te zeggen wat er aan
# de hand is. Loopt het vermogen tijdens draaien op, dan is er
# mechanisch iets; loopt de inschakelduur op, dan is er meer warmte -
# een warme schuur, een deur die openstond, een slechte afdichting.
#
# En het verklaart de reeks van de diepvries: 12 van de 30 dagen op
# 0,8 W, 13 dagen op 76-81 W. Dat is geen slijtage maar een sensor die
# hele dagen niets doorgaf. Op zo'n dag is de inschakelduur bijna nul,
# en dat is te zien - het daggemiddelde alleen laat het als "-98,8%
# drift, mogelijk defect" lezen.
#
# Boven deze grens telt een meting als "compressor draait". Ruim onder
# het draaivermogen van 76 W, ruim boven de ruis van een slimme stekker.
NILM_COMPRESSOR_ON_THRESHOLD_W = 15.0

# Draait de compressor minder dan dit deel van de dag, dan is er geen
# sprake van koelen maar van meetuitval. Een diepvries in een schuur
# draait ruwweg een kwart tot de helft van de tijd; onder de 5% doet hij
# niets, en dat kan een werkende diepvries niet.
NILM_COOLING_MIN_DUTY_CYCLE = 0.05

# --- Zonopvang uitstellen naar goedkope uren (v1.22.0) ---------------
# Gevraagd: "Ik had dus beter mijn inziens tot 11:30 smart_discharge
# kunnen doen? Dan had in de uren daarvoor mij meer geld opgeleverd, dan
# terugleveren toen de accu vol was na ca. 13:15 tegen 13,6 ct."
#
# Klopt, en de simulatie op 10 augustus bevestigt het. Het mechanisme:
# de accu neemt een vast aantal kilowattuur op; WELKE dat zijn bepaalt
# welke je exporteert. Laadt hij vroeg, dan slurpt hij de dure
# ochtendzon op (26,8 ct) en exporteer je de goedkope middagzon (13,6
# ct). Laadt hij laat, dan andersom.
#
# Zelfde eind-SoC, zelfde totale export, andere prijzen. Over 4,45 kWh
# met 13 ct verschil is dat ongeveer een halve euro per dag.
#
# Gesimuleerde uitkomst (netto opbrengst over 09:54-18:34):
#   nu (altijd smart) : 1,657 EUR
#   omslag 11:00      : 1,884 EUR   (+0,23)
#   omslag 13:00      : 2,152 EUR   (+0,49)  <- optimum
#   omslag 15:00      : 2,053 EUR   (+0,40, maar accu niet meer vol)
#
# Let op de klif: bij 15:00 is er te weinig zon over, moet er 0,86 kWh
# worden bijgekocht en eindigt de accu op 6,13 in plaats van 7,30 kWh.
# Het optimum ligt vlak vóór die rand - en de PV-voorspelling zit
# gemiddeld 15% naast. Vandaar een marge.

# Gevraagd: "Ik denk dat we rekening moeten houden met ca. 25%, een
# soort kans zodat we zeker weten dat de accu rond 16:00 zo goed als vol
# is?"
#
# Dat is sterker dan een marge tot zonsondergang, en wel hierom: door de
# accu al om 16:00 vol te willen hebben, wordt de late middagzon het
# VANGNET in plaats van onderdeel van het plan. Valt de middag tegen,
# dan is er nog een paar uur zon over om het gat te dichten.
#
# De 25% komt daar bovenop: er moet een kwart meer overschot worden
# verwacht dan er ruimte is. Samen dekt dat de gemeten voorspelfout van
# gemiddeld 15% ruim.
SOLAR_DEFER_SAFETY_FACTOR = 1.25

# De accu hoort rond dit uur zo goed als vol te zijn. Wat er daarna nog
# aan zon komt, is marge - niet iets waar het plan op steunt.
SOLAR_DEFER_TARGET_FULL_HOUR = 16

# Onder dit prijsverschil tussen nu en het geplande opvangmoment is het
# de moeite niet: het risico op een tegenvallende middag weegt dan
# zwaarder dan de winst.
SOLAR_DEFER_MIN_PRICE_GAIN_EUR = 0.05

# v1.28.0: de ondergrens op de accustand is VERVALLEN. Hij werd gemeten
# als percentage van de bruikbare capaciteit terwijl de accustand die je
# ziet de echte is, dus 25% werkte in de praktijk als 32,5% - en op 11
# augustus hield hij het uitstellen tegen bij 25% echt, met 23 kWh zon
# op komst en 18 ct prijsverschil.
#
# Gevraagd: "Ik wil alleen dat op basis van prijs en verwachte PV
# opbrengst de modus later naar smart gaat."
#
# Een lege accu betekent alleen dat er meer ruimte te vullen is, en dat
# zit al in SOLAR_DEFER_SAFETY_FACTOR: het overschot moet 1,25x de
# ruimte zijn, dus hoe leger de accu hoe strenger die eis vanzelf wordt.

# Uitstellen kan alleen zolang er nog zon komt; na dit uur heeft het
# geen zin meer om te wachten.
SOLAR_DEFER_LATEST_HOUR = 15

# --- Geen verkoop op zonarme dagen (v1.23.0) -------------------------
# Gevraagd: "Let wel, het belangrijkste blijft dat de accu genoeg heeft
# voor de nacht ofwel mijn eigen woning van energie te voorzien." En op
# de vraag of er in de winter überhaupt verkocht mag worden: "dan alleen
# laden en indien nodig bijladen, en de eigen woning voeden, punt."
#
# Doorgerekend op een winterdag met 5 kWh zon tegen 7,4 kWh verbruik:
# de accu verkocht 's ochtends tot nul en stond daarna drie uur leeg
# terwijl het huis 25 tot 33 ct per kWh uit het net betaalde.
#
# De reserve deed wél zijn werk - die bewaarde 1,20 kWh voor de vier uur
# tot het goedkope blok. Maar verkopen gaat op 1600 W terwijl het huis
# 300 W trekt: ruim vijf keer zo snel. Binnen een uur stond de accu op
# de bodem, en daar bleef hij.
#
# Onder deze dagopbrengst wordt er dus niet verkocht. Wat er is, is voor
# de woning; wat ontbreekt wordt in het goedkope blok bijgeladen.
SOLAR_POOR_DAY_KWH = 5.0

# Ook als de dag zelf genoeg zon geeft, moet er ná de verkoop nog genoeg
# overblijven om de woning te voeden tot het volgende goedkope blok -
# mét deze marge. Anders staat de accu straks leeg terwijl het huis aan
# het net hangt.
# --- Zelfconsumptie over een venster (v1.90.0) -----------------------
# Gevraagd: "de zonne-energie van gisteren, opgeslagen in de batterij, is
# vannacht gebruikt - dat is toch ook zelfconsumptie?"
#
# Ja, en de formule telt dat ook zo. Maar de daggrens vertekent: wordt
# die opgeslagen zon de volgende ochtend verkocht, dan telt de export bij
# de opwek van die dag terwijl hij bij gisteren hoort.
#
# Een week is lang genoeg om dat tegen elkaar weg te laten vallen, en
# kort genoeg om nog iets over het seizoen te zeggen.
SELF_CONSUMPTION_WINDOW_DAYS = 7

# Onder deze opwek in het hele venster valt er geen zinnig aandeel te
# berekenen.
SELF_CONSUMPTION_MIN_KWH = 1.0

SELL_RESERVE_SAFETY_FACTOR = 1.5

# v1.27.0: de toets hierboven rekende met de NETTOSOM tot het goedkope
# blok - verbruik min zon over de hele periode. Daarmee werd de zon van
# MORGENOCHTEND afgetrokken van het verbruik van VANNACHT, en dat is
# precies de fout die `_estimate_worst_case_deficit_kwh` elders al
# oplost: zon komt overdag, en helpt vannacht niet.
#
# Op 10 augustus 20:54 gaf de nettosom 1,77 kWh nodig; het diepste
# tekort onderweg was 5,23 kWh. De planning verkocht 10 kwartieren en
# voorspelde daarna twee kwartieren waarin het huis aan het net hing.
#
# De marge mag hier lager dan 1,5: die factor compenseerde een basis die
# structureel te laag was. Het diepste tekort is zelf al voorzichtig (zon
# telt met rendement, live verbruik telt mee), dus 1,15 - gelijk aan wat
# de energiebrug aanhoudt.
SELL_RESERVE_DEEPEST_SAFETY_FACTOR = 1.15

# --- Kwartierplanning: vooruitkijken en wijzigingen (v1.23.2) --------
# Gevraagd: "De kwartierplanning pagina moet eigenlijk vooruitkijken
# zoveel prijzen er zijn, dus waarschijnlijk max. 36 regels. Als
# kwartieren inmiddels voorbij zijn hoeft het niet meer getoond te
# worden, als de waarde later door extra verbruik of iets dergelijks
# verandert (smart_discharge naar smart) bijvoorbeeld, wil ik dat de
# tekst rood gearceerd wordt."
#
# v1.25.0, gemeld: "De kwartierplanning toont niet de maximale aantal
# kwartieren vooruit (waarin zonneplan prijzen beschikbaar zijn)."
#
# Klopt. De vraag was "zoveel prijzen er zijn"; ik las de schatting
# "waarschijnlijk max. 36 regels" als de eis en zette er een harde grens
# van 36 op. Die schatting was te laag: Zonneplan publiceert de prijzen
# van morgen in de loop van de middag, en in de export van 10 augustus
# stonden er 109 kwartieren (27 uur) vooruit klaar terwijl de tabel er
# 36 toonde.
#
# Deze grens is nu alleen nog een fysiek plafond: 192 kwartieren is
# twee volle etmalen, meer dan er ooit aan prijzen binnenkomt. In de
# praktijk bepaalt het aantal beschikbare prijzen de lengte.
QUARTER_PLAN_MAX_ROWS = 192

# --- Plan tegen werkelijkheid (v1.31.0) ------------------------------
# Gevraagd: "Kun je de diagnostiek zo maken, dat je leert van het accu
# gedrag en morgen verder optimaliseert indien noodzakelijk?" Hiervan is
# dit stap een: METEN. Zonder meting is bijsturen blind.
#
# De momentopname wordt genomen zodra de dag echt begonnen is; 's nachts
# staat er nog geen zon in het plan.
PLAN_SNAPSHOT_HOUR = 8

# Dertig dagen is genoeg om een patroon te zien zonder dat een seizoen
# van maanden geleden blijft meepraten.
PLAN_REVIEW_HISTORY_DAYS = 30

# Binnen deze afwijking heet het plan gewoon te kloppen. De
# PV-voorspelling zit zelf al 15% naast (gemeten mediaan 10,4%), dus
# strenger meten zou elke dag een klacht opleveren.
PLAN_REVIEW_TOLERANCE_PERCENT = 20.0

# Voor de accustand geldt een absolute marge in procentpunten: een
# voorspelde 40% die 35% wordt is normaal, 40% die 12% wordt niet.
PLAN_REVIEW_SOC_TOLERANCE_PERCENT = 10.0

# Onder deze noemer zegt een procentuele afwijking niets: bij een
# voorspelling van 0,02 kWh is alles honderden procenten.
PLAN_REVIEW_MIN_BASIS = 0.5

# Een losse dag zegt niets over een structurele afwijking.
PLAN_REVIEW_MIN_DAYS = 5

# Wat er als eerste voor een kwartier werd voorspeld, wordt onthouden.
# Verandert de modus daarna, dan is dat zichtbaar - juist die
# wijzigingen zeggen iets over hoe betrouwbaar de planning is.
QUARTER_PLAN_SNAPSHOT_LENGTH = 200

# --- Meldingen over planningswijzigingen (v1.23.4) -------------------
# Gevraagd: "Tevens wil ik voor belangrijke beslissingen/wijzigingen in
# de planning graag een bericht op mijn telefoon en in het
# meldingen overzicht. Wel moeten meldingen op telefoon uit te schakelen
# zijn."
#
# Alleen melden wat er werkelijk toe doet. Elke moduswissel zou
# tientallen berichten per dag opleveren, en dan zet je ze uit -
# precies wanneer je ze nodig hebt.
#
# Deze drie zijn het waard:
#   - de accu haalt de nacht niet (tekortkwartieren in de planning)
#   - het zonopvang-uitstelplan gaat aan of uit
#   - verkopen wordt geblokkeerd omdat de woning voorgaat
# --- Wanneer is een tekort een melding waard? (v3.9.0) ---------------
# Gemeld: "Deze melding op dit tijdstip is een beetje raar toch?" bij
# "Den accu haalt de nacht weer" om 09:30 's ochtends.
#
# Uit de geschiedenis bleek meer: 75 meldingen over tekorten, waarvan er
# 47 op één dag (16 augustus). Twaalf keer ging het om EEN ENKEL
# kwartier, en om 06:44 stond "hersteld" met om 06:45 weer "tekort".
#
# Een kwartier tekort is bij dit verbruik zo'n 0,1 kWh van het net. Dat
# is geen probleem maar een planning die precies uitkomt - en bij een
# laagste stand van exact 10% kantelt elke kleine verschuiving in de
# zonverwachting het.
PLAN_SHORTFALL_ALERT_MIN_QUARTERS = 3

# En de omslag naar "hersteld" pas als het even stabiel is. De planning
# wordt elke ronde opnieuw gebouwd en schommelt rond de grens; zonder
# wachttijd krijg je bij elke passage een bericht.
PLAN_SHORTFALL_RECOVERY_STABLE_MINUTES = 30.0

PLAN_CHANGE_MIN_QUARTERS = 1

# --- Achterhoeks (v1.24.0) -------------------------------------------
# Gevraagd: "kan ik door middel van 1 switch alles in het Achterhoeks
# laten tonen, dus ook de meldingen op mijn iPhone?"
#
# De hele integratie vertalen zou ongeveer 1.664 losse teksten in de
# code raken plus ruim 3.000 labels op het dashboard. Alleen de
# MELDINGEN doen is een fractie daarvan en levert het leukste deel op:
# je telefoon spreekt Achterhoeks, het dashboard blijft leesbaar voor
# wie meekijkt.
#
# Let op: dit is een benadering van Achterhoeks Nedersaksisch, geen
# gecontroleerde streektaal. Klopt een woord niet, dan is het zo
# aangepast - het staat allemaal in deze ene tabel.
CONF_ACHTERHOEKS = "achterhoeks_meldingen"

# Titels per meldingsoort.
ACHTERHOEKS_TITELS = {
    "plan_tekort": "Den accu kump tekort",
    "plan_uitstel": "Zunne opvangen wödt uut-esteld",
    "plan_verkoop_geblokkeerd": "Verkopen geet neet, 't huus geet veur",
    "vakantie_beweging": "Der beweeg wat, terwiel gi-j weg bunt",
    "proefstand_rijp": "'n Kandidaat is now zo wied",
    "zelfcontrole": "Der klopt wat neet in de sommen",
    # v3.1.0: NIET "an of uut" - dat zegt niet wat er gebeurt.
    #
    # Gemeld: "Accukoeling an of uut - Accu 30.0°C, buiten 20.4°C (...)
    # nog maor 9.6°C boven buiten". Maar het is of hij gaat aan, of hij
    # gaat uit.
    #
    # De Nederlandse titel maakte dat onderscheid wel ("koeling AAN" /
    # "koeling UIT"); de vertaling gooide het weg door één vaste titel
    # voor de hele soort te gebruiken. Zie ACHTERHOEKS_TITELS_PER_ACTIE.
    "sluipverbruik": "'t Lik of der wat stiekem stroom vret",
    # v2.0.7: "veranderd", niet "verandert" - voltooid deelwoord na "is",
    # geen persoonsvorm. Gevonden bij het nakijken van de meldingen.
    "mode_change": "De stand is veranderd",
    "battery_wont_last_night": "Den accu haalt de nacht neet",
    "battery_full_with_sun": "Accu vol en de zunne schient nog",
    "low_soc_before_peak": "Weinig in den accu veur de duurte",
    "cheap_block_soon": "'t Goedkope blok begint zo",
    "negative_prices": "Prieze gaot onder nul",
    "exceptional_peak_price": "Uutzunderlek duur kwartier vandage",
    "solar_underperforming": "De zunne dut minder as verwacht",
    "low_solar_day": "Weinig-zunne-dag",
    "sensor_unavailable": "'n Sensor is d'r neet meer",
    "integration_error": "'t Systeem löp vast",
    "interne_fout": "'n Onderdeel rekent neet meer",
    # v1.46.0, gemeld: "Niet in het achterhoeks?" bij een
    # herstelmelding. De titels van de PROBLEEMmeldingen stonden er wel
    # in, die van het herstel niet - en woordvervanging alleen maakt van
    # "Accu haalt de nacht weer" niets Achterhoeks, want geen van die
    # woorden staat in de tabel.
    "plan_tekort_hersteld": "Den accu kump neet meer tekort",
    "battery_wont_last_night_hersteld": "Den accu haalt de nacht weer",
    "sensor_unavailable_hersteld": "De sensor dut 't weer",
    "integration_error_hersteld": "'t Systeem löp weer",
    # v2.0.7: TERUGGEDRAAID. Even stond hier "rekenen", omdat "Alle
    # onderdelen rekent" als een meervoudsfout oogde. Dat is het niet:
    # het Achterhoeks heeft een EENVORMIG MEERVOUD op -t. Twee regels
    # verderop staat "Prieze gaot onder nul", en die volgt dezelfde
    # regel.
    "interne_fout_hersteld": "Alle onderdelen rekent weer",
    "cost_mismatch_hersteld": "De kosten kloppen weer",
    "solar_underperforming_hersteld": "De zunne dut 't weer",
    "pv_orientation_mismatch_hersteld": "De PV-richting klop weer",
    "battery_module_drift_hersteld": "De accumodules loopt weer geliek",
    "battery_module_drift": "'n Accumodule löp uut de pas",
    "module_became_ready": "'n Adviesmodule is klaor",
    "pv_orientation_mismatch": "De PV-richting klop neet",
    "cost_mismatch": "De kosten kloppen neet met de rekening",
    "daily_summary": "Dagoverzicht",
    "monthly_summary": "Maondoverzicht",    # v3.0.2: deze vier hebben een WISSELENDE Nederlandse titel en
    # krijgen hun onderscheid uit ACHTERHOEKS_TITELS_PER_ACTIE. Wat
    # hieronder staat is de terugval als de actie niet af te leiden is.
    "battery_cooling": "Accukoeling",
    "kalibratie_vol": "De accu is vol - kalibratie klaor",
    "appliance_ready": "'n Apparaat is klaor",
    "appliance_cheap_moment": "Good moment veur 'n apparaat",
    "device_drift": "'n Apparaat wiekt af",

}

# Woorden die in de berichtteksten worden vervangen.
#
# VOLGORDE IS KRITISCH, en dat bleek meteen bij het proberen:
#   - "niets" moet vóór "niet", anders wordt het "neets"
#   - "goedkope" moet erin staan, anders maakt "goed" -> "good"
#     er "goodkope" van
#   - "iets" moet ná "niets", anders wordt "niets" -> "nwat"
# Langere woorden dus altijd eerst.
# --- Titels die van de ACTIE afhangen (v3.1.0) -----------------------
# Een vaste titel per soort werkt alleen als die soort altijd hetzelfde
# betekent. Bij de accukoeling is dat niet zo: aan en uit zijn
# tegenovergesteld, en "an of uut" laat de lezer raden.
ACHTERHOEKS_TITELS_PER_ACTIE = {
    ("battery_cooling", "aan"): "De koeling geet an",
    ("battery_cooling", "uit"): "De koeling geet uut",
    # v3.0.2: dezelfde behandeling voor de andere drie meldingen met een
    # wisselende titel. Gevonden bij het nazoeken van de koelmelding:
    # vier soorten verloren hun onderscheid, niet één.
    ("appliance_ready", "aan"): "'n Apparaat is klaor",
    ("appliance_cheap_moment", "aan"): "Now is 't goodkoop veur 'n apparaat",
    ("device_drift", "aan"): "'n Apparaat wiekt af van gewoon",
}

ACHTERHOEKS_WOORDEN = (
    # v1.35.0: gespeld volgens de WALD-spelling (Staring Instituut),
    # na de vraag "Helpt deze informatie nog voor de achterhoekse
    # vertaling om deze te verbeteren?" met een verwijzing naar de
    # uitgangspunten van die spelling en de Achterhoekse taalwiezer.
    #
    # Vier regels die deze tabel raakten:
    #
    # 1. "ao" is een zelfstandig teken; "oa" bestaat niet. Er stond
    #    goan, moar, noar, oaver, doar, kloar - dat wordt gaon, maor,
    #    naor, aover, daor, klaor.
    # 2. De e ZONDER KLEMTOON schrijf je altijd als e. Daarmee wordt
    #    -lijk dus -lek (meugelek) en -ig wordt -eg (neudeg). Juist dat
    #    onderscheid maakt het Achterhoeks zichtbaar naast het Liemers,
    #    dat -ig houdt.
    # 3. De tweeklank i-j krijgt een streepje; een apostrof is voor
    #    samengetrokken woorden (he'j, da'k). Er stond bi'j.
    # 4. Bij een scheidbaar werkwoord komt in het voltooid deelwoord een
    #    streepje tussen de delen: an-egeven, weg-enommen. Dus
    #    op-ewekt en uut-esteld.
    #
    # v1.33.0: nagelopen tegen het dialectwoordenboek van
    # mijnwoordenboek.nl (1326 woorden, door bezoekers aangedragen).
    #
    # Ja - en het bracht meteen een fout aan het licht: "mangs" betekent
    # niet "mogelijk" maar SOMS, alvast of binnenkort. "Den accu haalt
    # de nacht mangs neet" zei dus iets anders dan bedoeld.
    #
    # De lange woorden staan boven de korte: de vervanging loopt van
    # boven naar beneden, en "niet" zou anders binnen "mogelijk niet"
    # toeslaan voordat die regel aan de beurt is.
    ("mogelijk niet", "meugelek neet"),
    ("waarschijnlijk", "waarschijnlek"),
    ("teruggeleverd", "trugge-elevert"),
    ("teruglevering", "truggelevering"),
    ("waterontharder", "waterontharder"),
    ("gedetecteerd", "opgemarkt"),
    ("beschikbaar", "beschikbaor"),
    ("kilowattuur", "kilowattuur"),
    ("goedkoopste", "goedkoopste"),
    ("bijgeladen", "bi-j-elaojen"),
    ("geblokkeerd", "geblokkeerd"),
    ("kwartier(en)", "kwartier(e)"),
    ("verwachting", "verwachting"),
    ("uitgesteld", "uut-esteld"),
    ("vaatwasser", "vaatwasser"),
    ("wasmachine", "wasmachine"),
    ("nachtelijk", "nachtelek"),
    ("gemiddeld", "gemiddeld"),
    ("goedkope", "goedkope"),
    ("gestegen", "umhoog-egaon"),
    ("mogelijk", "meugelek"),
    ("verbruik", "verbruuk"),
    ("opgewekt", "op-ewekt"),
    ("verkopen", "verkopen"),
    ("goedkoop", "goedkoop"),
    ("verwacht", "verwacht"),
    ("terwijl", "terwiel"),
    ("vandaag", "vandage"),
    ("volgens", "volgens"),
    ("geladen", "elaojen"),
    ("weinig", "weineg"),
    ("hangen", "hangen"),
    ("worden", "wodden"),
    ("moeten", "motten"),
    ("daarna", "daornao"),
    ("schijnt", "schient"),
    # v1.40.0: "de woning" wordt "'t huus", niet "de huus" - huis is
    # onzijdig. Gezien in de melding van 11 augustus 15:31.
    ("de woning", "'t huus"),
    ("woning", "huus"),
    ("laatste", "leste"),
    ("straks", "strak"),
    ("zonder", "zunder"),
    ("werken", "warken"),
    ("meteen", "dreks"),
    ("minuut", "minuut"),
    ("moment", "moment"),
    ("eerste", "eerste"),
    ("hangt", "hunk"),
    ("staat", "steet"),
    ("wordt", "wödt"),
    ("bijna", "bi-jnao"),
    ("nodig", "neudeg"),
    ("klaar", "klaor"),
    ("zonne", "zunne"),
    ("marge", "marge"),
    # Zonder spatie, zodat "zon," en "zon." ook meegaan. Veilig omdat
    # "zonder" en "zonne" hierboven al zijn afgevangen.
    ("zon", "zunne"),
    ("water", "waoter"),
    ("verder", "wieter"),
    ("genoeg", "genög"),
    ("tijd", "tied"),
    ("werk", "wark"),
    ("niets", "niks"),
    ("iets", "wat"),
    ("niet", "neet"),
    ("veel", "veule"),
    ("even", "efkes"),
    ("gaat", "geet"),
    ("gaan", "gaon"),
    ("goed", "good"),
    ("koud", "kold"),
    ("warm", "heit"),
    ("vaak", "duk"),
    ("soms", "mangs"),
    ("nacht", "nacht"),
    ("accu", "accu"),
    ("moet", "mot"),
    ("kan ", "kan "),
    ("het ", "'t "),
    ("een ", "'n "),
    ("zijn", "bunt"),
    ("is er", "is d'r"),
    ("er is", "d'r is"),
    ("naar", "naor"),
    ("over", "aover"),
    ("voor", "veur"),
    ("maar", "maor"),
    ("daar", "daor"),
    ("meer", "meer"),
    ("dag", "dag"),
    ("nog", "nog"),
    ("uit", "uut"),
    ("nu ", "now "),
    ("ook", "ok"),
)
