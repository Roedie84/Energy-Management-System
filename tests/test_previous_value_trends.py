"""'Previous value' helpers for continuously-updating rolling averages
(v0.54.0) - hourly consumption profile and PV hourly bias don't have a
discrete "history" list like the daily trackers do, so these compute
"the average before the most recent sample" instead, to support a
dashboard trend display.
"""
import pytest




def test_previous_hourly_avg_kw_excludes_the_last_sample(make_coordinator):
    coordinator = make_coordinator({})
    coordinator.hourly_consumption_profile[9] = [0.3, 0.4, 0.5]

    # Current average (all 3 samples): 0.4
    assert coordinator.learned_hourly_avg_kw(9) == pytest.approx(0.4)
    # Previous average (first 2 samples only): 0.35
    assert coordinator.previous_hourly_avg_kw(9) == pytest.approx(0.35)


def test_previous_hourly_avg_kw_none_with_fewer_than_two_samples(make_coordinator):
    coordinator = make_coordinator({})
    coordinator.hourly_consumption_profile[9] = [0.3]

    assert coordinator.previous_hourly_avg_kw(9) is None


def test_previous_pv_hourly_ratio_excludes_the_last_sample(make_coordinator):
    coordinator = make_coordinator({})
    coordinator.pv_hourly_bias_history[10] = [0.8, 0.9, 1.0]

    assert coordinator.previous_pv_hourly_ratio(10) == pytest.approx(0.85)


def test_previous_pv_hourly_ratio_none_with_fewer_than_two_samples(make_coordinator):
    coordinator = make_coordinator({})
    coordinator.pv_hourly_bias_history[10] = [0.8]

    assert coordinator.previous_pv_hourly_ratio(10) is None
