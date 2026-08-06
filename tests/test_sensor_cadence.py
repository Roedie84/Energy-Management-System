"""Meetfrequentie van bronsensoren zichtbaar maken (v1.1.4).

Gevraagd: "Had je dit eerder kunnen afvangen als de diagnostiek beter
was, en zitten er elders meer van dit soort zaken?"

Op het eerste: ja. De export toonde de UITKOMST (sensor-gezondheid 21%,
een reeks foutwaarden) maar nergens hoe vaak elke bronsensor eigenlijk
bijwerkte. Precies dat getal onderscheidt "de sensoren spreken elkaar
tegen" van "de sensoren meten op een ander tempo" - en alleen het tweede
was waar.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_AVAILABLE_ENERGY_SENSOR,
    SENSOR_CADENCE_MIN_SAMPLES,
    SENSOR_CADENCE_SLOW_PERCENT,
)

DAY0 = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


def _config():
    return {CONF_AVAILABLE_ENERGY_SENSOR: "sensor.beschikbaar"}


def test_a_sensor_that_follows_the_tick(make_coordinator, hass):
    c = make_coordinator(_config())
    for i in range(SENSOR_CADENCE_MIN_SAMPLES + 5):
        hass.states.set("sensor.beschikbaar", str(6.0 + i * 0.01))
        c._update_sensor_cadence_tracking()

    rapport = c.get_sensor_cadence_report()["sensor.beschikbaar"]

    assert rapport["status"] == "volgt_de_tick"
    assert rapport["beweegt_percent"] > 90


def test_a_slow_sensor_is_recognised(make_coordinator, hass):
    """Het gerapporteerde geval: beweegt maar bij een fractie van de
    ticks."""
    c = make_coordinator(_config())
    for i in range(SENSOR_CADENCE_MIN_SAMPLES + 10):
        # Beweegt eens per vijf ticks.
        hass.states.set("sensor.beschikbaar", str(6.0 + (i // 5) * 0.1))
        c._update_sensor_cadence_tracking()

    rapport = c.get_sensor_cadence_report()["sensor.beschikbaar"]

    assert rapport["status"] == "traag"
    assert rapport["beweegt_percent"] < SENSOR_CADENCE_SLOW_PERCENT


def test_no_verdict_below_the_minimum(make_coordinator, hass):
    c = make_coordinator(_config())
    for _ in range(5):
        hass.states.set("sensor.beschikbaar", "6.0")
        c._update_sensor_cadence_tracking()

    assert c.get_sensor_cadence_report()["sensor.beschikbaar"]["status"] == (
        "onvoldoende_data"
    )


def test_a_slow_sensor_is_informational_not_an_attention_point(
    make_coordinator, hass
):
    """Traag is geen storing. Het hoort zichtbaar te zijn zonder de
    systeemstatus omlaag te trekken - zelfde afweging als bij de
    NILM-duplicaten en de waterdekking."""
    c = make_coordinator(_config())
    for i in range(SENSOR_CADENCE_MIN_SAMPLES + 10):
        hass.states.set("sensor.beschikbaar", str(6.0 + (i // 5) * 0.1))
        c._update_sensor_cadence_tracking()

    samenvatting = c.get_diagnostic_summary()

    assert any("beweegt maar bij" in p for p in samenvatting["informatief"])
    assert not any("beweegt maar bij" in p for p in samenvatting["aandachtspunten"])


def test_the_window_stays_recent(make_coordinator, hass):
    """Zonder begrenzing zou het percentage een gemiddelde over maanden
    worden en een recente verslechtering verbergen."""
    from custom_components.energy_management_system.const import (
        SENSOR_CADENCE_HISTORY_LENGTH,
    )

    c = make_coordinator(_config())
    for i in range(SENSOR_CADENCE_HISTORY_LENGTH + 50):
        hass.states.set("sensor.beschikbaar", str(6.0 + i * 0.01))
        c._update_sensor_cadence_tracking()

    assert c.sensor_cadence["sensor.beschikbaar"]["ticks"] <= (
        SENSOR_CADENCE_HISTORY_LENGTH
    )


def test_it_is_in_the_diagnostics_export():
    """Het getal dat vorige keer ontbrak moet in de export staan."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert "sensor_cadence" in bron
