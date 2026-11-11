"""Vooruitplannen met de nachtreserve, nu en na de saldering (v5.90).

Gevraagd (12-10): "Opbrengst na de saldering als eerste klaarmaken" en
"Vooruitplannen over 24 uur eerst laten rekenen met de nachtreserve, zodat
we zien wat het echt oplevert."

De oude vergelijking legde greedy arbitragewinst naast de NETTO uitkomst van
het plan (inclusief alle stroom die het huis van het net haalt): +2,50 euro
per dag tegen 0,56 als theoretisch maximum. Nu rekenen plan en optimum met
dezelfde kwartieren, dezelfde natuurkunde en dezelfde waardering.
"""
from datetime import datetime, timezone

import pytest

from custom_components.energy_management_system import vooruitplan

NU = datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc)
INST = dict(rendement=0.85, slijtage_eur=0.04, eindwaarde_eur=0.0)


def _kw(prijs, verbruik=0.1, zon=0.0, export=None, reserve=0.0):
    return {
        "verbruik_kwh": verbruik,
        "zon_kwh": zon,
        "import_eur": prijs,
        "export_eur": prijs if export is None else export,
        "reserve_kwh": reserve,
    }


def test_niets_doen_kost_precies_de_netstroom():
    kw = [_kw(0.30), _kw(0.40)]

    uit = vooruitplan.waardeer(kw, 2.0, [2.0, 2.0], **INST)

    assert uit["netto_eur"] == pytest.approx(-(0.1 * 0.30 + 0.1 * 0.40))


def test_goedkoop_laden_en_duur_verkopen_als_het_loont():
    kw = [_kw(0.10)] * 4 + [_kw(0.50)] * 4

    beste = vooruitplan.optimaliseer(kw, 0.0, 4.0, laad_kwh=0.5, ontlaad_kwh=0.5, **INST)
    plan = vooruitplan.waardeer(kw, 0.0, [0.0] * 8, **INST)

    assert beste["standen_kwh"][3] > 1.0
    assert beste["netto_eur"] > plan["netto_eur"]


def test_geen_arbitrage_als_de_marge_het_rendement_niet_dekt():
    kw = [_kw(0.30)] * 4 + [_kw(0.33)] * 4

    beste = vooruitplan.optimaliseer(kw, 0.0, 4.0, laad_kwh=0.5, ontlaad_kwh=0.5, **INST)

    assert max(beste["standen_kwh"]) == pytest.approx(0.0)


def test_onder_de_nachtreserve_wordt_niet_verkocht():
    """Dure kwartieren, volle accu: verkopen mag tot de reserve, niet verder."""
    kw = [_kw(0.60, verbruik=0.0, reserve=2.0)] * 8 + [_kw(0.30, reserve=2.0)] * 4

    beste = vooruitplan.optimaliseer(kw, 4.0, 4.0, laad_kwh=0.5, ontlaad_kwh=0.5, **INST)

    assert min(beste["standen_kwh"][:8]) >= 2.0 - 1e-6


def test_het_huis_bedienen_mag_onder_de_reserve():
    """De reserve is er juist voor het huis."""
    kw = [_kw(0.50, verbruik=0.4, reserve=3.0)] * 6

    beste = vooruitplan.optimaliseer(kw, 2.0, 4.0, laad_kwh=0.5, ontlaad_kwh=0.5, **INST)

    assert beste["standen_kwh"][-1] < 2.0


def test_na_de_saldering_zon_bewaren_voor_de_avond():
    """Middagzon tegen het kale tarief verkopen of bewaren voor een dure
    avond: na de saldering wint bewaren - onder saldering is het om het even."""
    middag = [_kw(0.25, verbruik=0.1, zon=0.6, export=0.25 - 0.111 + 0.02)] * 4
    avond = [_kw(0.45, verbruik=0.4, export=0.45 - 0.111 + 0.02)] * 6
    kw = middag + avond
    # het plan: de zon gaat het net op, de accu blijft leeg
    plan_standen = [0.0] * 10

    uit = vooruitplan.vergelijk(
        kw, 0.0, plan_standen, 4.0, laad_kwh=0.5, ontlaad_kwh=0.5, **INST
    )

    assert uit["verschil_eur"] > 0.3
    assert uit["kwartieren_anders"] >= 4
    assert uit["voordeel_ct_per_kwh"] > 2


def test_een_optimaal_plan_levert_geen_verschil():
    """Vlakke prijs, en wat er overblijft is evenveel waard als nu
    gebruiken: dan valt er niets te winnen."""
    kw = [_kw(0.30)] * 8

    uit = vooruitplan.vergelijk(
        kw, 1.0, [1.0 - 0.1 * (i + 1) for i in range(8)], 4.0,
        laad_kwh=0.5, ontlaad_kwh=0.5, rendement=0.85, slijtage_eur=0.04, eindwaarde_eur=0.26,
    )

    assert abs(uit["verschil_eur"]) < 0.02
