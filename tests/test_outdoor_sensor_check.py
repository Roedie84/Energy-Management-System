"""Leest de buitensensor plausibel? (v1.96.0)

Gevonden bij de eindcontrole van 14 augustus: de verouderingsdrijvers
legden een buitentemperatuur van 41,7 °C vast, en in de koelgeschiedenis
staan 35,4 en 35,9. Voor Lochem is dat onwaarschijnlijk hoog.

De sensor is `hue_outdoor_motion_sensor_1_temperatuur` - een
bewegingsmelder die in de zon hangt. Zulke sensoren lezen bij direct
zonlicht makkelijk vijf tot tien graden te hoog. Dat is geen uitschieter
maar een aanhoudende afwijking, dus het bestaande piekfilter ziet er niets
van.
"""
from custom_components.energy_management_system.const import (
    CONF_KNMI_WEATHER_ENTITY,
    CONF_OPENWEATHERMAP_WEATHER_ENTITY,
)


def _coordinator(make_coordinator, hass, sensor, weer):
    c = make_coordinator(
        {
            CONF_KNMI_WEATHER_ENTITY: "weather.knmi",
            CONF_OPENWEATHERMAP_WEATHER_ENTITY: "weather.owm",
        }
    )
    c.climate_live_outdoor_temp_c = sensor
    for entity_id, waarde in (("weather.knmi", weer), ("weather.owm", weer)):
        hass.states.set(entity_id, "sunny", {"temperature": waarde})
    return c


def test_a_sensor_in_the_sun_is_flagged(make_coordinator, hass):
    """De gemeten situatie: 35,9 op de sensor tegen ongeveer 28 volgens
    de weerbronnen."""
    c = _coordinator(make_coordinator, hass, sensor=35.9, weer=28.0)

    toets = c.get_outdoor_sensor_check()

    assert toets["verdacht"] is True
    assert toets["verschil_c"] == 7.9
    assert "zonlicht" in toets["reden"]


def test_it_names_the_effect_on_cooling(make_coordinator, hass):
    """Dit raakt de aansturing: de koeling vergelijkt de accu met buiten,
    en een te hoge buitenwaarde maakt dat verschil kunstmatig klein."""
    c = _coordinator(make_coordinator, hass, sensor=35.9, weer=28.0)

    assert "ventilator" in c.get_outdoor_sensor_check()["reden"]


def test_a_normal_difference_is_not_flagged(make_coordinator, hass):
    """Een tuin is vaak een graad of twee warmer dan het weerstation;
    dat is geen probleem."""
    c = _coordinator(make_coordinator, hass, sensor=29.5, weer=28.0)

    assert c.get_outdoor_sensor_check()["verdacht"] is False


def test_a_colder_sensor_is_not_flagged(make_coordinator, hass):
    """Een sensor in de schaduw leest lager - dat is juist goed."""
    c = _coordinator(make_coordinator, hass, sensor=26.0, weer=28.0)

    assert c.get_outdoor_sensor_check()["verdacht"] is False


def test_nothing_is_adjusted_automatically():
    """Er wordt niets bijgesteld. Welke waarde de ventilator werkelijk
    aanzuigt weten we niet - dat hangt van de opstelling af. Meten en
    melden, niet sturen."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("def get_outdoor_sensor_check")
    blok = bron[kop : bron.index("def _weather_outdoor_temperature_c")]

    assert "climate_live_outdoor_temp_c =" not in blok


def test_without_a_weather_source_it_says_so(make_coordinator, hass):
    """Niet te toetsen is iets anders dan goed."""
    c = make_coordinator({})
    c.climate_live_outdoor_temp_c = 35.9

    assert c.get_outdoor_sensor_check()["beschikbaar"] is False
