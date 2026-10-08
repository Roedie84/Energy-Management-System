"""Watersensoren in liters, en een nieuwe dag alleen bij een echte dagwissel
(v5.47).

Gemeten op 8 oktober: `sensor.water_verbruik_vandaag` (utility_meter) meldt na
elke herstart eerst 0,060 m³ en direct daarna weer 60 L. EMS las het getal
zonder eenheid: `vandaag_liter` 0,06, trend -100%, het verhaal "0 L". En een
sprong 52 L -> 0,052 m³ is een daling, die als nieuwe dag werd gearchiveerd.
"""
from datetime import datetime, timedelta, timezone

import pytest

# 08-10 09:01 lokaal (07:01 UTC)
NU = datetime(2026, 10, 8, 7, 1, tzinfo=timezone.utc)
RESET = "2026-10-07T22:00:00.008287+00:00"


def _c(make_coordinator, **extra):
    config = {
        "water_daily_total_sensor_entity": "sensor.water_verbruik_vandaag",
        "water_active_usage_sensor_entity": "sensor.watermeter_active_water_usage",
        "water_total_usage_sensor_entity": "sensor.watermeter_total_water_usage",
    }
    config.update(extra)
    return make_coordinator(config)


def _dag(hass, waarde, eenheid, reset=RESET):
    hass.states.set(
        "sensor.water_verbruik_vandaag",
        waarde,
        {"unit_of_measurement": eenheid, "last_reset": reset, "device_class": "water"},
    )


def test_m3_wordt_liter(make_coordinator, hass):
    c = _c(make_coordinator)
    _dag(hass, "0.060", "m³")

    c._update_water_tracking(NU)

    assert c.water_daily_total_l == 60.0


def test_de_eenheidssprong_na_een_herstart_maakt_geen_nepdag(make_coordinator, hass):
    c = _c(make_coordinator)
    _dag(hass, "52.0", "L")
    c._update_water_tracking(NU)
    _dag(hass, "0.052", "m³")
    c._update_water_tracking(NU + timedelta(seconds=1))
    _dag(hass, "52.0", "L")
    c._update_water_tracking(NU + timedelta(seconds=2))

    assert c.water_daily_history == []
    assert c.water_daily_total_l == 52.0


def test_een_daling_zonder_dagwissel_is_geen_nieuwe_dag(make_coordinator, hass):
    """Ook als de eenheid niet de oorzaak is (meter corrigeert): dezelfde
    last_reset betekent dezelfde dag."""
    c = _c(make_coordinator)
    _dag(hass, "52.0", "L")
    c._update_water_tracking(NU)
    _dag(hass, "0.4", "L")
    c._update_water_tracking(NU + timedelta(minutes=5))

    assert c.water_daily_history == []


def test_een_nieuwe_last_reset_archiveert_wel(make_coordinator, hass):
    c = _c(make_coordinator)
    _dag(hass, "357.0", "L")
    c._update_water_tracking(NU)
    _dag(hass, "0.0", "L", reset="2026-10-08T22:00:00+00:00")
    c._update_water_tracking(NU + timedelta(hours=15))

    assert c.water_daily_history == [357.0]


def test_zonder_last_reset_telt_de_datum(make_coordinator, hass):
    c = _c(make_coordinator)
    hass.states.set("sensor.water_verbruik_vandaag", "300.0", {"unit_of_measurement": "L"})
    c._update_water_tracking(datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc))
    hass.states.set("sensor.water_verbruik_vandaag", "1.0", {"unit_of_measurement": "L"})
    c._update_water_tracking(datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc))

    assert c.water_daily_history == [300.0]


