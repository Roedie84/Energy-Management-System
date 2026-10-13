"""v5.94: echte verkoop gescheiden van regeloverschot (L-EMS-022), de
verkoopvrijgave op het moment van export, en planvolging waarin oorzaak en
status elkaar niet tegenspreken (L-EMS-023). Alleen meten; stuurt niets."""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import planvolging

TZ = timezone(timedelta(hours=2))
NU = datetime(2026, 10, 11, 19, 45, 7, tzinfo=TZ)


def _c(make_coordinator, net_w=-1850.0, accu_w=2400.0, pv_w=0.0, reden="expensive_quarter",
       mag=False):
    c = make_coordinator({"update_interval_seconds": 60})
    c.beschikbare_energie_kwh = lambda: 6.05
    c._read_sensor_float = lambda _e: net_w
    c._read_corrected_battery_power = lambda: accu_w
    c._lees_pv_vermogen_w = lambda: pv_w
    c._read_corrected_consumption_power = lambda: 550.0
    c.last_reason = reden
    c.last_sell_check = {"mag_verkopen": mag, "nodig_voor_woning_kwh": 6.58}
    return c


def _regel(c):
    return c.dagverloop[NU.date().isoformat()][-1]


def test_verkoop_zonder_vrijgave_blijft_zichtbaar(make_coordinator):
    """11-10 19:45: expensive_quarter, 1,85 kW naar het net, toets zei nee."""
    c = _c(make_coordinator)
    for m in range(8):
        c._leg_dagverloop_vast(NU + timedelta(minutes=m))
    r = _regel(c)
    assert r["verkocht"] is True
    assert r["export_uit_accu_kwh"] > 0.2
    assert r["eerste_export_om"] == "19:45:07"
    assert r["mag_verkopen_bij_export"] is False
    assert r["export_zonder_vrijgave_rondes"] == 8
    assert r["marge_bij_eerste_export_kwh"] == -0.53
    attr = c.sturing_meetattributen()
    assert len(attr["verkoopkwartieren"]) == 1
    assert attr["verkoopkwartieren"][0]["mag_verkopen_bij_export"] is False


def test_regeloverschot_telt_niet_als_verkoop(make_coordinator):
    """12-10 16:15: accu ontlaadt ~1 kW voor het huis, kort 200 W terug."""
    c = _c(make_coordinator, net_w=-200.0, accu_w=1000.0, reden="default_smart", mag=False)
    c._leg_dagverloop_vast(NU)
    c._read_sensor_float = lambda _e: 50.0
    for m in range(1, 5):
        c._leg_dagverloop_vast(NU + timedelta(minutes=m))
    r = _regel(c)
    assert r["verkocht"] is False
    assert r["regeloverschot_kwh"] > 0
    assert r["marge_bij_export_min_kwh"] is not None   # ruw blijft bestaan
    attr = c.sturing_meetattributen()
    assert attr["verkoopkwartieren"] == []
    assert attr["regeloverschot_kwh"][NU.date().isoformat()] > 0


def test_te_weinig_export_is_geen_verkoop(make_coordinator):
    c = _c(make_coordinator, net_w=-150.0, accu_w=600.0, mag=True)
    c._leg_dagverloop_vast(NU)
    r = _regel(c)
    assert r["export_uit_accu_kwh"] < 0.025 and r["verkocht"] is False


def test_zon_export_is_geen_accuverkoop(make_coordinator):
    c = _c(make_coordinator, net_w=-2000.0, accu_w=0.0, pv_w=2500.0)
    for m in range(5):
        c._leg_dagverloop_vast(NU + timedelta(minutes=m))
    r = _regel(c)
    assert r["export_kwh"] > 0.1 and r["export_uit_accu_kwh"] == 0
    assert r["verkocht"] is False


def test_planvolging_oorzaak_volgt_status():
    gepland = {"accu_w": -1322.0, "zon_w": 2000.0, "huis_w": 500.0, "modus": "smart"}
    # verklaard door zon: oorzaak nooit "accu"
    u = planvolging.beoordeel(gepland, -1477.0, 2150.0, 500.0)
    assert u["status"] == "verklaard" and u["oorzaak"] == "zon"
    # grote rest, maar zon grootste bijdrage: toch afwijking accu met oorzaak accu
    gepland = {"accu_w": 1000.0, "zon_w": 0.0, "huis_w": 1000.0, "modus": "smart"}
    u = planvolging.beoordeel(gepland, 2600.0, 0.0, 1300.0)
    assert u["status"] == "afwijking accu" and u["oorzaak"] == "accu"
    gepland = {"accu_w": -2000.0, "zon_w": 3000.0, "huis_w": 500.0, "modus": "smart"}
    u = planvolging.beoordeel(gepland, -200.0, 1000.0, 500.0)   # minder zon + rest 200
    assert u["status"] == "afwijking accu" and u["oorzaak"] == "accu"
