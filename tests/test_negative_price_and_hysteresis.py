"""Negative price handling (v0.26.0) and energy-bridge-check hysteresis
(v0.35.0, fixes real flickering seen in the field: available_kwh
hovering between 0.00 and -0.09 kWh caused rapid mode switching every
few minutes).
"""
import asyncio
from datetime import datetime, timedelta, timezone

from conftest import make_price_forecast

DAY0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


def test_negative_price_triggers_charge_and_solar_ramp_down(make_coordinator, hass):
    def price_fn(hour, minute):
        if hour == 13 and minute == 0:
            return -500_000  # negative price for one quarter
        return 2_500_000

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "200")
    hass.states.set("number.solar_limit", "100")

    coordinator = make_coordinator(
        {
            "price_sensor_entity": "sensor.price",
            "price_attribute": "price_tax_included",
            "operation_select_entity": "select.op",
            "manual_power_number_entity": "number.pow",
            "manual_discharge_power": 1600,
            "negative_price_charge_power": -2000,
            "solar_power_limit_entity": "number.solar_limit",
        }
    )

    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: DAY0.replace(hour=13, minute=0)

    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason == "negative_price"
    assert coordinator.last_charge_power_applied == -2000
    assert coordinator._is_negative_price_active is True


def test_negative_price_transition_back_to_normal(make_coordinator, hass):
    """Once price turns positive again, the negative-price flag clears
    and normal decision logic resumes."""

    def price_fn(hour, minute):
        if hour == 13 and minute == 0:
            return -500_000
        return 2_500_000

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "200")

    coordinator = make_coordinator(
        {
            "price_sensor_entity": "sensor.price",
            "price_attribute": "price_tax_included",
            "operation_select_entity": "select.op",
            "manual_power_number_entity": "number.pow",
            "manual_discharge_power": 1600,
            "negative_price_charge_power": -2000,
        }
    )

    from custom_components.energy_management_system import coordinator as coord_mod

    async def run():
        coord_mod.dt_util.now = lambda: DAY0.replace(hour=13, minute=0)
        await coordinator._async_update_locked()
        assert coordinator._is_negative_price_active is True

        coord_mod.dt_util.now = lambda: DAY0.replace(hour=13, minute=15)
        await coordinator._async_update_locked()
        assert coordinator._is_negative_price_active is False
        assert coordinator.last_reason != "negative_price"

    asyncio.run(run())


def test_hysteresis_prevents_flickering_near_the_threshold(make_coordinator, hass):
    """Reproduces the exact field incident: available_kwh flickering
    between 0.00 and -0.09 kWh (sensor noise around empty) should no
    longer cause the postpone-charging decision to flip every tick."""
    hass.states.set("sensor.p1", "50")

    coordinator = make_coordinator(
        {
            "consumption_power_sensor_entity": "sensor.p1",
            "available_energy_sensor_entity": "sensor.available",
        }
    )
    cheap_block_start = DAY0.replace(hour=9, minute=0)

    readings = [
        (DAY0.replace(hour=7, minute=0), 0.0),
        (DAY0.replace(hour=7, minute=1), -0.09),
        (DAY0.replace(hour=7, minute=15), 0.0),
        (DAY0.replace(hour=7, minute=45), -0.09),
        (DAY0.replace(hour=7, minute=54), 0.0),
        (DAY0.replace(hour=8, minute=0), -0.09),
        (DAY0.replace(hour=8, minute=1), 0.0),
        (DAY0.replace(hour=8, minute=9), -0.09),
        (DAY0.replace(hour=8, minute=15), 0.0),
    ]

    results = []
    for when, available in readings:
        hass.states.set("sensor.available", str(available))
        results.append(
            coordinator._should_postpone_charging([], when, cheap_block_start)
        )

    flips = sum(1 for a, b in zip(results, results[1:]) if a != b)
    assert flips == 0, f"expected a stable decision, got {flips} flip(s): {results}"
