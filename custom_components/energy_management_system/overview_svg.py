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

import base64
import re


def als_afbeelding(svg: str | None, beschrijving: str = "Overzicht") -> str:
    """Pakt een plaat in als `<img>` met een data-URI (v3.26.0).

    Vier opleveringen lang verscheen de visuele pagina als platte tekst.
    De oorzaak zit niet in de plaat maar in de markdown-kaart:
    `hui-markdown-card.ts` zet `allow-svg` NIET, dus draait de opschoner
    met de gewone witte lijst en die kent geen enkel SVG-element. Alles
    wat er niet op staat wordt naar tekst ontsnapt - de hele plaat dus.

    Zelfs mét `allow-svg` zou het niet gaan: die lijst kent alleen
    `svg`, `path` en `img`, en de plaat bestaat uit `rect`, `text`,
    `circle` en `line`.

    `<img>` staat wél op de gewone lijst, en `safeAttrValue` van de
    xss-bibliotheek laat `data:image/` uitdrukkelijk toe. Base64, want
    de plaat staat vol `#`-kleurcodes en die breken een niet-gecodeerde
    data-URI.
    """
    if not svg:
        return ""

    plaat = _vaste_maten(svg)
    blok = base64.b64encode(plaat.encode("utf-8")).decode("ascii")
    tekst = beschrijving.replace('"', "'")

    # v5.18.2: de vaste maat blijft op de SVG staan - daar is hij voor, want
    # zonder eigen afmeting valt een `<img>` terug op 300 bij 150 pixels.
    # De REK hoort op de afbeelding: `width="100%"` laat hem de volle
    # breedte van de kaart pakken, ook op een breed scherm. Zonder dat bleef
    # hij hangen op de 1000 pixels uit de viewBox.
    return (
        f'<img alt="{tekst}" width="100%" '
        f'src="data:image/svg+xml;base64,{blok}">'
    )


def _vaste_maten(svg: str) -> str:
    """Zet `width="100%"` om naar de maat uit de `viewBox`.

    Binnen een `<img>` is een percentage betekenisloos: de browser kent
    dan geen eigen afmeting en valt terug op 300 bij 150 pixels. Met een
    echte maat klopt de verhouding, en `img { max-width: 100% }` uit
    `ha-markdown` laat hem alsnog meeschalen op een telefoon.
    """
    kop = re.match(r"<svg\b[^>]*>", svg)
    if not kop:
        return svg

    origineel = kop.group(0)
    doos = re.search(r'viewBox="([^"]+)"', origineel)
    if not doos:
        return svg

    delen = doos.group(1).split()
    if len(delen) != 4:
        return svg

    breedte, hoogte = delen[2], delen[3]
    nieuw = re.sub(r'\s(width|height)="[^"]*"', "", origineel)
    nieuw = nieuw.replace(
        "<svg", f'<svg width="{breedte}" height="{hoogte}"', 1
    )

    return nieuw + svg[len(origineel):]


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


def _primair(waarde, opmaak) -> str:
    """Een primaire waarde, of ONBEKEND (v5.18).

    Gevraagd: "een ontbrekende primaire vermogenswaarde mag nooit visueel
    lijken op 0 W". 0 is een meting - de accu die stilstaat, de zon die
    niet schijnt. Ontbreekt de meting, dan staat er ONBEKEND.
    """
    return ONBEKEND if waarde is None else opmaak(waarde)


ONBEKEND = "ONBEKEND"


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
    """Een stroompijl waarvan de dikte het vermogen volgt (v3.25.4).

    v3.25.4: ZONDER `<animate>`.

    Gemeld: "Visueel is nog steeds een lap tekst." De plaat verscheen als
    platte tekst, en de tijdlijn wijst één kant op: de beweging kwam er
    in v3.22.1, en precies daarna begon dit. Daarvoor renderde hij.

    Home Assistant filtert SMIL-animatie (`<animate>`) uit de
    markdown-kaart; wat overblijft is geen geldige SVG meer en valt terug
    op tekst.

    De richting is net zo goed te zien met een pijlPUNT, en die is
    gewone SVG. Bij nul vermogen wordt er niets getekend - een pijl die
    altijd staat zegt niets.
    """
    import math

    try:
        w = abs(float(watt or 0))
    except (TypeError, ValueError):
        return ""
    if w < 25:
        return ""

    dikte = min(7.0, 1.5 + w / 500)
    # De punt op driekwart van de lijn, zodat hij niet op het blok valt.
    lengte = math.hypot(x2 - x1, y2 - y1)
    if lengte < 1:
        return ""
    ex, ey = (x2 - x1) / lengte, (y2 - y1) / lengte
    px, py = x1 + ex * lengte * 0.72, y1 + ey * lengte * 0.72
    # Een driehoek loodrecht op de richting.
    b = 4.5 + dikte / 2
    punt = (
        f"{px + ex * 9:.1f},{py + ey * 9:.1f} "
        f"{px - ey * b:.1f},{py + ex * b:.1f} "
        f"{px + ey * b:.1f},{py - ex * b:.1f}"
    )
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{kleur}" '
        f'stroke-width="{dikte:.1f}" stroke-linecap="round" opacity="0.65"/>'
        f'<polygon points="{punt}" fill="{kleur}" opacity="0.9"/>'
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

