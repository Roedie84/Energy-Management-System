"""v5.156.1 (L-EMS-051, leerronde 02-11): de nabeschouwing straft een dag
die onder de bodem begint niet meer af.

Gemeten 01-11: laadstand 22 % -> 9 %, de bodem van de meetlat (15 % van de
capaciteit) lag boven de beginstand. `beste_planning` begon stil op de
bodem, de werkelijkheid werd tegen de bodem gewaardeerd: de nabeschouwing
gaf "accu leverde -0,64, gemist 0,64 door de voorspelling" terwijl het
dagarchief -0,04 zag. Een deel daarvan is echt (voorraad 22 -> 9 % leverde
weinig op); het deel (bodem - begin) x dagprijs was een rekenfout. Op een dag
die leeg begint (02-11: 9 %) is dat de hele bodem, ~€ 0,60.
"""
from custom_components.energy_management_system.nabeschouwing import beste_planning
import pytest

from custom_components.energy_management_system.nabeschouwing import Kwartier, nabeschouwing

TIJDEN = [f"{i:02d}:00" for i in range(16)]
ACCU = dict(capaciteit_kwh=2.0, laad_kw=2.0, ontlaad_kw=1.6, rendement=0.84, slijtage_eur_per_kwh=0.0)


def _vlak(prijs=0.45):
    return [Kwartier(huis_kwh=0.1, pv_kwh=0.0, prijs_eur=prijs, accu_kwh=0.0) for _ in range(16)]


def test_niets_doen_onder_de_bodem_mist_niets():
    """Vlakke prijs, accu doet niets, begin = eind onder de bodem: 0 gemist."""
    uit = nabeschouwing(_vlak(), begin_kwh=0.1, eind_kwh=0.1, bodem_kwh=0.3, tijdstippen=TIJDEN, **ACCU)

    assert uit["accu_leverde_op_eur"] == pytest.approx(0.0, abs=0.005)
    assert uit["gemist_eur"] == pytest.approx(0.0, abs=0.005)
    assert uit["gemist_door_voorspelling_eur"] == pytest.approx(0.0, abs=0.005)
    assert uit["bodem_meetlat_kwh"] == 0.3
    assert uit["bodem_gebruikt_kwh"] == 0.1


def test_niets_doen_onder_de_bodem_gelijk_aan_niets_doen_erboven():
    """Hetzelfde gedrag geeft hetzelfde oordeel, waar de beginstand ook ligt."""
    onder = nabeschouwing(_vlak(), begin_kwh=0.1, eind_kwh=0.1, bodem_kwh=0.3, tijdstippen=TIJDEN, **ACCU)
    boven = nabeschouwing(_vlak(), begin_kwh=0.8, eind_kwh=0.8, bodem_kwh=0.3, tijdstippen=TIJDEN, **ACCU)

    # `accu_leverde_op_eur` telt de eindvoorraad boven de bodem mee; het
    # vergelijkbare getal is het gemiste bedrag.
    assert onder["gemist_eur"] == pytest.approx(boven["gemist_eur"], abs=0.02)


def test_boven_de_bodem_verandert_niets():
    """Begint de dag boven de bodem, dan rekent de meetlat zoals altijd."""
    uit = nabeschouwing(_vlak(), begin_kwh=0.8, eind_kwh=0.5, bodem_kwh=0.3, tijdstippen=TIJDEN, **ACCU)

    assert uit["bodem_gebruikt_kwh"] == 0.3
    assert uit["bodem_meetlat_kwh"] == 0.3


def test_leeg_begonnen_dag_zonder_actie_krijgt_geen_bodemstraf():
    """Begin 0, eind 0, bodem 1,5 (zoals 02-11): vroeger ~€ 0,60 'gemist'."""
    kw = [Kwartier(0.3, 0.0, 0.42, 0.0) for _ in range(16)]
    uit = nabeschouwing(
        kw, begin_kwh=0.0, eind_kwh=0.0, bodem_kwh=1.5, tijdstippen=TIJDEN,
        **{**ACCU, "capaciteit_kwh": 10.0},
    )

    assert uit["gemist_eur"] == pytest.approx(0.0, abs=0.005)
    assert uit["accu_leverde_op_eur"] == pytest.approx(0.0, abs=0.005)


def test_beste_planning_zelf_ongewijzigd():
    """De DP is niet aangeraakt: alleen de aanroep uit `nabeschouwing`."""
    kw = _vlak()
    a = beste_planning(kw, begin_kwh=0.8, bodem_kwh=0.3, **{k: v for k, v in ACCU.items() if k != "slijtage_eur_per_kwh"})
    assert a["te_becijferen"] and a["eindstand_kwh"] >= 0.3


def test_best_mogelijk_blijft_een_ondergrens_onder_de_bodem():
    kw = [Kwartier(0.1, 0.0, p, 0.0) for p in [0.30] * 8 + [0.55] * 8]
    uit = nabeschouwing(kw, begin_kwh=0.1, eind_kwh=0.1, bodem_kwh=0.3, tijdstippen=TIJDEN, **ACCU)

    assert uit["kosten_best_mogelijk_eur"] <= uit["kosten_werkelijk_eur"] + 0.001
    assert uit["gemist_eur"] >= 0
