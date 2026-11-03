"""v5.174.0: de onzekerheidsband - ensemble, terugval, dekking, gebruik in een plan."""
import asyncio
import math
from datetime import date, datetime, timedelta, timezone

from custom_components.energy_management_system import prijsband as B
from custom_components.energy_management_system import prijsmodel as M
from custom_components.energy_management_system import prijsverwachting as P


def _ensemble_punt(tijden, basis, spreiding, leden=50):
    uurlijks = {"time": tijden, "wind_speed_100m": [basis] * len(tijden),
                "shortwave_radiation": [0.0] * len(tijden)}
    for m in range(1, leden + 1):
        afw = spreiding * ((m - 1) / (leden - 1) * 2 - 1)   # gelijk verdeeld -s..+s
        uurlijks[f"wind_speed_100m_member{m:02d}"] = [basis + afw] * len(tijden)
        uurlijks[f"shortwave_radiation_member{m:02d}"] = [0.0] * len(tijden)
    return {"hourly": uurlijks}


def test_ensemble_url_klein_en_juiste_namen():
    url = B.ensemble_url()
    assert "models=ecmwf_ifs025" in url and "forecast_days=8" in url
    assert "wind_speed_100m,shortwave_radiation" in url and "temperature" not in url
    aantal = sum(len(p) for p in B.ENSEMBLE_PUNTEN.values())
    assert url.split("latitude=")[1].split("&")[0].count(",") == aantal - 1


def test_ensemble_uit_open_meteo_leden_per_groep():
    tijden = ["2026-11-04T12:00", "2026-11-04T13:00"]
    antwoord = [_ensemble_punt(tijden, 20, 10), _ensemble_punt(tijden, 30, 10),
                _ensemble_punt(tijden, 40, 0), _ensemble_punt(tijden, 40, 0),
                _ensemble_punt(tijden, 50, 20)]
    ens = B.ensemble_uit_open_meteo(antwoord)
    g = ens["2026-11-04T12"]
    assert len(g["nl"]["wind"]) == 51   # controle + 50 leden
    assert g["nl"]["wind"][0] == 25.0 and min(g["nl"]["wind"]) == 15.0 and max(g["nl"]["wind"]) == 35.0
    assert set(g["buur"]["wind"]) == {40.0} and len(g["ver"]["zon"]) == 51


def test_leden_weer_verschuift_het_deterministische_weer():
    w = {"wind": 20.0, "zon": 100.0, "temp": 10.0, "wind_buur": 30.0, "zon_buur": 50.0}
    ens = {"nl": {"wind": [10.0, 20.0, 30.0], "zon": [100.0, 100.0, 100.0]},
           "buur": {"wind": [5.0, 5.0, 5.0], "zon": [0.0, 0.0, 0.0]}}
    leden = B.leden_weer(w, ens)
    assert [lid["wind"] for lid in leden] == [10.0, 20.0, 30.0]
    assert all(lid["wind_buur"] == 30.0 for lid in leden)
    assert "wind_ver" not in leden[0]      # niet in het weer: niet verzinnen
    assert B.leden_weer(w, None) == [] and B.leden_weer(w, {"nl": {"wind": [1.0], "zon": [1.0]}}) == []


def test_band_uit_de_ledenkwantielen():
    # een model met alleen een windterm: prijs = 0,30 - 0,01 per 10 km/u
    coefs = [0.30, -0.01] + [0.0] * 8 + [0.0] * 23
    prijzen = {P.uur_sleutel(datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(hours=h)): 0.3
               for h in range(24 * 10)}
    ctx = M.Context(prijzen)
    sleutel = "2026-10-11T12"
    w = {"wind": 20.0, "zon": 0.0, "temp": 10.0}
    ens = {"nl": {"wind": [20.0 + x for x in range(-10, 11)], "zon": [0.0] * 21}}
    lo, hi = B.ensemble_afwijking(coefs, M.OPZETTEN["basis"], ctx, sleutel, 1, w, ens)
    # wind P10/P90 = gemiddelde -/+ 8 km/u -> prijs +/- 0,008
    assert abs(lo + 0.008) < 1e-9 and abs(hi - 0.008) < 1e-9
    onder, boven = B.onschaalde_band({"res_p10": -0.006, "res_p90": 0.006}, (lo, hi))
    assert abs(onder + 0.01) < 1e-9 and abs(boven - 0.01) < 1e-9   # wortel uit 6² + 8²


def test_terugval_alleen_restfout_en_geen_band_zonder_terugtoets():
    assert B.onschaalde_band(None, (-0.01, 0.01)) is None
    assert B.onschaalde_band({"res_p10": -0.02, "res_p90": 0.03}, None) == (-0.02, 0.03)
    # een scheve restfout zonder ondergrens: de band begint bij de verwachting
    assert B.onschaalde_band({"res_p10": 0.01, "res_p90": 0.03}, None) == (-0.0, 0.03)


