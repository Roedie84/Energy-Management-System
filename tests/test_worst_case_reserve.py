"""Worst-case cumulative deficit reserve calculation (v0.43.0/0.43.1).

The most important safety fix in the whole project: a simple net
balance over the whole bridging window can look fine on paper (abundant
solar expected tomorrow) while still hiding a real overnight shortfall,
since solar credit is concentrated in daylight hours. This walks hour by
hour and protects against the deepest point reached, not just the net
end-of-window balance.
"""
from datetime import datetime, timedelta, timezone

import pytest

DAY0 = datetime(2026, 8, 2, tzinfo=timezone.utc)


def _two_day_pv_forecast(peak_kw: float = 1.4, start_hour: int = 8, end_hour: int = 16):
    detailed = []
    for day_offset in range(2):
        for hour in range(24):
            for minute in (0, 30):
                pv = peak_kw if start_hour <= hour < end_hour else 0.0
                detailed.append(
                    {
                        "period_start": (DAY0 + timedelta(days=day_offset)).replace(
                            hour=hour, minute=minute
                        ),
                        "pv_estimate": pv,
                    }
                )
    return detailed


def test_worst_case_deficit_exceeds_naive_net_balance(make_coordinator, hass):
    """Reproduces the exact field scenario: ~11+ kWh of solar expected
    tomorrow makes the naive net balance look like ~0 reserve is needed,
    while a real overnight deficit (before any solar arrives) remains."""
    coordinator = make_coordinator({"solar_forecast_sensor_entity": "sensor.solcast"})
    for hour in range(24):
        coordinator.hourly_consumption_profile[hour] = [0.3]  # flat 300W all day

    hass.states.set(
        "sensor.solcast", "11.2", {"detailedForecast": _two_day_pv_forecast()}
    )

    start = DAY0.replace(hour=23, minute=45)
    end = (DAY0 + timedelta(days=1)).replace(hour=11, minute=15)

    naive_consumption = coordinator._estimate_consumption_kwh_for_period(start, end)
    naive_pv_offset = coordinator._get_efficiency_discounted_pv_offset(start, end)
    naive_reserve = max(0.0, naive_consumption - naive_pv_offset)

    worst_case_reserve = coordinator._estimate_worst_case_deficit_kwh(start, end)

    assert naive_reserve == pytest.approx(0.0, abs=0.01)
    assert worst_case_reserve > 2.0  # a real overnight deficit remains
    assert worst_case_reserve > naive_reserve


def test_worst_case_deficit_reacts_to_live_consumption_spike(make_coordinator, hass):
    """An airco running right now should scale up the whole worst-case
    estimate proportionally, not just get averaged away by history."""
    coordinator = make_coordinator(
        {
            "solar_forecast_sensor_entity": "sensor.solcast",
            "consumption_power_sensor_entity": "sensor.p1",
        }
    )
    for hour in range(24):
        coordinator.hourly_consumption_profile[hour] = [0.3]

    hass.states.set(
        "sensor.solcast", "11.2", {"detailedForecast": _two_day_pv_forecast()}
    )

    start = DAY0.replace(hour=23, minute=45)
    end = (DAY0 + timedelta(days=1)).replace(hour=11, minute=15)

    hass.states.set("sensor.p1", "300")  # matches the learned average
    for _ in range(4):
        coordinator._track_recent_consumption_reading(start)
    reserve_normal = coordinator._estimate_worst_case_deficit_kwh(start, end)

    coordinator2 = make_coordinator(
        {
            "solar_forecast_sensor_entity": "sensor.solcast",
            "consumption_power_sensor_entity": "sensor.p1",
        }
    )
    for hour in range(24):
        coordinator2.hourly_consumption_profile[hour] = [0.3]
    hass.states.set("sensor.p1", "900")  # airco on and sustained: 3x the learned avg
    for _ in range(4):
        coordinator2._track_recent_consumption_reading(start)
    reserve_with_airco = coordinator2._estimate_worst_case_deficit_kwh(start, end)

    # v1.68.0: de correctie geldt vol in het eerste uur en dooft daarna
    # uit. Over dit venster van elfenhalf uur blijft er dus een deel van
    # de factor 3 over, niet de volle drie.
    #
    # Gemeld: het plan rekende met 1,26 kW terwijl het profiel 0,25 zei,
    # omdat er om 16:30 gekookt werd en die factor over 31 uur werd
    # uitgesmeerd. Dat de airco nu draait zegt iets over het komende uur,
    # niet over 03:00 vannacht.
    assert reserve_with_airco > reserve_normal
    assert reserve_with_airco < reserve_normal * 3


