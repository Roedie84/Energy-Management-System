"""v5.172.0 punt 2 - geen mini-laadblokken, en 'blok' volgt het plan.

03-11 12:00: het waardeplan had `laden_net` 0,027 kWh (een stap van 0,1 kWh
inhoud = ~0,12 kWh AC boven een zonoverschot van ~0,09) en zette de Zendure op
manual. `diagnose_sturing` noemde nog 'blok 10:15' (het oude goedkope blok).
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import waardeplan as W
from custom_components.energy_management_system.const import WAARDEPLAN_MIN_ACTIE_W

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 3, 12, 0, tzinfo=TZ)


def _kw(spec):
    t, uit = NU, []
    for verbruik, zon, prijs in spec:
        uit.append(W.Kwartier(t, verbruik, zon, prijs, prijs))
        t += timedelta(minutes=15)
    return uit


# --- de vertaling van een stap naar een actie ------------------------------

def test_restje_netlading_met_zon_wordt_zon():
    assert W.actie_van(0.12, 0.0, 0.093)[0] == "laden_net"  # zonder grens: het oude gedrag
    actie, kwh = W.actie_van(0.12, 0.0, 0.093, 0.1)
    assert actie == "zon" and kwh == pytest.approx(0.093)


def test_restje_netlading_zonder_zon_wordt_houden():
    assert W.actie_van(0.05, 0.1, 0.1, 0.1) == ("houden", 0.0)


def test_echte_netlading_blijft():
    assert W.actie_van(0.3, 0.1, 0.0, 0.1) == ("laden_net", pytest.approx(0.3))


def test_restje_verkoop_wordt_huis():
    assert W.actie_van(-0.15, 0.1, 0.0, 0.1) == ("huis", pytest.approx(0.1))
    assert W.actie_van(-0.5, 0.1, 0.0, 0.1) == ("verkopen", pytest.approx(0.4))


def test_drempel_is_400_w_een_tiende_kwh_per_kwartier():
    assert WAARDEPLAN_MIN_ACTIE_W == 400.0


# --- in het plan -------------------------------------------------------------

def _plan(min_w):
    spec = [(0.10, 0.17, 0.28)] + [(0.3, 0.0, 0.45)] * 4
    accu = W.Accu(inhoud_kwh=0.0, bruikbaar_kwh=9.8, rendement=0.83, slijtage_eur=0.03,
                  laden_kw=0.48, min_actie_w=min_w)
    return W.plan(_kw(spec), accu).kwartieren[0]


def test_plan_zonder_grens_heeft_het_restje():
    rij = _plan(0.0)
    assert rij["actie"] == "laden_net" and rij["kwh"] < 0.1


def test_plan_met_grens_laadt_alleen_de_zon():
    rij = _plan(WAARDEPLAN_MIN_ACTIE_W)
    assert rij["actie"] == "zon"
    # de inhoud van het plan blijft de stap (de zon gaat er in de slimme stand in)
    assert rij["inhoud_kwh"] == pytest.approx(0.1)


def test_een_kort_kwartier_heeft_een_evenredig_kleinere_grens():
    k = W.Kwartier(NU, 0.0, 0.0, 0.2, 0.2, uren=0.1)
    # 400 W x 0,1 u = 0,04 kWh: een lading van 0,05 kWh telt dan wel
    assert W.actie_van(0.05, k.verbruik_kwh, k.zon_kwh, 400 / 1000 * k.uren)[0] == "laden_net"


def test_coordinator_geeft_de_grens_mee():
    from pathlib import Path

    bron = Path(W.__file__).with_name("coordinator.py").read_text(encoding="utf-8")
    assert "min_actie_w=WAARDEPLAN_MIN_ACTIE_W" in bron


# --- 'blok' in de diagnose volgt het plan van nu -----------------------------

def _stuurt(make_coordinator, rijen):
    c = make_coordinator({})
    c.last_reason = "waardeplan_houden"
    c.last_waardeplan = {"beschikbaar": True}
    c._waardeplan_rijen = rijen
    c.last_cheap_block_start = datetime(2026, 11, 3, 10, 15, tzinfo=TZ)
    return c


def _blok(c):
    return dict(c._diagnose_sturing())["blok"]()


def test_blok_komt_uit_het_plan(make_coordinator, hass, monkeypatch):
    from homeassistant.util import dt as dt_util

    monkeypatch.setattr(dt_util, "now", lambda *a, **k: datetime(2026, 11, 3, 11, 50, tzinfo=TZ))
    rijen = [
        {"begin": NU - timedelta(minutes=15), "actie": "houden", "kwh": 0.0},
        {"begin": NU, "actie": "laden_net", "kwh": 0.4},
        {"begin": NU + timedelta(minutes=15), "actie": "laden_net", "kwh": 0.4},
    ]
    assert _blok(_stuurt(make_coordinator, rijen)) == "12:00 plan"


def test_plan_zonder_netlading_zegt_geen(make_coordinator, hass, monkeypatch):
    from homeassistant.util import dt as dt_util

    monkeypatch.setattr(dt_util, "now", lambda *a, **k: datetime(2026, 11, 3, 11, 50, tzinfo=TZ))
    rijen = [{"begin": NU + timedelta(minutes=15 * i), "actie": "houden", "kwh": 0.0} for i in range(8)]
    assert _blok(_stuurt(make_coordinator, rijen)).startswith("geen")


def test_zonder_waardeplan_het_oude_blok(make_coordinator, hass):
    c = _stuurt(make_coordinator, [])
    c.last_reason = "default_smart"
    assert _blok(c) == "10:15"
