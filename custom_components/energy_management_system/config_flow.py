"""Config flow for Energy Management System."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_EXPENSIVE_QUARTERS_COUNT,
    CONF_INVERT_BATTERY_POWER_SIGN,
    CONF_LOW_SOLAR_THRESHOLD_KWH,
    CONF_MANUAL_CHARGE_POWER,
    CONF_NEGATIVE_PRICE_CHARGE_POWER,
    CONF_SOLAR_POWER_LIMIT_ENTITY,
    CONF_BATTERY_ROUND_TRIP_EFFICIENCY,
    DEFAULT_BATTERY_ROUND_TRIP_EFFICIENCY_PERCENT,
    CONF_VACATION_CONSUMPTION_REDUCTION_PERCENT,
    DEFAULT_VACATION_CONSUMPTION_REDUCTION_PERCENT,
    CONF_MANUAL_DISCHARGE_POWER,
    CONF_MANUAL_POWER_NUMBER,
    CONF_MIN_SOC_PERCENT,
    CONF_OPERATION_SELECT,
    CONF_PRICE_ATTRIBUTE,
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
    DEFAULT_PRICE_ATTRIBUTE,
    DOMAIN,
    PRICE_ATTRIBUTE_OPTIONS,
)


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
            vol.Optional(
                CONF_SOLAR_POWER_LIMIT_ENTITY,
                default=defaults.get(CONF_SOLAR_POWER_LIMIT_ENTITY),
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="number")),
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
            vol.Optional(
                CONF_SOC_SENSOR,
                default=defaults.get(CONF_SOC_SENSOR),
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_MIN_SOC_PERCENT,
                default=defaults.get(CONF_MIN_SOC_PERCENT, DEFAULT_MIN_SOC_PERCENT),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=100, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_SOLAR_FORECAST_SENSOR,
                default=defaults.get(CONF_SOLAR_FORECAST_SENSOR),
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_SOLAR_TODAY_FORECAST_SENSOR,
                default=defaults.get(CONF_SOLAR_TODAY_FORECAST_SENSOR),
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_SOLAR_REMAINING_TODAY_SENSOR,
                default=defaults.get(CONF_SOLAR_REMAINING_TODAY_SENSOR),
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_SOLAR_EXTENDED_FORECAST_SENSORS,
                default=defaults.get(CONF_SOLAR_EXTENDED_FORECAST_SENSORS, []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", multiple=True)
            ),
            vol.Optional(
                CONF_SOLAR_ACTUAL_SENSOR,
                default=defaults.get(CONF_SOLAR_ACTUAL_SENSOR),
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_CONSUMPTION_POWER_SENSOR,
                default=defaults.get(CONF_CONSUMPTION_POWER_SENSOR),
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_BATTERY_POWER_SENSOR,
                default=defaults.get(CONF_BATTERY_POWER_SENSOR),
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_INVERT_BATTERY_POWER_SIGN,
                default=defaults.get(CONF_INVERT_BATTERY_POWER_SIGN, False),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_PV_POWER_SENSOR,
                default=defaults.get(CONF_PV_POWER_SENSOR),
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_AVAILABLE_ENERGY_SENSOR,
                default=defaults.get(CONF_AVAILABLE_ENERGY_SENSOR),
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
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
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=DEFAULT_NAME, data=user_input)

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
            return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_schema(current))
