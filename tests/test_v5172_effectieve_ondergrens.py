"""v5.172.0 punt 4 - de effectieve ondergrens van de accu.

Melding: ontladen stopt op ~15-16 % terwijl de min-SoC 10 % is. Live nagekeken:
op 02-11 om 19:45 schakelde het EMS zelf van 'waardeplan_huis' naar
'waardeplan_houden' (16 %, 0,69 kWh); daarna maakte de modulesprong-correctie
(0,551 kWh, module 00996 onder 15 %) de inhoud 0,02-0,14 kWh, zodat de ochtend
er niets van kreeg. Op 01-11 leverde de accu na de sprong (module 18 -> 0 %)
wel door tot 10 %. Een echte vroege stop van het apparaat is in deze nachten
dus niet gezien. De ondergrens leert die alleen als hij echt gebeurt, en de
sprongcorrectie is begrensd op wat de lage module zelf nog meldt.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import (
    OPTION_SMART,
    OPTION_SMART_CHARGING,
)
from custom_components.energy_management_system.coordinator import effectieve_ondergrens
from tests._coordinator_bron import coordinator_bron

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 3, 8, 0, tzinfo=TZ)


def _w(dagen_geleden, soc):
    return {"moment": (NU - timedelta(days=dagen_geleden)).isoformat(), "soc": soc}


# --- de rekenregel -------------------------------------------------------------

def test_zonder_waarnemingen_de_min_soc():
    assert effectieve_ondergrens([], 10.0, NU)[0] == 10.0


def test_mediaan_van_geldige_waarnemingen():
    bodem, reden = effectieve_ondergrens([_w(1, 16), _w(2, 15), _w(3, 17)], 10.0, NU)
    assert bodem == 16.0 and "16 %" in reden


def test_oude_waarnemingen_vervallen():
    assert effectieve_ondergrens([_w(8, 16)], 10.0, NU)[0] == 10.0


def test_begrensd_tot_15_punt_boven_de_min_soc():
    assert effectieve_ondergrens([_w(1, 40)], 10.0, NU)[0] == 25.0


# --- het leren -----------------------------------------------------------------

def _coord(make_coordinator, hass, monkeypatch):
    from homeassistant.util import dt as dt_util

    c = make_coordinator({
        "battery_power_sensor_entity": "sensor.accu_w",
        "consumption_power_sensor_entity": "sensor.p1_w",
        "battery_soc_sensor_entity": "sensor.soc",
        "min_soc_percent": 10,
        "battery_total_capacity_sensor_entity": "sensor.cap",
    })
    hass.states.set("sensor.cap", "11.52", {"unit_of_measurement": "kWh"})
    c.last_applied_operation = OPTION_SMART
    klok = {"t": datetime(2026, 11, 2, 19, 40, tzinfo=TZ)}
    monkeypatch.setattr(dt_util, "now", lambda *a, **k: klok["t"])

    def ronde(minuut, accu_w, net_w, soc, stand=OPTION_SMART):
        klok["t"] = datetime(2026, 11, 2, 19, 40, tzinfo=TZ) + timedelta(minutes=minuut)
        hass.states.set("sensor.accu_w", str(accu_w), {"unit_of_measurement": "W"})
        hass.states.set("sensor.p1_w", str(net_w), {"unit_of_measurement": "W"})
        hass.states.set("sensor.soc", str(soc), {"unit_of_measurement": "%"})
        c.last_applied_operation = stand
        c._volg_ondergrens(klok["t"])

    return c, ronde


def test_een_echte_stop_bij_afname_wordt_geleerd(make_coordinator, hass, monkeypatch):
    c, ronde = _coord(make_coordinator, hass, monkeypatch)
    ronde(0, 700, 0, 17)
    ronde(1, 650, 0, 16)
    for m in range(2, 15):
        ronde(m, 0, 450, 16)
    assert [w["soc"] for w in c.ondergrens_waarnemingen] == [16]
    assert c.effectieve_ondergrens_procent() == 16.0
    # 6 % van 11,52 kWh gaat van de beschikbare energie af
    assert c.ondergrens_correctie_kwh() == pytest.approx(0.691, abs=0.001)
    assert "16 %" in c.ondergrens_zin()


def test_02_11_19_45_stop_door_het_ems_zelf_telt_niet(make_coordinator, hass, monkeypatch):
    c, ronde = _coord(make_coordinator, hass, monkeypatch)
    ronde(0, 860, 0, 16)
    for m in range(1, 20):
        ronde(m, 0, 450, 16, stand=OPTION_SMART_CHARGING)
    assert not c.ondergrens_waarnemingen
    assert c.effectieve_ondergrens_procent() == 10.0


def test_stop_omdat_het_huis_niets_meer_vraagt_telt_niet(make_coordinator, hass, monkeypatch):
    c, ronde = _coord(make_coordinator, hass, monkeypatch)
    ronde(0, 700, 0, 30)
    for m in range(1, 20):
        ronde(m, 0, 20, 30)
    assert not c.ondergrens_waarnemingen


def test_stop_op_de_min_soc_telt_niet(make_coordinator, hass, monkeypatch):
    c, ronde = _coord(make_coordinator, hass, monkeypatch)
    ronde(0, 700, 0, 11)
    for m in range(1, 20):
        ronde(m, 0, 450, 11)
    assert not c.ondergrens_waarnemingen


def test_dieper_leveren_laat_de_bodem_vervallen(make_coordinator, hass, monkeypatch):
    c, ronde = _coord(make_coordinator, hass, monkeypatch)
    c.ondergrens_waarnemingen = [{"moment": "2026-11-02T19:00:00+01:00", "soc": 16}]
    assert c.effectieve_ondergrens_procent() == 16.0
    ronde(0, 800, 0, 14)
    assert not c.ondergrens_waarnemingen
    assert c.effectieve_ondergrens_procent() == 10.0


# --- waar de bodem doorwerkt ---------------------------------------------------

def test_beschikbaar_trekt_de_grootste_correctie_af(make_coordinator, hass):
    c = make_coordinator({"available_energy_sensor_entity": "sensor.b"})
    c.module_leeg_correctie_kwh = lambda: 0.43
    c.ondergrens_correctie_kwh = lambda: 0.691
    assert c._na_module_leeg(0.6912) == pytest.approx(0.0, abs=1e-3)
    c.ondergrens_correctie_kwh = lambda: 0.0
    assert c._na_module_leeg(0.6912) == pytest.approx(0.2612)


def test_tekort_rekent_met_de_bodem(make_coordinator, hass):
    c = make_coordinator({})
    c.last_reason = "default_smart"
    c.piekverkoop_tot = None
    c.accustand_procent = lambda: 17
    c.beschikbare_energie_kwh = lambda: None
    c.effective_min_soc_percent = lambda: 10.0
    assert c._netimport_is_tekort(NU) is False
    c.ondergrens_waarnemingen = [_w(1, 16)]
    assert c._netimport_is_tekort(NU) is True  # 17 <= 16 + 3


def test_waardeplan_rekent_boven_de_bodem():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = coordinator_bron()
    assert "bruikbaar = capaciteit * (100 - self.effectieve_ondergrens_procent(now)) / 100" in bron


# --- de sprongcorrectie begrensd op de lage module -------------------------------

def test_sprong_niet_groter_dan_wat_de_module_meldt(make_coordinator, hass):
    c = make_coordinator({"battery_total_capacity_sensor_entity": "sensor.cap"})
    hass.states.set("sensor.cap", "11.52", {"unit_of_measurement": "kWh"})
    c.module_leeg_sprongen = [
        {"moment": "2026-11-01T18:15:35+01:00", "kwh": 0.551, "module": "AB3000 00996"}
    ]
    modules = [
        {"apparaat_id": "AB3000 01029", "soc_percent": 16},
        {"apparaat_id": "AB3000 00917", "soc_percent": 16},
        {"apparaat_id": "AB3000 02093", "soc_percent": 16},
        {"apparaat_id": "AB3000 00996", "soc_percent": 11},
    ]
    staat = {"actief": True, "apparaat": "AB3000 00996", "sprong_gezien": False}
    c._module_leeg = staat
    t = datetime(2026, 11, 3, 2, 0, tzinfo=TZ)
    for i, soc in enumerate([11, 12, 13, 14, 15, 14, 13, 12, 11]):
        modules[3]["soc_percent"] = soc
        c._module_leeg_plafond(t + timedelta(minutes=i), staat, modules)
    # hoogste stand 15 % van een module van 2,88 kWh = 0,432 kWh
    assert c.module_leeg_correctie_kwh() == pytest.approx(0.432)


def test_zonder_plafond_de_gemeten_sprong(make_coordinator, hass):
    c = make_coordinator({})
    c.module_leeg_sprongen = [
        {"moment": "2026-11-01T18:15:35+01:00", "kwh": 0.551, "module": "AB3000 00996"}
    ]
    c._module_leeg = {"actief": True, "apparaat": "AB3000 00996", "sprong_gezien": False}
    assert c.module_leeg_correctie_kwh() == pytest.approx(0.551)


def test_kenmerken_op_de_sensor(make_coordinator, hass):
    c = make_coordinator({})
    info = c.get_ondergrens()
    assert {"procent", "min_soc_procent", "reden", "waarnemingen"} <= set(info)
