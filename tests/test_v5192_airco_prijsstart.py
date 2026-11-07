"""v5.192.0 (L-EMS-074): het opwarmmoment van de airco op prijs.

Gevraagd 07-11: houdt de airco-sturing rekening met prijzen? Het opwarmen
begon altijd net op tijd voor het geleerde moment. Nu kiest het binnen twee
uur ervoor het goedkoopste begin, met de kosten van het langer vasthouden.
Akkoord Ruud 07-11 11:08.
"""
import pytest

from custom_components.energy_management_system import airco_ritme as A
from tests.test_v5101_airco_dagritme import _ritme_zoals_19_oktober, _t

# 19-10: aan om 16:32, 78 min opwarmen -> basisstart 15:14 (914)
ARG = dict(woonkamer_c=18.5, verwacht_om=lambda m: 18.4, tempo_c_per_uur=2.0,
           aanwezigheid="thuis", advies="airco", airco_stand="off")


def _kost(goedkoop_tot: int, laag=0.41, hoog=0.54):
    return lambda m: laag if m < goedkoop_tot else hoog


def test_zonder_prijzen_zoals_voorheen():
    start, info = A.prijsstart(914, 1.3, None)
    assert start == 914 and info is None
    assert A.prijsstart(914, 1.3, lambda m: None) == (914, None)


def test_vlakke_prijs_niet_eerder():
    assert A.prijsstart(914, 1.3, lambda m: 0.45) == (914, None)


def test_piek_tijdens_het_opwarmen_trekt_het_naar_voren():
    """De piek begint om 16:00, midden in het opwarmen (15:14-16:32)."""
    start, info = A.prijsstart(914, 1.3, _kost(16 * 60, laag=0.10, hoog=0.60), nu_min=12 * 60)
    assert start < 914 and start >= 914 - A.PRIJS_VROEG_MAX_MIN
    assert info["voordeel_eur"] >= A.PRIJS_MIN_VOORDEEL_EUR
    assert info["kosten_eur"] < info["basis_kosten_eur"]


def test_vasthouden_kost_ook_geld():
    """07-11: tot 14:45 ~41 ct, daarna ~54 ct. Een uur eerder opwarmen scheelt
    ~10 ct, maar het langer warm houden in de dure uren kost meer: niet doen."""
    start, info = A.prijsstart(914, 1.3, _kost(14 * 60 + 45), nu_min=12 * 60)
    assert start == 914 and info is None


def test_niet_in_het_verleden():
    start, _ = A.prijsstart(914, 1.3, _kost(16 * 60, laag=0.10, hoog=0.60), nu_min=14 * 60 + 50)
    assert start >= 14 * 60 + 45


def test_besluit_dag_begint_eerder_als_het_goedkoper_is():
    r = _ritme_zoals_19_oktober()
    kost = _kost(16 * 60, laag=0.10, hoog=0.60)
    # 15:00: zonder prijs nog niets (start 15:14), met prijs al verwarmen
    assert A.besluit_dag(r, nu=_t(19, 15, 0), **ARG) is None
    uit = A.besluit_dag(r, nu=_t(19, 15, 0), kost_per_uur=kost, **ARG)
    assert uit is not None and uit["actie"] == "verwarmen"
    assert uit["prijsstart"]["voordeel_eur"] > 0 and "goedkoper" in uit["tekst"]


def test_dagje_uit_niets():
    """Niemand thuis: ook met een goedkoop kwartier gaat de airco niet aan."""
    r = _ritme_zoals_19_oktober()
    weg = dict(ARG, aanwezigheid="weg")
    assert A.besluit_dag(r, nu=_t(19, 14, 30), kost_per_uur=_kost(14 * 60 + 45), **weg) is None
    assert A.besluit_dag(r, nu=_t(19, 16, 0), kost_per_uur=_kost(14 * 60 + 45), **weg) is None


def test_coordinator_levert_kosten_per_uur(make_coordinator):
    c = make_coordinator({})
    c.huidige_prijs_eur_per_kwh = lambda m=None: 0.40
    c._get_live_outdoor_temp_c = lambda now: 5.0
    c._voorspelde_buitentemp_c = lambda a, b: 5.0
    kost = c._airco_kost_per_uur(_t(19, 12, 0), A.leeg())
    assert kost(900) == pytest.approx(0.40 * 1.0)
    c._voorspelde_buitentemp_c = lambda a, b: 0.0    # kouder: lager rendement, duurder
    kost = c._airco_kost_per_uur(_t(19, 12, 0), A.leeg())
    assert kost(900) > 0.40
