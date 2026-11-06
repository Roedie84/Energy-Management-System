"""v5.189.0 - L-EMS-068 (tekortkans over het venster van de tekortnacht) en
L-EMS-069 (vlag 'huis gaat voor' per kwartier, P1-rimpel telt niet).

Ruud 06-11: "Jij moet voor mij de beste keuze maken."
"""
from datetime import date, datetime, timedelta, timezone

from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)

TZ = timezone(timedelta(hours=1))


# --- L-EMS-069 -----------------------------------------------------------

def test_rimpel_boven_reserve_is_geen_schending():
    """04-11: 0,159 kWh in kleine stukjes boven de reserve - geen vlag meer."""
    stukjes = [{"kwh": 0.02, "marge_kwh": 1.5}] * 8  # 0,16 kWh
    kpi = C._huis_gaat_voor_kpi([], {"2026-11-04": 0.16}, {"2026-11-04": stukjes})
    d = kpi["2026-11-04"]
    assert d["geschonden"] is False
    assert d["rimpel_kwh"] == 0.16
    assert d["lek_kwartieren"] == 0 and d["overschot_onder_reserve_kwartieren"] == 0
    assert d["regeloverschot_kwh"] == 0.16


def test_structureel_lek_in_een_kwartier_is_schending():
    kpi = C._huis_gaat_voor_kpi(
        [], {"2026-11-01": 0.38}, {"2026-11-01": [{"kwh": 0.30, "marge_kwh": 2.0}, {"kwh": 0.08, "marge_kwh": 2.0}]}
    )
    assert kpi["2026-11-01"]["geschonden"] is True
    assert kpi["2026-11-01"]["lek_kwartieren"] == 2


def test_overschot_onder_de_reserve_is_schending():
    kpi = C._huis_gaat_voor_kpi(
        [], {"2026-11-06": 0.03}, {"2026-11-06": [{"kwh": 0.03, "marge_kwh": -0.2}]}
    )
    assert kpi["2026-11-06"]["geschonden"] is True
    assert kpi["2026-11-06"]["overschot_onder_reserve_kwartieren"] == 1


def test_piepklein_onder_de_reserve_telt_als_rimpel():
    kpi = C._huis_gaat_voor_kpi(
        [], {"2026-11-06": 0.01}, {"2026-11-06": [{"kwh": 0.01, "marge_kwh": -0.2}]}
    )
    assert kpi["2026-11-06"]["geschonden"] is False


def test_verkoop_onder_reserve_blijft_schending():
    kpi = C._huis_gaat_voor_kpi(
        [{"dag": "2026-11-06", "marge_bij_export_min_kwh": -0.1}], {}, {}
    )
    assert kpi["2026-11-06"]["geschonden"] is True


def test_zonder_kwartieren_de_oude_dagsomregel():
    kpi = C._huis_gaat_voor_kpi([], {"2026-11-04": 0.159})
    assert kpi["2026-11-04"]["geschonden"] is True
    assert "rimpel_kwh" not in kpi["2026-11-04"]


def test_meetattributen_geven_kwartieren_door(make_coordinator):
    c = make_coordinator({})
    c.dagverloop = {
        "2026-11-05": [
            {"tijd": "07:15", "verkocht": False, "regeloverschot_kwh": 0.02, "marge_bij_export_min_kwh": 1.0},
            {"tijd": "18:30", "verkocht": False, "regeloverschot_kwh": 0.03, "marge_kwh": 0.8},
            {"tijd": "19:00", "verkocht": False, "regeloverschot_kwh": 0.0},
        ]
    }
    kpi = c.sturing_meetattributen()["huis_gaat_voor"]["2026-11-05"]
    assert kpi["geschonden"] is False
    assert kpi["rimpel_kwh"] == 0.05
    assert kpi["regel"].startswith("per kwartier")


# --- L-EMS-068 -----------------------------------------------------------

def _segmenten(start, uren):
    uit, t = [], start
    for _ in range(uren):
        eind = t + timedelta(hours=1)
        uit.append((t.hour, 1.0, eind))
        t = eind
    return uit


def test_nachtvenster_kapt_af_op_negen_uur(make_coordinator):
    c = make_coordinator({})
    start = datetime(2026, 11, 5, 22, 0, tzinfo=TZ)
    seg = _segmenten(start, 15)  # tot 13:00 de dag erna
    centrum = [(0.3, 0.0)] * 11 + [(5.0, 0.0)] * 4  # het tekort zit na 09:00
    c.hourly_consumption_profile = {}
    c.pv_hourly_bias_history = {}
    tot_blok = sorted(c._monte_carlo_trajecten(seg, centrum, 1.0, 0.0))
    nacht = c._monte_carlo_nachttrajecten(start, seg, centrum, 1.0, tot_blok)
    assert c.monte_carlo_nacht_tot == datetime(2026, 11, 6, 9, 0, tzinfo=TZ)
    assert max(nacht) < 3.5 < min(tot_blok)   # 11 x 0,3 = 3,3 tegen 23,3


def test_nachtvenster_gelijk_aan_blok_als_blok_eerder(make_coordinator):
    c = make_coordinator({})
    start = datetime(2026, 11, 5, 22, 0, tzinfo=TZ)
    seg = _segmenten(start, 4)  # blok om 02:00
    tot_blok = [1.0, 2.0]
    assert c._monte_carlo_nachttrajecten(start, seg, [(0.5, 0.0)] * 4, 1.0, tot_blok) == tot_blok
    assert c.monte_carlo_nacht_tot == datetime(2026, 11, 6, 2, 0, tzinfo=TZ)


def test_kalibratie_telt_nachtvenster_altijd_mee(make_coordinator):
    c = make_coordinator({})
    c.reserve_daily_records = [
        # blok de dag erna om 13:00: vroeger apart, nu met kans tot 09:00 in de Brier
        {"date": "2026-11-07", "shortfall": False,
         "mc_22u": {"kans_pct": 100.0, "kans_nacht_pct": 10.0, "basis": "tot_blok",
                    "horizon_tot": "2026-11-07T13:00:00+01:00"}},
        # oude stand zonder nachtvenster en met late horizon: blijft apart
        {"date": "2026-11-02", "shortfall": True,
         "mc_22u": {"kans_pct": 100.0, "basis": "tot_blok",
                    "horizon_tot": "2026-11-02T14:00:00+01:00"}},
    ]
    k = c.get_mc_kalibratie_22u()
    assert k["nachten"] == 1 and k["nachten_venster_tot_9u"] == 1
    assert k["brier"] == 0.01
    assert len(k["nachten_andere_horizon"]) == 1
