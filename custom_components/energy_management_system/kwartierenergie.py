"""Kwartierenergie uit tellers (v5.28).

Uit de review: "Vermogenssensoren -> realtime context en besturing;
energietellers -> financiële reconstructie en benchmark." Het dagverloop
bewaart per kwartier een momentopname; een kortdurende piek weegt daardoor
te zwaar. Hier: de delta van cumulatieve kWh-tellers tussen twee
kwartiergrenzen.

Kwaliteit per teller en per kwartier:

    measured             beide standen vers (binnen 60 s voor de grens)
    partially_estimated  een stand ouder dan 60 s - wel een echte stand, iets te laat
    estimated            geen teller: geschat uit het accuvermogen
    invalid              teller onbekend, of een reset (de stand ging omlaag)

Er wordt nooit geïnterpoleerd of een waarde verzonnen: een oude stand is een
echte stand, met een lagere kwaliteit.

Zuivere functies, zonder Home Assistant.
"""
from __future__ import annotations

from datetime import datetime

TELLERS = ("grid_import", "grid_export", "pv", "battery_out", "battery_in")
VERS_SECONDEN = 60
_RANG = {"measured": 0, "partially_estimated": 1, "estimated": 2, "invalid": 3}


def stand(waarde, laatst_bijgewerkt: datetime | None, grens: datetime) -> dict:
    """Een tellerstand op een kwartiergrens, met of hij vers is."""
    try:
        getal = float(waarde)
    except (TypeError, ValueError):
        return {"waarde": None, "vers": False}
    vers = (
        laatst_bijgewerkt is not None
        and 0 <= (grens - laatst_bijgewerkt).total_seconds() <= VERS_SECONDEN
    )
    return {"waarde": getal, "vers": vers}


def _delta(begin: dict | None, eind: dict | None) -> tuple[float | None, str]:
    if not begin or not eind or begin.get("waarde") is None or eind.get("waarde") is None:
        return None, "invalid"
    verschil = eind["waarde"] - begin["waarde"]
    if verschil < 0:
        return None, "invalid"  # reset of vervangen teller: geen gemeten waarde
    return verschil, ("measured" if begin.get("vers") and eind.get("vers") else "partially_estimated")


def kwartier(
    start: datetime,
    begin: dict,
    eind: dict,
    prijs_eur: float | None,
    accu_in_geschat_kwh: float | None = None,
) -> dict:
    """Het kwartier van `start` uit de tellerstanden op begin- en eindgrens.

    `accu_in_geschat_kwh` alleen als er geen laadteller is: geschat uit het
    geïntegreerde accuvermogen, gemarkeerd als `estimated`.
    """
    waarden: dict = {}
    kwaliteit: dict = {}
    for teller in TELLERS:
        if teller == "battery_in" and begin.get(teller) is None and eind.get(teller) is None:
            if accu_in_geschat_kwh is not None:
                waarden[teller], kwaliteit[teller] = round(accu_in_geschat_kwh, 4), "estimated"
            else:
                waarden[teller], kwaliteit[teller] = None, "invalid"
            continue
        delta, k = _delta(begin.get(teller), eind.get(teller))
        waarden[teller] = round(delta, 4) if delta is not None else None
        kwaliteit[teller] = k
    huis = None
    if all(waarden[t] is not None for t in TELLERS):
        huis = round(
            waarden["grid_import"] - waarden["grid_export"] + waarden["pv"]
            + waarden["battery_out"] - waarden["battery_in"],
            4,
        )
    totaal = sum(abs(v) for v in waarden.values() if v is not None)
    gemeten = sum(abs(waarden[t]) for t in TELLERS if waarden[t] is not None and kwaliteit[t] == "measured")
    if totaal > 0:
        dekking = round(100 * gemeten / totaal, 1)
    else:
        dekking = 100.0 if all(kwaliteit[t] == "measured" for t in TELLERS) else 0.0
    return {
        "kwartier": start.isoformat(),
        **{f"{t}_kwh": waarden[t] for t in TELLERS},
        "house_kwh": huis,
        "prijs_eur": prijs_eur,
        "kwaliteit_per_teller": kwaliteit,
        "quality": max(kwaliteit.values(), key=lambda k: _RANG[k]),
        "coverage_percent": dekking,
    }


_CODE = {"measured": "m", "partially_estimated": "p", "estimated": "e", "invalid": "x"}
_TERUG = {v: k for k, v in _CODE.items()}
_KORT = {"grid_import": "i", "grid_export": "e", "pv": "p", "battery_out": "o", "battery_in": "c"}


def compact(record: dict) -> dict:
    """Opslagvorm (± 130 bytes): korte sleutels, kwaliteit als code per teller."""
    uit = {"t": record["kwartier"], "h": record["house_kwh"], "pr": record["prijs_eur"],
           "q": "".join(_CODE[record["kwaliteit_per_teller"][t]] for t in TELLERS),
           "cov": record["coverage_percent"]}
    for teller, kort in _KORT.items():
        uit[kort] = record[f"{teller}_kwh"]
    return uit


def uitpakken(kort: dict) -> dict:
    """Terug naar de volledige vorm."""
    kwaliteit = {t: _TERUG[c] for t, c in zip(TELLERS, kort["q"])}
    return {
        "kwartier": kort["t"],
        **{f"{t}_kwh": kort[k] for t, k in _KORT.items()},
        "house_kwh": kort["h"], "prijs_eur": kort["pr"],
        "kwaliteit_per_teller": kwaliteit,
        "quality": max(kwaliteit.values(), key=lambda q: _RANG[q]),
        "coverage_percent": kort["cov"],
    }
