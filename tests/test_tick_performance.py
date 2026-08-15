"""Hoe zwaar is een ronde? (v2.1.0)

Gevraagd: "Nu wordt alle data om de 5 minuten gerefreshed, wat als we
naar live gaan? Hoe belastend is dat?"

Dat viel niet te schatten: in een testomgeving zonder echte prijzen
bouwt de kwartierplanning niet, en dat is juist het zwaarste deel. Een
geschat getal naast echte cijfers zetten is precies wat deze week een
paar keer is teruggedraaid.

Dus meet de integratie het zelf.
"""
from custom_components.energy_management_system.const import (
    TICK_MAX_DUTY_FRACTION,
    UPDATE_INTERVAL_MINUTES,
)


def test_without_measurements_it_says_so(make_coordinator, hass):
    c = make_coordinator({})

    assert c.get_tick_performance()["beschikbaar"] is False


def test_the_load_is_the_share_of_the_interval(make_coordinator, hass):
    """Een ronde van 300 ms bij vijf minuten is 0,1% van de tijd."""
    c = make_coordinator({})
    c.tick_duration_history = [300.0] * 10

    p = c.get_tick_performance()

    assert p["mediaan_ms"] == 300.0
    verwacht = 100 * 0.3 / (UPDATE_INTERVAL_MINUTES * 60)
    assert abs(p["belasting_procent"] - verwacht) < 0.001


def test_it_names_the_smallest_responsible_interval(make_coordinator, hass):
    """Dat is het antwoord op "kan het vaker?" - met een getal in plaats
    van een vermoeden."""
    c = make_coordinator({})
    c.tick_duration_history = [500.0] * 10

    p = c.get_tick_performance()

    # 0,5 s per ronde bij hoogstens 5% belasting = 10 s ertussen.
    assert p["kleinste_verantwoorde_interval_s"] == round(
        0.5 / TICK_MAX_DUTY_FRACTION, 1
    )


def test_the_slowest_round_is_kept_separately(make_coordinator, hass):
    """De mediaan verbergt een uitschieter, en juist die bepaalt of Home
    Assistant merkbaar hapert."""
    c = make_coordinator({})
    c.tick_duration_history = [50.0] * 9 + [2000.0]

    p = c.get_tick_performance()

    assert p["mediaan_ms"] == 50.0
    assert p["langzaamste_ms"] == 2000.0


def test_a_heavy_round_is_flagged(make_coordinator, hass):
    """Boven vijf procent staat Home Assistant te vaak op deze
    integratie te wachten."""
    import custom_components.energy_management_system.coordinator as mod
    from datetime import datetime, timezone

    nu = datetime(2026, 8, 15, 13, 0, tzinfo=timezone.utc)
    mod.dt_util.now = lambda: nu

    c = make_coordinator({})
    c.last_successful_update = nu.isoformat()
    c.gross_consumption_today_kwh = 0.0
    c.energy_daily_history = []
    # 30 seconden per ronde bij vijf minuten = 10%.
    c.tick_duration_history = [30_000.0] * 10

    namen = [b["naam"] for b in c.get_consistency_checks(nu)["bevindingen"]]

    assert "Rondeduur" in namen


def test_measurements_do_not_survive_a_restart():
    """De meting geldt voor de HUIDIGE versie op de HUIDIGE machine. Een
    herstart komt meestal juist door een nieuwe versie, en dan zegt de
    oude meting niets meer."""
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "tick_duration_history" not in PERSISTED_PLAIN_FIELDS
