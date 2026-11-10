"""v5.204.0: de kwaliteit van de zonvoorspelling waar het PLAN mee rekent.

Ruud 10-11 ("oplossen"): de dagcontrole meldde -14,2 % over 40 dagen. Dat is
Solcast zelf; de gecorrigeerde voorspelling van het plan zat de laatste 10
dagen op -1,8 %. Echte plantoetsing 11-10 t/m 09-11.
"""
from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)

ECHT = [("11-09", 5.01, 6.39), ("11-08", 2.67, 0.58), ("11-07", 4.9, 5.67), ("11-06", 7.85, 7.33),
        ("11-05", 7.81, 7.49), ("11-04", 6.01, 6.62), ("11-03", 5.09, 4.96), ("11-02", 2.39, 1.99),
        ("11-01", 2.82, 1.83), ("10-31", 4.14, 4.94), ("10-30", 6.71, 5.3), ("10-29", 7.43, 3.68),
        ("10-28", 9.33, 7.95), ("10-27", 5.22, 5.19), ("10-26", 5.58, 5.39), ("10-25", 7.22, 5.47),
        ("10-24", 6.14, 4.66), ("10-23", 4.15, 4.3), ("10-22", 5.25, 4.21), ("10-21", 6.7, 5.03),
        ("10-20", 11.32, 10.31), ("10-19", 6.91, 6.15), ("10-18", 4.13, 2.5), ("10-17", 10.11, 6.04),
        ("10-16", 8.12, 7.63), ("10-15", 10.89, 9.4), ("10-14", 10.59, 9.3), ("10-13", 4.16, 2.95),
        ("10-12", 12.69, 11.75), ("10-11", 9.14, 7.49)]


def _hist(rijen):
    return [{"datum": f"2026-{d}", "zon": {"voorspeld_kwh": v, "werkelijk_kwh": w}} for d, v, w in reversed(rijen)]


def test_laatste_10_dagen_zonder_structurele_afwijking():
    k = C._pv_plan_kwaliteit(_hist(ECHT))
    assert k["beschikbaar"]
    assert k["laatste_10"]["bias_procent"] == -1.8
    assert k["alles"]["bias_procent"] == -14.0
    assert "gemiddeld goed" in k["duiding"]


def test_structureel_te_hoog_wordt_genoemd():
    k = C._pv_plan_kwaliteit(_hist(ECHT[10:20]))
    assert k["laatste_10"]["bias_procent"] == -19.7
    assert "structureel" in k["duiding"]


def test_leeg_en_nachtdagen():
    assert C._pv_plan_kwaliteit([])["beschikbaar"] is False
    assert C._pv_plan_kwaliteit(_hist([("11-01", 0.2, 0.1)]))["beschikbaar"] is False


def test_in_het_rapport(make_coordinator):
    c = make_coordinator({})
    from types import SimpleNamespace
    c.solar_tracker = SimpleNamespace(deviation_history=[-10.0, -20.0, 5.0])
    c.plan_review_history = _hist(ECHT)
    q = c.get_pv_forecast_quality()
    assert q["bron"].startswith("Solcast zelf")
    assert q["plan"]["laatste_10"]["bias_procent"] == -1.8


def test_vooruitblik_toont_bereik():
    """Ruud 10-11: blok 07:30-09:45 '1,6 kW' (gemiddelde van 1,2 en 2,0 kW)
    naast 'gepland 1,27 kW' voor het kwartier van nu."""
    from pathlib import Path
    js = (Path(__file__).parent.parent / "custom_components" / "energy_management_system"
          / "www" / "ems-cockpit.js").read_text()
    blok = js.split("  _vooruitblik(rijen, tijden) {")[1].split("const regels")[0]
    assert "hi - lo >= 300" in blok and "Math.min(...zelfde)" in blok
