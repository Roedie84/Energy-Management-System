"""Detailpagina achter de samenvattingen (v1.12.7).

Gemeld: "Bij een tik zie ik nog geen details?" - met een screenshot van
de standaard more-info van Home Assistant, die alleen geschiedenis en
logboek toont.

Dat is de oorzaak: HA laat in more-info geen attributen zien. Elke tegel
was sinds v1.12.4 aanklikbaar, maar de belofte "tik voor details" leverde
niets op. De onderbouwing zat wél in de attributen - alleen niet
zichtbaar.

Nu een SUBVIEW: die staat niet in de tabbalk, maar is bereikbaar via
navigate. Zo blijven de tabbladen summier én is het detail één tik weg.
"""
from pathlib import Path

import custom_components.energy_management_system as pkg
import yaml

PAKKET = Path(pkg.__file__).parent


def _data():
    return yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())


def _detailpaginas():
    """Alle detailpagina's (v1.17.0).

    De verzamelpagina "Details" telde zestien kaarten en bijna 6000
    tekens - niet overzichtelijker dan de tabbladen die ervoor waren
    opgeruimd; het probleem was alleen verplaatst. Nu één pagina per
    onderwerp, met `detail-` als voorvoegsel in het pad.
    """
    return [
        v for v in _data()["views"] if str(v.get("path", "")).startswith("detail-")
    ]


def _detailkaarten_alle():
    kaarten = []
    for view in _detailpaginas():
        kaarten += list(view.get("cards") or [])
        for sectie in view.get("sections") or []:
            kaarten += sectie.get("cards") or []
    return kaarten


# --- de pagina bestaat en is verborgen -------------------------------


def test_the_detail_page_is_a_subview():
    """Een gewoon tabblad zou de tabbalk weer voller maken - precies wat
    er in v1.12.2 is teruggebracht van tien naar zeven."""
    kaarten = _detailkaarten_alle()

    paginas = _detailpaginas()

    assert len(paginas) == 16
    for pagina in paginas:
        assert pagina.get("subview") is True, pagina["title"]


def test_only_the_overview_is_in_the_tab_bar():
    """v1.13.0, gevraagd: "De tabbladen moeten standaard niet zichtbaar
    zijn, ik wil het alleen zien als ik daadwerkelijk op meer info
    klik." Alles behalve Overzicht is nu een subview."""
    zichtbaar = [v["title"] for v in _data()["views"] if not v.get("subview")]

    assert zichtbaar == ["Overzicht"]


# --- de detailpagina bevat wat elders is weggehaald ------------------

def test_it_contains_the_removed_tables():
    """Het opruimen mocht geen informatie kosten, alleen ruimte."""
    kaarten = _detailkaarten_alle()
    titels = {k.get("title") for k in kaarten}

    for onderdeel in (
        "Aandachtspunten",
        "Betrouwbaarheid per grootheid",
        "Verbetermogelijkheden",
        "Accumodules",
        "Herkende apparaten",
        "Waterverbruik vandaag",
    ):
        assert onderdeel in titels, onderdeel


def test_the_attention_points_are_listed_in_full():
    """Op Overzicht staat alleen een telling; hier hoort de hele lijst."""
    kaarten = _detailkaarten_alle()
    kaart = next(k for k in _detailkaarten_alle() if k.get("title") == "Aandachtspunten")

    assert "for punt in p" in kaart["content"]
    assert "informatief" in kaart["content"]


# --- de tegels wijzen er ook echt heen -------------------------------


