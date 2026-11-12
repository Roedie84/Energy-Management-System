"""v5.230.0: de gemiste opbrengst van de stilstand van 08/09-11-2026 eenmalig bijboeken."""

import inspect

from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)


def _c(make_coordinator, rauw=-2.5611, maandsleutel=202611):
    c = make_coordinator({})
    c.counterfactual_cost_all_time_eur = 44.82
    c.actual_cost_all_time_eur = -5.04
    c.counterfactual_cost_current_month_eur = 45.06
    c._counterfactual_month_key = maandsleutel
    c.besparing_maand = {"maand": "2026-11" if maandsleutel == 202611 else "2026-12", "begin_eur": 46.6098, "waarde_eur": 3.48}
    c.besparing_dagen = [
        {"datum": "2026-11-07", "hoofdgetal_eur": 0.1124, "rauw_eur": 0.1124},
        {"datum": "2026-11-08", "hoofdgetal_eur": -1.98, "rauw_eur": rauw},
        {"datum": "2026-11-09", "hoofdgetal_eur": 1.4587, "rauw_eur": 2.0398},
    ]
    c.hoofdgetal_correcties = None
    return c


def test_boekt_eenmalig_bij(make_coordinator):
    c = _c(make_coordinator)
    assert c._boek_stilstand_0811_bij() is True
    assert round(c.counterfactual_cost_all_time_eur, 2) == 46.90
    assert round(c.counterfactual_cost_current_month_eur, 2) == 47.14
    per_dag = {d["datum"]: d for d in c.besparing_dagen}
    r = lambda dag, veld: round(per_dag[dag][veld], 4)
    assert r("2026-11-08", "rauw_eur") == -0.9511 and r("2026-11-08", "hoofdgetal_eur") == -0.37
    assert r("2026-11-09", "rauw_eur") == 2.5098 and r("2026-11-09", "hoofdgetal_eur") == 1.9287
    assert per_dag["2026-11-07"] == {"datum": "2026-11-07", "hoofdgetal_eur": 0.1124, "rauw_eur": 0.1124}
    assert c.besparing_maand["begin_eur"] == 46.6098       # november: de beginstand blijft
    assert c.hoofdgetal_correcties == ["stilstand-2026-11-08"]
    # tweede keer: niets
    assert c._boek_stilstand_0811_bij() is False
    assert round(c.counterfactual_cost_all_time_eur, 2) == 46.90


def test_een_andere_installatie_of_al_gecorrigeerd_blijft_ongemoeid(make_coordinator):
    for rauw in (-0.95, 0.4, None):
        c = _c(make_coordinator, rauw=rauw)
        assert c._boek_stilstand_0811_bij() is False
        assert c.counterfactual_cost_all_time_eur == 44.82 and not c.hoofdgetal_correcties
    c = _c(make_coordinator)
    c.besparing_dagen = []
    assert c._boek_stilstand_0811_bij() is False


def test_in_een_latere_maand_schuift_de_beginstand_mee(make_coordinator):
    c = _c(make_coordinator, maandsleutel=202612)
    assert c._boek_stilstand_0811_bij() is True
    assert round(c.counterfactual_cost_all_time_eur, 2) == 46.90
    assert c.counterfactual_cost_current_month_eur == 45.06
    assert round(c.besparing_maand["begin_eur"], 4) == 48.6898


def test_het_totaal_van_de_bijboeking_is_2_08():
    _naam, _maand, dagen = C.STILSTAND_0811
    assert round(sum(b for _d, b in dagen), 2) == 2.08


def test_wordt_bij_het_laden_aangeroepen_en_bewaard():
    from custom_components.energy_management_system.const import PERSISTED_PLAIN_FIELDS
    assert "hoofdgetal_correcties" in PERSISTED_PLAIN_FIELDS
    bron = inspect.getsource(C)
    laden = bron[bron.index("self._migreer_dagreeks_kosten()\n        self._ruim_oude_klimaatcellen_op()"):]
    assert "if self._boek_stilstand_0811_bij():" in laden[:6000]
