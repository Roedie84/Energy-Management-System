"""v5.183.1: 'Accu leeg' pas als de accu niets meer levert; ondergrens in de grafiek.

04-11 14:33 (Ruud): "Accu leeg maar accu lijn in grafiek nog niet op 10%". De
kwartieren 20:00-20:45 heetten al tekort terwijl de accu nog ~615 W leverde
(13 -> 10 %); en leeg = de ondergrens (10 %), niet 0 % op de as.
"""
from pathlib import Path

import custom_components.energy_management_system as pkg

JS = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def test_levert_nog_dus_geen_tekort(make_coordinator):
    c = make_coordinator({})
    t = c._waardeplan_tekort
    assert t({"actie": "huis", "net_kwh": 0.05, "inhoud_kwh": 0.1, "accu_kwh": -0.15}) is False
    assert t({"actie": "houden", "net_kwh": 0.15, "inhoud_kwh": 0.0, "accu_kwh": 0.0}) is True


def test_ondergrens_in_de_grafiek():
    assert 'num((rijen[0] || {}).ondergrens_procent)' in JS
    assert '<line class="vloer"' in JS
    assert "leeg (${fmt(vloer)} %)" in JS
    code = (Path(pkg.__file__).parent / "waardeplan_sturing.py").read_text(encoding="utf-8")
    assert '"ondergrens_procent": round(min_soc)' in code
