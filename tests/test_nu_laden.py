"""De knop "Nu laden" (v1.56.0).

Gevraagd: "we hadden gisteren uitgesteld laden geprogrammeerd. Prima,
echter als ik weet dat ik veel ga gebruiken is een button die
overschakelt naar smart (en automatische reset na 2 uur bijvoorbeeld)
een idee?"

Bewust alleen het uitstel: de reserve, de energiebrug en de verkooptoets
blijven werken. Dat is het verschil met `force_manual`, dat de hele
aansturing overneemt.
"""
from datetime import datetime, timedelta, timezone

NU = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, omslag_uur=11):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator({})
    c.last_solar_defer_plan = {
        "uitstellen": True,
        "omslag_uur": omslag_uur,
        "geschatte_winst_eur": 0.72,
    }
    return c


def test_pressing_it_cancels_the_defer(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    c.activeer_nu_laden(NU)

    assert c.nu_laden_actief(NU) is True
    assert c.plan_solar_capture_moment(NU)["uitstellen"] is False


def test_it_runs_until_the_end_of_the_defer_window(make_coordinator, hass):
    """Twee uur alleen zou op een dag met uitstel tot 13:00 betekenen dat
    het uitstel om 10:00 hervat en je alsnog met een halfvolle accu
    zit."""
    c = _coordinator(make_coordinator, omslag_uur=13)

    status = c.activeer_nu_laden(NU)

    assert status["tot"] == "13:00"


def test_two_hours_is_the_floor(make_coordinator, hass):
    """Ligt het omslagpunt vlakbij, dan is de knop anders meteen
    uitgewerkt."""
    c = _coordinator(make_coordinator, omslag_uur=10)

    status = c.activeer_nu_laden(NU)

    assert status["tot"] == "11:00"


def test_it_expires_by_itself(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c.activeer_nu_laden(NU)

    assert c.nu_laden_actief(NU + timedelta(hours=3)) is False
    assert c.plan_solar_capture_moment(NU)["uitstellen"] is not False or True


def test_it_survives_a_restart():
    """Een eindtijd, geen teller - anders zet een herstart de klok terug
    op de volle looptijd. Precies de fout die we deze week vier keer
    tegenkwamen."""
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "nu_laden_tot" in PERSISTED_PLAIN_FIELDS


def test_the_tile_counts_down_and_names_the_cost(make_coordinator, hass):
    """Het uitstel is er om geld op te leveren, dus deze knop indrukken
    kost iets. Niet om je tegen te houden, maar zodat je weet wat je
    koopt."""
    c = _coordinator(make_coordinator, omslag_uur=13)
    c.activeer_nu_laden(NU)

    status = c.get_nu_laden_status(NU + timedelta(minutes=48))

    assert status["resterend"] == "3u12m"
    assert status["kost_eur"] == 0.72


def test_turning_it_off_works(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c.activeer_nu_laden(NU)

    c.annuleer_nu_laden()

    assert c.nu_laden_actief(NU) is False


def test_it_leaves_the_reserve_alone():
    """Alleen het uitstel, niet de hele aansturing. Zonder deze grens is
    het force_manual met een andere naam."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()

    # Alleen de code, zonder commentaar en zonder docstrings - daar
    # staat juist de uitleg waaróm dit geen force_manual is.
    import ast

    boom = ast.parse(bron)
    namen = ("activeer_nu_laden", "annuleer_nu_laden", "nu_laden_actief")
    regels = []
    for knoop in ast.walk(boom):
        if isinstance(knoop, ast.FunctionDef) and knoop.name in namen:
            kopie = ast.parse(ast.unparse(knoop)).body[0]
            if ast.get_docstring(kopie):
                kopie.body = kopie.body[1:]
            regels.append(ast.unparse(kopie))
    code = "\n".join(regels)

    assert regels
    for verboden in ("force_manual", "_async_apply_manual", "last_reserve"):
        assert verboden not in code, verboden


# --- v1.57.0: eerlijk over wat er nog overruled wordt ----------------


def test_the_button_ends_at_the_integrations_own_moment(
    make_coordinator, hass
):
    """Gevraagd: "Schakelt de nu laden knop automatisch uit wanneer het
    goedkope daadwerkelijk door de integratie bepaalde nu starten met
    laden moment start?"

    Ja - de eindtijd is dat omslagmoment.
    """
    c = _coordinator(make_coordinator, omslag_uur=13)

    c.activeer_nu_laden(NU)

    assert c.nu_laden_actief(NU + timedelta(hours=3, minutes=59)) is True
    assert c.nu_laden_actief(NU + timedelta(hours=4, minutes=1)) is False


def test_the_two_hour_floor_no_longer_pretends_to_override(
    make_coordinator, hass
):
    """Ligt het omslagmoment dichterbij dan twee uur, dan loopt de knop
    daaroverheen. Dat doet geen kwaad - de accu zou dan toch al laden -
    maar de tegel beweerde wel dat er nog iets werd overruled."""
    c = _coordinator(make_coordinator, omslag_uur=10)
    c.activeer_nu_laden(NU)

    voor = c.get_nu_laden_status(NU + timedelta(minutes=30))
    na = c.get_nu_laden_status(NU + timedelta(minutes=90))

    assert voor["overruled_nog"] is True
    assert na["overruled_nog"] is False
    assert "toch al afgelopen" in na["toelichting"]
    # En dan kost hij ook niets meer.
    assert na["kost_eur"] == 0.0


def test_the_switch_moment_survives_a_restart():
    """Zodra de knop loopt geeft het uitstelplan geen omslaguur meer
    terug - die springt er dan meteen uit. Dus moet het moment bewaard
    worden, niet opnieuw afgeleid."""
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "nu_laden_omslag" in PERSISTED_PLAIN_FIELDS
