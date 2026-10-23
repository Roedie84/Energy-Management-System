"""v5.120.0 (leerronde 23-10, H-EMS-14): de live verbruikscorrectie zichtbaar
in de reserve-uitsplitsing en in de reservesprongen. Alleen meten.

22-10 20:11-23:00: 17 sprongen "alleen behoefte" waarin
`needed_kwh_before_margin` telkens ~1,49 kWh wisselde (8,90 <-> 10,39) met
alle bijdragen 0, dus `grootste_onderdeel` "basisbehoefte". Het verschil is
precies CONSUMPTION_CORRECTION_MAX_EXTRA_KWH (1,5): de live correctie die aan
en uit ging. Om 00:00, 00:09 en 02:13 veranderde zo ook de reserve zelf
(niet afgekapt: 10,37 -> 9,85, 9,81 -> 10,21, 9,64 -> 9,26).
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import (
    CONSUMPTION_CORRECTION_MAX_EXTRA_KWH,
)

TZ = timezone(timedelta(hours=2))


def _uits(reserve, nodig, live):
    return {
        "reserve_kwh_after_margin": reserve, "needed_kwh_before_margin": nodig,
        "lange_horizon_extra_kwh": 0.0, "regelverschuiving_w": 10,
        "total_percent": 25.0, "airco_ochtend_extra_kwh": 0.0,
        "airco_gebruik_extra_kwh": 0.0, "temperatuur_extra_kwh": 0.0,
        "live_correctie_extra_kwh": live, "live_correctie_verhouding": 1.0 if not live else 3.0,
        "ongekapt_kwh": nodig * 1.25, "bodem_bindend": False, "boven_capaciteit": True,
    }


def test_sprong_door_live_correctie_heet_zo(make_coordinator):
    c = make_coordinator({})
    nu = datetime(2026, 10, 22, 20, 11, tzinfo=TZ)
    blok = datetime(2026, 10, 23, 21, 45, tzinfo=TZ)
    c._noteer_reserve_sprong(nu, blok, _uits(10.368, 9.434, 0.0), _uits(10.368, 10.93, 1.5))
    s = c.reserve_sprongen[-1]
    assert s["bijdragen_kwh"]["live_correctie_extra_kwh"] == pytest.approx(1.5)
    assert s["grootste_onderdeel"] == "live_correctie_extra_kwh"
    assert s["live_correctie_extra_kwh"] == [0.0, 1.5]
    assert s["live_correctie_verhouding"] == [1.0, 3.0]
    assert s["alleen_behoefte"] is True


def test_zonder_live_veld_blijft_het_basisbehoefte(make_coordinator):
    """Oude uitsplitsing (van voor de update): geen veld, geen bijdrage."""
    c = make_coordinator({})
    nu = datetime(2026, 10, 22, 20, 11, tzinfo=TZ)
    oud = _uits(10.368, 9.434, 0.0)
    nieuw = _uits(10.368, 10.93, 1.5)
    del oud["live_correctie_extra_kwh"], nieuw["live_correctie_extra_kwh"]
    c._noteer_reserve_sprong(nu, None, oud, nieuw)
    assert c.reserve_sprongen[-1]["grootste_onderdeel"] == "basisbehoefte"


def _wandeling(c, live_kw, geleerd_kw=0.3):
    c.learned_hourly_avg_kw = lambda uur: geleerd_kw
    c._estimate_pv_kwh_for_period = lambda a, b, veilig=True: 0.0
    c.geplande_witgoed_kwh_in_periode = lambda a, b: 0.0
    c.lopend_witgoed_kwh_in_periode = lambda a, b: 0.0
    c.regelverschuiving_kw = lambda: 0.0
    c._vacation_adjusted_kwh = lambda kwh: kwh
    c._get_smoothed_consumption_correction_ratio = (
        lambda uur: max(1.0, live_kw / geleerd_kw)
    )
    from custom_components.energy_management_system import coordinator as mod

    nu = mod.dt_util.now()  # dezelfde klok als de uitdemping
    return c._segmenten_verbruik_zon(nu, nu + timedelta(hours=25))


def test_wandeling_noteert_de_live_correctie(make_coordinator):
    c = make_coordinator({})
    _wandeling(c, live_kw=1.2)
    live = c._laatste_live_correctie
    assert live["verhouding"] == pytest.approx(4.0)
    assert 0 < live["extra_kwh"] <= CONSUMPTION_CORRECTION_MAX_EXTRA_KWH
    _wandeling(c, live_kw=0.2)
    assert c._laatste_live_correctie == {"extra_kwh": 0.0, "verhouding": 1.0}


def test_segmenten_ongewijzigd_door_het_meten(make_coordinator):
    """Het meten verandert de wandeling zelf niet."""
    c = make_coordinator({})
    a = _wandeling(c, live_kw=1.2)
    c.__dict__.pop("_laatste_live_correctie", None)
    b = _wandeling(c, live_kw=1.2)
    assert [x for seg in a for x in seg] == pytest.approx(
        [x for seg in b for x in seg], abs=1e-6
    )
