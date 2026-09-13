"""Labels passen binnen de tegelbreedte (v1.12.6).

Gemeld: "De rendement card is wel volledig leesbaar, de rest niet, graag
optimaliseren."

De rendementskaart stond op volle breedte (12 kolommen), de rest op de
halve (6). Labels als "Netstroom, P1 (kan negatief zijn bij export)" (44
tekens) en "Grootverbruiker bevestigd actief (omzeilt mediaan-vertraging)"
(61 tekens) werden daardoor afgekapt tot "Netstroom, P1 (kan n…".

Een afgekapt label is erger dan een kort label: je ziet dát er iets staat
maar niet wát, en de tegel wordt onbruikbaar zonder erop te klikken.
"""
import re
from pathlib import Path

import custom_components.energy_management_system as pkg
import yaml

PAKKET = Path(pkg.__file__).parent

# Vuistregel uit de praktijk: een mushroom-tegel toont ongeveer 22
# tekens per label bij zes kolommen, en het dubbele bij twaalf.
# v1.17.3: bij volle sectiebreedte (12) past aanzienlijk meer, omdat de
# secties zelf al naast elkaar staan - een sectie is ongeveer een derde
# van het scherm, niet het hele scherm. Vandaar 34 en niet 48.
MAX_TEKENS = {4: 15, 6: 22, 12: 34}


def _kaarten(view):
    """Alle kaarten, ook die binnen een grid.

    v1.13.2: die werden overgeslagen, waardoor twaalf te lange labels op
    Financieel onopgemerkt bleven - "Besparing t.o.v. zonder
    accu-sturing (vandaag)" is 46 tekens.
    """
    k = list(view.get("cards") or [])
    for sectie in view.get("sections") or []:
        k += sectie.get("cards") or []
    for kaart in list(k):
        k += kaart.get("cards") or []
    return k


def test_no_label_is_cut_off():
    """De kern: elk vast label past binnen de breedte van zijn tegel."""
    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())
    te_lang = []

    for view in data["views"]:
        for kaart in _kaarten(view):
            for veld in ("secondary", "name"):
                label = kaart.get(veld)
                # Sjablonen overslaan: die berekenen hun eigen tekst.
                if not isinstance(label, str) or "{" in label:
                    continue
                # Zonder expliciete breedte staat een kaart in een grid,
                # en die zijn standaard smal - uitgaan van de volle
                # breedte was juist de fout.
                kolommen = (kaart.get("grid_options") or {}).get("columns", 6)
                grens = MAX_TEKENS.get(kolommen, 22)
                if len(label) > grens:
                    te_lang.append(
                        f"{view['title']}: '{label}' ({len(label)} tekens, "
                        f"{kolommen} kolommen, max {grens})"
                    )

    assert not te_lang, te_lang


def test_the_control_tiles_are_wide_enough():
    """Vier kolommen was te smal voor namen als "Steelstofzuiger
    overrule"; die sectie staat nu op zes."""
    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())
    overzicht = next(v for v in data["views"] if v["title"] == "Overzicht")

    besturing = next(
        sec
        for sec in overzicht["sections"]
        if any(k.get("heading") == "Besturing" for k in sec.get("cards") or [])
    )

    for kaart in besturing["cards"]:
        if kaart.get("type") == "heading":
            continue
        kolommen = (kaart.get("grid_options") or {}).get("columns", 12)
        # v1.17.2: de besturingstegels staan op vier kolommen (drie per
        # rij) om het scrollen te beperken; de namen zijn navenant
        # ingekort.
        assert kolommen >= 4, kaart.get("name")


def test_shortening_did_not_lose_the_meaning():
    """"PV-limiet" moet nog steeds herkenbaar zijn; een label dat
    nietszeggend wordt is geen verbetering."""
    yaml_tekst = (PAKKET / "dashboard_template.yaml").read_text()

    for label in (
        "Netstroom (P1)",
        "Huishoudverbruik",
        "Werkelijke modus",
        "Verwachte modus",
        "Boven prijsdrempel",
        "Grootverbruiker actief",
    ):
        assert f"secondary: {label}" in yaml_tekst, label


def test_the_full_explanation_is_still_reachable():
    """De uitleg die uit de labels is gehaald - "kan negatief zijn bij
    export", "omzeilt mediaan-vertraging" - moet ergens blijven staan.
    Elke tegel is aanklikbaar, dus die staat in de attributen."""
    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())
    overzicht = next(v for v in data["views"] if v["title"] == "Overzicht")

    tegels = [
        k
        for k in _kaarten(overzicht)
        if "template-card" in str(k.get("type")) and k.get("entity")
    ]

    assert tegels
    for tegel in tegels:
        assert tegel.get("tap_action"), tegel.get("secondary")


