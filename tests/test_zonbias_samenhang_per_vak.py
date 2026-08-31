"""Een bewolkingsvak dat twee soorten dagen bevat (v3.92.2).

Openstaand punt 3 uit de overdracht: "De zonvoorspelling zat er twee
dagen op rij 44% naast." Gemeten in de export van 31 augustus:

    datum    bewolking   afwijking   vak
    24-08         0,0 %      -1,9 %  helder
    25-08        51,7 %     -13,7 %  half
    26-08        19,9 %      -6,6 %  helder
    27-08       100,0 %     -10,2 %  bewolkt
    28-08        37,4 %     -41,2 %  half
    29-08        74,9 %      +0,9 %  bewolkt
    30-08        84,8 %     -43,9 %  bewolkt

De correlatie tussen bewolking en afwijking is -0,23: vrijwel afwezig.
De beste dag (29-08, +0,9%) en de slechtste (30-08, -43,9%) zitten in
HETZELFDE vak, tien procentpunt bewolking uit elkaar.

De overdracht ging ervan uit dat de vakcorrectie al actief was. Dat is
niet zo: alle drie de vakken staan op `genoeg: false`, want de drempel
is vier dagen. De fout zit in wat er gebeurt zodra ze wél vollopen.

`bias_voor_bewolking` kijkt alleen naar het AANTAL dagen in een vak, niet
of die dagen bij elkaar horen. Het vak "bewolkt" spant nu al 44,8
procentpunt; bij een vierde dag gaat hij corrigeren met de mediaan van
een verzameling die geen middelpunt heeft.

De vlakke correctie heeft die toets sinds v3.33.0 wél
(`bias_ingehouden_reden`: "Twee soorten dagen"). Dezelfde regel hoort per
vak te gelden - het argument is er niet anders, alleen de verzameling.
"""
import pytest

import custom_components.energy_management_system.solar_forecast as sfm
from custom_components.energy_management_system.const import (
    CONF_SOLAR_ACTUAL_SENSOR,
    CONF_SOLAR_FORECAST_SENSOR,
    SOLAR_BIAS_MIN_PER_VAK,
)


@pytest.fixture
def tracker(hass):
    return sfm.SolarForecastAccuracyTracker(
        hass,
        {
            CONF_SOLAR_FORECAST_SENSOR: "sensor.solcast",
            CONF_SOLAR_ACTUAL_SENSOR: "sensor.opbrengst",
        },
    )


def _vul(tracker, rijen):
    """rijen: (bewolking_percent, afwijking_procent)"""
    tracker.deviation_context = [
        {"datum": f"2026-08-{20 + i:02d}", "bewolking": b, "afwijking": a}
        for i, (b, a) in enumerate(rijen)
    ]


# --- het geval van 30 augustus ----------------------------------------


def test_een_vak_met_twee_soorten_dagen_corrigeert_niet(tracker):
    """Het vak "bewolkt" zoals het er op 31 augustus voor stond, plus de

    vierde dag die de drempel haalt: -10,2, +0,9, -43,9 en nog een. Een
    mediaan daarvan is geen correctie maar een gok.
    """
    _vul(tracker, [(100.0, -10.2), (74.9, 0.9), (84.75, -43.9), (90.0, -5.0)])

    assert tracker.bias_voor_bewolking(85.0) is None


def test_een_vak_dat_wel_bij_elkaar_hoort_corrigeert_gewoon(tracker):
    """De correctie mag niet doof worden: liggen de dagen op één hoop,

    dan is de mediaan precies wat je wil.
    """
    _vul(tracker, [(80.0, -28.0), (85.0, -31.0), (90.0, -26.0), (95.0, -33.0)])

    correctie = tracker.bias_voor_bewolking(85.0)

    assert correctie == pytest.approx(-29.5, abs=0.6)


def test_alleen_goede_dagen_leveren_een_kleine_correctie(tracker):
    """Het vak "helder": -1,9 en -6,6, aangevuld tot de drempel. Geen

    enkele dag zit er ver naast, dus er is niets om over te twisten.
    """
    _vul(tracker, [(0.0, -1.9), (19.85, -6.6), (10.0, -3.0), (25.0, -5.0)])

    correctie = tracker.bias_voor_bewolking(15.0)

    assert correctie is not None
    assert -8.0 <= correctie <= 0.0


def test_de_drempel_op_het_aantal_blijft_gelden(tracker):
    """Samenhang vervangt de telling niet, hij komt eronder."""
    _vul(tracker, [(80.0, -28.0), (85.0, -31.0)])

    assert SOLAR_BIAS_MIN_PER_VAK > 2
    assert tracker.bias_voor_bewolking(85.0) is None


# --- en het is te zien waarom ----------------------------------------


def test_de_kaart_laat_zien_dat_een_vak_is_ingehouden(tracker):
    """Een correctie die stilzwijgend uitblijft, is niet na te kijken.

    Dezelfde reden waarom de vlakke correctie sinds v3.33.0 een reden
    meelevert.
    """
    _vul(tracker, [(100.0, -10.2), (74.9, 0.9), (84.75, -43.9), (90.0, -5.0)])

    vakken = tracker.bewolkingsvakken()

    assert vakken["bewolkt"]["genoeg"] is True
    assert vakken["bewolkt"]["ingehouden_reden"]
    assert vakken["helder"]["ingehouden_reden"] is None


def test_een_samenhangend_vak_meldt_niets(tracker):
    _vul(tracker, [(80.0, -28.0), (85.0, -31.0), (90.0, -26.0), (95.0, -33.0)])

    assert tracker.bewolkingsvakken()["bewolkt"]["ingehouden_reden"] is None
