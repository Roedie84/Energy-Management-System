"""Levert Kalman-filteren hier eigenlijk iets op? (v1.0.7)

Gevraagd bij "Kalman filtering — klaar — alle 3 filters geconvergeerd":
doen we hier actief iets mee, en wat zou het betekenen als wel?

"Geconvergeerd" zegt alleen dat de interne onzekerheid van het filter is
uitgezakt - niet dat de gefilterde waarde BETER is dan de ruwe. Er was
geen enkel cijfer dat die vraag kon beantwoorden. Deze meting levert dat
cijfer, zodat de vervolgvraag met data beantwoord kan worden in plaats
van met een aanname.

Blijft volledig adviserend: er wordt niets mee gestuurd.
"""
from custom_components.energy_management_system.const import (
    KALMAN_DIVERGENCE_MEANINGFUL_PERCENT,
    KALMAN_DIVERGENCE_MIN_SAMPLES,
)


def _vul(c, signaal, verschil, ruw, aantal=KALMAN_DIVERGENCE_MIN_SAMPLES):
    c.kalman_divergence_history[signaal] = [[verschil, ruw] for _ in range(aantal)]


# --- vastleggen -----------------------------------------------------


def test_a_pair_is_recorded_per_measurement(make_coordinator, hass):
    c = make_coordinator({})

    c._record_kalman_divergence("pv", ruw=3000.0, gefilterd=2950.0)

    assert c.kalman_divergence_history["pv"] == [[50.0, 3000.0]]


def test_missing_values_are_skipped(make_coordinator, hass):
    c = make_coordinator({})

    c._record_kalman_divergence("soc", ruw=None, gefilterd=4.0)
    c._record_kalman_divergence("soc", ruw=4.0, gefilterd=None)

    assert c.kalman_divergence_history == {}


def test_history_is_bounded(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        KALMAN_DIVERGENCE_HISTORY_LENGTH,
    )

    c = make_coordinator({})
    for _ in range(KALMAN_DIVERGENCE_HISTORY_LENGTH + 100):
        c._record_kalman_divergence("load", ruw=200.0, gefilterd=190.0)

    assert len(c.kalman_divergence_history["load"]) == (
        KALMAN_DIVERGENCE_HISTORY_LENGTH
    )


# --- oordeel --------------------------------------------------------


def test_no_verdict_below_the_minimum(make_coordinator, hass):
    c = make_coordinator({})
    _vul(c, "pv", 50.0, 3000.0, aantal=KALMAN_DIVERGENCE_MIN_SAMPLES - 1)

    assert c.get_kalman_divergence_status()["pv"]["status"] == "onvoldoende_data"


def test_a_tiny_difference_is_called_negligible(make_coordinator, hass):
    """15 W op 3000 W is een half procent - daar valt niets te winnen."""
    c = make_coordinator({})
    _vul(c, "pv", 15.0, 3000.0)

    status = c.get_kalman_divergence_status()["pv"]

    assert status["status"] == "verwaarloosbaar"
    assert status["percentage_van_signaal"] == 0.5


def test_a_large_difference_is_flagged_as_meaningful(make_coordinator, hass):
    c = make_coordinator({})
    _vul(c, "load", 40.0, 200.0)

    status = c.get_kalman_divergence_status()["load"]

    assert status["status"] == "noemenswaardig"
    assert status["percentage_van_signaal"] >= KALMAN_DIVERGENCE_MEANINGFUL_PERCENT


def test_the_same_absolute_difference_is_judged_by_scale(make_coordinator, hass):
    """De kern van het ontwerp: 50 W afwijking op 10 kW PV is
    verwaarloosbaar, dezelfde 50 W op 200 W huisverbruik is fors. Een
    absolute drempel zou dat verschil missen."""
    c = make_coordinator({})
    _vul(c, "pv", 50.0, 10000.0)
    _vul(c, "load", 50.0, 200.0)

    status = c.get_kalman_divergence_status()

    assert status["pv"]["status"] == "verwaarloosbaar"
    assert status["load"]["status"] == "noemenswaardig"


def test_a_signal_that_stayed_at_zero_gives_no_verdict(make_coordinator, hass):
    """'s Nachts staat PV op nul; een verhouding tegen nul zegt niets."""
    c = make_coordinator({})
    _vul(c, "pv", 0.0, 0.0)

    assert c.get_kalman_divergence_status()["pv"]["status"] == "onvoldoende_data"


def test_the_ratio_is_taken_over_the_sums_not_per_measurement(
    make_coordinator, hass
):
    """Per meting delen zou een moment met bijna nul opwek een absurde
    verhouding geven die het gemiddelde volledig domineert."""
    c = make_coordinator({})
    c.kalman_divergence_history["pv"] = (
        [[10.0, 0.01]] + [[10.0, 3000.0]] * (KALMAN_DIVERGENCE_MIN_SAMPLES - 1)
    )

    status = c.get_kalman_divergence_status()["pv"]

    # Sommen: ~500 verschil op ~147.000 ruw = ruim onder 1%.
    assert status["status"] == "verwaarloosbaar"


# --- inbedding ------------------------------------------------------


def test_it_stays_advisory(make_coordinator, hass):
    """De divergentiemeting mag zelf nergens een commando raken - dat
    was juist het punt: eerst meten, dan pas eventueel besluiten."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    for regel in bron.split("\n"):
        if "kalman_divergence" in regel:
            assert "_async_apply" not in regel


def test_exposed_on_the_kalman_sensor(make_coordinator, hass):
    from custom_components.energy_management_system.sensor import (
        KalmanFilterAdvisorySensor,
    )

    c = make_coordinator({})
    _vul(c, "pv", 15.0, 3000.0)

    attrs = KalmanFilterAdvisorySensor(c, "entry1").extra_state_attributes

    assert attrs["levert_filteren_iets_op"]["pv"]["status"] == "verwaarloosbaar"


def test_the_measurement_survives_a_restart(make_coordinator, hass):
    """Vijftig metingen per signaal zijn nodig; zonder herstel zou elke
    herstart de telling terugzetten."""
    import asyncio

    from custom_components.energy_management_system.const import (
        PERSISTED_PLAIN_FIELDS,
    )

    assert "kalman_divergence_history" in PERSISTED_PLAIN_FIELDS

    bron = make_coordinator({})
    _vul(bron, "pv", 15.0, 3000.0)
    asyncio.run(bron.async_save_persisted_state_now())

    verse = make_coordinator({})
    asyncio.run(verse.async_load_persisted_state())

    assert len(verse.kalman_divergence_history["pv"]) == (
        KALMAN_DIVERGENCE_MIN_SAMPLES
    )
