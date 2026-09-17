"""Dagrapportage in de diagnostiek (v1.9.0).

Gevraagd: "Ik wil nu elke dag met je het diagnostiek file delen, is deze
voldoende gevuld zodat je elke dag kunt verbeteren?"

De export toonde tot dan toe alleen de HUIDIGE stand. Wat er om 03:00
gebeurde was onzichtbaar tenzij het toevallig in een bewaarde reeks
stond - en dan mis je precies de context die een diagnose mogelijk maakt.

Twee lagen: een beslislogboek per tick (het verloop binnen de dag) en een
dagsamenvatting (patronen over dagen heen).
"""
from datetime import date, datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    DAILY_REPORT_HISTORY_DAYS,
    DECISION_LOG_LENGTH,
)

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator):
    c = make_coordinator({})
    c.last_expected_mode = "smart"
    c.last_reason = "expensive_quarter"
    c.last_soc_percent = 62.0
    c.accustand_procent = lambda v=62.0: v
    c.last_available_kwh = 4.8
    c.last_current_price_per_kwh = 0.3421
    return c


# --- beslislogboek ---------------------------------------------------


def test_each_tick_is_logged(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    c._record_decision_log(NOW)

    regel = c.decision_log[0]
    assert regel["modus"] == "smart"
    assert regel["reden"] == "expensive_quarter"
    assert regel["soc"] == 62.0
    assert regel["prijs"] == 0.3421


def test_the_log_is_bounded(make_coordinator, hass):
    """Zeshonderd regels is ongeveer twee dagen bij een tick van vijf
    minuten - genoeg om een nacht terug te kijken zonder de export
    onleesbaar te maken."""
    c = _coordinator(make_coordinator)

    for i in range(DECISION_LOG_LENGTH + 100):
        c._record_decision_log(NOW + timedelta(minutes=5 * i))

    assert len(c.decision_log) == DECISION_LOG_LENGTH


def test_the_log_keeps_the_newest(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    for i in range(DECISION_LOG_LENGTH + 10):
        c._record_decision_log(NOW + timedelta(minutes=5 * i))

    laatste = c.decision_log[-1]["t"]
    assert laatste.startswith("2026-08-09") or laatste.startswith("2026-08-10")


def test_missing_values_do_not_crash_the_log(make_coordinator, hass):
    """Vlak na een herstart is nog niets ingevuld; dat mag het logboek
    niet onderuit halen."""
    c = make_coordinator({})

    c._record_decision_log(NOW)

    assert c.decision_log[0]["soc"] is None


# --- dagsamenvatting -------------------------------------------------


def test_a_day_is_summarised_at_the_rollover(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    c._update_daily_report(NOW)
    c._update_daily_report(NOW + timedelta(hours=6))
    c._update_daily_report(NOW + timedelta(days=1))

    assert len(c.daily_report_history) == 1
    assert c.daily_report_history[0]["datum"] == "2026-08-07"


def test_the_summary_counts_decisions(make_coordinator, hass):
    """Welke beslissingen hoe vaak tekent het karakter van de dag."""
    c = _coordinator(make_coordinator)

    c._update_daily_report(NOW)
    for i in range(3):
        c._update_daily_report(NOW + timedelta(hours=i + 1))
    c.last_reason = "cheap_block"
    c._update_daily_report(NOW + timedelta(hours=5))
    c._update_daily_report(NOW + timedelta(days=1))

    redenen = c.daily_report_history[0]["redenen"]
    assert redenen["expensive_quarter"] == 4
    assert redenen["cheap_block"] == 1


def test_the_biggest_reason_comes_first(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c._update_daily_report(NOW)
    c.last_reason = "zeldzaam"
    c._update_daily_report(NOW + timedelta(hours=1))
    c.last_reason = "vaak"
    for i in range(5):
        c._update_daily_report(NOW + timedelta(hours=2 + i))
    c._update_daily_report(NOW + timedelta(days=1))

    eerste = next(iter(c.daily_report_history[0]["redenen"]))
    assert eerste == "vaak"


def test_the_soc_range_is_tracked(make_coordinator, hass):
    """Zag de accu de bodem, of bleef hij structureel hoog? Dat zegt
    iets over of de reserve knelde."""
    c = _coordinator(make_coordinator)
    c._update_daily_report(NOW)
    c.last_soc_percent = 20.0
    c.accustand_procent = lambda v=20.0: v
    c._update_daily_report(NOW + timedelta(hours=1))
    c.last_soc_percent = 95.0
    c.accustand_procent = lambda v=95.0: v
    c._update_daily_report(NOW + timedelta(hours=2))
    c._update_daily_report(NOW + timedelta(days=1))

    rapport = c.daily_report_history[0]
    assert rapport["soc_min_procent"] == 20.0
    assert rapport["soc_max_procent"] == 95.0


def test_errors_are_counted(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c._update_daily_report(NOW)
    c.last_error = "iets mis"
    c._update_daily_report(NOW + timedelta(hours=1))
    c._update_daily_report(NOW + timedelta(days=1))

    assert c.daily_report_history[0]["fouten"] == 1


def test_the_report_includes_sensor_dropouts(make_coordinator, hass):
    """Op welke schaal viel er iets weg - dat was precies wat er miste
    bij de analyse van de gezondheidsscore."""
    c = _coordinator(make_coordinator)
    c.balance_missing_by_entity = {"sensor.zendure": 9}
    c.energy_balance_error_history = [50.0] * 11 + [None] * 9

    c._update_daily_report(NOW)
    c._update_daily_report(NOW + timedelta(days=1))

    rapport = c.daily_report_history[0]
    assert rapport["sensor_uitval"] == 9
    assert rapport["sensor_uitval_per_sensor"]["sensor.zendure"] == 9


def test_the_history_is_bounded(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    for d in range(DAILY_REPORT_HISTORY_DAYS + 10):
        c.daily_report_history.append(
            c._sluit_dagrapport_af(date(2026, 1, 1), c._nieuwe_dagteller())
        )
        c.daily_report_history = c.daily_report_history[
            -DAILY_REPORT_HISTORY_DAYS:
        ]

    assert len(c.daily_report_history) == DAILY_REPORT_HISTORY_DAYS


# --- persistentie en export ------------------------------------------


def test_the_daily_reports_survive_a_restart(make_coordinator, hass):
    """Dertig dagen patronen zijn waardeloos als ze bij elke herstart
    verdwijnen."""
    import asyncio

    bron = _coordinator(make_coordinator)
    bron.daily_report_history = [
        bron._sluit_dagrapport_af(date(2026, 8, 6), bron._nieuwe_dagteller())
    ]
    asyncio.run(bron.async_save_persisted_state_now())

    verse = make_coordinator({})
    asyncio.run(verse.async_load_persisted_state())

    assert len(verse.daily_report_history) == 1


def test_the_decision_log_is_deliberately_not_persisted():
    """Een momentopname van twee dagen heeft na een herstart weinig
    waarde, en zou de opslag met honderden regels per herstart
    belasten."""
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "decision_log" not in PERSISTED_PLAIN_FIELDS
    assert "daily_report_history" in PERSISTED_PLAIN_FIELDS


def test_both_are_in_the_diagnostics_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "decision_log" in bron
    assert "daily_report_history" in bron
