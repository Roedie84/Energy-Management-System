"""Structurele NILM-uitsluitingspatronen (v0.63.89, gevraagd: "alles
waar fase 1 bij staat mag sowieso uitgesloten worden net als solaredge
en zendure entiteiten").
"""
from datetime import datetime, timezone

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)


def test_fase_1_entity_id_never_becomes_a_candidate(make_coordinator, hass):
    hass.states.set(
        "sensor.aquarium_jill_vermogen_fase_1",
        "5",
        {"unit_of_measurement": "W", "friendly_name": "Aquarium Jill Vermogen fase 1"},
    )
    coordinator = make_coordinator({})

    coordinator._update_nilm_discovery(DAY0)

    assert coordinator.nilm_unconfirmed_candidates == {}


def test_fase_1_in_friendly_name_only_is_also_excluded(make_coordinator, hass):
    """Even if the entity_id itself doesn't literally say fase_1, a
    friendly name containing 'fase 1' must still be excluded."""
    hass.states.set(
        "sensor.iets_anders_123",
        "5",
        {"unit_of_measurement": "W", "friendly_name": "Iets Vermogen fase 1"},
    )
    coordinator = make_coordinator({})

    coordinator._update_nilm_discovery(DAY0)

    assert coordinator.nilm_unconfirmed_candidates == {}


def test_solaredge_entity_never_becomes_a_candidate(make_coordinator, hass):
    hass.states.set(
        "sensor.solaredge_i1_ac_power",
        "1500",
        {"unit_of_measurement": "W", "friendly_name": "Solaredge I1 AC Power"},
    )
    coordinator = make_coordinator({})

    coordinator._update_nilm_discovery(DAY0)

    assert coordinator.nilm_unconfirmed_candidates == {}


def test_zendure_entity_never_becomes_a_candidate(make_coordinator, hass):
    hass.states.set(
        "sensor.zendure_battery_power",
        "300",
        {"unit_of_measurement": "W", "friendly_name": "Zendure Batterij Vermogen"},
    )
    coordinator = make_coordinator({})

    coordinator._update_nilm_discovery(DAY0)

    assert coordinator.nilm_unconfirmed_candidates == {}


def test_unrelated_sensor_is_unaffected(make_coordinator, hass):
    """The pattern exclusion must not be so broad it catches unrelated
    devices - a sanity check that normal discovery still works."""
    hass.states.set(
        "sensor.koelkast_vermogen",
        "80",
        {"unit_of_measurement": "W", "friendly_name": "Koelkast"},
    )
    coordinator = make_coordinator({})

    coordinator._update_nilm_discovery(DAY0)

    assert "sensor.koelkast_vermogen" in coordinator.nilm_unconfirmed_candidates


def test_pruned_from_existing_unconfirmed_candidates(make_coordinator, hass):
    """A device already sitting in the candidate list (discovered
    before this pattern rule existed) must be pruned on the next tick,
    not just excluded going forward for newly-seen entities."""
    coordinator = make_coordinator({})
    coordinator.nilm_unconfirmed_candidates = {
        "sensor.zendure_battery_power": {
            "friendly_name": "Zendure Batterij Vermogen",
            "current_power_w": 300,
            "first_seen": "2026-08-01",
        }
    }
    hass.states.set(
        "sensor.zendure_battery_power",
        "300",
        {"unit_of_measurement": "W", "friendly_name": "Zendure Batterij Vermogen"},
    )

    coordinator._update_nilm_discovery(DAY0)

    assert "sensor.zendure_battery_power" not in coordinator.nilm_unconfirmed_candidates


def test_pruned_from_existing_confirmed_devices(make_coordinator, hass):
    """A device already confirmed before this pattern rule existed
    must be removed from the confirmed list too - it's a structural
    exclusion, not just a "don't suggest new ones" rule."""
    coordinator = make_coordinator({})
    coordinator.nilm_confirmed_devices = {
        "sensor.aquarium_jill_vermogen_fase_1": {
            "friendly_name": "Aquarium Jill Vermogen fase 1",
            "confirmed_at": "2026-08-01",
        }
    }

    coordinator._update_nilm_discovery(DAY0)

    assert "sensor.aquarium_jill_vermogen_fase_1" not in coordinator.nilm_confirmed_devices


def test_pruned_from_rejected_entities_list(make_coordinator, hass):
    """A previously-rejected fase_1/solaredge/zendure entity is now
    redundant to keep in the separate rejected list - the pattern rule
    handles it structurally, so it gets pruned to keep that list small
    and meaningful."""
    coordinator = make_coordinator({})
    coordinator.nilm_rejected_entities = [
        "sensor.aquarium_jill_vermogen_fase_1",
        "sensor.koelkast_vermogen",
    ]

    coordinator._update_nilm_discovery(DAY0)

    assert coordinator.nilm_rejected_entities == ["sensor.koelkast_vermogen"]


def test_solarflow_entity_never_becomes_a_candidate(make_coordinator, hass):
    """v0.63.103, gerapporteerd: 'elke keer terug krijg onbevestigde
    kandidaten na herstart' - de batterij verschijnt onder de
    merknaam 'SolarFlow' (niet 'zendure') in entity-namen."""
    hass.states.set(
        "sensor.solarflow_2400_ac_pv1_solar_power",
        "0.0",
        {"unit_of_measurement": "W", "friendly_name": "SolarFlow 2400 AC PV1 Solar Power"},
    )
    coordinator = make_coordinator({})

    coordinator._update_nilm_discovery(DAY0)

    assert coordinator.nilm_unconfirmed_candidates == {}


