"""The 'verwacht schema' (upcoming schedule) must reflect the live
arbitrage_solar_capture override (v0.63.60) for the current interval,
not just live_is_expensive/live_should_postpone_charging (v0.63.70).

Reported, with screenshots: the live decision correctly showed "smart"
(the solar-capture override kicking in instead of smart_discharging),
but the displayed schedule's current row still showed
"smart_discharging" - _build_forecast_timeline's "now" override never
knew about this newer override at all.
"""
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 8, 5, tzinfo=timezone.utc)


def _build_flat_entries():
    entries = []
    for hour in range(24):
        for minute in (0, 15, 30, 45):
            start = DAY0.replace(hour=hour, minute=minute)
            entries.append((start, start + timedelta(minutes=15), 0.13 * 1_000_000))
    return entries


def test_solar_capture_override_shows_smart_not_discharging(make_coordinator):
    coordinator = make_coordinator({})
    entries = _build_flat_entries()
    now = DAY0.replace(hour=15, minute=30)

    timeline = coordinator._build_forecast_timeline(
        entries,
        now,
        None,
        None,
        live_is_expensive=False,
        live_should_postpone_charging=True,
        live_should_capture_solar=True,
    )

    current = next(t for t in timeline if t["start"] == now.isoformat())
    assert current["mode"] == "smart"


def test_without_solar_capture_still_shows_discharging(make_coordinator):
    """Confirms the existing behaviour is untouched when the override
    isn't active."""
    coordinator = make_coordinator({})
    entries = _build_flat_entries()
    now = DAY0.replace(hour=15, minute=30)

    timeline = coordinator._build_forecast_timeline(
        entries,
        now,
        None,
        None,
        live_is_expensive=False,
        live_should_postpone_charging=True,
        live_should_capture_solar=False,
    )

    current = next(t for t in timeline if t["start"] == now.isoformat())
    assert current["mode"] == "smart_discharging"


def test_full_tick_wires_the_override_into_the_timeline(make_coordinator, hass):
    """End-to-end: a full update tick where should_postpone_charging is
    forced True (monkeypatched directly - found, while building this
    test, that this fixture's price/P1/PV combination doesn't reliably
    produce that condition on its own through the real reserve
    calculation) but live solar fully covers the target charge rate
    must show 'smart' for the current interval in last_timeline, not
    'smart_discharging'."""
    import asyncio

    from conftest import make_price_forecast

    def _price_fn(hour, minute):
        if hour < 16:
            return 1_300_000  # 0.13 EUR/kWh - "now", cheap
        return 3_900_000  # 0.39 EUR/kWh later today - clears the margin check

    forecast = make_price_forecast(DAY0, _price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "-2300")
    hass.states.set("sensor.pv", "2500")
    hass.states.set("sensor.available_energy", "8.0")

    coordinator = make_coordinator(
        {
            "price_sensor_entity": "sensor.price",
            "price_attribute": "price_tax_included",
            "operation_select_entity": "select.op",
            "manual_power_number_entity": "number.pow",
            "manual_discharge_power": 1600,
            "manual_charge_power": -2000,
            "available_energy_sensor_entity": "sensor.available_energy",
            "consumption_power_sensor_entity": "sensor.p1",
            "pv_power_sensor_entity": "sensor.pv",
        }
    )

    coordinator.learned_efficiency_history = [88.2] * 7

    def fake_should_postpone(entries, now, cheap_block_start):
        return True

    coordinator._should_postpone_charging = fake_should_postpone

    now = DAY0.replace(hour=15, minute=30)

    async def run():
        from custom_components.energy_management_system import (
            coordinator as coord_mod,
        )

        coord_mod.dt_util.now = lambda: now
        await coordinator._async_update_locked()

    asyncio.run(run())

    assert coordinator.last_reason == "arbitrage_solar_capture"
    now_iso = now.isoformat()
    current = next(t for t in coordinator.last_timeline if t["start"] == now_iso)
    assert current["mode"] == "smart"


def test_arbitrage_charging_override_shows_manual_not_smart(make_coordinator, hass):
    """v0.63.75, reported: 'verwacht schema' still showed 'smart' for
    the current interval while the actual live decision was 'manual'
    via arbitrage_charging (a genuine grid purchase, v0.63.73's
    'reserve insufficient, margin profitable' case) - neither
    is_expensive nor should_postpone_charging, so the override logic's
    else-branch silently defaulted to smart, missing this case."""
    coordinator = make_coordinator({})
    entries = _build_flat_entries()
    now = DAY0.replace(hour=15, minute=30)

    timeline = coordinator._build_forecast_timeline(
        entries,
        now,
        None,
        None,
        live_is_expensive=False,
        live_should_postpone_charging=False,
        live_should_capture_solar=False,
        live_is_arbitrage_charging=True,
    )

    current = next(t for t in timeline if t["start"] == now.isoformat())
    assert current["mode"] == "manual"


def test_full_tick_wires_arbitrage_charging_into_the_timeline(make_coordinator, hass):
    """End-to-end: a full update tick where should_postpone_charging is
    False (genuinely insufficient reserve) and the margin is profitable
    must show 'manual' for the current interval in last_timeline, not
    'smart'."""
    import asyncio

    from conftest import make_price_forecast

    def _price_fn(hour, minute):
        if hour < 16:
            return 1_300_000  # 0.13 EUR/kWh - "now", cheap
        return 3_900_000  # 0.39 EUR/kWh later today - clears the margin check

    forecast = make_price_forecast(DAY0, _price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "200")
    hass.states.set("sensor.available_energy", "8.0")

    coordinator = make_coordinator(
        {
            "price_sensor_entity": "sensor.price",
            "price_attribute": "price_tax_included",
            "operation_select_entity": "select.op",
            "manual_power_number_entity": "number.pow",
            "manual_discharge_power": 1600,
            "manual_charge_power": -2000,
            "available_energy_sensor_entity": "sensor.available_energy",
            "consumption_power_sensor_entity": "sensor.p1",
        }
    )
    coordinator.learned_efficiency_history = [88.2] * 7

    def fake_should_postpone(entries, now, cheap_block_start):
        return False

    coordinator._should_postpone_charging = fake_should_postpone

    now = DAY0.replace(hour=15, minute=30)

    async def run():
        from custom_components.energy_management_system import (
            coordinator as coord_mod,
        )

        coord_mod.dt_util.now = lambda: now
        await coordinator._async_update_locked()

    asyncio.run(run())

    assert coordinator.last_reason == "arbitrage_charging"
    now_iso = now.isoformat()
    current = next(t for t in coordinator.last_timeline if t["start"] == now_iso)
    assert current["mode"] == "manual"
