"""Gezondheidsscore uitgesplitst in nauwkeurigheid en beschikbaarheid
(v1.6.5).

Uit een diagnostiek-export: score 65% ("verminderd"), terwijl alle
dertien werkelijke vergelijkingen prima waren - 47 tot 141 W, ruim onder
de drempel van 300. De hele daling kwam door zeven momenten waarop de
sensor even wegviel.

Dat zijn twee volstrekt verschillende problemen. "Verminderd" leest als
"je metingen zijn onnauwkeurig", en dan ga je zoeken naar een meetfout
die er niet is - terwijl een wegvallende sensor een heel andere
oplossing vraagt.
"""
from custom_components.energy_management_system.const import (
    ENERGY_BALANCE_ERROR_BAD_THRESHOLD_W,
)

# De echte reeks uit de export.
ECHTE_REEKS = [
    80.7, 108.9, 66.8, 102.4, 95.9, 140.9, 93.8, 63.9, 72.1, 128.9,
    46.7, 117.5, None, None, None, 133.9, None, None, None, None,
]


def _met_historie(make_coordinator, historie, score=65.0, kwaliteit="verminderd"):
    c = make_coordinator({})
    c.energy_balance_error_history = list(historie)
    c.sensor_health_score = score
    c.measurement_quality = kwaliteit
    return c


# --- het gerapporteerde geval ----------------------------------------


def test_the_real_case_is_attributed_to_dropouts(make_coordinator, hass):
    c = _met_historie(make_coordinator, ECHTE_REEKS)

    uitsplitsing = c.get_sensor_health_breakdown()

    assert uitsplitsing["nauwkeurigheid_percent"] == 100.0
    assert uitsplitsing["beschikbaarheid_percent"] == 65.0
    assert uitsplitsing["hoofdoorzaak"] == "uitval"


def test_the_message_says_it_is_not_an_accuracy_problem(
    make_coordinator, hass
):
    """De kern: de melding moet je de juiste kant op sturen."""
    c = _met_historie(make_coordinator, ECHTE_REEKS)

    melding = next(
        p
        for p in c.get_diagnostic_summary()["aandachtspunten"]
        if "gezondheid" in p
    )

    # v1.14.9: de formulering is aangepast omdat "Niet door
    # onnauwkeurige metingen" onjuist was zodra er wél metingen buiten
    # de marge vielen. De strekking blijft: uitval is de hoofdoorzaak,
    # en de nauwkeurigheid staat er eerlijk bij.
    assert "Vooral doordat een sensor" in melding
    assert "13 vergelijkingen" in melding
    assert "7 van de 20" in melding


# --- het andere geval ------------------------------------------------


def test_genuine_inaccuracy_is_named_as_such(make_coordinator, hass):
    """Zijn de metingen écht onnauwkeurig, dan hoort de melding dát te
    zeggen - de correctie mag het echte probleem niet verbergen."""
    slecht = ENERGY_BALANCE_ERROR_BAD_THRESHOLD_W + 500
    c = _met_historie(make_coordinator, [50.0] * 5 + [slecht] * 15)

    uitsplitsing = c.get_sensor_health_breakdown()
    melding = next(
        p
        for p in c.get_diagnostic_summary()["aandachtspunten"]
        if "gezondheid" in p
    )

    assert uitsplitsing["hoofdoorzaak"] == "nauwkeurigheid"
    assert "Niet door onnauwkeurige metingen" not in melding
    assert "binnen de marge" in melding


def test_both_problems_at_once_names_the_biggest(make_coordinator, hass):
    """Bij beide problemen tegelijk wijst de melding naar de grootste
    veroorzaker - daar valt de meeste winst te halen."""
    slecht = ENERGY_BALANCE_ERROR_BAD_THRESHOLD_W + 500
    c = _met_historie(
        make_coordinator, [50.0] * 8 + [slecht] * 2 + [None] * 10
    )

    assert c.get_sensor_health_breakdown()["hoofdoorzaak"] == "uitval"


def test_a_perfect_history_has_no_cause(make_coordinator, hass):
    c = _met_historie(make_coordinator, [50.0] * 20, 100.0, "goed")

    assert c.get_sensor_health_breakdown()["hoofdoorzaak"] is None


