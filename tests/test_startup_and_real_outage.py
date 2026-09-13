"""Aanlooptijd en aanhoudende uitval (v1.11.0).

Gemeld: "sensor.zendure_manager_available_kwh heeft langer nodig om op te
starten, als HA is geherstart dient er dus rekening mee gehouden te
worden. Ik wil dat na een herstart niet mee telt in analyses van sensor
kwaliteit en de melding ook pas laten komen als hij ECHT onbeschikbaar
zou zijn."

In de bijbehorende export stond de score op 70% ("verminderd") terwijl
alle veertien werkelijke vergelijkingen binnen de marge vielen (4 tot 110
W). De zes ontbrekende metingen stonden aaneengesloten aan het eind van
de reeks - precies de opstartperiode.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_APPLIANCE_NOTIFY_SERVICE,
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    SENSOR_STARTUP_GRACE_MINUTES,
    SENSOR_UNAVAILABLE_CONFIRM_MINUTES,
)

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
ACCU = "sensor.zendure_manager_available_kwh"


def _ronde(c, moment):
    """Draait de meldingsronde met een bevroren klok.

    `_dispatch_notification` gebruikt intern `dt_util.now()` voor het
    dempingsvenster en de aanlooptijd; zonder bevriezing loopt die uit
    de pas met het moment dat de test hanteert, en dan wordt de melding
    als "nog in de aanlooptijd" geweigerd.
    """
    from custom_components.energy_management_system import coordinator as mod

    origineel = mod.dt_util.now
    try:
        mod.dt_util.now = lambda: moment
        c._evaluate_new_notifications(moment)
    finally:
        mod.dt_util.now = origineel


def _coordinator(make_coordinator, hass):
    c = make_coordinator(
        {
            CONF_AVAILABLE_ENERGY_SENSOR: ACCU,
            CONF_BATTERY_POWER_SENSOR: "sensor.accu_w",
            CONF_APPLIANCE_NOTIFY_SERVICE: "notify.telefoon",
        }
    )
    c._get_forecast_entries = lambda: []
    hass.states.set("sensor.accu_w", "500")
    return c


# --- 1. de opstart telt niet mee -------------------------------------


def test_a_missing_sensor_during_startup_is_not_recorded(
    make_coordinator, hass
):
    """De kern. Niet als goede meting en niet als slechte - geen meting
    is eerlijker dan een slechte meting."""
    c = _coordinator(make_coordinator, hass)
    c._started_at = NOW
    hass.states.set(ACCU, "unavailable")

    for minuut in range(0, SENSOR_STARTUP_GRACE_MINUTES, 5):
        c._update_energy_balance_validation(NOW + timedelta(minutes=minuut))

    assert c.energy_balance_error_history == []
    assert c.balance_missing_by_entity == {}


def test_after_the_grace_it_is_recorded_again(make_coordinator, hass):
    """De aanlooptijd mag een echte storing niet verbergen."""
    c = _coordinator(make_coordinator, hass)
    c._started_at = NOW
    hass.states.set(ACCU, "unavailable")

    c._update_energy_balance_validation(
        NOW + timedelta(minutes=SENSOR_STARTUP_GRACE_MINUTES + 1)
    )

    assert c.energy_balance_error_history == [None]
    assert c.balance_missing_by_entity[ACCU] == 1


def test_the_grace_is_wider_than_the_notification_delay(make_coordinator, hass):
    """De score kijkt terug over twintig metingen, dus daar weegt een
    verkeerde registratie veel langer door dan bij een melding."""
    from custom_components.energy_management_system.const import (
        STARTUP_GRACE_SECONDS,
    )

    assert SENSOR_STARTUP_GRACE_MINUTES * 60 > STARTUP_GRACE_SECONDS


def test_without_a_start_time_nothing_is_skipped(make_coordinator, hass):
    """Zonder bekend starttijdstip het oude gedrag aanhouden in plaats
    van alles overslaan."""
    c = _coordinator(make_coordinator, hass)
    c._started_at = None

    assert c.is_within_startup_grace(NOW) is False


# --- 2. melden pas bij ECHTE uitval ----------------------------------


def test_a_single_missed_reading_is_not_reported(make_coordinator, hass):
    """Een enkele gemiste uitlezing komt voor bij elke cloudgebonden
    integratie; daarover melden leert je meldingen te negeren."""
    c = _coordinator(make_coordinator, hass)
    c._started_at = NOW - timedelta(hours=1)
    c.set_notification_enabled("sensor_unavailable", True)
    hass.states.set(ACCU, "unavailable")

    _ronde(c, NOW)

    assert not any(
        "niet uitleesbaar" in m["titel"] for m in c.notification_history
    )


def test_a_sustained_outage_is_reported(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    c._started_at = NOW - timedelta(hours=1)
    c.set_notification_enabled("sensor_unavailable", True)
    hass.states.set(ACCU, "unavailable")

    _ronde(c, NOW)
    later = NOW + timedelta(minutes=SENSOR_UNAVAILABLE_CONFIRM_MINUTES + 1)
    _ronde(c, later)

    melding = next(
        m for m in c.notification_history if "niet uitleesbaar" in m["titel"]
    )
    assert ACCU in melding["bericht"]
    assert f"{SENSOR_UNAVAILABLE_CONFIRM_MINUTES} minuten" in melding["bericht"]


def test_a_recovered_sensor_clears_the_timer(make_coordinator, hass):
    """Komt de sensor terug, dan begint de teller opnieuw - anders zou
    een korte hapering later alsnog als lange uitval gelden."""
    c = _coordinator(make_coordinator, hass)
    c._started_at = NOW - timedelta(hours=1)

    hass.states.set(ACCU, "unavailable")
    c._track_sensor_availability(NOW, ACCU, False)
    c._track_sensor_availability(NOW + timedelta(minutes=5), ACCU, True)

    assert not c.is_sensor_genuinely_unavailable(
        NOW + timedelta(minutes=30), ACCU
    )


def test_the_timer_starts_at_the_first_absence(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)

    c._track_sensor_availability(NOW, ACCU, False)
    c._track_sensor_availability(NOW + timedelta(minutes=5), ACCU, False)

    # Gemeten vanaf het EERSTE moment, niet vanaf de laatste tick.
    assert c.is_sensor_genuinely_unavailable(
        NOW + timedelta(minutes=SENSOR_UNAVAILABLE_CONFIRM_MINUTES + 1), ACCU
    )


def test_an_available_sensor_is_never_flagged(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    hass.states.set(ACCU, "6.5")

    c._track_sensor_availability(NOW, ACCU, True)

    assert not c.is_sensor_genuinely_unavailable(
        NOW + timedelta(hours=2), ACCU
    )
