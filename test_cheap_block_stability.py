"""Cheapest-block selection stability (v0.49.0).

Regression test for a real-world incident: the energy bridge check
logged wild swings in needed_kwh (e.g. 24.37 kWh immediately followed by
0.0 kWh at the same logged minute) with an unchanged available_kwh -
consistent with the "cheapest block" target flipping between two
near-tied candidates elsewhere in the day as time passed and which
quarters still counted as "upcoming" shifted.
"""
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 8, 3, tzinfo=timezone.utc)


def _forecast_with_two_near_tied_candidates():
    """08:45 and 15:00 are both cheap, with 15:00 only marginally
    (0.01 in the raw price scale) more expensive - a near-tie."""
    entries = []
    for hour in range(24):
        for minute in (0, 15, 30, 45):
            start = DAY0.replace(hour=hour, minute=minute)
            if hour == 8 and minute == 45:
                price = 1_290_000
            elif hour == 15 and minute == 0:
                price = 1_291_000
            else:
                price = 2_500_000
            entries.append((start, start + timedelta(minutes=15), price))
    return entries


def test_sticks_with_previous_choice_while_still_upcoming(make_coordinator):
    """While the previously-chosen cheap quarter hasn't ended yet, a
    near-tied candidate elsewhere in the day should not steal the
    selection away."""
    coordinator = make_coordinator({})
    forecast = _forecast_with_two_near_tied_candidates()

    now_1 = DAY0.replace(hour=8, minute=40)
    start_1, _ = coordinator._cheapest_block_range(forecast, now_1)
    coordinator.last_cheap_block_start = start_1
    assert start_1 == DAY0.replace(hour=8, minute=45)

    # One minute before the 08:45 quarter itself expires (at 09:00) -
    # it's still technically "upcoming", so hysteresis should keep it.
    now_2 = DAY0.replace(hour=8, minute=59)
    start_2, _ = coordinator._cheapest_block_range(forecast, now_2)
    assert start_2 == DAY0.replace(hour=8, minute=45)


def test_switches_once_the_previous_choice_has_genuinely_expired(make_coordinator):
    """Once the previously-chosen quarter has actually ended, switching
    to the next candidate is unavoidable and correct - not a bug."""
    coordinator = make_coordinator({})
    forecast = _forecast_with_two_near_tied_candidates()

    coordinator.last_cheap_block_start = DAY0.replace(hour=8, minute=45)

    now = DAY0.replace(hour=9, minute=0)  # 08:45-09:00 quarter has now ended
    start, _ = coordinator._cheapest_block_range(forecast, now)
    assert start == DAY0.replace(hour=15, minute=0)


def test_switches_immediately_if_new_candidate_is_meaningfully_cheaper(
    make_coordinator,
):
    """Hysteresis should only protect against near-ties - a genuinely
    much cheaper candidate should still win right away."""
    coordinator = make_coordinator({})
    entries = []
    for hour in range(24):
        for minute in (0, 15, 30, 45):
            start = DAY0.replace(hour=hour, minute=minute)
            if hour == 8 and minute == 45:
                price = 2_000_000  # previous choice: not actually that cheap
            elif hour == 15 and minute == 0:
                price = 500_000  # much cheaper - a real, not near-tied, winner
            else:
                price = 2_500_000
            entries.append((start, start + timedelta(minutes=15), price))

    coordinator.last_cheap_block_start = DAY0.replace(hour=8, minute=45)
    now = DAY0.replace(hour=8, minute=50)  # previous choice still upcoming
    start, _ = coordinator._cheapest_block_range(entries, now)

    assert start == DAY0.replace(hour=15, minute=0)


def test_transition_log_includes_the_target_cheap_block(make_coordinator, hass):
    """The energy bridge transition log should record cheap_block_start
    alongside each entry, so a future swing in needed_kwh can be
    attributed with certainty instead of guessed at."""
    coordinator = make_coordinator(
        {"consumption_power_sensor_entity": "sensor.p1"}
    )
    hass.states.set("sensor.p1", "50")
    cheap_block_start = DAY0.replace(hour=9, minute=0)

    coordinator.last_has_enough_energy = False  # simulate a genuine flip
    coordinator._log_energy_transition(
        DAY0.replace(hour=7, minute=0), True, 5.0, 1.0, cheap_block_start
    )

    assert coordinator.energy_bridge_transition_log
    last_entry = coordinator.energy_bridge_transition_log[-1]
    assert last_entry["cheap_block_start"] == cheap_block_start.isoformat()
