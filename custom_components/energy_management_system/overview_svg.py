"""Een dynamisch overzichtsplaatje (v3.17.0).

Gevraagd: "Kunnen we het visuele dashboard dynamisch maken en kleinere
getallen (dus geen zon als het bewolkt is) etc. etc. Tevens wil ik dat op
alle devices het visuele dashboard goed zichtbaar is. Ook moeten zaken
klikbaar zijn zodat je naar gedetailleerdere informatie gaat. Tevens
stromen inzichtelijk maken."

De oude kaart was een STATISCHE SVG met `picture-elements` eroverheen,
met vaste pixelgroottes. Dat verklaart alle vier de klachten:

- de zon kon niet meebewegen met de bewolking, want hij zat in het
  plaatje;
- de getallen kwamen rauw uit de sensor - "0.2900598 €/kWh";
- vaste pixels schalen niet mee op een telefoon;
- en stromen waren niet te tekenen zonder de achtergrond te vervangen.

Deze module bouwt de hele plaat elke ronde opnieuw op, als tekst. Een
`viewBox` zonder vaste breedte schaalt vanzelf mee met de kaart, en
`<a>`-elementen maken onderdelen klikbaar.
"""
from __future__ import annotations


def _getal(waarde, eenheid: str = "", decimalen: int = 1) -> str:
    """Een leesbaar getal, of een streepje.

    Gemeld met een screenshot: "0.2900598 €/kWh" en "6,6528 kWh". Dat
    zijn rekenuitkomsten, geen getallen om naar te kijken.
    """
    if waarde is None:
        return "—"
    try:
        getal = float(waarde)
    except (TypeError, ValueError):
        return str(waarde)
    tekst = f"{getal:,.{decimalen}f}".replace(",", " ").replace(".", ",")
    return f"{tekst} {eenheid}".strip()


def _vermogen(watt) -> str:
    """Watt onder de kilowatt, anders kilowatt met één decimaal."""
    if watt is None:
        return "—"
    try:
        w = float(watt)
    except (TypeError, ValueError):
        return "—"
    if abs(w) < 1000:
        return f"{w:.0f} W"
    return _getal(w / 1000, "kW", 1)


def zon_icoon(bewolking, opwek_w) -> tuple[str, str]:
    """Welk weerbeeld hoort hierbij? (v3.17.0)

    Gemeld: "geen zon als het bewolkt is". Op het screenshot stond een
    stralende zon bij 99,6% bewolking.

    De bewolking bepaalt het beeld, niet de opwek: 's avonds is er geen
    opwek terwijl het helder kan zijn.
    """
    try:
        dekking = float(bewolking) if bewolking is not None else None
    except (TypeError, ValueError):
        dekking = None

    if dekking is None:
        return "zon", "#f9d423"
    if dekking >= 85:
        return "bewolkt", "#8fa3b0"
    if dekking >= 50:
        return "halfbewolkt", "#c8ccd4"
    if dekking >= 20:
        return "licht bewolkt", "#f0d78c"
    return "zon", "#f9d423"


def _zon_svg(x: float, y: float, soort: str, kleur: str) -> str:
    """Tekent zon, wolk of iets ertussenin."""
    if soort == "bewolkt":
        return (
            f'<g transform="translate({x},{y})">'
            f'<ellipse cx="0" cy="4" rx="30" ry="16" fill="{kleur}"/>'
            f'<circle cx="-14" cy="-2" r="14" fill="{kleur}"/>'
            f'<circle cx="8" cy="-6" r="18" fill="{kleur}"/>'
            "</g>"
        )
    stralen = "".join(
        f'<line x1="0" y1="-26" x2="0" y2="-34" stroke="{kleur}" '
        f'stroke-width="4" stroke-linecap="round" '
        f'transform="rotate({hoek})"/>'
        for hoek in range(0, 360, 45)
    )
    zon = (
        f'<g transform="translate({x},{y})">'
        f'<circle cx="0" cy="0" r="18" fill="{kleur}"/>{stralen}'
    )
    if soort in ("halfbewolkt", "licht bewolkt"):
        zon += (
            '<ellipse cx="10" cy="12" rx="26" ry="13" fill="#8fa3b0"/>'
            '<circle cx="-4" cy="8" r="11" fill="#8fa3b0"/>'
        )
    return zon + "</g>"


def _pijl(
    x1: float, y1: float, x2: float, y2: float, watt, kleur: str
) -> str:
    """Een stroompijl waarvan de dikte het vermogen volgt (v3.17.0).

    Gevraagd: "stromen inzichtelijk maken (bijvoorbeeld stroom van PV
    naar huis of accu etc)".

    Bij nul vermogen wordt er niets getekend - een pijl die altijd staat
    zegt niets.
    """
    try:
        w = abs(float(watt or 0))
    except (TypeError, ValueError):
        return ""
    if w < 25:
        return ""
    dikte = min(9.0, 1.5 + w / 400)
    duur = max(1.2, 4.0 - w / 800)
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{kleur}" '
        f'stroke-width="{dikte:.1f}" stroke-linecap="round" opacity="0.75" '
        f'stroke-dasharray="10 14">'
        f'<animate attributeName="stroke-dashoffset" from="24" to="0" '
        f'dur="{duur:.1f}s" repeatCount="indefinite"/>'
        "</line>"
    )


