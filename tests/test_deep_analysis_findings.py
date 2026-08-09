"""Vondsten uit een diepe analyse van de ochtendexport (v1.16.8).

Gevraagd: eerst een diepe analyse voordat er geïnstalleerd wordt.

Twee echte vondsten, beide onzichtbaar in de samenvatting en beide
gemist door de ingebouwde controles.
"""
from custom_components.energy_management_system.const import (
    RESERVE_CONSECUTIVE_SHORTFALL_ALERT,
    SELF_CONSUMPTION_MIN_PRODUCTION_KWH,
)


# --- 1. zelfconsumptie 0,0% bij vrijwel geen opwek -------------------


def test_no_ratio_below_meaningful_production(make_coordinator, hass):
    """Uit de export: opwek 0,215 kWh, export 0,56 kWh, zelfconsumptie
    0,0%.

    Rekenkundig klopt dat - de begrenzing uit v1.9.2 kapt de export op de
    dagopwek - maar het leest als "geen enkele zon zelf gebruikt". De
    werkelijke oorzaak was dat de accu 's nachts meer verkocht dan de zon
    die ochtend opwekte. Over een fractie van een kilowattuur valt geen
    zinnig aandeel te berekenen.
    """
    c = make_coordinator({})
    c.pv_production_today_kwh = 0.215
    c.pv_export_today_kwh = 0.56

    assert c.self_consumption_ratio_percent is None


def test_a_real_day_still_gets_a_ratio(make_coordinator, hass):
    """De drempel mag een normale dag niet stilzetten."""
    c = make_coordinator({})
    c.pv_production_today_kwh = 15.5
    c.pv_export_today_kwh = 4.0

    verhouding = c.self_consumption_ratio_percent

    assert verhouding is not None
    assert 0 <= verhouding <= 100


def test_the_threshold_is_modest():
    """Een halve kWh is ruwweg een half uur zon; hoger zou een bewolkte
    dag onnodig stilzetten."""
    assert SELF_CONSUMPTION_MIN_PRODUCTION_KWH <= 1.0


# --- 2. opeenvolgende tekorten ---------------------------------------


def _met_dagen(c, tekorten):
    c.reserve_daily_records = [
        {"date": f"2026-08-{4 + i:02d}", "shortfall": t, "excess": False}
        for i, t in enumerate(tekorten)
    ]
    return c


def test_consecutive_shortfalls_are_reported_immediately(
    make_coordinator, hass
):
    """Uit de export: tekorten op 7 en 8 augustus, twee op rij. De
    zelfevaluatie zag dat niet, want die vraagt veertien dagen.

    Voor een VERHOUDING is dat verdedigbaar - vijf dagen zegt weinig -
    maar twee tekorten op rij is een patroon: dan is er twee nachten
    achtereen tegen de ochtendprijs bijgekocht.
    """
    c = _met_dagen(make_coordinator({}), [False, False, False, True, True])

    bevinding = next(
        b for b in c.get_self_evaluation() if "achtereen" in b["onderwerp"]
    )

    assert "laatste 2 nachten" in bevinding["bewijs"]
    assert "ochtendprijs" in bevinding["voorstel"]


def test_a_single_shortfall_is_not_reported(make_coordinator, hass):
    """Eén tekort kan een uitzonderlijke nacht zijn."""
    c = _met_dagen(make_coordinator({}), [False, False, False, False, True])

    assert not any(
        "achtereen" in b["onderwerp"] for b in c.get_self_evaluation()
    )


def test_older_shortfalls_do_not_count(make_coordinator, hass):
    """Twee tekorten van vier dagen geleden, gevolgd door goede nachten,
    is geen lopend probleem."""
    c = _met_dagen(make_coordinator({}), [True, True, False, False, False])

    assert not any(
        "achtereen" in b["onderwerp"] for b in c.get_self_evaluation()
    )


def test_it_does_not_wait_for_fourteen_days(make_coordinator, hass):
    """De kern van deze vondst: met vijf dagen data moet het al melden."""
    c = _met_dagen(make_coordinator({}), [False, False, False, True, True])

    assert len(c.reserve_daily_records) == 5
    assert c.get_self_evaluation()


def test_the_threshold_is_two():
    """Bij drie zou je een tweede slechte nacht laten passeren."""
    assert RESERVE_CONSECUTIVE_SHORTFALL_ALERT == 2
