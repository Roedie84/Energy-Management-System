"""Het MPC-plan rekent mét verbruik en zon (v3.68.0).

Gevraagd: "Het EMS zou niet meer alleen reageren op 'is dit een goedkoop
of duur kwartier?', maar op 'welke actie levert over de komende 24 uur
het beste resultaat op?'"

De vier modules uit dat voorstel bestaan alle vier al: het uurprofiel,
de PV-voorspelling met bias per bewolkingsvak, de energiebalans in
`_build_forecast_timeline`, en de besluitboom.

Wat ontbrak zat in de arbitragerekening zelf. Die was BEWUST puur prijs,
zonder huis en zonder zon - de toelichting noemde de winst daarom "een
theoretische bovengrens, geen aanbeveling".

Zonder die twee klopt de ruimte niet. Een kwartier waarin de zon de accu
al vult heeft geen laadruimte meer, en een kwartier waarin het huis 2 kW
trekt heeft minder ontlaadruimte over dan het vermogen suggereert.
"""
from datetime import datetime, timedelta

import pytest

from custom_components.energy_management_system.const import (
    MPC_MIN_METINGEN,
    PRICE_SCALE_FACTOR,
)

NU = datetime(2026, 8, 29, 10, 0)


def _entries(prijzen):
    return [
        (
            NU + timedelta(minutes=15 * i),
            NU + timedelta(minutes=15 * (i + 1)),
            p * PRICE_SCALE_FACTOR,
        )
        for i, p in enumerate(prijzen)
    ]


def _opstelling(make_coordinator, zon=0.0, huis=0.0):
    c = make_coordinator({})
    c._estimate_pv_kwh_for_period = lambda s, e: zon
    c._estimate_consumption_kwh_for_period = lambda s, e: huis
    return c


# --- de ruimte per kwartier ------------------------------------------


def test_sun_fills_the_battery_so_there_is_less_room_to_buy(
    make_coordinator, hass
):
    """Een kwartier waarin de zon de accu al vult heeft geen laadruimte

    meer om goedkoop bij te kopen.
    """
    c = _opstelling(make_coordinator, zon=0.5, huis=0.1)

    kwartieren = c._mpc_kwartieren(_entries([0.13, 0.38]), 2000, 1600)

    # 2000 W over een kwartier is 0,5 kWh; de zon vult daar 0,4 van.
    assert kwartieren[0]["charge_remaining_kwh"] == pytest.approx(0.1)
    assert kwartieren[0]["zon_naar_accu_kwh"] == pytest.approx(0.4)


def test_the_house_eats_into_the_discharge_room(make_coordinator, hass):
    """Een kwartier waarin het huis trekt heeft minder ontlaadruimte over

    dan het vermogen suggereert - dat deel is basislast, geen arbitrage.
    """
    c = _opstelling(make_coordinator, zon=0.0, huis=0.3)

    kwartieren = c._mpc_kwartieren(_entries([0.38]), 2000, 1600)

    # 1600 W over een kwartier is 0,4 kWh; het huis neemt 0,3.
    assert kwartieren[0]["discharge_remaining_kwh"] == pytest.approx(0.1)
    assert kwartieren[0]["tekort_kwh"] == pytest.approx(0.3)


def test_room_never_goes_negative(make_coordinator, hass):
    """Een huis dat meer trekt dan de accu kan leveren, maakt de ruimte

    nul - niet negatief.
    """
    c = _opstelling(make_coordinator, zon=0.0, huis=5.0)

    kwartieren = c._mpc_kwartieren(_entries([0.38]), 2000, 1600)

    assert kwartieren[0]["discharge_remaining_kwh"] == 0.0


def test_without_sun_or_load_it_is_the_old_behaviour(
    make_coordinator, hass
):
    """De oude rekening blijft eruit komen als er niets te verrekenen

    valt - anders zou deze wijziging de bestaande cijfers omgooien.
    """
    c = _opstelling(make_coordinator, zon=0.0, huis=0.0)

    kwartieren = c._mpc_kwartieren(_entries([0.13]), 2000, 1600)

    assert kwartieren[0]["charge_remaining_kwh"] == pytest.approx(0.5)
    assert kwartieren[0]["discharge_remaining_kwh"] == pytest.approx(0.4)


# --- de energiebalans ------------------------------------------------


def test_the_balance_is_sun_minus_consumption(make_coordinator, hass):
    """Gevraagd: "Verwacht verbruik min verwachte PV-opbrengst geeft een

    verwacht energietekort of energieoverschot."
    """
    c = _opstelling(make_coordinator, zon=0.5, huis=0.2)

    kwartieren = c._mpc_kwartieren(_entries([0.13] * 4), 2000, 1600)
    balans = c._mpc_energiebalans(kwartieren, beschikbaar_kwh=4.0)

    assert balans["zon_kwh"] == pytest.approx(2.0)
    assert balans["verbruik_kwh"] == pytest.approx(0.8)
    assert balans["saldo_kwh"] == pytest.approx(1.2)
    assert balans["uren"] == 1.0


