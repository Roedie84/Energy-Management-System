"""Daglicht-poort op basis van de zonnestand (v1.3.0).

Gevraagd: "Ik heb de sun integratie in HA, kan dit nog helpen bij
verbeteringen?"

De belangrijkste toepassing repareert een blinde vlek uit v1.1.9. Daar
wordt de meetfrequentie van de PV-sensor overgeslagen als die op nul
staat, omdat de nacht het cijfer vertekende. Maar dat gebruikt de sensor
ZELF als criterium: hangt de koppeling er midden op de dag uit, dan is de
waarde 0, concludeert de code "geen zon dus terecht stil", en blijft de
storing volledig onzichtbaar.
"""
from custom_components.energy_management_system.const import (
    CONF_PV_POWER_SENSOR,
    CONF_SUN_ELEVATION_SENSOR,
    CONF_SUN_PHASE_SENSOR,
    SENSOR_CADENCE_MIN_SAMPLES,
    SUN_DAYLIGHT_MIN_ELEVATION_DEGREES,
)

HOOGTE = "sensor.zon_van_eibergen_hoogtehoek"
FASE = "sensor.zon_van_eibergen_fase"


# --- de gerepareerde blinde vlek -------------------------------------


def test_a_stuck_pv_sensor_is_now_visible(make_coordinator, hass):
    """De kern: PV-sensor hangt op 0 W terwijl de zon hoog staat. Dat
    hoort als 'traag' op te vallen, niet weggemoffeld te worden."""
    c = make_coordinator(
        {
            CONF_PV_POWER_SENSOR: "sensor.pv",
            CONF_SUN_ELEVATION_SENSOR: HOOGTE,
        }
    )
    hass.states.set(HOOGTE, "45.0")

    for _ in range(SENSOR_CADENCE_MIN_SAMPLES + 5):
        hass.states.set("sensor.pv", "0")
        c._update_sensor_cadence_tracking()

    rapport = c.get_sensor_cadence_report()["sensor.pv"]
    assert rapport["status"] == "traag"
    assert rapport["beweegt_percent"] == 0.0


def test_night_is_still_skipped(make_coordinator, hass):
    """De oorspronkelijke correctie moet blijven werken: 's nachts telt
    de PV-sensor niet mee."""
    c = make_coordinator(
        {
            CONF_PV_POWER_SENSOR: "sensor.pv",
            CONF_SUN_ELEVATION_SENSOR: HOOGTE,
        }
    )
    hass.states.set(HOOGTE, "-12.0")

    for _ in range(50):
        hass.states.set("sensor.pv", "0")
        c._update_sensor_cadence_tracking()

    assert "sensor.pv" not in c.sensor_cadence


# --- bronvolgorde ----------------------------------------------------


def test_the_phase_sensor_wins(make_coordinator, hass):
    """De fase-sensor geeft een schone opsomming, dus er hoeft geen
    eigen drempel gekozen te worden."""
    c = make_coordinator(
        {CONF_SUN_PHASE_SENSOR: FASE, CONF_SUN_ELEVATION_SENSOR: HOOGTE}
    )
    hass.states.set(FASE, "day")
    hass.states.set(HOOGTE, "-30.0")

    assert c.is_daylight_now() is True


def test_twilight_is_not_daylight(make_coordinator, hass):
    c = make_coordinator({CONF_SUN_PHASE_SENSOR: FASE})
    hass.states.set(FASE, "civil_twilight")

    assert c.is_daylight_now() is False


def test_the_elevation_sensor_is_used_next(make_coordinator, hass):
    c = make_coordinator({CONF_SUN_ELEVATION_SENSOR: HOOGTE})
    hass.states.set(HOOGTE, str(SUN_DAYLIGHT_MIN_ELEVATION_DEGREES + 1))

    assert c.is_daylight_now() is True

    hass.states.set(HOOGTE, str(SUN_DAYLIGHT_MIN_ELEVATION_DEGREES - 1))
    assert c.is_daylight_now() is False


def test_sun_dot_sun_is_the_safety_net(make_coordinator, hass):
    """`sun.sun` zit standaard in Home Assistant en vereist geen opzet -
    zo stopt de meting niet stilzwijgend als de eigen bron wegvalt."""
    c = make_coordinator({})
    hass.states.set("sun.sun", "above_horizon", {"elevation": 30.0})

    assert c.get_sun_elevation_degrees() == 30.0
    assert c.is_daylight_now() is True


def test_it_falls_back_to_the_state_without_elevation(make_coordinator, hass):
    c = make_coordinator({})
    hass.states.set("sun.sun", "below_horizon", {})

    assert c.is_daylight_now() is False


def test_without_any_source_it_says_unknown(make_coordinator, hass):
    """None betekent "niet vast te stellen" - de aanroeper hoort dan
    terug te vallen op het oude gedrag in plaats van te gokken."""
    c = make_coordinator({})

    assert c.is_daylight_now() is None


def test_without_sun_data_the_old_behaviour_returns(make_coordinator, hass):
    c = make_coordinator({CONF_PV_POWER_SENSOR: "sensor.pv"})
    hass.states.set("sensor.pv", "0")

    for _ in range(50):
        c._update_sensor_cadence_tracking()

    assert "sensor.pv" not in c.sensor_cadence


def test_an_unreadable_own_sensor_falls_through(make_coordinator, hass):
    c = make_coordinator({CONF_SUN_ELEVATION_SENSOR: HOOGTE})
    hass.states.set(HOOGTE, "unavailable")
    hass.states.set("sun.sun", "above_horizon", {"elevation": 25.0})

    assert c.get_sun_elevation_degrees() == 25.0
