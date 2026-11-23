"""Tweede prijsbron (v5.251.0): EnergyZero als reserve voor Zonneplan.

Ruud 23-11 (akkoord op punt 1): Zonneplan gaf die ochtend een serverfout
(500) en de prijssensor viel weg. Het EMS rekende verder met de bewaarde
reeks, maar die reikt hooguit tot middernacht; duurt een storing tot na de
publicatie van de prijzen van morgen, dan plant het EMS blind.

EnergyZero (ingebouwde HA-integratie, geen account) geeft dezelfde
beursprijs per kwartier. Het verschil met Zonneplan is vrijwel vast
(opslag en energiebelasting, incl. btw): dat leert het EMS uit de
kwartieren waarvoor beide bronnen een prijs hebben (mediaan). Pas met
genoeg kwartieren (OPSLAG_MIN) wordt de reserve gebruikt.

Zuivere functies; de lijm staat in `reserveprijs_sturing.py`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import median

#: Zonneplan geeft bedragen in 1e-7 euro per kWh.
ZONNEPLAN_SCHAAL = 10_000_000
#: Zoveel kwartierverschillen worden bewaard (een week).
OPSLAG_BEWAARD = 672
#: Onder dit aantal geen reserve: de opslag is dan nog niet betrouwbaar.
OPSLAG_MIN = 96
_KWARTIER = timedelta(minutes=15)


def _tijd(waarde) -> datetime | None:
    if isinstance(waarde, datetime):
        t = waarde
    else:
        try:
            t = datetime.fromisoformat(str(waarde).replace(" ", "T", 1))
        except (TypeError, ValueError):
            return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _sleutel(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")


def lees_energyzero(antwoord) -> list[dict]:
    """Het antwoord van `energyzero.get_energy_prices` als
    [{"start", "eind", "prijs"}] (UTC-iso, euro per kWh incl. btw)."""
    uit = []
    for p in (antwoord or {}).get("prices") or []:
        begin, eind = _tijd(p.get("start") or p.get("timestamp")), _tijd(p.get("end"))
        try:
            prijs = float(p.get("price"))
        except (TypeError, ValueError):
            continue
        if begin is None or eind is None or eind <= begin:
            continue
        uit.append({"start": begin.astimezone(timezone.utc).isoformat(),
                    "eind": eind.astimezone(timezone.utc).isoformat(), "prijs": prijs})
    uit.sort(key=lambda r: r["start"])
    return uit


def _bedrag(item: dict, veld: str) -> float | None:
    waarde = item.get(veld)
    if isinstance(waarde, dict):
        waarde = waarde.get("amount")
    try:
        return float(waarde) / ZONNEPLAN_SCHAAL
    except (TypeError, ValueError):
        return None


def leer_verschillen(verschillen: dict | None, zonneplan: list, reserve: list) -> dict:
    """Per kwartier het verschil Zonneplan - EnergyZero (incl. en excl.
    belasting); geeft de bijgewerkte, ingekorte verzameling terug."""
    uit = dict(verschillen or {})
    per_kwartier = {}
    for r in reserve or []:
        begin, eind = _tijd(r["start"]), _tijd(r["eind"])
        # een uurprijs geldt voor de vier kwartieren erin
        while begin is not None and eind is not None and begin < eind:
            per_kwartier[_sleutel(begin)] = r["prijs"]
            begin = begin + _KWARTIER
    for item in zonneplan or []:
        if not isinstance(item, dict):
            continue
        begin = _tijd(item.get("start_date"))
        if begin is None:
            continue
        ez = per_kwartier.get(_sleutel(begin))
        incl, excl = _bedrag(item, "price_tax_included"), _bedrag(item, "price_tax_excluded")
        if ez is None or incl is None:
            continue
        uit[_sleutel(begin)] = [round(incl - ez, 5), round(excl - ez, 5) if excl is not None else None]
    for oud in sorted(uit)[:-OPSLAG_BEWAARD]:
        del uit[oud]
    return uit


def opslag(verschillen: dict | None) -> dict | None:
    """De geleerde opslag (mediaan), of None met te weinig kwartieren."""
    rijen = list((verschillen or {}).values())
    if len(rijen) < OPSLAG_MIN:
        return None
    excl = [r[1] for r in rijen if r[1] is not None]
    return {"incl_eur": round(median(r[0] for r in rijen), 5),
            "excl_eur": round(median(excl), 5) if excl else None,
            "kwartieren": len(rijen)}


def als_zonneplan(reserve: list, geleerd: dict, na: datetime | None = None) -> list[dict]:
    """De reserveprijzen in het formaat van de Zonneplan-forecast, per
    kwartier, vanaf `na` (UTC)."""
    uit = []
    for r in reserve or []:
        begin, eind = _tijd(r["start"]), _tijd(r["eind"])
        while begin is not None and eind is not None and begin < eind:
            volgende = begin + _KWARTIER
            if na is None or volgende > na:
                incl = r["prijs"] + geleerd["incl_eur"]
                item = {"start_date": begin.isoformat(), "end_date": volgende.isoformat(),
                        "price_tax_included": {"amount": round(incl * ZONNEPLAN_SCHAAL)},
                        "bron": "energyzero"}
                if geleerd.get("excl_eur") is not None:
                    item["price_tax_excluded"] = {
                        "amount": round((r["prijs"] + geleerd["excl_eur"]) * ZONNEPLAN_SCHAAL)}
                uit.append(item)
            begin = volgende
    return uit


def vul_aan(reeks: list, reserve_items: list) -> list:
    """`reeks` aangevuld met de reservekwartieren die na zijn laatste
    kwartier beginnen."""
    if not reserve_items:
        return list(reeks or [])
    eind = None
    for item in reeks or []:
        t = _tijd(item.get("end_date")) if isinstance(item, dict) else None
        if t is not None and (eind is None or t > eind):
            eind = t
    erbij = [i for i in reserve_items if eind is None or _tijd(i["start_date"]) >= eind]
    return list(reeks or []) + erbij
