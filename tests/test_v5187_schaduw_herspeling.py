"""v5.187.0 economische schaduw - plantoets 1: de echte dag 28-10 (regressie).

Herspeling 26-10 t/m 28-10 op de gemeten kwartieren (fixture), uitvoeren en
afrekenen via `economische_schaduw`. Bijlage A van het plan: productie 1,967 EUR,
niets doen 1,808 EUR, inhoud 1,82 -> 3,09 kWh; met voorraadcorrectie een besparing.
"""
import pytest

from custom_components.energy_management_system import economische_schaduw as es
from tests import _schaduw_herspeling as H


@pytest.fixture(scope="module")
def herspeling():
    return H.herspeel("2026-10-26", "2026-10-29")


def test_28_10_productie_niets_doen_en_voorraad(herspeling):
    per_dag, waarden = herspeling
    rijen = [es.rij_als_lijst(r) for r in per_dag["2026-10-28"]]
    assert len(rijen) == 96
    dag = es.dagsamenvatting("2026-10-28", rijen, waarden["2026-10-28"], H.ETA_O, H.CAP)
    # kasstroom + slijtage zonder voorraadcorrectie (zoals de audit)
    assert dag["production_kas_eur"] + dag["production_slijtage_eur"] == pytest.approx(1.967, rel=0.02)
    assert dag["zonder_accu_eur"] == pytest.approx(1.808, rel=0.02)
    eerste, laatste = per_dag["2026-10-28"][0], per_dag["2026-10-28"][-1]
    assert eerste["p_inh0"] == pytest.approx(1.82, rel=0.02)
    assert laatste["p_inh1"] == pytest.approx(3.09, rel=0.02)
    assert dag["production_voorraad_kwh"] == pytest.approx(1.27, abs=0.03)
    # met voorraadcorrectie tegen de eindwaarde van het eerste plan: geen verlies
    assert 0.2 <= dag["waarde_inhoud"] <= 0.4
    assert dag["ems_besparing_eur"] > 0
    assert dag["production_cost_eur"] < dag["zonder_accu_eur"]
    assert dag["volledig"] is True and dag["kwartieren_ok"] == 96


def test_gelijke_varianten_geven_nul_verschil(herspeling):
    per_dag, waarden = herspeling
    rijen = [es.rij_als_lijst(r) for r in per_dag["2026-10-27"]]
    dag = es.dagsamenvatting("2026-10-27", rijen, waarden["2026-10-27"], H.ETA_O, H.CAP)
    assert dag["saving_c2_eur"] == 0 and dag["saving_c0_eur"] == 0
    assert dag["different_actions_c2_pct"] == 0
