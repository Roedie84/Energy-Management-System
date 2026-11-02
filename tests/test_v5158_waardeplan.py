"""v5.158.0 - het waardeplan stuurt (akkoord Ruud 02-11: "Optimaal aanpassen").

Doorrekening 23-10 t/m 01-11: de accu haalde 35 % van het haalbare
(werkelijk EUR 20,07, zonder accu 22,36, perfect achteraf 15,79). Het
waardeplan rekent elk kwartier de goedkoopste inzet uit over de bekende
prijzen (dynamisch programmeren over de accu-inhoud).
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import waardeplan as W
from custom_components.energy_management_system.const import (
    OPTION_SMART,
    OPTION_SMART_CHARGING,
    PRICE_SCALE_FACTOR,
    REASON_REGISTRY,
    REDENEN_BEWUSTE_NETAFNAME,
)

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 2, 7, 0, tzinfo=TZ)


def _kw(prijzen, verbruik=0.1, zon=0.0, teruglever=None):
    t = NU
    uit = []
    for p in prijzen:
        uit.append(W.Kwartier(t, verbruik, zon, p, p if teruglever is None else teruglever))
        t += timedelta(minutes=15)
    return uit


def _accu(inhoud=0.0, **k):
    return W.Accu(inhoud_kwh=inhoud, bruikbaar_kwh=9.8, rendement=0.83, slijtage_eur=0.053, **k)


# --- het rekenhart -------------------------------------------------------

def test_goedkoop_laden_duur_gebruiken():
    """Eerst 8 goedkope kwartieren (15 ct), dan 8 dure (50 ct)."""
    u = W.plan(_kw([0.15] * 8 + [0.50] * 8, teruglever=0.0), _accu(0.0, verkopen=False))
    acties = [r["actie"] for r in u.kwartieren]
    assert "laden_net" in acties[:8]
    assert all(a in ("huis",) for a in acties[8:])
    assert u.kosten_plan_eur < u.kosten_zonder_accu_eur


def test_vlakke_prijs_niet_laden_uit_het_net():
    u = W.plan(_kw([0.30] * 16), _accu(0.0))
    assert not any(r["actie"] == "laden_net" for r in u.kwartieren)


def test_lading_gaat_naar_de_duurste_kwartieren():
    """1 kWh in de accu, huis 0,1 kWh per kwartier: de lading gaat naar de
    duurste kwartieren, in de goedkopere wordt hij bewaard."""
    prijzen = [0.25, 0.25, 0.45, 0.25, 0.25, 0.45, 0.45, 0.25]
    u = W.plan(_kw(prijzen, teruglever=0.0), _accu(0.25, netladen=False, verkopen=False))
    for r, p in zip(u.kwartieren, prijzen):
        if p == 0.25:
            assert r["actie"] == "houden"
    assert sum(r["actie"] == "huis" for r in u.kwartieren) >= 2


def test_verkopen_alleen_met_marge():
    """Laden 20 ct, verkopen 40 ct: na rendement en slijtage ~11 ct over."""
    prijzen = [0.20] * 8 + [0.40] * 8
    met = W.plan(_kw(prijzen, verbruik=0.0), _accu(0.0, verkoopmarge_eur=0.0))
    assert any(r["actie"] == "verkopen" for r in met.kwartieren)
    hoog = W.plan(_kw(prijzen, verbruik=0.0), _accu(0.0, verkoopmarge_eur=0.15))
    assert not any(r["actie"] == "verkopen" for r in hoog.kwartieren)


def test_zon_overschot_gaat_de_accu_in_als_dat_later_loont():
    prijzen = [0.10] * 4 + [0.45] * 4
    kw = _kw(prijzen, verbruik=0.0, zon=0.0)
    for k in kw[:4]:
        k.zon_kwh = 0.4
    for k in kw[4:]:
        k.verbruik_kwh = 0.3
    u = W.plan(kw, _accu(0.0, netladen=False, verkopen=False))
    assert u.kwartieren[3]["inhoud_kwh"] > 1.0
    assert all(r["actie"] == "huis" for r in u.kwartieren[4:])


def test_nooit_boven_de_capaciteit_of_onder_nul():
    u = W.plan(_kw([0.05] * 40 + [0.6] * 40), _accu(9.0))
    assert all(0.0 <= r["inhoud_kwh"] <= 9.8 + 1e-9 for r in u.kwartieren)


def test_actie_van():
    assert W.actie_van(0.3, 0.1, 0.0)[0] == "laden_net"
    assert W.actie_van(0.1, 0.0, 0.2)[0] == "zon"
    assert W.actie_van(-0.1, 0.1, 0.0)[0] == "huis"
    assert W.actie_van(-0.5, 0.1, 0.0) == ("verkopen", pytest.approx(0.4))
    assert W.actie_van(0.0, 0.2, 0.0)[0] == "houden"


def test_snel_genoeg_voor_36_uur():
    import time

    t0 = time.perf_counter()
    W.plan(_kw([0.2 + 0.1 * ((i // 8) % 3) for i in range(144)]), _accu(4.0))
    assert time.perf_counter() - t0 < 1.0


# --- de sturing --------------------------------------------------------

def _c(make_coordinator, plan, inhoud=5.0, reserve=2.0):
    c = make_coordinator({})
    c.beschikbare_energie_kwh = lambda: inhoud
    c.bereken_waardeplan = lambda now, entries: plan
    c._is_emergency_low_battery = lambda: False
    c.verkoopreserve = lambda now, blok, entries: {"reserve_kwh": reserve}
    c.smart_charging_supported = lambda: True
    toegepast = []

    async def manual(w):
        toegepast.append(("manual", w))

    async def stand(s):
        toegepast.append(("stand", s))

    c._async_apply_manual = manual
    c._async_apply_operation = stand
    c._update_financial_tracking = lambda *a, **k: None
    c._update_shortfall_detection = lambda *a, **k: None
    c._finish_decision_tick = lambda *a, **k: None
    return c, toegepast


def _plan(actie, accu_kwh, kwh, inhoud=5.0):
    return {
        "beschikbaar": True, "inhoud_kwh": inhoud, "bruikbaar_kwh": 9.8,
        "nu": {"actie": actie, "accu_kwh": accu_kwh, "kwh": kwh, "prijs_eur": 0.3,
               "begin": NU.isoformat(), "inhoud_kwh": inhoud},
        "vooruit": [], "kwartieren": 96, "besparing_plan_eur": 1.2,
    }


def test_houden_wordt_smart_charging(make_coordinator, hass):
    c, t = _c(make_coordinator, _plan("houden", 0.0, 0.0))
    assert asyncio.run(c._waardeplan_als_nodig(NU, [])) is True
    assert c.last_reason == "waardeplan_houden"
    assert t[-1] == ("stand", OPTION_SMART_CHARGING)


def test_huis_wordt_smart(make_coordinator, hass):
    c, t = _c(make_coordinator, _plan("huis", -0.2, 0.2))
    asyncio.run(c._waardeplan_als_nodig(NU, []))
    assert c.last_reason == "waardeplan_huis"
    assert t[-1] == ("stand", OPTION_SMART)


def test_laden_uit_het_net(make_coordinator, hass):
    c, t = _c(make_coordinator, _plan("laden_net", 0.6, 0.6))
    asyncio.run(c._waardeplan_als_nodig(NU, []))
    assert c.last_reason == "waardeplan_laden"
    from custom_components.energy_management_system.const import DEFAULT_MANUAL_CHARGE_POWER

    assert t[-1] == ("manual", -min(abs(DEFAULT_MANUAL_CHARGE_POWER), 2400))


def test_verkopen_boven_de_reserve(make_coordinator, hass):
    c, t = _c(make_coordinator, _plan("verkopen", -0.6, 0.5), inhoud=5.0, reserve=2.0)
    asyncio.run(c._waardeplan_als_nodig(NU, []))
    from custom_components.energy_management_system.const import DEFAULT_MANUAL_DISCHARGE_POWER

    assert c.last_reason == "waardeplan_verkopen"
    assert t[-1] == ("manual", min(abs(DEFAULT_MANUAL_DISCHARGE_POWER), 2400))


def test_niet_verkopen_onder_de_reserve(make_coordinator, hass):
    """Het huis gaat voor: onder de verkoopreserve wordt niets verkocht."""
    c, t = _c(make_coordinator, _plan("verkopen", -0.6, 0.5), inhoud=2.0, reserve=2.5)
    asyncio.run(c._waardeplan_als_nodig(NU, []))
    assert c.last_reason == "waardeplan_huis"
    assert t[-1] == ("stand", OPTION_SMART)
    assert c.last_waardeplan["verkoop_tegengehouden"]


def test_zonder_plan_gelden_de_oude_regels(make_coordinator, hass):
    c, t = _c(make_coordinator, {"beschikbaar": False, "reden": "geen verbruik"})
    assert asyncio.run(c._waardeplan_als_nodig(NU, [])) is False
    assert t == []


def test_bijna_leeg_gaat_voor(make_coordinator, hass):
    c, t = _c(make_coordinator, _plan("houden", 0.0, 0.0))
    c._is_emergency_low_battery = lambda: True
    assert asyncio.run(c._waardeplan_als_nodig(NU, [])) is False


def test_celbescherming_gaat_voor_en_daarna_het_waardeplan(make_coordinator, hass):
    c, t = _c(make_coordinator, _plan("huis", -0.2, 0.2))
    c.celbeschermingsbesluit = lambda now: {"actie": None}
    assert asyncio.run(c._celbescherming_als_nodig(NU, [])) is True
    assert c.last_reason == "waardeplan_huis"
    c.celbeschermingsbesluit = lambda now: {"actie": "houden"}
    asyncio.run(c._celbescherming_als_nodig(NU, []))
    assert c.last_reason == "celbescherming_houden"


def test_een_keer_per_kwartier_rekenen(make_coordinator, hass):
    c, _ = _c(make_coordinator, None)
    teller = []

    def reken(now, entries):
        teller.append(now)
        return _plan("huis", -0.2, 0.2)

    c.bereken_waardeplan = reken
    c._waardeplan_nu(NU, [])
    c._waardeplan_nu(NU + timedelta(minutes=1), [])
    assert len(teller) == 1
    c._waardeplan_nu(NU + timedelta(minutes=15), [])
    assert len(teller) == 2


def test_waarom_regels(make_coordinator, hass):
    c, _ = _c(make_coordinator, _plan("houden", 0.0, 0.0))
    c.last_waardeplan = {
        **_plan("houden", 0.0, 0.0),
        "vooruit": [
            {"begin": "2026-11-02T07:00:00+01:00", "actie": "houden", "prijs_eur": 0.3},
            {"begin": "2026-11-02T18:00:00+01:00", "actie": "huis", "prijs_eur": 0.52},
        ],
    }
    regels = " · ".join(c._waarom_waardeplan())
    assert "18:00 (52 ct)" in regels
    c.last_reason = "waardeplan_houden"
    assert "Onbekende reden" not in c._build_explanation()


def test_kwartieren_met_salderen_en_daarna(make_coordinator, hass):
    c = make_coordinator({})
    c._segmenten_verbruik_zon = lambda a, b, veilig=True: [(0.1, 0.0)]
    c._estimate_pv_kwh_for_period = lambda a, b, veilig=False: 0.05
    eind_2026 = datetime(2026, 12, 31, 23, 45, tzinfo=TZ)
    entries = [
        (eind_2026, eind_2026 + timedelta(minutes=15), 0.30 * PRICE_SCALE_FACTOR),
        (eind_2026 + timedelta(minutes=15), eind_2026 + timedelta(minutes=30), 0.30 * PRICE_SCALE_FACTOR),
    ]
    c._kale_entries = lambda: [(entries[1][0], entries[1][1], 0.19 * PRICE_SCALE_FACTOR)]
    c._is_salderen_active = lambda t: t < datetime(2027, 1, 1, tzinfo=TZ)
    kw = c._waardeplan_kwartieren(eind_2026, entries)
    assert kw[0].teruglever_eur > 0.30          # salderen: inkoop + premie
    assert kw[1].teruglever_eur < 0.30          # 2027: kale prijs
    assert kw[0].verbruik_kwh == 0.1 and kw[0].zon_kwh == 0.05


def test_redenen_geregistreerd():
    for reden in ("waardeplan_laden", "waardeplan_verkopen", "waardeplan_huis", "waardeplan_houden"):
        assert reden in REASON_REGISTRY
    assert "waardeplan_houden" in REDENEN_BEWUSTE_NETAFNAME
    assert "waardeplan_laden" in REDENEN_BEWUSTE_NETAFNAME


def test_kwartierplan_toont_het_waardeplan(make_coordinator, hass):
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: 11.52
    c.effective_min_soc_percent = lambda: 15.0
    c._waardeplan_rijen = [
        {"begin": NU, "actie": "houden", "inhoud_kwh": 2.0, "net_kwh": 0.1},
        {"begin": NU + timedelta(minutes=15), "actie": "verkopen", "inhoud_kwh": 1.4, "net_kwh": -0.4},
    ]
    plan = [
        {"start": NU.isoformat(), "modus": "smart", "soc_kwh": 3.0, "net_kwh": 0.0, "tekort": True},
        {"start": (NU + timedelta(minutes=15)).isoformat(), "modus": "smart", "soc_kwh": 2.9},
        {"start": (NU + timedelta(minutes=30)).isoformat(), "modus": "smart", "soc_kwh": 2.8},
    ]
    uit = c._met_waardeplan(plan)
    assert uit[0]["modus"] == "smart_charging (sparen)" and uit[0]["soc_kwh"] == 2.0
    assert uit[0]["tekort"] is False and uit[0]["bron"] == "waardeplan"
    assert uit[1]["modus"] == "manual (verkopen)" and uit[1]["net_kwh"] == -0.4
    assert uit[2] == plan[2]
