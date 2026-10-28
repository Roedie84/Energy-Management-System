"""v5.141.0 - leerronde 28-10: L-EMS-043 (airco-buffer schaal) en L-EMS-041
(Monte Carlo 22:00-stand als het goedkope blok al loopt)."""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    MC_KANS_BASIS_IN_BLOK,
    PRICE_SCALE_FACTOR,
)

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 10, 27, 17, 0, tzinfo=TZ)


def _ruwe_reeks(c, nu_prijs, later_eur):
    """Zoals de echte prijssensor: de reeks in eenheden van 1e-7 euro."""
    c._get_forecast_entries = lambda *a, **k: [
        (NU + timedelta(minutes=15 * (i + 1)), NU + timedelta(minutes=15 * (i + 2)),
         round(p * PRICE_SCALE_FACTOR))
        for i, p in enumerate(later_eur)
    ]
    c.huidige_prijs_eur_per_kwh = lambda now=None: nu_prijs


def _verwarmen():
    return {"actie": "verwarmen", "doel_c": 21.0, "tekst": "t", "redenen": []}


def test_geen_voorverwarmen_bij_vrijwel_gelijke_prijs(make_coordinator):
    # 27-10 07:40: "nu 38 ct, straks tot 390089400 ct" - de reeks was niet geschaald
    c = make_coordinator({})
    _ruwe_reeks(c, 0.38, [0.3900894, 0.40])
    uit = c._airco_buffer_ronde(NU, _verwarmen(), "off")
    assert uit["doel_c"] == 21.0
    assert not any("voorverwarmen" in r for r in uit.get("redenen") or [])


def test_wel_voorverwarmen_voor_een_duur_blok_met_ct_in_de_tekst(make_coordinator):
    c = make_coordinator({})
    _ruwe_reeks(c, 0.20, [0.25, 0.40])
    uit = c._airco_buffer_ronde(NU, _verwarmen(), "off")
    assert uit["doel_c"] == 21.5
    reden = uit["redenen"][-1]
    assert "nu 20 ct" in reden and "straks tot 40 ct" in reden


def test_duur_kwartier_werkt_weer(make_coordinator):
    c = make_coordinator({})
    _ruwe_reeks(c, 0.45, [0.30, 0.28])
    uit = c._airco_buffer_ronde(NU, _verwarmen(), "off")
    assert uit["doel_c"] == 20.5
    assert "duur kwartier" in uit["redenen"][-1]


def _mc_klaar(c):
    c.monte_carlo_shortfall_probability_percent = 12.5
    c.monte_carlo_kans_incl_lange_horizon_pct = 30.0
    c.monte_carlo_lange_extra_kwh = 1.0
    c.monte_carlo_deterministisch_kwh = 2.0
    c.monte_carlo_median_deficit_kwh = 1.5
    c.monte_carlo_p90_deficit_kwh = 3.0
    c.monte_carlo_horizon_basis = "test"
    c.mc_22u_per_avond = {}
    c.schedule_persisted_state_save = lambda: None


def test_stand_van_22u_in_blok_wordt_bewaard(make_coordinator):
    c = make_coordinator({})
    _mc_klaar(c)
    avond = datetime(2026, 10, 25, 22, 0, tzinfo=TZ)
    c._leg_mc_22u_vast(avond, 4.2, basis=MC_KANS_BASIS_IN_BLOK)
    stand = c.mc_22u_per_avond["2026-10-25"]
    assert stand["basis"] == "in_blok" and stand["kans_pct"] == 12.5


def test_in_blok_telt_apart_en_niet_in_de_brier(make_coordinator):
    c = make_coordinator({})
    c.reserve_daily_records = [
        {"date": "2026-10-25", "shortfall": False, "mc_22u": {"kans_pct": 10.0, "basis": "tot_blok"}},
        {"date": "2026-10-26", "shortfall": False, "mc_22u": {"kans_pct": 26.7, "basis": "in_blok"}},
    ]
    k = c.get_mc_kalibratie_22u()
    assert k["nachten"] == 1
    assert k["brier"] == 0.01
    assert k["nachten_oude_basis_uitgesloten"] == 0
    assert k["nachten_in_blok"] == [
        {"nacht_tot": "2026-10-26", "kans_pct": 26.7, "tekortnacht": False, "horizon_tot": None}
    ]


def test_de_ronde_bewaart_ook_tijdens_het_blok():
    from pathlib import Path
    bron = (Path(__file__).parents[1] / "custom_components" / "energy_management_system"
            / "coordinator.py").read_text(encoding="utf-8")
    assert "basis=MC_KANS_BASIS_TOT_BLOK if start <= now else MC_KANS_BASIS_IN_BLOK" in bron
