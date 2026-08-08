"""Uitgezette meldingen blijven nalees baar (v1.12.5).

Gevraagd: "Als ik door een button een melding uitzet moet hij niet meer
naar mijn iPhone, maar nog wel zichtbaar zijn in [de geschiedenis]."

Terecht onderscheid: de schakelaar bepaalt of je telefoon rinkelt, niet
of het wordt vastgelegd. Tot nu toe sloeg een geblokkeerde melding de
geschiedenis over - en dan is uitzetten hetzelfde als weggooien.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_APPLIANCE_NOTIFY_SERVICE,
    NOTIFICATION_TYPES,
)

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator):
    return make_coordinator(
        {CONF_APPLIANCE_NOTIFY_SERVICE: "notify.telefoon"}
    )


def _stuur(c, kind="mode_change", titel="test"):
    c._dispatch_notification(
        notify_service="notify.telefoon",
        title=titel,
        message="bericht",
        notification_id=f"ems_{kind}",
        kind=kind,
    )


# --- de kern ---------------------------------------------------------


def test_a_disabled_notification_is_still_recorded(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c.set_notification_enabled("mode_change", False)

    _stuur(c)

    assert len(c.notification_history) == 1
    assert c.notification_history[0]["verstuurd"] is False


def test_it_does_not_reach_the_phone(make_coordinator, hass):
    """Vastleggen mag niet betekenen dat hij alsnog verstuurd wordt."""
    c = _coordinator(make_coordinator)
    c.set_notification_enabled("mode_change", False)

    _stuur(c)

    assert hass.services.calls == []


def test_the_reason_is_recorded(make_coordinator, hass):
    """Zonder reden lijkt het alsof de melding zomaar niet aankwam."""
    c = _coordinator(make_coordinator)
    c.set_notification_enabled("mode_change", False)

    _stuur(c)

    assert "staat uit" in c.notification_history[0]["reden_niet_verstuurd"]


def test_the_master_switch_behaves_the_same(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c.notifications_master_enabled = False

    _stuur(c)

    assert c.notification_history[0]["verstuurd"] is False
    assert hass.services.calls == []


def test_a_sent_notification_is_marked_as_sent(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c.set_notification_enabled("mode_change", True)

    _stuur(c)

    regel = c.notification_history[0]
    assert regel["verstuurd"] is True
    assert regel["reden_niet_verstuurd"] is None


# --- demping werkt bewust anders -------------------------------------


def test_a_throttled_repeat_is_not_recorded(make_coordinator, hass):
    """Het dempingsvenster bestaat juist om herhaling te voorkomen. Die
    herhaling dan alsnog vastleggen zou de geschiedenis volschrijven met
    dubbele regels - precies waar hij onbruikbaar van wordt."""
    c = _coordinator(make_coordinator)
    c.set_notification_enabled("mode_change", True)

    _stuur(c)
    _stuur(c)

    assert len(c.notification_history) == 1


def test_the_startup_grace_also_does_not_fill_the_history(
    make_coordinator, hass
):
    """De aanlooptijd na een herstart gaat ook over TIMING, niet over
    een keuze van de gebruiker."""
    c = _coordinator(make_coordinator)
    c.set_notification_enabled("sensor_unavailable", True)
    c._started_at = None

    from custom_components.energy_management_system import coordinator as mod

    origineel = mod.dt_util.now
    try:
        mod.dt_util.now = lambda: NOW
        c._started_at = NOW
        _stuur(c, "sensor_unavailable")
    finally:
        mod.dt_util.now = origineel

    assert c.notification_history == []


# --- zichtbaar op het dashboard --------------------------------------


def test_the_table_marks_unsent_notifications():
    """Zonder markering lijkt het alsof de schakelaar niets doet."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    yaml_tekst = (
        Path(pkg.__file__).parent / "dashboard_template.yaml"
    ).read_text()

    assert "m.verstuurd is defined and not m.verstuurd" in yaml_tekst
    assert "niet naar je telefoon gestuurd" in yaml_tekst


def test_every_type_can_be_disabled_and_still_logged(
    make_coordinator, hass
):
    """Geldt voor alle tweeëntwintig soorten, niet alleen de geteste."""
    c = _coordinator(make_coordinator)
    c.notifications_master_enabled = False

    for kind, _, _, _, _ in NOTIFICATION_TYPES:
        _stuur(c, kind)

    assert len(c.notification_history) == len(NOTIFICATION_TYPES)
    assert all(m["verstuurd"] is False for m in c.notification_history)
