"""Digital Twin: nauwkeurigheid t.o.v. de werkelijkheid (v1.0.1).

Gerapporteerd: de adviesmodule meldde "Digital Twin — structureel
beschikbaar — Simuleert over 34.8 uur, nauwkeurigheid t.o.v. het
daadwerkelijke resultaat wordt niet bijgehouden."

Eerlijk, maar onnodig: de twin voorspelt een SoC, en die is later gewoon
na te meten. Dezelfde "leg een voorspelling vast, controleer 'm later"-
techniek als de zonvoorspelling-tracker.

Bewust NIET voor MPC: dat plan is een theoretisch optimum dat met opzet
niet wordt uitgevoerd, dus er valt niets tegen af te rekenen.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import (
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_BATTERY_MIN_SOC_NUMBER,
    CONF_BATTERY_TOTAL_CAPACITY_SENSOR,
    DIGITAL_TWIN_ACCURACY_HORIZON_HOURS,
    DIGITAL_TWIN_ACCURACY_MAX_LATE_MINUTES,
    DIGITAL_TWIN_ACCURACY_MIN_SAMPLES,
    DIGITAL_TWIN_ACCURACY_QUEUE_INTERVAL_MINUTES,
)

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


def _config():
    return {CONF_AVAILABLE_ENERGY_SENSOR: "sensor.beschikbaar"}


def _met_capaciteit(coordinator, hass, totaal_kwh, min_soc=0.0, suffix=""):
    """De bruikbare capaciteit komt uit totale capaciteit MINUS de
    hardware-minimum-SoC; beide entiteiten zijn nodig, anders is de
    capaciteit onbekend.

    `suffix` maakt aparte entiteiten mogelijk wanneer één test twee
    coordinators naast elkaar zet - die delen dezelfde
    toestandsmachine, dus dezelfde entity_id zou de tweede de eerste
    laten overschrijven.
    """
    cap = f"sensor.capaciteit{suffix}"
    minimum = f"number.min_soc{suffix}"
    hass.states.set(cap, str(totaal_kwh))
    hass.states.set(minimum, str(min_soc))
    coordinator.config[CONF_BATTERY_TOTAL_CAPACITY_SENSOR] = cap
    coordinator.config[CONF_BATTERY_MIN_SOC_NUMBER] = minimum


def _traject(vanaf, uren=12, soc=4.0):
    return [
        {
            "start": (vanaf + timedelta(hours=u)).isoformat(),
            "mode": "smart",
            "soc_kwh": soc,
        }
        for u in range(uren)
    ]


def _coordinator(make_coordinator, hass, beschikbaar=4.0):
    c = make_coordinator(_config())
    hass.states.set("sensor.beschikbaar", str(beschikbaar))
    c.digital_twin_trajectory = _traject(NOW)
    return c


# --- vastleggen -----------------------------------------------------


def test_a_prediction_is_queued_for_the_horizon(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)

    c._queue_digital_twin_prediction(NOW)

    assert len(c._digital_twin_pending) == 1
    afrekenen = datetime.fromisoformat(c._digital_twin_pending[0]["afrekenen_op"])
    assert afrekenen == NOW + timedelta(hours=DIGITAL_TWIN_ACCURACY_HORIZON_HOURS)


def test_not_queued_again_within_the_interval(make_coordinator, hass):
    """Elke tick vastleggen zou honderden sterk overlappende
    voorspellingen opleveren; het gemiddelde zou dan vooral meten hoe
    vaak er gemeten is."""
    c = _coordinator(make_coordinator, hass)

    c._queue_digital_twin_prediction(NOW)
    c._queue_digital_twin_prediction(NOW + timedelta(minutes=5))
    c._queue_digital_twin_prediction(NOW + timedelta(minutes=30))

    assert len(c._digital_twin_pending) == 1


def test_queued_again_after_the_interval(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)

    c._queue_digital_twin_prediction(NOW)
    later = NOW + timedelta(
        minutes=DIGITAL_TWIN_ACCURACY_QUEUE_INTERVAL_MINUTES + 1
    )
    c.digital_twin_trajectory = _traject(later)
    c._queue_digital_twin_prediction(later)

    assert len(c._digital_twin_pending) == 2


def test_nothing_queued_without_a_trajectory(make_coordinator, hass):
    c = make_coordinator(_config())

    c._queue_digital_twin_prediction(NOW)

    assert c._digital_twin_pending == []


def test_a_short_trajectory_queues_nothing(make_coordinator, hass):
    """Reikt de tijdlijn niet tot de horizon, dan bestaat er geen
    voorspelling OVER die horizon - een punt van veel dichterbij als
    zodanig afrekenen zou de meting te rooskleurig maken."""
    c = _coordinator(make_coordinator, hass)
    c.digital_twin_trajectory = _traject(NOW, uren=2)

    c._queue_digital_twin_prediction(NOW)

    assert c._digital_twin_pending == []


# --- afrekenen ------------------------------------------------------


def test_prediction_is_resolved_against_reality(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    c._queue_digital_twin_prediction(NOW)

    moment = NOW + timedelta(hours=DIGITAL_TWIN_ACCURACY_HORIZON_HOURS)
    hass.states.set("sensor.beschikbaar", "3.5")
    c._resolve_digital_twin_predictions(moment)

    assert len(c.digital_twin_accuracy_history) == 1
    meting = c.digital_twin_accuracy_history[0]
    assert meting["voorspeld_kwh"] == 4.0
    assert meting["werkelijk_kwh"] == 3.5
    assert meting["fout_kwh"] == 0.5
    assert c._digital_twin_pending == []


def test_a_prediction_is_not_resolved_early(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    c._queue_digital_twin_prediction(NOW)

    c._resolve_digital_twin_predictions(NOW + timedelta(hours=1))

    assert c.digital_twin_accuracy_history == []
    assert len(c._digital_twin_pending) == 1


def test_a_much_too_late_prediction_is_discarded(make_coordinator, hass):
    """Na een herstart zou een oude voorspelling een fout meten die niets
    met de modelkwaliteit te maken heeft."""
    c = _coordinator(make_coordinator, hass)
    c._queue_digital_twin_prediction(NOW)

    veel_later = NOW + timedelta(
        hours=DIGITAL_TWIN_ACCURACY_HORIZON_HOURS,
        minutes=DIGITAL_TWIN_ACCURACY_MAX_LATE_MINUTES + 10,
    )
    c._resolve_digital_twin_predictions(veel_later)

    assert c.digital_twin_accuracy_history == []
    assert c._digital_twin_pending == []


def test_an_unreadable_sensor_does_not_record_a_fake_error(
    make_coordinator, hass
):
    c = _coordinator(make_coordinator, hass)
    c._queue_digital_twin_prediction(NOW)
    hass.states.set("sensor.beschikbaar", "unavailable")

    c._resolve_digital_twin_predictions(
        NOW + timedelta(hours=DIGITAL_TWIN_ACCURACY_HORIZON_HOURS)
    )

    assert c.digital_twin_accuracy_history == []


# --- oordeel --------------------------------------------------------


def _vul_historie(c, fout_kwh, aantal=DIGITAL_TWIN_ACCURACY_MIN_SAMPLES):
    c.digital_twin_accuracy_history = [
        {
            "moment": NOW.isoformat(),
            "voorspeld_kwh": 4.0,
            "werkelijk_kwh": 4.0 - fout_kwh,
            "fout_kwh": fout_kwh,
        }
        for _ in range(aantal)
    ]


def test_no_verdict_below_the_minimum(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    _vul_historie(c, 0.1, aantal=DIGITAL_TWIN_ACCURACY_MIN_SAMPLES - 1)

    assert c.digital_twin_accuracy_mae_kwh is None
    assert c.get_digital_twin_accuracy_status()["status"] == "onvoldoende_data"


def test_small_error_is_judged_ready(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    _met_capaciteit(c, hass, 7.5)
    _vul_historie(c, 0.2)

    status = c.get_digital_twin_accuracy_status()

    assert c.digital_twin_accuracy_mae_kwh == 0.2
    assert status["status"] == "klaar"
    assert "%" in status["reden"]


def test_large_error_is_judged_too_low(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    _met_capaciteit(c, hass, 7.5)
    _vul_historie(c, 3.0)

    assert c.get_digital_twin_accuracy_status()["status"] == "kwaliteit_te_laag"


def test_error_is_relative_to_capacity_not_absolute(make_coordinator, hass):
    """Dezelfde fout van 0,5 kWh is prima bij een grote accu en te veel
    bij een kleine - een vaste kWh-drempel zou dat verschil missen."""
    groot = _coordinator(make_coordinator, hass)
    _met_capaciteit(groot, hass, 10.0, suffix="_groot")
    _vul_historie(groot, 0.5)

    klein = _coordinator(make_coordinator, hass)
    _met_capaciteit(klein, hass, 2.0, suffix="_klein")
    _vul_historie(klein, 0.5)

    assert groot.get_digital_twin_accuracy_status()["status"] == "klaar"
    assert klein.get_digital_twin_accuracy_status()["status"] != "klaar"


def test_without_capacity_it_says_so_honestly(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    _vul_historie(c, 0.4)

    status = c.get_digital_twin_accuracy_status()

    assert status["status"] == "structureel_beschikbaar"
    assert "niet te zeggen" in status["reden"]


# --- inbedding ------------------------------------------------------


def test_readiness_uses_the_measurement(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    _met_capaciteit(c, hass, 7.5)
    c.digital_twin_hours_simulated = 34.8
    _vul_historie(c, 0.2)

    c._update_advisory_readiness(NOW)
    entry = c.advisory_readiness["digital_twin"]

    assert entry["status"] == "klaar"
    assert "34.8 uur" in entry["reden"]
    assert "niet bijgehouden" not in entry["reden"]


def test_sensor_restores_history_across_a_restart(make_coordinator, hass):
    """Er zijn acht vergelijkingen nodig, per uur vastgelegd met een
    horizon van zes uur. Zonder herstel zou elke herstart de meting op
    nul zetten en zou het oordeel bij frequent herstarten nooit
    verschijnen."""
    import asyncio

    from custom_components.energy_management_system.sensor import (
        DigitalTwinAccuracySensor,
    )

    bron = _coordinator(make_coordinator, hass)
    _vul_historie(bron, 0.3)
    bron._digital_twin_pending = [
        {
            "voorspeld_op": NOW.isoformat(),
            "afrekenen_op": (NOW + timedelta(hours=6)).isoformat(),
            "voorspelde_soc_kwh": 4.0,
        }
    ]
    attrs = DigitalTwinAccuracySensor(bron, "entry1").extra_state_attributes

    class _Vorige:
        attributes = attrs

    verse = make_coordinator(_config())
    sensor = DigitalTwinAccuracySensor(verse, "entry1")

    async def get_last_state():
        return _Vorige()

    sensor.async_get_last_state = get_last_state
    asyncio.run(sensor.async_added_to_hass())

    assert len(verse.digital_twin_accuracy_history) == (
        DIGITAL_TWIN_ACCURACY_MIN_SAMPLES
    )
    assert len(verse._digital_twin_pending) == 1


def test_mpc_deliberately_has_no_accuracy_tracking(make_coordinator, hass):
    """Het MPC-plan is een theoretisch optimum dat met opzet NIET wordt
    uitgevoerd - er valt dus niets tegen af te rekenen. Die tekst hoort
    er te blijven staan, zodat "consistentie" later geen reden wordt om
    er alsnog een meting bij te verzinnen."""
    c = make_coordinator({})
    c.mpc_horizon_quarters_used = 96

    c._update_advisory_readiness(NOW)

    assert "niet bijgehouden" in c.advisory_readiness["mpc"]["reden"]
