"""Vooruitplannen met de nachtreserve, nu en na de saldering (v5.90).

Gevraagd (12-10): "Opbrengst na de saldering als eerste klaarmaken" en
"Vooruitplannen over 24 uur eerst laten rekenen met de nachtreserve, zodat
we zien wat het echt oplevert."

De oude vergelijking legde greedy arbitragewinst naast de NETTO uitkomst van
het plan (inclusief alle stroom die het huis van het net haalt): +2,50 euro
per dag tegen 0,56 als theoretisch maximum. Nu rekenen plan en optimum met
dezelfde kwartieren, dezelfde natuurkunde en dezelfde waardering.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import vooruitplan
from custom_components.energy_management_system.const import MPC_MIN_METINGEN

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


# --- in de coordinator -------------------------------------------------


def _invoer():
    kw = [_kw(0.10)] * 4 + [_kw(0.50)] * 4
    return {
        "kwartieren": kw, "start_kwh": 0.0, "plan_standen_kwh": [0.0] * 8,
        "bruikbaar_kwh": 4.0, "laad_kwh": 0.5, "ontlaad_kwh": 0.5, **INST,
    }


def test_een_keer_per_dag_gemeten_ook_na_een_herstart(make_coordinator, hass):
    c = make_coordinator({})
    c._vooruitplan_invoer = lambda now, na: _invoer()

    c._meet_vooruitplan(NU)
    c._meet_vooruitplan(NU + timedelta(hours=3))
    assert len(c.vooruitplan_history) == 1
    assert {"nu", "na_saldering"} <= set(c.vooruitplan_history[0])

    c._meet_vooruitplan(NU + timedelta(days=1))
    assert len(c.vooruitplan_history) == 2


def test_zonder_invoer_geen_meting(make_coordinator, hass):
    c = make_coordinator({})
    c._vooruitplan_invoer = lambda now, na: None

    c._meet_vooruitplan(NU)

    assert c.vooruitplan_history == []


def test_de_invoer_volgt_het_plan_en_de_nieuwe_waardering(make_coordinator, hass):
    c = make_coordinator({})
    start = NU.replace(minute=0)
    c.get_quarter_plan = lambda now=None: [
        {"start": (start + timedelta(minutes=15 * i)).isoformat(), "prijs_ct": 30.0,
         "zon_kwh": 0.0, "verbruik_kwh": 0.1, "soc_kwh": 2.0}
        for i in range(4)
    ]
    c._read_sensor_float = lambda entity: 8.64
    c.effective_min_soc_percent = lambda: 10
    c.beschikbare_energie_kwh = lambda: 3.0
    c.get_wear_cost_overview = lambda: {"beschikbaar": True, "slijtage_ct_per_kwh": 4.2}
    c._gemeten_belastingdeel_eur_per_kwh = lambda: 0.111
    c._get_forecast_entries = lambda **kw: []
    c._planning_reserve_kwh = lambda moment, cache, entries: 1.5

    nu = c._vooruitplan_invoer(NU, False)
    na = c._vooruitplan_invoer(NU, True)

    assert nu["kwartieren"][0]["export_eur"] == pytest.approx(0.32)
    assert na["kwartieren"][0]["export_eur"] < nu["kwartieren"][0]["export_eur"] - 0.1
    assert na["kwartieren"][0]["reserve_kwh"] == 1.5
    assert nu["start_kwh"] == 3.0
    assert vooruitplan.vergelijk(**na)["beschikbaar"] is True


def test_de_saldering_kandidaat_wordt_becijferd(make_coordinator, hass):
    c = make_coordinator({})
    c.get_quarter_plan = lambda *a, **k: [
        {"net_kwh": -0.5, "prijs_ct": 30.0, "cumulatief_eur": 1.0, "zon_kwh": 0.6, "verbruik_kwh": 0.1}
    ]
    c._gemeten_belastingdeel_eur_per_kwh = lambda: 0.111
    meting = {"verschil_eur": 0.42, "verschoven_kwh": 3.0, "kwartieren_anders": 20}
    c.vooruitplan_history = [{"dag": str(i), "nu": meting, "na_saldering": meting} for i in range(MPC_MIN_METINGEN)]

    k = c._kandidaat_na_saldering()

    assert k["status"] == "betrouwbaar"
    assert k["zou_hebben_opgeleverd"]["te_becijferen"] is True
    assert k["zou_hebben_opgeleverd"]["bedrag_per_dag_eur"] == pytest.approx(0.42)
    assert k["zou_hebben_opgeleverd"]["mediaan_voordeel_ct_per_kwh"] == pytest.approx(14.0)


def test_de_saldering_kandidaat_meldt_hoe_ver_hij_is(make_coordinator, hass):
    c = make_coordinator({})
    c.get_quarter_plan = lambda *a, **k: [
        {"net_kwh": -0.5, "prijs_ct": 30.0, "cumulatief_eur": 1.0, "zon_kwh": 0.6, "verbruik_kwh": 0.1}
    ]
    c._gemeten_belastingdeel_eur_per_kwh = lambda: 0.111

    reden = c._kandidaat_na_saldering()["zou_hebben_opgeleverd"]["reden"]

    assert f"0 van {MPC_MIN_METINGEN} dagen" in reden


def test_de_meting_stuurt_niets():
    import ast
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    for fn in (C._meet_vooruitplan, C._vooruitplan_invoer):
        boom = ast.parse(inspect.getsource(fn).lstrip())
        aanroepen = {
            n.func.attr for n in ast.walk(boom)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }
        assert not aanroepen & {"_async_apply_operation", "_async_apply_manual", "async_call"}


def test_de_proefstand_draait_ook_na_de_saldering(make_coordinator, hass):
    """Klaar voor 1 januari: de hele proefstand rekent zonder fout als de
    saldering voorbij is."""
    c = make_coordinator({})
    c._is_salderen_active = lambda now: False
    meting = {"verschil_eur": 0.3, "verschoven_kwh": 2.0, "kwartieren_anders": 15}
    c.vooruitplan_history = [{"dag": str(i), "nu": meting, "na_saldering": meting} for i in range(20)]

    namen = {k["naam"]: k for k in c.get_proefstand()["kandidaten"]}

    assert namen["Vooruitplannen over 24 uur"]["status"] == "betrouwbaar"
