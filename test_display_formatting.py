"""Leesbare weergave van accuvermogen en tijdstip (v0.63.127).

Gerapporteerd bij de nieuwe grafische kaart: "Vermogen naar/van accu is
niet inzichtelijk en de datum notatie is niet duidelijk".

Beide zijn bij de BRON opgelost, niet op het dashboard: een
`state-label` op een picture-elements-kaart toont de ruwe attribuutwaarde
en heeft geen sjabloonmogelijkheid.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import (
    CONF_BATTERY_POWER_SENSOR,
    MIN_BATTERY_POWER_IDLE_W,
)
from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator,
)

LOKAAL = timezone(timedelta(hours=2))


@pytest.fixture(autouse=True)
def _lokale_tijd():
    """Echte omrekening naar NL-zomertijd, met opruiming - de gedeelde
    test-fake laat een tz-bewuste waarde ongemoeid."""
    from custom_components.energy_management_system import coordinator as mod

    origineel = mod.dt_util.as_local
    mod.dt_util.as_local = lambda v: (
        v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v
    ).astimezone(LOKAAL)
    yield
    mod.dt_util.as_local = origineel


# --- tijdstip -------------------------------------------------------


def test_iso_timestamp_becomes_readable():
    moment = datetime(2026, 8, 6, 12, 48, 28, 434441, tzinfo=LOKAAL)

    assert EnergyManagementSystemCoordinator.format_moment_short(moment) == (
        "do 6 aug 12:48"
    )


def test_microseconds_and_offset_are_gone():
    """Precies wat er op de kaart stond: 2026-08-06T12:48:28.434441+02:00."""
    tekst = EnergyManagementSystemCoordinator.format_moment_short(
        datetime(2026, 8, 6, 12, 48, 28, 434441, tzinfo=LOKAAL)
    )

    assert "T" not in tekst
    assert "+" not in tekst
    assert "434441" not in tekst


def test_utc_input_is_shown_in_local_time():
    """10:48 UTC is 12:48 lokaal - de kaart hoort lokale tijd te tonen."""
    moment = datetime(2026, 8, 6, 10, 48, tzinfo=timezone.utc)

    assert "12:48" in EnergyManagementSystemCoordinator.format_moment_short(moment)


def test_none_stays_none():
    assert EnergyManagementSystemCoordinator.format_moment_short(None) is None


def test_all_months_and_weekdays_are_covered():
    """Geen IndexError op een willekeurige datum."""
    moment = datetime(2026, 1, 1, 0, 0, tzinfo=LOKAAL)
    for _ in range(370):
        tekst = EnergyManagementSystemCoordinator.format_moment_short(moment)
        assert tekst and len(tekst.split()) == 4
        moment += timedelta(days=1)


# --- accuvermogen ---------------------------------------------------


def _coordinator_met_vermogen(make_coordinator, hass, watt):
    coordinator = make_coordinator(
        {CONF_BATTERY_POWER_SENSOR: "sensor.accu_vermogen"}
    )
    hass.states.set("sensor.accu_vermogen", str(watt))
    return coordinator


def test_discharging_is_named(make_coordinator, hass):
    coordinator = _coordinator_met_vermogen(make_coordinator, hass, 800)

    assert coordinator.get_battery_power_display() == "ontladen 800 W"


def test_charging_is_named(make_coordinator, hass):
    coordinator = _coordinator_met_vermogen(make_coordinator, hass, -597)

    assert coordinator.get_battery_power_display() == "laden 597 W"


def test_near_zero_is_called_rest(make_coordinator, hass):
    """Een stilstaande accu schommelt altijd een paar watt; "laden 3 W"
    suggereert een richting die er niet is."""
    coordinator = _coordinator_met_vermogen(
        make_coordinator, hass, MIN_BATTERY_POWER_IDLE_W - 1
    )

    assert coordinator.get_battery_power_display() == "rust"


def test_just_above_idle_shows_a_direction(make_coordinator, hass):
    coordinator = _coordinator_met_vermogen(
        make_coordinator, hass, MIN_BATTERY_POWER_IDLE_W + 1
    )

    assert "ontladen" in coordinator.get_battery_power_display()


def test_missing_sensor_is_honest(make_coordinator, hass):
    coordinator = make_coordinator({})

    assert coordinator.get_battery_power_display() == "onbekend"


def test_uses_the_same_source_as_the_decision_logic(make_coordinator, hass):
    """Kaart en besluit mogen nooit iets anders beweren - beide lezen
    `_read_corrected_battery_power`, dus ook dezelfde
    teken-omkering."""
    coordinator = make_coordinator(
        {
            CONF_BATTERY_POWER_SENSOR: "sensor.accu_vermogen",
            "invert_battery_power_sign": True,
        }
    )
    hass.states.set("sensor.accu_vermogen", "800")

    assert coordinator.get_battery_power_display() == "laden 800 W"
