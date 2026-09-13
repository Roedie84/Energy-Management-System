"""De piek per fase, naast die van het totaal (v3.58.0).

Gedeeld op 28 augustus, uit de P1-meter:

    fase 1   1305 W   5,61 A
    fase 2     40 W   0,17 A
    fase 3     76 W   0,32 A
    totaal   1421 W

De accu laadt op fase 1 (`phaseSwitch: 1`) en de omvormer is een
SE4000H, enkelfasig - die levert ook op fase 1. Alles wat er gebeurt,
gebeurt dus op een fase, terwijl de integratie alleen het TOTAAL kende.

Dat maakt uit voor twee dingen: het capaciteitstarief wordt bepaald door
de zwaarst belaste fase, en bij 2 kW laden plus het huisverbruik op
diezelfde fase zit je al richting de grens van wat een fase aankan.

Meet alleen; er wordt niets mee aangestuurd.
"""
from datetime import datetime

import pytest

from custom_components.energy_management_system.const import (
    CONF_PHASE_POWER_SENSORS,
    FASEPIEK_MELDGRENS_W,
)

NU = datetime(2026, 8, 28, 12, 0)
FASEN = [
    "sensor.p1_active_power_l1",
    "sensor.p1_active_power_l2",
    "sensor.p1_active_power_l3",
]


def _coordinator(make_coordinator, hass, vermogens):
    c = make_coordinator({CONF_PHASE_POWER_SENSORS: FASEN})
    for entity_id, w in zip(FASEN, vermogens):
        hass.states.set(entity_id, str(w))
    return c


def test_the_measured_situation(make_coordinator, hass):
    """De cijfers van 28 augustus."""
    c = _coordinator(make_coordinator, hass, [1305, 40, 76])

    c._volg_fasepieken(NU)

    assert c.fasepieken["per_fase"] == {
        "fase_1": 1305.0,
        "fase_2": 40.0,
        "fase_3": 76.0,
    }


def test_only_the_highest_of_the_day_is_kept(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, [1305, 40, 76])
    c._volg_fasepieken(NU)

    for entity_id, w in zip(FASEN, [800, 900, 50]):
        hass.states.set(entity_id, str(w))
    c._volg_fasepieken(NU)

    assert c.fasepieken["per_fase"]["fase_1"] == 1305.0
    assert c.fasepieken["per_fase"]["fase_2"] == 900.0


def test_a_new_day_starts_over(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, [1305, 40, 76])
    c._volg_fasepieken(NU)

    morgen = NU.replace(day=NU.day + 1)
    for entity_id in FASEN:
        hass.states.set(entity_id, "100")
    c._volg_fasepieken(morgen)

    assert c.fasepieken["per_fase"]["fase_1"] == 100.0


def test_an_unreadable_phase_is_skipped(make_coordinator, hass):
    """Een sensor die even niets zegt mag de andere twee niet meenemen."""
    c = _coordinator(make_coordinator, hass, [1305, 40, 76])
    hass.states.set(FASEN[1], "unavailable")

    c._volg_fasepieken(NU)

    assert "fase_2" not in c.fasepieken["per_fase"]
    assert c.fasepieken["per_fase"]["fase_1"] == 1305.0


# --- het oordeel -----------------------------------------------------


def test_a_phase_above_the_total_is_reported(make_coordinator, hass):
    """Het geval waar het om gaat: een fase die doorschiet terwijl het

    totaal meevalt. Dan denkt de piekbewaking dat het goed gaat.
    """
    c = _coordinator(make_coordinator, hass, [2400, 40, 76])
    c._volg_fasepieken(NU)
    c.peak_power_today_w = 1800.0

    overzicht = c.get_fasepiek_overzicht()

    assert overzicht["oordeel"] == "fase_boven_totaal"
    assert overzicht["zwaarste_fase"] == "fase_1"
    assert "capaciteitstarief" in overzicht["uitleg"]


def test_a_phase_within_the_total_is_fine(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, [1305, 40, 76])
    c._volg_fasepieken(NU)
    c.peak_power_today_w = 1421.0

    assert c.get_fasepiek_overzicht()["oordeel"] == "in_orde"


def test_measurement_noise_is_not_a_finding(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass, [1421, 40, 76])
    c._volg_fasepieken(NU)
    c.peak_power_today_w = 1421.0 - FASEPIEK_MELDGRENS_W + 10

    assert c.get_fasepiek_overzicht()["oordeel"] == "in_orde"


def test_without_configured_phases_nothing_happens(make_coordinator, hass):
    c = make_coordinator({})

    c._volg_fasepieken(NU)

    assert c.get_fasepiek_overzicht()["beschikbaar"] is False


def test_it_reaches_the_export():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    assert '"fasepieken"' in bron