_ICONEN = {
    # Eenvoudige lijnfiguren; geen letterlijke afbeeldingen, alleen vorm.
    "zon": (
        '<circle cx="0" cy="0" r="6" fill="none" stroke="{k}" stroke-width="2"/>'
        + "".join(
            f'<line x1="{9 * __import__("math").cos(h * 0.7854):.1f}" '
            f'y1="{9 * __import__("math").sin(h * 0.7854):.1f}" '
            f'x2="{13 * __import__("math").cos(h * 0.7854):.1f}" '
            f'y2="{13 * __import__("math").sin(h * 0.7854):.1f}" '
            f'stroke="{{k}}" stroke-width="2" stroke-linecap="round"/>'
            for h in range(8)
        )
    ),
    "huis": (
        '<path d="M-11,1 L0,-9 L11,1 M-8,1 L-8,11 L8,11 L8,1" fill="none" '
        'stroke="{k}" stroke-width="2" stroke-linejoin="round" '
        'stroke-linecap="round"/>'
    ),
    "net": (
        '<path d="M-9,-10 L-3,10 M9,-10 L3,10 M-7,-3 L7,-3 M-5,4 L5,4 '
        'M-9,-10 L9,-10" fill="none" stroke="{k}" stroke-width="2" '
        'stroke-linecap="round"/>'
    ),
    "accu": (
        '<rect x="-11" y="-7" width="20" height="14" rx="3" fill="none" '
        'stroke="{k}" stroke-width="2"/>'
        '<rect x="9" y="-3" width="3" height="6" rx="1" fill="{k}"/>'
        '<rect x="-8" y="-4" width="6" height="8" rx="1" fill="{k}"/>'
    ),
}


def _icoon(x: float, y: float, soort: str, kleur: str) -> str:
    """Een lijnfiguur bij een knoop - herkenbaar voordat je leest."""
    vorm = _ICONEN.get(soort, "")
    return f'<g transform="translate({x},{y})">{vorm.format(k=kleur)}</g>'


def _sparkline(x, y, b, h, reeksen, nu_uur=None, verwacht=None) -> str:
    """Het verloop van vandaag, klein en zonder assen.

    Een dag in een oogopslag naast de momentopname: de plaat toonde tot nu
    toe alleen het NU, en dan mis je of een getal hoog of laag is voor dit
    moment van de dag.
    """
    delen = []
    # De as beslaat altijd de HELE dag, ook 's ochtends. Anders wordt een
    # half uur zon over de volle breedte uitgerekt en lijkt een vlakke
    # ochtend een vlakke dag.
    uren = max([24] + [len(p) for p, _k, _v in reeksen]
               + [len(p) for p, _k in (verwacht or [])])
    for punten, kleur, vullen in reeksen:
        waarden = [p for p in punten if p is not None]
        if len(waarden) < 2:
            continue
        top = max(max(waarden), 1.0)
        stap = b / max(1, uren - 1)
        pad = []
        for i, waarde in enumerate(punten):
            if waarde is None:
                continue
            px = x + i * stap
            py = y + h - (waarde / top) * h
            pad.append(f"{'M' if not pad else 'L'}{px:.0f},{py:.0f}")
        if not pad:
            continue
        lijn = " ".join(pad)
        if vullen:
            # De vulling stopt waar de METING stopt. Doorlopen tot de
            # rechterrand tekende 's ochtends een grote driehoek over een
            # deel van de dag dat nog moet komen.
            eind_x = x + (len(punten) - 1) * stap
            delen.append(
                f'<path d="{lijn} L{eind_x:.0f},{y + h:.0f} L{x:.0f},'
                f'{y + h:.0f} Z" fill="{kleur}" opacity="0.12"/>'
            )
        delen.append(
            f'<path d="{lijn}" fill="none" stroke="{kleur}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
        )
    # Rechts van NU de VERWACHTING, met een stippellijn - zodat zichtbaar
    # is wat er nog komt zonder dat het op een meting lijkt.
    stap = b / max(1, uren - 1)
    for punten, kleur in verwacht or []:
        waarden = [p for p in punten if p is not None]
        if len(waarden) < 2:
            continue
        top = max(max(waarden), 1.0)
        pad = []
        for i, waarde in enumerate(punten):
            if waarde is None:
                continue
            pad.append(
                f"{'M' if not pad else 'L'}{x + i * stap:.0f},"
                f"{y + h - (waarde / top) * h:.0f}"
            )
        if pad:
            delen.append(
                f'<path d="{" ".join(pad)}" fill="none" stroke="{kleur}" '
                f'stroke-width="1.5" stroke-dasharray="3 4" opacity="0.55"/>'
            )
    if nu_uur is not None:
        nx = x + max(0, min(uren - 1, nu_uur)) * stap
        delen.append(
            f'<line x1="{nx:.0f}" y1="{y - 4}" x2="{nx:.0f}" y2="{y + h + 4}" '
            f'stroke="#6f7d8c" stroke-width="1" stroke-dasharray="2 3"/>'
            f'<text x="{nx:.0f}" y="{y - 8}" fill="#6f7d8c" font-size="9" '
            f'text-anchor="middle" letter-spacing="1">NU</text>'
        )
    return "".join(delen)


