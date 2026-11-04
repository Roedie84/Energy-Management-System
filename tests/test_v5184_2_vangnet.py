"""v5.184.2: vangnet - past geen enkele stap in de regels, dan zonder de dekregels.

Akkoord Ruud 04-11 16:58. Bij de kookfout (16:45) bleef er geen ontlaadstap
over en koos het plan stil 'houden' (keuze 0, kosten oneindig).
"""
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import waardeplan as W

T0 = datetime(2026, 11, 4, 17, 0)


def test_vangnet_vult_een_onmogelijk_kwartier_en_meldt_het(monkeypatch):
    # v5.186.0: het oude geval (dekken bij een grens van 0,3 kW) is nu gewoon te
    # plannen: de slimme stand dekt exact wat het vermogen toelaat (0,075 kWh).
    kw = [W.Kwartier(T0 + timedelta(minutes=15 * i), 0.3, 0.0, 0.40, 0.42, dekken=(i == 0)) for i in range(8)]
    acc = W.Accu(inhoud_kwh=1.0, bruikbaar_kwh=4.0, ontladen_kw=0.3, netladen=False, verkopen=False)
    res = W.plan(kw, acc)
    assert res.beschikbaar and not res.kwartieren[0].get("vangnet")
    assert res.kwartieren[0]["actie"] == "huis" and abs(res.kwartieren[0]["accu_kwh"] + 0.075) < 1e-6
    # het vangnet zelf: past er streng geen enkele actie (hier de slimme stand
    # kunstmatig uitgezet), dan zonder de dekregel en gemeld
    echt = W._Kw.evalueer

    def zonder_slim(self, j, accu, e, waarde, raster, cap, eta_l, streng=True):
        kosten, b, e2 = echt(self, j, accu, e, waarde, raster, cap, eta_l, streng)
        if streng and self.k.dekken and j == self.i_slim:
            kosten = np.full(np.shape(e), np.inf)
        return kosten, b, e2

    monkeypatch.setattr(W._Kw, "evalueer", zonder_slim)
    res = W.plan(kw, acc)
    assert res.beschikbaar
    assert res.kwartieren[0].get("vangnet") is True
    assert np.isfinite(res.kosten_plan_eur)


def test_normaal_geen_vangnet():
    kw = [W.Kwartier(T0 + timedelta(minutes=15 * i), 0.17, 0.0, 0.40, 0.42) for i in range(8)]
    res = W.plan(kw, W.Accu(inhoud_kwh=1.0, bruikbaar_kwh=4.0))
    assert not any(r.get("vangnet") for r in res.kwartieren)


def test_sturing_meldt_en_telt():
    code = (Path(pkg.__file__).parent / "waardeplan_sturing.py").read_text(encoding="utf-8")
    assert '"vangnet_kwartieren": sum(1 for r in res.kwartieren if r.get("vangnet"))' in code
    assert "gekozen zonder de dekregels (vangnet)" in code
