"""Accu-koeling geïntegreerd (v0.63.122).

Gevraagd: "Integreren zodat ik dit niet meer als losse automatisering
hoef te doen, het heeft mijn inziens toch met de accu te maken."

Overgenomen uit "Accu: Temperatuurbeheer Thuisaccu (Buiten) - PRO v9".
De drempels zijn EXACT die van de automatisering; de tests hieronder
leggen elk van de vier aanzet-redenen en de drie-voorwaarden-uit-regel
apart vast, plus de twee bewuste afwijkingen (geen float(0)-terugval,
geen 20-seconden-vertraging).
"""
import asyncio
from datetime import datetime, timezone

from custom_components.energy_management_system.const import (
    CONF_APPLIANCE_NOTIFY_SERVICE,
    CONF_BATTERY_COOLING_FAN_SWITCH,
    CONF_BATTERY_COOLING_OUTDOOR_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_BATTERY_TEMPERATURE_SENSOR,
)

NOW = datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc)
FAN = "switch.ventilatoren_thuisaccu"


def _config():
    return {
        CONF_BATTERY_TEMPERATURE_SENSOR: "sensor.accu_temp",
        CONF_BATTERY_COOLING_OUTDOOR_SENSOR: "sensor.buiten_temp",
        CONF_BATTERY_COOLING_FAN_SWITCH: FAN,
        CONF_BATTERY_POWER_SENSOR: "sensor.accu_vermogen",
    }


def _situatie(hass, accu, buiten, vermogen, ventilator="off"):
    hass.states.set("sensor.accu_temp", str(accu))
    hass.states.set("sensor.buiten_temp", str(buiten))
    hass.states.set("sensor.accu_vermogen", str(vermogen))
    hass.states.set(FAN, ventilator)


# --- de vier aanzet-redenen ----------------------------------------


def test_turns_on_when_delta_exceeds_five(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=28.0, buiten=22.0, vermogen=0)

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] == "aan"
    assert "boven buiten" in besluit["reden"]


def test_turns_on_above_the_absolute_limit(make_coordinator, hass):
    """Ook zonder groot verschil met buiten: 35°C is gewoon te warm."""
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=35.5, buiten=34.0, vermogen=0)

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] == "aan"
    assert "absolute grens" in besluit["reden"]


def test_turns_on_at_moderate_load_slightly_above_outdoor(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=25.0, buiten=22.0, vermogen=800)

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] == "aan"
    assert "800W" in besluit["reden"]


def test_turns_on_at_heavy_load_above_thirty(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=31.0, buiten=30.0, vermogen=1800)

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] == "aan"
    assert "zwaar belast" in besluit["reden"]


def test_stays_off_when_no_reason_applies(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=24.0, buiten=22.0, vermogen=100)

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] is None


# --- uitschakelen: alle drie tegelijk -------------------------------


def test_turns_off_when_all_three_conditions_hold(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=25.0, buiten=24.0, vermogen=100, ventilator="on")

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] == "uit"


def test_keeps_cooling_when_only_the_load_dropped(make_coordinator, hass):
    """Eén voorwaarde die terugvalt is niet genoeg - de accu staat nog
    ruim boven buiten."""
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=30.0, buiten=24.0, vermogen=100, ventilator="on")

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] is None
    assert besluit["reden"] == "Blijft koelen."


def test_keeps_cooling_when_still_too_hot(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=34.0, buiten=33.5, vermogen=50, ventilator="on")

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] is None


def test_hysteresis_prevents_immediate_switch_back(make_coordinator, hass):
    """Bij delta 3°C: te weinig om aan te gaan (>5), te veel om uit te
    gaan (<2). Wat er ook staat, blijft staan."""
    coordinator = make_coordinator(_config())

    _situatie(hass, accu=25.0, buiten=22.0, vermogen=100, ventilator="off")
    assert coordinator.evaluate_battery_cooling()["actie"] is None

    _situatie(hass, accu=25.0, buiten=22.0, vermogen=100, ventilator="on")
    assert coordinator.evaluate_battery_cooling()["actie"] is None


# --- bewuste afwijking: geen float(0)-terugval ----------------------


def test_unavailable_outdoor_sensor_does_not_switch_anything(
    make_coordinator, hass
):
    """De oorspronkelijke automatisering las een ontbrekende sensor als
    0 via `float(0)`. Buiten = 0°C maakt de delta gelijk aan de hele
    accutemperatuur, waardoor de ventilator zou aanslaan op een meting
    die er niet is."""
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=28.0, buiten=22.0, vermogen=0)
    hass.states.set("sensor.buiten_temp", "unavailable")

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] is None
    assert "niet uitleesbaar" in besluit["reden"]


def test_unavailable_battery_sensor_does_not_switch_anything(
    make_coordinator, hass
):
    """Andersom net zo gevaarlijk: accu = 0°C zou betekenen dat er nooit
    meer gekoeld wordt."""
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=36.0, buiten=22.0, vermogen=0, ventilator="off")
    hass.states.set("sensor.accu_temp", "unavailable")

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] is None


def test_unavailable_fan_switch_is_not_guessed_at(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=36.0, buiten=22.0, vermogen=0)
    hass.states.set(FAN, "unavailable")

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] is None
    assert "niet uitleesbaar" in besluit["reden"]


