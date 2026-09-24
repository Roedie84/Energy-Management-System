"""De dagbedragen gingen verloren bij de dagwissel (v5.15.2).

De eerste dagregel met het prijsoverzicht, uit de export van 24 september
06:58:

    {"datum": "2026-09-23", "opwek_kwh": 14.13, ... "co2_kg": 0.2087}

Geen van de zeven bedragen. De oorzaak staat in de volgorde van de ronde:

    ("prijsdag", ...)          <- zet de dagstand op de NIEUWE dag
    ("zelfvoorziening", ...)   <- sluit de OUDE dag af

Na middernacht wordt de dagstand dus eerst doorgezet, en pas daarna wordt
de oude dag weggeschreven - die bedragen zijn dan al weg. En de sensoren
van de leverancier springen om middernacht zelf naar nul, dus opnieuw
uitlezen helpt niet.

Niet opgelost door de volgorde om te draaien: dan hangt het geheel aan een
regelnummer, en dat breekt bij de volgende wijziging. In plaats daarvan
wordt de laatste stand van de vorige dag BEWAARD, zodat het afsluiten hem
nog kan gebruiken - ongeacht de volgorde.

De dag van 23 september blijft zonder bedragen; die zijn niet meer op te
halen. Het weekgemiddelde begint dus bij 24 september.
"""
from datetime import datetime, timedelta, timezone

import pytest

MIDDERNACHT = datetime(2026, 9, 24, 0, 0, 40, tzinfo=timezone.utc)
GISTEREN = datetime(2026, 9, 23, 23, 59, tzinfo=timezone.utc)


def _met_sensoren(c, hass, bedrag):
    c.config = dict(c.config or {})
    c.config["inkoop_eur_vandaag_sensor_entity"] = "sensor.afname"
    c.config["gas_m3_vandaag_sensor_entity"] = "sensor.gas"
    hass.states.set("sensor.afname", str(bedrag))
    hass.states.set("sensor.gas", "0.4")
    return c


def test_de_dagwissel_bewaart_de_stand_van_gisteren(make_coordinator, hass):
    c = _met_sensoren(make_coordinator({}), hass, 3.21)
    c.prijs_vandaag = {}
    c._werk_prijsdag_bij(GISTEREN)

    # middernacht: de sensoren springen naar nul en de dag wisselt
    _met_sensoren(c, hass, 0.0)
    c._werk_prijsdag_bij(MIDDERNACHT)

    assert c.prijs_vandaag["dag"] == "2026-09-24"
    assert c._prijsdag_velden(GISTEREN.date()) == {"inkoop_eur": 3.21, "gas_m3": 0.4}


def test_de_dagregel_krijgt_de_bedragen_ongeacht_de_volgorde(make_coordinator, hass):
    """Het gemeten geval: eerst de dagstand doorzetten, dan pas afsluiten."""
    c = _met_sensoren(make_coordinator({}), hass, 3.21)
    c.prijs_vandaag = {}
    c._werk_prijsdag_bij(GISTEREN)
    _met_sensoren(c, hass, 0.0)
    c._werk_prijsdag_bij(MIDDERNACHT)

    velden = c._prijsdag_velden(GISTEREN.date())

    assert velden.get("inkoop_eur") == 3.21


def test_de_stand_van_eergisteren_wordt_niet_gebruikt(make_coordinator, hass):
    """Maar één dag terug: anders krijgt een dag zonder meting de bedragen
    van een andere dag."""
    c = _met_sensoren(make_coordinator({}), hass, 3.21)
    c.prijs_vandaag = {}
    c._werk_prijsdag_bij(GISTEREN)
    _met_sensoren(c, hass, 0.0)
    c._werk_prijsdag_bij(MIDDERNACHT)

    assert c._prijsdag_velden(GISTEREN.date() - timedelta(days=1)) == {}


def test_binnen_dezelfde_dag_verandert_er_niets(make_coordinator, hass):
    c = _met_sensoren(make_coordinator({}), hass, 1.0)
    c.prijs_vandaag = {}
    c._werk_prijsdag_bij(GISTEREN)
    _met_sensoren(c, hass, 2.5)
    # een minuut NA 23:59 is de volgende dag - dat was een fout in de
    # eerste versie van deze toets, niet in de code
    c._werk_prijsdag_bij(GISTEREN - timedelta(minutes=1))

    assert c._prijsdag_velden(GISTEREN.date())["inkoop_eur"] == 2.5
