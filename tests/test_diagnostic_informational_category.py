"""Informatieve observaties brengen de systeemstatus niet omlaag
(v0.63.116).

Gevraagd: "de melding duplicaten zie ik niet als een melding welke
systeem status niet naar ok kan brengen."

Waarschijnlijke NILM-duplicaatparen zijn een observatie over de
HA-installatie zelf (twee entiteiten die hetzelfde fysieke signaal
meten), niet iets dat mis is met deze integratie. Het is bovendien een
permanente toestand die bewust zo gelaten kan worden - dan zou de
systeemstatus voor altijd op "Aandacht gewenst" blijven staan en
daarmee waardeloos worden als signaal.

De diagnostiek-samenvatting kent daarom twee categorieën:
`aandachtspunten` (mogen de status omlaag brengen) en `informatief`
(blijven zichtbaar, laten de status op "OK").
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.sensor import (
    SystemStatusSensor,
)

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


def _add_duplicate_pair(coordinator):
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


def test_duplicates_alone_keep_the_summary_nominal(make_coordinator, hass):
    coordinator = make_coordinator({})
    _add_duplicate_pair(coordinator)

    summary = coordinator.get_diagnostic_summary()

    assert summary["status"] == "nominaal"
    assert summary["aandachtspunten"] == []
    assert len(summary["informatief"]) == 1


def test_duplicates_are_still_reported(make_coordinator, hass):
    """Onderdrukken is niet de bedoeling - alleen herclassificeren."""
    coordinator = make_coordinator({})
    _add_duplicate_pair(coordinator)

    summary = coordinator.get_diagnostic_summary()

    assert any("duplicaat" in p.lower() for p in summary["informatief"])


def test_system_status_stays_ok_with_only_duplicates(make_coordinator, hass):
    """De eigenlijke klacht, end-to-end op de statussensor zelf."""
    coordinator = make_coordinator({})
    _add_duplicate_pair(coordinator)
    coordinator.last_successful_update = None
    coordinator.last_error = None
    coordinator.last_error_time = None

    assert coordinator.system_status == "OK"


def test_real_attention_point_still_lowers_the_status(make_coordinator, hass):
    """Regressiebewaking: de status moet nog wél reageren op echte
    aandachtspunten, anders is het signaal alsnog waardeloos."""
    coordinator = make_coordinator({})
    _add_duplicate_pair(coordinator)
    coordinator.nilm_confirmed_devices["sensor.a"]["anomaly_detected"] = True
    coordinator.last_successful_update = None
    coordinator.last_error = None
    coordinator.last_error_time = None

    assert coordinator.system_status == "Aandacht gewenst"


def test_status_sensor_exposes_both_lists(make_coordinator, hass):
    coordinator = make_coordinator({})
    _add_duplicate_pair(coordinator)
    sensor = SystemStatusSensor(coordinator, "entry1")

    attrs = sensor.extra_state_attributes

    assert attrs["aandachtspunten"] == []
    assert any("duplicaat" in p.lower() for p in attrs["informatief"])


def test_narrative_labels_informational_items_differently(make_coordinator, hass):
    """In het Live-verhaal moeten informatieve regels zichtbaar blijven
    maar niet als probleem lezen."""
    coordinator = make_coordinator({})
    _add_duplicate_pair(coordinator)

    tekst = coordinator._narrate_attention()

    assert tekst is not None
    assert "Ter info:" in tekst
    assert "Let op:" not in tekst


def test_narrative_still_says_let_op_for_real_points(make_coordinator, hass):
    coordinator = make_coordinator({})
    _add_duplicate_pair(coordinator)
    coordinator.nilm_confirmed_devices["sensor.a"]["anomaly_detected"] = True

    tekst = coordinator._narrate_attention()

    assert "Let op:" in tekst
    assert "Ter info:" in tekst


def test_narrative_returns_none_when_nothing_at_all(make_coordinator, hass):
    coordinator = make_coordinator({})

    assert coordinator._narrate_attention() is None


def test_error_status_still_wins_over_informational(make_coordinator, hass):
    """Een echte, actieve fout blijft zwaarder wegen."""
    coordinator = make_coordinator({})
    _add_duplicate_pair(coordinator)
    coordinator.last_error = "iets ging mis"
    coordinator.last_error_time = NOW
    coordinator.last_successful_update = NOW - timedelta(minutes=30)

    assert coordinator.system_status == "Fout"
