"""Repairs en gemeten capaciteit (v3.5.0).

Uit een externe review, twee punten die hout sneden:

1. "Ik mis een vermelding van Repair Issues. Veel meldingen worden nu via
   notificaties, dashboard en diagnostiek afgehandeld."
2. "Je leert al rendement en gezondheid. De volgende stap: nominaal 8,64
   kWh, gemeten 7,95 kWh - en automatisch de reserveberekening
   aanpassen."
"""
from custom_components.energy_management_system.const import (
    CAPACITY_MEASURE_MIN_FRACTION,
    CONF_BATTERY_TOTAL_CAPACITY_SENSOR,
    PROEFSTAND_MIN_TREND_DAYS,
)


# --- Repairs ---------------------------------------------------------


def test_a_missing_input_reaches_repairs(make_coordinator, hass):
    """Repairs is waar een gebruiker dit soort dingen VERWACHT: bij
    Instellingen, met uitleg, en het blijft staan tot het is opgelost."""
    from custom_components.energy_management_system import repairs

    geplaatst = []
    repairs.meld = lambda hass, sleutel, *a, **k: geplaatst.append(sleutel)
    repairs.los_op = lambda hass, sleutel: None

    c = make_coordinator({})
    c.get_input_health = lambda: [{"onderdeel": "azimut"}]
    c.get_consistency_checks = lambda *a, **k: {"bevindingen": []}
    c.get_dashboard_health = lambda: {}

    repairs.werk_bij(hass, c)

    assert repairs.REPAIR_ONTBREKENDE_INGANG in geplaatst


def test_a_resolved_problem_is_removed(make_coordinator, hass):
    """Even belangrijk als het plaatsen: een Repairs-scherm dat vol
    blijft staan met opgeloste dingen wordt niet meer gelezen."""
    from custom_components.energy_management_system import repairs

    opgelost = []
    repairs.meld = lambda *a, **k: None
    repairs.los_op = lambda hass, sleutel: opgelost.append(sleutel)

    c = make_coordinator({})
    c.get_input_health = lambda: []
    c.get_consistency_checks = lambda *a, **k: {"bevindingen": []}
    c.get_dashboard_health = lambda: {}
    c.internal_failures = {}

    repairs.werk_bij(hass, c)

    assert repairs.REPAIR_ONTBREKENDE_INGANG in opgelost
    assert repairs.REPAIR_INTERNE_FOUT in opgelost


def test_only_actionable_things_reach_repairs():
    """Een leerproces dat nog dagen nodig heeft is geen reparatie maar
    geduld. Zoiets in Repairs zetten leert mensen het scherm te
    negeren."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "repairs.py").read_text()

    for niet in ("proefstand", "onvoldoende_data", "leert nog"):
        assert niet not in bron.lower()


def test_every_repair_has_a_dutch_text():
    """Een melding zonder uitleg is niet te gebruiken."""
    import json
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "repairs.py").read_text()
    vertalingen = json.loads(
        (Path(pkg.__file__).parent / "translations" / "nl.json").read_text()
    )["issues"]

    import re

    sleutels = set(re.findall(r'REPAIR_\w+ = "(\w+)"', bron))

    for sleutel in sleutels:
        assert sleutel in vertalingen, sleutel
        assert vertalingen[sleutel]["description"]


# --- Gemeten capaciteit ----------------------------------------------


def _met_trend(make_coordinator, hass, gemeten, nominaal=8.6, dagen=None):
    c = make_coordinator(
        {CONF_BATTERY_TOTAL_CAPACITY_SENSOR: "sensor.capaciteit"}
    )
    hass.states.set("sensor.capaciteit", str(nominaal))
    # v3.92.5: de sleutel die `_update_proefstand` werkelijk schrijft.
    #
    # Hier stond `bruikbaar_kwh` - dezelfde sleutel die de lezer
    # gebruikte, en die de schrijver nooit heeft gezet. Deze zeven
    # toetsen bevestigden dus de aanname en niet de code, en daardoor
    # bleef `gemeten_kwh` 153 dagen op null zonder dat er iets omviel.
    c.capacity_trend_history = [
        {
            "datum": f"2026-01-{1 + i:02d}",
            "capaciteit_kwh": gemeten,
            "doorzet_kwh": 1.1 * i,
        }
        for i in range(dagen or PROEFSTAND_MIN_TREND_DAYS)
    ]
    return c


def test_too_few_days_keeps_the_nominal(make_coordinator, hass):
    """Een trend uit een handvol dagen zegt te weinig."""
    c = _met_trend(make_coordinator, hass, 7.95, dagen=2)

    assert c.gemeten_capaciteit_kwh() is None
    assert c.bruikbare_capaciteit_kwh() == 8.6


def test_the_measured_capacity_is_used(make_coordinator, hass):
    """Levert de accu feitelijk minder, dan is elke reserveberekening
    met de nominale waarde structureel optimistisch."""
    c = _met_trend(make_coordinator, hass, 7.95)

    assert c.gemeten_capaciteit_kwh() == 7.95
    assert c.bruikbare_capaciteit_kwh() == 7.95


def test_an_implausible_measurement_is_refused(make_coordinator, hass):
    """Een meting die ver onder nominaal ligt is eerder een meetfout dan
    een versleten accu - en dan zou een verkeerd uitgelezen sensor de
    hele accu blokkeren."""
    c = _met_trend(make_coordinator, hass, 2.0)

    assert c.gemeten_capaciteit_kwh() is None
    assert c.bruikbare_capaciteit_kwh() == 8.6


def test_measuring_above_nominal_is_capped(make_coordinator, hass):
    """Boven nominaal meten kan niet; dan is er iets anders aan de
    hand."""
    c = _met_trend(make_coordinator, hass, 9.8)

    assert c.bruikbare_capaciteit_kwh() == 8.6


def test_the_overview_names_the_degradation(make_coordinator, hass):
    c = _met_trend(make_coordinator, hass, 7.95)

    o = c.get_capacity_overview()

    assert o["nominaal_kwh"] == 8.6
    assert o["gemeten_kwh"] == 7.95
    assert o["degradatie_procent"] == 7.6


def test_the_reserve_goes_through_one_place():
    """Dertien losse aanroepen zouden uit elkaar gaan lopen - precies
    wat er met de reservemarge gebeurde in v1.86.0 tot en met v1.88.0."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()

    assert "def bruikbare_capaciteit_kwh" in bron
    assert bron.count("self.bruikbare_capaciteit_kwh()") >= 2


def test_the_floor_is_not_absurd():
    """Te streng zou een echt versleten accu weren; te ruim zou een
    meetfout laten doorwerken."""
    assert 0.5 <= CAPACITY_MEASURE_MIN_FRACTION <= 0.8
