"""Compacte tabbladen: conclusie in plaats van tabel (v1.12.0).

Gemeld: "Ik vind de dashboards veel te druk, het is zoveel dat het niet
meer overzichtelijk is. Graag opruimen. Het de meeste info (tabellen)
graag in een zin weergeven of het betrouwbaar is of niet. Ik zie liever
iets verschijnen in meldingen als het niet correct is."

Terecht: er was steeds informatie bijgekomen zonder dat er ooit iets
afging. De onderbouwing blijft volledig beschikbaar in de
sensorattributen en de diagnostiek-export; alleen staat ze niet meer
standaard open.
"""
import re
from pathlib import Path

import custom_components.energy_management_system as pkg
import yaml

PAKKET = Path(pkg.__file__).parent


def _views():
    """Alle tabbladen behalve de detailpagina.

    v1.13.0: sinds alle tabbladen subviews zijn (ze staan niet meer in de
    tabbalk, je komt er via een tegel op Overzicht) kan er niet meer op
    `subview` gefilterd worden. Alleen "Details" is uitgezonderd: die
    bevat juist de tabellen die elders zijn weggehaald.
    """
    alle = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())["views"]
    return [v for v in alle if v["title"] != "Details"]


def _kaarten(view):
    k = list(view.get("cards") or [])
    for sectie in view.get("sections") or []:
        k += sectie.get("cards") or []
    return k


# --- geen grote tabellen meer ----------------------------------------


def test_no_large_tables_outside_the_overview():
    """Een markdown-tabel met veel regels is precies wat te druk werd.
    Overzicht en Meldingen zijn uitgezonderd: het eerste is de
    landingspagina, het tweede een bedieningspaneel.
    """
    for view in _views():
        # Financieel is uitgezonderd: daar ZIJN de bedragen de inhoud.
        # Een tabel met week-, maand- en jaarcijfers naast elkaar is
        # precies wat je van een financieel tabblad verwacht, en die in
        # een zin persen zou informatie kosten in plaats van ruis
        # besparen. Overzicht is de landingspagina, Meldingen een
        # bedieningspaneel.
        # v1.17.2: detailpagina's zijn juist BEDOELD voor tabellen -
        # dat is wat er achter de doorklik hoort te zitten. Deze regel
        # stamt uit v1.12.0, toen alles op één niveau stond en elke
        # tabel dus meteen in beeld kwam.
        if view["title"] in (
            "Overzicht",
            "Meldingen",
        ) or str(view.get("path", "")).startswith("detail-"):
            continue
        for kaart in _kaarten(view):
            inhoud = kaart.get("content") or ""
            rijen = len(re.findall(r"^\s*\|", inhoud, re.M))
            assert rijen <= 3, (
                f"{view['title']}: tabel met {rijen} regels - hoort een "
                "samenvattende zin te zijn"
            )


def test_the_trimmed_tabs_are_small():
    """Het doel was overzicht. Een tabblad met twintig kaarten haalt dat
    niet, hoe compact de kaarten ook zijn."""
    for view in _views():
        # v1.17.2: detailpagina's zijn juist BEDOELD voor tabellen -
        # dat is wat er achter de doorklik hoort te zitten. Deze regel
        # stamt uit v1.12.0, toen alles op één niveau stond en elke
        # tabel dus meteen in beeld kwam.
        if view["title"] in (
            "Overzicht",
            "Meldingen",
        ) or str(view.get("path", "")).startswith("detail-"):
            continue
        # v1.14.8: van 10 naar 20. De 24 ontbrekende sensoren zijn op
        # verzoek teruggezet op de verborgen tabbladen; de grens blijft
        # bestaan zodat een tabblad niet opnieuw onoverzichtelijk wordt,
        # maar hij hoort bij "details achter een tik", niet bij
        # "alleen samenvattingen".
        assert len(_kaarten(view)) <= 20, view["title"]


def test_every_tab_still_says_something():
    """Opruimen mag niet betekenen dat een tabblad leeg achterblijft."""
    for view in _views():
        assert _kaarten(view), view["title"]


# --- de samenvattende zinnen -----------------------------------------


def test_every_topic_has_a_sentence_and_a_level(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        RELIABILITY_LABELS,
    )

    c = make_coordinator({})

    for onderwerp, gegevens in c.get_topic_summaries().items():
        assert gegevens["zin"], onderwerp
        assert gegevens["niveau"] in RELIABILITY_LABELS, onderwerp