def test_no_fan_configured_is_a_clean_no_op(make_coordinator, hass):
    coordinator = make_coordinator({})

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] is None
    assert "Geen ventilatorschakelaar" in besluit["reden"]


# --- daadwerkelijk schakelen ---------------------------------------


def _calls(hass):
    return getattr(hass.services, "calls", [])


def test_applying_calls_the_switch_service(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=36.0, buiten=22.0, vermogen=0)

    asyncio.run(coordinator._async_apply_battery_cooling())

    assert any(
        c[0] == "switch" and c[1] == "turn_on" for c in _calls(hass)
    )


def test_applying_records_history_and_timestamp(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=36.0, buiten=22.0, vermogen=0)

    asyncio.run(coordinator._async_apply_battery_cooling())

    assert len(coordinator.battery_cooling_history) == 1
    assert coordinator.battery_cooling_history[0]["actie"] == "aan"
    assert coordinator.battery_cooling_last_change is not None


def test_force_manual_blocks_the_switch(make_coordinator, hass):
    """Zelfde respect voor de bestaande noodrem als elke andere
    aansturing in deze integratie."""
    coordinator = make_coordinator(_config())
    coordinator.force_manual = True
    _situatie(hass, accu=36.0, buiten=22.0, vermogen=0)

    asyncio.run(coordinator._async_apply_battery_cooling())

    assert not any(c[0] == "switch" for c in _calls(hass))
    assert "force manual" in coordinator.battery_cooling_state["reden"]


def test_learning_only_blocks_the_switch(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    coordinator.learning_only = True
    _situatie(hass, accu=36.0, buiten=22.0, vermogen=0)

    asyncio.run(coordinator._async_apply_battery_cooling())

    assert not any(c[0] == "switch" for c in _calls(hass))


def test_no_redundant_switch_when_already_correct(make_coordinator, hass):
    """Ventilator staat al aan en moet aan blijven - niet elke tick
    opnieuw turn_on sturen."""
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=36.0, buiten=22.0, vermogen=0, ventilator="on")

    asyncio.run(coordinator._async_apply_battery_cooling())

    assert not any(c[0] == "switch" for c in _calls(hass))


def test_state_is_exposed_even_without_action(make_coordinator, hass):
    """Het dashboard moet ook kloppen als er niets te schakelen valt."""
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=24.0, buiten=22.0, vermogen=100)

    asyncio.run(coordinator._async_apply_battery_cooling())

    state = coordinator.battery_cooling_state
    assert state["accu_c"] == 24.0
    assert state["buiten_c"] == 22.0
    assert state["delta_c"] == 2.0
    assert state["ventilator_aan"] is False


# --- terugval op de bestaande buitentemperatuur ---------------------


def test_falls_back_to_the_existing_outdoor_temperature(make_coordinator, hass):
    """Zonder eigen buitensensor wordt de al beschikbare
    live-buitentemperatuur gebruikt."""
    config = _config()
    del config[CONF_BATTERY_COOLING_OUTDOOR_SENSOR]
    coordinator = make_coordinator(config)
    coordinator.climate_live_outdoor_temp_c = 22.0
    hass.states.set("sensor.accu_temp", "28.0")
    hass.states.set("sensor.accu_vermogen", "0")
    hass.states.set(FAN, "off")

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] == "aan"
    assert besluit["buiten_c"] == 22.0


def test_sensor_reports_the_current_state(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        BatteryCoolingSensor,
    )

    coordinator = make_coordinator(_config())
    _situatie(hass, accu=36.0, buiten=22.0, vermogen=0, ventilator="on")
    coordinator.battery_cooling_state = coordinator.evaluate_battery_cooling()

    sensor = BatteryCoolingSensor(coordinator, "entry1")

    assert sensor.native_value == "koelt"
    assert sensor.extra_state_attributes["accu_c"] == 36.0


def test_cooling_tile_sits_in_the_live_figures_section():
    """v0.63.124, gevraagd: de accu-koeling verplaatsen naar de tegels
    van 'Accu, rendement & live cijfers' in plaats van een eigen sectie.

    Als eigen sectie zette de masonry-layout hem linksboven, waar hij
    een volle kolombreedte innam voor één regel informatie.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    import yaml

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    overzicht = next(v for v in data["views"] if v["title"] == "Overzicht")

    koppen = [
        card.get("heading")
        for sectie in overzicht["sections"]
        for card in sectie.get("cards", [])
        if card.get("type") == "heading"
    ]
    assert "Accu-koeling" not in koppen, "staat nog als eigen sectie"

    doelsectie = next(
        sectie
        for sectie in overzicht["sections"]
        if any(
            card.get("heading") == "Accu, rendement & live cijfers"
            for card in sectie.get("cards", [])
        )
    )
    koeltegels = [
        card
        for card in doelsectie["cards"]
        if "accu_koeling" in str(card.get("entity", ""))
    ]
    assert len(koeltegels) == 1
    # Halve breedte, net als de andere tegels ernaast.
    # v1.17.3: volle sectiebreedte. Secties staan al naast elkaar (drie
    # op een breed scherm), dus binnen een sectie nog eens opdelen maakte
    # de tegels een negende van het scherm - te smal voor hun tekst.
    assert koeltegels[0]["grid_options"]["columns"] == 12
