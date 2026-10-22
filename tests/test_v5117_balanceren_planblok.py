"""v5.117.0: balanceerlading, en plan gelijk aan de beslissing bij blok en dip.

22-10: module 4 remde het laden af (2,0 i.p.v. 2,4 kW) met een cel op 3,45 V
bij 78 %; de accu was 8 dagen niet vol. En om 15:00 zei het plan "laden"
(dagdrempel 27,5 ct, prijs 26,4 ct) terwijl het blok al voorbij was en de
beslissing spaarde.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import dipplan
from custom_components.energy_management_system.const import (
    BALANCEER_NA_DAGEN,
    PERSISTED_FIELDS,
)
from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)

TZ = timezone(timedelta(hours=2))
NU = datetime(2026, 10, 22, 15, 0, tzinfo=TZ)


# --- 1. het plan kent alleen het blok van de beslissing -------------------

def _netregels_blok(start, eind):
    return {"blok": (start, eind)}


def test_dagdrempel_telt_niet_voor_het_bekende_blok():
    blok = (NU.replace(hour=21, minute=15), NU.replace(hour=23, minute=0))
    drempel = lambda _m: 0.275  # noqa: E731
    assert C._plan_in_laadblok(0.264, NU, _netregels_blok(*blok), drempel) is False
    assert C._plan_in_laadblok(0.40, NU.replace(hour=21, minute=30), _netregels_blok(*blok), drempel) is True


def test_na_het_bekende_blok_weer_de_dagdrempel():
    blok = (NU.replace(hour=21, minute=15), NU.replace(hour=23, minute=0))
    drempel = lambda _m: 0.275  # noqa: E731
    morgen = NU + timedelta(days=1)
    assert C._plan_in_laadblok(0.25, morgen, _netregels_blok(*blok), drempel) is True
    assert C._plan_in_laadblok(0.30, morgen, _netregels_blok(*blok), drempel) is False


def test_zonder_blok_de_dagdrempel():
    drempel = lambda _m: 0.275  # noqa: E731
    assert C._plan_in_laadblok(0.264, NU, {"blok": (None, None)}, drempel) is True


# --- 2. dip in het plan met de kwartieren van de beslissing --------------

def _k(uur, minuut=0, dag=0):
    return NU.replace(hour=uur, minute=minuut) + timedelta(days=dag)


def _netregels(reeks):
    return {"slijtage_ct": 11.0, "rendement": 84.0, "laad_per_kwartier": 0.6, "reeks": reeks}


def test_dip_laadt_als_het_loont_en_nu_het_goedkoopst_is():
    dip = [(_k(15), 0.20, 0.2), (_k(19), 0.48, 1.0), (_k(20), 0.45, 1.0)]
    reeks = [(b, p) for b, p, _d in dip]
    # 1,0 kWh dekt 19:00; 20:00 (45 ct) blijft over: 45 x 84 % - 11 = 26,8 > 20
    assert dipplan.plan_dip_laadt(_netregels(reeks), dip, _k(15), 0.20, 1.0, 5.0, 0.6) == 0.6


def test_dip_laadt_niet_als_er_eerst_goedkopere_kwartieren_komen():
    dip = [(_k(15), 0.20, 0.2), (_k(19), 0.48, 1.0), (_k(20), 0.45, 0.3)]
    # Er ontbreekt 0,5 kWh (één kwartier laden). Een goedkoper kwartier in het blok (niet in de dipkwartieren) telt mee,
    # net als in `_goedkoopste_laadmomenten`.
    reeks = [(b, p) for b, p, _d in dip] + [(_k(17), 0.15)]
    assert dipplan.plan_dip_laadt(_netregels(reeks), dip, _k(15), 0.20, 1.0, 5.0, 0.6) == 0.0


def test_dip_ook_kwartieren_na_het_blok_tellen_mee():
    # Zonder het kwartier na het blok haalt de accu het (1,0 >= 0,2 + 0,8).
    dip_kort = [(_k(15), 0.20, 0.2), (_k(19), 0.48, 0.8)]
    dip_lang = dip_kort + [(_k(7, dag=1), 0.47, 1.0), (_k(7, 15, dag=1), 0.46, 1.0)]
    reeks = [(b, p) for b, p, _d in dip_lang]
    assert dipplan.plan_dip_laadt(_netregels(reeks), dip_kort, _k(15), 0.20, 1.0, 5.0, 0.6) == 0.0
    assert dipplan.plan_dip_laadt(_netregels(reeks), dip_lang, _k(15), 0.20, 1.0, 5.0, 0.6) > 0


def test_dip_lege_lijst_laadt_nooit():
    assert dipplan.plan_dip_laadt(_netregels([]), [], _k(15), 0.10, 0.0, 5.0, 0.6) == 0.0


# --- 3. balanceerlading ---------------------------------------------------

def test_velden_bewaard():
    assert "balanceer_laatst_vol" in PERSISTED_FIELDS
    assert "balanceer_max_delta_v" in PERSISTED_FIELDS


def test_nodig_na_zeven_dagen(make_coordinator):
    c = make_coordinator({})
    c.balanceer_laatst_vol = (NU - timedelta(days=BALANCEER_NA_DAGEN, hours=1)).isoformat()
    assert c.balanceerlading(NU)["nodig"] is True
    c.balanceer_laatst_vol = (NU - timedelta(days=2)).isoformat()
    assert c.balanceerlading(NU)["nodig"] is False


def test_eerder_bij_celverschil_in_het_midden(make_coordinator):
    c = make_coordinator({})
    c.balanceer_laatst_vol = (NU - timedelta(days=5)).isoformat()
    c.balanceer_max_delta_v = 0.12
    assert c.balanceerlading(NU)["nodig"] is True


def test_volg_vol_en_celverschil(make_coordinator):
    c = make_coordinator({})
    c.balanceer_laatst_vol = (NU - timedelta(days=3)).isoformat()
    c.accustand_procent = lambda: 60.0
    c.battery_module_live = [
        {"cel_delta_v": 0.12, "soc_percent": 60.0},
        {"cel_delta_v": 0.30, "soc_percent": 10.0},  # onderin: telt niet
    ]
    c._volg_balanceren(NU)
    assert c.balanceer_max_delta_v == 0.12
    c.accustand_procent = lambda: 100.0
    c._volg_balanceren(NU)
    assert c.balanceer_laatst_vol == NU.isoformat()
    assert c.balanceer_max_delta_v is None


def test_eerste_start_uit_het_dagrapport(make_coordinator):
    c = make_coordinator({})
    c.daily_report_history = [
        {"datum": "2026-10-13", "soc_max_procent": 100.0},
        {"datum": "2026-10-14", "soc_max_procent": 99.5},
        {"datum": "2026-10-15", "soc_max_procent": 80.0},
    ]
    assert c._balanceer_laatst_vol_uit_dagrapport(NU).startswith("2026-10-14T23:59")
    c.daily_report_history = [{"datum": "2026-10-10", "soc_max_procent": 70.0}]
    assert c._balanceer_laatst_vol_uit_dagrapport(NU).startswith("2026-10-10")


def _klaar_voor_balans(c, monkeypatch, zon_vol=None, goedkoopst=True):
    c.balanceer_laatst_vol = (NU - timedelta(days=8)).isoformat()
    monkeypatch.setattr(c, "beschikbare_energie_kwh", lambda: 8.0)
    monkeypatch.setattr(c, "_zon_vol_om", lambda *a, **k: zon_vol)
    monkeypatch.setattr(c, "_goedkoopste_laadmomenten", lambda *a, **k: goedkoopst)


def test_balanceerlading_in_het_goedkoopste_kwartier(make_coordinator, monkeypatch):
    c = make_coordinator({})
    _klaar_voor_balans(c, monkeypatch)
    uit = c._balanceer_laadbesluit(NU, NU + timedelta(hours=2), 0.22, 2.0)
    assert uit["laden"] is True and uit["soort"] == "balanceren"


def test_geen_balanceerlading_als_de_zon_hem_vandaag_vol_maakt(make_coordinator, monkeypatch):
    c = make_coordinator({})
    _klaar_voor_balans(c, monkeypatch, zon_vol=NU + timedelta(hours=2))
    assert c._balanceer_laadbesluit(NU, NU + timedelta(hours=2), 0.22, 2.0) is None


def test_geen_balanceerlading_als_er_goedkopere_kwartieren_komen(make_coordinator, monkeypatch):
    c = make_coordinator({})
    _klaar_voor_balans(c, monkeypatch, goedkoopst=False)
    assert c._balanceer_laadbesluit(NU, NU + timedelta(hours=2), 0.22, 2.0) is None


def test_plan_balanceert_in_het_blok_zonder_hysterese(make_coordinator):
    c = make_coordinator({})
    blok = (_k(13), _k(15))
    reeks = [(_k(13) + timedelta(minutes=15 * i), 0.22 + 0.001 * i) for i in range(8)]
    netregels = {"slijtage_ct": 11.0, "rendement": 84.0, "laad_per_kwartier": 0.6,
                 "reeks": reeks, "blok": blok, "balanceren": True, "laadde_vorig": False,
                 "salderen": True}
    # 98 % vol (boven de hysterese van 97 %), 0,2 kWh ruimte; 14:45 is het
    # laatste kwartier van het blok, dus nu laden.
    assert c._plan_laadt(netregels, _k(15), 0.229, 9.8, 10.0, 0.6, 0.4) > 0


# --- v5.117.1: het plan kijkt vanaf wanneer het nodig is -------------------

def test_vanaf_moment_in_balanceerlading(make_coordinator):
    c = make_coordinator({})
    c.balanceer_laatst_vol = (NU - timedelta(days=6, hours=18)).isoformat()
    uit = c.balanceerlading(NU)
    assert uit["nodig"] is False
    assert datetime.fromisoformat(uit["vanaf"]) == NU + timedelta(hours=6)


def test_plan_balanceert_pas_vanaf_het_moment(make_coordinator):
    c = make_coordinator({})
    blok = (_k(13), _k(15))
    reeks = [(_k(13) + timedelta(minutes=15 * i), 0.22 + 0.001 * i) for i in range(8)]
    basis = {"slijtage_ct": 11.0, "rendement": 84.0, "laad_per_kwartier": 0.6,
             "reeks": reeks, "blok": blok, "laadde_vorig": False, "salderen": True}
    later = {**basis, "balanceren": _k(16)}
    eerder = {**basis, "balanceren": _k(12)}
    assert c._plan_laadt(later, _k(15), 0.229, 9.8, 10.0, 0.6, 0.4) == 0.0
    assert c._plan_laadt(eerder, _k(15), 0.229, 9.8, 10.0, 0.6, 0.4) > 0


def test_plan_balanceren_geeft_het_moment(make_coordinator, monkeypatch):
    c = make_coordinator({})
    c.balanceer_laatst_vol = (NU - timedelta(days=6, hours=18)).isoformat()
    monkeypatch.setattr(c, "_resterende_laadruimte_kwh", lambda: 5.0)
    assert c._plan_balanceren(NU) == NU + timedelta(hours=6)