def test_solcast_entity_never_becomes_a_candidate(make_coordinator, hass):
    hass.states.set(
        "sensor.solcast_pv_forecast_huidig_vermogen",
        "1085.0",
        {"unit_of_measurement": "W", "friendly_name": "Solcast PV Forecast Huidig vermogen"},
    )
    coordinator = make_coordinator({})

    coordinator._update_nilm_discovery(DAY0)

    assert coordinator.nilm_unconfirmed_candidates == {}


def test_mirrored_battery_entity_never_becomes_a_candidate(make_coordinator, hass):
    hass.states.set(
        "sensor.vermogen_accu_1_omgekeerd",
        "0.0",
        {
            "unit_of_measurement": "W",
            "friendly_name": "Vermogen accu 1 (omgekeerd) - fo4nhn2n1402093",
        },
    )
    coordinator = make_coordinator({})

    coordinator._update_nilm_discovery(DAY0)

    assert coordinator.nilm_unconfirmed_candidates == {}


def test_own_integration_sensor_never_becomes_a_candidate(make_coordinator, hass):
    """v0.63.103, gerapporteerd: de integratie stelde haar EIGEN,
    afgeleide sensoren voor als NILM-kandidaat (bijv. Piekvermogen,
    Hourly consumption profile) - die rapporteren ook in W maar zijn
    geen echte apparaten."""
    hass.states.set(
        "sensor.woonkamer_energy_management_system_piekvermogen",
        "0.0",
        {"unit_of_measurement": "W", "friendly_name": "Energy Management System Piekvermogen"},
    )
    hass.states.set(
        "sensor.woonkamer_energy_management_system_hourly_consumption_profile",
        "497.0",
        {
            "unit_of_measurement": "W",
            "friendly_name": "Energy Management System Hourly consumption profile",
        },
    )
    coordinator = make_coordinator({})

    coordinator._update_nilm_discovery(DAY0)

    assert coordinator.nilm_unconfirmed_candidates == {}


def test_legitimate_appliance_still_discovered_alongside_exclusions(
    make_coordinator, hass
):
    """Sanity check: the expanded exclusions must not accidentally
    catch unrelated, legitimate candidates."""
    hass.states.set(
        "sensor.televisie_woonkamer_vermogen",
        "2.5",
        {"unit_of_measurement": "W", "friendly_name": "Televisie Woonkamer Vermogen"},
    )
    hass.states.set(
        "sensor.solarflow_2400_ac_pv1_solar_power",
        "0.0",
        {"unit_of_measurement": "W", "friendly_name": "SolarFlow 2400 AC PV1 Solar Power"},
    )
    coordinator = make_coordinator({})

    coordinator._update_nilm_discovery(DAY0)

    assert "sensor.televisie_woonkamer_vermogen" in coordinator.nilm_unconfirmed_candidates
    assert (
        "sensor.solarflow_2400_ac_pv1_solar_power"
        not in coordinator.nilm_unconfirmed_candidates
    )


def test_own_integration_entity_pruned_from_existing_confirmed_devices(
    make_coordinator, hass
):
    coordinator = make_coordinator({})
    coordinator.nilm_confirmed_devices = {
        "sensor.woonkamer_energy_management_system_piekvermogen": {
            "friendly_name": "Energy Management System Piekvermogen",
            "confirmed_at": "2026-08-01",
        }
    }

    coordinator._update_nilm_discovery(DAY0)

    assert (
        "sensor.woonkamer_energy_management_system_piekvermogen"
        not in coordinator.nilm_confirmed_devices
    )


def test_p1_meter_phase_3_never_becomes_a_candidate(make_coordinator, hass):
    """v0.63.106, gerapporteerd: 'P1 meter vermogen mogen sowieso
    uitgesloten worden' - fase 3 glipte er eerder doorheen (alleen
    'fase 1' stond in het patroon, niet fase 2/3)."""
    hass.states.set(
        "sensor.p1_meter_vermogen_fase_3",
        "74.0",
        {"unit_of_measurement": "W", "friendly_name": "P1 meter Vermogen fase 3"},
    )
    coordinator = make_coordinator({})

    coordinator._update_nilm_discovery(DAY0)

    assert coordinator.nilm_unconfirmed_candidates == {}


def test_solar_production_forecast_entity_never_becomes_a_candidate(
    make_coordinator, hass
):
    """v0.63.106, gerapporteerd: 'Solar Production entiteiten... mogen
    sowieso uitgesloten worden' - een andere zon-voorspellingsintegratie
    dan Solcast, met eigen naamgeving."""
    hass.states.set(
        "sensor.solar_production_forecast_estimated_power_production_in_1_hour",
        "811.0",
        {
            "unit_of_measurement": "W",
            "friendly_name": "Solar production forecast Estimated power production - in 1 hour",
        },
    )
    coordinator = make_coordinator({})

    coordinator._update_nilm_discovery(DAY0)

    assert coordinator.nilm_unconfirmed_candidates == {}


def test_fase_2_entity_also_excluded(make_coordinator, hass):
    hass.states.set(
        "sensor.iets_fase_2",
        "5.0",
        {"unit_of_measurement": "W", "friendly_name": "Iets Vermogen fase 2"},
    )
    coordinator = make_coordinator({})

    coordinator._update_nilm_discovery(DAY0)

    assert coordinator.nilm_unconfirmed_candidates == {}
