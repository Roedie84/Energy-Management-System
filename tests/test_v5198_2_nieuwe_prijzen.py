"""v5.198.2: nieuwe prijzen = meteen een nieuw waardeplan.

09-11 13:22 (Ruud: "zon laden midden in de nacht?"): de prijzen van morgen
kwamen midden in het kwartier; het plan van dat kwartier liep tot 23:45 en de
planning toonde vanaf 00:00 de oude regels met een andere laadstand (16 % ->
32 % in een kwartier, als 'zon laden' 5,7 kW).
"""
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=1))
NU = datetime(2026, 11, 9, 13, 22, tzinfo=TZ)


def _entries(tot_uur):
    begin = NU.replace(minute=15, second=0, microsecond=0)
    uit, t = [], begin
    while t < tot_uur:
        uit.append((t, t + timedelta(minutes=15), 40.0))
        t += timedelta(minutes=15)
    return uit


def test_plan_onthoudt_tot_wanneer_de_prijzen_liepen(make_coordinator):
    c = make_coordinator({})
    vandaag = _entries(NU.replace(hour=0, minute=0) + timedelta(days=1))
    plan = c._waardeplan_bewaar(NU, "k", {"beschikbaar": True}, vandaag)
    assert plan["prijzen_tot"] == vandaag[-1][1].isoformat()
    assert c._nieuwe_prijzen(NU, plan, vandaag) is False
    morgen = _entries(NU.replace(hour=0, minute=0) + timedelta(days=2))
    assert c._nieuwe_prijzen(NU, plan, morgen) is True
    assert c.waardeplan_herplanningen["nieuwe_prijzen"] == 1


def test_cache_wordt_overgeslagen_bij_nieuwe_prijzen(make_coordinator):
    c = make_coordinator({})
    vandaag = _entries(NU.replace(hour=0, minute=0) + timedelta(days=1))
    morgen = _entries(NU.replace(hour=0, minute=0) + timedelta(days=2))
    oud = {"beschikbaar": True, "prijzen_tot": vandaag[-1][1].isoformat()}
    c._waardeplan_uit_cache = lambda now: ("k", oud)
    gerekend = []
    c.bereken_waardeplan = lambda now, e: gerekend.append(len(e)) or {"beschikbaar": True}
    assert c._waardeplan_nu(NU, vandaag) is oud
    c._waardeplan_nu(NU, morgen)
    assert gerekend == [len(morgen)]
