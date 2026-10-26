"""v5.131.0: de terugspeling vergelijkt eerlijk (punt A van de terugmeting).

Gevraagd 26-10: "Uitzoeken waarom het plan over 3 scenario's in de terugspeling
beter scoort dan 'best mogelijk'." Nagerekend op 22-09 (sensor: scenarioplan
-2,478, best mogelijk -1,388): drie ongelijkheden, geen fout in de sturing.

1. Het scenarioplan mag uit het net laden, best mogelijk niet. Nu ook
   `best_mogelijk_netladen_salderen_eur`.
2. Teruglevering: scenarioplan prijs + 2 ct premie, best mogelijk kale prijs.
   Nu overal met premie (keuzeoordeel en nabeschouwing).
3. Eenheden: `vooruitplan` rekent het hele verlies bij het laden; begin en
   capaciteit gingen er als opgeslagen kWh in (~10 % te veel). En het
   ontlaadvermogen is een AC-grens (uit de cellen 1/√rendement zoveel).
"""
import json
from pathlib import Path

from custom_components.energy_management_system import herspeel as H
from custom_components.energy_management_system import keuzeoordeel as K
from custom_components.energy_management_system import nabeschouwing as N

DAG = json.loads((Path(__file__).parent / "fixtures" / "dagverloop_2026-09-22.json").read_text())
MODEL = dict(capaciteit_kwh=11.52, min_soc_procent=10, laad_kw=2.4, ontlaad_kw=2.4,
             rendement=0.829775, slijtage_eur=0.0422)


def _dag22():
    return H.herspeel({"2026-09-22": DAG}, None, **MODEL)["dagen"][0]


def test_scenarioplan_niet_beter_dan_het_echte_optimum():
    d = _dag22()
    # het optimum met netladen is de ondergrens voor elk plan dat ook netlaadt
    assert d["best_mogelijk_netladen_salderen_eur"] <= d["scenarioplan_salderen_eur"] + 0.005
    # netladen erbij maakt het optimum nooit duurder
    assert d["best_mogelijk_netladen_salderen_eur"] <= d["best_mogelijk_salderen_eur"] + 0.001
    # en het voorbeeld dat het meldde: het verschil is uitgelegd
    assert d["scenarioplan_salderen_eur"] - d["best_mogelijk_netladen_salderen_eur"] < 0.10


def test_samenvatting_kent_het_nieuwe_veld():
    s = H.herspeel({"2026-09-22": DAG}, None, **MODEL)["samenvatting"]
    assert "best_mogelijk_netladen_salderen_per_dag_eur" in s


def _vlak(huis, prijs, n=8):
    return [K.Kwartier(tijd=f"{i // 4:02d}:{i % 4 * 15:02d}", huis_kwh=huis, pv_kwh=0.0, prijs_eur=prijs,
                       accu_kwh=0.0) for i in range(n)]


def test_ontlaadgrens_is_ac():
    m = K._model(_vlak(0.1, 0.3), 5.0, 0.0, 2.0, 2.4, 0.81, 0.05)
    # 2,4 kW AC = 0,6 kWh per kwartier; uit de cellen 0,6 / 0,9 = 0,667 -> 13 stappen
    assert m["ontlaad_max"] == 13


def test_teruglevering_met_premie():
    k = _vlak(0.0, 0.30, 1)[0]
    m = K._model([k], 5.0, 0.0, 2.0, 2.0, 0.81, 0.05)
    assert K._netkosten(-1.0, k, m) == -(0.30 + K.PREMIE_EUR)
    assert K._netkosten(1.0, k, m) == 0.30
    nk = N.Kwartier(huis_kwh=0.0, pv_kwh=1.0, prijs_eur=0.30, accu_kwh=0.0)
    assert N.kosten_zonder_accu([nk]) == -(0.30 + N.PREMIE_EUR)


def test_beste_kosten_met_netladen_is_goedkoper_bij_prijsverschil():
    dag = [K.Kwartier(tijd=f"{i // 4:02d}:{i % 4 * 15:02d}", huis_kwh=0.25, pv_kwh=0.0,
                      prijs_eur=0.10 if i < 8 else 0.60, accu_kwh=0.0) for i in range(16)]
    arg = dict(capaciteit_kwh=5.0, begin_kwh=0.0, bodem_kwh=0.0, laad_kw=2.0, ontlaad_kw=2.0,
               rendement=0.9, slijtage_eur_per_kwh=0.04)
    zonder = K.beste_kosten(dag, **arg)
    met = K.beste_kosten(dag, netladen=True, **arg)
    assert met < zonder - 0.5
