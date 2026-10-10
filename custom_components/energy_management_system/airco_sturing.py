"""Automatische airco-sturing voor de woonkamer - de besluitregels (v5.27).

Gevraagd: "Ik wil dat het EMS al wel geschikt wordt voor automatische airco
sturing, echter nog niet actief (dus met aan/uit-knop)." En: "voor zowel
stand aan als uit kunnen zien wat de besluitvorming van het EMS zou zijn,
zodat ik hier al met jou over kan sparren."

Dus: elke ronde een BESLUIT, met de redenen erbij, ook als de knop uit
staat. Alleen met de knop aan wordt het uitgevoerd.

Het economische argument staat al in het verwarmingsadvies (v5.14):
warmte uit gas kost gasprijs / 8,8 per kWh, uit de airco stroomprijs / COP,
dus de cv wint pas boven een stroomprijs van gasprijs / 8,8 x COP. De COP
komt uit `slimme_bronnen.cop_bij`: de algemene lijn (3,0 bij 0 °C), of
sinds v5.59 de fabrieksopgave bij 7 °C als die is ingesteld. Zolang de
airco de woonkamer op temperatuur houdt, slaat de cv-thermostaat niet aan.

Geen rooster: "ik heb een standaard werkweek maar mijn vrouw en dochter
niet". De bestaande aanwezigheidsdetectie (bewegingssensoren, lampen, tv)
ziet wie er thuis is - wie dat ook is.

Alleen de woonkamer: "de airco in de slaapkamer verwarmt sowieso nooit."

Zuivere functies, zonder Home Assistant: los te toetsen en samen bij te
sturen.
"""
from __future__ import annotations

import statistics
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

# "Meer kans dan niet": vanaf deze kans telt een temperatuur als het moment
# waarop jullie de airco op verwarmen zetten.
KANS_MEER_DAN_NIET_PROCENT = 50.0


