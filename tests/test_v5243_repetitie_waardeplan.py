"""v5.243.0 - de generale repetitie 2027 speelt ook het waardeplan na.

Ruud 19-11: proefdraaien voor 2027. De repetitie speelde alleen de oudere
regels van 2027 na; het waardeplan stuurt sinds v5.158. Nu rekent de
dagafsluiting dezelfde dag ook met het waardeplan en het tarief van 2027.
Alleen meten. Plus een toets op de jaarwissel: een kwartier voor middernacht
rekent met de saldering, het kwartier erna met het kale tarief.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import regime2027 as R
from custom_components.energy_management_system import waardeplan as W
from custom_components.energy_management_system.const import PRICE_SCALE_FACTOR

ARG = dict(capaciteit_kwh=5.0, laad_kw=2.0, ontlaad_kw=2.0, rendement=0.9)
TZ = timezone(timedelta(hours=1))


def _dag(n=96, **kw):
    basis = dict(huis_kwh=0.1, pv_kwh=0.0, import_eur=0.30, export_eur=0.05, accu_kwh=0.0)
    basis.update(kw)
    return [R.Kwartier(**basis) for _ in range(n)]


def _zonnige_dag():
    dag = _dag(96)
    for k in dag[40:56]:
        k.pv_kwh = 0.4          # overschot 0,3 kWh per kwartier
    for k in dag[72:96]:
        k.huis_kwh = 0.3
    return dag


def test_waardeplan_vangt_zon_op_voor_de_avond():
    uit = R.repetitie(_zonnige_dag(), begin_kwh=0.0, eind_kwh=0.0, **ARG)
    assert uit["waardeplan_2027_eur"] is not None
    # opslaan tegen 5 ct gemist en 30 ct bespaard: het plan gebruikt de accu
    assert uit["accu_levert_op_waardeplan_2027_eur"] > 0.5
    assert uit["waardeplan_uit_accu_kwh"] > 2.0
    # en het doet het niet slechter dan niets doen
    assert uit["waardeplan_2027_eur"] < uit["zonder_accu_eur"]


def test_waardeplan_verkoopt_niet_tegen_een_laag_tarief():
    # volle accu, terugleveren levert 5 ct op, inkoop kost 30 ct: alles naar het huis
    uit = R.repetitie(_dag(96), begin_kwh=4.0, eind_kwh=4.0, **ARG)
    plan = R.waardeplan_2027(_dag(96), begin_kwh=4.0, capaciteit_kwh=5.0, laad_kw=2.0, ontlaad_kw=2.0,
                             eta=0.9 ** 0.5, slijtage=0.0)
    assert plan is not None and plan["uit_accu_kwh"] <= 4.0 * 0.95 + 0.05
    assert uit["waardeplan_laat_liggen_eur"] is not None


def test_zelfde_afrekening_als_de_andere_kolommen():
    # zonder zon en met een lege accu valt er niets te halen: gelijk aan zonder accu
    dag = _dag(96, import_eur=0.30, export_eur=0.05)
    uit = R.repetitie(dag, begin_kwh=0.0, eind_kwh=0.0, **ARG)
    assert uit["waardeplan_2027_eur"] == pytest.approx(uit["zonder_accu_eur"], abs=0.02)
    assert uit["accu_levert_op_waardeplan_2027_eur"] == pytest.approx(0.0, abs=0.02)


def test_plan_dat_er_niet_uitkomt_geeft_geen_getal(monkeypatch):
    monkeypatch.setattr(W, "plan", lambda kws, accu: W.Uitkomst(False, "geen plan"))
    uit = R.repetitie(_zonnige_dag(), begin_kwh=0.0, eind_kwh=0.0, **ARG)
    assert uit["te_becijferen"] is True
    assert uit["waardeplan_2027_eur"] is None and uit["accu_levert_op_waardeplan_2027_eur"] is None
    # de bestaande kolommen blijven staan
    assert uit["regels_2027_eur"] is not None


def test_een_fout_in_het_plan_raakt_de_repetitie_niet(monkeypatch):
    def stuk(kws, accu):
        raise RuntimeError("stuk")
    monkeypatch.setattr(W, "plan", stuk)
    uit = R.repetitie(_zonnige_dag(), begin_kwh=0.0, eind_kwh=0.0, **ARG)
    assert uit["te_becijferen"] is True and uit["waardeplan_2027_eur"] is None


def test_samenvatting_telt_het_waardeplan():
    dag = R.repetitie(_zonnige_dag(), begin_kwh=0.0, eind_kwh=0.0, **ARG)
    s = R.samenvatting([dict(dag, datum=f"2026-11-{d:02d}") for d in range(1, 9)])
    assert s["waardeplan_dagen"] == 8
    assert s["accu_levert_op_waardeplan_2027_eur"] == pytest.approx(8 * dag["accu_levert_op_waardeplan_2027_eur"], abs=0.02)
    assert s["waardeplan_per_dag_2027_eur"] == pytest.approx(dag["accu_levert_op_waardeplan_2027_eur"], abs=0.01)
    # oude dagen zonder de nieuwe kolom tellen niet mee en breken niets
    oud = {k: v for k, v in dag.items() if "waardeplan" not in k}
    s2 = R.samenvatting([dict(oud, datum="2026-10-01")] * 8)
    assert s2["waardeplan_dagen"] == 0 and s2["waardeplan_per_dag_2027_eur"] is None


def test_jaarwissel_per_kwartier(make_coordinator, hass):
    """31-12 23:45 rekent nog met de saldering, 01-01 00:00 met het kale tarief."""
    c = make_coordinator({})
    c._segmenten_verbruik_zon = lambda a, b, veilig=True: [(0.1, 0.0)]
    c._estimate_pv_kwh_for_period = lambda a, b, veilig=False: 0.0
    c._planning_verkoopreserve_kwh = lambda *a: 0.0
    nu = datetime(2026, 12, 31, 23, 30, tzinfo=TZ)
    entries = [(nu + timedelta(minutes=15 * i), nu + timedelta(minutes=15 * (i + 1)), 0.30 * PRICE_SCALE_FACTOR)
               for i in range(4)]
    c._kale_entries = lambda: [(a, b, 0.10 * PRICE_SCALE_FACTOR) for a, b, _p in entries]
    assert c._is_salderen_active(datetime(2026, 12, 31, 23, 45, tzinfo=TZ)) is True
    assert c._is_salderen_active(datetime(2027, 1, 1, 0, 0, tzinfo=TZ)) is False
    kw = c._waardeplan_kwartieren(nu, entries)
    assert len(kw) == 4
    voor, na = kw[1], kw[2]
    assert voor.begin.year == 2026 and na.begin.year == 2027
    # onder de saldering: geen aparte accuprijs, terugleveren rond de inkoopprijs
    assert voor.teruglever_accu_eur is None
    assert voor.teruglever_eur >= voor.inkoop_eur
    # vanaf 1 januari: volle inkoopprijs, kaal tarief terug, accu zonder zonnebonus
    assert na.inkoop_eur == pytest.approx(0.30)
    assert na.teruglever_eur < na.inkoop_eur
    assert na.teruglever_accu_eur is not None and na.teruglever_accu_eur < na.teruglever_eur
