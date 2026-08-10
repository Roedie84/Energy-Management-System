"""NILM-like device auto-discovery (v0.63.39).

NOT genuine NILM (blind disaggregation of a single aggregate power
signal - a research-grade problem without training data). Instead:
discovers existing power-measuring sensor entities in Home Assistant
that aren't already tracked elsewhere in this integration, requires
explicit human confirmation via services before any tracking begins,
and then applies per-device CUSUM drift-detection (same principle as
the household sluipverbruik detector, v0.63.29) - purely informational,
never influences any battery decision.
"""
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)



def _vul_dag(coordinator, hass, entity_id, watt, dag, metingen=None):
    """Simuleert een volle dag aan metingen (v1.21.3).

    Sinds v1.21.3 vraagt een dagoordeel minstens NILM_MIN_SAMPLES_FOR_DAY
    metingen. Dat kwam voort uit een echte melding: met vijf metingen -
    een kwartier na een herstart - meldde de diepvries "-98,8% drift,
    mogelijk defect", terwijl de compressor in dat kwartier gewoon niet
    draaide.

    Een test die met twee metingen een dag afsluit, toetst dus iets dat
    in productie niet meer voorkomt.
    """
    from custom_components.energy_management_system.const import (
        NILM_MIN_SAMPLES_FOR_DAY,
    )

    hass.states.set(entity_id, str(watt))
    for n in range(metingen or NILM_MIN_SAMPLES_FOR_DAY):
        coordinator._update_nilm_confirmed_devices(
            dag + timedelta(minutes=5 * n)
        )

def test_discovers_a_power_sensor(make_coordinator, hass):
    hass.states.set(
        "sensor.koelkast_vermogen",
        "80",
        {"unit_of_measurement": "W", "friendly_name": "Koelkast"},
    )

    coordinator = make_coordinator({})
    coordinator._update_nilm_discovery(DAY0)

    assert "sensor.koelkast_vermogen" in coordinator.nilm_unconfirmed_candidates
    candidate = coordinator.nilm_unconfirmed_candidates["sensor.koelkast_vermogen"]
    assert candidate["friendly_name"] == "Koelkast"
    assert candidate["current_power_w"] == 80.0


def test_ignores_sensors_without_a_watt_unit(make_coordinator, hass):
    hass.states.set(
        "sensor.buiten_temperatuur",
        "18",
        {"unit_of_measurement": "°C", "friendly_name": "Buitentemperatuur"},
    )

    coordinator = make_coordinator({})
    coordinator._update_nilm_discovery(DAY0)

    assert coordinator.nilm_unconfirmed_candidates == {}


def test_excludes_already_configured_entities(make_coordinator, hass):
    hass.states.set(
        "sensor.pv_vermogen",
        "1500",
        {"unit_of_measurement": "W", "friendly_name": "PV-vermogen"},
    )

    coordinator = make_coordinator({"pv_power_sensor_entity": "sensor.pv_vermogen"})
    coordinator._update_nilm_discovery(DAY0)

    assert "sensor.pv_vermogen" not in coordinator.nilm_unconfirmed_candidates


def test_confirm_moves_candidate_to_confirmed_devices(make_coordinator, hass):
    hass.states.set(
        "sensor.koelkast_vermogen",
        "80",
        {"unit_of_measurement": "W", "friendly_name": "Koelkast"},
    )
    coordinator = make_coordinator({})
    coordinator._update_nilm_discovery(DAY0)

    result = coordinator.confirm_nilm_device("sensor.koelkast_vermogen")

    assert result is True
    assert "sensor.koelkast_vermogen" not in coordinator.nilm_unconfirmed_candidates
    assert "sensor.koelkast_vermogen" in coordinator.nilm_confirmed_devices
    assert (
        coordinator.nilm_confirmed_devices["sensor.koelkast_vermogen"][
            "friendly_name"
        ]
        == "Koelkast"
    )


def test_confirm_unknown_entity_returns_false(make_coordinator, hass):
    coordinator = make_coordinator({})
    result = coordinator.confirm_nilm_device("sensor.does_not_exist")

    assert result is False


