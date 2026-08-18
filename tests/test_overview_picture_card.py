"""Het dynamische overzichtsplaatje (v3.17.0).

Gevraagd: "Kunnen we het visuele dashboard dynamisch maken en kleinere
getallen (dus geen zon als het bewolkt is) etc. etc. Tevens wil ik dat op
alle devices het visuele dashboard goed zichtbaar is. Ook moeten zaken
klikbaar zijn zodat je naar gedetailleerdere informatie gaat. Tevens
stromen inzichtelijk maken."

De oude kaart was een STATISCHE SVG met `picture-elements` eroverheen,
met vaste pixelgroottes. Dat verklaarde alle vier de klachten - de tests
in dit bestand gingen daarover en zijn vervangen.
"""
from pathlib import Path

import yaml

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system.overview_svg import (
    bouw_overzicht,
    zon_icoon,
    _getal,
    _pijl,
    _vermogen,
)

PAKKET = Path(pkg.__file__).parent


def _visuele_view():
    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())
    return next(v for v in data["views"] if v.get("title") == "Visueel")


# --- 1. Dynamisch: geen zon als het bewolkt is -----------------------


def test_a_clouded_sky_shows_no_sun():
    """Op het screenshot stond een stralende zon bij 99,6% bewolking."""
    soort, _kleur = zon_icoon(99.6, 268)

    assert soort == "bewolkt"


def test_a_clear_sky_shows_the_sun():
    assert zon_icoon(5.0, 2400)[0] == "zon"


def test_the_in_between_is_in_between():
    assert zon_icoon(60.0, 900)[0] == "halfbewolkt"


def test_the_cloud_cover_decides_not_the_yield():
    """'s Avonds is er geen opwek terwijl het helder kan zijn."""
    assert zon_icoon(5.0, 0)[0] == "zon"


def test_without_cloud_data_it_falls_back():
    assert zon_icoon(None, 100)[0] == "zon"


# --- 2. Leesbare getallen --------------------------------------------


def test_a_price_is_not_seven_decimals():
    """Op het screenshot: "0.2900598 €/kWh" en "0.375653656 €/kWh"."""
    assert _getal(29.00598, "ct/kWh", 1) == "29,0 ct/kWh"


def test_energy_is_rounded():
    """En "6,6528 kWh"."""
    assert _getal(6.6528, "kWh", 2) == "6,65 kWh"


def test_power_switches_to_kilowatts():
    assert _vermogen(268) == "268 W"
    assert _vermogen(2400) == "2,4 kW"


def test_a_missing_value_is_a_dash():
    """Een leeg vakje is beter dan een verzonnen nul."""
    assert _getal(None) == "—"
    assert _vermogen(None) == "—"


# --- 3. Leesbaar op elk apparaat -------------------------------------


def test_the_drawing_scales_with_the_screen():
    """Vaste pixelgroottes zijn op een telefoon onleesbaar. Een viewBox
    zonder vaste breedte schaalt vanzelf mee."""
    svg = bouw_overzicht({})

    assert 'viewBox="0 0 1000 520"' in svg
    assert 'width="100%"' in svg
    assert 'height="1000"' not in svg


def test_the_card_fills_the_width():
    view = _visuele_view()

    # v3.23.0: geen paneelweergave meer maar secties over drie kolommen,
    # want alleen zo kunnen er echte klikbare tegels onder de plaat.
    # Beide vullen de volle breedte.
    assert view.get("type") == "sections"
    assert view.get("max_columns") == 3
    # De plaat en de cijfers staan in de eerste sectie, de klikbare
    # tegels in de tweede.
    kaarten = [k for sec in view["sections"] for k in sec["cards"]]
    platen = [k for k in kaarten if k.get("type") == "markdown"]

    assert len(platen) == 2


# --- 4. Klikbaar ------------------------------------------------------


def test_the_blocks_link_to_their_detail_pages():
    svg = bouw_overzicht({})

    for doel in ("detail-zon", "detail-accu", "detail-kwartier"):
        assert f"/energy-management-system/{doel}" in svg


def test_every_link_points_at_a_page_that_exists():
    """Een klikbaar blok dat nergens heen gaat is erger dan geen link."""
    import re

    svg = bouw_overzicht({})
    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())
    paden = {v.get("path") for v in data["views"]}

    for doel in re.findall(r"/energy-management-system/([\w-]+)", svg):
        assert doel in paden, doel


# --- 5. Stromen -------------------------------------------------------


def test_a_flow_is_drawn_when_power_moves():
    """Gevraagd: "stromen inzichtelijk maken (bijvoorbeeld stroom van PV
    naar huis of accu etc)"."""
    assert _pijl(0, 0, 100, 0, 1500, "#fff") != ""


def test_no_flow_is_drawn_at_rest():
    """Een pijl die altijd staat zegt niets."""
    assert _pijl(0, 0, 100, 0, 0, "#fff") == ""
    assert _pijl(0, 0, 100, 0, 10, "#fff") == ""


def test_more_power_draws_a_thicker_line():
    import re

    def _dikte(w):
        return float(
            re.search(r'stroke-width="([\d.]+)"', _pijl(0, 0, 100, 0, w, "#fff")).group(1)
        )

    assert _dikte(2000) > _dikte(300)


def test_the_whole_drawing_survives_missing_data():
    """Vlak na een herstart is vrijwel alles nog leeg."""
    svg = bouw_overzicht({})

    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
