"""Tijdweergave in de klimaattabel (v1.17.7).

Gemeld: "Tevens de tijdsaanduiding incorrect in deze tabel" - met een
screenshot waarop elke rij "2026-08-09T11:00:00+02:00" toonde.

Dat is de rauwe ISO-tijdstempel; alleen het uur is nodig. De kolom was
daardoor breder dan de rest van de tabel samen.

Onderweg viel iets tweeds op: de kolom "Betrouwbaar" stond op alle uren
op 22,0 °C terwijl het buiten van 26,7 naar 31,1 liep. Dat is bewust
gedrag - bij te weinig metingen wordt de huidige temperatuur aangehouden
in plaats van een verandering te gokken - maar dat was uit de tabel niet
af te lezen.
"""
from pathlib import Path

import custom_components.energy_management_system as pkg
import yaml

PAKKET = Path(pkg.__file__).parent


def _kaart():
    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())
    klimaat = next(v for v in data["views"] if v["path"] == "detail-klimaat")
    kaarten = [k for s in klimaat["sections"] for k in s.get("cards") or []]
    return next(
        k for k in kaarten if "Woonkamertemperatuur per uur" in str(k.get("title"))
    )


# --- de tijd ---------------------------------------------------------


def test_only_the_hour_is_shown():
    inhoud = _kaart()["content"]

    assert "timestamp_custom('%H:%M')" in inhoud


def test_no_raw_timestamp_remains():
    """`{{ u.get('tijd') }}` toont de hele ISO-string."""
    inhoud = _kaart()["content"]

    assert "{{ u.get('tijd') }}" not in inhoud


def test_a_missing_time_does_not_break_the_row():
    """Zonder terugval zou een ontbrekende tijd de hele tabel laten
    falen."""
    inhoud = _kaart()["content"]

    assert "if u.get('tijd') else '?'" in inhoud


def test_no_other_card_shows_a_raw_timestamp():
    """Dezelfde fout kan in elke tabel met tijden zitten."""
    import re

    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())
    ruw = []
    for view in data["views"]:
        kaarten = list(view.get("cards") or [])
        for sectie in view.get("sections") or []:
            kaarten += sectie.get("cards") or []
        for kaart in kaarten:
            inhoud = kaart.get("content") or ""
            ruw += re.findall(
                r"\{\{ [a-z]\.get\('(?:tijd|gestart|start|end|moment)'\) \}\}",
                inhoud,
            )

    assert not ruw, ruw


# --- de vlakke kolom -------------------------------------------------


def test_the_flat_column_is_explained():
    """"Betrouwbaar" op alle uren gelijk ziet eruit als een fout,
    terwijl het een bewuste keuze is: liever geen verandering
    voorspellen dan een verkeerde."""
    inhoud = _kaart()["content"]

    assert "op alle uren gelijk" in inhoud
    assert "liever geen verandering voorspellen dan een verkeerde" in inhoud


def test_the_sample_count_is_visible():
    """Met het aantal metingen erbij is te zien waarom een uur op de
    terugval valt."""
    inhoud = _kaart()["content"]

    assert "aantal_metingen" in inhoud


def test_both_series_are_still_shown():
    """De correctie mag geen informatie kosten."""
    inhoud = _kaart()["content"]

    for veld in (
        "kort_termijn_temp_c",
        "betrouwbaar_temp_c",
        "buitentemp_voorspeld_c",
        "basis",
    ):
        assert veld in inhoud, veld
