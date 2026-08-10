"""Koeling: meetuitval en buitentemperatuur (v1.21.0).

Gemeld: "Voor het verbruik van de koelkast/diepvries is het misschien
goed de buitentemperaturen mee te wegen, dit gezien ze in een relatief
warme schuur staan, welke sterk wordt beïnvloed door de
buitentemperatuur."

Terecht - maar er zat een groter probleem onder. De dagreeks van de
diepvries wisselde tussen 0,8 W en 90 W: dertien dagen onder 5 W, twaalf
boven 60. Een dagGEMIDDELDE van 0,8 W betekent dat de compressor die hele
dag niet draaide, wat voor een gevulde diepvries onmogelijk is. Dat zijn
dagen waarop de meter niets doorgaf.

De mediaan over álle dagen belandde daardoor op 19,68 W - precies tussen
beide groepen in - en meldde "+57,4% drift" terwijl 40,8 W een normale
dag was.
"""
import statistics

from custom_components.energy_management_system.const import (
    CONF_BACKYARD_TEMPERATURE_SENSOR,
    COOLING_DRIFT_PERCENT_PER_DEGREE,
    COOLING_TEMP_MIN_DAYS,
)

# De werkelijke dagreeks uit de export.
DIEPVRIES = [
    0.7, 0.7, 0.8, 76.3, 1.0, 0.7, 77.2, 0.9, 77.8, 78.3,
    19.7, 19.7, 0.9, 81.2, 0.8, 0.8, 79.8, 78.8, 41.5, 0.9,
    75.2, 228.6, 19.4, 75.5, 0.8, 0.7, 75.6, 0.9, 79.5, 31.0,
]


# --- meetuitval ------------------------------------------------------


def test_dropout_days_are_excluded(make_coordinator, hass):
    """Het gerapporteerde geval: de referentie kwam uit het niemandsland
    tussen twee groepen."""
    c = make_coordinator({})

    schoon = c._zonder_meetuitval(DIEPVRIES)

    assert statistics.median(DIEPVRIES) < 25
    assert statistics.median(schoon) > 70


def test_the_reference_becomes_realistic(make_coordinator, hass):
    """Een diepvries die 76 W trekt is normaal; 19,68 W was het
    gemiddelde van werken en niets doorgeven."""
    c = make_coordinator({})

    referentie = statistics.median(c._zonder_meetuitval(DIEPVRIES))

    assert 70 <= referentie <= 85


def test_a_genuinely_low_device_is_left_alone(make_coordinator, hass):
    """Te streng filteren zou een apparaat dat werkelijk weinig
    verbruikt onterecht opschonen."""
    c = make_coordinator({})
    lamp = [0.17, 0.18, 0.17, 0.16, 0.18, 0.17]

    assert c._zonder_meetuitval(lamp) == lamp


def test_a_short_history_is_kept(make_coordinator, hass):
    """Met twee metingen valt niet te zeggen wat uitval is."""
    c = make_coordinator({})

    assert c._zonder_meetuitval([0.8, 76.0]) == [0.8, 76.0]


def test_zero_days_are_dropped(make_coordinator, hass):
    """Nul is per definitie geen meting."""
    c = make_coordinator({})

    assert 0.0 not in c._zonder_meetuitval([0.0, 70.0, 68.0, 71.0, 0.0])


# --- buitentemperatuur -----------------------------------------------


def _koelkast(make_coordinator, hass, buiten, dagen=7):
    c = make_coordinator({CONF_BACKYARD_TEMPERATURE_SENSOR: "sensor.buiten"})
    hass.states.set("sensor.buiten", str(buiten))
    apparaat = {
        "friendly_name": "Diepvries schuur Vermogen",
        "outdoor_temp_history": [19.0] * dagen,
    }
    return c, apparaat


def test_warm_weather_gives_margin(make_coordinator, hass):
    """Een koelkast in een schuur werkt harder als het buiten warm is;
    zonder correctie leest een warme week als een defect."""
    c, apparaat = _koelkast(make_coordinator, hass, 25.0)

    marge = c._koeling_temperatuurmarge_procent(apparaat)

    assert marge == 6 * COOLING_DRIFT_PERCENT_PER_DEGREE


def test_cool_weather_gives_no_margin(make_coordinator, hass):
    """Alleen naar boven: koeler weer mag geen drift verbergen."""
    c, apparaat = _koelkast(make_coordinator, hass, 12.0)

    assert c._koeling_temperatuurmarge_procent(apparaat) == 0.0


def test_only_cooling_devices_get_a_margin(make_coordinator, hass):
    """Een lamp verbruikt niet meer omdat het warm is."""
    c, _ = _koelkast(make_coordinator, hass, 32.0)

    marge = c._koeling_temperatuurmarge_procent(
        {"friendly_name": "Eetkamer lamp 1 Power"}
    )

    assert marge == 0.0


def test_too_little_temperature_history_gives_no_margin(
    make_coordinator, hass
):
    """Zonder geschiedenis is er geen referentiepunt om tegen af te
    zetten."""
    c, apparaat = _koelkast(
        make_coordinator, hass, 30.0, dagen=COOLING_TEMP_MIN_DAYS - 1
    )

    assert c._koeling_temperatuurmarge_procent(apparaat) == 0.0


def test_without_a_temperature_sensor_there_is_no_margin(
    make_coordinator, hass
):
    c = make_coordinator({})

    marge = c._koeling_temperatuurmarge_procent(
        {
            "friendly_name": "Diepvries schuur Vermogen",
            "outdoor_temp_history": [19.0] * 7,
        }
    )

    assert marge == 0.0


def test_the_margin_is_modest_per_degree():
    """Rond 3% per graad is de vuistregel uit de koeltechniek; veel
    hoger zou een echt defect verbergen."""
    assert 1.0 <= COOLING_DRIFT_PERCENT_PER_DEGREE <= 5.0


# --- inbedding -------------------------------------------------------


def test_the_temperature_is_recorded_per_day():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()

    assert "outdoor_temp_history" in bron


def test_the_margin_is_used_in_the_drift_check():
    """Meten zonder toepassen zou het probleem niet oplossen."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    start = bron.index("groot_genoeg = reference_avg_w")
    blok = bron[start : start + 1200]

    assert "_koeling_temperatuurmarge_procent" in blok
    assert "verschil_w = max(0.0, verschil_w - verklaard_w)" in blok
