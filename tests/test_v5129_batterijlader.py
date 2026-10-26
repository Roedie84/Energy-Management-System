"""v5.129.0: de batterijlader in de keuken, zoals de fietsladers.

Gevraagd 26-10: "Kunnen we voor de oplader in de keuken een zelfde
automatisering bouwen als voor de fietsen en de steelstofzuiger?" (Shelly
`switch.opladers_batterijen` + Anker Prime 200 W USB-lader).

Laadt in het goedkope blok, schakelt uit zodra alles vol is (10 W-startdrempel,
daarna de geleerde drempel), kijkt daarna tot het blok voorbij is elk kwartier
of er weer iets aan hangt, en heeft een eigen overrule.
"""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from conftest import make_price_forecast

DAY0 = datetime(2026, 8, 1, tzinfo=timezone.utc)
COMP = Path(__file__).resolve().parents[1] / "custom_components" / "energy_management_system"


def _prijs(hour, minute):
    if 12 <= hour < 16:
        return 1_300_000
    return 2_500_000


def _config(**extra):
    config = {
        "price_sensor_entity": "sensor.price",
        "price_attribute": "price_tax_included",
        "operation_select_entity": "select.op",
        "manual_power_number_entity": "number.pow",
        "manual_discharge_power": 1600,
        "batterijlader_switch_entity": "switch.opladers_batterijen",
        "batterijlader_power_sensor_entity": "sensor.opladers_batterijen_power",
    }
    config.update(extra)
    return config


def _nu(when):
    from custom_components.energy_management_system import coordinator as coord_mod

    coord_mod.dt_util.now = lambda: when


def _schakel(hass, entity="switch.opladers_batterijen"):
    return [c for c in hass.services.calls if c[0] == "switch" and c[2].get("entity_id") == entity]


def _klaarzetten(hass, vermogen="0", stand="off"):
    hass.states.set("sensor.price", "0", {"forecast": make_price_forecast(DAY0, _prijs)})
    hass.states.set("switch.opladers_batterijen", stand)
    hass.states.set("sensor.opladers_batterijen_power", vermogen)


def test_aan_bij_begin_goedkoop_blok(make_coordinator, hass):
    _klaarzetten(hass, "0")
    c = make_coordinator(_config())
    _nu(DAY0.replace(hour=12, minute=0))
    asyncio.run(c._async_update_locked())
    calls = _schakel(hass)
    assert [x[1] for x in calls] == ["turn_on"]
    assert c.last_batterijlader_action == "test_aan"


def test_blijft_uit_buiten_het_blok(make_coordinator, hass):
    _klaarzetten(hass, "0")
    c = make_coordinator(_config())
    _nu(DAY0.replace(hour=9, minute=0))
    asyncio.run(c._async_update_locked())
    assert _schakel(hass) == []
    assert c.last_batterijlader_action == "wacht_op_goedkoop_blok"


def test_uit_als_alles_vol_is_met_10w_drempel(make_coordinator, hass):
    """12 W is boven de startdrempel van 10 W: laadt nog (een telefoon die
    afrondt). 4 W twee minuten lang: vol, uit, met melding-wacht voor de
    kwartiercontrole."""
    _klaarzetten(hass, "40")
    c = make_coordinator(_config())

    async def run():
        _nu(DAY0.replace(hour=12, minute=0))
        await c._async_update_locked()
        hass.states.set("switch.opladers_batterijen", "on")
        _nu(DAY0.replace(hour=12, minute=5))
        await c._async_update_locked()
        assert c.last_batterijlader_action == "aan_het_laden"

        hass.states.set("sensor.opladers_batterijen_power", "12")
        for minuut in (10, 13):
            _nu(DAY0.replace(hour=12, minute=minuut))
            await c._async_update_locked()
        assert c.last_batterijlader_action == "aan_het_laden"

        hass.states.set("sensor.opladers_batterijen_power", "4")
        _nu(DAY0.replace(hour=12, minute=15))
        await c._async_update_locked()
        _nu(DAY0.replace(hour=12, minute=18))
        await c._async_update_locked()

    asyncio.run(run())
    assert _schakel(hass)[-1][1] == "turn_off"
    assert c.last_batterijlader_action == "voltooid"
    # kwartiercontrole: niet "klaar voor de dag", maar het volgende kwartier
    # opnieuw kijken
    assert c._batterijlader_complete_today is False
    assert c._batterijlader_next_poll_at == DAY0.replace(hour=12, minute=30)
    assert c.batterijlader_charge_duration_history == [13.0]


def test_overrule_laat_de_schakelaar_met_rust(make_coordinator, hass):
    _klaarzetten(hass, "60")
    c = make_coordinator(_config())
    c.batterijlader_override = True
    _nu(DAY0.replace(hour=12, minute=0))
    asyncio.run(c._async_update_locked())
    assert _schakel(hass) == []
    assert c.last_batterijlader_action == "overruled"


def test_niet_geconfigureerd_doet_niets(make_coordinator, hass):
    _klaarzetten(hass, "60")
    cfg = _config()
    del cfg["batterijlader_switch_entity"]
    c = make_coordinator(cfg)
    _nu(DAY0.replace(hour=12, minute=0))
    asyncio.run(c._async_update_locked())
    assert _schakel(hass) == []
    assert c.last_batterijlader_action is None


def test_los_van_fietsen_en_stofzuiger(make_coordinator, hass):
    _klaarzetten(hass, "0")
    hass.states.set("switch.fietsladers", "off")
    hass.states.set("sensor.fietsladers_vermogen", "0")
    c = make_coordinator(_config(
        fietsladers_switch_entity="switch.fietsladers",
        fietsladers_power_sensor_entity="sensor.fietsladers_vermogen",
    ))
    c.fietsladers_override = True
    _nu(DAY0.replace(hour=12, minute=0))
    asyncio.run(c._async_update_locked())
    assert c.last_fietsladers_action == "overruled"
    assert [x[1] for x in _schakel(hass)] == ["turn_on"]


def test_drempel_constant_en_bewaarde_velden():
    from custom_components.energy_management_system import const

    assert const.BATTERIJLADER_COMPLETE_THRESHOLD_W == 10.0
    assert "batterijlader_switch_entity" in const.APPARAAT_INSTELLINGEN
    assert "batterijlader_power_sensor_entity" in const.APPARAAT_INSTELLINGEN
    tekst = (COMP / "const.py").read_text()
    for veld in ("batterijlader_charge_duration_history", "_batterijlader_complete_today",
                 "_batterijlader_complete_date"):
        assert f'"{veld}"' in tekst


def test_vertalingen_en_cockpit():
    for naam in ("strings.json", "translations/nl.json", "translations/en.json"):
        data = json.loads((COMP / naam).read_text())
        assert "batterijlader_switch_entity" in json.dumps(data)
    js = (COMP / "www" / "ems-cockpit.js").read_text()
    assert 'lader: "batterijlader_status"' in js
    assert 'laderOverrule: "batterijlader_override"' in js
    tpl = (COMP / "dashboard_template.yaml").read_text()
    assert "switch.woonkamer_energy_management_system_batterijlader_overrule" in tpl
    assert "sensor.woonkamer_energy_management_system_batterijlader_status" in tpl
