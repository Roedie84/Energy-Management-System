"""Klimaat-projectie meldde een verkeerde reden (v0.63.120).

Gerapporteerd met screenshot van een INGEVULD configuratieveld: "Maar ze
staan wel ingevuld?" - het Klimaat-tabblad toonde "Geen
living_room_temperature_sensor_entity geconfigureerd of niet
uitleesbaar", terwijl die sensor wel degelijk was geconfigureerd én een
actuele waarde gaf.

Root cause: `_recompute_climate_trajectory` liet de reden bij een
ontbrekende buitentemperatuur-voorspelling over aan wat de FETCH ooit in
`climate_forecast_note` had achtergelaten. Die fetch is gethrottled op
eens per 30 minuten, dus op alle tussenliggende ticks bleef daar de
melding van een VORIGE situatie staan. Concreet: als de
temperatuursensor eenmalig kort onbereikbaar was (heel normaal vlak na
een herstart, terwijl het apparaat nog verbinding maakt), werd de
sensor-melding gezet - en die bleef daarna eeuwig staan, ook toen de
sensor allang weer werkte en de werkelijke oorzaak iets heel anders was.

Bovendien gooide die ene tekst "niet geconfigureerd" en "niet
uitleesbaar" op één hoop, waardoor een tijdelijk probleem eruitzag als
een configuratiefout.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import (
    CONF_KNMI_WEATHER_ENTITY,
    CONF_LIVING_ROOM_TEMPERATURE_SENSOR,
)

NOW = datetime(2026, 8, 6, 11, 40, tzinfo=timezone.utc)
TEMP_ENTITY = "sensor.ultimatesensor_scd41_temperature"


def _config(**extra):
    basis = {CONF_LIVING_ROOM_TEMPERATURE_SENSOR: TEMP_ENTITY}
    basis.update(extra)
    return basis


def test_stale_sensor_note_is_replaced_once_the_sensor_works(
    make_coordinator, hass
):
    """DE gerapporteerde situatie, exact nagebootst.

    Tick 1: sensor nog niet bereikbaar (net na een herstart).
    Tick 2: sensor werkt, maar er is nog geen buitenvoorspelling.

    De melding van tick 1 mag in tick 2 niet blijven staan - die wijst
    de gebruiker naar een configuratieveld dat allang goed is ingevuld.
    """
    coordinator = make_coordinator(_config())

    # Tick 1 - sensor onbereikbaar.
    coordinator.living_room_current_temp_c = None
    coordinator._recompute_climate_trajectory(NOW)
    assert "niet uitleesbaar" in coordinator.climate_forecast_note

    # Tick 2 - sensor werkt weer, maar geen voorspelling beschikbaar.
    coordinator.living_room_current_temp_c = 23.5
    coordinator._recompute_climate_trajectory(NOW + timedelta(minutes=5))

    melding = coordinator.climate_forecast_note
    assert "living_room_temperature_sensor_entity" not in melding
    assert "niet uitleesbaar" not in melding


def test_missing_weather_entity_is_named_as_the_real_reason(
    make_coordinator, hass
):
    """Als de buitenvoorspelling de blokkade is, moet DAT er staan."""
    coordinator = make_coordinator(_config())
    coordinator.living_room_current_temp_c = 23.5
    coordinator._climate_forecast_fetch_note = (
        "Geen knmi_weather_entity/openweathermap_weather_entity "
        "geconfigureerd - geen buitentemperatuur-voorspelling "
        "beschikbaar om de projectie op te baseren."
    )

    coordinator._recompute_climate_trajectory(NOW)

    assert "weather_entity" in coordinator.climate_forecast_note


def test_unconfigured_sensor_gets_its_own_message(make_coordinator, hass):
    """Niet geconfigureerd is iets anders dan niet uitleesbaar."""
    coordinator = make_coordinator({})
    coordinator.living_room_current_temp_c = None

    coordinator._recompute_climate_trajectory(NOW)

    melding = coordinator.climate_forecast_note
    assert "geconfigureerd" in melding
    assert "niet uitleesbaar" not in melding


def test_configured_but_unreadable_names_the_entity(make_coordinator, hass):
    """De entity_id hoort erbij te staan - anders is niet te zien WELKE
    sensor bedoeld wordt."""
    coordinator = make_coordinator(_config())
    coordinator.living_room_current_temp_c = None

    coordinator._recompute_climate_trajectory(NOW)

    melding = coordinator.climate_forecast_note
    assert TEMP_ENTITY in melding
    assert "niet uitleesbaar" in melding
    assert "Geen woonkamertemperatuur-sensor geconfigureerd" not in melding


def test_configured_but_unreadable_does_not_suggest_a_config_error(
    make_coordinator, hass
):
    """De oude tekst stuurde naar het configuratiescherm terwijl daar
    niets mis was - dat kostte een hele zoekronde."""
    coordinator = make_coordinator(_config())
    coordinator.living_room_current_temp_c = None

    coordinator._recompute_climate_trajectory(NOW)

    assert "Configureren" not in coordinator.climate_forecast_note


def test_no_fetch_note_yet_falls_back_to_a_neutral_message(
    make_coordinator, hass
):
    """Vlak na de allereerste start is er nog niets opgehaald - dan mag
    er geen misleidende sensor-melding verschijnen."""
    coordinator = make_coordinator(_config())
    coordinator.living_room_current_temp_c = 23.5
    coordinator._climate_forecast_fetch_note = None

    coordinator._recompute_climate_trajectory(NOW)

    melding = coordinator.climate_forecast_note
    assert "buitentemperatuur-voorspelling" in melding
    assert "living_room_temperature_sensor_entity" not in melding


def test_successful_fetch_clears_the_fetch_note(make_coordinator, hass):
    """Anders zou een opgeloste storing als reden blijven hangen."""
    coordinator = make_coordinator(_config(**{CONF_KNMI_WEATHER_ENTITY: "weather.knmi"}))
    coordinator._climate_forecast_fetch_note = "oude storing"

    async def fake_fetch(entity_id):
        return [(NOW + timedelta(hours=1), 18.0)]

    coordinator._async_fetch_hourly_outdoor_forecast = fake_fetch

    import asyncio

    asyncio.run(coordinator._async_maybe_refresh_outdoor_forecast(NOW))

    assert coordinator._climate_forecast_fetch_note is None


def test_projection_recovers_completely_once_everything_is_available(
    make_coordinator, hass
):
    """End-to-end: na de storing moet de projectie er gewoon staan, met
    de normale toelichting in plaats van een foutmelding."""
    coordinator = make_coordinator(_config())
    coordinator.living_room_current_temp_c = None
    coordinator._recompute_climate_trajectory(NOW)
    assert coordinator.climate_forecast_trajectory == []

    coordinator.living_room_current_temp_c = 23.5
    coordinator._climate_cached_forecast = [
        (NOW + timedelta(hours=uur), 18.0) for uur in range(1, 5)
    ]
    coordinator._recompute_climate_trajectory(NOW + timedelta(minutes=5))

    assert len(coordinator.climate_forecast_trajectory) == 4
    assert "Adviserend" in coordinator.climate_forecast_note
