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
import pytest

from custom_components.energy_management_system.const import (
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    SENSOR_CADENCE_MIN_SAMPLES,
    SENSOR_CADENCE_SLOW_PERCENT,
)

DAY0 = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


def _config():
    return {
        CONF_AVAILABLE_ENERGY_SENSOR: "sensor.beschikbaar",
        # v1.1.9: de meting slaat momenten over waarop de sensor terecht
        # stilstaat. Voor de beschikbare energie betekent dat: alleen
        # meten als de accu daadwerkelijk laadt of ontlaadt.
        CONF_BATTERY_POWER_SENSOR: "sensor.accu_w",
    }


def _accu_actief(hass):
    hass.states.set("sensor.accu_w", "1500")


def test_a_sensor_that_follows_the_tick(make_coordinator, hass):
    c = make_coordinator(_config())
    _accu_actief(hass)
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
    _accu_actief(hass)
    for i in range(SENSOR_CADENCE_MIN_SAMPLES + 10):
        # Beweegt eens per vijf ticks, en dan met een KLEINE stap: dat
        # is achterlopen, niet afronden (v3.34.0).
        hass.states.set("sensor.beschikbaar", str(6.0 + (i // 5) * 0.001))
        c._update_sensor_cadence_tracking()

    rapport = c.get_sensor_cadence_report()["sensor.beschikbaar"]

    assert rapport["status"] == "traag"
    assert rapport["beweegt_percent"] < SENSOR_CADENCE_SLOW_PERCENT


def test_no_verdict_below_the_minimum(make_coordinator, hass):
    c = make_coordinator(_config())
    _accu_actief(hass)
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
    _accu_actief(hass)
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
    _accu_actief(hass)
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


# --- v1.1.9: alleen meten als de sensor kán bewegen -----------------


def test_night_time_does_not_count_against_the_pv_sensor(
    make_coordinator, hass
):
    """Gerapporteerd: "sensor.solaredge_i1_ac_power beweegt maar bij
    13,8% van de metingen".

    Dat cijfer telde ook de nacht mee, waarin de PV per definitie
    constant nul is. Over ruim zestien uur meten kwam de sensor daardoor
    op 13,4% uit, terwijl hij overdag bij 27% bewoog. De conclusie
    ("trager dan de tick") klopte, het getal niet.
    """
    from custom_components.energy_management_system.const import (
        CONF_PV_POWER_SENSOR,
    )

    c = make_coordinator({CONF_PV_POWER_SENSOR: "sensor.pv"})

    # Nacht: honderd metingen met de PV op nul.
    for _ in range(100):
        hass.states.set("sensor.pv", "0")
        c._update_sensor_cadence_tracking()

    assert "sensor.pv" not in c.sensor_cadence

    # Dag: beweegt bij elke tweede meting.
    for i in range(SENSOR_CADENCE_MIN_SAMPLES * 2):
        hass.states.set("sensor.pv", str(1000 + (i // 2) * 50))
        c._update_sensor_cadence_tracking()

    rapport = c.get_sensor_cadence_report()["sensor.pv"]
    assert rapport["ticks"] == SENSOR_CADENCE_MIN_SAMPLES * 2
    assert 40 < rapport["beweegt_percent"] < 60


def test_an_idle_battery_does_not_count_against_the_energy_sensor(
    make_coordinator, hass
):
    """Staat de accu stil, dan hóórt de beschikbare energie niet te
    bewegen - dat is geen trage sensor."""
    c = make_coordinator(_config())

    hass.states.set("sensor.accu_w", "0")
    for _ in range(100):
        hass.states.set("sensor.beschikbaar", "6.5")
        c._update_sensor_cadence_tracking()

    assert "sensor.beschikbaar" not in c.sensor_cadence


def test_the_grid_and_battery_power_are_always_measured(
    make_coordinator, hass
):
    """Netvermogen en accuvermogen fluctueren altijd - daar is stilstand
    wél een signaal, dus die worden onvoorwaardelijk gemeten."""
    from custom_components.energy_management_system.const import (
        CONF_CONSUMPTION_POWER_SENSOR,
    )

    c = make_coordinator(
        {
            CONF_CONSUMPTION_POWER_SENSOR: "sensor.p1",
            CONF_BATTERY_POWER_SENSOR: "sensor.accu_w",
        }
    )
    hass.states.set("sensor.accu_w", "0")

    for _ in range(SENSOR_CADENCE_MIN_SAMPLES + 5):
        hass.states.set("sensor.p1", "400")
        c._update_sensor_cadence_tracking()

    assert c.get_sensor_cadence_report()["sensor.p1"]["status"] == "traag"


def test_a_genuinely_slow_sensor_is_still_caught(make_coordinator, hass):
    """De correctie mag het probleem niet wegpoetsen: een sensor die
    tijdens ACTIEVE momenten nauwelijks beweegt, hoort nog steeds als
    traag te gelden."""
    c = make_coordinator(_config())
    _accu_actief(hass)

    for i in range(SENSOR_CADENCE_MIN_SAMPLES * 2):
        hass.states.set("sensor.beschikbaar", str(6.0 + (i // 8) * 0.001))
        c._update_sensor_cadence_tracking()

    assert c.get_sensor_cadence_report()["sensor.beschikbaar"]["status"] == (
        "traag"
    )


# --- grof afronden is geen achterstand (v3.34.0) ---------------------


def test_coarse_rounding_is_not_called_slow(make_coordinator, hass):
    """Gemeld: "Dit is toch logisch? Als de accu niets doet staat de

    waarde stil."

    Terecht, en het lag nog specifieker. De beschikbare-energiesensor
    bewoog bij 4,9% van de ticks en heette daarom "traag", met het advies
    om afgeleide tempo's anders te berekenen. Maar de stappen in de
    loggegevens waren allemaal veelvouden van 0,0864 kWh - exact één
    procent van 8,64 kWh. Die sensor rapporteert de laadstand in hele
    procenten; bij 300 W valt de volgende stap pas na een kwartier.

    De waarde klopt, hij komt alleen in brokken. Dat vraagt niets.
    """
    c = make_coordinator(_config())
    _accu_actief(hass)

    for i in range(SENSOR_CADENCE_MIN_SAMPLES * 2):
        # Eens per zeventien ticks een stap van 0,0864 - de gemeten
        # werkelijkheid.
        hass.states.set("sensor.beschikbaar", str(6.0 - (i // 17) * 0.0864))
        c._update_sensor_cadence_tracking()

    rapport = c.get_sensor_cadence_report()["sensor.beschikbaar"]

    assert rapport["status"] == "grof_afgerond"
    assert rapport["kleinste_stap"] == pytest.approx(0.0864, abs=0.0005)
    assert "resolutie" in rapport["reden"]
    assert "achterstand" in rapport["reden"]


def test_a_sensor_that_follows_the_tick_needs_no_verdict(make_coordinator, hass):
    c = make_coordinator(_config())
    _accu_actief(hass)

    for i in range(SENSOR_CADENCE_MIN_SAMPLES * 2):
        hass.states.set("sensor.beschikbaar", str(6.0 + i * 0.013))
        c._update_sensor_cadence_tracking()

    assert c.get_sensor_cadence_report()["sensor.beschikbaar"]["status"] == (
        "volgt_de_tick"
    )
