"""v5.31.2 - de accu stond op manual en deed niets.

Gemeld op 6 oktober 12:20: "Modus accu staat op manual maar er gebeurt
niets?" Het apparaat: acMode 1, inputLimit 0, outputLimit 0, laadstand 30%.
Daarna: "Naar smart gezet, laden begon; daarna door EMS naar manual gebeurt
er niets."

Sinds v5.29 schreef het EMS alleen wat afweek van de stand in Home
Assistant. Bij de wissel naar manual ging de select wel, maar het vermogen
niet: dat stond al op -2400, hersteld door Zendure na een herstart. De
Zendure-manager start de handmatige stand pas met een vermogen, dus bleef
de accu op 0 W.
"""
import asyncio

from custom_components.energy_management_system import coordinator as mod
from custom_components.energy_management_system.const import (
    CONF_MANUAL_POWER_NUMBER,
    CONF_OPERATION_SELECT,
    OPDRACHT_HERHAAL_SECONDEN,
    OPTION_MANUAL,
    OPTION_SMART,
)


def _opzet(make_coordinator, hass, stand, vermogen):
    c = make_coordinator({CONF_OPERATION_SELECT: "select.op", CONF_MANUAL_POWER_NUMBER: "number.pow"})
    hass.states.set("select.op", stand, {"options": ["manual", "smart", "smart_discharging", "smart_charging"]})
    hass.states.set("number.pow", vermogen)
    hass.services.calls.clear()
    return c


def _volg(hass):
    """Zoals Zendure: de entiteit neemt de geschreven waarde over."""
    for domein, _dienst, data in hass.services.calls:
        if domein == "select":
            hass.states.set(data["entity_id"], data["option"], {"options": ["manual", "smart", "smart_discharging", "smart_charging"]})
        if domein == "number":
            hass.states.set(data["entity_id"], str(data["value"]))


def _schrijf(hass):
    return [(d, x.get("option", x.get("value"))) for d, _s, x in hass.services.calls if d in ("select", "number")]


def test_van_smart_naar_manual_gaat_het_vermogen_mee(make_coordinator, hass):
    """Precies 6 oktober: het vermogen stond al op -2400."""
    c = _opzet(make_coordinator, hass, "smart", "-2400")
    asyncio.run(c._async_apply_manual(-2400))
    assert _schrijf(hass) == [("select", OPTION_MANUAL), ("number", -2400)]


def test_na_een_herstart_wordt_een_herstelde_stand_opnieuw_verstuurd(make_coordinator, hass):
    """Select en vermogen staan al goed, maar niet door dit EMS geschreven."""
    c = _opzet(make_coordinator, hass, "manual", "-2400")
    asyncio.run(c._async_apply_manual(-2400))
    assert _schrijf(hass) == [("select", OPTION_MANUAL), ("number", -2400)]


def test_wat_het_ems_net_schreef_wordt_niet_elke_ronde_herhaald(make_coordinator, hass):
    c = _opzet(make_coordinator, hass, "smart", "0")
    asyncio.run(c._async_apply_manual(-2400))
    _volg(hass)
    hass.services.calls.clear()
    for _ in range(5):
        asyncio.run(c._async_apply_manual(-2400))
    assert _schrijf(hass) == []


def test_na_tien_minuten_wordt_de_opdracht_herhaald(make_coordinator, hass, monkeypatch):
    klok = [1000.0]
    monkeypatch.setattr(mod.time, "monotonic", lambda: klok[0])
    c = _opzet(make_coordinator, hass, "smart", "0")
    asyncio.run(c._async_apply_manual(-2400))
    _volg(hass)
    hass.services.calls.clear()
    klok[0] += OPDRACHT_HERHAAL_SECONDEN - 1
    asyncio.run(c._async_apply_manual(-2400))
    assert _schrijf(hass) == []
    klok[0] += 2
    asyncio.run(c._async_apply_manual(-2400))
    assert _schrijf(hass) == [("select", OPTION_MANUAL), ("number", -2400)]


def test_iemand_anders_verzet_de_stand(make_coordinator, hass):
    c = _opzet(make_coordinator, hass, "smart", "0")
    asyncio.run(c._async_apply_operation(OPTION_SMART))
    _volg(hass)
    hass.services.calls.clear()
    hass.states.set("select.op", "manual", {"options": ["manual", "smart"]})
    asyncio.run(c._async_apply_operation(OPTION_SMART))
    assert _schrijf(hass) == [("select", OPTION_SMART)]


def test_een_mislukte_schrijfactie_telt_niet_als_geschreven(make_coordinator, hass):
    c = _opzet(make_coordinator, hass, "smart", "0")

    async def faalt(*a, **k):
        raise RuntimeError("cloud weg")

    echt = hass.services.async_call
    hass.services.async_call = faalt
    asyncio.run(c._async_apply_manual(-2400))
    hass.services.async_call = echt
    asyncio.run(c._async_apply_manual(-2400))
    assert _schrijf(hass) == [("select", OPTION_MANUAL), ("number", -2400)]
