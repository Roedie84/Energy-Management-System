"""Ontbrekend oordeel is geen slecht oordeel (v1.15.2).

Gemeld met screenshot: "⚠️ onbetrouwbaar kirchhoff — Score None% -
sensoren zelf lijken inconsistent."

Twee dingen die niet samengaan. `(self.sensor_health_score or 0)` viel
bij None terug op nul, waardoor een ONTBREKEND oordeel dezelfde tak in
ging als een SLECHT oordeel.

Dat zijn verschillende dingen: geen score betekent dat er nog niet genoeg
te vergelijken viel, niet dat de sensoren elkaar tegenspreken. Zo'n
melding is erger dan geen melding - hij stuurt je op zoek naar een
sensorprobleem dat er niet is.
"""
from datetime import datetime, timezone

from custom_components.energy_management_system.const import (
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    ENERGY_BALANCE_ERROR_HISTORY_LENGTH,
    MEASUREMENT_QUALITY_GOOD_THRESHOLD,
)

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


def _coordinator(make_coordinator, score, historie=None):
    c = make_coordinator(
        {
            CONF_AVAILABLE_ENERGY_SENSOR: "sensor.beschikbaar",
            CONF_BATTERY_POWER_SENSOR: "sensor.accu_w",
        }
    )
    c.energy_balance_error_history = (
        historie
        if historie is not None
        else [None] * ENERGY_BALANCE_ERROR_HISTORY_LENGTH
    )
    c.sensor_health_score = score
    c._update_advisory_readiness(NOW)
    return c.advisory_readiness["kirchhoff"]


# --- het gerapporteerde geval ----------------------------------------


def test_a_missing_score_is_not_called_unreliable(make_coordinator, hass):
    oordeel = _coordinator(make_coordinator, None)

    assert oordeel["status"] == "onvoldoende_data"
    assert "None%" not in oordeel["reden"]


def test_the_reason_explains_what_is_missing(make_coordinator, hass):
    """"Onvoldoende data" zonder te zeggen waaraan het ligt, laat je met
    de vraag zitten wat je eraan kunt doen."""
    oordeel = _coordinator(make_coordinator, None)

    assert "geen waarde" in oordeel["reden"]


# --- de andere takken blijven werken ---------------------------------


def test_a_low_score_is_still_flagged(make_coordinator, hass):
    """De correctie mag een echt probleem niet verbergen."""
    oordeel = _coordinator(
        make_coordinator,
        MEASUREMENT_QUALITY_GOOD_THRESHOLD - 20,
        historie=[500.0] * ENERGY_BALANCE_ERROR_HISTORY_LENGTH,
    )

    assert oordeel["status"] == "kwaliteit_te_laag"
    assert "inconsistent" in oordeel["reden"]


def test_a_good_score_is_ready(make_coordinator, hass):
    oordeel = _coordinator(
        make_coordinator,
        MEASUREMENT_QUALITY_GOOD_THRESHOLD + 5,
        historie=[50.0] * ENERGY_BALANCE_ERROR_HISTORY_LENGTH,
    )

    assert oordeel["status"] == "klaar"


def test_too_few_samples_comes_first(make_coordinator, hass):
    """De volgorde van de takken moet blijven: te weinig metingen gaat
    voor op een ontbrekend oordeel."""
    oordeel = _coordinator(make_coordinator, None, historie=[50.0] * 3)

    assert oordeel["status"] == "onvoldoende_data"
    assert "3/" in oordeel["reden"]


# --- borging ---------------------------------------------------------


def test_no_none_percentage_reaches_a_reason(make_coordinator, hass):
    """Een reden met "None%" erin is altijd een fout: er staat dan een
    getal aangekondigd dat er niet is."""
    for score in (None, 10.0, 95.0):
        oordeel = _coordinator(make_coordinator, score)
        assert "None" not in oordeel["reden"], score
