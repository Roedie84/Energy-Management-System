"""REASON_DEVIATION_ANALYSIS: welke reden wijkt af van het optimum? (v4.22)

De vraag "welke reden levert geld op?" bleek niet te beantwoorden. Ik
heb hem uitgevoerd en kreeg efficiënties van -137% en +272%. Dat is
geen rekenfout: de waarde van een optimale planning zit in de REEKS,
niet in het kwartier. Een kwartier waarin het optimum laadt, kost daar
geld en levert het later op; per kwartier toerekenen breekt dat.

Wat wel valide is, is de kWh-AFWIJKING: hoeveel wilde het optimum dit
kwartier anders doen dan wij deden. Dat is fysiek en lokaal - geen
reekswaarde nodig.

Gemeten over acht dagen:

    reden                            kwart  te weinig  te veel  mediaan
    default_smart                      559    29,89     27,75    -0,048
    discharging_window                  97     2,06      7,23    -0,067
    expensive_quarter                   17     0,46      4,91    -0,408
    expensive_quarter_soc_protected     23     2,04      1,62    -0,060
    arbitrage_solar_capture             43     2,18      1,37    +0,004
    solar_capture_deferred              27     0,00      1,68    -0,056

`expensive_quarter` springt eruit: mediaan -0,408 kWh, en 4,91 kWh dat
het optimum méér wilde vasthouden tegen 0,46 dat het meer wilde
ontladen. Steeds dezelfde richting.

Deze diagnostiek stuurt niets. Ze maakt zichtbaar welke redenen
structureel van het optimum afwijken, in de enige eenheid waarin dat
consistent te meten is.
"""
import pytest


def _dag(c, datum, regels):
    """regels: (reden, accu_kwh_werkelijk, accu_kwh_optimum)"""
    c.reden_afwijkingen = {}
    for reden, werkelijk, optimum in regels:
        c.noteer_reden_afwijking(datum, reden, werkelijk, optimum)


def test_de_afwijking_wordt_per_reden_geteld(make_coordinator, hass):
    c = make_coordinator({})
    _dag(c, "2026-09-18", [
        ("expensive_quarter", 0.5, 0.1),     # optimum wilde 0,4 minder ontladen
        ("expensive_quarter", 0.4, 0.1),     # 0,3 minder
        ("arbitrage_solar_capture", -0.3, -0.3),
    ])

    o = c.get_reden_afwijkingen()
    eq = next(r for r in o["redenen"] if r["reden"] == "expensive_quarter")

    assert eq["kwartieren"] == 2
    assert eq["te_veel_ontladen_kwh"] == pytest.approx(0.7, abs=0.01)
    assert eq["te_weinig_ontladen_kwh"] == 0.0
    assert eq["mediaan_kwh"] == pytest.approx(-0.35, abs=0.01)


def test_beide_richtingen_apart(make_coordinator, hass):
    c = make_coordinator({})
    _dag(c, "2026-09-18", [
        ("default_smart", 0.2, 0.5),   # optimum wilde 0,3 MEER ontladen
        ("default_smart", 0.5, 0.2),   # en hier 0,3 minder
    ])

    r = c.get_reden_afwijkingen()["redenen"][0]

    assert r["te_weinig_ontladen_kwh"] == pytest.approx(0.3, abs=0.01)
    assert r["te_veel_ontladen_kwh"] == pytest.approx(0.3, abs=0.01)


def test_de_rangorde_gaat_op_absolute_afwijking(make_coordinator, hass):
    c = make_coordinator({})
    _dag(c, "2026-09-18", [
        ("klein", 0.1, 0.12),
        ("groot", 0.1, 0.9),
        ("midden", 0.1, 0.4),
    ])

    namen = [r["reden"] for r in c.get_reden_afwijkingen()["redenen"]]

    assert namen == ["groot", "midden", "klein"]


def test_de_spreiding_staat_erbij(make_coordinator, hass):
    c = make_coordinator({})
    _dag(c, "2026-09-18", [("a", 0.0, v / 10) for v in range(1, 11)])

    r = c.get_reden_afwijkingen()["redenen"][0]

    assert r["p10_kwh"] < r["mediaan_kwh"] < r["p90_kwh"]


def test_zonder_metingen_geen_oordeel(make_coordinator, hass):
    c = make_coordinator({})
    c.reden_afwijkingen = {}

    o = c.get_reden_afwijkingen()

    assert o["redenen"] == []
    assert "nog geen" in o["oordeel"].lower()


def test_het_oordeel_noemt_de_grootste_afwijker(make_coordinator, hass):
    c = make_coordinator({})
    _dag(c, "2026-09-18", [
        ("expensive_quarter", 0.5, 0.1),
        ("expensive_quarter", 0.5, 0.1),
        ("expensive_quarter", 0.5, 0.1),
        ("default_smart", 0.2, 0.21),
    ])

    o = c.get_reden_afwijkingen()

    assert "expensive_quarter" in o["oordeel"]
    assert "vasthouden" in o["oordeel"] or "minder ontladen" in o["oordeel"]


def test_de_eenheid_staat_in_de_toelichting(make_coordinator, hass):
    """Waarom kWh en geen euro's - dat hoort erbij te staan, anders
    vraagt iemand over een maand opnieuw om euro-efficiëntie."""
    c = make_coordinator({})
    _dag(c, "2026-09-18", [("a", 0.1, 0.2)])

    o = c.get_reden_afwijkingen()

    assert "kWh" in o["toelichting"]
    assert "reeks" in o["toelichting"] or "kwartier" in o["toelichting"]
