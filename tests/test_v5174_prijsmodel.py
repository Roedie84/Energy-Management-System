"""v5.174.0: prijsvertraging zonder lek, een model per dag vooruit, de keuze per terugtoets."""
import math
import random
from datetime import date, datetime, timedelta, timezone

from custom_components.energy_management_system import prijsmodel as M
from custom_components.energy_management_system import prijsverwachting as P


def _reeks(dagen=70, zaad=3, ar=0.0):
    """Synthetische uurprijzen: wind, zon, avondpiek en een dagniveau dat
    (met `ar`) op het niveau van de dag ervoor leunt."""
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
            niveau = 0.30 + ar * (niveau - 0.30) + rnd.gauss(0, 0.04)
        wind = 15 + 15 * math.sin(h / 37.0) + rnd.uniform(-5, 5)
        zon = max(0.0, 600 * math.sin(math.pi * (lok.hour - 6) / 14)) if 6 <= lok.hour <= 20 else 0.0
        weer[s] = {"wind": wind, "zon": zon, "temp": 12.0}
        piek = 0.08 if 17 <= lok.hour < 21 else 0.0
        prijzen[s] = niveau - 0.003 * wind - 0.0001 * zon + piek + rnd.gauss(0, 0.01)
    return prijzen, weer


def test_vertraging_gebruikt_alleen_wat_op_d_min_k_bekend_was():
    prijzen, weer = _reeks(dagen=40)
    ctx = M.Context(prijzen)
    o = M.OPZETTEN["vertraging"]
    dag = max(ctx.dagsom) - timedelta(days=1)
    sleutel = [s for s in P.uren_van_dag(dag) if P._lokaal(s).hour == 18][0]
    r2 = M.rij(sleutel, 2, weer[sleutel], ctx, o)
    # de prijzen van d-1 en d zelf veranderen: de rij voor k=2 mag niet meebewegen
    vervalst = dict(prijzen)
    for s in P.uren_van_dag(dag) + P.uren_van_dag(dag - timedelta(days=1)):
        vervalst[s] = 9.99
    assert M.rij(sleutel, 2, weer[sleutel], M.Context(vervalst), o) == r2
    # wel: de prijs van d-2 om 18 uur is de vertraging
    i = 10 + 0  # na de tien basiskenmerken (geen ver, geen gasniveau)
    assert abs(r2[i] - ctx.per_uur[(dag - timedelta(days=2), 18)] * 10) < 1e-12
    assert abs(r2[i + 1] - ctx.per_uur[(dag - timedelta(days=7), 18)] * 10) < 1e-12


def test_ontbrekende_vertraging_valt_terug_op_het_niveau():
    prijzen, weer = _reeks(dagen=30)
    dag = max(P._lokaal(s).date() for s in prijzen) - timedelta(days=1)
    gat = {s: p for s, p in prijzen.items() if P._lokaal(s).date() not in
           (dag - timedelta(days=1), dag - timedelta(days=7))}
    ctx = M.Context(gat)
    sleutel = P.uren_van_dag(dag)[12]
    r = M.rij(sleutel, 1, weer[sleutel], ctx, M.OPZETTEN["vertraging"])
    niveau = ctx.niveau_tot(dag - timedelta(days=1))
    assert abs(r[10] - niveau * 10) < 1e-12 and abs(r[11] - niveau * 10) < 1e-12


def test_een_model_per_groep_en_k_als_kenmerk_voor_de_week():
    assert M.groepen_van(M.OPZETTEN["basis"]) == {1: (1,)}
    assert M.groepen_van(M.OPZETTEN["vertraging"]) == M.GROEPEN
    assert [M.model_voor(M.OPZETTEN["vertraging"], k) for k in range(1, 8)] == [1, 2, 3, 3, 3, 3, 3]
    assert [M.model_voor(M.OPZETTEN["basis"], k) for k in range(1, 8)] == [1] * 7
    prijzen, weer = _reeks(dagen=45)
    ctx = M.Context(prijzen)
    rijen = M.bouw_rijen(prijzen, weer, ctx, M.OPZETTEN["vertraging"])
    assert set(rijen) == {1, 2, 3}
    # de weekgroep traint op k=3..7 tegelijk: vijf keer zoveel rijen, eentje langer (k/7)
    assert len(rijen[3][0]) > 4 * len(rijen[2][0])
    assert len(rijen[3][0][0]) == len(rijen[1][0][0]) + 1
    modellen = M.train(prijzen, weer, ctx, M.OPZETTEN["vertraging"], rijen)
    assert modellen[1] != modellen[2]


def test_terugtoets_respecteert_de_oorsprong():
    prijzen, weer = _reeks(dagen=50)
    rijen_dag = {}
    ctx = M.Context(prijzen)
    rijen = M.bouw_rijen(prijzen, weer, ctx, M.OPZETTEN["vertraging"])
    for groep, (_r, _d, dagen) in rijen.items():
        rijen_dag[groep] = max(dagen)
    o = max(ctx.dagsom) - timedelta(days=10)
    cache = {}
    a = M.fit_tot(rijen[1], o, cache=cache)
    # dezelfde fit zonder de rijen na o
    keus = [i for i, d in enumerate(rijen[1][2]) if d <= o.toordinal()]
    b = M.fit_tot(([rijen[1][0][i] for i in keus], [rijen[1][1][i] for i in keus],
                   [rijen[1][2][i] for i in keus]), None)
    assert max(abs(x - y) for x, y in zip(a, b)) < 1e-9


