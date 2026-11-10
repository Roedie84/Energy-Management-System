"""v5.205.0: bewaarmarge en bewaarkost op 0.

Ruud 10-11 13:34: "economisch het beste doen voor mij", na de doorrekening van
31-10 t/m 09-11 (claude/ems-analyse-10-11.md): de planner van v5.204 nagespeeld
op de kwartiertellers kostte EUR 22,18 met de marges, EUR 20,97 zonder.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import const as C
from custom_components.energy_management_system import waardeplan as W

T = datetime(2026, 11, 10, 15, 0, tzinfo=timezone(timedelta(hours=1)))


def _kw(prijzen):
    return [W.Kwartier(T + timedelta(minutes=15 * i), 0.2, 0.0, p, p + 0.02) for i, p in enumerate(prijzen)]


def _accu(**kw):
    basis = dict(inhoud_kwh=0.8, bruikbaar_kwh=7.7, rendement=0.84, slijtage_eur=0.0422,
                 verkopen=False, netladen=False, eindprijs_eur=0.20)
    basis.update(kw)
    return W.Accu(**basis)


def test_constanten_nul():
    assert C.WAARDEPLAN_BEWAARMARGE_EUR == 0.0
    assert C.WAARDEPLAN_BEWAARKOST_EUR_PER_KWH_UUR == 0.0


def test_bewaart_voor_drie_cent_meer():
    """Vier kwartieren van 40 ct, dan vier van 43 ct, inhoud voor vier: zonder
    marge gaat de lading naar de 43 ct; met 5 ct marge ging ze meteen op."""
    k = _kw([0.40] * 4 + [0.43] * 4)
    zonder = W.plan(k, _accu(bewaarmarge_eur=C.WAARDEPLAN_BEWAARMARGE_EUR,
                             bewaarkost_eur_per_kwh_uur=C.WAARDEPLAN_BEWAARKOST_EUR_PER_KWH_UUR)).kwartieren
    met = W.plan(k, _accu(bewaarmarge_eur=0.05, bewaarkost_eur_per_kwh_uur=0.002)).kwartieren
    assert [r["actie"] for r in zonder[:4]] == ["houden"] * 4
    assert sum(-r["accu_kwh"] for r in zonder[4:]) > 0.7
    assert met[0]["actie"] == "huis"


def test_plan_zonder_marges_niet_duurder():
    """Op echte kosten (zonder de rekenmarges) is het plan zonder marge nooit duurder."""
    k = _kw([0.33, 0.33, 0.36, 0.36, 0.41, 0.45, 0.44, 0.38, 0.35, 0.34, 0.47, 0.46])

    def echt(rijen):
        return sum(r["net_kwh"] * kw.inkoop_eur + max(-r["accu_kwh"], 0) * 0.0422 for r, kw in zip(rijen, k))

    nul = W.plan(k, _accu(inhoud_kwh=1.2)).kwartieren
    marge = W.plan(k, _accu(inhoud_kwh=1.2, bewaarmarge_eur=0.05, bewaarkost_eur_per_kwh_uur=0.002)).kwartieren
    assert echt(nul) <= echt(marge) + 1e-6
