"""v5.167.0 punten 5-9: slijtage per kWh erin, beschikbare energie onder de
min-SoC, de verouderde `history`, zelfontlading over stilstandblokken en
één bron voor de maandbesparing."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.energy_management_system import accukosten as A
from custom_components.energy_management_system.coordinator import EnergyManagementSystemCoordinator as C
from tests._v5167_reeks import bouw

PKG = Path(A.__file__).parent


def test_slijtage_bij_laden_maal_laadrendement():
    """Punt 5: 4,22 ct per kWh door de cellen = 3,46 ct per kWh die erin gaat."""
    c = SimpleNamespace(get_wear_cost_overview=lambda: {"slijtage_ct_per_kwh": 4.22},
                        laadcorrectie_ct=lambda: 0.0, learned_battery_efficiency_percent=82.0,
                        learned_charge_efficiency_percent=82.0)
    c._plan_laadrendement = lambda rt: C._plan_laadrendement(c, rt)
    assert C._laadkosten_ct(c) == pytest.approx(3.46, abs=0.01)


def test_beschikbare_energie_onder_min_soc_is_nul(make_coordinator, hass):
    """Punt 6: de Zendure meldt -0,576 kWh onder de min-SoC; dat is 0, niet
    de (mogelijk oude) terugval."""
    c = make_coordinator({"available_energy_sensor_entity": "sensor.beschikbaar"})
    hass.states.set("sensor.beschikbaar", "-0.576")
    c.last_available_kwh = 4.2
    c.last_projection_available_kwh = 3.9
    assert c.beschikbare_energie_kwh() == 0.0
    hass.states.set("sensor.beschikbaar", "unavailable")
    assert c.beschikbare_energie_kwh() == 4.2       # storing: terugval zoals voorheen


def test_learned_battery_efficiency_zonder_oude_history():
    """Punt 7: de lijst [95.5 ... 56.4] werd nergens meer bijgeschreven."""
    from custom_components.energy_management_system.sensor import LearnedBatteryEfficiencySensor as S

    c = SimpleNamespace(learned_charge_efficiency_percent=82.0, learned_discharge_efficiency_percent=100.0,
                        _rendement_uit_rondes=lambda: {"laden": 82.0}, get_accukosten=lambda: {},
                        learned_efficiency_history=[95.5, 56.4])
    s = S.__new__(S)
    s._coordinator = c
    attr = s.extra_state_attributes
    assert "history" not in attr
    assert attr["laadrendement_procent"] == 82.0 and attr["ontlaadrendement_procent"] == 100.0


def test_zelfontlading_over_lange_stilstandblokken():
    """Punt 8: 6 W uit de cellen, 12 uur stil per dag, 5 dagen. Per kwartier
    (1,5 Wh) ziet het filter alleen de kwartieren zonder SoC-stap -> 0; over
    de blokken komt het eruit."""
    seg = []
    for _ in range(5):
        seg += [(48, 0.0, 0.0), (8, 1200.0, 0.0), (8, -1200.0, 0.0), (32, 0.0, 0.0)]
    # zelfontlading: in de stilstand daalt de echte inhoud met 6 W
    regels, gemeten, *_ = bouw(seg, inhoud0=6.0, eta_l=1.0, eta_o=1.0)
    # 1,5 Wh per stilstandkwartier eraf, daarna weer op de stap van 1 %
    import math
    totaal = 0.0
    for dag in sorted(regels):
        for r in regels[dag]:
            totaal += 0.0015 if r["accu_w"] == 0.0 else 0.0
            soc = math.floor((r["beschikbaar_kwh"] - totaal) / 0.1152 + 1e-9)
            r["beschikbaar_kwh"] = round(soc * 0.1152, 4)
    reeks = A.kwartierreeks(regels, gemeten)
    per_kwartier = A.sluimerverbruik(reeks, 15.0, 100.0)
    blokken = per_kwartier["zelfontlading_blokken"]
    gemiddeld = sum(b["kwh"] for b in blokken.values()) / sum(b["uren"] for b in blokken.values()) * 1000
    assert gemiddeld == pytest.approx(6.0, abs=2.5)
    assert sum(b["blokken"] for b in blokken.values()) >= 5
    # de oude per-kwartiermeting blijft zoals hij was (stuurt het sparen)
    assert "per_stand" in per_kwartier


def test_korte_stilstand_telt_niet_als_blok():
    reeks = [{"dag": "2026-10-24", "tijd": f"10:{m:02d}", "delta_kwh": -0.1152 if m == 15 else 0.0,
              "accu_kwh": 0.0, "soc": 50, "stand": "", "reden": ""} for m in (0, 15, 30, 45)]
    assert A.sluimer_blokken(reeks, 15.0, 100.0) == {}


def test_maandbesparing_een_bron():
    """Punt 9: sensor -0,79 tegen attribuut -0,08 (twee telwijzen)."""
    bron = (PKG / "sensor.py").read_text(encoding="utf-8")
    assert '"besparing_deze_maand_eur": c.besparing_deze_maand_eur(),' in bron
    assert '"besparing_deze_maand_ongecorrigeerd_eur": round(' in bron