def test_vertraging_helpt_morgen_als_de_prijs_op_gisteren_leunt():
    prijzen, weer = _reeks(dagen=75, ar=0.95)
    keuze = M.kies_opzet(prijzen, weer, oorsprongen=14, kandidaten=("basis", "vertraging"))
    basis, nieuw = keuze["per_opzet"]["basis"], keuze["per_opzet"]["vertraging"]
    # morgen: de prijs van vandaag zegt veel als het niveau van dag tot dag doorloopt
    assert nieuw[1]["model_ct"] < basis[1]["model_ct"] * 0.95
    # de keuze volgt de score over morgen tot en met over drie dagen
    s = keuze["scores"]
    assert keuze["opzet"] == ("vertraging" if s["vertraging"] < s["basis"] * 0.99 else "basis")
    assert set(nieuw) >= {1, 2, 3, 7}
    assert keuze["backtest"]["dagen"] >= 10 and keuze["residuen"][1]["res_p10"] < 0 < keuze["residuen"][1]["res_p90"]
    assert 0.5 <= keuze["schaal_terugtoets"] <= 4.0


def test_basis_blijft_als_niets_aantoonbaar_helpt():
    prijzen, weer = _reeks(dagen=60, ar=0.0)
    keuze = M.kies_opzet(prijzen, weer, oorsprongen=10, kandidaten=("basis", "vertraging_ver"))
    # zonder verre buren in het weer is vertraging_ver hooguit zo goed als
    # vertraging; basis wint tenzij het minstens 1% beter is
    s = keuze["scores"]
    assert keuze["opzet"] == ("basis" if s["vertraging_ver"] > s["basis"] * 0.99 else "vertraging_ver")


def test_naieven_en_tabel_per_vooruit():
    prijzen, weer = _reeks(dagen=50)
    samen = M.vat_samen(M.terugtoets(prijzen, weer, M.OPZETTEN["vertraging"], oorsprongen=8))
    tabel = M.tabel_per_vooruit(samen, {"d1": {"dagen": 3, "afwijking_model_ct": 3.63,
                                                "afwijking_zoals_gisteren_ct": 5.0,
                                                "dekking_band_procent": 77.0}})
    assert tabel[0]["vooruit"] == 1 and tabel[0]["live_excl_ct"] == 3.0
    assert abs(tabel[0]["terugtoets_excl_ct"] - tabel[0]["terugtoets_ct"] / 1.21) < 0.01
    assert {"zoals_gisteren_ct", "zoals_vorige_week_ct", "mix_ct"} <= set(tabel[1])


def test_gasniveau_en_ver_als_kenmerk():
    prijzen, weer = _reeks(dagen=30)
    gas = {date(2026, 7, 1) + timedelta(days=i): 1.4 + 0.01 * i for i in range(30)}
    ctx = M.Context(prijzen, gas)
    s = sorted(prijzen)[-5]
    w = {**weer[s], "wind_ver": 40.0, "zon_ver": 200.0}
    r = M.rij(s, 1, w, ctx, M.OPZETTEN["vertraging_ver_gas"])
    assert r[10] == 4.0 and r[11] == 2.0
    d = P._lokaal(s).date()
    assert abs(r[12] - gas[d - timedelta(days=1)]) < 1e-12   # het gas van d-1, niet van d


def test_weer_met_verre_buren():
    def punt(wind, zon):
        return {"hourly": {"time": ["2026-10-21T12:00"], "wind_speed_100m": [wind],
                           "shortwave_radiation": [zon], "temperature_2m": [10]}}

    antwoord = ([punt(20, 100)] * len(P.PUNTEN) + [punt(40, 300)] * len(P.BUUR_PUNTEN)
                + [punt(60, 50)] * len(P.VER_PUNTEN))
    w = P.weer_uit_open_meteo(antwoord)["2026-10-21T12"]
    assert w["wind_ver"] == 60.0 and w["zon_ver"] == 50.0 and w["wind_buur"] == 40.0
    assert len(P.PUNTEN + P.BUUR_PUNTEN + P.VER_PUNTEN) <= 16
    assert P.open_meteo_url().count("-1.2") == 1


def test_maak_verwachting_met_opzet_en_band():
    prijzen, weer = _reeks(dagen=45)
    laatste = max(P._lokaal(s).date() for s in prijzen)
    for h in range(1, 24 * 8):
        t = datetime.combine(laatste, datetime.min.time(), P.TZ) + timedelta(hours=h)
        weer[P.uur_sleutel(t)] = {"wind": 20.0, "zon": 0.0, "temp": 10.0}
    res = {k: {"res_p10": -0.03, "res_p90": 0.04} for k in range(1, 8)}
    uit = P.maak_verwachting(prijzen, weer, laatste, laatste, opzet="vertraging", residuen=res, schaal=1.5)
    assert uit["opzet"] == "vertraging" and "deel_van_gisteren" in uit["gevoeligheid"]
    assert len(uit["dagen"]) == 7
    d = uit["dagen"][(laatste + timedelta(days=3)).isoformat()]
    assert d["k"] == 3 and d["band"]["bron"] == "restfout"
    u, b = d["model"]["uren"][5], d["band"]["uren"][5]
    assert abs(b["p10"] - (u["prijs_eur"] - 0.045)) < 1e-4 and abs(b["p90"] - (u["prijs_eur"] + 0.06)) < 1e-4
    assert b["p10"] < b["p25"] < u["prijs_eur"] < b["p75"] < b["p90"]
