"""Uitschieter-filter sloeg aan op gewone meetruis (v1.0.6).

Gerapporteerd: "Uitschieter genegeerd: 24.3°C wijkt te snel af van
24.7°C ... Net was het andersom, betekent dit dan dat er ca. 60 minuten
geen correcte waarde wordt geïnterpreteerd?"

Root cause: het filter toetste alleen op TEMPO. Bij een tick van vijf
minuten komt 0,4 °C neer op 4,8 °C/uur en dat overschrijdt de
plausibiliteitsgrens van 4 °C/uur - terwijl 0,4 °C gewoon ruis is. Hoe
korter het interval, hoe absurder de toets: over één minuut haalde zelfs
0,07 °C de drempel al.

Gevolg: het filter sloeg heen en weer tussen twee volstrekt normale
waarden ("net was het andersom") en hield ondertussen een verouderde
waarde vast. Een echte zonneflits herken je aan een GROTE sprong in
korte tijd, dus beide voorwaarden moeten gelden.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES,
    BACKYARD_TEMP_SPIKE_MIN_DEVIATION_C,
    CONF_BACKYARD_TEMPERATURE_SENSOR,
)

NOW = datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc)
SENSOR = "sensor.achtertuin_temp"


def _coordinator(make_coordinator, hass, start_temp):
    c = make_coordinator({CONF_BACKYARD_TEMPERATURE_SENSOR: SENSOR})
    hass.states.set(SENSOR, str(start_temp))
    c._get_filtered_backyard_temp_c(NOW)  # eerste meting = referentie
    return c


def _meet(c, hass, temp, minuten):
    hass.states.set(SENSOR, str(temp))
    return c._get_filtered_backyard_temp_c(NOW + timedelta(minutes=minuten))


# --- de gerapporteerde situatie -------------------------------------


def test_small_fluctuation_is_accepted(make_coordinator, hass):
    """Exact het gerapporteerde geval: 24,7 -> 24,3 na vijf minuten."""
    c = _coordinator(make_coordinator, hass, 24.7)

    assert _meet(c, hass, 24.3, minuten=5) == 24.3
    assert c.last_backyard_spike_filtered_note is None


def test_it_no_longer_flip_flops(make_coordinator, hass):
    """"Net was het andersom" - het filter wees beide richtingen af en
    hield zo een verouderde waarde vast."""
    c = _coordinator(make_coordinator, hass, 24.7)

    assert _meet(c, hass, 24.3, minuten=5) == 24.3
    assert _meet(c, hass, 24.7, minuten=10) == 24.7
    assert _meet(c, hass, 24.4, minuten=15) == 24.4


def test_even_a_one_minute_interval_is_fine(make_coordinator, hass):
    """Op één minuut haalde vroeger zelfs 0,07 °C de drempel."""
    c = _coordinator(make_coordinator, hass, 24.7)

    assert _meet(c, hass, 24.6, minuten=1) == 24.6


# --- echte uitschieters moeten nog steeds gevangen worden -----------


def test_a_real_sun_flash_is_still_ignored(make_coordinator, hass):
    """Waar het filter voor gemaakt is: direct zonlicht op de behuizing
    geeft een grote sprong in korte tijd."""
    c = _coordinator(make_coordinator, hass, 24.0)

    assert _meet(c, hass, 32.0, minuten=5) == 24.0
    assert "Uitschieter genegeerd" in c.last_backyard_spike_filtered_note


def test_a_sustained_real_change_is_accepted_after_the_window(
    make_coordinator, hass
):
    """Een koufront of een echte opwarming moet er na het
    bevestigingsvenster alsnog doorheen komen - het filter mag niets
    permanent bevriezen."""
    c = _coordinator(make_coordinator, hass, 24.0)

    _meet(c, hass, 32.0, minuten=5)
    resultaat = _meet(
        c, hass, 32.0, minuten=5 + BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES + 1
    )

    assert resultaat == 32.0


def test_the_threshold_sits_between_noise_and_a_flash(make_coordinator, hass):
    """Net onder de drempel geaccepteerd, ruim erboven geweigerd."""
    c = _coordinator(make_coordinator, hass, 24.0)
    net_onder = 24.0 + BACKYARD_TEMP_SPIKE_MIN_DEVIATION_C - 0.1

    assert _meet(c, hass, round(net_onder, 2), minuten=1) == round(net_onder, 2)


def test_a_large_but_slow_change_is_accepted(make_coordinator, hass):
    """Acht graden over een halve dag is geen uitschieter maar gewoon
    het weer - de tempotoets hoort dat door te laten."""
    c = _coordinator(make_coordinator, hass, 16.0)

    assert _meet(c, hass, 24.0, minuten=720) == 24.0


# --- de melding zelf ------------------------------------------------


def test_the_note_clears_once_a_normal_value_returns(make_coordinator, hass):
    """Een opgeloste uitschieter mag niet op het dashboard blijven
    staan."""
    c = _coordinator(make_coordinator, hass, 24.0)
    _meet(c, hass, 32.0, minuten=5)
    assert c.last_backyard_spike_filtered_note is not None

    _meet(c, hass, 24.1, minuten=10)

    assert c.last_backyard_spike_filtered_note is None


def test_both_conditions_are_required(make_coordinator, hass):
    """De kern van de fix, expliciet: een onwaarschijnlijk TEMPO alleen
    is niet genoeg, er moet ook een noemenswaardige SPRONG zijn."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    start = bron.index("deviation_c = abs(raw_temp")
    blok = bron[start : start + 1400]

    assert "BACKYARD_TEMP_SPIKE_MIN_DEVIATION_C" in blok
    assert "BACKYARD_TEMP_MAX_PLAUSIBLE_RATE_C_PER_HOUR" in blok
