"""Wie of wat veranderde iets? (v5.263.0)

Home Assistant geeft bij elke toestand een `context` mee: wie de opdracht
gaf (`user_id`) en of die uit een automatisering of script kwam
(`parent_id`). Geen van beide: het apparaat meldde de wijziging zelf
(afstandsbediening, de app van de fabrikant, een knop op het apparaat).

Alleen vastleggen - de sturing gebruikt dit niet.
"""
from __future__ import annotations

EMS = "ems"
EIGEN_AUTOMATISERING = "eigen automatisering"
PERSOON = "persoon"
AUTOMATISERING = "automatisering"
APPARAAT = "apparaat"

TEKST = {
    EMS: "het EMS",
    EIGEN_AUTOMATISERING: "de ingestelde eigen automatisering",
    PERSOON: "iemand via Home Assistant (app of dashboard)",
    AUTOMATISERING: "een automatisering of script",
    APPARAAT: "het apparaat zelf (afstandsbediening of eigen app)",
}

MAX_REGELS = 40


def uit_context(context, *, door_ems: bool = False, eigen_automatisering: bool = False) -> str:
    """De oorzaak van een wijziging, uit de context van de toestand."""
    if door_ems:
        return EMS
    if eigen_automatisering:
        return EIGEN_AUTOMATISERING
    if getattr(context, "user_id", None):
        return PERSOON
    if getattr(context, "parent_id", None):
        return AUTOMATISERING
    return APPARAAT


def regel(moment_iso: str, van, naar, oorzaak: str) -> dict:
    return {
        "moment": moment_iso,
        "van": list(van) if van is not None else None,
        "naar": list(naar) if naar is not None else None,
        "oorzaak": oorzaak,
        "tekst": TEKST.get(oorzaak, oorzaak),
    }


def bijgewerkt(lijst, nieuwe: dict) -> list:
    return (list(lijst or []) + [nieuwe])[-MAX_REGELS:]