def test_only_dropouts_and_no_comparisons(make_coordinator, hass):
    """Zonder enkele geldige vergelijking valt er niets over
    nauwkeurigheid te zeggen."""
    c = _met_historie(make_coordinator, [None] * 20, 0.0, "slecht")

    uitsplitsing = c.get_sensor_health_breakdown()

    assert uitsplitsing["nauwkeurigheid_percent"] is None
    assert uitsplitsing["hoofdoorzaak"] == "uitval"


def test_an_empty_history_says_nothing(make_coordinator, hass):
    c = _met_historie(make_coordinator, [], None, None)

    assert c.get_sensor_health_breakdown()["totaal"] == 0


# --- inbedding -------------------------------------------------------


def test_the_reliability_overview_shows_the_split(make_coordinator, hass):
    c = _met_historie(make_coordinator, ECHTE_REEKS)

    rij = next(
        r
        for r in c.get_reliability_overview()
        if r["naam"] == "Sensor-gezondheid (Kirchhoff)"
    )

    assert "niet uitleesbaar" in rij["reden"]


def test_it_is_in_the_diagnostics_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "sensor_health_breakdown" in bron


# --- v1.8.2: welke sensor viel weg? ---------------------------------


def _met_uitval(make_coordinator, hass, ontbrekend):
    from datetime import datetime, timezone

    from custom_components.energy_management_system.const import (
        CONF_AVAILABLE_ENERGY_SENSOR,
        CONF_BATTERY_POWER_SENSOR,
    )

    c = make_coordinator(
        {
            CONF_AVAILABLE_ENERGY_SENSOR: "sensor.beschikbaar",
            CONF_BATTERY_POWER_SENSOR: "sensor.accu_w",
        }
    )
    now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
    for entity_id, waarde in (
        ("sensor.beschikbaar", "6.5"),
        ("sensor.accu_w", "500"),
    ):
        hass.states.set(entity_id, "unavailable" if entity_id in ontbrekend else waarde)
    for _ in range(9):
        c._update_energy_balance_validation(now)
    return c


def test_the_missing_sensor_is_named(make_coordinator, hass):
    """Gerapporteerd: "Maar kan niet ingrijpen, dit omdat ik niet weet om
    welke sensor het gaat."

    Het aandachtspunt meldde wél dat er negen keer geen waarde was, maar
    niet van wie - en dan valt er niets te doen.
    """
    c = _met_uitval(make_coordinator, hass, {"sensor.beschikbaar"})
    c.energy_balance_error_history = [50.0] * 11 + [None] * 9
    c.sensor_health_score = 55.0
    c.measurement_quality = "verminderd"

    melding = next(
        p
        for p in c.get_diagnostic_summary()["aandachtspunten"]
        if "gezondheid" in p
    )

    assert "sensor.beschikbaar (9x)" in melding


def test_multiple_sensors_are_all_named(make_coordinator, hass):
    c = _met_uitval(
        make_coordinator, hass, {"sensor.beschikbaar", "sensor.accu_w"}
    )

    uitsplitsing = c.get_sensor_health_breakdown()

    assert set(uitsplitsing["uitval_per_sensor"]) == {
        "sensor.beschikbaar",
        "sensor.accu_w",
    }


def test_the_worst_offender_comes_first(make_coordinator, hass):
    """Bij meerdere sensoren wil je weten waar de meeste winst zit."""
    c = _met_uitval(make_coordinator, hass, {"sensor.beschikbaar"})
    c.balance_missing_by_entity = {"sensor.a": 2, "sensor.b": 15}

    eerste = next(iter(c.get_sensor_health_breakdown()["uitval_per_sensor"]))

    assert eerste == "sensor.b"


def test_no_dropouts_gives_an_empty_map(make_coordinator, hass):
    c = _met_uitval(make_coordinator, hass, set())

    assert c.get_sensor_health_breakdown()["uitval_per_sensor"] == {}


def test_the_counts_survive_a_restart(make_coordinator, hass):
    """De foutreeks blijft bewaard, dus de namen erbij moeten dat ook -
    anders wordt de melding na een herstart weer generiek."""
    import asyncio

    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "balance_missing_by_entity" in PERSISTED_PLAIN_FIELDS

    bron = make_coordinator({})
    bron.balance_missing_by_entity = {"sensor.x": 4}
    asyncio.run(bron.async_save_persisted_state_now())

    verse = make_coordinator({})
    asyncio.run(verse.async_load_persisted_state())

    assert verse.balance_missing_by_entity == {"sensor.x": 4}


