"""v5.239.0: prijsmodel beter (Ruud 18-11: "Kunnen we het prijsmodel beter
maken?" - "Alle 3").

1. het prijsniveau beweegt sneller mee (`kort`);
2. netladen dat alleen op de prijsverwachting leunt moet de gebruikelijke
   fout ervan goedmaken (`netladen_op_verwachting`);
3. verwachte windproductie uit een vermogenscurve (`kracht`);
plus de toets van de aangenomen eindprijs (alleen meten).
"""
import math
import random
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import eindprijs_toets as E
from custom_components.energy_management_system import prijsmodel as M
from custom_components.energy_management_system import prijsverwachting as P
from custom_components.energy_management_system import waardeplan as W

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 18, 14, 0, tzinfo=TZ)


# --- 1 en 3: de kandidaten ------------------------------------------------

def _reeks(dagen=100, zaad=3, ar=0.9, kracht=True):
    rnd = random.Random(zaad)
    begin = datetime(2026, 7, 1, tzinfo=timezone.utc)
    weer, prijzen = {}, {}
    niveau, dag = 0.30, None
    for h in range(dagen * 24):
        t = begin + timedelta(hours=h)
        s = P.uur_sleutel(t)
        lok = t.astimezone(P.TZ)
        if lok.date() != dag:
            dag = lok.date()
            niveau = 0.30 + ar * (niveau - 0.30) + rnd.gauss(0, 0.02)
        wind = max(0.0, 25 + 22 * math.sin(h / 37.0) + rnd.uniform(-6, 6))
        buur = max(0.0, 25 + 22 * math.sin(h / 37.0 + 0.4) + rnd.uniform(-6, 6))
        zon = max(0.0, 600 * math.sin(math.pi * (lok.hour - 6) / 14)) if 6 <= lok.hour <= 20 else 0.0
        weer[s] = {"wind": wind, "zon": zon, "temp": 12.0, "wind_buur": buur, "zon_buur": zon,
                   "wind_ver": buur, "zon_ver": zon}
        piek = 0.08 if 17 <= lok.hour < 21 else 0.0
        effect = (0.10 * M.windkracht(wind) + 0.08 * M.windkracht(buur)) if kracht else 0.003 * wind
        prijzen[s] = niveau - effect - 0.0001 * zon + piek + rnd.gauss(0, 0.01)
    return prijzen, weer


def test_windkracht_is_een_vermogenscurve():
    assert M.windkracht(0) == 0.0 and M.windkracht(11) == 0.0
    assert 0.0 < M.windkracht(20) < M.windkracht(30) < 1.0
    assert M.windkracht(45) == 1.0 and M.windkracht(70) == 1.0
    assert M.windkracht(95) == 0.0 and M.windkracht(None) == 0.0
    # kubisch: van 20 naar 40 km/u veel meer dan het dubbele
    assert M.windkracht(40) > 6 * M.windkracht(20)


def test_bestaande_opzetten_hebben_dezelfde_kenmerken_als_voorheen():
    prijzen, weer = _reeks(dagen=30)
    ctx = M.Context(prijzen)
    sleutel = sorted(prijzen)[-30]
    oud = M.rij(sleutel, 1, weer[sleutel], ctx, M.OPZETTEN["vertraging_ver_gas"])
    kort = M.rij(sleutel, 1, weer[sleutel], ctx, M.OPZETTEN["vertraging_ver_gas_kort"])
    kracht = M.rij(sleutel, 1, weer[sleutel], ctx, M.OPZETTEN["vertraging_ver_gas_kracht"])
    beide = M.rij(sleutel, 1, weer[sleutel], ctx, M.OPZETTEN["vertraging_ver_gas_kort_kracht"])
    assert len(oud) == 15 + 23
    assert len(kort) == len(oud) + 2 and len(kracht) == len(oud) + 3 and len(beide) == len(oud) + 5
    assert kort[:15] == oud[:15] and kort[-23:] == oud[-23:]


