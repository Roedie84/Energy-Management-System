"""De zonverwachting van het plan per uur, per dag bewaard (v5.237.0).

Ruud 17-11 ("Wel gaan bewaren voor betere resultaten?"): de dagcontrole
meldde dat de voorspelling waar het plan mee rekent over 10 dagen 9,6 % te
hoog zat en opliep (-1,3 -> -5,5 -> -7,0 -> -9,6 %), maar kon niet zeggen in
welke uren, omdat de plantoetsing alleen het dagtotaal bewaarde.

Alleen meten: de momentopname van 08:00 bewaart de verwachte zon per uur, de
dagteller van de opwek wordt op elke uurgrens genoteerd, en bij het afsluiten
van de dag komen beide naast elkaar. De sturing verandert niet.

Zonder Home Assistant, zodat het los te toetsen is.
"""
from __future__ import annotations

MIN_UUR_KWH = 0.02  # eronder (schemer) zegt een uur niets
MIN_DAGEN = 3       # eronder geen oordeel per uur


def _uur(sleutel) -> int | None:
    try:
        uur = int(sleutel)
    except (TypeError, ValueError):
        return None
    return uur if 0 <= uur <= 23 else None


def _getal(waarde) -> float | None:
    if isinstance(waarde, bool) or not isinstance(waarde, (int, float)):
        return None
    return float(waarde)


def plan_per_uur(rijen) -> dict[str, float]:
    """(uur, kWh) per plankwartier -> kWh per uur van de dag."""
    per_uur: dict[int, float] = {}
    for uur, kwh in rijen or []:
        u, k = _uur(uur), _getal(kwh)
        if u is None or k is None:
            continue
        per_uur[u] = per_uur.get(u, 0.0) + k
    return {str(u): round(k, 3) for u, k in sorted(per_uur.items())}


def noteer_stand(standen, uur, pv_vandaag_kwh) -> dict[str, float]:
    """De dagteller bij het eerste meetmoment van een uur. Een uur dat er al
    staat blijft staan: de stand hoort bij het BEGIN van het uur."""
    nieuw = dict(standen or {})
    u, k = _uur(uur), _getal(pv_vandaag_kwh)
    if u is None or k is None or str(u) in nieuw:
        return nieuw
    nieuw[str(u)] = round(k, 3)
    return nieuw


def vergelijk(voorspeld, standen, opname_uur, pv_bij_opname_kwh, eind_pv_kwh) -> dict:
    """Voorspeld tegen opgewekt per uur, vanaf het uur van de momentopname.

    Het uur van de opname begint bij de stand van de opname (het plan begint
    immers bij 'nu'); het laatste uur eindigt bij de eindstand van de dag. Een
    uur zonder begin- of eindstand (HA lag eruit op de uurgrens) valt weg, net
    als een teller die terugloopt.
    """
    uit: dict[str, dict] = {}
    start = _uur(opname_uur)
    if start is None:
        return uit
    standen = standen or {}
    for sleutel, kwh in sorted((voorspeld or {}).items(), key=lambda x: _uur(x[0]) or 0):
        u, v = _uur(sleutel), _getal(kwh)
        if u is None or v is None or u < start:
            continue
        begin = _getal(pv_bij_opname_kwh) if u == start else _getal(standen.get(str(u)))
        eind = _getal(standen.get(str(u + 1)))
        if eind is None and not any((_uur(s) or 0) > u for s in standen):
            eind = _getal(eind_pv_kwh)  # het laatste gemeten uur van de dag
        if begin is None or eind is None or eind < begin - 0.001:
            continue
        uit[str(u)] = {"voorspeld_kwh": round(v, 3), "werkelijk_kwh": round(max(0.0, eind - begin), 3)}
    return uit


def kwaliteit(geschiedenis, dagen: int = 10) -> dict:
    """Per uur van de dag: voorspeld en opgewekt over de laatste `dagen`
    getoetste dagen die uurcijfers hebben."""
    met = [r for r in geschiedenis or [] if ((r or {}).get("zon") or {}).get("per_uur")]
    met.sort(key=lambda r: str(r.get("datum")))
    met = met[-dagen:]
    if not met:
        return {"beschikbaar": False, "reden": "nog geen dag met uurcijfers (vanaf v5.237.0)"}
    som: dict[int, list] = {}
    for r in met:
        for sleutel, paar in r["zon"]["per_uur"].items():
            u = _uur(sleutel)
            v, w = _getal((paar or {}).get("voorspeld_kwh")), _getal((paar or {}).get("werkelijk_kwh"))
            if u is None or v is None or w is None:
                continue
            s = som.setdefault(u, [0, 0.0, 0.0])
            s[0] += 1
            s[1] += v
            s[2] += w
    uren = {}
    for u, (n, v, w) in sorted(som.items()):
        if max(v, w) < MIN_UUR_KWH * n:
            continue
        uren[str(u)] = {
            "dagen": n,
            "voorspeld_kwh": round(v, 2),
            "werkelijk_kwh": round(w, 2),
            "verschil_kwh": round(w - v, 2),
            "bias_procent": round((w - v) / v * 100, 1) if v > 0 else None,
        }
    oordeel = {u: x for u, x in uren.items() if x["dagen"] >= MIN_DAGEN}
    grootste = max(oordeel, key=lambda u: abs(oordeel[u]["verschil_kwh"]), default=None)
    totaal = sum(x["verschil_kwh"] for x in oordeel.values())
    if grootste is None:
        zin = f"Nog te weinig dagen met uurcijfers ({len(met)}); een oordeel per uur vanaf {MIN_DAGEN} dagen."
    else:
        g = oordeel[grootste]
        aandeel = f" ({abs(g['verschil_kwh']) / abs(totaal) * 100:.0f} % van het totale verschil)" if abs(totaal) > 0.05 and g["verschil_kwh"] * totaal > 0 else ""
        zin = (
            f"Grootste verschil in het uur van {int(grootste):02d}:00: {g['verschil_kwh']:+.2f} kWh over "
            f"{g['dagen']} dagen{aandeel}."
        )
    return {
        "beschikbaar": True, "dagen": len(met), "van": met[0].get("datum"), "tot": met[-1].get("datum"),
        "uren": uren, "grootste_verschil_uur": int(grootste) if grootste is not None else None, "duiding": zin,
    }
