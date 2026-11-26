"""v5.256.0: vermoedelijke ontdooibeurten tellen (Ruud 24-11: "Kun je ook
zien wanneer de buitenunit 'bevroren' is?"). Alleen meting, geen sturing."""
from datetime import datetime, timedelta

from custom_components.energy_management_system import airco_ontdooi, airco_ritme

T0 = datetime(2026, 11, 24, 10, 40)


def _speel(metingen, buiten=0.0, doel=21.0, verwarmt=True):
    """metingen: lijst (minuut, hz, unit_c); tussenliggende minuten houden de
    laatste waarde vast, zoals de Daikin die om de twee minuten meldt."""
    model, buffer, nieuw = airco_ontdooi.leeg(), [], []
    stand = {m: (hz, c) for m, hz, c in metingen}
    hz = c = None
    for minuut in range(metingen[0][0], metingen[-1][0] + 1):
        if minuut in stand:
            hz, c = stand[minuut]
        doel_nu = doel(minuut) if callable(doel) else doel
        beurt = airco_ontdooi.ronde(
            model, buffer, T0 + timedelta(minutes=minuut),
            hz=hz, unit_c=c, buiten_c=buiten, doel_c=doel_nu, verwarmt=verwarmt,
        )
        if beurt:
            nieuw.append(beurt)
    return model, nieuw


# 24-11: 11:05 = minuut 25
VANDAAG = [(0, 40, 22), (17, 40, 22), (25, 18, 21), (27, 28, 20), (29, 40, 20), (33, 40, 19),
           (41, 58, 20), (45, 62, 21), (49, 51, 22), (60, 46, 22)]


def test_de_beurt_van_vanochtend_wordt_herkend():
    model, nieuw = _speel(VANDAAG)
    assert len(nieuw) == 1
    beurt = model["beurten"][0]
    assert beurt["begin"].startswith("2026-11-24T11:05")
    assert beurt["unit_voor_c"] == 22 and beurt["hz_laagst"] == 18
    assert beurt["hersteld"] is True and 20 <= beurt["duur_min"] <= 26


def test_geen_beurt_bij_zacht_weer_bediening_of_een_koude_start():
    assert _speel(VANDAAG, buiten=10.0)[1] == []
    assert _speel(VANDAAG, doel=lambda m: 21.0 if m < 24 else 19.0)[1] == []
    assert _speel(VANDAAG, verwarmt=False)[1] == []
    # de compressor stond net stil: dat zakken is de ventilator die aanslaat
    start = [(0, 0, 22), (20, 32, 21), (22, 47, 20), (28, 63, 21), (40, 66, 23)]
    assert _speel(start)[1] == []
    # rustig warm houden
    assert _speel([(0, 30, 22), (30, 28, 22), (60, 26, 21)])[1] == []


def test_het_overzicht_en_de_opslag():
    model, _ = _speel(VANDAAG)
    uit = airco_ontdooi.overzicht(model, T0 + timedelta(hours=2))
    assert uit["vandaag"] == 1 and uit["laatste_7_dagen"] == 1 and uit["zeker"] is False
    assert uit["gemiddelde_duur_min"] is not None
    ritme = airco_ritme.geldig({"ontdooi": model})
    assert ritme["ontdooi"]["beurten"] == model["beurten"]
    assert airco_ritme.geldig({})["ontdooi"] == {"beurten": []}
    assert airco_ontdooi.geldig({"beurten": [1, {"x": 1}]}) == {"beurten": []}


def test_de_coordinator_meet_mee(make_coordinator, hass):
    c = make_coordinator({})
    assert "ontdooien" in c.get_airco_vermogen()
    assert c.get_airco_vermogen()["ontdooien"]["vandaag"] == 0


# --- v5.259.0: strenger (de twee tellingen van 24-11 waren onterecht) -------

def test_alleen_een_daling_bij_de_binnenunit_telt_niet():
    # 24-11 15:38: frequentie 32 -> 28, binnenunit 25 -> 23
    assert _speel([(0, 32, 25), (17, 32, 25), (22, 28, 24), (26, 30, 23), (40, 32, 24)], buiten=2.2)[1] == []
    # 24-11 18:19: 36 -> 27
    assert _speel([(0, 36, 24), (17, 36, 24), (22, 27, 23), (26, 40, 22), (40, 38, 23)], buiten=-0.7)[1] == []
    # en boven de 5 graden buiten niet
    assert _speel(VANDAAG, buiten=6.0)[1] == []
    assert len(_speel(VANDAAG, buiten=4.0)[1]) == 1


# --- v5.266.0/v5.266.1: de plotselinge stop van 26-11 20:22. Eerst als
# ontdooien geteld; Ruud zag daarna geen water onder de buitenunit.

# 19:20 = minuut 0: vol bedrijf, 19:27 in een keer stil, 19:40 weer aan
STILSTAND = [(0, 67, 22), (4, 68, 22), (7, 0, 23), (11, 0, 24), (20, 43, 22), (24, 52, 21), (30, 67, 22)]
# 08:00 = minuut 0: afbouwen en afslaan op de eigen thermostaat
AFSLAAN = [(0, 33, 22), (6, 20, 22), (10, 12, 22), (14, 0, 22), (40, 0, 22)]


def test_in_een_keer_stil_en_weer_aan_is_een_plotselinge_stop_geen_ontdooien():
    model, nieuw = _speel([(-12, 66, 22)] + STILSTAND, buiten=-2.7)
    assert len(nieuw) == 1 and nieuw[0]["soort"] == "stilstand"
    beurt = model["beurten"][0]
    assert beurt["hz_voor"] == 68 and beurt["hersteld"] is True and beurt["duur_min"] == 13
    uit = airco_ontdooi.overzicht(model, T0 + timedelta(hours=1))
    assert uit["vandaag"] == 0 and uit["laatste"] is None and uit["beurten"] == []
    assert uit["plotselinge_stops_vandaag"] == 1 and uit["plotselinge_stops"][0]["duur_min"] == 13


def test_afbouwen_en_afslaan_telt_niet():
    model, nieuw = _speel([(-12, 40, 22)] + AFSLAAN, buiten=-2.7)
    assert nieuw == [] and model["beurten"] == []


def test_blijft_hij_uit_dan_telt_het_nergens():
    reeks = [(-12, 66, 22), (0, 67, 22), (4, 68, 22), (7, 0, 23), (40, 0, 22)]
    model, nieuw = _speel(reeks, buiten=-2.7)
    assert len(nieuw) == 1 and model["beurten"] == []
    # en zolang hij loopt telt hij nog niet mee in het overzicht
    model, _ = _speel(reeks[:4] + [(15, 0, 23)], buiten=-2.7)
    assert len(model["beurten"]) == 1
    uit = airco_ontdooi.overzicht(model, T0 + timedelta(minutes=16))
    assert uit["vandaag"] == 0 and uit["plotselinge_stops_vandaag"] == 0


def test_stilstand_bij_zacht_weer_of_na_bediening_telt_niet():
    assert _speel([(-12, 66, 22)] + STILSTAND, buiten=9.0)[1] == []
    assert _speel([(-12, 66, 22)] + STILSTAND, buiten=-2.7, doel=lambda m: 21.0 if m < 6 else 19.0)[1] == []
