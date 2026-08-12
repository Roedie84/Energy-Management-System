"""Hoe lang draait een noodloop al? (v1.58.0)

De les van deze week was steeds dezelfde: iets ving een probleem netjes
op - en zweeg. De azimut viel terug op `sun.sun`, kreeg niets, en het
installatieprofiel stond tien dagen op "0/5 heldere dagen".

Er zijn 28 terugvalpaden en geen enkele mat hoe lang hij al actief was.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_SOC_SENSOR,
    CONF_SUN_AZIMUTH_SENSOR,
)

NU = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, hass, **config):
    import custom_components.energy_management_system.coordinator as mod

    mod.dt_util.now = lambda: NU
    c = make_coordinator(config)
    # Het rendement per halve slag is standaard nog niet gemeten; dat is
    # een terechte terugval maar hier niet het onderwerp.
    c.charge_efficiency_history = [92.0] * 3
    c.discharge_efficiency_history = [96.0] * 3
    return c


def test_a_silent_sensor_starts_the_clock(make_coordinator, hass):
    c = _coordinator(
        make_coordinator, hass, **{CONF_SUN_AZIMUTH_SENSOR: "sensor.azimut"}
    )

    c._volg_terugvallen(NU)

    onderdelen = [r["onderdeel"] for r in c.get_fallback_overview()]
    assert "azimut" in onderdelen


def test_the_clock_does_not_restart_every_tick(make_coordinator, hass):
    """Anders staat er eeuwig "sinds nu" en is het getal waardeloos."""
    c = _coordinator(
        make_coordinator, hass, **{CONF_SUN_AZIMUTH_SENSOR: "sensor.azimut"}
    )

    c._volg_terugvallen(NU)
    c._volg_terugvallen(NU + timedelta(hours=5))

    assert c.fallback_since["azimut"] == NU.isoformat()


def test_a_recovered_sensor_clears_the_clock(make_coordinator, hass):
    c = _coordinator(
        make_coordinator, hass, **{CONF_SUN_AZIMUTH_SENSOR: "sensor.azimut"}
    )
    c._volg_terugvallen(NU)

    hass.states.set("sensor.azimut", "182.5")
    c._volg_terugvallen(NU + timedelta(hours=1))

    assert "azimut" not in c.fallback_since


def test_a_day_of_fallback_becomes_a_doing_item(make_coordinator, hass):
    """Een dag terugval is ruis - een sensor die even zweeg. Een week is
    een storing die niemand heeft gezien."""
    import custom_components.energy_management_system.coordinator as mod

    c = _coordinator(
        make_coordinator, hass, **{CONF_SUN_AZIMUTH_SENSOR: "sensor.azimut"}
    )
    c.get_reliability_overview = lambda: []
    c.get_proefstand = lambda: {"kandidaten": []}
    c.get_input_health = lambda: []
    c._volg_terugvallen(NU)

    mod.dt_util.now = lambda: NU + timedelta(days=3)
    overzicht = c.get_pending_overview()

    namen = [r["naam"] for r in overzicht["doen"]]
    assert any("noodloop" in n for n in namen)


def test_a_fresh_fallback_is_not_yet_an_alarm(make_coordinator, hass):
    c = _coordinator(
        make_coordinator, hass, **{CONF_SUN_AZIMUTH_SENSOR: "sensor.azimut"}
    )
    c._volg_terugvallen(NU)

    assert c.get_fallback_overview()[0]["langdurig"] is False


def test_a_derived_state_of_charge_counts_too(make_coordinator, hass):
    """De accustand wordt afgeleid uit de beschikbare energie als de
    sensor zwijgt - dat werkt, maar het hoort op te vallen."""
    c = _coordinator(make_coordinator, hass, **{CONF_SOC_SENSOR: "sensor.soc"})

    c._volg_terugvallen(NU)

    assert "accustand" in c.fallback_since


def test_the_start_moment_survives_a_restart():
    """Bij elke herstart opnieuw beginnen zou "al drie dagen" onmogelijk
    maken - en dat is precies het getal waar het om gaat."""
    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "fallback_since" in PERSISTED_PLAIN_FIELDS
