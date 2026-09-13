"""The schedule projection must reflect the secondary price tier
(v0.58.0) too, not just the live "now" decision (v0.58.1 fix).

Regression test for a real report: after installing v0.58.0, the live
decision correctly sold during a secondary-tier quarter right now, but
the *displayed schedule* for the very next quarters at an identical
price still showed 'smart' - because _build_forecast_timeline only
ever checked the primary threshold, never the secondary tier or the
spare headroom left over after primary-tier candidates.
"""
from datetime import datetime, timedelta, timezone

DAY0 = datetime(2026, 8, 3, tzinfo=timezone.utc)


def _build_entries():
    prices = {
        (18, 0): 0.312, (18, 15): 0.3264, (18, 30): 0.35, (18, 45): 0.3785,
        (19, 0): 0.365, (19, 15): 0.37, (19, 30): 0.375, (19, 45): 0.4177,
        (20, 0): 0.3606, (20, 15): 0.365, (20, 30): 0.37, (20, 45): 0.3741,
        (21, 0): 0.30, (21, 15): 0.28,
    }
    entries = []
    for hour in range(24):
        for minute in (0, 15, 30, 45):
            price = prices.get((hour, minute), 0.20)
            start = DAY0.replace(hour=hour, minute=minute)
            entries.append((start, start + timedelta(minutes=15), price * 1_000_000))
    return entries


def test_schedule_projection_includes_secondary_tier_quarters(make_coordinator):
    coordinator = make_coordinator({"manual_discharge_power": 1600})
    entries = _build_entries()
    now = DAY0.replace(hour=19, minute=45)

    # Same figures as the real report: enough spare headroom after the
    # one genuine primary-tier peak quarter for a few more secondary-tier
    # quarters.
    timeline = coordinator._build_forecast_timeline(
        entries,
        now,
        None,
        None,
        available_kwh=6.9984,
        reserve_kwh=5.42463397639144,
    )

    by_start = {t["start"]: t["mode"] for t in timeline}

    # The genuine peak quarter (primary tier) must still be manual.
    assert by_start["2026-08-03T19:45:00+00:00"] == "manual"

    # At least one of the secondary-tier quarters just after it (priced
    # 0.365-0.3741, below the primary bar but within spare headroom)
    # must now also show manual - previously all of these stayed
    # 'smart' because the projection never considered the secondary
    # tier at all.
    secondary_tier_starts = [
        "2026-08-03T20:15:00+00:00",
        "2026-08-03T20:30:00+00:00",
        "2026-08-03T20:45:00+00:00",
    ]
    assert any(by_start[s] == "manual" for s in secondary_tier_starts)
