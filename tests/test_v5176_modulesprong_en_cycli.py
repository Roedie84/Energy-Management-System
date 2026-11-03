"""v5.176.0 - modulesprong per module (L-EMS-061), cycli los van de capaciteit (L-EMS-062)."""
from __future__ import annotations

import asyncio
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import PERSISTED_FIELDS

TZ = timezone(timedelta(hours=1))
T = datetime(2026, 11, 3, 19, 45, tzinfo=TZ)
SPRONG_00996 = {
    "moment": "2026-11-01T18:15:35+01:00", "kwh": 0.551, "module": "AB3000 00996",
    "van_procent": 20.0, "naar_procent": 15.0,
}


def _accu(make_coordinator, hass, modules):
    c = make_coordinator({"battery_soc_sensor_entity": "sensor.soc"})
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c._read_corrected_battery_power = lambda: 0.0
    hass.states.set("sensor.soc", 12.0)
    c.battery_module_live = modules
    c.module_leeg_sprongen = [dict(SPRONG_00996)]
    return c


def _module(naam, soc, cel=3.2):
    return {"apparaat_id": naam, "soc_percent": soc, "cel_min_v": cel}


def test_sprong_van_een_vertrokken_module_geldt_niet_voor_een_andere(make_coordinator, hass):
    c = _accu(make_coordinator, hass, [
        _module("AB3000 01029", 13), _module("AB3000 00917", 16), _module("AB3000 02093", 16),
    ])
    c._volg_module_leeg(T)
    assert c.get_module_leeg()["actief"] is True
    assert c.get_module_leeg()["eigen_sprong"] is False
    assert c.module_leeg_correctie_kwh() == 0.0


def test_constante_trekt_niets_meer_af_zonder_eigen_sprong(make_coordinator, hass):
    c = _accu(make_coordinator, hass, [_module("AB3000 01029", 13)])
    c.module_leeg_sprongen = None
    c._volg_module_leeg(T)
    assert c.module_leeg_correctie_kwh() == 0.0


def test_oude_sprong_zonder_module_telt_niet(make_coordinator, hass):
    c = _accu(make_coordinator, hass, [_module("AB3000 01029", 13)])
    c.module_leeg_sprongen = [{"kwh": 0.5}]
    c._volg_module_leeg(T)
    assert c.module_leeg_correctie_kwh() == 0.0


def test_eigen_sprong_blijft_gelden_begrensd_op_de_module(make_coordinator, hass):
    c = _accu(make_coordinator, hass, [_module("AB3000 00996", 11), _module("AB3000 01029", 16)])
    c._volg_module_leeg(T)
    # 11 % van een module van 4,32 kWh is minder dan de gemeten 0,551.
    assert c.module_leeg_correctie_kwh() == pytest.approx(0.475, abs=0.001)
    assert c.get_module_leeg()["eigen_sprong"] is True


def test_de_mediaan_is_van_de_eigen_sprongen(make_coordinator, hass):
    c = _accu(make_coordinator, hass, [_module("AB3000 01029", 14)])
    c.module_leeg_sprongen = [
        dict(SPRONG_00996), dict(SPRONG_00996), {"kwh": 0.2, "module": "AB3000 01029"},
    ]
    assert c._module_leeg_sprong_kwh("AB3000 01029") == 0.2
    assert c._module_leeg_sprong_kwh() == 0.551


def test_nieuwe_sprong_bij_een_andere_module_wordt_gemeten_en_geldt_dan(make_coordinator, hass):
    modules = [_module("AB3000 01029", 13)]
    c = _accu(make_coordinator, hass, modules)
    hass.states.set("sensor.soc", 15.0)
    c._volg_module_leeg(T)
    hass.states.set("sensor.soc", 10.0)
    c._volg_module_leeg(T + timedelta(minutes=5))
    assert c.module_leeg_sprongen[-1]["module"] == "AB3000 01029"
    assert c.module_leeg_correctie_kwh() == 0.0  # deze sprong zit al in de meting

    c._module_leeg = None
    c._module_leeg_socs = None
    c._volg_module_leeg(T + timedelta(days=1))
    assert c.module_leeg_correctie_kwh() > 0


