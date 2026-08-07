"""Uitschieter-filter houdt rekening met de zonnestand (v1.3.1).

Het filter op de achtertuinsensor bestaat expliciet voor "kortstondig
direct zonlicht op de sensor". Tot v1.3.0 wist het niet of de zon
überhaupt scheen: een temperatuursprong om drie uur 's nachts kreeg
dezelfde behandeling, inclusief de melding dat het mogelijk zonlicht was.
Dat is aantoonbaar onjuist, en het kostte 45 minuten wachten voor iets
dat vrijwel zeker echt weer was.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    BACKYARD_SUN_EXPOSURE_MARGIN_DEGREES,
    BACKYARD_SUN_EXPOSURE_MIN_SAMPLES,
    BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES,
    BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES_NO_SUN,
    CONF_BACKYARD_TEMPERATURE_SENSOR,
    CONF_SUN_PHASE_SENSOR,
)

NOW = datetime(2026, 8, 7, 3, 0, tzinfo=timezone.utc)
SENSOR = "sensor.achtertuin"
FASE = "sensor.zon_fase"


def _coordinator(make_coordinator, hass, fase="night", azimut=None):
    c = make_coordinator(
        {
            CONF_BACKYARD_TEMPERATURE_SENSOR: SENSOR,
            CONF_SUN_PHASE_SENSOR: FASE,
        }
    )
    hass.states.set(FASE, fase)
    if azimut is not None:
        hass.states.set("sun.sun", "above_horizon", {"azimuth": azimut})
    return c


def _meet(c, hass, temp, minuten):
    hass.states.set(SENSOR, str(temp))
    return c._get_filtered_backyard_temp_c(NOW + timedelta(minutes=minuten))


# --- 's nachts is het geen zonneflits --------------------------------


def test_at_night_the_note_does_not_claim_sunlight(make_coordinator, hass):
    """De melding beweerde 's nachts iets dat aantoonbaar onmogelijk
    is."""
    c = _coordinator(make_coordinator, hass, fase="night")
    _meet(c, hass, 18.0, 0)

    _meet(c, hass, 26.0, 5)

    melding = c.last_backyard_spike_filtered_note
    assert "onder de horizon" in melding
    assert "direct zonlicht" not in melding


def test_at_night_the_wait_is_much_shorter(make_coordinator, hass):
    """45 minuten wachten voor iets dat geen zonneflits kán zijn is
    onnodig lang."""
    c = _coordinator(make_coordinator, hass, fase="night")
    _meet(c, hass, 18.0, 0)
    _meet(c, hass, 26.0, 5)

    resultaat = _meet(
        c, hass, 26.0, 5 + BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES_NO_SUN + 1
    )

    assert resultaat == 26.0


def test_by_day_the_full_window_still_applies(make_coordinator, hass):
    """Overdag kan het wél een flits zijn, dus daar blijft de
    voorzichtigheid staan."""
    c = _coordinator(make_coordinator, hass, fase="day", azimut=180.0)
    _meet(c, hass, 18.0, 0)
    _meet(c, hass, 30.0, 5)

    te_vroeg = _meet(
        c, hass, 30.0, 5 + BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES_NO_SUN + 1
    )
    assert te_vroeg == 18.0

    op_tijd = _meet(c, hass, 30.0, 5 + BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES + 1)
    assert op_tijd == 30.0


# --- geleerde blootstellingsrichting ---------------------------------


def test_the_exposure_direction_is_learned(make_coordinator, hass):
    """De integratie weet niet waar de sensor hangt; ernaar vragen zou
    een veld opleveren dat moeilijk goed in te vullen is. Dus leert hij
    het uit waar de flitsen vandaan kwamen."""
    c = _coordinator(make_coordinator, hass, fase="day", azimut=250.0)
    _meet(c, hass, 18.0, 0)

    # Twee opeenvolgende, niet-aanhoudende uitschieters: de eerste blijkt
    # een echte flits zodra de tweede een heel andere waarde heeft.
    _meet(c, hass, 30.0, 5)
    _meet(c, hass, 31.5, 10)

    assert c.backyard_sun_exposure_azimuths == [250.0]


def test_a_spike_from_another_direction_is_less_suspect(
    make_coordinator, hass
):
    """Staat de zon ver buiten de geleerde richting, dan is een sprong
    minder verdacht en hoeft er korter gewacht te worden."""
    c = _coordinator(make_coordinator, hass, fase="day", azimut=250.0)
    c.backyard_sun_exposure_azimuths = [250.0] * BACKYARD_SUN_EXPOSURE_MIN_SAMPLES

    # Zon nu in het oosten, ver van de geleerde westelijke richting.
    hass.states.set("sun.sun", "above_horizon", {"azimuth": 90.0})
    _meet(c, hass, 18.0, 0)
    _meet(c, hass, 26.0, 5)

    assert "ver buiten de richting" in c.last_backyard_spike_filtered_note


def test_a_spike_from_the_learned_direction_stays_suspect(
    make_coordinator, hass
):
    c = _coordinator(make_coordinator, hass, fase="day", azimut=250.0)
    c.backyard_sun_exposure_azimuths = [250.0] * BACKYARD_SUN_EXPOSURE_MIN_SAMPLES
    _meet(c, hass, 18.0, 0)

    _meet(c, hass, 30.0, 5)

    assert "direct zonlicht" in c.last_backyard_spike_filtered_note


def test_the_azimuth_distance_wraps_around(make_coordinator, hass):
    """350° en 10° liggen 20 graden uit elkaar, niet 340 - anders zou een
    sensor die op het noorden staat nooit herkend worden."""
    c = _coordinator(make_coordinator, hass, fase="day")
    c.backyard_sun_exposure_azimuths = [350.0] * BACKYARD_SUN_EXPOSURE_MIN_SAMPLES
    hass.states.set("sun.sun", "above_horizon", {"azimuth": 10.0})

    mogelijk, _ = c._sun_could_hit_the_backyard_sensor()

    assert mogelijk is True


def test_too_few_samples_means_no_conclusion(make_coordinator, hass):
    """Met te weinig geleerde flitsen mag de richting niets bepalen."""
    c = _coordinator(make_coordinator, hass, fase="day", azimut=90.0)
    c.backyard_sun_exposure_azimuths = [250.0]

    mogelijk, reden = c._sun_could_hit_the_backyard_sensor()

    assert mogelijk is True
    assert "direct zonlicht" in reden


def test_nothing_is_learned_at_night(make_coordinator, hass):
    """Een azimut 's nachts zegt niets over blootstelling aan zon."""
    c = _coordinator(make_coordinator, hass, fase="night")
    hass.states.set("sun.sun", "below_horizon", {"azimuth": 20.0})

    c._record_backyard_sun_exposure()

    assert c.backyard_sun_exposure_azimuths == []


