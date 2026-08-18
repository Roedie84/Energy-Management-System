"""Accu-koeling geïntegreerd (v0.63.122).

v1.80.0: alle temperaturen in dit bestand zijn twaalf graden opgehoogd.
Gemeld: "Ventilatoren zuigen af van de omvormer" - de sensor die de
koeling aanstuurt is dus `solarflow_2400_ac_hyper_tmp` en niet de cellen.

De drempels stonden op CELtemperaturen (35 graden als grens voor
versnelde veroudering van lithium-ijzerfosfaat), maar een omvormer
draait routinematig veel warmer. Daardoor sloeg de ventilator aan bij 25
tot 29 graden - voor een omvormer volstrekt normaal.

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
    _situatie(hass, accu=40.0, buiten=34.0, vermogen=0)

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] == "aan"
    assert "boven buiten" in besluit["reden"]


def test_turns_on_above_the_absolute_limit(make_coordinator, hass):
    """Ook zonder groot verschil met buiten: boven de absolute grens is
    de omvormer gewoon te warm."""
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=51.0, buiten=49.5, vermogen=0)

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] == "aan"
    assert "absolute grens" in besluit["reden"]


def test_turns_on_at_moderate_load_slightly_above_outdoor(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    # v1.76.0: 25,0 lag precies op de ondergrens, die nu op 26 ligt met
    # hysterese naar 24. De sensor meldt hele graden en wipte anders
    # mee - twintig schakelingen in een uur.
    _situatie(hass, accu=39.0, buiten=36.0, vermogen=800)

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] == "aan"
    assert "800W" in besluit["reden"]


def test_turns_on_at_heavy_load_above_thirty(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=43.0, buiten=42.0, vermogen=1800)

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] == "aan"
    assert "zwaar belast" in besluit["reden"]


def test_stays_off_when_no_reason_applies(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=36.0, buiten=34.0, vermogen=100)

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] is None


# --- uitschakelen: alle drie tegelijk -------------------------------


def test_turns_off_when_all_three_conditions_hold(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=37.0, buiten=36.0, vermogen=100, ventilator="on")

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] == "uit"


def test_keeps_cooling_when_only_the_load_dropped(make_coordinator, hass):
    """Eén voorwaarde die terugvalt is niet genoeg - de accu staat nog
    ruim boven buiten."""
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=42.0, buiten=36.0, vermogen=100, ventilator="on")

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] is None
    assert besluit["reden"] == "Blijft koelen."


def test_keeps_cooling_when_still_too_hot(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=46.0, buiten=45.5, vermogen=50, ventilator="on")

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] is None


def test_hysteresis_prevents_immediate_switch_back(make_coordinator, hass):
    """Bij delta 3°C: te weinig om aan te gaan (>5), te veel om uit te
    gaan (<2). Wat er ook staat, blijft staan."""
    coordinator = make_coordinator(_config())

    _situatie(hass, accu=37.0, buiten=34.0, vermogen=100, ventilator="off")
    assert coordinator.evaluate_battery_cooling()["actie"] is None

    _situatie(hass, accu=37.0, buiten=34.0, vermogen=100, ventilator="on")
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
    _situatie(hass, accu=40.0, buiten=34.0, vermogen=0)
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
    _situatie(hass, accu=48.0, buiten=34.0, vermogen=0, ventilator="off")
    hass.states.set("sensor.accu_temp", "unavailable")

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] is None


def test_unavailable_fan_switch_is_not_guessed_at(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=48.0, buiten=34.0, vermogen=0)
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
    _situatie(hass, accu=48.0, buiten=34.0, vermogen=0)

    asyncio.run(coordinator._async_apply_battery_cooling())

    assert any(
        c[0] == "switch" and c[1] == "turn_on" for c in _calls(hass)
    )


def test_applying_records_history_and_timestamp(make_coordinator, hass):
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=48.0, buiten=34.0, vermogen=0)

    asyncio.run(coordinator._async_apply_battery_cooling())

    assert len(coordinator.battery_cooling_history) == 1
    assert coordinator.battery_cooling_history[0]["actie"] == "aan"
    assert coordinator.battery_cooling_last_change is not None


def test_force_manual_blocks_an_optimisation(make_coordinator, hass):
    """v3.15.0: de noodrem blokkeert de koeling nog steeds, MAAR alleen
    zolang koelen een optimalisatie is.

    Gemeld: "Koelen mag niets te maken hebben met goedkoop of dure
    prijzen, hij moet wanneer nodig altijd koelen." Prijzen raakten de
    koeling al nergens - maar deze blokkade wél.
    """
    coordinator = make_coordinator(_config())
    coordinator.force_manual = True
    # Onder de beschermingsgrens: hier is koelen winst, geen noodzaak.
    _situatie(hass, accu=30.0, buiten=15.0, vermogen=0)

    asyncio.run(coordinator._async_apply_battery_cooling())

    assert not any(c[0] == "switch" for c in _calls(hass))
    assert "force manual" in coordinator.battery_cooling_state["reden"]


def test_force_manual_does_not_block_protection(make_coordinator, hass):
    """Een ventilator laadt of ontlaadt niets; hij beschermt alleen. Wie
    de sturing overneemt wil niet dat zijn accu ondertussen
    oververhit."""
    coordinator = make_coordinator(_config())
    coordinator.force_manual = True
    _situatie(hass, accu=48.0, buiten=34.0, vermogen=0)

    asyncio.run(coordinator._async_apply_battery_cooling())

    assert any(c[0] == "switch" for c in _calls(hass))
    assert "bescherming" in coordinator.battery_cooling_state["reden"]


def test_learning_only_does_not_block_protection(make_coordinator, hass):
    """Leermodus zegt "stuur mijn accu niet aan" - niet "laat hem
    oververhitten"."""
    coordinator = make_coordinator(_config())
    coordinator.learning_only = True
    _situatie(hass, accu=48.0, buiten=34.0, vermogen=0)

    asyncio.run(coordinator._async_apply_battery_cooling())

    assert any(c[0] == "switch" for c in _calls(hass))
    assert "bescherming" in coordinator.battery_cooling_state["reden"]


