"""v5.183.0: bewaarmarge, onzekerheid vooruit en de datacorrectie alleen uit het waardeplan.

Akkoord Ruud 04-11 14:04 (punten 1-3). Live 14:01: 1,9 kWh bleef van 18:00
tot 05:30 in de accu (huis op het net, 37-50 ct) voor morgenavond (55 ct).
"""
from datetime import datetime, timedelta
from pathlib import Path

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import accukosten as A
from custom_components.energy_management_system import waardeplan as W

T0 = datetime(2026, 11, 4, 18, 0)
# vanavond 50 ct, nacht 37 ct (2 kwartier laden mogelijk), morgenavond 55 ct
REEKS = ([(50.0, 680)] * 12 + [(40.0, 300)] * 20 + [(35.0, 220)] * 2 + [(38.0, 220)] * 30
         + [(55.0, 1000)] * 12)


def _kw():
    return [W.Kwartier(begin=T0 + timedelta(minutes=15 * i), verbruik_kwh=h / 4000, zon_kwh=0.0,
                       inkoop_eur=p / 100, teruglever_eur=p / 100 + 0.02)
            for i, (p, h) in enumerate(REEKS)]


def _accu(**extra):
    return W.Accu(inhoud_kwh=1.9, bruikbaar_kwh=7.7, rendement=0.834, slijtage_eur=0.0422,
                  verkoopmarge_eur=0.05, netlaadmarge_eur=0.05, min_actie_w=200, min_laad_w=500,
                  huis_eerst=True, eindprijs_eur=0.40, **extra)


def _eerste_huis_uit_accu(rijen):
    return sum(-r["accu_kwh"] for r in rijen[:12] if r["actie"] == "huis")


def test_zonder_marge_bewaart_voor_morgen_met_marge_naar_het_huis():
    k = _kw()
    zonder = W.plan(k, _accu()).kwartieren
    met = W.plan(k, _accu(bewaarmarge_eur=0.05, bewaarkost_eur_per_kwh_uur=0.002)).kwartieren
    assert _eerste_huis_uit_accu(met) > _eerste_huis_uit_accu(zonder) + 0.5


def test_groot_voordeel_mag_wel_bewaren():
    # vanavond 30 ct, morgenavond 55 ct: 25 ct voordeel, bewaren blijft
    k = [W.Kwartier(begin=T0 + timedelta(minutes=15 * i), verbruik_kwh=0.17, zon_kwh=0.0,
                    inkoop_eur=(0.30 if i < 12 else 0.55), teruglever_eur=(0.32 if i < 12 else 0.57))
         for i in range(24)]
    rijen = W.plan(k, _accu(bewaarmarge_eur=0.05)).kwartieren
    assert _eerste_huis_uit_accu(rijen) < 0.2


def test_te_duur_bewaard_regel():
    k = _kw()[:3]
    acc = _accu(bewaarmarge_eur=0.05)
    rijen = [{"actie": "houden", "net_kwh": 0.17, "inhoud_kwh": 1.9, "accu_kwh": 0.0},
             {"actie": "houden", "net_kwh": 0.17, "inhoud_kwh": 1.9, "accu_kwh": 0.0},
             {"actie": "huis", "net_kwh": 0.0, "inhoud_kwh": 1.7, "accu_kwh": -0.17}]
    assert W.te_duur_bewaard(rijen, k, acc) == [0, 1]      # later ook 50 ct: geen voordeel
    assert W.te_duur_bewaard(rijen, k, _accu()) == []        # marge uit


def test_sturing_en_constanten():
    from custom_components.energy_management_system import const as C
    assert C.WAARDEPLAN_BEWAARMARGE_EUR == 0.05
    assert C.WAARDEPLAN_BEWAARKOST_EUR_PER_KWH_UUR == 0.002
    code = (Path(pkg.__file__).parent / "waardeplan_sturing.py").read_text(encoding="utf-8")
    assert "bewaarmarge_eur=WAARDEPLAN_BEWAARMARGE_EUR" in code


def test_datacorrectie_alleen_waardeplan():
    assert A._laadverwachting({"reden": "cheap_block", "laad_waarde_ct": 40}) is None
    assert A._laadverwachting({"reden": "waardeplan_laden", "laad_waarde_ct": 40}) is None
    assert A._laadverwachting({"reden": "waardeplan_laden", "laad_waarde_bron": "waardeplan",
                               "laad_waarde_ct": 40}) == 40
