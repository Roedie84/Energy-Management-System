"""v5.223.0: de proefstand is vervallen, elke stap van de ronde heeft een klok.

Ruud 11-11 17:10 ("Resterende punten eerst oppakken"): rest van punt 10,
punt 6, 12 en 13 van het onderzoek van 11-11.
"""

import inspect
import time
from types import SimpleNamespace

import pytest

from custom_components.energy_management_system import const, diagnostics, sensor as S, switch as SW
from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)


# --- rest van punt 10: de proefstand ---------------------------------------


@pytest.mark.parametrize("methode", [
    "get_proefstand", "get_meet_stuurt_niet", "_update_proefstand", "_meld_rijpe_kandidaten",
    "_herinner_wat_meet", "_kandidaat_slijtage", "_kandidaat_netarbitrage", "_proefstand_balans",
])
def test_de_methode_bestaat_niet_meer(methode):
    assert not hasattr(C, methode)


def test_wat_anderen_gebruikten_blijft():
    assert hasattr(C, "_opbrengst_accu_per_jaar_eur")   # uitbreidingsadvies
    assert hasattr(C, "_update_capaciteitstrend")       # accugezondheid
    assert "capacity_trend_history" in const.PERSISTED_FIELDS


def test_de_capaciteitstrend_loopt_door_in_de_ronde():
    bron = inspect.getsource(C._finish_decision_tick)
    assert "_update_capaciteitstrend(now)" in bron and "_update_proefstand" not in bron


def test_capaciteitstrend_een_meting_per_dag():
    from datetime import datetime, timezone

    c = SimpleNamespace(
        _capacity_trend_day_key=None, capacity_trend_history=[], battery_cumulative_discharged_kwh=812.34,
        config={}, _read_sensor_float=lambda *_a, **_k: 8.64, schedule_persisted_state_save=lambda: None,
    )
    nu = datetime(2026, 11, 11, 17, 0, tzinfo=timezone.utc)
    C._update_capaciteitstrend(c, nu)
    C._update_capaciteitstrend(c, nu)
    assert c.capacity_trend_history == [{"datum": "2026-11-11", "capaciteit_kwh": 8.64, "doorzet_kwh": 812.3}]


def test_meldingen_en_schakelaars_zijn_weg():
    soorten = {k for k, *_ in const.NOTIFICATION_TYPES}
    assert not soorten & {"proefstand_rijp", "meet_stuurt_niet"}
    assert "proefstand_rijp" not in const.LOG_PRIORITEITEN and "meet_stuurt_niet" not in const.LOG_PRIORITEITEN
    assert set(SW.VERVALLEN_MELDINGSSCHAKELAARS) == {"proefstand_rijp", "meet_stuurt_niet"}
    assert "proefstand" in S.VERVALLEN_SENSOREN
    assert "proefstand" not in {p[0] for p in S.DASHBOARD_PAGINA_SENSOREN}


def test_geen_restanten_in_opslag_en_diagnose():
    for veld in ("proefstand_ledger", "_proefstand_doorzet_bij_dagstart", "price_shape_history", "_price_shape_day_key"):
        assert veld not in const.PERSISTED_FIELDS
    bron = inspect.getsource(diagnostics)
    assert "get_proefstand" not in bron and "get_meet_stuurt_niet" not in bron


def test_nog_niet_bepaald_noemt_geen_kandidaten_meer():
    assert "Proefstand" not in inspect.getsource(C.get_pending_overview).replace("proefstand is vervallen", "")


# --- punt 13: elke stap geklokt -------------------------------------------


def _c():
    return SimpleNamespace(_tick_part_timings={}, internal_failures={})


def test_een_stap_krijgt_een_tijd():
    c = _c()
    c._noteer_staartfout = lambda naam: C._noteer_staartfout(c, naam)
    c._wis_staartfout = lambda naam: C._wis_staartfout(c, naam)
    c._noteer_stapduur = lambda naam, begonnen: C._noteer_stapduur(c, naam, begonnen)
    C._voer_staartstap_uit(c, "nilm-apparaten", lambda: time.sleep(0.002))
    assert c._tick_part_timings["nilm-apparaten"][0] >= 1.5


def test_ook_een_omvallende_stap_wordt_geklokt():
    c = _c()
    gemeld = []
    c._noteer_staartfout = gemeld.append
    c._wis_staartfout = lambda naam: None
    c._noteer_stapduur = lambda naam, begonnen: C._noteer_stapduur(c, naam, begonnen)

    def kapot():
        raise RuntimeError("stuk")

    C._voer_staartstap_uit(c, "water", kapot)
    assert gemeld == ["water"] and len(c._tick_part_timings["water"]) == 1


def test_het_overzicht_noemt_de_zwaarste_onderdelen():
    bron = inspect.getsource(C.get_tick_performance)
    assert '"zwaarste_ms"' in bron and '"zonder_klok_ms"' in bron


# --- punt 6: plantoetsing --------------------------------------------------


def test_plantoetsing_toont_alleen_de_gemeten_besparing():
    uit = S._plantoetsing_voor_het_dashboard({"dagen_overzicht": [{
        "datum": "2026-11-10", "oordeel": "x",
        "opbrengst": {"voorspeld_eur": -0.76, "werkelijk_eur": 3.86, "vergelijkbaar": False},
    }]})
    dag = uit["dagen_overzicht"][0]
    assert dag["besparing_werkelijk_eur"] == 3.86 and "opbrengst" not in dag
