"""v5.131.2: de batterijlader rondt kleine ladingen af en blijft niet hangen.

26-10: de Anker laadde na een korte piek op ~5 W door (17:21-17:24), onder de
geleerde drempel van 6,6 W (rustverbruik ~1,6 W + 5 W marge): om 17:24 ging
hij "vol" uit terwijl er nog geladen werd. En 15:14-17:19 stond hij 2 uur op
"test_aan" zonder last: de schakelaar stond al aan, de test had geen eindtijd.
"""
import asyncio
from datetime import timedelta

from test_v5129_batterijlader import DAY0, _config, _klaarzetten, _nu, _schakel

RUST = [1.76, 1.95, 1.89, 1.86, 1.8, 1.58, 1.61, 1.44, 1.43, 1.3]


def test_drempel_batterijlader_2w_boven_rust(make_coordinator, hass):
    _klaarzetten(hass)
    c = make_coordinator(_config())
    c._batterijlader_idle_power_history = list(RUST)
    c._fietsladers_idle_power_history = list(RUST)
    lader = c._get_learned_completion_threshold_w("_batterijlader_idle_power_history", 10.0)
    fiets = c._get_learned_completion_threshold_w("_fietsladers_idle_power_history", 20.0)
    assert round(lader, 2) == round(1.69 + 2.0, 2)
    assert round(fiets, 2) == round(1.69 + 5.0, 2)


def test_vijf_watt_is_nog_laden(make_coordinator, hass):
    """Het patroon van 26-10: ~16 W, dan ~5 W. Dat is laden, niet vol."""
    _klaarzetten(hass, "0")
    c = make_coordinator(_config())
    c._batterijlader_idle_power_history = list(RUST)

    async def run():
        _nu(DAY0.replace(hour=17, minute=15))
        await c._async_update_locked()
        hass.states.set("switch.opladers_batterijen", "on")
        hass.states.set("sensor.opladers_batterijen_power", "16")
        _nu(DAY0.replace(hour=17, minute=19))
        await c._async_update_locked()
        assert c.last_batterijlader_action == "aan_het_laden"
        hass.states.set("sensor.opladers_batterijen_power", "4.9")
        for minuut in range(22, 60, 5):
            _nu(DAY0.replace(hour=17, minute=minuut))
            await c._async_update_locked()
            assert c.last_batterijlader_action == "aan_het_laden"

    asyncio.run(run())
    assert _schakel(hass)[-1][1] == "turn_on"


def test_vol_pas_na_tien_minuten_rust(make_coordinator, hass):
    _klaarzetten(hass, "0")
    c = make_coordinator(_config())
    c._batterijlader_idle_power_history = list(RUST)

    async def run():
        _nu(DAY0.replace(hour=17, minute=15))
        await c._async_update_locked()
        hass.states.set("switch.opladers_batterijen", "on")
        hass.states.set("sensor.opladers_batterijen_power", "16")
        _nu(DAY0.replace(hour=17, minute=19))
        await c._async_update_locked()
        hass.states.set("sensor.opladers_batterijen_power", "1.8")
        _nu(DAY0.replace(hour=17, minute=24))
        await c._async_update_locked()
        _nu(DAY0.replace(hour=17, minute=29))
        await c._async_update_locked()
        assert c.last_batterijlader_action == "aan_het_laden"
        _nu(DAY0.replace(hour=17, minute=34))
        await c._async_update_locked()

    asyncio.run(run())
    # v5.137.0: vol na tien minuten rust; overdag blijft hij daarna aan
    assert _schakel(hass)[-1][1] == "turn_on"
    assert c.last_batterijlader_action == "vol_blijft_aan"


def test_al_aan_zonder_test_krijgt_eindtijd(make_coordinator, hass):
    """Na een herstart staat de schakelaar aan, maar loopt er geen test."""
    _klaarzetten(hass, "1.8", stand="on")
    c = make_coordinator(_config())
    c._batterijlader_idle_power_history = list(RUST)
    begin = DAY0.replace(hour=15, minute=14)

    async def run():
        _nu(begin)
        await c._async_update_locked()
        assert c.last_batterijlader_action == "test_aan"
        assert c._batterijlader_next_poll_at == begin + timedelta(minutes=5)
        _nu(begin + timedelta(minutes=5))
        await c._async_update_locked()

    asyncio.run(run())
    assert [x[1] for x in _schakel(hass)] == ["turn_off"]
    assert c.last_batterijlader_action == "wacht_op_apparaat"
