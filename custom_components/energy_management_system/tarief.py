"""Tarieflaag (v5.28): wat een kWh kost en wat hij oplevert, los van de strategie.

Uit de review: "De batterijstrategie moet niet zelf hoeven weten hoe
Zonneplan, saldering of de situatie vanaf 2027 wordt berekend." De strategie
vraagt alleen `import_waarde` en `export_waarde` op.

Onbekend is onbekend: er wordt nooit een waarde verzonnen. Elke uitkomst
draagt een kwaliteit - "ok", "onzeker" (een expliciete aanname) of
"unknown" (geen waarde).

Zuivere functies, zonder Home Assistant.
"""
from __future__ import annotations

from datetime import date, datetime

TARIEF_MODEL_VERSIE = "2026.1"
SALDERING_EINDE = date(2027, 1, 1)


def saldeerruimte(jaar_inkoop_kwh: float | None, jaar_terug_kwh: float | None) -> dict:
    """Hoeveel er dit jaar nog binnen de saldering teruggeleverd kan worden.

    Inkoop min teruglevering sinds 1 januari. Zonder beginstand: onbekend.
    """
    if jaar_inkoop_kwh is None or jaar_terug_kwh is None:
        return {"kwh": None, "status": "unknown"}
    return {"kwh": round(jaar_inkoop_kwh - jaar_terug_kwh, 3), "status": "ok"}


def waarde(
    moment: datetime,
    prijs_eur: float | None,
    *,
    saldeerruimte_kwh: float | None,
    vergoeding_boven_eur: float | None = None,
    marktprijs_eur: float | None = None,
    exportkosten_2027_eur: float | None = None,
) -> dict:
    """Import- en exportwaarde van een kwartier.

    2026, binnen de saldeerruimte:   export = import
    2026, boven de saldeerruimte:    export = ingestelde vergoeding
    2026, saldeerruimte onbekend:    export = import, kwaliteit "onzeker"
    vanaf 2027:                      export = marktprijs - ingestelde kosten
    """
    uit = {
        "import_eur": prijs_eur,
        "export_eur": None,
        "regime": None,
        "kwaliteit": "unknown",
        "tariefmodel": TARIEF_MODEL_VERSIE,
    }
    if prijs_eur is None:
        uit["regime"] = "geen_prijs"
        return uit
    if moment.date() >= SALDERING_EINDE:
        uit["regime"] = "na_saldering"
        if marktprijs_eur is not None and exportkosten_2027_eur is not None:
            uit["export_eur"] = round(marktprijs_eur - exportkosten_2027_eur, 5)
            uit["kwaliteit"] = "ok"
        return uit
    if saldeerruimte_kwh is None:
        uit.update(export_eur=prijs_eur, regime="saldering_onbekend", kwaliteit="onzeker")
    elif saldeerruimte_kwh > 0:
        uit.update(export_eur=prijs_eur, regime="binnen_saldering", kwaliteit="ok")
    else:
        uit["regime"] = "boven_saldering"
        if vergoeding_boven_eur is not None:
            uit.update(export_eur=vergoeding_boven_eur, kwaliteit="ok")
    return uit
