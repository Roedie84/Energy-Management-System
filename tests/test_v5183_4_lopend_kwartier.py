"""v5.183.4: huis en zon van het lopende kwartier over de juiste duur.

Live 04-11 15:41: plan voor 15:30 huis 2201 W en zon 893 W bij een gemeten huis
van 613 W. De waardeplanrij rekende over de rest van het kwartier op het moment
van de berekening (15:34), de planregel deelde door de rest van NU. Dezelfde
fout als v5.165.0 bij het net; v5.183.3 bracht hem terug voor huis en zon.
"""
import pytest

from custom_components.energy_management_system import planvolging as P
from custom_components.energy_management_system.coordinator import EnergyManagementSystemCoordinator as C


def test_deel_volgt_de_rest_van_het_kwartier():
    rij = {"uren": 0.18}
    assert C._waardeplan_deel(rij, 0.06, True) == pytest.approx(1 / 3)


def test_heel_kwartier_blijft_heel():
    assert C._waardeplan_deel({"uren": 0.18}, 0.25, True) == 1.0
    assert C._waardeplan_deel({}, None, False) == 1.0


def test_rij_zonder_duur_eerste_rij_is_al_de_rest():
    assert C._waardeplan_deel({}, 0.06, True) == 1.0


def test_oudere_rij_is_heel_kwartier():
    assert C._waardeplan_deel({}, 0.125, False) == pytest.approx(0.5)


def test_nooit_meer_dan_de_rij():
    assert C._waardeplan_deel({"uren": 0.05}, 0.1, True) == 1.0


def test_vermogen_blijft_gelijk_tijdens_het_kwartier():
    # 15:34 berekend: 0.18 u, huis 0.14 kWh = 778 W, zon 0.056 kWh = 311 W
    r = {"uren": 0.18, "verbruik_kwh": 0.14, "zon_kwh": 0.056}
    for uren in (0.18, 0.1, 0.0628, 0.02):
        deel = C._waardeplan_deel(r, uren, True)
        rij = {"uren": uren, "plan_verbruik_kwh": r["verbruik_kwh"] * deel,
               "plan_zon_kwh": r["zon_kwh"] * deel, "inhoud_delta_kwh": 0.0, "soc_kwh": 3.0}
        v = P.vermogens_per_kwartier([rij], 3.0)[0]
        g = P.gepland_uit_plan(rij, 3.0)
        assert v["huis_w"] == pytest.approx(778, abs=1) and g["huis_w"] == pytest.approx(778, abs=1)
        assert v["zon_w"] == pytest.approx(311, abs=1) and g["zon_w"] == pytest.approx(311, abs=1)
