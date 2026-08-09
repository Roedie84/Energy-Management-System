"""Waterverbruik toewijzen aan een bron (v1.18.0).

Gevraagd: "Tevens is het volgens mij mogelijk om te detecteren waar water
voor is gebruikt. Vaatwasser aan = water naar vaatwasser, wasmachine aan
= water naar wasmachine. Ketel aan en waterverbruik langer dan 3 minuten
is douchen, korter dan 3 minuten is tandenpoetsen. Quooker aan +
waterverbruik is keuken. Misschien is er een mechanisme te bedenken zodat
ik ook daadwerkelijk kan bevestigen dat bijvoorbeeld de wc is
doorgespoeld, en je daarvan leert?"

Plus: "Ik weet zeker dat de waterontharder nog niet heeft geregenereerd,
misschien de drempel anders leggen?"
"""
from custom_components.energy_management_system.const import (
    CONF_DISHWASHER_POWER_SENSOR,
    CONF_QUOOKER_POWER_SENSOR,
    CONF_WASHING_MACHINE_POWER_SENSOR,
    WATER_SOFTENER_MIN_DURATION_MINUTES,
    WATER_SOFTENER_MIN_LITERS,
)

APPARATEN = ("sensor.vw", "sensor.wm", "sensor.qk", "sensor.cv_ketel_vermogen")


def _coordinator(make_coordinator, hass):
    c = make_coordinator(
        {
            CONF_DISHWASHER_POWER_SENSOR: "sensor.vw",
            CONF_WASHING_MACHINE_POWER_SENSOR: "sensor.wm",
            CONF_QUOOKER_POWER_SENSOR: "sensor.qk",
        }
    )
    # De CV-ketel komt uit de bevestigde NILM-apparaten, niet uit een
    # eigen configuratieveld - gevraagd: "CV ketel kan toch op basis van
    # het vermogen dat je al weet?"
    c.nilm_confirmed_devices = {
        "sensor.cv_ketel_vermogen": {"friendly_name": "CV-ketel Vermogen"}
    }
    for naam in APPARATEN:
        hass.states.set(naam, "0")
    return c


def _met(hass, **standen):
    for naam in APPARATEN:
        hass.states.set(naam, "0")
    for naam, waarde in standen.items():
        hass.states.set(naam, waarde)


# --- de vier apparaten -----------------------------------------------


