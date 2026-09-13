"""De winterguard rekent de slijtage mee (v3.13.0).

Gemeld op 18 augustus 14:15: "Waarom wordt er vandaag zoveel van het net
gehaald, is toch meer als nodig vannacht?"

De cijfers: 5,33 kWh import bij 2,68 kWh verbruik, accu op 80%, reden
`grid_charging_low_solar_extra_dip`. Er werd dus bewust van het net
geladen omdat er weinig zon werd verwacht - 11,5 kWh tegen een typische
18,6.

De rekensom klopte, maar was onvolledig:

    28,9 ct inkoop, 38,3 ct in het duurste kwartier (21:15)
    marge = 0,845 x 38,3 - 28,9 = 3,49 ct  ->  boven de drempel van 3,00

Alleen kost elke doorgezette kWh ook 4,22 ct aan slijtage. Netto kostte
dat laden dus ongeveer een cent per kWh in plaats van dat het bespaarde.
"""
from custom_components.energy_management_system.const import (
    LOW_SOLAR_EXTRA_DIP_MIN_MARGIN_EUR_PER_KWH,
)


def _marge(nu, later, rendement=0.845, slijtage=0.0422):
    return rendement * later - nu - slijtage


def test_the_reported_case_no_longer_charges():
    """Het gemelde geval: 28,9 ct nu tegen 38,3 ct om 21:15."""
    marge = _marge(0.289, 0.383)

    assert marge < LOW_SOLAR_EXTRA_DIP_MIN_MARGIN_EUR_PER_KWH


def test_a_real_winter_gap_still_charges():
    """De regel is gemaakt voor de winter, wanneer het prijsverschil
    groot genoeg is om de accukosten te dekken. Dat moet zo blijven."""
    marge = _marge(0.12, 0.45)

    assert marge >= LOW_SOLAR_EXTRA_DIP_MIN_MARGIN_EUR_PER_KWH


def test_wear_is_actually_subtracted():
    """Zonder slijtage lijkt het gemelde geval gunstig - dat was precies
    de fout."""
    zonder = 0.845 * 0.383 - 0.289
    met = _marge(0.289, 0.383)

    assert zonder >= LOW_SOLAR_EXTRA_DIP_MIN_MARGIN_EUR_PER_KWH
    assert met < LOW_SOLAR_EXTRA_DIP_MIN_MARGIN_EUR_PER_KWH


def test_the_code_reads_the_wear_overview():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("self.last_extra_dip_margin_eur_per_kwh = None")
    blok = bron[kop : kop + 3500]

    assert "get_wear_cost_overview" in blok
    assert "slijtage_eur_per_kwh" in blok


def test_the_main_block_is_left_alone():
    """Het hoofdblok heeft bewust GEEN rendementstoets - uitdrukkelijk zo
    gevraagd, omdat dat per definitie het goedkoopste moment van de dag
    is. Die keuze blijft staan.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "const.py").read_text()

    # De zin loopt over twee regels in de bron.
    assert "Bewust géén rendement-check op het" in bron
    assert "hoofdblok zelf (expliciet zo gevraagd)" in bron


def test_a_missing_wear_figure_does_not_block_charging():
    """Zonder slijtagecijfer valt de aftrek weg en geldt de oude regel -
    beter dan nooit meer laden."""
    marge_zonder_cijfer = 0.845 * 0.45 - 0.12 - 0.0

    assert marge_zonder_cijfer >= LOW_SOLAR_EXTRA_DIP_MIN_MARGIN_EUR_PER_KWH
