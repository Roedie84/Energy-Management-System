"""v5.105.1 - het lopende kwartier telt in het plan alleen voor wat er nog over is.

Gemeld 19-10 om 14:09 (screenshot): "Verwachting iets te optimistisch? het is
nu 14:09" - accu 57%, laden 2,4 kW, en het plan beloofde 62% om 14:15. De
stand is de gemeten stand van NU; het plan rekende er een heel kwartier laden
bovenop.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import PRICE_SCALE_FACTOR

TZ = timezone(timedelta(hours=2))
KWARTIER = datetime(2026, 10, 19, 14, 0, tzinfo=TZ)


def _plan(make_coordinator, nu):
    c = make_coordinator({"manual_charge_power": -2400, "manual_discharge_power": 1600})
    entries = [
        (KWARTIER + timedelta(minutes=15 * i), KWARTIER + timedelta(minutes=15 * (i + 1)),
         0.324 * PRICE_SCALE_FACTOR)
        for i in range(4)
    ]
    c._get_forecast_entries = lambda *a, **k: entries
    c._read_sensor_float = lambda *a, **k: 10.0
    c.beschikbare_energie_kwh = lambda: 5.0
    c.effective_min_soc_percent = lambda: 0
    c._estimate_pv_kwh_for_period = lambda *a, **k: 0.0
    c._verbruik_met_terugval = lambda *a, **k: 0.0
    c._plan_netregels = lambda *a, **k: {"gespaard": set()}
    c._plan_verkoopruimte = lambda *a, **k: None
    gezien = []

    def laadt(netregels, einde, prijs, soc, bruikbaar, laad_kwh, per_kwartier):
        gezien.append(per_kwartier)
        return laad_kwh

    c._plan_laadt = laadt
    return c._bouw_kwartierplan(nu), gezien


def test_het_lopende_kwartier_laadt_alleen_de_rest(make_coordinator, hass):
    plan, _ = _plan(make_coordinator, KWARTIER + timedelta(minutes=9))
    # 6 van de 15 minuten over: 2,4 kW x 0,1 u = 0,24 kWh op 10 kWh = +2,4%
    assert plan[0]["soc_procent"] == pytest.approx(52.4, abs=0.6)
    # het volgende kwartier is weer heel: 0,6 kWh = +6%
    assert plan[1]["soc_procent"] - plan[0]["soc_procent"] == pytest.approx(6.0, abs=0.6)


def test_aan_het_begin_van_het_kwartier_telt_het_hele_kwartier(make_coordinator, hass):
    plan, _ = _plan(make_coordinator, KWARTIER)
    assert plan[0]["soc_procent"] == pytest.approx(56.0, abs=0.6)


def test_de_laadregel_rekent_met_hele_latere_kwartieren(make_coordinator, hass):
    _, gezien = _plan(make_coordinator, KWARTIER + timedelta(minutes=9))
    assert gezien[0] == pytest.approx(0.4)          # 1600 W x 15 min, niet x 6 min


def test_het_lopende_kwartier_draagt_zijn_uren(make_coordinator, hass):
    plan, _ = _plan(make_coordinator, KWARTIER + timedelta(minutes=9))
    assert plan[0]["uren"] == pytest.approx(0.1)
    assert plan[1]["uren"] == pytest.approx(0.25)


def test_planvolging_rekent_het_vermogen_over_de_rest():
    from custom_components.energy_management_system import planvolging

    rij = {"soc_kwh": 5.24, "uren": 0.1, "zon_kwh": 0.0, "verbruik_kwh": 0.0}
    assert planvolging.gepland_uit_plan(rij, 5.0)["accu_w"] == -2400
    heel = {"soc_kwh": 5.6, "zon_kwh": 0.0, "verbruik_kwh": 0.0}          # zonder uren: kwartier
    assert planvolging.gepland_uit_plan(heel, 5.0)["accu_w"] == -2400
