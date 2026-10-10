"""v5.77 (Ruud 10-10 16:07): "Staan de ramen in de woonkamer open? Dan mag de
airco nooit aan" - "Keuken hoort bij woonkamer, is dezelfde ruimte".

Nieuwe optie `airco_raam_entities` (leeg = geen blokkade). Eén raam "on"
(ook de ventilatiestand): nooit aanzetten of hoger zetten; heeft het EMS hem
aangezet, dan zet het EMS hem uit. Onbekend/onbeschikbaar telt niet als open,
maar staat in de redenen. De vaste uittijd blijft.
"""
import json
from pathlib import Path

from custom_components.energy_management_system import airco_sturing
from custom_components.energy_management_system.const import CONF_AIRCO_RAAM_ENTITIES

from tests.test_airco_sturing import NU, _coordinator

PAKKET = Path(airco_sturing.__file__).parent
RAMEN = [
    "binary_sensor.raam_sensor_wk_voor_contact",
    "binary_sensor.raam_sensor_wk_achter_contact",
    "binary_sensor.raam_sensor_keuken_contact",
]


def _met_ramen(make_coordinator, hass, keuken="off", stand="off", doel=None):
    c, _aanroepen, taken = _coordinator(make_coordinator, hass, stand=stand, doel=doel)
    for coro in taken:
        coro.close()
    c.config[CONF_AIRCO_RAAM_ENTITIES] = list(RAMEN)
    hass.states.set(RAMEN[0], "off", {"friendly_name": "Raam woonkamer voor"})
    hass.states.set(RAMEN[1], "off", {"friendly_name": "Raam woonkamer achter"})
    hass.states.set(RAMEN[2], keuken, {"friendly_name": "Raam keuken"})
    return c


def test_ramen_dicht_dan_gewoon_verwarmen(make_coordinator, hass):
    c = _met_ramen(make_coordinator, hass)
    c._airco_ronde(NU)
    assert c.last_airco_besluit["actie"] == "verwarmen"


def test_een_raam_open_dan_nooit_aan(make_coordinator, hass):
    c = _met_ramen(make_coordinator, hass, keuken="on")
    c.airco_automaat_aan = True
    c._airco_ronde(NU)
    b = c.last_airco_besluit
    assert b["actie"] == "niets"
    assert b["toegepast"] is False
    assert "raam open: Raam keuken" in b["redenen"]
    assert "raam open: Raam keuken" in b["samenvatting"]


def test_door_het_ems_aan_en_raam_open_dan_uit(make_coordinator, hass):
    c = _met_ramen(make_coordinator, hass, keuken="on", stand="heat", doel=21.0)
    c.airco_automaat_aan = True
    c.airco_door_ems = True
    c._airco_laatste_ems = {"stand": "heat", "doel": 21.0, "basis": 21.0}
    c._airco_laatst_gezien = ("heat", 21.0)
    c._airco_ronde(NU)
    b = c.last_airco_besluit
    assert b["actie"] == "uit"
    assert b["toegepast"] is True
    assert b["tekst"].startswith("Uitzetten: raam open")


def test_iemand_zette_hem_zelf_aan_dan_laat_het_ems_hem_staan(make_coordinator, hass):
    """De HA-automatisering zet hem uit; het EMS zet niets aan en vecht niet."""
    c = _met_ramen(make_coordinator, hass, keuken="on", stand="heat", doel=21.0)
    c.airco_automaat_aan = True
    c.airco_door_ems = False
    c._airco_ronde(NU)
    assert c.last_airco_besluit["actie"] == "niets"


def test_onbekende_raamsensor_blokkeert_niet_maar_staat_in_de_redenen(make_coordinator, hass):
    c = _met_ramen(make_coordinator, hass, keuken="unavailable")
    c._airco_ronde(NU)
    b = c.last_airco_besluit
    assert b["actie"] == "verwarmen"
    assert any("raamsensor onbekend" in r and "Raam keuken" in r for r in b["redenen"])


def test_zonder_optie_geen_blokkade(make_coordinator, hass):
    c, _a, _t = _coordinator(make_coordinator, hass)
    hass.states.set(RAMEN[2], "on")
    c._airco_ronde(NU)
    assert c.last_airco_besluit["actie"] == "verwarmen"


def test_een_uit_blijft_uit():
    uit = {"actie": "uit", "tekst": "Vaste uittijd.", "redenen": [], "altijd": True}
    b = airco_sturing.raam_open(uit, {"open": ["Raam"], "onbekend": []}, airco_stand="heat", door_ems_aan=True)
    assert b["actie"] == "uit" and b["altijd"] is True and b["tekst"] == "Vaste uittijd."


def test_ook_bijstellen_naar_een_hoger_doel_wordt_tegengehouden():
    uit = {"actie": "verwarmen", "tekst": "Bijstellen naar 21,5 °C.", "redenen": [], "doel_c": 21.5}
    b = airco_sturing.raam_open(uit, {"open": ["Raam"], "onbekend": []}, airco_stand="off", door_ems_aan=False)
    assert b["actie"] == "niets"


def test_de_optie_staat_in_het_opties_scherm():
    from custom_components.energy_management_system import config_flow

    sleutels = [str(k) for k in config_flow._schema({}).schema]
    assert CONF_AIRCO_RAAM_ENTITIES in sleutels
    for bestand in ("translations/nl.json", "translations/en.json", "strings.json"):
        tekst = json.loads((PAKKET / bestand).read_text(encoding="utf-8"))
        assert tekst["options"]["step"]["init"]["data"][CONF_AIRCO_RAAM_ENTITIES]
    nl = json.loads((PAKKET / "translations/nl.json").read_text(encoding="utf-8"))
    assert "ventilatiestand" in nl["options"]["step"]["init"]["data"][CONF_AIRCO_RAAM_ENTITIES]