def _archief_met_band(dagen, fout, lo=-0.02, hi=0.02, s=1.0, vandaag=date(2026, 11, 3)):
    archief, prijzen = {}, {}
    for terug in range(1, dagen + 1):
        dag = vandaag - timedelta(days=terug)
        uren = P.uren_van_dag(dag)
        archief[dag.isoformat()] = {"d1": {"model": {"datum": dag.isoformat(), "uren": [[x, 0.30] for x in uren]},
                                           "band": {"s": s, "u": [[x, lo, hi] for x in uren]}, "k": 1}}
        for i, x in enumerate(uren):
            prijzen[x] = 0.30 + (fout if i % 2 else -fout)
    return archief, prijzen


def test_kalibreer_leert_de_schaal_uit_de_dekking():
    archief, prijzen = _archief_met_band(10, fout=0.03)   # alles 1,5 x buiten de band
    k = B.kalibreer(archief, prijzen, date(2026, 11, 3))
    assert k["dekking"]["d1"]["dekking_procent"] == 0.0
    assert k["schaal_ongedempt"] == 1.5 and 1.0 < k["schaal"] < 1.5      # gedempt
    archief, prijzen = _archief_met_band(10, fout=0.01)
    k = B.kalibreer(archief, prijzen, date(2026, 11, 3))
    assert k["dekking"]["d1"]["dekking_procent"] == 100.0 and k["schaal"] < 1.0
    assert B.kalibreer({}, {}, date(2026, 11, 3))["schaal"] == 1.0


def test_live_beoordeling_telt_de_dekking_en_de_extra_naieven():
    archief, prijzen = _archief_met_band(5, fout=0.01, s=2.0)
    vandaag = date(2026, 11, 3)
    for terug in range(1, 15):     # prijzen voor de naieven
        for x in P.uren_van_dag(vandaag - timedelta(days=terug)):
            prijzen.setdefault(x, 0.31)
    # d1 zonder bewaarde naieve verwachting: die volgt uit de prijzen van d-k
    live = P.live_beoordeling(archief, prijzen)
    assert live["d1"]["dagen"] == 5 and live["d1"]["dekking_band_procent"] == 100.0
    assert "afwijking_zoals_vorige_week_ct" in live["d1"] and "afwijking_zoals_mix_ct" in live["d1"]


def test_archiveer_week_vooruit_zonder_naief_met_band_en_k():
    archief = {}
    dag = date(2026, 11, 8)
    model = P.samenvatting(dag, [{"uur": "12:00", "sleutel": "2026-11-08T11", "prijs_eur": 0.3}])
    band = {"schaal": 1.2, "onschaald": [["2026-11-08T11", -0.02, 0.03]], "uren": []}
    P.archiveer(archief, dag.isoformat(), 5, model, None, band=band, k=6)
    assert archief[dag.isoformat()]["d5"]["band"] == {"s": 1.2, "u": [["2026-11-08T11", -0.02, 0.03]]}
    assert archief[dag.isoformat()]["d5"]["k"] == 6 and "naief" not in archief[dag.isoformat()]["d5"]
    P.archiveer(archief, "2026-11-04", 1, model, None)     # morgen zonder naief: niet (zoals v5.100)
    assert "2026-11-04" not in archief


def test_risicowaarden_en_spread_binnen_de_onzekerheid():
    uur = {"prijs_eur": 0.40, "p25": 0.37, "p75": 0.44}
    r = B.risicowaarden(uur)
    assert r["ontladen_eur"] < 0.40 < r["laden_eur"]
    assert abs((0.40 - r["ontladen_eur"]) - 0.03 * 0.5244 / 0.6745) < 1e-4
    assert B.risicowaarden({"prijs_eur": 0.4})["laden_eur"] == 0.4
    goedkoop = {"prijs_eur": 0.30, "p25": 0.27, "p75": 0.33}
    duur = {"prijs_eur": 0.38, "p25": 0.33, "p75": 0.43}
    # met de verwachting zelf 0,38*0,85 - 0,30 = +0,023; voorzichtig niet meer
    assert 0.38 * 0.85 - 0.30 > 0 and B.spread_zeker(duur, goedkoop) < 0


def test_verschuif_legt_de_band_om_de_bijgestelde_verwachting():
    band = {"bron": "restfout", "schaal": 2.0, "onschaald": [["2026-11-04T11", -0.01, 0.02]], "uren": []}
    nieuw = B.verschuif(band, [{"uur": "12:00", "sleutel": "2026-11-04T11", "prijs_eur": 0.35}])
    assert nieuw["uren"][0]["p10"] == 0.33 and nieuw["uren"][0]["p90"] == 0.39