# Waar de vier blokken staan. Eén viewBox van 1000 breed; de kaart
# schaalt daar zelf naartoe, dus dit werkt op elk scherm.
_PAD = "/energy-management-system"


def _blok(
    x: float,
    y: float,
    breedte: float,
    hoogte: float,
    titel: str,
    regels: list[tuple[str, str]],
    kleur: str,
    doel: str | None = None,
) -> str:
    """Eén kaartje, klikbaar als er een doel is."""
    inhoud = (
        f'<rect x="{x}" y="{y}" width="{breedte}" height="{hoogte}" rx="14" '
        f'fill="#1c2128" stroke="{kleur}" stroke-opacity="0.45"/>'
        f'<text x="{x + 18}" y="{y + 30}" fill="{kleur}" font-size="17" '
        f'font-weight="600" letter-spacing="1.5">{titel}</text>'
    )
    regel_y = y + 62
    for label, waarde in regels:
        inhoud += (
            f'<text x="{x + 18}" y="{regel_y}" fill="#8b98a5" '
            f'font-size="13">{label}</text>'
            f'<text x="{x + 18}" y="{regel_y + 26}" fill="#e8edf2" '
            f'font-size="24" font-weight="600">{waarde}</text>'
        )
        regel_y += 58
    if doel:
        return f'<a href="{_PAD}/{doel}">{inhoud}</a>'
    return inhoud


def bouw_overzicht(gegevens: dict) -> str:
    """Bouwt het hele overzicht als SVG-tekst (v3.17.0).

    Eén `viewBox`, geen vaste breedte: de kaart schaalt mee met het
    scherm. Dat was de derde klacht - vaste pixelgroottes zijn op een
    telefoon onleesbaar.
    """
    bewolking = gegevens.get("bewolking")
    soort, zonkleur = zon_icoon(bewolking, gegevens.get("pv_w"))

    delen = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        'viewBox="0 0 1000 520" width="100%" '
        'font-family="system-ui, sans-serif">',
        '<rect width="1000" height="520" rx="16" fill="#0f1419"/>',
    ]

    # --- kop -----------------------------------------------------------
    status = gegevens.get("status") or "onbekend"
    statuskleur = {
        "goed": "#3ecf8e",
        "aandacht_gewenst": "#f0b429",
    }.get(status, "#8b98a5")
    delen.append(
        f'<a href="{_PAD}/detail-gezondheid">'
        f'<text x="32" y="44" fill="#8b98a5" font-size="14" '
        f'letter-spacing="2">ENERGY MANAGEMENT SYSTEM</text>'
        f'<text x="32" y="78" fill="{statuskleur}" font-size="30" '
        f'font-weight="700">{status.replace("_", " ").capitalize()}</text>'
        "</a>"
    )

    # --- stromen, achter de blokken -------------------------------------
    #
    # Van links naar rechts: zon -> huis, huis <-> accu, huis <-> net.
    pv_w = gegevens.get("pv_w") or 0
    accu_w = gegevens.get("accu_w") or 0
    net_w = gegevens.get("net_w") or 0
    delen.append(_pijl(250, 210, 390, 210, pv_w, "#f9d423"))
    delen.append(_pijl(610, 210, 750, 210, net_w, "#5aa9e6"))
    delen.append(_pijl(500, 300, 500, 380, accu_w, "#3ecf8e"))

    # --- de vier blokken ------------------------------------------------
    delen.append(
        _blok(
            32, 120, 218, 190, "ZON",
            [
                ("Opwek nu", _vermogen(pv_w)),
                ("Bewolking", _getal(bewolking, "%", 0)),
                ("Resterend vandaag", _getal(gegevens.get("zon_rest"), "kWh", 1)),
            ],
            "#f9d423", "detail-zon",
        )
    )
    delen.append(_zon_svg(196, 176, soort, zonkleur))

    delen.append(
        _blok(
            282, 120, 436, 190, "HUIS",
            [
                ("Verbruik nu", _vermogen(gegevens.get("huis_w"))),
                ("Grootste verbruiker", str(gegevens.get("grootste") or "—")),
            ],
            "#e8edf2", "detail-kwartier",
        )
    )
    delen.append(
        _blok(
            750, 120, 218, 190, "NET",
            [
                ("Netstroom", _vermogen(net_w)),
                ("Prijs nu", _getal(gegevens.get("prijs_ct"), "ct/kWh", 1)),
                ("Drempel duur", _getal(gegevens.get("drempel_ct"), "ct/kWh", 1)),
            ],
            "#5aa9e6", "detail-kwartier",
        )
    )

    delen.append(
        _blok(
            32, 340, 218, 156, "BESLUIT",
            [
                ("Verwachte modus", str(gegevens.get("modus") or "—")),
                ("Dure kwartieren", _getal(gegevens.get("dure_kwartieren"), "", 0)),
            ],
            "#b088f9", "detail-planning",
        )
    )
    delen.append(
        _blok(
            282, 340, 436, 156, "THUISACCU",
            [
                ("Lading", _getal(gegevens.get("soc"), "%", 0)),
                ("Beschikbaar", _getal(gegevens.get("beschikbaar_kwh"), "kWh", 2)),
            ],
            "#3ecf8e", "detail-accu",
        )
    )
    delen.append(
        _blok(
            750, 340, 218, 156, "BEWAKING",
            [
                ("Sensor-gezondheid", _getal(gegevens.get("sensor_gezondheid"), "%", 0)),
                ("Sluipverbruik", str(gegevens.get("sluipverbruik") or "—")),
            ],
            "#f0b429", "detail-gezondheid",
        )
    )

    # De koeling erbij op de accuregel: die hoort bij de accu en het
    # blok had er ruimte voor.
    delen.append(
        f'<text x="300" y="472" fill="#8b98a5" font-size="13">Koeling</text>'
        f'<text x="300" y="492" fill="#e8edf2" font-size="17">'
        f'{gegevens.get("koeling") or "—"} · '
        f'{_getal(gegevens.get("omvormer_c"), "°C", 0)}</text>'
    )

    delen.append("</svg>")
    return "".join(delen)

