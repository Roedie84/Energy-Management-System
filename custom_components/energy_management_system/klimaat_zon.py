"""Zon in de klimaatprojectie (v5.66).

Zelfde opzet als de wind (`klimaat_wind`, v5.64): geen extra dimensie in de
leercellen, maar een correctie erbovenop. Na elke uurmeting met de airco uit
wordt bewaard hoeveel sneller de kamer opwarmde (of trager afkoelde) dan haar
cel gewoonlijk doet, per rolluikstand en zonklasse.

De maat voor de zon is de eigen PV-opbrengst, als deel van het hoogste
vermogen dat de panelen ooit leverden: dat meet de zon op déze plek, met
déze oriëntatie, en is er ook als voorspelling per uur. Bijna geen zon (<5%)
telt niet: dan is er niets te corrigeren.

Om de wind en de zon niet dubbel te tellen: de wind leert alleen in uren
met weinig zon, de zon leert na aftrek van de al geleerde windcorrectie.
"""

from __future__ import annotations

from . import klimaat_wind

ZON_GEEN = 0.05
ZON_ZWAK = 0.30
ZON_MATIG = 0.60
PIEK_SLEUTEL = "_piek_w"
KLASSEN = ("zwak", "matig", "sterk")
ROLLUIKEN = ("beide_open", "gedeeltelijk", "beide_dicht")


def piek(residuen: dict) -> float | None:
    waarde = (residuen or {}).get(PIEK_SLEUTEL)
    try:
        return float(waarde) if waarde else None
    except (TypeError, ValueError):
        return None


def werk_piek_bij(residuen: dict, pv_w) -> None:
    """Het hoogste PV-vermogen dat ooit gemeten is."""
    try:
        w = float(pv_w)
    except (TypeError, ValueError):
        return
    if w > (piek(residuen) or 0.0):
        residuen[PIEK_SLEUTEL] = round(w, 0)


def klasse(pv_w, piek_w) -> str | None:
    """'zwak', 'matig', 'sterk' - of None bij (bijna) geen zon of onbekend."""
    try:
        deel = float(pv_w) / float(piek_w)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if deel < ZON_GEEN:
        return None
    if deel < ZON_ZWAK:
        return "zwak"
    return "matig" if deel < ZON_MATIG else "sterk"


def zonsleutel(rolluik: str | None, pv_w, piek_w) -> str | None:
    k = klasse(pv_w, piek_w)
    if k is None or not rolluik:
        return None
    return f"{rolluik}|{k}"


def correctie(residuen: dict, sleutel: str | None) -> dict:
    return klimaat_wind.correctie(residuen, sleutel)


def overzicht(residuen: dict) -> list[dict]:
    uit = []
    for r in ROLLUIKEN:
        for k in KLASSEN:
            c = correctie(residuen, f"{r}|{k}")
            if c["metingen"]:
                uit.append(
                    {
                        "rolluiken": r,
                        "zon": k,
                        "metingen": c["metingen"],
                        "correctie_c_per_uur": c["c_per_uur"],
                        "betrouwbaar": c["betrouwbaar"],
                    }
                )
    return uit
