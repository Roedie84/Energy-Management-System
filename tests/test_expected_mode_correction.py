"""last_expected_mode correction (v0.63.20): it's set early from the
price check alone (is_expensive -> 'manual'), before headroom/SoC/
price-priority checks can downgrade that guess back to smart - without
correcting it afterwards, the dashboard's 'Verwachte modus' could
disagree with what was actually decided and shown as 'Werkelijke modus'.

Reported: a genuine expensive quarter with exhausted headroom correctly
fell back to smart (expensive_quarter_soc_protected), matching the
actual Zendure mode - but 'Verwachte modus (logica)' still showed
'manual', the pre-check guess.
"""
import asyncio
from datetime import datetime, timezone

from conftest import make_price_forecast

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def with_now(coordinator, when: datetime) -> None:
    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: when


def test_expected_mode_corrected_to_smart_when_reserve_exhausted(
    make_coordinator, hass, monkeypatch
):
    def price_fn(hour, minute):
        return 3_780_000 if hour == 20 else 2_000_000

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "250")
    hass.states.set("sensor.available_energy", "3.0")

    coordinator = make_coordinator(
        {
            "price_sensor_entity": "sensor.price",
            "price_attribute": "price_tax_included",
            "operation_select_entity": "select.op",
            "manual_power_number_entity": "number.pow",
            "manual_discharge_power": 1600,
            "available_energy_sensor_entity": "sensor.available_energy",
            "consumption_power_sensor_entity": "sensor.p1",
        }
    )
    monkeypatch.setattr(
        coordinator, "_get_dynamic_discharge_reserve_kwh", lambda now, cbs: 3.0
    )

    with_now(coordinator, DAY0.replace(hour=20, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason == "expensive_quarter_soc_protected"
    # Without the fix, this stayed "manual" (the pre-check guess based
    # purely on is_expensive), disagreeing with the actual decision.
    assert coordinator.last_expected_mode == "smart"


def test_expected_mode_matches_manual_for_a_genuine_discharge(make_coordinator, hass):
    def price_fn(hour, minute):
        return 3_780_000 if hour == 20 else 2_000_000

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "250")

    coordinator = make_coordinator(
        {
            "price_sensor_entity": "sensor.price",
            "price_attribute": "price_tax_included",
            "operation_select_entity": "select.op",
            "manual_power_number_entity": "number.pow",
            "manual_discharge_power": 1600,
        }
    )

    with_now(coordinator, DAY0.replace(hour=20, minute=0))
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_reason == "expensive_quarter"
    assert coordinator.last_expected_mode == "manual"
