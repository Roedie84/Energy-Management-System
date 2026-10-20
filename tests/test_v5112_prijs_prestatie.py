"""v5.112.0: hoe goed is de prijsverwachting, en bijstellen op de eigen fout.

Gevraagd 20-10: "Ja graag en ik wil de performance zien hoe goed de
voorspellingen zijn en ook terug rekenen".
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from custom_components.energy_management_system import prijsverwachting as P

JS = (Path(__file__).resolve().parent.parent / "custom_components" / "energy_management_system"
      / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def _dag(datum: date, prijs) -> dict:
    uren = [{"uur": P._lokaal(s).strftime("%H:%M"), "sleutel": s,
             "prijs_eur": prijs(P._lokaal(s).hour) if callable(prijs) else prijs}
            for s in P.uren_van_dag(datum)]
    return P.samenvatting(datum, uren)


def _echt(datum: date, prijs) -> dict:
    return {s: (prijs(P._lokaal(s).hour) if callable(prijs) else prijs) for s in P.uren_van_dag(datum)}


def test_bijstelling_leert_een_vaste_fout_per_blok():
    vandaag = date(2026, 10, 20)
    archief, prijzen = {}, {}
    for d in range(1, 8):
        datum = vandaag - timedelta(days=d)
        # verwachting 0,30; echt 's avonds (18-21) 4 ct hoger, verder gelijk
        P.archiveer(archief, datum.isoformat(), 1, _dag(datum, 0.30), _dag(datum, 0.30))
        prijzen.update(_echt(datum, lambda h: 0.34 if 18 <= h < 21 else 0.30))
    b = P.bijstelling(archief, prijzen, 1, vandaag)
    assert b["dagen"] == 7
    avond = b["blokken_ct"][6]
    assert abs(avond - 4 * 7 / 10) < 0.01          # gedempt: 7 / (7 + 3)
    assert b["blokken_ct"][0] == 0.0
    model = _dag(vandaag + timedelta(days=1), 0.30)
    na = P.pas_bijstelling_toe(model, b)
    assert next(u for u in na["uren"] if u["uur"] == "19:00")["prijs_eur"] == round(0.30 + avond / 100, 4)
    assert next(u for u in na["uren"] if u["uur"] == "03:00")["prijs_eur"] == 0.30


def test_bijstelling_begrensd_en_leeg_zonder_archief():
    vandaag = date(2026, 10, 20)
    archief, prijzen = {}, {}
    for d in range(1, 8):
        datum = vandaag - timedelta(days=d)
        P.archiveer(archief, datum.isoformat(), 2, _dag(datum, 0.30), _dag(datum, 0.30))
        prijzen.update(_echt(datum, 0.60))
    assert max(P.bijstelling(archief, prijzen, 2, vandaag)["blokken_ct"]) == 5.0
    assert P.bijstelling({}, {}, 1, vandaag) == {"dagen": 0, "blokken_ct": [0.0] * 8}
    m = _dag(vandaag, 0.3)
    assert P.pas_bijstelling_toe(m, {"dagen": 0}) is m


def test_bijstelling_meet_op_de_ruwe_verwachting():
    vandaag = date(2026, 10, 20)
    archief, prijzen = {}, {}
    datum = vandaag - timedelta(days=1)
    # bijgesteld model zat goed, ruw zat 2 ct te laag: de bijstelling meet ruw
    P.archiveer(archief, datum.isoformat(), 1, _dag(datum, 0.32), _dag(datum, 0.30), ruw=_dag(datum, 0.30))
    prijzen.update(_echt(datum, 0.32))
    b = P.bijstelling(archief, prijzen, 1, vandaag)
    assert b["dagen"] == 1 and abs(b["blokken_ct"][3] - 2 * 1 / 4) < 0.01


def test_stel_bij_bewaart_ruw_en_live_vergelijkt_met_en_zonder():
    vandaag = date(2026, 10, 20)
    archief, prijzen = {}, {}
    for d in range(1, 8):
        datum = vandaag - timedelta(days=d)
        P.archiveer(archief, datum.isoformat(), 1, _dag(datum, 0.30), _dag(datum, 0.29))
        prijzen.update(_echt(datum, 0.33))
    dagen = {"2026-10-21": {"model": _dag(date(2026, 10, 21), 0.30), "vooruit": 1},
             "2026-10-25": {"model": _dag(date(2026, 10, 25), 0.30), "vooruit": 5}}
    bij = P.stel_bij(dagen, archief, prijzen, vandaag)
    assert bij["d1"]["dagen"] == 7
    for d in dagen.values():
        assert d["ruw"]["gemiddeld_eur"] == 0.30 and d["model"]["gemiddeld_eur"] > 0.30
    # live: een dag met ruw erbij geeft met/zonder bijstelling
    datum = date(2026, 10, 21)
    P.archiveer(archief, datum.isoformat(), 1, dagen["2026-10-21"]["model"], _dag(datum, 0.29),
                dagen["2026-10-21"]["ruw"])
    prijzen.update(_echt(datum, 0.33))
    live = P.live_beoordeling(archief, prijzen)["d1"]
    assert live["bijgesteld_dagen"] == 1 and live["met_bijstelling_ct"] < live["zonder_bijstelling_ct"]
    rij = live["per_dag"][-1]
    assert rij["datum"] == "2026-10-21" and "zonder_bijstelling_ct" in rij and rij["echt_ct"] == 33.0


def test_terugtoets_geeft_per_dag():
    import math
    import random

    rnd = random.Random(2)
    begin = datetime(2026, 7, 1, tzinfo=timezone.utc)
    weer, prijzen = {}, {}
    for h in range(40 * 24):
        t = begin + timedelta(hours=h)
        s = P.uur_sleutel(t)
        wind = 15 + 15 * math.sin(h / 37.0)
        weer[s] = {"wind": wind, "zon": 0.0, "temp": 12.0}
        prijzen[s] = 0.35 - 0.003 * wind + rnd.gauss(0, 0.005)
    uit = P.backtest(prijzen, weer, dagen=5, vooruit=2)
    assert len(uit["per_dag"]) == uit["dagen"] >= 4
    assert {"datum", "afwijking_ct", "zoals_gisteren_ct", "duurste_geraakt"} <= set(uit["per_dag"][0])


def test_cockpit_toont_de_kwaliteit():
    assert "this._prijsKwaliteit() +" in JS and "_prijsKwaliteit() {" in JS
    begin = JS.index("_prijsKwaliteit() {")
    stuk = JS[begin:JS.index("\n  }\n", begin)]
    assert "nauwkeurigheid_live" in stuk and "backtest_21_dagen" in stuk and "bijstelling" in stuk
    assert all(ord(ch) < 128 for ch in stuk)
