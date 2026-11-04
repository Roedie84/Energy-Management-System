"""v5.177.0 (A13) - geen ERROR bij het opstarten; battery_protection weg."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import sensor as S
from custom_components.energy_management_system.const import (
    CLIMATE_FORECAST_FETCH_INTERVAL_MINUTES,
    WEER_OPNIEUW_MINUTEN,
)


def test_weerentiteit_nog_niet_klaar_is_een_waarschuwing(make_coordinator, hass, caplog):
    c = make_coordinator({})

    class Diensten:
        async def async_call(self, *a, **k):
            raise RuntimeError("Service call requested response data but did not match any entities")

    c.hass = type("H", (), {"services": Diensten(), "states": hass.states})()
    with caplog.at_level(logging.WARNING):
        assert asyncio.run(c._async_fetch_hourly_outdoor_forecast("weather.knmi")) is None
        asyncio.run(c._async_fetch_hourly_outdoor_forecast("weather.knmi"))
    assert c._weer_opnieuw_proberen
    fouten = [r for r in caplog.records if r.levelno >= logging.ERROR]
    waarschuwingen = [r for r in caplog.records if r.levelno == logging.WARNING and "weer.knmi" not in r.getMessage()]
    assert not fouten
    assert len([r for r in waarschuwingen if "nog niet beschikbaar" in r.getMessage()]) == 1


def test_opnieuw_proberen_binnen_enkele_minuten():
    assert WEER_OPNIEUW_MINUTEN < CLIMATE_FORECAST_FETCH_INTERVAL_MINUTES


def test_battery_protection_bestaat_niet_meer():
    assert not hasattr(S, "BatteryProtectionSensor")
    assert hasattr(S, "_ruim_accubescherming_op")
