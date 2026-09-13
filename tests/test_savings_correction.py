"""De besparing gecorrigeerd voor wat er nog in de accu zit (v1.52.0).

Gevonden in de export van 11 augustus 19:40: de besparing van vandaag
stond op -0,37 euro, alsof de aansturing slechter is dan niets doen.
Maar de accu stond op 98% en had de zon van vanmiddag nog in huis.

De vergelijking rekent per tick af tegen de netstroom. Laden is op dat
moment een KOST - die kWh had ook teruggeleverd kunnen worden - en de
opbrengst volgt pas bij het ontladen.
"""
from datetime import datetime, timezone

NU = datetime(2026, 8, 11, 19, 40, tzinfo=timezone.utc)


def _coordinator(make_coordinator, begin, nu_kwh, waarde=0.37):
    c = make_coordinator({})
    c._savings_day_start_available_kwh = begin
    c.beschikbare_energie_kwh = lambda: nu_kwh
    c.current_feedin_value_eur_per_kwh = waarde
    c.counterfactual_cost_today_eur = -2.40
    c.actual_cost_today_eur = -2.03
    return c


def test_a_fuller_battery_explains_a_negative_saving(make_coordinator, hass):
    """De echte cijfers van 19:40: -0,37 rauw, terwijl de accu vol staat."""
    c = _coordinator(make_coordinator, begin=1.2, nu_kwh=7.60)

    correctie = c.get_savings_correction()

    assert correctie["besparing_vandaag_eur"] == -0.37
    assert correctie["voorraadverschil_kwh"] == 6.4
    assert correctie["besparing_gecorrigeerd_eur"] > 1.5


def test_an_empty_battery_at_both_ends_needs_no_correction(
    make_coordinator, hass
):
    """Begint en eindigt de dag gelijk, dan is het rauwe cijfer al
    eerlijk."""
    c = _coordinator(make_coordinator, begin=3.0, nu_kwh=3.0)

    correctie = c.get_savings_correction()

    assert correctie["voorraadwaarde_eur"] == 0.0
    assert (
        correctie["besparing_gecorrigeerd_eur"]
        == correctie["besparing_vandaag_eur"]
    )


def test_a_battery_that_emptied_lowers_the_corrected_figure(
    make_coordinator, hass
):
    """Andersom moet het ook werken: eindigt de dag leger, dan is een
    deel van de besparing geleend van gisteren."""
    c = _coordinator(make_coordinator, begin=7.0, nu_kwh=1.0)

    correctie = c.get_savings_correction()

    assert correctie["voorraadwaarde_eur"] < 0
    assert (
        correctie["besparing_gecorrigeerd_eur"]
        < correctie["besparing_vandaag_eur"]
    )


def test_without_a_starting_level_it_says_so(make_coordinator, hass):
    """Een verzonnen correctie is erger dan geen correctie."""
    c = _coordinator(make_coordinator, begin=None, nu_kwh=7.0)

    correctie = c.get_savings_correction()

    assert correctie["correctie_beschikbaar"] is False
    assert correctie["besparing_vandaag_eur"] == -0.37


def test_the_raw_figure_is_never_overwritten(make_coordinator, hass):
    """De correctie staat NAAST het rauwe cijfer: dat laatste is wat er
    werkelijk is afgerekend, de correctie schat wat er nog komt."""
    c = _coordinator(make_coordinator, begin=1.2, nu_kwh=7.60)

    correctie = c.get_savings_correction()

    assert correctie["besparing_vandaag_eur"] == -0.37
    assert c.counterfactual_cost_today_eur == -2.40


def test_the_starting_level_survives_a_restart():
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "_savings_day_start_available_kwh" in PERSISTED_PLAIN_FIELDS
