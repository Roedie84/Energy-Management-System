"""Rekentijd per attribuut van de zelfbeoordelingssensor (v4.9.7).

Gemeld uit het logboek, één keer om 07:46:

    Updating state for sensor...gacs_zelfbeoordeling took 0.425 seconds

Dat was 2,624 seconden voor v3.99.20, toen het PV-model nog in de event
loop trainde. De grote oorzaak is dus weg, en wat er nu overblijft is
0,4 seconde bij het opstarten - net boven de grens waarbij Home
Assistant waarschuwt, en één keer.

Daar wil ik niet naar gokken. Deze sensor bouwt veertig attributen op,
elk met een eigen aanroep; welke daarvan de tijd kost, is te meten in
plaats van te vermoeden. Net als bij de proefstand in v4.2.
"""
import pytest


def test_de_rekentijd_staat_bij_de_attributen(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        GacsAssessmentSensor,
    )

    s = GacsAssessmentSensor(make_coordinator({}), "entry1")

    attributen = s.extra_state_attributes
    rekentijd = attributen["rekentijd_ms"]

    assert isinstance(rekentijd["totaal"], float)
    assert rekentijd["traagste"]
    assert len(rekentijd["traagste"]) <= 10
    # de traagste staat vooraan
    tijden = list(rekentijd["traagste"].values())
    assert tijden == sorted(tijden, reverse=True)


def test_een_falend_attribuut_krijgt_geen_tijd(make_coordinator, hass):
    """Wat omvalt hoort niet als 0,0 ms in de lijst te staan."""
    from custom_components.energy_management_system.sensor import (
        GacsAssessmentSensor,
    )

    c = make_coordinator({})
    c.get_topic_summaries = lambda: (_ for _ in ()).throw(ValueError("stuk"))
    s = GacsAssessmentSensor(c, "entry1")

    attributen = s.extra_state_attributes

    assert "fout" in attributen["samenvattingen"]
    assert "samenvattingen" not in attributen["rekentijd_ms"]["traagste"]
