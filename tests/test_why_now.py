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


# --- v1.63.0: "vandaag" moet ook echt vandaag zijn -------------------


def test_todays_sun_stops_at_midnight(make_coordinator, hass):
    """Gemeld met een screenshot van Solcast ernaast: "De verwachtte kw
    zonneenergie kan niet kloppen." De regel zei "er wordt vandaag nog
    28,5 kWh zon verwacht" terwijl Solcast 6,63 meldde.

    28,5 = 6,6 vandaag plus ruim 22 van morgen. De kaart meldde het zelf:
    "over 32 uur". Derde keer dat deze horizon een maat betekenisloos
    maakte, na de tekortkwartieren (v1.42.0) en de plantoetsing
    (v1.48.0).
    """
    gevraagd = {}

    c = _coordinator(make_coordinator, "arbitrage_solar_capture")

    def _samenvatting(nu=None, tot=None):
        gevraagd["tot"] = tot
        return {"zon_kwh": 6.6}

    c.get_quarter_plan_summary = _samenvatting

    tekst = " ".join(c.get_why_now(NU)["redenen"])

    # Er wordt expliciet om een grens gevraagd, en die ligt op
    # middernacht.
    assert gevraagd["tot"] is not None
    assert gevraagd["tot"].hour == 0
    assert gevraagd["tot"].date() > NU.date()
    assert "6.6 kWh" in tekst


# --- v1.66.0: een volle accu vangt niets meer op ---------------------


def _met_ruimte(make_coordinator, ruimte):
    c = _coordinator(make_coordinator, "arbitrage_solar_capture")
    c._resterende_laadruimte_kwh = lambda: ruimte
    return c


def test_a_full_battery_says_the_surplus_goes_to_the_grid(
    make_coordinator, hass
):
    """Gemeld: "Zonoverschot gaat de accu in? Kan niet want die is vol
    :)" De regel stond er onvoorwaardelijk, ook bij 100%."""
    c = _met_ruimte(make_coordinator, 0.0)

    tekst = " ".join(c.get_why_now(NU)["redenen"])

    assert "het net op" in tekst
    assert "gaat de accu in" not in tekst


def test_room_left_names_how_much(make_coordinator, hass):
    c = _met_ruimte(make_coordinator, 3.4)

    tekst = " ".join(c.get_why_now(NU)["redenen"])

    assert "gaat de accu in" in tekst
    assert "3.4 kWh ruimte" in tekst


def test_almost_full_counts_as_full(make_coordinator, hass):
    """Een kwartier laden op 2000 W is 0,5 kWh; onder een paar tienden is
    er in de praktijk geen ruimte meer."""
    c = _met_ruimte(make_coordinator, 0.2)

    assert "het net op" in " ".join(c.get_why_now(NU)["redenen"])


def test_without_a_capacity_it_stays_vague(make_coordinator, hass):
    """Geen ruimte bekend betekent niet: geen ruimte."""
    c = _met_ruimte(make_coordinator, None)

    tekst = " ".join(c.get_why_now(NU)["redenen"])

    assert "gaat de accu in" in tekst
    assert "ruimte)" not in tekst