# --- SCADA-stijl (v3.17.0) -------------------------------------------
# Gevraagd naar aanleiding van een schermafbeelding van een Grid Support
# Unit: halve-cirkelmeters met één groot getal, staafjes per accupakket,
# een enkelkleurschema met rood alleen voor alarmen.
#
# Overgenomen wat daar werkt:
#   - de meter zegt in één blik waar je staat op een schaal;
#   - staafjes naast elkaar tonen een uitschieter meteen (module 1 loopt
#     al een week uit de pas);
#   - één kleur, zodat rood iets betekent.
#
# NIET overgenomen: meters voor vaste getallen. Op het voorbeeld staat
# "Power capacity 413 kW" in een halve cirkel, en dat is versiering - een
# waarde die nooit beweegt hoort geen meter te krijgen.

KLEUR_LIJN = "#2b7c9e"
KLEUR_ACCENT = "#4fc3f7"
KLEUR_VLAK = "#0e2733"
KLEUR_TEKST = "#cfe8f3"
KLEUR_ZWAK = "#6b8fa3"
KLEUR_ALARM = "#e05252"
KLEUR_GOED = "#5fd38d"


def _meter(
    x: float,
    y: float,
    waarde,
    minimum: float,
    maximum: float,
    label: str,
    eenheid: str = "",
    straal: float = 38.0,
    alarm_boven: float | None = None,
) -> str:
    """Een halve-cirkelmeter met het getal in het midden.

    De boog loopt van links (minimum) naar rechts (maximum). Ontbreekt
    de waarde, dan blijft de boog leeg en staat er een streepje - beter
    dan een naald op nul, want dat lijkt een meting.
    """
    import math

    # v3.18.0: de achtergrondboog duidelijk zichtbaar.
    #
    # Gemeld: "deze ook nog niet correct uitgelijnd". De teksten stonden
    # wél gelijk, maar de BOGEN niet: 87% en 81% vullen bijna de hele
    # halve cirkel, 36% blijft links hangen. Dan lijkt de middelste meter
    # lager en kleiner, terwijl hij op dezelfde hoogte staat.
    #
    # Met een zichtbare achtergrondboog zie je altijd de volle cirkel en
    # verschilt alleen de vulling - dat is wat een meter hoort te doen.
    achtergrond = (
        f'<path d="M {x - straal} {y} A {straal} {straal} 0 0 1 '
        f'{x + straal} {y}" fill="none" stroke="{KLEUR_LIJN}" '
        f'stroke-opacity="0.28" stroke-width="9" stroke-linecap="round"/>'
    )

    if waarde is None:
        return (
            f'{achtergrond}'
            f'<text x="{x}" y="{y - 6}" text-anchor="middle" '
            f'font-size="20" fill="{KLEUR_ZWAK}">--</text>'
            f'<text x="{x}" y="{y + 16}" text-anchor="middle" '
            f'font-size="10" fill="{KLEUR_ZWAK}">{label}</text>'
        )

    deel = max(0.0, min(1.0, (float(waarde) - minimum) / (maximum - minimum)))
    hoek = math.pi * (1 - deel)
    ex = x + straal * math.cos(hoek)
    ey = y - straal * math.sin(hoek)
    groot = 1 if deel > 0.5 else 0
    kleur = (
        KLEUR_ALARM
        if alarm_boven is not None and float(waarde) >= alarm_boven
        else KLEUR_ACCENT
    )

    boog = (
        f'<path d="M {x - straal} {y} A {straal} {straal} 0 {groot} 1 '
        f'{ex:.1f} {ey:.1f}" fill="none" stroke="{kleur}" '
        f'stroke-width="9" stroke-linecap="round"/>'
    )
    # De schaalgrenzen erbij: zonder die twee getallen is niet te zien
    # of 26 laag of hoog is.
    # v3.20.0: naar buiten geschoven en met een decimaal waar dat nodig
    # is.
    #
    # Gemeld: "dit nog niet netjes op het overzicht". Twee fouten: de
    # getallen stonden op x ± straal, precies onder de uiteinden van de
    # boog, en 8,6 kWh werd afgerond weergegeven als "9" - een grens die
    # niet klopt.
    def _grens(waarde) -> str:
        # Onder tien telt de decimaal: 8,6 is niet 9.
        return _getal(waarde, "", 1 if abs(waarde) < 10 else 0)

    grenzen = (
        f'<text x="{x - straal - 3}" y="{y + 7}" text-anchor="end" '
        f'font-size="6.5" fill="{KLEUR_ZWAK}" fill-opacity="0.6">'
        f'{_grens(minimum)}</text>'
        f'<text x="{x + straal + 3}" y="{y + 7}" text-anchor="start" '
        f'font-size="6.5" fill="{KLEUR_ZWAK}" fill-opacity="0.6">'
        f'{_grens(maximum)}</text>'
    )
    return (
        f'{achtergrond}{boog}{grenzen}'
        f'<text x="{x}" y="{y - 6}" text-anchor="middle" font-size="22" '
        f'font-weight="600" fill="{KLEUR_TEKST}">{_getal(waarde, "", 0)}'
        f'<tspan font-size="11" fill="{KLEUR_ZWAK}"> {eenheid}</tspan></text>'
        f'<text x="{x}" y="{y + 26}" text-anchor="middle" font-size="10" '
        f'fill="{KLEUR_ZWAK}">{label}</text>'
    )


