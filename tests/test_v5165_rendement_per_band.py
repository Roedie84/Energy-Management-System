"""v5.165.0 punt 2 - ontlaadrendement per vermogensband in het waardeplan.

Gemeten: het huis dekken onder 500 W haalt 69 %, verkopen met 2,4 kW veel
meer. Het waardeplan rekende met één rondrit. Nu per stap het rendement van
de band waarin het vermogen valt; zonder banddata het ene getal.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system import waardeplan as W

NU = datetime(2026, 11, 2, 7, 0, tzinfo=timezone.utc)
BANDEN = ((500.0, 0.69), (1500.0, None), (float("inf"), 0.92))


def _kw(prijzen, verbruik=0.1):
    return [W.Kwartier(NU + timedelta(minutes=15 * i), verbruik, 0.0, p, p) for i, p in enumerate(prijzen)]


def test_bandopzoeking_met_terugval():
    accu = W.Accu(inhoud_kwh=0, bruikbaar_kwh=5, ontlaadbanden=BANDEN)
    assert W.ontlaadrendement(400, accu, 0.9) == 0.69
    assert W.ontlaadrendement(1000, accu, 0.9) == 0.9   # band zonder meting
    assert W.ontlaadrendement(2400, accu, 0.9) == 0.92
    assert W.ontlaadrendement(400, W.Accu(inhoud_kwh=0, bruikbaar_kwh=5), 0.9) == 0.9


def test_zonder_banden_dezelfde_stappen_als_voorheen():
    accu = W.Accu(inhoud_kwh=0, bruikbaar_kwh=5, rendement=0.83)
    eta = 0.83 ** 0.5
    s, b = W._ontlaadstappen(accu, eta)
    max_af = int(2.4 * 0.25 / eta / W.STAP_KWH + 1e-9)
    assert list(s) == list(range(-max_af, 0))
    assert b == pytest.approx(s * W.STAP_KWH * eta)


def test_huis_dekken_met_het_rendement_van_de_lage_band():
    prijzen = [0.50] * 8 + [0.20] * 8
    accu = dict(inhoud_kwh=2.0, bruikbaar_kwh=4.0, netladen=False, verkopen=False)
    met = W.plan(_kw(prijzen), W.Accu(**accu, ontlaadbanden=BANDEN))
    huis = [r for r in met.kwartieren if r["actie"] == "huis"]
    assert huis
    for r in huis:
        assert -r.get("accu_stap_kwh", r["accu_kwh"]) / -r["inhoud_delta_kwh"] == pytest.approx(0.69, abs=0.01)  # v5.183.2
    zonder = W.plan(_kw(prijzen), W.Accu(**accu))
    r = next(r for r in zonder.kwartieren if r["actie"] == "huis")
    assert -r.get("accu_stap_kwh", r["accu_kwh"]) / -r["inhoud_delta_kwh"] == pytest.approx(0.83 ** 0.5, abs=0.01)


def test_verkopen_met_het_rendement_van_de_hoge_band():
    prijzen = [0.60] * 4 + [0.20] * 12
    u = W.plan(_kw(prijzen, verbruik=0.0),
               W.Accu(inhoud_kwh=3.0, bruikbaar_kwh=4.0, netladen=False, ontlaadbanden=BANDEN))
    r = next(r for r in u.kwartieren if r["actie"] == "verkopen")
    assert -r["accu_kwh"] / -r["inhoud_delta_kwh"] == pytest.approx(0.92, abs=0.01)
    assert -r["accu_kwh"] <= 2.4 * 0.25 + 1e-9


def test_gemeten_laadrendement():
    accu = W.Accu(inhoud_kwh=0, bruikbaar_kwh=5, rendement=0.83, rendement_laden=0.95)
    laden, ontladen = W.rendementen(accu)
    assert laden == 0.95
    assert ontladen == pytest.approx(0.83 / 0.95)
    assert W.rendementen(W.Accu(inhoud_kwh=0, bruikbaar_kwh=5, rendement=0.81)) == pytest.approx((0.9, 0.9))


def test_snel_genoeg_met_banden():
    import time

    t0 = time.perf_counter()
    W.plan(_kw([0.2 + 0.1 * ((i // 8) % 3) for i in range(144)]),
           W.Accu(inhoud_kwh=4.0, bruikbaar_kwh=9.8, ontlaadbanden=BANDEN))
    assert time.perf_counter() - t0 < 1.0


def test_coordinator_neemt_alleen_betrouwbare_banden(make_coordinator, hass):
    c = make_coordinator({})
    c.laadcorrectie_ct = lambda: 0.0
    c.get_rendement_per_band = lambda now=None: {"ontladen": {
        "<500 W": {"rendement_procent": 69.0, "betrouwbaar": True},
        "500-1500 W": {"rendement_procent": 80.0, "betrouwbaar": False},
        ">1500 W": {"rendement_procent": 91.0, "betrouwbaar": True},
    }}
    banden = c._waardeplan_rendementen(NU)["ontlaadbanden"]
    # v5.213.0: een onbruikbare band neemt het cijfer van de dichtstbijzijnde bruikbare (was: None)
    assert banden == ((500.0, 0.69), (1500.0, 0.69), (float("inf"), 0.91))
    c.get_rendement_per_band = lambda now=None: {"ontladen": {}}
    assert "ontlaadbanden" not in c._waardeplan_rendementen(NU)
