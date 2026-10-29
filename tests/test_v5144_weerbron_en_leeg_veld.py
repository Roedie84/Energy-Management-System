"""v5.144.0 (akkoord Ruud 29-10-2026): twee punten uit de dagcontrole.

1. Een geweerde weerbron is informatief, geen aandachtspunt.
   Gemeten 29-10 10:14: het EMS weerde weather.openweathermap (48,5 %
   overeenstemming, forecast_thuis 89 %). Dat is bedoeld gedrag (v5.3),
   maar als aandachtspunt zette het de status op "Aandacht gewenst" en
   de cockpit op LET OP, en dat bleef zo zolang de bron in de
   configuratie stond.

2. Een optioneel entiteitveld kon nooit meer leeg.
   Gemeld 29-10: weather.openweathermap was niet uit de EMS-configuratie
   te halen. `_optioneel` gaf een opgeslagen waarde mee als `default`,
   dus voluptuous vulde een leeggemaakt veld weer in. En een weggelaten
   veld viel terug op `entry.data` van de eerste installatie.
"""
import voluptuous as vol


# --- 1. geweerde weerbron ---------------------------------------------


def test_geweerde_weerbron_is_geen_aandachtspunt(make_coordinator, hass):
    c = make_coordinator({})
    c.weerbron_keuze = {
        "gebruikt": ["weather.forecast_thuis"],
        "geweerd": ["weather.openweathermap"],
        "reden": "test",
    }

    punten = c._aandachtspunten_over_de_integratie()

    assert not any("weather.openweathermap" in p for p in punten)


def test_geweerde_weerbron_staat_wel_bij_de_informatieve_punten(
    make_coordinator, hass
):
    """Niet stil: wie kijkt, ziet nog steeds welke bron niet meeweegt en
    wat eraan te doen is."""
    c = make_coordinator({})
    c.weerbron_keuze = {
        "gebruikt": ["weather.forecast_thuis"],
        "geweerd": ["weather.openweathermap"],
        "reden": "test",
    }

    regel = c._weerbron_melding()

    assert regel and "weather.openweathermap" in regel
    assert "configuratie" in regel


def test_zonder_geweerde_bron_geen_extra_regel(make_coordinator, hass):
    c = make_coordinator({})
    c.weerbron_keuze = {"gebruikt": ["weather.forecast_thuis"], "geweerd": []}

    assert c._weerbron_geweerd_melding() is None


# --- 2. optioneel veld leegmaken ----------------------------------------


def test_opgeslagen_waarde_is_een_voorstel_geen_default():
    from custom_components.energy_management_system.config_flow import _optioneel

    veld = _optioneel(
        "openweathermap_weather_entity",
        {"openweathermap_weather_entity": "weather.openweathermap"},
    )

    assert veld.description["suggested_value"] == "weather.openweathermap"
    # Geen default: een leeg ingezonden formulier blijft leeg.
    schema = vol.Schema({veld: str})
    assert "openweathermap_weather_entity" not in schema({})


def test_standaardentiteit_zonder_opgeslagen_waarde_blijft_default():
    """De standaardentiteiten van v3.54.0 moeten zonder invullen meekomen."""
    from custom_components.energy_management_system.config_flow import _optioneel
    from custom_components.energy_management_system.const import (
        STANDAARD_ENTITEITEN,
    )

    sleutel, waarde = next(iter(STANDAARD_ENTITEITEN.items()))
    veld = _optioneel(sleutel, {})

    assert veld.default() == waarde


def test_leeggemaakt_entiteitveld_wordt_none():
    from homeassistant.helpers import selector

    from custom_components.energy_management_system.config_flow import (
        _leeggemaakte_entiteitvelden,
    )

    class _GeenEntiteit:
        def __call__(self, waarde):
            return waarde

    entiteit = selector.EntitySelector(selector.EntitySelectorConfig(domain="weather"))
    schema = vol.Schema(
        {
            vol.Optional("openweathermap_weather_entity"): entiteit,
            vol.Optional("knmi_weather_entity"): entiteit,
            vol.Optional("nooit_ingevuld"): entiteit,
            vol.Optional("een_getal"): _GeenEntiteit(),
        }
    )
    opgeslagen = {
        "openweathermap_weather_entity": "weather.openweathermap",
        "knmi_weather_entity": "weather.forecast_thuis",
        "een_getal": 5,
    }
    invoer = {"knmi_weather_entity": "weather.forecast_thuis"}

    uit = _leeggemaakte_entiteitvelden(schema, opgeslagen, invoer)

    assert uit == {"openweathermap_weather_entity": None}


def test_het_optiesformulier_slaat_de_lege_keuze_op():
    """De hele weg: opgeslagen in entry.data, leeggemaakt in het
    formulier, dan moet de opgeslagen optie None zijn - anders wint
    entry.data weer."""
    import asyncio

    from custom_components.energy_management_system.config_flow import (
        EnergyManagementSystemOptionsFlow,
    )

    class _Entry:
        data = {
            "price_sensor_entity": "sensor.prijs",
            "operation_select_entity": "select.modus",
            "manual_power_number_entity": "number.vermogen",
            "openweathermap_weather_entity": "weather.openweathermap",
        }
        options = {}

    flow = EnergyManagementSystemOptionsFlow()
    flow.config_entry = _Entry()
    opgeslagen = {}

    def _create_entry(title, data):
        opgeslagen.update(data)
        return {"type": "create_entry", "data": data}

    flow.async_create_entry = _create_entry
    invoer = {
        "price_sensor_entity": "sensor.prijs",
        "price_attribute": "price_tax_included",
        "operation_select_entity": "select.modus",
        "manual_power_number_entity": "number.vermogen",
    }

    asyncio.run(flow.async_step_init(dict(invoer)))

    assert "openweathermap_weather_entity" in opgeslagen
    assert opgeslagen["openweathermap_weather_entity"] is None
