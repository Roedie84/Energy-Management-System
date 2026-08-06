"""Grootste bekende verbruiker op de visuele kaart (v0.63.130).

Gerapporteerd: "In de visual is nu de zwaarste bron nog niet zichtbaar,
mijn inziens is er altijd een zwaarste bron ook al zou die maar 10 W
zijn."

Oorzaak: de kaart toonde `heavy_load_source`, een BESLISLOGICA-signaal
dat alleen iets teruggeeft als een specifiek zwaar apparaat aantoonbaar
draait (vaatwasser, wasmachine, Quooker, airco, oven, kookplaat). Dat
signaal dient om de mediaan-voorzichtigheid van de verbruikscorrectie
over te slaan en hoort dus meestal leeg te zijn. Het label beloofde iets
anders dan het attribuut betekende.

Nu een eigen berekening over de bevestigde NILM-apparaten: van alles met
een eigen vermogensmeting degene die nu het meeste trekt.
"""
from custom_components.energy_management_system.sensor import ExplanationSensor


def _bevestig(coordinator, hass, entity_id, naam, watt):
    coordinator.nilm_confirmed_devices[entity_id] = {
        "friendly_name": naam,
        "daily_avg_history": [],
        "anomaly_detected": False,
    }
    hass.states.set(entity_id, str(watt), {"unit_of_measurement": "W"})


def test_picks_the_highest_consumer(make_coordinator, hass):
    coordinator = make_coordinator({})
    _bevestig(coordinator, hass, "sensor.koelkast", "Koelkast", 82)
    _bevestig(coordinator, hass, "sensor.tv", "Televisie", 120)
    _bevestig(coordinator, hass, "sensor.lamp", "Lamp", 8)

    assert coordinator.get_largest_known_consumer() == "Televisie (120 W)"


def test_a_small_consumer_still_counts(make_coordinator, hass):
    """De kern van de melding: ook 10 W is een grootste verbruiker."""
    coordinator = make_coordinator({})
    _bevestig(coordinator, hass, "sensor.lamp", "Lamp", 10)

    assert coordinator.get_largest_known_consumer() == "Lamp (10 W)"


def test_production_entities_are_skipped(make_coordinator, hass):
    """Onder de bevestigde apparaten zitten ook productie-entiteiten die
    negatief meten - dat is geen verbruiker."""
    coordinator = make_coordinator({})
    _bevestig(coordinator, hass, "sensor.aquarium_productie", "Aquarium productie", -40)
    _bevestig(coordinator, hass, "sensor.lamp", "Lamp", 8)

    assert coordinator.get_largest_known_consumer() == "Lamp (8 W)"


def test_zero_watt_is_not_reported_as_a_consumer(make_coordinator, hass):
    """"Grootste verbruiker: 0 W" is geen informatie."""
    coordinator = make_coordinator({})
    _bevestig(coordinator, hass, "sensor.lamp", "Lamp", 0)

    assert coordinator.get_largest_known_consumer() == "geen gemeten apparaat actief"


def test_unreadable_sensors_are_skipped(make_coordinator, hass):
    coordinator = make_coordinator({})
    _bevestig(coordinator, hass, "sensor.stuk", "Stuk", 0)
    hass.states.set("sensor.stuk", "unavailable")
    _bevestig(coordinator, hass, "sensor.lamp", "Lamp", 15)

    assert coordinator.get_largest_known_consumer() == "Lamp (15 W)"


def test_falls_back_to_the_heavy_load_signal(make_coordinator, hass):
    """Zonder bevestigde NILM-apparaten moet een draaiende vaatwasser
    alsnog zichtbaar zijn."""
    coordinator = make_coordinator({})
    coordinator.last_heavy_load_source = "vaatwasser"

    assert coordinator.get_largest_known_consumer() == "vaatwasser"


def test_nilm_devices_win_over_the_fallback(make_coordinator, hass):
    """Een concreet apparaat met een gemeten waarde zegt meer dan een
    categorielabel."""
    coordinator = make_coordinator({})
    coordinator.last_heavy_load_source = "vaatwasser"
    _bevestig(coordinator, hass, "sensor.oven", "Oven", 2100)

    assert coordinator.get_largest_known_consumer() == "Oven (2100 W)"


def test_nothing_known_is_stated_honestly(make_coordinator, hass):
    coordinator = make_coordinator({})

    assert coordinator.get_largest_known_consumer() == "geen gemeten apparaat actief"


def test_never_returns_none(make_coordinator, hass):
    """Een leeg attribuut liet het vak op de kaart leeg - precies de
    klacht. Er moet altijd tekst uit komen."""
    coordinator = make_coordinator({})

    waarde = coordinator.get_largest_known_consumer()
    assert isinstance(waarde, str) and waarde


def test_exposed_on_the_explanation_sensor(make_coordinator, hass):
    coordinator = make_coordinator({})
    _bevestig(coordinator, hass, "sensor.tv", "Televisie", 120)

    sensor = ExplanationSensor(coordinator, "entry1")

    assert sensor.extra_state_attributes["grootste_verbruiker"] == (
        "Televisie (120 W)"
    )


def test_card_uses_the_new_attribute():
    """De kaart mag niet meer op `heavy_load_source` staan - dat is een
    beslislogica-signaal, geen verbruikersaanduiding."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg
    import yaml

    data = yaml.safe_load(
        (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text()
    )
    kaart = next(
        card
        for view in data["views"]
        for card in view.get("cards") or []
        if card.get("type") == "picture-elements"
    )
    attributen = [e.get("attribute") for e in kaart["elements"]]

    assert "grootste_verbruiker" in attributen
    assert "heavy_load_source" not in attributen


def test_svg_label_matches_what_is_shown():
    """Het label beloofde "zwaarste bron" terwijl er iets anders stond;
    tekening en inhoud moeten hetzelfde zeggen."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    svg = (Path(pkg.__file__).parent / "overview_background.svg").read_text()

    assert "GROOTSTE VERBRUIKER" in svg
    assert "ZWAARSTE BRON" not in svg