def test_summary_tiles_navigate_to_the_detail_page():
    """De kern van de melding: een tik moet ergens heen leiden."""
    data = _data()
    gevonden = 0

    for view in data["views"]:
        kaarten = list(view.get("cards") or [])
        for sectie in view.get("sections") or []:
            kaarten += sectie.get("cards") or []
        for kaart in kaarten:
            blok = str(kaart)
            if not any(
                w in blok
                for w in ("samenvattingen", "zonneplan_vergelijking", "aandachtspunten")
            ):
                continue
            if "template-card" not in str(kaart.get("type")):
                continue
            actie = kaart.get("tap_action") or {}
            assert actie.get("action") == "navigate", kaart.get("primary")
            # v1.17.0: elke tegel wijst naar ZIJN eigen onderwerp-pagina
            # in plaats van naar één verzamelpagina.
            pad = actie.get("navigation_path", "")
            assert "/detail-" in pad or pad.endswith(
                ("/financieel", "/kwaliteit", "/systeem", "/verloop")
            ), pad
            gevonden += 1

    assert gevonden >= 5, f"maar {gevonden} tegels wijzen naar de details"


def test_measurement_tiles_keep_more_info():
    """Tegels met een losse meetwaarde houden more-info: daar is de
    grafiek juist wél het nuttige detail."""
    data = _data()
    overzicht = next(v for v in data["views"] if v["title"] == "Overzicht")
    kaarten = [k for sec in overzicht["sections"] for k in sec.get("cards") or []]

    metingen = [
        k
        for k in kaarten
        if (k.get("tap_action") or {}).get("action") == "more-info"
    ]

    assert metingen, "geen enkele tegel opent nog more-info"


# --- v1.12.8: het principe geldt voor élke kaart --------------------


def _alle_kaarten(view):
    k = list(view.get("cards") or [])
    for sectie in view.get("sections") or []:
        k += sectie.get("cards") or []
        for kaart in sectie.get("cards") or []:
            k += kaart.get("cards") or []
    for kaart in view.get("cards") or []:
        k += kaart.get("cards") or []
    return k


def test_every_tile_everywhere_can_be_opened():
    """Gevraagd: "Graag voor alle cards doen die dit principe moeten
    hanteren."

    Negen tegels binnen de grid-kaarten op Financieel hadden nog geen
    tap_action. Die tonen losse bedragen, dus daar is more-info het
    juiste detail - maar zonder tap_action gebeurde er niets.
    """
    zonder = []
    for view in _data()["views"]:
        if view["title"] == "Details":
            continue
        for kaart in _alle_kaarten(view):
            if "template-card" not in str(kaart.get("type")):
                continue
            if not kaart.get("tap_action"):
                zonder.append(
                    f"{view['title']}: {str(kaart.get('primary'))[:45]}"
                )

    assert not zonder, zonder


def test_the_exceptions_are_deliberate():
    """Drie soorten volgen het principe bewust NIET, en dat hoort zo:

    - schakelaars (`entity-card`) schakelen bij een tik; navigeren zou
      juist verhinderen waar ze voor zijn;
    - grafieken ZIJN al het detail;
    - markdown-kaarten ondersteunen geen tap_action in Home Assistant.
    """
    soorten = set()
    for view in _data()["views"]:
        if view.get("subview"):
            continue
        if view["title"] == "Details":
            continue
        for kaart in _alle_kaarten(view):
            if not kaart.get("tap_action") and kaart.get("type") not in (
                "heading",
                "grid",
            ):
                soorten.add(kaart["type"])

    toegestaan = {
        "markdown",
        "history-graph",
        "statistics-graph",
        "custom:mushroom-entity-card",
        "custom:mushroom-title-card",
        "picture-elements",
    }
    assert soorten <= toegestaan, soorten - toegestaan


def test_nothing_is_shown_twice():
    """v1.17.1: de verbetermogelijkheden stonden zowel op het
    Kwaliteit-tabblad als op de detailpagina. Sinds de opsplitsing is er
    per onderwerp nog één pagina, dus de controle is: geen enkele
    kaarttitel komt twee keer voor over alle detailpagina's heen."""
    titels = [
        k.get("title")
        for k in _detailkaarten_alle()
        if k.get("title") and "title-card" not in str(k.get("type"))
    ]

    dubbel = sorted({t for t in titels if titels.count(t) > 1})

    assert not dubbel, dubbel


