"""Config flow for Energy Management System."""
from __future__ import annotations

from datetime import date

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_BATTERY_STATE_SENSOR,
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_EXPENSIVE_QUARTERS_COUNT,
    CONF_INVERT_BATTERY_POWER_SIGN,
    CONF_LOW_SOLAR_THRESHOLD_KWH,
    CONF_MANUAL_CHARGE_POWER,
    CONF_NEGATIVE_PRICE_CHARGE_POWER,
    CONF_SOLAR_POWER_LIMIT_ENTITY,
    CONF_KNMI_WEATHER_ENTITY,
    CONF_OPENWEATHERMAP_WEATHER_ENTITY,
    CONF_BACKYARD_TEMPERATURE_SENSOR,
    CONF_CO2_INTENSITY_SENSOR,
    CONF_BATTERY_ROUND_TRIP_EFFICIENCY,
    DEFAULT_BATTERY_ROUND_TRIP_EFFICIENCY_PERCENT,
    CONF_VACATION_CONSUMPTION_REDUCTION_PERCENT,
    DEFAULT_VACATION_CONSUMPTION_REDUCTION_PERCENT,
    CONF_DISHWASHER_POWER_SENSOR,
    CONF_DISHWASHER_READY_SENSOR,
    CONF_WASHING_MACHINE_POWER_SENSOR,
    CONF_WASHING_MACHINE_READY_SENSOR,
    CONF_QUOOKER_POWER_SENSOR,
    CONF_AIRCO_CLIMATE_ENTITY,
    CONF_SLAAPKAMER_CLIMATE_ENTITY,
    BATTERY_COOLING_OPPORTUNITY_MIN_C,
    CONF_BATTERY_COOLING_FAN_SWITCH,
    CONF_BATTERY_COOLING_OPPORTUNITY_C,
    CONF_PV_ACTUAL_AZIMUTH_DEGREES,
    CONF_POWER_LIMITS_INTENTIONAL,
    CONF_PRESENCE_BEDTIME_SENSOR,
    CONF_PRESENCE_MOTION_SENSORS,
    CONF_PRESENCE_LIGHT_ENTITIES,
    CONF_PRESENCE_TV_ENTITY,
    CONF_WATER_SOFTENER_END_HOUR,
    CONF_WATER_SOFTENER_START_HOUR,
    CONF_PV_ENERGY_SENSOR,
    CONF_PV_ACTUAL_TILT_DEGREES,
    CONF_DISHWASHER_START_IN,
    CONF_PRESENCE_ABSENCE_MINUTES,
    CONF_UPDATE_INTERVAL_SECONDS,
    UPDATE_INTERVAL_MAX_SECONDS,
    UPDATE_INTERVAL_MIN_SECONDS,
    UPDATE_INTERVAL_MINUTES,
    PRESENCE_ABSENCE_AFTER_MINUTES_FAST,
    CONF_SUN_AZIMUTH_SENSOR,
    CONF_WASHING_MACHINE_END_AT,
    CONF_SUN_ELEVATION_SENSOR,
    CONF_SUN_PHASE_SENSOR,
    CONF_BATTERY_MODULE_CELL_VOLTAGE_MAX_SENSORS,
    CONF_BATTERY_MODULE_CELL_VOLTAGE_MIN_SENSORS,
    CONF_BATTERY_MODULE_POWER_SENSORS,
    CONF_BATTERY_MODULE_SOC_SENSORS,
    CONF_BATTERY_MODULE_TEMPERATURE_SENSORS,
    CONF_BATTERY_COOLING_OUTDOOR_SENSOR,
    CONF_BATTERY_TEMPERATURE_SENSOR,
    CONF_LIVING_ROOM_TEMPERATURE_SENSOR,
    CONF_LIVING_ROOM_HUMIDITY_SENSOR,
    CONF_LIVING_ROOM_SHUTTER_ENTITY_1,
    CONF_LIVING_ROOM_SHUTTER_ENTITY_2,
    CONF_OVEN_STATE_SENSOR,
    CONF_KOOKPLAAT_STATE_SENSOR,
    CONF_STEELSTOFZUIGER_SWITCH,
    CONF_STEELSTOFZUIGER_POWER_SENSOR,
    CONF_FIETSLADERS_SWITCH,
    CONF_FIETSLADERS_POWER_SENSOR,
    CONF_APPLIANCE_NOTIFY_SERVICE,
    CONF_WATER_ACTIVE_USAGE_SENSOR,
    CONF_WATER_DAILY_TOTAL_SENSOR,
    CONF_WATER_TOTAL_USAGE_SENSOR,
    CONF_MANUAL_DISCHARGE_POWER,
    CONF_BATTERY_TOTAL_CAPACITY_SENSOR,
    CONF_BATTERY_MIN_SOC_NUMBER,
    STANDAARD_ENTITEITEN,
    CONF_BATTERY_MAX_SOC_NUMBER,
    CONF_BATTERY_MAX_CHARGE_POWER_ENTITY,
    CONF_BATTERY_MAX_DISCHARGE_POWER_ENTITY,
    CONF_MANUAL_POWER_NUMBER,
    CONF_MIN_SOC_PERCENT,
    CONF_OPERATION_SELECT,
    CONF_FEEDIN_COST_EUR_PER_KWH,
    CONF_FEEDIN_PRICE_ATTRIBUTE,
    CONF_PRICE_ATTRIBUTE,
    CONF_BATTERY_DISCHARGE_ENERGY_SENSOR,
    CONF_CONTRACT_START_DATE,
    CONF_COST_ENERGY_SENSOR,
    CONF_GRID_EXPORT_ENERGY_SENSOR,
    CONF_GRID_IMPORT_ENERGY_SENSOR,
    CONF_SALDEREN_END_DATE,
    CONF_PRICE_SENSOR,
    CONF_PV_POWER_SENSOR,
    CONF_SOC_SENSOR,
    CONF_SOLAR_ACTUAL_SENSOR,
    CONF_SOLAR_EXTENDED_FORECAST_SENSORS,
    CONF_SOLAR_FORECAST_SENSOR,
    CONF_SOLAR_REMAINING_TODAY_SENSOR,
    CONF_SOLAR_TODAY_FORECAST_SENSOR,
    DEFAULT_EXPENSIVE_QUARTERS_COUNT,
    DEFAULT_LOW_SOLAR_THRESHOLD_KWH,
    DEFAULT_MANUAL_CHARGE_POWER,
    DEFAULT_NEGATIVE_PRICE_CHARGE_POWER,
    DEFAULT_MANUAL_DISCHARGE_POWER,
    DEFAULT_MIN_SOC_PERCENT,
    DEFAULT_NAME,
    DEFAULT_FEEDIN_COST_EUR_PER_KWH,
    DEFAULT_FEEDIN_PRICE_ATTRIBUTE,
    DEFAULT_PRICE_ATTRIBUTE,
    DEFAULT_SALDEREN_END_DATE,
    DOMAIN,
    PRICE_ATTRIBUTE_OPTIONS,
)


