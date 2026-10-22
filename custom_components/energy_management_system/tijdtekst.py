"""Een tijdstip als tekst, met de dag erbij als het niet vandaag is (v5.118.0).

Gemeld 22-10 16:49 (cockpit, apparaten): "Liever wachten tot 21:15 - Nu
EUR 0,39, vanaf 21:15 gem. EUR 0,24." Dat 21:15 was MORGEN; dat stond er
niet bij. Vandaag blijft alleen de tijd, morgen "morgen 21:15", gisteren
"gisteren 21:15", verder weg de weekdag ("vr 21:15") en meer dan een week
weg de datum ("30-10 21:15").
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.util import dt as dt_util

WEEKDAGEN = ("ma", "di", "wo", "do", "vr", "za", "zo")


def _lokaal(moment: datetime) -> datetime:
    return dt_util.as_local(moment) if moment.tzinfo else moment


def dag_label(dag: date, vandaag: date) -> str:
    """"" voor vandaag, anders "morgen ", "gisteren ", "vr " of "30-10 "."""
    verschil = (dag - vandaag).days
    if verschil == 0:
        return ""
    if verschil == 1:
        return "morgen "
    if verschil == -1:
        return "gisteren "
    if -7 < verschil < 7:
        return f"{WEEKDAGEN[dag.weekday()]} "
    return f"{dag:%d-%m} "


def tijd_met_dag(
    moment: datetime | None,
    nu: datetime | None = None,
    eind: bool = False,
    vandaag: date | None = None,
) -> str:
    """"21:15", "morgen 21:15" of "vr 21:15".

    `eind`: een eindtijd van 00:00 hoort bij de dag die dan afloopt
    ("24:00", v5.31.3).
    """
    if moment is None:
        return "-"
    lokaal = _lokaal(moment)
    if vandaag is None:
        vandaag = _lokaal(nu or dt_util.now()).date()
    dag = lokaal.date()
    tekst = lokaal.strftime("%H:%M")
    if eind and tekst == "00:00":
        dag = dag - timedelta(days=1)
        tekst = "24:00"
    return dag_label(dag, vandaag) + tekst


def periode_met_dag(
    van: datetime, tot: datetime, nu: datetime | None = None
) -> str:
    """"21:15-23:00", "morgen 21:15-23:00"; de eindtijd krijgt alleen een
    eigen dag als die anders is dan die van het begin."""
    vandaag = _lokaal(nu or dt_util.now()).date()
    begin = tijd_met_dag(van, vandaag=vandaag)
    eind_dag = tijd_met_dag(tot, eind=True, vandaag=_lokaal(van).date())
    return f"{begin}-{eind_dag}"