def test_lage_module_met_eigen_sprong_gaat_voor(make_coordinator, hass):
    modules = [_module("AB3000 01029", 13), _module("AB3000 00996", 16)]
    c = _accu(make_coordinator, hass, modules)
    c._volg_module_leeg(T)
    assert c.module_leeg_correctie_kwh() == 0.0
    modules[1]["soc_percent"] = 14
    c._volg_module_leeg(T + timedelta(minutes=1))
    assert c._module_leeg["apparaat"] == "AB3000 00996"
    assert c._module_leeg["soc_percent"] == 14
    assert c.module_leeg_correctie_kwh() > 0


# --- L-EMS-062 ---------------------------------------------------------------

def _cycli(make_coordinator, hass, capaciteit):
    c = make_coordinator({
        "battery_total_capacity_sensor_entity": "sensor.cap",
        "battery_discharge_energy_sensor_entity": "sensor.geleverd",
    })
    hass.states.set("sensor.cap", capaciteit)
    hass.states.set("sensor.geleverd", "2186.0")
    return c


def test_cycli_springen_niet_als_een_module_weggaat(make_coordinator, hass):
    c = _cycli(make_coordinator, hass, "11.52")
    c._onthoud_hoogste_capaciteit()
    voor = c.battery_estimated_full_cycles
    hass.states.set("sensor.cap", "8.64")
    c._onthoud_hoogste_capaciteit()
    assert voor == pytest.approx(189.8, abs=0.1)
    assert c.battery_estimated_full_cycles == voor
    assert c.battery_capaciteit_hoogste_kwh == 11.52


def test_cycli_met_een_grotere_accu_volgen_de_nieuwe_capaciteit(make_coordinator, hass):
    c = _cycli(make_coordinator, hass, "8.64")
    c._onthoud_hoogste_capaciteit()
    hass.states.set("sensor.cap", "11.52")
    c._onthoud_hoogste_capaciteit()
    assert c.battery_estimated_full_cycles == pytest.approx(189.8, abs=0.1)


def test_onleesbare_capaciteit_verandert_niets(make_coordinator, hass):
    c = _cycli(make_coordinator, hass, "unavailable")
    c._onthoud_hoogste_capaciteit()
    assert c.battery_capaciteit_hoogste_kwh is None


def test_hoogste_capaciteit_wordt_bewaard():
    assert "battery_capaciteit_hoogste_kwh" in PERSISTED_FIELDS


def _recorder(monkeypatch, rijen, aanroepen):
    recorder = types.ModuleType("homeassistant.components.recorder")
    statistieken = types.ModuleType("homeassistant.components.recorder.statistics")

    class _Instantie:
        async def async_add_executor_job(self, functie, *args):
            aanroepen.append(args)
            return functie(*args)

    recorder.get_instance = lambda _hass: _Instantie()
    statistieken.statistics_during_period = lambda *_a: rijen
    monkeypatch.setitem(sys.modules, "homeassistant.components.recorder", recorder)
    monkeypatch.setitem(sys.modules, "homeassistant.components.recorder.statistics", statistieken)


def test_bootstrap_vindt_de_oude_capaciteit(make_coordinator, hass, monkeypatch):
    c = _cycli(make_coordinator, hass, "8.64")
    _recorder(monkeypatch, {"sensor.cap": [{"max": 8.64}, {"max": 11.52}, {"max": None}]}, [])
    asyncio.run(c.async_bootstrap_hoogste_capaciteit())
    assert c.battery_capaciteit_hoogste_kwh == 11.52
    assert c.battery_estimated_full_cycles == pytest.approx(189.8, abs=0.1)


def test_bootstrap_alleen_de_eerste_keer(make_coordinator, hass, monkeypatch):
    c = _cycli(make_coordinator, hass, "8.64")
    c.battery_capaciteit_hoogste_kwh = 8.64
    aanroepen = []
    _recorder(monkeypatch, {"sensor.cap": [{"max": 11.52}]}, aanroepen)
    asyncio.run(c.async_bootstrap_hoogste_capaciteit())
    assert aanroepen == []
    assert c.battery_capaciteit_hoogste_kwh == 8.64
