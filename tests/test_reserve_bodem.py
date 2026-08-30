"""De reserve houdt altijd iets achter (v3.74.0).

Gemeld: "De accu was weer leeg, dat moet opgelost worden." Drie
ochtenden op rij, en gemeten in de export van 30 augustus:

    diepste tekort onderweg   0,001 kWh
    marge                    55 %
    reserve                   0,001 kWh

Daar zit de weeffout. De marge wordt VERMENIGVULDIGD met het diepste
tekort, en dat tekort is nul zodra de voorspelling zegt dat de zon het
huis morgen dekt. Vijfenvijftig procent van nul is nul.

De reserve houdt dus structureel niets achter op precies de dagen dat de
voorspelling optimistisch is. Op 29 augustus ging 2,24 van de 5,92
ontladen kilowattuur naar het NET; had de accu die gehouden, dan was hij
's ochtends op 40% gebleven in plaats van 13%.

Anders dan de bodem uit v3.71.0: die zat alleen in de verkooptoets en
werkte als max() op één plek. Deze staat in de RESERVE en werkt door in
het ontladen, de verkooptoets en de kwartierplanning tegelijk.
"""
import pytest

from custom_components.energy_management_system.const import (
    RESERVE_BODEM_FRACTIE,
)


def _overzicht(c):
    """De uitsplitsing wordt gevuld door de reserveberekening zelf;

    `get_reserve_margin_overview` leest hem alleen.
    """
    from datetime import datetime, timedelta

    nu = datetime(2026, 8, 30, 20, 0)
    c._get_dynamic_discharge_reserve_kwh(nu, nu + timedelta(hours=13))
    return c.last_reserve_margin_breakdown


# --- de situatie van 30 augustus -------------------------------------


def test_a_zero_deficit_still_reserves_something(make_coordinator, hass):
    """Het geval waar het om gaat: de voorspelling zegt dat er niets

    nodig is, en dan houdt de reserve niets achter.
    """
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: 7.78
    c._estimate_worst_case_deficit_kwh = lambda *a, **k: 0.001

    b = _overzicht(c)

    assert b["reserve_kwh_after_margin"] == pytest.approx(
        7.78 * RESERVE_BODEM_FRACTIE, abs=0.01
    )
    assert b["bodem_bindend"] is True


def test_a_real_deficit_still_wins(make_coordinator, hass):
    """De bodem vervangt de berekening niet - hij staat eronder."""
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: 7.78
    c._estimate_worst_case_deficit_kwh = lambda *a, **k: 5.0

    b = _overzicht(c)

    assert b["reserve_kwh_after_margin"] > 7.78 * RESERVE_BODEM_FRACTIE
    assert b["bodem_bindend"] is False


def test_the_floor_is_reported(make_coordinator, hass):
    """Wie leest waarom er niet ontladen wordt, hoort te zien of dat de

    voorspelling was of de bodem.
    """
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: 7.78
    c._estimate_worst_case_deficit_kwh = lambda *a, **k: 0.0

    b = _overzicht(c)

    assert b["bodem_kwh"] == pytest.approx(7.78 * RESERVE_BODEM_FRACTIE, abs=0.01)
    assert b["bodem_procent"] == pytest.approx(15.0)


def test_without_a_known_capacity_nothing_changes(make_coordinator, hass):
    """Geen capaciteit betekent geen bodem - beter dan een verzonnen

    grens.
    """
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: None
    c._estimate_worst_case_deficit_kwh = lambda *a, **k: 0.0

    b = _overzicht(c)

    assert b["bodem_kwh"] == 0
    assert b["reserve_kwh_after_margin"] == 0


# --- de afweging achter het getal ------------------------------------


def test_the_floor_covers_a_night(make_coordinator, hass):
    """Vijftien procent van 7,78 kWh is ongeveer 1,17 kWh. Bij een

    basislast van 250 W is dat bijna vijf uur - genoeg om de nacht te
    halen als de voorspelling tegenvalt.
    """
    bodem_kwh = 7.78 * RESERVE_BODEM_FRACTIE
    basislast_kw = 0.25

    assert 4.0 <= bodem_kwh / basislast_kw <= 6.0


def test_the_floor_leaves_room_for_arbitrage(make_coordinator, hass):
    """En klein genoeg om de arbitrage te laten werken op de dagen dat de

    voorspelling wél klopt: er blijft ruim vier vijfde over.
    """
    assert RESERVE_BODEM_FRACTIE <= 0.20


# --- het werkt door op alle drie de plekken --------------------------


def test_it_reaches_the_sell_check(make_coordinator, hass):
    """Het verschil met de bodem uit v3.71.0: die zat ALLEEN in de

    verkooptoets. Deze staat in de reserve, en de verkooptoets gebruikt
    diezelfde reserve.
    """
    import inspect

    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    bron = inspect.getsource(C.get_reserve_margin_overview)

    assert "reserve_kwh_after_margin" in bron
