"""v5.130.0: de herspeeluitslag per EMS-versie op de zelfanalyse-sensor.

Gevraagd 26-10 (punt B van de terugmeting): "De uitslag van de terugspeling per
EMS-versie zichtbaar maken op de zelfanalyse-sensor, zodat je voor en na een
versie kunt vergelijken."
"""
import asyncio
from datetime import timedelta

import pytest

from test_v5123_herspeel import _dag


def _met_twee_versies(make_coordinator):
    c = make_coordinator({})
    from custom_components.energy_management_system import coordinator as mod

    gisteren = (mod.dt_util.now().date() - timedelta(days=1)).isoformat()
    c.dagverloop = {gisteren: _dag()}
    c._gemeten_kwartieren = lambda d: {}
    c.bruikbare_capaciteit_kwh = lambda: 9.8
    for versie in ("5.129.1", "5.130.0"):
        c._manifest_versie = versie
        asyncio.run(c._async_herspeel())
    return c, gisteren


def test_zelfanalyse_toont_per_versie(make_coordinator):
    c, dag = _met_twee_versies(make_coordinator)
    h = c.get_zelfanalyse()["herspeel"]
    assert set(h["per_versie"]) == {"5.129.1", "5.130.0"}
    regel = h["per_versie"]["5.130.0"]
    assert regel["dagen"] == f"{dag} t/m {dag}"
    assert regel["aantal_dagen"] == 1
    assert "werkelijk_salderen_per_dag_eur" in regel
    # alleen bedragen per dag, geen sommen (die staan in de diagnostiek)
    assert not any(k.endswith("_som_eur") for k in regel)


def test_laatste_twee_versies_met_venster(make_coordinator):
    c, dag = _met_twee_versies(make_coordinator)
    twee = c.get_zelfanalyse()["herspeel"]["laatste_twee_versies"]
    assert (twee["oud"], twee["nieuw"]) == ("5.129.1", "5.130.0")
    assert twee["zelfde_dagen"] is True
    assert twee["per_dag_verschil_eur"]["werkelijk_salderen_per_dag_eur"] == pytest.approx(0.0)
    assert c.get_herspeel()["laatste_twee_versies"] == twee


def test_een_versie_geen_vergelijking(make_coordinator):
    c = make_coordinator({})
    c.herspeel_per_versie = {"5.130.0": {"berekend_om": "x", "van": "a", "tot": "b",
                                         "samenvatting": {"dagen": 3, "werkelijk_salderen_per_dag_eur": 0.1}}}
    h = c.get_zelfanalyse()["herspeel"]
    assert h["per_versie"]["5.130.0"]["werkelijk_salderen_per_dag_eur"] == 0.1
    assert "laatste_twee_versies" not in h
