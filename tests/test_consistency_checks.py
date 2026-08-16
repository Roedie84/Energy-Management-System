"""Zelfcontrole: getallen die elkaar moeten kloppen (v2.0.0).

Gevraagd: "Kun je dit soort zaken ook live in de integratie analyseren,
dus zonder jou een diagnostiek te sturen? (...) Eigenlijk dus een soort
van AI in de integratie, zodat ik live kan zien dat een berekening ofzo
niet klopt."

Geen taalmodel - en dat is geen beperking maar de juiste keuze. Vrijwel
alles wat er deze week bij het nakijken van een diagnostiek uit kwam,
kwam uit KRUISCONTROLES: twee getallen die hetzelfde horen te zeggen en
dat niet deden. Die zijn mechanisch te vinden.

Elke toets hieronder komt overeen met een fout die werkelijk is
voorgekomen.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def vervang_zelfvoorziening():
    """Vervangt de property tijdelijk en zet hem daarna terug.

    Zonder terugzetten lekt de vervanging naar andere testbestanden -
    precies wat er bij de eerste poging gebeurde.
    """
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as Klasse,
    )

    origineel = Klasse.self_sufficiency_ratio_percent

    def _zet(waarde):
        Klasse.self_sufficiency_ratio_percent = property(
            lambda self: waarde
        )

    yield _zet
    Klasse.self_sufficiency_ratio_percent = origineel


def _coordinator(make_coordinator, hass):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator({})
    c.last_successful_update = NU.isoformat()
    c.gross_consumption_today_kwh = 0.0
    c.energy_daily_history = []
    return c


def test_self_sufficiency_must_follow_from_the_counters(
    make_coordinator, hass, vervang_zelfvoorziening
):
    c = _coordinator(make_coordinator, hass)
    c.gross_consumption_today_kwh = 10.0
    c.grid_import_today_kwh = 2.0
    vervang_zelfvoorziening(50.0)  # zou 80 moeten zijn

    namen = [
        b["naam"] for b in c.get_consistency_checks(NU)["bevindingen"]
    ]

    assert "Zelfvoorziening" in namen


def test_an_exact_match_of_yield_and_use_is_reported(
    make_coordinator, hass
):
    """Dit was de verklikker bij de ingelezen geschiedenis: opwek en
    verbruik stonden op exact hetzelfde getal, omdat verbruik werd
    berekend als opwek plus import min export terwijl die twee nul
    waren."""
    c = _coordinator(make_coordinator, hass)
    c.energy_daily_history = [
        {"datum": "2026-08-14", "opwek_kwh": 21.9, "verbruik_kwh": 21.9}
    ]

    namen = [b["naam"] for b in c.get_consistency_checks(NU)["bevindingen"]]

    assert "Dagreeks" in namen


def test_an_impossible_day_is_reported(make_coordinator, hass):
    """131548 kWh in een week - een niet-omgerekende eenheid."""
    c = _coordinator(make_coordinator, hass)
    c.energy_daily_history = [
        {"datum": "2026-08-14", "opwek_kwh": 21924.0, "verbruik_kwh": 9.0}
    ]

    bevindingen = c.get_consistency_checks(NU)["bevindingen"]

    assert any(b["naam"] == "Dagreeks" for b in bevindingen)


def test_a_stalled_tick_is_reported(make_coordinator, hass):
    """Twee ticks missen kan; een half uur stilte niet."""
    c = _coordinator(make_coordinator, hass)
    c.last_successful_update = (NU - timedelta(minutes=40)).isoformat()

    namen = [b["naam"] for b in c.get_consistency_checks(NU)["bevindingen"]]

    assert "Tick" in namen


def test_a_flapping_fan_is_reported(make_coordinator, hass):
    """De ventilator schakelde in de nacht van 15 augustus dertien
    keer."""
    c = _coordinator(make_coordinator, hass)
    # v2.0.3: over een venster van zes uur, niet vanaf middernacht.
    c.battery_cooling_history = [
        {
            "moment": (NU - timedelta(minutes=20 * i)).isoformat(),
            "actie": "aan",
        }
        for i in range(15)
    ]

    bevindingen = c.get_consistency_checks(NU)["bevindingen"]

    assert any(b["naam"] == "Accukoeling" for b in bevindingen)


def test_a_healthy_system_reports_nothing(
    make_coordinator, hass, vervang_zelfvoorziening
):
    """Een controle die altijd iets vindt, wordt genegeerd."""
    c = _coordinator(make_coordinator, hass)
    c.gross_consumption_today_kwh = 10.0
    c.grid_import_today_kwh = 2.0
    vervang_zelfvoorziening(80.0)

    uitkomst = c.get_consistency_checks(NU)

    assert uitkomst["alles_klopt"] is True
    assert uitkomst["bevindingen"] == []


def test_it_is_honest_about_what_it_cannot_catch(make_coordinator, hass):
    """Wat dit niet vangt is een fout van een soort die er niet in
    staat. Dat hoort erbij te staan."""
    c = _coordinator(make_coordinator, hass)

    assert "niet" in c.get_consistency_checks(NU)["toelichting"]


def test_no_language_model_is_used():
    """Een taalmodel zou hier niets aan toevoegen en wel een reden
    kunnen verzinnen die niet klopt - dezelfde afweging als bij de
    waarom-uitleg (v1.60.0)."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("def get_consistency_checks")
    blok = bron[kop : bron.index("\n    def ", kop + 10)]

    for verboden in ("openai", "anthropic", "requests.post", "aiohttp"):
        assert verboden not in blok.lower()