def test_brief_single_tick_spike_does_not_scale_the_whole_estimate(
    make_coordinator, hass
):
    """Regression test for a real-world incident: a single brief power
    spike used to scale a 15+ hour estimate to an absurd value (reported:
    17.4 kWh baseline for what should have been a few kWh). Median-based
    smoothing over a short rolling window should fully ignore a one-off
    blip surrounded by normal readings (unlike a mean, which would still
    be skewed by it)."""
    coordinator = make_coordinator(
        {"consumption_power_sensor_entity": "sensor.p1"}
    )
    for hour in range(24):
        coordinator.hourly_consumption_profile[hour] = [0.3]

    start = DAY0.replace(hour=7, minute=0)
    end = DAY0.replace(hour=22, minute=0)  # a long ~15 hour window

    # Establish the normal (no-spike) baseline for comparison.
    hass.states.set("sensor.p1", "300")
    for _ in range(4):
        coordinator._track_recent_consumption_reading(start)
    normal_estimate = coordinator._estimate_consumption_kwh_for_period(start, end)

    # Now simulate a single brief spike among otherwise-normal readings -
    # e.g. an oven or "Quooker"-style instant hot water tap drawing
    # ~2000-9000W for just a minute or two while its heating element
    # cycles, landing inside exactly one 5-minute sample.
    coordinator2 = make_coordinator({"consumption_power_sensor_entity": "sensor.p1"})
    for hour in range(24):
        coordinator2.hourly_consumption_profile[hour] = [0.3]
    hass.states.set("sensor.p1", "300")
    coordinator2._track_recent_consumption_reading(start)
    coordinator2._track_recent_consumption_reading(start)
    hass.states.set("sensor.p1", "9000")  # a huge, brief spike (e.g. a glitch)
    coordinator2._track_recent_consumption_reading(start)
    hass.states.set("sensor.p1", "300")
    coordinator2._track_recent_consumption_reading(start)
    spiky_estimate = coordinator2._estimate_consumption_kwh_for_period(start, end)

    # The median of [300, 300, 9000, 300] is 300 - the outlier is
    # ignored outright, so a single brief blip (regardless of how
    # extreme) should produce exactly the same estimate as no spike at
    # all, not just a dampened-but-still-inflated one.
    assert spiky_estimate == pytest.approx(normal_estimate, rel=0.01)


def test_moderate_brief_spike_is_fully_ignored_by_median_smoothing(
    make_coordinator, hass
):
    """A single-tick spike among 3 normal readings should be fully
    ignored (median, not mean) - only a *sustained* change (at least
    half the window reflecting the new level) should move the ratio."""
    coordinator = make_coordinator({"consumption_power_sensor_entity": "sensor.p1"})
    for hour in range(24):
        coordinator.hourly_consumption_profile[hour] = [0.3]

    start = DAY0.replace(hour=7, minute=0)

    hass.states.set("sensor.p1", "300")
    coordinator._track_recent_consumption_reading(start)
    coordinator._track_recent_consumption_reading(start)
    hass.states.set("sensor.p1", "900")  # one brief 3x spike (oven/Quooker)
    coordinator._track_recent_consumption_reading(start)
    hass.states.set("sensor.p1", "300")
    coordinator._track_recent_consumption_reading(start)

    ratio = coordinator._get_smoothed_consumption_correction_ratio(7)

    # Median of [300, 300, 900, 300] is 300 -> ratio 1.0 (no correction
    # at all) - a real improvement over a mean-based 1.5x, since a
    # 1-2 minute appliance blip shouldn't inflate a multi-hour estimate.
    assert ratio == pytest.approx(1.0, rel=0.01)


