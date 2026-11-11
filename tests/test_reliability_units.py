"""Een getal zonder eenheid is niet te controleren (v1.82.0).

Gemeld met een screenshot van de betrouwbaarheidstabel:

    ✅ betrouwbaar PV-dagopwek — 13.21

Dertien komma twee wát? De tabel toonde kale getallen, en dat gold voor
de hele lijst: rendement, nachtverbruik, sensorgezondheid en
kostenverschil stonden er net zo bij.

Deze pagina is er juist om na te kunnen rekenen of een waarde klopt.
"""
from pathlib import Path

import yaml

WORTEL = Path(__file__).resolve().parent.parent


def _rijen(make_coordinator, hass):
    c = make_coordinator({})
    c.pv_production_today_kwh = 13.21
    # v1.83.0: ook de regels die pas verschijnen zodra er metingen zijn -
    # anders toetst de controle alleen het halve overzicht.
    c.sensor_cadence = {
        "sensor.p1": {"ticks": 40, "wijzigingen": 39}
    }
    c.weather_source_agreement = {
        "weather.knmi": [True] * 40 + [False] * 10,
        "weather.owm": [True] * 38 + [False] * 12,
    }
    return {r["naam"]: r for r in c.get_reliability_overview()}


def test_the_reported_row_names_its_unit(make_coordinator, hass):
    rijen = _rijen(make_coordinator, hass)

    assert rijen["PV-dagopwek"]["waarde"] == 13.21
    assert rijen["PV-dagopwek"]["eenheid"] == "kWh"


def test_every_row_with_a_value_names_a_unit(make_coordinator, hass):
    """Niet alleen die ene regel: elke waarde in de tabel hoort
    controleerbaar te zijn."""
    zonder = [
        naam
        for naam, r in _rijen(make_coordinator, hass).items()
        if r.get("waarde") is not None and not r.get("eenheid")
    ]

    assert not zonder, f"geen eenheid bij: {zonder}"


def test_the_units_come_from_a_known_set(make_coordinator, hass):
    """Vangt een typefout of een eenheid die niet bij de grootheid past.
    Een regel mag wel een eenheid dragen terwijl de waarde nog ontbreekt -
    dat is de normale toestand voor een leerroutine die nog verzamelt.
    """
    toegestaan = {"kWh", "kW", "%", "EUR", "W", "°C", None}

    onbekend = {
        r.get("eenheid")
        for r in _rijen(make_coordinator, hass).values()
        if r.get("eenheid") not in toegestaan
    }

    assert not onbekend, f"onbekende eenheid: {onbekend}"


# --- v1.83.0: en de rest van het dashboard ---------------------------


def test_every_numeric_sensor_declares_its_unit():
    """Ook buiten het dashboard: een sensor met een state_class hoort een
    eenheid te hebben, anders staat er in Home Assistant zelf een kaal
    getal."""
    import re

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "sensor.py").read_text()

    zonder = []
    for blok in bron.split("\nclass ")[1:]:
        kop = blok.split("\n")[0]
        if "SensorEntity" not in kop:
            continue
        numeriek = "_attr_state_class" in blok or "SensorDeviceClass" in blok
        if numeriek and "_attr_native_unit_of_measurement" not in blok:
            zonder.append(blok.split("(")[0].strip())

    assert not zonder, zonder
