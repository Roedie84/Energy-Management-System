"""v5.176.3 (L-EMS-060) - bewolking van vandaag overleeft een herstart, en een
daglabel vraagt dekking.

03-11: na de herstarts van 14:58 en 15:36 stonden nog 3 kwartieren in
`bewolking_vandaag` (08:15, 15:30, 15:45); vanaf 16:00 was de drempel van 4
gehaald en kreeg de dag een label op alleen de late middag.
"""
from datetime import date, datetime, timedelta, timezone

import custom_components.energy_management_system.solar_forecast as sfm
from custom_components.energy_management_system.const import (
    CONF_SOLAR_ACTUAL_SENSOR,
    CONF_SOLAR_FORECAST_SENSOR,
)

TZ = timezone(timedelta(hours=1))
DAG = date(2026, 11, 3)


def _tracker(hass):
    return sfm.SolarForecastAccuracyTracker(
        hass, {CONF_SOLAR_FORECAST_SENSOR: "sensor.solcast", CONF_SOLAR_ACTUAL_SENSOR: "sensor.pv"}
    )


def _moment(uur, minuut=0):
    return datetime(2026, 11, 3, uur, minuut, tzinfo=TZ)


def test_nieuw_kwartier_schrijft_eenmaal(hass):
    t = _tracker(hass)
    geteld = []
    t.register_listener(lambda: geteld.append(1))
    t.noteer_bewolking(_moment(12, 0), 50.0, 0.2)
    t.noteer_bewolking(_moment(12, 5), 60.0, 0.2)
    t.noteer_bewolking(_moment(12, 14), 70.0, 0.2)
    assert len(geteld) == 1
    t.noteer_bewolking(_moment(12, 15), 70.0, 0.2)
    assert len(geteld) == 2


def test_geen_zon_schrijft_niet(hass):
    t = _tracker(hass)
    geteld = []
    t.register_listener(lambda: geteld.append(1))
    t.noteer_bewolking(_moment(23, 0), 50.0, 0.0)
    t.noteer_bewolking(_moment(23, 15), None, 0.2)
    assert geteld == []


def _vergeleken(t, verwacht):
    t.last_predicted_kwh = verwacht
    t.last_compared_date = DAG


def test_03_11_alleen_late_middag_geeft_geen_label(hass):
    t = _tracker(hass)
    # De vier kwartieren die overbleven, met weinig zon; verwacht 7,69 kWh
    for uur, minuut in ((8, 15), (15, 30), (15, 45), (16, 0)):
        t.noteer_bewolking(_moment(uur, minuut), 40.0, 0.05)
    _vergeleken(t, 7.69)
    assert t.bewolking_van_de_dag(DAG) is None


def test_hele_dag_geeft_wel_label(hass):
    t = _tracker(hass)
    for kw in range(9 * 4, 15 * 4):
        t.noteer_bewolking(_moment(kw // 4, kw % 4 * 15), 80.0, 0.4)
    _vergeleken(t, 7.69)
    assert t.bewolking_van_de_dag(DAG) == 80.0


def test_precies_op_de_grens_telt(hass):
    t = _tracker(hass)
    for kw in range(10 * 4, 11 * 4):
        t.noteer_bewolking(_moment(kw // 4, kw % 4 * 15), 80.0, 0.5)
    # 4 kwartieren x 0,5 / 2 = 1,0 kWh van de 2,0 verwacht
    _vergeleken(t, 2.0)
    assert t.bewolking_van_de_dag(DAG) == 80.0
    _vergeleken(t, 2.01)
    assert t.bewolking_van_de_dag(DAG) is None


def test_zonder_dagverwachting_alleen_het_aantal(hass):
    t = _tracker(hass)
    for uur, minuut in ((8, 15), (15, 30), (15, 45), (16, 0)):
        t.noteer_bewolking(_moment(uur, minuut), 40.0, 0.05)
    assert t.bewolking_van_de_dag(DAG) == 40.0