def test_reject_removes_candidate_and_never_resuggests(make_coordinator, hass):
    hass.states.set(
        "sensor.random_vermogen",
        "5",
        {"unit_of_measurement": "W", "friendly_name": "Iets willekeurigs"},
    )
    coordinator = make_coordinator({})
    coordinator._update_nilm_discovery(DAY0)
    assert "sensor.random_vermogen" in coordinator.nilm_unconfirmed_candidates

    coordinator.reject_nilm_device("sensor.random_vermogen")
    assert "sensor.random_vermogen" not in coordinator.nilm_unconfirmed_candidates

    # A subsequent discovery scan must not re-suggest it.
    coordinator._update_nilm_discovery(DAY0 + timedelta(minutes=5))
    assert "sensor.random_vermogen" not in coordinator.nilm_unconfirmed_candidates
    assert "sensor.random_vermogen" in coordinator.nilm_rejected_entities


def test_reject_also_removes_an_already_confirmed_device(make_coordinator, hass):
    hass.states.set(
        "sensor.koelkast_vermogen",
        "80",
        {"unit_of_measurement": "W", "friendly_name": "Koelkast"},
    )
    coordinator = make_coordinator({})
    coordinator._update_nilm_discovery(DAY0)
    coordinator.confirm_nilm_device("sensor.koelkast_vermogen")

    coordinator.reject_nilm_device("sensor.koelkast_vermogen")

    assert "sensor.koelkast_vermogen" not in coordinator.nilm_confirmed_devices


def test_daily_average_tracked_for_confirmed_device(make_coordinator, hass):
    hass.states.set(
        "sensor.koelkast_vermogen",
        "80",
        {"unit_of_measurement": "W", "friendly_name": "Koelkast"},
    )
    coordinator = make_coordinator({})
    coordinator._update_nilm_discovery(DAY0)
    coordinator.confirm_nilm_device("sensor.koelkast_vermogen")

    # v1.21.3: een halve dag aan metingen, want met minder wordt de dag
    # bewust niet meer afgerond - twee metingen zeggen niets over een
    # apparaat dat in cycli werkt.
    _vul_dag(coordinator, hass, "sensor.koelkast_vermogen", 80, DAY0)
    _vul_dag(
        coordinator,
        hass,
        "sensor.koelkast_vermogen",
        100,
        DAY0 + timedelta(hours=10),
    )

    day2 = DAY0 + timedelta(days=1)
    coordinator._update_nilm_confirmed_devices(day2)

    device = coordinator.nilm_confirmed_devices["sensor.koelkast_vermogen"]
    assert device["daily_avg_history"] == [90.0]


def test_sustained_drift_flags_a_possible_defect(make_coordinator, hass):
    hass.states.set(
        "sensor.koelkast_vermogen",
        "80",
        {"unit_of_measurement": "W", "friendly_name": "Koelkast"},
    )
    coordinator = make_coordinator({})
    coordinator._update_nilm_discovery(DAY0)
    coordinator.confirm_nilm_device("sensor.koelkast_vermogen")
    device = coordinator.nilm_confirmed_devices["sensor.koelkast_vermogen"]

    # 15 stable days at 80W.
    # v1.21.3: elke dag een halve dag aan metingen; met één meting per
    # dag wordt de dag bewust niet meer afgerond.
    for i in range(15):
        day = DAY0 + timedelta(days=i)
        _vul_dag(coordinator, hass, "sensor.koelkast_vermogen", 80, day)

    # Then a sustained jump to 130W (well above the 10% slack) for
    # several days.
    for i in range(15, 22):
        day = DAY0 + timedelta(days=i)
        _vul_dag(coordinator, hass, "sensor.koelkast_vermogen", 130, day)

    assert device["anomaly_detected"] is True
    assert device["estimated_drift_percent"] > 0


def test_never_calls_any_hass_service(make_coordinator, hass):
    """NILM discovery/tracking must never touch the battery or any
    other device - purely observational."""
    hass.states.set(
        "sensor.koelkast_vermogen",
        "80",
        {"unit_of_measurement": "W", "friendly_name": "Koelkast"},
    )
    coordinator = make_coordinator({})
    coordinator._update_nilm_discovery(DAY0)
    coordinator.confirm_nilm_device("sensor.koelkast_vermogen")
    coordinator._update_nilm_confirmed_devices(DAY0)

    assert hass.services.calls == []
