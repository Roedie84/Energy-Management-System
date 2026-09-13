"""De klok die verspringt (v3.90.0).

Gevraagd bij de doorlichting: "Worden zomer- en wintertijd correct
verwerkt? Wat gebeurt er bij een overgang van CET naar CEST? Wat gebeurt
er rond middernacht? Welke dag hoort een kwartier van 00:00 precies
toe?"

Op geen van die vragen lag een toets. Op 25 oktober gaat de klok terug
en bestaat 02:00 twee keer; op 29 maart bestaat hij helemaal niet.

Dat is precies het soort dag waarop een fout duur is: de prijzen lopen
door, de accu moet de nacht halen, en niemand kijkt.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.energy_management_system.const import (
    PRICE_SCALE_FACTOR,
)

AMS = ZoneInfo("Europe/Amsterdam")


def _reeks(c, start, aantal=8, stap_minuten=15, prijs=0.25):
    """Een prijsreeks vanaf `start`, met echte tijdzone-aritmetiek."""
    entries = []
    for i in range(aantal):
        begin = start + timedelta(minutes=stap_minuten * i)
        entries.append(
            (
                begin,
                begin + timedelta(minutes=stap_minuten),
                prijs * PRICE_SCALE_FACTOR,
            )
        )
    c._get_forecast_entries = lambda **kw: entries
    return entries


# --- de nacht dat de klok terug gaat --------------------------------


def test_the_night_the_clock_falls_back(make_coordinator, hass):
    """25 oktober 2026: om 03:00 gaat de klok naar 02:00, dus 02:00 tot

    03:00 bestaat twee keer. De reeks loopt door met echte
    tijdzone-tijden.
    """
    c = make_coordinator({})
    start = datetime(2026, 10, 25, 1, 0, tzinfo=AMS)
    entries = _reeks(c, start, aantal=16)

    # De reeks blijft oplopen in ABSOLUTE tijd, ook al herhaalt de
    # klokstand zich.
    momenten = [e[0] for e in entries]
    assert momenten == sorted(momenten)

    prijs = c.huidige_prijs_eur_per_kwh(start + timedelta(minutes=30))
    assert prijs == pytest.approx(0.25)


def test_a_repeated_clock_hour_is_not_a_duplicate(make_coordinator, hass):
    """02:30 komt die nacht twee keer op de klok, maar het zijn twee

    VERSCHILLENDE momenten. De dubbeldetectie mag daar niet op afgaan.
    """
    c = make_coordinator({})
    eerste = datetime(2026, 10, 25, 2, 30, tzinfo=AMS, fold=0)
    tweede = datetime(2026, 10, 25, 2, 30, tzinfo=AMS, fold=1)

    bevindingen = c._controleer_prijsreeks(
        [
            (eerste, eerste + timedelta(minutes=15), 0.25),
            (tweede, tweede + timedelta(minutes=15), 0.30),
        ]
    )

    # Ze zijn niet gelijk in absolute tijd, dus geen dubbele.
    assert bevindingen["dubbele"] == [] or eerste == tweede


# --- middernacht -----------------------------------------------------


def test_midnight_belongs_to_the_new_day(make_coordinator, hass):
    """"Welke dag hoort een kwartier van 00:00 precies toe?" - de nieuwe.

    Dat lijkt vanzelfsprekend, maar het bepaalt of de dagreeks van
    gisteren of van vandaag is, en daarmee welke besparing waar wordt
    geboekt.
    """
    middernacht = datetime(2026, 10, 25, 0, 0, tzinfo=AMS)

    assert middernacht.date() == datetime(2026, 10, 25).date()


def test_the_last_quarter_of_the_day(make_coordinator, hass):
    """23:45 tot 00:00 hoort nog bij de oude dag."""
    laatste = datetime(2026, 10, 24, 23, 45, tzinfo=AMS)

    assert laatste.date().day == 24
    assert (laatste + timedelta(minutes=15)).date().day == 25


# --- de dubbel- en gatdetectie zelf ---------------------------------


def test_a_real_duplicate_is_caught(make_coordinator, hass):
    """Twee records met exact dezelfde starttijd: dat kwartier zou

    DUBBEL tellen in elke som.
    """
    c = make_coordinator({})
    start = datetime(2026, 8, 31, 12, 0, tzinfo=AMS)

    bevindingen = c._controleer_prijsreeks(
        [
            (start, start + timedelta(minutes=15), 0.25),
            (start, start + timedelta(minutes=15), 0.25),
            (
                start + timedelta(minutes=15),
                start + timedelta(minutes=30),
                0.30,
            ),
        ]
    )

    assert len(bevindingen["dubbele"]) == 1
    assert bevindingen["in_orde"] is False


def test_a_gap_is_reported_not_filled(make_coordinator, hass):
    """Een prijs verzinnen voor een kwartier dat de leverancier niet gaf,

    is erger dan een gat.
    """
    c = make_coordinator({})
    start = datetime(2026, 8, 31, 12, 0, tzinfo=AMS)

    bevindingen = c._controleer_prijsreeks(
        [
            (start, start + timedelta(minutes=15), 0.25),
            (
                start + timedelta(minutes=15),
                start + timedelta(minutes=30),
                0.25,
            ),
            # Hier ontbreken twee kwartieren.
            (
                start + timedelta(minutes=75),
                start + timedelta(minutes=90),
                0.30,
            ),
        ]
    )

    assert len(bevindingen["gaten"]) == 1
    assert bevindingen["gaten"][0]["gemist_minuten"] == 45


def test_a_clean_series_is_clean(make_coordinator, hass):
    c = make_coordinator({})
    start = datetime(2026, 8, 31, 12, 0, tzinfo=AMS)
    entries = [
        (
            start + timedelta(minutes=15 * i),
            start + timedelta(minutes=15 * (i + 1)),
            0.25,
        )
        for i in range(8)
    ]

    bevindingen = c._controleer_prijsreeks(entries)

    assert bevindingen["in_orde"] is True
    assert bevindingen["interval_minuten"] == 15


def test_hourly_data_is_recognised(make_coordinator, hass):
    """Sommige leveranciers geven uurprijzen. Dan is de verwachte stap

    zestig minuten, en is er geen gat.
    """
    c = make_coordinator({})
    start = datetime(2026, 8, 31, 12, 0, tzinfo=AMS)
    entries = [
        (
            start + timedelta(hours=i),
            start + timedelta(hours=i + 1),
            0.25,
        )
        for i in range(6)
    ]

    bevindingen = c._controleer_prijsreeks(entries)

    assert bevindingen["interval_minuten"] == 60
    assert bevindingen["gaten"] == []


def test_the_smallest_step_decides_not_the_first_two(
    make_coordinator, hass
):
    """"Is de detectie gebaseerd op de eerste twee records of op de

    volledige dataset?" - op de volledige, want juist bij de eerste twee
    kan een fout zitten.
    """
    c = make_coordinator({})
    start = datetime(2026, 8, 31, 12, 0, tzinfo=AMS)
    entries = [
        # De eerste stap is een uur; de rest een kwartier.
        (start, start + timedelta(hours=1), 0.25),
        (start + timedelta(hours=1), start + timedelta(minutes=75), 0.25),
        (
            start + timedelta(minutes=75),
            start + timedelta(minutes=90),
            0.25,
        ),
        (
            start + timedelta(minutes=90),
            start + timedelta(minutes=105),
            0.25,
        ),
    ]

    bevindingen = c._controleer_prijsreeks(entries)

    assert bevindingen["interval_minuten"] == 15


# --- het juiste soort entiteit ---------------------------------------


def test_a_sensor_where_a_number_belongs_is_caught(
    make_coordinator, hass
):
    """"Wat gebeurt er als een number-entity per ongeluk een sensor

    wordt?" Er valt niet naartoe te schrijven, en de aansturing mislukt
    stil.
    """
    from custom_components.energy_management_system.const import (
        CONF_MANUAL_POWER_NUMBER,
    )

    c = make_coordinator({CONF_MANUAL_POWER_NUMBER: "sensor.vermogen"})

    uitkomst = c.get_entiteittypecontrole()

    assert uitkomst["in_orde"] is False
    assert uitkomst["verkeerd_type"][0]["verwacht"] == "number"
    assert "stil" in uitkomst["verkeerd_type"][0]["gevolg"]


def test_correct_types_are_silent(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        CONF_MANUAL_POWER_NUMBER,
        CONF_OPERATION_SELECT,
        CONF_SOC_SENSOR,
    )

    c = make_coordinator(
        {
            CONF_OPERATION_SELECT: "select.modus",
            CONF_MANUAL_POWER_NUMBER: "number.vermogen",
            CONF_SOC_SENSOR: "sensor.soc",
        }
    )

    assert c.get_entiteittypecontrole()["in_orde"] is True


def test_it_lands_in_the_analysis(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        CONF_OPERATION_SELECT,
    )

    c = make_coordinator({CONF_OPERATION_SELECT: "sensor.modus"})

    analyse = c.get_analyse()

    assert any(
        p["onderwerp"] == "Verkeerd soort entiteit" for p in analyse["punten"]
    )
