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


def test_empty_table_when_nothing_confirmed(make_coordinator, hass):
    coordinator = make_coordinator({})

    table = coordinator.get_nilm_devices_table()

    assert table == []
