"""Weather ensemble cross-check (v0.63.30): live cloud_coverage from
KNMI/OpenWeatherMap weather entities, alongside a flag for when live PV
output disagrees with what those sources say the sky is doing.
Deliberately not a genuine kWh yield ensemble (needs panel specs this
integration doesn't collect) - a live cross-check, not a forecast blend.
"""
from datetime import datetime, timezone

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _base_config(**overrides):
    config = {
        "knmi_weather_entity": "weather.knmi",
        "openweathermap_weather_entity": "weather.openweathermap",
    }
    config.update(overrides)
    return config


def test_averages_cloud_cover_across_both_sources(make_coordinator, hass):
    hass.states.set("weather.knmi", "cloudy", {"cloud_coverage": 90})
    hass.states.set("weather.openweathermap", "cloudy", {"cloud_coverage": 80})

    coordinator = make_coordinator(_base_config())
    coordinator._update_weather_ensemble_check(DAY0)

    assert coordinator.weather_ensemble_cloud_cover_percent == 85.0
    assert coordinator.weather_ensemble_label == "bewolkt"
    assert set(coordinator.weather_ensemble_sources_used) == {
        "weather.knmi",
        "weather.openweathermap",
    }


def test_clear_label_below_threshold(make_coordinator, hass):
    hass.states.set("weather.knmi", "sunny", {"cloud_coverage": 10})
    hass.states.set("weather.openweathermap", "sunny", {"cloud_coverage": 15})

    coordinator = make_coordinator(_base_config())
    coordinator._update_weather_ensemble_check(DAY0)

    assert coordinator.weather_ensemble_label == "helder"


def test_partly_cloudy_label_in_the_middle(make_coordinator, hass):
    hass.states.set("weather.knmi", "partlycloudy", {"cloud_coverage": 50})

    coordinator = make_coordinator({"knmi_weather_entity": "weather.knmi"})
    coordinator._update_weather_ensemble_check(DAY0)

    assert coordinator.weather_ensemble_label == "half bewolkt"


def test_works_with_only_one_source_configured(make_coordinator, hass):
    hass.states.set("weather.knmi", "cloudy", {"cloud_coverage": 90})

    coordinator = make_coordinator({"knmi_weather_entity": "weather.knmi"})
    coordinator._update_weather_ensemble_check(DAY0)

    assert coordinator.weather_ensemble_cloud_cover_percent == 90.0
    assert coordinator.weather_ensemble_sources_used == ["weather.knmi"]


def test_no_sources_configured_does_nothing(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._update_weather_ensemble_check(DAY0)

    assert coordinator.weather_ensemble_cloud_cover_percent is None


def test_missing_cloud_coverage_attribute_is_skipped(make_coordinator, hass):
    hass.states.set("weather.knmi", "sunny", {})  # no cloud_coverage attr
    hass.states.set("weather.openweathermap", "sunny", {"cloud_coverage": 20})

    coordinator = make_coordinator(_base_config())
    coordinator._update_weather_ensemble_check(DAY0)

    assert coordinator.weather_ensemble_cloud_cover_percent == 20.0
    assert coordinator.weather_ensemble_sources_used == ["weather.openweathermap"]


def test_underperform_disagreement_flagged(make_coordinator, hass):
    """Live PV well below Solcast's forecast for right now, while both
    weather sources report clear skies - worth flagging."""
    hass.states.set("weather.knmi", "sunny", {"cloud_coverage": 5})
    hass.states.set("weather.openweathermap", "sunny", {"cloud_coverage": 10})
    hass.states.set("sensor.pv", "500")  # 0.5 kW live

    coordinator = make_coordinator(
        _base_config(
            pv_power_sensor_entity="sensor.pv",
            solar_today_forecast_sensor_entity="sensor.solcast",
        )
    )
    hass.states.set(
        "sensor.solcast",
        "0",
        {
            "detailedForecast": [
                {"period_start": DAY0, "pv_estimate": 2.0},  # 2 kW expected
            ]
        },
    )

    coordinator._update_weather_ensemble_check(DAY0)

    assert coordinator.weather_ensemble_disagreement is not None
    assert "onder" in coordinator.weather_ensemble_disagreement


def test_no_disagreement_when_cloudy_and_underperforming(make_coordinator, hass):
    """Underperformance while sources also report heavy cloud is
    consistent, not a disagreement - shouldn't be flagged."""
    hass.states.set("weather.knmi", "cloudy", {"cloud_coverage": 90})
    hass.states.set("sensor.pv", "500")

    coordinator = make_coordinator(
        {
            "knmi_weather_entity": "weather.knmi",
            "pv_power_sensor_entity": "sensor.pv",
            "solar_today_forecast_sensor_entity": "sensor.solcast",
        }
    )
    hass.states.set(
        "sensor.solcast",
        "0",
        {"detailedForecast": [{"period_start": DAY0, "pv_estimate": 2.0}]},
    )

    coordinator._update_weather_ensemble_check(DAY0)

    assert coordinator.weather_ensemble_disagreement is None


def test_no_disagreement_check_without_pv_sensor(make_coordinator, hass):
    hass.states.set("weather.knmi", "sunny", {"cloud_coverage": 5})

    coordinator = make_coordinator({"knmi_weather_entity": "weather.knmi"})
    coordinator._update_weather_ensemble_check(DAY0)

    assert coordinator.weather_ensemble_disagreement is None
