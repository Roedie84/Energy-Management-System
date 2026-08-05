"""Heavy-load awareness (v0.63.0): when a known heavy consumer
(vaatwasser, wasmachine, Quooker, airco) is confirmed active via its own
entity, the median smoothing's built-in caution for the live consumption
correction is skipped - the live reading is trusted immediately instead
of waiting several update ticks for the median to catch up.

Reported scenario: an airco that only runs heating some autumn evenings,
unpredictably - too irregular for the 7-day learned median (v0.62.0) to
ever treat as normal, but a real load worth reacting to immediately on
the nights it does run.
"""
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _base_config(**overrides):
    config = {
        "dishwasher_power_sensor_entity": "sensor.vaatwasser_vermogen",
        "washing_machine_power_sensor_entity": "sensor.wasmachine_vermogen",
        "quooker_power_sensor_entity": "sensor.quooker_vermogen",
        "airco_climate_entity": "climate.woonkamer_airco",
        "slaapkamer_climate_entity": "climate.slaapkamer",
        "oven_state_sensor_entity": "sensor.oven_operation_state",
        "kookplaat_state_sensor_entity": "sensor.kookplaat_operation_state",
    }
    config.update(overrides)
    return config


def test_dishwasher_running_is_confirmed(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.vaatwasser_vermogen", "1200")

    assert coordinator._get_confirmed_heavy_load_source(DAY0) == "vaatwasser"


def test_washing_machine_running_is_confirmed(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.wasmachine_vermogen", "600")

    assert coordinator._get_confirmed_heavy_load_source(DAY0) == "wasmachine"


def test_appliance_below_threshold_is_not_confirmed(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.vaatwasser_vermogen", "2")  # standby draw

    assert coordinator._get_confirmed_heavy_load_source(DAY0) is None


def test_airco_heating_is_confirmed(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set(
        "climate.woonkamer_airco", "heat", {"hvac_action": "heating"}
    )

    assert coordinator._get_confirmed_heavy_load_source(DAY0) == "airco"


def test_airco_idle_is_not_confirmed(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set(
        "climate.woonkamer_airco", "heat", {"hvac_action": "idle"}
    )

    assert coordinator._get_confirmed_heavy_load_source(DAY0) is None


def test_slaapkamer_heating_is_confirmed(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set(
        "climate.slaapkamer", "heat", {"hvac_action": "heating"}
    )

    assert coordinator._get_confirmed_heavy_load_source(DAY0) == "slaapkamer"


def test_slaapkamer_idle_is_not_confirmed(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set(
        "climate.slaapkamer", "heat", {"hvac_action": "idle"}
    )

    assert coordinator._get_confirmed_heavy_load_source(DAY0) is None


def test_airco_and_slaapkamer_are_independent(make_coordinator, hass):
    """Airco idle shouldn't mask a genuinely active slaapkamer unit."""
    coordinator = make_coordinator(_base_config())
    hass.states.set(
        "climate.woonkamer_airco", "heat", {"hvac_action": "idle"}
    )
    hass.states.set(
        "climate.slaapkamer", "heat", {"hvac_action": "cooling"}
    )

    assert coordinator._get_confirmed_heavy_load_source(DAY0) == "slaapkamer"


def test_quooker_brief_tap_is_not_confirmed(make_coordinator, hass):
    """A single brief tap (under QUOOKER_SUSTAINED_MINUTES) is exactly
    the kind of noise the median smoothing was built to ignore - must
    NOT bypass it."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.quooker_vermogen", "2000")

    coordinator._update_quooker_tracking(DAY0)
    assert coordinator._get_confirmed_heavy_load_source(DAY0) is None

    # Still within the sustained window (1 minute in) - not yet confirmed.
    later = DAY0 + timedelta(minutes=1)
    coordinator._update_quooker_tracking(later)
    assert coordinator._get_confirmed_heavy_load_source(later) is None


def test_quooker_sustained_use_is_confirmed(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.quooker_vermogen", "2000")

    coordinator._update_quooker_tracking(DAY0)
    later = DAY0 + timedelta(minutes=2, seconds=1)
    coordinator._update_quooker_tracking(later)

    assert coordinator._get_confirmed_heavy_load_source(later) == "quooker"


def test_quooker_tracking_resets_when_power_drops(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.quooker_vermogen", "2000")
    coordinator._update_quooker_tracking(DAY0)

    # Power drops back to standby before the sustained window elapses.
    hass.states.set("sensor.quooker_vermogen", "1")
    coordinator._update_quooker_tracking(DAY0 + timedelta(minutes=1))

    # Then comes back on - the "since" timer must have reset, not
    # continued from the original start time.
    hass.states.set("sensor.quooker_vermogen", "2000")
    restart = DAY0 + timedelta(minutes=1, seconds=30)
    coordinator._update_quooker_tracking(restart)
    just_after_restart = restart + timedelta(seconds=30)
    coordinator._update_quooker_tracking(just_after_restart)

    assert coordinator._get_confirmed_heavy_load_source(just_after_restart) is None


def test_no_appliance_active_returns_none(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.vaatwasser_vermogen", "0")
    hass.states.set("sensor.wasmachine_vermogen", "0")
    hass.states.set("climate.woonkamer_airco", "off", {"hvac_action": "off"})
    hass.states.set("sensor.oven_operation_state", "Inactive")
    hass.states.set("sensor.kookplaat_operation_state", "Inactive")

    assert coordinator._get_confirmed_heavy_load_source(DAY0) is None


def test_oven_running_is_confirmed(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.oven_operation_state", "Run")

    assert coordinator._get_confirmed_heavy_load_source(DAY0) == "oven"


def test_oven_state_matching_is_case_insensitive(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.oven_operation_state", "run")

    assert coordinator._get_confirmed_heavy_load_source(DAY0) == "oven"


def test_oven_ready_is_not_confirmed(make_coordinator, hass):
    """'Ready'/'DelayedStart' mean scheduled-but-idle, not drawing power."""
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.oven_operation_state", "Ready")

    assert coordinator._get_confirmed_heavy_load_source(DAY0) is None


def test_oven_finished_is_not_confirmed(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.oven_operation_state", "Finished")

    assert coordinator._get_confirmed_heavy_load_source(DAY0) is None


def test_kookplaat_running_is_confirmed(make_coordinator, hass):
    coordinator = make_coordinator(_base_config())
    hass.states.set("sensor.kookplaat_operation_state", "Run")

    assert coordinator._get_confirmed_heavy_load_source(DAY0) == "kookplaat"


def test_correction_ratio_bypasses_median_when_heavy_load_confirmed(make_coordinator):
    """Core behaviour: with a confirmed heavy load, the correction ratio
    uses the latest single reading, not the median of the last few -
    reacting immediately instead of needing ~15-20 min to convince the
    median."""
    coordinator = make_coordinator({})
    coordinator.hourly_consumption_profile[20] = [0.3]  # learned ~300W for hour 20
    # A brief low reading followed by one high reading just now - median
    # of these 4 would still be low, but the latest single reading is high.
    coordinator._recent_consumption_readings_kw = [0.3, 0.3, 0.3, 2.0]

    coordinator.last_heavy_load_source = None
    ratio_without_confirmation = coordinator._get_smoothed_consumption_correction_ratio(20)
    assert ratio_without_confirmation == 1.0  # median (0.3) doesn't exceed learned

    coordinator.last_heavy_load_source = "airco"
    ratio_with_confirmation = coordinator._get_smoothed_consumption_correction_ratio(20)
    assert ratio_with_confirmation > 1.0  # latest reading (2.0) does exceed learned


def test_correction_ratio_still_capped_when_heavy_load_confirmed(make_coordinator):
    """Even with confirmation, an absurd reading is still capped - the
    appliance confirms genuine activity, not the plausibility of the
    exact wattage."""
    coordinator = make_coordinator({})
    coordinator.hourly_consumption_profile[20] = [0.3]
    coordinator._recent_consumption_readings_kw = [50.0]  # implausible glitch
    coordinator.last_heavy_load_source = "quooker"

    ratio = coordinator._get_smoothed_consumption_correction_ratio(20)

    from custom_components.energy_management_system.const import (
        MAX_CONSUMPTION_CORRECTION_RATIO,
    )

    assert ratio == MAX_CONSUMPTION_CORRECTION_RATIO


def test_heavy_load_source_wired_into_full_update_tick(make_coordinator, hass):
    """End-to-end: the confirmed source is computed and stored during
    the normal update tick, so it's visible in diagnostics."""
    import asyncio
    from conftest import make_price_forecast

    def price_fn(hour, minute):
        return 2_500_000

    forecast = make_price_forecast(DAY0, price_fn)
    hass.states.set("sensor.price", "0", {"forecast": forecast})
    hass.states.set("sensor.p1", "300")
    hass.states.set("sensor.vaatwasser_vermogen", "1500")

    coordinator = make_coordinator(
        _base_config(
            price_sensor_entity="sensor.price",
            price_attribute="price_tax_included",
            operation_select_entity="select.op",
            manual_power_number_entity="number.pow",
            consumption_power_sensor_entity="sensor.p1",
        )
    )

    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: DAY0.replace(hour=10, minute=0)
    asyncio.run(coordinator._async_update_locked())

    assert coordinator.last_heavy_load_source == "vaatwasser"
