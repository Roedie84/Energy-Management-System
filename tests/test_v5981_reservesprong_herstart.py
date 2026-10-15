"""v5.98.1 (L-EMS-020-aanvulling): reservesprong vlak na een herstart.

Een sprong in de eerste minuten na de start is opstarten (sensoren en
geleerde waarden komen binnen), geen gedrag van de reserve: gemarkeerd en
niet meegeteld in `reserve_sprongen_aantal`.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import RESERVE_SPRONG_HERSTART_S

TZ = timezone.utc


def _uits(reserve, nodig):
    return {"ronde": 1, "reserve_kwh_after_margin": reserve,
            "needed_kwh_before_margin": nodig, "regelverschuiving_w": 20}


def test_sprong_na_herstart_gemarkeerd_en_niet_geteld(make_coordinator):
    c = make_coordinator({})
    start = datetime(2026, 10, 15, 7, 0, tzinfo=TZ)
    c._started_at = start
    c._noteer_reserve_sprong(start + timedelta(minutes=2), None, _uits(4.0, 3.0), _uits(6.0, 5.0))
    c._noteer_reserve_sprong(start + timedelta(seconds=RESERVE_SPRONG_HERSTART_S + 60), None,
                             _uits(4.0, 3.0), _uits(6.0, 5.0))
    assert c.reserve_sprongen[0].get("na_herstart") is True
    assert "na_herstart" not in c.reserve_sprongen[1]
    attr = c.sturing_meetattributen()
    assert attr["reserve_sprongen_aantal"] == 1
    assert attr["reserve_sprongen_na_herstart"] == 1
