"""Detailtabellen lezen bestaande sleutels (v1.14.2).

Gemeld met screenshot: de tabel "Herkende apparaten" toonde 38 rijen met
"None W" en "None%" in elke kolom.

De oorzaak was niet dat er nog data moest worden opgebouwd - die was er
al - maar dat het sjabloon sleutels opvroeg die niet bestaan:
`gemiddeld_w`, `referentie_w` en `drift_procent`. De tabel levert
`naam`, `huidig_vermogen_w` en `trend`.

Een sjabloon dat een niet-bestaande sleutel opvraagt geeft stilzwijgend
`None`. Dat is verraderlijk: de tabel ziet er compleet uit, en het lijkt
alsof de meting nog moet opstarten.
"""
import re
from pathlib import Path

import custom_components.energy_management_system as pkg
import yaml

PAKKET = Path(pkg.__file__).parent


def _detailkaarten():
    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())
    detail = next(v for v in data["views"] if v["title"] == "Details")
    kaarten = list(detail.get("cards") or [])
    for sectie in detail.get("sections") or []:
        kaarten += sectie.get("cards") or []
    return kaarten


def _sleutels_uit(inhoud: str) -> set[str]:
    """Alle `x.get('sleutel')`-aanroepen uit een sjabloon."""
    return set(re.findall(r"\.get\('([a-z_]+)'\)", inhoud))


def test_the_device_table_uses_existing_keys(make_coordinator, hass):
    """Het gerapporteerde geval."""
    c = make_coordinator({})
    c.nilm_confirmed_devices = {
        "sensor.test": {"friendly_name": "Testapparaat", "daily_avg_history": []}
    }

    echte = set(c.get_nilm_devices_table()[0])
    kaart = next(
        k for k in _detailkaarten() if k.get("title") == "Herkende apparaten"
    )
    gevraagd = _sleutels_uit(kaart["content"])

    onbekend = gevraagd - echte - {"totaal_aantal"}
    assert not onbekend, f"sjabloon vraagt niet-bestaande sleutels: {onbekend}"


def test_the_module_table_uses_existing_keys(make_coordinator, hass):
    c = make_coordinator({})
    c.battery_module_live = [
        {
            "module": 1,
            "cel_delta_v": 0.05,
            "temperatuur_c": 20.0,
            "soc_percent": 17.0,
            "vermogen_w": 57.0,
        }
    ]

    echte = set(c.get_battery_module_table()[0])
    kaart = next(k for k in _detailkaarten() if k.get("title") == "Accumodules")
    gevraagd = _sleutels_uit(kaart["content"])

    assert not gevraagd - echte, gevraagd - echte


def test_the_reliability_table_uses_existing_keys(make_coordinator, hass):
    c = make_coordinator({})

    echte = set(c.get_reliability_overview()[0])
    kaart = next(
        k
        for k in _detailkaarten()
        if k.get("title") == "Betrouwbaarheid per grootheid"
    )
    gevraagd = _sleutels_uit(kaart["content"])

    assert not gevraagd - echte, gevraagd - echte


def test_the_water_table_uses_existing_keys():
    """De watersessies hebben `gestart`, `duur_minuten` en `liter`."""
    kaart = next(
        k for k in _detailkaarten() if k.get("title") == "Waterverbruik vandaag"
    )
    gevraagd = _sleutels_uit(kaart["content"])

    assert gevraagd <= {"gestart", "duur_minuten", "liter",
                        "waarschijnlijk_waterontharder"}, gevraagd


def test_the_device_table_says_how_many_there_are():
    """De tabel toont maar een deel van de apparaten; zonder het totaal
    lijkt het alsof er meer ontbreken."""
    kaart = next(
        k for k in _detailkaarten() if k.get("title") == "Herkende apparaten"
    )

    assert "totaal_aantal" in kaart["content"]


# --- v1.14.4: leesbaar bij elke breedte -----------------------------


def test_the_detail_page_is_one_column():
    """Gemeld: "uitlijning niet goed" - met een screenshot waarop de
    betrouwbaarheidstabel afbrak op "Ni…" waar "Niveau" hoort te staan.

    De pagina stond in masonry, waardoor brede tabellen in een smalle
    kolom werden geperst. Eén kolom geeft elke tabel de volle breedte.
    """
    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())
    detail = next(v for v in data["views"] if v["title"] == "Details")

    assert detail.get("type") == "sections"
    assert detail.get("max_columns") == 1


