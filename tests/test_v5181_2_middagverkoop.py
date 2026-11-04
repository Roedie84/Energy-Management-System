"""v5.181.2 (g) - geen verkoop op het goedkoopste moment die de zon meteen weer bijvult.

Live 04-11 12:01 (waardeplan van 12:00, saldering met overschot: rekenprijs =
prijs - 11,08 ct belastingdeel, teruglever = rekenprijs + 2 ct premie; zon
terugleveren geweigerd door de huis-eerst-regel):
    12:00 37,6 ct  verkopen 0,209 kWh, net -0,529 (zon 1685 W, huis 406 W)
    12:15 37,3 ct  zon laden 0,321 kWh (-1283 W)
    ... 's avonds ~50 ct.
Verkopen op 26,6+2 ct en bijvullen met zon die 26-30 ct aan teruglevering had
opgebracht kost rondrit, slijtage en marge: nooit doen.
"""
import math
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import waardeplan as W

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 4, 12, 0, tzinfo=TZ)
BELASTING = 0.1108

# (prijs incl., zon kWh, huis kWh) per kwartier vanaf 12:00, uit de live rijen
LIVE = [
    (0.3763, 0.421, 0.1015), (0.3727, 0.422, 0.10), (0.3702, 0.272, 0.10), (0.3728, 0.272, 0.10),
    (0.3707, 0.175, 0.10), (0.3657, 0.175, 0.10), (0.3719, 0.106, 0.10), (0.3607, 0.106, 0.10),
    (0.3673, 0.141, 0.10), (0.3725, 0.141, 0.10), (0.3990, 0.102, 0.10), (0.4135, 0.102, 0.10),
    (0.3781, 0.027, 0.10), (0.4100, 0.027, 0.10), (0.4435, 0.0, 0.119), (0.4670, 0.0, 0.118),
    (0.4417, 0.0, 0.179), (0.4722, 0.0, 0.18), (0.4936, 0.0, 0.198), (0.5059, 0.0, 0.198),
    (0.4679, 0.0, 0.308), (0.4940, 0.0, 0.308), (0.5007, 0.0, 0.308), (0.5087, 0.0, 0.308),
]


def kwartieren():
    rijen = list(LIVE)
    for i in range(24, 48):   # 18:00-24:00
        t = NU + timedelta(minutes=15 * i)
        rijen.append((0.50 if t.hour < 19 or (t.hour == 19 and t.minute < 30) else 0.42, 0.0, 0.15))
    uit = []
    for i, (p, zon, huis) in enumerate(rijen):
        reken = p - BELASTING
        vloer = 1.3 if i < 13 else 7.78
        uit.append(W.Kwartier(NU + timedelta(minutes=15 * i), huis, zon, reken, reken + 0.02, vloer,
                              prijs_incl_eur=p))
    return uit


def accu(verkopen_bij_zon=True):
    return W.Accu(
        inhoud_kwh=2.25, bruikbaar_kwh=7.78, laden_kw=2.4, ontladen_kw=2.4, rendement=0.835,
        slijtage_eur=0.0422, verkoopmarge_eur=0.02, netlaadmarge_eur=0.0475,
        rendement_laden=0.835, rendement_ontladen=1.0,
        ontlaadbanden=((500, 0.993), (1500, 1.043), (math.inf, None)),
        min_actie_w=400.0, min_laad_w=500.0, zon_export_afdwingbaar=False, eindprijs_eur=0.32,
        verkopen_bij_zon=verkopen_bij_zon,
    )


def _acties(res, n=6):
    return [r["actie"] for r in res.kwartieren[:n]]


def test_reproductie_zonder_de_reparatie():
    """Het oude plan (geen toets, verkopen met zon toegestaan) verkoopt om 12:00."""
    oud = W._plan(kwartieren(), accu())
    assert oud.kwartieren[0]["actie"] == "verkopen"
    assert "zon" in _acties(oud)[1:]
    assert W.zinloze_verkopen(oud.kwartieren, kwartieren(), accu()) == [0]


def test_de_toets_verbiedt_de_middagverkoop():
    res = W.plan(kwartieren(), accu())
    assert "verkopen" not in [r["actie"] for r in res.kwartieren[:16]]
    assert res.kwartieren[0]["actie"] in ("zon", "houden")
    # wat overblijft is altijd economisch: geen enkele verkoop die later duurder bijvult
    assert W.zinloze_verkopen(res.kwartieren, kwartieren(), accu()) == []


def test_huis_eerst_verbiedt_verkopen_met_zon():
    res = W._plan(kwartieren(), accu(verkopen_bij_zon=False))
    zon = kwartieren()
    for r, k in zip(res.kwartieren, zon):
        if k.zon_kwh > k.verbruik_kwh + W.EPS_KWH:
            assert r["accu_kwh"] >= 0, r


def test_verkoop_met_zon_telt_als_terugleveren_voor_huis_eerst():
    rijen = [
        {"actie": "verkopen", "net_kwh": -0.529, "accu_kwh": -0.209, "inhoud_kwh": 2.0},
        {"actie": "huis", "net_kwh": 0.3, "accu_kwh": -0.2, "inhoud_kwh": 0.0},
    ]
    assert W.zon_export_laat_huis_tekort(rijen) is True
    # een verkoop zonder zon (net = accu) telt niet
    rijen[0]["net_kwh"] = -0.209
    assert W.zon_export_laat_huis_tekort(rijen) is False


def test_avondverkoop_blijft():
    """Verkopen op de dure avond zonder duurder bijvullen erna blijft staan."""
    kw = [W.Kwartier(NU + timedelta(minutes=15 * i), 0.1, 0.0, p, p, 0.0)
          for i, p in enumerate([0.70] * 4 + [0.20] * 8)]
    a = W.Accu(inhoud_kwh=1.5, bruikbaar_kwh=9.8, rendement=0.83, slijtage_eur=0.05, netladen=False)
    res = W.plan(kw, a)
    assert "verkopen" in _acties(res, 4)


def test_coordinator_zet_verkopen_bij_zon_uit_bij_huis_eerst(make_coordinator):
    c = make_coordinator({})

    class Res:
        def __init__(self, rijen):
            self.beschikbaar, self.kwartieren = True, rijen

    a = accu()
    a.zon_export_afdwingbaar = True
    eerst = Res([{"actie": "zon_export", "net_kwh": -0.2, "accu_kwh": 0.0, "inhoud_kwh": 0.5},
                 {"actie": "huis", "net_kwh": 0.3, "accu_kwh": -0.2, "inhoud_kwh": 0.0}])
    gezien = {}

    def plan(kw, acc):
        gezien["bij_zon"] = acc.verkopen_bij_zon
        return Res([])

    import custom_components.energy_management_system.waardeplan as wp
    oud = wp.plan
    wp.plan = plan
    try:
        c._waardeplan_huis_eerst([], a, eerst)
    finally:
        wp.plan = oud
    assert gezien["bij_zon"] is False and a.zon_export_afdwingbaar is False
