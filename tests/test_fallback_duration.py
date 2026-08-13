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


# --- v1.79.0: wachten is geen handeling ------------------------------


def test_a_learning_fallback_lands_in_the_waiting_pile(
    make_coordinator, hass
):
    """Gevonden in de export van 13 augustus 12:07: het rendement stond
    bij "vraagt een handeling" omdat het al 24 uur op de oude methode
    draaide.

    Maar daar valt niets aan te doen - er zijn drie meetstukken per kant
    nodig van minstens 1,5 kWh, en die komen vanzelf. Een noodloop die op
    een zwijgende sensor wacht is een handeling; een leerroutine die
    metingen verzamelt is wachten.
    """
    import custom_components.energy_management_system.coordinator as mod

    c = _coordinator(make_coordinator, hass)
    # Het rendement is standaard nog niet per halve slag gemeten.
    c.charge_efficiency_history = []
    c.discharge_efficiency_history = []
    c.get_reliability_overview = lambda: []
    c.get_proefstand = lambda: {"kandidaten": []}
    c.get_input_health = lambda: []
    c._volg_terugvallen(NU)

    mod.dt_util.now = lambda: NU + timedelta(days=2)
    overzicht = c.get_pending_overview()

    assert overzicht["aantal_doen"] == 0
    assert any("noodloop" in r["naam"] for r in overzicht["wachten"])


def test_a_silent_sensor_still_asks_for_action(make_coordinator, hass):
    """Het onderscheid moet wel blijven werken: een sensor die zwijgt
    lost zichzelf niet op."""
    import custom_components.energy_management_system.coordinator as mod

    from custom_components.energy_management_system.const import (
        CONF_SUN_AZIMUTH_SENSOR,
    )

    c = _coordinator(
        make_coordinator, hass, **{CONF_SUN_AZIMUTH_SENSOR: "sensor.azimut"}
    )
    c.get_reliability_overview = lambda: []
    c.get_proefstand = lambda: {"kandidaten": []}
    c.get_input_health = lambda: []
    c._volg_terugvallen(NU)

    mod.dt_util.now = lambda: NU + timedelta(days=2)
    overzicht = c.get_pending_overview()

    assert any("azimut" in r["naam"] for r in overzicht["doen"])


def test_every_fallback_says_which_kind_it_is(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    c.charge_efficiency_history = []
    c.discharge_efficiency_history = []
    c._volg_terugvallen(NU)

    for regel in c.get_fallback_overview():
        assert regel["soort"] in ("wachten", "doen")
