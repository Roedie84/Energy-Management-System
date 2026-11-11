"""v5.212.0 (punt 3): op hoeveel rondes rust een rendementsband en hoe zeker is hij?"""
from custom_components.energy_management_system import accukosten as A


def test_onder_drie_rondes_geen_uitspraak():
    assert A._band_onzekerheid([(1.0, 1.0), (2.0, 2.0)]) is None


def test_gelijke_rondes_geven_nul():
    assert A._band_onzekerheid([(1.06, 1.0), (2.12, 2.0), (3.18, 3.0)]) == 0.0


def test_uiteenlopende_rondes_geven_een_marge():
    marge = A._band_onzekerheid([(1.00, 1.0), (1.10, 1.0), (0.95, 1.0), (1.08, 1.0)])
    assert 2.0 < marge < 5.0


def test_lege_noemer():
    assert A._band_onzekerheid([(0.0, 0.0)] * 4) is None
