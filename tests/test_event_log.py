"""Logboek met drie prioriteiten (v2.1.0).

Gevraagd: "Misschien een soort logboek? Waarbij ik live besluiten, en
allerlei zaken kan zien? Dit in 3 prio's definieren, en bij een kritische
melding een melding naar mijn iPhone?"

De bouwstenen lagen er al, maar verspreid over vier reeksen. Dit voegt ze
samen op moment - bewust GEEN vijfde reeks die alles nog eens apart
bijhoudt, want dan kunnen de twee uit elkaar gaan lopen.
"""
from datetime import datetime, timezone

from custom_components.energy_management_system.const import (
    LOG_PRIO_AANDACHT,
    LOG_PRIO_INFO,
    LOG_PRIO_KRITIEK,
    LOG_PRIORITEITEN,
    NOTIFICATION_TYPES,
)

NU = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator({})
    c.notification_history = [
        {
            "moment": "2026-08-15T07:00:00+02:00",
            "soort": "plan_tekort",
            "titel": "Accu haalt de nacht niet",
            "bericht": "8 kwartieren aan het net",
        },
        {
            "moment": "2026-08-15T08:00:00+02:00",
            "soort": "battery_cooling",
            "titel": "Koeling aan",
            "bericht": "35 graden",
        },
    ]
    c.mode_change_log = [
        {"at": "2026-08-15T09:00:00+02:00", "reason": "expensive_quarter",
         "expected_mode": "manual"}
    ]
    c.battery_cooling_history = []
    c.energy_bridge_transition_log = []
    c.last_consistency_checks = {}
    return c


def test_every_notification_kind_has_a_priority():
    """Een soort zonder prioriteit zou stilzwijgend als info eindigen -
    ook als het kritiek is."""
    zonder = [
        kind for kind, *_ in NOTIFICATION_TYPES if kind not in LOG_PRIORITEITEN
    ]

    assert not zonder, zonder


def test_the_log_merges_the_existing_series(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)

    regels = c.get_event_log(NU)["regels"]

    soorten = {r["soort"] for r in regels}
    assert "plan_tekort" in soorten
    assert "besluit" in soorten


def test_it_is_sorted_newest_first(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)

    regels = c.get_event_log(NU)["regels"]

    assert regels == sorted(regels, key=lambda r: r["moment"], reverse=True)


def test_priorities_are_assigned(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)

    per_soort = {r["soort"]: r["prio"] for r in c.get_event_log(NU)["regels"]}

    assert per_soort["plan_tekort"] == LOG_PRIO_KRITIEK
    assert per_soort["battery_cooling"] == LOG_PRIO_INFO


def test_it_can_be_filtered(make_coordinator, hass):
    """Een logboek zonder filter is bij honderd regels onbruikbaar."""
    c = _coordinator(make_coordinator, hass)

    regels = c.get_event_log(NU, prio=LOG_PRIO_KRITIEK)["regels"]

    assert regels
    assert all(r["prio"] == LOG_PRIO_KRITIEK for r in regels)


def test_it_counts_per_priority(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)

    aantallen = c.get_event_log(NU)["aantallen"]

    assert aantallen[LOG_PRIO_KRITIEK] == 1
    assert set(aantallen) == {LOG_PRIO_KRITIEK, LOG_PRIO_AANDACHT, LOG_PRIO_INFO}


def test_no_second_series_is_kept():
    """Bewust geen vijfde reeks die alles nog eens apart bijhoudt: dan
    kunnen de twee uit elkaar gaan lopen, en dat is precies waar het deze
    week een paar keer misging."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("def get_event_log")
    blok = bron[kop : bron.index("\n    def ", kop + 10)]

    assert ".append(" not in blok.replace("regels.append(", "")


def test_a_critical_notification_breaks_through_silent_mode():
    """Gevraagd: "bij een kritische melding een melding naar mijn
    iPhone?"

    Een melding die om drie uur 's nachts tegelijk met de rest in de
    wachtrij belandt, is geen kritieke melding.
    `interruption-level: time-sensitive` is het iOS-veld daarvoor.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()

    assert "time-sensitive" in bron
    assert "LOG_PRIORITEITEN.get(kind) == LOG_PRIO_KRITIEK" in bron


def test_only_critical_kinds_get_the_flag(make_coordinator, hass):
    """Alles op time-sensitive zetten is hetzelfde als niets - dan gaat
    de telefoon bij elke modusverandering af."""
    assert LOG_PRIORITEITEN["mode_change"] == LOG_PRIO_INFO
    assert LOG_PRIORITEITEN["battery_cooling"] == LOG_PRIO_INFO
    assert LOG_PRIORITEITEN["plan_tekort"] == LOG_PRIO_KRITIEK


def test_the_critical_set_stays_small():
    """Als er tien soorten kritiek zijn, is er geen enkele meer
    kritiek."""
    kritiek = [
        k for k, v in LOG_PRIORITEITEN.items() if v == LOG_PRIO_KRITIEK
    ]

    assert len(kritiek) <= 8, kritiek
