"""Weerbronnen apart zichtbaar (v1.1.8).

Gerapporteerd: "Weather ensemble (bewolkingsgraad) 25,4% - het is nu zo
goed als volledig bewolkt."

De ensemble middelt twee weerbronnen. Dat gemiddelde alleen kan een groot
meningsverschil volledig verbergen: 0% en 51% geeft precies hetzelfde
cijfer als twee keer 25%, terwijl het eerste geval betekent dat er iets
mis is met een bron. De afzonderlijke waarden waren nergens zichtbaar -
ook niet in de diagnostiek - waardoor niet te achterhalen was WELKE bron
ernaast zat.
"""
from datetime import datetime, timezone

from custom_components.energy_management_system.const import (
    CONF_KNMI_WEATHER_ENTITY,
    CONF_OPENWEATHERMAP_WEATHER_ENTITY,
    WEATHER_ENSEMBLE_SPREAD_ATTENTION_PERCENT,
)

NOW = datetime(2026, 8, 7, 9, 0, tzinfo=timezone.utc)
BRON_A = "weather.forecast_thuis"
BRON_B = "weather.openweathermap"


def _config():
    return {
        CONF_KNMI_WEATHER_ENTITY: BRON_A,
        CONF_OPENWEATHERMAP_WEATHER_ENTITY: BRON_B,
    }


def _weer(hass, entity_id, bewolking):
    hass.states.set(entity_id, "cloudy", {"cloud_coverage": bewolking})


def test_each_source_is_recorded_separately(make_coordinator, hass):
    c = make_coordinator(_config())
    _weer(hass, BRON_A, 0)
    _weer(hass, BRON_B, 51)

    c._update_weather_ensemble_check(NOW)

    assert c.weather_ensemble_readings == {BRON_A: 0.0, BRON_B: 51.0}


def test_the_average_alone_hides_the_disagreement(make_coordinator, hass):
    """De kern: twee heel verschillende situaties geven hetzelfde
    gemiddelde. Alleen de spreiding onderscheidt ze."""
    eens = make_coordinator(_config())
    _weer(hass, BRON_A, 25)
    _weer(hass, BRON_B, 26)
    eens._update_weather_ensemble_check(NOW)

    oneens = make_coordinator(_config())
    _weer(hass, BRON_A, 0)
    _weer(hass, BRON_B, 51)
    oneens._update_weather_ensemble_check(NOW)

    assert eens.weather_ensemble_cloud_cover_percent == pytest_approx(25.5)
    assert oneens.weather_ensemble_cloud_cover_percent == pytest_approx(25.5)
    assert eens.weather_ensemble_spread_percent == 1.0
    assert oneens.weather_ensemble_spread_percent == 51.0


def pytest_approx(waarde):
    import pytest

    return pytest.approx(waarde)


def test_a_large_spread_is_reported(make_coordinator, hass):
    c = make_coordinator(_config())
    _weer(hass, BRON_A, 0)
    _weer(hass, BRON_B, 90)

    c._update_weather_ensemble_check(NOW)
    samenvatting = c.get_diagnostic_summary()

    melding = next(
        p for p in samenvatting["informatief"] if "Weerbronnen" in p
    )
    assert BRON_A in melding and BRON_B in melding


def test_it_is_informational_not_an_attention_point(make_coordinator, hass):
    """Het is geen storing van deze integratie - de systeemstatus hoort
    er niet door omlaag te gaan."""
    c = make_coordinator(_config())
    _weer(hass, BRON_A, 0)
    _weer(hass, BRON_B, 90)

    c._update_weather_ensemble_check(NOW)

    assert not any(
        "Weerbronnen" in p
        for p in c.get_diagnostic_summary()["aandachtspunten"]
    )


def test_agreeing_sources_are_not_flagged(make_coordinator, hass):
    c = make_coordinator(_config())
    _weer(hass, BRON_A, 88)
    _weer(hass, BRON_B, 92)

    c._update_weather_ensemble_check(NOW)

    assert c.weather_ensemble_spread_percent == 4.0
    assert not any(
        "Weerbronnen" in p for p in c.get_diagnostic_summary()["informatief"]
    )


def test_the_threshold_is_respected(make_coordinator, hass):
    c = make_coordinator(_config())
    _weer(hass, BRON_A, 0)
    _weer(hass, BRON_B, WEATHER_ENSEMBLE_SPREAD_ATTENTION_PERCENT - 1)

    c._update_weather_ensemble_check(NOW)

    assert not any(
        "Weerbronnen" in p for p in c.get_diagnostic_summary()["informatief"]
    )


def test_a_single_source_has_no_spread(make_coordinator, hass):
    """Met één bron valt er niets te vergelijken - dan hoort er geen
    getal te staan in plaats van een misleidende nul."""
    c = make_coordinator({CONF_KNMI_WEATHER_ENTITY: BRON_A})
    _weer(hass, BRON_A, 90)

    c._update_weather_ensemble_check(NOW)

    assert c.weather_ensemble_spread_percent is None
    assert c.weather_ensemble_readings == {BRON_A: 90.0}


def test_readings_are_cleared_when_no_source_reports(make_coordinator, hass):
    c = make_coordinator(_config())
    _weer(hass, BRON_A, 90)
    _weer(hass, BRON_B, 88)
    c._update_weather_ensemble_check(NOW)

    hass.states.set(BRON_A, "cloudy", {})
    hass.states.set(BRON_B, "cloudy", {})
    c._update_weather_ensemble_check(NOW)

    assert c.weather_ensemble_readings == {}
    assert c.weather_ensemble_spread_percent is None


def test_the_sensor_exposes_the_breakdown(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        WeatherEnsembleSensor,
    )

    c = make_coordinator(_config())
    _weer(hass, BRON_A, 0)
    _weer(hass, BRON_B, 51)
    c._update_weather_ensemble_check(NOW)

    attrs = WeatherEnsembleSensor(c, "entry1").extra_state_attributes

    assert attrs["metingen_per_bron"] == {BRON_A: 0.0, BRON_B: 51.0}
    assert attrs["spreiding_percent"] == 51.0
