"""Eén detailpagina per onderwerp (v1.17.0).

Gemeld: "Als ik op een button ofzo klik kom ik op een tabblad met meer
informatie, dit tabblad is niet standaard zichtbaar. Echter op de
tabbladen staat zoveel in dat het nog niet overzichtelijk wordt. Kun je
specifieke tabbladen maken voor alle facetten? Dus meer info accu
bijvoorbeeld toont alleen info over de accu."

Terecht: de verzamelpagina telde zestien kaarten en bijna 6000 tekens -
niet overzichtelijker dan de tabbladen die er in v1.12.0 voor waren
opgeruimd. Het probleem was alleen verplaatst.
"""
import re
from pathlib import Path

import custom_components.energy_management_system as pkg
import yaml

PAKKET = Path(pkg.__file__).parent


def _data():
    return yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())


def _detailpaginas():
    return [
        v for v in _data()["views"] if str(v.get("path", "")).startswith("detail-")
    ]


def _kaarten(view):
    k = list(view.get("cards") or [])
    for sectie in view.get("sections") or []:
        k += sectie.get("cards") or []
    return k


# --- de opzet --------------------------------------------------------


def test_there_is_a_page_per_topic():
    paden = {v["path"] for v in _detailpaginas()}

    for onderwerp in (
        "detail-accu",
        "detail-apparaten",
        "detail-besparing",
        "detail-klimaat",
        "detail-kosten",
        "detail-kwaliteit",
        "detail-planning",
        "detail-water",
        "detail-witgoed",
        "detail-zon",
    ):
        assert onderwerp in paden, onderwerp


def test_each_page_stays_small():
    """Eén onderwerp per pagina is het doel; loopt er een vol, dan is de
    indeling weer te grof geworden."""
    for pagina in _detailpaginas():
        kaarten = _kaarten(pagina)
        tekens = sum(len(k.get("content") or "") for k in kaarten)

        # v1.17.1: van 6 naar 10. Planning telt negen korte tegels op
        # één onderwerp; dat is nog steeds overzichtelijk. De tekengrens
        # hieronder is de werkelijke rem tegen een volgelopen pagina.
        assert len(kaarten) <= 10, f"{pagina['title']}: {len(kaarten)} kaarten"
        assert tekens <= 2500, f"{pagina['title']}: {tekens} tekens"


def test_none_is_visible_in_the_tab_bar():
    zichtbaar = [v["title"] for v in _data()["views"] if not v.get("subview")]

    assert zichtbaar == ["Overzicht"]


def test_each_page_says_what_it_shows():
    """Zonder ondertitel weet je bij binnenkomst niet waar je bent."""
    for pagina in _detailpaginas():
        koppen = [
            k for k in _kaarten(pagina) if "title-card" in str(k.get("type"))
        ]
        assert koppen, pagina["title"]
        assert koppen[0].get("subtitle"), pagina["title"]


# --- niets kwijtgeraakt ----------------------------------------------


def test_all_sixteen_cards_survived():
    """Het opsplitsen mocht geen informatie kosten."""
    kaarten = [k for p in _detailpaginas() for k in _kaarten(p)]
    titels = {k.get("title") for k in kaarten}

    for titel in (
        "Accumodules",
        "Herkende apparaten",
        "Te beoordelen",
        "Woonkamertemperatuur per uur",
        "Waterontharder",
        "Waterverbruik vandaag",
        "Komend schema",
        "Aandachtspunten",
        "Betrouwbaarheid per grootheid",
        "Verbetermogelijkheden",
    ):
        assert titel in titels, titel


# --- bereikbaarheid --------------------------------------------------


def test_every_page_has_an_entrance():
    """Een detailpagina zonder ingang is een pagina die niet bestaat."""
    tekst = (PAKKET / "dashboard_template.yaml").read_text()
    doelen = set(re.findall(r"navigation_path: \S*/([a-z-]+)", tekst))

    for pagina in _detailpaginas():
        assert pagina["path"] in doelen, pagina["path"]


def test_no_link_points_at_the_old_collection_page():
    """De oude verzamelpagina bestaat niet meer; een tik erheen zou een
    lege weergave geven."""
    tekst = (PAKKET / "dashboard_template.yaml").read_text()

    assert "navigation_path: /energy-management-system/details" not in tekst


def test_tiles_lead_to_their_own_topic():
    """Een accu-tegel die op de waterpagina uitkomt is erger dan geen
    doorklik: dan zoek je op de verkeerde plek."""
    overzicht = next(v for v in _data()["views"] if v["title"] == "Overzicht")
    kaarten = [k for s in overzicht["sections"] for k in s.get("cards") or []]

    verwacht = {
        "accumodules": "detail-accu",
        "apparaten": "detail-apparaten",
        "klimaat": "detail-klimaat",
        "water": "detail-water",
    }
    gevonden = 0
    for kaart in kaarten:
        blok = str(kaart)
        for onderwerp, pad in verwacht.items():
            if f".get('{onderwerp}')" in blok:
                actie = kaart.get("tap_action") or {}
                assert actie.get("navigation_path", "").endswith(pad), onderwerp
                gevonden += 1

    assert gevonden >= 4


# --- v1.17.1: fijnere opsplitsing -----------------------------------


def test_each_page_covers_one_subject():
    """Gemeld: "Meer subviews, dan maar meer, maar specifiekere info
    waar ik naar wil kijken, PV = PV, accu = accu, water = water."

    De vier gemengde tabbladen (Systeem, Financieel, Verloop, Kwaliteit)
    telden 11 tot 16 kaarten met onderwerpen door elkaar. Nu twaalf
    pagina's die elk één ding tonen.
    """
    titels = {v["title"] for v in _detailpaginas()}

    for onderwerp in (
        "PV / zon",
        "Accu",
        "Water",
        "Klimaat",
        "Apparaten",
        "Planning",
        "Kosten",
        "Besparing",
        "Adviesmodules",
        "Meetkwaliteit",
    ):
        assert onderwerp in titels, onderwerp


def test_the_mixed_tabs_are_gone():
    """Systeem en Financieel mengden onderwerpen; die namen horen niet
    terug te komen."""
    titels = {v["title"] for v in _data()["views"]}

    assert "Systeem" not in titels
    assert "Financieel" not in titels


def test_the_jinja_survives_the_yaml_rewrite():
    """Het dashboard is via `yaml.dump` herschreven, waardoor
    aanhalingstekens op schijf verdubbeld staan ('' in plaats van ').

    Dat is bekend terrein: in v1.10.1 is een YAML-ronde juist VERMEDEN
    om deze reden. Na parsing is de Jinja identiek - Home Assistant leest
    het correct - maar deze test legt vast dat dat zo blijft.
    """
    for pagina in _detailpaginas():
        for kaart in _kaarten(pagina):
            for veld in ("primary", "secondary", "content"):
                waarde = kaart.get(veld)
                if not isinstance(waarde, str) or "{{" not in waarde:
                    continue
                # Let op: `''` is ook een geldige LEGE tekenreeks in
                # Jinja (`v not in ['unknown','unavailable','']`). Alleen
                # verdubbeling BINNEN een naam is fout, en dat is te zien
                # aan een quote direct naast een letter.
                import re as _re

                assert not _re.search(r"\w''\w", waarde), (
                    f"{pagina['title']}: {veld} bevat verdubbelde quotes"
                )
                assert waarde.count("{{") == waarde.count("}}")
