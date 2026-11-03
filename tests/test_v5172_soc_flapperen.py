"""v5.172.0 punt 1 - SoC-flapperen zonder stroom gedempt.

Nacht 02->03: `sensor.solarflow_2400_ac_electric_level` sprong de hele nacht
elke ~8 min tussen 15 en 16 % (3 min 15, 5 min 16) bij 0 W, omdat module
00996 zaagde tussen 11 en 15 %. De Zendure meldde 0,576 / 0,6912 kWh; elke
stap schoof `beschikbaar` 0,115 kWh en de besparing van vandaag ~5 ct.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.coordinator import demp_soc_stap

TZ = timezone(timedelta(hours=1))
T0 = datetime(2026, 11, 2, 22, 0, tzinfo=TZ)
LAAG, HOOG = 0.576, 0.6912


def _flapreeks(uren=3, stap_min=1):
    """Elke minuut een meting: 5 min 16 %, 3 min 15 % (zoals gemeten)."""
    uit = []
    for m in range(0, uren * 60, stap_min):
        uit.append((T0 + timedelta(minutes=m), HOOG if (m % 8) < 5 else LAAG))
    return uit


def _speel(reeks, vermogen=0.0, staat=None):
    uit = []
    for t, v in reeks:
        w, staat = demp_soc_stap(staat, v, vermogen, t)
        uit.append(w)
    return uit, staat


def test_flapperen_bij_0_w_blijft_een_waarde():
    uit, staat = _speel(_flapreeks())
    assert set(uit) == {HOOG}
    assert staat["gedempt"] >= 20


def test_begint_de_nacht_op_15_dan_blijft_15():
    reeks = [(t, v) for t, v in _flapreeks()]
    reeks.insert(0, (T0 - timedelta(minutes=1), LAAG))
    uit, _ = _speel(reeks)
    assert set(uit) == {LAAG}


def test_met_stroom_volgt_hij_de_meting():
    uit, _ = _speel(_flapreeks(uren=1), vermogen=-600.0)
    assert set(uit) == {LAAG, HOOG}


def test_een_waarde_die_20_minuten_aanhoudt_telt():
    reeks = [(T0 + timedelta(minutes=m), HOOG if m < 5 else LAAG) for m in range(40)]
    uit, _ = _speel(reeks)
    assert uit[10] == HOOG and uit[-1] == LAAG
    eerste = next(i for i, w in enumerate(uit) if w == LAAG)
    assert eerste == 25  # 5 min + 20 min


def test_een_grote_stap_telt_meteen():
    uit, _ = _speel([(T0, 2.0), (T0 + timedelta(minutes=1), 1.45)])
    assert uit[-1] == 1.45


def test_echte_energie_onder_de_stilstandgrens_telt_ook():
    # 35 W gedurende 2 uur = 0,07 kWh >= de helft van een stap van 0,115
    reeks = [(T0 + timedelta(minutes=m), HOOG) for m in range(0, 120, 5)]
    reeks.append((T0 + timedelta(minutes=121), LAAG))
    uit, _ = _speel(reeks, vermogen=35.0)
    assert uit[-1] == LAAG


def _coord(make_coordinator, hass):
    c = make_coordinator({
        "available_energy_sensor_entity": "sensor.beschikbaar",
        "battery_power_sensor_entity": "sensor.accu_w",
    })
    hass.states.set("sensor.accu_w", "0.0", {"unit_of_measurement": "W"})
    c.module_leeg_correctie_kwh = lambda: 0.0
    return c


def test_beschikbare_energie_van_de_sturing_flappert_niet(make_coordinator, hass, monkeypatch):
    from homeassistant.util import dt as dt_util

    c = _coord(make_coordinator, hass)
    gezien = set()
    for t, v in _flapreeks(uren=1):
        monkeypatch.setattr(dt_util, "now", lambda *a, _t=t, **k: _t)
        hass.states.set("sensor.beschikbaar", str(v), {"unit_of_measurement": "kWh"})
        gezien.add(c.beschikbare_energie_kwh())
    assert gezien == {HOOG}
    assert c.get_soc_demper()["gedempte_stappen"] > 0


def test_besparing_vandaag_springt_niet_mee(make_coordinator, hass, monkeypatch):
    from homeassistant.util import dt as dt_util

    c = _coord(make_coordinator, hass)
    c._savings_day_start_available_kwh = HOOG
    c._savings_day_start_stock_eur = None
    c.counterfactual_cost_today_eur = 1.0
    c.actual_cost_today_eur = 1.0
    c._voorraad_kwh_waarde = lambda: (0.43, "kostprijsmodel")
    cijfers = set()
    for t, v in _flapreeks(uren=1):
        monkeypatch.setattr(dt_util, "now", lambda *a, _t=t, **k: _t)
        hass.states.set("sensor.beschikbaar", str(v), {"unit_of_measurement": "kWh"})
        cijfers.add(c.get_savings_correction()["besparing_gecorrigeerd_eur"])
    assert cijfers == {0.0}


def test_zonder_vermogenssensor_geen_demping(make_coordinator, hass):
    c = make_coordinator({"available_energy_sensor_entity": "sensor.beschikbaar"})
    c.module_leeg_correctie_kwh = lambda: 0.0
    hass.states.set("sensor.beschikbaar", str(LAAG), {"unit_of_measurement": "kWh"})
    assert c.beschikbare_energie_kwh() == pytest.approx(LAAG)
    hass.states.set("sensor.beschikbaar", str(HOOG), {"unit_of_measurement": "kWh"})
    assert c.beschikbare_energie_kwh() == pytest.approx(HOOG)
