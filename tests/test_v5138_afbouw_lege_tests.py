"""v5.138.0: minder testschakelingen als er niets aan de lader hangt.

Audit 27-10 punt 1: de e-bikelader schakelde op 25-10 133 keer - elk kwartier
een test zonder fiets (5-6 W, alleen de lader zelf). Nu bouwt de wachttijd
na lege tests op: 15, 30, daarna 60 minuten. Hangt er iets aan, of begint
een nieuw goedkoop blok, dan weer elk kwartier.
"""
import asyncio

from test_v530_fietsen_kwartiercontrole import LADER, VERMOGEN, _opzet, _ronde


def _aan_tijden(hass):
    uit = []
    for x in hass.services.calls:
        if x[0] == "switch" and x[2].get("entity_id") == LADER and x[1] == "turn_on":
            uit.append(x)
    return len(uit)


def test_wachttijd_bouwt_op(make_coordinator, hass):
    c = _opzet(make_coordinator, hass)
    hass.states.set(VERMOGEN, "2")

    async def run():
        for minuut in range(0, 240, 5):
            await _ronde(c, hass, 12 + minuut // 60, minuut % 60)

    asyncio.run(run())
    # 12:00-16:00 elk kwartier zou 16 tests zijn; met afbouw: 12:00, 12:15,
    # 12:45, 13:45, 14:45, 15:45
    assert _aan_tijden(hass) == 6


def test_lading_zet_terug_naar_kwartier(make_coordinator, hass):
    c = _opzet(make_coordinator, hass)
    hass.states.set(VERMOGEN, "2")

    async def run():
        for uur, minuut in ((12, 0), (12, 5), (12, 15), (12, 20)):
            await _ronde(c, hass, uur, minuut)
        assert c._lege_tests.get("last_fietsladers_action") == 2
        hass.states.set(VERMOGEN, "300")
        for uur, minuut in ((12, 45), (12, 50)):
            await _ronde(c, hass, uur, minuut)

    asyncio.run(run())
    assert "last_fietsladers_action" not in c._lege_tests
    assert c.last_fietsladers_action == "aan_het_laden"


def test_afbouw_constant():
    from custom_components.energy_management_system import const

    assert const.SCHEDULED_CHARGE_AFBOUW_EXTRA_MINUTEN == (0, 15, 45)