def _optioneel(sleutel: str, defaults: dict):
    """Een optioneel veld, met of zonder bestaande waarde (v2.2.1).

    Gemeld met een screenshot van het configuratiescherm:

        Entity None is neither a valid entity ID nor a valid UUID

    `vol.Optional(sleutel, default=None)` geeft de EntitySelector een
    lege waarde mee, en die weigert dat - het veld is dan niet in te
    vullen. Zonder `default` laat voluptuous het veld gewoon weg als er
    niets is gekozen, en dat is wat een optioneel veld hoort te doen.

    Dit raakte elk leeg entiteitsveld, niet alleen de nieuwe; die twee
    vielen alleen op omdat ze nog nooit waren ingevuld.
    """
    waarde = defaults.get(sleutel)
    if waarde in (None, ""):
        # v3.54.0: voor de bekende Zendure-entiteiten een
        # standaardwaarde, zodat er niets ingevuld hoeft te worden.
        #
        # Gevraagd: "Alles wat nu goed en bekend is moet hard in de code
        # staan om verwarring te voorkomen." Als standaardwaarde in
        # plaats van hard ingebakken, want deze week braken drie dingen
        # doordat een naam of adres veranderde - en hard ingebakken
        # namen breken dan stil.
        waarde = STANDAARD_ENTITEITEN.get(sleutel)
    if waarde in (None, ""):
        return vol.Optional(sleutel)
    return vol.Optional(sleutel, default=waarde)