def test_coordinator_band_voor_plan_en_ensemble_zonder_netwerk(make_coordinator, hass):
    c = make_coordinator({})

    class Kapot:
        def get(self, url):
            assert "ensemble-api.open-meteo.com" in url
            raise ConnectionError("geen netwerk in de test")

    async def executor(fn, *args):
        return fn(*args)

    c.hass.async_add_executor_job = executor
    assert asyncio.run(c._prijs_ensemble(Kapot())) is None
    assert "ConnectionError" in c._prijs_ensemble_fout
    dagen = {"2026-11-05": {"model": {"uren": [{"uur": "18:00", "sleutel": "2026-11-05T17", "prijs_eur": 0.40}]},
                            "band": {"uren": [{"uur": "18:00", "sleutel": "2026-11-05T17", "p10": 0.34,
                                               "p25": 0.37, "p75": 0.44, "p90": 0.48}]}}}
    plan = c._prijs_band_voor_plan(dagen)
    assert plan[0][0] == "2026-11-05T17" and plan[0][1] < 40.0 < plan[0][2]


def test_bandschaal_eerst_uit_de_terugtoets_dan_live():
    from custom_components.energy_management_system.coordinator import _prijs_bandschaal

    assert _prijs_bandschaal({"dagen": 2, "uren": 48, "schaal": 3.0}, {"schaal_terugtoets": 1.4}) == 1.4
    assert _prijs_bandschaal({"dagen": 8, "uren": 24 * 8, "schaal": 1.8}, {"schaal_terugtoets": 1.4}) == 1.8
    assert _prijs_bandschaal(None, None) == 1.0
    assert math.isclose(B.Z50 / B.Z80, 0.5263, rel_tol=1e-3)


def test_prijsverwachting_met_ensemble_door_de_coordinator(make_coordinator, hass, monkeypatch):
    """De hele keten zonder netwerk: weer, ensemble met leden, terugtoets, keuze, band."""
    import sys
    import types

    c = make_coordinator({})
    begin = datetime(2026, 9, 1, tzinfo=timezone.utc)
    tijden, wind = [], []
    for h in range(55 * 24):
        t = begin + timedelta(hours=h)
        lok = t.astimezone(P.TZ)
        w = 15 + 10 * math.sin(h / 30)
        if t < datetime(2026, 10, 20, tzinfo=timezone.utc):
            c.prijsgeschiedenis[P.uur_sleutel(t)] = 0.30 + (0.1 if 17 <= lok.hour < 21 else 0.0) - 0.002 * w
        tijden.append(t.strftime("%Y-%m-%dT%H:00"))
        wind.append(w)
    weer = [{"hourly": {"time": tijden, "wind_speed_100m": wind, "shortwave_radiation": [0.0] * len(tijden),
                        "temperature_2m": [10.0] * len(tijden)}}]
    toekomst = [x for x in tijden if x >= "2026-10-19"]
    ens = [_ensemble_punt(toekomst, 20, 8, leden=10) for _ in range(5)]
    gevraagd = []

    class Antwoord:
        def __init__(self, data):
            self.data = data

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def raise_for_status(self):
            pass

        async def json(self):
            return self.data

    class Sessie:
        def get(self, url):
            gevraagd.append(url)
            return Antwoord(ens if "ensemble-api" in url else weer)

    ac = types.ModuleType("homeassistant.helpers.aiohttp_client")
    ac.async_get_clientsession = lambda hass: Sessie()
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.aiohttp_client", ac)

    async def executor(fn, *args):
        return fn(*args)

    c.hass.async_add_executor_job = executor
    c._prijsgeschiedenis_gezaaid = True
    c._get_forecast_entries = lambda: []
    asyncio.run(c._async_prijsverwachting(datetime(2026, 10, 19, 8, 0, tzinfo=timezone.utc)))
    pv = c.get_prijsverwachting()
    assert pv["fout"] is None, pv["fout"]
    assert len(gevraagd) == 2 and any("ecmwf_ifs025" in u for u in gevraagd)
    assert pv["opzet"] in M.OPZETTEN and pv["opzet_scores_ct"]
    assert pv["band_ensemble_uren"] > 0 and pv["band_ensemble_fout"] is None
    dag = sorted(pv["dagen"])[0]
    assert pv["dagen"][dag]["band"] and pv["dagen"][dag]["band_bron"] == "ensemble"
    assert pv["per_vooruit"][0]["vooruit"] == 1 and pv["band_voor_plan"]
    # d1 tot en met d7 in het archief, met band
    plekken = {s for d in c.prijsverwachting_archief.values() for s in d}
    assert {"d1", "d2", "d3"} <= plekken
    assert any("band" in p for d in c.prijsverwachting_archief.values() for p in d.values())
