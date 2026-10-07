"""Tekortdag als één gekoppelde meting (v5.33).

Gemeten over 30 september - 6 oktober (P1 per uur naast de reden en het
dagrecord):

    1 okt   ochtend 37%, 0,56 kWh bijgekocht 22-24 uur onder
            `battery_saved_for_peak`      -> telde als tekort (onterecht)
    2 okt   ochtend 9%, 1,87 kWh bijgekocht in `default_smart`
                                          -> telde niet (gemist)

Een tekort is netafname terwijl de accu LEEG is en de reden geen bewuste
netafname is. Vasthouden boven de vloer is sparen, geen tekort.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import (
    PERSISTED_PLAIN_FIELDS,
    RESERVE_EXCESS_RATIO_THRESHOLD,
    SMART_MAX_DISCHARGE_W,
)

TZ = timezone.utc


def _opzet(c, hass, *, net_w, soc, min_soc=10, reden="default_smart"):
    hass.states.set("sensor.net", str(net_w))
    hass.states.set("sensor.soc", str(soc))
    hass.states.set("number.min_soc", str(min_soc))
    c.config = dict(c.config or {})
    c.config["consumption_power_sensor_entity"] = "sensor.net"
    c.config["battery_soc_sensor_entity"] = "sensor.soc"
    c.config["battery_min_soc_number_entity"] = "number.min_soc"
    c.last_reason = reden
    c.piekverkoop_tot = None


def _nacht(c, begin, uren, stap_min=1):
    """Draait de ochtendmeting elke minuut over `uren` uur."""
    for i in range(int(uren * 60 / stap_min) + 1):
        c._volg_de_ochtend(begin + timedelta(minutes=i * stap_min))


def test_lege_accu_in_default_smart_is_een_tekort(make_coordinator, hass):
    """2 oktober: 9% op een vloer van 10%, de hele nacht import."""
    c = make_coordinator({})
    _opzet(c, hass, net_w=250, soc=9)
    _nacht(c, datetime(2026, 10, 2, 1, 0, tzinfo=TZ), 8)
    c._volg_de_ochtend(datetime(2026, 10, 2, 9, 5, tzinfo=TZ))

    assert c._tekortnacht_vandaag_kwh == pytest.approx(2.0, abs=0.05)
    assert c._telt_als_tekortdag(c._tekortnacht_vandaag_kwh) is True


def test_vasthouden_boven_de_vloer_is_geen_tekort(make_coordinator, hass):
    """1 oktober: 37% in de accu, bewust vastgehouden voor de piek."""
    c = make_coordinator({})
    _opzet(c, hass, net_w=280, soc=37, reden="battery_saved_for_peak")
    _nacht(c, datetime(2026, 10, 1, 22, 0, tzinfo=TZ), 2)

    assert c._tekortnacht_lopend_kwh == pytest.approx(0.0)
    # de oude, ongefilterde meting telt het wel
    assert c._netimport_nacht_kwh > 0.5


@pytest.mark.parametrize(
    "reden", ["grid_charging_profitable", "grid_charging_dip", "negative_price", "force_manual"]
)
def test_bewust_netladen_is_nooit_een_tekort(make_coordinator, hass, reden):
    c = make_coordinator({})
    _opzet(c, hass, net_w=2400, soc=8, reden=reden)
    _nacht(c, datetime(2026, 10, 3, 2, 0, tzinfo=TZ), 1)

    assert c._tekortnacht_lopend_kwh == pytest.approx(0.0)


def test_na_een_piekverkoop_is_import_afgesproken(make_coordinator, hass):
    c = make_coordinator({})
    _opzet(c, hass, net_w=300, soc=9)
    c.piekverkoop_tot = datetime(2026, 10, 3, 11, 0, tzinfo=TZ).isoformat()
    _nacht(c, datetime(2026, 10, 3, 2, 0, tzinfo=TZ), 1)

    assert c._tekortnacht_lopend_kwh == pytest.approx(0.0)


def test_de_nacht_loopt_over_middernacht_door(make_coordinator, hass):
    """22-24 en 00-09 zijn één nacht; die hoort bij de ochtend erna."""
    c = make_coordinator({})
    _opzet(c, hass, net_w=300, soc=9)
    _nacht(c, datetime(2026, 10, 3, 23, 0, tzinfo=TZ), 1)  # 23:00-00:00
    # middernacht: de dag wordt afgesloten, de lopende nacht niet
    c._shortfall_check_date = datetime(2026, 10, 3, tzinfo=TZ).date()
    c._update_shortfall_detection(
        datetime(2026, 10, 4, 0, 1, tzinfo=TZ), "default_smart", None, None
    )
    assert c._tekortnacht_lopend_kwh == pytest.approx(0.3, abs=0.02)
    _nacht(c, datetime(2026, 10, 4, 0, 1, tzinfo=TZ), 1)
    c._volg_de_ochtend(datetime(2026, 10, 4, 9, 0, tzinfo=TZ))

    assert c._tekortnacht_vandaag_kwh == pytest.approx(0.6, abs=0.03)
    assert c._tekortnacht_lopend_kwh is None


def test_het_dagrecord_gebruikt_de_gekoppelde_meting(make_coordinator, hass):
    """De oude vlag aan en veel netafname, maar geen lege accu: geen
    tekortdag. Andersom: vlag uit, lege accu en bijgekocht: wel."""
    c = make_coordinator({})
    dag = datetime(2026, 10, 1, tzinfo=TZ).date()

    c._shortfall_check_date = dag
    c._shortfall_detected_today = True
    c._netimport_nacht_kwh = 0.79
    c._tekortnacht_vandaag_kwh = 0.0
    c._update_shortfall_detection(
        datetime(2026, 10, 2, 0, 0, tzinfo=TZ), "default_smart", None, None
    )
    assert c.reserve_daily_records[-1]["shortfall"] is False
    assert c.reserve_daily_records[-1]["tekortvlag"] is True

    c._shortfall_detected_today = False
    c._tekortnacht_vandaag_kwh = 1.87
    c._update_shortfall_detection(
        datetime(2026, 10, 3, 0, 0, tzinfo=TZ), "default_smart", None, None
    )
    assert c.reserve_daily_records[-1]["shortfall"] is True
    assert c.reserve_daily_records[-1]["tekortnacht_kwh"] == 1.87


def test_de_maandtelling_volgt_het_dagrecord(make_coordinator, hass):
    c = make_coordinator({})
    c._shortfall_check_date = datetime(2026, 10, 1, tzinfo=TZ).date()
    c._shortfall_detected_today = True
    c._tekortnacht_vandaag_kwh = 0.0
    voor = c.current_month_shortfall_days
    c._update_shortfall_detection(
        datetime(2026, 10, 2, 0, 0, tzinfo=TZ), "default_smart", None, None
    )
    assert c.current_month_shortfall_days == voor


def test_de_meting_overleeft_een_herstart():
    assert "_tekortnacht_lopend_kwh" in PERSISTED_PLAIN_FIELDS
    assert "_tekortnacht_vandaag_kwh" in PERSISTED_PLAIN_FIELDS


def test_opgeslagen_dagen_worden_naar_twee_kanten_herbeoordeeld(
    make_coordinator, hass
):
    """De echte records van 30 september - 6 oktober."""
    c = make_coordinator({})
    hass.states.set("number.min_soc", "10")
    c.config = dict(c.config or {})
    c.config["battery_min_soc_number_entity"] = "number.min_soc"
    c.reserve_daily_records = [
        {"date": "2026-09-30", "shortfall": True, "laagste_soc_ochtend": 7, "netimport_nacht_kwh": 1.44, "excess": False},
        {"date": "2026-10-01", "shortfall": True, "laagste_soc_ochtend": 37, "netimport_nacht_kwh": 0.79, "excess": False},
        {"date": "2026-10-02", "shortfall": False, "laagste_soc_ochtend": 9, "netimport_nacht_kwh": 1.88, "excess": False},
        {"date": "2026-10-03", "shortfall": True, "laagste_soc_ochtend": 9, "netimport_nacht_kwh": 0.68, "excess": False},
        {"date": "2026-10-04", "shortfall": True, "laagste_soc_ochtend": 9, "netimport_nacht_kwh": 1.68, "excess": False},
        {"date": "2026-10-05", "shortfall": False, "laagste_soc_ochtend": 30, "netimport_nacht_kwh": 0.46, "excess": False},
        {"date": "2026-10-06", "shortfall": False, "laagste_soc_ochtend": 24, "netimport_nacht_kwh": 0.18, "excess": False},
    ]

    c._herbeoordeel_tekortdagen()

    assert c.reserve_shortfall_history == [True, False, True, True, True, False, False]
    assert c.reserve_daily_records[1]["herbeoordeeld"] == "v5.33"
    assert c.reserve_daily_records[2]["herbeoordeeld"] == "v5.33"
    # nogmaals draaien verandert niets
    c._herbeoordeel_tekortdagen()
    assert c.reserve_shortfall_history == [True, False, True, True, True, False, False]


def test_nieuwe_records_worden_niet_herbeoordeeld(make_coordinator, hass):
    c = make_coordinator({})
    c.reserve_daily_records = [
        {"date": "2026-10-08", "shortfall": False, "tekortnacht_kwh": 0.1,
         "laagste_soc_ochtend": 5, "netimport_nacht_kwh": 3.0, "excess": False},
    ]
    c._herbeoordeel_tekortdagen()
    assert c.reserve_daily_records[0]["shortfall"] is False


def test_de_overschotkant_kan_weer_optreden():
    """Bij 3,0 trad hij in zeven dagen nul keer op; de marge kon alleen
    stijgen."""
    assert RESERVE_EXCESS_RATIO_THRESHOLD == 1.5


def test_de_slimme_ontlaadgrens_komt_van_de_omvormer(make_coordinator, hass):
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["battery_max_discharge_power_entity"] = "sensor.inverse_max"

    hass.states.set("sensor.inverse_max", "2400")
    assert c.slimme_ontlaadgrens_w() == 2400.0

    hass.states.set("sensor.inverse_max", "unavailable")
    assert c.slimme_ontlaadgrens_w() == SMART_MAX_DISCHARGE_W


def test_met_2400_w_telt_2000_w_niet_meer_als_de_grens(make_coordinator, hass):
    c = make_coordinator({})
    hass.states.set("sensor.inverse_max", "2400")
    hass.states.set("sensor.accu", "2000")
    c.config = dict(c.config or {})
    c.config["battery_max_discharge_power_entity"] = "sensor.inverse_max"
    c.config["battery_power_sensor_entity"] = "sensor.accu"
    c.piekverkoop_tot = None

    assert c._import_verklaard_door_ontlaadgrens("default_smart") is False
    hass.states.set("sensor.accu", "2350")
    assert c._import_verklaard_door_ontlaadgrens("default_smart") is True