def _staafjes(
    x: float,
    y: float,
    waarden: list,
    labels: list,
    hoogte: float = 54.0,
    breedte: float = 16.0,
    tussen: float = 26.0,
    eenheid: str = "",
    alarm_boven: float | None = None,
) -> str:
    """Staafjes naast elkaar - een uitschieter valt meteen op.

    Dat is precies waarvoor dit nodig is: module 1 loopt al een week uit
    de pas, en in een tabel zie je dat pas als je de getallen vergelijkt.
    """
    echte = [w for w in waarden if w is not None]
    if not echte:
        return (
            f'<text x="{x}" y="{y}" font-size="10" fill="{KLEUR_ZWAK}">'
            "geen modulegegevens</text>"
        )

    # v3.17.1: vanaf NUL schalen, niet vanaf de laagste meting.
    #
    # Bij drie gelijke waarden gaf de oude opzet drie minimale staafjes -
    # dat oogt als "bijna niets" terwijl het "allemaal gelijk" betekent.
    # En bij 31/28/27 graden werd het verschil van vier graden uitvergroot
    # tot de volle hoogte, wat een alarm suggereert dat er niet is.
    #
    # Vanaf nul is de verhouding eerlijk: gelijke waarden geven gelijke
    # staafjes, en een uitschieter blijft zichtbaar omdat hij als enige
    # de accentkleur krijgt.
    hoog = max(echte)
    laag = 0.0
    spanne = max(hoog, 1e-6)
    delen = []
    for i, (w, naam) in enumerate(zip(waarden, labels)):
        bx = x + i * tussen
        if w is None:
            delen.append(
                f'<rect x="{bx}" y="{y - 4}" width="{breedte}" height="4" '
                f'rx="2" fill="{KLEUR_VLAK}"/>'
            )
            continue
        # Relatief binnen de gemeten spreiding, met een bodem zodat een
        # gelijke rij niet als nul verdwijnt.
        h = max(3.0, hoogte * (w - laag) / spanne)
        kleur = (
            KLEUR_ALARM
            if alarm_boven is not None and w >= alarm_boven
            else (KLEUR_ACCENT if w == hoog and hoog > laag else KLEUR_LIJN)
        )
        delen.append(
            f'<rect x="{bx}" y="{y - h:.1f}" width="{breedte}" '
            f'height="{h:.1f}" rx="2" fill="{kleur}"/>'
            f'<text x="{bx + breedte / 2}" y="{y + 12}" text-anchor="middle" '
            f'font-size="9" fill="{KLEUR_ZWAK}">{_getal(w, eenheid, 0)}</text>'
            f'<text x="{bx + breedte / 2}" y="{y + 22}" text-anchor="middle" '
            f'font-size="8" fill="{KLEUR_ZWAK}">{naam}</text>'
        )
    return "".join(delen)


def _kader(x, y, b, h, titel: str) -> str:
    """Een omkaderd blok met een kopje, zoals op het voorbeeld."""
    return (
        f'<rect x="{x}" y="{y}" width="{b}" height="{h}" rx="6" '
        f'fill="{KLEUR_VLAK}" fill-opacity="0.45" stroke="{KLEUR_LIJN}" '
        f'stroke-opacity="0.5"/>'
        f'<text x="{x + 12}" y="{y + 17}" font-size="10" '
        f'fill="{KLEUR_ZWAK}" letter-spacing="1">{titel.upper()}</text>'
    )