def _knoop(x, y, b, h, titel, waarde, onder=None, kleur="#e8edf2",
           vandaag=None, balk=None, icoon=None, rechtsonder=None):
    """Een apparaat in het schema: naam, vermogen nu, dagtotaal, context."""
    eenheid = ""
    if " " in str(waarde):
        waarde, eenheid = str(waarde).split(" ", 1)
    d = [
        f'<rect x="{x}" y="{y}" width="{b}" height="{h}" rx="14" '
        f'fill="url(#kaart)" stroke="#2c3846"/>',
        f'<rect x="{x}" y="{y}" width="4" height="{h}" rx="2" fill="{kleur}" '
        f'opacity="0.9"/>',
        f'<text x="{x + 20}" y="{y + 27}" fill="#8b98a5" font-size="11" '
        f'letter-spacing="1.8" font-weight="600">{titel}</text>',
        f'<text x="{x + 20}" y="{y + 60}" fill="#f4f7fa" font-size="30" '
        f'font-weight="650" letter-spacing="-0.5">{waarde}'
        f'<tspan font-size="15" font-weight="500" fill="#8b98a5"> {eenheid}'
        f"</tspan></text>",
    ]
    if icoon:
        d.append(_icoon(x + b - 30, y + 28, icoon, kleur))
    if vandaag:
        # Vanaf de ONDERKANT van de kaart: een vaste hoogte viel bij een
        # lagere kaart buiten het kader.
        hoogte, anker = ((y + 27, "end") if rechtsonder else (y + h - 14, "start"))
        px = (x + b - 48) if rechtsonder else (x + 20)
        d.append(
            f'<text x="{px}" y="{hoogte}" fill="#6f7d8c" font-size="11" '
            f'text-anchor="{anker}">vandaag {vandaag}</text>'
        )
    if onder:
        d.append(
            f'<text x="{x + 20}" y="{y + h - (4 if rechtsonder else 32)}" '
            f'fill="#8b98a5" font-size="12">{_kort(str(onder), 42)}</text>'
        )
    if rechtsonder:
        d.append(
            f'<text x="{x + 20}" y="{y + 88}" fill="{kleur}" font-size="12" '
            f'letter-spacing="1.4" font-weight="600">'
            f"{_kort(str(rechtsonder), 22)}</text>"
        )
    if balk is not None:
        d.append(_laadbalk(x + 20, y + h - 20, b - 40, balk[0], kleur, balk[1]))
    return "".join(d)


def _laadbalk(x, y, b, deel, kleur, reservedeel=None):
    """Laadstand als balk; het streepje markeert de reserve."""
    d = [
        f'<rect x="{x}" y="{y}" width="{b}" height="9" rx="4.5" '
        f'fill="#141b23" stroke="#2c3846" stroke-width="0.5"/>',
        f'<rect x="{x}" y="{y}" width="{max(0.0, min(1.0, deel)) * b:.0f}" '
        f'height="9" rx="4.5" fill="{kleur}"/>',
    ]
    if reservedeel is not None:
        rx = x + max(0.0, min(1.0, reservedeel)) * b
        d.append(
            f'<line x1="{rx:.0f}" y1="{y - 4}" x2="{rx:.0f}" y2="{y + 13}" '
            f'stroke="#f4f7fa" stroke-width="2"/>'
        )
    return "".join(d)