def test_a_deficit_shows_as_a_negative_balance(make_coordinator, hass):
    c = _opstelling(make_coordinator, zon=0.05, huis=0.30)

    kwartieren = c._mpc_kwartieren(_entries([0.30] * 4), 2000, 1600)

    assert c._mpc_energiebalans(kwartieren, 4.0)["saldo_kwh"] < 0


# --- de kandidaat ----------------------------------------------------


def test_the_candidate_waits_for_enough_days(make_coordinator, hass):
    c = make_coordinator({})
    c.mpc_vergelijking_history = [{"verschil_eur": 0.5}] * 3

    kandidaat = c._kandidaat_mpc()

    assert kandidaat["status"] == "onvoldoende_data"
    assert str(MPC_MIN_METINGEN) in kandidaat["zou_hebben_opgeleverd"]["reden"]


def test_the_candidate_reports_the_median_difference(
    make_coordinator, hass
):
    c = make_coordinator({})
    c.mpc_vergelijking_history = [
        {"verschil_eur": v} for v in ([0.40] * 12 + [-0.10] * 4)
    ]

    opbrengst = c._kandidaat_mpc()["zou_hebben_opgeleverd"]

    assert opbrengst["bedrag_per_dag_eur"] == pytest.approx(0.40)
    assert opbrengst["aandeel_gunstig_procent"] == 75.0


def test_the_candidate_admits_what_it_does_not_know(
    make_coordinator, hass
):
    """Het MPC-plan beschermt de nachtreserve niet, dus een deel van het

    verschil is minder voorzichtigheid en geen betere planning. Dat hoort
    erbij te staan, anders leest het als gratis winst.
    """
    c = make_coordinator({})
    c.mpc_vergelijking_history = [
        {"verschil_eur": 0.4} for _ in range(MPC_MIN_METINGEN)
    ]

    reden = c._kandidaat_mpc()["zou_hebben_opgeleverd"]["reden"]

    assert "nachtreserve" in reden


def test_it_is_measured_once_a_day(make_coordinator, hass):
    """Beide plannen kijken over dezelfde 24 uur; vaker meten levert

    dezelfde vergelijking met een andere starttijd.
    """
    c = make_coordinator({})
    c.mpc_projected_total_profit_eur = 2.0
    c.get_quarter_plan_summary = lambda: {"netto_opbrengst_eur": 1.5}

    c._meet_mpc(NU)
    c._meet_mpc(NU + timedelta(hours=2))

    assert len(c.mpc_vergelijking_history) == 1
    assert c.mpc_vergelijking_history[0]["verschil_eur"] == pytest.approx(0.5)


def test_a_new_day_is_measured_again(make_coordinator, hass):
    c = make_coordinator({})
    c.mpc_projected_total_profit_eur = 2.0
    c.get_quarter_plan_summary = lambda: {"netto_opbrengst_eur": 1.5}

    c._meet_mpc(NU)
    c._meet_mpc(NU + timedelta(days=1))

    assert len(c.mpc_vergelijking_history) == 2


def test_it_is_on_the_bench(make_coordinator, hass):
    c = make_coordinator({})

    namen = [k["naam"] for k in c.get_proefstand()["kandidaten"]]

    assert "Vooruitplannen over 24 uur" in namen


def test_it_still_steers_nothing(make_coordinator, hass):
    """De hele MPC-tak is adviserend sinds v0.63.33, en dat blijft zo."""
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    import ast

    for fn in (C._compute_mpc_plan, C._mpc_kwartieren, C._meet_mpc):
        # Via de boomstructuur, niet via de tekst: de toelichting van
        # v0.63.33 NOEMT die twee functies juist om te zeggen dat ze
        # nooit worden aangeroepen. Een zoekopdracht op tekst vindt dat
        # ook - dezelfde valkuil als bij structuurscan 15.
        boom = ast.parse(inspect.getsource(fn).lstrip())
        aanroepen = {
            n.func.attr
            for n in ast.walk(boom)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }

        assert "_async_apply_operation" not in aanroepen
        assert "_async_apply_manual" not in aanroepen


def test_a_restart_does_not_add_a_second_measurement(
    make_coordinator, hass
):
    """v3.72.0: gemeten in de export van 29 augustus - twee metingen op

    28 augustus en twee op 29, terwijl er één per dag hoort te staan.

    `_mpc_gemeten_op` is vluchtig, dus na een herstart stond die weer op
    None. Bij twee installaties op één dag levert dat twee metingen met
    heel verschillende uitkomsten (+1,45 en -0,75), en die verstoren de
    mediaan.

    De geschiedenis overleeft de herstart wél.
    """
    c = make_coordinator({})
    c.mpc_projected_total_profit_eur = 2.0
    c.get_quarter_plan_summary = lambda: {"netto_opbrengst_eur": 1.5}

    c._meet_mpc(NU)
    # De herstart: de markering is weg, de geschiedenis niet.
    c._mpc_gemeten_op = None
    c.mpc_projected_total_profit_eur = 3.0
    c._meet_mpc(NU + timedelta(hours=3))

    assert len(c.mpc_vergelijking_history) == 1
