"""Twee soorten dagen, geen verschuiving (v3.28.0).

Gemeld met een schermafdruk van de meetkwaliteitskaart: "1 van de 26
gemeten grootheden is onbetrouwbaar: Zonvoorspelling (klopt de correctie
nog?)". De melding wees vervuiling, een uitgevallen streng of toegenomen
beschaduwing aan.

De zes dagen eronder zeggen iets anders:

    13 aug  21,62 voorspeld  21,48 werkelijk   -0,7%
    14 aug  21,36            20,90             -2,2%
    15 aug  15,39             9,13            -40,7%
    16 aug  16,17            16,38             +1,3%
    17 aug  18,49             9,44            -48,9%
    18 aug   9,14             5,20            -43,2%

Een uitgevallen streng zou élke dag met ongeveer hetzelfde percentage
omlaag halen. Drie van de zes dagen zitten binnen 2,2%. Een array die
21,48 kWh levert op 21,62 voorspeld mist geen streng en is niet
vervuild.

Het zijn twee soorten dagen: heldere dagen kloppen, wisselvallige dagen
zitten er 40 tot 50% naast. De integratie zei het zelf al elders:
gemiddelde fout 22,6% tegenover een mediane fout van 4,7%.

En daar zat de tweede fout. De geleerde bias is het GEMIDDELDE van de
afwijkingen, en dat gemiddelde wordt door de uitschieters bepaald. Met
-22,6% als vlakke correctie op alles wordt een heldere dag die klopte
22% te laag voorspeld, terwijl een bewolkte dag nog steeds niet gedekt
wordt.

Nagerekend over deze zeven dagen (correctiefactor f, fout na correctie
is (1+afwijking)/f - 1):

    zonder correctie      gemiddelde fout 22,6%   mediaan 4,7%
    gemiddelde-bias 0,774 gemiddelde fout 29,6%   mediaan 27,3%
    mediaan-bias 0,953    gemiddelde fout 21,9%   mediaan 4,0%

De correctie die er nu in zit maakt het slechter dan helemaal niet
corrigeren. Dat is geen afweging meer.
"""
import statistics

import pytest

from custom_components.energy_management_system.solar_forecast import (
    SolarForecastAccuracyTracker,
)

# De zeven gemeten afwijkingen uit de export van 19 augustus 08:46.
GEMETEN = [-1.3, -2.7, -1.5, -41.6, -4.7, -51.4, -54.8]


def _tracker(afwijkingen: list[float]) -> SolarForecastAccuracyTracker:
    tracker = SolarForecastAccuracyTracker.__new__(SolarForecastAccuracyTracker)
    tracker.deviation_history = list(afwijkingen)
    return tracker


def _fout_na_correctie(afwijkingen: list[float], bias: float) -> tuple:
    """Wat blijft er over als je met deze bias corrigeert?"""
    f = 1 + bias / 100
    fouten = [abs((1 + d / 100) / f - 1) * 100 for d in afwijkingen]
    return round(statistics.fmean(fouten), 1), round(statistics.median(fouten), 1)


# --- 1. de bias zelf -------------------------------------------------


def test_the_learned_bias_is_the_median():
    """Het gemiddelde wordt door de uitschieters bepaald; de mediaan

    niet. Bij vier goede en drie slechte dagen hoort de correctie de
    goede dagen met rust te laten.
    """
    assert _tracker(GEMETEN).learned_bias_percent == -4.7


def test_the_mean_is_still_visible_for_comparison():
    """Zonder het oude getal ernaast is niet na te gaan of de keuze nog

    klopt.
    """
    assert _tracker(GEMETEN).mean_bias_percent == -22.6


def test_the_old_correction_was_worse_than_no_correction_at_all():
    """Dit is de reden dat dit geen afweging is maar een reparatie."""
    zonder = _fout_na_correctie(GEMETEN, 0.0)
    gemiddelde = _fout_na_correctie(GEMETEN, -22.6)
    mediaan = _fout_na_correctie(GEMETEN, -4.7)

    assert gemiddelde[0] > zonder[0], "gemiddelde-bias hoorde slechter te zijn"
    assert mediaan[0] < zonder[0], "mediaan-bias hoorde beter te zijn"
    assert mediaan[0] < gemiddelde[0]


def test_a_real_shift_is_still_learned():
    """De mediaan is niet blind: zakt élke dag met 20%, dan corrigeert

    hij net zo hard als het gemiddelde. Alleen bij uitschieters lopen ze
    uiteen.
    """
    verschoven = [-19.0, -21.0, -20.0, -22.0, -18.0, -20.0, -20.0]
    tracker = _tracker(verschoven)

    assert tracker.learned_bias_percent == -20.0
    assert abs(tracker.learned_bias_percent - tracker.mean_bias_percent) < 1.0


def test_an_empty_history_still_returns_nothing():
    assert _tracker([]).learned_bias_percent is None
    assert _tracker([]).mean_bias_percent is None


# --- 2. de duiding ---------------------------------------------------


class _Kaal:
    """Alleen de duiding, zonder de rest van de coordinator."""

    def __init__(self, afwijkingen):
        self.solar_tracker = _tracker(afwijkingen)


def _oordeel(afwijkingen):
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    return C.get_solar_forecast_health(_Kaal(afwijkingen))


def test_two_kinds_of_days_are_not_blamed_on_the_installation():
    """De aanleiding. Drie dagen binnen 2,2% bewijzen dat de panelen

    leveren wat er voorspeld wordt; dan kan het geen streng of
    vervuiling zijn.
    """
    oordeel = _oordeel(GEMETEN)

    assert oordeel["soort"] == "spreiding"
    assert "niet op de installatie" in oordeel["reden"]
    assert "beschaduwing" not in oordeel["reden"]


def test_it_says_what_it_actually_is():
    """Heldere dagen kloppen, wisselvallige dagen niet. Dat is een

    bewolkingsprobleem in de voorspelling.
    """
    oordeel = _oordeel(GEMETEN)

    assert "bewolk" in oordeel["reden"] or "wisselvallig" in oordeel["reden"]
    assert oordeel["soort"] == "spreiding"


def test_a_real_installation_change_is_still_reported_as_one():
    """Zakt élke dag ongeveer even hard, dan is er wél iets veranderd aan

    de installatie - en dan hoort die tekst er juist te staan.
    """
    # Lang rond -2, en dan zakt élke dag naar -30: geen goede dag meer
    # in het venster. Dat is wél een verandering aan de installatie.
    oordeel = _oordeel(
        [-1.0, -2.0, -3.0, -2.0, -1.0, -2.0, -30.0, -31.0, -29.0, -32.0, -30.0]
    )

    assert oordeel["soort"] == "verschuiving"
    assert "streng" in oordeel["reden"]


def test_a_forecast_that_simply_works_stays_quiet():
    oordeel = _oordeel([-1.3, -2.7, -1.5, -4.7, 0.4, -2.0, -1.0])

    assert oordeel["status"] != "onbetrouwbaar"


@pytest.mark.parametrize(
    "afwijkingen",
    [
        [-1.0, -2.0, -50.0, -1.0, -49.0],
        [2.0, -45.0, 1.0, -51.0, -3.0],
    ],
)
def test_the_spread_is_recognised_regardless_of_order(afwijkingen):
    """De volgorde van goede en slechte dagen mag niet uitmaken."""
    assert _oordeel(afwijkingen)["soort"] == "spreiding"
