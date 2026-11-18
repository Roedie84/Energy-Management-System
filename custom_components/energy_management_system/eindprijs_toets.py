"""Toets van de eindprijs: wat het plan voor de uren na de horizon aannam
tegen wat het werd (v5.239.0). Alleen meten.

Ruud 18-11 ("Dus het is gebaseerd op de hoge verwachte prijzen van vrijdag?"
- "Hoe goed is het eigen prijsmodel?"): het waardeplan waardeert wat aan het
eind in de accu zit tegen het 75e percentiel van de prijsverwachting over de
uren direct na de horizon. Of die aanname klopt werd nergens bijgehouden. Nu:
eens per dag de aanname vastleggen en afsluiten zodra de echte prijzen van
die uren er zijn.

Zonder Home Assistant.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

BEWAAR_DAGEN = 45
MIN_DAGEN = 5


def p75(prijzen) -> float | None:
    """Het 75e percentiel zoals `_waardeplan_eindprijs` het neemt."""
    reeks = sorted(float(p) for p in prijzen if isinstance(p, (int, float)) and not isinstance(p, bool))
    if len(reeks) < 4:
        return None
    return reeks[min(len(reeks) - 1, int(round(0.75 * (len(reeks) - 1))))]


def uur_sleutel(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")


def noteer(staat, datum: str, van: datetime, tot: datetime, verwacht_eur) -> dict:
    """De aanname van vandaag (eens per datum; de eerste blijft staan)."""
    nieuw = {"open": list((staat or {}).get("open") or []), "klaar": list((staat or {}).get("klaar") or [])}
    if not isinstance(verwacht_eur, (int, float)) or isinstance(verwacht_eur, bool):
        return nieuw
    if any(r.get("datum") == datum for r in nieuw["open"] + nieuw["klaar"]):
        return nieuw
    nieuw["open"].append({"datum": datum, "van": van.astimezone(timezone.utc).isoformat(),
                          "tot": tot.astimezone(timezone.utc).isoformat(), "verwacht_eur": round(float(verwacht_eur), 4)})
    return nieuw


def uurprijzen(kwartieren) -> dict[str, float]:
    """(begin, prijs incl. belasting) per kwartier -> gemiddelde per vol UTC-uur."""
    som: dict[str, list] = {}
    for begin, prijs in kwartieren or []:
        if begin is None or not isinstance(prijs, (int, float)) or isinstance(prijs, bool):
            continue
        s = som.setdefault(uur_sleutel(begin), [0.0, 0])
        s[0] += float(prijs)
        s[1] += 1
    return {k: v[0] / v[1] for k, v in som.items() if v[1] >= 4}


def sluit(staat, prijzen_per_uur: dict, nu: datetime) -> dict:
    """Sluit elke open aanname af waarvan alle uren een echte prijs hebben;
    wat te oud wordt zonder prijzen vervalt."""
    nieuw = {"open": [], "klaar": list((staat or {}).get("klaar") or [])}
    for r in (staat or {}).get("open") or []:
        try:
            van, tot = datetime.fromisoformat(r["van"]), datetime.fromisoformat(r["tot"])
        except (KeyError, TypeError, ValueError):
            continue
        uren, t = [], van
        while t < tot:
            uren.append(prijzen_per_uur.get(uur_sleutel(t)))
            t += timedelta(hours=1)
        if uren and all(u is not None for u in uren):
            echt = p75(uren)
            if echt is not None:
                nieuw["klaar"].append({"datum": r["datum"], "verwacht_eur": r["verwacht_eur"],
                                       "echt_eur": round(echt, 4)})
                continue
        if nu - tot <= timedelta(days=3):
            nieuw["open"].append(r)
    nieuw["klaar"] = sorted(nieuw["klaar"], key=lambda r: str(r.get("datum")))[-BEWAAR_DAGEN:]
    return nieuw


def overzicht(staat) -> dict:
    klaar = [r for r in (staat or {}).get("klaar") or []
             if isinstance(r.get("verwacht_eur"), (int, float)) and isinstance(r.get("echt_eur"), (int, float))]
    if not klaar:
        return {"dagen": 0, "open": len((staat or {}).get("open") or []),
                "duiding": "Nog geen afgesloten dag (vanaf v5.239.0)."}
    verschil = [(r["verwacht_eur"] - r["echt_eur"]) * 100 for r in klaar]
    gem = sum(verschil) / len(verschil)
    fout = sum(abs(v) for v in verschil) / len(verschil)
    te_hoog = sum(1 for v in verschil if v > 0)
    if len(klaar) < MIN_DAGEN:
        zin = f"{len(klaar)} dag(en) gemeten; een oordeel vanaf {MIN_DAGEN}."
    else:
        zin = (f"De aangenomen eindprijs lag over {len(klaar)} dagen gemiddeld {gem:+.1f} ct naast de echte "
               f"(gemiddeld {fout:.1f} ct ernaast, {te_hoog} keer te hoog).")
    return {
        "dagen": len(klaar), "open": len((staat or {}).get("open") or []),
        "gemiddeld_verschil_ct": round(gem, 2), "gemiddelde_fout_ct": round(fout, 2), "te_hoog_dagen": te_hoog,
        "laatste": [{"datum": r["datum"], "verwacht_ct": round(r["verwacht_eur"] * 100, 1),
                     "echt_ct": round(r["echt_eur"] * 100, 1)} for r in klaar[-7:]],
        "duiding": zin,
    }
