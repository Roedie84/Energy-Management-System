"""Drie kleine dingen uit de lijst (v3.99.22).

Gevraagd: "Verder nog zaken welke verbeterd dienen te worden, heb nog
wel even tijd."
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 8, 2, 0, tzinfo=timezone.utc)


# --- 1. "verkopen geblokkeerd" een keer per episode --------------------
#
# 8 september: zes keer op een dag, waarvan drie 's nachts. De ontdub-
# belsleutel was de redentekst, en daar staan de getallen in: "2,35 kWh
# nodig en 2,51 beschikbaar". Elke ronde nieuwe getallen, dus elke keer
# dat de demping het toeliet een "nieuwe" melding. Een blokkering is een
# episode: een melding als hij begint, en pas weer een als hij na een
# vrije periode opnieuw begint.


def _plan(c, hass, mag_verkopen, reden):
    c.config = dict(c.config or {})
    c.config["appliance_notify_service"] = "notify.test"
    c.gestuurd = []
    c._dispatch_notification = lambda *a, **kw: c.gestuurd.append(kw.get("kind") or (a[4] if len(a) > 4 else None))
    c.last_sell_check = {"mag_verkopen": mag_verkopen, "reden": reden}
    c.get_quarter_plan_summary = lambda now=None: {"beschikbaar": True, "tekort_kwartieren": 0, "tekort_perioden": []}
    c.last_solar_defer_plan = {}
    c._meld_planningswijzigingen(NU)
    return c.gestuurd.count("plan_verkoop_geblokkeerd")


def test_een_blokkering_meldt_een_keer(make_coordinator, hass):
    c = make_coordinator({})
    n1 = _plan(c, hass, False, "De woning heeft 2.35 kWh nodig en er is 2.51")
    n2 = _plan(c, hass, False, "De woning heeft 1.82 kWh nodig en er is 1.81")
    assert (n1, n2) == (1, 0)


def test_na_vrijgave_opnieuw(make_coordinator, hass):
    c = make_coordinator({})
    _plan(c, hass, False, "a")
    _plan(c, hass, True, "")
    assert _plan(c, hass, False, "b") == 1


# --- 2. de lange-reservegeschiedenis in de export -----------------------
#
# Om 15:18 was niet meer na te kijken hoe groot het verschil tussen de
# korte en de lange reserve was: de export toonde de laatste dertig
# regels, een half uur. De coordinator bewaart er driehonderd. De export
# toont nu per uur de regel met het grootste verschil, over de hele reeks.


def test_de_export_toont_per_uur_het_grootste_verschil(make_coordinator, hass):
    c = make_coordinator({})
    c.lange_reserve_history = [
        {"moment": (NU + timedelta(minutes=m)).isoformat(), "reserve_kort_kwh": 3.0,
         "reserve_lang_kwh": 3.0 + (2.0 if m == 75 else 0.1), "extra_kwh": 2.0 if m == 75 else 0.1}
        for m in range(0, 180, 3)
    ]

    uit = c.lange_reserve_per_uur()

    assert len(uit) == 3
    assert uit[1]["extra_kwh"] == 2.0
    assert uit[1]["uur"].endswith("03:00")


# --- 3. "bestaat niet" sinds wanneer ----------------------------------
#
# Een cloudstoring laat een entiteit verdwijnen; een hernoeming ook. De
# configuratiecontrole zei bij beide "bestaat niet (meer)". Het verschil
# zit in de duur: een storing is uren, een hernoeming is voorgoed.


def test_bestaat_niet_krijgt_een_sinds(make_coordinator, hass):
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["dishwasher_ready_sensor_entity"] = "binary_sensor.weg"
    c._bestaat_niet_sinds = {}

    from custom_components.energy_management_system import coordinator as mod

    mod.dt_util.now = lambda: NU
    r1 = [r for r in c.get_configuratiecontrole()["entiteiten"] if r["entiteit"] == "binary_sensor.weg"][0]
    mod.dt_util.now = lambda: NU + timedelta(hours=30)
    r2 = [r for r in c.get_configuratiecontrole()["entiteiten"] if r["entiteit"] == "binary_sensor.weg"][0]

    assert r1["bestaat_niet_sinds"] == NU.isoformat()
    assert "uur" in r1["uitleg"] or "storing" in r1["uitleg"]
    assert r2["bestaat_niet_uren"] == pytest.approx(30, abs=0.1)
    assert "hernoem" in r2["uitleg"].lower()
