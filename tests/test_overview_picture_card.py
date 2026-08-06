"""Grafische overzichtskaart met entiteiten in een afbeelding
(v0.63.125).

Gevraagd: "een grote afbeelding waarin alle gegevens zijn opgenomen...
1 grote card met alle gegevens in verwerkt per subcategorie", eerst voor
tabblad 1.

Gebouwd als `picture-elements` (kernkaart van Home Assistant, geen HACS
nodig): een SVG-achtergrond met daarop absoluut gepositioneerde
`state-label`- en `state-icon`-elementen.

De grootste foutbron hier is dat de tekening en de posities uit elkaar
lopen: de posities zijn PERCENTAGES van de afbeelding, dus als de SVG
verandert zonder dat de percentages meebewegen, staan de waarden er
naast zonder dat iets stukgaat. Deze tests bewaken die koppeling.
"""
import re
from pathlib import Path

import yaml

import custom_components.energy_management_system as pkg

PAKKET = Path(pkg.__file__).parent
SVG = PAKKET / "overview_background.svg"
DASHBOARD = PAKKET / "dashboard_template.yaml"


def _visuele_view():
    """v0.63.126: de kaart heeft een EIGEN tabblad gekregen in plaats van
    boven aan Overzicht te staan."""
    data = yaml.safe_load(DASHBOARD.read_text())
    for view in data["views"]:
        for card in view.get("cards") or []:
            if card.get("type") == "picture-elements":
                return view
    raise AssertionError("geen tabblad met een picture-elements-kaart gevonden")


def _kaart():
    return next(
        card
        for card in _visuele_view()["cards"]
        if card["type"] == "picture-elements"
    )


def test_background_is_shipped_with_the_integration():
    """Zonder meegeleverde tekening toont de kaart een gebroken
    afbeelding met alle waarden er wél overheen - verwarrender dan een
    lege kaart."""
    assert SVG.exists()
    assert SVG.stat().st_size > 1000


def test_background_is_valid_xml():
    import xml.etree.ElementTree as ET

    ET.parse(SVG)


def test_repository_and_shipped_background_are_identical():
    """Zelfde afspraak als voor het dashboard zelf: de twee kopieën
    mogen nooit uiteenlopen."""
    repo = PAKKET.parent.parent / "dashboards" / "energy_management_system_overview.svg"
    assert repo.read_text() == SVG.read_text()


def test_card_points_at_the_shipped_background():
    """Home Assistant serveert alleen `www/` (als /local/). Wijst de
    kaart ergens anders heen, dan laadt de afbeelding nooit."""
    assert _kaart()["image"].startswith(
        "/local/energy_management_system_overview.svg"
    )


def test_image_url_carries_the_current_version_as_cache_key():
    """v0.63.131, gerapporteerd: "Afbeelding (richtingen van de stromen)
    nog niet geupdate?" - de waarden waren wél bij, de tekening niet.

    Root cause: /local/ serveert een statisch bestand onder een VASTE
    naam. De entiteitswaarden komen live over de websocket binnen, maar
    de achtergrond blijft uit de browsercache komen - dus nieuwe cijfers
    op een oude tekening. De versiesleutel in de URL dwingt een verse
    ophaal af bij elke release.

    Deze test koppelt die sleutel hard aan manifest.json: wordt de versie
    opgehoogd zonder de sleutel bij te werken, dan faalt de testsuite
    voordat er een release uitgaat.
    """
    import json

    versie = json.loads((PAKKET / "manifest.json").read_text())["version"]

    assert _kaart()["image"].endswith(f"?v={versie}"), (
        "de cache-sleutel loopt achter op manifest.json - dan blijft de "
        "oude tekening in beeld na een update"
    )


def test_integration_copies_the_background_into_www():
    bron = (PAKKET / "__init__.py").read_text()
    assert "_copy_overview_background" in bron
    assert "www/energy_management_system_overview.svg" in bron
    # Moet via een executor draaien - het is een blokkerende
    # bestandsoperatie en mag de event loop niet ophouden.
    assert "async_add_executor_job(_copy_overview_background" in bron


def test_every_element_stays_within_the_image():
    """Een percentage buiten 0-100 zet de waarde onzichtbaar buiten de
    kaart."""
    for element in _kaart()["elements"]:
        stijl = element["style"]
        for as_ in ("top", "left"):
            waarde = float(stijl[as_].rstrip("%"))
            assert 0 <= waarde <= 100, f"{element.get('entity')} valt buiten beeld"


