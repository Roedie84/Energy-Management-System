"""Herstelmeldingen (v1.6.2).

Gerapporteerd: "Er is nu een melding verstuurd dat een sensor niet
uitleesbaar is, maar er komt geen melding wanneer de sensor weer
uitleesbaar is."

Terecht, en het geldt breder dan die ene. Zonder herstelmelding blijf je
in het ongewisse: is het opgelost, of is de melding gewoon gedempt? Dat
is precies het soort onzekerheid waardoor mensen meldingen gaan negeren.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_APPLIANCE_NOTIFY_SERVICE,
    CONF_AVAILABLE_ENERGY_SENSOR,
    NOTIFICATION_RECOVERY_KINDS,
    NOTIFICATION_TYPES,
)

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass):
    c = make_coordinator(
        {
            CONF_APPLIANCE_NOTIFY_SERVICE: "notify.telefoon",
            CONF_AVAILABLE_ENERGY_SENSOR: "sensor.beschikbaar",
        }
    )
    c._get_forecast_entries = lambda: []
    c.set_notification_enabled("sensor_unavailable", True)
    return c


def _ronde(c, moment=NOW):
    from custom_components.energy_management_system import coordinator as mod

    origineel = mod.dt_util.now
    try:
        mod.dt_util.now = lambda: moment
        c._evaluate_new_notifications(moment)
    finally:
        mod.dt_util.now = origineel


def _titels(c):
    return [m["titel"] for m in c.notification_history]


# --- het gerapporteerde geval ----------------------------------------


def test_a_recovered_sensor_is_reported(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)

    # Sensor weg: probleemmelding.
    hass.states.set("sensor.beschikbaar", "unavailable")
    _ronde(c)
    assert any("niet uitleesbaar" in t for t in _titels(c))

    # Sensor terug: herstelmelding.
    hass.states.set("sensor.beschikbaar", "6.5")
    _ronde(c, NOW + timedelta(minutes=5))

    assert any("weer uitleesbaar" in t for t in _titels(c))


def test_the_recovery_ignores_the_throttle(make_coordinator, hass):
    """Een probleem dat vijf minuten na de melding is opgelost zou
    anders stilzwijgend verdwijnen - en juist dan wil je het horen."""
    c = _coordinator(make_coordinator, hass)
    venster = next(v for k, _, _, _, v in NOTIFICATION_TYPES
                   if k == "sensor_unavailable")

    hass.states.set("sensor.beschikbaar", "unavailable")
    _ronde(c)
    hass.states.set("sensor.beschikbaar", "6.5")
    _ronde(c, NOW + timedelta(minutes=1))

    assert venster > 1
    assert any("weer uitleesbaar" in t for t in _titels(c))


def test_no_recovery_without_a_problem(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    hass.states.set("sensor.beschikbaar", "6.5")

    _ronde(c)
    _ronde(c, NOW + timedelta(minutes=5))

    assert not any("weer uitleesbaar" in t for t in _titels(c))


def test_no_repeated_recovery(make_coordinator, hass):
    """Eenmaal hersteld is hersteld."""
    c = _coordinator(make_coordinator, hass)
    hass.states.set("sensor.beschikbaar", "unavailable")
    _ronde(c)
    hass.states.set("sensor.beschikbaar", "6.5")
    _ronde(c, NOW + timedelta(minutes=5))
    _ronde(c, NOW + timedelta(minutes=10))

    assert len([t for t in _titels(c) if "weer uitleesbaar" in t]) == 1


# --- de schakelaar blijft leidend ------------------------------------


def test_a_disabled_notification_gets_no_recovery(make_coordinator, hass):
    """Wie "sensor valt weg" uitzet, wil ook het herstel niet - dat is
    wat je verwacht als je een melding uitschakelt."""
    c = _coordinator(make_coordinator, hass)
    hass.states.set("sensor.beschikbaar", "unavailable")
    _ronde(c)
    c.set_notification_enabled("sensor_unavailable", False)

    hass.states.set("sensor.beschikbaar", "6.5")
    _ronde(c, NOW + timedelta(minutes=5))

    assert not any("weer uitleesbaar" in t for t in _titels(c))


def test_the_master_switch_blocks_recoveries_too(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    hass.states.set("sensor.beschikbaar", "unavailable")
    _ronde(c)
    c.notifications_master_enabled = False

    hass.states.set("sensor.beschikbaar", "6.5")
    _ronde(c, NOW + timedelta(minutes=5))

    assert not any("weer uitleesbaar" in t for t in _titels(c))


# --- een terugkerend probleem ----------------------------------------


def test_a_returning_problem_is_reported_immediately(make_coordinator, hass):
    """Na een herstel wordt het dempingsvenster gewist, zodat hetzelfde
    probleem dat terugkomt meteen weer meldt in plaats van pas na het
    venster."""
    c = _coordinator(make_coordinator, hass)

    hass.states.set("sensor.beschikbaar", "unavailable")
    _ronde(c)
    hass.states.set("sensor.beschikbaar", "6.5")
    _ronde(c, NOW + timedelta(minutes=5))
    hass.states.set("sensor.beschikbaar", "unavailable")
    _ronde(c, NOW + timedelta(minutes=10))

    assert len([t for t in _titels(c) if "niet uitleesbaar" in t]) == 2


# --- welke soorten wel en niet ---------------------------------------


def test_only_condition_kinds_have_a_recovery():
    """Meldingen die een GEBEURTENIS beschrijven - apparaat klaar,
    dagoverzicht - horen er niet bij: daar valt niets aan te
    herstellen."""
    for gebeurtenis in (
        "appliance_ready",
        "daily_summary",
        "monthly_summary",
        "cheap_block_soon",
        "negative_prices",
    ):
        assert gebeurtenis not in NOTIFICATION_RECOVERY_KINDS


def test_every_recovery_kind_is_a_real_notification_type():
    """Een herstelmelding voor een soort die niet bestaat zou nooit
    afgaan."""
    bekend = {k for k, _, _, _, _ in NOTIFICATION_TYPES}

    assert set(NOTIFICATION_RECOVERY_KINDS) <= bekend


def test_every_recovery_has_a_title_and_message():
    for kind, (titel, bericht) in NOTIFICATION_RECOVERY_KINDS.items():
        assert titel and len(bericht) > 20, kind


# --- persistentie ----------------------------------------------------


def test_the_active_conditions_survive_a_restart(make_coordinator, hass):
    """Zonder bewaren zou een herstart als "opgelost" gelden en meteen
    een herstelmelding sturen voor een probleem dat nog gewoon speelt."""
    import asyncio

    bron = _coordinator(make_coordinator, hass)
    bron.notification_active_conditions = ["sensor_unavailable"]
    asyncio.run(bron.async_save_persisted_state_now())

    # Bewust ZONDER `_coordinator`: die roept
    # `set_notification_enabled` aan, wat meteen opslaat en daarmee de
    # zojuist bewaarde toestand zou overschrijven vóór het laden. In
    # productie kan dat niet - het laden gebeurt in de setup, vóór de
    # platforms en vóór de eerste tick.
    verse = make_coordinator({})
    asyncio.run(verse.async_load_persisted_state())

    assert verse.notification_active_conditions == ["sensor_unavailable"]
