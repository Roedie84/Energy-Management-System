"""Overzicht van optionele, niet-geconfigureerde sensoren (v0.63.105,
gevraagd: "kun je een melding ergens op een geschikt dashboard
plaatsen wanneer er 1 ontbreekt"). Puur informatief, stuurt niets aan.
"""


def test_all_missing_when_nothing_configured(make_coordinator, hass):
    coordinator = make_coordinator({})

    missing = coordinator.get_missing_optional_features()

    names = {item["naam"] for item in missing}
    assert "Achtertuin-temperatuursensor" in names
    assert "Weerentiteit (KNMI of OpenWeatherMap)" in names
    assert "Accu-totaalcapaciteit-sensor" in names


def test_configured_sensor_no_longer_listed(make_coordinator, hass):
    coordinator = make_coordinator(
        {"backyard_temperature_sensor_entity": "sensor.achtertuin"}
    )

    missing = coordinator.get_missing_optional_features()

    names = {item["naam"] for item in missing}
    assert "Achtertuin-temperatuursensor" not in names


def test_weather_entity_satisfied_by_either_knmi_or_owm(make_coordinator, hass):
    coordinator = make_coordinator({"knmi_weather_entity": "weather.knmi"})

    missing = coordinator.get_missing_optional_features()

    names = {item["naam"] for item in missing}
    assert "Weerentiteit (KNMI of OpenWeatherMap)" not in names


def test_weather_entity_still_missing_if_neither_configured(make_coordinator, hass):
    coordinator = make_coordinator({})

    missing = coordinator.get_missing_optional_features()

    names = {item["naam"] for item in missing}
    assert "Weerentiteit (KNMI of OpenWeatherMap)" in names


def test_each_entry_has_a_description(make_coordinator, hass):
    coordinator = make_coordinator({})

    missing = coordinator.get_missing_optional_features()

    assert len(missing) > 0
    for item in missing:
        assert item["naam"]
        assert item["ontgrendelt"]


def test_empty_when_everything_configured(make_coordinator, hass):
    coordinator = make_coordinator(
        {
            "backyard_temperature_sensor_entity": "sensor.achtertuin",
            "solar_remaining_today_sensor_entity": "sensor.resterend",
            "co2_intensity_sensor_entity": "sensor.co2",
            "battery_total_capacity_sensor_entity": "sensor.capaciteit",
            "living_room_temperature_sensor_entity": "sensor.woonkamer",
            "water_active_usage_sensor_entity": "sensor.water",
            "appliance_notify_service": "notify.mobile_app",
            "dishwasher_power_sensor_entity": "sensor.vaatwasser",
            "washing_machine_power_sensor_entity": "sensor.wasmachine",
            "knmi_weather_entity": "weather.knmi",
        }
    )

    missing = coordinator.get_missing_optional_features()

    assert missing == []