def test_all_subcategories_are_represented():
    """De vraag was expliciet "per subcategorie" - elk vak in de
    tekening moet ook echt gevulde waarden krijgen."""
    svg = SVG.read_text()
    for zone in ("ZON", "HUIS", "NET", "THUISACCU", "BESLUIT", "BEWAKING"):
        assert f">{zone}<" in svg, f"zone {zone} ontbreekt in de tekening"

    elementen = _kaart()["elements"]
    hoogtes = [float(e["style"]["top"].rstrip("%")) for e in elementen]
    breedtes = [float(e["style"]["left"].rstrip("%")) for e in elementen]
    # Zowel de bovenste rij (zon/huis/net) als de onderste
    # (besluit/accu/bewaking) moet bezet zijn, en zowel links als rechts.
    assert any(h < 50 for h in hoogtes) and any(h > 55 for h in hoogtes)
    assert any(b < 30 for b in breedtes) and any(b > 60 for b in breedtes)


def test_every_anchor_in_the_svg_has_a_matching_element():
    """De SVG documenteert zijn ankerpunten in commentaar ("anker X: x
    A..B, y C..D"). Elk anker hoort een element te hebben dat er binnen
    valt - zo blijft de tekening leidend en lopen de twee niet stil uit
    elkaar."""
    svg = SVG.read_text()
    ankers = re.findall(
        r"anker ([a-z ]+): x (\d+)\.\.(\d+), y (\d+)\.\.(\d+)", svg
    )
    assert len(ankers) >= 10, "te weinig gedocumenteerde ankerpunten"

    posities = [
        (
            float(e["style"]["left"].rstrip("%")) / 100 * 1600,
            float(e["style"]["top"].rstrip("%")) / 100 * 900,
        )
        for e in _kaart()["elements"]
    ]

    for naam, x1, x2, y1, y2 in ankers:
        x1, x2, y1, y2 = int(x1), int(x2), int(y1), int(y2)
        gevonden = any(
            x1 - 40 <= x <= x2 + 40 and y1 - 40 <= y <= y2 + 40
            for x, y in posities
        )
        assert gevonden, f"anker '{naam.strip()}' heeft geen element in de buurt"


def test_labels_are_readable_on_the_dark_background():
    """Alles moet een expliciete kleur en schaduw hebben - de
    themakleur van Home Assistant is niet gegarandeerd leesbaar op deze
    eigen achtergrond."""
    for element in _kaart()["elements"]:
        if element["type"] != "state-label":
            continue
        stijl = element["style"]
        assert stijl.get("color"), f"{element['entity']} heeft geen kleur"
        assert "text-shadow" in stijl


def test_labels_do_not_wrap():
    """Zonder nowrap breekt een lange waarde af en schuift alles op."""
    for element in _kaart()["elements"]:
        if element["type"] == "state-label":
            assert element["style"].get("white-space") == "nowrap"


def test_elements_are_clickable_for_detail():
    """De kaart is een overzicht, geen doodlopende weg - elk element
    moet doorklikken naar de details."""
    for element in _kaart()["elements"]:
        assert element.get("tap_action"), f"{element.get('entity')} is niet klikbaar"


def test_no_duplicate_positions():
    """Twee elementen op exact dezelfde plek overlappen elkaar
    onleesbaar."""
    posities = [
        (e["style"]["left"], e["style"]["top"]) for e in _kaart()["elements"]
    ]
    assert len(posities) == len(set(posities))


def test_the_original_overview_is_untouched():
    """De grafische kaart komt ERBIJ, niet in plaats van. Overzicht
    houdt zijn tabellen en schakelaars - die blijven nodig voor het
    echte werk."""
    data = yaml.safe_load(DASHBOARD.read_text())
    overzicht = data["views"][0]

    assert overzicht["title"] == "Overzicht"
    koppen = [
        card.get("heading")
        for sectie in overzicht["sections"]
        for card in sectie.get("cards", [])
        if card.get("type") == "heading"
    ]
    for verwacht in ("Accu, rendement & live cijfers", "Modus & besluit", "Besturing"):
        assert verwacht in koppen

    # En de kaart staat er niet meer bovenop.
    assert not any(
        card.get("type") == "picture-elements"
        for sectie in overzicht["sections"]
        for card in sectie.get("cards", [])
    )


