"""v5.93.3: het kwartierplan kent de secundaire prijslaag.

Gemeld 12-10 20:56: "Waarom ontlaadt accu nu? Niet te zien in de planning."
Het plan zette 20:45 (40,3 ct) op smart; de sturing verkocht op 2,4 kW via
de secundaire laag (top 45% van de dagprijsrange, met ruimte boven de
verkoopreserve). Het plan kende alleen de primaire drempel.
"""
from datetime import datetime, timedelta, timezone

DAG = datetime(2026, 8, 3, tzinfo=timezone.utc)


def _reeks():
    """Zelfde vorm als test_secondary_tier: dal 0,15, avond 0,36, piek 0,4177."""
    prijzen = {}
    for uur in range(9, 12):
        for m in (0, 15, 30, 45):
            prijzen[(uur, m)] = 0.15
    for uur in range(18, 21):
        for m in (0, 15, 30, 45):
            prijzen[(uur, m)] = 0.36
    prijzen[(19, 45)] = 0.4177
    uit = []
    for uur in range(24):
        for m in (0, 15, 30, 45):
            start = DAG.replace(hour=uur, minute=m)
            uit.append((start, start + timedelta(minutes=15), prijzen.get((uur, m), 0.25) * 1_000_000))
    return uit


def _coordinator(make_coordinator, reserve=2.0):
    c = make_coordinator({"manual_discharge_power": 1600})
    c._planning_verkoopreserve_kwh = lambda moment, cache, entries, prijs: reserve
    return c


def _regels(zonarm=False):
    return {"zonarm": {DAG.date(): zonarm}}


def _ruimte(c, start, duur_kwartier, soc, regels=None):
    return c._plan_verkoopruimte(
        _reeks(), start, 0.36, duur_kwartier, soc, 0.4, {}, regels or _regels(), 1600
    )


def test_secundaire_laag_verkoopt_in_het_plan_met_ruimte(make_coordinator):
    c = _coordinator(make_coordinator)
    assert _ruimte(c, DAG.replace(hour=18, minute=15), False, soc=4.83) == 4.83 - 2.0


def test_secundaire_laag_niet_als_de_piek_de_ruimte_nodig_heeft(make_coordinator):
    c = _coordinator(make_coordinator)
    assert _ruimte(c, DAG.replace(hour=18, minute=15), False, soc=2.4) is None


def test_niet_onder_de_verkoopreserve(make_coordinator):
    c = _coordinator(make_coordinator, reserve=5.0)
    assert _ruimte(c, DAG.replace(hour=18, minute=15), False, soc=4.83) is None


def test_niet_op_een_zonarme_dag(make_coordinator):
    c = _coordinator(make_coordinator)
    assert _ruimte(c, DAG.replace(hour=18, minute=15), False, soc=8.0, regels=_regels(True)) is None


def test_niet_onder_de_secundaire_drempel(make_coordinator):
    c = _coordinator(make_coordinator)
    assert _ruimte(c, DAG.replace(hour=9, minute=0), False, soc=10.0) is None


def test_primaire_laag_zoals_voorheen(make_coordinator):
    c = _coordinator(make_coordinator)
    piek = DAG.replace(hour=19, minute=45)
    assert _ruimte(c, piek, True, soc=4.0) == 2.0
    # te weinig in de accu voor een half kwartier: niet verkopen
    assert _ruimte(c, piek, True, soc=0.1) is None


def test_plan_en_beslissing_gebruiken_dezelfde_secundaire_toets():
    from pathlib import Path

    bron = (Path(__file__).resolve().parents[1] / "custom_components" / "energy_management_system"
            / "coordinator.py").read_text(encoding="utf-8")
    assert "if self._is_worth_discharging_at_secondary_tier(entries, start, ruimte, ontlaad_w):" in bron
    assert "if (ruimte := self._plan_verkoopruimte(" in bron
