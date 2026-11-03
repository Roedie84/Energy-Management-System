"""v5.170.1 - accukosten rekent door met ontladen > 1,0 (SoC-eenheden, v5.169.0).

Live na de herstart van 03-11 07:22: ontlaadrendement 1,012 -> doorreken gaf
'geen rendement', accukosten onbeschikbaar en de netlaadmarge viel weg.
"""
from custom_components.energy_management_system import accukosten as A


def _dag():
    rijen = []
    inhoud = 2.0
    for i in range(16):
        m = 8 * 60 + i * 15
        tijd = f"{m // 60:02d}:{m % 60:02d}"
        accu_w = -1600.0 if i < 8 else 1000.0
        rijen.append({"tijd": tijd, "beschikbaar_kwh": round(inhoud, 3), "prijs_ct": 25.0 if i < 8 else 45.0,
                      "accu_w": accu_w, "net_w": 0.0, "huis_w": 300.0, "pv_w": 0.0})
        inhoud += 0.33 if i < 8 else -0.25
    return {"2026-11-03": rijen}


def test_ontladen_boven_een_wordt_doorgerekend():
    uit = A.doorreken(_dag(), 0.82, 1.012, 0.042)
    assert uit.get("beschikbaar") is not False
    assert uit.get("reden") != "geen rendement"


def test_onzin_rendement_blijft_geweigerd():
    assert A.doorreken(_dag(), 0.82, 1.5, 0.042)["reden"] == "geen rendement"
    assert A.doorreken(_dag(), 0.0, 1.0, 0.042)["reden"] == "geen rendement"