def test_learning_only_still_blocks_an_optimisation(make_coordinator, hass):
    """Onder de beschermingsgrens blijft de oude terughoudendheid
    gelden: dan is koelen een optimalisatie, en die hoort te wijken voor
    wie de sturing overneemt."""
    coordinator = make_coordinator(_config())
    coordinator.learning_only = True
    _situatie(hass, accu=30.0, buiten=15.0, vermogen=0)

    asyncio.run(coordinator._async_apply_battery_cooling())

    assert not any(c[0] == "switch" for c in _calls(hass))


def test_no_price_touches_the_cooling_decision():
    """Gemeld: "Koelen mag niets te maken hebben met goedkoop of dure
    prijzen." Dat was al zo, en het hoort zo te blijven.

    De naam "goedkoop koelen" uit v3.6.0 sloeg op de VENTILATOR - een
    paar watt voor veel koeling - niet op de stroomprijs. Een
    ongelukkige naam, en dit legt vast waar het om gaat.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    for naam in (
        "evaluate_battery_cooling",
        "_battery_cooling_should_turn_on",
        "_battery_cooling_should_turn_off",
        "_koelen_is_goedkoop",
        "_goedkope_koeling_nog_zinvol",
    ):
        kop = bron.index(f"def {naam}(")
        blok = bron[kop : bron.index("\n    def ", kop + 10)]
        code = "\n".join(r.split("#")[0] for r in blok.splitlines())

        for verboden in ("price", "prijs", "entries", "cheap_block"):
            assert verboden not in code, f"{naam} kijkt naar {verboden}"


def test_no_redundant_switch_when_already_correct(make_coordinator, hass):
    """Ventilator staat al aan en moet aan blijven - niet elke tick
    opnieuw turn_on sturen."""
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=48.0, buiten=34.0, vermogen=0, ventilator="on")

    asyncio.run(coordinator._async_apply_battery_cooling())

    assert not any(c[0] == "switch" for c in _calls(hass))


def test_state_is_exposed_even_without_action(make_coordinator, hass):
    """Het dashboard moet ook kloppen als er niets te schakelen valt."""
    coordinator = make_coordinator(_config())
    _situatie(hass, accu=36.0, buiten=34.0, vermogen=100)

    asyncio.run(coordinator._async_apply_battery_cooling())

    state = coordinator.battery_cooling_state
    assert state["accu_c"] == 36.0
    assert state["buiten_c"] == 34.0
    assert state["delta_c"] == 2.0
    assert state["ventilator_aan"] is False


# --- terugval op de bestaande buitentemperatuur ---------------------


def test_falls_back_to_the_existing_outdoor_temperature(make_coordinator, hass):
    """Zonder eigen buitensensor wordt de al beschikbare
    live-buitentemperatuur gebruikt."""
    config = _config()
    del config[CONF_BATTERY_COOLING_OUTDOOR_SENSOR]
    coordinator = make_coordinator(config)
    coordinator.climate_live_outdoor_temp_c = 34.0
    hass.states.set("sensor.accu_temp", "40.0")
    hass.states.set("sensor.accu_vermogen", "0")
    hass.states.set(FAN, "off")

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] == "aan"
    assert besluit["buiten_c"] == 34.0


def test_sensor_reports_the_current_state(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        BatteryCoolingSensor,
    )

    coordinator = make_coordinator(_config())
    _situatie(hass, accu=48.0, buiten=34.0, vermogen=0, ventilator="on")
    coordinator.battery_cooling_state = coordinator.evaluate_battery_cooling()

    sensor = BatteryCoolingSensor(coordinator, "entry1")

    assert sensor.native_value == "koelt"
    assert sensor.extra_state_attributes["accu_c"] == 48.0


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


# --- v1.73.0: niet koelen wat niet warm is ---------------------------

# Gemeld: "De koeling van de accu is nu wel heel veel aan, is dit
# daadwerkelijk zoveel nodig? (...) Ik kan me voorstellen dat hij pas bij
# ca. 25 graden actief gaat koelen?"


def _aan(accu, buiten, vermogen):
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    # v3.6.0: de functie kent nu ook de KANS om goedkoop te koelen, en
    # leest daarvoor de configuratie. Vandaar een echt object in plaats
    # van een aanroep op de klasse.
    class _Kaal:
        config: dict = {}
        _koelen_is_goedkoop = C._koelen_is_goedkoop

    return C._battery_cooling_should_turn_on(_Kaal(), accu, buiten, vermogen)


def _uit(accu, buiten, vermogen):
    """v3.14.0: de uitschakelregel kent nu ook de GOEDKOPE koeling, en
    leest daarvoor de configuratie. Vandaar een echt object in plaats van
    een aanroep op de klasse."""
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    class _Kaal:
        config: dict = {}
        _goedkope_koeling_nog_zinvol = C._goedkope_koeling_nog_zinvol

    return C._battery_cooling_should_turn_off(_Kaal(), accu, buiten, vermogen)


def test_the_logged_case_no_longer_starts_the_fan():
    """Uit de export van 13 augustus: de ventilator draaide bij 23 °C
    accutemperatuur, met als reden "1203W door de accu en al 3,0 °C
    boven buiten".

    Drie van de vier aanzetregels kijken naar het VERSCHIL met buiten of
    naar het vermogen. Op een frisse ochtend is de accu bijna altijd
    twee graden warmer - dat is normale afvoerwarmte.
    """
    assert _aan(30.0, 27.0, 1203.0) is None


def test_a_big_difference_on_a_cold_morning_is_not_a_reason():
    """Ook de vijf-graden-regel geldt niet als de accu zelf koud is: 20
    tegen 12 graden is acht graden verschil en volstrekt onschuldig."""
    assert _aan(28.0, 20.0, 0.0) is None


def test_above_the_floor_the_old_rules_still_apply():
    """Boven de ondergrens verandert er niets - dat is precies waar de
    koeling voor is."""
    assert _aan(38.0, 34.0, 1203.0) is not None
    assert _aan(52.0, 44.0, 0.0) is not None


def test_a_warm_battery_keeps_cooling_on_a_warm_day():
    """Uit de export van 12 augustus 15:27: "accu 32,0 °C, nog maar 1,9
    °C boven buiten" - en de ventilator ging uit. Bij 32 graden, het
    warmste punt van die dag, omdat het buiten óók warm was.
    """
    assert _uit(44.0, 42.1, 0.0) is False


def test_a_cold_battery_always_stops_cooling():
    """Onder de ondergrens valt er niets te koelen, ook als de andere
    voorwaarden nog niet zijn teruggevallen."""
    assert _uit(30.0, 23.0, 1500.0) is True


def test_the_hysteresis_in_the_middle_is_unchanged():
    """Tussen 25 en 30 graden gelden de oude regels met hun hysterese."""
    assert _uit(37.0, 36.0, 100.0) is True
    assert _uit(37.0, 30.0, 100.0) is False


def test_the_floor_matches_the_aging_threshold():
    """De grens waarboven doorgekoeld wordt is dezelfde als waarboven de
    verouderingsdrijvers de uren tellen - dan betekent "warm" overal
    hetzelfde."""
    from custom_components.energy_management_system.const import (
        AGING_HIGH_TEMPERATURE_C,
        BATTERY_COOLING_KEEP_RUNNING_ABOVE_C,
    )

    # v1.80.0: deze koppeling is vervallen. De koeling stuurt op de
    # OMVORMER, de verouderingsdrijvers tellen op de CELLEN - twee
    # verschillende grootheden, dus twee verschillende grenzen.
    assert BATTERY_COOLING_KEEP_RUNNING_ABOVE_C > AGING_HIGH_TEMPERATURE_C


def test_a_flickering_sensor_no_longer_toggles_the_fan(
    make_coordinator, hass
):
    """Uit de export van 13 augustus: twintig schakelingen in een uur,
    sommige binnen drie seconden. De temperatuursensor meldt hele graden
    en wipte tussen 24 en 25 - precies op de ondergrens van v1.73.0.

    Met hysterese blijft de ventilator staan waar hij staat zolang de
    accu tussen 24 en 26 zweeft.
    """
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    # Aan blijven: 24 en 25 mogen niet uitschakelen.
    assert _uit(34.0, 26.5, 500.0) is False
    assert _uit(33.0, 26.5, 500.0) is False

    # En niet aanslaan zolang hij onder de bovenste grens blijft.
    assert _aan(34.0, 26.5, 500.0) is None


def test_below_the_hysteresis_band_it_still_stops():
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    assert _uit(31.0, 23.0, 1500.0) is True


def test_above_the_band_it_still_starts():
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )

    assert _aan(38.0, 30.0, 0.0) is not None


# --- v1.99.0: minimale loop- en rusttijd -----------------------------


def test_the_fan_does_not_short_cycle(make_coordinator, hass):
    """Gevonden bij de controle van 15 augustus: de ventilator pendelde
    die nacht DERTIEN keer tussen 31 en 35 graden, om de twintig minuten.

    Geen sensorruis - de hysterese van v1.76.0 vangt dat al. Het is echt
    thermisch pendelen: de ventilator koelt de omvormer in minuten van 35
    naar 31, waarna hij weer opwarmt. Het systeem is dus sneller dan de
    band tussen 32 en 35 breed is.
    """
    from datetime import timedelta

    import custom_components.energy_management_system.coordinator as mod

    coordinator = make_coordinator(_config())
    nu = datetime(2026, 8, 15, 2, 0, tzinfo=timezone.utc)
    mod.dt_util.now = lambda: nu

    # De ventilator draait en is net aangezet.
    coordinator.battery_cooling_last_change = nu - timedelta(minutes=8)
    _situatie(hass, accu=31.0, buiten=23.0, vermogen=300)
    hass.states.set(FAN, "on")

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] is None
    assert "pendelen" in besluit["reden"]


def test_after_the_minimum_runtime_it_may_stop(make_coordinator, hass):
    from datetime import timedelta

    import custom_components.energy_management_system.coordinator as mod

    coordinator = make_coordinator(_config())
    nu = datetime(2026, 8, 15, 2, 0, tzinfo=timezone.utc)
    mod.dt_util.now = lambda: nu
    coordinator.battery_cooling_last_change = nu - timedelta(minutes=45)
    _situatie(hass, accu=33.0, buiten=31.5, vermogen=100)
    hass.states.set(FAN, "on")

    assert coordinator.evaluate_battery_cooling()["actie"] == "uit"


def test_a_pointless_fan_stops_immediately(make_coordinator, hass):
    """De uitzondering op de minimale looptijd moet SMAL zijn.

    Eerst stond er "onder de ondergrens", maar dat ondermijnde precies
    het geval dat de regel moet vangen: op 15 augustus schakelde hij uit
    bij 31 graden, en dat is onder de ondergrens van 32.

    Alleen als het verschil met buiten te klein is om nog iets te halen,
    hoeft er niet gewacht te worden.
    """
    from datetime import timedelta

    import custom_components.energy_management_system.coordinator as mod

    coordinator = make_coordinator(_config())
    nu = datetime(2026, 8, 15, 2, 0, tzinfo=timezone.utc)
    mod.dt_util.now = lambda: nu
    coordinator.battery_cooling_last_change = nu - timedelta(minutes=2)
    # Nauwelijks verschil met buiten: koelen levert niets op.
    _situatie(hass, accu=28.0, buiten=27.5, vermogen=100)
    hass.states.set(FAN, "on")

    assert coordinator.evaluate_battery_cooling()["actie"] == "uit"


def test_it_waits_before_starting_again(make_coordinator, hass):
    """Ook de andere kant op: net uitgezet betekent even niet aan."""
    from datetime import timedelta

    import custom_components.energy_management_system.coordinator as mod

    coordinator = make_coordinator(_config())
    nu = datetime(2026, 8, 15, 2, 0, tzinfo=timezone.utc)
    mod.dt_util.now = lambda: nu
    coordinator.battery_cooling_last_change = nu - timedelta(minutes=5)
    _situatie(hass, accu=36.0, buiten=25.0, vermogen=300)
    hass.states.set(FAN, "off")

    besluit = coordinator.evaluate_battery_cooling()

    assert besluit["actie"] is None
    assert "net uitgezet" in besluit["reden"]


# --- v3.6.0: koelen als het bijna niets kost -------------------------


def test_the_reported_case_now_cools():
    """Gemeld op 18 augustus 07:57: "De accu moet meer gekoeld worden,
    hij is nu 31 graden en de buitentemperatuur is veel lager."

    Terecht. De ventilator stond stil omdat 31 onder de drempel van 35
    ligt. Die drempel beschermt de OMVORMER - hij zegt niets over de
    vraag of koelen de moeite is. Bij 31 met 14,1 buiten is er bijna
    zeventien graden te halen voor een paar watt.
    """
    assert _aan(31.0, 14.1, 190.0) is not None


def test_a_small_difference_is_not_worth_it():
    """Zonder verschil met buiten valt er niets te halen, hoe warm de
    omvormer ook is."""
    assert _aan(31.0, 25.0, 190.0) is None


def test_a_cool_inverter_is_left_alone():
    """Onder de ondergrens wordt er sowieso niet gekoeld: dan is er niets
    te winnen, hoe koud het buiten ook is."""
    assert _aan(22.0, 4.0, 190.0) is None


def test_the_old_rules_are_untouched():
    """Boven 35 graden verandert er niets - de bestaande bescherming van
    de omvormer blijft precies zoals hij was."""
    assert _aan(38.0, 34.0, 1203.0) is not None
    assert _aan(52.0, 44.0, 0.0) is not None


def test_the_threshold_is_configurable():
    """De drempels zijn schattingen - Zendure publiceert niet wanneer de
    omvormer terugregelt (v1.80.0). Dan hoort de gebruiker eraan te
    kunnen draaien."""
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )
    from custom_components.energy_management_system.const import (
        CONF_BATTERY_COOLING_OPPORTUNITY_C,
    )

    class _Kaal:
        config = {CONF_BATTERY_COOLING_OPPORTUNITY_C: 34.0}
        _koelen_is_goedkoop = C._koelen_is_goedkoop

    # Met een hogere drempel blijft 31 graden ongemoeid.
    assert (
        C._battery_cooling_should_turn_on(_Kaal(), 31.0, 14.1, 190.0) is None
    )


def test_nonsense_in_the_setting_falls_back():
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )
    from custom_components.energy_management_system.const import (
        CONF_BATTERY_COOLING_OPPORTUNITY_C,
    )

    class _Kaal:
        config = {CONF_BATTERY_COOLING_OPPORTUNITY_C: "warm"}
        _koelen_is_goedkoop = C._koelen_is_goedkoop

    assert (
        C._battery_cooling_should_turn_on(_Kaal(), 31.0, 14.1, 190.0)
        is not None
    )


# --- v3.7.0: de tegel zegt wat er aan de hand is ---------------------


def test_the_tile_shows_both_temperatures():
    """Gemeld met een screenshot: "niet actief / Accu-koeling: niet
    actief" - twee keer hetzelfde en geen enkel getal.

    Terwijl er op dat moment 31,0 °C omvormer tegen 14,1 buiten in de
    toestand stond. De tegel liet het alleen niet zien.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    sjabloon = (
        Path(pkg.__file__).parent / "dashboard_template.yaml"
    ).read_text()
    # De regel van de koeltegel op de landingspagina.
    regel = next(
        r
        for r in sjabloon.splitlines()
        if "accu_koeling" in r and "°C omvormer" in r
    )
    kop = sjabloon.index(regel)
    blok = sjabloon[kop : kop + 1400]

    assert "buiten_c" in blok
    assert "delta_c" in blok
    assert "vermogen_w" in blok


