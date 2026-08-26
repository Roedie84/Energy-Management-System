"""Elke sensor overleeft een verse coordinator (v3.37.0).

Gevraagd naar aanleiding van de dekkingsmeting: `sensor.py` had de
grootste hoeveelheid ongeziene regels, 398 stuks over 60 klassen waarvan
er 33 in geen enkele test voorkwamen.

Deze toets komt uit een echte storing. In een eerdere versie was het hele
attributenblok van de GACS-sensor één enkele dict-uitdrukking: viel er
één waarde weg, dan wierp de hele uitdrukking een fout en bleven ALLE
tegels leeg. Niet één tegel - alle.

Het gevaarlijkste moment daarvoor is de eerste ronde na een herstart:
alles staat op zijn beginwaarde, niets is berekend, en de sensoren worden
wél al uitgelezen. Home Assistant vangt zo'n fout af en toont de entiteit
als niet-beschikbaar, dus je ziet het niet in het logboek van je
dashboard - je ziet alleen een lege kaart.

Getoetst op een échte, vers gebouwde coordinator en niet op een stub:
een stub die alles op None zet meldt zesendertig problemen die geen van
alle bestaan, want de coordinator zet zijn lijsten en woordenboeken zelf
al leeg klaar.
"""
import inspect

import pytest

import custom_components.energy_management_system.sensor as S

KLASSEN = sorted(
    (k for n, k in inspect.getmembers(S, inspect.isclass)
     if k.__module__ == S.__name__),
    key=lambda k: k.__name__,
)


def _bouw(klasse, coordinator):
    """Bouwt een sensor, of geeft None als hij extra argumenten vraagt."""
    try:
        return klasse(coordinator, entry_id="entry1")
    except TypeError:
        return None


def test_there_are_sensors_to_check():
    """Vangt het geval dat deze toets stilletjes niets meer doorloopt."""
    assert len(KLASSEN) > 40


@pytest.mark.parametrize("klasse", KLASSEN, ids=lambda k: k.__name__)
def test_a_fresh_coordinator_never_makes_a_sensor_throw(
    klasse, make_coordinator, hass
):
    """De eerste ronde na een herstart: niets berekend, alles op zijn

    beginwaarde, en de sensoren worden al uitgelezen.
    """
    sensor = _bouw(klasse, make_coordinator({}))
    if sensor is None:
        pytest.skip("basisklasse, wordt met eigen argumenten gebouwd")

    for veld in ("native_value", "extra_state_attributes", "available", "icon"):
        getattr(sensor, veld, None)


@pytest.mark.parametrize("klasse", KLASSEN, ids=lambda k: k.__name__)
def test_the_attributes_are_a_mapping_or_nothing(
    klasse, make_coordinator, hass
):
    """Home Assistant verwacht een woordenboek. Iets anders levert een

    entiteit op die niet laadt, zonder duidelijke fout.
    """
    sensor = _bouw(klasse, make_coordinator({}))
    if sensor is None:
        pytest.skip("basisklasse")

    kenmerken = getattr(sensor, "extra_state_attributes", None)

    assert kenmerken is None or isinstance(kenmerken, dict)


def test_no_two_sensors_share_a_unique_id(make_coordinator, hass):
    """Twee entiteiten met hetzelfde id betekent dat er één verdwijnt -

    en welke van de twee is niet te voorspellen.
    """
    c = make_coordinator({})
    ids = []
    for klasse in KLASSEN:
        sensor = _bouw(klasse, c)
        if sensor is None:
            continue
        eigen = getattr(sensor, "_attr_unique_id", None)
        if eigen:
            ids.append(eigen)

    dubbel = {i for i in ids if ids.count(i) > 1}

    assert not dubbel, f"dezelfde unieke id: {sorted(dubbel)}"


def test_every_sensor_belongs_to_the_device(make_coordinator, hass):
    """Zonder apparaat komt een entiteit los in de lijst te staan, buiten

    het EMS-apparaat om.
    """
    c = make_coordinator({})
    los = []
    for klasse in KLASSEN:
        sensor = _bouw(klasse, c)
        if sensor is None:
            continue
        if getattr(sensor, "_attr_unique_id", None) and not getattr(
            sensor, "_attr_device_info", None
        ):
            los.append(klasse.__name__)

    assert not los, f"geen apparaat: {los}"
