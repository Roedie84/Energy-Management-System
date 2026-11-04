"""v5.176.4 - een weerentiteit die nog niet geladen is, is geen fout.

04-11 06:39: `weather.get_forecasts` faalde bij het opstarten met "did not
match any entities"; dat gaf een traceback en 30 minuten geen verwachting.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from custom_components.energy_management_system.const import (
    CLIMATE_FORECAST_FETCH_INTERVAL_MINUTES,
    CLIMATE_FORECAST_RETRY_NIET_GELADEN_MINUTES,
    CONF_KNMI_WEATHER_ENTITY,
)

NU = datetime(2026, 11, 4, 6, 40, tzinfo=timezone.utc)
WEER = "weather.forecast_thuis"


def _opstellen(make_coordinator, hass, staat=None):
    coordinator = make_coordinator({CONF_KNMI_WEATHER_ENTITY: WEER})
    oproepen = []

    async def geen_entiteit(*a, **k):
        oproepen.append(a)
        raise RuntimeError("did not match any entities")

    hass.services.async_call = geen_entiteit
    hass.states.get = lambda entity_id: staat
    return coordinator, oproepen


def test_niet_geladen_geeft_geen_foutmelding(make_coordinator, hass, caplog):
    coordinator, _ = _opstellen(make_coordinator, hass)

    with caplog.at_level(logging.ERROR):
        asyncio.run(coordinator._async_maybe_refresh_outdoor_forecast(NU))

    assert not caplog.records
    assert "Kon geen uurlijkse" in coordinator.climate_forecast_note


def test_unavailable_telt_als_niet_geladen(make_coordinator, hass, caplog):
    coordinator, _ = _opstellen(
        make_coordinator, hass, SimpleNamespace(state="unavailable")
    )

    with caplog.at_level(logging.ERROR):
        asyncio.run(coordinator._async_maybe_refresh_outdoor_forecast(NU))

    assert not caplog.records


def test_niet_geladen_probeert_snel_opnieuw(make_coordinator, hass):
    coordinator, oproepen = _opstellen(make_coordinator, hass)
    wacht = timedelta(minutes=CLIMATE_FORECAST_RETRY_NIET_GELADEN_MINUTES)

    asyncio.run(coordinator._async_maybe_refresh_outdoor_forecast(NU))
    asyncio.run(
        coordinator._async_maybe_refresh_outdoor_forecast(
            NU + wacht - timedelta(seconds=1)
        )
    )
    assert len(oproepen) == 1

    asyncio.run(coordinator._async_maybe_refresh_outdoor_forecast(NU + wacht))
    assert len(oproepen) == 2


def test_echte_fout_blijft_fout_met_vaste_wachttijd(make_coordinator, hass, caplog):
    coordinator, oproepen = _opstellen(
        make_coordinator, hass, SimpleNamespace(state="sunny")
    )

    with caplog.at_level(logging.ERROR):
        asyncio.run(coordinator._async_maybe_refresh_outdoor_forecast(NU))
    assert any("Kon geen uurlijkse" in r.getMessage() for r in caplog.records)

    bijna = timedelta(minutes=CLIMATE_FORECAST_FETCH_INTERVAL_MINUTES - 1)
    asyncio.run(coordinator._async_maybe_refresh_outdoor_forecast(NU + bijna))
    assert len(oproepen) == 1