def bouw_scada(g: dict) -> str:
    """Het overzicht in drie kolommen (v3.21.0).

    Indeling op verzoek: "2 blokken links, 2 blokken midden, status per
    onderwerp rechts."

    Links accu en installatie, midden vermogen en vandaag, rechts de
    statuslijst over de volle hoogte. Onderaan een balk over de hele
    breedte voor koeling en planning.

    Alles wat hier staat BEWEEGT. Een meter voor een vast getal is
    versiering, en die staat er dus niet in.
    """
    accu_w = g.get("accu_w")
    laadt = accu_w is not None and accu_w > 0

    # Drie kolommen binnen 760: 232 + 232 + 232 met 16 marge en 12
    # tussenruimte.
    # Twee kolommen van 360 breed, want de status staat er niet meer
    # naast.
    L, M, KB = 16, 392, 352

    inhoud_h = 240
    hoogte = 44 + inhoud_h + 64

    d = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 {hoogte}" '
        f'width="100%" role="img" aria-label="Overzicht accu-installatie">',
        f'<rect width="760" height="{hoogte}" rx="10" fill="#081820"/>',
    ]

    # --- kop --------------------------------------------------------
    d.append(
        f'<text x="20" y="27" font-size="11.5" fill="{KLEUR_ACCENT}" '
        f'letter-spacing="2">ENERGY MANAGEMENT SYSTEM</text>'
    )
    status = (g.get("status") or "").replace("_", " ")
    statuskleur = KLEUR_GOED if status == "goed" else KLEUR_ALARM
    d.append(
        f'<circle cx="732" cy="23" r="4.5" fill="{statuskleur}"/>'
        f'<text x="722" y="27" text-anchor="end" font-size="9.5" '
        f'fill="{KLEUR_ZWAK}">{status or "onbekend"}</text>'
    )

    # ================= LINKS: accu + installatie ====================
    # v3.21.1: drie meters op ÉÉN rij.
    #
    # Gemeld: "dat ziet er al een heel stuk beter uit, alleen nog steeds
    # die gauges." Twee boven en één eronder was asymmetrisch, en het
    # label van de onderste viel bovendien BUITEN het kader: y 176 + 26
    # is 202, terwijl het kader op 194 eindigt.
    #
    # Drie meters van straal 22 op 56/120/184 binnen een kolom van 240:
    # elk 44 breed, met 20 pixels tussenruimte. De schaalgrenzen staan
    # ernaast en die hebben ook plek nodig, dus kleiner dan hiervoor.
    # v3.22.0: getallen met een balkje, geen halve cirkels meer.
    d.append(_kader(L, 44, KB, 84, "accu"))
    for x, waarde, mn, mx, label, eenheid, alarm in (
        (L + 16, g.get("soc"), 0, 100, "accustand", "%", None),
        (L + 130, g.get("omvormer_c"), 10, 55, "omvormer", "°C", 45),
        (L + 244, g.get("beschikbaar_kwh"), 0, 8.6, "beschikbaar", "kWh", None),
    ):
        d.append(
            _balkje(
                x, 84, waarde, mn, mx, label, eenheid,
                breedte=92.0, alarm_boven=alarm,
            )
        )

    # v3.22.0: het schema compacter. Drie blokken op een rij met de
    # accu eronder gaf veel lucht; nu twee rijen dicht op elkaar.
    d.append(_kader(L, 136, KB, 148, "installatie"))
    for naam, x, y, w in (
        ("zon", L + 92, 178, g.get("pv_w")),
        ("net", L + 260, 178, g.get("net_w")),
        ("huis", L + 92, 244, g.get("huis_w")),
        ("accu", L + 260, 244, g.get("accu_w")),
    ):
        kleur = KLEUR_ACCENT if naam == "accu" else KLEUR_LIJN
        d.append(
            f'<rect x="{x - 44}" y="{y - 18}" width="88" height="36" rx="5" '
            f'fill="none" stroke="{kleur}" stroke-opacity="0.7"/>'
            f'<text x="{x}" y="{y}" text-anchor="middle" font-size="12.5" '
            f'fill="{KLEUR_TEKST}">{_vermogen(w)}</text>'
            f'<text x="{x}" y="{y + 13}" text-anchor="middle" '
            f'font-size="8.5" fill="{KLEUR_ZWAK}">{naam}</text>'
        )
    # v3.22.1: bewegende stroompijlen tussen de blokken.
    #
    # Gevraagd: "Bewegen er nu ook richtingspijlen in het installatie
    # gedeelte?" - nee, en dat was een gemis. De pijlfunctie bestond al
    # sinds v3.17.0 maar werd na de herindeling niet meer gebruikt.
    #
    # De DIKTE volgt het vermogen en de SNELHEID ook: bij veel stroom
    # lopen de streepjes sneller. Onder 25 W wordt er niets getekend -
    # een pijl die altijd staat zegt niets.
    #
    # De richting volgt de werkelijkheid: levert het net (import), dan
    # loopt de pijl naar beneden; lever je terug, dan omhoog. Hetzelfde
    # voor de accu.
    net_w = g.get("net_w")
    accu_w = g.get("accu_w")
    d.append(
        f'<line x1="{L + 92}" y1="196" x2="{L + 92}" y2="226" '
        f'stroke="{KLEUR_LIJN}" stroke-opacity="0.25" stroke-width="1"/>'
        f'<line x1="{L + 260}" y1="196" x2="{L + 260}" y2="226" '
        f'stroke="{KLEUR_LIJN}" stroke-opacity="0.25" stroke-width="1"/>'
        f'<line x1="{L + 92}" y1="211" x2="{L + 260}" y2="211" '
        f'stroke="{KLEUR_LIJN}" stroke-opacity="0.25" stroke-width="1"/>'
    )
    # Zon naar beneden: die levert altijd.
    d.append(_pijl(L + 92, 196, L + 92, 226, g.get("pv_w"), KLEUR_GOED))
    # Net: naar beneden bij afname, omhoog bij teruglevering.
    if net_w:
        if net_w > 0:
            d.append(_pijl(L + 260, 196, L + 260, 226, net_w, "#e0a852"))
        else:
            d.append(_pijl(L + 260, 226, L + 260, 196, net_w, KLEUR_GOED))
    # Accu: naar het blok toe bij laden, ervandaan bij ontladen.
    if accu_w:
        if accu_w > 0:
            d.append(_pijl(L + 176, 211, L + 260, 226, accu_w, KLEUR_ACCENT))
        else:
            d.append(_pijl(L + 260, 226, L + 176, 211, accu_w, KLEUR_ACCENT))
    # En naar het huis.
    d.append(_pijl(L + 176, 211, L + 92, 226, g.get("huis_w"), KLEUR_TEKST))

    # ================= MIDDEN: vermogen + vandaag ===================
    d.append(_kader(M, 44, KB, 122, "vermogen"))
    d.append(
        f'<text x="{M + 176}" y="98" text-anchor="middle" font-size="32" '
        f'font-weight="600" fill="{KLEUR_TEKST}">'
        f'{abs(accu_w or 0):.0f}<tspan font-size="14" fill="{KLEUR_ZWAK}">'
        " W</tspan></text>"
    )
    d.append(
        f'<text x="{M + 176}" y="116" text-anchor="middle" font-size="10" '
        f'fill="{KLEUR_ACCENT}">'
        f'{"LADEN" if laadt else "ONTLADEN" if accu_w else "RUST"}</text>'
    )
    prijs, accu_ct = g.get("prijs_ct"), g.get("accu_ct")
    for j, (label, waarde) in enumerate(
        (("stroomprijs nu", prijs), ("kWh uit de accu", accu_ct))
    ):
        d.append(
            f'<text x="{M + 14}" y="{136 + j * 14}" font-size="9" '
            f'fill="{KLEUR_ZWAK}">{label}</text>'
            f'<text x="{M + KB - 14}" y="{136 + j * 14}" text-anchor="end" '
            f'font-size="9.5" fill="{KLEUR_TEKST}">'
            f'{_getal(waarde, "ct", 1) if waarde else "--"}</text>'
        )
    d.append(
        f'<text x="{M + 14}" y="160" font-size="9" fill="{KLEUR_LIJN}">'
        f'{_kort(str(g.get("reden") or ""), 36)}</text>'
    )

    d.append(_kader(M, 176, KB, 108, "vandaag"))
    for j, (label, waarde, naast) in enumerate(
        (
            ("opgewekt", g.get("opgewekt_kwh"), g.get("voorspeld_kwh")),
            ("verbruikt", g.get("verbruik_kwh"), None),
            ("van het net", g.get("import_kwh"), None),
            ("waarvan in de accu", g.get("netlading_kwh"), None),
            ("teruggeleverd", g.get("export_kwh"), None),
            ("zelfvoorziening", g.get("zelfvoorziening_pct"), None),
        )
    ):
        yy = 200 + j * 15
        if label == "zelfvoorziening":
            tekst = _getal(waarde, "%", 0) if waarde is not None else "--"
        else:
            tekst = _getal(waarde, "kWh", 1) if waarde is not None else "--"
            if naast:
                tekst += f' / {_getal(naast, "", 1)}'
        d.append(
            f'<text x="{M + 14}" y="{yy}" font-size="9.5" '
            f'fill="{KLEUR_ZWAK}">{label}</text>'
            f'<text x="{M + KB - 14}" y="{yy}" text-anchor="end" '
            f'font-size="10" fill="{KLEUR_TEKST}">{tekst}</text>'
        )

    # v3.23.0: de statuskolom staat niet meer IN de plaat.
    #
    # De opschoner van de markdown-kaart accepteert `<a>` binnen SVG
    # niet en toont dan het hele blok als platte tekst. Gevraagd is om
    # het klikbaar te HOUDEN, dus staan de statusblokken nu als echte
    # tegels onder de plaat - die werken gegarandeerd.

    # ================= ONDERBALK ====================================
    balk_y = 44 + inhoud_h + 8
    d.append(_kader(16, balk_y, 728, 50, "koeling en planning"))
    koeling = g.get("koeling") or {}
    aan = koeling.get("ventilator_aan")
    d.append(
        f'<circle cx="40" cy="{balk_y + 33}" r="6" fill="'
        f'{KLEUR_ACCENT if aan else KLEUR_VLAK}" stroke="{KLEUR_LIJN}"/>'
        f'<text x="56" y="{balk_y + 37}" font-size="10" fill="{KLEUR_TEKST}">'
        f'ventilator {"draait" if aan else "uit"}</text>'
    )
    buiten = koeling.get("buiten_c")
    if buiten is not None:
        d.append(
            f'<text x="190" y="{balk_y + 37}" font-size="10" '
            f'fill="{KLEUR_ZWAK}">buiten {_getal(buiten, "°C", 1)}</text>'
        )
    tekort = g.get("tekort_kwartieren")
    if tekort is not None:
        kleur = KLEUR_ALARM if tekort else KLEUR_GOED
        d.append(
            f'<text x="310" y="{balk_y + 37}" font-size="10" fill="{kleur}">'
            f'{tekort} tekortkwartier(en)</text>'
        )
    verkoop = g.get("verkoopkwartieren")
    if verkoop is not None:
        d.append(
            f'<text x="460" y="{balk_y + 37}" font-size="10" '
            f'fill="{KLEUR_ZWAK}">{verkoop} verkoopkwartieren</text>'
        )
    groot = g.get("grootverbruiker")
    if isinstance(groot, dict):
        groot = groot.get("naam")
    if groot:
        d.append(
            f'<text x="728" y="{balk_y + 37}" text-anchor="end" '
            f'font-size="10" fill="{KLEUR_ZWAK}">grootste: '
            f'{_kort(str(groot), 20)}</text>'
        )

    d.append("</svg>")
    return "".join(d)


