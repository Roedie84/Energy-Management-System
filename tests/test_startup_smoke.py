"""Start de integratie nog op? (v2.0.2)

Gevraagd: "Tevens wil ik zien dat de integratie nog opstart (na een
herstart van HA)."

Terecht na drie dagen met tientallen wijzigingen. De testsuite draait
`async_setup()` al, maar een aantal dingen wordt pas bij een échte start
aangeraakt: de configuratiestroom bouwt zijn formulier, Home Assistant
leest de vertalingen en het manifest, en het dashboardbestand wordt
ingelezen.

Een fout in een van die vier laat de integratie niet laden, of laat hem
laden zonder dat je hem kunt instellen - en geen van de bestaande tests
zou dat merken.
"""
import json
from pathlib import Path

import custom_components.energy_management_system as pkg

PAKKET = Path(pkg.__file__).parent
WORTEL = PAKKET.parent.parent


def test_every_module_imports():
    """Een ontbrekende constante of een tikfout in een import laat de
    integratie helemaal niet laden."""
    import importlib

    for naam in (
        "const",
        "coordinator",
        "config_flow",
        "sensor",
        "switch",
        "button",
        "diagnostics",
        "solar_forecast",
    ):
        importlib.import_module(
            f"custom_components.energy_management_system.{naam}"
        )


def test_the_config_form_can_be_built(hass):
    """Bij elk nieuw veld kan hier iets misgaan - een verkeerde selector
    of een standaardwaarde die niet bij het type past. Dan laadt de
    integratie wel, maar kun je hem niet instellen."""
    from custom_components.energy_management_system import config_flow

    schema = config_flow._schema({})

    assert schema is not None
    assert len(schema.schema) > 20


def test_the_form_survives_an_existing_configuration(hass):
    """En met bestaande waarden erin - dat is het pad na een herstart."""
    from custom_components.energy_management_system import config_flow
    from custom_components.energy_management_system.const import (
        CONF_CONTRACT_START_DATE,
        CONF_PRESENCE_ABSENCE_MINUTES,
    )

    schema = config_flow._schema(
        {
            CONF_CONTRACT_START_DATE: "2026-04-01",
            CONF_PRESENCE_ABSENCE_MINUTES: 20,
        }
    )

    assert schema is not None


def test_the_translations_are_valid_json():
    """Home Assistant leest deze bij het laden; een komma te veel en de
    integratie start niet."""
    for taal in ("nl", "en"):
        pad = PAKKET / "translations" / f"{taal}.json"
        data = json.loads(pad.read_text())
        assert data


def test_every_config_field_has_a_dutch_label():
    """Een veld zonder omschrijving is niet in te vullen."""
    import re

    bron = (PAKKET / "config_flow.py").read_text()
    vertalingen = json.loads((PAKKET / "translations" / "nl.json").read_text())
    tekst = json.dumps(vertalingen, ensure_ascii=False)

    velden = set(re.findall(r"vol\.Optional\(\s*(CONF_\w+)", bron))
    velden |= set(re.findall(r"vol\.Required\(\s*(CONF_\w+)", bron))

    from custom_components.energy_management_system import const

    ontbreekt = [
        naam
        for naam in sorted(velden)
        if getattr(const, naam, None) and f'"{getattr(const, naam)}"' not in tekst
    ]

    assert not ontbreekt, f"geen Nederlandse omschrijving voor: {ontbreekt}"


def test_the_manifest_is_valid():
    manifest = json.loads((PAKKET / "manifest.json").read_text())

    for sleutel in ("domain", "name", "version", "documentation", "codeowners"):
        assert manifest.get(sleutel), sleutel


def test_the_services_file_is_valid():
    import yaml

    diensten = yaml.safe_load((PAKKET / "services.yaml").read_text())

    assert diensten
    for naam, beschrijving in diensten.items():
        assert "name" in beschrijving or "description" in beschrijving, naam


def test_the_dashboard_parses():
    """Wordt bij elke start naar de configuratiemap gekopieerd en door
    Home Assistant ingelezen."""
    import yaml

    data = yaml.safe_load((PAKKET / "dashboard_template.yaml").read_text())

    assert data["views"]
    for view in data["views"]:
        assert view.get("title"), view.get("path")


def test_the_diagnostics_reach_every_attribute_they_name(hass, make_coordinator):
    """De diagnostiek noemt attributen bij naam. Bestaat er één niet, dan
    faalt het downloaden - en dat merk je pas op het moment dat je hem
    nodig hebt."""
    import re

    bron = (PAKKET / "diagnostics.py").read_text()
    c = make_coordinator({})

    ontbreekt = [
        naam
        for naam in sorted(set(re.findall(r"coordinator\.(\w+)", bron)))
        if not hasattr(c, naam)
    ]

    assert not ontbreekt, ontbreekt


def test_a_full_startup_runs_through(hass, make_coordinator):
    """De echte opstartronde met een realistische configuratie.

    Dit is wat er bij een herstart van Home Assistant gebeurt: de
    coordinator wordt gebouwd, de bewaarde toestand teruggezet, de
    geschiedenis ingelezen en de tick opgestart.
    """
    import asyncio

    from custom_components.energy_management_system.const import (
        CONF_CONTRACT_START_DATE,
        CONF_PRESENCE_ABSENCE_MINUTES,
        CONF_PRICE_SENSOR,
        CONF_PV_ENERGY_SENSOR,
    )

    c = make_coordinator(
        {
            # De prijssensor is verplicht; zonder deze laadt de
            # integratie terecht niet.
            CONF_PRICE_SENSOR: "sensor.zonneplan_prijs",
            CONF_CONTRACT_START_DATE: "2026-04-01",
            CONF_PRESENCE_ABSENCE_MINUTES: 20,
            CONF_PV_ENERGY_SENSOR: "sensor.pv_totaal",
        }
    )

    asyncio.run(c.async_setup())

    # En een volledige beslisronde erna.
    asyncio.run(c.async_update())

    assert c.last_successful_update is not None


def test_the_first_tick_produces_a_readable_state(hass, make_coordinator):
    """Een integratie die laadt maar niets toont, is net zo stuk."""
    import asyncio

    from custom_components.energy_management_system.const import (
        CONF_PRICE_SENSOR,
    )

    c = make_coordinator({CONF_PRICE_SENSOR: "sensor.zonneplan_prijs"})
    asyncio.run(c.async_setup())
    asyncio.run(c.async_update())

    for functie in (
        c.get_consistency_checks,
        c.get_period_overview,
        c.get_self_consumption_overview,
        c.get_reserve_margin_overview,
        c.get_sun_position_check,
        c.get_outdoor_sensor_check,
        c.get_aging_drivers,
        c.get_fallback_overview,
    ):
        functie()
