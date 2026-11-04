"""v5.184.3: opbrengst en looptotaal volgen het net van het waardeplan.

Live 04-11 18:12: 00:15-00:45 daalde `cumulatief_eur` € 0,24 per kwartier bij
een net van 228 W, omdat de kolommen van de oude planregel bleven staan.
"""
import pytest

from custom_components.energy_management_system.coordinator import EnergyManagementSystemCoordinator as C


def test_looptotaal_volgt_het_net_van_de_rij():
    plan = [
        {"prijs_ct": 37.1, "net_kwh": 0.057, "cumulatief_eur": -0.8, "opbrengst_eur": -0.24},
        {"prijs_ct": 36.5, "net_kwh": 0.057, "cumulatief_eur": -1.08, "opbrengst_eur": -0.24},
    ]
    uit = C._plan_opbrengst_opnieuw(plan)
    assert uit[0]["opbrengst_eur"] == pytest.approx(-0.0211, abs=1e-4)
    assert uit[1]["cumulatief_eur"] == pytest.approx(-0.042, abs=1e-3)


def test_teruglevering_levert_op():
    uit = C._plan_opbrengst_opnieuw([{"prijs_ct": 50.0, "net_kwh": -0.2}])
    assert uit[0]["opbrengst_eur"] == pytest.approx(0.1)


def test_rij_zonder_prijs_of_net_breekt_niet():
    uit = C._plan_opbrengst_opnieuw([
        {"prijs_ct": None, "net_kwh": 1.0, "cumulatief_eur": 5.0},
        {"prijs_ct": 40.0, "net_kwh": None},
    ])
    assert uit[0]["cumulatief_eur"] == 5.0
    assert uit[1]["cumulatief_eur"] == 0.0


def test_lege_lijst():
    assert C._plan_opbrengst_opnieuw([]) == []
