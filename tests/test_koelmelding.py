"""Twaalf koelmeldingen per etmaal (v3.99.13).

Nacht van 6 op 7 september: de ventilator aan om 01:12, uit om 01:42,
aan om 03:42, uit om 04:12, aan om 06:12, uit om 06:42. Allemaal
"koelen zolang het goedkoop is" - de opportunistische koeling van
v3.6.0, met het ritme dat v3.14.0 en v3.23.1 erin hebben gelegd. Het
doet precies wat het moet. Er twaalf keer per etmaal over vertellen is
geen informatie meer.

De geschiedenis en het logboek houden elke beurt bij. Op de telefoon
komt alleen nog het thermisch beheer: de accu boven zijn eigen grens.
"""
from custom_components.energy_management_system.const import (
    BATTERY_COOLING_MIN_ABSOLUTE_C,
)


def _besluit(c, actie, reden, accu_c):
    c.config = dict(c.config or {})
    c.config["appliance_notify_service"] = "notify.test"
    c.gestuurd = []
    c._dispatch_notification = lambda **kw: c.gestuurd.append(kw["title"])
    c.battery_cooling_history = []
    from datetime import datetime, timezone

    c.battery_cooling_last_change = datetime(2026, 9, 7, 1, 12, tzinfo=timezone.utc)
    c._leg_koelbesluit_vast(
        {"actie": actie, "reden": reden, "accu_c": accu_c, "buiten_c": 16.0,
         "delta_c": accu_c - 16.0, "vermogen_w": 230.0, "moment": "2026-09-07T01:12:20+02:00"}
    )
    return c.gestuurd


def test_goedkope_koeling_aan_wordt_niet_gepusht(make_coordinator, hass):
    c = make_coordinator({})
    gestuurd = _besluit(c, "aan", "accu 30°C met 17°C buiten - 13°C te halen voor een paar watt ventilator, dus koelen zolang het goedkoop is", 30.0)
    assert gestuurd == []
    assert len(c.battery_cooling_history) == 1


def test_goedkope_koeling_uit_ook_niet(make_coordinator, hass):
    c = make_coordinator({})
    assert _besluit(c, "uit", "accu 23.0°C, nog maar 6.8°C boven buiten en 230W belasting", 23.0) == []


def test_thermische_koeling_wel(make_coordinator, hass):
    c = make_coordinator({})
    gestuurd = _besluit(c, "aan", "accu staat 8.0°C boven buiten bij 1600W", BATTERY_COOLING_MIN_ABSOLUTE_C + 5)
    assert gestuurd == ["🔋 Accu: koeling AAN"]
