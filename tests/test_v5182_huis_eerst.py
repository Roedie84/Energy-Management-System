"""v5.182.0: woning eerst - de accu verkoopt alleen echt overschot.

Akkoord Ruud 04-11 13:45 ("liever meer voor de woning"). Live 13:38: netladen
om 13:30 voor 37 ct, verkopen 18:45-20:15 voor ~50 ct, daarna 21:00-24:00 het
huis op het net met de accu op 40 % voor een verkoop de volgende ochtend.
"""
from datetime import datetime, timedelta

from custom_components.energy_management_system import waardeplan as W

T0 = datetime(2026, 11, 4, 13, 30)
# (prijs ct, zon W, huis W) per kwartier, naar de planrijen van 04-11 13:38
DAG = (
    [(37.2, 650, 840), (36.1, 650, 850), (36.7, 580, 620), (37.2, 580, 620), (39.9, 480, 620),
     (41.4, 480, 620), (37.8, 410, 760), (41.0, 410, 760), (44.4, 300, 760), (46.7, 300, 760),
     (44.2, 120, 800), (47.2, 120, 800), (49.4, 20, 800), (50.6, 20, 800), (46.8, 0, 1220),
     (49.4, 0, 1220), (50.1, 0, 1220), (50.9, 0, 1220)]
    + [(49.8, 0, 680)] * 8 + [(47.6, 0, 600)]
    + [(45.0, 0, 640)] * 8 + [(40.0, 0, 300)] * 8
    + [(36.5, 0, 220)] * 24          # nacht, goedkoop
    + [(49.5, 0, 290)] * 4           # ochtendpiek
)


def _kwartieren():
    uit = []
    for i, (p, z, h) in enumerate(DAG):
        uit.append(W.Kwartier(begin=T0 + timedelta(minutes=15 * i), verbruik_kwh=h / 4000,
                              zon_kwh=z / 4000, inkoop_eur=p / 100, teruglever_eur=p / 100 + 0.02))
    return uit


def _accu(huis_eerst):
    return W.Accu(inhoud_kwh=3.0, bruikbaar_kwh=7.7, rendement=0.832, slijtage_eur=0.0422,
                  verkoopmarge_eur=0.05, min_actie_w=200, min_laad_w=500, huis_eerst=huis_eerst)


def _netladen_voor_verkoop(rijen):
    gezien = False
    for r in rijen:
        if r["actie"] == "laden_net":
            gezien = True
        if r["actie"] == "verkopen" and gezien:
            return True
    return False


def test_huis_eerst_geen_verkoop_van_netlading_en_huis_gedekt():
    k = _kwartieren()
    res = W.plan(k, _accu(True))
    assert res.beschikbaar
    rijen = res.kwartieren
    assert not _netladen_voor_verkoop(rijen)
    assert W.verkopen_voor_huis(rijen, k, _accu(True)) == []


def test_huis_eerst_meer_accu_naar_het_huis():
    k = _kwartieren()
    zonder = W.plan(k, _accu(False)).kwartieren
    met = W.plan(k, _accu(True)).kwartieren
    huis = lambda rijen: sum(r["accu_kwh"] for r in rijen if r["actie"] == "huis")  # noqa: E731
    verkocht = lambda rijen: sum(-r["accu_kwh"] for r in rijen if r["actie"] == "verkopen")  # noqa: E731
    assert verkocht(met) <= verkocht(zonder) + 1e-9
    assert -huis(met) >= -huis(zonder) - 1e-9


def test_regel_zelf():
    k = _kwartieren()[14:18]   # 1,2 kW huis, geen zon
    acc = _accu(True)
    rijen = [
        {"actie": "laden_net", "accu_kwh": 0.6, "inhoud_kwh": 3.5},
        {"actie": "verkopen", "accu_kwh": -0.3, "inhoud_kwh": 3.2},
        {"actie": "huis", "accu_kwh": -0.2, "inhoud_kwh": 3.0},
        {"actie": "houden", "accu_kwh": 0.0, "inhoud_kwh": 3.0},
    ]
    assert W.verkopen_voor_huis(rijen, k, acc) == [1]          # lading uit het net
    rijen[0] = {"actie": "huis", "accu_kwh": -0.2, "inhoud_kwh": 0.3}
    rijen[1] = {"actie": "verkopen", "accu_kwh": -0.3, "inhoud_kwh": 0.05}
    assert W.verkopen_voor_huis(rijen, k, acc) == [1]          # huis daarna niet gedekt
    rijen[1] = {"actie": "verkopen", "accu_kwh": -0.3, "inhoud_kwh": 3.0}
    assert W.verkopen_voor_huis(rijen, k, acc) == []           # echt overschot


def test_sturing_zet_hem_aan():
    from custom_components.energy_management_system.const import WAARDEPLAN_HUIS_EERST
    from pathlib import Path
    import custom_components.energy_management_system as pkg
    assert WAARDEPLAN_HUIS_EERST is True
    code = (Path(pkg.__file__).parent / "waardeplan_sturing.py").read_text(encoding="utf-8")
    assert "huis_eerst=WAARDEPLAN_HUIS_EERST" in code



def test_accukosten_slijtage_bij_opstarten():
    """Live 04-11 13:38: na de herstart een kwartier 'slijtage 0,0 ct' in de cockpit."""
    from pathlib import Path
    import custom_components.energy_management_system as pkg
    code = (Path(pkg.__file__).parent / "coordinator.py").read_text(encoding="utf-8")
    deel = code.split("    def get_accukosten(", 1)[1].split("\n    def ", 1)[0]
    assert "WAARDEPLAN_SLIJTAGE_TERUGVAL_CT if slijtage is None else slijtage" in deel
    assert "if slijtage is not None:\n            self._accukosten_cache" in deel
