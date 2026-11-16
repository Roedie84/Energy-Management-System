"""v5.236.0: de prijsverwachting meet wat een gemiste keuze kost.

Ruud 16-11: "Hoe goed is het prijs vooruitzicht?" - goedkoopste uren 1,7 van
de 4 geraakt. Onderzoek: het dal is vlak, dus het aantal geraakte uren zegt
weinig over de kosten.
"""
from custom_components.energy_management_system import prijsverwachting as P


def _dag(verwacht, echt):
    uren = [{"sleutel": f"2026-11-16T{u:02d}", "prijs_eur": v} for u, v in enumerate(verwacht)]
    return P.vergelijk({"datum": "2026-11-16", "uren": uren}, {f"2026-11-16T{u:02d}": e for u, e in enumerate(echt)})


VLAK = [0.40] * 24


def test_alles_goed_geraden_kost_niets():
    echt = [0.30, 0.31, 0.32, 0.33] + [0.40] * 16 + [0.50, 0.51, 0.52, 0.53]
    u = _dag(echt, echt)
    assert u["goedkoopste_uren_geraakt"] == 4 and u["goedkoopste_meerprijs_eur"] == 0.0
    assert u["duurste_uren_geraakt"] == 4 and u["duurste_gemist_eur"] == 0.0


def test_vlak_dal_niets_geraakt_kost_bijna_niets():
    echt = [0.300, 0.301, 0.302, 0.303, 0.304, 0.305, 0.306, 0.307] + [0.40] * 16
    verwacht = [0.35, 0.35, 0.35, 0.35, 0.30, 0.30, 0.30, 0.30] + [0.40] * 16     # kiest 4-7 i.p.v. 0-3
    u = _dag(verwacht, echt)
    assert u["goedkoopste_uren_geraakt"] == 0
    assert u["goedkoopste_meerprijs_eur"] == 0.004


def test_verkeerd_blok_kost_het_verschil():
    echt = [0.20] * 4 + [0.40] * 20                 # nacht goedkoop
    verwacht = [0.40] * 12 + [0.20] * 4 + [0.40] * 8  # verwachting kiest de middag
    u = _dag(verwacht, echt)
    assert u["goedkoopste_uren_geraakt"] == 0 and u["goedkoopste_meerprijs_eur"] == 0.2


def test_dure_kant_gemist():
    echt = [0.40] * 20 + [0.60] * 4
    verwacht = [0.60] * 4 + [0.40] * 20
    u = _dag(verwacht, echt)
    assert u["duurste_uren_geraakt"] == 0 and u["duurste_gemist_eur"] == 0.2


def test_samenvatting_en_dagrij_tonen_de_meerprijs_in_ct():
    goed = _dag([0.20] * 4 + [0.40] * 20, [0.20] * 4 + [0.40] * 20)
    fout = _dag([0.40] * 12 + [0.20] * 4 + [0.40] * 8, [0.20] * 4 + [0.40] * 20)
    uit = P.beoordeel([{"model": goed, "naief": fout}, {"model": fout, "naief": fout}])
    assert uit["goedkoopste_meerprijs_ct"] == 10.0
    assert uit["goedkoopste_meerprijs_zoals_gisteren_ct"] == 20.0
    assert uit["duurste_gemist_ct"] is not None
    rij = P.dagrij({"model": fout, "naief": goed})
    assert rij["goedkoopste_meerprijs_ct"] == 20.0 and "duurste_gemist_ct" in rij


def test_oude_uitkomst_zonder_de_velden_breekt_niets():
    oud = {"datum": "x", "gemiddelde_afwijking_eur": 0.03, "verwacht_gemiddeld_eur": 0.4, "echt_gemiddeld_eur": 0.4,
           "echt_duurste_eur": 0.5, "duurste_uren_geraakt": 3, "goedkoopste_uren_geraakt": 2}
    uit = P.beoordeel([{"model": oud, "naief": oud}])
    assert uit["goedkoopste_meerprijs_ct"] is None
    assert "goedkoopste_meerprijs_ct" not in P.dagrij({"model": oud, "naief": oud})
