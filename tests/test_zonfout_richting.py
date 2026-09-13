""""17% naast" terwijl het 17% TE HOOG is (v3.95.1).

Gemeld met een schermafdruk van de PV/zon-kaart:

    12.8 kWh opgewekt vandaag (voorspeld 13.8). De voorspelling zit er
    over 7 dagen gemiddeld 17% naast.

Dat getal klopt. De zeven afwijkingen zijn:

    -1,9   -13,7   -6,6   -10,2   -41,2   +0,9   -43,9

Gemiddelde absolute fout: 16,9 -> 17%. Maar de gemiddelde afwijking MET
teken is -16,7. Zes van de zeven dagen zaten eronder.

"17% naast" leest als spreiding: soms te hoog, soms te laag, gemiddeld
17 ernaast. De werkelijkheid is een voorspelling die stelselmatig 17% te
hoog is - en dat is precies het mechanisme dat de accu in de nacht van
30 op 31 augustus leeg trok.

`bias_procent` wordt al berekend, met in de code de opmerking "De bias
zegt de RICHTING: structureel te hoog of te laag". Alleen komt hij niet
in de zin terecht.
"""
import pytest

EENZIJDIG = [-1.9, -13.7, -6.6, -10.2, -41.2, 0.9, -43.9]
GESPREID = [-18.0, 17.0, -16.0, 19.0, -17.0, 16.0, -18.0]


def _zin(c, afwijkingen):
    tracker = type("T", (), {"deviation_history": list(afwijkingen)})()
    c.solar_tracker = tracker
    return c.get_topic_summaries()["zon"]["zin"]


def test_een_eenzijdige_fout_krijgt_een_richting(make_coordinator, hass):
    """Het geval van de schermafdruk."""
    c = make_coordinator({})

    zin = _zin(c, EENZIJDIG)

    assert "te hoog" in zin
    assert "17" in zin


def test_een_gespreide_fout_blijft_naast(make_coordinator, hass):
    """Wisselt hij van kant, dan is "naast" het eerlijke woord - een

    richting suggereren die er niet is, is net zo misleidend.
    """
    c = make_coordinator({})

    zin = _zin(c, GESPREID)

    assert "naast" in zin
    assert "te hoog" not in zin
    assert "te laag" not in zin


def test_stelselmatig_te_laag_wordt_ook_benoemd(make_coordinator, hass):
    c = make_coordinator({})

    zin = _zin(c, [x * -1 for x in EENZIJDIG])

    assert "te laag" in zin


def test_de_richting_staat_ook_in_de_kwaliteitskaart(make_coordinator, hass):
    """`bias_procent` bestond al maar werd nergens getoond. Zonder dat

    getal is niet na te kijken waar "te hoog" vandaan komt.
    """
    c = make_coordinator({})
    c.solar_tracker = type("T", (), {"deviation_history": list(EENZIJDIG)})()

    kwaliteit = c.get_pv_forecast_quality()

    assert kwaliteit["bias_procent"] == pytest.approx(-16.7, abs=0.2)
    assert kwaliteit["eenzijdig"] is True


def test_gespreid_heet_niet_eenzijdig(make_coordinator, hass):
    c = make_coordinator({})
    c.solar_tracker = type("T", (), {"deviation_history": list(GESPREID)})()

    assert c.get_pv_forecast_quality()["eenzijdig"] is False
