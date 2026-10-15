"""v5.99: planvolging toont ook zon gepland (voorspelling) tegen gemeten."""
from pathlib import Path

from custom_components.energy_management_system import planvolging as pv
import custom_components.energy_management_system as pkg

PLAN = {"kwartier": "x", "van": "12:00", "modus": "smart", "accu_w": -350, "zon_w": 500, "huis_w": 150}


def test_nu_bevat_zon_gepland_en_gemeten():
    o = pv.beoordeel(PLAN, -750, 933, 128)
    assert o["gepland_zon_w"] == 500
    assert o["gemeten_zon_w"] == 933
    assert o["zon_verschil_w"] == 433
    assert o["zon_verschil_tekst"] == "meer zon"


def test_zon_verschil_tekst():
    assert pv.zon_verschil_tekst(None) == "onbekend"
    assert pv.zon_verschil_tekst(20) == "geen"
    assert pv.zon_verschil_tekst(-300) == "minder zon"


def test_zon_zonder_meting():
    o = pv.beoordeel(PLAN, -350, None, 150)
    assert o["gemeten_zon_w"] is None and o["zon_verschil_tekst"] == "onbekend"


def test_kwartier_en_dag_dragen_zon():
    k = pv.sluit_kwartier(PLAN, [{"accu_w": -750, "zon_w": 900, "huis_w": 150}])
    assert k["gepland_zon_w"] == 500 and k["gemeten_zon_w"] == 900 and k["zon_verschil_w"] == 400
    dag = pv.dagsamenvatting("2026-10-15", [{**k, "dag": "2026-10-15"}, {**k, "zon_verschil_w": None}])
    assert dag["zon_kwartieren"] == 1
    assert dag["zon_verschil_kwh"] == 0.1


def test_dag_zonder_zon_na_herstart():
    # teruggezette kwartieren van voor v5.99 hebben geen zonverschil
    dag = pv.dagsamenvatting("d", [{"oorzaak": "geen", "status": "volgens plan", "verschil_w": 0}])
    assert dag["zon_verschil_kwh"] is None and dag["zon_kwartieren"] == 0


def test_cockpit_toont_zon():
    js = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")
    assert "_planvolgingZon(nu)" in js
    assert "gepland_zon_w" in js and "gemeten_zon_w" in js and "zon_verschil_kwh" in js