def _as_text(waarde) -> str:
    """Toont een opgeslagen getal als tekst in een TextSelector
    (v1.15.1).

    Home Assistant geeft de opgeslagen waarde terug als standaardwaarde
    van het veld. Staat daar een getal en is het veld een tekstveld, dan
    weigert het formulier met "expected str" - en dan is het HELE
    formulier geblokkeerd, ook alle andere instellingen erop.

    Hele getallen zonder decimaal, want "200" leest prettiger dan
    "200.0".
    """
    if waarde in (None, ""):
        return ""
    if isinstance(waarde, float) and waarde.is_integer():
        return str(int(waarde))
    return str(waarde)


def _validate_input(user_input: dict) -> dict[str, str]:
    """Controleert de vrije-tekstvelden (v1.1.5).

    Tot nu toe werd `errors` wel aangemaakt maar nooit gevuld: elk veld
    ging ongecontroleerd door. Voor de meeste velden geeft Home Assistant
    zelf al een keuzelijst of entiteitkiezer, maar de salderingsdatum is
    vrije tekst - en die stuurt sinds v1.1.0 óók de beslislogica.

    Een typefout daarin ("31-12-2026", "2026-13-01") viel stilzwijgend
    terug op "salderen actief". Verdedigbaar als noodgreep, maar niet als
    de gebruiker geen enkel signaal krijgt dat zijn invoer niet is
    aangekomen: het gedrag na saldering zou dan gewoon nooit aangaan.
    """
    errors: dict[str, str] = {}

    einddatum = user_input.get(CONF_SALDEREN_END_DATE)
    if einddatum:
        try:
            date.fromisoformat(str(einddatum))
        except (TypeError, ValueError):
            errors[CONF_SALDEREN_END_DATE] = "invalid_date"

    kosten = user_input.get(CONF_FEEDIN_COST_EUR_PER_KWH)
    if kosten not in (None, ""):
        try:
            if float(kosten) < 0:
                errors[CONF_FEEDIN_COST_EUR_PER_KWH] = "negative_cost"
        except (TypeError, ValueError):
            errors[CONF_FEEDIN_COST_EUR_PER_KWH] = "invalid_number"

    for veld, minimum, maximum in (
        (CONF_PV_ACTUAL_AZIMUTH_DEGREES, 0, 360),
        (CONF_PV_ACTUAL_TILT_DEGREES, 0, 90),
    ):
        rauw = user_input.get(veld)
        if rauw in (None, ""):
            # Leeg laten mag: dan is er simpelweg geen ijkpunt.
            user_input.pop(veld, None)
            continue
        try:
            waarde = float(str(rauw).replace(",", "."))
        except (TypeError, ValueError):
            errors[veld] = "invalid_number"
            continue
        if not minimum <= waarde <= maximum:
            errors[veld] = "out_of_range"
            continue
        # Meteen als getal opslaan, zodat de coordinator er niet later
        # alsnog een tekst uit krijgt.
        user_input[veld] = waarde

    return errors


