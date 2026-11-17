"""v5.238.0: het termijnbedrag wijzigt in de loop van het contractjaar.

Ruud 17-11: "Heb mijn maandbedrag vanaf nu bijgesteld naar 90 euro". Contract
vanaf 01-04, afschrijving rond de 25e: april t/m oktober 7 x 70 betaald, vanaf
25-11 5 x 90.
"""
from datetime import date
from pathlib import Path

from custom_components.energy_management_system import jaarafrekening as ja

START = date(2026, 4, 1)
BASIS = Path(__file__).parent.parent / "custom_components" / "energy_management_system"


def _inst(**kw):
    return ja.Instellingen(termijn_eur=90.0, termijn_vorig_eur=70.0, termijn_gewijzigd=date(2026, 11, 17), **kw)


def test_betaald_telt_de_oude_termijnen_met_het_oude_bedrag():
    uit = ja.bereken({}, START, date(2026, 11, 17), _inst())
    assert uit["termijnen_betaald"] == 7
    assert uit["betaald_eur"] == 490.0
    assert uit["betaald_delen"] == [[7, 70.0]]
    assert uit["termijn_eur"] == 90.0 and uit["termijn_vorig_eur"] == 70.0
    assert uit["termijn_gewijzigd"] == "2026-11-17"


def test_na_de_eerste_nieuwe_afschrijving():
    uit = ja.bereken({}, START, date(2026, 11, 26), _inst())
    assert uit["betaald_eur"] == 580.0
    assert uit["betaald_delen"] == [[7, 70.0], [1, 90.0]]


def test_saldo_rekent_met_wat_er_het_hele_jaar_betaald_wordt():
    nieuw = ja.bereken({}, START, date(2026, 11, 17), _inst())
    oud = ja.bereken({}, START, date(2026, 11, 17), ja.Instellingen(termijn_eur=70.0))
    # 7 x 70 + 5 x 90 = 940 tegen 12 x 70 = 840
    assert round(nieuw["verwacht_saldo_eur"] - oud["verwacht_saldo_eur"], 2) == 100.0
    assert nieuw["verwacht_kosten_eur"] == oud["verwacht_kosten_eur"]
    assert nieuw["maanden"][6]["betaald_cum"] == 490.0
    assert nieuw["maanden"][7]["betaald_cum"] == 580.0
    assert nieuw["maanden"][-1]["betaald_cum"] == 940.0


def test_advies_rekent_met_het_echt_betaalde_bedrag():
    nieuw = ja.bereken({}, START, date(2026, 11, 17), _inst())["advies"]
    fout = ja.bereken({}, START, date(2026, 11, 17), ja.Instellingen(termijn_eur=90.0))["advies"]
    assert nieuw["resterende_termijnen"] == 5
    # zonder de wijziging zou er 7 x 90 betaald lijken: 140 te veel, 28 per termijn
    assert round(nieuw["nodig_per_termijn_eur"] - fout["nodig_per_termijn_eur"], 2) == 28.0


def test_zonder_wijziging_blijft_alles_gelijk():
    uit = ja.bereken({}, START, date(2026, 11, 17), ja.Instellingen(termijn_eur=70.0))
    assert uit["betaald_eur"] == 490.0 and uit["betaald_delen"] == [[7, 70.0]]
    assert uit["termijn_vorig_eur"] is None and uit["termijn_gewijzigd"] is None
    half = ja.Instellingen(termijn_eur=90.0, termijn_vorig_eur=70.0)  # geen datum: geldt niet
    assert ja.bereken({}, START, date(2026, 11, 17), half)["betaald_eur"] == 630.0


def test_volgend_contractjaar_geldt_alleen_het_nieuwe_bedrag():
    uit = ja.bereken({}, START, date(2027, 6, 1), _inst())
    assert uit["betaald_delen"] == [[2, 90.0]]


def test_instelling_formulier_en_kaart():
    flow = (BASIS / "config_flow.py").read_text()
    assert "CONF_JAAR_TERMIJN_VORIG_EUR, 0, 1000, 1" in flow
    assert 'errors[CONF_JAAR_TERMIJN_GEWIJZIGD] = "invalid_date"' in flow
    for naam in ("strings.json", "translations/nl.json", "translations/en.json"):
        tekst = (BASIS / naam).read_text()
        assert tekst.count('"jaar_termijn_vorig_eur"') == 2 and tekst.count('"jaar_termijn_gewijzigd"') == 2
    js = (BASIS / "www" / "ems-cockpit.js").read_text()
    assert "a.betaald_delen.map" in js
    assert "termijn_vorig_eur=_getal(c.get(CONF_JAAR_TERMIJN_VORIG_EUR), None) or None" in (
        BASIS / "jaarafrekening_sturing.py").read_text()
