"""Zelfevaluatie: achteraf toetsen of instellingen goed uitpakken
(v1.14.0).

Gevraagd: "Kun je een mechanisme bedenken waardoor de integratie zichzelf
verbetert? Dus tips geeft welke verbetermogelijkheden er zijn."

Zichzelf herschrijven kan ze niet. Wat wél kan is beoordelen of een keuze
goed uitviel, met de eigen meetgeschiedenis als bewijs. Nadrukkelijk
VOORSTELLEN, geen ingrepen: de reserveberekening is eerder expliciet
afgeschermd, en een systeem dat ongevraagd zijn eigen veiligheidsmarges
verlaagt is precies wat je niet wilt.
"""
from custom_components.energy_management_system.const import (
    SELF_EVAL_MIN_DAYS,
)


def _met_reserve(c, dagen, tekort=False, over=True):
    c.reserve_daily_records = [
        {"date": f"2026-07-{d:02d}", "shortfall": tekort, "excess": over}
        for d in range(1, dagen + 1)
    ]
    return c


def _met_rapporten(c, dagen, soc_min=15.0, redenen=None):
    c.daily_report_history = [
        {
            "datum": f"2026-07-{d:02d}",
            "soc_min_procent": soc_min,
            "redenen": redenen or {"a": 5, "b": 3, "c": 2},
        }
        for d in range(1, dagen + 1)
    ]
    return c


# --- 1. reserve te ruim of te krap -----------------------------------


def test_a_consistently_wide_reserve_is_reported(make_coordinator, hass):
    """Dertig dagen overschot en nul tekorten: die energie had in het
    dure blok verkocht kunnen worden."""
    c = _met_rapporten(_met_reserve(make_coordinator({}), 30), 30)

    bevinding = next(
        b for b in c.get_self_evaluation() if "ruim" in b["onderwerp"]
    )

    assert "30x energie over" in bevinding["bewijs"]
    assert "controleer eerst" in bevinding["voorstel"]


def test_a_tight_reserve_is_reported(make_coordinator, hass):
    c = make_coordinator({})
    c.reserve_daily_records = [
        {"date": f"2026-07-{d:02d}", "shortfall": d <= 10, "excess": False}
        for d in range(1, 21)
    ]

    bevinding = next(
        b for b in c.get_self_evaluation() if "krap" in b["onderwerp"]
    )

    assert "10x" in bevinding["bewijs"]


def test_a_healthy_balance_says_nothing(make_coordinator, hass):
    """Advies geven waar niets aan de hand is, maakt de hele lijst
    waardeloos."""
    c = make_coordinator({})
    c.reserve_daily_records = [
        {"date": f"2026-07-{d:02d}", "shortfall": d == 1, "excess": d > 15}
        for d in range(1, 21)
    ]

    assert not any(
        "reserve" in b["onderwerp"].lower() for b in c.get_self_evaluation()
    )


def test_too_few_days_gives_no_verdict(make_coordinator, hass):
    """Eén rustige week zegt niets, en te snel adviseren de marge te
    verlagen is gevaarlijker dan te laat."""
    c = _met_reserve(make_coordinator({}), SELF_EVAL_MIN_DAYS - 1)

    assert c.get_self_evaluation() == []


# --- 2. de accu wordt niet benut -------------------------------------


def test_a_never_discharged_battery_is_reported(make_coordinator, hass):
    c = _met_rapporten(make_coordinator({}), 20, soc_min=55.0)

    bevinding = next(
        b for b in c.get_self_evaluation() if "diep ontladen" in b["onderwerp"]
    )

    assert "55%" in bevinding["bewijs"]
    assert "minimale SoC" in bevinding["voorstel"]


def test_a_properly_used_battery_says_nothing(make_coordinator, hass):
    c = _met_rapporten(make_coordinator({}), 20, soc_min=12.0)

    assert not any(
        "ontladen" in b["onderwerp"] for b in c.get_self_evaluation()
    )


# --- 3. weinig variatie in beslissingen ------------------------------


def test_little_variation_is_reported(make_coordinator, hass):
    """Kan betekenen dat een drempel zo staat dat er zelden iets
    verandert."""
    c = _met_rapporten(
        make_coordinator({}), 20, redenen={"expensive_quarter": 200}
    )

    bevinding = next(
        b for b in c.get_self_evaluation() if "variatie" in b["onderwerp"]
    )

    assert "expensive_quarter" in bevinding["bewijs"]


def test_normal_variation_says_nothing(make_coordinator, hass):
    c = _met_rapporten(make_coordinator({}), 20)

    assert not any(
        "variatie" in b["onderwerp"] for b in c.get_self_evaluation()
    )


# --- vorm en inbedding -----------------------------------------------


def test_every_finding_has_evidence_and_a_proposal(make_coordinator, hass):
    """Een voorstel zonder bewijs is een mening; bewijs zonder voorstel
    laat je met de vraag zitten wat je ermee moet."""
    c = _met_rapporten(_met_reserve(make_coordinator({}), 30), 30, soc_min=55.0)

    bevindingen = c.get_self_evaluation()

    assert bevindingen
    for b in bevindingen:
        assert b["bewijs"] and b["voorstel"]
        assert len(b["voorstel"]) > 50, b["onderwerp"]


def test_nothing_is_changed_automatically(make_coordinator, hass):
    """De kern van het ontwerp: voorstellen, niet ingrijpen. Een systeem
    dat ongevraagd zijn eigen veiligheidsmarges verlaagt is precies wat
    je niet wilt."""
    c = _met_rapporten(_met_reserve(make_coordinator({}), 30), 30)
    voor = dict(c.config)

    c.get_self_evaluation()

    assert dict(c.config) == voor


def test_the_findings_join_the_improvement_list(make_coordinator, hass):
    """Voor de gebruiker is het onderscheid tussen "je mist een sensor"
    en "je instelling pakt slecht uit" niet interessant."""
    c = _met_rapporten(_met_reserve(make_coordinator({}), 30), 30)

    onderwerpen = {a["onderwerp"] for a in c.get_improvement_suggestions()}

    assert "Nachtreserve staat ruim" in onderwerpen


def test_it_is_in_the_diagnostics_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "self_evaluation" in bron
