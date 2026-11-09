"""v5.198.1: de zontegels sloten niet op elkaar aan.

09-11 12:51 (Ruud: "klopt niet?"): "Zon vandaag 4,2 van 5,0" en "Nog te komen
3,0". De 5,0 was de verwachting van vanochtend, de 3,0 de kale Solcast; het
plan rekende met 2,5. Nu: de eigen rest, en opgewekt + rest als totaal.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import coordinator as mod

NU = datetime(2026, 11, 9, 12, 51, tzinfo=timezone(timedelta(hours=1)))
JS = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def test_rest_en_totaal_van_nu(make_coordinator, monkeypatch):
    c = make_coordinator({})
    monkeypatch.setattr(mod.dt_util, "now", lambda: NU)
    c.pv_production_today_kwh = 4.18
    c.voorspelde_zon_vandaag_kwh = lambda nu: (5.0, "vastgelegd om 07:00")
    c._estimate_pv_kwh_for_period = lambda a, b, veilig=False: 2.51
    z = c.get_solar_today(NU)
    assert z["rest_kwh"] == 2.51 and z["verwacht_nu_kwh"] == 6.7
    assert z["voorspeld_kwh"] == 5.0


def test_cockpit_toont_de_eigen_rest():
    assert "zon.rest_kwh" in JS and "verwacht_nu_kwh" in JS and "Solcast" in JS
    assert "altijd beschermd" not in JS and "nooit verkocht" not in JS
