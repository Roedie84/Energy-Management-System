"""Wanneer is een tekort een melding waard? (v3.9.0)

Gemeld: "Deze melding op dit tijdstip is een beetje raar toch?" bij

    18 Aug 09:30 · Den accu haalt de nacht weer

Uit de geschiedenis bleek meer dan de bewoording: **75 meldingen** over
tekorten, waarvan 47 op één dag (16 augustus). Twaalf keer ging het om
EEN ENKEL kwartier. Om 06:44 stond "hersteld", om 06:45 weer "tekort",
en om 00:00 kwamen beide in dezelfde minuut.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_APPLIANCE_NOTIFY_SERVICE,
    PLAN_SHORTFALL_ALERT_MIN_QUARTERS,
    PLAN_SHORTFALL_RECOVERY_STABLE_MINUTES,
)

NU = datetime(2026, 8, 18, 9, 30, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass, tekorten, perioden=None):
    c = make_coordinator({CONF_APPLIANCE_NOTIFY_SERVICE: "notify.telefoon"})
    c.set_notification_enabled("plan_tekort", True)
    c.set_notification_enabled("plan_tekort_hersteld", True)
    c.get_quarter_plan_summary = lambda *a, **k: {
        "beschikbaar": True,
        "tekort_kwartieren": tekorten,
        "tekort_perioden": perioden or [],
        "laagste_soc_procent": 10,
    }
    return c


def _soorten(c):
    return [m["soort"] for m in c.notification_history]


def test_a_single_quarter_is_not_worth_a_message(make_coordinator, hass):
    """Eén kwartier is bij dit verbruik zo'n 0,1 kWh van het net. Dat is
    geen probleem maar een planning die precies uitkomt."""
    c = _coordinator(make_coordinator, hass, tekorten=1)

    c._meld_planningswijzigingen(NU)

    assert "plan_tekort" not in _soorten(c)


def test_a_real_shortfall_still_warns(make_coordinator, hass):
    c = _coordinator(
        make_coordinator, hass, tekorten=PLAN_SHORTFALL_ALERT_MIN_QUARTERS
    )

    c._meld_planningswijzigingen(NU)

    assert "plan_tekort" in _soorten(c)


def test_the_message_says_when(make_coordinator, hass):
    """"Haalt de nacht" om half tien 's ochtends slaat nergens op - het
    tekort kan op elk moment binnen de horizon liggen."""
    c = _coordinator(
        make_coordinator, hass, tekorten=5, perioden=["morgen 07:00-09:00"]
    )

    c._meld_planningswijzigingen(NU)

    bericht = next(
        m["bericht"] for m in c.notification_history if m["soort"] == "plan_tekort"
    )
    assert "morgen 07:00-09:00" in bericht


def test_the_message_no_longer_claims_the_night(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, tekorten=5)

    c._meld_planningswijzigingen(NU)

    titels = " ".join(m["titel"] for m in c.notification_history)
    assert "nacht" not in titels.lower()


def test_recovery_waits_for_a_stable_period(make_coordinator, hass):
    """Om 06:44 stond "hersteld", om 06:45 weer "tekort". Zonder
    wachttijd is die melding niets waard."""
    c = _coordinator(make_coordinator, hass, tekorten=5)
    c._meld_planningswijzigingen(NU)

    # Tekort weg, maar nog niet lang genoeg.
    c.get_quarter_plan_summary = lambda *a, **k: {
        "beschikbaar": True,
        "tekort_kwartieren": 0,
        "laagste_soc_procent": 28,
    }
    c._meld_planningswijzigingen(NU + timedelta(minutes=1))

    assert "plan_tekort_hersteld" not in _soorten(c)


def test_recovery_arrives_after_the_wait(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, tekorten=5)
    c._meld_planningswijzigingen(NU)

    c.get_quarter_plan_summary = lambda *a, **k: {
        "beschikbaar": True,
        "tekort_kwartieren": 0,
        "laagste_soc_procent": 28,
    }
    c._meld_planningswijzigingen(NU + timedelta(minutes=1))
    c._meld_planningswijzigingen(
        NU + timedelta(minutes=PLAN_SHORTFALL_RECOVERY_STABLE_MINUTES + 2)
    )

    assert "plan_tekort_hersteld" in _soorten(c)


def test_a_returning_shortfall_resets_the_clock(make_coordinator, hass):
    """Precies het gemelde patroon: hersteld om 06:44, tekort om 06:45.
    Dan hoort de klok opnieuw te beginnen."""
    c = _coordinator(make_coordinator, hass, tekorten=5)
    c._meld_planningswijzigingen(NU)

    c.get_quarter_plan_summary = lambda *a, **k: {
        "beschikbaar": True,
        "tekort_kwartieren": 0,
        "laagste_soc_procent": 28,
    }
    c._meld_planningswijzigingen(NU + timedelta(minutes=1))

    # En weer een tekort.
    c.get_quarter_plan_summary = lambda *a, **k: {
        "beschikbaar": True,
        "tekort_kwartieren": 5,
        "laagste_soc_procent": 10,
    }
    c._meld_planningswijzigingen(NU + timedelta(minutes=2))

    assert c._plan_tekort_vrij_sinds is None


def test_one_quarter_does_not_count_as_recovered(make_coordinator, hass):
    """Bij één kwartier komt er geen waarschuwing, maar er is ook geen
    herstel: er is immers nog een tekort."""
    c = _coordinator(make_coordinator, hass, tekorten=5)
    c._meld_planningswijzigingen(NU)

    c.get_quarter_plan_summary = lambda *a, **k: {
        "beschikbaar": True,
        "tekort_kwartieren": 1,
        "laagste_soc_procent": 10,
    }
    c._meld_planningswijzigingen(NU + timedelta(minutes=1))

    assert c._plan_tekort_vrij_sinds is None
    assert "plan_tekort_hersteld" not in _soorten(c)


def test_the_thresholds_match_the_reported_pattern():
    """Twaalf van de 75 meldingen gingen over één kwartier; de drempel
    moet die wegfilteren zonder een echt tekort te missen."""
    assert PLAN_SHORTFALL_ALERT_MIN_QUARTERS >= 3
    assert PLAN_SHORTFALL_RECOVERY_STABLE_MINUTES >= 15
