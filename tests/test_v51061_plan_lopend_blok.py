"""v5.106.1 - het plan kent het lopende goedkope blok, net als de beslissing.

Gemeld 20-10 14:36 (screenshot): "Waarom nu op manual? Dit is niet volgens
plan toch?" De accu laadde om 14:30 uit het net ("bijladen omdat het loont",
28,6 ct; een kWh is straks 43,3 x 85 % - 4,2 = 32,6 ct waard), het plan zei
voor dat kwartier "slim". De beslissing gebruikt het lopende blok (het
goedkoopste dal van wat nog komt: 14:15-14:45), het plan alleen de
dagdrempel, en de ochtend was veel goedkoper (11:00-14:15).
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import PRICE_SCALE_FACTOR

TZ = timezone(timedelta(hours=2))
DAG = datetime(2026, 10, 20, 0, 0, tzinfo=TZ)


def _prijs(t: datetime) -> float:
    if 11 <= t.hour < 14 or (t.hour == 14 and t.minute < 15):
        return 0.20                       # de ochtenddip van vandaag
    if t.hour == 14 and t.minute < 45:
        return 0.286                      # het lopende blok
    return 0.43


def _plan(make_coordinator, nu, blok):
    c = make_coordinator({"manual_charge_power": -2400, "manual_discharge_power": 2400})
    entries = [(DAG + timedelta(minutes=15 * i), DAG + timedelta(minutes=15 * (i + 1)),
                _prijs(DAG + timedelta(minutes=15 * i)) * PRICE_SCALE_FACTOR) for i in range(96)]
    c._get_forecast_entries = lambda *a, **k: entries
    c._read_sensor_float = lambda *a, **k: 11.5
    c.beschikbare_energie_kwh = lambda: 7.8
    c.effective_min_soc_percent = lambda: 0
    c._estimate_pv_kwh_for_period = lambda *a, **k: 0.0
    c._verbruik_met_terugval = lambda *a, **k: 0.0
    c._plan_netregels = lambda *a, **k: {"gespaard": set(), "blok": blok}
    c._plan_verkoopruimte = lambda *a, **k: None
    gezien = {"blok": [], "dip": []}

    def laadt(netregels, einde, *a):
        gezien["blok"].append(einde - timedelta(minutes=15))
        return 0.0

    def dip(netregels, start, *a):
        gezien["dip"].append(start)
        return 0.0

    c._plan_laadt = laadt
    c._plan_dip_laadt = dip
    c._bouw_kwartierplan(nu)
    return gezien


def test_het_lopende_blok_volgt_de_laadregel_van_het_blok(make_coordinator, hass):
    nu = DAG.replace(hour=14, minute=36)
    blok = (DAG.replace(hour=14, minute=15), DAG.replace(hour=14, minute=45))
    gezien = _plan(make_coordinator, nu, blok)
    assert DAG.replace(hour=14, minute=30) in gezien["blok"]
    assert DAG.replace(hour=14, minute=30) not in gezien["dip"]
    # Na het blok weer de gewone regel.
    assert DAG.replace(hour=14, minute=45) in gezien["dip"]


def test_zonder_lopend_blok_verandert_er_niets(make_coordinator, hass):
    nu = DAG.replace(hour=14, minute=36)
    gezien = _plan(make_coordinator, nu, (None, None))
    assert DAG.replace(hour=14, minute=30) in gezien["dip"]


def test_de_dagdrempel_blijft_gelden():
    from custom_components.energy_management_system.coordinator import EnergyManagementSystemCoordinator as C

    t = DAG.replace(hour=3)
    assert C._plan_in_laadblok(0.20, t, {"blok": (None, None)}, lambda m: 0.25) is True
    assert C._plan_in_laadblok(0.30, t, {"blok": (None, None)}, lambda m: 0.25) is False
    assert C._plan_in_laadblok(0.30, t, {"blok": (t, t + timedelta(minutes=30))}, lambda m: 0.25) is True