def test_sustained_change_still_fully_detected_with_median_smoothing(
    make_coordinator, hass
):
    """A genuinely sustained change (half the window or more reflecting
    the new level) must still be picked up - median smoothing dampens
    isolated blips, not real regime changes."""
    coordinator = make_coordinator({"consumption_power_sensor_entity": "sensor.p1"})
    for hour in range(24):
        coordinator.hourly_consumption_profile[hour] = [0.3]

    start = DAY0.replace(hour=7, minute=0)

    hass.states.set("sensor.p1", "300")
    coordinator._track_recent_consumption_reading(start)
    coordinator._track_recent_consumption_reading(start)
    hass.states.set("sensor.p1", "900")  # airco just started, sustained from here
    coordinator._track_recent_consumption_reading(start)
    coordinator._track_recent_consumption_reading(start)

    ratio = coordinator._get_smoothed_consumption_correction_ratio(7)

    # Median of [300, 300, 900, 900] is 600 -> ratio 2.0x.
    assert ratio == pytest.approx(2.0, rel=0.01)





# --- v1.68.0: hoe ver reikt de live correctie? -----------------------


def test_a_short_window_keeps_the_full_correction(make_coordinator, hass):
    """Draait de airco nu, dan zegt het gemiddelde van vorige week te
    weinig over het komende uur. Daar is de correctie voor."""
    c = make_coordinator({})

    assert c._uitgedempte_correctie(
        DAY0, DAY0 + timedelta(minutes=30), 5.0
    ) == 5.0


def test_a_long_horizon_fades_it_out(make_coordinator, hass):
    """Gemeld: "34 kwartier(en) aan het net - morgen 01:00-09:30 (...) €
    -2.0 over 31 uur."

    Om 16:30 werd er gekookt, dus de correctie zat op zijn maximum van
    5,0x - toegepast op de hele planning van 31 uur. Het plan rekende
    met 1,26 tot 1,38 kW terwijl het profiel 0,20 tot 0,41 kW zegt.
    """
    c = make_coordinator({})

    over_31_uur = c._uitgedempte_correctie(DAY0, DAY0 + timedelta(hours=31), 5.0)

    assert over_31_uur < 1.4


def test_the_fade_is_gradual(make_coordinator, hass):
    """Geen harde knip: een venster van twee uur hoort tussen die van één
    en vier in te liggen."""
    c = make_coordinator({})

    een = c._uitgedempte_correctie(DAY0, DAY0 + timedelta(hours=1), 3.0)
    twee = c._uitgedempte_correctie(DAY0, DAY0 + timedelta(hours=2), 3.0)
    vier = c._uitgedempte_correctie(DAY0, DAY0 + timedelta(hours=4), 3.0)

    assert een > twee > vier > 1.0


def test_no_correction_stays_no_correction(make_coordinator, hass):
    """Zonder afwijking mag er niets veranderen, hoe lang het venster ook
    is."""
    c = make_coordinator({})

    assert c._uitgedempte_correctie(DAY0, DAY0 + timedelta(hours=31), 1.0) == 1.0


def test_the_night_estimate_is_no_longer_inflated_by_dinner(
    make_coordinator, hass
):
    """De praktijktoets: koken om half vijf mag de nacht niet vier keer
    zo duur maken."""
    c = make_coordinator({"consumption_power_sensor_entity": "sensor.p1"})
    for hour in range(24):
        c.hourly_consumption_profile[hour] = [0.3]

    start = DAY0.replace(hour=16, minute=30)
    hass.states.set("sensor.p1", "1500")  # koken: 5x het gemiddelde
    for _ in range(4):
        c._track_recent_consumption_reading(start)

    nacht = c._estimate_consumption_kwh_for_period(
        start, start + timedelta(hours=17)
    )
    zonder_correctie = 0.3 * 17

    # Een deel van de piek telt mee - dat is de bedoeling, en naar boven
    # afwijken is de veilige kant: dan houdt de accu meer achter de hand.
    # Maar niet vijf keer het hele etmaal.
    #
    # Met de uitdemping komt er over zeventien uur het equivalent van
    # ruim twee uur verhoogd verbruik bij, in plaats van zeventien.
    assert nacht < zonder_correctie * 5 * 0.4
    assert nacht > zonder_correctie