def test_kort_niveau_lekt_niet_uit_de_toekomst():
    prijzen, weer = _reeks(dagen=40)
    ctx = M.Context(prijzen)
    o = M.OPZETTEN["vertraging_ver_gas_kort"]
    dag = max(ctx.dagsom) - timedelta(days=1)
    sleutel = [s for s in P.uren_van_dag(dag) if P._lokaal(s).hour == 18][0]
    r2 = M.rij(sleutel, 2, weer[sleutel], ctx, o)
    vervalst = dict(prijzen)
    for s in P.uren_van_dag(dag) + P.uren_van_dag(dag - timedelta(days=1)):
        vervalst[s] = 9.99
    assert M.rij(sleutel, 2, weer[sleutel], M.Context(vervalst), o) == r2
    bekend = dag - timedelta(days=2)
    assert r2[15] == pytest.approx(ctx.niveau_kort(bekend, 1) * 10)
    assert r2[16] == pytest.approx(ctx.niveau_kort(bekend, 3) * 10)


def test_kort_niveau_valt_terug_op_het_weekniveau():
    prijzen, weer = _reeks(dagen=30)
    dag = max(P._lokaal(s).date() for s in prijzen) - timedelta(days=1)
    gat = {s: p for s, p in prijzen.items()
           if not (dag - timedelta(days=3) <= P._lokaal(s).date() <= dag - timedelta(days=1))}
    ctx = M.Context(gat)
    sleutel = P.uren_van_dag(dag)[12]
    r = M.rij(sleutel, 1, weer[sleutel], ctx, M.OPZETTEN["vertraging_ver_gas_kort"])
    niveau = ctx.niveau_tot(dag - timedelta(days=1))
    assert r[15] == pytest.approx(niveau * 10) and r[16] == pytest.approx(niveau * 10)


def test_uitbreiding_wint_als_hij_aantoonbaar_beter_is():
    prijzen, weer = _reeks(dagen=100, kracht=True)
    keuze = M.kies_opzet(prijzen, weer, None, oorsprongen=14)
    assert set(keuze["scores"]) == set(M.OPZETTEN)
    assert M.OPZETTEN[keuze["opzet"]].get("kracht")
    assert keuze["scores"][keuze["opzet"]] <= keuze["scores"]["vertraging_ver_gas"] * M.UITBREIDING_WINST


def test_uitbreiding_die_niets_toevoegt_wint_niet(monkeypatch):
    prijzen, weer = _reeks(dagen=60, kracht=False)

    def nep(prijzen_, weer_, opzet, oorsprongen=21, gas=None, ctx=None, rijen=None):
        # een uitbreiding die 0,5 % beter scoort: binnen de ruis
        fout = 0.0398 if opzet.get("uitbreiding_van") else 0.0400
        dagen = [{"model": fout, "gisteren": 0.06, "week": 0.07, "mix": 0.065, "residuen": [0.0] * 24,
                  "datum": f"2026-09-{d:02d}"} for d in range(1, 11)]
        return {"per_k": {k: list(dagen) for k in range(1, 8)}}

    monkeypatch.setattr(M, "terugtoets", nep)
    keuze = M.kies_opzet(prijzen, weer, None, oorsprongen=10)
    assert not M.OPZETTEN[keuze["opzet"]].get("uitbreiding_van")


def test_verwachting_en_gevoeligheid_met_de_nieuwe_opzet():
    prijzen, weer = _reeks(dagen=60)
    laatste = max(P._lokaal(s).date() for s in prijzen)
    bekend = laatste - timedelta(days=3)
    tot_bekend = {s: p for s, p in prijzen.items() if P._lokaal(s).date() <= bekend}
    v = P.maak_verwachting(tot_bekend, weer, bekend, bekend, opzet="vertraging_ver_gas_kort_kracht")
    assert v["beschikbaar"] and v["opzet"] == "vertraging_ver_gas_kort_kracht"
    g = v["gevoeligheid"]
    assert "deel_van_laatste_dag_gemiddeld" in g and "windproductie_nl_ct_vol_vermogen" in g
    assert g["windproductie_nl_ct_vol_vermogen"] < 0  # meer wind = goedkoper


# --- 2: netladen op de verwachting ----------------------------------------

def _kw(prijzen, verbruik=0.1, begin=NU):
    t, uit = begin, []
    for p in prijzen:
        uit.append(W.Kwartier(t, verbruik, 0.0, p, p))
        t += timedelta(minutes=15)
    return uit


def _accu(inhoud, **k):
    return W.Accu(inhoud_kwh=inhoud, bruikbaar_kwh=7.8, rendement=0.84, slijtage_eur=0.0422, **k)


