"""Grootverbruikers herkennen aan hun eigen vermogensmeting (v5.31, schaduw).

Gevraagd: "Ik wil dat het EMS aan de hand van vermogensmetingen definieert of
iets een grootverbruiker is of niet, buiten de door mij aangegeven
grootverbruikers om." En daarna: "Alleen apparaten met een eigen
vermogensmeting."

Tot nu toe is een grootverbruiker alleen wat in de vaste lijst staat
(vaatwasser, wasmachine, Quooker, airco, slaapkamer, oven, kookplaat). Een
ander zwaar apparaat ziet het EMS als "het huis verbruikt ineens meer".

Deze module leert per apparaat met een eigen meting:
- wanneer het een keer gebruikt wordt: minstens MIN_MINUTEN boven DREMPEL_W;
- hoe lang zo'n keer duurt en hoeveel energie hij kost (mediaan);
- en deelt het daarmee in: kortlopend (één cyclus met bekende energie) of
  aanhoudend (verwarmt of koelt urenlang, zoals de airco).

SCHADUW: dit stuurt niets. Het laat zien wat het EMS zou doen. Pas na
bewijs gaat het meetellen; de eigen lijst blijft altijd gelden.
"""
from __future__ import annotations

from datetime import datetime
from statistics import median

DREMPEL_W = 1000.0
# Korter is een piek (een waterkoker die aanslaat), geen gebruik.
MIN_MINUTEN = 3.0
# Zo lang onder de drempel = klaar. Overbrugt de thermostaatpauzes van een
# oven of een droger, die anders als losse keren zouden tellen.
EINDE_NA_MINUTEN = 10.0
# Een meetgat langer dan dit telt niet als verbruik.
MAX_STAP_MINUTEN = 10.0
KORTLOPEND_TOT_MINUTEN = 90.0
MIN_KEREN = 3
HISTORIE = 20


def _tijd(tekst: str | None) -> datetime | None:
    if not tekst:
        return None
    try:
        return datetime.fromisoformat(tekst)
    except (TypeError, ValueError):
        return None


def _minuten(van: datetime, tot: datetime) -> float:
    return (tot - van).total_seconds() / 60


def werk_bij(
    leer: dict, entiteit: str, naam: str, vermogen_w: float | None, nu: datetime
) -> None:
    """Eén meting verwerken. `leer` wordt ter plekke bijgewerkt.

    Een apparaat komt pas in `leer` als het één keer boven de drempel kwam:
    een lamp van 8 W hoeft niet onthouden te worden.
    """
    staat = leer.get(entiteit)
    boven = vermogen_w is not None and vermogen_w >= DREMPEL_W
    if staat is None:
        if not boven:
            return
        staat = leer[entiteit] = {"naam": naam, "duren_min": [], "energie_kwh": [], "piek_w": []}
    staat["naam"] = naam
    actief = staat.get("actief")

    if actief is None:
        if boven:
            staat["actief"] = {
                "start": nu.isoformat(),
                "laatst": nu.isoformat(),
                "boven_laatst": nu.isoformat(),
                "energie_wh": 0.0,
                "piek_w": float(vermogen_w),
            }
        return

    laatst = _tijd(actief.get("laatst")) or nu
    stap = _minuten(laatst, nu)
    if vermogen_w is not None and vermogen_w > 0 and 0 < stap <= MAX_STAP_MINUTEN:
        actief["energie_wh"] += vermogen_w * stap / 60
    actief["laatst"] = nu.isoformat()

    if boven:
        actief["boven_laatst"] = nu.isoformat()
        actief["piek_w"] = max(actief["piek_w"], float(vermogen_w))
        return

    boven_laatst = _tijd(actief.get("boven_laatst")) or nu
    if _minuten(boven_laatst, nu) < EINDE_NA_MINUTEN:
        return
    start = _tijd(actief.get("start")) or boven_laatst
    duur = _minuten(start, boven_laatst)
    if duur >= MIN_MINUTEN:
        for veld, waarde in (
            ("duren_min", round(duur, 1)),
            ("energie_kwh", round(actief["energie_wh"] / 1000, 3)),
            ("piek_w", round(actief["piek_w"])),
        ):
            staat[veld] = (staat.get(veld) or [])[-(HISTORIE - 1):] + [waarde]
    staat["actief"] = None


