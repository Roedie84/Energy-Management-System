"""Wind in de klimaatprojectie (v5.64).

Gevraagd: "Ook de windrichting is denk ik van belang?" Ja: een harde, koude
wind op de gevel koelt het huis sneller af dan dezelfde buitentemperatuur
zonder wind, en hoe hard hangt af van de kant waar hij op staat.

Geen extra dimensie in de leercellen van de projectie - die zijn er al 252
en de meeste hebben nog weinig metingen. In plaats daarvan een correctie
erbovenop: na elke uurmeting (airco uit) wat de kamer ANDERS deed dan haar
cel normaal doet, apart bewaard per windrichting (8) en windklasse (matig,
hard). Windstil telt niet: dan is er niets te corrigeren.

Pas vanaf `WIND_MIN_METINGEN` metingen per richting en klasse gaat de
correctie in de indicatieve reeks mee, vanaf `WIND_BETROUWBAAR_METINGEN`
ook in de strenge. Tot die tijd rekent de projectie zoals voorheen.
"""

from __future__ import annotations

import statistics

WIND_KALM_KMH = 10.0
WIND_HARD_KMH = 25.0
WIND_MIN_METINGEN = 5
WIND_BETROUWBAAR_METINGEN = 15
WIND_HISTORIE = 20

RICHTINGEN = [
    "noord", "noordoost", "oost", "zuidoost",
    "zuid", "zuidwest", "west", "noordwest",
]

_NAAR_KMH = {
    "km/h": 1.0,
    "m/s": 3.6,
    "mph": 1.609344,
    "kn": 1.852,
    "kt": 1.852,
    "ft/s": 1.09728,
}


def naar_kmh(snelheid, eenheid: str | None) -> float | None:
    """Windsnelheid in km/h; onbekende eenheid geldt als km/h (de HA-standaard)."""
    try:
        waarde = float(snelheid)
    except (TypeError, ValueError):
        return None
    if waarde < 0:
        return None
    return waarde * _NAAR_KMH.get(str(eenheid or "km/h").strip().lower(), 1.0)


def richting(graden) -> str | None:
    try:
        g = float(graden)
    except (TypeError, ValueError):
        return None
    return RICHTINGEN[int((g % 360 + 22.5) // 45) % 8]


def klasse(kmh: float | None) -> str | None:
    if kmh is None or kmh < WIND_KALM_KMH:
        return None
    return "hard" if kmh >= WIND_HARD_KMH else "matig"


def windsleutel(kmh: float | None, graden) -> str | None:
    """'zuidwest|hard', of None bij windstil of een ontbrekende meting."""
    k = klasse(kmh)
    r = richting(graden)
    if k is None or r is None:
        return None
    return f"{r}|{k}"


def wind_label(kmh: float | None, graden) -> str | None:
    r = richting(graden)
    if kmh is None:
        return None
    if r is None or kmh < 1:
        return f"{kmh:.0f} km/h"
    return f"{r} {kmh:.0f} km/h"


def uit_attributen(attributen) -> tuple[float | None, float | None]:
    """(km/h, graden) uit de attributen van een weerentiteit."""
    attributen = attributen or {}
    kmh = naar_kmh(attributen.get("wind_speed"), attributen.get("wind_speed_unit"))
    try:
        graden = float(attributen.get("wind_bearing"))
    except (TypeError, ValueError):
        graden = None
    return kmh, graden


def leer_residu(residuen: dict, sleutel: str | None, residu: float) -> bool:
    """Bewaar één afwijking (°C/uur) onder deze wind. Waar als bewaard."""
    if sleutel is None or residu is None:
        return False
    reeks = list(residuen.get(sleutel) or [])
    reeks.append(round(float(residu), 3))
    residuen[sleutel] = reeks[-WIND_HISTORIE:]
    return True


def correctie(residuen: dict, sleutel: str | None) -> dict:
    """De geleerde windcorrectie voor deze wind (°C/uur, mediaan)."""
    reeks = list((residuen or {}).get(sleutel) or []) if sleutel else []
    if len(reeks) < WIND_MIN_METINGEN:
        return {"c_per_uur": None, "metingen": len(reeks), "betrouwbaar": False}
    return {
        "c_per_uur": round(statistics.median(reeks), 3),
        "metingen": len(reeks),
        "betrouwbaar": len(reeks) >= WIND_BETROUWBAAR_METINGEN,
    }


def overzicht(residuen: dict) -> list[dict]:
    """Per richting en klasse wat er geleerd is - voor het dashboard."""
    uit = []
    for r in RICHTINGEN:
        for k in ("matig", "hard"):
            c = correctie(residuen, f"{r}|{k}")
            uit.append(
                {
                    "richting": r,
                    "klasse": k,
                    "metingen": c["metingen"],
                    "correctie_c_per_uur": c["c_per_uur"],
                    "betrouwbaar": c["betrouwbaar"],
                }
            )
    return uit