def een_decimaal(temp_c: float) -> float:
    """Een temperatuur op één decimaal, de helft naar boven (v5.60).

    Zoals de sensor de woonkamertemperatuur toont. Niet met Pythons
    `round`: die rondt een exacte helft naar het even cijfer af
    (round(19.25, 1) == 19.2), waardoor 19,25 °C in bakje 19,0 viel in
    plaats van 19,5. Via de decimale schrijfwijze, zodat 19.25 ook echt
    als 19,25 telt en niet als 19,2499999...
    """
    return float(
        Decimal(repr(float(temp_c))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    )


def temperatuurbakje(temp_c: float, bakgrootte_c: float = 0.5) -> str:
    """Het bakje waarin een woonkamertemperatuur valt (v5.58, v5.60).

    Sinds v5.60 per halve graad (LIVING_ROOM_TEMP_BUCKET_SIZE_C = 0,5, besluit
    Ruud 9 oktober 2026): de dichtstbijzijnde halve graad, de helft naar
    boven.

    Eerst op één decimaal (`een_decimaal`), zoals de sensor de temperatuur
    toont, zodat de leerstap en de sensor nooit een ander bakje kiezen. Dan
    naar de dichtstbijzijnde halve graad, een exacte helft (x,25 / x,75)
    naar boven:

        18,75-19,24 °C  ->  bakje "19.0"   (getoond: 18,8 tot en met 19,2)
        19,25-19,74 °C  ->  bakje "19.5"   (getoond: 19,3 tot en met 19,7)

    Dus 18,8 -> 19,0; 18,7 -> 18,5; 19,2 -> 19,0; 19,3 -> 19,5.

    Sleutels zijn tekst met één decimaal: "19.0", "19.5". Gerekend met
    Decimal, zodat er geen 19.499999 of 0.1-ruis in een sleutel komt. Met
    bakgrootte_c = 1.0 is het de indeling van v5.58 (hele graden).
    """
    t = Decimal(repr(een_decimaal(temp_c)))
    b = Decimal(repr(float(bakgrootte_c)))
    bakje = (t / b + Decimal("0.5")).to_integral_value(rounding=ROUND_FLOOR) * b
    return str(float(bakje))


def bakje_label(sleutel) -> str:
    """Hoe een bakje op het dashboard staat: "19.5" -> "19,5 °C" (v5.60)."""
    try:
        return f"{float(sleutel):.1f}".replace(".", ",") + " °C"
    except (TypeError, ValueError):
        return "—"


def aanzettemperatuur(bakjes: dict) -> float | None:
    """De hoogste temperatuur waarbij jullie de airco op verwarmen zetten.

    Uit de bestaande leercurve (`get_airco_kansen_per_bakje`): per bakje
    (sinds v5.60 een halve graad, dus ook 19,5 kan het antwoord zijn) de
    kans dat de airco binnen een uur aangaat, en in welke richting. Alleen
    bakjes met genoeg metingen, richting "verwarmen" en meer kans dan niet.
    None zolang dat nog nooit gezien is. De besluittekst toont hem met één
    decimaal (v5.60), anders verscheen 19,5 als 20.
    """
    kandidaten = []
    for sleutel, bakje in (bakjes or {}).items():
        if not bakje.get("voldoende_data"):
            continue
        if bakje.get("richting") != "verwarmen":
            continue
        if (bakje.get("probability_percent") or 0.0) < KANS_MEER_DAN_NIET_PROCENT:
            continue
        try:
            kandidaten.append(float(sleutel))
        except (TypeError, ValueError):
            continue
    return max(kandidaten) if kandidaten else None


def gewenste_temperatuur(setpunten: list, minimaal: int) -> float | None:
    """De temperatuur waarop jullie de airco zetten als hij verwarmt: de
    mediaan van wat jullie zelf kozen. None zolang er te weinig keuzes zijn."""
    waarden = [float(s) for s in (setpunten or []) if s is not None]
    if len(waarden) < minimaal:
        return None
    return round(statistics.median(waarden), 1)


def besluit(
    *,
    woonkamer_c: float | None,
    aanwezigheid: str | None,
    aanzet_c: float | None,
    doel_c: float | None,
    advies: str | None,
    handmatig: bool,
    airco_stand: str | None,
    door_ems_aan: bool,
    setpunten_gezien: int,
    setpunten_nodig: int,
    vooruit: dict | None = None,
) -> dict:
    """Wat het EMS met de woonkamer-airco zou doen, en waarom.

    Volgorde van voorrang:
    1. geen meting                       -> niets
    2. jullie bedienen hem zelf          -> niets, tot de aanwezigheid verandert
    3. nog niet geleerd wanneer of waarop -> niets ("leert nog")
    4. niemand thuis, of iedereen slaapt -> uit, als het EMS hem aanzette
    5. gas is nu goedkoper               -> uit, als het EMS hem aanzette
    6. kouder dan de aanzettemperatuur   -> verwarmen tot de gewenste temperatuur
    7. over een uur kouder dan de aanzettemperatuur volgens een projectie
       die nauwkeurig genoeg is (v5.64)  -> vooruit verwarmen
    8. anders                            -> niets

    Het EMS zet de airco alleen UIT als het hem zelf AANzette; wat een mens
    aanzette, laat het staan.
    """
    redenen: list[str] = []

    def uit_of_niets(reden: str) -> dict:
        redenen.append(reden)
        if door_ems_aan and airco_stand == "heat":
            return _uitkomst("uit", "Uitzetten: " + reden, redenen, doel_c, aanzet_c)
        return _uitkomst("niets", reden[0].upper() + reden[1:] + ".", redenen, doel_c, aanzet_c)

    if woonkamer_c is None:
        redenen.append("geen woonkamertemperatuur gemeten")
        return _uitkomst("niets", "Geen woonkamertemperatuur - niets doen.", redenen, doel_c, aanzet_c)
    redenen.append(f"woonkamer {woonkamer_c:.1f} °C")
    if handmatig:
        redenen.append("iemand bedient de airco zelf")
        return _uitkomst(
            "niets",
            "Jullie bedienen de airco zelf; het EMS blijft eraf tot de "
            "aanwezigheid verandert.",
            redenen, doel_c, aanzet_c,
        )
    if aanzet_c is None:
        redenen.append("nog nooit gezien bij welke temperatuur jullie gaan verwarmen")
        return _uitkomst(
            "niets",
            "Leert nog: het EMS heeft nog niet gezien bij welke temperatuur "
            "jullie de airco op verwarmen zetten.",
            redenen, doel_c, aanzet_c,
        )
    redenen.append(f"jullie zetten hem op verwarmen onder {aanzet_c:.1f} °C")
    if doel_c is None:
        redenen.append(
            f"gewenste temperatuur nog niet geleerd ({setpunten_gezien} van "
            f"{setpunten_nodig} keer gezien)"
        )
        return _uitkomst(
            "niets",
            "Leert nog: nog niet genoeg keer gezien op welke temperatuur "
            "jullie de airco zetten.",
            redenen, doel_c, aanzet_c,
        )
    redenen.append(f"gewenste temperatuur {doel_c:.1f} °C")
    if aanwezigheid != "thuis":
        stand = {"weg": "niemand thuis", "slaapt": "iedereen slaapt"}.get(
            aanwezigheid or "", "aanwezigheid onbekend"
        )
        return uit_of_niets(stand)
    redenen.append("er is iemand thuis")
    if advies != "airco":
        return uit_of_niets("gas is nu goedkoper dan de airco")
    redenen.append("de airco is goedkoper dan gas")
    if woonkamer_c < aanzet_c:
        if airco_stand == "heat":
            return _uitkomst("niets", "De airco verwarmt al.", redenen, doel_c, aanzet_c)
        return _uitkomst(
            "verwarmen",
            f"Verwarmen tot {doel_c:.1f} °C: het is {woonkamer_c:.1f} °C, "
            f"onder de {aanzet_c:.1f} °C waarbij jullie hem aanzetten.",
            redenen, doel_c, aanzet_c,
        )
    verwacht_c = (vooruit or {}).get("verwacht_c")
    if verwacht_c is not None and verwacht_c < aanzet_c:
        wind = (vooruit or {}).get("wind")
        redenen.append(
            f"over een uur naar verwachting {verwacht_c:.1f} °C"
            + (f" (wind {wind})" if wind else "")
        )
        if airco_stand == "heat":
            return _uitkomst("niets", "De airco verwarmt al.", redenen, doel_c, aanzet_c)
        return _uitkomst(
            "verwarmen",
            f"Vooruit verwarmen tot {doel_c:.1f} °C: nu {woonkamer_c:.1f} °C, over "
            f"een uur naar verwachting {verwacht_c:.1f} °C - onder de "
            f"{aanzet_c:.1f} °C waarbij jullie hem aanzetten.",
            redenen, doel_c, aanzet_c,
        )
    if (vooruit or {}).get("reden"):
        redenen.append(vooruit["reden"])
    elif verwacht_c is not None:
        redenen.append(f"over een uur naar verwachting {verwacht_c:.1f} °C")
    return _uitkomst(
        "niets",
        f"Warm genoeg: {woonkamer_c:.1f} °C, niet onder de {aanzet_c:.1f} °C.",
        redenen, doel_c, aanzet_c,
    )


def _uitkomst(actie, tekst, redenen, doel_c, aanzet_c) -> dict:
    return {
        "actie": actie,
        "tekst": tekst,
        "redenen": list(redenen),
        "redenen_tekst": " · ".join(redenen),
        "doel_c": doel_c,
        "aanzet_c": aanzet_c,
    }


# --- v5.66: voorverwarmen op goedkope stroom ---------------------------------

BUFFER_C = 0.5
BUFFER_VOORUIT_UREN = 3
BUFFER_MIN_VERSCHIL_EUR = 0.05
BUFFER_VERHOUDING = 0.8


def buffer(doel_c: float | None, prijs_nu: float | None, komende: list) -> dict:
    """Het huis als warmtebuffer (v5.66, gevraagd: "voorverwarmen op goedkope
    stroom").

    `komende`: de prijzen van de komende `BUFFER_VOORUIT_UREN` uur, na dit
    kwartier. Komt er een duur blok aan en is het nu duidelijk goedkoper
    (minstens 5 cent en hoogstens 80% van de duurste), dan een halve graad
    hoger: de kamer slaat warmte op voor straks. Is het nu juist het dure
    blok (de goedkoopste komende prijs is minstens 5 cent en 20% lager), dan
    een halve graad lager: de opgeslagen warmte opmaken en stoken als het
    weer goedkoop is. Daartussen: het gewone doel.

    Altijd binnen een halve graad van wat jullie zelf kiezen.
    """
    if doel_c is None or prijs_nu is None or not komende:
        return {"doel_c": doel_c, "reden": None}
    duurst = max(komende)
    goedkoopst = min(komende)
    if duurst - prijs_nu >= BUFFER_MIN_VERSCHIL_EUR and prijs_nu <= duurst * BUFFER_VERHOUDING:
        return {
            "doel_c": round(doel_c + BUFFER_C, 1),
            "reden": (
                f"voorverwarmen: nu {prijs_nu * 100:.0f} ct, straks tot "
                f"{duurst * 100:.0f} ct - een halve graad warmer"
            ),
        }
    if prijs_nu - goedkoopst >= BUFFER_MIN_VERSCHIL_EUR and goedkoopst <= prijs_nu * BUFFER_VERHOUDING:
        return {
            "doel_c": round(doel_c - BUFFER_C, 1),
            "reden": (
                f"duur kwartier: nu {prijs_nu * 100:.0f} ct, straks "
                f"{goedkoopst * 100:.0f} ct - een halve graad lager"
            ),
        }
    return {"doel_c": doel_c, "reden": None}


# --- v5.77: een raam open = de airco nooit aan -------------------------------


def ramen(toestanden: list) -> dict:
    """Welke ramen open staan, en welke onbekend zijn (v5.77).

    `toestanden`: (naam, toestand) per raamsensor. "on" is open - ook de
    ventilatiestand. "unknown"/"unavailable"/None telt NIET als open (een
    kapotte sensor mag de airco niet blokkeren), maar wordt wel genoemd.
    """
    open_, onbekend = [], []
    for naam, toestand in toestanden or []:
        if toestand == "on":
            open_.append(naam)
        elif toestand not in ("off",):
            onbekend.append(naam)
    return {"open": open_, "onbekend": onbekend}


def raam_open(
    uit: dict,
    raam: dict,
    *,
    airco_stand: str | None,
    door_ems_aan: bool,
    open_sinds_s: float | None = None,
    uitstel_s: float = 0,
) -> dict:
    """Het besluit met de ramen erbij (v5.77, Ruud 10-10).

    Na alle andere stappen (gewoon besluit, dagritme, thuiskomst,
    voorverwarmen), zodat geen enkele weg de airco aanzet of een hoger doel
    zet terwijl een raam open is. Staat de airco aan door het EMS, dan zet het
    EMS hem uit - net als de Home Assistant-automatisering die hetzelfde doet;
    beide zetten hem uit, dus er is geen gevecht. Een "uit" (bijvoorbeeld de
    vaste uittijd van 22:00) blijft staan.
    """
    redenen = list(uit.get("redenen") or [])
    if raam.get("onbekend"):
        redenen.append("raamsensor onbekend (telt niet als open): " + ", ".join(raam["onbekend"]))
    if not raam.get("open"):
        if redenen == list(uit.get("redenen") or []):
            return uit
        return dict(uit, redenen=redenen, redenen_tekst=" · ".join(redenen))
    reden = "raam open: " + ", ".join(raam["open"])
    redenen.append(reden)
    nieuw = dict(uit, redenen=redenen, redenen_tekst=" · ".join(redenen), raam_open=True)
    if uit.get("actie") == "uit":
        return nieuw
    if door_ems_aan and airco_stand == "heat":
        # v5.78 (Ruud 10-10 16:31): pas uit als het raam `uitstel_s` open is,
        # gelijk met de HA-automatisering (5 min). Aanzetten blijft geblokkeerd.
        if open_sinds_s is not None and open_sinds_s < uitstel_s:
            nog = max(1, round((uitstel_s - open_sinds_s) / 60))
            nieuw.update(actie="niets", tekst=f"Raam open: de airco gaat over {nog} min uit.")
        else:
            nieuw.update(actie="uit", tekst="Uitzetten: " + reden + ".")
    else:
        nieuw.update(actie="niets", tekst="Niet aanzetten: " + reden + ".")
    return nieuw
