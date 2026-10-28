"""v5.142.2 - het plan spaart ook tussen twee laadblokken (gemeld 28-10 21:33).

De sturing kijkt elk kwartier naar het eerstvolgende laadkwartier in het blok
(`_netladen_volgt_in_blok`) en spaart als terugladen duurder is dan de stroom
nu. Het plan nam alleen de kwartieren tot het EERSTE laadmoment over en liet
00:00-00:45 en 01:00-01:45 op "slim" staan.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import PRICE_SCALE_FACTOR

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 10, 28, 21, 30, tzinfo=TZ)
BLOK = (NU, datetime(2026, 10, 29, 6, 0, tzinfo=TZ))
PRIJZEN = {  # ct, 28-10
    "21:30": 47.5, "23:30": 41.5, "23:45": 40.4, "00:00": 42.4, "00:15": 42.5,
    "00:45": 41.2, "01:00": 42.4, "01:45": 41.4, "02:00": 41.5, "05:45": 60.0,
}


def _t(hhmm):
    h, m = map(int, hhmm.split(":"))
    dag = NU if h >= 12 else NU + timedelta(days=1)
    return dag.replace(hour=h, minute=m)


def _entries():
    return [
        (_t(k), _t(k) + timedelta(minutes=15), v / 100 * PRICE_SCALE_FACTOR)
        for k, v in PRIJZEN.items()
    ]


def _c(make_coordinator, monkeypatch, laden=("23:45", "00:45", "01:45")):
    c = make_coordinator({})
    c.last_cheap_block_start, c.last_cheap_block_end = BLOK
    c.laadplan_gewijzigd = {"kwartieren": [_t(x).isoformat() for x in laden]}
    monkeypatch.setattr(type(c), "learned_battery_efficiency_percent",
                        property(lambda self: 83.5))
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": 4.22}
    return c


def test_spaart_tussen_de_laadblokken(make_coordinator, monkeypatch):
    c = _c(make_coordinator, monkeypatch)
    gespaard = c._plan_sparen_tussen_laden(NU, _entries())
    for k in ("21:30", "23:30", "00:00", "00:15", "01:00"):
        assert _t(k) in gespaard, k


def test_niet_na_het_laatste_laadkwartier_of_in_een_laadkwartier(make_coordinator, monkeypatch):
    c = _c(make_coordinator, monkeypatch)
    gespaard = c._plan_sparen_tussen_laden(NU, _entries())
    for k in ("23:45", "00:45", "01:45", "02:00", "05:45"):
        assert _t(k) not in gespaard, k


def test_niet_als_stroom_nu_duurder_is_dan_terugladen(make_coordinator, monkeypatch):
    c = _c(make_coordinator, monkeypatch, laden=("23:45",))
    entries = [(b, e, 0.60 * PRICE_SCALE_FACTOR if b == _t("21:30") else p)
               for b, e, p in _entries()]
    assert _t("21:30") not in c._plan_sparen_tussen_laden(NU, entries)


def test_zonder_laadplan_of_blok_niets(make_coordinator, monkeypatch):
    c = _c(make_coordinator, monkeypatch, laden=())
    assert c._plan_sparen_tussen_laden(NU, _entries()) == set()
    c = _c(make_coordinator, monkeypatch)
    c.last_cheap_block_start = None
    assert c._plan_sparen_tussen_laden(NU, _entries()) == set()


def test_plan_gebruikt_het():
    bron = open("custom_components/energy_management_system/coordinator.py",
                encoding="utf-8").read()
    assert "| self._plan_sparen_tussen_laden(now, entries)" in bron
