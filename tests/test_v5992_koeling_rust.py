"""v5.99.2: goedkope koeling - rusttijd korter bij echte belasting, tekst met tijden.

Gemeld 15-10 12:05: "maar de ventilator is net uitgezet" terwijl hij om 11:10
uit ging; en "ik ga zo volgas laden, dan gaat hij toch eerder aan?".
"""
from datetime import datetime, timedelta, timezone

from test_battery_cooling_control import FAN, _config, _situatie


def _klaar(make_coordinator, hass, minuten_geleden, vermogen):
    import custom_components.energy_management_system.coordinator as mod

    c = make_coordinator(_config())
    nu = datetime(2026, 10, 15, 10, 5, tzinfo=timezone.utc)
    mod.dt_util.now = lambda: nu
    c.battery_cooling_last_change = nu - timedelta(minutes=minuten_geleden)
    _situatie(hass, accu=32.0, buiten=15.0, vermogen=vermogen)
    hass.states.set(FAN, "off")
    return c


def test_stil_wacht_twee_uur_met_tijden_in_de_tekst(make_coordinator, hass):
    c = _klaar(make_coordinator, hass, 55, 50)
    b = c.evaluate_battery_cooling()
    assert b["actie"] is None
    assert "uitgezet; weer aan vanaf" in b["reden"]
    assert "2 uur rust" in b["reden"]
    assert "net uitgezet" not in b["reden"]


def test_volgas_laden_wacht_alleen_de_gewone_rusttijd(make_coordinator, hass):
    c = _klaar(make_coordinator, hass, 55, -2500)
    assert c.evaluate_battery_cooling()["actie"] == "aan"


def test_volgas_laden_binnen_een_half_uur_wacht_nog(make_coordinator, hass):
    c = _klaar(make_coordinator, hass, 10, -2500)
    b = c.evaluate_battery_cooling()
    assert b["actie"] is None
    assert "30 min rust" in b["reden"]
