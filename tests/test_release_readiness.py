"""Controles vóór een installatie (v1.9.6).

Gevraagd: "Wil je het nu nog 1 keer volledig zelf beoordelen zodat er
niets geen onvolkomenheden in zitten voor de volgende installatie?"

Deze controles waren tot nu toe handwerk. Ze horen bij elke run te
draaien, want juist vóór een installatie wil je niet dat iets afhangt van
of iemand eraan dacht.
"""
import json
import re
from pathlib import Path

import custom_components.energy_management_system as pkg

PAKKET = Path(pkg.__file__).parent
WORTEL = PAKKET.parent.parent


def _labels(bestand: str) -> set[str]:
    data = json.loads((PAKKET / bestand).read_text())
    gevonden: set[str] = set()

    def loop(o):
        if isinstance(o, dict):
            if "data" in o and isinstance(o["data"], dict):
                gevonden.update(o["data"])
            for x in o.values():
                loop(x)

    loop(data)
    return gevonden


def test_every_config_field_has_a_dutch_label():
    """Een veld zonder label toont de kale sleutel in het formulier -
    `water_total_usage_sensor_entity` in plaats van
    "Watermeterstand in liter". Acht velden hadden er geen.
    """
    const = (PAKKET / "const.py").read_text()
    flow = (PAKKET / "config_flow.py").read_text()
    velden = {
        sleutel
        for naam, sleutel in re.findall(
            r'^(CONF_[A-Z0-9_]+) = "([a-z0-9_]+)"', const, re.M
        )
        if naam in flow
    }

    ontbreekt = sorted(velden - _labels("translations/nl.json"))

    assert not ontbreekt, f"geen Nederlands label voor: {ontbreekt}"


def test_the_english_translation_is_complete():
    """Home Assistant valt terug op Engels; een gat daar geeft dezelfde
    kale sleutel."""
    nl = _labels("translations/nl.json")
    en = _labels("translations/en.json")

    assert not sorted(nl - en)


def test_the_version_is_consistent_everywhere():
    """De cachesleutel van de achtergrondtekening moet meebewegen met de
    versie, anders blijft een oude tekening in de browser hangen."""
    versie = json.loads((PAKKET / "manifest.json").read_text())["version"]
    dashboard = (PAKKET / "dashboard_template.yaml").read_text()

    # v3.17.0: de overzichtsplaat komt niet meer uit een BESTAND maar
    # live uit de sensor, dus er valt geen browsercache te omzeilen. De
    # cache-sleutel is daarmee overbodig geworden.
    assert "?v=" not in dashboard, (
        "de plaat wordt live opgebouwd; een cache-sleutel wijst op een "
        "achtergebleven statische afbeelding"
    )
    assert f"## v{versie}" in (WORTEL / "CHANGELOG.md").read_text()


def test_the_dashboard_copy_is_in_sync():
    """De kopie in `custom_components` is wat er wordt uitgerold; loopt
    die achter, dan installeer je een ander dashboard dan je test."""
    bron = (WORTEL / "dashboards" / "energy_management_system_dashboard.yaml")

    assert bron.read_text() == (PAKKET / "dashboard_template.yaml").read_text()


def test_the_svg_copy_is_in_sync():
    bron = WORTEL / "dashboards" / "energy_management_system_overview.svg"

    assert bron.read_text() == (PAKKET / "overview_background.svg").read_text()


def test_every_service_is_registered_and_documented():
    """Een dienst in services.yaml die niet geregistreerd is, verschijnt
    wel in de UI maar doet niets."""
    import yaml

    diensten = set(
        yaml.safe_load((PAKKET / "services.yaml").read_text())
    )
    init = (PAKKET / "__init__.py").read_text()

    niet_geregistreerd = sorted(d for d in diensten if d not in init)

    assert not niet_geregistreerd, niet_geregistreerd


def test_no_debugging_leftovers():
    """`print` en `breakpoint` horen niet in een integratie die in Home
    Assistant draait."""
    gevonden = []
    for bestand in PAKKET.glob("*.py"):
        for nummer, regel in enumerate(bestand.read_text().splitlines(), 1):
            kaal = regel.strip()
            if kaal.startswith("print(") or "breakpoint()" in kaal:
                gevonden.append(f"{bestand.name}:{nummer}")

    assert not gevonden, gevonden
