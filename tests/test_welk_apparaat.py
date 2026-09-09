"""Welk apparaat is meer gaan gebruiken? (v4.4)

Gevraagd: "De integratie heeft bijna alle entiteiten binnen HA, dan kan
de integratie toch ook aangeven welk apparaat plots meer is gaan
gebruiken?"

Terecht. De sluipverbruikmelding zei "structureel ~40 W hoger" en liet
het zoeken aan de bewoner. Maar Home Assistant heeft de
vermogenssensoren, en de integratie draait elke minuut.

Elke nacht tussen 02:00 en 05:00 - het rustigste venster, en precies het
venster waarin de melding zelf rekent - wordt van ELKE vermogenssensor
in W de mediaan van die nacht bewaard. Na een paar nachten is de
vergelijking te maken: welke sensor staat nu hoger dan een week
geleden? Geen recorder, geen databasevraag; de rondes zijn er toch al.

Wat het NIET is: een sluitend bewijs. Een sensor die stijgt kan de
oorzaak zijn of een gevolg. Maar "sensor.vriezer_garage van 12 naar
48 W" is een startpunt, en "structureel 40 W hoger" is dat niet.
"""
from datetime import datetime, timedelta, timezone

import pytest

NACHT = datetime(2026, 9, 9, 3, 0, tzinfo=timezone.utc)


def _meet(c, hass, waarden, wanneer):
    for entity_id, watt in waarden.items():
        hass.states.set(entity_id, str(watt), {"unit_of_measurement": "W", "device_class": "power"})
    c._meet_nachtelijke_basislast(wanneer)


def test_alleen_vermogenssensoren_in_watt(make_coordinator, hass):
    c = make_coordinator({})
    c.nachtlast_per_apparaat = {}
    hass.states.set("sensor.temperatuur", "18.4", {"unit_of_measurement": "°C"})
    hass.states.set("sensor.energie", "12.5", {"unit_of_measurement": "kWh"})
    _meet(c, hass, {"sensor.vriezer": 40.0}, NACHT)

    nacht = c.nachtlast_per_apparaat["2026-09-09"]
    assert set(nacht) == {"sensor.vriezer"}


def test_de_mediaan_van_de_nacht_wint(make_coordinator, hass):
    """Een compressor die aanslaat mag de nacht niet bepalen."""
    c = make_coordinator({})
    c.nachtlast_per_apparaat = {}
    for i, w in enumerate([40, 42, 300, 41, 40]):
        _meet(c, hass, {"sensor.vriezer": w}, NACHT + timedelta(minutes=i))

    assert c.nachtlast_per_apparaat["2026-09-09"]["sensor.vriezer"] == 41.0


def test_buiten_het_venster_wordt_niet_gemeten(make_coordinator, hass):
    c = make_coordinator({})
    c.nachtlast_per_apparaat = {}
    _meet(c, hass, {"sensor.vriezer": 40.0}, NACHT.replace(hour=14))

    assert c.nachtlast_per_apparaat == {}


def _nachten(c, per_nacht):
    c.nachtlast_per_apparaat = {
        f"2026-09-{d:02d}": w for d, w in per_nacht.items()
    }


def test_de_grootste_stijger_wordt_aangewezen(make_coordinator, hass):
    c = make_coordinator({})
    _nachten(c, {
        **{d: {"sensor.vriezer": 12.0, "sensor.router": 8.0} for d in range(1, 8)},
        **{d: {"sensor.vriezer": 48.0, "sensor.router": 8.5} for d in range(8, 11)},
    })

    uit = c.welke_apparaten_stegen()

    assert uit["beschikbaar"] is True
    assert uit["stijgers"][0]["entiteit"] == "sensor.vriezer"
    assert uit["stijgers"][0]["toen_w"] == 12.0
    assert uit["stijgers"][0]["nu_w"] == 48.0
    assert uit["stijgers"][0]["stijging_w"] == 36.0
    assert all(r["entiteit"] != "sensor.router" for r in uit["stijgers"])


def test_te_weinig_nachten_geen_uitspraak(make_coordinator, hass):
    c = make_coordinator({})
    _nachten(c, {d: {"sensor.vriezer": 12.0} for d in range(1, 4)})

    uit = c.welke_apparaten_stegen()

    assert uit["beschikbaar"] is False
    assert "nachten" in uit["reden"]


def test_een_nieuwe_sensor_telt_als_stijger(make_coordinator, hass):
    """Een apparaat dat er vorige week nog niet was, is het duidelijkste
    geval."""
    c = make_coordinator({})
    _nachten(c, {
        **{d: {"sensor.router": 8.0} for d in range(1, 8)},
        **{d: {"sensor.router": 8.0, "sensor.nieuwe_lader": 25.0} for d in range(8, 11)},
    })

    stijgers = c.welke_apparaten_stegen()["stijgers"]

    assert stijgers[0]["entiteit"] == "sensor.nieuwe_lader"
    assert stijgers[0]["toen_w"] is None


def test_de_melding_noemt_het_apparaat(make_coordinator, hass):
    c = make_coordinator({})
    _nachten(c, {
        **{d: {"sensor.vriezer": 12.0} for d in range(1, 8)},
        **{d: {"sensor.vriezer": 48.0} for d in range(8, 11)},
    })

    regel = c._sluipverbruik_verdachten_zin()

    assert "sensor.vriezer" in regel
    assert "48" in regel and "12" in regel
