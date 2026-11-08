"""v5.194.2: de planning werkt bij tijdens de kalibratie.

Gemeld 08-11 11:30: de tabel bleef op het plan van voor de kalibratie (accu
10 %, sparen) terwijl de accu op 2,4 kW vol laadde. Nu: laden tot vol, een
uur vasthouden, daarna het gewone plan vanaf een volle accu.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import kalibratie_plan as K
from custom_components.energy_management_system import waardeplan as W

T0 = datetime(2026, 11, 8, 11, 30, tzinfo=timezone.utc)


def _ks(n=96):
    return [W.Kwartier(T0 + timedelta(minutes=15 * i), 0.1, 0.0, 0.30 if i < 40 else 0.45, 0.05)
            for i in range(n)]


def _accu(inhoud):
    return W.Accu(inhoud_kwh=inhoud, bruikbaar_kwh=8.0, laden_kw=2.4, rendement=0.81, verkopen=False)


def test_laadt_tot_vol_en_houdt_een_uur_vast():
    res = K.plan(_ks(), _accu(1.0), None, 60)
    rijen = res.kwartieren
    assert res.beschikbaar and len(rijen) == 96
    kal = [r for r in rijen if r.get("kalibratie")]
    assert all(r["actie"] == "laden_net" for r in kal)
    assert kal[0]["accu_kwh"] == pytest.approx(0.6) and kal[0]["vol_vermogen"]
    vol = next(i for i, r in enumerate(kal) if r["inhoud_kwh"] >= 8.0 - K.VOL_MARGE_KWH)
    # na vol nog een uur (4 kwartieren, de rest van het volle kwartier telt mee)
    assert len(kal) - vol - 1 in (4, 5)
    assert all(r["accu_kwh"] == 0 for r in kal[vol + 1:])
    # daarna het gewone plan, vanaf vol
    na = rijen[len(kal)]
    assert not na.get("kalibratie") and na["inhoud_kwh"] <= 8.0


def test_al_vol_houdt_tot_het_bekende_einde():
    res = K.plan(_ks(), _accu(8.0), T0 + timedelta(minutes=40), 60)
    kal = [r for r in res.kwartieren if r.get("kalibratie")]
    assert len(kal) == 3 and all(r["accu_kwh"] == 0 for r in kal)


def test_ronde_vult_de_planning(make_coordinator, hass):
    c = make_coordinator({"battery_soc_sensor_entity": "sensor.soc"})
    hass.states.set("sensor.soc", "26")
    c.kalibratie = True
    c.kalibratie_vol_sinds = None
    c._waardeplan_invoer = lambda now, e: {"kwartieren": _ks(), "accu": _accu(1.5), "bruikbaar": 8.0, "balans": {}}
    c._waardeplan_cache = ("oud", {"beschikbaar": True})
    asyncio.new_event_loop().run_until_complete(c._kalibratie_planning(T0, []))
    assert c.last_waardeplan.get("kalibratie") is True and c.last_waardeplan.get("beschikbaar")
    assert c._waardeplan_rijen[0]["kalibratie"] and c._waardeplan_rijen[0]["actie"] == "laden_net"
    assert c._waardeplan_cache is None
