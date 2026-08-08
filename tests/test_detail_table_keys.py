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
    return detail["cards"]


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
