"""Gedeelde hulpfuncties op moduleniveau van de coordinator (B4).

Ongewijzigd verhuisd uit `coordinator.py` zodat de mixin-modules ze kunnen
gebruiken zonder `coordinator.py` te importeren; `coordinator.py` exporteert
ze opnieuw, dus `from .coordinator import ...` blijft werken.
"""
from __future__ import annotations

import statistics
from datetime import (
    datetime,
)
from homeassistant.util import (
    dt as dt_util,
)
from .const import (
    ONDERGRENS_GELDIG_DAGEN,
    ONDERGRENS_MAX_BOVEN,
    SOC_DEMPER_MAX_STAP_KWH,
    SOC_DEMPER_MINUTEN,
    SOC_DEMPER_STIL_W,
    SOC_DEMPER_STROOM_FRACTIE,
    TEKORT_LEEG_INHOUD_KWH,
)

# ---- verhuisd uit coordinator.py ----


def _nl(getal: float, decimalen: int = 1) -> str:
    """Een getal met een komma (v5.42)."""
    return f"{getal:.{decimalen}f}".replace(".", ",")


def accu_is_leeg(soc, inhoud_kwh, vloer: float, grens_kwh: float | None = None) -> bool:
    """Staat de accu leeg, voor de tekortmeting? (v5.33, v5.171.0)

    Leeg: de laadstand op de vloer (minimum + TEKORT_LEEG_MARGE_PROCENT), of
    sinds v5.171.0 (L-EMS-059) een bruikbare inhoud onder
    TEKORT_LEEG_INHOUD_KWH, los van de laadstand: een module die eerder op
    zijn celgrens zit, maakt de accu leeg bij 15-16 %. Geen van beide
    bekend: niet leeg.

    v5.177.0 (A7): met `grens_kwh` (zie `EnergyManagementSystemCoordinator.
    accu_leeg_grens_kwh`) beslist de gecorrigeerde inhoud als die bekend is:
    leeg tot en met die grens (de marge boven de ondergrens in kWh). Alleen
    zonder inhoud de laadstand.
    """
    if grens_kwh is not None and isinstance(inhoud_kwh, (int, float)):
        return inhoud_kwh <= grens_kwh + 1e-9
    if isinstance(inhoud_kwh, (int, float)) and inhoud_kwh < TEKORT_LEEG_INHOUD_KWH:
        return True
    return isinstance(soc, (int, float)) and soc <= vloer


# (interval start, interval end, price)
PriceEntry = tuple[datetime, datetime, float]


def demp_soc_stap(staat: dict | None, gemeten: float, vermogen_w: float, now: datetime) -> tuple[float, dict]:
    """De beschikbare energie zonder SoC-flapperen bij stilstand (v5.172.0, punt 1).

    Nacht 02->03: de laadstand sprong elke ~8 min tussen 15 en 16 % bij 0 W
    (module 00996 zaagde 11-15 %); 0,115 kWh per stap. De laatste aangenomen
    inhoud blijft staan zolang de accu stilstaat (|vermogen| < SOC_DEMPER_STIL_W),
    de stap klein is (<= SOC_DEMPER_MAX_STAP_KWH) en er sinds die waarde
    minder energie liep dan SOC_DEMPER_STROOM_FRACTIE van de stap. Een nieuwe
    waarde die SOC_DEMPER_MINUTEN aanhoudt, telt wel (echte langzame daling).
    Geeft (waarde, nieuwe staat).
    """
    if not staat:
        return gemeten, {"waarde": gemeten, "laatst": now, "stroom_kwh": 0.0,
                         "kandidaat": None, "kandidaat_sinds": None, "gedempt": 0}
    staat = dict(staat)
    uren = (now - staat["laatst"]).total_seconds() / 3600
    if 0 < uren <= 1:
        staat["stroom_kwh"] = staat.get("stroom_kwh", 0.0) + abs(vermogen_w) / 1000 * uren
    staat["laatst"] = now
    stap = gemeten - staat["waarde"]

    def neem() -> tuple[float, dict]:
        staat.update(waarde=gemeten, stroom_kwh=0.0, kandidaat=None, kandidaat_sinds=None)
        return gemeten, staat

    if abs(stap) < 1e-9:
        staat.update(kandidaat=None, kandidaat_sinds=None)
        return gemeten, staat
    if abs(vermogen_w) >= SOC_DEMPER_STIL_W or abs(stap) > SOC_DEMPER_MAX_STAP_KWH:
        return neem()
    if staat.get("stroom_kwh", 0.0) >= SOC_DEMPER_STROOM_FRACTIE * abs(stap):
        return neem()
    if staat.get("kandidaat") is None or abs(staat["kandidaat"] - gemeten) > 1e-9:
        staat.update(kandidaat=gemeten, kandidaat_sinds=now)
        staat["gedempt"] = staat.get("gedempt", 0) + 1
    elif (now - staat["kandidaat_sinds"]).total_seconds() >= SOC_DEMPER_MINUTEN * 60:
        return neem()
    return staat["waarde"], staat


def effectieve_ondergrens(waarnemingen, min_soc: float, now: datetime) -> tuple[float, str]:
    """De werkelijke bodem van de accu en waarom (v5.172.0, punt 4).

    De mediaan van de geldige waarnemingen (jonger dan ONDERGRENS_GELDIG_DAGEN)
    waarin de accu stopte met leveren terwijl het huis nog van het net nam.
    Geen waarnemingen: de min-SoC. Nooit onder de min-SoC en nooit meer dan
    ONDERGRENS_MAX_BOVEN erboven.
    """
    geldig = []
    for w in waarnemingen or []:
        moment = dt_util.parse_datetime(str(w.get("moment") or "")) if isinstance(w, dict) else None
        soc = w.get("soc") if isinstance(w, dict) else None
        if moment is None or not isinstance(soc, (int, float)):
            continue
        if (now - moment).total_seconds() <= ONDERGRENS_GELDIG_DAGEN * 86400:
            geldig.append(float(soc))
    if not geldig:
        return float(min_soc), "min-SoC (geen vroege stop gezien)"
    bodem = min(max(float(statistics.median(geldig)), min_soc), min_soc + ONDERGRENS_MAX_BOVEN)
    if bodem <= min_soc + 0.5:
        return float(min_soc), "min-SoC"
    return round(bodem, 1), (
        f"accu stopte {len(geldig)}x met leveren op ~{bodem:.0f} % terwijl het huis "
        f"van het net nam (min-SoC {min_soc:.0f} %)"
    )
