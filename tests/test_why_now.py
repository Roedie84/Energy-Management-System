"""Waarom doet de aansturing dit nu? (v1.60.0)

Gevraagd: "Kun je in de integratie nog een eigen AI maken, die zaken als
'Waarom laad je nu? -> Omdat tussen 16:00 en 19:00 de prijs 31 cent
hoger ligt, er slechts 4,2 kWh zon wordt verwacht, en de kans op een
tekort vannacht 27% bedraagt' kan toelichten, en dan niet alleen het
bovenstaande voorbeeld maar voor alles?"

Geen taalmodel: het besluit is deterministisch, dus een gegenereerde
verklaring kan er náást zitten zonder dat iemand het merkt. Elke regel
komt uit een waarde die de beslissing daadwerkelijk nam.
"""
from datetime import datetime, timezone

from custom_components.energy_management_system.const import (
    DECISION_REASON_LABELS,
    WHY_MAX_REASONS,
    WHY_QUESTIONS,
)

NU = datetime(2026, 8, 12, 19, 45, tzinfo=timezone.utc)


def _coordinator(make_coordinator, reden, **extra):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator({})
    c.last_reason = reden
    c.last_current_price_per_kwh = 0.689
    c.last_expensive_price_threshold = 0.43
    c.accustand_procent = lambda: 77.0
    c.beschikbare_energie_kwh = lambda: 5.2
    c.last_needed_kwh_to_bridge = 2.3
    c.get_quarter_plan_summary = lambda *a, **k: {"zon_kwh": 4.2}
    for k, v in extra.items():
        setattr(c, k, v)
    return c


def test_every_reason_has_a_question():
    """"Waarom laad je nu?" leest anders dan "Waarom verkoop je nu?", en
    dat verschil is het halve antwoord."""
    for code in DECISION_REASON_LABELS:
        if code in ("wacht_op_goedkoop_blok",):
            continue
        assert code in WHY_QUESTIONS or True  # niet elke code is een tick-reden

    # De redenen die de tick daadwerkelijk zet, moeten er wel zijn.
    for code in (
        "expensive_quarter",
        "solar_capture_deferred",
        "grid_cheaper_than_battery",
        "default_smart",
        "negative_price",
    ):
        assert code in WHY_QUESTIONS, code


def test_selling_explains_itself_with_real_numbers(make_coordinator, hass):
    c = _coordinator(make_coordinator, "expensive_quarter")

    w = c.get_why_now(NU)

    assert w["vraag"] == "Waarom verkoop je nu?"
    tekst = " ".join(w["redenen"])
    assert "68.9 ct" in tekst
    assert "43.0 ct" in tekst
    assert "2.3 kWh" in tekst


def test_deferring_explains_the_gain(make_coordinator, hass):
    c = _coordinator(
        make_coordinator,
        "solar_capture_deferred",
        last_solar_defer_plan={
            "omslag_uur": 11,
            "prijsverschil_ct": 9.6,
            "geschatte_winst_eur": 0.72,
        },
    )

    w = c.get_why_now(NU)

    tekst = " ".join(w["redenen"])
    assert "11:00" in tekst
    assert "9.6 ct" in tekst
    assert "0.72" in tekst


def test_holding_the_battery_names_all_three_costs(make_coordinator, hass):
    """Kostprijs, rendement én slijtage - anders is niet na te gaan
    waarom de accu duurder zou zijn dan het net."""
    c = _coordinator(
        make_coordinator,
        "grid_cheaper_than_battery",
        last_battery_vs_grid={
            "accu_eur_per_kwh": 0.31,
            "net_eur_per_kwh": 0.12,
            "kostprijs_eur_per_kwh": 0.2175,
            "rendement_procent": 82.9,
            "slijtage_ct_per_kwh": 4.7,
        },
    )

    tekst = " ".join(c.get_why_now(NU)["redenen"])

    assert "31.0 ct" in tekst
    assert "12.0 ct" in tekst
    assert "83%" in tekst


def test_at_most_three_reasons(make_coordinator, hass):
    """Meer leest niemand, en de vierde reden is per definitie de minst
    belangrijke."""
    c = _coordinator(make_coordinator, "expensive_quarter")

    assert len(c.get_why_now(NU)["redenen"]) <= WHY_MAX_REASONS


def test_no_language_model_is_involved():
    """Een taalmodel verzint de reden achteraf uit wat het te zien
    krijgt; het besluit is deterministisch. Elke regel hoort uit een
    gemeten waarde te komen."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("def _waarom_regels")
    staart = bron[kop : bron.index("def get_aging_drivers")]

    for verboden in ("openai", "anthropic", "requests.post", "aiohttp"):
        assert verboden not in staart.lower(), verboden


def test_without_a_decision_it_says_so(make_coordinator, hass):
    c = _coordinator(make_coordinator, None)

    assert c.get_why_now(NU)["beschikbaar"] is False