def test_a_sentence_is_actually_a_sentence(make_coordinator, hass):
    """Geen opsomming en geen tabel - dat was juist het probleem."""
    c = make_coordinator({})

    for onderwerp, gegevens in c.get_topic_summaries().items():
        zin = gegevens["zin"]
        assert "|" not in zin, onderwerp
        assert "\\n" not in zin, onderwerp


def test_the_weakest_link_determines_the_level(make_coordinator, hass):
    """Bij een onderwerp met meerdere metingen bepaalt de zwakste of je
    erop kunt varen - het gemiddelde zou een probleem verbergen."""
    from custom_components.energy_management_system.const import (
        RELIABILITY_UNRELIABLE,
    )

    c = make_coordinator({})
    c.nilm_confirmed_devices = {
        "sensor.a": {"friendly_name": "Koelkast", "anomaly_detected": True},
        "sensor.b": {"friendly_name": "Vriezer", "anomaly_detected": False},
    }

    assert c.get_topic_summaries()["apparaten"]["niveau"] == RELIABILITY_UNRELIABLE


def test_a_problem_is_named_in_the_sentence(make_coordinator, hass):
    """"Er is iets mis" zonder te zeggen wát, dwingt je alsnog te gaan
    zoeken - precies wat we wilden vermijden."""
    c = make_coordinator({})
    c.nilm_confirmed_devices = {
        "sensor.a": {"friendly_name": "Koelkast schuur", "anomaly_detected": True}
    }

    assert "Koelkast schuur" in c.get_topic_summaries()["apparaten"]["zin"]


# --- de details blijven bereikbaar -----------------------------------


def test_the_detail_is_still_in_the_diagnostics_export():
    """De tabellen zijn weg van het scherm, niet uit de gegevens."""
    bron = (PAKKET / "diagnostics.py").read_text()

    for onderdeel in (
        "water_session_history",
        "nilm",
        "battery_module",
        "reliability_overview",
        "decision_log",
    ):
        assert onderdeel in bron, onderdeel


def test_the_summaries_are_on_a_sensor():
    """Zonder attribuut kan het dashboard de zinnen niet tonen."""
    bron = (PAKKET / "sensor.py").read_text()

    assert "get_topic_summaries" in bron


# --- v1.12.1: Overzicht past op één scherm --------------------------


def test_the_overview_has_little_prose():
    """Gemeld: "Ik wil eigenlijk niet hoeven scrollen." Vier
    tekstblokken van samen ~2700 tekens waren de grootste veroorzaker -
    waaronder een muur met alle aandachtspunten uitgeschreven.
    """
    overzicht = next(v for v in _views() if v["title"] == "Overzicht")

    tekens = sum(
        len(kaart.get("content") or "")
        for sectie in overzicht["sections"]
        for kaart in sectie.get("cards") or []
    )

    assert tekens < 1600, f"{tekens} tekens tekst op de landingspagina"


def test_the_attention_points_are_readable_on_the_overview():
    """v1.14.5, gemeld: "Ik wil toch weer meer informatie op de
    dashboard... Ik mis teveel om nu goed te kunnen beoordelen."

    In v1.12.1 werden de aandachtspunten teruggebracht tot een telling.
    Dat bleek te ver: een getal zegt niet WAT er aan de hand is, dus moest
    je alsnog doorklikken om te weten of er iets van je verwacht werd.

    Ze staan nu weer uitgeschreven, met de informatieve regels erbij en
    de doorklik naar de details intact.
    """
    overzicht = next(v for v in _views() if v["title"] == "Overzicht")
    kaarten = [
        k
        for sectie in overzicht["sections"]
        for k in sectie.get("cards") or []
        if "aandachtspunten" in str(k)
    ]

    assert kaarten, "geen aandachtspunten-kaart gevonden"
    uitgeschreven = [k for k in kaarten if "for punt in p" in str(k)]
    assert uitgeschreven, "de punten staan niet uitgeschreven"
    assert any("informatief" in str(k) for k in uitgeschreven)



def test_the_overview_has_no_detail_sections():
    """Uitklaplijsten met onderliggende sensoren horen niet op een
    landingspagina; die staan in more-info en de diagnostiek-export."""
    overzicht = next(v for v in _views() if v["title"] == "Overzicht")

    koppen = [
        k.get("heading", "")
        for sectie in overzicht["sections"]
        for k in sectie.get("cards") or []
        if k.get("type") == "heading"
    ]

    assert not any("detail" in k.lower() for k in koppen), koppen


# --- v1.12.2: geen tabbladen voor één kaart -------------------------