def _stroom(x1, y1, x2, y2, watt, label_x=None, label_y=None, kleur="#3ecf8e"):
    """Een stroompijl: overal even dik, richting naar het teken.

    De pijlPUNT is een polygon en geen marker: zonder beweging moet de
    richting uit de punt blijken. Een actieve lijn krijgt stippen over een
    doorlopende baan; loopt er niets, dan alleen een matte stippellijn - de
    verbinding bestaat wel, er gaat niets doorheen.
    """
    if not watt:
        return (
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#222c37" '
            f'stroke-width="2" stroke-dasharray="3 6"/>'
        )
    # v5.16.1: alle lijnen even dik en hetzelfde stippatroon. De dikte
    # volgde eerst het vermogen, en dan oogt elke lijn anders - gemeld:
    # "lijnen even dik/format". Hoeveel er loopt staat er als getal bij;
    # hoe hard de stippen lopen volgt nog wel het vermogen.
    dik = 3.0
    if watt < 0:
        x1, y1, x2, y2 = x2, y2, x1, y1
    lengte = max(1.0, ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5)
    ex, ey = (x2 - x1) / lengte, (y2 - y1) / lengte
    punt = 10.0
    bx, by = x2 - ex * punt, y2 - ey * punt
    label = (
        f'<text x="{label_x}" y="{label_y}" fill="#f4f7fa" font-size="12" '
        f'font-weight="600" text-anchor="middle">{_vermogen(abs(watt))}</text>'
        if label_x is not None
        else ""
    )
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{bx:.0f}" y2="{by:.0f}" '
        f'stroke="{kleur}" stroke-width="{dik:.1f}" stroke-linecap="round" '
        f'opacity="0.35"/>'
        # De stippen LOPEN mee met de stroom (v5.16.1).
        #
        # Beweging was verboden sinds v3.25.4: Home Assistant filterde SMIL
        # uit de markdown-kaart, en wat overbleef was geen geldige SVG meer
        # - de plaat viel terug op een lap tekst. Dat verbod is verouderd.
        # Sinds v3.26.0 gaat de plaat als base64 in een `<img>`, en de
        # opschoner kan niet in base64 kijken; er wordt dus niets meer
        # gefilterd.
        #
        # De terugval is bovendien mild geworden: negeert een browser de
        # animatie, dan staan de stippen stil en blijft de plaat heel.
        # Toen sloopte het filter de HELE plaat.
        f'<line x1="{x1}" y1="{y1}" x2="{bx:.0f}" y2="{by:.0f}" '
        f'stroke="{kleur}" stroke-width="{dik:.1f}" stroke-linecap="round" '
        f'stroke-dasharray="1 9">'
        f'<animate attributeName="stroke-dashoffset" from="10" to="0" '
        f'dur="{max(0.5, min(2.2, 900 / max(120, abs(watt)))):.2f}s" '
        f'repeatCount="indefinite"/></line>'
        f'<polygon points="{x2:.0f},{y2:.0f} '
        f'{bx - ey * 5.5:.0f},{by + ex * 5.5:.0f} '
        f'{bx + ey * 5.5:.0f},{by - ex * 5.5:.0f}" fill="{kleur}"/>' + label
    )


def _infobalk(x, y, b, velden, hoog=88):
    """De balk onderaan met wat er op de landingspagina staat."""
    if not velden:
        return ""
    d = [
        f'<rect x="{x}" y="{y}" width="{b}" height="{hoog}" rx="14" '
        f'fill="url(#kaart)" stroke="#2c3846"/>'
    ]
    if hoog > 100:
        # Smal en hoog: onder elkaar, label links en waarde rechts.
        regel = (hoog - 24) / len(velden)
        for i, (label, waarde, kleur, _pad) in enumerate(velden):
            ry = y + 32 + i * regel
            d.append(
                f'<text x="{x + 22}" y="{ry:.0f}" fill="#6f7d8c" '
                f'font-size="10" letter-spacing="1.4" '
                f'font-weight="600">{label}</text>'
                f'<text x="{x + b - 22}" y="{ry:.0f}" fill="{kleur}" '
                f'font-size="17" font-weight="650" text-anchor="end">'
                f"{_kort(ONBEKEND if waarde is None else str(waarde), 18)}</text>"
            )
        return "".join(d)
    kolom = b / len(velden)
    for i, (label, waarde, kleur, pad) in enumerate(velden):
        _ = pad  # geen links: de plaat wordt als afbeelding getoond
        mx = x + kolom * i + kolom / 2
        d.append(
            f'<text x="{mx:.0f}" y="{y + 32}" fill="#6f7d8c" font-size="10" '
            f'letter-spacing="1.6" font-weight="600" '
            f'text-anchor="middle">{label}</text>'
            f'<text x="{mx:.0f}" y="{y + 63}" fill="{kleur}" font-size="18" '
            f'font-weight="650" text-anchor="middle">'
            f"{_kort(ONBEKEND if waarde is None else str(waarde), 21)}</text>"
        )
        if i:
            lx = x + kolom * i
            d.append(
                f'<line x1="{lx:.0f}" y1="{y + 18}" x2="{lx:.0f}" '
                f'y2="{y + 70}" stroke="#222c37"/>'
            )
    return "".join(d)



