"""v5.167.0 punt 2 en 5 - accukosten volgt de AC-meter, houdt partijen over
een gat, en de slijtage telt per kWh door de cellen.

Audit 02-11 over 25 dagen: AC-meter erin 176,3 / eruit 149,8 kWh (85,0 %);
accukosten telde 132 kWh ontladen (74 %). Ontladen werd afgeleid als
SoC-daling x bandrendement (95,8 %) en na elk gat van meer dan 60 min
begonnen de partijen opnieuw als "begin", zodat wat daarna ontlaadde niet
meer meetelde.
"""
from datetime import datetime

import pytest

from custom_components.energy_management_system import accukosten as A
from tests._v5167_reeks import bouw

ETA_L, ETA_O, SLIJT = 0.82, 1.0, 0.0422


def _dag(n_dagen=1, inhoud0=1.0, **kw):
    """Elke dag: 4 kwartieren laden 2400 W uit het net (02:00), stil, dan
    huis dekken met 240 W (60 Wh per kwartier) tot de lading op is."""
    seg = []
    for _ in range(n_dagen):
        seg += [(8, 0.0, 300.0), (4, -2400.0, 2700.0), (56, 0.0, 300.0), (28, 240.0, 60.0)]
    return bouw(seg, inhoud0=inhoud0, eta_l=ETA_L, eta_o=ETA_O,
                prijs=lambda t: 22.0 if t.hour < 6 else 40.0, **kw)


def test_ontladen_volgt_de_ac_meter():
    regels, gemeten, ac_in, ac_uit = _dag(5)
    uit = A.doorreken(regels, ETA_L, ETA_O, SLIJT, gemeten=gemeten)
    assert uit["gemeten_kwartieren"] > 400
    assert uit["ontladen_totaal_kwh"] == pytest.approx(ac_uit, rel=0.01)
    assert uit["net"]["erin_kwh"] == pytest.approx(ac_in, rel=0.01)


def test_zonder_meting_met_de_oude_95_8_procent_te_weinig():
    """Ter vergelijking: de laadstand x 95,8 % (de oude terugval)."""
    regels, _gemeten, _ac_in, ac_uit = _dag(5)
    oud = A.doorreken(regels, ETA_L, 0.958, SLIJT)
    assert oud["ontladen_totaal_kwh"] < ac_uit * 0.97
    # met het gemeten ontlaadrendement (~1,0) klopt ook de laadstand-weg
    nieuw = A.doorreken(regels, ETA_L, 1.0, SLIJT)
    assert nieuw["ontladen_totaal_kwh"] == pytest.approx(ac_uit, rel=0.03)


def test_gat_gooit_de_partijen_niet_weg():
    """Twee uur geen regels midden in het ontladen: wat daarna ontlaadt komt
    nog steeds uit de netlading (en niet uit "begin")."""
    regels, gemeten, _ac_in, ac_uit = _dag(1, inhoud0=0.0, gat_na=8 + 4 + 56 + 4, gat_kwartieren=8)
    uit = A.doorreken(regels, ETA_L, ETA_O, SLIJT, gemeten=gemeten)
    assert uit["dagen_met_gat"] == ["2026-10-24"]
    # 28 kwartieren ontladen, 8 in het gat: de overige 20 x 60 Wh telden
    assert uit["net"]["ontladen_kwh"] == pytest.approx(20 * 0.06, abs=0.07)
    assert uit["niet_toegerekend_over_gaten_kwh"] == pytest.approx(8 * 0.06, abs=0.12)


def test_dagen_met_gat_tellen_niet_mee_in_de_datacorrectie():
    regels, gemeten, _i, _u = _dag(6)
    for rs in regels.values():
        for r in rs:
            if r.get("accu_w", 0) < 0:
                r["laad_waarde_bron"] = "waardeplan"   # v5.183.0
                r["laad_waarde_ct"] = 40.0       # verwachtte veel meer dan 40 x ... - slijtage
    nu = datetime(2026, 10, 31)
    vol = A.doorreken(regels, ETA_L, ETA_O, SLIJT, nu, gemeten=gemeten)
    assert vol["correctie"]["dagen"] >= 5
    # haal op drie dagen een stuk van 2 uur weg: die dagen vallen af
    for dag in ("2026-10-25", "2026-10-26", "2026-10-27"):
        regels[dag] = [r for r in regels[dag] if not ("10:00" <= r["tijd"] < "12:00")]
    met_gat = A.doorreken(regels, ETA_L, ETA_O, SLIJT, nu, gemeten=gemeten)
    assert set(met_gat["dagen_met_gat"]) == {"2026-10-25", "2026-10-26", "2026-10-27"}
    assert met_gat["correctie"]["dagen"] == vol["correctie"]["dagen"] - 3


def test_slijtage_per_kwh_door_de_cellen():
    """Punt 5: 4,22 ct per kWh door de cellen; per kWh die erin ging x 0,82."""
    regels, gemeten, _i, _u = _dag(3)
    met = A.doorreken(regels, ETA_L, ETA_O, SLIJT, gemeten=gemeten)
    zonder = A.doorreken(regels, ETA_L, ETA_O, 0.0, gemeten=gemeten)
    verschil = zonder["net"]["marge_ct_per_kwh"] - met["net"]["marge_ct_per_kwh"]
    assert verschil == pytest.approx(4.22 * ETA_L, abs=0.05)


def test_rustverbruik_bij_meting_via_gelijkzetten():
    """Stilstand waarin de laadstand 3 stappen zakt zonder AC eruit: rust."""
    regels, gemeten, _i, _u = _dag(1)
    dag = "2026-10-24"
    for r in regels[dag]:
        if "10:00" <= r["tijd"] and r.get("accu_w") == 0.0 and r["tijd"] < "16:00":
            r["beschikbaar_kwh"] = round(r["beschikbaar_kwh"] - 3 * 0.1152, 4)
    uit = A.doorreken(regels, ETA_L, ETA_O, SLIJT, gemeten=gemeten)
    assert uit["rust_kwh"] >= 0.3
