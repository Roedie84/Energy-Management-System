"""Vragen stellen over de eigen gegevens (v2.3.0).

Gevraagd: "zodat ik ook vragen kan stellen als: Wat is het verwachte
verbruik vandaag, wat zijn de kosten vandaag? Hoe laat was iedereen thuis,
weg etc."

Geen taalmodel in de integratie - dezelfde afweging als bij de
waarom-uitleg (v1.60.0) en de zelfcontrole (v2.0.0). Een gegenereerd
antwoord kan een getal noemen dat nergens staat, en dat is bij
energiecijfers erger dan geen antwoord.
"""
from datetime import datetime, timezone

NU = datetime(2026, 8, 15, 14, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator({})
    c.gross_consumption_today_kwh = 6.4
    c.pv_production_today_kwh = 18.2
    c.actual_cost_today_eur = -3.1
    c.counterfactual_cost_today_eur = -0.4
    c._estimate_consumption_kwh_for_period = lambda a, b: 3.6
    return c


def test_it_answers_the_expected_consumption(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)

    uitkomst = c.beantwoord_vraag("Wat is het verwachte verbruik vandaag?", NU)

    assert uitkomst["gevonden"] is True
    assert "6.4" in uitkomst["antwoord"]
    assert uitkomst["waarden"]["verwacht_totaal_kwh"] == 10.0


def test_it_answers_the_costs(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)

    uitkomst = c.beantwoord_vraag("Wat zijn de kosten vandaag?", NU)

    assert "3.10" in uitkomst["antwoord"]
    assert "opbrengst" in uitkomst["antwoord"]


def test_it_answers_about_presence(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    c.get_presence_overview = lambda: {"nu": "thuis"}
    c.presence_timeline = []

    uitkomst = c.beantwoord_vraag("Hoe laat was iedereen thuis?", NU)

    assert uitkomst["gevonden"] is True
    assert "thuis" in uitkomst["antwoord"]


def test_an_unknown_question_says_so(make_coordinator, hass):
    """Wat er niet in staat krijgt eerlijk "die vraag ken ik niet" plus
    de lijst met wat wel kan - geen verzonnen antwoord."""
    c = _coordinator(make_coordinator, hass)

    uitkomst = c.beantwoord_vraag("Hoeveel regent het morgen?", NU)

    assert uitkomst["gevonden"] is False
    assert "ken ik niet" in uitkomst["antwoord"]
    assert uitkomst["bekende_vragen"]


def test_no_language_model_is_involved():
    """Een gegenereerd antwoord kan een getal noemen dat nergens staat,
    en dat is bij energiecijfers erger dan geen antwoord."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("def beantwoord_vraag")
    blok = bron[kop : bron.index("\n    def _antwoord_verbruik", kop)]

    for verboden in ("openai", "anthropic", "requests.post", "aiohttp"):
        assert verboden not in blok.lower()


def test_every_answer_comes_from_measured_values(make_coordinator, hass):
    """Elk antwoord draagt de waarden waarop het rust, zodat het na te
    rekenen is."""
    c = _coordinator(make_coordinator, hass)

    for vraag in ("verbruik vandaag", "kosten vandaag", "opwek vandaag"):
        uitkomst = c.beantwoord_vraag(vraag, NU)
        assert uitkomst["gevonden"] is True
        assert "waarden" in uitkomst, vraag


def test_a_broken_answer_does_not_crash(make_coordinator, hass):
    """Een vraag die de integratie kent maar niet kan beantwoorden, moet
    dat zeggen in plaats van de hele ronde te breken."""
    c = _coordinator(make_coordinator, hass)
    c._estimate_consumption_kwh_for_period = lambda a, b: 1 / 0

    uitkomst = c.beantwoord_vraag("verbruik vandaag", NU)

    assert uitkomst["gevonden"] is True
    assert "niet te berekenen" in uitkomst["antwoord"]


def test_the_service_is_registered():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "__init__.py").read_text()
    diensten = (Path(pkg.__file__).parent / "services.yaml").read_text()

    assert "SERVICE_VRAAG" in bron
    assert "vraag:" in diensten
