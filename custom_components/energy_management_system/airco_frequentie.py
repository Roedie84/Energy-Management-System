"""Het airco-vermogen uit de compressorfrequentie (v5.200.0).

Ruud 09-11: "kun je het verbruik van de airco beter analyseren door
sensor.woonkamer_compressor_frequency mee te nemen?" - akkoord op drie punten.

Tot nu gebruikte het EMS de Daikin-sensor "geschat vermogen". Die rekent
alleen hoe snel de energieteller (stappen van 0,1 kWh) een stap zet: hij
springt van 0 naar 5 kW en staat vaak op 0 terwijl de compressor draait. Het
geleerde vermogen werd daardoor 1,01 kW zolang hij aan staat; 08-11 gaf dat
8,9 kWh tegen 6,0 kWh op de teller.

Nu:

1. vermogen = a x frequentie + b zolang de compressor draait (08-11 gefit:
   31,4 W/Hz en -238 W; dagtotaal op 0,02 kWh na). a en b leert het EMS zelf
   bij uit de energieteller: per vijf tellerstappen (0,5 kWh) de opgetelde
   Hz-uren en draai-uren, dan een kleinste-kwadratenfit.
2. opwarmen en vasthouden apart: het vermogen terwijl de kamer nog een graad
   of meer onder het doel zit (opwarmen, 50-66 Hz) en het gemiddelde verbruik
   per graad verschil met buiten als de kamer op temperatuur blijft
   (vasthouden, 16-20 Hz, inclusief de pauzes).
3. het verbruik per uur uit de teller zelf, met de modelschatting alleen voor
   het stukje sinds de laatste tellerstap.

Alleen pure functies; de toestand die bewaard moet blijven staat in het
dagritme (`ritme["frequentie"]`).
"""
from __future__ import annotations

import statistics

#: Startwaarden (fit 08-11), tot er genoeg eigen metingen zijn.
STANDAARD_W_PER_HZ = 31.4
STANDAARD_BASIS_W = -238.0
#: Ondergrens zolang de compressor draait.
MIN_DRAAI_W = 50.0
#: Eén tellerstap van de Daikin.
TELLER_STAP_KWH = 0.1
#: Zoveel tellerstappen per meetvenster.
STAPPEN_PER_VENSTER = 5
VENSTERS_MAX = 60
VENSTERS_MIN = 8
#: Opwarmen: de kamer zit minstens zoveel onder het doel.
OPWARM_ONDER_C = 1.0
OPWARM_MAX = 240
OPWARM_MIN = 10
#: Vasthouden: de kamer blijft binnen zoveel van het doel.
HOUD_BINNEN_C = 0.5
HOUD_VENSTER_UREN = 1.0
HOUD_MAX = 30
HOUD_MIN = 3
#: Kleinste verschil binnen-buiten voor een vasthoudmeting.
HOUD_MIN_VERSCHIL_C = 3.0


def leeg() -> dict:
    return {"vensters": [], "opwarm_w": [], "houd_w_per_graad": []}


def geldig(waarde) -> dict:
    basis = leeg()
    if not isinstance(waarde, dict):
        return basis
    vensters = waarde.get("vensters")
    if isinstance(vensters, list):
        basis["vensters"] = [
            [float(x) for x in v] for v in vensters
            if isinstance(v, (list, tuple)) and len(v) == 3
            and all(isinstance(x, (int, float)) for x in v)
        ][-VENSTERS_MAX:]
    for sleutel, maximum in (("opwarm_w", OPWARM_MAX), ("houd_w_per_graad", HOUD_MAX)):
        reeks = waarde.get(sleutel)
        if isinstance(reeks, list):
            basis[sleutel] = [float(x) for x in reeks if isinstance(x, (int, float))][-maximum:]
    return basis


def _redelijk(a: float, b: float) -> bool:
    return (
        10.0 <= a <= 60.0
        and a * 16 + b >= MIN_DRAAI_W
        and 800.0 <= a * 66 + b <= 3500.0
    )


def coefficienten(model: dict) -> tuple[float, float, bool]:
    """(W per Hz, basis-W, geleerd?) - de eigen fit als die redelijk is."""
    vensters = (model or {}).get("vensters") or []
    if len(vensters) >= VENSTERS_MIN:
        # kWh = a*Hz-uren + b*draai-uren  (in Wh: x1000)
        sxx = sum(v[0] * v[0] for v in vensters)
        sxy = sum(v[0] * v[1] for v in vensters)
        syy = sum(v[1] * v[1] for v in vensters)
        sxz = sum(v[0] * v[2] * 1000 for v in vensters)
        syz = sum(v[1] * v[2] * 1000 for v in vensters)
        det = sxx * syy - sxy * sxy
        if abs(det) > 1e-9:
            a = (sxz * syy - syz * sxy) / det
            b = (sxx * syz - sxy * sxz) / det
            if _redelijk(a, b):
                return a, b, True
    return STANDAARD_W_PER_HZ, STANDAARD_BASIS_W, False


def vermogen_w(model: dict, hz: float | None) -> float | None:
    """Het vermogen bij deze frequentie; 0 als de compressor stilstaat."""
    if hz is None:
        return None
    if hz <= 0:
        return 0.0
    a, b, _ = coefficienten(model)
    return max(a * hz + b, MIN_DRAAI_W)


