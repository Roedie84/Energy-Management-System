"""v5.193.0 (L-EMS-075): 'bijladen loonde' onder het waardeplan opnieuw toetsen.

Dagcontrole 08-11: de nachten naar 4 t/m 7 november stonden als 'bijladen
loonde, maar de accu werd niet vol'. Het waardeplan laadde de kwartieren die
loonden; een extra kWh kostte meer dan hij waard was (nacht naar 8-11: 33,6 ct
waard, minstens 39,7 ct). Ze hielden de cockpit op LET OP en telden als
tekortdag. Akkoord Ruud 08-11 09:26.
"""
from datetime import datetime, timedelta

from custom_components.energy_management_system.const import TEKORT_REDEN_LOONDE
from tests.test_v541_tekort_economisch import _c


def _verloop(laad_kwartieren, prijs_vrij, nachtprijs=40.0):
    """09:00-09:00 op 2/3 okt; het plan laadt in `laad_kwartieren` (index),
    vanaf 03:00 is de accu leeg en komt 200 W uit het net."""
    dagen = {"2026-10-02": [], "2026-10-03": []}
    for k in range(96):
        moment = datetime(2026, 10, 2, 9, 0) + timedelta(minutes=15 * k)
        tekort = k >= 72
        laadt = k in laad_kwartieren
        dagen[moment.date().isoformat()].append({
            "tijd": moment.strftime("%H:%M"), "soc": 55,
            "net_w": 200.0 if tekort else (800.0 if laadt else 0.0),
            "accu_w": 0.0 if tekort else (-800.0 if laadt else 0.0),
            "prijs_ct": nachtprijs if tekort else (20.0 if laadt else prijs_vrij),
            "reden": "waardeplan_laden" if laadt else "waardeplan_huis",
            "stand": "smart",
        })
    return dagen


def _records(c, verloop):
    c.dagverloop = verloop
    c.reserve_daily_records = [{
        "date": "2026-10-03", "shortfall": True, "tekortnacht_kwh": 1.2,
        "tekort_soort": "planning", "tekort_reden": TEKORT_REDEN_LOONDE,
    }]
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 4.2}


def test_extra_kwh_loonde_niet_wordt_economisch(make_coordinator, hass):
    # tekort 40 ct x ~0,84 - 4,2 = ~29 ct; vrije kwartieren 39,7 ct
    c = _c(make_coordinator, hass)
    _records(c, _verloop({20, 21, 22}, prijs_vrij=39.7))
    assert c._toets_laadnachten_op_economie() == 1
    r = c.reserve_daily_records[0]
    assert r["tekort_soort"] == "economisch" and "extra kWh" in r["tekort_reden"]
    assert c.get_tekortsoorten()["tekortnachten_planning"] == 0


def test_extra_kwh_had_geloond_blijft_staan(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _records(c, _verloop({20, 21, 22}, prijs_vrij=15.0))
    assert c._toets_laadnachten_op_economie() == 0
    r = c.reserve_daily_records[0]
    assert r["tekort_soort"] == "planning" and r["economietoets"] == "v5.193"


def test_een_keer_per_nacht(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _records(c, _verloop({20}, prijs_vrij=39.7))
    c._toets_laadnachten_op_economie()
    c.reserve_daily_records[0].update(tekort_soort="planning", tekort_reden=TEKORT_REDEN_LOONDE)
    assert c._toets_laadnachten_op_economie() == 0


def test_zonder_dagverloop_later_opnieuw(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _records(c, {})
    assert c._toets_laadnachten_op_economie() == 0
    assert "economietoets" not in c.reserve_daily_records[0]


def test_live_nacht_wordt_economisch(make_coordinator, hass):
    c = _c(make_coordinator, hass)
    _records(c, _verloop({20, 21, 22}, prijs_vrij=39.7))
    c._tekort_soort = lambda *a, **k: "planning"
    c._tekort_reden = lambda soort: TEKORT_REDEN_LOONDE
    c._tekort_venster_begin = lambda now: datetime(2026, 10, 3, 9, 0)
    c._deel_afgelopen_nacht_in(datetime(2026, 10, 3, 9, 0))
    assert c._tekort_soort_vandaag == "economisch"
    assert "extra kWh" in c._tekort_reden_vandaag
