"""Een verband dat sterk oogt maar het niet is (v3.39.0).

Gevraagd: "Hoe zit het met correlaties welke gemaakt worden door de
integratie?"

Uitgezocht op de export van 20 augustus. De temperatuur-verbruikreeks
stond op zeven metingen:

    21,3 °C -> 239 W        helling  +6,3 W per graad
    19,2 °C -> 212 W        correlatie r = 0,90
    17,6 °C -> 207 W        r² = 0,81
    17,0 °C -> 209 W
    17,0 °C -> 197 W        bereik 15,3 tot 21,3 °C
    15,9 °C -> 205 W
    15,3 °C -> 197 W

Een correlatie van 0,90 ziet er overtuigend uit. Leg hem naast het
dagverbruik en het valt om: 12 en 13 augustus 12,3 en 12,6 kWh met
bewoners thuis, vanaf 15 augustus 4,6 tot 7,1 kWh met een leeg huis. De
warmste meting is de laatste bewoonde nacht. Het model zag "warmer is
meer verbruik" terwijl de oorzaak "thuis is meer verbruik" was.

En structureler: dit model is gebouwd na de analyse van 11 januari, de
koudste nacht van het jaar, waar het verband NEGATIEF is. Een positieve
helling doorgetrokken naar 0 °C gaf hier 105 W waar er 400 hoort te
staan.

Drie wachters dus - en één ding dat bewust NIET geweigerd wordt.
"""
import pytest

from custom_components.energy_management_system.const import (
    TEMP_CONSUMPTION_MIN_RANGE_C,
)

GEMETEN = [
    {"temp_c": 21.3, "kw": 0.239, "uren": 6.5},
    {"temp_c": 15.9, "kw": 0.205, "uren": 5.3},
    {"temp_c": 17.6, "kw": 0.207, "uren": 3.5},
    {"temp_c": 17.0, "kw": 0.197, "uren": 2.5},
    {"temp_c": 15.3, "kw": 0.197, "uren": 6.2},
    {"temp_c": 17.0, "kw": 0.209, "uren": 8.0},
    {"temp_c": 19.2, "kw": 0.212, "uren": 2.2},
]

WINTER = [
    {"temp_c": 10.0, "kw": 0.250, "uren": 8.0},
    {"temp_c": 5.0, "kw": 0.375, "uren": 8.0},
    {"temp_c": 0.0, "kw": 0.500, "uren": 8.0},
    {"temp_c": -5.0, "kw": 0.625, "uren": 8.0},
    {"temp_c": 12.0, "kw": 0.210, "uren": 8.0},
]


# --- de vakantiereeks wordt geweigerd --------------------------------


def test_the_measured_summer_series_predicts_nothing(make_coordinator, hass):
    """Zes graden bereik is te smal, hoe mooi de correlatie ook is."""
    c = make_coordinator({})
    c.temp_consumption_history = list(GEMETEN)

    assert c._predict_temp_consumption_kw(0.0) is None
    assert c._predict_temp_consumption_kw(18.0) is None


def test_it_says_the_range_is_too_narrow(make_coordinator, hass):
    """Zonder uitleg lijkt het alsof er te weinig metingen zijn, terwijl

    de reeks vol staat.
    """
    c = make_coordinator({})
    c.temp_consumption_history = list(GEMETEN)

    oordeel = c.get_temp_consumption_bruikbaarheid(0.0)

    assert oordeel["oordeel"] == "bereik_te_smal"
    assert oordeel["spreiding_c"] == 6.0
    assert "smal" in oordeel["reden"]


def test_the_measured_slope_is_reported_anyway(make_coordinator, hass):
    """Het getal blijft zichtbaar; alleen wordt er niet op voorspeld."""
    c = make_coordinator({})
    c.temp_consumption_history = list(GEMETEN)

    oordeel = c.get_temp_consumption_bruikbaarheid()

    assert oordeel["helling_w_per_graad"] == pytest.approx(6.3, abs=0.5)


# --- het teken -------------------------------------------------------


def test_a_positive_slope_is_never_used_for_a_cold_night(
    make_coordinator, hass
):
    """Een zomerverband - koeling, koelkast - kan best kloppen, maar het

    mag niet onder het gemeten bereik worden losgelaten.
    """
    c = make_coordinator({})
    c.temp_consumption_history = [
        {"temp_c": 12.0, "kw": 0.20, "uren": 8.0},
        {"temp_c": 18.0, "kw": 0.24, "uren": 8.0},
        {"temp_c": 24.0, "kw": 0.28, "uren": 8.0},
        {"temp_c": 28.0, "kw": 0.31, "uren": 8.0},
    ]

    assert c._predict_temp_consumption_kw(0.0) is None
    # Binnen het bereik mag het wel: daar is het gemeten.
    assert c._predict_temp_consumption_kw(20.0) is not None


def test_the_summer_relationship_is_named(make_coordinator, hass):
    c = make_coordinator({})
    c.temp_consumption_history = [
        {"temp_c": 12.0, "kw": 0.20, "uren": 8.0},
        {"temp_c": 18.0, "kw": 0.24, "uren": 8.0},
        {"temp_c": 24.0, "kw": 0.28, "uren": 8.0},
        {"temp_c": 28.0, "kw": 0.31, "uren": 8.0},
    ]

    oordeel = c.get_temp_consumption_bruikbaarheid(0.0)

    assert oordeel["oordeel"] == "zomerverband"
    assert "omgekeerd" in oordeel["reden"]


# --- en wat er WEL mag -----------------------------------------------


def test_a_real_winter_series_still_predicts_the_coldest_night(
    make_coordinator, hass
):
    """Bewuste keuze: buiten het gemeten bereik voorspellen wordt NIET

    geweigerd. Dit model bestaat juist voor de koudste nacht van het
    jaar, en die ligt per definitie buiten wat er tot dan toe gemeten
    is. Weigeren zou het uitschakelen op precies het moment waarvoor het
    gebouwd is.
    """
    c = make_coordinator({})
    c.temp_consumption_history = list(WINTER)

    koud = c._predict_temp_consumption_kw(-10.0)
    zacht = c._predict_temp_consumption_kw(8.0)

    assert koud is not None
    assert koud > zacht


def test_extrapolation_is_marked_as_such(make_coordinator, hass):
    """Doorgetrokken is niet gemeten, en dat hoort erbij te staan."""
    c = make_coordinator({})
    c.temp_consumption_history = list(WINTER)

    ver = c.get_temp_consumption_bruikbaarheid(-15.0)
    binnen = c.get_temp_consumption_bruikbaarheid(5.0)

    assert ver["geextrapoleerd"] is True
    assert "buiten het gemeten bereik" in ver["reden"]
    assert "geextrapoleerd" not in binnen


def test_a_good_series_is_simply_usable(make_coordinator, hass):
    c = make_coordinator({})
    c.temp_consumption_history = list(WINTER)

    assert c.get_temp_consumption_bruikbaarheid(0.0)["oordeel"] == "bruikbaar"


def test_too_few_measurements_is_still_the_first_answer(
    make_coordinator, hass
):
    c = make_coordinator({})
    c.temp_consumption_history = [{"temp_c": 5.0, "kw": 0.3, "uren": 8.0}]

    oordeel = c.get_temp_consumption_bruikbaarheid(0.0)

    assert oordeel["oordeel"] == "onvoldoende_metingen"


def test_the_range_threshold_is_wider_than_the_measured_series():
    """De aanleiding, als getal: de gemeten reeks besloeg zes graden."""
    assert TEMP_CONSUMPTION_MIN_RANGE_C > 6.0