def _geladen(res):
    return round(sum(r["kwh"] for r in res.kwartieren if r["actie"] == "laden_net"), 2)


def test_netladen_voor_na_de_horizon_alleen_met_marge():
    """18-11: vol laden voor 24,4 ct (marginaal) omdat de verwachting voor de
    dag erna 34,5 ct gaf: kost 29 ct per kWh inhoud tegen een eindwaarde van
    ~32 ct. Met 4 ct marge blijft dat laden achterwege."""
    kw = _kw([0.244] * 16)
    zonder = W.plan(kw, _accu(5.5, eindprijs_eur=0.345))
    assert _geladen(zonder) > 1.0
    met = W.plan(kw, _accu(5.5, eindprijs_eur=0.345, eindprijs_marge_eur=0.04))
    assert _geladen(met) == 0.0
    assert met.netladen_verwachting_geweigerd == 16 and zonder.netladen_verwachting_geweigerd == 0
    assert not met.resterend.get("netladen_op_verwachting") and not met.rondelimiet


def test_ruim_lonend_netladen_blijft():
    kw = _kw([0.12] * 16)
    met = W.plan(kw, _accu(3.0, eindprijs_eur=0.345, eindprijs_marge_eur=0.04))
    assert _geladen(met) > 1.0 and met.netladen_verwachting_geweigerd == 0


def test_netladen_voor_een_bekende_piek_blijft():
    """Laden voor een piek binnen de gepubliceerde prijzen leunt niet op de
    verwachting; alleen de staart na de laatste ontlading wordt getoetst."""
    kw = _kw([0.20] * 12 + [0.45] * 12 + [0.244] * 8, verbruik=0.25)
    zonder = W.plan(kw, _accu(0.0, eindprijs_eur=0.345))
    met = W.plan(kw, _accu(0.0, eindprijs_eur=0.345, eindprijs_marge_eur=0.04))
    voor_piek = lambda res: round(sum(r["kwh"] for r in res.kwartieren[:12] if r["actie"] == "laden_net"), 2)
    assert voor_piek(met) > 1.0 and voor_piek(met) >= voor_piek(zonder) - 0.3
    staart = lambda res: round(sum(r["kwh"] for r in res.kwartieren[24:] if r["actie"] == "laden_net"), 2)
    assert staart(zonder) > 0.5 and staart(met) == 0.0


def test_bewaren_en_ontladen_veranderen_niet():
    """De marge raakt alleen netladen: een volle accu blijft bewaard voor een
    hogere verwachte prijs, en een bekende piek wordt nog gewoon gepakt."""
    kw = _kw([0.28] * 8 + [0.50] * 4 + [0.40] * 4, verbruik=0.2)
    zonder = W.plan(kw, _accu(7.7, eindprijs_eur=0.345))
    met = W.plan(kw, _accu(7.7, eindprijs_eur=0.345, eindprijs_marge_eur=0.04))
    assert [r["actie"] for r in met.kwartieren] == [r["actie"] for r in zonder.kwartieren]
    assert met.kosten_plan_eur == zonder.kosten_plan_eur


def test_zonder_prijsverwachting_geen_toets():
    kw = _kw([0.244] * 16)
    res = W.plan(kw, _accu(5.5, eindprijs_marge_eur=0.04))  # eindprijs uit het plan zelf
    assert res.netladen_verwachting_geweigerd == 0
    assert W.netladen_op_verwachting(res.kwartieren, kw, _accu(5.5, eindprijs_marge_eur=0.04)) == []


def test_marge_uit_de_gemeten_fout(make_coordinator):
    c = make_coordinator({})
    c.prijsverwachting = {"live": {"d1": {"afwijking_model_ct": 3.9, "dagen": 30}}}
    assert c._waardeplan_eindprijs_marge() == pytest.approx(0.039)
    c.prijsverwachting = {"live": {"d1": {"afwijking_model_ct": 12.0, "dagen": 30}}}
    assert c._waardeplan_eindprijs_marge() == pytest.approx(0.08)
    c.prijsverwachting = {"live": {"d1": {"afwijking_model_ct": 0.5, "dagen": 30}}}
    assert c._waardeplan_eindprijs_marge() == pytest.approx(0.02)
    c.prijsverwachting = {"live": {"d1": {"afwijking_model_ct": 3.9, "dagen": 5}}}
    assert c._waardeplan_eindprijs_marge() == pytest.approx(0.04)
    c.prijsverwachting = {}
    assert c._waardeplan_eindprijs_marge() == pytest.approx(0.04)


