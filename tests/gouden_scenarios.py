"""Gouden scenario's (v5.28): wat productie beslist, vóór en na de meetrelease.

Gevraagd in de review: "Laat expliciet zien dat voor de gouden scenario's
v5.27.4 production_action = v5.28 production_action, inclusief Zendure-stand
en vermogen." Elk scenario draait een volledige ronde (`_async_update_locked`)
en legt vast: de reden, de verwachte stand, en elke verstuurde opdracht.
"""
import asyncio
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=2))
DAG = datetime(2026, 10, 1, tzinfo=TZ)


def _prijs_dag(uur, minuut):
    """Een herkenbare Nederlandse dag in ct: nacht ~31, ochtendpiek ~44,
    middag ~25, avondpiek ~51."""
    t = uur + minuut / 60
    if t < 6: ct = 31.5
    elif t < 7: ct = 35.0
    elif t < 9: ct = 44.0
    elif t < 11: ct = 38.0
    elif t < 16: ct = 25.0
    elif t < 18: ct = 36.0
    elif t < 21: ct = 51.0 if 19.25 <= t < 20.0 else 46.0
    else: ct = 38.0
    return int(ct / 100 * 10_000_000)


def _prijs_negatief(uur, minuut):
    return -500_000 if 12 <= uur < 15 else _prijs_dag(uur, minuut)


SCENARIOS = {
    "nacht_03u_accu_half":      dict(uur=3,  minuut=0,  energie="3.5", p1="250",  pv=None),
    "ochtendpiek_08u":          dict(uur=8,  minuut=0,  energie="4.0", p1="300",  pv=None),
    "middag_zon_overschot":     dict(uur=13, minuut=0,  energie="5.0", p1="-900", pv="1400"),
    "middag_goedkoop_leeg":     dict(uur=13, minuut=0,  energie="0.8", p1="300",  pv="100"),
    "avondpiek_vol":            dict(uur=19, minuut=30, energie="7.5", p1="350",  pv=None),
    "avondpiek_laag":           dict(uur=19, minuut=30, energie="1.2", p1="350",  pv=None),
    "avond_22u_bijna_leeg":     dict(uur=22, minuut=0,  energie="0.3", p1="280",  pv=None),
    "negatieve_prijs":          dict(uur=13, minuut=0,  energie="4.0", p1="200",  pv="600", prijs=_prijs_negatief),
    "accustand_onbekend_piek":  dict(uur=19, minuut=30, energie="unavailable", p1="350", pv=None),
    "middag_16u_vol":           dict(uur=16, minuut=0,  energie="7.7", p1="400",  pv="300"),
}


def _config():
    return {
        "price_sensor_entity": "sensor.price",
        "price_attribute": "price_tax_included",
        "operation_select_entity": "select.op",
        "manual_power_number_entity": "number.pow",
        "manual_discharge_power": 1600,
        "manual_charge_power": -2000,
        "available_energy_sensor_entity": "sensor.available_energy",
        "consumption_power_sensor_entity": "sensor.p1",
        "pv_power_sensor_entity": "sensor.pv",
        "battery_total_capacity_sensor_entity": "sensor.capaciteit",
    }


def draai(make_coordinator, hass, naam):
    """Een volledige ronde; geeft reden, stand en opdrachten terug."""
    from conftest import make_price_forecast
    from custom_components.energy_management_system import coordinator as coord_mod

    s = SCENARIOS[naam]
    prijs = s.get("prijs", _prijs_dag)
    vandaag = make_price_forecast(DAG, prijs)
    morgen = make_price_forecast(DAG + timedelta(days=1), _prijs_dag)
    hass.states.set("sensor.price", "0", {"forecast": vandaag + morgen})
    hass.states.set("sensor.p1", s["p1"])
    hass.states.set("sensor.available_energy", s["energie"])
    hass.states.set("sensor.capaciteit", "8.64")
    hass.states.set("sensor.pv", s["pv"] if s["pv"] is not None else "0")
    hass.states.set("select.op", "smart")
    hass.states.set("number.pow", "0")
    c = make_coordinator(_config())
    c.learned_efficiency_history = [83.8] * 7
    moment = DAG.replace(hour=s["uur"], minute=s["minuut"])
    coord_mod.dt_util.now = lambda: moment
    hass.services.calls.clear()
    asyncio.run(c._async_update_locked())
    # v5.28: precies zoals in bedrijf - de meetlaag direct na het besluit.
    # De opdrachten hieronder zijn pas daarna uitgelezen.
    c._meetlaag_na_besluit()
    draai.laatste = c
    return {
        "reden": c.last_reason,
        "stand": c.last_expected_mode,
        "opdrachten": [
            [d, srv, {k: v for k, v in sorted(data.items())}]
            for d, srv, data in hass.services.calls
            if d in ("select", "number")
        ],
    }