STATUSKLEUREN = {
    "GOED": "#5fd38d",
    "LET OP": "#f0b429",
    "INGRIJPEN": "#e08a3c",
    "STORING": "#e05252",
}


def _soc_balk(x, y, b, soc_deel, reserve_deel, kleur, ondergrens_deel=None):
    """De laadstand in DRIE zones (v5.17).

    Gevraagd: "ik wil in een oogopslag kunnen zien hoeveel energie
    aanwezig is, hoeveel daarvan als reserve wordt aangehouden en hoeveel
    vrije capaciteit nog beschikbaar is".

        [ reserve | vrij te gebruiken | nog te vullen ]
    """
    soc_deel = max(0.0, min(1.0, soc_deel or 0.0))
    # NIET afkappen op de laadstand: staat de reserve hoger dan wat erin
    # zit, dan is dat juist het nieuws - de accu staat onder zijn reserve.
    heeft_reserve = reserve_deel is not None
    reserve_echt = max(0.0, min(1.0, reserve_deel or 0.0))
    reserve_deel = min(soc_deel, reserve_echt)
    d = [
        f'<rect x="{x}" y="{y}" width="{b}" height="10" rx="5" '
        f'fill="#141b23" stroke="#2c3846" stroke-width="0.5"/>'
    ]
    if reserve_deel:
        d.append(
            f'<rect x="{x}" y="{y}" width="{reserve_deel * b:.0f}" height="10" '
            f'rx="5" fill="{kleur}" opacity="0.38"/>'
        )
    if soc_deel > reserve_deel:
        d.append(
            f'<rect x="{x + reserve_deel * b:.0f}" y="{y}" '
            f'width="{(soc_deel - reserve_deel) * b:.0f}" height="10" rx="5" '
            f'fill="{kleur}"/>'
        )
    if ondergrens_deel:
        # De absolute ondergrens van de accu: daaronder komt hij nooit.
        d.append(
            f'<rect x="{x}" y="{y}" width="{ondergrens_deel * b:.0f}" '
            f'height="10" rx="5" fill="#2c3846"/>'
        )
    if reserve_echt > soc_deel:
        # Het tekort: van wat erin zit tot waar de reserve staat.
        d.append(
            f'<rect x="{x + soc_deel * b:.0f}" y="{y}" '
            f'width="{(reserve_echt - soc_deel) * b:.0f}" height="10" rx="5" '
            f'fill="{KLEUR_ALARM}" opacity="0.25"/>'
        )
    # Geen reserve, geen markering: een streepje op 0% zou een reserve van
    # nul suggereren, terwijl er gewoon niets te overbruggen is.
    if heeft_reserve:
        d.append(
            f'<line x1="{x + reserve_echt * b:.0f}" y1="{y - 4}" '
            f'x2="{x + reserve_echt * b:.0f}" y2="{y + 14}" stroke="#f4f7fa" '
            f'stroke-width="2"/>'
        )
    return "".join(d)


def _regels(tekst: str, tekens: int, maximaal: int) -> list[str]:
    """Breekt een zin af op WOORDEN, over hoogstens zoveel regels (v5.18.2).

    Gemeld: de uitleg en de waarom-regel werden afgekapt op "om zowel
    het...". Midden in een zin afkappen leest slecht, en juist die zin is
    de motivatie van het besluit.
    """
    woorden = str(tekst or "").split()
    regels: list[str] = []
    huidig = ""
    for woord in woorden:
        kandidaat = f"{huidig} {woord}".strip()
        if len(kandidaat) <= tekens:
            huidig = kandidaat
            continue
        regels.append(huidig)
        huidig = woord
        if len(regels) == maximaal:
            break
    if huidig and len(regels) < maximaal:
        regels.append(huidig)
    if not regels:
        return []
    # Past het niet, dan alleen op de LAATSTE regel een beletselteken.
    gebruikt = sum(len(r) + 1 for r in regels)
    if gebruikt < len(" ".join(woorden)):
        regels[-1] = regels[-1][: tekens - 1].rstrip() + "…"
    return regels


