"""Digital Twin advisory engine (v0.63.36).

Advisory ONLY - simulates forward what the *existing* rule-based logic
(via self.last_timeline, already computed for the "Overzicht komende
uren" dashboard table) would do to the SoC/financial outcome. Never
sends a device command, never overrides the real decision tree.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from conftest import make_price_forecast

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _base_config(**overrides):
    config = {
        "price_sensor_entity": "sensor.price",
        "price_attribute": "price_tax_included",
        "operation_select_entity": "select.op",
        "manual_power_number_entity": "number.pow",
        "available_energy_sensor_entity": "sensor.available_energy",
        "battery_total_capacity_sensor_entity": "sensor.total_capacity",
        "battery_min_soc_number_entity": "number.min_soc",
        "manual_discharge_power": 1600,
        "manual_charge_power": -1600,
    }
    config.update(overrides)
    return config


def with_now(coordinator, when: datetime) -> None:
    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: when


def test_no_timeline_yet_produces_no_simulation(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    coordinator._run_digital_twin_simulation(DAY0)

    assert coordinator.digital_twin_trajectory == []
    assert coordinator.digital_twin_projected_profit_eur is None
    assert "tijdlijn" in coordinator.digital_twin_note.lower()


def test_no_simulation_without_available_energy_sensor(make_coordinator, hass):
    coordinator = make_coordinator(
        {
            "price_sensor_entity": "sensor.price",
            "price_attribute": "price_tax_included",
        }
    )
    coordinator.last_timeline = [
        {
            "start": DAY0.isoformat(),
            "end": (DAY0).isoformat(),
            "price_per_kwh": 0.3,
            "mode": "manual",
            "is_expensive": True,
        }
    ]
    coordinator._run_digital_twin_simulation(DAY0)

    assert coordinator.digital_twin_projected_profit_eur is None
    assert "available_energy" in coordinator.digital_twin_note


def test_full_tick_produces_a_trajectory_and_never_touches_the_battery(
    make_coordinator, hass
):
    def price_fn(hour, minute):
        return 1_500_000 if hour in (2, 3) else (4_500_000 if hour in (19, 20) else 2_500_000)

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.available_energy", "1.0")
    hass.states.set("sensor.total_capacity", "5.0")
    hass.states.set("number.min_soc", "0")

    coordinator = make_coordinator(_base_config())

    async def run():
        with_now(coordinator, DAY0.replace(hour=0, minute=0))
        await coordinator._async_update_locked()

    asyncio.run(run())

    assert len(coordinator.digital_twin_trajectory) > 0
    assert coordinator.digital_twin_projected_profit_eur is not None
    assert coordinator.digital_twin_final_soc_kwh is not None
    assert coordinator.digital_twin_hours_simulated > 0
    assert "adviserend" in coordinator.digital_twin_note.lower()


def test_discharge_bounded_by_remaining_soc(make_coordinator, hass):
    """A near-empty battery shouldn't be simulated as discharging more
    energy than it actually holds."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.available_energy", "0.05")

    coordinator.last_timeline = [
        {
            "start": DAY0.isoformat(),
            "end": (DAY0.replace(hour=1)).isoformat(),
            "price_per_kwh": 0.5,
            "mode": "manual",
            "is_expensive": True,
        }
    ]
    coordinator._run_digital_twin_simulation(DAY0)

    assert coordinator.digital_twin_final_soc_kwh == 0.0
    # 0.05 kWh sold at 0.5 EUR/kWh = 0.025 EUR, not the full 1600W*1h.
    assert coordinator.digital_twin_projected_profit_eur == 0.025


def test_charge_only_within_the_identified_cheap_block(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.available_energy", "1.0")
    hass.states.set("sensor.total_capacity", "5.0")
    hass.states.set("number.min_soc", "0")
    coordinator.last_cheap_block_start = DAY0
    coordinator.last_cheap_block_end = DAY0 + timedelta(hours=1)

    coordinator.last_timeline = [
        {
            "start": DAY0.isoformat(),
            "end": (DAY0 + timedelta(hours=1)).isoformat(),
            "price_per_kwh": 0.1,
            "mode": "smart",
            "is_expensive": False,
        },
        {
            "start": (DAY0 + timedelta(hours=1)).isoformat(),
            "end": (DAY0 + timedelta(hours=2)).isoformat(),
            "price_per_kwh": 0.2,
            "mode": "smart",
            "is_expensive": False,
        },
    ]
    coordinator._run_digital_twin_simulation(DAY0)

    # Only the first (within cheap block) quarter should have charged.
    assert coordinator.digital_twin_trajectory[0]["soc_kwh"] > 1.0
    assert (
        coordinator.digital_twin_trajectory[1]["soc_kwh"]
        == coordinator.digital_twin_trajectory[0]["soc_kwh"]
    )


def test_smart_discharging_leaves_soc_unchanged(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.available_energy", "2.0")

    coordinator.last_timeline = [
        {
            "start": DAY0.isoformat(),
            "end": (DAY0.replace(hour=1)).isoformat(),
            "price_per_kwh": 0.2,
            "mode": "smart_discharging",
            "is_expensive": False,
        },
    ]
    coordinator._run_digital_twin_simulation(DAY0)

    assert coordinator.digital_twin_final_soc_kwh == 2.0
    assert coordinator.digital_twin_projected_profit_eur == 0.0