def test_no_tab_is_too_thin():
    """Gemeld: "Sommige tabbladen zijn nu zo leeg dat het beter is deze
    samen te voegen op 1 tabblad."

    Na het opruimen hielden Accumodules, Apparaten en Zelflerend elk nog
    één kaart over. Een tabblad voor één zin kost meer aandacht dan het
    oplevert - je moet ernaartoe klikken om één regel te lezen.

    Visueel is uitgezonderd: dat is één schermvullende plattegrond.
    """
    for view in _views():
        # v1.17.0: detailpagina's mogen juist klein zijn - één onderwerp
        # per pagina was het doel. De regel geldt voor de TABBLADEN, waar
        # een pagina met één kaart betekent dat je ernaartoe klikt voor
        # één regel.
        if view["title"] == "Visueel" or str(view.get("path", "")).startswith(
            "detail-"
        ):
            continue
        assert len(_kaarten(view)) >= 3, (
            f"{view['title']}: {len(_kaarten(view))} kaart(en) - hoort "
            "samengevoegd te worden"
        )


def test_each_topic_has_its_own_page():
    """v1.17.1: het samengevoegde tabblad "Systeem" met koppen per
    onderwerp is vervangen door een pagina PER onderwerp. De garantie is
    dezelfde - elk onderwerp is apart vindbaar - maar nu als eigen
    pagina in plaats van een kop op een gedeeld tabblad."""
    titels = {v["title"] for v in _views()}

    for onderwerp in ("Accu", "Apparaten", "Water", "Klimaat"):
        assert onderwerp in titels, onderwerp



def test_each_heading_explains_what_it_shows():
    """Een kop "Zelflerend" alleen zegt nog niet wát je ziet."""
    systeem = next(v for v in _views() if v["title"] == "Apparaten")

    for kaart in _kaarten(systeem):
        if "title-card" in str(kaart.get("type")):
            assert kaart.get("subtitle"), kaart.get("title")


# --- v1.12.4: het principe overal ------------------------------------


def test_every_tile_can_be_opened():
    """Gemeld: "Misschien dit nu voor alles toepassen (dus sumiere
    informatie op de dashboards) en wanneer meer informatie gewenst is
    dit door middel van op de card klikken zichtbaar maken?"

    Dat werkt alleen als élke tegel ook echt te openen is. Een kaart die
    de conclusie toont maar niet doorklikt, laat je met de vraag zitten
    zonder een manier om hem te beantwoorden.
    """
    for view in _views():
        if view["title"] in ("Visueel", "Meldingen"):
            continue
        for kaart in _kaarten(view):
            if "template-card" not in str(kaart.get("type")):
                continue
            if not kaart.get("entity"):
                continue
            assert kaart.get("tap_action"), (
                f"{view['title']}: tegel '{str(kaart.get('primary'))[:40]}' "
                "toont een conclusie maar is niet aanklikbaar"
            )


def test_no_tab_is_a_wall_of_text():
    """De tabbladen moeten leesbaar blijven zonder te scrollen. Meldingen
    is uitgezonderd: dat is een bedieningspaneel met tweeëntwintig
    schakelaars."""
    for view in _views():
        if view["title"] == "Meldingen":
            continue
        tekens = sum(len(k.get("content") or "") for k in _kaarten(view))
        # v1.14.5: van 800 naar 1400. Bewust ruimer: met alleen
        # samenvattingen viel er te weinig te beoordelen. De grens blijft
        # bestaan zodat een tabblad niet opnieuw een muur tekst wordt -
        # het gaat om genoeg, niet om alles.
        assert tekens < 1400, f"{view['title']}: {tekens} tekens tekst"


def test_the_financial_tab_uses_tiles_not_tables():
    """De drie grote tabellen (afrekening, week/maand/jaar,
    maandoverzicht) waren samen ruim 4000 tekens - het laatste bastion
    van de oude opzet."""
    # v1.17.1: "Financieel" heet nu "Kosten".
    financieel = next(v for v in _views() if v["title"] == "Kosten")

    tekens = sum(len(k.get("content") or "") for k in _kaarten(financieel))

    assert tekens == 0, f"{tekens} tekens tabeltekst op Financieel"


# --- v1.13.1: koppen blijven bij hun kaarten -------------------------