def _besluitblok(x, y, b, h, besluit, uitleg, waarom):
    """Het EMS-besluit met zijn eigen motivatie (v5.17).

    Gevraagd: "dit is een van de intelligentste onderdelen van het hele
    EMS en verdient meer visueel gewicht", met een verplichte waarom-regel
    uit de werkelijke beslisparameters.
    """
    d = [
        f'<rect x="{x}" y="{y}" width="{b}" height="{h}" rx="14" '
        f'fill="url(#kaart)" stroke="#2c3846"/>',
        f'<rect x="{x}" y="{y}" width="4" height="{h}" rx="2" fill="#b088f9"/>',
        f'<text x="{x + 24}" y="{y + 26}" fill="#6f7d8c" font-size="11" '
        f'letter-spacing="1.8" font-weight="600">EMS BESLUIT</text>',
        f'<text x="{x + 24}" y="{y + 56}" fill="#f4f7fa" font-size="24" '
        f'font-weight="650" letter-spacing="0.5">'
        f"{_kort(str(besluit).upper() if besluit else ONBEKEND, 34)}</text>",
    ]
    # v5.19.8: compact. Gemeld: "EMS besluit is te nadrukkelijk aanwezig
    # nu? Mogelijk een korte opsomming maken, duidelijk maar compacter."
    # De redenen uit de beslislogica ZIJN die opsomming; de lange uitleg
    # staat op de detailpagina's en komt hier alleen als er geen redenen
    # zijn.
    hoogte = y + 82
    regels = (
        _regels(" · ".join(waarom), 136, 2) if waarom else _regels(uitleg, 136, 2)
    )
    for i, regel in enumerate(regels):
        if i == 0 and waarom:
            d.append(
                f'<text x="{x + 24}" y="{hoogte}" fill="#8b98a5" '
                f'font-size="13"><tspan fill="#b088f9" '
                f'font-weight="600">WAAROM  </tspan>{regel}</text>'
            )
        else:
            d.append(
                f'<text x="{x + (92 if waarom else 24)}" y="{hoogte}" '
                f'fill="#8b98a5" font-size="13">{regel}</text>'
            )
        hoogte += 19
    return "".join(d)


