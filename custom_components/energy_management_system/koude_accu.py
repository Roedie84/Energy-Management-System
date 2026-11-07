"""Laden bij koude accu (v5.191.0, L-EMS-073).

Gevraagd 07-11: de AB3000-modules warmen zich bij zeer koud weer eerst op
voordat ze laden. Het waardeplan rekende met het volle laadvermogen; een
laadblok kwam dan later op gang en de accu was voor het dure blok minder vol
dan gepland. Akkoord Ruud 07-11 10:33: het laadplan vervroegen bij ~0 °C.

- Meten: per kwartier waarin het plan uit het net laadt en de koudste cel
  rond het vriespunt zit (of een module verwarmt): hoeveel er echt geladen
  werd tegenover de opdracht. Plus de verwarmingsperiodes (heat_state).
- Plannen: zolang de cellen zo koud zijn rekent het plan de komende uren met
  dat deel van het laadvermogen (geleerd, eerst 50 %). Het plan begint dan
  vanzelf eerder of laadt langer.

Alleen pure functies; de coordinator bewaart de toestand (`koude_laden`).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median

from homeassistant.util import dt as dt_util

#: Koudste cel op of onder deze temperatuur = laden kan vertraagd zijn.
KOUD_LADEN_C = 1.0
#: Zo ver vooruit geldt de lagere laadfactor (cellen koelen/warmen langzaam).
KOUD_HORIZON_UREN = 12
#: Laadfactor zonder metingen.
KOUD_FACTOR_STANDAARD = 0.5
KOUD_FACTOR_MIN = 0.2
KOUD_FACTOR_MAX = 1.0
#: Pas vanaf zoveel gemeten koude laadkwartieren telt de geleerde factor.
KOUD_MIN_METINGEN = 4
KOUD_METINGEN_BEWAREN = 20
KOUD_EPISODES_BEWAREN = 20
#: Een kwartier telt als meting vanaf deze gevraagde lading (kWh).
KOUD_MIN_GEVRAAGD_KWH = 0.1
#: Langere gaten tussen rondes tellen niet mee in de optelling.
KOUD_MAX_STAP_S = 180


def leeg() -> dict:
    return {"metingen": [], "episodes": [], "lopend": None, "verwarmen_sinds": None,
            "laatste_tijd": None, "laatste": None}


def _t(waarde) -> datetime | None:
    if not waarde:
        return None
    try:
        return dt_util.parse_datetime(str(waarde))
    except (TypeError, ValueError):
        return None


def _kwartier(moment: datetime) -> datetime:
    return moment.replace(minute=moment.minute - moment.minute % 15, second=0, microsecond=0)


def is_koud(koudste_c: float | None, verwarmt: bool) -> bool:
    return bool(verwarmt) or (koudste_c is not None and koudste_c <= KOUD_LADEN_C)


def stap(
    toestand: dict | None,
    nu: datetime,
    koudste_c: float | None,
    verwarmt: bool,
    gevraagd_w: float,
    geladen_w: float,
) -> dict:
    """Eén ronde. `gevraagd_w`: de laadopdracht uit het net (0 als het plan
    niet laadt); `geladen_w`: het gemeten laadvermogen (>= 0)."""
    t = dict(leeg())
    t.update(toestand or {})
    t["metingen"] = list(t.get("metingen") or [])
    t["episodes"] = list(t.get("episodes") or [])
    koud = is_koud(koudste_c, verwarmt)

    # Verwarmingsperiodes.
    sinds = _t(t.get("verwarmen_sinds"))
    if verwarmt and sinds is None:
        t["verwarmen_sinds"] = nu.isoformat()
        t["verwarmen_temp_c"] = koudste_c
    elif not verwarmt and sinds is not None:
        t["episodes"].append({
            "begin": sinds.isoformat(), "eind": nu.isoformat(),
            "minuten": round((nu - sinds).total_seconds() / 60, 1),
            "temp_c": t.get("verwarmen_temp_c"),
        })
        t["episodes"] = t["episodes"][-KOUD_EPISODES_BEWAREN:]
        t["verwarmen_sinds"] = None

    # Kwartiermeting.
    kw = _kwartier(nu)
    lopend = t.get("lopend")
    if lopend and lopend.get("kwartier") != kw.isoformat():
        if lopend.get("koud") and lopend.get("gevraagd_kwh", 0.0) >= KOUD_MIN_GEVRAAGD_KWH:
            verhouding = lopend.get("geladen_kwh", 0.0) / lopend["gevraagd_kwh"]
            t["metingen"].append(round(max(0.0, min(1.2, verhouding)), 3))
            t["metingen"] = t["metingen"][-KOUD_METINGEN_BEWAREN:]
        lopend = None
    if lopend is None:
        lopend = {"kwartier": kw.isoformat(), "gevraagd_kwh": 0.0, "geladen_kwh": 0.0, "koud": False}
    vorige = _t(t.get("laatste_tijd"))
    if vorige is not None:
        dt_s = (nu - vorige).total_seconds()
        if 0 < dt_s <= KOUD_MAX_STAP_S and gevraagd_w > 0:
            lopend["gevraagd_kwh"] = lopend["gevraagd_kwh"] + gevraagd_w * dt_s / 3.6e6
            lopend["geladen_kwh"] = (
                lopend["geladen_kwh"] + max(0.0, min(geladen_w, gevraagd_w * 1.2)) * dt_s / 3.6e6
            )
            lopend["koud"] = lopend["koud"] or koud
    t["lopend"] = lopend
    t["laatste_tijd"] = nu.isoformat()
    t["laatste"] = {"tijd": nu.isoformat(), "koudste_c": koudste_c, "verwarmt": bool(verwarmt),
                    "gevraagd_w": round(gevraagd_w), "geladen_w": round(geladen_w)}
    return t


def geleerde_factor(toestand: dict | None) -> float | None:
    metingen = (toestand or {}).get("metingen") or []
    if len(metingen) < KOUD_MIN_METINGEN:
        return None
    return max(KOUD_FACTOR_MIN, min(KOUD_FACTOR_MAX, median(metingen)))


def factor(toestand: dict | None, koudste_c: float | None, verwarmt: bool) -> float:
    """De laadfactor voor de komende uren: 1,0 als de cellen niet koud zijn."""
    if not is_koud(koudste_c, verwarmt):
        return 1.0
    geleerd = geleerde_factor(toestand)
    return KOUD_FACTOR_STANDAARD if geleerd is None else geleerd


def pas_toe(kwartieren: list, nu: datetime, f: float) -> int:
    """Zet `laad_factor` op de kwartieren binnen de horizon; geeft het aantal terug."""
    if f >= 1.0:
        return 0
    grens = nu + timedelta(hours=KOUD_HORIZON_UREN)
    n = 0
    for k in kwartieren:
        begin = getattr(k, "begin", None)
        if hasattr(begin, "tzinfo") and begin < grens:
            k.laad_factor = f
            n += 1
    return n


def samenvatting(toestand: dict | None, koudste_c: float | None, verwarmt: bool) -> dict:
    t = toestand or leeg()
    f = factor(t, koudste_c, verwarmt)
    episodes = t.get("episodes") or []
    return {
        "koud": is_koud(koudste_c, verwarmt),
        "koudste_cel_c": koudste_c,
        "verwarmt": bool(verwarmt),
        "laadfactor": f,
        "geleerde_factor": geleerde_factor(t),
        "metingen": len(t.get("metingen") or []),
        "metingen_nodig": KOUD_MIN_METINGEN,
        "verwarmingen": len(episodes),
        "laatste_verwarming": episodes[-1] if episodes else None,
        "grens_c": KOUD_LADEN_C,
        "toelichting": (
            f"Is de koudste cel {KOUD_LADEN_C:g} °C of kouder (of verwarmt een module), dan "
            f"rekent het laadplan de komende {KOUD_HORIZON_UREN} uur met {round(f * 100)} % van "
            "het laadvermogen en begint het zo eerder. Gemeten per kwartier dat het plan dan "
            f"uit het net laadt; vanaf {KOUD_MIN_METINGEN} metingen telt het geleerde deel."
        ),
    }
