"""NILM-duplicaatdetectie (v0.63.91, gevraagd na een diagnostiek-
review waarbij 5 "Eetkamer lamp"-sensoren een identieke vermogens-
geschiedenis bleken te delen - vermoedelijk hetzelfde fysieke circuit
onder meerdere HA-entiteiten). Puur informatief - beslist niets
automatisch.
"""


def _confirm_device(coordinator, entity_id, friendly_name, history):
    coordinator.nilm_confirmed_devices[entity_id] = {
        "friendly_name": friendly_name,
        "confirmed_at": "2026-08-01",
        "daily_avg_history": history,
        "cusum_accumulator": 0.0,
        "anomaly_detected": False,
        "estimated_drift_percent": None,
        "reference_avg_w": None,
        "_today_sum": 0.0,
        "_today_count": 0,
        "_check_date": None,
    }


def test_identical_history_flagged_as_duplicate(make_coordinator, hass):
    coordinator = make_coordinator({})
    _confirm_device(
        coordinator, "sensor.lamp_1", "Eetkamer lamp 1", [0.17, 0.17, 1.63, 1.63]
    )
    _confirm_device(
        coordinator, "sensor.lamp_2", "Eetkamer lamp 2", [0.17, 0.17, 1.63, 1.63]
    )

    pairs = coordinator.get_nilm_duplicate_pairs()

    assert len(pairs) == 1
    assert {pairs[0]["apparaat_1"], pairs[0]["apparaat_2"]} == {
        "Eetkamer lamp 1",
        "Eetkamer lamp 2",
    }
    assert pairs[0]["gedeelde_dagen"] == 4


def test_within_tolerance_still_flagged(make_coordinator, hass):
    """Tiny measurement noise (within the tolerance fraction) must
    still count as a likely duplicate - exact-equality would be too
    strict for real-world sensor noise."""
    coordinator = make_coordinator({})
    _confirm_device(coordinator, "sensor.a", "Apparaat A", [10.0, 10.0, 10.0])
    _confirm_device(coordinator, "sensor.b", "Apparaat B", [10.05, 9.98, 10.02])

    pairs = coordinator.get_nilm_duplicate_pairs()

    assert len(pairs) == 1


def test_meaningfully_different_history_not_flagged(make_coordinator, hass):
    coordinator = make_coordinator({})
    _confirm_device(coordinator, "sensor.koelkast", "Koelkast", [70.0, 71.0, 69.0])
    _confirm_device(coordinator, "sensor.iptv", "IPTV", [3.0, 3.1, 2.9])

    pairs = coordinator.get_nilm_duplicate_pairs()

    assert pairs == []


def test_too_few_shared_days_not_flagged(make_coordinator, hass):
    """Even identical values must not be flagged if there aren't
    enough shared days yet - a coincidental single-day match isn't
    strong enough evidence."""
    coordinator = make_coordinator({})
    _confirm_device(coordinator, "sensor.a", "Apparaat A", [5.0, 5.0])
    _confirm_device(coordinator, "sensor.b", "Apparaat B", [5.0, 5.0])

    pairs = coordinator.get_nilm_duplicate_pairs()

    assert pairs == []


def test_three_identical_devices_produce_three_pairs(make_coordinator, hass):
    """With 3 mutually-identical devices, every distinct pair should be
    reported (A-B, A-C, B-C) - not just adjacent ones."""
    coordinator = make_coordinator({})
    history = [1.0, 1.0, 1.0, 1.0]
    _confirm_device(coordinator, "sensor.a", "Lamp A", history)
    _confirm_device(coordinator, "sensor.b", "Lamp B", history)
    _confirm_device(coordinator, "sensor.c", "Lamp C", history)

    pairs = coordinator.get_nilm_duplicate_pairs()

    assert len(pairs) == 3


def test_only_compares_the_most_recent_shared_days(make_coordinator, hass):
    """Devices confirmed at different times may have different-length
    histories - comparison should use the most recent overlapping
    days, not require equal-length lists."""
    coordinator = make_coordinator({})
    _confirm_device(coordinator, "sensor.a", "Lamp A", [99.0, 0.17, 0.17, 0.17])
    _confirm_device(coordinator, "sensor.b", "Lamp B", [0.17, 0.17, 0.17])

    pairs = coordinator.get_nilm_duplicate_pairs()

    assert len(pairs) == 1
    assert pairs[0]["gedeelde_dagen"] == 3


def test_empty_with_no_confirmed_devices(make_coordinator, hass):
    coordinator = make_coordinator({})

    assert coordinator.get_nilm_duplicate_pairs() == []
