"""v5.121.0 (23-10, "Wat verbetert toepassen"): punten 1, 3 en 6.

1. Overschotwaarde: de marginale waarde van een extra kWh; sturend alleen in
   het regime van 2027 (airco-afweging, fietsladers), tot dan schaduw.
3. P1-doel 2027: wat de vaste extra teruglevering kost, en de sensor
   "P1 regeldoel" die tot en met 2026 gelijk is aan de regelsensor.
6. Negatieve terugleverwaarde in 2027: begrenzen naar ~0 en ruimte houden;
   in 2026 verandert er niets.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import overschotwaarde as OW
from custom_components.energy_management_system import regime2027 as R
from custom_components.energy_management_system.const import (
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_REGEL_P1_SENSOR,
    CONF_SALDEREN_END_DATE,
    CONF_SOLAR_POWER_LIMIT_ENTITY,
)

TZ = timezone(timedelta(hours=2))
NU_2026 = datetime(2026, 10, 23, 13, 0, tzinfo=TZ)
NU_2027 = datetime(2027, 5, 1, 13, 0, tzinfo=TZ)


# --- punt 1: zuivere module ---------------------------------------------------

def test_terugleverwaarde_2027_met_bonus():
    assert OW.terugleverwaarde_2027(0.08) == pytest.approx(0.08 + 0.02 + 0.008)
    # bonus alleen over een positieve kale prijs
    assert OW.terugleverwaarde_2027(-0.05) == pytest.approx(-0.03)
    assert OW.terugleverwaarde_2027(None) is None


def test_marginale_waarde_overschot_en_volle_accu_is_teruglevering():
    w = OW.marginale_waarde(overschot_w=800, accu_vol=True, laadt_op_max=False,
                            inkoop_eur=0.25, teruglever_eur=0.10)
    assert w["bron"] == "teruglevering" and w["eur"] == pytest.approx(0.10)
    w = OW.marginale_waarde(overschot_w=3000, accu_vol=False, laadt_op_max=True,
                            inkoop_eur=0.25, teruglever_eur=0.10)
    assert w["bron"] == "teruglevering"


def test_marginale_waarde_anders_inkoop():
    # accu neemt het overschot nog op
    w = OW.marginale_waarde(overschot_w=800, accu_vol=False, laadt_op_max=False,
                            inkoop_eur=0.25, teruglever_eur=0.10)
    assert w["bron"] == "inkoop" and w["eur"] == pytest.approx(0.25)
    # geen overschot (ruis)
    w = OW.marginale_waarde(overschot_w=30, accu_vol=True, laadt_op_max=False,
                            inkoop_eur=0.25, teruglever_eur=0.10)
    assert w["bron"] == "inkoop"


def test_per_kwartier_en_beste_venster():
    kw = []
    for i in range(12):
        zon = 1.0 if 4 <= i < 8 else 0.0
        kw.append({"start": f"t{i}", "zon_kwh": zon, "verbruik_kwh": 0.1,
                   "soc_kwh": 5.0, "inkoop_eur": 0.25, "teruglever_eur": 0.10})
    waarden = OW.per_kwartier(kw, start_kwh=5.0, bruikbaar_kwh=5.0, laad_kwh_max=0.6)
    assert [w["bron"] for w in waarden[4:8]] == ["teruglevering"] * 4
    assert waarden[0]["bron"] == "inkoop"
    beste = OW.beste_venster(waarden, 4)
    assert beste["start"] == "t4" and beste["uit_overschot_kwartieren"] == 4
    assert OW.beste_venster(waarden[:2], 4) is None


def test_laadt_op_max_in_het_plan():
    kw = [{"start": "a", "zon_kwh": 2.0, "verbruik_kwh": 0.1, "soc_kwh": 1.6,
           "inkoop_eur": 0.25, "teruglever_eur": 0.10}]
    w = OW.per_kwartier(kw, start_kwh=1.0, bruikbaar_kwh=5.0, laad_kwh_max=0.6)
    assert w[0]["bron"] == "teruglevering"


# --- punt 6: zuivere module ---------------------------------------------------

def _kw(start, overschot, t, inkoop=0.15):
    return {"start": start, "overschot_kwh": overschot, "inkoop_eur": inkoop, "teruglever_2027_eur": t}


def test_ruimte_houden_voor_negatieve_uren():
    nu = NU_2027.replace(hour=10)
    kwartieren = [_kw(nu + timedelta(minutes=15 * i), 0.5, 0.05) for i in range(8)]
    kwartieren += [_kw(nu + timedelta(hours=2, minutes=15 * i), 0.6, -0.02) for i in range(8)]
    uit = OW.ruimte_voor_negatief(kwartieren, now=nu, bruikbaar_kwh=5.0, beschikbaar_kwh=2.0,
                                  laad_kwh=0.6, teruglever_nu=0.05, overschot_w=1500)
    assert uit["nodig_kwh"] == pytest.approx(4.8)
    assert uit["ruimte_houden"] is True
    # genoeg ruimte: niets doen
    uit = OW.ruimte_voor_negatief(kwartieren, now=nu, bruikbaar_kwh=10.0, beschikbaar_kwh=2.0,
                                  laad_kwh=0.6, teruglever_nu=0.05, overschot_w=1500)
    assert uit["ruimte_houden"] is False
    # in het negatieve blok zelf: opvangen, niet laten gaan
    binnen = nu + timedelta(hours=2, minutes=30)
    uit = OW.ruimte_voor_negatief(kwartieren, now=binnen, bruikbaar_kwh=5.0, beschikbaar_kwh=2.0,
                                  laad_kwh=0.6, teruglever_nu=-0.02, overschot_w=1500)
    assert uit["ruimte_houden"] is False


def test_geen_negatieve_uren_geen_ruimte():
    nu = NU_2027
    kwartieren = [_kw(nu + timedelta(minutes=15 * i), 0.5, 0.05) for i in range(20)]
    uit = OW.ruimte_voor_negatief(kwartieren, now=nu, bruikbaar_kwh=5.0, beschikbaar_kwh=4.9,
                                  laad_kwh=0.6, teruglever_nu=0.05, overschot_w=1500)
    assert uit["ruimte_houden"] is False and uit["negatief_vanaf"] is None


def test_grens_voor_nul_teruglevering():
    # 2000 W zon bij 100 %, 600 W teruglevering -> 70 %
    assert OW.grens_voor_nul_teruglevering(huidig_procent=100, pv_w=2000, net_w=-600) == pytest.approx(70.0)
    # binnen de dode zone: laten staan
    assert OW.grens_voor_nul_teruglevering(huidig_procent=70, pv_w=1400, net_w=-40) is None
    # import bij een lage grens: weer omhoog
    assert OW.grens_voor_nul_teruglevering(huidig_procent=50, pv_w=1000, net_w=400) == pytest.approx(70.0)
    # al open en import: niets
    assert OW.grens_voor_nul_teruglevering(huidig_procent=100, pv_w=1000, net_w=400) is None


# --- regime2027: begrenzen, ruimte, P1-doel -----------------------------------

def _dag(export, begrens=False, ruimte=False, regelt=False, n=96):
    uit = []
    for i in range(n):
        zon = 1.0 if 40 <= i < 60 else 0.0
        uit.append(R.Kwartier(huis_kwh=0.1, pv_kwh=zon, import_eur=0.25, export_eur=export,
                              accu_kwh=0.0, opvangen=False, verkoop=True,
                              begrens=begrens and zon > 0, ruimte=ruimte, regelt=regelt))
    return uit


def test_begrenzen_vermijdt_negatieve_teruglevering():
    arg = dict(begin_kwh=0.0, capaciteit_kwh=5.0, laad_kw=2.4, ontlaad_kw=2.4, eta=0.92, slijtage=0.0)
    zonder = R.regels_2027(_dag(-0.03), **arg)["kosten_eur"]
    met = R.regels_2027(_dag(-0.03, begrens=True), **arg)["kosten_eur"]
    assert met < zonder
    # bij een positieve terugleverwaarde verandert begrenzen niets
    assert R.regels_2027(_dag(0.05, begrens=True), **arg)["kosten_eur"] == pytest.approx(
        R.regels_2027(_dag(0.05), **arg)["kosten_eur"])


def test_p1_doel_kosten():
    dag = _dag(0.07, regelt=True)
    uit = R.p1_doel_kosten(dag, verschuiving_kw=0.05, rendement=0.85)
    assert uit["regelkwartieren"] == 96
    assert uit["extra_teruglevering_kwh"] == pytest.approx(1.2)
    # 2027: vasthouden (0,25 x 0,922) is meer waard dan 0,07 terugleveren
    assert uit["kosten_2027_eur_per_dag"] > 0.15
    # salderen: vrijwel niets kwijt (sterker: iets gewonnen)
    assert uit["kosten_2026_eur_per_dag"] <= 0.0
    assert uit["kosten_2027_eur_per_jaar"] == pytest.approx(uit["kosten_2027_eur_per_dag"] * 365, abs=0.2)


def test_repetitie_en_samenvatting_dragen_p1_en_schaduw():
    rep = R.repetitie(_dag(-0.03, begrens=True, regelt=True), begin_kwh=0.0, eind_kwh=0.0, capaciteit_kwh=5.0,
                      laad_kw=2.4, ontlaad_kw=2.4, rendement=0.85, verschuiving_kw=0.01)
    assert rep["begrenzen_kwartieren"] == 20
    assert rep["p1_doel"]["verschuiving_w"] == 10
    samen = R.samenvatting([dict(rep, datum="2026-10-22")])
    assert samen["p1_doel_kosten_2027_eur_per_dag"] == rep["p1_doel"]["kosten_2027_eur_per_dag"]
    assert samen["begrenzen_kwartieren"] == 20


# --- coordinator: 2026 ongewijzigd, 2027 sturend ------------------------------

def _coord(make_coordinator, hass, eind="2026-12-31"):
    c = make_coordinator({CONF_SALDEREN_END_DATE: eind, CONF_SOLAR_POWER_LIMIT_ENTITY: "number.pv_grens",
                          CONF_CONSUMPTION_POWER_SENSOR: "sensor.p1", CONF_REGEL_P1_SENSOR: "sensor.regel"})
    c.huidige_prijs_eur_per_kwh = lambda now=None: 0.25
    c._get_forecast_entries = lambda price_key_override=None: [(NU_2026 - timedelta(days=1),
                                                                NU_2027 + timedelta(days=1), 25.0)]
    c._terugleverwaarde_2027 = lambda now, kale=None: 0.09
    c._lees_pv_vermogen_w = lambda: 3000.0
    c._read_corrected_consumption_power = lambda: 500.0
    c._read_corrected_battery_power = lambda: 0.0
    c.accustand_procent = lambda: 100.0
    c._bovengrens_procent = lambda: 100.0
    return c


def test_overschotwaarde_2026_schaduw(make_coordinator, hass):
    c = _coord(make_coordinator, hass)
    w = c.get_overschotwaarde(NU_2026)
    assert w["regime"] == "salderen" and w["sturend"] is False
    assert w["schaduw_2027"]["bron"] == "teruglevering"
    assert w["schaduw_2027"]["eur"] == pytest.approx(0.09)


def test_overschotwaarde_2027_stuurt(make_coordinator, hass):
    c = _coord(make_coordinator, hass, eind="2026-12-31")
    w = c.get_overschotwaarde(NU_2027)
    assert w["sturend"] is True and w["bron"] == "teruglevering"


def test_fietsladers_alleen_in_2027_op_overschot(make_coordinator, hass):
    c = _coord(make_coordinator, hass)
    c.get_overschotwaarde = lambda now=None: {
        "beschikbaar": True, "sturend": False, "bron": "inkoop", "overschot_w": 2500,
        "schaduw_2027": {"bron": "teruglevering", "eur": 0.09}}
    assert c._fietsladers_op_overschot(NU_2026) is False
    assert c.last_fiets_overschot["zou_laden_in_2027"] is True
    c.get_overschotwaarde = lambda now=None: {
        "beschikbaar": True, "sturend": True, "bron": "teruglevering", "overschot_w": 2500,
        "schaduw_2027": {"bron": "teruglevering", "eur": 0.09}}
    assert c._fietsladers_op_overschot(NU_2027) is True
    # het venster houdt even aan als de wolk komt
    c.get_overschotwaarde = lambda now=None: {
        "beschikbaar": True, "sturend": True, "bron": "inkoop", "overschot_w": 0,
        "schaduw_2027": {"bron": "inkoop", "eur": 0.25}}
    assert c._fietsladers_op_overschot(NU_2027 + timedelta(minutes=5)) is True
    assert c._fietsladers_op_overschot(NU_2027 + timedelta(minutes=30)) is False


def test_negatieve_teruglevering_2026_alleen_schaduw(make_coordinator, hass):
    c = _coord(make_coordinator, hass)
    c._negatieve_teruglevering_besluit = lambda now, invoer=None: {"begrenzen": True, "ruimte_houden": True}
    gestart = []
    c._start_solar_ramp = lambda p: gestart.append(p)
    asyncio.run(c._async_negatieve_teruglevering(NU_2026))
    assert gestart == []
    assert c.last_negatieve_teruglevering["sturend"] is False
    assert c._ruimte_houden_sturend(NU_2026) is False


def test_negatieve_teruglevering_2027_begrenst(make_coordinator, hass):
    c = _coord(make_coordinator, hass)
    c._negatieve_teruglevering_besluit = lambda now, invoer=None: {"begrenzen": True}
    hass.states.set("number.pv_grens", "100")
    hass.states.set("sensor.p1", "-900")
    gestart = []
    c._start_solar_ramp = lambda p: gestart.append(p)
    asyncio.run(c._async_negatieve_teruglevering(NU_2027))
    assert gestart == [pytest.approx(70.0)]
    assert c._teruglevering_begrensd is True
    # niet meer negatief: panelen weer open
    c._negatieve_teruglevering_besluit = lambda now, invoer=None: {"begrenzen": False}
    asyncio.run(c._async_negatieve_teruglevering(NU_2027))
    assert gestart[-1] == 100.0 and c._teruglevering_begrensd is False


def test_verwarmingsadvies_2026_rekent_met_de_inkoop(make_coordinator, hass):
    c = _coord(make_coordinator, hass)
    c._lees_optionele_sensor = lambda conf: 1.20
    c._get_live_outdoor_temp_c = lambda now: 7.0
    c.get_overschotwaarde = lambda now=None: {"beschikbaar": True, "sturend": False, "eur": 0.25,
                                             "bron": "inkoop", "schaduw_2027": {"eur": 0.09, "bron": "teruglevering"}}
    uit = c.get_verwarmingsadvies()
    assert uit["overschotwaarde"]["stroomprijs_eur"] == pytest.approx(0.25)
    assert uit["schaduw_2027"]["stroomprijs_eur"] == pytest.approx(0.09)


def test_verwarmingsadvies_2027_rekent_met_de_overschotwaarde(make_coordinator, hass):
    c = _coord(make_coordinator, hass)
    c._lees_optionele_sensor = lambda conf: 1.20
    c._get_live_outdoor_temp_c = lambda now: 7.0
    c.get_overschotwaarde = lambda now=None: {"beschikbaar": True, "sturend": True, "eur": 0.09,
                                             "bron": "teruglevering", "schaduw_2027": {"eur": 0.09}}
    uit = c.get_verwarmingsadvies()
    assert uit["overschotwaarde"]["stroomprijs_eur"] == pytest.approx(0.09)
    assert uit["advies"] == "airco"


def test_p1_regeldoel_spiegelt_in_2026_en_mikt_op_nul_in_2027(make_coordinator, hass):
    c = _coord(make_coordinator, hass)
    for _ in range(10):
        c.p1_regeldoel(10.0, 0.0, NU_2026)
    uit = c.p1_regeldoel(-90.0, -100.0, NU_2026)
    assert uit["waarde_w"] == -90.0          # precies de regelsensor
    assert uit["template_verschuiving_w"] == pytest.approx(10.0)
    uit = c.p1_regeldoel(-90.0, -100.0, NU_2027)
    assert uit["waarde_w"] == pytest.approx(-100.0)   # verschuiving eraf: doel 0 W op de meter


def test_regelverschuiving_leest_de_eigen_sensor_als_de_zendure_hem_volgt(make_coordinator, hass):
    c = _coord(make_coordinator, hass)
    hass.states.set("sensor.regel", "60")
    hass.states.set("sensor.p1", "10")
    hass.states.set("sensor.ems_p1", "10", {"ems_p1_regeldoel": True})
    c._ronde_stempel = lambda: None
    c._zendure_p1meter = lambda: "sensor.regel"
    assert c.regelverschuiving_kw() == pytest.approx(0.05)
    c._zendure_p1meter = lambda: "sensor.ems_p1"
    assert c.regelverschuiving_kw() == pytest.approx(0.0)


def test_r27_velden_dragen_begrenzen_en_ruimte(make_coordinator, hass):
    c = _coord(make_coordinator, hass)
    c.should_capture_surplus_over_selling = lambda now: True
    c._verkoop_loont_na_saldering = lambda now: None
    c._get_feedin_value_per_kwh = lambda e, now: -0.01
    c._negatief_invoer = lambda now: {"teruglever_nu": -0.01, "inkoop_nu": 0.12, "kwartieren": []}
    uit = c._r27_velden(NU_2026)
    assert uit["r27_begrens"] is True and uit["r27_ruimte"] is False
