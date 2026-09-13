"""Bijkopen bij een verwacht tekort (v3.11.0).

Gevraagd: "Maar wat als het rendabel is om bij te kopen wanneer er niet
genoeg PV energie is?"

Een andere vraag dan arbitrage. Je koopt niet om te verkopen, je koopt om
niet LATER duurder te moeten kopen.

En daarbij: "let op dat het bijladen vanaf het net in de modus manual
gebeuren moet, net als het ontladen op dure kwartieren, maar dan laden."
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    BIJKOOP_MIN_METINGEN,
    PRICE_SCALE_FACTOR,
)

NU = datetime(2026, 8, 18, 20, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass, prijs_nu=0.20, tekort_ct=40.0):
    c = make_coordinator({})
    c.last_current_price_per_kwh = prijs_nu
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 4.22}
    c.get_quarter_plan_summary = lambda *a, **k: {
        "beschikbaar": True,
        "tekort_kwartieren": 4,
    }
    c.get_quarter_plan = lambda *a, **k: [
        {"tekort": True, "prijs_ct": tekort_ct, "verbruik_kwh": 0.25}
        for _ in range(4)
    ]
    entries = [(NU + timedelta(minutes=15 * i), None, PRICE_SCALE_FACTOR) for i in range(8)]
    return c, entries


def test_a_measurement_is_taken_at_a_shortfall(make_coordinator, hass):
    c, entries = _coordinator(make_coordinator, hass)

    c._meet_bijkopen_bij_tekort(NU, entries)

    assert len(c.bijkoop_history) == 1
    assert c.bijkoop_history[0]["tekort_kwh"] == 1.0


def test_nothing_is_measured_without_a_shortfall(make_coordinator, hass):
    """Zonder verwacht tekort is er niets te vergelijken."""
    c, entries = _coordinator(make_coordinator, hass)
    c.get_quarter_plan_summary = lambda *a, **k: {
        "beschikbaar": True,
        "tekort_kwartieren": 0,
    }

    c._meet_bijkopen_bij_tekort(NU, entries)

    assert c.bijkoop_history == []


def test_cheap_now_and_expensive_later_is_favourable(
    make_coordinator, hass
):
    """20 ct nu bij 90% rendement plus 4,22 ct slijtage is 26,4 ct;
    het tekort kost 40 ct. Dat scheelt."""
    c, entries = _coordinator(make_coordinator, hass, prijs_nu=0.20, tekort_ct=40.0)
    c.charge_efficiency_history = [90.0] * 3
    c.discharge_efficiency_history = [100.0] * 3

    c._meet_bijkopen_bij_tekort(NU, entries)

    assert c.bijkoop_history[0]["voordeel_eur_per_kwh"] > 0


def test_a_small_gap_is_not_favourable(make_coordinator, hass):
    """Bij 84,5% rendement en 4,22 ct slijtage moet er ruim 11 ct
    verschil zijn - de drempel die op 18 augustus niet werd gehaald."""
    c, entries = _coordinator(make_coordinator, hass, prijs_nu=0.31, tekort_ct=35.5)
    c.charge_efficiency_history = [92.0] * 3
    c.discharge_efficiency_history = [92.0] * 3

    c._meet_bijkopen_bij_tekort(NU, entries)

    assert c.bijkoop_history[0]["voordeel_eur_per_kwh"] < 0


def test_efficiency_and_wear_are_charged(make_coordinator, hass):
    """Een kWh in de accu zetten kost rendement en slijtage; zonder die
    twee lijkt bijladen altijd gunstig."""
    c, entries = _coordinator(make_coordinator, hass, prijs_nu=0.30)
    c.charge_efficiency_history = [80.0] * 3
    c.discharge_efficiency_history = [80.0] * 3

    c._meet_bijkopen_bij_tekort(NU, entries)

    assert c.bijkoop_history[0]["laadprijs_nu_eur"] > 0.30


def test_too_few_measurements_says_so(make_coordinator, hass):
    c, _ = _coordinator(make_coordinator, hass)

    assert c._kandidaat_bijkopen()["waarde"] is None


def test_with_enough_measurements_it_reports(make_coordinator, hass):
    c, _ = _coordinator(make_coordinator, hass)
    c.bijkoop_history = [
        {"voordeel_eur_per_kwh": 0.08, "voordeel_totaal_eur": 0.08}
        for _ in range(BIJKOOP_MIN_METINGEN)
    ]

    k = c._kandidaat_bijkopen()

    assert k["zou_hebben_opgeleverd"]["aandeel_gunstig_procent"] == 100.0
    assert k["zou_hebben_opgeleverd"]["gemist_voordeel_eur"] > 0


def test_the_steering_route_is_recorded(make_coordinator, hass):
    """Gevraagd: "let op dat het bijladen vanaf het net in de modus
    manual gebeuren moet, net als het ontladen op dure kwartieren, maar
    dan laden."

    Dat hoort vastgelegd voordat er iets gebouwd wordt - anders is het
    over drie maanden weg.
    """
    c, _ = _coordinator(make_coordinator, hass)
    c.bijkoop_history = [
        {"voordeel_eur_per_kwh": 0.08, "voordeel_totaal_eur": 0.08}
    ] * BIJKOOP_MIN_METINGEN

    uitleg = c._kandidaat_bijkopen()["betrouwbaarheid"]

    assert "manual" in uitleg
    assert "POSITIEF" in uitleg


def test_it_admits_what_it_cannot_see(make_coordinator, hass):
    """Deze meting weet niet of er ruimte in de accu was, en of laden de
    piekbuffer zou verstoren. Dat is precies waarom `smart_charging`
    niet wordt toegepast."""
    c, _ = _coordinator(make_coordinator, hass)
    c.bijkoop_history = [
        {"voordeel_eur_per_kwh": 0.08, "voordeel_totaal_eur": 0.08}
    ] * BIJKOOP_MIN_METINGEN

    uitleg = c._kandidaat_bijkopen()["betrouwbaarheid"]

    assert "ruimte in de accu" in uitleg
    assert "piekbuffer" in uitleg


def test_it_steers_nothing():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("def _meet_bijkopen_bij_tekort")
    blok = bron[kop : bron.index("\n    def ", kop + 10)]
    code = "\n".join(r.split("#")[0] for r in blok.splitlines())

    for verboden in ("async_call", "select_option", "set_value", "OPTION_MANUAL"):
        assert verboden not in code, verboden


# --- v3.24.0: ook meten bij een dreigend tekort ----------------------


def test_a_tight_margin_is_also_measured(make_coordinator, hass):
    """Gevraagd na een dag met 42,9% minder zon dan voorspeld: de
    kandidaat stond op nul metingen, terwijl het precies zo'n dag was
    waarop bijkopen relevant kon zijn.

    Hij mat alleen bij een BECIJFERD tekort, en dat was er niet - de
    reserve had het opgevangen. Dan blijft de kandidaat maandenlang op
    nul staan tot de reserve een keer tekortschiet, en dan is er nog
    niets geleerd.
    """
    c, entries = _coordinator(make_coordinator, hass)
    c.get_quarter_plan_summary = lambda *a, **k: {
        "beschikbaar": True,
        "tekort_kwartieren": 0,
        "laagste_soc_procent": 14,
    }
    c.effective_min_soc_percent = lambda: 10.0
    c.get_quarter_plan = lambda *a, **k: [
        {"soc_procent": 14, "prijs_ct": 40.0, "verbruik_kwh": 0.25},
        {"soc_procent": 60, "prijs_ct": 30.0, "verbruik_kwh": 0.25},
    ]

    c._meet_bijkopen_bij_tekort(NU, entries)

    assert c.bijkoop_history
    assert c.bijkoop_history[0]["soort"] == "krappe marge"


def test_a_comfortable_plan_is_not_measured(make_coordinator, hass):
    """Anders zou elke dag meetellen en zegt het cijfer niets."""
    c, entries = _coordinator(make_coordinator, hass)
    c.get_quarter_plan_summary = lambda *a, **k: {
        "beschikbaar": True,
        "tekort_kwartieren": 0,
        "laagste_soc_procent": 55,
    }
    c.effective_min_soc_percent = lambda: 10.0

    c._meet_bijkopen_bij_tekort(NU, entries)

    assert c.bijkoop_history == []


def test_a_real_shortfall_is_marked_as_such(make_coordinator, hass):
    """Een meting bij een krappe marge weegt lichter dan een bij een
    echt tekort - daar had de reserve het al opgevangen."""
    c, entries = _coordinator(make_coordinator, hass)

    c._meet_bijkopen_bij_tekort(NU, entries)

    assert c.bijkoop_history[0]["soort"] == "tekort"


def test_the_candidate_separates_the_two_kinds(make_coordinator, hass):
    """Zonder dat onderscheid zijn de cijfers later niet te duiden."""
    c, _ = _coordinator(make_coordinator, hass)
    c.bijkoop_history = [
        {"soort": "tekort", "voordeel_eur_per_kwh": 0.08, "voordeel_totaal_eur": 0.08}
    ] * 10 + [
        {"soort": "krappe marge", "voordeel_eur_per_kwh": -0.02, "voordeel_totaal_eur": 0.0}
    ] * 20

    o = c._kandidaat_bijkopen()["zou_hebben_opgeleverd"]

    assert o["bij_echt_tekort"] == 10
    assert o["bij_krappe_marge"] == 20
