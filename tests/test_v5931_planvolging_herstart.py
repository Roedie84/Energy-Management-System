"""v5.93.1: planvolging over een herstart.

Gemeld 12-10 12:43 (schermafdruk Energiestroom): na de herstart van 12:38 was
het blok met gepland/gemeten weg. Het kwartierplan was bij de eerste ronde na
de herstart nog niet klaar; het kwartier bleef daardoor tot 12:45 leeg. En de
kwartieren van vandaag gingen bij elke herstart verloren.
"""
from datetime import timedelta

from test_v591_planvolging import KWARTIER, NU, _coordinator


def test_plan_later_in_het_kwartier_alsnog_vastgelegd(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    plan = c.get_quarter_plan
    c.get_quarter_plan = lambda now=None: []  # net na de herstart: nog geen plan
    c._volg_plan(NU)
    assert c.get_planvolging()["nu"] == {"beschikbaar": False}

    c.get_quarter_plan = plan
    c._volg_plan(NU + timedelta(minutes=1))
    nu = c.get_planvolging()["nu"]
    assert nu["beschikbaar"] and nu["gepland_accu_w"] == -300


def test_kwartieren_van_vandaag_overleven_een_herstart(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c._volg_plan(NU)
    c._volg_plan(NU + timedelta(minutes=15))
    c._volg_plan(NU + timedelta(minutes=30))
    assert len(c._planvolging_kwartieren) == 2
    bewaard = c.planvolging_vandaag
    assert len(bewaard) == 2
    # stand, oorzaak, accuverschil en (v5.99) zonverschil; geen huisverbruik
    assert all(set(k) == {"dag", "van", "status", "oorzaak", "verschil_w", "zon_verschil_w"} for k in bewaard)

    na = _coordinator(make_coordinator)
    na.planvolging_vandaag = bewaard
    na._volg_plan(NU + timedelta(minutes=45))
    # niet via get_planvolging()["vandaag"]: dat kijkt naar de echte klok
    from custom_components.energy_management_system import planvolging as pv

    vandaag = [k for k in na._planvolging_kwartieren if k["dag"] == NU.date().isoformat()]
    assert len(vandaag) == 2
    assert pv.dagsamenvatting(NU.date().isoformat(), vandaag)["kwartieren"] == 2


def test_veld_wordt_bewaard():
    from custom_components.energy_management_system.const import PERSISTED_FIELDS

    assert "planvolging_vandaag" in PERSISTED_FIELDS
    assert "_planvolging_kwartieren" not in PERSISTED_FIELDS


# --- airco: waar "niet verwacht" op rust (gevraagd 12:54) ---------------

from datetime import datetime, timezone  # noqa: E402

from custom_components.energy_management_system import airco_ritme  # noqa: E402

VAN = datetime(2026, 10, 12, 13, 0, tzinfo=timezone.utc)
TOT = VAN + timedelta(hours=4)


def test_basis_nooit_aan():
    ritme = {"uurverbruik": {str(h): [0.0] * 9 for h in range(24)}}
    b = airco_ritme.verwachting_basis(ritme, VAN, TOT)
    assert b["dagen"] == 9 and b["uren_met_data"] == 4 and b["meeste_dagen_aan"] == 0
    assert b["tekst"] == "9 dagen gemeten, in deze uren nooit aan"


def test_basis_soms_aan_en_te_weinig_data():
    ritme = {"uurverbruik": {"13": [0.0, 0.3, 0.0, 0.4], "14": [0.0, 0.0, 0.0, 0.0], "15": [0.1]}}
    b = airco_ritme.verwachting_basis(ritme, VAN, TOT)
    assert b["meeste_dagen_aan"] == 2 and b["uren_met_data"] == 2
    assert "hooguit 2x aan" in b["tekst"] and "2 van 4 uur nog te weinig gemeten" in b["tekst"]


def test_basis_zonder_data():
    b = airco_ritme.verwachting_basis({}, VAN, TOT)
    assert b["uren_met_data"] == 0 and "te weinig gemeten" in b["tekst"]


def test_verwachting_geeft_basis_en_knop(make_coordinator):
    c = make_coordinator({})
    c.last_cheap_block_start = VAN + timedelta(hours=4)
    c._airco_ochtend_extra_kwh = lambda now, tot: {"extra_kwh": 0.0, "verwacht_kwh": 0.0}
    c._airco_gebruik_extra_kwh = lambda now, tot: {"extra_kwh": 0.0, "verwacht_kwh": 0.0, "uren": []}
    c._airco_ritme = lambda: {"uurverbruik": {str(h): [0.0] * 5 for h in range(24)}}
    c.airco_automaat_aan = False
    v = c.get_airco_verwachting(VAN)
    assert v["basis"]["tekst"] == "5 dagen gemeten, in deze uren nooit aan"
    assert v["knop_automaat"] is False


def test_cockpit_toont_de_basis():
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "custom_components" / "energy_management_system"
          / "www" / "ems-cockpit.js").read_text(encoding="utf-8")
    assert "vw.basis && vw.basis.tekst" in js and "knop automaat uit" in js
