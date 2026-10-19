"""v5.100: generale repetitie voor 2027 (na de saldering)."""
from custom_components.energy_management_system import regime2027 as R

ARG = dict(capaciteit_kwh=5.0, laad_kw=2.0, ontlaad_kw=2.0, rendement=0.9)


def _dag(n=96, **kw):
    basis = dict(huis_kwh=0.1, pv_kwh=0.0, import_eur=0.30, export_eur=0.05, accu_kwh=0.0)
    basis.update(kw)
    return [R.Kwartier(**basis) for _ in range(n)]


def test_te_weinig_kwartieren():
    uit = R.repetitie(_dag(40), begin_kwh=2.0, eind_kwh=2.0, **ARG)
    assert uit["te_becijferen"] is False and "minimaal 80" in uit["reden"]


def test_verkopen_wordt_in_2027_begrensd_tot_het_huis():
    # het EMS verkocht 0,5 kWh per kwartier terwijl het huis 0,1 vroeg
    dag = _dag(96, accu_kwh=0.0)
    for k in dag[72:80]:
        k.accu_kwh, k.verkoop = 0.5, False
    uit = R.repetitie(dag, begin_kwh=4.0, eind_kwh=0.0, **ARG)
    assert uit["te_becijferen"]
    # in 2027 levert terugverkopen tegen 5 ct minder op dan bewaren tegen 30 ct
    assert uit["overgang_levert_op_eur"] > 0
    assert uit["anders_dan_nu_kwartieren"] == 8
    assert uit["uit_accu_teruggeleverd_kwh"] == 3.2


def test_opvangen_van_zon_telt_mee():
    dag = _dag(96, pv_kwh=0.0)
    for k in dag[40:56]:
        k.pv_kwh, k.opvangen = 0.4, True   # overschot 0,3 kWh, het EMS deed niets
    for k in dag[72:96]:
        k.huis_kwh = 0.3
    uit = R.repetitie(dag, begin_kwh=0.0, eind_kwh=0.0, **ARG)
    assert uit["accu_levert_op_2027_eur"] > uit["accu_levert_op_nu_eur"]
    assert uit["regels_laten_liggen_eur"] >= -0.05


def test_best_mogelijk_nooit_slechter_dan_regels():
    dag = _dag(96)
    for i, k in enumerate(dag):
        k.pv_kwh = 0.5 if 36 <= i < 60 else 0.0
        k.import_eur = 0.45 if 68 <= i < 84 else 0.25
        k.opvangen = k.pv_kwh > k.huis_kwh
        k.accu_kwh = 0.1 if i >= 68 else 0.0
    uit = R.repetitie(dag, begin_kwh=1.0, eind_kwh=0.0, **ARG)
    assert uit["best_mogelijk_eur"] <= uit["regels_2027_eur"] + 0.02


def test_samenvatting_oordeel():
    dag = {"te_becijferen": True, "datum": "2026-10-18", "accu_levert_op_nu_eur": 0.5,
           "accu_levert_op_2027_eur": 0.9, "overgang_levert_op_eur": 0.1, "regels_laten_liggen_eur": 0.05}
    s = R.samenvatting([dag] * 8)
    assert s["dagen"] == 8 and s["oordeel"].startswith("klaar voor 2027")
    s = R.samenvatting([{**dag, "regels_laten_liggen_eur": 0.6}] * 8)
    assert "laten nog geld liggen" in s["oordeel"]
    assert "zeven dagen" in R.samenvatting([dag])["oordeel"]
    assert R.samenvatting([])["dagen"] == 0


def test_kaart():
    assert R.kaart({"dagen": 0, "oordeel": "nog geen dag doorgerekend"})["kaart_primair"] == "Generale repetitie 2027"
    k = R.kaart({"per_dag_2027_eur": 0.456, "oordeel": "klaar", "regels_laten_liggen_eur": 1.2, "dagen": 9})
    assert k["kaart_primair"] == "€ 0,46 per dag in 2027" and "€ 1,20 in 9 dagen" in k["kaart_secundair"]


def test_stilstaande_volle_accu_levert_niets_op():
    """Reviewbevinding: de eindwaarde werd gerekend zonder de beginwaarde."""
    uit = R.repetitie(_dag(96), begin_kwh=4.0, eind_kwh=4.0, **ARG)
    assert abs(uit["accu_levert_op_nu_eur"]) < 0.01
    assert uit["regels_laten_liggen_eur"] >= 0


def test_extra_zon_wordt_s_avonds_gebruikt_in_een_dekkende_stand():
    dag = _dag(96)
    for i, k in enumerate(dag):
        k.dekt = True
        if 40 <= i < 56:
            k.pv_kwh, k.opvangen = 0.4, True
    uit = R.repetitie(dag, begin_kwh=0.0, eind_kwh=0.0, **ARG)
    # de opgevangen zon dekt het huis daarna, in plaats van alleen restwaarde te zijn
    assert uit["accu_levert_op_2027_eur"] > 0.5


def test_kwartier_zonder_teruglevertarief_blijft_meedoen():
    dag = _dag(96)
    dag[10].export_eur = None
    uit = R.repetitie(dag, begin_kwh=1.0, eind_kwh=1.0, **ARG)
    assert uit["te_becijferen"] and uit["kwartieren"] == 96
    dag2 = _dag(96)
    for k in dag2[:20]:
        k.export_eur = None
    assert R.repetitie(dag2, begin_kwh=1.0, eind_kwh=1.0, **ARG)["te_becijferen"] is False
