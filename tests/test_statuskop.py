"""Hetzelfde aandachtspunt twee keer onder elkaar (v3.95.3).

Gemeld met een schermafdruk van de landingspagina:

    ⚠️ 1 aandachtspunt(en)
    5 onverwachte tekort-dag(en) in de laatste 7 dagen. Tik voor alle
    details.

    5 onverwachte tekort-dag(en) in de laatste 7 dagen.

Twee kaarten onder elkaar, dezelfde zin.

De bovenste is een samenvattingskaart: aantal, plus de eerste ZIN van
het eerste punt. De onderste somt alle punten op. Bij één punt van één
zin zijn die twee identiek.

De samenvatting hoort te samenvatten. Het aantal en de verdeling, niet
de inhoud - die staat er al onder.
"""
import pytest


def _status(c, punten, informatief=()):
    c.get_diagnostic_summary = lambda: {
        "aandachtspunten": list(punten),
        "informatief": list(informatief),
    }
    return c.statuskop_zin()


def test_de_kop_herhaalt_het_punt_niet(make_coordinator, hass):
    """Het geval van de schermafdruk."""
    c = make_coordinator({})

    zin = _status(c, ["5 onverwachte tekort-dag(en) in de laatste 7 dagen."])

    assert "tekort-dag" not in zin


def test_de_kop_zegt_hoeveel_het_er_zijn(make_coordinator, hass):
    c = make_coordinator({})

    zin = _status(c, ["a.", "b.", "c."])

    assert "3 aandachtspunt" in zin


def test_informatieve_regels_worden_apart_geteld(make_coordinator, hass):
    """Anders lijkt het aantal te laag tegenover wat eronder staat."""
    c = make_coordinator({})

    zin = _status(c, ["a."], informatief=["x.", "y."])

    assert "1 aandachtspunt" in zin
    assert "2 informatief" in zin


def test_zonder_punten_staat_er_iets_geruststellends(make_coordinator, hass):
    c = make_coordinator({})

    zin = _status(c, [])

    assert "orde" in zin.lower()


def test_er_wordt_niet_naar_details_verwezen_die_er_niet_zijn(
    make_coordinator, hass
):
    """"Tik voor alle details" bij nul punten stuurt je naar een lege

    pagina.
    """
    c = make_coordinator({})

    assert "Tik" not in _status(c, [])
    assert "Tik" in _status(c, ["a."])