def test_without_sun_data_the_old_behaviour_returns(make_coordinator, hass):
    """Zonder zonnestand het oude gedrag aanhouden in plaats van te
    gokken."""
    c = make_coordinator({CONF_BACKYARD_TEMPERATURE_SENSOR: SENSOR})

    mogelijk, reden = c._sun_could_hit_the_backyard_sensor()

    assert mogelijk is True
    assert "direct zonlicht" in reden


def test_the_learned_exposure_survives_a_restart(make_coordinator, hass):
    """Vijf flitsen zijn nodig voordat de richting iets doet - zonder
    bewaren zou die telling na elke herstart opnieuw beginnen."""
    import asyncio

    bron = _coordinator(make_coordinator, hass)
    bron.backyard_sun_exposure_azimuths = [250.0, 255.0]
    asyncio.run(bron.async_save_persisted_state_now())

    verse = _coordinator(make_coordinator, hass)
    asyncio.run(verse.async_load_persisted_state())

    assert verse.backyard_sun_exposure_azimuths == [250.0, 255.0]


def test_a_real_sun_flash_is_still_ignored(make_coordinator, hass):
    """Het filter mag zijn functie niet verliezen."""
    c = _coordinator(make_coordinator, hass, fase="day", azimut=250.0)
    _meet(c, hass, 24.0, 0)

    assert _meet(c, hass, 34.0, 5) == 24.0
