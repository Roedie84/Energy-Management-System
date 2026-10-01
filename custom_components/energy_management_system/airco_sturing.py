"""Automatische airco-sturing voor de woonkamer - de besluitregels (v5.27).

Gevraagd: "Ik wil dat het EMS al wel geschikt wordt voor automatische airco
sturing, echter nog niet actief (dus met aan/uit-knop)." En: "voor zowel
stand aan als uit kunnen zien wat de besluitvorming van het EMS zou zijn,
zodat ik hier al met jou over kan sparren."

Dus: elke ronde een BESLUIT, met de redenen erbij, ook als de knop uit
staat. Alleen met de knop aan wordt het uitgevoerd.

Het economische argument staat al in het verwarmingsadvies (v5.14):
warmte uit de airco kost bij een COP van 4,4 ongeveer de helft van warmte
uit gas, tot een stroomprijs van zo'n 83 ct. Zolang de airco de woonkamer op
temperatuur houdt, slaat de cv-thermostaat niet aan.

Geen rooster: "ik heb een standaard werkweek maar mijn vrouw en dochter
niet". De bestaande aanwezigheidsdetectie (bewegingssensoren, lampen, tv)
ziet wie er thuis is - wie dat ook is.

Alleen de woonkamer: "de airco in de slaapkamer verwarmt sowieso nooit."

Zuivere functies, zonder Home Assistant: los te toetsen en samen bij te
sturen.
"""
from __future__ import annotations

import statistics

# "Meer kans dan niet": vanaf deze kans telt een temperatuur als het moment
# waarop jullie de airco op verwarmen zetten.
KANS_MEER_DAN_NIET_PROCENT = 50.0


def aanzettemperatuur(bakjes: dict) -> float | None:
    """De hoogste temperatuur waarbij jullie de airco op verwarmen zetten.

    Uit de bestaande leercurve (`get_airco_kansen_per_bakje`): per graad de
    kans dat de airco binnen een uur aangaat, en in welke richting. Alleen
    bakjes met genoeg metingen, richting "verwarmen" en meer kans dan niet.
    None zolang dat nog nooit gezien is.
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
) -> dict:
    """Wat het EMS met de woonkamer-airco zou doen, en waarom.

    Volgorde van voorrang:
    1. geen meting                       -> niets
    2. jullie bedienen hem zelf          -> niets, tot de aanwezigheid verandert
    3. nog niet geleerd wanneer of waarop -> niets ("leert nog")
    4. niemand thuis, of iedereen slaapt -> uit, als het EMS hem aanzette
    5. gas is nu goedkoper               -> uit, als het EMS hem aanzette
    6. kouder dan de aanzettemperatuur   -> verwarmen tot de gewenste temperatuur
    7. anders                            -> niets

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
    redenen.append(f"jullie zetten hem op verwarmen onder {aanzet_c:.0f} °C")
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
            f"onder de {aanzet_c:.0f} °C waarbij jullie hem aanzetten.",
            redenen, doel_c, aanzet_c,
        )
    return _uitkomst(
        "niets",
        f"Warm genoeg: {woonkamer_c:.1f} °C, niet onder de {aanzet_c:.0f} °C.",
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