def indeling(staat: dict) -> str:
    duren = staat.get("duren_min") or []
    if len(duren) < MIN_KEREN:
        return "lerend"
    return "kortlopend" if median(duren) < KORTLOPEND_TOT_MINUTEN else "aanhoudend"


def _schaduwbesluit(soort: str, al_ingesteld: bool, actief: bool, keren: int, energie: float | None) -> str:
    if al_ingesteld:
        return "Staat al in je eigen lijst; verandert niets."
    if soort == "lerend":
        return f"Nog {MIN_KEREN - keren} keer meten voordat het iets zou doen."
    if soort == "kortlopend":
        cyclus = f"één cyclus van {energie:.2f} kWh" if energie is not None else "één cyclus"
        if actief:
            return f"Zou nu meetellen als {cyclus}, in plaats van het huisverbruik op te schalen."
        return f"Zou bij gebruik meetellen als {cyclus}."
    if actief:
        return "Zou nu direct meetellen, zonder afvlakking (zoals de airco)."
    return "Zou bij gebruik direct meetellen, zonder afvlakking (zoals de airco)."


def overzicht(leer: dict, ingesteld: set[str], vermogens: dict[str, float | None]) -> list[dict]:
    """Wat er geleerd is, per apparaat, met het schaduwbesluit."""
    rijen = []
    for entiteit, staat in leer.items():
        duren = staat.get("duren_min") or []
        energie = staat.get("energie_kwh") or []
        pieken = staat.get("piek_w") or []
        soort = indeling(staat)
        actief = staat.get("actief") is not None
        mediaan_energie = round(median(energie), 2) if energie else None
        rijen.append(
            {
                "naam": staat.get("naam") or entiteit,
                "entiteit": entiteit,
                "nu_w": vermogens.get(entiteit),
                "actief": actief,
                "keren": len(duren),
                "mediaan_duur_min": round(median(duren)) if duren else None,
                "mediaan_energie_kwh": mediaan_energie,
                "mediaan_piek_w": round(median(pieken)) if pieken else None,
                "indeling": soort,
                "al_ingesteld": entiteit in ingesteld,
                "schaduwbesluit": _schaduwbesluit(
                    soort, entiteit in ingesteld, actief, len(duren), mediaan_energie
                ),
            }
        )
    rijen.sort(key=lambda r: (r["al_ingesteld"], -r["keren"], r["naam"]))
    return rijen


def als_tekst(apparaten: list[dict], drempel_w: float, toelichting: str) -> str:
    """De Proefstand-kaart als kant-en-klare markdown.

    Hier en niet in het dashboard: logica in een sjabloon faalt stil en
    heeft geen toets (sjabloonratel, v3.95.4).
    """
    if not apparaten:
        return (
            f"_Nog geen apparaat met een eigen meting boven {drempel_w:.0f} W "
            f"gezien._\n\n_{toelichting}_"
        )

    def _getal(waarde, eenheid: str, decimalen: int = 0) -> str:
        if waarde is None:
            return "–"
        return f"{waarde:.{decimalen}f} {eenheid}".replace(".", ",")

    regels = [
        "| Apparaat | Nu | Keren | Duur | Energie | Indeling |",
        "|---|---|---|---|---|---|",
    ]
    for r in apparaten:
        naam = ("⚡ " if r["actief"] else "") + r["naam"]
        if r["al_ingesteld"]:
            naam += " (eigen lijst)"
        regels.append(
            f"| {naam} | {_getal(r['nu_w'], 'W')} | {r['keren']} | "
            f"{_getal(r['mediaan_duur_min'], 'min')} | "
            f"{_getal(r['mediaan_energie_kwh'], 'kWh', 2)} | {r['indeling']} |"
        )
    besluiten = [
        f"**{r['naam']}**: {r['schaduwbesluit']}" for r in apparaten if not r["al_ingesteld"]
    ]
    return "\n".join(regels) + "\n\n" + "\n\n".join(besluiten + [f"_{toelichting}_"])