def test_a_running_dishwasher_claims_the_water(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    _met(hass, **{"sensor.vw": "1800"})

    assert c.classify_water_session(12.0, 3.0)["bron"] == "vaatwasser"


def test_a_running_washing_machine_claims_the_water(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    _met(hass, **{"sensor.wm": "2100"})

    assert c.classify_water_session(18.0, 5.0)["bron"] == "wasmachine"


def test_the_boiler_plus_duration_means_a_shower(make_coordinator, hass):
    """Het onderscheid dat gevraagd werd: langer dan drie minuten is
    douchen."""
    c = _coordinator(make_coordinator, hass)
    _met(hass, **{"sensor.cv_ketel_vermogen": "900"})

    resultaat = c.classify_water_session(45.0, 8.0)

    assert resultaat["bron"] == "douche"
    assert "8.0 minuten" in resultaat["reden"]


def test_the_boiler_plus_a_short_tap_is_not_a_shower(make_coordinator, hass):
    """Korter dan drie minuten: handen wassen of tandenpoetsen."""
    c = _coordinator(make_coordinator, hass)
    _met(hass, **{"sensor.cv_ketel_vermogen": "900"})

    assert c.classify_water_session(1.2, 0.6)["bron"] == "warm water kort"


def test_the_quooker_means_the_kitchen(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    _met(hass, **{"sensor.qk": "120"})

    assert c.classify_water_session(1.5, 0.4)["bron"] == "keuken"


def test_the_boiler_comes_from_the_confirmed_devices(make_coordinator, hass):
    """Geen apart configuratieveld dat fout ingevuld kan worden."""
    c = _coordinator(make_coordinator, hass)
    hass.states.set("sensor.cv_ketel_vermogen", "900")

    assert c._boiler_power_w() == 900.0


# --- het toilet ------------------------------------------------------


def test_a_flush_is_recognised_by_its_volume(make_coordinator, hass):
    """Zonder apparaat is het volumepatroon het enige signaal. Een
    spoeling is opvallend constant - dat is juist wat hem herkenbaar
    maakt."""
    c = _coordinator(make_coordinator, hass)

    resultaat = c.classify_water_session(6.2, 0.7)

    assert resultaat["bron"] == "toilet"
    assert resultaat["zekerheid"] == "mogelijk"


def test_a_long_session_is_not_a_flush(make_coordinator, hass):
    """Zes liter over vijf minuten is een kraan, geen spoeling."""
    c = _coordinator(make_coordinator, hass)

    assert c.classify_water_session(6.2, 5.0)["bron"] is None


def test_an_unrecognised_session_says_so(make_coordinator, hass):
    """Gokken is erger dan toegeven dat je het niet weet."""
    c = _coordinator(make_coordinator, hass)

    resultaat = c.classify_water_session(22.0, 4.0)

    assert resultaat["bron"] is None
    assert resultaat["zekerheid"] == "onbekend"


# --- bevestigen en leren ---------------------------------------------


def test_confirming_records_the_pattern(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    c.water_session_history = [{"liter": 6.4, "duur_minuten": 0.8}]

    c.confirm_water_source("toilet")

    assert c.water_session_history[-1]["bron"] == "toilet"
    assert c.water_session_history[-1]["zekerheid"] == "bevestigd"
    assert c.water_source_profiles["toilet"]["liters"] == [6.4]


def test_the_learned_pattern_beats_the_rule_of_thumb(make_coordinator, hass):
    """De kern van het leren: jouw wc kan 4,5 of 9 liter spoelen. Na een
    paar bevestigingen hoort dát het uitgangspunt te zijn, niet de
    algemene 6 liter."""
    c = _coordinator(make_coordinator, hass)
    for liters in (9.1, 9.0, 9.2, 8.9):
        c.water_session_history = [{"liter": liters, "duur_minuten": 1.0}]
        c.confirm_water_source("toilet")

    resultaat = c.classify_water_session(9.0, 1.0)

    assert resultaat["bron"] == "toilet"
    assert resultaat["zekerheid"] == "geleerd"
    assert "4 bevestigingen" in resultaat["reden"]


def test_a_few_confirmations_are_not_enough(make_coordinator, hass):
    """Twee bevestigingen zeggen nog niets over spreiding."""
    c = _coordinator(make_coordinator, hass)
    for liters in (9.1, 9.0):
        c.water_session_history = [{"liter": liters, "duur_minuten": 1.0}]
        c.confirm_water_source("toilet")

    assert c.classify_water_session(9.0, 1.0)["zekerheid"] != "geleerd"


def test_the_overview_shows_what_was_learned(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    for liters in (9.1, 9.0, 9.2):
        c.water_session_history = [{"liter": liters, "duur_minuten": 1.0}]
        c.confirm_water_source("toilet")

    overzicht = c.get_water_source_overview()

    assert overzicht["toilet"]["bevestigingen"] == 3
    assert overzicht["toilet"]["typisch_liter"] == 9.1


def test_the_service_exists():
    """Zonder dienst is er niets om op te klikken."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    pakket = Path(pkg.__file__).parent
    assert "confirm_water_source" in (pakket / "services.yaml").read_text()
    assert "confirm_water_source" in (pakket / "__init__.py").read_text()


# --- de ontharder-drempel --------------------------------------------


def test_the_softener_threshold_matches_reality():
    """Gemeld: de ontharder had niet geregenereerd. De drempel stond op
    tien liter - dat haalt een wc-spoeling plus een kraan al. Een echte
    regeneratie spoelt de harslaag met pekel en spoelt na: 50 tot 200
    liter over 20 tot 60 minuten."""
    assert WATER_SOFTENER_MIN_LITERS >= 40.0
    assert WATER_SOFTENER_MIN_DURATION_MINUTES >= 15.0


def test_both_criteria_are_required():
    """Volume alleen is niet genoeg: een snelle sessie van veertig liter
    is eerder een bad of een lekkage."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    start = bron.index("WATER_SOFTENER_NIGHT_WINDOW_START_HOUR\n")
    blok = bron[start : bron.index("):", start)]

    assert "WATER_SOFTENER_MIN_LITERS" in blok
    assert "WATER_SOFTENER_MIN_DURATION_MINUTES" in blok
