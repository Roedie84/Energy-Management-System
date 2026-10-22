"""v5.119.0: meetfouten in de rapportage (akkoord Ruud 22-10 18:05).

L-EMS-024: dagarchief - verwachting van de ochtend en accu-opbrengst met
voorraadverschil. L-EMS-029: MC-kalibratie op dezelfde horizon als de
tekortnacht. L-EMS-030: digital twin laadt met het laadrendement.
Sturing verandert niet.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from custom_components.energy_management_system import dagarchief as D
from custom_components.energy_management_system.const import MC_KANS_BASIS_TOT_BLOK

TZ = timezone(timedelta(hours=2))


# --- L-EMS-024 -----------------------------------------------------------------

def test_accu_opbrengst_20_10_met_voorraad():
    """20-10: geladen 9,65, ontladen 3,98 kWh, b was -1,02."""
    regel = {"l": 9.65, "o": 3.98, "k": 3.00, "kz": 1.98, "b": -1.02, "pg": 25.0}
    uit = D.met_voorraad(regel, 0.85)
    # (9,65 x 0,85 - 3,98) x 0,25 = 1,055
    assert uit["bv"] in (1.05, 1.06)
    assert uit["b"] == round(1.98 - 3.00 + (9.65 * 0.85 - 3.98) * 0.25, 2)
    assert regel["b"] == -1.02                       # origineel ongemoeid


def test_accu_opbrengst_zonder_gegevens_ongewijzigd():
    assert D.met_voorraad({"l": 1.0, "o": 1.0, "kz": 1.0}, 0.85) == {"l": 1.0, "o": 1.0, "kz": 1.0}
    assert "bv" not in D.met_voorraad({"l": 1.0, "o": 1.0, "k": 1.0, "kz": 1.0, "pg": 20.0}, None)
    assert D.met_voorraad(None, 0.85) is None
    assert D.NAMEN["bv"] == "accu_voorraadcorrectie_eur"


def test_ochtendverwachting_niet_het_lege_middernachtkwartier(make_coordinator):
    c = make_coordinator({})
    c.solar_tracker = None
    verwachting = {
        "00:00": {"zon_kwh": 0.0, "verbruik_kwh": 9.0},
        "00:15": {"zon_kwh": 6.7, "verbruik_kwh": 8.9},
        "08:00": {"zon_kwh": 6.5, "verbruik_kwh": 6.0},
        "12:00": {"zon_kwh": 9.0, "verbruik_kwh": 4.0},   # na 09:00: telt niet
    }
    begin = c._ochtendverwachting("2026-10-20", verwachting)
    assert begin == {"zon_kwh": 6.7, "verbruik_kwh": 8.9}


def test_ochtendverwachting_valt_terug_op_day_ahead(make_coordinator):
    c = make_coordinator({})
    c.solar_tracker = SimpleNamespace(last_compared_date="2026-10-21", last_predicted_kwh=7.82)
    begin = c._ochtendverwachting("2026-10-21", {"00:00": {"zon_kwh": 0.0, "verbruik_kwh": 9.0}})
    assert begin["zon_kwh"] == 7.82 and begin["verbruik_kwh"] == 9.0
    assert c._ochtendverwachting("2026-10-21", {}) is None


# --- L-EMS-029 -----------------------------------------------------------------

def _record(nacht_tot, kans, tekort, horizon_tot=None):
    stand = {"kans_pct": kans, "basis": MC_KANS_BASIS_TOT_BLOK}
    if horizon_tot:
        stand["horizon_tot"] = horizon_tot
        stand["uren_tot_blok"] = 31.2
    return {"date": nacht_tot, "shortfall": tekort, "mc_22u": stand}


def test_kalibratie_sluit_andere_horizon_uit(make_coordinator):
    c = make_coordinator({})
    c.reserve_daily_records = [
        _record("2026-10-22", 100.0, False, "2026-10-22T10:45:00+02:00"),   # blok ochtend: telt
        _record("2026-10-23", 95.0, False, "2026-10-23T21:15:00+02:00"),    # blok 21:15 morgen: apart
        _record("2026-10-21", 20.0, False),                                  # oude stand: telt
    ]
    k = c.get_mc_kalibratie_22u()
    assert k["nachten"] == 2
    assert k["brier"] == round((1.0 ** 2 + 0.2 ** 2) / 2, 3)
    assert [n["nacht_tot"] for n in k["nachten_andere_horizon"]] == ["2026-10-23"]
    assert k["nachten_andere_horizon"][0]["uren_tot_blok"] == 31.2


def test_22u_stand_bewaart_horizon(make_coordinator):
    c = make_coordinator({})
    nu = datetime(2026, 10, 22, 22, 0, tzinfo=TZ)
    c.last_cheap_block_start = datetime(2026, 10, 23, 21, 15, tzinfo=TZ)
    h = c._mc_22u_horizon(nu)
    assert h == {"horizon_tot": "2026-10-23T21:15:00+02:00", "uren_tot_blok": 23.2}
    c.last_cheap_block_start = None
    assert c._mc_22u_horizon(nu)["horizon_tot"] is None


def test_horizon_grens_12_uur(make_coordinator):
    c = make_coordinator({})
    assert c._mc_horizon_vergelijkbaar({"horizon_tot": "2026-10-23T12:00:00+02:00"}, "2026-10-22")
    assert not c._mc_horizon_vergelijkbaar({"horizon_tot": "2026-10-23T12:15:00+02:00"}, "2026-10-22")
    assert c._mc_horizon_vergelijkbaar({}, "2026-10-22")


# --- L-EMS-030 -----------------------------------------------------------------

def test_twin_laadt_met_laadrendement(make_coordinator, monkeypatch):
    c = make_coordinator({})
    monkeypatch.setattr(type(c), "learned_charge_efficiency_percent", property(lambda s: 85.0))
    erin, net = c._twin_laadstap(10.0, 2.4)            # 1 u op 2,4 kW
    assert round(erin, 2) == 2.04 and round(net, 2) == 2.4
    erin, net = c._twin_laadstap(1.0, 2.4)             # bijna vol
    assert erin == 1.0 and round(net, 3) == round(1.0 / 0.85, 3)


def test_twin_laadfactor_terugval(make_coordinator, monkeypatch):
    c = make_coordinator({})
    monkeypatch.setattr(type(c), "learned_charge_efficiency_percent", property(lambda s: None))
    monkeypatch.setattr(type(c), "learned_battery_efficiency_percent", property(lambda s: 81.0))
    assert round(c._twin_laadfactor(), 3) == 0.9
