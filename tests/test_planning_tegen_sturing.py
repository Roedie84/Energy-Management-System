"""Waar wijkt de planning af van de aansturing? (v3.87.0)

Gemeld bij de doorlichting, en tweemaal zelf ingetrapt: de
kwartierplanning laat de accu naar 10% zakken terwijl de verkooptoets
bij 4,86 kWh ingrijpt.

Dat is geen fout maar een verschil in aard. De planning is een
VOORUITBEREKENING die laat zien wat er gebeurt als de prijs leidend is;
de verkooptoets is een GRENDEL die elk moment opnieuw kijkt of de woning
nog genoeg overhoudt.

Wie de planning leest zonder dat te weten, denkt dat de accu vannacht
leeg gaat.
"""
import pytest


def _coordinator(make_coordinator, socs, reserve=4.86, capaciteit=7.78):
    c = make_coordinator({})
    c.quarter_plan = [
        {"van": f"{9 + i}:00", "soc_procent": soc, "modus": "smart"}
        for i, soc in enumerate(socs)
    ]
    c.last_projection_reserve_kwh = reserve
    c.bruikbare_capaciteit_kwh = lambda: capaciteit
    c.effective_min_soc_percent = lambda: 10.0
    return c


def test_quarters_below_the_reserve_are_listed(make_coordinator, hass):
    """De situatie van 30 augustus: de planning zakt naar 10% terwijl de

    verkooptoets bij 4,86 kWh grendelt.
    """
    c = _coordinator(make_coordinator, [90.0, 70.0, 40.0, 10.0])

    uit = c.get_planning_tegen_sturing()

    assert uit["kwartieren_onder_de_reserve"] == 2
    assert uit["laagste"]["soc_procent"] == 10.0


def test_a_plan_that_stays_above_says_nothing(make_coordinator, hass):
    c = _coordinator(make_coordinator, [90.0, 85.0, 80.0])

    assert c.get_planning_tegen_sturing()["kwartieren_onder_de_reserve"] == 0


def test_it_reports_the_first_one(make_coordinator, hass):
    """Wanneer het zou beginnen, is de vraag die je stelt."""
    c = _coordinator(make_coordinator, [90.0, 70.0, 40.0, 10.0])

    assert c.get_planning_tegen_sturing()["eerste"]["soc_procent"] == 40.0


def test_without_a_reserve_it_says_so(make_coordinator, hass):
    c = _coordinator(make_coordinator, [90.0])
    c.last_projection_reserve_kwh = None

    assert c.get_planning_tegen_sturing()["beschikbaar"] is False


def test_the_conversion_uses_the_floor(make_coordinator, hass):
    """Bij een ondergrens van 10% is 10% laadstand nul bruikbare kWh -

    niet 0,78.
    """
    c = _coordinator(make_coordinator, [10.0], reserve=0.1)

    uit = c.get_planning_tegen_sturing()

    assert uit["laagste"]["beschikbaar_kwh"] == 0.0
