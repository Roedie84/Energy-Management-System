"""Snelle gezondheidscheck-samenvatting (v0.63.91, gevraagd: "zijn er
nog zaken om de integratie te verbeteren, bijvoorbeeld de diagnostiek
gedetailleerder maken"). Puur informatief, hergebruikt bestaande,
al berekende signalen - geen nieuwe metingen.
"""


def test_nominal_when_nothing_stands_out(make_coordinator, hass):
    coordinator = make_coordinator({})

    summary = coordinator.get_diagnostic_summary()

    assert summary["status"] == "nominaal"
    assert summary["aandachtspunten"] == []


def test_flags_poor_measurement_quality(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.measurement_quality = "slecht"
    coordinator.sensor_health_score = 0.0
    coordinator.energy_balance_error_history = [None, 460.0, 577.0]

    summary = coordinator.get_diagnostic_summary()

    assert summary["status"] == "aandacht_gewenst"
    assert any("Sensor-gezondheid" in p for p in summary["aandachtspunten"])


def test_good_measurement_quality_not_flagged(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.measurement_quality = "goed"

    summary = coordinator.get_diagnostic_summary()

    assert not any("Sensor-gezondheid" in p for p in summary["aandachtspunten"])


def test_flags_possibly_defective_nilm_devices(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.nilm_confirmed_devices = {
        "sensor.a": {"friendly_name": "CV-ketel", "anomaly_detected": True},
        "sensor.b": {"friendly_name": "Koelkast", "anomaly_detected": False},
    }

    summary = coordinator.get_diagnostic_summary()

    assert summary["status"] == "aandacht_gewenst"
    assert any("CV-ketel" in p for p in summary["aandachtspunten"])
    assert not any("Koelkast" in p for p in summary["aandachtspunten"])


def test_flags_nilm_duplicates(make_coordinator, hass):
    coordinator = make_coordinator({})
    history = [1.0, 1.0, 1.0, 1.0]
    coordinator.nilm_confirmed_devices = {
        "sensor.a": {
            "friendly_name": "Lamp A",
            "daily_avg_history": history,
            "anomaly_detected": False,
        },
        "sensor.b": {
            "friendly_name": "Lamp B",
            "daily_avg_history": history,
            "anomaly_detected": False,
        },
    }

    summary = coordinator.get_diagnostic_summary()

    assert summary["status"] == "aandacht_gewenst"
    assert any("duplicaat" in p.lower() for p in summary["aandachtspunten"])


def test_flags_recent_shortfall_days(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.reserve_daily_records = [
        {"date": "2026-08-01", "shortfall": False, "excess": False},
        {"date": "2026-08-02", "shortfall": True, "excess": False},
    ]

    summary = coordinator.get_diagnostic_summary()

    assert summary["status"] == "aandacht_gewenst"
    assert any("tekort-dag" in p for p in summary["aandachtspunten"])


def test_flags_sluipverbruik_detected(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.sluipverbruik_detected = True

    summary = coordinator.get_diagnostic_summary()

    assert summary["status"] == "aandacht_gewenst"
    assert any("Sluipverbruik" in p for p in summary["aandachtspunten"])


def test_flags_last_error(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.last_error = "Kon prijssensor niet uitlezen"

    summary = coordinator.get_diagnostic_summary()

    assert summary["status"] == "aandacht_gewenst"
    assert any("Kon prijssensor niet uitlezen" in p for p in summary["aandachtspunten"])


def test_multiple_issues_all_listed(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.measurement_quality = "slecht"
    coordinator.sensor_health_score = 10.0
    coordinator.energy_balance_error_history = [400.0, 500.0]
    coordinator.sluipverbruik_detected = True

    summary = coordinator.get_diagnostic_summary()

    assert len(summary["aandachtspunten"]) == 2
