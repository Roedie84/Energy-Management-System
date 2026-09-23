"""Gemiddelde in- en verkoopprijzen per periode (v5.15).

Gevraagd: *"houdt de integratie ook de gemiddelde prijzen per uur, dag,
week, maand, jaar bij voor in- en verkoop van electra en inkoop van gas?"*
en *"ik wil incl en excl BTW"*.

Wat er live al bleek te staan, van de leverancier zelf, incl EN excl btw:

    Afname / Teruglevering:  vandaag · deze maand · dit jaar   (euro en
                             gemiddelde prijs per kWh)
    Gas:                     alleen vandaag (m3 en euro)

Wat ontbrak: per UUR, per WEEK, het contractjaar, en gas over langere
perioden. Die komen nu uit de eigen dagreeks: de dagbedragen worden
vastgelegd zoals opwek en verbruik dat al werden, en tellen daarna vanzelf
mee in week, maand, jaar en contractjaar.

Waarom incl en excl allebei worden gelezen en niet omgerekend: het verschil
is geen vast percentage maar een vast BEDRAG per kWh - energiebelasting
plus btw. Gemeten op 23 september: 0,3494 tegen 0,2386 euro per kWh, een
verschil van 0,1108. Bij een lage prijs valt er dus verhoudingsgewijs veel
meer weg, en 0,3494 gedeeld door 1,21 zou 0,2888 geven - fout.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import slimme_bronnen as sb

NU = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


# --- de rekenlogica ------------------------------------------------------


def test_de_gemiddelde_prijzen_per_periode():
    perioden = {
        "week": {
            "dagen": 7, "van": "2026-09-16",
            "import_kwh": 28.49, "export_kwh": 40.0, "gas_m3": 2.0,
            "inkoop_eur": 9.96, "inkoop_eur_excl": 6.80,
            "teruglever_eur": 12.72, "teruglever_eur_excl": 8.30,
            "gas_eur": 3.34, "gas_eur_excl": 1.90,
        }
    }

    uit = sb.prijzen_per_periode(perioden)["week"]

    assert uit["inkoop_eur_per_kwh"] == pytest.approx(0.3496, abs=0.001)
    assert uit["inkoop_eur_per_kwh_excl"] == pytest.approx(0.2387, abs=0.001)
    assert uit["teruglever_eur_per_kwh"] == pytest.approx(0.318, abs=0.001)
    assert uit["gas_eur_per_m3"] == pytest.approx(1.67, abs=0.01)


def test_zonder_hoeveelheid_geen_prijs():
    """Delen door nul geeft geen prijs, maar ook geen fout."""
    uit = sb.prijzen_per_periode({"week": {"inkoop_eur": 5.0, "import_kwh": 0}})

    assert uit["week"]["inkoop_eur_per_kwh"] is None


def test_de_prijs_per_uur_middelt_de_kwartieren():
    kwartieren = [
        (NU.replace(hour=10, minute=m), p)
        for m, p in ((0, 0.40), (15, 0.30), (30, 0.20), (45, 0.10))
    ]

    uit = sb.prijzen_per_uur(kwartieren, belastingdeel_eur=0.1108)

    assert uit[10]["eur_per_kwh"] == pytest.approx(0.25)
    assert uit[10]["eur_per_kwh_excl"] == pytest.approx(0.1392, abs=0.001)
    assert uit[10]["kwartieren"] == 4


def test_zonder_gemeten_belastingdeel_blijft_excl_leeg():
    """Geen percentage raden: het verschil is een vast bedrag per kWh, en
    zonder meting blijft de kolom leeg."""
    uit = sb.prijzen_per_uur([(NU.replace(hour=9), 0.30)], belastingdeel_eur=None)

    assert uit[9]["eur_per_kwh_excl"] is None


# --- de koppeling --------------------------------------------------------


def _met_sensoren(c, hass):
    c.config = dict(c.config or {})
    waarden = {
        "inkoop_eur_vandaag_sensor_entity": ("sensor.afname", "0.0244611"),
        "inkoop_eur_vandaag_excl_sensor_entity": ("sensor.afname_excl", "0.0167018"),
        "teruglever_eur_vandaag_sensor_entity": ("sensor.terug", "0.1342089"),
        "teruglever_eur_vandaag_excl_sensor_entity": ("sensor.terug_excl", "0.0914215"),
        "gas_m3_vandaag_sensor_entity": ("sensor.gas_m3", "0.05"),
        "gas_eur_vandaag_sensor_entity": ("sensor.gas_eur", "0.08"),
        "gas_eur_vandaag_excl_sensor_entity": ("sensor.gas_eur_excl", "0.0453569"),
    }
    for sleutel, (entity, waarde) in waarden.items():
        c.config[sleutel] = entity
        hass.states.set(entity, waarde)
    return c


def test_de_dagbedragen_worden_bijgehouden(make_coordinator, hass):
    c = _met_sensoren(make_coordinator({}), hass)
    c.prijs_vandaag = {}

    c._werk_prijsdag_bij(NU)

    assert c.prijs_vandaag["dag"] == "2026-09-23"
    assert c.prijs_vandaag["inkoop_eur"] == 0.0245
    assert c.prijs_vandaag["gas_m3"] == 0.05


def test_een_nieuwe_dag_begint_opnieuw(make_coordinator, hass):
    c = _met_sensoren(make_coordinator({}), hass)
    c.prijs_vandaag = {"dag": "2026-09-22", "inkoop_eur": 9.99}

    c._werk_prijsdag_bij(NU)

    assert c.prijs_vandaag["dag"] == "2026-09-23"
    assert c.prijs_vandaag["inkoop_eur"] == 0.0245


def test_de_dagregel_krijgt_de_bedragen_mee(make_coordinator, hass):
    """Alleen als de dagstand ook echt over die dag gaat - de sensoren van
    de leverancier springen 's nachts terug naar nul."""
    c = make_coordinator({})
    c.prijs_vandaag = {"dag": "2026-09-23", "inkoop_eur": 1.23, "gas_m3": 0.4}

    assert c._prijsdag_velden(NU.date()) == {"inkoop_eur": 1.23, "gas_m3": 0.4}
    assert c._prijsdag_velden(NU.date() - timedelta(days=1)) == {}


def test_de_nieuwe_grootheden_tellen_mee_per_periode(make_coordinator, hass):
    velden = {s for s, _n, _e in type(make_coordinator({})).PERIODE_GROOTHEDEN}

    for veld in (
        "inkoop_eur", "inkoop_eur_excl", "teruglever_eur",
        "teruglever_eur_excl", "gas_m3", "gas_eur", "gas_eur_excl",
    ):
        assert veld in velden, veld


def test_het_overzicht_staat_in_de_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    assert "get_prijsoverzicht" in (
        Path(pkg.__file__).parent / "diagnostics.py"
    ).read_text()
