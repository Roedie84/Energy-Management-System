"""v5.134.0: de aanzettemperatuur uit de keren dat jullie de airco aanzetten.

26-10: "Leert nog: het EMS heeft nog niet gezien bij welke temperatuur jullie
de airco op verwarmen zetten", terwijl het dagritme 10x aan telde. De kans per
halve graad kwam nooit boven 50% (5-15%).
"""
from custom_components.energy_management_system import airco_sturing as a


def _b(kans, n, richting="verwarmen"):
    return {"probability_percent": kans, "sample_count": n, "richting": richting,
            "voldoende_data": n >= 5}


# De echte leercurve van 26-10 (sensor Airco-verwachting, geleerde_buckets)
LIVE = {
    "16.0": _b(0, 3, None), "16.5": _b(15, 20), "17.0": _b(5, 20), "17.5": _b(5, 20),
    "18.0": _b(10, 20), "18.5": _b(5, 20), "19.0": _b(5, 20), "19.5": _b(10, 20),
    "20.0": _b(0, 20, None), "20.5": _b(9.1, 11), "21.0": _b(0, 8, None),
    "21.5": _b(0, 2, None),
}


def test_live_26_10_geeft_19():
    assert a.aanzettemperatuur(LIVE) == 19.0


def test_een_bakje_boven_de_helft_gaat_voor():
    bakjes = dict(LIVE, **{"18.0": _b(60, 20)})
    assert a.aanzettemperatuur(bakjes) == 18.0


def test_te_weinig_keer_dan_nog_niets():
    assert a.aanzettemperatuur({"18.0": _b(10, 20), "19.0": _b(5, 20)}) is None  # 3 keer


def test_koelen_telt_niet():
    bakjes = {"26.0": _b(25, 20, "koelen"), "18.0": _b(10, 20)}
    assert a.aanzettemperatuur(bakjes) is None


def test_drie_van_de_vier():
    bakjes = {"17.0": _b(15, 20), "18.0": _b(15, 20), "19.0": _b(5, 20), "20.0": _b(5, 20)}
    # 3x17, 3x18, 1x19, 1x20 -> 8 keer, 6e = 18,0
    assert a.aanzettemperatuur(bakjes) == 18.0
