"""v5.81 (L-EMS-018, leerronde 11-10): verkooptoets en spaarplan per kwartier
in het dagverloop - alleen meten, stuurt niets.

Aanleiding 10-10 18:45-19:00: de beschikbare energie zakte van 6,91 naar 6,22
kWh tegen een reserve tot het blok van 6,78. Achteraf was dat niet na te
rekenen: het dagverloop had alleen `mag_verkopen`, en het spaarplan (8,1 kWh
nodig tot het blok) en de verkooptoets (<= 5,5) stonden nergens naast elkaar.
"""
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=2))
NU = datetime(2026, 10, 10, 18, 46, tzinfo=TZ)


def _c(make_coordinator, beschikbaar=6.91, net_w=-1850.0):
    c = make_coordinator({"update_interval_seconds": 60})
    c.beschikbare_energie_kwh = lambda: beschikbaar
    c._read_sensor_float = lambda _e: net_w
    c.last_sell_check = {
        "mag_verkopen": True, "nodig_voor_woning_kwh": 6.78,
        "vrij_te_verkopen_kwh": 0.13, "nodig_tot_blok_kwh": 5.42,
        "nodig_na_blok_kwh": 1.2,
    }
    c.last_spaarplan = {"nodig_tot_blok_kwh": 8.1}
    return c


def _regel(c, moment=NU):
    return c.dagverloop[moment.date().isoformat()][-1]


def test_dagverloop_bewaart_verkoopreserve_vrij_en_spaarplan(make_coordinator):
    c = _c(make_coordinator)
    c._leg_dagverloop_vast(NU)
    r = _regel(c)
    assert r["verkoopreserve_kwh"] == 6.78
    assert r["vrij_kwh"] == 0.13
    assert r["nodig_tot_blok_kwh"] == 5.42
    assert r["nodig_na_blok_kwh"] == 1.2
    assert r["spaarplan_nodig_tot_blok_kwh"] == 8.1
    assert r["marge_kwh"] == 0.13


def test_verkoop_onder_de_reserve_blijft_zichtbaar_in_het_kwartier(make_coordinator):
    """Halverwege onder de reserve, aan het eind van het kwartier gestopt:
    de laatste ronde wint, maar de kleinste marge bij export blijft staan."""
    c = _c(make_coordinator, beschikbaar=6.91)
    c._leg_dagverloop_vast(NU)
    c.beschikbare_energie_kwh = lambda: 6.22
    c._leg_dagverloop_vast(NU + timedelta(minutes=8))
    c.beschikbare_energie_kwh = lambda: 6.20
    c._read_sensor_float = lambda _e: 300.0   # gestopt: weer afname
    c._leg_dagverloop_vast(NU + timedelta(minutes=12))
    r = _regel(c)
    assert len(c.dagverloop[NU.date().isoformat()]) == 1
    assert r["marge_bij_export_min_kwh"] == -0.56
    assert r["marge_kwh"] == -0.58


def test_regelverschuiving_telt_niet_als_export(make_coordinator):
    c = _c(make_coordinator, beschikbaar=2.16, net_w=-48.0)
    c.last_sell_check = {"mag_verkopen": False, "nodig_voor_woning_kwh": 3.0}
    c._leg_dagverloop_vast(NU)
    r = _regel(c)
    assert r["marge_bij_export_min_kwh"] is None
    assert r["vrij_kwh"] == 0.0
    assert r["marge_kwh"] == -0.84


def test_nieuw_kwartier_begint_opnieuw(make_coordinator):
    c = _c(make_coordinator, beschikbaar=6.22)
    c._leg_dagverloop_vast(NU)
    c.beschikbare_energie_kwh = lambda: 7.5
    c._leg_dagverloop_vast(NU + timedelta(minutes=15))
    reeks = c.dagverloop[NU.date().isoformat()]
    assert len(reeks) == 2
    assert reeks[0]["marge_bij_export_min_kwh"] == -0.56
    assert reeks[1]["marge_bij_export_min_kwh"] == 0.72


def test_zonder_verkooptoets_en_spaarplan_leeg(make_coordinator):
    c = make_coordinator({"update_interval_seconds": 60})
    c.last_sell_check = None
    c.last_spaarplan = None
    c._leg_dagverloop_vast(NU)
    r = _regel(c)
    for veld in ("verkoopreserve_kwh", "vrij_kwh", "spaarplan_nodig_tot_blok_kwh",
                 "marge_kwh", "marge_bij_export_min_kwh"):
        assert r[veld] is None