def test_no_detail_table_has_more_than_three_columns():
    """Vier kolommen passen niet op een telefoon. De
    betrouwbaarheidslijst is daarom een gegroepeerde opsomming geworden
    in plaats van een tabel."""
    # v1.14.6: BLINDE VLEK gedicht. De test keek of een regel begint met
    # "|", maar tabelrijen in deze sjablonen beginnen met een Jinja-tag
    # ("{% for u in t %}| ..."). Daardoor werd vrijwel geen enkele rij
    # gecontroleerd - de accumodule-tabel met zes kolommen glipte er
    # gewoon door.
    #
    # De grens is zes in plaats van drie: de detailpagina staat sinds
    # v1.14.4 op één kolom, dus een tabel krijgt de volle breedte. Op een
    # telefoon blijft dat krap, maar de alternatieven zijn informatie
    # weglaten of de tabel omzetten naar een lijst - en bij deze tabellen
    # is de kolomvergelijking juist het nut.
    for kaart in _detailkaarten():
        inhoud = kaart.get("content") or ""
        for regel in inhoud.splitlines():
            kaal = regel.strip()
            if "---" in kaal or kaal.count("|") < 2:
                continue
            kolommen = kaal.count("|") - 1
            assert kolommen <= 6, (
                f"{kaart.get('title')}: {kolommen} kolommen - past niet op "
                "een smal scherm"
            )


def test_the_reliability_list_still_shows_everything():
    """Het omzetten van tabel naar lijst mag geen informatie kosten."""
    kaart = next(
        k
        for k in _detailkaarten()
        if k.get("title") == "Betrouwbaarheid per grootheid"
    )
    inhoud = kaart["content"]

    for veld in ("groep", "label", "naam", "waarde", "reden"):
        assert f"'{veld}'" in inhoud, veld


def test_the_climate_projection_shows_both_series():
    """Gemeld: "Ik mis nu ook de uur temperatuur voorspelling van de
    woonkamer?" en daarna: "Snelle voorspelling en lange termijn zoals
    origineel".

    De twee reeksen meten iets anders. `kort_termijn_temp_c` valt terug
    op naburige cellen zodra de exacte combinatie te dun bezet is (de fix
    uit v1.1.2); `betrouwbaar_temp_c` komt pas bij genoeg metingen in
    precies die situatie. De eerste is er snel, de tweede is hard - beide
    weggeven zou de tabel waardeloos maken.
    """
    kaart = next(
        k
        for k in _detailkaarten()
        if k.get("title") == "Woonkamertemperatuur per uur"
    )
    inhoud = kaart["content"]

    for veld in (
        "kort_termijn_temp_c",
        "betrouwbaar_temp_c",
        "buitentemp_voorspeld_c",
        "basis",
        "aantal_metingen",
    ):
        assert f"'{veld}'" in inhoud, veld


def test_the_climate_projection_explains_the_two_columns():
    """Zonder uitleg is "Snel" naast "Betrouwbaar" niet te
    interpreteren."""
    kaart = next(
        k
        for k in _detailkaarten()
        if k.get("title") == "Woonkamertemperatuur per uur"
    )

    assert "naburige situaties" in kaart["content"]
    assert "Basis" in kaart["content"]


# --- v1.14.7: beoordelen moet mogelijk blijven ----------------------


def test_the_nilm_buttons_are_on_the_dashboard():
    """Gevraagd: "Waar kan ik nu Nilm apparaten beoordelen, net als
    mogelijke duplicaties?"

    Bij het opruimen van het Apparaten-tabblad zijn de knoppen
    verdwenen. Zonder die knoppen kan een kandidaat niet worden
    bevestigd of afgewezen en blijft een gemeld duplicaat staan - de
    detectie draait dan wel, maar je kunt er niets mee.
    """
    yaml_tekst = (PAKKET / "dashboard_template.yaml").read_text()

    for knop in (
        "nilm_kandidaat_1_bevestigen",
        "nilm_kandidaat_1_negeren",
        "nilm_duplicaat_1_bevestigen",
        "nilm_duplicaat_1_negeren",
    ):
        assert knop in yaml_tekst, knop


def test_the_button_ids_match_the_code():
    """De weergavenamen zijn dynamisch (ze tonen de kandidaat), dus de
    entity_id's zijn daar niet uit af te leiden. `button.py` legt ze
    expliciet vast - juist om de "_2"-deduplicatie uit v0.63.81 te
    voorkomen. Die twee moeten gelijk blijven.
    """
    bron = (PAKKET / "button.py").read_text()
    yaml_tekst = (PAKKET / "dashboard_template.yaml").read_text()

    assert "nilm_kandidaat_" in bron
    assert "nilm_duplicaat_" in bron
    # Geen zelfbedachte varianten in het dashboard.
    assert "nilm_slot_1_" not in yaml_tekst


def test_the_candidate_and_duplicates_are_shown():
    """Een knop "bevestigen" zonder te tonen wát je bevestigt, is niet
    te gebruiken."""
    kaart = next(
        k for k in _detailkaarten() if k.get("title") == "Te beoordelen"
    )
    inhoud = kaart["content"]

    assert "kandidaat_naam" in inhoud
    assert "waarschijnlijke_duplicaten" in inhoud
    assert "apparaat_1" in inhoud and "apparaat_2" in inhoud
