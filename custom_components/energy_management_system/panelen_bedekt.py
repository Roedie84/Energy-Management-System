"""Panelen bedekt door sneeuw of ijs (v5.190.0, L-EMS-072).

Gevraagd 07-11 (rijp op de panelen): kan het EMS zelf zien of de panelen
"schoon" zijn? Niet met de camera (raam, reflecties, schemer), maar met de
eigen heldere-hemel-ijklijn: vriest het, meldt het weer een (vrijwel) heldere
hemel en blijven de panelen ver onder wat een wolkeloze hemel op deze
zonnestand geeft, dan liggen ze vermoedelijk onder sneeuw of ijs.

Zolang dat zo is:
- rekent de zonschatting vooruit met de gemeten verhouding in plaats van met
  Solcast (Solcast weet niets van sneeuw);
- tellen die uren en dagen niet mee in het leren van de zoncorrectie (anders
  wordt de voorspelling na de dooi dagenlang te somber).

Rijp die binnen het uur wegdooit haalt de drempel niet (07-11: 09-10 uur
~0,8 van de ijklijn); dit is voor sneeuw en ijs die blijven liggen.

Alleen pure functies; de coordinator bewaart de toestand (`panelen_bedekt`).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

# Een kandidaat-moment: vorst, heldere lucht en de panelen ver onder de ijklijn.
BEDEKT_HELDERHEID_MAX = 0.35
BEDEKT_BEWOLKING_MAX_PCT = 40.0
# Vorst telt als de buitentemperatuur hieronder kwam, en blijft zo lang gelden
# (sneeuw van gisteravond ligt er vanochtend nog).
BEDEKT_VORST_C = 0.5
BEDEKT_VORST_GELDIG_UREN = 36
# Zo lang achter elkaar kandidaat voordat het telt (rijp is dan meestal weg).
BEDEKT_MIN_MINUTEN = 60
# Vrij: de panelen leveren weer, ongeacht vorst of lucht.
VRIJ_HELDERHEID_MIN = 0.6
VRIJ_MIN_MINUTEN = 15
# Geen bevestiging meer (bewolkt, geen meting): na deze tijd vervalt het.
BEDEKT_VERVAL_UREN = 72
# Factor op de zonvoorspelling zolang bedekt: de gemeten verhouding, begrensd.
BEDEKT_FACTOR_MAX = 0.35
BEDEKT_FACTOR_STANDAARD = 0.1
BEDEKT_UREN_BEWAREN = 72
BEDEKT_DAGEN_BEWAREN = 14


def leeg() -> dict:
    return {
        "bedekt": False, "sinds": None, "kandidaat_sinds": None, "vrij_sinds": None,
        "laatste_bevestiging": None, "vorst_tot": None, "factor": None,
        "uren": [], "dagen": [], "laatste": None, "einde": None,
    }


def _t(waarde) -> datetime | None:
    if not waarde:
        return None
    try:
        return dt_util.parse_datetime(str(waarde))
    except (TypeError, ValueError):
        return None


def _uursleutel(moment: datetime) -> str:
    return dt_util.as_local(moment).strftime("%Y-%m-%dT%H")


def _voeg_toe(reeks: list, waarde: str, max_len: int) -> list:
    reeks = [x for x in (reeks or []) if isinstance(x, str)]
    if waarde not in reeks:
        reeks.append(waarde)
    return reeks[-max_len:]


def stap(
    toestand: dict | None,
    nu: datetime,
    helderheid: float | None,
    bewolking_pct: float | None,
    temp_c: float | None,
    recent: float | None,
) -> dict:
    """Eén ronde. Geeft de nieuwe toestand terug (de oude blijft ongewijzigd)."""
    t = dict(leeg())
    t.update(toestand or {})
    t["uren"] = list(t.get("uren") or [])
    t["dagen"] = list(t.get("dagen") or [])

    if temp_c is not None and temp_c <= BEDEKT_VORST_C:
        t["vorst_tot"] = (nu + timedelta(hours=BEDEKT_VORST_GELDIG_UREN)).isoformat()
    vorst_tot = _t(t.get("vorst_tot"))
    vorst = vorst_tot is not None and nu < vorst_tot
    helder = bewolking_pct is not None and bewolking_pct <= BEDEKT_BEWOLKING_MAX_PCT

    t["laatste"] = {
        "tijd": nu.isoformat(), "helderheid": helderheid, "bewolking_pct": bewolking_pct,
        "temp_c": temp_c, "vorst": vorst, "recent": None if recent is None else round(recent, 3),
    }

    # Verval: te lang geen bevestiging (bewolkt, geen zon).
    if t["bedekt"]:
        bevestigd = _t(t.get("laatste_bevestiging")) or _t(t.get("sinds"))
        if bevestigd is None or nu - bevestigd > timedelta(hours=BEDEKT_VERVAL_UREN):
            return _vrij(t, nu, "verlopen")

    if helderheid is None:
        # Nacht of zon te laag: niets te beoordelen, tellers opnieuw.
        t["kandidaat_sinds"] = None
        t["vrij_sinds"] = None
        return t

    kandidaat = vorst and helder and helderheid < BEDEKT_HELDERHEID_MAX

    if not t["bedekt"]:
        t["vrij_sinds"] = None
        if not kandidaat:
            t["kandidaat_sinds"] = None
            return t
        begin = _t(t.get("kandidaat_sinds")) or nu
        t["kandidaat_sinds"] = begin.isoformat()
        t["uren"] = _voeg_toe(t["uren"], _uursleutel(nu), BEDEKT_UREN_BEWAREN)
        if nu - begin >= timedelta(minutes=BEDEKT_MIN_MINUTEN):
            t["bedekt"] = True
            t["sinds"] = begin.isoformat()
            t["laatste_bevestiging"] = nu.isoformat()
            t["einde"] = None
            t["kandidaat_sinds"] = None
            t["dagen"] = _voeg_toe(
                t["dagen"], dt_util.as_local(begin).date().isoformat(), BEDEKT_DAGEN_BEWAREN
            )
        _werk_factor_bij(t, recent)
        return t

    # Bedekt.
    t["uren"] = _voeg_toe(t["uren"], _uursleutel(nu), BEDEKT_UREN_BEWAREN)
    t["dagen"] = _voeg_toe(t["dagen"], dt_util.as_local(nu).date().isoformat(), BEDEKT_DAGEN_BEWAREN)
    if helderheid >= VRIJ_HELDERHEID_MIN:
        begin = _t(t.get("vrij_sinds")) or nu
        t["vrij_sinds"] = begin.isoformat()
        if nu - begin >= timedelta(minutes=VRIJ_MIN_MINUTEN):
            return _vrij(t, nu, "levert weer")
        return t
    t["vrij_sinds"] = None
    if helder and helderheid < BEDEKT_HELDERHEID_MAX:
        t["laatste_bevestiging"] = nu.isoformat()
    _werk_factor_bij(t, recent)
    return t


def _werk_factor_bij(t: dict, recent: float | None) -> None:
    if recent is not None:
        t["factor"] = round(max(0.0, min(BEDEKT_FACTOR_MAX, float(recent))), 3)


def _vrij(t: dict, nu: datetime, reden: str) -> dict:
    t["bedekt"] = False
    t["kandidaat_sinds"] = None
    t["vrij_sinds"] = None
    t["einde"] = {"tijd": nu.isoformat(), "reden": reden}
    return t


def factor(toestand: dict | None) -> float | None:
    """De factor op de zonvoorspelling, of None als de panelen niet bedekt zijn."""
    if not toestand or not toestand.get("bedekt"):
        return None
    f = toestand.get("factor")
    if f is None:
        return BEDEKT_FACTOR_STANDAARD
    return max(0.0, min(BEDEKT_FACTOR_MAX, float(f)))


def uur_bedekt(toestand: dict | None, moment: datetime) -> bool:
    """Was dit (lokale) uur bedekt of kandidaat? Dan telt het niet mee in het leren."""
    return _uursleutel(moment) in ((toestand or {}).get("uren") or [])


def dag_bedekt(toestand: dict | None, dag) -> bool:
    sleutel = dag.isoformat() if hasattr(dag, "isoformat") else str(dag)
    return sleutel in ((toestand or {}).get("dagen") or [])


def melding(toestand: dict | None) -> str | None:
    """Aandachtspunt zolang de panelen bedekt zijn."""
    if not toestand or not toestand.get("bedekt"):
        return None
    sinds = _t(toestand.get("sinds"))
    wanneer = dt_util.as_local(sinds).strftime("%d-%m %H:%M") if sinds else "onbekend"
    f = factor(toestand)
    return (
        f"Zonnepanelen vermoedelijk bedekt (sneeuw/ijs) sinds {wanneer}: bij vorst en heldere "
        f"lucht leveren ze ver onder de heldere-hemel-lijn. Het EMS rekent vooruit met "
        f"{round((f or 0) * 100)} % van Solcast tot de panelen weer leveren."
    )


def samenvatting(toestand: dict | None) -> dict:
    t = toestand or leeg()
    return {
        "bedekt": bool(t.get("bedekt")),
        "sinds": t.get("sinds"),
        "factor": factor(t),
        "kandidaat_sinds": t.get("kandidaat_sinds"),
        "vrij_sinds": t.get("vrij_sinds"),
        "vorst_tot": t.get("vorst_tot"),
        "laatste": t.get("laatste"),
        "einde": t.get("einde"),
        "dagen_niet_geleerd": list(t.get("dagen") or []),
        "drempels": {
            "helderheid_onder": BEDEKT_HELDERHEID_MAX,
            "bewolking_max_pct": BEDEKT_BEWOLKING_MAX_PCT,
            "vorst_c": BEDEKT_VORST_C,
            "minuten": BEDEKT_MIN_MINUTEN,
            "vrij_helderheid": VRIJ_HELDERHEID_MIN,
        },
        "toelichting": (
            "Vriest het, is de lucht helder en levert de zon minder dan 35 % van de "
            "heldere-hemel-lijn, een uur lang, dan zijn de panelen vermoedelijk bedekt. "
            "Dan rekent de zonschatting met de gemeten verhouding en tellen die uren en "
            "dagen niet mee in het leren. Vrij zodra ze 15 min boven 60 % leveren."
        ),
    }
