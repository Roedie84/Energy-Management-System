"""Opgewekt tegenover voorspeld (v1.65.0).

Gevraagd: "xx kw opgewekt vandaag (voorspeld was xx kw). Kun je het
'voorspeld was xx kw' stuk toevoegen? Ik wil de voorspelling van de
integratie."

Nadrukkelijk de eigen verwachting, niet de kale Solcast-waarde: die
wordt gecorrigeerd met de geleerde bias per uur en de live teller.
Precies dat verschil maakt "zit er x% naast" een zinnig getal.
"""
from datetime import datetime, timedelta, timezone

NU = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, opgewekt=16.4, rest=6.6):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator({})
    c.pv_production_today_kwh = opgewekt
    c._estimate_pv_kwh_for_period = lambda a, b: rest
    return c


def test_the_morning_snapshot_is_a_real_prediction(make_coordinator, hass):
    """Dat is een echte "was": het getal stond vast voordat de dag zich
    ontvouwde."""
    c = _coordinator(make_coordinator)
    c.plan_snapshot = {
        "datum": "2026-08-12",
        "opgenomen_om": "08:00",
        "pv_bij_opname_kwh": 1.2,
        "verwachte_zon_kwh": 21.3,
    }

    waarde, herkomst = c.voorspelde_zon_vandaag_kwh(NU)

    assert waarde == 22.5
    assert "08:00" in herkomst


def test_without_a_snapshot_it_falls_back_and_says_so(
    make_coordinator, hass
):
    """Wat er nu nog verwacht wordt plus wat er al ligt schuift mee met
    de dag, en is dus geen eerlijke voorspelling meer - maar het staat
    erbij."""
    c = _coordinator(make_coordinator, opgewekt=16.4, rest=6.6)

    waarde, herkomst = c.voorspelde_zon_vandaag_kwh(NU)

    assert waarde == 23.0
    assert "bijgesteld" in herkomst


def test_a_snapshot_from_yesterday_is_not_used(make_coordinator, hass):
    """Anders staat er morgen nog steeds de voorspelling van vandaag."""
    c = _coordinator(make_coordinator)
    c.plan_snapshot = {
        "datum": "2026-08-11",
        "pv_bij_opname_kwh": 1.0,
        "verwachte_zon_kwh": 30.0,
    }

    _waarde, herkomst = c.voorspelde_zon_vandaag_kwh(NU)

    assert "bijgesteld" in herkomst


def test_the_summary_names_both_numbers(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c.get_pv_forecast_quality = lambda: {
        "beschikbaar": True,
        "dagen": 7,
        "gemiddelde_fout_procent": 9.0,
    }

    zin = c.get_topic_summaries()["zon"]["zin"]

    assert "16.4 kWh opgewekt" in zin
    assert "voorspeld 23.0" in zin


def test_it_also_works_before_the_first_complete_day(
    make_coordinator, hass
):
    """De voorspelling hoort er ook te staan als er nog niets te toetsen
    valt - dan is hij juist interessant."""
    c = _coordinator(make_coordinator)
    c.get_pv_forecast_quality = lambda: {"beschikbaar": False, "reden": "x"}

    zin = c.get_topic_summaries()["zon"]["zin"]

    assert "voorspeld 23.0" in zin


def test_the_deviation_is_computed(make_coordinator, hass):
    c = _coordinator(make_coordinator, opgewekt=16.4, rest=6.6)

    overzicht = c.get_solar_today(NU)

    assert overzicht["opgewekt_kwh"] == 16.4
    assert overzicht["voorspeld_kwh"] == 23.0
    assert overzicht["afwijking_procent"] < 0


def test_without_a_forecast_nothing_is_claimed(make_coordinator, hass):
    c = _coordinator(make_coordinator)
    c._estimate_pv_kwh_for_period = lambda a, b: None

    waarde, herkomst = c.voorspelde_zon_vandaag_kwh(NU)

    assert waarde is None
    assert "geen voorspelling" in herkomst
