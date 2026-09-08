"""Wat alleen meet, raakt niet uit het oog (v4.1).

Gevraagd: "Hoe weet ik zeker dat zaken die nu alleen meten niet uit het
oog verloren raken?"

Er was een melding bij de OMSLAG naar "klaar om mee te doen" (v3.61.0).
Mis je die, dan is hij weg. En de dingen die geen proefstandkandidaat
zijn - de ijklijn, Powercalc, het PV-model, de capaciteit, de
waterbronnen - hadden helemaal geen plek.

Nu:
1. Eén overzicht in de export en op het dashboard: alles wat meet en
   niet stuurt, met status, dagen aan het meten, en wat er zou
   gebeuren als het mee gaat doen. Rijp bovenaan.
2. Elke maandag om negen uur een melding met wat er klaar staat en al
   langer dan een week wacht - niet alleen bij de omslag.
"""
from datetime import datetime, timezone

import pytest

MAANDAG = datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc)   # maandag
DINSDAG = datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc)


def _proefstand(c, kandidaten):
    c.get_proefstand = lambda: {"kandidaten": kandidaten}
    c.get_helderheid_ijking = lambda: {"status": "onvoldoende_data", "mag_regelen": False, "wat_ontbreekt": "3 dagen"}
    c.get_powercalc_proef = lambda: {"status": "indicatief", "mag_regelen": False, "residu_rustiger": False}
    c.get_pv_model_evaluation = lambda: {"beschikbaar": True, "beter": False, "winst_procent": -11.5}
    c.gemeten_capaciteit_kwh = lambda: None
    c.get_water_source_overview = lambda: {}


def test_het_overzicht_zet_rijp_bovenaan(make_coordinator, hass):
    c = make_coordinator({})
    _proefstand(c, [
        {"naam": "Bijkopen bij tekort", "gereedheid": "meet nog", "status": "indicatief", "waarde": "-22 ct"},
        {"naam": "Verder vooruitkijken", "gereedheid": "klaar om mee te doen", "status": "betrouwbaar", "waarde": "+1.48 kWh", "stuurt_sinds": "v3.99.18"},
        {"naam": "Reserve uit de nabeschouwing", "gereedheid": "klaar om mee te doen", "status": "betrouwbaar", "waarde": "te hoog"},
    ])

    uit = c.get_meet_stuurt_niet()

    namen = [r["naam"] for r in uit["items"]]
    assert namen[0] == "Reserve uit de nabeschouwing"      # rijp en stuurt nog niet: bovenaan
    assert "Verder vooruitkijken" not in namen              # stuurt al
    assert "Heldere-hemel-ijklijn" in namen
    assert "Powercalc als NILM-hulp" in namen
    assert uit["rijp"] == ["Reserve uit de nabeschouwing"]


def test_maandag_negen_uur_een_herinnering(make_coordinator, hass):
    c = make_coordinator({})
    _proefstand(c, [{"naam": "X", "gereedheid": "klaar om mee te doen", "status": "betrouwbaar", "waarde": "ja"}])
    c.config = dict(c.config or {})
    c.config["appliance_notify_service"] = "notify.test"
    c.gestuurd = []
    c._dispatch_notification = lambda *a, **kw: c.gestuurd.append(kw.get("kind"))
    c._laatste_meetherinnering = None

    c._herinner_wat_meet(MAANDAG)
    c._herinner_wat_meet(MAANDAG)            # zelfde dag: niet nog eens
    c._herinner_wat_meet(DINSDAG)            # dinsdag: niet

    assert c.gestuurd == ["meet_stuurt_niet"]


def test_zonder_rijpe_kandidaten_geen_herinnering(make_coordinator, hass):
    c = make_coordinator({})
    _proefstand(c, [{"naam": "X", "gereedheid": "meet nog", "status": "indicatief", "waarde": None}])
    c.config = dict(c.config or {})
    c.config["appliance_notify_service"] = "notify.test"
    c.gestuurd = []
    c._dispatch_notification = lambda *a, **kw: c.gestuurd.append(kw.get("kind"))
    c._laatste_meetherinnering = None

    c._herinner_wat_meet(MAANDAG)

    assert c.gestuurd == []
