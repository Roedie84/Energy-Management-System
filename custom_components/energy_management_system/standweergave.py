"""Wat de accu nu doet, in één zin voor de hele cockpit (v5.181.1, punt 9).

Live 04-11 10:59: de tegel "Accu nu" zei "Accu bewaren voor later
(waardeplan)" (reden waardeplan_houden, stand smart_charging) terwijl de
accu 1,29 kW uit de zon laadde; de tijdlijn en de grafiek kleurden het
kwartier "zon laden" en de planvolging zei "Accu laadt 1,3 kW, volgens
plan". De interne reden klopt (de lading wordt bewaard en de zon mag erin),
maar de weergave beschreef maar de helft.

Deze module geeft één weergave uit drie dingen: de reden, de soort planrij
(handmatig laden, verkopen, terugleveren) en het gemeten accuvermogen. Een
handmatige planrij bepaalt wat er gebeurt; in de slimme standen het
vermogen. De reden voegt er hooguit een toelichting aan toe ("lading
bewaren voor later"). De cockpit (www/ems-cockpit.js, `standWeergave`)
gebruikt dezelfde tabellen; tests/test_v51811_live_0411.py houdt ze gelijk.

Zuiver, zonder Home Assistant. Tekenafspraak: + is ontladen, - is laden.
"""
from __future__ import annotations

# Dezelfde sleutels en namen als DOEN in de cockpit.
STANDEN: dict[str, str] = {
    "rust": "Rust",
    "zon": "Zon laden",
    "net": "Net laden",
    "voeden": "Huis voeden",
    "verkopen": "Verkopen",
    "terug": "Zon terugleveren",
    "leeg": "Accu leeg",
}

# Toelichting per reden in de slimme standen (bij laden uit de zon of in rust).
TOELICHTING: dict[str, str] = {
    "waardeplan_houden": "lading bewaren voor later",
    "battery_saved_for_peak": "lading bewaren voor de piek",
    "sparen_in_blok": "lading bewaren voor na het blok",
    "celbescherming_houden": "lading vasthouden (celbescherming)",
}

# In rust met deze redenen is het bewaren zelf de stand.
RUST_LABEL: dict[str, str] = {
    "waardeplan_houden": "Bewaren voor later",
    "battery_saved_for_peak": "Bewaren voor de piek",
    "sparen_in_blok": "Bewaren voor na het blok",
    "celbescherming_houden": "Lading vasthouden",
}

DREMPEL_W = 50.0


def soort(plan_modus: str | None, accu_w: float | None, tekort: bool = False) -> str:
    """De sleutel van wat er gebeurt (zoals `doen` in de cockpit)."""
    m = str(plan_modus or "")
    if m.startswith("manual (verkopen)"):
        return "verkopen"
    if m.startswith("manual (terugleveren)"):
        return "terug"
    if m.startswith("manual (laden)"):
        return "net"
    if tekort:
        return "leeg"
    if accu_w is not None:
        if accu_w <= -DREMPEL_W:
            return "zon"
        if accu_w >= DREMPEL_W:
            return "voeden"
        return "rust"
    return "voeden" if m.startswith("smart_discharging") else "rust"


def weergave(
    reden: str | None,
    plan_modus: str | None = None,
    accu_w: float | None = None,
    tekort: bool = False,
) -> dict:
    """{"k": sleutel, "label": zin} voor tegel, kopchip, tijdlijn en uitleg."""
    k = soort(plan_modus, accu_w, tekort)
    if reden == "waardeplan_leeg" and k == "rust":
        k = "leeg"
    toelichting = TOELICHTING.get(reden or "")
    if k == "rust" and reden in RUST_LABEL:
        label = RUST_LABEL[reden]
    elif k == "zon" and toelichting:
        label = f"{STANDEN[k]} – {toelichting}"
    else:
        label = STANDEN[k]
    return {"k": k, "label": label}