def test_the_message_does_not_contradict_the_numbers(make_coordinator, hass):
    """v1.14.9: in een export stond 78,6% nauwkeurigheid terwijl de
    melding zei "alle 14 vergelijkingen vielen binnen de marge" - drie
    zaten er ruim boven (368, 798, 593 W).

    Een melding die zichzelf tegenspreekt maakt alle meldingen
    verdacht: je weet niet meer welk deel je kunt geloven.
    """
    c = make_coordinator({})
    c.energy_balance_error_history = (
        [97.0, 80.4, 43.2, 110.5, 51.1, 4.5, 14.5]
        + [None] * 6
        + [195.6, 86.1, 368.2, 35.8, 248.0, 797.8, 593.1]
    )
    c.balance_missing_by_entity = {"sensor.zendure": 8}
    c.sensor_health_score = 55.0
    c.measurement_quality = "verminderd"

    melding = next(
        p
        for p in c.get_diagnostic_summary()["aandachtspunten"]
        if "gezondheid" in p
    )

    assert "alle 14" not in melding
    assert "11 van de 14" in melding


def test_a_perfect_accuracy_still_says_all(make_coordinator, hass):
    """Bij écht alle metingen binnen de marge moet dat er ook staan -
    de correctie mag niet doorslaan naar omslachtig."""
    c = make_coordinator({})
    c.energy_balance_error_history = [50.0] * 14 + [None] * 6
    c.balance_missing_by_entity = {"sensor.zendure": 6}
    c.sensor_health_score = 70.0
    c.measurement_quality = "verminderd"

    melding = next(
        p
        for p in c.get_diagnostic_summary()["aandachtspunten"]
        if "gezondheid" in p
    )

    assert "alle 14 vergelijkingen" in melding


# --- v1.15.0: het oordeel overleeft een herstart --------------------


def test_the_quality_is_recomputed_from_the_history(make_coordinator, hass):
    """Gemeld in een export: `sensor_health_score` en
    `measurement_quality` stonden op None terwijl de foutreeks van
    twintig metingen wél was hersteld.

    De reeks wordt bewaard, het daaruit afgeleide oordeel niet - en dat
    werd alleen berekend bij een NIEUWE meting. Na een herstart was er
    dus wel data maar geen oordeel, en verdween het aandachtspunt terwijl
    het probleem gewoon doorliep. Precies het omgekeerde van wat je wilt.
    """
    c = make_coordinator({})
    c.energy_balance_error_history = (
        [97.0, 80.4, 43.2, 110.5, 51.1, 4.5, 14.5]
        + [None] * 6
        + [195.6, 86.1, 368.2, 35.8, 248.0, 797.8, 593.1]
    )
    assert c.sensor_health_score is None

    c._recompute_measurement_quality()

    assert c.sensor_health_score == 55.0
    assert c.measurement_quality == "verminderd"


def test_the_attention_point_returns_after_a_restart(make_coordinator, hass):
    """Het gevolg dat ertoe doet: de melding hoort terug te komen."""
    c = make_coordinator({})
    c.energy_balance_error_history = [50.0] * 11 + [None] * 9
    c.balance_missing_by_entity = {"sensor.zendure": 9}

    c._recompute_measurement_quality()

    assert any(
        "gezondheid" in p for p in c.get_diagnostic_summary()["aandachtspunten"]
    )


def test_too_few_samples_gives_no_verdict(make_coordinator, hass):
    """Onder de minimumdrempel hoort er geen oordeel te staan - ook niet
    na herberekening."""
    from custom_components.energy_management_system.const import (
        MEASUREMENT_QUALITY_MIN_SAMPLES,
    )

    c = make_coordinator({})
    c.energy_balance_error_history = [50.0] * (MEASUREMENT_QUALITY_MIN_SAMPLES - 1)

    c._recompute_measurement_quality()

    assert c.sensor_health_score is None


def test_it_runs_after_loading_the_stored_state():
    """Herberekenen is beter dan het oordeel bewaren: dan kan het nooit
    uit de pas lopen met de reeks waarop het rust."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    start = bron.index("self._state_store_loaded = True")

    assert "_recompute_measurement_quality()" in bron[start : start + 500]
