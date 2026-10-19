"""v5.102: dagarchief - per dag één compacte regel die altijd blijft."""
import asyncio
from datetime import date, datetime, timedelta, timezone

from custom_components.energy_management_system import dagarchief as D
from custom_components.energy_management_system import kwartierenergie
from custom_components.energy_management_system.coordinator import _reken_dagarchief, _stat_moment


def _kwartieren(datum=date(2026, 10, 18), n=96, prijs=0.30):
    begin = datetime.combine(datum, datetime.min.time(), tzinfo=D.TZ)
    uit = []
    for i in range(n):
        t = begin + timedelta(minutes=15 * i)
        zon = 0.3 if 40 <= i < 64 else 0.0
        accu_uit = 0.1 if i >= 72 else 0.0
        accu_in = 0.1 if 44 <= i < 60 else 0.0
        huis = 0.15
        net = huis - zon - accu_uit + accu_in
        uit.append({
            "kwartier": t.isoformat(), "grid_import_kwh": max(net, 0.0), "grid_export_kwh": max(-net, 0.0),
            "pv_kwh": zon, "battery_out_kwh": accu_uit, "battery_in_kwh": accu_in, "house_kwh": huis,
            "prijs_eur": prijs, "quality": "measured",
        })
    return uit


def test_dag_uit_kwartieren():
    r = D.dag_uit_kwartieren(_kwartieren())
    assert r["b_"] == "m" and r["q"] == 96
    assert r["v"] == 14.4 and r["p"] == 7.2 and r["l"] == 1.6 and r["o"] == 2.4
    # nacht 22-07: 9 uur van 0,6 kWh
    assert r["n"] == 5.4
    assert r["pg"] == 30.0 and r["kz"] == round((14.4 - 7.2) * 0.30, 2)
    assert r["b"] == round(r["kz"] - r["k"], 2) and r["b"] > 0


def test_te_weinig_kwartieren_geen_dag():
    assert D.dag_uit_kwartieren(_kwartieren(n=60)) is None


def test_zonder_prijs_geen_kosten():
    r = D.dag_uit_kwartieren(_kwartieren(prijs=None))
    assert "k" not in r and "pg" not in r and r["v"] == 14.4


def test_statistiekdag_overschrijft_geen_meetlogdag_en_aanvulling_blijft():
    a = D.leeg()
    D.zet(a, "2026-10-18", D.dag_uit_kwartieren(_kwartieren()))
    D.vul_aan(a, "2026-10-18", gm=0.31, pv=None)
    D.zet(a, "2026-10-18", {"v": 99.0, "b_": "s"})
    assert a["dagen"]["2026-10-18"]["v"] == 14.4
    D.zet(a, "2026-10-18", {**D.dag_uit_kwartieren(_kwartieren()), "v": 15.0})
    assert a["dagen"]["2026-10-18"]["v"] == 15.0 and a["dagen"]["2026-10-18"]["gm"] == 0.31


def test_dagen_uit_statistiek():
    begin = datetime(2025, 10, 17, 22, 0, tzinfo=timezone.utc)   # 18-10 00:00 lokaal
    imp, exp, pv, prijs = {}, {}, {}, {}
    for h in range(24):
        t = begin + timedelta(hours=h)
        imp[t], exp[t], pv[t], prijs[t] = 0.5, 0.1, 0.2, 0.25
    dagen = D.dagen_uit_statistiek({"grid_import": imp, "grid_export": exp, "pv": pv}, prijs)
    r = dagen["2025-10-18"]
    assert r["b_"] == "s" and r["v"] == 14.4 and r["l"] == 0 and r["pg"] == 25.0
    # een prijs op een ander niveau telt niet mee
    dagen = D.dagen_uit_statistiek({"grid_import": imp, "grid_export": exp, "pv": pv},
                                   {t: 25.0 for t in prijs})
    assert "pg" not in dagen["2025-10-18"]


def test_vergelijking_met_vorig_jaar_en_kaart():
    a = D.leeg()
    vandaag = date(2026, 10, 19)
    for i in range(1, 31):
        nu = vandaag - timedelta(days=i)
        toen = nu - timedelta(days=D.JAAR_DAGEN)
        a["dagen"][nu.isoformat()] = {"v": 9.0, "p": 4.0, "i": 5.0, "e": 0.5, "n": 3.0, "b": 0.6, "t": 9.0, "gd": 9.0}
        a["dagen"][toen.isoformat()] = {"v": 10.0, "p": 5.0, "i": 6.0, "e": 1.0, "n": 3.0, "t": 11.0, "gd": 7.0}
    v = D.vergelijking(a, vandaag)
    assert v["verschil_procent"]["verbruik"] == -10.0 and v["graaddagen_verschil"] == 2.0
    k = D.kaart(a, v)
    assert k["kaart_primair"] == "Verbruik -10,0% t.o.v. vorig jaar"
    assert "vorig jaar 10,0 kWh/dag" in k["kaart_secundair"] and "2,0 graaddag per dag kouder" in k["kaart_secundair"]
    assert "accu € 0,60/dag" in k["kaart_secundair"]


