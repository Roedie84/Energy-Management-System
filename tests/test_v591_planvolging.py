"""Planvolging: gepland tegen gemeten accuvermogen (v5.91).

Gevraagd (12-10): "Wordt er ook rekening gehouden met hoeveel W de accu nu al
laadt ten opzichte van de planning en of dit verwacht was?"

Tekenafspraak: positief is ontladen, negatief is laden.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import planvolging as pv

NU = datetime(2026, 10, 12, 9, 31, tzinfo=timezone.utc)
KWARTIER = NU.replace(minute=30)


def _gepland(accu_w=-300, zon_w=900, huis_w=400, modus="smart"):
    return {"kwartier": KWARTIER.isoformat(), "van": "09:30", "modus": modus,
            "accu_w": accu_w, "zon_w": zon_w, "huis_w": huis_w}


def test_gepland_uit_de_planregel():
    rij = {"start": KWARTIER.isoformat(), "van": "09:30", "modus": "smart",
           "soc_kwh": 3.075, "zon_kwh": 0.225, "verbruik_kwh": 0.1}

    g = pv.gepland_uit_plan(rij, 3.0)

    assert g["accu_w"] == -300  # 0,075 kWh erbij in een kwartier = 300 W laden
    assert g["zon_w"] == 900
    assert g["huis_w"] == 400


def test_volgens_plan():
    o = pv.beoordeel(_gepland(), -350, 950, 400)

    assert o["status"] == "volgens plan"
    assert "volgens plan" in o["tekst"]


def test_meer_zon_verklaart_harder_laden():
    """Het voorbeeld uit de vraag: gepland 0,3 kW laden, het wordt 1,8 kW."""
    o = pv.beoordeel(_gepland(), -1800, 2400, 400)

    assert o["oorzaak"] == "zon"
    assert o["status"] == "verklaard"
    assert "meer zon" in o["tekst"]
    assert abs(o["onverklaard_w"]) < pv.DREMPEL_W


def test_meer_verbruik_verklaart_ontladen():
    o = pv.beoordeel(_gepland(accu_w=0, zon_w=0, huis_w=400), 1500, 0, 1900)

    assert o["oorzaak"] == "verbruik"
    assert o["status"] == "verklaard"


def test_de_accu_zelf_wijkt_af():
    """Zon en verbruik zoals voorspeld, maar de accu laadt niet: vol,
    begrensd, of een andere stand dan bedoeld."""
    o = pv.beoordeel(_gepland(), 0, 900, 400)

    assert o["oorzaak"] == "accu"
    assert o["status"] == "afwijking accu"


def test_in_een_handmatige_stand_ligt_het_vermogen_vast():
    """Bij verkopen gaat extra zon naar het net; wijkt de accu af, dan is
    dat de accu zelf."""
    o = pv.beoordeel(_gepland(accu_w=2400, modus="manual (verkopen)"), 1200, 2500, 400)

    assert o["oorzaak"] == "accu"


def test_zonder_meting_of_plan_niets():
    assert pv.beoordeel(None, -500, 0, 0) == {"beschikbaar": False}
    assert pv.beoordeel(_gepland(), None, 0, 0) == {"beschikbaar": False}


def test_een_kwartier_wordt_op_het_gemiddelde_beoordeeld():
    monsters = [{"accu_w": -1800, "zon_w": 2400, "huis_w": 400}, {"accu_w": -200, "zon_w": 800, "huis_w": 400}]

    o = pv.sluit_kwartier(_gepland(), monsters)

    assert o["gemeten_accu_w"] == -1000
    assert o["monsters"] == 2


def test_de_dagsamenvatting():
    k = [
        {"verschil_w": 0, "oorzaak": "geen", "status": "volgens plan"},
        {"verschil_w": -1500, "oorzaak": "zon", "status": "verklaard"},
        {"verschil_w": 300, "oorzaak": "accu", "status": "afwijking accu"},
        {"verschil_w": 50, "oorzaak": "geen", "status": "volgens plan"},
    ]

    d = pv.dagsamenvatting("2026-10-12", k)

    assert d["volgens_plan_procent"] == 50.0
    assert d["afwijking_accu"] == 1
    assert d["oorzaken"] == {"geen": 2, "zon": 1, "accu": 1}


# --- in de coordinator -------------------------------------------------


def _coordinator(make_coordinator, accu=-1800.0, zon=2400.0, huis=400.0):
    c = make_coordinator({})
    c._read_sensor_float = lambda entity: 8.64
    c.effective_min_soc_percent = lambda: 10
    c.beschikbare_energie_kwh = lambda: 3.0
    c.get_quarter_plan = lambda now=None: [
        {"start": (KWARTIER + timedelta(minutes=15 * i)).isoformat(), "van": "09:30",
         "modus": "smart", "soc_kwh": 3.075, "zon_kwh": 0.225, "verbruik_kwh": 0.1}
        for i in range(3)
    ]
    c._read_corrected_battery_power = lambda: accu
    c._live_pv_w = lambda: zon
    c._read_corrected_consumption_power = lambda: huis
    return c


def test_live_gepland_tegen_gemeten(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    c._volg_plan(NU)
    nu = c.get_planvolging()["nu"]

    assert nu["gepland_accu_w"] == -300
    assert nu["gemeten_accu_w"] == -1800
    assert nu["oorzaak"] == "zon"


def test_het_plan_wordt_aan_het_begin_van_het_kwartier_vastgelegd(make_coordinator, hass):
    """De planning daarna rekent vanaf de echte stand en is geen maat meer."""
    c = _coordinator(make_coordinator)
    c._volg_plan(NU)
    c.get_quarter_plan = lambda now=None: []

    c._volg_plan(NU + timedelta(minutes=5))

    assert c.get_planvolging()["nu"]["gepland_accu_w"] == -300
    assert len(c._planvolging["monsters"]) == 2


def test_kwartier_en_dagwissel(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c._volg_plan(NU)
    c._volg_plan(NU + timedelta(minutes=15))
    assert len(c._planvolging_kwartieren) == 1
    assert c._planvolging_kwartieren[0]["dag"] == NU.date().isoformat()

    c._volg_plan(NU + timedelta(days=1))

    assert c.planvolging_dagen[-1]["dag"] == NU.date().isoformat()
    assert c.get_planvolging()["dagen"][-1]["kwartieren"] >= 1


def test_alleen_de_dagsamenvatting_wordt_bewaard():
    """Per kwartier staat het huisverbruik erin - dat blijft vluchtig
    (privacykeuze van v5.28)."""
    from custom_components.energy_management_system.const import PERSISTED_FIELDS

    assert "planvolging_dagen" in PERSISTED_FIELDS
    assert "_planvolging_kwartieren" not in PERSISTED_FIELDS
    assert "_planvolging" not in PERSISTED_FIELDS


def test_planvolging_stuurt_niets():
    import ast
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    for fn in (C._volg_plan, C._planvolging_gepland, C._planvolging_dagwissel, C.get_planvolging):
        boom = ast.parse(inspect.getsource(fn).lstrip())
        aanroepen = {
            n.func.attr for n in ast.walk(boom)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }
        assert not aanroepen & {"_async_apply_operation", "_async_apply_manual", "async_call"}


def test_de_kaart_toont_de_planvolging():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    js = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")
    assert "_planvolgingRegel" in js
    assert '"planvolging"' in js
    assert 'stroom: ["pv", "net", "accu_vermogen", "huis", "soc", "plan"]' in js
