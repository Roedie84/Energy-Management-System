"""Snelle gezondheidscheck-samenvatting (v0.63.91, gevraagd: "zijn er
nog zaken om de integratie te verbeteren, bijvoorbeeld de diagnostiek
gedetailleerder maken"). Puur informatief, hergebruikt bestaande,
al berekende signalen - geen nieuwe metingen.
"""
import pytest
from datetime import datetime, timezone


@pytest.fixture(autouse=True)
def _restore_dt_util_now():
    """v0.63.108: enkele tests in dit bestand zetten `dt_util.now`
    tijdelijk vast op een bekende datum (nodig voor de nieuwe, datum-
    gevoelige diagnostiek-checks). Zonder herstel zou dat blijven
    hangen voor tests die hierna draaien - een bestaand patroon
    elders in deze testsuite (18 andere bestanden doen hetzelfde
    zonder opruiming), maar dat is geen reden om zelf ook bij te
    dragen aan hetzelfde probleem."""
    from custom_components.energy_management_system import coordinator as coord_mod

    original = coord_mod.dt_util.now
    yield
    coord_mod.dt_util.now = original



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


def test_shows_recovery_progress_for_a_normalizing_device(make_coordinator, hass):
    """v0.63.100, gevraagd: "kan dit eerder in diagnostiek worden
    opgevangen" - een apparaat dat alweer een paar dagen normaal
    gedrag laat zien (op weg naar auto-reset) moet die context tonen,
    niet alleen een kale "mogelijk defect"-melding."""
    coordinator = make_coordinator({})
    coordinator.nilm_confirmed_devices = {
        "sensor.a": {
            "friendly_name": "CV-ketel Vermogen",
            "anomaly_detected": True,
            "_normal_streak_days": 2,
        },
    }

    summary = coordinator.get_diagnostic_summary()

    assert any(
        "2 dag(en) op rij weer normaal" in p for p in summary["aandachtspunten"]
    )
    assert any("nog 3 dag(en)" in p for p in summary["aandachtspunten"])


def test_no_recovery_note_without_a_streak(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.nilm_confirmed_devices = {
        "sensor.a": {
            "friendly_name": "CV-ketel Vermogen",
            "anomaly_detected": True,
            "_normal_streak_days": 0,
        },
    }

    summary = coordinator.get_diagnostic_summary()

    assert not any("weer normaal" in p for p in summary["aandachtspunten"])


def test_flags_climate_projection_with_no_learned_cells_after_days(
    make_coordinator, hass
):
    """v0.63.108, gevraagd: "kun je zien te detecteren in de diagnose"
    - verklaart waarom Korte termijn/Betrouwbaar er identiek uitzien
    zonder dat het een bug is."""
    from datetime import date, timedelta
    from custom_components.energy_management_system import coordinator as coord_mod

    fixed_now = datetime(2026, 8, 6, 12, tzinfo=timezone.utc)
    coord_mod.dt_util.now = lambda: fixed_now

    coordinator = make_coordinator(
        {"living_room_temperature_sensor_entity": "sensor.living_room_temp"}
    )
    coordinator.first_seen_date = fixed_now.date() - timedelta(days=3)
    coordinator.climate_rate_history = {}

    summary = coordinator.get_diagnostic_summary()

    assert any(
        "Klimaat-projectie" in p and "nog geen enkele geleerde cel" in p
        for p in summary["aandachtspunten"]
    )


def test_no_climate_flag_with_some_learned_data(make_coordinator, hass):
    from datetime import timedelta
    from custom_components.energy_management_system import coordinator as coord_mod

    fixed_now = datetime(2026, 8, 6, 12, tzinfo=timezone.utc)
    coord_mod.dt_util.now = lambda: fixed_now

    coordinator = make_coordinator(
        {"living_room_temperature_sensor_entity": "sensor.living_room_temp"}
    )
    coordinator.first_seen_date = fixed_now.date() - timedelta(days=3)
    coordinator.climate_rate_history = {"20|beide_dicht|uit": [0.5]}

    summary = coordinator.get_diagnostic_summary()

    assert not any("Klimaat-projectie" in p for p in summary["aandachtspunten"])


def test_no_climate_flag_too_early_to_expect_data(make_coordinator, hass):
    from custom_components.energy_management_system import coordinator as coord_mod

    fixed_now = datetime(2026, 8, 6, 12, tzinfo=timezone.utc)
    coord_mod.dt_util.now = lambda: fixed_now

    coordinator = make_coordinator(
        {"living_room_temperature_sensor_entity": "sensor.living_room_temp"}
    )
    coordinator.first_seen_date = fixed_now.date()  # started today
    coordinator.climate_rate_history = {}

    summary = coordinator.get_diagnostic_summary()

    assert not any("Klimaat-projectie" in p for p in summary["aandachtspunten"])


def test_flags_large_number_of_unconfirmed_nilm_candidates(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.nilm_unconfirmed_candidates = {
        f"sensor.device_{i}": {"friendly_name": f"Device {i}"} for i in range(20)
    }

    summary = coordinator.get_diagnostic_summary()

    assert any("20 onbevestigde NILM-kandidaten" in p for p in summary["aandachtspunten"])


def test_no_flag_for_a_small_number_of_candidates(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.nilm_unconfirmed_candidates = {
        "sensor.a": {"friendly_name": "A"},
        "sensor.b": {"friendly_name": "B"},
    }

    summary = coordinator.get_diagnostic_summary()

    assert not any("onbevestigde NILM-kandidaten" in p for p in summary["aandachtspunten"])


def test_flags_water_total_much_higher_than_recorded_sessions(make_coordinator, hass):
    from custom_components.energy_management_system import coordinator as coord_mod

    fixed_now = datetime(2026, 8, 6, 12, tzinfo=timezone.utc)
    coord_mod.dt_util.now = lambda: fixed_now

    coordinator = make_coordinator(
        {"water_daily_total_sensor_entity": "sensor.water_daily"}
    )
    coordinator.water_daily_total_l = 60.0
    today = fixed_now.date().isoformat()
    coordinator.water_session_history = [
        {"gestart": f"{today}T08:00:00+00:00", "liter": 1.0},
    ]

    summary = coordinator.get_diagnostic_summary()

    assert any(
        "Waterverbruik" in p and "mogelijk" in p for p in summary["aandachtspunten"]
    )


def test_no_water_flag_when_sessions_explain_the_total(make_coordinator, hass):
    from custom_components.energy_management_system import coordinator as coord_mod

    fixed_now = datetime(2026, 8, 6, 12, tzinfo=timezone.utc)
    coord_mod.dt_util.now = lambda: fixed_now

    coordinator = make_coordinator(
        {"water_daily_total_sensor_entity": "sensor.water_daily"}
    )
    coordinator.water_daily_total_l = 60.0
    today = fixed_now.date().isoformat()
    coordinator.water_session_history = [
        {"gestart": f"{today}T08:00:00+00:00", "liter": 50.0},
    ]

    summary = coordinator.get_diagnostic_summary()

    assert not any("Waterverbruik" in p for p in summary["aandachtspunten"])


def test_no_water_flag_for_a_small_daily_total(make_coordinator, hass):
    coordinator = make_coordinator(
        {"water_daily_total_sensor_entity": "sensor.water_daily"}
    )
    coordinator.water_daily_total_l = 5.0  # below the 20L threshold
    coordinator.water_session_history = []

    summary = coordinator.get_diagnostic_summary()

    assert not any("Waterverbruik" in p for p in summary["aandachtspunten"])
