"""Lopend, samenhangend verhaal in gewone taal (v0.63.97, gevraagd:
"een tabblad wat live vertelt wat de gehele integratie doet... om
mijzelf bewuster te maken wat er gebeurt op alle vlakken en mogelijk
weer extra input aan jou kan geven"). Puur informatief/samenvattend -
herformuleert bestaande state, berekent zelf niets nieuws.
"""
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc)


def test_narrative_always_includes_the_battery_explanation(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.last_explanation = "Er wordt nu verkocht tegen €0,27/kWh."

    narrative = coordinator.get_live_narrative(DAY0)

    assert "Er wordt nu verkocht tegen €0,27/kWh." in narrative


def test_narrative_mentions_a_running_dishwasher(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._dishwasher_state = "actief"
    coordinator._dishwasher_cycle_started_at = DAY0 - timedelta(minutes=25)

    narrative = coordinator.get_live_narrative(DAY0)

    assert "vaatwasser draait al 25 minuten" in narrative


def test_narrative_mentions_a_running_washing_machine(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._washing_machine_state = "actief"
    coordinator._washing_machine_cycle_started_at = DAY0 - timedelta(minutes=10)

    narrative = coordinator.get_live_narrative(DAY0)

    assert "wasmachine draait al 10 minuten" in narrative


def test_narrative_silent_about_appliances_when_idle(make_coordinator, hass):
    coordinator = make_coordinator({})

    result = coordinator._narrate_appliances(DAY0)

    assert result is None


def test_narrative_mentions_active_water_usage(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator._water_usage_state = "actief"
    coordinator._water_session_started_at = DAY0 - timedelta(minutes=6)

    narrative = coordinator.get_live_narrative(DAY0)

    assert "water sinds 6 minuten geleden" in narrative


def test_narrative_falls_back_to_daily_water_total_when_idle(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.water_daily_total_l = 142.0

    narrative = coordinator.get_live_narrative(DAY0)

    assert "142 L water verbruikt" in narrative


def test_narrative_mentions_unconfirmed_nilm_candidates(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.nilm_unconfirmed_candidates = {
        "sensor.a": {"friendly_name": "A"},
        "sensor.b": {"friendly_name": "B"},
    }

    narrative = coordinator.get_live_narrative(DAY0)

    assert "2 nog onbeoordeelde NILM-kandidaten" in narrative


def test_narrative_mentions_a_single_unconfirmed_candidate_with_correct_grammar(
    make_coordinator, hass
):
    coordinator = make_coordinator({})
    coordinator.nilm_unconfirmed_candidates = {"sensor.a": {"friendly_name": "A"}}

    narrative = coordinator.get_live_narrative(DAY0)

    assert "1 nog onbeoordeelde NILM-kandidaat" in narrative
    assert "kandidaten" not in narrative


def test_narrative_mentions_possibly_defective_nilm_devices(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.nilm_confirmed_devices = {
        "sensor.a": {"friendly_name": "CV-ketel", "anomaly_detected": True},
    }

    narrative = coordinator.get_live_narrative(DAY0)

    assert "mogelijk defect" in narrative
    assert "CV-ketel" in narrative


def test_narrative_mentions_climate_note_when_present(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.climate_forecast_note = "Geen weerentiteit geconfigureerd."

    narrative = coordinator.get_live_narrative(DAY0)

    assert "Geen weerentiteit geconfigureerd." in narrative


def test_narrative_mentions_projected_temperature_without_a_note(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.climate_forecast_trajectory = [
        {"kort_termijn_temp_c": 23.5},
    ]

    narrative = coordinator.get_live_narrative(DAY0)

    assert "23.5°C" in narrative


def test_narrative_includes_attention_points_when_present(make_coordinator, hass):
    coordinator = make_coordinator({})
    coordinator.measurement_quality = "slecht"
    coordinator.sensor_health_score = 10.0
    coordinator.energy_balance_error_history = [400.0, 500.0]

    narrative = coordinator.get_live_narrative(DAY0)

    assert "Let op:" in narrative
    assert "Sensor-gezondheid" in narrative


def test_narrative_omits_attention_section_when_nominal(make_coordinator, hass):
    coordinator = make_coordinator({})

    narrative = coordinator.get_live_narrative(DAY0)

    assert "Let op:" not in narrative


def test_narrative_falls_back_to_placeholder_without_any_decision_yet(
    make_coordinator, hass
):
    coordinator = make_coordinator({})

    narrative = coordinator.get_live_narrative(DAY0)

    assert "Nog geen data verwerkt." in narrative