def _tekstregel(x: float, y: float, label: str, waarde: str, kleur=None) -> str:
    """Een label links, een waarde rechts uitgelijnd."""
    return (
        f'<text x="{x}" y="{y}" font-size="10" fill="{KLEUR_ZWAK}">{label}</text>'
        f'<text x="{x + 210}" y="{y}" text-anchor="end" font-size="10" '
        f'fill="{kleur or KLEUR_TEKST}">{waarde}</text>'
    )


def bouw_secties(g: dict) -> str:
    """Drie kolommen met de cijfers achter de plaat (v3.18.0).

    Gevraagd: "Tevens mag er wat meer relevante informatie op, misschien
    3 secties naast elkaar welke wat meer info geven."

    De plaat toont de TOESTAND - wat er nu gebeurt. Deze secties tonen
    het VERHAAL: waar de dag heen gaat, wat de accu kost, en hoe
    betrouwbaar de cijfers zijn.

    Alles hier komt uit gegevens die de integratie toch al bijhoudt; er
    wordt niets extra berekend.
    """
    d = []
    d.append(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 210" '
        'width="100%" role="img" aria-label="Cijfers bij het overzicht">'
    )
    d.append('<rect width="760" height="210" rx="10" fill="#081820"/>')

    kolom_b = 234
    for i, (titel, regels) in enumerate(g.get("secties") or []):
        x = 16 + i * (kolom_b + 12)
        d.append(_kader(x, 12, kolom_b, 186, titel))
        for j, regel in enumerate(regels[:8]):
            label, waarde, kleur = regel
            d.append(
                _tekstregel(x + 12, 46 + j * 19, label, waarde, kleur)
            )

    d.append("</svg>")
    return "".join(d)