# --- de toets van de eindprijs (alleen meten) -------------------------------

def test_p75_gelijk_aan_het_plan():
    assert E.p75([0.2 + 0.02 * i for i in range(12)]) == pytest.approx(0.36)
    assert E.p75([0.1, 0.2, 0.3]) is None


def test_eindprijs_noteren_en_afsluiten():
    van = datetime(2026, 11, 19, 0, 0, tzinfo=TZ)
    tot = van + timedelta(hours=12)
    staat = E.noteer({}, "2026-11-19", van, tot, 0.455)
    staat = E.noteer(staat, "2026-11-19", van, tot, 0.999)  # tweede keer dezelfde dag: blijft
    assert len(staat["open"]) == 1 and staat["open"][0]["verwacht_eur"] == 0.455
    # prijzen nog niet compleet: blijft open
    half = E.uurprijzen((van + timedelta(minutes=15 * i), 0.40) for i in range(24))
    assert E.sluit(staat, half, van)["open"]
    echt = E.uurprijzen((van + timedelta(minutes=15 * i), 0.30 + 0.01 * (i // 4)) for i in range(48))
    klaar = E.sluit(staat, echt, van)
    assert not klaar["open"]
    assert klaar["klaar"] == [{"datum": "2026-11-19", "verwacht_eur": 0.455, "echt_eur": 0.38}]


def test_een_uur_met_te_weinig_kwartieren_telt_niet():
    van = datetime(2026, 11, 19, 0, 0, tzinfo=TZ)
    u = E.uurprijzen((van + timedelta(minutes=15 * i), 0.4) for i in range(7))
    assert len(u) == 1


def test_oude_open_aanname_vervalt():
    van = datetime(2026, 11, 10, 0, 0, tzinfo=TZ)
    staat = E.noteer({}, "2026-11-10", van, van + timedelta(hours=12), 0.4)
    assert E.sluit(staat, {}, van + timedelta(days=5))["open"] == []


def test_overzicht():
    assert E.overzicht({})["dagen"] == 0
    klaar = [{"datum": f"2026-11-{d:02d}", "verwacht_eur": 0.40, "echt_eur": 0.37 if d % 2 else 0.41}
             for d in range(1, 9)]
    o = E.overzicht({"klaar": klaar, "open": []})
    assert o["dagen"] == 8 and o["gemiddeld_verschil_ct"] == 1.0 and o["gemiddelde_fout_ct"] == 2.0
    assert o["te_hoog_dagen"] == 4 and len(o["laatste"]) == 7
    assert "+1.0 ct" in o["duiding"]
    assert "oordeel vanaf" in E.overzicht({"klaar": klaar[:2]})["duiding"]


def test_sturing_legt_de_aanname_vast_en_sluit_af(make_coordinator):
    c = make_coordinator({})
    c.schedule_persisted_state_save = lambda *a, **k: None
    c._is_salderen_active = lambda m: False
    kw = _kw([0.2] * 8)
    eind = kw[-1].begin + timedelta(minutes=15)
    uren = []
    for i in range(12):
        t = (eind + timedelta(hours=i)).astimezone(timezone.utc)
        uren.append({"sleutel": t.strftime("%Y-%m-%dT%H"), "prijs_eur": 0.30 + 0.01 * i})
    c.prijsverwachting = {"dagen": {"x": {"model": {"uren": uren}}}}
    assert c._waardeplan_eindprijs(kw) == pytest.approx(0.38)
    assert len(c.eindprijs_toets["open"]) == 1 and c.eindprijs_toets["open"][0]["verwacht_eur"] == 0.38
    # later: de prijzen van die twaalf uur zijn gepubliceerd en zitten in het plan
    lang = _kw([0.25] * (8 + 48 + 8))
    c.prijsverwachting = {"dagen": {"x": {"model": {"uren": [
        {"sleutel": (lang[-1].begin + timedelta(minutes=15, hours=i)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H"),
         "prijs_eur": 0.3} for i in range(12)]}}}}
    c._waardeplan_eindprijs(lang)
    klaar = c.eindprijs_toets["klaar"]
    assert klaar and klaar[0]["verwacht_eur"] == 0.38 and klaar[0]["echt_eur"] == 0.25
