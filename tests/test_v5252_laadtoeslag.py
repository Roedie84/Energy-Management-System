"""v5.252.0: bovenin kost netladen meer stroom.

Dagcontrole 24-11: op 23-11 verkocht de accu 's ochtends voor 46-48 ct en
laadde hij tussen 11:00 en 14:15 voor 38-40 ct weer bij tot 99 %; verlies
EUR 0,06. Het plan rekende met een laadrendement, terwijl de rondrit boven
80 % SoC 82 % is en boven 90 % 78 % (onder 80 %: 85 %).
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import waardeplan as W
from custom_components.energy_management_system.const import WAARDEPLAN_LAADTOESLAG_SOC

NU = datetime(2026, 11, 24, 10, 0, tzinfo=timezone(timedelta(hours=1)))
TOESLAG = ((0.8, 0.045), (0.9, 0.03))


def _kw(prijzen, verbruik=0.3):
    return [W.Kwartier(NU + timedelta(minutes=15 * i), verbruik, 0.0, p, 0.0) for i, p in enumerate(prijzen)]


def _accu(inhoud, **k):
    return W.Accu(inhoud_kwh=inhoud, bruikbaar_kwh=9.8, rendement=0.83, slijtage_eur=0.0,
                  verkopen=False, **k)


def _netlading(u):
    return sum(r["kwh"] for r in u.kwartieren if r["actie"] == "laden_net")


PRIJZEN = [0.40] * 4 + [0.50] * 12


def test_krap_bijladen_bovenin_gebeurt_niet_meer():
    zonder = W.plan(_kw(PRIJZEN), _accu(8.9))
    met = W.plan(_kw(PRIJZEN), _accu(8.9, laadtoeslag=TOESLAG))
    assert _netlading(zonder) > 0.3          # het oude plan vulde de laatste kWh
    assert _netlading(met) == 0.0


def test_onder_de_grens_verandert_er_niets():
    zonder = W.plan(_kw(PRIJZEN), _accu(2.0))
    met = W.plan(_kw(PRIJZEN), _accu(2.0, laadtoeslag=TOESLAG))
    assert _netlading(met) == _netlading(zonder) > 1.0
    assert abs(met.kosten_plan_eur - zonder.kosten_plan_eur) < 1e-6


def test_ruim_verschil_laadt_ook_bovenin_nog():
    ruim = [0.25] * 4 + [0.50] * 12
    met = W.plan(_kw(ruim), _accu(8.9, laadtoeslag=TOESLAG))
    assert _netlading(met) > 0.3


def test_de_grenzen_komen_uit_de_meting():
    assert WAARDEPLAN_LAADTOESLAG_SOC == ((80.0, 0.045), (90.0, 0.03))


def test_soc_grenzen_worden_fracties_van_de_bruikbare_inhoud(make_coordinator, hass):
    c = make_coordinator({})
    c.effective_min_soc_percent = lambda: 10.0
    (f80, t80), (f90, t90) = c._waardeplan_laadtoeslag()
    assert abs(f80 - 70 / 90) < 1e-9 and abs(f90 - 80 / 90) < 1e-9
    assert (t80, t90) == (0.045, 0.03)
