"""Het dagritme van de woonkamer-airco, geleerd uit jullie eigen bediening (v5.65).

Gevraagd: "Ik wil dat het EMS dit gaat regelen, dus leert van mijn gedrag" -
en "op basis van voorspelling, niet op tijdstippen". Geen vaste tijden en
geen extra automatisering: het EMS kijkt hoe jullie de airco bedienen.

Wat het leert, apart voor werkdagen (ma-vr) en het weekend:
- **warm om**: hoe laat jullie 's ochtends (04:00-11:00) de airco op
  verwarmen zetten - de mediaan;
- **ochtendtemperatuur**: op welke temperatuur jullie hem dan zetten (die
  kan anders zijn dan overdag);
- **hoe vaak**: op hoeveel van de ochtenden met iemand thuis dat gebeurt;
- **bedtijd**: hoe laat jullie hem 's avonds (19:00-03:00) uitzetten.

Wat het ermee doet (alleen met de knop Airco automaat aan):
- 's ochtends zet het de airco zo vroeg aan dat het op "warm om" de
  ochtendtemperatuur is. Hoe vroeg volgt uit de voorspelde temperatuur op
  dat moment en hoe snel de airco de kamer opwarmt - beide geleerd;
- 's avonds op de geleerde bedtijd gaat hij uit, ook als iemand hem zelf
  aanzette. Eén keer per avond: zet iemand hem daarna weer aan, dan blijft
  het EMS eraf.

Pas vanaf `MIN_KEER` waarnemingen. Wat het EMS zelf doet, telt niet als
waarneming - anders leert het van zichzelf. Zetten jullie een ochtend die
het EMS aanzette binnen de ochtend weer uit, dan telt die ochtend als "niet
gewenst".
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta

OCHTEND_VAN = 4 * 60
OCHTEND_TOT = 11 * 60
AVOND_VAN = 19 * 60
AVOND_TOT_NA_MIDDERNACHT = 3 * 60
MIN_KEER = 3
HISTORIE = 20
VERMOGEN_HISTORIE = 50
UURVERBRUIK_DAGEN = 14
VERMOGEN_AAN_W = 150.0
VERMOGEN_MIN_METINGEN = 5
VASTHOUDEN_FACTOR = 0.5
KANS_MINIMAAL = 0.5
NA_WARM_OM_MIN = 60
VOORLOOP_MIN_UUR = 0.25
VOORLOOP_MAX_UUR = 1.5
VOORLOOP_ONBEKEND_UUR = 0.5
MARGE_C = 0.3


def leeg() -> dict:
    return {
        "aan": {"werkdag": {}, "weekend": {}},
        "uit": {"werkdag": {}, "weekend": {}},
        "ochtenden": {"werkdag": [], "weekend": []},
        "ems": {"aan": None, "uit": None},
        "snelheden": [],
        "vermogens": [],
        "uurverbruik": {},
    }


def geldig(ritme) -> dict:
    """Een bruikbare structuur, ook uit een oude of kapotte opslag."""
    basis = leeg()
    if not isinstance(ritme, dict):
        return basis
    for deel in ("aan", "uit"):
        for soort in ("werkdag", "weekend"):
            waarde = (ritme.get(deel) or {}).get(soort)
            if isinstance(waarde, dict):
                basis[deel][soort] = dict(waarde)
    for soort in ("werkdag", "weekend"):
        waarde = (ritme.get("ochtenden") or {}).get(soort)
        if isinstance(waarde, list):
            basis["ochtenden"][soort] = [str(d) for d in waarde]
    snelheden = ritme.get("snelheden")
    if isinstance(snelheden, list):
        basis["snelheden"] = [float(v) for v in snelheden if isinstance(v, (int, float))][-HISTORIE:]
    vermogens = ritme.get("vermogens")
    if isinstance(vermogens, list):
        basis["vermogens"] = [float(v) for v in vermogens if isinstance(v, (int, float))][-VERMOGEN_HISTORIE:]
    uren = ritme.get("uurverbruik")
    if isinstance(uren, dict):
        basis["uurverbruik"] = {
            str(k): [float(v) for v in reeks if isinstance(v, (int, float))][-UURVERBRUIK_DAGEN:]
            for k, reeks in uren.items() if isinstance(reeks, list)
        }
    ems = ritme.get("ems")
    if isinstance(ems, dict):
        basis["ems"].update({k: ems.get(k) for k in ("aan", "uit")})
    return basis


def dagsoort(datum) -> str:
    return "weekend" if datum.weekday() >= 5 else "werkdag"


def minuut(moment: datetime) -> int:
    return moment.hour * 60 + moment.minute


def is_ochtend(moment: datetime) -> bool:
    return OCHTEND_VAN <= minuut(moment) < OCHTEND_TOT


def avond(moment: datetime) -> tuple[str, int] | None:
    """(datum van de avond, minuut sinds middernacht van die avond), of None.
    00:30 hoort bij de avond ervoor en telt als 24:30 (1470)."""
    m = minuut(moment)
    if m >= AVOND_VAN:
        return moment.date().isoformat(), m
    if m < AVOND_TOT_NA_MIDDERNACHT:
        return (moment.date() - timedelta(days=1)).isoformat(), m + 1440
    return None


def _bijsnijden(reeks: dict) -> dict:
    return {k: reeks[k] for k in sorted(reeks)[-HISTORIE:]}


def noteer_ochtend_thuis(ritme: dict, moment: datetime) -> None:
    """Deze ochtend was er iemand thuis - de noemer van "hoe vaak"."""
    if not is_ochtend(moment):
        return
    lijst = ritme["ochtenden"][dagsoort(moment)]
    datum = moment.date().isoformat()
    if datum not in lijst:
        lijst.append(datum)
        del lijst[:-HISTORIE]


def noteer_bediening(ritme: dict, moment: datetime, stand: str | None, doel) -> None:
    """Iemand bediende de airco zelf (niet het EMS)."""
    soort = dagsoort(moment)
    datum = moment.date().isoformat()
    if is_ochtend(moment):
        aan = ritme["aan"][soort]
        if stand == "heat":
            bestaand = aan.get(datum)
            if bestaand is None or bestaand.get("ems"):
                # Eerste keer verwarmen vanochtend - of jullie namen het
                # over van het EMS: dan geldt jullie moment niet, wel jullie
                # temperatuur.
                aan[datum] = {
                    "minuut": None if bestaand else minuut(moment),
                    "doel": _getal(doel),
                }
            elif _getal(doel) is not None:
                bestaand["doel"] = _getal(doel)
            ritme["aan"][soort] = _bijsnijden(aan)
        elif stand == "off" and (aan.get(datum) or {}).get("ems"):
            # Het EMS zette hem aan, jullie zetten hem uit: niet gewenst.
            aan.pop(datum, None)
        return
    plek = avond(moment)
    if plek and stand == "off":
        datum_avond, m = plek
        uit = ritme["uit"][dagsoort(datetime.fromisoformat(datum_avond))]
        uit[datum_avond] = m
        ritme["uit"][dagsoort(datetime.fromisoformat(datum_avond))] = _bijsnijden(uit)


def noteer_ems_aan(ritme: dict, moment: datetime) -> None:
    ritme["aan"][dagsoort(moment)][moment.date().isoformat()] = {
        "minuut": None, "doel": None, "ems": True,
    }
    ritme["ems"]["aan"] = moment.date().isoformat()


def noteer_ems_uit(ritme: dict, moment: datetime) -> None:
    plek = avond(moment)
    if plek:
        ritme["ems"]["uit"] = plek[0]


def _getal(waarde) -> float | None:
    try:
        return float(waarde)
    except (TypeError, ValueError):
        return None


def geleerd(ritme: dict, soort: str) -> dict:
    """Wat er voor deze dagsoort geleerd is."""
    aan = ritme["aan"][soort]
    momenten = [v["minuut"] for v in aan.values() if v.get("minuut") is not None]
    doelen = [v["doel"] for v in aan.values() if v.get("doel") is not None]
    uit = list(ritme["uit"][soort].values())
    ochtenden = ritme["ochtenden"][soort]
    gewenst = sum(1 for d in ochtenden if d in aan)
    return {
        "warm_om": round(statistics.median(momenten)) if len(momenten) >= MIN_KEER else None,
        "ochtend_doel_c": (
            round(statistics.median(doelen), 1) if len(doelen) >= MIN_KEER else None
        ),
        "bedtijd": round(statistics.median(uit)) if len(uit) >= MIN_KEER else None,
        "kans": round(gewenst / len(ochtenden), 2) if ochtenden else None,
        "keer_aan": len(momenten),
        "keer_doel": len(doelen),
        "keer_uit": len(uit),
        "ochtenden": len(ochtenden),
    }


def klok(m: int | None) -> str:
    if m is None:
        return "—"
    m = int(m) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def voorloop_uren(verwacht_c, doel_c: float, tempo_c_per_uur) -> float:
    """Hoe lang van tevoren aan: het tekort gedeeld door hoe snel de airco
    de kamer opwarmt, begrensd. Onbekend tempo: een half uur."""
    if verwacht_c is None:
        return VOORLOOP_ONBEKEND_UUR
    tekort = max(doel_c - verwacht_c, 0.0)
    if not tempo_c_per_uur or tempo_c_per_uur <= 0:
        return VOORLOOP_ONBEKEND_UUR if tekort > 0 else VOORLOOP_MIN_UUR
    return min(max(tekort / tempo_c_per_uur, VOORLOOP_MIN_UUR), VOORLOOP_MAX_UUR)


def besluit(
    ritme: dict,
    *,
    nu: datetime,
    woonkamer_c: float | None,
    verwacht_bij_warm_om,
    tempo_c_per_uur,
    aanwezigheid: str | None,
    advies: str | None,
    airco_stand: str | None,
    bedtijd_vast: int | None = None,
) -> dict | None:
    """Wat het ritme nu vraagt - of None als het niets te zeggen heeft.

    `verwacht_bij_warm_om` is een functie die voor een minuut van vandaag de
    voorspelde woonkamertemperatuur geeft (of None).
    """
    plek = avond(nu)
    if plek:
        datum_avond, m = plek
        leer = geleerd(ritme, dagsoort(datetime.fromisoformat(datum_avond)))
        vast = bedtijd_vast is not None
        bed = bedtijd_vast if vast else leer["bedtijd"]
        if bed is None or m < bed or ritme["ems"]["uit"] == datum_avond:
            return None
        # v5.67.1: één keer per avond. Stond hij al uit, dan is de avond
        # ook afgehandeld - wie hem daarna zelf weer aanzet, zet hem ook
        # zelf weer uit.
        if airco_stand != "heat":
            return {"actie": "niets", "markeer_uit": True, "tekst": "", "reden": ""}
        return {
            "actie": "uit",
            "markeer_uit": True,
            # v5.67.2: de vaste uittijd geldt ook met de knop Airco automaat uit.
            "altijd": vast,
            "tekst": (
                f"Uitzetten: het is {klok(bed)}, dan gaat de airco uit."
                if vast
                else f"Uitzetten: bedtijd - jullie zetten hem rond {klok(bed)} uit."
            ),
            "reden": (
                f"vaste uittijd {klok(bed)}"
                if vast
                else f"geleerde bedtijd {klok(bed)} ({leer['keer_uit']} avonden)"
            ),
        }
    if not is_ochtend(nu) or aanwezigheid == "weg":
        return None
    soort = dagsoort(nu)
    leer = geleerd(ritme, soort)
    if leer["warm_om"] is None or leer["ochtend_doel_c"] is None:
        return None
    if ritme["ems"]["aan"] == nu.date().isoformat() and airco_stand == "heat":
        # Het EMS zette hem vanochtend aan: laat hem lopen tot een uur na
        # het geleerde moment, ook als de aanwezigheid nog "slaapt" zegt -
        # daar was hij juist voor.
        if minuut(nu) < leer["warm_om"] + NA_WARM_OM_MIN:
            return {
                "actie": "niets",
                "houd_aan": True,
                "tekst": f"Ochtendverwarming loopt (warm om {klok(leer['warm_om'])}).",
                "reden": f"{soort}: ochtendverwarming tot {klok(leer['warm_om'] + NA_WARM_OM_MIN)}",
            }
        return None
    if (leer["kans"] or 0) < KANS_MINIMAAL:
        return None
    if nu.date().isoformat() in ritme["aan"][soort] or airco_stand == "heat":
        return None
    if advies != "airco" or woonkamer_c is None:
        return None
    doel = leer["ochtend_doel_c"]
    verwacht = verwacht_bij_warm_om(leer["warm_om"]) if verwacht_bij_warm_om else None
    if verwacht is None:
        verwacht = woonkamer_c
    if verwacht >= doel - MARGE_C and woonkamer_c >= doel - MARGE_C:
        return None
    voorloop = voorloop_uren(verwacht, doel, tempo_c_per_uur)
    start = leer["warm_om"] - round(voorloop * 60)
    m = minuut(nu)
    if not (start <= m < leer["warm_om"] + NA_WARM_OM_MIN):
        return None
    return {
        "actie": "verwarmen",
        "doel_c": doel,
        "tekst": (
            f"Ochtend: verwarmen tot {doel:.1f} °C zodat het om {klok(leer['warm_om'])} "
            f"warm is (verwacht dan {verwacht:.1f} °C, {round(voorloop * 60)} min "
            "opwarmen)."
        ),
        "reden": (
            f"{soort}: jullie willen het rond {klok(leer['warm_om'])} {doel:.1f} °C "
            f"({leer['keer_aan']} ochtenden, {round((leer['kans'] or 0) * 100)}% van de ochtenden)"
        ),
    }


def overzicht(ritme: dict) -> dict:
    """Voor het dashboard en de export."""
    uit = {}
    for soort in ("werkdag", "weekend"):
        leer = geleerd(ritme, soort)
        uit[soort] = {
            **leer,
            "warm_om_klok": klok(leer["warm_om"]),
            "bedtijd_klok": klok(leer["bedtijd"]),
        }
    uit["verwarmvermogen_kw"] = verwarmvermogen_kw(ritme)
    uit["vermogensmetingen"] = len(ritme.get("vermogens") or [])
    uit["toelichting"] = (
        f"Geleerd uit jullie eigen bediening, vanaf {MIN_KEER} keer. 's Ochtends "
        "(04-11 uur) zet het EMS de airco zo vroeg aan dat het op het geleerde "
        "moment warm is; 's avonds (19-03 uur) gaat hij uit op de geleerde "
        "bedtijd. Alleen met de knop Airco automaat aan."
    )
    return uit


# --- v5.66: warm bij thuiskomst --------------------------------------------

THUISKOMST_MIN_KM = 0.3
THUISKOMST_MAX_KM = 30.0
SNELHEID_STANDAARD_KMH = 50.0
SNELHEID_MIN_KMH = 5.0
SNELHEID_MAX_KMH = 130.0
THUISKOMST_MARGE_MIN = 5


def noteer_nadering(ritme: dict, vorige, nu: datetime, km: float) -> None:
    """Hoe snel komen jullie naar huis? Uit twee metingen tijdens het
    naderen (afstand en tijd), begrensd tot een plausibele snelheid."""
    if not vorige:
        return
    t0, km0 = vorige
    uren = (nu - t0).total_seconds() / 3600
    if uren <= 0 or uren > 0.5 or km0 is None or km >= km0:
        return
    snelheid = (km0 - km) / uren
    if SNELHEID_MIN_KMH <= snelheid <= SNELHEID_MAX_KMH:
        ritme["snelheden"].append(round(snelheid, 1))
        del ritme["snelheden"][:-HISTORIE]


def reissnelheid(ritme: dict) -> float:
    reeks = ritme.get("snelheden") or []
    return statistics.median(reeks) if len(reeks) >= MIN_KEER else SNELHEID_STANDAARD_KMH


def thuiskomst(
    ritme: dict,
    *,
    koers: str | None,
    km: float | None,
    aanwezigheid: str | None,
    woonkamer_c: float | None,
    doel_c: float | None,
    tempo_c_per_uur,
    advies: str | None,
    airco_stand: str | None,
    door_ems: bool,
) -> dict | None:
    """Iemand komt naar huis terwijl er niemand is (v5.66, gevraagd: "warm
    bij thuiskomst").

    Zet de airco zo vroeg aan dat de kamer warm is als jullie binnenkomen:
    de verwachte reistijd (afstand / geleerde reissnelheid, eerst 50 km/h)
    tegenover de opwarmtijd. Alleen binnen 30 km en als jullie richting huis
    gaan; draait hij al voor de thuiskomst, dan houdt dit hem aan zolang
    iemand nadert, ook al zegt de aanwezigheid nog "weg".
    """
    if aanwezigheid != "weg" or koers != "towards" or km is None:
        return None
    if not THUISKOMST_MIN_KM <= km <= THUISKOMST_MAX_KM:
        return None
    snelheid = reissnelheid(ritme)
    eta_min = round(km / snelheid * 60)
    if airco_stand == "heat" and door_ems:
        return {
            "actie": "niets",
            "houd_aan": True,
            "tekst": f"Thuiskomst: iemand is {km:.1f} km van huis, ongeveer {eta_min} min.",
            "reden": f"thuiskomst over ongeveer {eta_min} min",
        }
    if doel_c is None or woonkamer_c is None or advies != "airco" or airco_stand == "heat":
        return None
    if woonkamer_c >= doel_c - MARGE_C:
        return None
    opwarmen_min = round(voorloop_uren(woonkamer_c, doel_c, tempo_c_per_uur) * 60)
    if eta_min > opwarmen_min + THUISKOMST_MARGE_MIN:
        return None
    return {
        "actie": "verwarmen",
        "doel_c": doel_c,
        "tekst": (
            f"Thuiskomst: verwarmen tot {doel_c:.1f} °C - iemand is {km:.1f} km van "
            f"huis, ongeveer {eta_min} min; opwarmen duurt ongeveer {opwarmen_min} min."
        ),
        "reden": f"thuiskomst over ongeveer {eta_min} min ({snelheid:.0f} km/h)",
    }


# --- v5.67: de ochtendverwarming in de nachtplanning ------------------------

def noteer_vermogen(ritme: dict, vermogen_w) -> None:
    """Het vermogen van de airco terwijl hij draait - voor de schatting."""
    if vermogen_w is not None and vermogen_w >= VERMOGEN_AAN_W:
        ritme["vermogens"].append(round(float(vermogen_w), 0))
        del ritme["vermogens"][:-VERMOGEN_HISTORIE]


def verwarmvermogen_kw(ritme: dict) -> float | None:
    reeks = ritme.get("vermogens") or []
    if len(reeks) < VERMOGEN_MIN_METINGEN:
        return None
    return statistics.median(reeks) / 1000


def noteer_uur(ritme: dict, uur: int, kwh: float) -> None:
    """Wat de airco in een afgelopen uur gebruikte (ook 0)."""
    reeks = ritme["uurverbruik"].setdefault(str(uur), [])
    reeks.append(round(max(kwh, 0.0), 3))
    del reeks[:-UURVERBRUIK_DAGEN]


def _overlap_uren(a_van: datetime, a_tot: datetime, b_van: datetime, b_tot: datetime) -> float:
    return max((min(a_tot, b_tot) - max(a_van, b_van)).total_seconds() / 3600, 0.0)


def profiel_kwh(ritme: dict, van: datetime, tot: datetime) -> float:
    """Hoeveel airco-verbruik het gewone verbruiksprofiel al meeneemt in dit
    venster: per klokuur de mediaan van wat de airco de laatste dagen in
    dat uur gebruikte."""
    totaal = 0.0
    uur = van.replace(minute=0, second=0, microsecond=0)
    while uur < tot:
        reeks = ritme["uurverbruik"].get(str(uur.hour)) or []
        if reeks:
            totaal += statistics.median(reeks) * _overlap_uren(uur, uur + timedelta(hours=1), van, tot)
        uur += timedelta(hours=1)
    return totaal


def ochtend_kwh(ritme: dict, van: datetime, tot: datetime, verwacht_op, tempo_c_per_uur) -> float:
    """Het verwachte verbruik van de ochtendverwarming in dit venster:
    opwarmen op vol vermogen, daarna een uur vasthouden op half vermogen."""
    vermogen = verwarmvermogen_kw(ritme)
    if vermogen is None:
        return 0.0
    totaal = 0.0
    dag = van.date()
    while dag <= tot.date():
        leer = geleerd(ritme, dagsoort(dag))
        if (
            leer["warm_om"] is not None and leer["ochtend_doel_c"] is not None
            and (leer["kans"] or 0) >= KANS_MINIMAAL
            and ritme["ems"]["aan"] != dag.isoformat()
        ):
            middernacht = datetime.combine(dag, datetime.min.time(), tzinfo=van.tzinfo)
            warm = middernacht + timedelta(minutes=leer["warm_om"])
            voorspeld = verwacht_op(warm) if verwacht_op else None
            voorloop = voorloop_uren(voorspeld, leer["ochtend_doel_c"], tempo_c_per_uur)
            if voorspeld is None or voorspeld < leer["ochtend_doel_c"] - MARGE_C:
                start = warm - timedelta(hours=voorloop)
                totaal += vermogen * _overlap_uren(start, warm, van, tot)
                totaal += vermogen * VASTHOUDEN_FACTOR * _overlap_uren(
                    warm, warm + timedelta(minutes=NA_WARM_OM_MIN), van, tot
                )
        dag += timedelta(days=1)
    return totaal


def nacht_extra_kwh(ritme: dict, van: datetime, tot: datetime, verwacht_op, tempo_c_per_uur) -> dict:
    """Wat er bovenop het gewone verbruiksprofiel bij moet: de verwachte
    ochtendverwarming min wat het profiel al aan airco meeneemt. Nooit
    negatief - het profiel wordt hier niet verlaagd."""
    verwacht = ochtend_kwh(ritme, van, tot, verwacht_op, tempo_c_per_uur)
    al_in_profiel = profiel_kwh(ritme, van, tot)
    return {
        "verwacht_kwh": round(verwacht, 3),
        "al_in_profiel_kwh": round(al_in_profiel, 3),
        "extra_kwh": round(max(verwacht - al_in_profiel, 0.0), 3),
    }


def minuten_uit_klok(waarde) -> int | None:
    """'22:00' of '22:00:00' -> 1320; leeg of onzin -> None (v5.67.1)."""
    try:
        delen = str(waarde).strip().split(":")
        uur, minuut = int(delen[0]), int(delen[1])
    except (TypeError, ValueError, IndexError):
        return None
    if not (0 <= uur < 24 and 0 <= minuut < 60):
        return None
    m = uur * 60 + minuut
    # Na middernacht hoort bij de avond ervoor (zoals `avond`).
    return m + 1440 if m < AVOND_TOT_NA_MIDDERNACHT else m