def bouw_scada(g: dict) -> str:
    """De EMS-cockpit (v5.17).

    Gevraagd: het scherm moet binnen enkele seconden vijf vragen
    beantwoorden - is mijn EMS gezond, waar komt de energie vandaan, waar
    gaat hij heen, wat heeft het EMS besloten, en waarom.

    Uitdrukkelijk NIET zoveel mogelijk informatie: de centrale opbouw
    blijft (zon boven, net links, huis rechts, accu onder), en alles wat
    erbij komt moet een van die vijf vragen beantwoorden.

    Alles komt uit werkelijke grootheden van het EMS. Waar iets niet
    bestaat - een "confidence" van het besluit bijvoorbeeld - staat er
    niets, in plaats van een getal dat achteraf is verzonnen.
    """
    # v5.18: GEEN `or 0` meer - dat maakte van een ontbrekende meting een
    # nul, en een nul is een echte meting.
    pv, accu, net, huis = (
        g.get("pv_w"), g.get("accu_w"), g.get("net_w"), g.get("huis_w")
    )
    status = str(g.get("status_kort") or "GOED").upper()
    statuskleur = STATUSKLEUREN.get(status, KLEUR_ZWAK)
    netkleur = "#5aa9e6"
    if net is None:
        netrichting, netpijl = ONBEKEND, ""
    elif net > 0:
        netrichting, netpijl = "INKOOP", "↓"
    elif net < 0:
        netrichting, netpijl = "TERUGLEVERING", "↑"
    else:
        netrichting, netpijl = "GEEN UITWISSELING", "·"
    # De stand komt uit de coordinator, met dezelfde dode band als de
    # regellogica (MIN_BATTERY_POWER_IDLE_W). De plaat bepaalt hem niet zelf.
    accustand = g.get("accustand") or ONBEKEND
    koeling = g.get("koeling")
    if isinstance(koeling, dict):
        # Alleen als hij DRAAIT: dat is het nieuws.
        koeling = (
            "ventilator draait"
            if koeling.get("ventilator_aan") or koeling.get("actie") == "aan"
            else None
        )
    d = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 530" '
        'width="100%" font-family="system-ui, -apple-system, Segoe UI, '
        'sans-serif">',
        # v5.18.3: een SVG in een `<img>` kent zijn EIGEN breedte, dus hij
        # kan zelf zien of hij op een telefoon staat. Op een smal scherm
        # vallen de bijzaken weg en wordt het schema groter getekend - dan
        # blijven de cijfers leesbaar in plaats van mee te krimpen.
        "<style>"
        "@media (max-width: 760px) {"
        "  .bijzaak { display: none; }"
        "  #stroomschema { transform: translate(0px, -120px) scale(1.5);"
        "                  transform-origin: 700px 240px; }"
        "}"
        "</style>"
        "<defs>"
        '<linearGradient id="doek" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#151d26"/>'
        '<stop offset="1" stop-color="#0d1218"/></linearGradient>'
        '<linearGradient id="kaart" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#1e2731"/>'
        '<stop offset="1" stop-color="#171f28"/></linearGradient>'
        "</defs>",
        '<rect width="1600" height="530" rx="18" fill="url(#doek)"/>',
        '<text x="36" y="40" fill="#6f7d8c" font-size="11" letter-spacing="2.4" '
        'font-weight="600">ENERGY MANAGEMENT SYSTEM</text>',
        f'<circle cx="42" cy="70" r="6" fill="{statuskleur}"/>',
        f'<text x="58" y="77" fill="{statuskleur}" font-size="26" '
        f'font-weight="700" letter-spacing="0.5">{status}</text>',
        f'<text x="36" y="102" fill="#6f7d8c" font-size="12">'
        f"{_kort(str(g.get('status_regel') or ''), 90)}</text>",
        f'<text x="1564" y="40" fill="#6f7d8c" font-size="11" '
        f'text-anchor="end" letter-spacing="1">{g.get("moment") or ""}</text>',
    ]
    verloop = g.get("verloop") or {}
    if verloop:
        d.append('<g class="bijzaak">')
        d.append(
            _sparkline(
                1240, 46, 324, 40,
                [
                    (verloop.get("pv") or [], "#f0b429", True),
                    (verloop.get("huis") or [], "#8b98a5", False),
                ],
                nu_uur=verloop.get("nu_uur"),
                verwacht=[
                    (verloop.get("pv_verwacht") or [], "#f0b429"),
                    (verloop.get("huis_verwacht") or [], "#8b98a5"),
                ],
            )
        )
        # v5.19.4: de lijnen bij hun KLEUR benoemen. Gevraagd: "welke kleur
        # is werkelijk/verwacht?" - en dat legde een fout bloot: het
        # dagverloop levert alleen gemeten waarden, dus er was helemaal geen
        # verwachte lijn. Het label beloofde iets wat er niet stond.
        #
        # Als LOSSE stukken op vaste plekken, niet als een regel met
        # gekleurde tspans: die lijnt niet betrouwbaar uit.
        heeft_verwacht = any(
            len([x for x in (verloop.get(sleutel) or []) if x is not None]) >= 2
            for sleutel in ("pv_verwacht", "huis_verwacht")
        )
        legenda = [(1240, "VANDAAG", "#6f7d8c"), (1318, "— ZON", "#f0b429"),
                   (1372, "— VERBRUIK", "#8b98a5")]
        if heeft_verwacht:
            legenda.append((1462, "· VERWACHT GESTIPPELD", "#6f7d8c"))
        for lx, tekst, kleur in legenda:
            d.append(
                f'<text x="{lx}" y="100" fill="{kleur}" font-size="10" '
                f'letter-spacing="1" font-weight="600">{tekst}</text>'
            )
        d.append("</g>")
    d += [
        '<g id="stroomschema">',
        '<circle cx="700" cy="240" r="22" fill="none" stroke="#2c3846">'
        '<animate attributeName="r" values="20;26;20" dur="3.4s" '
        'repeatCount="indefinite"/>'
        '<animate attributeName="opacity" values="0.9;0.25;0.9" dur="3.4s" '
        'repeatCount="indefinite"/></circle>',
        '<circle cx="700" cy="240" r="7" fill="#f4f7fa"/>',
        _stroom(700, 182, 700, 216, pv or 0, 744, 204, "#f0b429"),
        _stroom(430, 240, 674, 240, net or 0, 552, 226, netkleur),
        _stroom(726, 240, 970, 240, huis or 0, 848, 226, "#f4f7fa"),
        _stroom(700, 282, 700, 264, accu or 0, 646, 276, KLEUR_GOED),
        _knoop(563, 70, 274, 112, "ZONNEPANELEN", _primair(pv, _vermogen),
               g.get("zon_onder") or "—", "#f0b429", g.get("zon_vandaag"),
               icoon="zon"),
        # De pijl hoort bij de RICHTING, niet bij het getal: stond hij
        # ervoor, dan werd bij precies nul uitwisseling het bolletje het
        # hoofdgetal - de opmaak splitst op de eerste spatie.
        _knoop(120, 184, 310, 112, "NET",
               _primair(None if net is None else abs(net), _vermogen),
               g.get("net_onder")
               or (
                   f'stroomprijs nu {_getal(g.get("prijs_ct"), " ct/kWh", 1)}'
                   if g.get("prijs_ct") is not None
                   else "stroomprijs nu —"
               ),
               netkleur, g.get("net_vandaag"), icoon="net",
               rechtsonder=f"{netpijl} {netrichting}".strip()),
        _knoop(970, 184, 310, 112, "HUIS", _primair(huis, _vermogen),
               g.get("huis_onder") or "—", "#f4f7fa", g.get("huis_vandaag"),
               icoon="huis"),
        _accukaart(563, 282, 274, 112, accu, accustand, g, koeling),
        "</g>",
        '<g class="bijzaak">',
        _besluitblok(120, 398, 1010, 116, g.get("besluit"), g.get("besluit_uitleg"),
                     g.get("waarom")),
        _infobalk(1160, 398, 320, g.get("balk") or [], hoog=116),
        "</g>",
        "</svg>",
    ]
    return "".join(d)


