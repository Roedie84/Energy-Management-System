"""v5.160.0 - het waardeplan verkoopt niet onder de verkoopreserve."""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import waardeplan as W

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 2, 18, 0, tzinfo=TZ)


def _kw(prijzen, vloer=0.0, verbruik=0.1):
    return [
        W.Kwartier(NU + timedelta(minutes=15 * i), verbruik, 0.0, p, p, vloer)
        for i, p in enumerate(prijzen)
    ]


def _accu(inhoud):
    return W.Accu(inhoud_kwh=inhoud, bruikbaar_kwh=9.8, rendement=0.83, slijtage_eur=0.05, netladen=False)


PRIJZEN = [0.70] * 4 + [0.20] * 8


def test_zonder_vloer_verkoopt_hij():
    u = W.plan(_kw(PRIJZEN), _accu(1.5))
    assert "verkopen" in [r["actie"] for r in u.kwartieren]


def test_met_vloer_boven_de_inhoud_verkoopt_hij_niet_maar_dekt_het_huis():
    u = W.plan(_kw(PRIJZEN, vloer=2.0), _accu(1.5))
    acties = [r["actie"] for r in u.kwartieren]
    assert "verkopen" not in acties
    assert "huis" in acties[:4]
    assert u.kwartieren[3]["inhoud_kwh"] < 1.5


def test_alleen_wat_boven_de_vloer_zit_gaat_het_net_op():
    u = W.plan(_kw(PRIJZEN, vloer=1.0), _accu(1.5))
    verkocht = [r for r in u.kwartieren if r["actie"] == "verkopen"]
    assert verkocht
    assert all(r["inhoud_kwh"] >= 1.0 - 1e-6 for r in verkocht)


def test_coordinator_geeft_de_reserve_mee(make_coordinator, hass, monkeypatch):
    # v5.198.0: standaard uit (Ruud 09-11); met de vlag aan zoals voorheen.
    import custom_components.energy_management_system.waardeplan_sturing as ws
    monkeypatch.setattr(ws, "WAARDEPLAN_VERKOOPVLOER_RESERVE", True)
    c = make_coordinator({})
    c._segmenten_verbruik_zon = lambda *a, **k: [(0.2, 0.0)]
    c._estimate_pv_kwh_for_period = lambda *a, **k: 0.0
    c._kale_entries = lambda: []
    c._is_salderen_active = lambda b: True
    gezien = []

    def reserve(moment, cache, entries, prijs):
        gezien.append(prijs)
        return 1.25

    c._planning_verkoopreserve_kwh = reserve
    from custom_components.energy_management_system.const import PRICE_SCALE_FACTOR

    entries = [(NU, NU + timedelta(minutes=15), 0.40 * PRICE_SCALE_FACTOR)]
    uit = c._waardeplan_kwartieren(NU - timedelta(minutes=1), entries)
    assert uit[0].verkoop_vloer_kwh == 1.25
    assert abs(gezien[0] - 0.40) < 1e-9