def test_the_tile_does_not_repeat_itself():
    """"niet actief / Accu-koeling: niet actief" - de tweede regel
    voegde niets toe."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    sjabloon = (
        Path(pkg.__file__).parent / "dashboard_template.yaml"
    ).read_text()

    assert "Accu-koeling: {{ st }}" not in sjabloon


def test_an_inactive_state_says_why(make_coordinator, hass):
    """"niet actief" is niet te onderscheiden van een defect. Het kan
    drie dingen betekenen: geen ventilator ingesteld, geen
    temperatuursensor, of nog geen ronde geweest."""
    from custom_components.energy_management_system.sensor import (
        BatteryCoolingSensor,
    )

    c = make_coordinator({})
    c.battery_cooling_state = {}
    sensor = BatteryCoolingSensor(c, "entry")

    assert sensor.native_value == "geen ventilator ingesteld"


def test_a_missing_temperature_is_named(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        CONF_BATTERY_COOLING_FAN_SWITCH,
    )
    from custom_components.energy_management_system.sensor import (
        BatteryCoolingSensor,
    )

    c = make_coordinator({CONF_BATTERY_COOLING_FAN_SWITCH: "switch.vent"})
    c.battery_cooling_state = {}
    sensor = BatteryCoolingSensor(c, "entry")

    assert sensor.native_value == "geen temperatuur"


def test_a_working_state_is_unchanged(make_coordinator, hass):
    """De gewone gevallen blijven precies zoals ze waren."""
    from custom_components.energy_management_system.sensor import (
        BatteryCoolingSensor,
    )

    c = make_coordinator({})
    sensor = BatteryCoolingSensor(c, "entry")

    c.battery_cooling_state = {"ventilator_aan": True, "accu_c": 35.0}
    assert sensor.native_value == "koelt"

    c.battery_cooling_state = {"ventilator_aan": False, "accu_c": 31.0}
    assert sensor.native_value == "uit"


# --- v3.14.0: hysterese voor de goedkope koeling ---------------------


def test_the_cheap_cooling_keeps_running():
    """Gemeld: acht schakelingen in zes uur, netjes op de klok van de
    minimale looptijd.

    De regel uit v3.6.0 zette de ventilator aan bij 27 graden, waarna de
    gewone uitschakelregel hem meteen weer wilde stoppen omdat 27 onder
    de 32 ligt. Aan bij 27, uit bij 27 - dat is geen hysterese maar een
    tegenstelling.
    """
    # Het gemeten geval van 09:17: aan bij 27 met 14,8 buiten, met de
    # drempel op 25 (zelf ingesteld, standaard is 28).
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )
    from custom_components.energy_management_system.const import (
        CONF_BATTERY_COOLING_OPPORTUNITY_C,
    )

    class _Kaal:
        config = {CONF_BATTERY_COOLING_OPPORTUNITY_C: 25.0}
        _koelen_is_goedkoop = C._koelen_is_goedkoop
        _goedkope_koeling_nog_zinvol = C._goedkope_koeling_nog_zinvol

    assert (
        C._battery_cooling_should_turn_on(_Kaal(), 27.0, 14.8, 200.0)
        is not None
    )
    # En dan NIET meteen weer uit.
    assert (
        C._battery_cooling_should_turn_off(_Kaal(), 27.0, 14.8, 200.0) is False
    )


def test_it_stops_once_the_inverter_is_really_cool():
    """Gemeten om 09:47: 21 graden met 14,9 buiten. Bij een drempel van
    25 loopt de koeling door tot 20 - maar het verschil met buiten is
    dan nog maar 6,1 graden, en dat is te weinig."""
    assert _uit(21.0, 14.9, 200.0) is True


def test_the_hysteresis_band_is_wide_enough():
    """De ventilator haalt er in een half uur zes tot acht graden af
    (27 naar 21). Een smallere band zou dezelfde tegenstelling
    opleveren."""
    from custom_components.energy_management_system.const import (
        BATTERY_COOLING_OPPORTUNITY_HYSTERESE_C,
    )

    assert BATTERY_COOLING_OPPORTUNITY_HYSTERESE_C >= 4.0


def test_without_a_difference_it_stops_anyway():
    """Zonder verschil met buiten valt er niets te halen, ook niet
    binnen de band."""
    assert _uit(26.0, 25.0, 200.0) is True


def test_the_normal_rules_are_untouched():
    """Boven 32 graden verandert er niets - de bestaande bescherming van
    de omvormer blijft precies zoals hij was."""
    assert _uit(34.0, 26.5, 500.0) is False
    assert _uit(31.0, 29.5, 100.0) is True
