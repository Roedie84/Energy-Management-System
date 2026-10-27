"""v5.140.0: nabeschouwing met netladen (L-EMS-042) en meetlog-opslag.

Akkoord Ruud 27-10 20:16 (punten 5 en 8).
- Nabeschouwing: 3 van 7 dagen 'beter dan perfect' (26-10 € 1,92 tegen
  € 0,70), want de meetlat laadde niet uit het net en de sturing wel.
- Meetlog: 26,6 MB tegen een limiet van 26,2 MB na 19 dagen; de limiet wiste
  per dag snapshot én evaluatie samen.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import meetlog

TZ = timezone.utc


def test_snapshots_14_dagen_evaluaties_30():
    assert meetlog.BEWAREN_DAGEN["snapshot"] == 14
    assert meetlog.BEWAREN_DAGEN["evaluatie"] == 30
    log = meetlog.MeetLog()
    vandaag = datetime(2026, 10, 27, tzinfo=TZ)
    m = vandaag - timedelta(days=20)
    log.leg_snapshot_vast({"a": 1}, m)
    log.voeg_toe("evaluatie", m, {"x": 1})
    log.opruimen(vandaag.date())
    over = {s for s, _ in log._groottes}
    assert "snapshot" not in over
    assert "evaluatie" in over


def test_limiet_wist_eerst_snapshots_dan_evaluaties():
    log = meetlog.MeetLog(limiet_bytes=40_000)
    vandaag = datetime(2026, 10, 27, tzinfo=TZ)
    groot = "a" * 3000
    for d in range(10, 0, -1):
        m = vandaag - timedelta(days=d)
        log.leg_snapshot_vast({"s": groot, "d": d}, m)
        log.voeg_toe("evaluatie", m, {"e": groot})
    log.opruimen(vandaag.date())
    assert log.grootte_bytes() <= 40_000
    # alle evaluaties staan er nog; alleen snapshots zijn gewist
    assert sum(1 for s, _ in log._groottes if s == "evaluatie") == 10
    assert all(r.startswith("snapshot") for r in log.door_limiet_gewist)


def test_limiet_is_40_mb():
    assert meetlog.LIMIET_BYTES == 40 * 1024 * 1024
