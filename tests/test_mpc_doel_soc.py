"""De doel-SOC per kwartier, achteruit gerekend (v3.69.0).

Gevraagd: "De voorspelde energiebehoefte kan worden gecombineerd met een
voorspelling van de verwachte PV-opbrengst. Deze energiebalans zou
gebruikt kunnen worden om een gewenst doel-SOC te berekenen."

Dit is iets anders dan de arbitragerekening ernaast. Die zoekt de
winstgevendste PAREN; dit loopt de horizon van ACHTER naar VOREN en
vraagt per kwartier: hoeveel moet er in de accu zitten om alles wat
hierna komt te overbruggen?

Achteruit werken is de kern. Vooruit weet je niet wat je nodig hebt;
achteruit wel, want het laatste kwartier heeft alleen zichzelf nodig en
elk kwartier daarvoor telt zijn eigen tekort erbij op.

Waar de bestaande reserve één getal is voor de hele horizon, is dit een
LIJN - lager als er zon aankomt, hoger vlak voor een dure nacht.
"""
from datetime import datetime, timedelta

import pytest

NU = datetime(2026, 8, 29, 18, 0)


def _kwartier(uur_offset, tekort=0.0, zon_naar_accu=0.0):
    return {
        "start": NU + timedelta(minutes=15 * uur_offset),
        "tekort_kwh": tekort,
        "zon_naar_accu_kwh": zon_naar_accu,
    }


# --- de kern: achteruit rekenen --------------------------------------

def test_the_last_quarter_only_needs_itself(make_coordinator, hass):
    c = make_coordinator({})

    uit = c._mpc_doel_soc([_kwartier(0, tekort=0.3)], 5.0, 7.78)

    assert uit["nu_nodig_kwh"] == pytest.approx(0.3)


def test_deficits_add_up_backwards(make_coordinator, hass):
    """Vier kwartieren van 0,3 kWh betekent 1,2 kWh aan het begin."""
    c = make_coordinator({})

    uit = c._mpc_doel_soc(
        [_kwartier(i, tekort=0.3) for i in range(4)], 5.0, 7.78
    )

    assert uit["nu_nodig_kwh"] == pytest.approx(1.2)
    # En de eis daalt naarmate de horizon opraakt.
    assert uit["lijn"][-1]["doel_kwh"] == pytest.approx(0.3)


def test_sun_ahead_lowers_the_requirement(make_coordinator, hass):
    """Zon die het huis niet nodig heeft vult de accu - dat verlaagt wat

    er vooraf in moet zitten. Dit is jouw "veel zon verwacht, accu
    bewust leger houden".
    """
    c = make_coordinator({})

    zonder = c._mpc_doel_soc(
        [_kwartier(i, tekort=0.3) for i in range(4)], 5.0, 7.78
    )
    met = c._mpc_doel_soc(
        [_kwartier(0, tekort=0.3)]
        + [_kwartier(i, zon_naar_accu=0.5) for i in range(1, 4)],
        5.0,
        7.78,
    )

    assert met["nu_nodig_kwh"] < zonder["nu_nodig_kwh"]


def test_the_requirement_never_goes_below_zero(make_coordinator, hass):
    """Meer zon dan er nodig is maakt de eis nul, niet negatief."""
    c = make_coordinator({})

    uit = c._mpc_doel_soc(
        [_kwartier(i, zon_naar_accu=2.0) for i in range(4)], 5.0, 7.78
    )

    assert uit["nu_nodig_kwh"] == 0.0


# --- wat er niet in past ---------------------------------------------

def test_more_than_the_battery_holds_is_flagged(make_coordinator, hass):
    """Een eis boven de capaciteit is geen doel maar een constatering:

    er komt hoe dan ook iets van het net.
    """
    c = make_coordinator({})

    uit = c._mpc_doel_soc(
        [_kwartier(i, tekort=1.0) for i in range(20)], 5.0, 7.78
    )

    assert uit["kwartieren_onbereikbaar"] > 0
    assert uit["nu_nodig_kwh"] <= 7.78


# --- het verschil met wat er nu in zit -------------------------------

def test_it_reports_the_shortfall_against_the_current_charge(
    make_coordinator, hass
):
    c = make_coordinator({})

    uit = c._mpc_doel_soc(
        [_kwartier(i, tekort=0.5) for i in range(8)], 2.0, 7.78
    )

    # 8 x 0,5 = 4,0 nodig, 2,0 aanwezig.
    assert uit["tekort_nu_kwh"] == pytest.approx(2.0)


def test_enough_charge_means_no_shortfall(make_coordinator, hass):
    c = make_coordinator({})

    uit = c._mpc_doel_soc(
        [_kwartier(i, tekort=0.1) for i in range(4)], 5.0, 7.78
    )

    assert uit["tekort_nu_kwh"] == 0.0


# --- de vorm ---------------------------------------------------------

def test_the_line_has_a_point_per_quarter(make_coordinator, hass):
    c = make_coordinator({})

    uit = c._mpc_doel_soc(
        [_kwartier(i, tekort=0.2) for i in range(12)], 5.0, 7.78
    )

    assert len(uit["lijn"]) == 12
    assert uit["lijn"][0]["van"] == "18:00"


def test_without_a_horizon_it_says_so(make_coordinator, hass):
    c = make_coordinator({})

    assert c._mpc_doel_soc([], 5.0, 7.78)["beschikbaar"] is False


def test_it_steers_nothing(make_coordinator, hass):
    import ast
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    boom = ast.parse(inspect.getsource(C._mpc_doel_soc).lstrip())
    aanroepen = {
        n.func.attr
        for n in ast.walk(boom)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }

    assert "_async_apply_operation" not in aanroepen
    assert "_async_apply_manual" not in aanroepen