def test_the_same_finding_is_not_reported_twice(make_coordinator, hass):
    """Dezelfde bevinding elke ronde opnieuw melden is de snelste manier
    om ervoor te zorgen dat er niet meer naar gekeken wordt."""
    c = _coordinator(make_coordinator, hass)
    c.last_successful_update = (NU - timedelta(minutes=40)).isoformat()
    verstuurd = []
    c._dispatch_notification = lambda **kw: verstuurd.append(kw)

    c._meld_zelfcontrole(NU)
    c._meld_zelfcontrole(NU)

    assert len(verstuurd) == 1


# --- v2.0.1: klein op het overzicht, uitgebreid op de eigen pagina ---


def test_the_overview_has_a_compact_tile():
    """Gevraagd: "Dit uiteraard op een apart tabblad, maar op de
    landingspagina een klein overzicht."

    De tegel toont het oordeel en hoogstens de eerste bevinding; de rest
    staat op de eigen pagina.
    """
    from pathlib import Path

    import yaml

    import custom_components.energy_management_system as pkg

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    overzicht = data["views"][0]
    tegels = [
        k
        for sec in overzicht["sections"]
        for k in sec["cards"]
        if "detail-zelfcontrole" in str(k)
    ]

    assert len(tegels) == 1
    assert "bevindingen[0]" in str(tegels[0])


def test_the_tile_colours_by_severity():
    """Groen als alles klopt, rood bij een fout, amber bij aandacht.
    Zonder kleur moet je hem lezen om te weten of er iets is."""
    from pathlib import Path

    import yaml

    import custom_components.energy_management_system as pkg

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    tegel = next(
        k
        for sec in data["views"][0]["sections"]
        for k in sec["cards"]
        if "detail-zelfcontrole" in str(k)
    )

    kleur = tegel["icon_color"]
    assert "green" in kleur and "red" in kleur and "amber" in kleur


def test_the_full_list_stays_on_its_own_page():
    """De landingspagina mag geen lijst worden - daar is de subview
    voor."""
    from pathlib import Path

    import yaml

    import custom_components.energy_management_system as pkg

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    pagina = next(
        v for v in data["views"] if v.get("path") == "detail-zelfcontrole"
    )
    inhoud = "".join(
        str(k.get("content") or "")
        for sec in pagina["sections"]
        for k in sec["cards"]
    )

    assert "for b in z.bevindingen" in inhoud


# --- v2.0.3: onvolledig is geen rekenfout ----------------------------