def test_tabs_with_several_headings_use_sections():
    """Gemeld: "De zelflerend titel staat nog niet correct op de
    pagina."

    De standaard masonry-indeling verdeelt kaarten over kolommen zonder
    te weten welke kop erbij hoort. Op Systeem stond "Zelflerend" links
    en de bijbehorende kaart rechts, onder een andere kop.

    `type: sections` houdt elk groepje bij elkaar.
    """
    alle = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())

    for view in alle["views"]:
        kaarten = view.get("cards") or []
        koppen = [k for k in kaarten if "title-card" in str(k.get("type"))]
        assert len(koppen) <= 1, (
            f"{view['title']}: {len(koppen)} koppen in een masonry-indeling "
            "- gebruik `type: sections` zodat elke kop bij zijn kaarten "
            "blijft"
        )


def test_no_section_is_only_a_heading():
    """Een sectie met alleen een kop en geen kaarten toont een titel
    zonder inhoud."""
    alle = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())

    for view in alle["views"]:
        for sectie in view.get("sections") or []:
            kaarten = sectie.get("cards") or []
            inhoud = [
                k
                for k in kaarten
                if k.get("type") != "heading"
                and "title-card" not in str(k.get("type"))
            ]
            assert inhoud, f"{view['title']}: sectie zonder inhoud"


def test_the_overview_shows_a_status_per_topic():
    """v1.14.5: de statuszinnen stonden op vier verschillende verborgen
    tabbladen, waardoor je moest klikken om te weten óf er iets aan de
    hand was - precies de verkeerde kant op. De conclusie hoort op het
    beginscherm, het detail achter een tik."""
    overzicht = next(v for v in _views() if v["title"] == "Overzicht")
    kaarten = [
        k for sectie in overzicht["sections"] for k in sectie.get("cards") or []
    ]

    koppen = [k.get("heading") for k in kaarten if k.get("type") == "heading"]
    assert "Status per onderwerp" in koppen

    onderwerpen = {
        "accumodules",
        "apparaten",
        "zelflerend",
        "financieel",
        "klimaat",
        "water",
        "kwaliteit",
    }
    for onderwerp in onderwerpen:
        assert any(
            f"'{onderwerp}'" in str(k) and "samenvattingen" in str(k)
            for k in kaarten
        ), onderwerp


def test_the_status_tiles_still_drill_down():
    """Meer informatie op het beginscherm mag de doorklik niet
    vervangen: de zin is de conclusie, de onderbouwing blijft één tik
    weg."""
    overzicht = next(v for v in _views() if v["title"] == "Overzicht")

    for sectie in overzicht["sections"]:
        for kaart in sectie.get("cards") or []:
            if "samenvattingen" not in str(kaart):
                continue
            actie = kaart.get("tap_action") or {}
            assert actie.get("action") == "navigate", kaart.get("primary")
            # v1.17.0: elke tegel wijst naar zijn eigen onderwerp-pagina.
            assert "/detail-" in actie.get("navigation_path", ""), kaart.get(
                "primary"
            )


def test_every_sensor_appears_somewhere_on_the_dashboard():
    """v1.14.8, gevraagd: "Misschien alles wat we vanmorgen hebben
    verwijderd qua dashboards maar weer terug zetten?"

    Bij het opruimen bleken 24 van de 55 sensoren nergens meer te staan -
    veel meer dan de drie die opvielen. Een sensor die de integratie wel
    berekent maar die je nergens ziet, is verspilde moeite: hij kost
    rekentijd en levert niets op.

    Deze test vangt dat bij de bron, zodat een volgende opruimronde niet
    stilletjes informatie laat verdwijnen.
    """
    import re
    import unicodedata

    def slug(naam: str) -> str:
        tekst = unicodedata.normalize("NFKD", naam).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "_", tekst.lower()).strip("_")

    namen = re.findall(
        r'_attr_name = "([^"]+)"', (PAKKET / "sensor.py").read_text()
    )
    dashboard = (PAKKET / "dashboard_template.yaml").read_text()

    # Home Assistant kent de entity_id toe bij de EERSTE aanmaak en laat
    # die daarna ongemoeid, ook als de weergavenaam verandert. Deze
    # sensoren heten inmiddels anders dan hun entity_id - dezelfde
    # uitzondering die in v1.6.4 al is vastgelegd voor
    # `test_dashboard_entity_references`.
    HISTORISCH = {
        "Piekvermogen (netimport)": "piekvermogen",
        "Advies-gereedheid (10 modules)": "advies_gereedheid_8_modules",
    }

    ontbreekt = sorted(
        n
        for n in namen
        if slug(n) not in dashboard
        and HISTORISCH.get(n, slug(n)) not in dashboard
    )

    assert not ontbreekt, (
        f"{len(ontbreekt)} sensoren staan nergens op het dashboard: "
        f"{ontbreekt}"
    )
