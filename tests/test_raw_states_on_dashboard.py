"""Geen rauwe toestanden op het dashboard (v1.15.9).

Gemeld met screenshot: "Gesimuleerde actie: Onbekend", "Energie-check:
Onbekend" en "Accubescherming: 1600.0".

Drie verschillende problemen met dezelfde oorzaak - de sensortoestand
werd ongewijzigd getoond:

- "Onbekend" leest als een storing, terwijl het meestal betekent dat een
  onderdeel simpelweg niet actief is;
- de energie-check levert Engelse waarden (`enough_to_postpone`) terwijl
  de rest van het dashboard Nederlands is;
- "1600.0" is een getal zonder eenheid - 1600 wat?
"""
import re
from pathlib import Path

import custom_components.energy_management_system as pkg
import yaml

PAKKET = Path(pkg.__file__).parent


def _kaarten():
    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())
    alle = []
    for view in data["views"]:
        kaarten = list(view.get("cards") or [])
        for sectie in view.get("sections") or []:
            kaarten += sectie.get("cards") or []
        for kaart in list(kaarten):
            kaarten += kaart.get("cards") or []
        alle += kaarten
    return alle


def _kaart_voor(sleutel: str) -> dict:
    return next(k for k in _kaarten() if sleutel in str(k.get("entity", "")))


# --- de drie gerapporteerde gevallen ---------------------------------


def test_the_simulation_explains_it_is_not_running():
    kaart = _kaart_voor("simulated_action")

    assert "simulatie draait niet" in str(kaart)


def test_the_bridge_check_is_translated():
    """`enough_to_postpone` zegt niets als je de code niet kent."""
    kaart = _kaart_voor("energy_bridge_check")
    tekst = str(kaart)

    assert "genoeg om uit te stellen" in tekst
    assert "bijladen nodig" in tekst
    assert "nog niet beoordeeld" in tekst


def test_the_battery_protection_has_a_unit():
    """"1600.0" is een getal zonder betekenis."""
    kaart = _kaart_voor("battery_protection")

    assert "W ontlaadgrens" in str(kaart)
    assert "geen grens actief" in str(kaart)


# --- borging ---------------------------------------------------------


def test_no_card_shows_an_english_state():
    """Engelse sensorwaarden horen vertaald te worden voordat ze op een
    Nederlands dashboard verschijnen."""
    yaml_tekst = (PAKKET / "dashboard_template.yaml").read_text()

    for engels in ("enough_to_postpone", "top_up_needed"):
        # Mag alleen voorkomen als vergelijking, niet als weergave.
        for treffer in re.finditer(re.escape(engels), yaml_tekst):
            omgeving = yaml_tekst[
                max(0, treffer.start() - 60) : treffer.start()
            ]
            assert "==" in omgeving, (
                f"{engels} wordt getoond in plaats van vergeleken"
            )


def test_these_three_cards_are_template_cards():
    """Een entity-card toont de rauwe toestand; alleen een
    template-card kan hem vertalen of van een eenheid voorzien."""
    for sleutel in (
        "simulated_action",
        "energy_bridge_check",
        "battery_protection",
    ):
        kaart = _kaart_voor(sleutel)
        assert "template-card" in str(kaart.get("type")), sleutel


# --- v1.16.0: het komende schema ------------------------------------


def test_the_schedule_tile_shows_blocks_not_a_count():
    """Gemeld: "Die komend schema is inderdaad ook raar."

    De tegel toonde de TOESTAND van de sensor, en dat is het aantal
    geplande kwartieren - "96" zegt niets. De bruikbare informatie zit in
    het attribuut `transitions`: de blokken met begintijd en modus.
    """
    kaart = _kaart_voor("upcoming_schedule")
    tekst = str(kaart)

    assert "transitions" in tekst
    assert "blok(ken) gepland" in tekst
    assert "nog geen schema" in tekst


def test_the_schedule_tile_names_the_current_mode():
    """"3 blokken gepland" is nog steeds een getal; je wilt weten wat de
    accu nú doet en tot wanneer."""
    kaart = _kaart_voor("upcoming_schedule")

    assert "Nu {{ t[0].get('mode') }}" in str(kaart)


def test_the_full_schedule_is_on_the_detail_page():
    """Het verloop over de dag laat zich niet in een tegel vangen."""
    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())
    detail = next(v for v in data["views"] if v["title"] == "Details")
    kaarten = [k for s in detail["sections"] for k in s.get("cards") or []]

    kaart = next(k for k in kaarten if k.get("title") == "Komend schema")

    for veld in ("start", "end", "mode", "max_price_per_kwh"):
        assert f"'{veld}'" in kaart["content"], veld


# --- v1.16.1: "Onbekend" dat geen storing is ------------------------


def test_the_bias_explains_why_it_is_empty():
    """Gemeld: "Bias ook kapot?" bij "PV-voorspelling bias: Onbekend".

    Niet kapot: die sensor toont de bias voor HET HUIDIGE UUR, en buiten
    de daglichturen is die er niet. Correct gedrag, maar "Onbekend" leest
    als een storing - zeker naast een kaart die wél een waarde toont.
    """
    kaart = _kaart_voor("pv_hourly_forecast_bias")
    tekst = str(kaart)

    assert "buiten daglichturen" in tekst
    assert "uren geleerd" in tekst


def test_the_bias_card_uses_a_real_attribute():
    """Ik had `profiel` verzonnen; het attribuut heet
    `profile_confident`. Een sjabloon dat een niet-bestaand attribuut
    opvraagt geeft stilzwijgend niets terug - de kaart ziet er dan
    correct uit terwijl de telling ontbreekt."""
    kaart = _kaart_voor("pv_hourly_forecast_bias")
    bron = (PAKKET / "sensor.py").read_text()

    assert "'profile_confident'" in str(kaart)
    assert '"profile_confident":' in bron
    assert "'profiel'" not in str(kaart)


def test_every_requested_attribute_exists_in_the_code():
    """Borging: elk attribuut dat het dashboard opvraagt, moet ergens in
    sensor.py worden aangeboden. Dat vangt verzonnen namen bij de bron -
    dit is vandaag de derde keer dat een verzonnen attribuut of
    entity_id een kaart stil liet falen.
    """
    yaml_tekst = (PAKKET / "dashboard_template.yaml").read_text()
    # Attributen komen niet alleen van sensoren: schakelaars, knoppen en
    # de coordinator leveren er ook. Alleen in sensor.py kijken gaf zeven
    # valse treffers.
    bron = "".join(
        (PAKKET / naam).read_text()
        for naam in ("sensor.py", "switch.py", "button.py", "coordinator.py")
    )

    gevraagd = set(re.findall(r"state_attr\([^,]+,\s*'([a-z0-9_]+)'\)", yaml_tekst))
    aangeboden = set(re.findall(r'"([a-z0-9_]+)":', bron))
    aangeboden |= set(re.findall(r"\*\*self\._coordinator\.(\w+)", bron))
    # Attributen die Home Assistant zelf toevoegt.
    aangeboden |= {"friendly_name", "unit_of_measurement", "device_class"}

    ontbreekt = sorted(gevraagd - aangeboden)

    assert not ontbreekt, f"dashboard vraagt onbekende attributen: {ontbreekt}"
