"""Veel schakelen is niet hetzelfde als pendelen (v4.9.6).

Op de landingspagina stond twee dagen op rij:

    Accukoeling: 8 schakelingen in de laatste 6 uur - dat wijst op
    pendelen rond een drempel.

Ik stond op het punt er een dode zone in te bouwen, zoals bij de vijf
schakelparen van v3.99.4 en v3.99.14. Eerst de koelgeschiedenis gelezen:

    12:05 aan   accu 36 °C   buiten 18,4
    12:57 uit   accu 26 °C   buiten 18,7
    13:27 aan   accu 35 °C   buiten 18,7
    14:10 uit   accu 27 °C   buiten 19,6
    14:41 aan   accu 35 °C   buiten 19,4
    15:38 uit   accu 26 °C   buiten 20,9

Elke beurt duurt een uur en haalt de accu ACHT TOT DERTIEN GRADEN
omlaag. Daarna warmt hij in anderhalf uur weer op en gaat de ventilator
opnieuw aan. Dat is geen pendelen rond een drempel - dat is een
koelcyclus die werkt. Pendelen zou zijn: aan bij 28,1 en uit bij 27,9.

De telling keek alleen naar het AANTAL schakelingen. Nu kijkt ze naar
wat elke beurt heeft opgeleverd: haalt een cyclus meer dan een paar
graden omlaag, dan doet hij zijn werk en is er niets te melden. Alleen
korte beurten zonder temperatuurdaling zijn pendelen.

Bijna had ik een rem gezet op een regellus die het goed deed.
"""
import pytest


def _cyclus(c, paren):
    """paren: (aan_c, uit_c) per beurt."""
    c.battery_cooling_history = []
    for n, (aan, uit) in enumerate(paren):
        c.battery_cooling_history += [
            {"moment": f"2026-09-10T{12 + n * 2:02d}:05:00+02:00", "actie": "aan",
             "accu_c": aan, "buiten_c": 18.0},
            {"moment": f"2026-09-10T{12 + n * 2:02d}:57:00+02:00", "actie": "uit",
             "accu_c": uit, "buiten_c": 18.0},
        ]


def test_een_werkende_cyclus_is_geen_pendelen(make_coordinator, hass):
    c = make_coordinator({})
    _cyclus(c, [(36.0, 26.0), (35.0, 27.0), (35.0, 26.0), (31.0, 23.0)])

    uit = c.koeling_pendelt()

    assert uit["pendelt"] is False
    assert uit["mediaan_daling_c"] == pytest.approx(8.5, abs=0.6)
    assert "werkt" in uit["uitleg"]


def test_beurten_zonder_daling_zijn_wel_pendelen(make_coordinator, hass):
    c = make_coordinator({})
    _cyclus(c, [(28.1, 27.9), (28.2, 27.8), (28.0, 27.9), (28.1, 28.0)])

    uit = c.koeling_pendelt()

    assert uit["pendelt"] is True
    assert uit["mediaan_daling_c"] < 1.0


def test_te_weinig_beurten_geen_oordeel(make_coordinator, hass):
    c = make_coordinator({})
    _cyclus(c, [(36.0, 26.0)])

    assert c.koeling_pendelt()["pendelt"] is False


def test_het_aandachtspunt_volgt_de_daling(make_coordinator, hass):
    """De landingspagina meldt alleen nog pendelen dat echt pendelen is."""
    c = make_coordinator({})
    _cyclus(c, [(36.0, 26.0), (35.0, 27.0), (35.0, 26.0), (31.0, 23.0)])
    c.battery_cooling_switches_today = 8

    punten = (c.get_consistency_checks() or {}).get("punten") or []
    koeling = [p for p in punten if p.get("onderwerp") == "Accukoeling"]

    assert not [p for p in koeling if p.get("ernst") != "in_orde"], koeling
