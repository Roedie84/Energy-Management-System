"""Zon-export of accu-export? Meten in plaats van aannemen (v1.76.0).

Gevonden bij de volledige controle van 13 augustus: zelfconsumptie stond
op 100,0% terwijl er 1,04 kWh was teruggeleverd bij 2,29 kWh opwek.

De berekening trok eerst de hele dagontlading van de export af - en
omdat de accu die dag 2,47 kWh had geleverd, bleef er niets over als
zon-export. Die aanname is achteraf niet toetsbaar: met alleen
dagtotalen is "alle export kwam uit de accu" net zo consistent met de
energiebalans als "alle export was zon".
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_PV_POWER_SENSOR,
)

NU = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass):
    c = make_coordinator(
        {
            CONF_PV_POWER_SENSOR: "sensor.pv",
            CONF_CONSUMPTION_POWER_SENSOR: "sensor.p1",
        }
    )
    return c


def _tick(c, hass, pv_w, p1_w, accu_w=0.0, moment=NU):
    """accu_w positief = ontladen."""
    hass.states.set("sensor.pv", str(pv_w))
    hass.states.set("sensor.p1", str(p1_w))
    c._read_corrected_battery_power = lambda: accu_w
    c.is_battery_discharging = lambda: accu_w > 0
    c._update_self_sufficiency_tracking(moment)


def test_solar_surplus_counts_as_solar_export(make_coordinator, hass):
    """Is de zon groter dan wat het huis vraagt, dan gaat dat overschot
    het net op - ongeacht wat de accu ondertussen doet."""
    c = _coordinator(make_coordinator, hass)
    _tick(c, hass, 3000, -2000, moment=NU)
    _tick(c, hass, 3000, -2000, moment=NU + timedelta(minutes=15))

    assert c.solar_export_today_kwh > 0
    assert c.battery_export_today_kwh == 0


def test_export_without_sun_is_battery_export(make_coordinator, hass):
    """'s Avonds verkopen uit de accu is geen zon-export."""
    c = _coordinator(make_coordinator, hass)
    _tick(c, hass, 0, -1600, accu_w=1600, moment=NU)
    _tick(c, hass, 0, -1600, accu_w=1600, moment=NU + timedelta(minutes=15))

    assert c.solar_export_today_kwh == 0
    assert c.battery_export_today_kwh > 0


def test_the_two_add_up_to_the_total(make_coordinator, hass):
    """De splitsing mag niets kwijtraken of verzinnen."""
    c = _coordinator(make_coordinator, hass)
    _tick(c, hass, 2500, -1800, moment=NU)
    _tick(c, hass, 500, -1200, accu_w=700, moment=NU + timedelta(minutes=15))
    _tick(c, hass, 0, -1600, accu_w=1600, moment=NU + timedelta(minutes=30))

    totaal = c.solar_export_today_kwh + c.battery_export_today_kwh
    assert abs(totaal - c.pv_export_today_kwh) < 0.001


def test_the_reported_case_no_longer_says_hundred_percent(
    make_coordinator, hass
):
    """De cijfers van 13 augustus 10:31: 2,29 kWh opwek, 1,04 kWh export,
    2,47 kWh accu-ontlading. Dat gaf 100,0%."""
    c = _coordinator(make_coordinator, hass)
    c.pv_production_today_kwh = 2.287
    c.pv_export_today_kwh = 1.044
    c.battery_discharge_today_kwh = 2.467
    # Gemeten: de export viel samen met zonoverschot.
    c.solar_export_today_kwh = 1.044
    c.battery_export_today_kwh = 0.0

    assert c.self_consumption_ratio_percent == 54.4


def test_without_a_pv_power_sensor_the_old_assumption_remains(
    make_coordinator, hass
):
    """Zonder PV-vermogenssensor valt er niets te splitsen; dan blijft de
    oude afleiding staan in plaats van een verzonnen nul."""
    c = make_coordinator({})
    c.pv_production_today_kwh = 2.287
    c.pv_export_today_kwh = 1.044
    c.battery_discharge_today_kwh = 2.467

    assert c.self_consumption_ratio_percent == 100.0


def test_a_half_measured_day_is_not_used(make_coordinator, hass):
    """Loopt de splitsing pas sinds vanmiddag, dan is hij geen volledig
    beeld van de dag - en dan liever de oude afleiding."""
    c = _coordinator(make_coordinator, hass)
    c.pv_production_today_kwh = 2.287
    c.pv_export_today_kwh = 1.044
    c.battery_discharge_today_kwh = 2.467
    c.solar_export_today_kwh = 0.2
    c.battery_export_today_kwh = 0.0

    assert c._solar_export_gemeten() is False


def test_the_split_survives_a_restart():
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "solar_export_today_kwh" in PERSISTED_PLAIN_FIELDS
    assert "battery_export_today_kwh" in PERSISTED_PLAIN_FIELDS


def test_both_at_once_is_split_correctly(make_coordinator, hass):
    """Zon en accu tegelijk het net op: de accu kan niet meer leveren dan
    hij op dat moment doet, de rest is zon."""
    c = _coordinator(make_coordinator, hass)
    _tick(c, hass, 3000, -2500, accu_w=1000, moment=NU)
    _tick(c, hass, 3000, -2500, accu_w=1000, moment=NU + timedelta(minutes=15))

    verhouding = c.battery_export_today_kwh / c.pv_export_today_kwh
    assert abs(verhouding - 1000 / 2500) < 0.01


def test_a_charging_battery_never_exports(make_coordinator, hass):
    """Laadt de accu, dan is alle export per definitie zon."""
    c = _coordinator(make_coordinator, hass)
    _tick(c, hass, 4000, -1500, accu_w=-2000, moment=NU)
    _tick(c, hass, 4000, -1500, accu_w=-2000, moment=NU + timedelta(minutes=15))

    assert c.battery_export_today_kwh == 0
    assert c.solar_export_today_kwh > 0