def nieuwe_teller() -> dict:
    """De lopende toestand (niet bewaard): het meetvenster en de stand."""
    return {
        "teller": None, "begonnen": False, "hz_uren": 0.0, "draai_uren": 0.0,
        "stappen": 0, "rest_kwh": 0.0, "totaal_kwh": 0.0,
        "houd_kwh": 0.0, "houd_graaduren": 0.0, "houd_uren": 0.0, "houd_doel": None,
    }


def ronde(
    model: dict,
    loop: dict,
    *,
    hz: float | None,
    teller_kwh: float | None,
    uren: float,
    binnen_c: float | None = None,
    buiten_c: float | None = None,
    doel_c: float | None = None,
    verwarmt: bool = False,
) -> None:
    """Eén ronde bijhouden. `uren` = tijd sinds de vorige ronde, `hz` de
    frequentie in die tijd. Werkt `model` (bewaard) en `loop` (lopend) bij."""
    if hz is None or uren <= 0 or uren > 0.25:
        _houd_stop(loop)
        return
    p = vermogen_w(model, hz) or 0.0
    kwh = p / 1000 * uren
    loop["hz_uren"] += hz * uren
    loop["draai_uren"] += uren if hz > 0 else 0.0
    loop["rest_kwh"] += kwh
    _punt2(model, loop, p, kwh, uren, binnen_c, buiten_c, doel_c, verwarmt and hz is not None)
    if teller_kwh is None:
        return
    vorige = loop["teller"]
    loop["teller"] = teller_kwh
    if vorige is None:
        return
    if teller_kwh < vorige - 1e-6:
        # middernacht: de teller begint opnieuw; het venster is kapot
        loop["totaal_kwh"] += teller_kwh
        loop["rest_kwh"] = 0.0
        _venster_opnieuw(loop, begonnen=False)
        return
    if teller_kwh <= vorige + 1e-6:
        return
    erbij = teller_kwh - vorige
    loop["totaal_kwh"] += erbij
    loop["rest_kwh"] = 0.0
    if not loop["begonnen"]:
        _venster_opnieuw(loop, begonnen=True)
        return
    loop["stappen"] += max(1, round(erbij / TELLER_STAP_KWH))
    if loop["stappen"] >= STAPPEN_PER_VENSTER:
        if loop["hz_uren"] > 0:
            model.setdefault("vensters", []).append(
                [round(loop["hz_uren"], 4), round(loop["draai_uren"], 4),
                 round(loop["stappen"] * TELLER_STAP_KWH, 3)]
            )
            del model["vensters"][:-VENSTERS_MAX]
        _venster_opnieuw(loop, begonnen=True)


def _venster_opnieuw(loop: dict, *, begonnen: bool) -> None:
    loop.update(begonnen=begonnen, hz_uren=0.0, draai_uren=0.0, stappen=0)


def _houd_stop(loop: dict) -> None:
    loop.update(houd_kwh=0.0, houd_graaduren=0.0, houd_uren=0.0, houd_doel=None)


def _punt2(model, loop, p, kwh, uren, binnen_c, buiten_c, doel_c, verwarmt) -> None:
    if not verwarmt or binnen_c is None or doel_c is None:
        _houd_stop(loop)
        return
    if p > 0 and binnen_c <= doel_c - OPWARM_ONDER_C:
        model.setdefault("opwarm_w", []).append(round(p, 0))
        del model["opwarm_w"][:-OPWARM_MAX]
    if (
        buiten_c is None or abs(binnen_c - doel_c) > HOUD_BINNEN_C
        or binnen_c - buiten_c < HOUD_MIN_VERSCHIL_C
    ):
        _houd_stop(loop)
        return
    if loop["houd_doel"] is not None and abs(loop["houd_doel"] - doel_c) > 0.05:
        _houd_stop(loop)
    loop["houd_doel"] = doel_c
    loop["houd_kwh"] += kwh
    loop["houd_graaduren"] += (binnen_c - buiten_c) * uren
    loop["houd_uren"] += uren
    if loop["houd_uren"] >= HOUD_VENSTER_UREN and loop["houd_graaduren"] > 0:
        model.setdefault("houd_w_per_graad", []).append(
            round(loop["houd_kwh"] * 1000 / loop["houd_graaduren"], 1)
        )
        del model["houd_w_per_graad"][:-HOUD_MAX]
        _houd_stop(loop)
        loop["houd_doel"] = doel_c


def opwarm_kw(model: dict) -> float | None:
    reeks = (model or {}).get("opwarm_w") or []
    if len(reeks) < OPWARM_MIN:
        return None
    return statistics.median(reeks) / 1000


def houd_w_per_graad(model: dict) -> float | None:
    reeks = (model or {}).get("houd_w_per_graad") or []
    if len(reeks) < HOUD_MIN:
        return None
    return statistics.median(reeks)


def stand_kwh(loop: dict) -> float | None:
    """Het totaal sinds het begin van het tellen: de tellerstappen plus de
    modelschatting sinds de laatste stap (hooguit één stap)."""
    if loop.get("teller") is None:
        return None
    return loop["totaal_kwh"] + min(max(loop["rest_kwh"], 0.0), TELLER_STAP_KWH * 0.999)
