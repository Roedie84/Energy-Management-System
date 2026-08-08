"""Dashboardcontrole in de diagnostiek-export (v1.16.3).

Gevraagd: "Had je alles afgevangen met een betere diagnose file?"

Eerlijk antwoord was nee. Van de veertien problemen op één dag zaten er
tien in het DASHBOARD, en de export bevatte alleen sensorwaarden - niet
hoe die worden getoond. Elke fout zat in de laag ertussen, en die was
alleen op een screenshot te zien.

Deze controle sluit dat gat voor negen van die tien: bestaat elke
entiteit waar het dashboard naar verwijst, en staat ze niet leeg?
"""
from pathlib import Path

import custom_components.energy_management_system as pkg

PAKKET = Path(pkg.__file__).parent


# --- de controle zelf ------------------------------------------------


def test_it_checks_every_referenced_entity(make_coordinator, hass):
    c = make_coordinator({})

    rapport = c.get_dashboard_health()

    assert rapport["beschikbaar"] is True
    assert rapport["gecontroleerd"] > 50


def test_a_missing_entity_is_reported(make_coordinator, hass):
    """Het patroon van vandaag: een verkeerd afgeleide entity_id die
    "Entiteit niet gevonden" toont."""
    c = make_coordinator({})

    rapport = c.get_dashboard_health()

    # In de testomgeving bestaat vrijwel niets, dus de lijst hoort
    # gevuld te zijn - dat bewijst dat de controle werkt.
    assert rapport["niet_bestaande_entiteiten"]


def test_an_empty_entity_is_reported_separately(make_coordinator, hass):
    """"Onbekend" en "Entiteit niet gevonden" zien er op een screenshot
    hetzelfde uit, maar vragen om een ander onderzoek: de eerste kan
    normaal zijn, de tweede nooit."""
    c = make_coordinator({})
    hass.states.set(
        "sensor.energy_management_system_last_decision_reason", "unknown"
    )

    rapport = c.get_dashboard_health()

    assert (
        "sensor.energy_management_system_last_decision_reason"
        in rapport["lege_entiteiten"]
    )
    assert (
        "sensor.energy_management_system_last_decision_reason"
        not in rapport["niet_bestaande_entiteiten"]
    )


def test_a_working_entity_is_not_reported(make_coordinator, hass):
    c = make_coordinator({})
    hass.states.set(
        "sensor.energy_management_system_last_decision_reason",
        "expensive_quarter",
    )

    rapport = c.get_dashboard_health()

    for lijst in ("niet_bestaande_entiteiten", "lege_entiteiten"):
        assert (
            "sensor.energy_management_system_last_decision_reason"
            not in rapport[lijst]
        )


# --- inbedding -------------------------------------------------------


def test_it_is_in_the_export():
    bron = (PAKKET / "diagnostics.py").read_text()

    assert "dashboard_health" in bron


def test_it_explains_what_the_findings_mean(make_coordinator, hass):
    """Een lijst entity_id's zonder duiding laat je gissen wat je ermee
    moet - zeker omdat "Onbekend" vaak normaal is en "niet gevonden"
    nooit."""
    c = make_coordinator({})

    toelichting = c.get_dashboard_health()["toelichting"]

    assert "Entiteit niet gevonden" in toelichting
    assert "Onbekend" in toelichting


def test_a_missing_template_does_not_crash(make_coordinator, hass):
    """Zonder sjabloon hoort de export gewoon door te gaan; een
    diagnostiek die zelf faalt is waardeloos."""
    c = make_coordinator({})
    c._read_dashboard_template = lambda: ""

    assert c.get_dashboard_health() == {"beschikbaar": False}
