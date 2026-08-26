"""Een correctie per soort dag (v3.45.0).

De vlakke correctie werd in v3.33.0 ingehouden omdat het twee soorten
dagen zijn: heldere binnen 2%, wisselvallige 40 tot 55% ernaast.
Nagerekend won geen van de drie mogelijkheden - gemiddelde, mediaan of
niets - overtuigend.

Inhouden was het eerlijke antwoord maar geen oplossing. Op 23 augustus
stond de voorspelling nog altijd ongecorrigeerd, en de tweeling zat er
overdag 2,16 kWh naast tegen 0,90 's nachts. Diezelfde dag meldde de
integratie zelf: "Twee soorten dagen: 2 van de 5 binnen 10% en 2 meer
dan 25% ernaast."

De oplossing is niet een beter gemiddelde maar een correctie PER SOORT
DAG. Bij weinig bewolking hoort een correctie rond nul; bij veel
bewolking een forse.
"""
import pytest

import custom_components.energy_management_system.solar_forecast as sfm
from custom_components.energy_management_system.const import (
    CONF_SOLAR_ACTUAL_SENSOR,
    CONF_SOLAR_FORECAST_SENSOR,
    SOLAR_BIAS_MIN_PER_VAK,
)


def _tracker(hass, context=()):
    t = sfm.SolarForecastAccuracyTracker(
        hass,
        {
            CONF_SOLAR_FORECAST_SENSOR: "sensor.solcast",
            CONF_SOLAR_ACTUAL_SENSOR: "sensor.opbrengst",
        },
    )
    t.deviation_context = [
        {"datum": f"d{i}", "afwijking": a, "bewolking": b}
        for i, (a, b) in enumerate(context)
    ]
    return t


# De gemeten werkelijkheid: heldere dagen kloppen, bewolkte niet.
GEMETEN = [
    (-0.7, 12.0), (-2.2, 18.0), (1.3, 21.0), (-1.5, 9.0), (-2.7, 15.0),
    (-40.7, 78.0), (-48.9, 85.0), (-43.2, 72.0), (-51.4, 91.0),
]


def test_a_clear_day_gets_almost_no_correction(hass):
    """De vijf heldere dagen liggen binnen 2,7%; daar valt niets te

    corrigeren, en een vlakke -36,8% zou ze een derde te laag maken.
    """
    t = _tracker(hass, GEMETEN)

    assert t.bias_voor_bewolking(15.0) == pytest.approx(-1.5, abs=0.5)


def test_a_cloudy_day_gets_the_full_correction(hass):
    t = _tracker(hass, GEMETEN)

    assert t.bias_voor_bewolking(85.0) == pytest.approx(-45.9, abs=3.0)


def test_an_empty_bucket_gives_nothing(hass):
    """Halfbewolkte dagen zitten er in deze reeks niet bij; dan liever

    geen correctie dan die van een ander soort dag.
    """
    t = _tracker(hass, GEMETEN)

    assert t.bias_voor_bewolking(50.0) is None


def test_too_few_days_in_a_bucket_gives_nothing(hass):
    t = _tracker(hass, GEMETEN[:2] + GEMETEN[5:7])

    assert t.bias_voor_bewolking(15.0) is None
    assert len(GEMETEN[:2]) < SOLAR_BIAS_MIN_PER_VAK


def test_without_cloud_data_nothing_is_corrected(hass):
    t = _tracker(hass, GEMETEN)

    assert t.bias_voor_bewolking(None) is None


def test_the_buckets_are_visible(hass):
    """Op de kaart hoort te staan hoeveel dagen er per soort zijn -

    anders is niet te zien waarom er niet gecorrigeerd wordt.
    """
    vakken = _tracker(hass, GEMETEN).bewolkingsvakken()

    assert vakken["helder"]["dagen"] == 5
    assert vakken["helder"]["genoeg"] is True
    assert vakken["half"]["dagen"] == 0
    assert vakken["half"]["genoeg"] is False
    assert vakken["bewolkt"]["dagen"] == 4


def test_impossible_deviations_are_left_out(hass):
    """Dezelfde grens als de vlakke correctie; een sensor-rollover mag

    ook hier niet meetellen.
    """
    t = _tracker(hass, list(GEMETEN) + [(-9999.0, 15.0)])

    assert t.bias_voor_bewolking(15.0) == pytest.approx(-1.5, abs=0.5)


# --- de coordinator kiest de juiste ---------------------------------


def test_the_coordinator_prefers_the_bucket(make_coordinator, hass):
    """Per soort dag gaat vóór de vlakke correctie: die is aantoonbaar

    onbruikbaar bij een gespreide reeks, en dat is precies de situatie.
    """
    c = make_coordinator({})
    c.solar_tracker = _tracker(hass, GEMETEN)
    c._weather_cloud_cover_percent = lambda: 85.0

    assert c.zonbias_percent() == pytest.approx(-45.9, abs=3.0)


def test_the_coordinator_falls_back_to_the_flat_one(make_coordinator, hass):
    """Is er nog geen vakje gevuld, dan blijft het oude gedrag gelden -

    inclusief het inhouden bij twee soorten dagen.
    """
    c = make_coordinator({})
    c.solar_tracker = _tracker(hass, GEMETEN[:2])
    c.solar_tracker.deviation_history = [-20.0] * 7
    c._weather_cloud_cover_percent = lambda: 50.0

    assert c.zonbias_percent() == -20.0


def test_without_a_tracker_there_is_no_correction(make_coordinator, hass):
    c = make_coordinator({})
    c.solar_tracker = None

    assert c.zonbias_percent() is None


def test_the_cloud_reading_reaches_the_tracker(make_coordinator, hass):
    """Zonder deze doorgifte kan de avondvergelijking de bewolking niet

    bij de afwijking bewaren, en blijft de reeks onsplitsbaar.
    """
    c = make_coordinator({})
    c.solar_tracker = _tracker(hass)
    c._weather_cloud_cover_percent = lambda: 63.0

    c._deel_bewolking_met_de_zontracker()

    assert c.solar_tracker.laatste_bewolking_percent == 63.0
