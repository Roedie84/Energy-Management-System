"""v5.175.2: bevindingen analysekaart EMS 03-11 18:10."""
from datetime import datetime, timedelta

import pytest

from custom_components.energy_management_system import waardeplan as W
from custom_components.energy_management_system.const import PLAN_SPAREN_LEEG_KWH
from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)


def _samenvatting(make_coordinator, modules):
    c = make_coordinator({})
    c.battery_module_live = modules
    c.battery_module_spread = {"temperatuur_c": 6.0}
    return c.get_diagnostic_summary()


def _temp(samenvatting, soort):
    return [p for p in samenvatting[soort] if "celtemperatuur" in p]


def test_momentopname_zonder_belasting_is_geen_aandachtspunt(make_coordinator, hass):
    s = _samenvatting(make_coordinator, [
        {"module": 1, "temperatuur_c": 32.0, "vermogen_w": 4.0},
        {"module": 2, "temperatuur_c": 29.0, "vermogen_w": 100.0},
        {"module": 3, "temperatuur_c": 26.0, "vermogen_w": 130.0},
    ])
    assert _temp(s, "aandachtspunten") == []
    assert "Te weinig belasting" in _temp(s, "informatief")[0]


def test_te_warme_module_blijft_aandachtspunt_zonder_belasting(make_coordinator, hass):
    s = _samenvatting(make_coordinator, [
        {"module": 1, "temperatuur_c": 45.0, "vermogen_w": 4.0},
        {"module": 2, "temperatuur_c": 39.0, "vermogen_w": 100.0},
    ])
    assert _temp(s, "aandachtspunten")


def test_onder_belasting_blijft_het_aandachtspunt(make_coordinator, hass):
    s = _samenvatting(make_coordinator, [
        {"module": 1, "temperatuur_c": 32.0, "vermogen_w": 442.0},
        {"module": 2, "temperatuur_c": 29.0, "vermogen_w": 562.0},
        {"module": 3, "temperatuur_c": 26.0, "vermogen_w": 602.0},
    ])
    assert "levert het minste" in _temp(s, "aandachtspunten")[0]


def test_uitgezette_module_telt_niet_voor_de_status(make_coordinator, hass):
    c = make_coordinator({})
    c.battery_module_live = [{"module": 4, "naam": "Accu module 4", "apparaat_id": "AB3000 00996"}]
    c._module_drift_velden = lambda *a, **k: ["cel_delta_afwijking_v"]
    tekst = "loopt aanhoudend uit de pas"

    assert any(tekst in p for p in c.get_diagnostic_summary()["aandachtspunten"])
    c.zet_module_melding("AB3000 00996", False)
    s = c.get_diagnostic_summary()
    assert not any(tekst in p for p in s["aandachtspunten"])
    assert any(tekst in p for p in s["informatief"])


def test_een_restje_van_een_stap_telt_als_leeg():
    assert C._waardeplan_tekort({"actie": "houden", "net_kwh": 0.15, "inhoud_kwh": 0.1}) is True
    assert C._waardeplan_tekort({"actie": "houden", "net_kwh": 0.15, "inhoud_kwh": 0.2}) is False
    assert 0.1 < PLAN_SPAREN_LEEG_KWH < 0.2


def test_net_volgt_de_zonlading_niet_de_afgeronde_stap():
    """Plan 04-11 10:30: zon 564, huis 288, accu -268, en toch net +212 W."""
    t0 = datetime(2026, 11, 4, 10, 30)
    ks = [
        W.Kwartier(t0 + timedelta(minutes=15 * i), 288 / 4000, 564 / 4000, 0.30, 0.10,
                   prijs_incl_eur=0.41)
        for i in range(8)
    ]
    accu = W.Accu(inhoud_kwh=1.0, bruikbaar_kwh=10.37, rendement=0.83, slijtage_eur=0.0422,
                  verkoopmarge_eur=0.05, netlaadmarge_eur=0.05, rendement_laden=0.836,
                  rendement_ontladen=0.99, min_actie_w=400.0)
    for r in W.plan(ks, accu).kwartieren:
        assert r["actie"] == "zon"
        assert r["accu_ac_w"] == -276
        assert r["net_kwh"] == pytest.approx(0.0, abs=0.001)
