"""v5.150.0: wat kost een tapmoment, en de douche.

Gevraagd 30-10: "Hoelang duurt een gemiddelde douchebeurt bij ons en wat
kost dit" en daarna "Alle 3": waterprijs, kosten per tapmoment (met het
gas van een douche) en een douche-overzicht. Referentie 29-10: één
douche van 21,8 min, 140 L, gasmeter 0,51 m³, gas € 2,007/m³.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import waterkosten

DAG = datetime(2026, 10, 29, 18, 42, tzinfo=timezone.utc)


def _config(**extra):
    c = {
        "water_active_usage_sensor_entity": "sensor.water_active",
        "water_total_usage_sensor_entity": "sensor.water_total",
        "gas_meter_total_sensor_entity": "sensor.gasmeter",
        "gas_price_sensor_entity": "sensor.gasprijs",
        "water_price_eur_per_m3": 1.82,
    }
    c.update(extra)
    return c


def _gas(hass, m3, moment):
    hass.states.set("sensor.gasmeter", str(m3))
    hass.states.get("sensor.gasmeter").last_changed = moment


def _douche(c, hass, liter=140.0, minuten=22, ketel=True):
    """Een tapmoment met de ketel aan, via de echte toestandsmachine."""
    c._boiler_power_w = lambda: 80.0 if ketel else 0.0
    debiet = liter / minuten
    hass.states.set("sensor.water_total", "100.000")
    for n in range(minuten + 1):
        c._process_water_flow_sample(debiet, DAG + timedelta(minutes=n))
    hass.states.set("sensor.water_total", f"{100 + liter / 1000:.3f}")
    for n in range(4):
        c._process_water_flow_sample(0.0, DAG + timedelta(minutes=minuten + 1 + n))
    return c.water_session_history[-1]


def test_schatting_en_kosten():
    assert abs(waterkosten.schat_gas_m3(140) - 0.576) < 0.005
    k = waterkosten.kosten(140, 1.82, 0.51, 2.007)
    assert k["water_eur"] == 0.255
    assert k["gas_eur"] == 1.024
    assert k["kosten_eur"] == 1.28


def test_gemeten_gas_wordt_afgewezen_bij_onzin():
    assert waterkosten.gemeten_gas_m3(10.0, 10.51, 140) == 0.51 or abs(
        waterkosten.gemeten_gas_m3(10.0, 10.51, 140) - 0.51
    ) < 1e-9
    assert waterkosten.gemeten_gas_m3(0.9, 0.1, 140) is None  # dagteller om
    assert waterkosten.gemeten_gas_m3(10.0, 15.0, 140) is None  # te veel
    assert waterkosten.gemeten_gas_m3(None, 1.0, 140) is None


def test_douche_wacht_op_de_gasmeter(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set("sensor.gasprijs", "2.007")
    _gas(hass, 4324.165, DAG - timedelta(minutes=60))
    sessie = _douche(c, hass)
    assert sessie["bron"] == "douche"
    assert sessie["water_eur"] is not None
    assert "gas_wacht" in sessie
    assert c.water_douche_history == []

    # Nog geen nieuwe stand: blijft wachten.
    c._verwerk_gas_wachtrij(DAG + timedelta(minutes=26))
    assert "gas_wacht" in sessie

    # De eerste stand na het einde.
    _gas(hass, 4324.675, DAG + timedelta(minutes=28))
    c._verwerk_gas_wachtrij(DAG + timedelta(minutes=28))
    assert "gas_wacht" not in sessie
    assert sessie["gas_bron"] == "gasmeter"
    assert abs(sessie["gas_m3"] - 0.51) < 0.001
    assert sessie["kosten_eur"] == round(sessie["liter"] / 1000 * 1.82 + 0.51 * 2.007, 2)
    assert len(c.water_douche_history) == 1


def test_geen_gasstand_binnen_de_wachttijd_dan_geschat(make_coordinator, hass):
    c = make_coordinator(_config())
    hass.states.set("sensor.gasprijs", "2.0")
    _gas(hass, 100.0, DAG - timedelta(hours=2))
    sessie = _douche(c, hass)
    c._verwerk_gas_wachtrij(DAG + timedelta(minutes=27 + 76))
    assert sessie["gas_bron"] == "schatting"
    assert abs(sessie["gas_m3"] - waterkosten.schat_gas_m3(sessie["liter"])) < 0.001
    assert len(c.water_douche_history) == 1


def test_zonder_gasmeter_direct_geschat(make_coordinator, hass):
    c = make_coordinator(_config(gas_meter_total_sensor_entity=None))
    hass.states.set("sensor.gasprijs", "2.0")
    sessie = _douche(c, hass)
    assert "gas_wacht" not in sessie
    assert sessie["gas_bron"] == "schatting"
    assert len(c.water_douche_history) == 1


def test_koud_water_alleen_waterkosten(make_coordinator, hass):
    c = make_coordinator(_config())
    sessie = _douche(c, hass, liter=6.0, minuten=2, ketel=False)
    assert sessie["water_eur"] == round(sessie["liter"] / 1000 * 1.82, 3)
    assert sessie.get("gas_eur") is None
    assert "gas_wacht" not in sessie


def test_bevestigen_als_douche_en_terug(make_coordinator, hass):
    c = make_coordinator(_config(gas_meter_total_sensor_entity=None))
    hass.states.set("sensor.gasprijs", "2.0")
    sessie = _douche(c, hass, liter=60.0, minuten=8, ketel=False)
    tijd = sessie["gestart"][11:16]
    c.confirm_water_source("douche", tijd)
    assert sessie["bron"] == "douche"
    assert len(c.water_douche_history) == 1
    assert sessie["gas_bron"] == "schatting"
    c.confirm_water_source("toilet", tijd)
    assert c.water_douche_history == []
    assert sessie.get("gas_eur") is None


def test_waterprijs_standaard_en_dagkosten(make_coordinator, hass):
    c = make_coordinator({})
    assert c.waterprijs_eur_per_m3() == 1.82
    c.water_daily_total_l = 298
    assert c.water_vandaag_eur() == 0.54


def test_bestaande_douche_wordt_overgenomen(make_coordinator, hass):
    c = make_coordinator(_config(gas_meter_total_sensor_entity=None))
    hass.states.set("sensor.gasprijs", "2.0")
    c.water_session_history = [
        {"gestart": DAG.isoformat(), "duur_minuten": 21.9, "liter": 140.1, "bron": "douche"},
        {"gestart": DAG.isoformat()[:11] + "19:22:00+00:00", "liter": 0.8, "bron": "toilet"},
    ]
    c._verwerk_gas_wachtrij(DAG + timedelta(hours=18))
    assert len(c.water_douche_history) == 1
    assert c.water_douche_history[0]["gas_bron"] == "schatting"
    # Niet nog eens.
    c._verwerk_gas_wachtrij(DAG + timedelta(hours=19))
    assert len(c.water_douche_history) == 1


def test_douche_overzicht():
    nu = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
    douches = [
        {"gestart": (nu - timedelta(days=d)).isoformat(), "duur_minuten": m,
         "liter": m * 6.4, "gas_m3": m * 0.023, "kosten_eur": k, "gas_bron": "gasmeter"}
        for d, m, k in ((1, 22, 1.28), (2, 10, 0.60), (9, 12, 0.70), (40, 30, 2.0))
    ]
    o = waterkosten.douche_overzicht(douches, nu)
    assert o["beschikbaar"] and o["aantal"] == 3
    assert o["gem_minuten"] == round((22 + 10 + 12) / 3, 1)
    assert o["gem_eur"] == round((1.28 + 0.6 + 0.7) / 3, 2)
    assert o["totaal_eur"] == 2.58
    assert o["laatste"]["duur_minuten"] == 22
    assert sum(w["aantal"] for w in o["per_week"]) == 3
    assert waterkosten.douche_overzicht([], nu)["beschikbaar"] is False


def test_sensor_toont_het(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import WaterUsageSensor

    c = make_coordinator(_config())
    c.water_daily_total_l = 100
    attrs = WaterUsageSensor(c, "e1").extra_state_attributes
    assert attrs["waterprijs_eur_per_m3"] == 1.82
    assert attrs["vandaag_eur"] == 0.18
    assert attrs["douche"]["beschikbaar"] is False
