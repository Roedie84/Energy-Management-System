"""Kirchhoff-style energy-balance validation (v0.63.28): cross-checks
the battery power sensor against what the available-energy sensor's
rate of change implies the battery power must be. Uses only sensors
already configured, not a new measurement - catches a stale/unavailable
sensor, a wrong entity, a unit mismatch, or a sign-convention issue.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import (
    MEASUREMENT_QUALITY_MIN_SAMPLES,
)

DAY0 = datetime(2026, 8, 4, tzinfo=timezone.utc)

# v1.1.6: de balanscheck wacht op ENERGY_BALANCE_MIN_INTERVAL_MINUTES.
# De sensor stapt in hele SoC-procenten; over een kort interval zou de
# check de resolutie meten in plaats van de sensoren. Deze tests
# gebruiken daarom een realistisch interval.
STAP = 35


def _fill_window(coordinator, waarde):
    """Vult het venster tot net onder de minimumdrempel (v0.63.121).

    Sinds v0.63.121 wordt er pas een oordeel geveld vanaf
    MEASUREMENT_QUALITY_MIN_SAMPLES metingen - anders leverde één
    afwijkende meting meteen "slecht (0.0%, 1 metingen)" op. De tests
    hieronder controleren de REKENREGEL, niet die drempel, dus vullen ze
    het venster eerst met metingen van het gewenste soort.
    """
    coordinator.energy_balance_error_history = [waarde] * (
        MEASUREMENT_QUALITY_MIN_SAMPLES - 1
    )


def _base_config(**overrides):
    config = {
        "available_energy_sensor_entity": "sensor.available_energy",
        "battery_power_sensor_entity": "sensor.battery_power",
    }
    config.update(overrides)
    return config


def test_first_tick_only_seeds(make_coordinator, hass):
    hass.states.set("sensor.available_energy", "3.0")
    hass.states.set("sensor.battery_power", "0")

    coordinator = make_coordinator(_base_config())
    coordinator._update_energy_balance_validation(DAY0)

    assert coordinator.last_energy_balance_error_w is None
    assert coordinator.sensor_health_score is None


def test_consistent_readings_score_perfectly(make_coordinator, hass):
    """Battery discharging at 1000W for 35 minutes should drain
    1000W*(35/60)h = 0.5833 kWh - if the available-energy sensor agrees,
    the error should be ~0 and the health score 100."""
    hass.states.set("sensor.available_energy", "3.0")
    hass.states.set("sensor.battery_power", "1000")

    coordinator = make_coordinator(_base_config())
    coordinator._update_energy_balance_validation(DAY0)
    _fill_window(coordinator, 0.0)

    later = DAY0 + timedelta(minutes=STAP)
    hass.states.set("sensor.available_energy", "2.4167")  # -0.5833 kWh over 35 min = -1000W
    coordinator._update_energy_balance_validation(later)

    assert abs(coordinator.last_energy_balance_error_w) < 1.0
    assert coordinator.sensor_health_score == 100.0
    assert coordinator.measurement_quality == "goed"


def test_large_mismatch_is_flagged(make_coordinator, hass):
    """Battery power sensor claims idle (0W), but available_kwh dropped
    fast - implies a large discrepancy, e.g. a wrong/stale sensor."""
    hass.states.set("sensor.available_energy", "3.0")
    hass.states.set("sensor.battery_power", "0")

    coordinator = make_coordinator(_base_config())
    coordinator._update_energy_balance_validation(DAY0)
    _fill_window(coordinator, 99999.0)

    later = DAY0 + timedelta(minutes=STAP)
    hass.states.set("sensor.available_energy", "-3.0")  # -6.0 kWh over 35 min, ver boven de drempel
    coordinator._update_energy_balance_validation(later)

    assert abs(coordinator.last_energy_balance_error_w) > 9000
    assert coordinator.sensor_health_score == 0.0
    assert coordinator.measurement_quality == "slecht"


def test_missing_sensor_reading_counts_as_a_bad_sample(make_coordinator, hass):
    hass.states.set("sensor.available_energy", "3.0")
    hass.states.set("sensor.battery_power", "500")

    coordinator = make_coordinator(_base_config())
    coordinator._update_energy_balance_validation(DAY0)
    _fill_window(coordinator, 99999.0)

    # Battery power sensor goes unavailable.
    hass.states.set("sensor.battery_power", "unavailable")
    later = DAY0 + timedelta(minutes=STAP)
    coordinator._update_energy_balance_validation(later)

    assert coordinator.sensor_health_score == 0.0
    assert coordinator.measurement_quality == "slecht"


def test_stale_gap_after_a_restart_is_not_counted_as_an_error(make_coordinator, hass):
    """A restart-sized gap shouldn't be misattributed to a single power
    level, same staleness principle as the hourly trackers."""
    hass.states.set("sensor.available_energy", "3.0")
    hass.states.set("sensor.battery_power", "0")

    coordinator = make_coordinator(_base_config())
    coordinator._update_energy_balance_validation(DAY0)

    much_later = DAY0 + timedelta(hours=3)
    hass.states.set("sensor.available_energy", "1.0")
    coordinator._update_energy_balance_validation(much_later)

    assert coordinator.energy_balance_error_history == []


def test_health_score_averages_over_a_rolling_window(make_coordinator, hass):
    # Beginwaarde gelijk aan waar de lus hieronder vanaf rekent - anders
    # is de allereerste meting kunstmatig fout.
    hass.states.set("sensor.available_energy", "100.0")
    # v1.1.3: het vermogen bij de eerste meting telt mee in het eerste
    # venster (het is het vermogen aan het begin van dat interval), dus
    # hier meteen op de waarde zetten die de rest van de test aanhoudt.
    hass.states.set("sensor.battery_power", "1000")

    coordinator = make_coordinator(_base_config())
    now = DAY0
    coordinator._update_energy_balance_validation(now)

    # v1.1.3: een onveranderde sensor levert nu GEEN meting meer op -
    # dat is geen goede meting maar geen meting. Goede ticks moeten dus
    # een beweging tonen die klopt met het gemeten vermogen: 1000 W
    # ontladen gedurende 6 minuten is precies 0,1 kWh.
    beschikbaar = 100.0
    for _ in range(15):
        now = now + timedelta(minutes=STAP)
        # 1000 W gedurende 35 minuten = 0,5833 kWh.
        beschikbaar -= 0.5833
        hass.states.set("sensor.available_energy", f"{beschikbaar:.4f}")
        coordinator._update_energy_balance_validation(now)

    # 5 slechte ticks (telkens een veel grotere, onverklaarde daling).
    for _ in range(5):
        now = now + timedelta(minutes=STAP)
        beschikbaar -= 30.0
        hass.states.set("sensor.available_energy", f"{beschikbaar:.4f}")
        coordinator._update_energy_balance_validation(now)

    # 15 goed, 5 slecht op 20 metingen -> 75%.
    assert coordinator.sensor_health_score == pytest.approx(75.0)
    assert coordinator.measurement_quality == "verminderd"


def test_no_action_without_both_sensors_configured(make_coordinator, hass):
    coordinator = make_coordinator(
        {"available_energy_sensor_entity": "sensor.available_energy"}
    )
    hass.states.set("sensor.available_energy", "3.0")
    coordinator._update_energy_balance_validation(DAY0)

    assert coordinator.sensor_health_score is None
