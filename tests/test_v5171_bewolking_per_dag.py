"""v5.171.0 (L-EMS-058) - de bewolking van een dag is het gewogen gemiddelde
over de zonkwartieren, niet de stand om 23:59:50.

02-11: label 25,8 % (de stand om middernacht) terwijl het tot 15:15 100 % was.
Oude dagen houden hun label maar tellen niet mee in de vakken.
"""
from datetime import date, datetime, timedelta, timezone

import custom_components.energy_management_system.solar_forecast as sfm
from custom_components.energy_management_system.const import (
    CONF_SOLAR_ACTUAL_SENSOR,
    CONF_SOLAR_FORECAST_SENSOR,
    SOLAR_BIAS_MIN_PER_VAK,
)

TZ = timezone(timedelta(hours=1))
DAG = date(2026, 11, 2)


def _tracker(hass):
    return sfm.SolarForecastAccuracyTracker(
        hass, {CONF_SOLAR_FORECAST_SENSOR: "sensor.solcast", CONF_SOLAR_ACTUAL_SENSOR: "sensor.pv"}
    )


def _moment(uur, minuut=0):
    return datetime(2026, 11, 2, uur, minuut, tzinfo=TZ)


def test_02_11_bewolkt_tot_15_15_geeft_geen_heldere_dag(hass):
    t = _tracker(hass)
    # 08:00-15:00 100 % met de meeste zon, 15:15-16:15 helder met weinig zon
    for kw in range(8 * 4, 15 * 4):
        t.noteer_bewolking(_moment(kw // 4, kw % 4 * 15), 100.0, 0.2)
    for kw in range(int(15.25 * 4), int(16.5 * 4)):
        t.noteer_bewolking(_moment(kw // 4, kw % 4 * 15), 3.9, 0.02)
    # 's avonds en om middernacht: geen zon, telt niet
    t.noteer_bewolking(_moment(23, 59), 25.8, 0.0)
    waarde = t.bewolking_van_de_dag(DAG)
    assert waarde is not None and waarde > 90
    assert t.laatste_bewolking_percent == 25.8


def test_gewogen_met_de_verwachte_zon(hass):
    t = _tracker(hass)
    t.noteer_bewolking(_moment(11), 0.0, 0.3)
    t.noteer_bewolking(_moment(12), 0.0, 0.3)
    t.noteer_bewolking(_moment(13), 0.0, 0.3)
    t.noteer_bewolking(_moment(16), 100.0, 0.1)
    assert t.bewolking_van_de_dag(DAG) == 10.0


def test_per_kwartier_de_laatste_stand(hass):
    t = _tracker(hass)
    t.noteer_bewolking(_moment(12, 0), 0.0, 0.2)
    t.noteer_bewolking(_moment(12, 14), 50.0, 0.2)
    assert t.bewolking_kwartieren == {"12:00": [50.0, 0.2]}


def test_te_weinig_zonkwartieren_geen_label(hass):
    t = _tracker(hass)
    for m in (0, 15, 30):
        t.noteer_bewolking(_moment(12, m), 50.0, 0.2)
    assert t.bewolking_van_de_dag(DAG) is None


def test_nieuwe_dag_begint_leeg(hass):
    t = _tracker(hass)
    t.noteer_bewolking(_moment(12), 50.0, 0.2)
    t.noteer_bewolking(datetime(2026, 11, 3, 0, 5, tzinfo=TZ), 80.0, None)
    assert t.bewolking_kwartieren == {}
    assert t.bewolking_van_de_dag(DAG) is None


def test_dagrecord_bewaart_gemiddelde_en_bron(hass):
    t = _tracker(hass)
    for kw in range(10 * 4, 14 * 4):
        t.noteer_bewolking(_moment(kw // 4, kw % 4 * 15), 80.0, 0.2)
    t.noteer_bewolking(_moment(23, 59), 10.0, 0.0)
    t.last_deviation_percent = -30.0
    r = t._dagrecord(DAG)
    assert r["bewolking"] == 80.0
    assert r["bewolking_bron"] == "zonkwartieren"
    assert r["bewolking_middernacht"] == 10.0
    assert r["bewolking_zonkwartieren"] == 16


def test_oude_dagen_tellen_niet_mee_in_het_vak(hass):
    t = _tracker(hass)
    t.deviation_context = [
        {"datum": f"2026-10-{10 + i}", "afwijking": -40.0, "bewolking": 90.0}
        for i in range(SOLAR_BIAS_MIN_PER_VAK + 2)
    ]
    assert t.bias_voor_bewolking(90.0) is None
    vak = t.bewolkingsvakken()["bewolkt"]
    assert vak["dagen"] == 0
    assert vak["oude_dagen_apart"] == SOLAR_BIAS_MIN_PER_VAK + 2


def test_nieuwe_dagen_tellen_wel(hass):
    t = _tracker(hass)
    t.deviation_context = [
        {"datum": f"2026-11-{i + 1:02d}", "afwijking": -40.0, "bewolking": 90.0,
         "bewolking_bron": "zonkwartieren"}
        for i in range(SOLAR_BIAS_MIN_PER_VAK)
    ]
    assert t.bias_voor_bewolking(90.0) == -40.0


def test_coordinator_geeft_de_verwachte_zon_mee(make_coordinator, hass):
    c = make_coordinator({})
    t = _tracker(hass)
    c.solar_tracker = t
    nu = datetime.now(TZ).replace(second=0, microsecond=0)
    c._get_pv_forecast_entries = lambda: [(nu - timedelta(minutes=10), nu + timedelta(minutes=20), 0.4)]
    c._weather_cloud_cover_percent = lambda: 55.0
    assert c._pv_verwacht_nu_kwh(nu) == 0.4
    assert c._pv_verwacht_nu_kwh(nu + timedelta(hours=1)) is None
