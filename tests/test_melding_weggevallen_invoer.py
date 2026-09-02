"""Een uitgeschakelde buitensensor gaf geen melding (v3.99.6).

Gemeld: "De Hue sensor had ik per ongeluk uitgeschakeld" - en daarna:
"Maar dan had ik toch een melding moeten hebben?"

Terecht. De melding "Sensor niet uitleesbaar" (v1.6.6) bewaakte precies
VIER sensoren: beschikbare energie, accuvermogen, netvermogen en
PV-vermogen. Alles daarbuiten - de buitentemperatuur voor de
accukoeling, de laadstand, de prijssensor, de weerbronnen, Solcast - viel
weg zonder een woord. De configuratiecontrole zag het wel (twee regels
"geen_waarde" in de export), maar die controle voedt alleen de export.

Nu bewaakt de melding elke geconfigureerde entiteit, met dezelfde
bevestigingstijd van vijftien minuten - een gemiste uitlezing is geen
storing - en met uitzondering van de apparaatinstellingen: een
wasmachine die uit staat, slaapt (v3.95.0).
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc)
LATER = NU + timedelta(minutes=20)


def _opzet(c, hass, extra_config, staten):
    c.config = dict(c.config or {})
    c.config.update(extra_config)
    for e, s in staten.items():
        hass.states.set(e, s)
    c._started_at = NU - timedelta(hours=5)
    c.gestuurd = []
    c._dispatch_notification = lambda **kw: c.gestuurd.append(kw)
    c._verstuur_meldingen_indien_nodig = getattr(c, "_verstuur_meldingen_indien_nodig", None)


def _weggevallen(c, now):
    return c.weggevallen_invoer(now)


def test_de_buitensensor_wordt_nu_gezien(make_coordinator, hass):
    """Het geval van 2 september."""
    c = make_coordinator({})
    _opzet(
        c, hass,
        {"battery_cooling_outdoor_sensor_entity": "sensor.hue_buiten"},
        {"sensor.hue_buiten": "unavailable"},
    )

    c._volg_beschikbaarheid_van_de_invoer(NU)
    c._volg_beschikbaarheid_van_de_invoer(LATER)

    weg = _weggevallen(c, LATER)
    assert [r["entiteit"] for r in weg] == ["sensor.hue_buiten"]
    assert "koeling" in weg[0]["gebruikt_voor"].lower() or "buiten" in weg[0]["gebruikt_voor"].lower()


def test_een_gemiste_uitlezing_is_geen_storing(make_coordinator, hass):
    c = make_coordinator({})
    _opzet(
        c, hass,
        {"battery_cooling_outdoor_sensor_entity": "sensor.hue_buiten"},
        {"sensor.hue_buiten": "unavailable"},
    )

    c._volg_beschikbaarheid_van_de_invoer(NU)

    assert _weggevallen(c, NU + timedelta(minutes=5)) == []


def test_een_slapend_apparaat_telt_niet(make_coordinator, hass):
    c = make_coordinator({})
    _opzet(
        c, hass,
        {"washing_machine_end_at_entity": "sensor.wasmachine_eind"},
        {"sensor.wasmachine_eind": "unavailable"},
    )

    c._volg_beschikbaarheid_van_de_invoer(NU)
    c._volg_beschikbaarheid_van_de_invoer(LATER)

    assert _weggevallen(c, LATER) == []


def test_een_entiteit_die_niet_bestaat_telt_wel(make_coordinator, hass):
    """Een hernoeming is erger dan unavailable: die komt niet terug."""
    c = make_coordinator({})
    _opzet(c, hass, {"price_sensor_entity": "sensor.prijs_oud"}, {})

    c._volg_beschikbaarheid_van_de_invoer(NU)
    c._volg_beschikbaarheid_van_de_invoer(LATER)

    weg = _weggevallen(c, LATER)
    assert [r["entiteit"] for r in weg] == ["sensor.prijs_oud"]


def test_terug_is_terug(make_coordinator, hass):
    c = make_coordinator({})
    _opzet(
        c, hass,
        {"battery_cooling_outdoor_sensor_entity": "sensor.hue_buiten"},
        {"sensor.hue_buiten": "unavailable"},
    )
    c._volg_beschikbaarheid_van_de_invoer(NU)
    c._volg_beschikbaarheid_van_de_invoer(LATER)
    hass.states.set("sensor.hue_buiten", "18.4")
    c._volg_beschikbaarheid_van_de_invoer(LATER + timedelta(minutes=1))

    assert _weggevallen(c, LATER + timedelta(minutes=1)) == []