def test_kaart_zonder_vorig_jaar():
    a = D.leeg()
    a["dagen"]["2026-10-18"] = {"v": 9.0, "p": 4.0}
    k = D.kaart(a, D.vergelijking(a, date(2026, 10, 19)))
    assert k["kaart_primair"] == "1 dagen bewaard" and "vorig jaar nog niet" in k["kaart_secundair"]
    assert D.kaart(D.leeg(), {})["kaart_secundair"] == "nog geen volledige dag"


def test_weer_en_maanden():
    a = D.leeg()
    a["dagen"]["2026-10-18"] = {"v": 9.0, "p": 4.0, "k": 1.0}
    a["dagen"]["2026-10-17"] = {"v": 8.0, "p": 3.0}
    weer = {f"2026-10-17T{h:02d}" if h < 22 else f"2026-10-18T{h - 22:02d}": {"temp": 10.0} for h in range(46)}
    weer.update({f"2026-10-18T{h:02d}": {"temp": 12.0} for h in range(22)})
    assert D.vul_weer(a, weer) >= 1
    assert a["dagen"]["2026-10-18"]["gd"] == round(18 - a["dagen"]["2026-10-18"]["t"], 1)
    m = D.per_maand(a)
    assert m["2026-10"]["dagen"] == 2 and m["2026-10"]["verbruik_kwh"] == 17.0 and m["2026-10"]["kosten_eur"] == 1.0


def test_snoei_vangnet():
    a = D.leeg()
    begin = date(2010, 1, 1)
    for i in range(D.MAX_DAGEN + 5):
        a["dagen"][(begin + timedelta(days=i)).isoformat()] = {"v": 1.0}
    D.zet(a, "2030-01-01", {"v": 1.0, "b_": "m"})
    assert len(a["dagen"]) == D.MAX_DAGEN and "2010-01-01" not in a["dagen"]


def test_reken_dagarchief_uit_compacte_meetlogregels():
    compact = []
    for r in _kwartieren():
        compact.append(kwartierenergie.compact({
            **r, "kwaliteit_per_teller": {t: "measured" for t in kwartierenergie.TELLERS},
            "leeftijd_s": {t: 5 for t in kwartierenergie.TELLERS}, "coverage_percent": 100.0,
        }))
    uit = _reken_dagarchief(D, {"2026-10-18": compact, "2026-10-17": compact[:10]})
    assert list(uit) == ["2026-10-18"] and uit["2026-10-18"]["v"] == 14.4


def test_stat_moment():
    t = datetime(2025, 1, 1, 12, tzinfo=timezone.utc)
    assert _stat_moment({"start": t.timestamp()}) == t
    assert _stat_moment({"start": t}) == t
    assert _stat_moment({"start": t.isoformat()}) == t


def test_archiveer_zelfanalyse_en_getter(make_coordinator, hass):
    c = make_coordinator({})
    invoer = {"verwachting": {"00:00": {"zon_kwh": 6.234, "verbruik_kwh": 11.0}, "12:00": {"zon_kwh": 1.0, "verbruik_kwh": 4.0}}}
    oordeel = {"te_becijferen": True, "gemist_eur": 0.31, "niet_de_beste": [
        {"spijt_eur": 0.25, "oorzaak": "regel", "handmatig": False},
        {"spijt_eur": 0.5, "oorzaak": "regel", "handmatig": True},
        {"spijt_eur": 0.1, "oorzaak": "voorspelling", "handmatig": False}]}
    c._archiveer_zelfanalyse("2026-10-18", invoer, oordeel, {"te_becijferen": False})
    dag = c.dagarchief["dagen"]["2026-10-18"]
    assert dag == {"pv": 6.23, "vv": 11.0, "gm": 0.31, "gr": 0.25}
    uit = c.get_dagarchief()
    assert uit["dagen_bewaard"] == 0 and "toelichting" in uit


def test_dagarchief_vult_uit_de_meetlog(make_coordinator, hass):
    c = make_coordinator({})

    class Log:
        _dagen = {("kwartier", "2026-10-18"): {}, ("kwartier", "2026-10-19"): {}, ("evaluatie", "2026-10-18"): {}}

        def regels_alleen_lezen(self, soort, dag):
            return [kwartierenergie.compact({
                **r, "kwaliteit_per_teller": {t: "measured" for t in kwartierenergie.TELLERS},
                "leeftijd_s": {t: 5 for t in kwartierenergie.TELLERS}, "coverage_percent": 100.0,
            }) for r in _kwartieren(dag)]

    class Laag:
        log = Log()
        _laden_klaar = True

    c._meetlaag = Laag()
    c.reserve_daily_records = [{"date": "2026-10-18", "tekortnacht_kwh": 0.0, "excess": True, "laagste_soc_ochtend": 22}]
    c.dagarchief = {"dagen": {}, "gezaaid": True}

    async def executor(fn, *args):
        return fn(*args)

    c.hass.async_add_executor_job = executor
    asyncio.run(c._async_dagarchief("2026-10-19"))
    dagen = c.dagarchief["dagen"]
    assert list(dagen) == ["2026-10-18"]   # vandaag nog niet
    assert dagen["2026-10-18"]["v"] == 14.4 and dagen["2026-10-18"]["ov"] is True and dagen["2026-10-18"]["so"] == 22
    assert c.get_dagarchief()["uit_meetlog"] == 1
