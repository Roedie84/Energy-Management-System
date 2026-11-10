"""v5.208.0 (Ruud 10-11): een eigen automatisering (2 graden zuiniger tijdens
het koken) is geen handbediening. Zolang de ingestelde entiteit "on" is, trekt
het EMS zich niet terug, leert het er niet van en stelt het het doel niet bij;
daarna pakt het EMS de airco weer op."""
from datetime import datetime, timezone

import pytest

from tests.test_airco_sturing import _coordinator

NU = datetime(2026, 11, 10, 15, 50, tzinfo=timezone.utc)
KOOK = "input_boolean.airco_kookstand"


def _met_ems_aan(make_coordinator, hass, kook="off"):
    c, aanroepen, taken = _coordinator(make_coordinator, hass, stand="heat", doel=21.5)
    c.config["airco_extern_entity"] = KOOK
    hass.states.set(KOOK, kook)
    c.airco_automaat_aan = True
    c.airco_door_ems = True
    c._airco_laatste_ems = {"stand": "heat", "doel": 21.5, "basis": 21.0}
    c.living_room_current_temp_c = 22.0
    c._airco_ronde(NU)                       # eerste waarneming
    return c, aanroepen, taken


def test_zonder_instelling_blijft_een_wijziging_handbediening(make_coordinator, hass):
    c, _a, _t = _met_ems_aan(make_coordinator, hass)
    c.config.pop("airco_extern_entity")
    hass.states.set(KOOK, "on")
    hass.states.set("climate.woonkamer", "heat", {"temperature": 19.5})

    c._airco_ronde(NU)

    assert c._airco_handmatig_bij is not None


def test_verlaging_door_de_kookstand_is_geen_handbediening(make_coordinator, hass):
    c, _a, _t = _met_ems_aan(make_coordinator, hass)
    setpunten = list(c.airco_setpunten)
    hass.states.set(KOOK, "on")
    hass.states.set("climate.woonkamer", "heat", {"temperature": 19.5})

    c._airco_ronde(NU)

    assert c._airco_handmatig_bij is None
    assert c.airco_door_ems is True
    assert c.airco_setpunten == setpunten          # er wordt niet van geleerd
    assert "zelf" not in c.last_airco_besluit["tekst"]


def test_terugzetten_na_het_koken_is_ook_geen_handbediening(make_coordinator, hass):
    """De automatisering zet terug en zet daarna pas de kookstand uit; het EMS
    kan dat in één ronde zien (kookstand al uit)."""
    c, _a, _t = _met_ems_aan(make_coordinator, hass)
    c._airco_laatste_ems = None                   # het EMS zette hem niet zelf
    c.airco_door_ems = False
    hass.states.set(KOOK, "on")
    hass.states.set("climate.woonkamer", "heat", {"temperature": 19.5})
    c._airco_ronde(NU)
    hass.states.set(KOOK, "off")
    hass.states.set("climate.woonkamer", "heat", {"temperature": 21.5})

    c._airco_ronde(NU)

    assert c._airco_handmatig_bij is None


def test_een_ronde_later_is_een_wijziging_weer_handbediening(make_coordinator, hass):
    c, _a, _t = _met_ems_aan(make_coordinator, hass, kook="on")
    hass.states.set(KOOK, "off")
    c._airco_ronde(NU)                            # ronde direct na afloop
    c._airco_ronde(NU)
    hass.states.set("climate.woonkamer", "heat", {"temperature": 23.0})

    c._airco_ronde(NU)

    assert c._airco_handmatig_bij is not None


def test_tijdens_de_kookstand_stelt_het_ems_het_doel_niet_bij(make_coordinator, hass):
    c, _a, taken = _met_ems_aan(make_coordinator, hass, kook="on")
    c._airco_buffer_ronde = lambda now, uit, stand: dict(
        uit, actie="verwarmen", doel_c=21.0, tekst="Doel bijstellen."
    )

    c._airco_ronde(NU)

    assert c.last_airco_besluit["actie"] == "niets"
    assert c.last_airco_besluit["toegepast"] is False
    assert "eigen automatisering" in c.last_airco_besluit["redenen_tekst"]
    assert taken == []


@pytest.mark.asyncio
async def test_na_de_kookstand_pakt_het_ems_het_doel_weer_op(make_coordinator, hass):
    c, aanroepen, taken = _met_ems_aan(make_coordinator, hass, kook="on")
    c._airco_buffer_ronde = lambda now, uit, stand: dict(
        uit, actie="verwarmen", doel_c=21.0, tekst="Doel bijstellen."
    )
    c._airco_ronde(NU)
    hass.states.set(KOOK, "off")

    c._airco_ronde(NU)
    for taak in taken:
        await taak

    assert c.last_airco_besluit["toegepast"] is True
    assert aanroepen[-1] == ("climate", "set_temperature",
                             {"entity_id": "climate.woonkamer", "temperature": 21.0, "hvac_mode": "heat"})
