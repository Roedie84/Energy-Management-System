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


def _weg_sinds(c, entity_id, moment):
    """v1.11.0: de melding komt pas bij AANHOUDENDE uitval, dus de
    sensor moet al een tijd weg zijn. Een enkele gemiste uitlezing komt
    voor bij elke cloudgebonden integratie en is geen storing."""
    from custom_components.energy_management_system.const import (
        SENSOR_UNAVAILABLE_CONFIRM_MINUTES,
    )

    c._sensor_unavailable_since[entity_id] = moment - timedelta(
        minutes=SENSOR_UNAVAILABLE_CONFIRM_MINUTES + 1
    )


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
    _weg_sinds(c, "sensor.beschikbaar", NOW)
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

    _weg_sinds(c, "sensor.beschikbaar", NOW)
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
    _weg_sinds(c, "sensor.beschikbaar", NOW)
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
    _weg_sinds(c, "sensor.beschikbaar", NOW)
    _ronde(c)
    c.set_notification_enabled("sensor_unavailable", False)

    hass.states.set("sensor.beschikbaar", "6.5")
    _ronde(c, NOW + timedelta(minutes=5))

    assert not any("weer uitleesbaar" in t for t in _titels(c))


def test_the_master_switch_blocks_recoveries_too(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    hass.states.set("sensor.beschikbaar", "unavailable")
    _weg_sinds(c, "sensor.beschikbaar", NOW)
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

    _weg_sinds(c, "sensor.beschikbaar", NOW)
    _ronde(c)
    hass.states.set("sensor.beschikbaar", "6.5")
    _ronde(c, NOW + timedelta(minutes=5))
    hass.states.set("sensor.beschikbaar", "unavailable")
    _weg_sinds(c, "sensor.beschikbaar", NOW)
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


# --- v1.6.3: de geschiedenis moet bruikbaar zijn ---------------------


def test_the_history_stores_the_message_not_just_the_title(
    make_coordinator, hass
):
    """Gerapporteerd: "kan in de gecreeerde tabel niet zien om welke het
    ging".

    De titel zegt DAT er een sensor wegviel, het bericht zegt WELKE.
    Alleen de titel bewaren maakt de geschiedenis onbruikbaar voor
    precies het geval waarvoor je hem opzoekt.
    """
    c = _coordinator(make_coordinator, hass)
    hass.states.set("sensor.beschikbaar", "unavailable")
    _weg_sinds(c, "sensor.beschikbaar", NOW)

    _ronde(c)

    regel = next(m for m in c.notification_history if "niet uitleesbaar" in m["titel"])
    assert "sensor.beschikbaar" in regel["bericht"]


def test_the_recovery_also_stores_its_message(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    hass.states.set("sensor.beschikbaar", "unavailable")
    _weg_sinds(c, "sensor.beschikbaar", NOW)
    _ronde(c)
    hass.states.set("sensor.beschikbaar", "6.5")
    _ronde(c, NOW + timedelta(minutes=5))

    regel = next(
        m for m in c.notification_history if "weer uitleesbaar" in m["titel"]
    )
    assert regel["bericht"]


def test_the_history_is_long_enough_for_a_busy_day(make_coordinator, hass):
    """Met tweeëntwintig soorten en herstelmeldingen erbij was vijftig
    krap: een drukke dag vulde de lijst en duwde de melding waar je naar
    zocht er alweer uit."""
    from custom_components.energy_management_system.const import (
        NOTIFICATION_HISTORY_LENGTH,
        NOTIFICATION_TYPES,
    )

    assert NOTIFICATION_HISTORY_LENGTH >= len(NOTIFICATION_TYPES) * 5


def test_the_dashboard_shows_the_message():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    yaml_tekst = (
        Path(pkg.__file__).parent / "dashboard_template.yaml"
    ).read_text()

    assert "m.bericht" in yaml_tekst
    assert "niet na een bepaalde tijd" in yaml_tekst


# --- v1.6.6: welke sensor, en aanlooptijd na een herstart ------------


def test_the_recovery_names_the_sensor(make_coordinator, hass):
    """Gerapporteerd: "Ik doelde vooral op dat '✅ Sensor is weer
    uitleesbaar' niet aangeeft welke sensor weer uitleesbaar is. Nu wist
    ik het omdat het er maar 1 is."

    De probleemmelding noemde de entity_id wél; de herstelmelding bleef
    generiek.
    """
    c = _coordinator(make_coordinator, hass)
    c._started_at = NOW - timedelta(hours=1)

    hass.states.set("sensor.beschikbaar", "unavailable")

    _weg_sinds(c, "sensor.beschikbaar", NOW)
    _ronde(c)
    hass.states.set("sensor.beschikbaar", "6.5")
    _ronde(c, NOW + timedelta(minutes=5))

    herstel = next(
        m for m in c.notification_history if "weer uitleesbaar" in m["titel"]
    )
    assert "sensor.beschikbaar" in herstel["bericht"]


def test_the_names_are_cleared_after_the_recovery(make_coordinator, hass):
    """Anders zou een volgende herstelmelding de sensoren van de vórige
    storing noemen."""
    c = _coordinator(make_coordinator, hass)
    c._started_at = NOW - timedelta(hours=1)

    hass.states.set("sensor.beschikbaar", "unavailable")

    _weg_sinds(c, "sensor.beschikbaar", NOW)
    _ronde(c)
    hass.states.set("sensor.beschikbaar", "6.5")
    _ronde(c, NOW + timedelta(minutes=5))

    assert c._unavailable_entities == []


# --- aanlooptijd -----------------------------------------------------


def test_no_unavailability_alert_right_after_a_restart(
    make_coordinator, hass
):
    """Gerapporteerd: "Het uitvallen komt door een herstart (start
    relatief traag op), misschien deze melding iets vertragen?"

    Een melding over iets dat binnen een minuut vanzelf goed komt, leert
    je die meldingen te negeren - en dan mis je de keer dat het wél echt
    misgaat.
    """
    c = _coordinator(make_coordinator, hass)
    c._started_at = NOW
    hass.states.set("sensor.beschikbaar", "unavailable")
    _weg_sinds(c, "sensor.beschikbaar", NOW)

    _ronde(c, NOW + timedelta(seconds=30))

    assert not any("niet uitleesbaar" in t for t in _titels(c))


def test_the_alert_does_arrive_after_the_grace_period(
    make_coordinator, hass
):
    """De aanlooptijd mag een echte storing niet verbergen."""
    from custom_components.energy_management_system.const import (
        STARTUP_GRACE_SECONDS,
    )

    c = _coordinator(make_coordinator, hass)
    c._started_at = NOW
    hass.states.set("sensor.beschikbaar", "unavailable")
    _weg_sinds(c, "sensor.beschikbaar", NOW)

    _ronde(c, NOW + timedelta(seconds=STARTUP_GRACE_SECONDS + 10))

    assert any("niet uitleesbaar" in t for t in _titels(c))


def test_other_notifications_are_not_delayed(make_coordinator, hass):
    """Alleen beschikbaarheidsmeldingen wachten; een prijspiek of een
    apparaat dat klaar is heeft niets met opstarten te maken."""
    from custom_components.energy_management_system.const import (
        STARTUP_GRACE_KINDS,
    )

    c = _coordinator(make_coordinator, hass)
    c._started_at = NOW

    toegestaan, _ = c.is_notification_allowed("mode_change", NOW)

    assert toegestaan is True
    assert "mode_change" not in STARTUP_GRACE_KINDS


def test_the_reason_explains_the_delay(make_coordinator, hass):
    """Zodat op het tabblad te zien is waarom een melding uitbleef."""
    c = _coordinator(make_coordinator, hass)
    c._started_at = NOW

    toegestaan, reden = c.is_notification_allowed(
        "sensor_unavailable", NOW + timedelta(seconds=10)
    )

    assert toegestaan is False
    assert "aanlooptijd" in reden
