"""v5.133.0: geen tests van de laders tussen 22:00 en 06:00 (Ruud 26-10).

"de batterijlader, stofzuiger en fietsen niet controleren tussen 22:00 en
06:00, dan worden dan toch niet aangesloten en dit scheelt schakelingen".
Een lading die al loopt, loopt af.
"""
import asyncio
from datetime import timedelta

import pytest

from test_v5129_batterijlader import DAY0, _config, _klaarzetten, _nu, _schakel


@pytest.mark.parametrize("uur", [22, 23, 0, 3, 5])
def test_geen_test_in_de_nacht(make_coordinator, hass, uur):
    _klaarzetten(hass, "0")
    c = make_coordinator(_config())
    _nu(DAY0.replace(hour=uur, minute=15))
    asyncio.run(c._async_update_locked())
    assert _schakel(hass) == []
    assert c.last_batterijlader_action == "nachtrust"


@pytest.mark.parametrize("uur", [6, 12, 21])
def test_overdag_wel(make_coordinator, hass, uur):
    _klaarzetten(hass, "0")
    c = make_coordinator(_config())
    _nu(DAY0.replace(hour=uur, minute=15))
    asyncio.run(c._async_update_locked())
    assert [x[1] for x in _schakel(hass)] == ["turn_on"]
    assert c.last_batterijlader_action == "test_aan"


def test_lopende_lading_loopt_door_na_22(make_coordinator, hass):
    _klaarzetten(hass, "0")
    c = make_coordinator(_config())

    async def run():
        _nu(DAY0.replace(hour=21, minute=50))
        await c._async_update_locked()
        hass.states.set("switch.opladers_batterijen", "on")
        hass.states.set("sensor.opladers_batterijen_power", "30")
        _nu(DAY0.replace(hour=21, minute=55))
        await c._async_update_locked()
        for minuut in range(0, 30, 5):
            _nu(DAY0.replace(hour=22, minute=minuut))
            await c._async_update_locked()
            assert c.last_batterijlader_action == "aan_het_laden"

    asyncio.run(run())
    assert [x[1] for x in _schakel(hass)] == ["turn_on"]


def test_na_vol_om_23_geen_nieuwe_test_tot_6(make_coordinator, hass):
    _klaarzetten(hass, "0")
    c = make_coordinator(_config())

    async def run():
        _nu(DAY0.replace(hour=21, minute=50))
        await c._async_update_locked()
        hass.states.set("switch.opladers_batterijen", "on")
        hass.states.set("sensor.opladers_batterijen_power", "30")
        _nu(DAY0.replace(hour=21, minute=55))
        await c._async_update_locked()
        hass.states.set("sensor.opladers_batterijen_power", "1")
        _nu(DAY0.replace(hour=22, minute=40))
        await c._async_update_locked()
        _nu(DAY0.replace(hour=22, minute=51))
        await c._async_update_locked()
        assert c.last_batterijlader_action == "voltooid"
        hass.states.set("switch.opladers_batterijen", "off")
        moment = DAY0.replace(hour=23)
        while moment < DAY0.replace(hour=6) + timedelta(days=1):
            _nu(moment)
            await c._async_update_locked()
            assert c.last_batterijlader_action == "nachtrust"
            moment += timedelta(minutes=15)
        _nu(DAY0.replace(hour=6, minute=0) + timedelta(days=1))
        await c._async_update_locked()

    asyncio.run(run())
    assert [x[1] for x in _schakel(hass)] == ["turn_on", "turn_off", "turn_on"]
    assert c.last_batterijlader_action == "test_aan"
