"""Meldingen bij planningswijzigingen (v1.23.4).

Gevraagd: "Tevens wil ik voor belangrijke beslissingen/wijzigingen in de
planning graag een bericht op mijn telefoon en in het meldingenoverzicht.
Wel moeten meldingen op telefoon uit te schakelen zijn."

Alleen bij een OVERGANG, niet elke tick: anders levert één situatie
tientallen berichten per dag op, en dan zet je ze uit - precies wanneer
je ze nodig hebt.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    PRICE_SCALE_FACTOR,
    CONF_APPLIANCE_NOTIFY_SERVICE,
    CONF_BATTERY_TOTAL_CAPACITY_SENSOR,
    CONF_MANUAL_DISCHARGE_POWER,
    CONF_MIN_SOC_PERCENT,
    NOTIFICATION_TYPES,
)

NU = datetime(2026, 8, 11, 18, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass, beschikbaar=0.4, prijs=0.36):
    # v1.24.2: de parser geeft rauwe eenheden terug.
    prijs_ruw = prijs * PRICE_SCALE_FACTOR
    c = make_coordinator(
        {
            CONF_BATTERY_TOTAL_CAPACITY_SENSOR: "sensor.cap",
            CONF_MIN_SOC_PERCENT: 10.0,
            CONF_MANUAL_DISCHARGE_POWER: 1600.0,
            CONF_APPLIANCE_NOTIFY_SERVICE: "notify.telefoon",
        }
    )
    hass.states.set("sensor.cap", "8.6")
    c.last_available_kwh = beschikbaar
    c.last_expensive_price_threshold = 0.32
    c._get_forecast_entries = lambda: [
        (
            NU + timedelta(minutes=15 * i),
            NU + timedelta(minutes=15 * (i + 1)),
            prijs_ruw,
        )
        for i in range(40)
    ]
    c._estimate_pv_kwh_for_period = lambda a, b: 0.0
    c._estimate_consumption_kwh_for_period = lambda a, b: 0.08
    return c


# --- de melding zelf -------------------------------------------------


def test_a_shortfall_is_reported(make_coordinator, hass):
    """De belangrijkste: de accu haalt de nacht niet."""
    c = _coordinator(make_coordinator, hass)
    voor = len(c.notification_history)

    c._meld_planningswijzigingen(NU)

    nieuw = c.notification_history[voor:]
    assert any(r.get("soort") == "plan_tekort" for r in nieuw)


def test_it_only_fires_on_a_change(make_coordinator, hass):
    """Elke tick melden zou binnen een dag onleesbaar worden."""
    c = _coordinator(make_coordinator, hass)
    c._meld_planningswijzigingen(NU)
    tussen = len(c.notification_history)

    c._meld_planningswijzigingen(NU)

    assert len(c.notification_history) == tussen


def test_a_healthy_plan_reports_nothing(make_coordinator, hass):
    """Melden waar niets aan de hand is, maakt de melding waardeloos."""
    c = _coordinator(make_coordinator, hass, beschikbaar=7.5, prijs=0.15)
    voor = len(c.notification_history)

    c._meld_planningswijzigingen(NU)

    nieuw = c.notification_history[voor:]
    assert not [r for r in nieuw if r.get("soort") == "plan_tekort"]


def test_the_message_names_the_numbers(make_coordinator, hass):
    """Een melding zonder cijfers dwingt tot doorklikken."""
    c = _coordinator(make_coordinator, hass)
    voor = len(c.notification_history)

    c._meld_planningswijzigingen(NU)

    bericht = next(
        r["bericht"]
        for r in c.notification_history[voor:]
        if r.get("soort") == "plan_tekort"
    )
    assert "kwartier" in bericht
    assert "%" in bericht


# --- uitschakelbaar --------------------------------------------------


def test_all_three_are_switchable():
    """Gevraagd: "Wel moeten meldingen op telefoon uit te schakelen
    zijn." Elke soort hoort zijn eigen schakelaar te hebben."""
    soorten = {k for k, _, _, _, _ in NOTIFICATION_TYPES}

    for soort in ("plan_tekort", "plan_uitstel", "plan_verkoop_geblokkeerd"):
        assert soort in soorten, soort


def test_only_the_shortfall_defaults_on():
    """De tekortmelding vuurt alleen als er werkelijk iets misgaat; de
    andere twee zijn informatief en kunnen ruis worden."""
    standaard = {k for k, _, _, aan, _ in NOTIFICATION_TYPES if aan}

    assert "plan_tekort" in standaard
    assert "plan_uitstel" not in standaard
    assert "plan_verkoop_geblokkeerd" not in standaard


def test_each_has_a_switch_on_the_dashboard():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    tekst = (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()

    for soort in ("plan_tekort", "plan_uitstel", "plan_verkoop_geblokkeerd"):
        assert f"melding_{soort}" in tekst, soort


# --- veiligheid ------------------------------------------------------


def test_a_failing_notification_never_breaks_the_control():
    """Dit is een melding; die mag de aansturing nooit laten vallen."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    start = bron.index("self._meld_planningswijzigingen(now)")
    blok = bron[start - 200 : start + 200]

    assert "try:" in blok
    assert "except Exception" in blok


def test_the_new_fields_are_in_the_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "effective_min_soc_percent" in bron
    assert "quarter_plan_first_seen" in bron
