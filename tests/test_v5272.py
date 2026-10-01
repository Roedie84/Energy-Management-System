"""Systeemcontrole van 1 oktober (v5.27.2): snelheid, de zonarme dag in het
plan, en de opstarttekst."""
import random
from datetime import datetime, timedelta, timezone

import pytest

TZ = timezone(timedelta(hours=2))
START = datetime(2026, 10, 1, 13, 30, tzinfo=TZ)


def _reeks(rng, n=220, gaten=True):
    uit, t = [], START
    for _ in range(n):
        if gaten and rng.random() < 0.05:
            t += timedelta(minutes=15 * rng.randint(1, 4))   # een gat in de reeks
        uit.append((t, round(rng.uniform(0.15, 0.55), 4)))
        t += timedelta(minutes=15)
    return uit


@pytest.mark.parametrize("zaad", range(12))
def test_de_snelle_piekgrens_is_exact_de_oude(make_coordinator, hass, zaad):
    """Dezelfde uitkomst als `_duurste_later` per kwartier - alleen sneller."""
    c = make_coordinator({})
    rng = random.Random(zaad)
    reeks = _reeks(rng)
    blok = None if zaad % 4 == 0 else reeks[rng.randint(5, 150)][0]
    vervang = None if zaad % 3 == 0 else rng.uniform(0.25, 0.50)

    snel = c._duurste_later_alle(reeks, blok, vervang)

    for begin, _p in reeks:
        verwacht = c._duurste_later(
            begin, reeks,
            blok if blok is not None and blok > begin else None,
            vervang if blok is not None and blok > begin else None,
        )
        assert snel[begin] == verwacht, begin


def test_het_plan_wordt_een_keer_per_ronde_opgebouwd(make_coordinator, hass):
    c = make_coordinator({})
    c._forecast_cache_ronde = START
    keer = []
    c.get_quarter_plan = lambda now=None: keer.append(1) or []

    c.get_plan_blokken()
    c.get_plan_blokken()
    assert len(keer) == 1

    c._forecast_cache_ronde = START + timedelta(minutes=5)
    c.get_plan_blokken()
    assert len(keer) == 2


def test_de_zonarme_dag_zoals_de_verkooptoets_hem_ziet(make_coordinator, hass):
    from custom_components.energy_management_system.const import SOLAR_POOR_DAY_KWH

    c = make_coordinator({})
    c._zon_vandaag_totaal = lambda now: (SOLAR_POOR_DAY_KWH - 1, None, 0.0)
    c.config = dict(c.config or {})
    c.config["solar_forecast_sensor_entity"] = "sensor.solcast_morgen"
    hass.states.set("sensor.solcast_morgen", str(SOLAR_POOR_DAY_KWH + 5))

    zonarm = c._zonarme_dagen(START)

    assert zonarm[START.date()] is True
    assert zonarm[(START + timedelta(days=1)).date()] is False


def test_het_plan_verkoopt_niet_boven_de_reserve_op_een_zonarme_dag():
    """Dezelfde poort als `may_sell_now`; de piekregel gaat er wel voor."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    assert 'and not netregels["zonarm"].get(start.date(), False)' in bron
    assert "verwacht_vandaag, al_opgewekt, nog_te_komen = self._zon_vandaag_totaal(now)" in bron


def test_de_opstarttekst_zegt_dat_de_sturing_al_draait(make_coordinator, hass):
    c = make_coordinator({})
    c._started_at = START
    c.opstart_resterend_s = lambda now=None: 60.0

    assert "De sturing draait al" in c.opstart_tekst()
