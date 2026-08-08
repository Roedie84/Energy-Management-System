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
    return yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())["views"]


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
        if view["title"] in ("Overzicht", "Meldingen", "Financieel"):
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
        if view["title"] in ("Overzicht", "Meldingen", "Financieel"):
            continue
        assert len(_kaarten(view)) <= 10, view["title"]


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


def test_the_attention_card_is_a_count_not_a_wall():
    """De aandachtspunten stonden volledig uitgeschreven; nu een telling
    met een verwijzing. De inhoud zelf komt als melding binnen - dat was
    het uitgangspunt."""
    overzicht = next(v for v in _views() if v["title"] == "Overzicht")
    # v1.12.3: het is een template-card geworden in plaats van markdown,
    # zodat hij aanklikbaar is - de tekst verwees naar "de statuskaart"
    # terwijl die in v1.12.1 was weggehaald. De inhoud zit nu in
    # `primary`/`secondary` in plaats van in `content`.
    kaarten = [
        k
        for sectie in overzicht["sections"]
        for k in sectie.get("cards") or []
        if "aandachtspunten" in str(k)
    ]

    assert kaarten, "geen aandachtspunten-kaart gevonden"
    for kaart in kaarten:
        plat = str(kaart)
        assert "for punt in punten" not in plat
        assert "aandachtspunt(en)" in plat
        # Aanklikbaar, anders is "tik voor details" een loze verwijzing.
        assert kaart.get("tap_action", {}).get("action") == "more-info"


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
        if view["title"] == "Visueel":
            continue
        assert len(_kaarten(view)) >= 3, (
            f"{view['title']}: {len(_kaarten(view))} kaart(en) - hoort "
            "samengevoegd te worden"
        )


def test_the_merged_tab_labels_each_topic():
    """Zonder tabbladnaam is niet meer af te leiden waar een zin over
    gaat, dus elk onderwerp krijgt een kop."""
    systeem = next(v for v in _views() if v["title"] == "Systeem")
    koppen = [
        k.get("title")
        for k in _kaarten(systeem)
        if "title-card" in str(k.get("type"))
    ]

    for onderwerp in ("Accumodules", "Apparaten", "Zelflerend"):
        assert onderwerp in koppen, onderwerp


def test_each_heading_explains_what_it_shows():
    """Een kop "Zelflerend" alleen zegt nog niet wát je ziet."""
    systeem = next(v for v in _views() if v["title"] == "Systeem")

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
        assert tekens < 800, f"{view['title']}: {tekens} tekens tekst"


def test_the_financial_tab_uses_tiles_not_tables():
    """De drie grote tabellen (afrekening, week/maand/jaar,
    maandoverzicht) waren samen ruim 4000 tekens - het laatste bastion
    van de oude opzet."""
    financieel = next(v for v in _views() if v["title"] == "Financieel")

    tekens = sum(len(k.get("content") or "") for k in _kaarten(financieel))

    assert tekens == 0, f"{tekens} tekens tabeltekst op Financieel"
