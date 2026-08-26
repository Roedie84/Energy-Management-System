"""_should_postpone_charging must use the worst-case cumulative deficit
(v0.43.0), not the old net-balance-over-the-whole-window estimate
(v0.57.1 fix).

Regression test for a real report: the explanation text showed "geschat
nodig: 0.00 kWh" purely because expected solar (5.78 kWh) slightly
exceeded flat baseline consumption (5.356 kWh) over the whole bridging
window - even though the worst-case-deficit fix (v0.43.0) had already
solved exactly this "abundant solar hides a real overnight shortfall"
problem for the discharge-power cap. It just hadn't been wired into
this postpone-charging decision too.
"""
from datetime import datetime, timedelta, timezone


def _two_day_pv_forecast(peak_kw: float, start_hour: int = 8, end_hour: int = 16):
    detailed = []
    for day_offset in range(2):
        for hour in range(24):
            for minute in (0, 30):
                pv = peak_kw if start_hour <= hour < end_hour else 0.0
                detailed.append(
                    {
                        "period_start": (
                            datetime(2026, 8, 2, tzinfo=timezone.utc)
                            + timedelta(days=day_offset)
                        ).replace(hour=hour, minute=minute),
                        "pv_estimate": pv,
                    }
                )
    return detailed


def test_postpone_decision_uses_worst_case_deficit_not_net_balance(
    make_coordinator, hass
):
    day0 = datetime(2026, 8, 2, tzinfo=timezone.utc)
    coordinator = make_coordinator(
        {
            "solar_forecast_sensor_entity": "sensor.solcast",
            "available_energy_sensor_entity": "sensor.available",
        }
    )
    hass.states.set("sensor.available", "5.0")
    for hour in range(24):
        coordinator.hourly_consumption_profile[hour] = [0.3]  # flat 300W all day

    hass.states.set(
        "sensor.solcast", "11.2", {"detailedForecast": _two_day_pv_forecast(1.4)}
    )

    start = day0.replace(hour=23, minute=45)
    end = (day0 + timedelta(days=1)).replace(hour=11, minute=15)

    # The old net-balance approach would show ~0 needed here (abundant
    # solar tomorrow more than covers flat baseline consumption over the
    # whole window) - confirm that premise still holds for this data.
    naive_consumption = coordinator._estimate_consumption_kwh_for_period(start, end)
    naive_pv_offset = coordinator._get_efficiency_discounted_pv_offset(start, end)
    assert naive_consumption - naive_pv_offset <= 0.5  # near-zero net balance

    # The worst-case-deficit figure must still show a real, positive
    # overnight shortfall despite that.
    worst_case = coordinator._estimate_worst_case_deficit_kwh(start, end)
    assert worst_case > 2.0

    # And _should_postpone_charging's own breakdown must report that
    # same worst-case figure (via last_needed_kwh_breakdown), not the
    # old near-zero net balance.
    coordinator._should_postpone_charging([], start, end)
    breakdown = coordinator.last_needed_kwh_breakdown
    assert breakdown["diepste_tekort_kwh"] == round(worst_case, 3)
    assert breakdown["diepste_tekort_kwh"] > 2.0
