"""Melding, hersteld, melding, hersteld (v3.99.10).

Uit de export van 6 september, de nacht van 5 op 6:

    01:00  Accu haalt de nacht niet   nodig 1,78  beschikbaar 1,04
    02:01  hersteld
    02:08  Accu haalt de nacht niet   nodig 1,56
    02:12  hersteld
    03:03  Accu haalt de nacht niet   nodig 1,66
    03:13  hersteld

De probleemmelding heeft een demping. De herstelmelding omzeilt die
bewust (v1.6.2): "een probleem dat tien minuten na de melding is
opgelost zou anders stilzwijgend verdwijnen". Terecht - maar het
herstel vuurt nu in de EERSTE ronde waarin de voorwaarde wegvalt. En
de reserve springt tussen rondes, dus valt de voorwaarde weg en komt
hij terug, en dat drie keer in een nacht.

`plan_tekort` had dit al goed: "al een half uur geen kwartieren meer".
Dezelfde regel voor alle herstelmeldingen. Een probleem dat is
opgelost, blijft opgelost; een probleem dat na tien minuten terugkomt,
was niet opgelost.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import (
    HERSTEL_BEVESTIGING_MINUTEN,
)

T0 = datetime(2026, 9, 6, 1, 0, tzinfo=timezone.utc)


def _opzet(c):
    c.notifications_master_enabled = True
    c.notification_enabled = {"battery_wont_last_night": True}
    c.notification_active_conditions = ["battery_wont_last_night"]
    c.gestuurd = []
    c._dispatch_notification = lambda **kw: c.gestuurd.append(kw.get("geschiedenis_soort") or kw.get("kind"))
    c.config = dict(c.config or {})
    c.config["appliance_notify_service"] = "notify.test"


def test_herstel_pas_na_een_half_uur_rust(make_coordinator, hass):
    c = make_coordinator({})
    _opzet(c)

    c._dispatch_recovery_notifications([], now=T0)                     # net weg
    c._dispatch_recovery_notifications([], now=T0 + timedelta(minutes=10))

    assert "battery_wont_last_night_hersteld" not in c.gestuurd

    c._dispatch_recovery_notifications([], now=T0 + timedelta(minutes=HERSTEL_BEVESTIGING_MINUTEN + 1))

    assert "battery_wont_last_night_hersteld" in c.gestuurd


def test_komt_het_terug_dan_begint_de_teller_opnieuw(make_coordinator, hass):
    """02:01 weg, 02:08 terug: geen herstel geweest, en de teller start

    opnieuw.
    """
    c = make_coordinator({})
    _opzet(c)

    c._dispatch_recovery_notifications([], now=T0)
    c._dispatch_recovery_notifications(["battery_wont_last_night"], now=T0 + timedelta(minutes=8))
    c._dispatch_recovery_notifications([], now=T0 + timedelta(minutes=12))
    c._dispatch_recovery_notifications([], now=T0 + timedelta(minutes=35))

    assert "battery_wont_last_night_hersteld" not in c.gestuurd

    c._dispatch_recovery_notifications([], now=T0 + timedelta(minutes=12 + HERSTEL_BEVESTIGING_MINUTEN + 1))
    assert c.gestuurd.count("battery_wont_last_night_hersteld") == 1
