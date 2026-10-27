"""Planning van vaatwasser en wasmachine, in gewone taal (v5.139.0).

Gevraagd 27-10: "Kunnen we iets bouwen dat we uitgestelde start en eindtijd
helderder in het EMS krijgen? Voor o.a. wasmachine en vaatwasser."

Wat er was (v1.61.0/v1.70.0): het EMS las de uitgestelde start van de
vaatwasser (`number.vaatwasser_begin_relatief`) en de eindtijd van de
wasmachine (`sensor.wasmachine_programma_eindtijd`) en telde de cyclus mee in
de reserve. Maar:

* de vaatwasser had alleen een begin, de wasmachine alleen een eind;
* zodra het apparaat draaide, verdween het uit beeld;
* de duur was één mediaan per apparaat (wasmachine 150 min, met een snel
  programma van 23 min in dezelfde reeks), dus een snel programma kreeg een
  begin dat ruim twee uur te vroeg lag - en daar zette de reserve het
  verbruik neer;
* de eigen voortgang (verstreken tijd / geleerde duur) stond op 10% terwijl
  Home Connect 33% zei.

Hier staat de afleiding, los van Home Assistant zodat hij te toetsen is.
De coordinator leest de entiteiten en geeft de waarden door.

Uitlezen, niet bedienen: het EMS start of verplaatst nooit een apparaat.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .tijdtekst import tijd_met_dag

# --- Home Connect ----------------------------------------------------
# De zusterentiteiten worden gevonden op het einde van hun unique_id
# (Home Connect: "<ha_id>-<sleutel>"); de entity_id verschilt per taal
# (hier: sensor.wasmachine_status tegen sensor.vaatwasser_operation_state).
HC_TOESTAND = "BSH.Common.Status.OperationState"
HC_VOORTGANG = "BSH.Common.Option.ProgramProgress"
HC_EINDTIJD = "BSH.Common.Option.RemainingProgramTime"
HC_START_OVER = "BSH.Common.Option.StartInRelative"
HC_ACTIEF_PROGRAMMA = "BSH.Common.Root.ActiveProgram"
HC_GEKOZEN_PROGRAMMA = "BSH.Common.Root.SelectedProgram"

#: Toestanden waarin het programma loopt (verbruik of onderbreking).
HC_LOOPT = frozenset({"run", "pause", "actionrequired", "aborting"})
#: Wacht op een uitgestelde start.
HC_UITGESTELD = "delayedstart"
#: Geen bruikbare toestand: dan beslist de oude afleiding, zoals voorheen.
ONBRUIKBAAR = (None, "", "unknown", "unavailable", "none")

# --- Leren per programma ---------------------------------------------
#: Zoveel beurten per programma worden bewaard.
PROGRAMMA_HISTORIE = 10
#: Zoveel programma's per apparaat; het minst recente valt eruit.
PROGRAMMA_MAX = 16
#: Vanaf zoveel beurten geldt de duur van het programma zelf. Eén beurt is
#: al beter dan het gemiddelde over alle programma's: een snel programma
#: van 30 minuten is nooit 150 minuten.
PROGRAMMA_MIN_BEURTEN = 1

# --- Weergave --------------------------------------------------------
#: Zo lang na "klaar" blijft dat in de planning staan.
KLAAR_TONEN_UREN = 6.0
#: Verder vooruit kijkt de planning niet (gelijk aan APPLIANCE_PLAN_MAX_HOURS).
PLAN_MAX_UREN = 24.0
#: Pas vanaf dit verschil heet een ander moment "goedkoper".
PRIJS_VERSCHIL_MIN_EUR = 0.02
#: Stap waarmee een goedkoper begin gezocht wordt.
ZOEKSTAP_MINUTEN = 15

#: Leesbare programmanamen. Onbekende: het laatste deel, met hoofdletter.
PROGRAMMA_NAMEN = {
    "cotton": "Katoen",
    "cotton_eco": "Katoen eco",
    "eco_4060": "Eco 40-60",
    "easy_care": "Kreukherstellend",
    "synthetic": "Synthetisch",
    "mix": "Gemengd",
    "delicates_silk": "Fijn/zijde",
    "wool": "Wol",
    "super_153045_super_15": "Super 15",
    "super_153045_super_1530": "Super 15/30",
    "drum_clean": "Trommelreiniging",
    "sensitive": "Sensitive",
    "towels": "Handdoeken",
    "shirts_blouses": "Overhemden",
    "rinse_spin_drain": "Spoelen/centrifugeren",
    "spin_spin_drain": "Centrifugeren",
    "eco_50": "Eco 50",
    "auto_1": "Auto 35-45",
    "auto_2": "Auto 45-65",
    "auto_3": "Auto 65-75",
    "intensiv_70": "Intensief 70",
    "quick_45": "Snel 45",
    "quick_65": "Snel 65",
    "glas_40": "Glas 40",
    "night_wash": "Nacht",
    "kurz_60": "Kort 60",
    "pre_rinse": "Voorspoelen",
    "machine_care": "Machinereiniging",
}


def programma_sleutel(waarde) -> str | None:
    """"laundry_care_washer_program_cotton" -> "cotton"; leeg -> None."""
    tekst = str(waarde or "").strip().lower()
    if tekst in ONBRUIKBAAR:
        return None
    if "_program_" in tekst:
        return tekst.split("_program_", 1)[1] or None
    # Home Connect zonder vertaling: "LaundryCare.Washer.Program.Cotton"
    if ".program." in tekst:
        return tekst.split(".program.", 1)[1].replace(".", "_") or None
    return tekst


def programma_naam(sleutel: str | None) -> str | None:
    if not sleutel:
        return None
    if sleutel in PROGRAMMA_NAMEN:
        return PROGRAMMA_NAMEN[sleutel]
    return sleutel.replace("_", " ").capitalize()


def leer_programma(
    reeksen: dict, sleutel: str | None, waarde: float
) -> dict:
    """Voegt één beurt toe aan het programma; geeft de nieuwe reeksen terug.

    Bewaart per programma de laatste PROGRAMMA_HISTORIE waarden en hooguit
    PROGRAMMA_MAX programma's (het langst niet gebruikte valt weg).
    """
    if not sleutel:
        return dict(reeksen or {})
    uit = {k: list(v) for k, v in (reeksen or {}).items() if isinstance(v, list)}
    reeks = uit.pop(sleutel, [])
    reeks.append(round(float(waarde), 3))
    uit[sleutel] = reeks[-PROGRAMMA_HISTORIE:]
    while len(uit) > PROGRAMMA_MAX:
        uit.pop(next(iter(uit)))
    return uit


def geleerd_per_programma(reeksen: dict, sleutel: str | None) -> tuple[float, int] | None:
    """(mediaan, aantal) voor dit programma, of None als het onbekend is."""
    if not sleutel:
        return None
    reeks = [float(v) for v in (reeksen or {}).get(sleutel) or [] if v]
    if len(reeks) < PROGRAMMA_MIN_BEURTEN:
        return None
    return statistics.median(reeks), len(reeks)


# --- Prijs -----------------------------------------------------------


def kosten_bij_start(
    prijzen: list[tuple[datetime, datetime, float]],
    start: datetime,
    duur_minuten: float,
    kwh: float,
) -> float | None:
    """Wat de cyclus kost als hij om `start` begint (EUR).

    Het verbruik gelijk over de duur verdeeld - fijner weet het EMS het niet
    vooraf. Zolang salderen geldt is eigen opwek even veel waard als de
    kwartierprijs (zie `cycluskosten`, v5.74), dus prijs maal kWh klopt ook
    op een zonnige middag. None als de prijzen de cyclus niet dekken.
    """
    if duur_minuten <= 0 or kwh <= 0 or not prijzen:
        return None
    einde = start + timedelta(minutes=duur_minuten)
    per_minuut = kwh / duur_minuten
    totaal = 0.0
    gedekt = 0.0
    for blok_start, blok_eind, prijs in prijzen:
        van = max(start, blok_start)
        tot = min(einde, blok_eind)
        if tot <= van:
            continue
        minuten = (tot - van).total_seconds() / 60
        totaal += minuten * per_minuut * prijs
        gedekt += minuten
    if gedekt < duur_minuten - 0.5:
        return None
    return totaal


def goedkoopste_start(
    prijzen: list[tuple[datetime, datetime, float]],
    vanaf: datetime,
    uiterlijk_klaar: datetime,
    duur_minuten: float,
    kwh: float,
) -> tuple[datetime, float] | None:
    """Het goedkoopste begin tussen `vanaf` en zo dat hij om
    `uiterlijk_klaar` klaar is. In stappen van een kwartier, op de
    kwartiergrens."""
    if duur_minuten <= 0:
        return None
    laatste = uiterlijk_klaar - timedelta(minutes=duur_minuten)
    if laatste < vanaf:
        return None
    eerste = vanaf.replace(second=0, microsecond=0)
    rest = eerste.minute % ZOEKSTAP_MINUTEN
    if rest:
        eerste += timedelta(minutes=ZOEKSTAP_MINUTEN - rest)
    beste: tuple[datetime, float] | None = None
    kandidaat = eerste
    for _ in range(int(PLAN_MAX_UREN * 60 / ZOEKSTAP_MINUTEN) + 1):
        if kandidaat > laatste:
            break
        kost = kosten_bij_start(prijzen, kandidaat, duur_minuten, kwh)
        if kost is not None and (beste is None or kost < beste[1] - 1e-9):
            beste = (kandidaat, kost)
        kandidaat += timedelta(minutes=ZOEKSTAP_MINUTEN)
    return beste


# --- De planning -----------------------------------------------------


@dataclass
class Invoer:
    """Wat de coordinator over één apparaat weet."""

    naam: str  # "vaatwasser" of "wasmachine"
    nu: datetime
    #: Home Connect: bedrijfstoestand (lowercase) of None.
    hc_toestand: str | None = None
    #: Home Connect: seconden tot de uitgestelde start (vaatwasser).
    hc_start_over_s: float | None = None
    #: Home Connect: verwachte eindtijd (beide apparaten).
    hc_eindtijd: datetime | None = None
    #: Home Connect: voortgang in procenten.
    hc_voortgang: float | None = None
    #: Ruwe programmawaarde (actief, anders gekozen).
    programma: str | None = None
    #: Eigen toestandsmachine: "rustend", "actief" of "klaar".
    ems_toestand: str = "rustend"
    ems_gestart: datetime | None = None
    ems_klaar_sinds: datetime | None = None
    #: Geleerde duur per programma (reeksen) en over alle programma's.
    duur_per_programma: dict = field(default_factory=dict)
    duur_apparaat: float | None = None
    #: Verbruik per programma (reeksen) en per apparaat, met herkomst.
    kwh_per_programma: dict = field(default_factory=dict)
    kwh_apparaat: float = 0.0
    kwh_herkomst: str = "schatting"
    #: Prijzen (start, eind, EUR/kWh), voor het prijsoordeel.
    prijzen: list = field(default_factory=list)
    #: Kleinste plausibele duur; korter is een fragment, geen cyclus.
    min_duur: float = 30.0


def _duur(invoer: Invoer, sleutel: str | None) -> tuple[float | None, str, int]:
    """(minuten, bron, aantal beurten)."""
    per_prog = geleerd_per_programma(invoer.duur_per_programma, sleutel)
    if per_prog is not None and per_prog[0] >= invoer.min_duur:
        return per_prog[0], "programma", per_prog[1]
    if invoer.duur_apparaat is not None and invoer.duur_apparaat >= invoer.min_duur:
        return invoer.duur_apparaat, "apparaat", 0
    return None, "onbekend", 0


def _kwh(invoer: Invoer, sleutel: str | None) -> tuple[float, str]:
    per_prog = geleerd_per_programma(invoer.kwh_per_programma, sleutel)
    if per_prog is not None and per_prog[0] > 0:
        return per_prog[0], "gemeten per programma"
    return invoer.kwh_apparaat, invoer.kwh_herkomst


def _bruikbaar(toestand: str | None) -> bool:
    return toestand not in ONBRUIKBAAR


def bepaal(invoer: Invoer) -> dict:
    """De planning van één apparaat.

    `status`: "gepland", "draait", "klaar" of "niets".
    `start`/`eind`: ISO-tijden of None; `*_bron` zegt waar ze vandaan komen
    ("home_connect", "geleerd" of "eigen meting"). Een afgeleide tijd krijgt
    in `tekst` een "±".
    `in_reserve`: alleen bij "gepland" - de lopende cyclus zit al in de
    live meting.
    """
    nu = invoer.nu
    sleutel = programma_sleutel(invoer.programma)
    duur, duur_bron, duur_beurten = _duur(invoer, sleutel)
    kwh, kwh_herkomst = _kwh(invoer, sleutel)
    toestand = (invoer.hc_toestand or "").lower() or None
    hc_bekend = _bruikbaar(toestand)

    uit: dict = {
        "apparaat": invoer.naam,
        "status": "niets",
        "start": None,
        "eind": None,
        "start_bron": None,
        "eind_bron": None,
        "voortgang_procent": None,
        "voortgang_bron": None,
        "programma": sleutel,
        "programma_naam": programma_naam(sleutel),
        "duur_minuten": round(duur) if duur else None,
        "duur_bron": duur_bron,
        "duur_beurten": duur_beurten,
        "kwh": round(kwh, 2) if kwh else None,
        "kwh_herkomst": kwh_herkomst,
        "home_connect_toestand": toestand,
        "in_reserve": False,
        "prijs": None,
    }

    draait = (hc_bekend and toestand in HC_LOOPT) or invoer.ems_toestand == "actief"
    if draait and not (hc_bekend and toestand == HC_UITGESTELD):
        return _draait(uit, invoer, duur)

    start, eind = _gepland(invoer, toestand, hc_bekend, duur)
    if start is not None or eind is not None:
        uit["status"] = "gepland"
        uit["start"] = start["moment"].isoformat() if start else None
        uit["start_bron"] = start["bron"] if start else None
        uit["eind"] = eind["moment"].isoformat() if eind else None
        uit["eind_bron"] = eind["bron"] if eind else None
        # In de reserve: alleen als het begin nog komt en het binnen het
        # planvenster ligt.
        begin = start["moment"] if start else None
        uit["in_reserve"] = bool(
            begin is not None
            and begin > nu
            and (begin - nu).total_seconds() / 3600 <= PLAN_MAX_UREN
        )
        uit["prijs"] = _prijsoordeel(invoer, start, eind, duur, kwh)
        uit["tekst"] = _tekst_gepland(uit, start, eind, nu)
        return uit

    if invoer.ems_toestand == "klaar" and invoer.ems_klaar_sinds is not None:
        uren = (nu - invoer.ems_klaar_sinds).total_seconds() / 3600
        if 0 <= uren <= KLAAR_TONEN_UREN:
            uit["status"] = "klaar"
            uit["eind"] = invoer.ems_klaar_sinds.isoformat()
            uit["eind_bron"] = "eigen meting"
            uit["tekst"] = f"Klaar sinds {tijd_met_dag(invoer.ems_klaar_sinds, nu)}"
            return uit

    if hc_bekend and toestand == HC_UITGESTELD:
        uit["status"] = "gepland"
        uit["tekst"] = "Uitgestelde start, tijd nog niet bekend"
        return uit

    uit["tekst"] = "Niets gepland"
    return uit


def _gepland(invoer: Invoer, toestand, hc_bekend: bool, duur):
    """(start, eind) als dicts {moment, bron, afgeleid} of None."""
    nu = invoer.nu
    # Zegt Home Connect iets anders dan "uitgesteld", dan is er niets
    # gepland - ook al staat er nog een starttijd of eindtijd in een optie
    # (die blijft bij een gekozen programma soms staan).
    if hc_bekend and toestand != HC_UITGESTELD:
        return None, None

    start = None
    eind = None
    if invoer.hc_start_over_s is not None and invoer.hc_start_over_s > 0:
        start = {
            "moment": nu + timedelta(seconds=invoer.hc_start_over_s),
            "bron": "home_connect",
            "afgeleid": False,
        }
    if invoer.hc_eindtijd is not None and invoer.hc_eindtijd > nu:
        # Bij een uitgestelde start geeft Home Connect soms de eindtijd ALS
        # HIJ NU ZOU STARTEN; een eindtijd vóór het begin is die.
        if start is None or invoer.hc_eindtijd > start["moment"]:
            eind = {"moment": invoer.hc_eindtijd, "bron": "home_connect", "afgeleid": False}

    if start is None and eind is None:
        return None, None
    if duur:
        if start is not None and eind is None:
            eind = {
                "moment": start["moment"] + timedelta(minutes=duur),
                "bron": "geleerd",
                "afgeleid": True,
            }
        elif eind is not None and start is None:
            begin = eind["moment"] - timedelta(minutes=duur)
            # Ligt het begin al in het verleden, dan draait hij (of had hij
            # moeten draaien): niet als gepland tonen. Zonder Home Connect
            # was dat de regel van v1.70.0.
            if begin <= nu:
                if hc_bekend:
                    begin = nu
                else:
                    return None, None
            start = {"moment": begin, "bron": "geleerd", "afgeleid": True}
    elif start is None and not hc_bekend:
        # v1.70.0: zonder duur bleef de eindtijd staan als moment.
        start = {"moment": eind["moment"], "bron": "eindtijd", "afgeleid": True}
    if start is not None and (start["moment"] - nu).total_seconds() / 3600 > PLAN_MAX_UREN:
        return None, None
    return start, eind


def _draait(uit: dict, invoer: Invoer, duur) -> dict:
    nu = invoer.nu
    uit["status"] = "draait"
    begin = invoer.ems_gestart
    if begin is not None:
        uit["start"] = begin.isoformat()
        uit["start_bron"] = "eigen meting"
    eind = None
    if invoer.hc_eindtijd is not None and invoer.hc_eindtijd > nu - timedelta(minutes=5):
        eind = invoer.hc_eindtijd
        uit["eind_bron"] = "home_connect"
    elif begin is not None and duur:
        eind = begin + timedelta(minutes=duur)
        uit["eind_bron"] = "geleerd"
    if eind is not None:
        uit["eind"] = eind.isoformat()

    voortgang = invoer.hc_voortgang
    if voortgang is not None and 0 <= voortgang <= 100:
        uit["voortgang_procent"] = round(voortgang)
        uit["voortgang_bron"] = "home_connect"
    elif begin is not None and duur:
        verstreken = (nu - begin).total_seconds() / 60
        uit["voortgang_procent"] = round(min(99, max(0, 100 * verstreken / duur)))
        uit["voortgang_bron"] = "geleerd"

    delen = ["Draait"]
    if uit["programma_naam"]:
        delen[0] = f"Draait ({uit['programma_naam']})"
    if eind is not None:
        teken = "±" if uit["eind_bron"] == "geleerd" else ""
        delen.append(f"klaar {teken}{tijd_met_dag(eind, nu)}")
    if uit["voortgang_procent"] is not None:
        delen.append(f"{uit['voortgang_procent']}%")
    uit["tekst"] = " · ".join(delen)
    return uit


def _prijsoordeel(invoer: Invoer, start, eind, duur, kwh) -> dict | None:
    """Wat het gekozen moment kost, en of het binnen dezelfde eindtijd
    goedkoper kan. Alleen informatie."""
    if start is None or not duur or not kwh or not invoer.prijzen:
        return None
    kost = kosten_bij_start(invoer.prijzen, start["moment"], duur, kwh)
    if kost is None:
        return {"te_becijferen": False, "reden": "Prijzen dekken de cyclus nog niet."}
    oordeel = {
        "te_becijferen": True,
        "kosten_eur": round(kost, 2),
        "beste_start": None,
        "beste_kosten_eur": None,
        "besparing_eur": 0.0,
    }
    uiterlijk = eind["moment"] if eind is not None else start["moment"] + timedelta(minutes=duur)
    beste = goedkoopste_start(invoer.prijzen, invoer.nu, uiterlijk, duur, kwh)
    if beste is not None and kost - beste[1] >= PRIJS_VERSCHIL_MIN_EUR:
        oordeel["beste_start"] = beste[0].isoformat()
        oordeel["beste_kosten_eur"] = round(beste[1], 2)
        oordeel["besparing_eur"] = round(kost - beste[1], 2)
    return oordeel


def _eur(waarde: float) -> str:
    return f"€ {waarde:.2f}".replace(".", ",")


def _tekst_gepland(uit: dict, start, eind, nu: datetime) -> str:
    delen = []
    if start is not None:
        teken = "±" if start["afgeleid"] else ""
        delen.append(f"Start {teken}{tijd_met_dag(start['moment'], nu)}")
    if eind is not None:
        teken = "±" if eind["afgeleid"] else ""
        delen.append(f"klaar {teken}{tijd_met_dag(eind['moment'], nu)}")
    if not delen:
        return "Gepland"
    if uit["programma_naam"]:
        delen.append(uit["programma_naam"])
    prijs = uit.get("prijs") or {}
    if prijs.get("te_becijferen"):
        if prijs.get("beste_start"):
            beste = datetime.fromisoformat(prijs["beste_start"])
            delen.append(
                f"ca. {_eur(prijs['kosten_eur'])}; start {tijd_met_dag(beste, nu)} "
                f"zou {_eur(prijs['beste_kosten_eur'])} zijn"
            )
        else:
            delen.append(f"ca. {_eur(prijs['kosten_eur'])}, goedkoopste moment")
    tekst = " · ".join(delen)
    return tekst[0].upper() + tekst[1:]
