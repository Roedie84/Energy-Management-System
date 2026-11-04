"""v5.183.3: de plantabel rekent met het huis en de zon van het waardeplan.

Live 04-11 15:24 na de herstart: 15:30 net 2428 W bij een huis van 760 W en
16:15 accu 1261 W bij een huis van 804 W. Het waardeplan rekent met de live
gecorrigeerde verwachting (en apparaten), de tabel met de oude planregel.
De ondergrens kwam niet in het attribuut (veldenlijst).
"""
from pathlib import Path

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import planvolging as P


def test_tabel_gebruikt_plan_verbruik():
    rij = {"uren": 0.25, "net_kwh": 0.0, "inhoud_delta_kwh": -0.3, "accu_ac_w": 1261,
           "verbruik_kwh": 0.201, "zon_kwh": 0.033, "plan_verbruik_kwh": 0.348, "plan_zon_kwh": 0.033}
    v = P.vermogens_per_kwartier([rij], 3.0)[0]
    assert v["huis_w"] == 1392 and v["zon_w"] == 132
    assert abs(v["accu_w"] + (v["net_w"] or 0) + v["zon_w"] - v["huis_w"]) <= 2


def test_ondergrens_in_de_veldenlijst():
    code = (Path(pkg.__file__).parent / "coordinator.py").read_text(encoding="utf-8")
    assert '"ondergrens_procent",\n        )\n        plan = self.get_quarter_plan(now)' in code
