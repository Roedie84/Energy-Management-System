"""Gedeelde hulpfuncties op moduleniveau van de coordinator (B4).

Ongewijzigd verhuisd uit `coordinator.py` zodat de mixin-modules ze kunnen
gebruiken zonder `coordinator.py` te importeren; `coordinator.py` exporteert
ze opnieuw, dus `from .coordinator import ...` blijft werken.
"""
from __future__ import annotations

from .const import (
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
