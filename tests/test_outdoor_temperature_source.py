"""Welke bron levert de live buitentemperatuur? (v1.1.1)

Gerapporteerd met screenshot: "We hebben mijn buitentemperatuur sensor
toegevoegd maar die zie ik niet terug?"

De sensor werd wél degelijk gebruikt - `_get_live_outdoor_temp_c`
verkiest de achtertuinsensor sinds v0.63.95 boven de weerentiteit. Alleen
het dashboardlabel noemde nog hardgecodeerd "KNMI/OpenWeatherMap", uit de
tijd daarvóór. Het label beweerde dus iets anders dan de code deed.

Dezelfde soort fout als de verouderde legenda in v1.0.5 en de
vastgeroeste klimaatmelding in v0.63.120: de code veranderde, de tekst
ernaast niet. De oplossing is niet een nieuwe hardgecodeerde tekst, maar
de werkelijke bron laten tonen.
"""
from datetime import datetime, timezone

from custom_components.energy_management_system.const import (
    CONF_BACKYARD_TEMPERATURE_SENSOR,
    CONF_KNMI_WEATHER_ENTITY,
    CONF_OPENWEATHERMAP_WEATHER_ENTITY,
)

NOW = datetime(2026, 8, 6, 15, 0, tzinfo=timezone.utc)
ACHTERTUIN = "sensor.hue_outdoor_motion_sensor_1_temperatuur"
KNMI = "weather.forecast_thuis"
OWM = "weather.openweathermap"


def _config(**extra):
    basis = {
        CONF_BACKYARD_TEMPERATURE_SENSOR: ACHTERTUIN,
        CONF_KNMI_WEATHER_ENTITY: KNMI,
        CONF_OPENWEATHERMAP_WEATHER_ENTITY: OWM,
    }
    basis.update(extra)
    return basis


def _weer(hass, entity_id, temp):
    hass.states.set(entity_id, "sunny", {"temperature": temp})


def test_the_backyard_sensor_is_preferred(make_coordinator, hass):
    """De kern van de melding: de eigen sensor wordt gebruikt, en dat
    hoort ook zichtbaar te zijn."""
    c = make_coordinator(_config())
    hass.states.set(ACHTERTUIN, "24.9")
    _weer(hass, KNMI, 22.0)

    assert c._get_live_outdoor_temp_c(NOW) == 24.9
    assert c.climate_live_outdoor_source == ACHTERTUIN


def test_it_falls_back_to_the_weather_entity(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set(ACHTERTUIN, "unavailable")
    _weer(hass, KNMI, 22.0)

    assert c._get_live_outdoor_temp_c(NOW) == 22.0
    assert c.climate_live_outdoor_source == KNMI


def test_openweathermap_is_the_last_resort(make_coordinator, hass):
    c = make_coordinator(_config(**{CONF_KNMI_WEATHER_ENTITY: None}))
    hass.states.set(ACHTERTUIN, "unavailable")
    _weer(hass, OWM, 21.5)

    assert c._get_live_outdoor_temp_c(NOW) == 21.5
    assert c.climate_live_outdoor_source == OWM


def test_without_any_source_it_stays_empty(make_coordinator, hass):
    c = make_coordinator({})

    assert c._get_live_outdoor_temp_c(NOW) is None
    assert c.climate_live_outdoor_source is None


def test_the_source_is_reset_between_reads(make_coordinator, hass):
    """Valt de achtertuinsensor weg, dan mag de bron niet op die sensor
    blijven staan - dat zou opnieuw iets onwaars tonen."""
    c = make_coordinator(_config())
    hass.states.set(ACHTERTUIN, "24.9")
    c._get_live_outdoor_temp_c(NOW)
    assert c.climate_live_outdoor_source == ACHTERTUIN

    hass.states.set(ACHTERTUIN, "unavailable")
    _weer(hass, KNMI, 22.0)
    c._get_live_outdoor_temp_c(NOW)

    assert c.climate_live_outdoor_source == KNMI


def test_the_source_is_exposed_on_the_sensor(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        ClimateForecastSensor,
    )

    c = make_coordinator(_config())
    hass.states.set(ACHTERTUIN, "24.9")
    c._get_live_outdoor_temp_c(NOW)

    attrs = ClimateForecastSensor(c, "entry1").extra_state_attributes

    assert attrs["buitentemperatuur_bron"] == ACHTERTUIN