# Welk pad hoort bij welk onderwerp, en hoe het heet op het scherm.
ONDERWERP_PADEN = {
    "zon": ("PV / zon", "detail-zon"),
    "accumodules": ("Accumodules", "detail-accu"),
    "apparaten": ("Apparaten", "detail-apparaten"),
    "zelflerend": ("Zelflerend", "detail-kwaliteit"),
    "financieel": ("Financieel", "detail-kosten"),
    "klimaat": ("Klimaat", "detail-klimaat"),
    "water": ("Water", "detail-water"),
    "meetkwaliteit": ("Meetkwaliteit", "detail-betrouwbaarheid"),
    "zelfcontrole": ("Zelfcontrole", "detail-zelfcontrole"),
    "planning": ("Planning", "detail-planning"),
}

NIVEAU_KLEUR = {
    "betrouwbaar": KLEUR_GOED,
    "indicatief": "#e0a852",
    "onvoldoende_data": KLEUR_ZWAK,
    "onbetrouwbaar": KLEUR_ALARM,
}


def _wikkel(inhoud: str, pad: str | None) -> str:
    """v3.23.0: GEEN links meer in de SVG.

    Gemeld met een schermafbeelding waarop de hele plaat als platte
    tekst verscheen, met de linkgedeelten blauw onderstreept. De
    opschoner van de markdown-kaart accepteert `<a>` binnen SVG niet en
    zet dan het hele blok om naar tekst.

    Gevraagd: "niet de links eruit, ik wil hem juist klikbaar hebben."
    Terecht - maar dan moet het klikken buiten de SVG gebeuren. Onder de
    plaat staan nu echte tegels met een navigate-actie; die werken
    gegarandeerd en zien er hetzelfde uit.
    """
    return inhoud


def _oude_wikkel(inhoud: str, pad: str | None) -> str:
    """Maakt een blok klikbaar (v3.19.0).

    SVG kent gewoon `<a>`, en Home Assistant laat dat door in een
    markdown-kaart. Werkt het bij jou niet, dan is de plaat nog steeds
    leesbaar - de link is een toevoeging, geen voorwaarde.
    """
    if not pad:
        return inhoud
    return (
        f'<a href="/energy-management-system/{pad}" target="_top">'
        f"{inhoud}</a>"
    )


