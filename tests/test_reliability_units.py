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


def test_the_dashboard_renders_the_unit():
    """De eenheid moet ook echt op het scherm komen - hem alleen
    opslaan lost niets op."""
    pad = WORTEL / "dashboards" / "energy_management_system_dashboard.yaml"
    data = yaml.safe_load(pad.read_text())

    kaarten = [
        k
        for v in data["views"]
        for sec in (v.get("sections") or [])
        for k in (sec.get("cards") or [])
        if "betrouwbaarheid_gegenereerde_data" in str(k.get("content", ""))
    ]

    assert kaarten
    assert "eenheid" in kaarten[0]["content"]
