"""CUSUM-uitschietercap voor NILM-drift.

v1.12.3: de vermogens in deze tests zijn x10 gegaan (6,2 -> 62 W). Er
geldt nu een ondergrens voor drift-detectie: een apparaat moet
noemenswaardig verbruiken én het verschil moet in absolute zin de moeite
waard zijn. Bij 6,2 W is een drift van 20% nog geen anderhalve watt, en
daarover melden leert je meldingen te negeren.
"""


def _device_with_history(history):
    return {
        "friendly_name": "Test apparaat",
        "daily_avg_history": list(history),
        "cusum_accumulator": 0.0,
        "anomaly_detected": False,
        "estimated_drift_percent": None,
        "reference_avg_w": None,
    }


def test_single_isolated_outlier_does_not_trigger_the_alarm(make_coordinator, hass):
    """The exact reported scenario: a stable ~6.2W device (CV-ketel-
    achtig) with a single isolated 45W outlier day must NOT trigger
    the alarm from that one day alone - the daily contribution is
    capped."""
    coordinator = make_coordinator({})
    stable_history = [62.0] * 10
    device = _device_with_history(stable_history)
    coordinator.nilm_confirmed_devices["sensor.test"] = device

    # One isolated outlier day.
    coordinator._finalize_nilm_device_day("sensor.test", device, 451.3)

    assert device["anomaly_detected"] is False
    assert device["cusum_accumulator"] <= 0.5


def test_sustained_deviation_still_triggers_the_alarm(make_coordinator, hass):
    """A genuine, repeated deviation (not a one-off) must still
    correctly accumulate and trigger the alarm - the cap only guards
    against isolated outliers, not real sustained drift."""
    coordinator = make_coordinator({})
    stable_history = [62.0] * 10
    device = _device_with_history(stable_history)
    coordinator.nilm_confirmed_devices["sensor.test"] = device

    # Several consecutive days with a genuine, sustained ~40% rise.
    for _ in range(5):
        coordinator._finalize_nilm_device_day("sensor.test", device, 87.0)

    assert device["anomaly_detected"] is True


def test_negative_deviation_is_not_capped(make_coordinator, hass):
    """A day with unusually LOW power (pulling the accumulator down)
    must not be affected by the cap - the cap only limits how much a
    single day can push the accumulator UP."""
    coordinator = make_coordinator({})
    device = _device_with_history([62.0] * 10)
    device["cusum_accumulator"] = 2.0  # already elevated
    coordinator.nilm_confirmed_devices["sensor.test"] = device

    coordinator._finalize_nilm_device_day("sensor.test", device, 1.0)

    # A near-zero reading should pull the accumulator down a lot more
    # than the cap would otherwise allow if it were symmetric.
    assert device["cusum_accumulator"] < 1.5


def test_auto_reset_after_sustained_return_to_normal(make_coordinator, hass):
    """v0.631.0, gevraagd: "kan dit live zelf oplossen" - zonder
    auto-reset zou het gerapporteerde CV-ketel-scenario bijna 90 dagen
    nodig hebben om via de normale, trage afbouw te herstellen. Na
    NILM_CUSUM_RESET_STREAK_DAYS opeenvolgende dagen genuine terugkeer
    naar normaal (op/onder de referentie) moet de accumulator direct
    volledig resetten."""
    from custom_components.energy_management_system.const import (
        NILM_CUSUM_RESET_STREAK_DAYS,
    )

    coordinator = make_coordinator({})
    device = _device_with_history([62.0] * 10)
    coordinator.nilm_confirmed_devices["sensor.test"] = device

    # Establish a genuine, elevated alarm first (sustained deviation).
    for _ in range(5):
        coordinator._finalize_nilm_device_day("sensor.test", device, 87.0)
    assert device["anomaly_detected"] is True
    assert device["cusum_accumulator"] > 0

    # Device genuinely returns to normal (at/below reference) for the
    # full reset-streak window.
    for _ in range(NILM_CUSUM_RESET_STREAK_DAYS):
        coordinator._finalize_nilm_device_day("sensor.test", device, 60.0)

    assert device["cusum_accumulator"] == 0.0
    assert device["anomaly_detected"] is False


def test_streak_resets_if_normal_behaviour_is_interrupted(make_coordinator, hass):
    """A single day back above the reference must reset the streak
    counter - the reset requires genuinely CONSECUTIVE normal days,
    not just "most" of them."""
    from custom_components.energy_management_system.const import (
        NILM_CUSUM_RESET_STREAK_DAYS,
    )

    coordinator = make_coordinator({})
    device = _device_with_history([62.0] * 10)
    coordinator.nilm_confirmed_devices["sensor.test"] = device

    for _ in range(5):
        coordinator._finalize_nilm_device_day("sensor.test", device, 87.0)
    assert device["anomaly_detected"] is True

    # Almost enough consecutive normal days...
    for _ in range(NILM_CUSUM_RESET_STREAK_DAYS - 1):
        coordinator._finalize_nilm_device_day("sensor.test", device, 60.0)
    # ...then one day breaks the streak.
    coordinator._finalize_nilm_device_day("sensor.test", device, 87.0)

    assert device["_normal_streak_days"] == 0
    assert device["cusum_accumulator"] > 0  # not reset yet


def test_no_reset_without_an_active_alarm(make_coordinator, hass):
    """Sustained normal behaviour on an already-healthy device (no
    accumulator to reset) must not error or do anything unexpected."""
    from custom_components.energy_management_system.const import (
        NILM_CUSUM_RESET_STREAK_DAYS,
    )

    coordinator = make_coordinator({})
    device = _device_with_history([62.0] * 10)
    coordinator.nilm_confirmed_devices["sensor.test"] = device

    for _ in range(NILM_CUSUM_RESET_STREAK_DAYS + 2):
        coordinator._finalize_nilm_device_day("sensor.test", device, 60.0)

    assert device["cusum_accumulator"] == 0.0
    assert device["anomaly_detected"] is False
