"""Structuurscan 15 en de configuratiecontrole (v3.56.0).

Gevraagd: "Alles wat vandaag gecorrigeerd is had volgens mij uit een
diagnostiek kunnen komen, dus deze verder uitbreiden zodat we samen de
integratie telkens beter maken."

Terecht. Van de correcties van 28 augustus stonden er drie al in de
export, maar niet op een plek waar je ze zou zien:

- `sensor.zendure_manager_available_kwh` gaf al dagen 0,00 kWh terwijl
  de accu vol zat
- `wear_cost_overview` stond op null, met de reden verstopt
- de laadstand kwam uit een veld dat maar op drie plaatsen wordt gezet

En de vierde was een valkuil die vier-en-dertig keer in de code stond:

    config.get(CONF_BATTERY_CYCLE_LIFE, DEFAULT_BATTERY_CYCLE_LIFE)

De standaard geldt alleen als de SLEUTEL ontbreekt. Home Assistant slaat
een leeg veld op MET de waarde None, en dan komt de standaard er nooit
aan te pas. Gevolg: geen slijtagekosten, en dat getal zit in vrijwel elke
afweging.
"""
import ast
import re
from pathlib import Path

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system.const import (
    CONF_BATTERY_CYCLE_LIFE,
    CONF_SOC_SENSOR,
    DEFAULT_BATTERY_CYCLE_LIFE,
)

MAP = Path(pkg.__file__).parent


# --- de helper -------------------------------------------------------


def test_a_stored_none_still_gets_the_default(make_coordinator, hass):
    """De aanleiding: cyclusaantal None, dus geen slijtageberekening."""
    c = make_coordinator({CONF_BATTERY_CYCLE_LIFE: None})

    assert c.instelling(CONF_BATTERY_CYCLE_LIFE, DEFAULT_BATTERY_CYCLE_LIFE) == (
        DEFAULT_BATTERY_CYCLE_LIFE
    )


def test_a_missing_key_gets_the_default(make_coordinator, hass):
    c = make_coordinator({})

    assert c.instelling(CONF_BATTERY_CYCLE_LIFE, 6000) == 6000


def test_a_real_value_always_wins(make_coordinator, hass):
    c = make_coordinator({CONF_BATTERY_CYCLE_LIFE: 4000})

    assert c.instelling(CONF_BATTERY_CYCLE_LIFE, 6000) == 4000


def test_zero_is_a_value_not_an_absence(make_coordinator, hass):
    """Nul is een geldige instelling; alleen None telt als leeg."""
    c = make_coordinator({CONF_BATTERY_CYCLE_LIFE: 0})

    assert c.instelling(CONF_BATTERY_CYCLE_LIFE, 6000) == 0


def test_no_call_site_uses_the_unsafe_form():
    """Structuurscan 15. Vier-en-dertig plekken gebruikten dit patroon;

    één ervan kostte de hele slijtageberekening.
    """
    # Via de boomstructuur, niet via de tekst: in de toelichting van
    # `instelling()` staat het patroon met opzet, als voorbeeld van wat
    # er mis was. Een zoekopdracht op tekst vindt dat ook.
    boom = ast.parse((MAP / "coordinator.py").read_text())
    onveilig = []
    for knoop in ast.walk(boom):
        if not (
            isinstance(knoop, ast.Call)
            and isinstance(knoop.func, ast.Attribute)
            and knoop.func.attr == "get"
            and len(knoop.args) == 2
        ):
            continue
        doel = knoop.func.value
        if not (
            isinstance(doel, ast.Attribute) and doel.attr == "config"
        ):
            continue
        eerste, tweede = knoop.args
        if (
            isinstance(eerste, ast.Name)
            and eerste.id.startswith("CONF_")
            and isinstance(tweede, ast.Name)
            and tweede.id.startswith("DEFAULT_")
        ):
            onveilig.append(f"regel {knoop.lineno}: {eerste.id}")

    assert not onveilig, (
        "deze plekken vallen niet terug op hun standaard bij een "
        f"opgeslagen None: {onveilig[:5]}"
    )


# --- de configuratiecontrole ----------------------------------------


def test_a_dead_entity_is_reported(make_coordinator, hass):
    """Een entiteit die niet meer bestaat, bijvoorbeeld na hernoemen of

    na het verwijderen van een integratie.
    """
    c = make_coordinator({CONF_SOC_SENSOR: "sensor.weg"})

    controle = c.get_configuratiecontrole()
    regel = next(
        r for r in controle["entiteiten"] if r["entiteit"] == "sensor.weg"
    )

    assert regel["oordeel"] == "bestaat_niet"
    assert controle["aantal_stuk"] == 1


def test_an_unavailable_entity_is_reported(make_coordinator, hass):
    c = make_coordinator({CONF_SOC_SENSOR: "sensor.soc"})
    hass.states.set("sensor.soc", "unavailable")

    regel = next(
        r
        for r in c.get_configuratiecontrole()["entiteiten"]
        if r["entiteit"] == "sensor.soc"
    )

    assert regel["oordeel"] == "geen_waarde"


def test_a_working_entity_shows_its_value(make_coordinator, hass):
    c = make_coordinator({CONF_SOC_SENSOR: "sensor.soc"})
    hass.states.set("sensor.soc", "31.0")

    regel = next(
        r
        for r in c.get_configuratiecontrole()["entiteiten"]
        if r["entiteit"] == "sensor.soc"
    )

    assert regel["oordeel"] == "in_orde"
    assert regel["waarde"] == "31.0"


def test_empty_settings_are_listed(make_coordinator, hass):
    """De vierde correctie van 28 augustus: cyclusaantal en moduleprijs

    stonden leeg, en dat was nergens te zien.
    """
    c = make_coordinator({CONF_BATTERY_CYCLE_LIFE: None})

    assert CONF_BATTERY_CYCLE_LIFE in (
        c.get_configuratiecontrole()["lege_instellingen"]
    )


def test_non_entity_settings_are_left_alone(make_coordinator, hass):
    """Getallen en teksten zijn geen entiteiten en horen hier niet."""
    c = make_coordinator({CONF_BATTERY_CYCLE_LIFE: 6000})

    entiteiten = c.get_configuratiecontrole()["entiteiten"]

    assert all("." in r["entiteit"] for r in entiteiten)


def test_it_reaches_the_export():
    bron = (MAP / "diagnostics.py").read_text()

    assert '"configuratiecontrole"' in bron
