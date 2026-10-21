"""v5.113.1: de prijsverwachting blijft binnen het bereik van de geschiedenis.

Gezien 21-10 07:25: voor zaterdag 24-10 (storm, weekend) -3 ct all-in om
23:00, lager dan elke bekende uurprijs.
"""
from datetime import date

from custom_components.energy_management_system import prijsverwachting as P


def test_grenzen():
    prijzen = {f"2026-10-01T{h:02d}": 0.20 + h / 100 for h in range(24)}
    laag, hoog = P.grenzen(prijzen)
    assert round(laag, 4) == 0.18 and round(hoog, 4) == round(0.43 + 0.05, 4)
    assert P.grenzen({}) == (float("-inf"), float("inf"))


def test_verwachting_geknipt():
    dag = date(2026, 10, 24)
    weer = {s: {"wind": 100.0, "zon": 0.0, "temp": 10.0} for s in P.uren_van_dag(dag)}
    # geschiedenis: 4 dagen tussen 0,20 en 0,40 (voor het niveau en de grenzen)
    prijzen = {}
    for d in range(17, 24):
        for i, s in enumerate(P.uren_van_dag(date(2026, 10, d))):
            prijzen[s] = 0.20 + (i % 10) / 50
    n = len(P.kenmerken(P.uren_van_dag(dag)[0], weer, 0.3))
    coefs = [0.0] * n
    coefs[0], coefs[1] = 0.5, -0.1          # 100 km/u -> 0,5 - 1,0 = -0,5
    v = P.verwacht_dag(coefs, weer, prijzen, dag)
    assert min(u["prijs_eur"] for u in v["uren"]) == round(0.20 - 0.02, 4)
