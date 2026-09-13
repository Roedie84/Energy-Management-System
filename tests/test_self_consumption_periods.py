"""Zelfconsumptie per week, maand, jaar en contractjaar (v1.90.0).

Gevraagd: "Misschien zelfconsumptie per dag/week/maand/jaar?" en "de
start van mijn contract bij Zonneplan (...) zodat ik precies het gebeuren
voor mijn contractjaar kan zien".

Daaronder zat een echte vraag: "de zonne-energie van gisteren, opgeslagen
in de batterij, is vannacht gebruikt - dat is toch ook zelfconsumptie?"

Ja, en de formule doet dat al goed: wat niet is geëxporteerd, is zelf
gebruikt. Waar het misging is de DAGGRENS. Op 14 augustus 08:23 stond er
0,109 kWh opwek tegen 0,448 kWh export - allemaal gisteren opgeslagen zon
die vannacht is verkocht. Over een week valt die grens weg.
"""
from datetime import date, datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_CONTRACT_START_DATE,
)

NU = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, dagen=10, **config):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator(config)
    c.energy_daily_history = [
        {
            "datum": (NU.date() - timedelta(days=n)).isoformat(),
            "opwek_kwh": 20.0,
            "zon_export_kwh": 8.0,
            "accu_export_kwh": 1.0,
            "export_kwh": 9.0,
            "verbruik_kwh": 10.0,
            "import_kwh": 1.0,
        }
        for n in range(1, dagen + 1)
    ]
    return c


def test_a_week_is_computed(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    week = c.get_self_consumption_overview(NU)["perioden"]["week"]

    assert week["dagen"] == 6
    # 20 kWh opwek, 8 het net op -> 60% zelf gebruikt.
    assert week["zelfconsumptie_procent"] == 60.0
    assert week["zelfvoorziening_procent"] == 90.0


def test_the_measured_split_is_used(make_coordinator, hass):
    """De gemeten zon-export, niet de totale export. Anders telt
    accu-export van gisteren mee tegen de opwek van vandaag - precies de
    fout die de vraag opriep."""
    c = _coordinator(make_coordinator)
    for r in c.energy_daily_history:
        r["export_kwh"] = 15.0  # veel accu-export

    week = c.get_self_consumption_overview(NU)["perioden"]["week"]

    assert week["zelfconsumptie_procent"] == 60.0


def test_an_old_day_without_the_split_falls_back(make_coordinator, hass):
    """Dagen van vóór v1.76.0 hebben geen splitsing; dan de totale
    export, begrensd op de opwek, zoals v1.9.2 al deed."""
    c = _coordinator(make_coordinator)
    for r in c.energy_daily_history:
        r["zon_export_kwh"] = None
        r["export_kwh"] = 30.0

    week = c.get_self_consumption_overview(NU)["perioden"]["week"]

    assert week["zelfconsumptie_procent"] == 0.0


def test_the_contract_year_is_shown_when_configured(make_coordinator, hass):
    """Een energiecontract loopt zelden gelijk met het kalenderjaar."""
    c = _coordinator(
        make_coordinator, dagen=30, **{CONF_CONTRACT_START_DATE: "2026-08-01"}
    )

    o = c.get_self_consumption_overview(NU)

    assert o["contractjaar_begin"] == "2026-08-01"
    assert "contractjaar" in o["perioden"]


def test_a_contract_that_started_last_year(make_coordinator, hass):
    """Begint het contract later in het jaar dan vandaag, dan loopt het
    lopende jaar vanaf vorig jaar."""
    c = _coordinator(
        make_coordinator, **{CONF_CONTRACT_START_DATE: "2025-11-15"}
    )

    assert c._huidig_contractjaar_begin(date(2026, 8, 14)) == date(2025, 11, 15)


def test_without_a_contract_date_nothing_is_claimed(make_coordinator, hass):
    c = _coordinator(make_coordinator)

    o = c.get_self_consumption_overview(NU)

    assert o["contractjaar_begin"] is None
    assert "contractjaar" not in o["perioden"]


def test_too_little_sun_gives_no_percentage(make_coordinator, hass):
    """Over een fractie van een kilowattuur valt geen aandeel te
    berekenen - dat gaf ooit -244,6%."""
    c = _coordinator(make_coordinator)
    for r in c.energy_daily_history:
        r["opwek_kwh"] = 0.01

    assert "week" not in c.get_self_consumption_overview(NU)["perioden"]


def test_a_finished_day_is_recorded(make_coordinator, hass):
    c = _coordinator(make_coordinator, dagen=0)
    c.pv_production_today_kwh = 18.0
    c.solar_export_today_kwh = 6.0
    c.pv_export_today_kwh = 7.0
    c.gross_consumption_today_kwh = 9.0
    c.grid_import_today_kwh = 0.5

    c._sluit_energiedag_af(date(2026, 8, 13))

    r = c.energy_daily_history[-1]
    assert r["datum"] == "2026-08-13"
    assert r["opwek_kwh"] == 18.0
    assert r["zon_export_kwh"] == 6.0


def test_the_series_survives_a_restart():
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "energy_daily_history" in PERSISTED_PLAIN_FIELDS