def test_cards_inside_grids_are_checked_too():
    """v1.13.2: de test keek alleen naar kaarten met een expliciete
    kolombreedte. Kaarten binnen een grid hebben die niet en vielen dus
    buiten de controle - twaalf te lange labels op Financieel bleven
    daardoor staan tot ze op een screenshot opvielen.

    Deze test legt vast dat er daadwerkelijk in de grids wordt gekeken.
    """
    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())
    financieel = next(v for v in data["views"] if v["title"] == "Kosten")

    op_viewniveau = len(financieel.get("cards") or [])
    met_grids = len(_kaarten(financieel))

    assert met_grids > op_viewniveau, (
        "de helper kijkt niet in de grid-kaarten"
    )


def test_dynamic_labels_are_short_too():
    """Sjabloonlabels worden niet automatisch getoetst - ze berekenen
    hun eigen tekst - maar kunnen net zo goed te lang uitvallen. Deze
    twee waren 60+ tekens."""
    yaml_tekst = (PAKKET / "dashboard_template.yaml").read_text()

    assert "Accubesparing (kostprijs-model)" not in yaml_tekst
    assert "Uitstoot vandaag (huidige intensiteit" not in yaml_tekst


# --- v1.17.3: geen dubbele opdeling ---------------------------------


def test_overview_tiles_use_the_full_section_width():
    """Gemeld: "Veel niet leesbaar, graag volledige breedte per card (in
    acht houden dat er 3 secties zijn in de breedte)."

    Home Assistant zet secties naast elkaar - op een breed scherm drie.
    Elke sectie is dus ongeveer een derde van het scherm. Daarbinnen
    stonden de tegels op 4 van de 12 kolommen, wat neerkomt op een
    NEGENDE van het scherm. Daar past "Accumodules" niet in, laat staan
    de statuszin eronder.

    De drie kolommen die je ziet zijn de secties zelf; binnen een sectie
    nog eens opdelen is dubbelop.
    """
    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())
    overzicht = next(v for v in data["views"] if v["title"] == "Overzicht")

    for sectie in overzicht["sections"]:
        for kaart in sectie.get("cards") or []:
            if kaart.get("type") == "heading" or "title-card" in str(
                kaart.get("type")
            ):
                continue
            kolommen = (kaart.get("grid_options") or {}).get("columns")
            assert kolommen == 12, (
                f"{kaart.get('secondary') or kaart.get('name')}: {kolommen} "
                "kolommen binnen een sectie - dat is een negende scherm"
            )


def test_the_status_sentences_may_wrap_again():
    """In v1.17.2 zijn ze op één regel gezet omdat de tegels smal waren.
    Met volle sectiebreedte is er ruimte, en een afgekapte zin zegt
    niets."""
    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())
    overzicht = next(v for v in data["views"] if v["title"] == "Overzicht")

    statustegels = [
        k
        for s in overzicht["sections"]
        for k in s.get("cards") or []
        if "samenvattingen" in str(k)
    ]

    assert statustegels
    for tegel in statustegels:
        assert tegel.get("multiline_secondary") is True


# --- v1.17.4: geen lege iconen --------------------------------------


def test_every_card_has_an_icon():
    """Gemeld met screenshot: de Airco-verwachting toonde een lege
    blauwe cirkel.

    De sensor heeft wél een icoon (`_attr_icon = "mdi:thermometer-lines"`)
    maar een mushroom-kaart neemt dat niet over als het veld `icon`
    ontbreekt - dan blijft er een lege cirkel staan. Dertien kaarten
    hadden dat.
    """
    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())

    zonder = []
    for view in data["views"]:
        for kaart in _kaarten(view):
            soort = str(kaart.get("type", ""))
            if "entity-card" not in soort and "template-card" not in soort:
                continue
            if not kaart.get("icon"):
                zonder.append(
                    f"{view['title']}: "
                    f"{kaart.get('name') or str(kaart.get('primary'))[:40]}"
                )

    assert not zonder, zonder


def test_the_icons_are_mdi():
    """Een icoonnaam zonder `mdi:` rendert niet."""
    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())

    for view in data["views"]:
        for kaart in _kaarten(view):
            icoon = kaart.get("icon")
            if not isinstance(icoon, str) or "{" in icoon:
                continue
            assert icoon.startswith("mdi:"), f"{view['title']}: {icoon}"
