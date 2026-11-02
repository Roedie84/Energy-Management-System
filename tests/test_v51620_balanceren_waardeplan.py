"""v5.162.0: balanceerlading onder het waardeplan (L-EMS-055) en vol laadvermogen."""
import asyncio
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import planvolging, waardeplan as W

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 2, 20, 0, tzinfo=TZ)


def _kw(prijzen):
    return [
        W.Kwartier(NU + timedelta(minutes=15 * i), 0.1, 0.0, p, p)
        for i, p in enumerate(prijzen)
    ]


def _accu(inhoud=2.0, **k):
    return W.Accu(inhoud_kwh=inhoud, bruikbaar_kwh=9.8, rendement=0.83, slijtage_eur=0.053, **k)


def test_zonder_eis_niet_vol():
    u = W.plan(_kw([0.40] * 48), _accu())
    assert u.kwartieren[-1]["inhoud_kwh"] < 9.8


def test_eis_vult_de_accu_in_de_goedkoopste_kwartieren():
    prijzen = [0.40] * 12 + [0.30] * 20 + [0.45] * 16
    u = W.plan(_kw(prijzen), _accu(vol_na_kwartier=31))
    assert u.kwartieren[31]["inhoud_kwh"] >= 9.7
    laden = [i for i, r in enumerate(u.kwartieren) if r["actie"] == "laden_net"]
    assert laden and all(12 <= i <= 31 for i in laden)


def test_onhaalbare_eis_laadt_zoveel_als_kan():
    u = W.plan(_kw([0.40] * 8), _accu(0.0, vol_na_kwartier=3))
    assert [r["actie"] for r in u.kwartieren[:4]] == ["laden_net"] * 4
    assert u.kwartieren[3]["inhoud_kwh"] == 2.0


def test_grootste_stap_is_vol_vermogen():
    u = W.plan(_kw([0.15] * 4 + [0.50] * 28), _accu(0.0))
    rij = u.kwartieren[0]
    assert rij["vol_vermogen"] and rij["accu_kwh"] < 0.6


def _c(make_coordinator):
    c = make_coordinator({})
    c.instelling = lambda sleutel, standaard=None: -2400 if "charge" in str(sleutel) else standaard
    return c


def test_vol_vermogen_is_ingesteld_vermogen(make_coordinator):
    c = _c(make_coordinator)
    assert c._waardeplan_laadvermogen_w({"accu_kwh": 0.549, "vol_vermogen": True}) == 2400
    assert c._waardeplan_laadvermogen_w({"accu_kwh": 0.3, "vol_vermogen": False}) == 1200


def test_plan_toont_vermogen_aan_het_net():
    assert planvolging._accu_w({"laden_w": 2400, "inhoud_delta_kwh": 0.5}, None) == -2400
    assert planvolging._accu_w({"inhoud_delta_kwh": -0.2}, None) == 800


def _balans(make_coordinator, nodig=True, ruimte=7.0, zon=False):
    c = _c(make_coordinator)
    c.balanceerlading = lambda now: {"nodig": nodig, "reden": "7 dagen niet vol"}
    c._resterende_laadruimte_kwh = lambda: ruimte
    c._balanceer_zon_vult_vandaag = lambda *a: zon
    return c


def test_niet_nodig_geen_eis(make_coordinator):
    c = _balans(make_coordinator, nodig=False)
    assert c._waardeplan_balanceren(NU, _kw([0.3] * 96), _accu()) == {}


def test_zon_vult_geen_eis(make_coordinator):
    c = _balans(make_coordinator, zon=True)
    assert "kwartier" not in c._waardeplan_balanceren(NU, _kw([0.3] * 96), _accu())


def test_vol_voor_acht_uur_en_blijft_vast(make_coordinator):
    c = _balans(make_coordinator)
    kw = _kw([0.3] * 96)
    uit = c._waardeplan_balanceren(NU, kw, _accu())
    assert uit["kwartier"] == 47  # 20:00 + 12 uur = 08:00
    doel = c._balanceer_doel
    later = NU + timedelta(hours=1)
    c._waardeplan_balanceren(later, _kw([0.3] * 92), _accu())
    assert c._balanceer_doel == doel


def test_niet_haalbaar_de_dag_erna(make_coordinator):
    c = _balans(make_coordinator)
    laat = datetime(2026, 11, 2, 6, 30, tzinfo=TZ)
    kw = [W.Kwartier(laat + timedelta(minutes=15 * i), 0.1, 0.0, 0.3, 0.3) for i in range(120)]
    uit = c._waardeplan_balanceren(laat, kw, _accu(0.0))
    assert c._balanceer_doel.day == 3


def test_prijzen_onbekend_wacht(make_coordinator):
    c = _balans(make_coordinator)
    uit = c._waardeplan_balanceren(NU, _kw([0.3] * 8), _accu())
    assert "kwartier" not in uit and "wacht" in uit["reden"]
