"""v5.181.2 - verkopen in de duurste kwartieren eerst (één vloer langs het plan)."""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import waardeplan as W

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 4, 16, 45, tzinfo=TZ)
VERBRUIK = 0.15
# Avondprijzen: duurste eerst, daarna net iets goedkoper; dan het goedkope blok.
PRIJZEN = [0.509, 0.506, 0.500, 0.498, 0.497, 0.496, 0.495, 0.495] + [0.20] * 8
BLOK = 8


def _vloer_oud(i):
    """De oude vloer: huisbehoefte tot het blok x (1 + marge) - groter vooraan."""
    if i >= BLOK:
        return 0.3
    rest = (BLOK - i) * VERBRUIK
    return 0.3 + rest * 1.6


def _kw():
    return [
        W.Kwartier(NU + timedelta(minutes=15 * i), VERBRUIK, 0.0, p, p, _vloer_oud(i))
        for i, p in enumerate(PRIJZEN)
    ]


def _accu():
    # net boven de oude vloer van het eerste kwartier (2,22 kWh)
    return W.Accu(inhoud_kwh=2.3, bruikbaar_kwh=4.0, laden_kw=2.0, ontladen_kw=2.0,
                  rendement=0.85, slijtage_eur=0.02, netladen=False)


def test_vloer_zakt_precies_met_het_huisverbruik():
    kw = W.vloeren_gelijktrekken(_kw(), bodem_kwh=0.3)
    # het anker (laatste kwartier voor het blok) houdt zijn vloer met marge
    assert kw[BLOK - 1].verkoop_vloer_kwh == _vloer_oud(BLOK - 1)
    for a, b in zip(kw[:BLOK - 1], kw[1:BLOK]):
        assert abs((a.verkoop_vloer_kwh - b.verkoop_vloer_kwh) - VERBRUIK) < 1e-9
    for i, k in enumerate(kw):
        # nooit hoger dan de oude vloer, het huis tot het blok blijft beschermd
        assert k.verkoop_vloer_kwh <= _vloer_oud(i) + 1e-9
        if i < BLOK:
            assert k.verkoop_vloer_kwh >= (BLOK - i) * VERBRUIK + 0.3 - 1e-9
    assert all(k.verkoop_vloer_kwh == 0.3 for k in kw[BLOK:])


def test_anker_bij_de_bodem_en_stijgende_vloer_blijft():
    kw = [W.Kwartier(NU + timedelta(minutes=15 * i), 0.5, 0.0, 0.3, 0.3, v)
          for i, v in enumerate([3.0, 1.0, 2.0, 1.2, 0.2, 0.2])]
    uit = W.vloeren_gelijktrekken(kw, bodem_kwh=0.2)
    assert [round(k.verkoop_vloer_kwh, 3) for k in uit] == [1.5, 1.0, 1.7, 1.2, 0.2, 0.2]
    nul = W.vloeren_gelijktrekken([W.Kwartier(NU, 0.1, 0.0, 0.3, 0.3, 0.0)] * 3, 0.2)
    assert all(k.verkoop_vloer_kwh == 0.0 for k in nul)


def _verkocht(rijen):
    """kWh het net op per kwartier (0 als het kwartier niet verkoopt)."""
    return [r["kwh"] if r["actie"] == "verkopen" else 0.0 for r in rijen]


def test_oude_vloer_schuift_de_verkoop_naar_later():
    """Het probleem van 04-11: het duurste kwartier dekt alleen het huis."""
    u = W.plan(_kw(), _accu())
    assert u.kwartieren[0]["actie"] in ("huis", "houden")   # v5.183.2: volle dekking of bewaren
    assert sum(_verkocht(u.kwartieren[1:BLOK])) > 0


def test_verkoopt_in_de_duurste_kwartieren_eerst():
    oud = W.plan(_kw(), _accu())
    kw = W.vloeren_gelijktrekken(_kw(), bodem_kwh=0.3)
    u = W.plan(kw, _accu())
    rijen = u.kwartieren[:BLOK]
    verkocht = _verkocht(rijen)
    # het duurste kwartier verkoopt nu, en het meest
    assert rijen[0]["actie"] == "verkopen"
    assert verkocht[0] == max(verkocht) and verkocht[0] > 0.2
    # de twee duurste kwartieren samen verkopen meer dan alle goedkopere erna
    assert verkocht[0] + verkocht[1] > sum(verkocht[2:])
    # en niet minder in totaal dan het oude plan (binnen een stap)
    assert sum(verkocht) >= sum(_verkocht(oud.kwartieren[:BLOK])) - 0.1
    # de vloer van elk verkoopkwartier is gerespecteerd
    for r, k in zip(rijen, kw):
        if r["actie"] == "verkopen":
            assert r["inhoud_kwh"] >= k.verkoop_vloer_kwh - 1e-6
    # het huis tot het blok blijft gedekt: bij het blok staat er nog
    # minstens de vloer van het anker min zijn eigen kwartier in
    assert u.kwartieren[BLOK - 1]["inhoud_kwh"] >= kw[BLOK - 1].verkoop_vloer_kwh - VERBRUIK / 0.9
