"""v5.163.0: balanceren uit het net alleen onder 22 ct (besluit Ruud 02-11)."""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import waardeplan as W

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 2, 20, 0, tzinfo=TZ)


def _kw(prijzen):
    return [
        W.Kwartier(NU + timedelta(minutes=15 * i), 0.1, 0.0, p, p)
        for i, p in enumerate(prijzen)
    ]


def _accu():
    return W.Accu(inhoud_kwh=2.0, bruikbaar_kwh=9.8, rendement=0.83, slijtage_eur=0.053)


def _c(make_coordinator):
    c = make_coordinator({})
    c.instelling = lambda sleutel, standaard=None: -2400 if "charge" in str(sleutel) else standaard
    c.balanceerlading = lambda now: {"nodig": True, "reden": "7 dagen niet vol"}
    c._resterende_laadruimte_kwh = lambda: 7.0
    c._balanceer_zon_vult_vandaag = lambda *a: False
    return c


def test_boven_de_grens_geen_eis(make_coordinator):
    c = _c(make_coordinator)
    uit = c._waardeplan_balanceren(NU, _kw([0.393] * 96), _accu())
    assert "kwartier" not in uit and "onder 22 ct" in uit["reden"]
    assert c._balanceer_doel is None


def test_precies_op_de_grens_telt_niet(make_coordinator):
    c = _c(make_coordinator)
    assert "kwartier" not in c._waardeplan_balanceren(NU, _kw([0.22] * 96), _accu())


def test_te_weinig_goedkope_kwartieren_geen_eis(make_coordinator):
    c = _c(make_coordinator)
    uit = c._waardeplan_balanceren(NU, _kw([0.15] * 4 + [0.40] * 92), _accu())
    assert "kwartier" not in uit


def test_genoeg_goedkope_kwartieren_wel_en_het_plan_blijft_eronder(make_coordinator):
    c = _c(make_coordinator)
    prijzen = [0.40] * 12 + [0.20] * 24 + [0.45] * 60
    kw, accu = _kw(prijzen), _accu()
    uit = c._waardeplan_balanceren(NU, kw, accu)
    assert uit["kwartier"] == 47
    accu.vol_na_kwartier = uit["kwartier"]
    rijen = W.plan(kw, accu).kwartieren
    assert rijen[47]["inhoud_kwh"] >= 9.7
    laden = [r for r in rijen[:48] if r["actie"] == "laden_net"]
    assert laden and all(r["prijs_eur"] < 0.22 for r in laden)


def test_oude_regel_niet_boven_de_grens(make_coordinator, monkeypatch):
    c = _c(make_coordinator)
    monkeypatch.setattr(c, "_goedkoopste_laadmomenten", lambda *a, **k: True)
    monkeypatch.setattr(c, "beschikbare_energie_kwh", lambda: 2.0)
    eind = NU + timedelta(hours=2)
    assert c._balanceer_laadbesluit(NU, eind, 0.22, 2.0) is None
    assert c._balanceer_laadbesluit(NU, eind, 0.219, 2.0)["soort"] == "balanceren"
