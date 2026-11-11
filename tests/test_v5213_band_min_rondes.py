"""v5.213.0 (Ruud 11-11 11:42, akkoord): een rendementsband telt pas vanaf 8 rondes."""
import pytest

from custom_components.energy_management_system import accukosten as A


def _b(eta, rondes=None, betrouwbaar=True):
    d = {"rendement_procent": eta, "betrouwbaar": betrouwbaar, "kwartieren": 100, "kwh": 20.0}
    if rondes is not None:
        d["rondes"] = rondes
    return d


def _banden(*drie):
    return dict(zip(A.BAND_NAMEN, drie))


def test_de_stand_van_11_november():
    """>1500 W op 3 rondes neemt het cijfer van 500-1500 W."""
    uit = A.band_voor_plan(_banden(_b(100.9, 29), _b(106.2, 16), _b(106.9, 3)))
    assert uit == pytest.approx([1.009, 1.062, 1.062])


def test_genoeg_rondes_telt_zelf():
    uit = A.band_voor_plan(_banden(_b(100.9, 29), _b(106.2, 16), _b(102.0, 8)))
    assert uit == pytest.approx([1.009, 1.062, 1.02])


def test_onderste_band_neemt_de_middelste():
    assert A.band_voor_plan(_banden(_b(90.0, 2), _b(106.2, 16), _b(102.0, 9))) == pytest.approx([1.062, 1.062, 1.02])


def test_middelste_band_neemt_bij_gelijke_afstand_de_lagere():
    assert A.band_voor_plan(_banden(_b(99.0, 20), _b(110.0, 4), _b(102.0, 9))) == pytest.approx([0.99, 0.99, 1.02])


def test_geen_enkele_band_bruikbaar():
    assert A.band_voor_plan(_banden(_b(99.0, 1), _b(110.0, 4), _b(102.0, 2))) == [None, None, None]
    assert A.band_voor_plan(None) == [None, None, None]


def test_onbetrouwbare_band_neemt_ook_de_buur():
    assert A.band_voor_plan(_banden(_b(99.0, 20), _b(106.0, 20), _b(None, 0, betrouwbaar=False))) == pytest.approx([0.99, 1.06, 1.06])


def test_oude_gegevens_zonder_rondes_tellen_zoals_voorheen():
    assert A.band_voor_plan(_banden(_b(99.0), _b(106.0), _b(101.8))) == pytest.approx([0.99, 1.06, 1.018])
