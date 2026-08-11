"""Alleen Overzicht in de tabbalk, de rest via doorklikken (v1.13.0).

Gevraagd: "De tabbladen moeten standaard niet zichtbaar zijn, ik wil het
alleen zien als ik daadwerkelijk op 'meer info' klik."

Alles behalve Overzicht is nu een subview. Die staan niet in de tabbalk
maar zijn bereikbaar via de tegels onder "Meer bekijken". Zonder die
tegels zouden ze alleen via de URL te vinden zijn - en dus praktisch
onbereikbaar.
"""
from pathlib import Path

import custom_components.energy_management_system as pkg
import yaml

PAKKET = Path(pkg.__file__).parent


def _data():
    return yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())


def _navigatiedoelen():
    """Alle paden waar ergens naartoe wordt genavigeerd.

    v1.34.0: ook links IN een markdown-kaart tellen mee. Gemeld: "Er
    zijn nu 2 plannings tegels aanwezig op de landingspagina, kan dit
    samen gevoegd worden?" De vier planningspagina's hangen nu onder een
    enkele tegel, met de doorverwijzingen op de pagina zelf - anders
    groeit de landingspagina mee met elke nieuwe subpagina.
    """
    tekst = (PAKKET / "dashboard_template.yaml").read_text()
    import re

    tegels = set(re.findall(r"navigation_path: \S*/([a-z-]+)", tekst))
    links = set(re.findall(r"\]\(/energy-management-system/([a-z-]+)\)", tekst))
    return tegels | links


# --- de tabbalk ------------------------------------------------------


def test_only_the_overview_is_visible():
    zichtbaar = [v["title"] for v in _data()["views"] if not v.get("subview")]

    assert zichtbaar == ["Overzicht"]


# --- bereikbaarheid --------------------------------------------------


def test_every_hidden_page_can_be_reached():
    """De kern: een verborgen pagina zonder ingang is een pagina die
    niet bestaat."""
    verborgen = {
        v["path"] for v in _data()["views"] if v.get("subview")
    }

    onbereikbaar = sorted(verborgen - _navigatiedoelen())

    assert not onbereikbaar, f"geen tegel wijst naar: {onbereikbaar}"


def test_the_overview_has_a_navigation_section():
    overzicht = next(
        v for v in _data()["views"] if v["title"] == "Overzicht"
    )
    koppen = [
        k.get("heading")
        for sectie in overzicht["sections"]
        for k in sectie.get("cards") or []
        if k.get("type") == "heading"
    ]

    assert "Meer bekijken" in koppen


def test_every_navigation_tile_says_what_is_there():
    """"Systeem" alleen zegt niet waar je terechtkomt."""
    overzicht = next(
        v for v in _data()["views"] if v["title"] == "Overzicht"
    )
    sectie = next(
        s
        for s in overzicht["sections"]
        if any(k.get("heading") == "Meer bekijken" for k in s.get("cards") or [])
    )

    tegels = [k for k in sectie["cards"] if k.get("type") != "heading"]
    assert len(tegels) >= 6

    for tegel in tegels:
        assert tegel.get("secondary"), tegel.get("primary")
        assert (tegel.get("tap_action") or {}).get("action") == "navigate"


def test_no_navigation_path_points_nowhere():
    """Een tik die op een niet-bestaande pagina uitkomt geeft een lege
    weergave zonder uitleg."""
    paden = {v["path"] for v in _data()["views"]}

    dood = sorted(_navigatiedoelen() - paden)

    assert not dood, f"navigeert naar niet-bestaande pagina's: {dood}"


# --- v1.14.1: de eerste view bepaalt wat je ziet --------------------


def test_the_first_view_is_not_a_subview():
    """Gemeld: "Zie nu alleen maar een details tabblad meer?"

    Home Assistant opent altijd de EERSTE view. Stond daar een subview,
    dan zag je alleen die pagina - zonder tabbalk, want subviews tonen
    die niet. Het dashboard leek daardoor uit één losse detailpagina te
    bestaan.

    In v1.12.7 kwam Details vóór Overzicht in het bestand te staan; toen
    Overzicht in v1.13.0 als enige zichtbare view overbleef, werd dat
    zichtbaar.
    """
    eerste = _data()["views"][0]

    assert not eerste.get("subview"), (
        f"'{eerste['title']}' is een subview maar staat vooraan - Home "
        "Assistant opent die en toont dan geen tabbalk"
    )


def test_the_overview_opens_first():
    assert _data()["views"][0]["title"] == "Overzicht"


# --- v1.34.0: een tegel per onderwerp --------------------------------


def test_the_landing_page_has_one_tile_per_topic():
    """Gemeld: "Er zijn nu 2 plannings tegels aanwezig op de
    landingspagina, kan dit samen gevoegd worden?"

    Het waren er zelfs vier: Planning, Kwartierplanning,
    Planning-samenvatting en Plantoetsing. Elke keer dat er een pagina
    bijkwam omdat de tekengrens werd gehaald, kwam er ook een tegel bij
    - en zo groeit de landingspagina mee met een indeling die niets met
    onderwerpen te maken heeft.
    """
    import re

    tekst = (PAKKET / "dashboard_template.yaml").read_text()
    overzicht = tekst[: tekst.index("- title: Visueel")]
    doelen = re.findall(r"navigation_path: \S*/([a-z-]+)", overzicht)

    planning = [d for d in doelen if "planning" in d or "kwartier" in d]
    assert planning == ["detail-planning"]


def test_no_tile_points_to_the_wrong_page():
    """Onder "Meer bekijken" stonden vier tegels - Systeem, Financieel,
    Verloop en Kwaliteit - die alle vier naar dezelfde pagina wezen.
    Drie daarvan beloofden iets anders dan ze gaven."""
    import re

    tekst = (PAKKET / "dashboard_template.yaml").read_text()
    overzicht = tekst[: tekst.index("- title: Visueel")]
    doelen = re.findall(r"navigation_path: \S*/([a-z-]+)", overzicht)

    dubbel = {d for d in doelen if doelen.count(d) > 1}
    # De statusbalk bovenaan wijst ook naar de kwaliteitspagina, en dat
    # is geen onderwerpstegel maar de aandachtspunten-melding zelf.
    assert dubbel <= {"detail-kwaliteit"}, (
        f"meerdere tegels wijzen naar: {sorted(dubbel)}"
    )