def _accukaart(x, y, b, h, accu_w, accustand, g, koeling=None):
    """De accu: laadstand voorop, vermogen ernaast, drie zones in de balk."""
    soc = g.get("soc")
    kleur = KLEUR_ALARM if g.get("tekort_kwartieren") else KLEUR_GOED
    d = [
        f'<rect x="{x}" y="{y}" width="{b}" height="{h}" rx="14" '
        f'fill="url(#kaart)" stroke="#2c3846"/>',
        f'<rect x="{x}" y="{y}" width="4" height="{h}" rx="2" fill="{kleur}"/>',
        f'<text x="{x + 20}" y="{y + 24}" fill="#6f7d8c" font-size="11" '
        f'letter-spacing="1.8" font-weight="600">THUISACCU</text>',
        f'<text x="{x + 20}" y="{y + 58}" fill="#f4f7fa" '
        f'font-size="{30 if soc is not None else 18}" font-weight="650">'
        + (
            f'{_getal(soc, "", 0)}<tspan font-size="16" fill="#8b98a5">%</tspan>'
            if soc is not None
            else ONBEKEND
        )
        + "</text>",
        f'<text x="{x + b - 20}" y="{y + 58}" fill="{kleur}" font-size="20" '
        f'font-weight="600" text-anchor="end">'
        f'{ONBEKEND if accu_w is None else _vermogen(abs(accu_w))}</text>',
        f'<text x="{x + 20}" y="{y + 78}" fill="{kleur}" font-size="12" '
        f'letter-spacing="1.4" font-weight="600">{accustand}</text>',
        # v5.19.6: de ventilator op de titelregel; op de standregel staat nu
        # de resterende tijd.
        f'<text x="{x + b - 20}" y="{y + 24}" fill="#6f7d8c" font-size="11" '
        f'text-anchor="end">{_kort(str(koeling or ""), 20)}</text>',
        (
            f'<text x="{x + b - 20}" y="{y + 78}" fill="#8b98a5" font-size="12" '
            f'text-anchor="end">{g.get("resttijd")}</text>'
            if g.get("resttijd")
            else ""
        ),
        f'<text x="{x + 20}" y="{y + 94}" fill="#8b98a5" font-size="12">'
        f'reserve {g.get("reserve_tekst") or _getal(g.get("reserve_kwh"), "kWh", 2)}</text>',

        # Is er een tekort, dan staat dat hier in plaats van "vrij 0,0" -
        # anders lagen ze over elkaar heen, en "vrij 0,0" zegt minder.
        (
            f'<text x="{x + b - 20}" y="{y + 94}" fill="{KLEUR_ALARM}" '
            f'font-size="12" font-weight="600" text-anchor="end">tekort '
            f'{_getal(g.get("tekort_kwh"), "kWh", 2)}</text>'
            if g.get("tekort_kwh")
            else f'<text x="{x + b - 20}" y="{y + 94}" fill="#8b98a5" '
            f'font-size="12" text-anchor="end">vrij '
            f'{_getal(g.get("vrij_kwh"), "kWh", 1)}</text>'
        ),
        # Geen balk zonder nominale capaciteit en ondergrens - zie
        # `cockpit_accu`. Liever niets dan een geloofwaardige benadering.
        (
            _soc_balk(x + 20, y + h - 10, b - 40, balk.get("soc_deel"),
                      balk.get("reserve_deel"), kleur, balk.get("ondergrens_deel"))
            if (balk := g.get("accu_balk") or {})
            else ""
        ),
    ]
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
        d.append(blok)

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

