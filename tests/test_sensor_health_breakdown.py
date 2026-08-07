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

    assert "Niet door onnauwkeurige metingen" in melding
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
