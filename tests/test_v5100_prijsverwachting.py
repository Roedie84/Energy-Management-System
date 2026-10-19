"""v5.100: prijsverwachting uit wind, zon, uur en weekdag."""
import math
import random
from datetime import date, datetime, timedelta, timezone

from custom_components.energy_management_system import prijsverwachting as P


def _synthetisch(dagen=60, ruis=0.01, zaad=1):
    """Prijs = niveau - wind - zon + avondpiek, met wat ruis."""
    rnd = random.Random(zaad)
    begin = datetime(2026, 7, 1, tzinfo=timezone.utc)
    weer, prijzen = {}, {}
    for h in range(dagen * 24):
        t = begin + timedelta(hours=h)
        s = P.uur_sleutel(t)
        lok = t.astimezone(P.TZ)
        wind = 15 + 15 * math.sin(h / 37.0) + rnd.uniform(-5, 5)
        zon = max(0.0, 600 * math.sin(math.pi * (lok.hour - 6) / 14)) if 6 <= lok.hour <= 20 else 0.0
        weer[s] = {"wind": wind, "zon": zon, "temp": 12.0}
        avond = 0.08 if 17 <= lok.hour < 21 else 0.0
        prijzen[s] = 0.35 - 0.003 * wind - 0.0001 * zon + avond + rnd.gauss(0, ruis)
    return prijzen, weer


def test_fit_vindt_verband_en_verslaat_zoals_gisteren():
    prijzen, weer = _synthetisch()
    uit = P.backtest(prijzen, weer, dagen=10, vooruit=2)
    assert uit["dagen"] >= 9
    assert uit["afwijking_model_ct"] < uit["afwijking_zoals_gisteren_ct"]
    assert uit["winst_procent"] > 30
    assert uit["duurste_uren_geraakt_van_4"] >= 3


def test_maak_verwachting_geeft_de_onbekende_dagen():
    prijzen, weer = _synthetisch(dagen=40)
    laatste = max(P._lokaal(s).date() for s in prijzen)
    # weer ook voor de dagen erna
    for h in range(1, 24 * 4):
        t = datetime.combine(laatste, datetime.min.time(), P.TZ) + timedelta(hours=h)
        weer[P.uur_sleutel(t)] = {"wind": 20.0, "zon": 0.0, "temp": 10.0}
    vandaag = laatste - timedelta(days=1)
    uit = P.maak_verwachting(prijzen, weer, vandaag, laatste - timedelta(days=1))
    assert uit["beschikbaar"]
    assert set(uit["dagen"]) >= {laatste.isoformat(), (laatste + timedelta(days=1)).isoformat()}
    d = uit["dagen"][laatste.isoformat()]
    assert d["vooruit"] == 1 and d["model"]["duurste_uur"][:2] in {"17", "18", "19", "20"}


def test_te_weinig_gegevens_geen_model():
    prijzen, weer = _synthetisch(dagen=10)
    uit = P.maak_verwachting(prijzen, weer, date(2026, 7, 10), date(2026, 7, 10))
    assert uit["beschikbaar"] is False and "minimaal" in uit["reden"]


def test_archief_houdt_de_eerste_verwachting_en_toetst_live():
    prijzen, weer = _synthetisch(dagen=50)
    dag = max(P._lokaal(s).date() for s in prijzen) - timedelta(days=1)
    bekend = {s: p for s, p in prijzen.items() if P._lokaal(s).date() < dag - timedelta(days=1)}
    rijen, doelen = P.dataset(bekend, weer)
    coefs = P.fit(rijen, doelen)
    archief = {}
    P.archiveer(archief, dag.isoformat(), 2, P.verwacht_dag(coefs, weer, bekend, dag), P.naief(bekend, dag))
    eerste = archief[dag.isoformat()]["d2"]
    P.archiveer(archief, dag.isoformat(), 2, P.naief(bekend, dag), P.naief(bekend, dag))
    assert archief[dag.isoformat()]["d2"] is eerste
    oordeel = P.live_beoordeling(archief, prijzen)
    assert oordeel["d2"]["dagen"] == 1 and oordeel["d2"]["rijp"] is False
    assert oordeel["d2"]["laatste"]["datum"] == dag.isoformat()


def test_weer_uit_open_meteo_middelt_over_punten():
    antwoord = [
        {"hourly": {"time": ["2026-10-19T00:00"], "wind_speed_100m": [10], "shortwave_radiation": [0],
                    "temperature_2m": [8]}},
        {"hourly": {"time": ["2026-10-19T00:00"], "wind_speed_100m": [30], "shortwave_radiation": [0],
                    "temperature_2m": [10]}},
    ]
    w = P.weer_uit_open_meteo(antwoord)
    assert w == {"2026-10-19T00": {"wind": 20.0, "zon": 0.0, "temp": 9.0}}


def test_uren_van_dag_zomertijd():
    assert len(P.uren_van_dag(date(2026, 10, 25))) == 25
    assert len(P.uren_van_dag(date(2026, 3, 29))) == 23


def test_uurprijzen_uit_kwartieren_alleen_volle_uren():
    b = datetime(2026, 10, 19, 10, 0, tzinfo=timezone.utc)
    kw = [(b + timedelta(minutes=15 * i), 0.30 + 0.01 * i) for i in range(6)]
    uit = P.uurprijzen_uit_kwartieren(kw)
    assert list(uit) == ["2026-10-19T10"] and abs(uit["2026-10-19T10"] - 0.315) < 1e-9


def test_kaart():
    assert P.kaart({}, None, None)["kaart_secundair"] == "nog geen verwachting"
    d = {"2026-10-21": {"gemiddeld_eur": 0.3512, "duurste_uur": "19:00", "duurste_eur": 0.45,
                        "goedkoopste_uur": "13:00", "goedkoopste_eur": 0.25}}
    k = P.kaart(d, {"winst_procent": 38.7}, {"d2": {"dagen": 0}})
    assert k["kaart_primair"] == "35,1 ct verwacht"
    assert "duurst 19:00 (45 ct)" in k["kaart_secundair"] and "terugtoets 38.7%" in k["kaart_secundair"]
    k = P.kaart(d, {"winst_procent": 38.7}, {"d2": {"dagen": 15, "winst_procent": 30.0}})
    assert "live 30.0% beter" in k["kaart_secundair"]