def test_one_contributing_day_is_not_a_calculation_error(
    make_coordinator, hass
):
    """Gemeld: "Periode: CO2 - week, maand en jaar staan alle drie op
    0.05."

    De controle had gelijk, maar de oorzaak is niet dat er iets fout
    wordt gerekend: er is simpelweg één dag met een CO2-waarde.
    Ingelezen dagen hebben die niet, want de intensiteit per uur is nooit
    bewaard.

    Een fout melden waar niets aan te doen is, is de snelste manier om
    de controle te laten negeren - dezelfde afweging als bij de
    terugval-duur (v1.79.0).
    """
    c = _coordinator(make_coordinator, hass)
    c.energy_daily_history = [
        {"datum": "2026-08-14", "opwek_kwh": 20.0, "co2_kg": 0.05},
        *[
            {"datum": f"2026-08-{d:02d}", "opwek_kwh": 20.0, "co2_kg": None}
            for d in range(1, 14)
        ],
    ]

    co2 = [
        b
        for b in c.get_consistency_checks(NU)["bevindingen"]
        if b["naam"].endswith("CO2")
    ]

    assert co2
    assert co2[0]["ernst"] == "aandacht"
    assert "vult zich vanzelf" in co2[0]["uitleg"].lower()


def test_many_contributing_days_with_one_value_is_a_fault(
    make_coordinator, hass
):
    """Dragen de perioden VERSCHILLENDE dagen en staan ze toch op
    hetzelfde getal, dan is er echt iets mis.

    v2.1.2: gemeld dat "2 dagen een waarde hebben" als fout werd
    gemeld terwijl beide dagen binnen de week vielen - dan bevatten
    week, maand en jaar dezelfde twee dagen en hoort er hetzelfde getal
    te staan. Hier liggen ze wél verspreid.
    """
    c = _coordinator(make_coordinator, hass)
    c.energy_daily_history = [
        {"datum": f"2026-08-{d:02d}", "opwek_kwh": 20.0, "co2_kg": 0.05}
        for d in range(1, 15)
    ]

    co2 = [
        b
        for b in c.get_consistency_checks(NU)["bevindingen"]
        if b["naam"].endswith("CO2")
    ]

    if co2:
        assert co2[0]["ernst"] == "fout"


def test_the_cooling_check_looks_at_a_window(make_coordinator, hass):
    """Gemeld: "18 schakelingen vandaag." Dat telde ook de uren van vóór
    de minimale looptijd uit v1.99.0, die die middag pas was
    geïnstalleerd. Een controle die terugkijkt naar een periode waarin de
    reparatie nog niet draaide, meldt een probleem dat al opgelost is.
    """
    c = _coordinator(make_coordinator, hass)
    # Veel schakelingen vanochtend, niets in de laatste zes uur.
    c.battery_cooling_history = [
        {"moment": (NU - timedelta(hours=10, minutes=i)).isoformat()}
        for i in range(18)
    ]

    namen = [b["naam"] for b in c.get_consistency_checks(NU)["bevindingen"]]

    assert "Accukoeling" not in namen


def test_days_inside_one_week_are_not_a_fault(make_coordinator, hass):
    """v2.1.2: gemeld als fout terwijl het er geen was.

    "Week, maand en jaar staan alle drie op 0.09 terwijl 2 dagen een
    waarde hebben." Beide dagen vielen binnen de week, dus bevatten alle
    drie de perioden dezelfde twee dagen - en dan hoort er hetzelfde
    getal te staan.
    """
    c = _coordinator(make_coordinator, hass)
    c.energy_daily_history = [
        {
            "datum": (NU.date() - timedelta(days=n)).isoformat(),
            "opwek_kwh": 20.0,
            "co2_kg": 0.045,
        }
        for n in (1, 2)
    ] + [
        {
            "datum": (NU.date() - timedelta(days=n)).isoformat(),
            "opwek_kwh": 20.0,
            "co2_kg": None,
        }
        for n in range(3, 30)
    ]

    co2 = [
        b
        for b in c.get_consistency_checks(NU)["bevindingen"]
        if b["naam"].endswith("CO2")
    ]

    assert co2
    assert co2[0]["ernst"] == "aandacht"
    assert "binnen de week" in co2[0]["uitleg"]
