"""NILM confirmed-devices overview table (v0.63.51, requested): naam,
huidig vermogen, trend - three columns. Trend derived from the existing
CUSUM tracking (v0.63.39), no new tracking mechanism.
"""


def _confirm_device(coordinator, entity_id, friendly_name, power_w=0.0):
    coordinator.nilm_confirmed_devices[entity_id] = {
        "friendly_name": friendly_name,
        "confirmed_at": "2026-08-01",
        "daily_avg_history": [],
        "cusum_accumulator": 0.0,
        "anomaly_detected": False,
        "estimated_drift_percent": None,
        "reference_avg_w": None,
        "_today_sum": 0.0,
        "_today_count": 0,
        "_check_date": None,
    }


def test_table_has_three_columns_per_row(make_coordinator, hass):
    coordinator = make_coordinator({})
    _confirm_device(coordinator, "sensor.koelkast", "Koelkast")
    hass.states.set("sensor.koelkast", "82")

    table = coordinator.get_nilm_devices_table()

    assert len(table) == 1
    row = table[0]
    assert set(row.keys()) == {"naam", "huidig_vermogen_w", "trend"}
    assert row["naam"] == "Koelkast"
    assert row["huidig_vermogen_w"] == 82.0


def test_table_sorted_by_name(make_coordinator, hass):
    coordinator = make_coordinator({})
    _confirm_device(coordinator, "sensor.b", "Wasmachine-stekker")
    _confirm_device(coordinator, "sensor.a", "Aquarium")

    table = coordinator.get_nilm_devices_table()

    assert [row["naam"] for row in table] == ["Aquarium", "Wasmachine-stekker"]


def test_trend_unknown_without_enough_history(make_coordinator, hass):
    coordinator = make_coordinator({})
    _confirm_device(coordinator, "sensor.koelkast", "Koelkast")

    table = coordinator.get_nilm_devices_table()

    assert "nog niet genoeg data" in table[0]["trend"]


def test_trend_stable_when_close_to_reference(make_coordinator, hass):
    coordinator = make_coordinator({})
    _confirm_device(coordinator, "sensor.koelkast", "Koelkast")
    coordinator.nilm_confirmed_devices["sensor.koelkast"]["reference_avg_w"] = 80.0
    coordinator.nilm_confirmed_devices["sensor.koelkast"]["daily_avg_history"] = [81.0]

    table = coordinator.get_nilm_devices_table()

    assert table[0]["trend"] == "→ stabiel"


def test_trend_rising_above_threshold(make_coordinator, hass):
    coordinator = make_coordinator({})
    _confirm_device(coordinator, "sensor.koelkast", "Koelkast")
    coordinator.nilm_confirmed_devices["sensor.koelkast"]["reference_avg_w"] = 80.0
    coordinator.nilm_confirmed_devices["sensor.koelkast"]["daily_avg_history"] = [90.0]

    table = coordinator.get_nilm_devices_table()

    assert "stijgend" in table[0]["trend"]
    assert "aanhoudend" not in table[0]["trend"]


def test_trend_falling_below_threshold(make_coordinator, hass):
    coordinator = make_coordinator({})
    _confirm_device(coordinator, "sensor.koelkast", "Koelkast")
    coordinator.nilm_confirmed_devices["sensor.koelkast"]["reference_avg_w"] = 80.0
    coordinator.nilm_confirmed_devices["sensor.koelkast"]["daily_avg_history"] = [70.0]

    table = coordinator.get_nilm_devices_table()

    assert "dalend" in table[0]["trend"]


def test_trend_flags_sustained_anomaly_distinctly(make_coordinator, hass):
    coordinator = make_coordinator({})
    _confirm_device(coordinator, "sensor.koelkast", "Koelkast")
    coordinator.nilm_confirmed_devices["sensor.koelkast"]["reference_avg_w"] = 80.0
    coordinator.nilm_confirmed_devices["sensor.koelkast"]["daily_avg_history"] = [130.0]
    coordinator.nilm_confirmed_devices["sensor.koelkast"]["anomaly_detected"] = True
    coordinator.nilm_confirmed_devices["sensor.koelkast"][
        "estimated_drift_percent"
    ] = 62.5

    table = coordinator.get_nilm_devices_table()

    assert "mogelijk defect" in table[0]["trend"]
    assert "62" in table[0]["trend"]


def test_anomaly_with_non_positive_latest_drift_omits_the_misleading_percentage(
    make_coordinator, hass
):
    """v0.63.90, found during a diagnostics review: the CUSUM alarm is
    one-sided (only ever accumulates from sustained rises, clamped at
    0), so "aanhoudend stijgend" is conceptually always correct once
    it fires - but estimated_drift_percent is just the MOST RECENT
    day's deviation, which can legitimately be near-zero or slightly
    negative even while the accumulated history (built up over earlier
    days) triggered the alarm. Showing a non-positive number right next
    to "stijgend" (rising) looks contradictory - it must be omitted."""
    coordinator = make_coordinator({})
    _confirm_device(coordinator, "sensor.eetkamer_lamp", "Eetkamer lamp")
    coordinator.nilm_confirmed_devices["sensor.eetkamer_lamp"]["reference_avg_w"] = 0.17
    coordinator.nilm_confirmed_devices["sensor.eetkamer_lamp"][
        "daily_avg_history"
    ] = [0.17]
    coordinator.nilm_confirmed_devices["sensor.eetkamer_lamp"][
        "anomaly_detected"
    ] = True
    coordinator.nilm_confirmed_devices["sensor.eetkamer_lamp"][
        "estimated_drift_percent"
    ] = -0.0

    table = coordinator.get_nilm_devices_table()

    trend = table[0]["trend"]
    assert "mogelijk defect" in trend
    assert "aanhoudend stijgend" in trend
    assert "%" not in trend  # no misleading (-0%) shown


def test_empty_table_when_nothing_confirmed(make_coordinator, hass):
    coordinator = make_coordinator({})

    table = coordinator.get_nilm_devices_table()

    assert table == []