def test_sensor_attributen_tonen_liters_en_geen_min_honderd_procent(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import WaterUsageSensor

    c = _c(make_coordinator)
    c.water_daily_history = [443.06, 332.04, 509.95, 391.02, 386.81, 357.0]
    _dag(hass, "0.060", "m³")
    c._update_water_tracking(NU)

    a = WaterUsageSensor(c, "x").extra_state_attributes

    assert a["vandaag_liter"] == 60.0
    assert a["trend_procent"] > -100


def test_gallons_worden_liter(make_coordinator, hass):
    c = _c(make_coordinator)
    _dag(hass, "10", "gal")

    c._update_water_tracking(NU)

    assert c.water_daily_total_l == pytest.approx(37.85, abs=0.01)


def test_zonder_eenheid_blijft_het_dagtotaal_liters(make_coordinator, hass):
    c = _c(make_coordinator)
    hass.states.set("sensor.water_verbruik_vandaag", "60")

    c._update_water_tracking(NU)

    assert c.water_daily_total_l == 60.0


# --- meterstand en debiet --------------------------------------------------

def test_de_meterstand_in_liters_wordt_m3(make_coordinator, hass):
    c = _c(make_coordinator)
    hass.states.set(
        "sensor.watermeter_total_water_usage", "488037", {"unit_of_measurement": "L"}
    )
    assert c._read_water_volume_l("sensor.watermeter_total_water_usage", "m³") == 488037.0
    hass.states.set(
        "sensor.watermeter_total_water_usage", "488.037", {"unit_of_measurement": "m³"}
    )
    assert c._read_water_volume_l("sensor.watermeter_total_water_usage", "m³") == pytest.approx(488037.0)
    # Zonder eenheid: m³, zoals altijd aangenomen.
    hass.states.set("sensor.watermeter_total_water_usage", "488.037")
    assert c._read_water_volume_l("sensor.watermeter_total_water_usage", "m³") == pytest.approx(488037.0)


def test_een_sessie_in_liters_meet_hetzelfde_als_in_m3(make_coordinator, hass):
    """Begin in m³, eind in L (eenheidswissel midden in een douche)."""
    c = _c(make_coordinator)
    start = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)
    hass.states.set(
        "sensor.watermeter_total_water_usage", "488.000", {"unit_of_measurement": "m³"}
    )
    c._process_water_flow_sample(8.0, start)
    assert c._water_session_start_total_m3 == pytest.approx(488.0)
    hass.states.set(
        "sensor.watermeter_total_water_usage", "488040", {"unit_of_measurement": "L"}
    )
    c._water_session_liters_integrated = 0.0
    c._water_last_flow_l_per_min = None
    c._process_water_flow_sample(0.0, start + timedelta(minutes=5))
    c._process_water_flow_sample(0.0, start + timedelta(minutes=30))

    sessie = c.water_session_history[-1]
    volume = next(v for k, v in sessie.items() if "liter" in k and v is not None)
    assert volume == pytest.approx(40.0, abs=0.5)


def test_debiet_in_m3_per_uur(make_coordinator, hass):
    c = _c(make_coordinator)
    hass.states.set(
        "sensor.watermeter_active_water_usage", "0.6", {"unit_of_measurement": "m³/h"}
    )

    assert c._read_water_flow_l_per_min("sensor.watermeter_active_water_usage") == pytest.approx(10.0)


def test_debiet_in_l_per_min_blijft(make_coordinator, hass):
    c = _c(make_coordinator)
    hass.states.set(
        "sensor.watermeter_active_water_usage", "7.5", {"unit_of_measurement": "L/min"}
    )

    assert c._read_water_flow_l_per_min("sensor.watermeter_active_water_usage") == 7.5


def test_de_live_listener_rekent_ook_om(make_coordinator, hass):
    c = _c(make_coordinator)
    gezien = []
    c._process_water_flow_sample = lambda flow, now: gezien.append(flow)

    class _S:
        state = "0.6"
        attributes = {"unit_of_measurement": "m³/h"}
        last_changed = NU

    class _E:
        data = {"new_state": _S()}

    c._handle_water_flow_change(_E())

    assert gezien == [pytest.approx(10.0)]
