"""v5.198.0: economisch het voordeligst (Ruud 09-11 11:41).

"Je moet doen wat economisch voor mij het voordeligste is, ik wil zo weinig
mogelijk betalen" - akkoord op: verkoopmarge 2 ct (optie), huis-eerst uit,
en "het huis gaat voor" loslaten (geen huisreserve als verkoopvloer). Het plan
verkoopt dus ook wat het huis later nodig heeft als terugkopen goedkoper is.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import waardeplan as W
from custom_components.energy_management_system.const import (
    WAARDEPLAN_HUIS_EERST,
    WAARDEPLAN_VERKOOPVLOER_RESERVE,
)

T0 = datetime(2026, 11, 9, 17, 0, tzinfo=timezone(timedelta(hours=1)))


def test_vlaggen_uit():
    assert WAARDEPLAN_HUIS_EERST is False and WAARDEPLAN_VERKOOPVLOER_RESERVE is False


def _plan(huis_eerst):
    # 17-19 u duur (85 ct), daarna 's nachts goedkoop (40 ct); accu vol, huis 0,25 kWh/kw
    ks = [W.Kwartier(T0 + timedelta(minutes=15 * i), 0.25, 0.0,
                     0.85 if i < 8 else 0.40, 0.85 if i < 8 else 0.40) for i in range(48)]
    accu = W.Accu(inhoud_kwh=7.0, bruikbaar_kwh=7.5, laden_kw=2.4, rendement=0.84,
                  slijtage_eur=0.042, verkoopmarge_eur=0.02, huis_eerst=huis_eerst)
    return W.plan(ks, accu)


def test_verkoopt_meer_als_terugkopen_goedkoper_is():
    met, zonder = _plan(True), _plan(False)
    verkocht = lambda r: sum(-(x.get("net_kwh") or 0) for x in r.kwartieren if x.get("actie") == "verkopen")
    assert verkocht(zonder) >= verkocht(met)
    assert zonder.kosten_plan_eur <= met.kosten_plan_eur + 1e-9
