

# --- v3.0.1: de dagteller rolt om op de klok -------------------------


def test_the_counter_resets_on_a_quiet_day(make_coordinator, hass):
    """Gemeld met een screenshot: "15 gebruiksmoment(en) vandaag, 0
    liter" - terwijl er niemand thuis was. De sessies waren van 14
    augustus, drie dagen eerder.

    De teller werd alleen omgezet bij een NIEUWE sessie. Gebeurde er een
    dag niets, dan bleef die van eergisteren staan.
    """
    from datetime import date, datetime, timezone

    import custom_components.energy_management_system.coordinator as mod

    c = make_coordinator({})
    c._water_sessions_day_key = date(2026, 8, 14)
    c.water_sessions_today_count = 15
    c.water_sessions_today_l = 47.3

    nu = datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc)
    mod.dt_util.now = lambda: nu
    c._rol_waterdag_om(nu)

    assert c.water_sessions_today_count == 0
    assert c.water_sessions_today_l == 0.0


def test_the_counter_is_left_alone_within_the_day(make_coordinator, hass):
    from datetime import date, datetime, timezone

    c = make_coordinator({})
    c._water_sessions_day_key = date(2026, 8, 17)
    c.water_sessions_today_count = 4

    c._rol_waterdag_om(datetime(2026, 8, 17, 20, 0, tzinfo=timezone.utc))

    assert c.water_sessions_today_count == 4


def test_the_rollover_runs_on_the_clock_not_on_an_event():
    """Vijfde keer een dagwissel die niet loopt, na v1.74.0, v1.95.0,
    v1.98.0 en v2.6.1. Een dagteller mag niet afhangen van een
    gebeurtenis die er misschien niet komt."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    # De omrol hangt aan de tick via `_evaluate_new_notifications`, die
    # elke ronde draait. Wat telt is dat hij op `now` loopt en niet op
    # het binnenkomen van een sessie.
    kop = bron.index("def _finish_decision_tick")
    blok = bron[kop : bron.index("\n    def ", kop + 10)]

    assert "_rol_waterdag_om(now)" in blok

    # En de sessie-afhandeling mag niet de enige plek zijn.
    kop2 = bron.index("def _rol_waterdag_om")
    blok2 = bron[kop2 : bron.index("\n    def ", kop2 + 10)]
    assert "started_at" not in blok2


def test_zero_litres_with_sessions_is_contradictory(make_coordinator, hass):
    """Vijftien momenten van elk nul liter kan niet - dat was de
    verklikker. Na de omrol hoort de tegenstrijdigheid weg te zijn."""
    from datetime import date, datetime, timezone

    c = make_coordinator({})
    c._water_sessions_day_key = date(2026, 8, 14)
    c.water_sessions_today_count = 15
    c.water_sessions_today_l = 0.0

    c._rol_waterdag_om(datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc))

    assert not (c.water_sessions_today_count > 0 and c.water_sessions_today_l == 0.0)
