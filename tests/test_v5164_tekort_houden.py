"""v5.164.0 - L-EMS-054: een lege accu onder 'waardeplan_houden' telt als tekort."""
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 3, 2, 0, tzinfo=TZ)


def _c(make_coordinator, soc, reden):
    c = make_coordinator({})
    c.last_reason = reden
    c.piekverkoop_tot = None
    c.accustand_procent = lambda: soc
    c.effective_min_soc_percent = lambda: 10.0
    return c


def test_lege_accu_onder_houden_is_tekort(make_coordinator, hass):
    assert _c(make_coordinator, 10, "waardeplan_houden")._netimport_is_tekort(NU) is True


def test_houden_boven_de_vloer_is_geen_tekort(make_coordinator, hass):
    assert _c(make_coordinator, 40, "waardeplan_houden")._netimport_is_tekort(NU) is False


def test_laden_blijft_bewust(make_coordinator, hass):
    assert _c(make_coordinator, 10, "waardeplan_laden")._netimport_is_tekort(NU) is False