def _schema(defaults: dict | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_PRICE_SENSOR,
                default=defaults.get(CONF_PRICE_SENSOR),
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_PRICE_ATTRIBUTE,
                default=defaults.get(CONF_PRICE_ATTRIBUTE, DEFAULT_PRICE_ATTRIBUTE),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=PRICE_ATTRIBUTE_OPTIONS,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            # v0.63.117 - einde saldering. Laatste dag dat salderen
            # nog geldt; vanaf de dag erna wordt teruglevering apart
            # (en veel lager) gewaardeerd in alle financiele getallen.
            _optioneel(CONF_GRID_IMPORT_ENERGY_SENSOR, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            _optioneel(CONF_GRID_EXPORT_ENERGY_SENSOR, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            _optioneel(CONF_BATTERY_DISCHARGE_ENERGY_SENSOR, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            _optioneel(CONF_COST_ENERGY_SENSOR, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(
                CONF_CONTRACT_START_DATE,
                default=_as_text(defaults.get(CONF_CONTRACT_START_DATE)),
            ): selector.TextSelector(),
            vol.Optional(
                CONF_SALDEREN_END_DATE,
                default=defaults.get(
                    CONF_SALDEREN_END_DATE, DEFAULT_SALDEREN_END_DATE
                ),
            ): selector.TextSelector(),
            vol.Optional(
                CONF_FEEDIN_PRICE_ATTRIBUTE,
                default=defaults.get(
                    CONF_FEEDIN_PRICE_ATTRIBUTE, DEFAULT_FEEDIN_PRICE_ATTRIBUTE
                ),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=PRICE_ATTRIBUTE_OPTIONS,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_FEEDIN_COST_EUR_PER_KWH,
                default=defaults.get(
                    CONF_FEEDIN_COST_EUR_PER_KWH, DEFAULT_FEEDIN_COST_EUR_PER_KWH
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=1, step=0.001, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_OPERATION_SELECT,
                default=defaults.get(CONF_OPERATION_SELECT),
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="select")),
            vol.Required(
                CONF_MANUAL_POWER_NUMBER,
                default=defaults.get(CONF_MANUAL_POWER_NUMBER),
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="number")),
            vol.Optional(
                CONF_MANUAL_DISCHARGE_POWER,
                default=defaults.get(
                    CONF_MANUAL_DISCHARGE_POWER, DEFAULT_MANUAL_DISCHARGE_POWER
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=10000, step=50, mode=selector.NumberSelectorMode.BOX
                )
            ),
            _optioneel(CONF_BATTERY_TOTAL_CAPACITY_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_BATTERY_MIN_SOC_NUMBER, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="number")),
            # v3.53.0: de overige instellingen van het apparaat, om
            # tegen te spiegelen. Optioneel - wie ze niet koppelt, mist
            # alleen de controle.
            _optioneel(CONF_BATTERY_MAX_SOC_NUMBER, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="number")),
            _optioneel(CONF_BATTERY_MAX_CHARGE_POWER_ENTITY, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain=["number", "sensor"])),
            _optioneel(CONF_BATTERY_MAX_DISCHARGE_POWER_ENTITY, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain=["number", "sensor"])),
            vol.Optional(
                CONF_MANUAL_CHARGE_POWER,
                default=defaults.get(
                    CONF_MANUAL_CHARGE_POWER, DEFAULT_MANUAL_CHARGE_POWER
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=-10000, max=0, step=50, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_NEGATIVE_PRICE_CHARGE_POWER,
                default=defaults.get(
                    CONF_NEGATIVE_PRICE_CHARGE_POWER,
                    DEFAULT_NEGATIVE_PRICE_CHARGE_POWER,
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=-10000, max=0, step=50, mode=selector.NumberSelectorMode.BOX
                )
            ),
            _optioneel(CONF_SOLAR_POWER_LIMIT_ENTITY, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="number")),
            _optioneel(CONF_KNMI_WEATHER_ENTITY, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="weather")),
            _optioneel(CONF_OPENWEATHERMAP_WEATHER_ENTITY, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="weather")),
            _optioneel(CONF_BACKYARD_TEMPERATURE_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_CO2_INTENSITY_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_BATTERY_ROUND_TRIP_EFFICIENCY,
                default=defaults.get(
                    CONF_BATTERY_ROUND_TRIP_EFFICIENCY,
                    DEFAULT_BATTERY_ROUND_TRIP_EFFICIENCY_PERCENT,
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=50, max=100, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_VACATION_CONSUMPTION_REDUCTION_PERCENT,
                default=defaults.get(
                    CONF_VACATION_CONSUMPTION_REDUCTION_PERCENT,
                    DEFAULT_VACATION_CONSUMPTION_REDUCTION_PERCENT,
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=100, step=5, mode=selector.NumberSelectorMode.BOX
                )
            ),
            _optioneel(CONF_DISHWASHER_POWER_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_DISHWASHER_READY_SENSOR, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
            _optioneel(CONF_WASHING_MACHINE_POWER_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_WASHING_MACHINE_READY_SENSOR, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
            _optioneel(CONF_QUOOKER_POWER_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_AIRCO_CLIMATE_ENTITY, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="climate")
            ),
            _optioneel(CONF_SLAAPKAMER_CLIMATE_ENTITY, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="climate")
            ),
            vol.Optional(
                CONF_BATTERY_MODULE_CELL_VOLTAGE_MAX_SENSORS,
                default=defaults.get(CONF_BATTERY_MODULE_CELL_VOLTAGE_MAX_SENSORS, []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", multiple=True)
            ),
            vol.Optional(
                CONF_BATTERY_MODULE_CELL_VOLTAGE_MIN_SENSORS,
                default=defaults.get(CONF_BATTERY_MODULE_CELL_VOLTAGE_MIN_SENSORS, []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", multiple=True)
            ),
            vol.Optional(
                CONF_BATTERY_MODULE_TEMPERATURE_SENSORS,
                default=defaults.get(CONF_BATTERY_MODULE_TEMPERATURE_SENSORS, []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", multiple=True)
            ),
            vol.Optional(
                CONF_BATTERY_MODULE_SOC_SENSORS,
                default=defaults.get(CONF_BATTERY_MODULE_SOC_SENSORS, []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", multiple=True)
            ),
            vol.Optional(
                CONF_BATTERY_MODULE_POWER_SENSORS,
                default=defaults.get(CONF_BATTERY_MODULE_POWER_SENSORS, []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", multiple=True)
            ),
            # v1.4.2: TEKSTvelden, geen NumberSelector. Deze twee mogen
            # leeg blijven, en dan is de standaardwaarde None - wat een
            # NumberSelector afwijst met "expected float", waardoor het
            # hele formulier niet meer te verzenden was. Bestaande
            # getalvelden in deze flow hebben allemaal een concrete
            # standaard en lopen daar dus niet tegenaan. De waarde wordt
            # in `_validate_input` gecontroleerd en omgezet.
            _optioneel(CONF_PV_ENERGY_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            # v1.15.1: de standaardwaarde als TEKST teruggeven. In
            # v1.4.2 zijn dit tekstvelden geworden omdat een leeg
            # NumberSelector "expected float" gaf. Maar `_validate_input`
            # slaat een ingevulde waarde op als GETAL (200.0), en bij het
            # heropenen van het formulier kreeg het tekstveld dat getal
            # terug - "expected str", precies het spiegelbeeld van de
            # oorspronkelijke fout.
            #
            # Opslaan als getal blijft juist: de coordinator rekent
            # ermee. Alleen de weergave moet tekst zijn.
            vol.Optional(
                CONF_PV_ACTUAL_AZIMUTH_DEGREES,
                default=_as_text(defaults.get(CONF_PV_ACTUAL_AZIMUTH_DEGREES)),
            ): selector.TextSelector(),
            vol.Optional(
                CONF_PV_ACTUAL_TILT_DEGREES,
                default=_as_text(defaults.get(CONF_PV_ACTUAL_TILT_DEGREES)),
            ): selector.TextSelector(),
            _optioneel(CONF_SUN_ELEVATION_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_SUN_AZIMUTH_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_UPDATE_INTERVAL_SECONDS,
                default=defaults.get(
                    CONF_UPDATE_INTERVAL_SECONDS, UPDATE_INTERVAL_MINUTES * 60
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=UPDATE_INTERVAL_MIN_SECONDS,
                    max=UPDATE_INTERVAL_MAX_SECONDS,
                    step=5,
                    unit_of_measurement="s",
                )
            ),
            vol.Optional(
                CONF_PRESENCE_ABSENCE_MINUTES,
                # Terugvalwaarde verplicht: een leeg NumberSelector geeft
                # "expected float" en blokkeert het hele formulier.
                default=defaults.get(
                    CONF_PRESENCE_ABSENCE_MINUTES,
                    PRESENCE_ABSENCE_AFTER_MINUTES_FAST,
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=5, max=180, step=5, unit_of_measurement="min"
                )
            ),
            _optioneel(CONF_DISHWASHER_START_IN, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["number", "sensor"])
            ),
            _optioneel(CONF_WASHING_MACHINE_END_AT, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["sensor", "number"])
            ),
            _optioneel(CONF_SUN_PHASE_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_BATTERY_TEMPERATURE_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_BATTERY_COOLING_OPPORTUNITY_C,
                default=defaults.get(
                    CONF_BATTERY_COOLING_OPPORTUNITY_C,
                    BATTERY_COOLING_OPPORTUNITY_MIN_C,
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=20, max=45, step=1, unit_of_measurement="°C"
                )
            ),
            _optioneel(CONF_BATTERY_COOLING_FAN_SWITCH, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="switch")),
            _optioneel(CONF_BATTERY_COOLING_OUTDOOR_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_LIVING_ROOM_TEMPERATURE_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_LIVING_ROOM_HUMIDITY_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_LIVING_ROOM_SHUTTER_ENTITY_1, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="cover")),
            _optioneel(CONF_LIVING_ROOM_SHUTTER_ENTITY_2, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="cover")),
            _optioneel(CONF_OVEN_STATE_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_KOOKPLAAT_STATE_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_STEELSTOFZUIGER_SWITCH, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="switch")),
            _optioneel(CONF_STEELSTOFZUIGER_POWER_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_FIETSLADERS_SWITCH, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="switch")),
            _optioneel(CONF_FIETSLADERS_POWER_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_WATER_ACTIVE_USAGE_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_WATER_DAILY_TOTAL_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_WATER_TOTAL_USAGE_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_APPLIANCE_NOTIFY_SERVICE,
                default=defaults.get(CONF_APPLIANCE_NOTIFY_SERVICE, ""),
            ): str,
            vol.Optional(
                CONF_EXPENSIVE_QUARTERS_COUNT,
                default=defaults.get(
                    CONF_EXPENSIVE_QUARTERS_COUNT, DEFAULT_EXPENSIVE_QUARTERS_COUNT
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=20, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            _optioneel(CONF_SOC_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_MIN_SOC_PERCENT,
                default=defaults.get(CONF_MIN_SOC_PERCENT, DEFAULT_MIN_SOC_PERCENT),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=100, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            _optioneel(CONF_SOLAR_FORECAST_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_SOLAR_TODAY_FORECAST_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_SOLAR_REMAINING_TODAY_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_SOLAR_EXTENDED_FORECAST_SENSORS,
                default=defaults.get(CONF_SOLAR_EXTENDED_FORECAST_SENSORS, []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", multiple=True)
            ),
            _optioneel(CONF_SOLAR_ACTUAL_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_CONSUMPTION_POWER_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_BATTERY_POWER_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            # v1.16.9: de werkstand van de accu ("Laden"/"Ontladen") is
            # betrouwbaarder dan het teken van de vermogenssensor, dat
            # afhangt van de omkering hieronder. Optioneel: zonder deze
            # sensor blijft de tekenmethode de terugval.
            # v1.18.2: welke bewegingssensoren BINNEN hangen. Bewust een
            # keuze en geen automatische herkenning - buitensensoren
            # (deurbel, tuin) slaan aan op voorbijgangers en zeggen niets
            # over of er iemand thuis is.
            # v1.19.6: wanneer draait de waterontharder? De bewoner
            # weet dat, de integratie niet. Hoe smaller het venster, hoe
            # kleiner de kans dat een nachtelijk bad als regeneratie
            # telt - een sessie van 114 liter in 17 minuten voldoet
            # namelijk aan alle volume- en duureisen.
            vol.Optional(
                CONF_WATER_SOFTENER_START_HOUR,
                default=defaults.get(CONF_WATER_SOFTENER_START_HOUR, 0),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=23, step=1, mode="box")
            ),
            vol.Optional(
                CONF_WATER_SOFTENER_END_HOUR,
                default=defaults.get(CONF_WATER_SOFTENER_END_HOUR, 6),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=24, step=1, mode="box")
            ),
            # v1.20.0: welke sensor markeert naar bed gaan - een
            # overloop, een trap, een slaapkamer. Is die de LAATSTE
            # beweging 's avonds, dan is de stilte erna geen
            # afwezigheid maar een nacht.
            # v1.20.1: tv aan telt als aanwezig. Daarmee kan de
            # afwezigheidsdrempel van 45 naar 10 minuten - die 45 stond
            # er juist om stilzitten op de bank niet als afwezigheid te
            # tellen, en dat vangt de tv nu op.
            # v1.21.2: staan de vermogensgrenzen bewust lager dan wat de
            # omvormer aankan? Dan geen suggesties om ze te verhogen -
            # de redenen (groep, cellen sparen, geluid, marge) kent de
            # integratie niet.
            vol.Optional(
                CONF_POWER_LIMITS_INTENTIONAL,
                default=defaults.get(CONF_POWER_LIMITS_INTENTIONAL, False),
            ): selector.BooleanSelector(),
            _optioneel(CONF_PRESENCE_TV_ENTITY, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["media_player", "remote", "binary_sensor", "switch"]
                )
            ),
            vol.Optional(
                CONF_PRESENCE_LIGHT_ENTITIES,
                default=defaults.get(CONF_PRESENCE_LIGHT_ENTITIES, []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["light", "switch"], multiple=True
                )
            ),
            _optioneel(CONF_PRESENCE_BEDTIME_SENSOR, defaults): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
            vol.Optional(
                CONF_PRESENCE_MOTION_SENSORS,
                default=defaults.get(CONF_PRESENCE_MOTION_SENSORS, []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor", multiple=True)
            ),
            _optioneel(CONF_BATTERY_STATE_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_INVERT_BATTERY_POWER_SIGN,
                default=defaults.get(CONF_INVERT_BATTERY_POWER_SIGN, False),
            ): selector.BooleanSelector(),
            _optioneel(CONF_PV_POWER_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            _optioneel(CONF_AVAILABLE_ENERGY_SENSOR, defaults): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_LOW_SOLAR_THRESHOLD_KWH,
                default=defaults.get(
                    CONF_LOW_SOLAR_THRESHOLD_KWH, DEFAULT_LOW_SOLAR_THRESHOLD_KWH
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=100, step=0.5, mode=selector.NumberSelectorMode.BOX
                )
            ),
        }
    )


class EnergyManagementSystemConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Energy Management System."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_input(user_input)
            if not errors:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=DEFAULT_NAME, data=user_input)
            # Bij een fout het formulier opnieuw tonen MET de ingevulde
            # waarden, zodat alleen het foute veld hoeft te worden
            # aangepast in plaats van alles opnieuw.
            return self.async_show_form(
                step_id="user", data_schema=_schema(user_input), errors=errors
            )

        return self.async_show_form(step_id="user", data_schema=_schema(), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> EnergyManagementSystemOptionsFlow:
        return EnergyManagementSystemOptionsFlow()


class EnergyManagementSystemOptionsFlow(config_entries.OptionsFlow):
    """Allow changing the linked entities and thresholds after initial setup."""

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            errors = _validate_input(user_input)
            if not errors:
                return self.async_create_entry(title="", data=user_input)
            return self.async_show_form(
                step_id="init", data_schema=_schema(user_input), errors=errors
            )

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_schema(current))