def _kort(tekst: str, tekens: int) -> str:
    """Kapt af op een woordgrens, met een beletselteken."""
    if not tekst or len(tekst) <= tekens:
        return tekst or ""
    stuk = tekst[:tekens].rsplit(" ", 1)[0]
    return stuk + "…"


def bouw_status(g: dict) -> str:
    """De status per onderwerp, klikbaar (v3.19.0).

    Gevraagd: "Deze info toevoegen bijvoorbeeld? En klikbaar maken?" - bij
    een schermafbeelding van de statustegels op de landingspagina.

    Elk blok wijst naar de bijbehorende detailpagina. De kleur links
    zegt hoe betrouwbaar het onderwerp is: dat is dezelfde schaal die de
    proefstand en de meetkwaliteit gebruiken, dus geen nieuw begrip.
    """
    onderwerpen = g.get("onderwerpen") or {}
    zichtbaar = [
        (sleutel, gegevens)
        for sleutel, gegevens in onderwerpen.items()
        if sleutel in ONDERWERP_PADEN and (gegevens or {}).get("zin")
    ]
    if not zichtbaar:
        return ""

    regel_h = 44
    hoogte = 40 + len(zichtbaar) * regel_h
    d = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 {hoogte}" '
        f'width="100%" role="img" aria-label="Status per onderwerp">',
        f'<rect width="760" height="{hoogte}" rx="10" fill="#081820"/>',
        f'<text x="24" y="26" font-size="10" fill="{KLEUR_ZWAK}" '
        f'letter-spacing="1">STATUS PER ONDERWERP</text>',
    ]

    for i, (sleutel, gegevens) in enumerate(zichtbaar):
        naam, pad = ONDERWERP_PADEN[sleutel]
        y = 40 + i * regel_h
        kleur = NIVEAU_KLEUR.get(gegevens.get("niveau"), KLEUR_ZWAK)
        blok = (
            f'<rect x="16" y="{y}" width="728" height="{regel_h - 6}" rx="6" '
            f'fill="{KLEUR_VLAK}" fill-opacity="0.5" stroke="{KLEUR_LIJN}" '
            f'stroke-opacity="0.35"/>'
            f'<rect x="16" y="{y}" width="4" height="{regel_h - 6}" rx="2" '
            f'fill="{kleur}"/>'
            f'<text x="34" y="{y + 17}" font-size="11" font-weight="600" '
            f'fill="{KLEUR_TEKST}">{naam}</text>'
            f'<text x="34" y="{y + 31}" font-size="9.5" fill="{KLEUR_ZWAK}">'
            f'{_kort(gegevens.get("zin", ""), 118)}</text>'
            f'<text x="728" y="{y + 24}" text-anchor="end" font-size="12" '
            f'fill="{KLEUR_LIJN}">›</text>'
        )
        d.append(_wikkel(blok, pad))

    d.append("</svg>")
    return "".join(d)

def _balkje(
    x: float,
    y: float,
    waarde,
    minimum: float,
    maximum: float,
    label: str,
    eenheid: str = "",
    breedte: float = 68.0,
    alarm_boven: float | None = None,
) -> str:
    """Een getal met een dun voortgangsbalkje eronder (v3.22.0).

    Gemeld: "springt er teveel uit, misschien compacter, en geen
    gauges?"

    Terecht. Drie halve cirkels met bogen, achtergrondbogen en
    schaalgrenzen zijn veel lijnen voor drie getallen. Een balkje van
    drie pixels zegt hetzelfde: waar sta je tussen minimum en maximum.

    Het GETAL blijft het belangrijkste, en dat is nu ook wat opvalt.
    """
    if waarde is None:
        return (
            f'<text x="{x}" y="{y}" font-size="17" fill="{KLEUR_ZWAK}">'
            "--</text>"
            f'<text x="{x}" y="{y + 13}" font-size="8.5" '
            f'fill="{KLEUR_ZWAK}">{label}</text>'
        )

    deel = max(0.0, min(1.0, (float(waarde) - minimum) / (maximum - minimum)))
    kleur = (
        KLEUR_ALARM
        if alarm_boven is not None and float(waarde) >= alarm_boven
        else KLEUR_ACCENT
    )
    return (
        f'<text x="{x}" y="{y}" font-size="17" font-weight="600" '
        f'fill="{KLEUR_TEKST}">{_getal(waarde, "", 0)}'
        f'<tspan font-size="9" fill="{KLEUR_ZWAK}"> {eenheid}</tspan></text>'
        f'<rect x="{x}" y="{y + 6}" width="{breedte}" height="3" rx="1.5" '
        f'fill="{KLEUR_VLAK}"/>'
        f'<rect x="{x}" y="{y + 6}" width="{breedte * deel:.1f}" height="3" '
        f'rx="1.5" fill="{kleur}"/>'
        f'<text x="{x}" y="{y + 21}" font-size="8.5" fill="{KLEUR_ZWAK}">'
        f"{label}</text>"
    )

