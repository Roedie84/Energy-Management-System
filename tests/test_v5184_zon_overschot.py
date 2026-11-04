"""v5.184.0: zon alleen terugleveren als het echt overschot is.

Akkoord Ruud 04-11 15:56. Live 15:54: 05-11 09:30-10:45 zon terug voor
39-43 ct en om 11:45 bijladen uit het net voor 37 ct; de accu kwam niet
verder dan ~70 % en was om 21:30 leeg.
"""
from datetime import datetime, timedelta

from custom_components.energy_management_system import waardeplan as W
from tests.test_v5183_2_dekking_en_status import OCHTEND


def _plan(huis_eerst):
    t0 = datetime(2026, 11, 5, 4, 0)
    kw = [W.Kwartier(t0 + timedelta(minutes=15 * i), h / 4000, z / 4000, (p - 11) / 100, (p - 9) / 100,
                     prijs_incl_eur=p / 100) for i, (p, z, h) in enumerate(OCHTEND)]
    acc = W.Accu(inhoud_kwh=0.05, bruikbaar_kwh=7.78, rendement=0.834, slijtage_eur=0.0422,
                 verkoopmarge_eur=0.05, min_actie_w=200, min_laad_w=500, huis_eerst=huis_eerst,
                 eindprijs_eur=0.40, bewaarmarge_eur=0.05, bewaarkost_eur_per_kwh_uur=0.002,
                 zon_export_afdwingbaar=True)
    return W.plan(kw, acc).kwartieren, acc


def test_geen_zon_terug_als_de_accu_niet_vol_raakt():
    zonder, _ = _plan(False)
    assert any(r["actie"] == "zon_export" for r in zonder)   # 09:30 en 10:00, zoals live
    rijen, acc = _plan(True)
    assert W.zon_export_zonder_overschot(rijen, acc) == []
    for t, r in enumerate(rijen):
        if r["actie"] == "zon_export":
            assert any(x["inhoud_kwh"] >= acc.bruikbaar_kwh - 0.1 for x in rijen[t:])


def test_regel_zelf():
    acc = W.Accu(inhoud_kwh=1.0, bruikbaar_kwh=2.0)
    rijen = [{"actie": "zon_export", "inhoud_kwh": 1.0, "net_kwh": -0.2, "accu_kwh": 0.0},
             {"actie": "laden_net", "inhoud_kwh": 1.5, "net_kwh": 0.6, "accu_kwh": 0.6}]
    assert W.zon_export_zonder_overschot(rijen, acc) == [0]
    rijen[1] = {"actie": "zon", "inhoud_kwh": 2.0, "net_kwh": 0.0, "accu_kwh": 0.3}
    assert W.zon_export_zonder_overschot(rijen, acc) == []    # raakt toch vol: echt overschot
