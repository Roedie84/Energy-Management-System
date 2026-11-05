"""v5.188.0: jaarafrekening - betaald tegenover werkelijk en de verwachte afrekening.

Ruud 05-11-2026: termijn Zonneplan 70 euro, afschrijving rond de 25e, contractjaar
vanaf 1 april, gas tot 22-11 bij Zonneplan en daarna 60 euro bij een andere
leverancier.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import jaarafrekening as ja
from custom_components.energy_management_system import jaarafrekening_sturing as js


def _inst(**k):
    basis = dict(termijn_eur=70.0, afschrijfdag=25, vastrecht_stroom_mnd=0.0, vastrecht_gas_mnd=0.0,
                 netbeheer_stroom_jaar=0.0, netbeheer_gas_jaar=0.0, vermindering_eb_jaar=0.0)
    basis.update(k)
    return ja.Instellingen(**basis)


def _vol(begin: date, eind: date, **waarden) -> dict:
    dagen, d = {}, begin
    while d <= eind:
        dagen[d] = dict(waarden)
        d += timedelta(days=1)
    return dagen


def test_contractjaar_vanaf_1_april():
    assert ja.contractjaar(date(2025, 4, 1), date(2026, 11, 5)) == (date(2026, 4, 1), date(2027, 3, 31))
    assert ja.contractjaar(date(2025, 4, 1), date(2026, 3, 31)) == (date(2025, 4, 1), date(2026, 3, 31))


def test_termijn_telt_pas_na_de_afschrijving():
    r = ja.bereken({}, date(2025, 4, 1), date(2026, 11, 5), _inst())
    assert r["termijnen_betaald"] == 7          # april t/m oktober; november pas rond de 25e
    assert r["betaald_eur"] == pytest.approx(490.0)
    assert r["volgende_afschrijving"] == "2026-11-25"
    assert ja.bereken({}, date(2025, 4, 1), date(2026, 11, 25), _inst())["termijnen_betaald"] == 8


def test_afschrijfdag_begrensd_op_korte_maand():
    datums = ja.afschrijfdatums(date(2026, 4, 1), 31)
    assert date(2027, 2, 28) in datums and date(2026, 4, 30) in datums


def test_werkelijk_en_stand_met_vaste_kosten_naar_rato():
    dagen = _vol(date(2026, 4, 1), date(2026, 11, 4), afname_eur=1.0, terug_eur=0.5)
    inst = _inst(vastrecht_stroom_mnd=0.0, netbeheer_stroom_jaar=365.0, vermindering_eb_jaar=0.0)
    r = ja.bereken(dagen, date(2025, 4, 1), date(2026, 11, 5), inst)
    n = (date(2026, 11, 4) - date(2026, 4, 1)).days + 1
    assert r["werkelijk_eur"] == pytest.approx(n * (0.5 + 1.0))       # 0,50 netto + 1,00 netbeheer per dag
    assert r["stand_eur"] == pytest.approx(490.0 - n * 1.5)


def test_vandaag_telt_nog_niet_mee():
    dagen = {date(2026, 11, 5): {"afname_eur": 100.0}}
    r = ja.bereken(dagen, date(2025, 4, 1), date(2026, 11, 5), _inst())
    assert r["werkelijk_eur"] == pytest.approx(0.0)


def test_schatting_met_dezelfde_dag_vorig_jaar():
    dagen = _vol(date(2025, 11, 5), date(2026, 3, 31), afname_eur=2.0)
    r = ja.bereken(dagen, date(2025, 4, 1), date(2026, 11, 5), _inst(saldering_eind=None))
    rest = (date(2027, 3, 31) - date(2026, 11, 5)).days + 1
    assert r["schatting_rest"]["afname_eur"] == pytest.approx(rest * 2.0, abs=2.0)
    assert r["verwacht_saldo_eur"] == pytest.approx(840.0 - r["verwacht_kosten_eur"])


def test_na_saldering_levert_teruglevering_minder_op():
    dagen = _vol(date(2026, 1, 1), date(2026, 3, 31), terug_eur=3.0, terug_kwh=10.0)
    met = ja.bereken(dagen, date(2025, 4, 1), date(2026, 11, 5), _inst(saldering_eind=None))
    zonder = ja.bereken(dagen, date(2025, 4, 1), date(2026, 11, 5), _inst(saldering_eind=date(2026, 12, 31)))
    per_dag = 3.0 - 10.0 * ja.EB_STROOM_INCL_EUR
    assert zonder["schatting_rest"]["terug_eur"] == pytest.approx(90 * per_dag, abs=0.01)
    assert met["schatting_rest"]["terug_eur"] == pytest.approx(90 * 3.0)


def test_gas_na_overstap_telt_niet_meer_bij_zonneplan():
    dagen = _vol(date(2025, 11, 1), date(2026, 11, 4), gas_eur=1.0, gas_m3=0.5)
    inst = _inst(gas_overstap=date(2026, 11, 22), netbeheer_gas_jaar=365.0)
    r = ja.bereken(dagen, date(2025, 4, 1), date(2026, 11, 5), inst)
    assert r["schatting_rest"]["gas_eur"] == pytest.approx(17.0)      # 5 t/m 21 november
    # vaste gaskosten ook alleen tot de overstap
    assert r["schatting_rest"]["vast_eur"] == pytest.approx(17.0)


def test_termijnadvies_naar_beneden_afgerond_op_vijf():
    dagen = _vol(date(2026, 4, 1), date(2026, 11, 4), afname_eur=0.5)
    r = ja.bereken(dagen, date(2025, 4, 1), date(2026, 11, 5), _inst())
    adv = r["advies"]
    assert adv["resterende_termijnen"] == 5
    assert adv["advies_termijn_eur"] % 5 == 0
    assert adv["advies_termijn_eur"] >= 0


def test_gas_nieuwe_leverancier():
    dagen = _vol(date(2025, 11, 5), date(2026, 11, 4), gas_m3=200.0 / 365)
    inst = _inst(gas_overstap=date(2026, 11, 22), gas_nieuw_prijs_m3=2.04363, netbeheer_gas_jaar=267.0,
                 gas_nieuw_vastrecht_mnd=8.33, gas_nieuw_korting_jaar=210.0, gas_nieuw_termijn_eur=60.0)
    g = ja.gas_nieuw(dagen, date(2026, 11, 5), inst)
    verwacht = 200.0 * 2.04363 + 8.33 * 12 + 267.0 - 210.0
    assert g["kosten_jaar_eur"] == pytest.approx(verwacht, abs=0.1)
    assert g["verschil_per_maand_eur"] == pytest.approx(60.0 - verwacht / 12, abs=0.05)


def test_maandreeks_twaalf_maanden_cumulatief():
    r = ja.bereken({}, date(2025, 4, 1), date(2026, 11, 5), _inst())
    m = r["maanden"]
    assert [x["maand"] for x in m][:2] == ["apr", "mei"] and len(m) == 12
    assert m[-1]["betaald_cum"] == pytest.approx(840.0)
    assert sum(1 for x in m if x["betaald_echt"]) == 7
    assert sum(1 for x in m if x["kosten_echt"]) == 7


def test_dagen_uit_statistiek_lokale_datum():
    start = datetime(2026, 11, 3, 23, 0, tzinfo=timezone.utc).timestamp()   # 4 nov 00:00 lokaal
    rijen = {"sensor.kosten": [{"start": start, "change": 1.5}, {"start": start, "change": None}]}
    dagen = js.dagen_uit_statistiek(rijen, {"afname_eur": "sensor.kosten"})
    lokaal = js.dt_util.as_local(datetime.fromtimestamp(start, tz=timezone.utc)).date()
    assert dagen == {lokaal: {"afname_eur": 1.5}}


def test_attributen_klein():
    import json

    dagen = _vol(date(2025, 4, 1), date(2026, 11, 4), afname_eur=1.0, terug_eur=0.4, gas_eur=0.6, gas_m3=0.3,
                 afname_kwh=4.0, terug_kwh=2.0)
    inst = _inst(gas_overstap=date(2026, 11, 22), gas_nieuw_prijs_m3=2.0, gas_nieuw_termijn_eur=60.0,
                 saldering_eind=date(2026, 12, 31))
    assert len(json.dumps(ja.bereken(dagen, date(2025, 4, 1), date(2026, 11, 5), inst))) < 6000
