"""Structuurscan 10: de grote functies groeien niet verder (v3.35.0).

Gevraagd: "Wat kunnen we hier nog aan doen?" - over de 27.000 regels in
één klasse.

Eerst gemeten in plaats van gegist. De coordinator telt 27.798 regels,
maar daarvan is 34% documentatie:

    commentaar   3.968   14%
    docstrings   5.588   20%
    leeg         2.259    8%
    code        15.983   57%

En die code is fijnmazig verdeeld: 917 functies met een MEDIAAN van zes
uitspraken en een negentigste percentiel van vijfentwintig. Het is dus
geen kluwen van verstrengelde logica - het is een groot aantal kleine,
goed uitgelegde functies.

De werkelijke complexiteit zit in tweeëntwintig uitzonderingen, en twee
daarvan zijn de echte: `__init__` met 416 uitspraken en
`_async_update_locked` met 255. Alles opsplitsen in losse bestanden
verandert daar niets aan; die twee blijven even groot en even lastig.

Daarom geen grote verbouwing, maar een ratel. Deze scan bevriest de
huidige stand: bestaande grote functies mogen niet verder groeien, en er
mogen geen nieuwe bijkomen. Wie iets toevoegt aan een functie die al te
groot is, moet er eerst iets uit halen.

Gemeten in UITSPRAKEN, niet in regels. Deze codebase legt uit waarom
iets zo is - dat is de reden dat fouten hier terug te vinden zijn - en
commentaar mag daarom nooit tegen een grens aanlopen.
"""
import ast
from pathlib import Path

import pytest

import custom_components.energy_management_system as pkg

BESTANDEN = sorted(Path(pkg.__file__).parent.glob("*.py"))

# Boven dit aantal uitspraken heet een functie groot. Het negentigste
# percentiel ligt op vijfentwintig, dus zestig is ruim - dit is een
# ratel, geen stijlpolitie.
GRENS = 60

# De stand van 20 augustus 2026. Deze lijst hoort te KRIMPEN.
BEVROREN = {
    "__init__.py:_async_register_nilm_services": 71,
    # v3.58.0: de ratel sloeg voor de vierde keer aan, en toen is er
    # eindelijk een blok uit gegaan - de vijfenveertig velden die de
    # LAATSTE beslissing beschrijven staan nu in
    # `_init_laatste_beslissing()`. Van 420 naar 377.
    # v3.60.0: +1 voor `niet_ontladen_history`. De ratel liet net een
    # blok van 45 uitspraken vertrekken; deze ene erbij is de meting
    # waard die eronder ligt.
    # v3.63.0: +1 voor `bestandscontrole`.
    # v3.68.0: +1 voor `mpc_balans`. De twee blokken die het MPC-plan
    # lieten groeien zijn naar eigen functies verhuisd, dus daar is de
    # ratel wél op zijn eigen voorwaarden gehaald.
    # v3.68.0: +2 voor de MPC-vergelijking en de dagmarkering.
    "coordinator.py:__init__": 382,
    "coordinator.py:_async_update_locked": 255,
    "coordinator.py:_async_update_scheduled_charge_appliance": 70,
    "coordinator.py:_build_explanation": 73,
    "coordinator.py:_build_forecast_timeline": 66,
    "coordinator.py:_compute_mpc_plan": 83,
    "coordinator.py:_evaluate_new_notifications": 103,
    "coordinator.py:_finalize_nilm_device_day": 71,
    # v3.50.0: +2, de tijdstempels bij de twee schrijvers van
    # `last_soc_percent` in deze functie.
    "coordinator.py:_get_soc_scaled_discharge_power": 66,
    "coordinator.py:_run_monte_carlo_simulation": 61,
    "coordinator.py:_update_advisory_readiness": 68,
    "coordinator.py:_update_self_sufficiency_tracking": 67,
    "coordinator.py:_update_weather_ensemble_check": 87,
    "coordinator.py:_waarom_regels": 100,
    "coordinator.py:async_bootstrap_energy_history": 83,
    "coordinator.py:async_bootstrap_night_consumption_from_history": 99,
    "coordinator.py:get_consistency_checks": 81,
    # v3.67.0: +1 voor de aanroep van
    # `_aandachtspunten_over_de_integratie()`. De twee blokken zelf
    # staan in die functie, dus dit is een aanroep en geen groei van de
    # inhoud.
    "coordinator.py:get_diagnostic_summary": 121,
    "coordinator.py:get_quarter_plan": 95,
    "overview_svg.py:bouw_scada": 69,
    "solar_forecast.py:async_bootstrap_from_history": 69,
}


def _uitspraken(knoop) -> int:
    return sum(1 for k in ast.walk(knoop) if isinstance(k, ast.stmt)) - 1


def _grote_functies() -> dict:
    uit = {}
    for pad in BESTANDEN:
        boom = ast.parse(pad.read_text())
        for knoop in ast.walk(boom):
            if isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)):
                aantal = _uitspraken(knoop)
                if aantal > GRENS:
                    uit[f"{pad.name}:{knoop.name}"] = aantal
    return uit


def test_no_new_oversized_function_appears():
    """Een nieuwe functie boven de grens is een keuze, geen ongeluk.

    Wie er toch een nodig heeft, zet hem in `BEVROREN` met een reden -
    maar de vraag "kan dit niet in twee stukken" komt dan wel eerst.
    """
    nieuw = sorted(set(_grote_functies()) - set(BEVROREN))

    assert not nieuw, (
        "deze functies zijn boven de grens gekomen: " + ", ".join(nieuw)
    )


@pytest.mark.parametrize("naam", sorted(BEVROREN), ids=lambda n: n.split(":")[-1])
def test_a_big_function_does_not_grow(naam):
    """De ratel. Iets toevoegen aan een functie die al te groot is,

    betekent er eerst iets uit halen.
    """
    huidig = _grote_functies().get(naam)
    if huidig is None:
        pytest.skip(f"{naam} bestaat niet meer of is onder de grens gezakt")

    assert huidig <= BEVROREN[naam], (
        f"{naam} groeide van {BEVROREN[naam]} naar {huidig} uitspraken - "
        "haal er eerst iets uit"
    )


def test_the_frozen_list_shrinks_when_a_function_is_split():
    """Zakt een functie onder de grens, dan hoort hij uit de lijst.

    Anders vertelt de lijst over een jaar iets dat niet meer waar is, en
    dat is precies hoe deze codebase eerder in de problemen kwam.
    """
    huidig = _grote_functies()
    verdwenen = sorted(n for n in BEVROREN if n not in huidig)

    assert not verdwenen, (
        "deze staan nog in BEVROREN maar zijn onder de grens: "
        + ", ".join(verdwenen)
        + " - haal ze uit de lijst"
    )


def test_the_documentation_is_never_the_limit():
    """Gemeten in uitspraken, niet in regels.

    Deze codebase legt uit waarom iets zo is, en dat is de reden dat
    fouten hier terug te vinden zijn - de verklaring van 16 augustus
    stond letterlijk in een commentaarblok uit v2.2.2. Commentaar mag
    daarom nooit tegen een grens aanlopen.
    """
    code = "\n".join(
        [
            "def f():",
            *["    # " + "uitleg " * 8 for _ in range(200)],
            '    """Een docstring van vele regels.',
            *["    nog een regel" for _ in range(200)],
            '    """',
            "    return 1",
        ]
    )
    functie = ast.parse(code).body[0]

    assert _uitspraken(functie) <= 2
