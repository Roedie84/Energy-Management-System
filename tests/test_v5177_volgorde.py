"""v5.177.0 (A15) - het waardeplan eerst; de oude regels alleen als terugval."""
import asyncio
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 4, 13, 0, tzinfo=TZ)


def _c(make_coordinator, plan_resultaat):
    c = make_coordinator({})
    toegepast, plan = [], []

    async def manual(w):
        toegepast.append(w)

    async def waardeplan(now, entries):
        plan.append(now)
        return plan_resultaat

    c._async_apply_manual = manual
    c._waardeplan_als_nodig = waardeplan
    c._start_solar_ramp = lambda *a: None
    c.celbeschermingsbesluit = lambda now: {"actie": None}
    c._update_financial_tracking = lambda *a, **k: None
    c._finish_decision_tick = lambda *a, **k: None
    return c, toegepast, plan


def test_negatieve_prijs_volgt_het_plan(make_coordinator, hass):
    c, toegepast, plan = _c(make_coordinator, True)
    asyncio.run(c._negatieve_prijs_ronde(NU, []))
    assert plan and toegepast == [] and c._is_negative_price_active


def test_negatieve_prijs_zonder_plan_vaste_lading(make_coordinator, hass):
    c, toegepast, plan = _c(make_coordinator, False)
    asyncio.run(c._negatieve_prijs_ronde(NU, []))
    assert c.last_reason == "negative_price" and len(toegepast) == 1


def test_secundaire_laag_overgeslagen_als_het_plan_stuurt(make_coordinator, hass):
    c = make_coordinator({})
    c._get_secondary_expensive_price_threshold = lambda entries, now: 300000
    c._waardeplan_gaat_sturen = lambda now, entries: True
    c._get_dynamic_discharge_reserve_kwh = lambda *a, **k: (_ for _ in ()).throw(AssertionError("niet nodig"))
    assert c._secundaire_laag(NU, [], None) is False
    assert c.last_secondary_price_threshold is not None   # de drempel blijft voor de weergave
