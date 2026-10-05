"""v5.30 - fietsladers: elk kwartier controleren.

Gevraagd: "Fietsen laden moet elk kwartier worden gecontroleerd, het kan
zijn dat er tussentijds kort een fiets van de lader is gehaald."

Tot v5.29 gold twee minuten laag vermogen als "klaar voor vandaag": de lader
ging uit en bleef de rest van de dag uit. Een fiets die even van de lader
werd gehaald, laadde daarna niet meer. Nu: tot het goedkope blok voorbij is,
op elk kwartierbegin een korte controle. De opgeladen-melding wacht tot een
controle niets vindt, en komt één keer per dag.
"""
import asyncio
from datetime import datetime, timezone

from conftest import make_price_forecast

DAY0 = datetime(2026, 8, 1, tzinfo=timezone.utc)
LADER = "switch.fietsladers"
VERMOGEN = "sensor.fietsladers_vermogen"


def _vlak(hour, minute):
    return 1_300_000 if 12 <= hour < 16 else 2_500_000


def _prijs(hour, minute):
    if 12 <= hour < 16:
        return 1_300_000
    # na het blok een goedkoper avondblok, zodat 16:00 niet zelf het
    # goedkoopste resterende blok wordt
    return 2_000_000 if hour >= 22 else 2_500_000


def _opzet(make_coordinator, hass, prijs=_vlak):
    from custom_components.energy_management_system import coordinator as mod

    # De nep-klok is moduleglobaal: zet hem vóór het aanmaken, anders erft
    # de aanlooptijd van meldingen het tijdstip van de vorige toets.
    mod.dt_util.now = lambda: DAY0.replace(hour=10, minute=0)
    hass.states.set("sensor.price", "0", {"forecast": make_price_forecast(DAY0, prijs)})
    hass.states.set(LADER, "off")
    hass.states.set(VERMOGEN, "300")
    return make_coordinator(
        {
            "price_sensor_entity": "sensor.price",
            "price_attribute": "price_tax_included",
            "operation_select_entity": "select.op",
            "manual_power_number_entity": "number.pow",
            "fietsladers_switch_entity": LADER,
            "fietsladers_power_sensor_entity": VERMOGEN,
            "appliance_notify_service": "notify.mobile_app_test",
        }
    )


async def _ronde(c, hass, uur, minuut):
    from custom_components.energy_management_system import coordinator as mod

    mod.dt_util.now = lambda: DAY0.replace(hour=uur, minute=minuut)
    await c._async_update_locked()
    for _ in range(3):  # meldingen gaan via een taak
        await asyncio.sleep(0)
    # de schakelaar volgt de laatste opdracht
    schakel = [x for x in hass.services.calls if x[0] == "switch" and x[2].get("entity_id") == LADER]
    if schakel:
        hass.states.set(LADER, "on" if schakel[-1][1] == "turn_on" else "off")


async def _laden_tot_klaar(c, hass):
    await _ronde(c, hass, 12, 0)      # aan
    await _ronde(c, hass, 12, 3)      # 300 W: laadt
    hass.states.set(VERMOGEN, "2")    # fiets eraf (of vol)
    await _ronde(c, hass, 12, 6)
    await _ronde(c, hass, 12, 9)      # twee minuten laag: uit


def _meldingen(hass):
    return [
        x for x in hass.services.calls
        if x[0] == "notify" and "Fietsen" in x[2].get("title", "")
    ]


def test_een_fiets_die_even_eraf_was_laadt_bij_de_volgende_controle(make_coordinator, hass):
    c = _opzet(make_coordinator, hass)

    async def run():
        await _laden_tot_klaar(c, hass)
        assert c.last_fietsladers_action == "voltooid"
        assert hass.states.get(LADER).state == "off"
        hass.states.set(VERMOGEN, "300")  # fiets er weer aan
        await _ronde(c, hass, 12, 12)
        assert hass.states.get(LADER).state == "off"   # nog geen kwartier
        await _ronde(c, hass, 12, 15)
        assert hass.states.get(LADER).state == "on"    # controle op het kwartier
        await _ronde(c, hass, 12, 18)
        assert c.last_fietsladers_action == "aan_het_laden"

    asyncio.run(run())
    assert c._fietsladers_complete_today is False
    assert _meldingen(hass) == []


def test_controles_vallen_op_het_kwartier(make_coordinator, hass):
    c = _opzet(make_coordinator, hass)

    async def run():
        await _laden_tot_klaar(c, hass)
        assert c._fietsladers_next_poll_at == DAY0.replace(hour=12, minute=15)
        await _ronde(c, hass, 12, 15)   # aan
        await _ronde(c, hass, 12, 20)   # niets: uit
        assert c._fietsladers_next_poll_at == DAY0.replace(hour=12, minute=30)
        await _ronde(c, hass, 12, 25)
        assert hass.states.get(LADER).state == "off"
        await _ronde(c, hass, 12, 30)
        assert hass.states.get(LADER).state == "on"

    asyncio.run(run())


def test_melding_na_een_lege_controle_en_maar_een_keer_per_dag(make_coordinator, hass):
    c = _opzet(make_coordinator, hass)

    async def run():
        await _laden_tot_klaar(c, hass)
        assert _meldingen(hass) == []
        await _ronde(c, hass, 12, 15)
        await _ronde(c, hass, 12, 20)   # leeg: melden
        assert len(_meldingen(hass)) == 1
        # later nog een fiets, ook die raakt vol
        hass.states.set(VERMOGEN, "300")
        await _ronde(c, hass, 12, 30)
        await _ronde(c, hass, 12, 33)
        hass.states.set(VERMOGEN, "2")
        await _ronde(c, hass, 12, 36)
        await _ronde(c, hass, 12, 39)
        await _ronde(c, hass, 12, 45)
        await _ronde(c, hass, 12, 50)

    asyncio.run(run())
    assert len(_meldingen(hass)) == 1


def test_einde_van_het_blok_stuurt_een_wachtende_melding(make_coordinator, hass):
    c = _opzet(make_coordinator, hass, _prijs)

    async def run():
        await _ronde(c, hass, 15, 40)
        await _ronde(c, hass, 15, 43)
        hass.states.set(VERMOGEN, "2")
        await _ronde(c, hass, 15, 46)
        await _ronde(c, hass, 15, 49)   # klaar, melding wacht
        assert _meldingen(hass) == []
        await _ronde(c, hass, 16, 0)    # blok voorbij

    asyncio.run(run())
    assert len(_meldingen(hass)) == 1
    assert c.last_fietsladers_action == "wacht_op_goedkoop_blok"


def test_buiten_het_goedkope_blok_geen_controles(make_coordinator, hass):
    c = _opzet(make_coordinator, hass, _prijs)

    async def run():
        await _laden_tot_klaar(c, hass)
        await _ronde(c, hass, 16, 0)
        await _ronde(c, hass, 16, 15)
        await _ronde(c, hass, 16, 30)

    asyncio.run(run())
    assert hass.states.get(LADER).state == "off"
    aan_na_blok = [x for x in hass.services.calls if x[0] == "switch" and x[1] == "turn_on"]
    assert len(aan_na_blok) == 1   # alleen de eerste keer om 12:00


def test_volgend_kwartier():
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    assert C._volgend_kwartier(DAY0.replace(hour=12, minute=9)) == DAY0.replace(hour=12, minute=15)
    assert C._volgend_kwartier(DAY0.replace(hour=12, minute=15)) == DAY0.replace(hour=12, minute=30)
    assert C._volgend_kwartier(DAY0.replace(hour=12, minute=59)) == DAY0.replace(hour=13, minute=0)