def test_the_visual_card_has_its_own_tab():
    """v0.63.126, gevraagd: "Ik wil een extra tabblad voor hetgeen je
    net gemaakt hebt"."""
    view = _visuele_view()

    assert view["title"] == "Visueel"
    assert view.get("panel") is True, (
        "een panel-view laat de kaart de volle breedte vullen; zonder "
        "panel blijft de tekening klein in een kolom hangen"
    )
    assert len(view["cards"]) == 1, "een panel-view mag exact één kaart bevatten"


def test_panel_card_has_no_grid_options():
    """`grid_options` hoort bij een sections-view en doet niets in een
    panel-view - laten staan zou alleen verwarren."""
    assert "grid_options" not in _kaart()


# --- v0.63.127: leesbaarheid van twee waarden -----------------------


def test_battery_power_is_on_the_card():
    """Gerapporteerd: "Vermogen naar/van accu is niet inzichtelijk" - de
    pijl tussen huis en accu had geen waarde."""
    attributen = [e.get("attribute") for e in _kaart()["elements"]]
    assert "accu_vermogen_weergave" in attributen


def test_timestamp_uses_the_readable_attribute():
    """Gerapporteerd: "de datum notatie is niet duidelijk" - er stond een
    ruwe ISO-tijdstempel. Een state-label kan niet formatteren, dus de
    kaart moet het al-geformatteerde attribuut gebruiken."""
    attributen = [e.get("attribute") for e in _kaart()["elements"]]
    assert "last_successful_update_short" in attributen
    assert "last_successful_update" not in attributen


def test_battery_arrow_points_both_ways():
    """Een enkele pijl suggereerde permanent ontladen, terwijl de accu
    beide kanten op gaat."""
    svg = SVG.read_text()
    assert 'marker-start="url(#pijlAccuOmhoog)"' in svg
    assert 'id="pijlAccuOmhoog"' in svg


def test_grid_arrow_points_both_ways():
    """v0.63.128: het net is óók tweerichtingsverkeer - importeren én
    terugleveren. De netstroom kan negatief zijn (export), dus een pijl
    die alleen naar het huis wijst is onjuist."""
    svg = SVG.read_text()
    assert 'marker-start="url(#pijlNetTerug)"' in svg
    assert 'id="pijlNetTerug"' in svg


def test_solar_arrow_stays_one_directional():
    """Bewust géén dubbele pijl: de zon produceert alleen. Een dubbele
    pijl zou hier juist onjuist zijn."""
    svg = SVG.read_text()
    zonlijn = next(r for r in svg.split("\n") if "url(#pijlZon)" in r)

    assert "marker-end" in zonlijn
    assert "marker-start" not in zonlijn
    assert "pijlZonTerug" not in svg


def test_arrow_markers_do_not_scale_with_line_width():
    """v0.63.127: zonder `markerUnits="userSpaceOnUse"` schaalt een
    pijlpunt mee met de lijndikte - bij stroke-width 6 werd een punt van
    10 eenheden er één van 60, en raakten de twee punten van een dubbele
    pijl elkaar (zandloper in plaats van pijl)."""
    svg = SVG.read_text()
    for regel in svg.split("\n"):
        if "<marker" in regel:
            assert 'markerUnits="userSpaceOnUse"' in regel, regel.strip()


# --- v1.0.0: releaseborging ----------------------------------------


def test_release_workflow_exists_and_reads_the_manifest():
    """v1.0.0, gerapporteerd: "Nu zie ik met de update telkens een code
    als 48eb9da."

    HACS toont de commit-hash zodra een repository geen GitHub-releases
    heeft - dat is de terugval. Deze workflow maakt van elke
    versieverhoging in manifest.json automatisch een tag + release, zodat
    HACS een echt versienummer kan tonen.
    """
    workflow = PAKKET.parent.parent / ".github" / "workflows" / "release.yml"
    assert workflow.exists(), "geen release-workflow - HACS toont dan een hash"

    inhoud = workflow.read_text()
    # Het versienummer in manifest.json blijft de enige bron van
    # waarheid; de workflow mag er geen eigen nummering naast zetten.
    assert "manifest.json" in inhoud
    assert "softprops/action-gh-release" in inhoud
    # Een release zonder groene testsuite zou de hele borging van dit
    # project omzeilen.
    assert "pytest" in inhoud


def test_version_is_a_plain_three_part_number():
    """HACS sorteert releases op versienummer; een afwijkend formaat
    (datums, achtervoegsels) maakt "welke is nieuwer" onbetrouwbaar."""
    import json
    import re

    versie = json.loads((PAKKET / "manifest.json").read_text())["version"]

    assert re.fullmatch(r"\d+\.\d+\.\d+", versie), versie
