"""Waardeplan: de goedkoopste inzet van de accu over de bekende prijzen
(v5.158.0, akkoord Ruud 02-11: "Optimaal aanpassen ... nieuwe versie maken").

Aanleiding: een doorrekening over 23-10 t/m 01-11 (kwartierdata, met
rendement en slijtage) liet zien dat de accu 35 % haalde van wat met deze
prijzen haalbaar was:

    zonder accu          EUR 22,36
    werkelijk            EUR 20,07   (besparing 2,28)
    perfect achteraf     EUR 15,79   (besparing 6,57)

De regels hielden de accu vast of ontlaadden op volgorde van de klok; de
lading ging te vaak naar goedkope kwartieren (9,8 kWh onder 25 ct, optimaal
3,0) en te weinig naar de dagpiek. Een rollende planner die elk kwartier het
optimum zoekt over de bekende prijzen, met het verbruik uit het profiel en de
zonverwachting, haalde in dezelfde simulatie EUR 6,5 van de 6,57 - ook met de
zon van gisteren als verwachting.

Dit is die planner: dynamisch programmeren over de accu-inhoud (stap
0,1 kWh), per kwartier. Losse functies zonder Home Assistant.

v5.186.0 (review): de slimme stand (huis dekken, zon opslaan) is een eigen,
exacte actie: de inhoud zakt met tekort / rendement (of stijgt met het
overschot x rendement), niet met een afgeronde stap van 0,1 kWh. De waarde
van een inhoud tussen twee rasterpunten is lineair geinterpoleerd en de
vooruitrekening volgt een doorlopende inhoud. Laden uit het net, verkopen en
zon terugleveren blijven stappen op het raster (handmatig, vast vermogen).

Per kwartier t, bij inhoud e (kWh boven de ondergrens):
    accu laden    b > 0 (AC, kWh)   inhoud + b * rendement_laden
    accu ontladen b < 0             inhoud + b / rendement_ontladen
    net           g = verbruik - zon + b
    kosten        g * inkoopprijs   als g >= 0
                  g * terugleverwaarde als g < 0
                  + slijtage per kWh uit de accu
                  + verkoopmarge per kWh die uit de accu het net op gaat
                  + netlaadmarge per kWh die boven het zonoverschot uit
                    het net de accu in gaat (v5.165.0, de datacorrectie)
Het ontlaadrendement hangt af van het vermogen (v5.165.0): per stap het
gemeten rendement van die vermogensband, anders het ene getal.
Wat er aan het eind van de horizon in de accu zit, is de prijs van na de
horizon waard (maal rendement, min slijtage): niet alles op de laatste dag
weggeven, en ook niet eindeloos vasthouden. v5.177.0 (A10): die prijs komt
uit de prijsverwachting voor de uren direct na de horizon als die er is,
anders het 75e percentiel van de planprijzen (was de mediaan: de rest gaat
naar de dure uren, niet naar een gemiddeld uur).

v5.177.0 (A9): een kWh die uit de ACCU het net op gaat kan minder opbrengen
dan een kWh zonoverschot (de zonnebonus van 2027 geldt alleen voor zon):
`Kwartier.teruglever_accu_eur`.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from statistics import median

import numpy as np

STAP_KWH = 0.1
#: v5.186.0: één drempel voor plan en toetsen (was 0,02 in het plan en 0,01
#: in een deel van de toetsen: een overtreding die het plan niet kon zien).
EPS_KWH = 0.02
#: v5.186.0: de balanceereis is zacht - per kWh te kort na het eiskwartier.
BOETE_EIS_EUR_PER_KWH = 5.0
#: v5.186.0: kosten-to-go van een inhoud zonder geldige stap (eindig, zodat de
#: interpolatie werkt); daarboven telt een plan als onhaalbaar.
GROOT_EUR = 1.0e4
#: v5.186.0: hooguit zoveel rondes met de toetsen achteraf.
MAX_RONDES = 16
#: v5.169.0: ontladen in inhoud-eenheden (inhoud -> AC) mag boven 1,0: het is
#: een schaalfactor tussen de laadstand en de AC-kant (zie rondrit.py). De
#: afkapping op 1,0 drukte laden x ontladen onder de gemeten rondrit.
ONTLADEN_MAX = 1.20


@dataclass
class Kwartier:
    begin: object               # datetime (of iets vergelijkbaars)
    verbruik_kwh: float
    zon_kwh: float
    inkoop_eur: float
    teruglever_eur: float
    #: v5.160.0: onder deze inhoud (kWh) gaat er in dit kwartier niets uit de
    #: accu het net op; het huis dekken mag wel.
    verkoop_vloer_kwh: float = 0.0
    #: v5.165.0: zoveel uur telt dit kwartier (het lopende kwartier minder
    #: dan 0,25). Verbruik en zon gelden voor die duur; voor de weergave.
    uren: float = 0.25
    #: v5.168.0: de prijs incl. belasting voor de weergave, als het plan met
    #: een marginale prijs rekent (saldering met een verwacht overschot:
    #: `inkoop_eur` is dan de prijs zonder belastingdeel). None = gelijk.
    prijs_incl_eur: float | None = None
    #: v5.177.0 (A9): wat een kWh die uit de accu het net op gaat oplevert.
    #: Vanaf 2027 zonder de zonnebonus (die geldt alleen voor zonnestroom).
    #: None = gelijk aan `teruglever_eur`.
    teruglever_accu_eur: float | None = None
    #: v5.183.0 (bewaarmarge): in dit kwartier dekt de accu het huistekort zolang
    #: er inhoud is; bewaren voor later is hier niet genoeg waard (zie
    #: `te_duur_bewaard`). v5.186.0: verbiedt bewaren en netladen zolang er
    #: inhoud is; leeg mag alles. De bewaarmarge zit sindsdien ook in het plan zelf.
    dekken: bool = False
    #: v5.184.0 (akkoord Ruud 04-11 15:56): hier geen zon terugleveren zolang er
    #: ruimte is (ook niet via een verkoop); zie `zon_export_zonder_overschot`.
    geen_zon_export: bool = False
    #: v5.186.0: hier geen verkoop (toets achteraf). Apart van de vloer, zodat
    #: de rij de echte verkoopvloer blijft tonen (was: vloer boven vol).
    verkoop_verboden: bool = False
    #: v5.186.0 (punt 9): hier niet uit het net laden - de zon vult de accu
    #: daarna toch tot vol en levert dan terug.
    geen_netladen: bool = False
    #: v5.191.0 (L-EMS-073): deel van het laadvermogen dat hier echt de accu in
    #: gaat. Onder ~0 °C verwarmen de modules zich eerst (zie koude_accu.py).
    laad_factor: float = 1.0


@dataclass
class Accu:
    inhoud_kwh: float           # nu, boven de ondergrens
    bruikbaar_kwh: float        # boven de ondergrens
    laden_kw: float = 2.4
    ontladen_kw: float = 2.4
    rendement: float = 0.83     # rondrit
    slijtage_eur: float = 0.05  # per kWh uit de accu
    verkoopmarge_eur: float = 0.0
    netladen: bool = True
    verkopen: bool = True
    duur_h: float = 0.25
    #: v5.162.0 (L-EMS-055): na dit kwartier (index) moet de accu vol zijn,
    #: voor de balanceerlading. Het plan kiest zelf de goedkoopste kwartieren
    #: ervoor. None = geen eis.
    vol_na_kwartier: int | None = None
    #: v5.165.0 (akkoord Ruud 02-11): wat een kWh die uit het net de accu
    #: in gaat extra moet opleveren - de datacorrectie van het laadbesluit
    #: (gemeten netladingen leverden minder op dan voorspeld). Geldt voor
    #: het deel van de lading boven het zonoverschot.
    netlaadmarge_eur: float = 0.0
    #: v5.165.0: het gemeten laadrendement; None = wortel van de rondrit.
    rendement_laden: float | None = None
    #: v5.165.0: ontlaadrendement per vermogensband aan de netkant, als
    #: ((bovengrens_w, rendement of None), ...) oplopend. Leeg of None in
    #: een band = het ene getal (rondrit / laadrendement).
    ontlaadbanden: tuple = ()
    #: v5.167.0: het gemeten ontlaadrendement over alle rondes (fractie);
    #: None = rondrit / laden. Ook de terugval voor een onbetrouwbare band.
    rendement_ontladen: float | None = None
    #: v5.172.0 (punt 2): onder dit gemiddelde vermogen (W, netkant) is een
    #: netlading of verkoop in de planrij geen opdracht. 0 = elke stap.
    min_actie_w: float = 0.0
    #: v5.175.0: de slimme stand slaat elk zonoverschot op zolang er ruimte
    #: is ('houden' = smart_charging en 'huis' = smart doen dat allebei). Het
    #: plan rekent daarmee: in een kwartier met overschot gaat minstens dat
    #: overschot de accu in (tot vol en tot het laadvermogen), tenzij het
    #: plan echt verkoopt (handmatig ontladen, >= min_actie_w). False = het
    #: oude model, waarin 'houden' het overschot stil liet terugleveren.
    zon_opslaan: bool = True
    #: v5.175.0: kan de sturing zon terugleveren in plaats van opslaan
    #: afdwingen (laden begrenzen of handmatig op 0 W)? Nu niet: dan plant het
    #: plan dat ook niet. True = het mag, maar alleen als terugleveren minstens
    #: `verkoopmarge_eur` per kWh beter is dan opslaan voor later.
    zon_export_afdwingbaar: bool = False
    #: v5.177.0 (A12): onder dit vermogen (W, netkant) laadt het plan niet
    #: uit het net. Onder ~500 W haalde laden 72 % tegen 85 % bij 500-1500 W:
    #: liever minder kwartieren op een hoger vermogen. 0 = `min_actie_w`.
    min_laad_w: float = 0.0
    #: v5.177.0 (A10): de (reken)prijs per kWh voor de uren direct na de
    #: horizon, uit de prijsverwachting. None = 75e percentiel van het plan.
    eindprijs_eur: float | None = None
    #: v5.181.2 (g): mag het plan uit de accu verkopen in een kwartier met
    #: zonoverschot? Verkopen zet de accu handmatig en dan gaat de zon mee het
    #: net op. De huis-eerst-regel (v5.179.1) verbiedt zon terugleveren; daar
    #: hoort deze ook uit, anders gaat de zon via een mini-verkoop alsnog het
    #: net op (live 04-11 12:00: 0,2 kWh verkocht om 0,32 kWh zon te exporteren).
    verkopen_bij_zon: bool = True
    #: v5.182.0 (akkoord Ruud 04-11, "liever meer voor de woning"): de accu
    #: verkoopt alleen wat het huis tot het volgende bijvullen niet nodig
    #: heeft, en nooit lading die uit het net kwam (zie `verkopen_voor_huis`).
    huis_eerst: bool = False
    #: v5.183.0 (akkoord Ruud 04-11 14:04, punt 1): lading bewaren terwijl het
    #: huis op het net draait mag alleen als die later minstens zoveel per kWh
    #: meer oplevert (of duurder terug te laden is). 0 = uit.
    bewaarmarge_eur: float = 0.0
    #: v5.183.0 (punt 2): onzekerheid verder vooruit - een kleine kost per kWh
    #: inhoud per uur, zodat het plan bij een gelijkspel nu gebruikt. 0 = uit.
    bewaarkost_eur_per_kwh_uur: float = 0.0
    #: v5.183.5: het vermogen waarmee een verkoop (handmatig ontladen) loopt;
    #: `ontladen_kw` is dan de grens van de slimme stand (huis dekken). None =
    #: allebei `ontladen_kw`.
    verkoop_kw: float | None = None
    #: v5.186.0 (punt 13): het laadvermogen van de slimme stand (zon opslaan),
    #: los van het handmatige laadvermogen. None = `laden_kw`.
    laden_slim_kw: float | None = None


@dataclass
class Uitkomst:
    beschikbaar: bool
    reden: str = ""
    kwartieren: list = field(default_factory=list)
    kosten_plan_eur: float | None = None
    kosten_zonder_accu_eur: float | None = None
    eindwaarde_eur_per_kwh: float | None = None
    #: v5.186.0 (punt 4): tot deze inhoud geldt de eindwaarde hierboven (het
    #: verwachte huistekort na de horizon); daarboven `eindwaarde_laag`.
    eindwaarde_knik_kwh: float | None = None
    eindwaarde_laag_eur_per_kwh: float | None = None
    #: v5.186.0 (punt 15): hoeveel rondes de toetsen achteraf nodig hadden,
    #: welke overtredingen er in het eindplan nog staan, en of de grens van
    #: MAX_RONDES bereikt is.
    rondes: int = 0
    resterend: dict = field(default_factory=dict)
    rondelimiet: bool = False
    #: v5.186.0 (punt 14): in zoveel kwartieren is zon terugleveren geweigerd
    #: (huis eerst); was een losse herberekening in de sturing.
    zon_export_geweigerd: int = 0


def _kosten_stap(verbruik, zon, inkoop, teruglever, b, accu: Accu, teruglever_accu=None):
    """Kosten van een stap voor een rij accustromen b (numpy).

    v5.177.0 (A9): van wat het net op gaat, telt het deel uit de accu tegen
    `teruglever_accu` (zonder zonnebonus) en de rest (zon) tegen `teruglever`.
    """
    g = verbruik - zon + b
    uit = np.maximum(-b, 0.0)
    naar_net = np.minimum(np.maximum(-g, 0.0), uit)
    if teruglever_accu is None or teruglever_accu == teruglever:
        export = g * teruglever
    else:
        export = (g + naar_net) * teruglever - naar_net * teruglever_accu
    kosten = np.where(g >= 0, g * inkoop, export)
    kosten = kosten + uit * accu.slijtage_eur
    if accu.verkoopmarge_eur:
        kosten = kosten + naar_net * accu.verkoopmarge_eur
    if accu.netlaadmarge_eur:
        # v5.165.0: alleen wat boven het zonoverschot uit het net komt.
        netlading = np.maximum(b - max(zon - verbruik, 0.0), 0.0)
        kosten = kosten + netlading * accu.netlaadmarge_eur
    return kosten


def _kosten_een(k, b: float, accu: Accu, teruglever_accu=None) -> float:
    """`_kosten_stap` voor één stroom b, zonder numpy (v5.186.0: sneller)."""
    verbruik, zon = k.verbruik_kwh, k.zon_kwh
    g = verbruik - zon + b
    uit = max(-b, 0.0)
    naar_net = min(max(-g, 0.0), uit)
    if g >= 0:
        kosten = g * k.inkoop_eur
    elif teruglever_accu is None or teruglever_accu == k.teruglever_eur:
        kosten = g * k.teruglever_eur
    else:
        kosten = (g + naar_net) * k.teruglever_eur - naar_net * teruglever_accu
    kosten += uit * accu.slijtage_eur
    if accu.verkoopmarge_eur:
        kosten += naar_net * accu.verkoopmarge_eur
    if accu.netlaadmarge_eur:
        kosten += max(b - max(zon - verbruik, 0.0), 0.0) * accu.netlaadmarge_eur
    return kosten


def rendementen(accu: Accu) -> tuple[float, float]:
    """(laden, ontladen) als vaste getallen (v5.165.0).

    Laden: het gemeten laadrendement, anders de wortel van de rondrit.
    Ontladen: rondrit / laden (zoals de nacalculatie in accukosten.py).
    v5.169.0: ontladen tot ONTLADEN_MAX (inhoud -> AC, mag boven 1,0).
    """
    rondrit = max(0.5, min(1.0, accu.rendement))
    if accu.rendement_laden and accu.rendement_ontladen:
        # v5.167.0: beide gemeten (hele rondes) - zelfde grondslag voor
        # huisband en terugval.
        return (max(0.5, min(1.0, accu.rendement_laden)),
                max(0.5, min(ONTLADEN_MAX, accu.rendement_ontladen)))
    if accu.rendement_laden:
        eta_l = max(0.5, min(1.0, accu.rendement_laden))
        return eta_l, max(0.5, min(ONTLADEN_MAX, rondrit / eta_l))
    return rondrit ** 0.5, rondrit ** 0.5


def ontlaadrendement(vermogen_w: float, accu: Accu, terugval: float) -> float:
    """Het ontlaadrendement bij dit vermogen (aan de netkant, v5.165.0)."""
    for grens, eta in accu.ontlaadbanden or ():
        if vermogen_w < grens:
            return max(0.5, min(ONTLADEN_MAX, eta)) if eta else terugval
    return terugval


def _ontlaadstappen(accu: Accu, eta_o: float, grens_kw: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """De ontlaadstappen (negatief, in STAP_KWH) en hun AC-stroom (v5.165.0).

    Per stap het rendement van de band waarin het vermogen valt. De band
    volgt uit het vermogen aan de netkant, dat zelf van het rendement
    afhangt: twee keer bijstellen is genoeg (drie banden).
    v5.186.0: `grens_kw` = het vermogen van een verkoop (None = ontladen_kw).
    """
    grens_kwh = (accu.ontladen_kw if grens_kw is None else grens_kw) * accu.duur_h
    ruim = int(grens_kwh / 0.5 / STAP_KWH) + 1
    s = np.arange(-ruim, 0)
    dc = -s * STAP_KWH
    if accu.ontlaadbanden:
        eta = np.full(len(s), eta_o)
        for _ in range(2):
            vermogen = dc * eta / accu.duur_h * 1000
            eta = np.array([ontlaadrendement(v, accu, eta_o) for v in vermogen])
    else:
        eta = np.full(len(s), eta_o)
    ac = dc * eta
    houden = ac <= grens_kwh + 1e-9
    return s[houden], -ac[houden]


def actie_van(
    b: float, verbruik: float, zon: float, min_kwh: float = 0.0, min_laad_kwh: float | None = None
) -> tuple[str, float]:
    """Wat de accu in een kwartier doet, en hoeveel (kWh, AC).

    v5.172.0 (punt 2): een netlading of verkoop onder `min_kwh` is geen
    opdracht. Zo'n restje komt uit de stapgrootte (0,1 kWh inhoud = ~0,12 kWh
    AC), niet uit een afweging: 03-11 12:00 een stap van 0,12 kWh boven een
    zonoverschot van 0,09 = `laden_net` 0,027 kWh, en de Zendure ging op
    manual. Nu: met zonoverschot 'zon' (de slimme stand laadt dat vanzelf),
    zonder 'houden'; een verkooprestje wordt 'huis'.
    v5.177.0 (A12): een netlading telt vanaf `min_laad_kwh` (None = `min_kwh`).
    """
    overschot = max(zon - verbruik, 0.0)
    tekort = max(verbruik - zon, 0.0)
    if min_laad_kwh is None:
        min_laad_kwh = min_kwh
    if b > overschot + EPS_KWH:
        if b - overschot >= min_laad_kwh:
            return "laden_net", b - overschot
        if overschot > EPS_KWH:
            return "zon", overschot
        return "houden", 0.0
    if b < 0 and -b > tekort + EPS_KWH:
        if -b - tekort >= min_kwh:
            return "verkopen", -b - tekort
        return "huis", min(-b, tekort) if tekort > EPS_KWH else -b
    if b < -EPS_KWH:
        return "huis", -b
    if tekort > EPS_KWH:
        return "houden", 0.0
    return "zon", max(b, 0.0)


def zon_opslag_stappen(
    overschot_kwh: float, eta_l: float, max_op: int, niveaus: int, naar_beneden: bool = False
) -> np.ndarray:
    """Per inhoud (index) hoeveel stappen de slimme stand van het
    zonoverschot opslaat (v5.175.0): het overschot maal het laadrendement,
    afgerond op de stap (naar beneden als er niet uit het net geladen mag
    worden), hooguit het laadvermogen en de ruimte tot vol."""
    if overschot_kwh <= EPS_KWH:
        return np.zeros(niveaus, dtype=int)
    stappen = overschot_kwh * eta_l / STAP_KWH
    opslag = int(stappen + 1e-9) if naar_beneden else int(round(stappen))
    opslag = min(opslag, max_op)
    ruimte = (niveaus - 1) - np.arange(niveaus)
    return np.minimum(opslag, ruimte)


def _min_laad_kwh(accu: Accu, uren: float) -> float:
    """De kleinste netlading (kWh AC) in een kwartier van `uren` (v5.177.0)."""
    return (accu.min_laad_w or accu.min_actie_w) / 1000 * uren


def eindwaarde(kwartieren, accu: Accu, eta_o: float) -> float:
    """Wat een kWh die aan het eind in de accu zit waard is (per kWh inhoud).

    v5.165.0: tegen het rendement van de band van het gewone huisverbruik.
    v5.177.0 (A10): de prijs van na de horizon (`accu.eindprijs_eur`, uit de
    prijsverwachting), anders het 75e percentiel van de planprijzen. Met de
    mediaan gaf het plan de lading aan het eind te goedkoop weg: wat er dan
    nog in zit, gaat naar de dure uren.
    """
    huis_w = median(k.verbruik_kwh / (getattr(k, "uren", 0.25) or 0.25) for k in kwartieren) * 1000
    basis = accu.eindprijs_eur
    if basis is None:
        basis = float(np.percentile([k.inkoop_eur for k in kwartieren], 75))
    return max(0.0, basis * ontlaadrendement(huis_w, accu, eta_o) - accu.slijtage_eur)


def eindwaarde_knik(kwartieren, accu: Accu, eta_l: float, eta_o: float, hoog: float,
                    cap: float) -> tuple[float, float]:
    """(knik in kWh inhoud, waarde daarboven per kWh) van de eindwaarde (v5.186.0, punt 4).

    Was lineair: elke kWh aan het eind telde tegen de dure prijs, ook wat het
    huis na de horizon niet nodig heeft. Het plan laadde dan aan het eind uit
    het net alleen voor die eindwaarde. Nu: tot het verwachte huistekort na de
    horizon (het patroon van de laatste 24 uur van het plan, tot de zon de accu
    weer zou vullen) tegen `hoog`; daarboven wat een verkoop uit de accu
    oplevert (mediaan van de terugleverwaarde x rendement - slijtage - marge),
    nooit meer dan `hoog`.
    """
    if len(kwartieren) < 96:
        # Korter dan een etmaal: geen patroon voor na de horizon; dan de oude,
        # lineaire eindwaarde (alles tegen `hoog`).
        return cap, hoog
    patroon = kwartieren[-96:]
    op_slim = (accu.laden_slim_kw or accu.laden_kw)
    lopend = 0.0
    nodig = 0.0
    for k in patroon:
        uren = getattr(k, "uren", 0.25) or 0.25
        tekort = min(max(k.verbruik_kwh - k.zon_kwh, 0.0), accu.ontladen_kw * uren)
        overschot = min(max(k.zon_kwh - k.verbruik_kwh, 0.0), op_slim * uren) if accu.zon_opslaan else 0.0
        lopend += tekort / max(eta_o, 0.5) - overschot * eta_l
        nodig = max(nodig, lopend)
        if lopend <= nodig - cap:
            break       # de zon had de accu vanaf de knik weer vol gemaakt
    knik = min(cap, max(0.0, nodig))
    terug = median(
        (k.teruglever_eur if getattr(k, "teruglever_accu_eur", None) is None else k.teruglever_accu_eur)
        for k in kwartieren
    )
    verkoop_kw = accu.verkoop_kw if accu.verkoop_kw is not None else accu.ontladen_kw
    eta_v = ontlaadrendement(verkoop_kw * 1000, accu, eta_o)
    laag = max(0.0, min(hoog, terug * eta_v - accu.slijtage_eur - accu.verkoopmarge_eur))
    return knik, laag


def _eindkosten(e, hoog: float, knik: float, laag: float):
    """Kosten-to-go aan het eind (negatief = waard), stuksgewijs lineair (v5.186.0)."""
    e = np.asarray(e, dtype=float)
    return -(np.minimum(e, knik) * hoog + np.maximum(e - knik, 0.0) * laag)


def _min_laad_net(accu: Accu, uren: float) -> float:
    """v5.186.0: de kleinste netlading die als opdracht telt (kWh AC boven het
    zonoverschot): de laadgrens, en nooit minder dan de drempel EPS_KWH."""
    return max(_min_laad_kwh(accu, uren), EPS_KWH)


class _Kw:
    """Alles wat het plan per kwartier vaststaat (v5.186.0): grenzen, de
    toegestane acties en hun stroom. Gedeeld door terug- en vooruitrekenen."""

    __slots__ = ("k", "uren", "overschot", "tekort", "op_slim", "af_slim", "eta_h", "max_op",
                 "tl_accu", "eis", "acties", "i_slim", "i_houden", "zonruimte", "stapkost")

    def __init__(self, k, accu: Accu, eta_l: float, eta_o: float, af_s, af_b):
        self.k = k
        uren = self.uren = getattr(k, "uren", 0.25) or 0.25
        overschot = self.overschot = max(k.zon_kwh - k.verbruik_kwh, 0.0)
        tekort = self.tekort = max(k.verbruik_kwh - k.zon_kwh, 0.0)
        # v5.191.0 (L-EMS-073): koude cellen laden trager (eerst verwarmen).
        lf = max(0.0, min(1.0, float(getattr(k, "laad_factor", 1.0) or 0.0)))
        self.op_slim = (accu.laden_slim_kw or accu.laden_kw) * uren * lf
        self.af_slim = accu.ontladen_kw * uren
        huis_ac = min(tekort, self.af_slim)
        self.eta_h = max(0.5, ontlaadrendement(huis_ac / uren * 1000, accu, eta_o))
        self.max_op = int(accu.laden_kw * uren * lf * eta_l / STAP_KWH + 1e-9)
        self.tl_accu = getattr(k, "teruglever_accu_eur", None)
        self.eis = None
        #: v5.186.0 (punt 9): ruimte die de zon na dit kwartier nog vult (zie `_zonruimte`).
        self.zonruimte = 0.0
        # ("slim" | "houden" | "laden" | "export" | "verkopen", stappen, AC-stroom)
        acties = [("slim", 0, 0.0)]
        self.i_slim = 0
        self.i_houden = None
        if tekort > EPS_KWH:
            self.i_houden = len(acties)
            acties.append(("houden", 0, 0.0))
        min_laad = _min_laad_net(accu, uren)
        for s in range(1, self.max_op + 1):
            b = s * STAP_KWH / eta_l
            net = b - overschot
            if net > EPS_KWH:
                if not accu.netladen or k.geen_netladen or net < min_laad - 1e-9:
                    continue
            elif accu.zon_opslaan:
                continue        # geen netlading: dat doet de slimme stand al
            acties.append(("laden", s, b))
        if (accu.zon_opslaan and accu.zon_export_afdwingbaar and not k.geen_zon_export
                and overschot > EPS_KWH):
            min_laad_kwh = _min_laad_kwh(accu, uren)
            for s in range(0, self.max_op + 1):
                b = s * STAP_KWH / eta_l
                if b >= min(overschot, self.op_slim) - 1e-9:
                    break
                if s == 0 or b >= min_laad_kwh - 1e-9:
                    acties.append(("export", s, b))
        zon_mee = overschot > EPS_KWH and (k.geen_zon_export or not accu.verkopen_bij_zon)
        if accu.verkopen and not k.verkoop_verboden and not zon_mee:
            # v5.186.0 (punt 1): alleen een ECHTE verkoop (boven het huistekort,
            # vanaf de opdrachtgrens) is een stap; een restje erboven was
            # afronding en is nu de exacte slimme dekking.
            grens = (accu.verkoop_kw if accu.verkoop_kw is not None else accu.ontladen_kw) * uren
            min_kwh = max(accu.min_actie_w / 1000 * uren, EPS_KWH)
            for s, b in zip(af_s, af_b):
                ac = -float(b)
                if ac - tekort >= min_kwh - 1e-9 and ac <= grens + 1e-9:
                    acties.append(("verkopen", int(s), -ac))
        self.acties = acties
        #: v5.186.0: de kosten van een stap met vaste stroom (alles behalve 'slim').
        self.stapkost = [None if soort == "slim" else _kosten_een(k, b, accu, self.tl_accu)
                         for soort, _s, b in acties]

    def slim(self, accu: Accu, e, cap: float, eta_l: float):
        """(AC-stroom, inhoud erna) van de slimme stand, exact (v5.186.0, punt 2)."""
        if self.overschot > 1e-9 and accu.zon_opslaan:
            erin = np.minimum(min(self.overschot, self.op_slim) * eta_l, np.maximum(cap - e, 0.0))
            return erin / eta_l, e + erin
        if self.tekort > 1e-9:
            ac = np.minimum(min(self.tekort, self.af_slim), np.maximum(e, 0.0) * self.eta_h)
            return -ac, e - ac / self.eta_h
        return np.zeros_like(e), e

    def evalueer(self, j: int, accu: Accu, e, waarde, raster, cap: float, eta_l: float, streng: bool = True):
        """(kosten, AC-stroom, inhoud erna) van actie j voor de inhouden `e`."""
        soort, s, b0 = self.acties[j]
        k = self.k
        extra = 0.0
        geldig = None
        if soort == "slim":
            b, e2 = self.slim(accu, e, cap, eta_l)
            if accu.huis_eerst and accu.zon_opslaan and self.overschot > EPS_KWH and accu.verkoopmarge_eur:
                # v5.186.0 (punt 9): zon die over de rand van een volle accu gaat,
                # telt (net als zon terugleveren, `export`) met de verkoopmarge.
                # Anders was 's middags netladen tot vol en de zon erna
                # terugleveren winst (teruglevering = prijs + premie): de
                # netlading werd via de zon verkocht.
                gemist = np.maximum(min(self.overschot, self.op_slim) * eta_l - (e2 - e), 0.0)
                extra = gemist * accu.verkoopmarge_eur
        elif soort == "houden":
            b, e2 = np.zeros_like(e), e
            if accu.bewaarmarge_eur:
                # v5.186.0 (punt 3): de bewaarmarge in het plan zelf - bewaren
                # terwijl het huis op het net draait kost de marge per kWh die de
                # accu had kunnen dekken. Zo bewaart het plan alleen voor minstens
                # die marge meer later; de toets achteraf (`te_duur_bewaard`)
                # blijft als controle (was: ronde na ronde kwartieren op dekken).
                extra = np.minimum(min(self.tekort, self.af_slim), np.maximum(e, 0.0) * self.eta_h) \
                    * accu.bewaarmarge_eur
            if streng and k.dekken:
                # v5.186.0 (punt 5): dekken verbiedt alleen bewaren met inhoud.
                geldig = e <= EPS_KWH
        elif soort == "laden":
            # v5.186.0: de laatste stap mag de accu tot vol laden (de accu stopt
            # dan zelf); met een doorlopende inhoud past een hele stap daar niet.
            e2 = np.minimum(e + s * STAP_KWH, cap)
            b = (e2 - e) / eta_l
            geldig = e + (s - 1) * STAP_KWH < cap - 1e-9
            if self.zonruimte > 0:
                # v5.186.0 (punt 9, huis eerst): niet uit het net laden in de
                # ruimte die de zon daarna nog vult - anders raakt de accu vol en
                # gaat die zon het net op: de netlading via de zon verkocht.
                geldig = geldig & (e2 <= np.maximum(cap - self.zonruimte, e) + 1e-9)
            if accu.bewaarmarge_eur and self.tekort > EPS_KWH:
                # v5.186.0: netladen terwijl het huis op het net draait is ook
                # bewaren (de accu dekt dan niet); zelfde marge als 'houden',
                # anders ontliep een mini-netlading de marge (koken 17:00).
                extra = np.minimum(min(self.tekort, self.af_slim), np.maximum(e, 0.0) * self.eta_h) \
                    * accu.bewaarmarge_eur
            if streng and k.dekken and k.inkoop_eur >= 0 and self.tekort > EPS_KWH:
                # v5.186.0 (punt 5): in een dekkwartier ook geen netlading met
                # inhoud: bij dezelfde prijs is laden voor later nog minder waard
                # dan bewaren (de bewaarmarge haalt het al niet). Zonder deze
                # regel laadde het plan tijdens het koken uit het net (17:00,
                # 47-49 ct) om de dekplicht te ontlopen. Leeg mag het wel.
                geldig = geldig & (e <= EPS_KWH)
        else:
            b = np.full(e.shape, b0)
            e2 = e + s * STAP_KWH
            if soort == "export":
                erin, _ = self.slim(accu, e, cap, eta_l)
                erin = erin * eta_l
                geldig = s * STAP_KWH < erin - 1e-9      # minder dan de slimme stand
                extra = np.maximum(erin - s * STAP_KWH, 0.0) * accu.verkoopmarge_eur
            else:   # verkopen
                geldig = e2 >= max(0.0, k.verkoop_vloer_kwh) - 1e-9
        stap = self.stapkost[j]
        if stap is None or (soort == "laden" and (e + s * STAP_KWH > cap + 1e-9).any()):
            # v5.186.0: zonder verkoop (b ligt tussen -tekort en +overschot, of
            # laadt): geen accu-export, dus een eenvoudige vorm (sneller).
            g = (k.verbruik_kwh - k.zon_kwh) + b
            stap = np.where(g >= 0, g * k.inkoop_eur, g * k.teruglever_eur) + np.maximum(-b, 0.0) * accu.slijtage_eur
            if accu.netlaadmarge_eur:
                stap = stap + np.maximum(b - self.overschot, 0.0) * accu.netlaadmarge_eur
        kosten = stap + np.interp(e2, raster, waarde) + extra
        if accu.bewaarkost_eur_per_kwh_uur:
            # v5.183.0 (punt 2): wat erin blijft, kost een beetje per uur.
            kosten = kosten + e2 * accu.bewaarkost_eur_per_kwh_uur * self.uren
        if self.eis is not None:
            # v5.186.0 (punt 6): zachte eis - een boete per kWh te kort.
            kosten = kosten + np.maximum(self.eis - e2, 0.0) * BOETE_EIS_EUR_PER_KWH
        if geldig is not None:
            kosten = np.where(geldig, kosten, np.inf)
        return kosten, b, e2

    def label(self, j: int, accu: Accu, b: float) -> tuple[str, float]:
        """(actie, kWh) van actie j bij AC-stroom b, voor de planrij."""
        soort = self.acties[j][0]
        if soort == "slim":
            if self.overschot > EPS_KWH and accu.zon_opslaan:
                return "zon", max(b, 0.0)
            if self.tekort > EPS_KWH:
                return ("huis", -b) if -b > EPS_KWH else ("houden", 0.0)
            if b < -1e-6:
                return "huis", -b    # v5.186.0 (punt 7): ook een klein (kort) kwartier
            return "zon", max(b, 0.0)
        if soort == "houden":
            return "houden", 0.0
        if soort == "laden":
            net = b - self.overschot
            return ("laden_net", net) if net > EPS_KWH else ("zon", b)
        if soort == "export":
            return "zon_export", max(b, 0.0)
        return "verkopen", -b - self.tekort


def _marginaal(waarde, raster, c: float) -> float | None:
    """v5.186.0: de marginale waarde van een kWh inhoud bij inhoud c (EUR per
    kWh inhoud): (V(c - stap) - V(c)) / stap. None als die niet eindig is."""
    if waarde is None or len(raster) < 2:
        return None
    lo = max(0.0, c - STAP_KWH)
    hi = lo + STAP_KWH
    if hi > raster[-1]:
        hi = raster[-1]
        lo = hi - STAP_KWH
    v = np.interp([lo, hi], raster, waarde)
    verschil = float(v[0] - v[1]) / STAP_KWH
    if not np.isfinite(verschil) or abs(verschil) >= GROOT_EUR / 10:
        return None
    return verschil


def _terugrekenen(kws: list, accu: Accu, raster, waarde, cap: float, eta_l: float,
                  waardes: list, vangnet: list):
    """Achterwaarts: per kwartier en inhoud de goedkoopste actie (v5.186.0).

    `waardes[t]` = de kosten-to-go na kwartier t (op het raster). v5.184.2
    (vangnet): blijft er voor een inhoud geen geldige actie over, dan nog eens
    zonder de dekregel. Een inhoud zonder enige actie krijgt GROOT_EUR.
    """
    n = len(kws)
    niveaus = len(raster)
    keuze = np.zeros((n, niveaus), dtype=np.int16)
    for t in range(n - 1, -1, -1):
        kw = kws[t]
        waardes[t] = waarde
        beste = np.full(niveaus, np.inf)
        beste_j = np.zeros(niveaus, dtype=np.int16)
        for j in range(len(kw.acties)):
            kosten, _b, _e2 = kw.evalueer(j, accu, raster, waarde, raster, cap, eta_l)
            beter = kosten < beste
            beste[beter] = kosten[beter]
            beste_j[beter] = j
        open_ = ~np.isfinite(beste)
        if open_.any():
            los = np.full(niveaus, np.inf)
            los_j = np.zeros(niveaus, dtype=np.int16)
            for j in range(len(kw.acties)):
                kosten, _b, _e2 = kw.evalueer(j, accu, raster, waarde, raster, cap, eta_l, streng=False)
                beter = kosten < los
                los[beter] = kosten[beter]
                los_j[beter] = j
            gebruikt = open_ & np.isfinite(los)
            beste[gebruikt] = los[gebruikt]
            beste_j[gebruikt] = los_j[gebruikt]
            vangnet[t] = gebruikt
        keuze[t] = beste_j
        waarde = np.where(np.isfinite(beste), np.minimum(beste, GROOT_EUR), GROOT_EUR)
    return keuze, waarde


def _vooruit(kws: list, accu: Accu, keuze, raster, waardes, c: float, cap: float,
             eta_l: float) -> tuple[list, float, float, float]:
    """Vooruit met een doorlopende inhoud (v5.186.0): per kwartier de beste
    van de acties die op de twee buurpunten gekozen zijn, plus de slimme stand
    en bewaren, opnieuw doorgerekend bij de echte inhoud."""
    rijen = []
    kosten_plan = 0.0
    kosten_zonder = 0.0
    niveaus = len(raster)
    for t, kw in enumerate(kws):
        k = kw.k
        waarde = waardes[t]
        j0 = min(int(c / STAP_KWH + 1e-9), niveaus - 1)
        j1 = min(j0 + 1, niveaus - 1)
        kandidaten = {int(keuze[t, j0]), int(keuze[t, j1]), kw.i_slim}
        if kw.i_houden is not None:
            kandidaten.add(kw.i_houden)
        e = np.array([c])
        beste = None
        for streng in (True, False):
            for j in sorted(kandidaten if streng else range(len(kw.acties))):
                kosten, b, e2 = kw.evalueer(j, accu, e, waarde, raster, cap, eta_l, streng)
                if np.isfinite(kosten[0]) and (beste is None or kosten[0] < beste[0] - 1e-12):
                    beste = (float(kosten[0]), j, float(b[0]), float(e2[0]))
            if beste is not None:
                via_vangnet = not streng
                break
        if beste is None:   # kan niet (de slimme stand is altijd geldig); zeker is zeker
            beste, via_vangnet = (0.0, kw.i_slim, 0.0, c), True
        _kost, j, b, c2 = beste
        c2 = min(max(c2, 0.0), cap)
        actie, kwh = kw.label(j, accu, b)
        g = k.verbruik_kwh - k.zon_kwh + b
        kosten_plan += float(_kosten_stap(k.verbruik_kwh, k.zon_kwh, k.inkoop_eur, k.teruglever_eur,
                                          np.array([b]), accu, kw.tl_accu)[0])
        g0 = k.verbruik_kwh - k.zon_kwh
        kosten_zonder += g0 * (k.inkoop_eur if g0 >= 0 else k.teruglever_eur)
        soort, s, _b0 = kw.acties[j]
        rij = {
            "begin": k.begin,
            "actie": actie,
            "kwh": round(kwh, 3),
            "accu_kwh": round(b, 3),
            "net_kwh": round(g, 3),
            # v5.186.0: doorlopende inhoud (was het raster van 0,1 kWh)
            "inhoud_kwh": round(c2, 3),
            "inhoud_delta_kwh": round(c2 - c, 3),
            # v5.183.3: waarmee het plan rekende (incl. live correctie en
            # apparaten), zodat de tabel accu + net = huis laat zien.
            "verbruik_kwh": round(k.verbruik_kwh, 3),
            "zon_kwh": round(k.zon_kwh, 3),
            # v5.162.0 / v5.177.0 (A4): de grootste laadstap van DIT kwartier
            # = vol vermogen.
            "vol_vermogen": soort == "laden" and s > 0 and s == kw.max_op,
            # v5.168.0: wat het kwartier kost (incl. belasting) en waarmee
            # het plan rekende (de marginale prijs, bij een overschot lager).
            "prijs_eur": round(k.inkoop_eur if k.prijs_incl_eur is None else k.prijs_incl_eur, 4),
            "rekenprijs_eur": round(k.inkoop_eur, 4),
            # v5.165.0: de duur waarover verbruik en zon gelden.
            "uren": round(kw.uren, 4),
            # v5.177.0 (A1): de verkoopvloer waarmee het plan rekende.
            # v5.186.0: ook in een kwartier met een verboden verkoop de echte vloer.
            "verkoop_vloer_kwh": round(k.verkoop_vloer_kwh, 2),
        }
        if getattr(k, "laad_factor", 1.0) < 1.0:
            rij["laad_factor"] = round(k.laad_factor, 3)   # v5.191.0 (L-EMS-073)
        # v5.186.0 (punt 3): de marginale waarde van de inhoud na dit kwartier
        # (EUR per kWh inhoud) - de maat voor bewaren en verkopen achteraf.
        lam = _marginaal(waarde, raster, c2)
        if lam is not None:
            rij["waarde_inhoud_eur_per_kwh"] = round(lam, 4)
        if actie == "houden" and kw.tekort > EPS_KWH and c2 > EPS_KWH:
            # v5.186.0 (punt 3): wat de inhoud die dekken hier had gekost het
            # plan later waard is (EUR per kWh inhoud, gemiddeld over die daling).
            daling = min(min(kw.tekort, kw.af_slim) / kw.eta_h, c2)
            v = np.interp([c2 - daling, c2], raster, waarde)
            gem = float(v[0] - v[1]) / daling
            if np.isfinite(gem) and abs(gem) < GROOT_EUR / 10:
                rij["waarde_dekking_eur_per_kwh"] = round(gem, 4)
        if via_vangnet:
            rij["vangnet"] = True   # v5.184.2: zonder de dekregels gekozen
        if actie == "laden_net":
            # v5.177.0 (A3): wat een kWh uit het net hier later oplevert (per kWh AC).
            rij["waarde_eur_per_kwh"] = None if lam is None else round(lam * eta_l, 4)
        if soort == "slim" or actie == "houden":
            # v5.175.0 / v5.177.0 (A12): wat de slimme stand aan de netkant doet
            # (W, - = laden); nu exact, dus gelijk aan de stroom van het plan.
            rij["accu_ac_w"] = round(-b / kw.uren * 1000) if kw.uren > 0 else 0
        rijen.append(rij)
        c = c2
    return rijen, kosten_plan, kosten_zonder, c


def _zonruimte(kws: list, accu: Accu, eta_l: float) -> None:
    """v5.186.0 (punt 9): per kwartier hoeveel inhoud de zon daarna nog
    opslaat voordat de avond begint (het eerste kwartier met tekort en zonder
    zon), met de tekorten van bewolkte kwartieren ertussen verrekend: het
    hoogste lopende saldo. Alleen met huis eerst; bij een negatieve prijs geen
    grens (dan verdient netladen zelf)."""
    if not (accu.huis_eerst and accu.zon_opslaan):
        return
    lopend_na = []          # per kwartier: (bijdrage, avond begint hier)
    for kw in kws:
        winst = min(kw.overschot, kw.op_slim) * eta_l
        verlies = min(kw.tekort, kw.af_slim) / kw.eta_h
        avond = kw.tekort > EPS_KWH and kw.k.zon_kwh <= EPS_KWH
        lopend_na.append((winst - verlies, avond))
    n = len(kws)
    for t in range(n):
        if kws[t].k.inkoop_eur < 0:
            continue
        saldo = hoogste = 0.0
        for u in range(t + 1, n):
            bijdrage, avond = lopend_na[u]
            if avond:
                break
            saldo += bijdrage
            hoogste = max(hoogste, saldo)
        kws[t].zonruimte = hoogste


def _eis_niveau(kws: list, accu: Accu, t_eis: int, c_start: float, cap: float, eta_l: float) -> float:
    """v5.186.0 (punt 6): de inhoud die na kwartier `t_eis` hooguit haalbaar
    is, met het lopende (korte) kwartier naar zijn resterende tijd."""
    c = c_start
    for kw in kws[: t_eis + 1]:
        c = min(cap, c + kw.max_op * STAP_KWH)
    return c


def zon_export_laat_huis_tekort(rijen: list[dict], leeg_kwh: float = 0.01) -> bool:
    """Levert het plan zon terug terwijl het huis daarna, vóór het volgende
    laden uit het net, met een lege accu aan het net hangt? (v5.179.1)

    Akkoord Ruud 04-11 ("woning gaat voor, dus opslaan in accu is toch
    beter?"): zon gaat het net niet op zolang het huis later met een lege
    accu stroom inkoopt. Het geldverschil was een paar cent per dag.
    """
    gezien = False
    for r in rijen:
        actie = r.get("actie")
        # v5.181.2 (g): een verkoop met zonoverschot levert de zon ook terug
        # (het net krijgt meer dan de accu levert).
        if actie == "zon_export" or _zon_mee(r):
            gezien = True
            continue
        if not gezien:
            continue
        if actie == "laden_net":
            return False
        if actie != "verkopen" and (r.get("net_kwh") or 0.0) > EPS_KWH and (r.get("inhoud_kwh") or 0.0) <= leeg_kwh:
            return True
    return False


def vloeren_gelijktrekken(kwartieren: list[Kwartier], bodem_kwh: float = 0.0,
                          eta_o: float = 1.0) -> list[Kwartier]:
    """Eén verkoopvloer langs het hele plan (v5.181.2).

    Gemeten 04-11 11:27: met een volle accu dekte het plan om 16:45
    (50,6 ct) en 17:45 (50,9 ct) alleen het huis en verkocht het pas van
    18:00 tot 19:15 (49,5-50,0 ct). Oorzaak: de vloer per kwartier is de
    huisreserve tot het goedkope blok, MET een marge evenredig aan wat er
    vanaf dat kwartier nog nodig is. Een vroeger kwartier heeft een langere
    rest -> een grotere marge -> een hogere vloer, en de verkoop schoof naar
    latere, goedkopere kwartieren. Terwijl X kWh om 16:45 of om 18:00
    verkopen op hetzelfde uitkomt als het huis er tussendoor uit de accu
    draait: de eindstand bij het blok is gelijk.

    Nu: de marge geldt één keer, als eindvoorwaarde. Het anker is het
    laatste kwartier vóór het blok (het laatste met een vloer boven de
    bodem): zijn vloer blijft zoals hij was - met de marge op wat daarna
    nog nodig is en de bodem. Elk eerder kwartier krijgt die vloer plus
    het verwachte huistekort (verbruik - zon) ertussen, en nooit meer dan
    zijn eigen oude vloer. De vloer zakt dus precies met het huisverbruik:
    verkopen kost in elk kwartier evenveel ruimte en het plan kiest de
    duurste. Het huis tot het blok blijft beschermd (het hele tekort ertussen
    plus de marge van het anker), alleen de dubbel getelde marge vooraan
    vervalt. Een kwartier waarvan de volgende vloer op de bodem staat (in
    het blok, of niets nodig) is zelf een anker. Het tekort telt aan de
    netkant (zonder ontlaadverlies): bij twijfel liever eerder dan later.

    v5.186.0 (punt 10): de vloer geldt voor de inhoud NA kwartier t; erbij
    komt dus het tekort van kwartier t+1 (was dat van t zelf: een kwartier
    verschoven), gedeeld door het ontlaadrendement. Een rendement boven 1
    (inhoud -> AC) telt als 1: de vloer zakt niet onder het tekort aan de netkant.
    """
    n = len(kwartieren)
    uit = list(kwartieren)
    bodem = max(0.0, float(bodem_kwh or 0.0)) + 1e-9
    eta = max(0.5, min(1.0, float(eta_o or 1.0)))
    volgende = None
    tekort_volgende = 0.0
    for t in range(n - 1, -1, -1):
        k = kwartieren[t]
        oud = max(0.0, float(k.verkoop_vloer_kwh or 0.0))
        vloer = oud
        if volgende is not None and volgende > bodem:
            vloer = min(oud, volgende + tekort_volgende / eta)
        if vloer < oud - 1e-12:
            uit[t] = replace(k, verkoop_vloer_kwh=vloer)
        volgende = vloer
        tekort_volgende = max(0.0, k.verbruik_kwh - k.zon_kwh)
    return uit


def _zon_mee(r: dict) -> bool:
    """Een verkoop met zonoverschot levert de zon ook terug (v5.181.2, g): het
    net krijgt meer dan de accu levert."""
    return (r.get("actie") == "verkopen"
            and -(r.get("net_kwh") or 0.0) > -(r.get("accu_kwh") or 0.0) + EPS_KWH)


def zinloze_verkopen(rijen: list[dict], kwartieren: list[Kwartier], accu: Accu,
                     uitgebreid: bool = False) -> list[int]:
    """Verkoopkwartieren die niet meer opleveren dan bewaren (v5.181.2, g).

    Live 04-11 12:01: verkopen om 12:00 (rekenprijs 26,6 ct + 2 ct premie)
    en vanaf 12:15 de accu weer vullen met zon die 26-30 ct aan teruglevering
    had opgebracht. Rondrit (83,5 %), slijtage (4,22 ct) en marge (2 ct)
    maken dat altijd verlies; het plan koos het op een gelijkspel van een
    tiende cent, via de zon die met de verkoop mee het net op ging.

    Een verkoop blijft alleen staan als hij per kWh inhoud meer oplevert
    (prijs x ontlaadrendement - slijtage - marge) dan het goedkoopste latere
    bijvullen kost: zon tegen de gemiste teruglevering, net tegen de
    inkoopprijs plus de netlaadmarge, beide gedeeld door het laadrendement
    (alles per kWh inhoud).

    v5.186.0 (punt 3): bewust NIET de marginale waarde uit het plan. Het plan
    verkoopt precies tot die waarde (de laatste verkochte kWh is altijd een
    gelijkspel): elke ronde een nieuwe 'zinloze' verkoop, tot de rondegrens.
    De nepverkopen uit de afronding (de oorzaak van 04-11 12:01) bestaan niet
    meer sinds de exacte slimme dekking.

    v5.186.0: `uitgebreid` (voor `plan`) geeft ook de kwartieren zonder verkoop
    waarin een verkoop even zinloos zou zijn (rendement van de verkoopband):
    anders schoof het plan de verkoop elke ronde één kwartier op.
    """
    eta_l, eta_o = rendementen(accu)
    n = len(rijen)
    # het goedkoopste bijvullen NA elk kwartier (achteraan beginnen)
    na: list = [None] * n
    beste = None
    for u in range(n - 1, -1, -1):
        na[u] = beste
        ru, ku = rijen[u], kwartieren[u]
        if (ru.get("accu_kwh") or 0.0) <= EPS_KWH:
            continue
        if ru.get("actie") == "laden_net":
            kost = (ku.inkoop_eur + accu.netlaadmarge_eur) / eta_l
        elif ru.get("actie") in ("zon", "zon_export"):
            kost = ku.teruglever_eur / eta_l
        else:
            continue
        beste = kost if beste is None else min(beste, kost)
    verkoop_kw = accu.verkoop_kw if accu.verkoop_kw is not None else accu.ontladen_kw
    eta_v = ontlaadrendement(verkoop_kw * 1000, accu, eta_o)
    uit = []
    for t, r in enumerate(rijen):
        if na[t] is None:
            continue
        k = kwartieren[t]
        prijs = k.teruglever_eur if getattr(k, "teruglever_accu_eur", None) is None else k.teruglever_accu_eur
        inhoud = -(r.get("inhoud_delta_kwh") or 0.0)
        ac = -(r.get("accu_kwh") or 0.0)
        if r.get("actie") == "verkopen" and inhoud > 1e-9 and ac > 1e-9:
            verhouding = ac / inhoud
        elif uitgebreid:
            verhouding = eta_v
        else:
            continue
        if verhouding * (prijs - accu.slijtage_eur - accu.verkoopmarge_eur) <= na[t] + 1e-9:
            uit.append(t)
    return uit


def verkopen_voor_huis(rijen: list[dict], kwartieren: list[Kwartier], accu: Accu,
                       uitgebreid: bool = False) -> list[int]:
    """Verkoopkwartieren die tegen de huis-eerst-regel ingaan (v5.182.0).

    Akkoord Ruud 04-11 13:45. Live 13:38: netladen om 13:30 voor 37 ct,
    verkopen van 18:45 tot 20:15 voor ~50 ct, en daarna 21:00-24:00 het huis
    op het net terwijl de accu op 40 % bleef staan voor een verkoop de
    volgende ochtend. Financieel een paar cent per kWh beter (de 2 ct
    terugleverpremie), maar Ruud wil de lading liever in de woning.

    v5.186.0 (punt 8): een verkoop is verboden als
    * hij lading uit het net zou verkopen: het plan houdt bij hoeveel inhoud
      uit het net kwam (het deel van een netlading boven het zonoverschot, x
      laadrendement); het huis gebruikt die lading eerst, een verkoop alleen
      de rest. Was: één netlading (hoe klein ook) verbood elke latere verkoop
      tot de accu leeg stond; of
    * het huis daarna, in de slimme stand, met een lege accu aan het net komt
      voordat de accu weer vol raakt (zon) of uit het net laadt. Het
      zonoverschot telt mee naar wat het werkelijk bijvult (was: het eerste
      kwartier met een klein overschot gold al als bijvullen).

    `uitgebreid` (voor `plan`): bij een huistekort ook de kwartieren tot waar
    het huis leeg zou staan - een verkoop daar heeft hetzelfde probleem, en
    anders schoof het plan de verkoop elke ronde één kwartier op.
    """
    eta_l, eta_o = rendementen(accu)
    eta_o = max(eta_o, 0.5)
    cap = int(accu.bruikbaar_kwh / STAP_KWH + 1e-9) * STAP_KWH
    op_slim = accu.laden_slim_kw or accu.laden_kw
    n = len(rijen)
    uit = []
    uit_net = 0.0       # inhoud (kWh) die uit het net kwam
    vorige = max(0.0, min(accu.inhoud_kwh, cap))
    for t, r in enumerate(rijen):
        k = kwartieren[t]
        actie = r.get("actie")
        inhoud = r.get("inhoud_kwh") or 0.0
        delta = r.get("inhoud_delta_kwh")
        if delta is None:
            delta = inhoud - vorige
        if actie == "verkopen" and -(r.get("accu_kwh") or 0.0) > 1e-9:
            if inhoud < uit_net - EPS_KWH:
                uit.append(t)               # verkoopt lading uit het net
            else:
                c = inhoud
                for u in range(t + 1, n):
                    ku = kwartieren[u]
                    if rijen[u].get("actie") == "laden_net":
                        break
                    uren = getattr(ku, "uren", 0.25) or 0.25
                    c -= min(max(ku.verbruik_kwh - ku.zon_kwh, 0.0), accu.ontladen_kw * uren) / eta_o
                    if c < -EPS_KWH:
                        uit.extend(range(t, u + 1) if uitgebreid else (t,))
                        break
                    c += min(max(ku.zon_kwh - ku.verbruik_kwh, 0.0), op_slim * uren) * eta_l
                    if c >= cap - EPS_KWH:
                        break               # de zon vult de accu weer: de verkoop was overschot
        if actie == "laden_net":
            overschot = max(k.zon_kwh - k.verbruik_kwh, 0.0)
            uit_net += max(0.0, (r.get("accu_kwh") or 0.0) - overschot) * eta_l
        elif actie == "huis" and delta < 0:
            uit_net += delta                # het huis gebruikt de netlading eerst
        uit_net = max(0.0, min(uit_net, inhoud))
        vorige = inhoud
    return uit


def te_duur_bewaard(rijen: list[dict], kwartieren: list[Kwartier], accu: Accu,
                    leeg_kwh: float = 0.05) -> list[int]:
    """Kwartieren waarin het plan lading bewaart terwijl het huis op het net
    draait, voor te weinig voordeel (v5.183.0, bewaarmarge).

    Akkoord Ruud 04-11 14:04. Live 14:01: 1,9 kWh bleef van 18:00 tot 05:30
    staan (huis op het net, 37-50 ct) voor morgenavond (55 ct); vannacht
    bijladen kostte met verlies, slijtage en datacorrectie net iets meer.
    Het verschil was een paar cent; Ruud wil de lading dan in de woning.

    v5.186.0 (punt 3): wat de bewaarde lading later oplevert is de marginale
    waarde uit het plan (`waarde_inhoud_eur_per_kwh`, per kWh inhoud), omgerekend
    naar een prijs aan de netkant: waarde / ontlaadrendement + slijtage. Was de
    prijs van het eerste latere leverkwartier, ook als de lading pas veel later
    of helemaal niet daar terechtkwam. Is die prijs minder dan
    `bewaarmarge_eur` boven de prijs nu, dan moet de accu hier dekken. Rijen
    zonder die waarde (losse toetsen) houden de oude schatting, met het
    bijladen nu door beide rendementen.
    """
    if not accu.bewaarmarge_eur:
        return []
    eta_l, eta_o = rendementen(accu)
    eind = accu.eindprijs_eur
    if eind is None:
        eind = float(np.percentile([k.inkoop_eur for k in kwartieren], 75))
    n = len(rijen)
    uit = []
    for t, r in enumerate(rijen):
        k = kwartieren[t]
        if r.get("actie") != "houden" or (r.get("net_kwh") or 0.0) <= EPS_KWH:
            continue
        if (r.get("inhoud_kwh") or 0.0) <= leeg_kwh or k.verbruik_kwh - k.zon_kwh <= EPS_KWH:
            continue
        lam = r.get("waarde_dekking_eur_per_kwh", r.get("waarde_inhoud_eur_per_kwh"))
        if lam is not None:
            uren = getattr(k, "uren", 0.25) or 0.25
            ac = min(k.verbruik_kwh - k.zon_kwh, accu.ontladen_kw * uren)
            eta_h = max(0.5, ontlaadrendement(ac / uren * 1000, accu, eta_o))
            later = lam / eta_h + accu.slijtage_eur
        else:
            later = None
            bijladen = None
            for u in range(t + 1, n):
                ru, ku = rijen[u], kwartieren[u]
                if ru.get("actie") == "laden_net":
                    kost = (ku.inkoop_eur + accu.netlaadmarge_eur) / (eta_l * eta_o) + accu.slijtage_eur
                    bijladen = kost if bijladen is None else min(bijladen, kost)
                elif ru.get("actie") in ("huis", "verkopen") and (ru.get("accu_kwh") or 0.0) < -EPS_KWH:
                    later = ku.inkoop_eur if ru.get("actie") == "huis" else (
                        ku.teruglever_eur if ku.teruglever_accu_eur is None else ku.teruglever_accu_eur)
                    break
            if later is None:
                later = eind
            if bijladen is not None:
                later = min(later, bijladen)
        if later - k.inkoop_eur < accu.bewaarmarge_eur - 1e-9:
            uit.append(t)
    return uit


def _vol_kwh(accu: Accu) -> float:
    """Vanaf deze inhoud telt de accu als vol voor de toetsen."""
    return accu.bruikbaar_kwh - STAP_KWH - 1e-9


def zon_export_zonder_overschot(rijen: list[dict], accu: Accu) -> list[int]:
    """Zon terugleveren terwijl de accu niet vol raakt (v5.184.0).

    Akkoord Ruud 04-11 15:56: zon alleen terugleveren als het echt overschot
    is - als de accu anders vol zou raken. Live 15:54: 05-11 09:30-10:45 zon
    terug voor 39-43 ct (+2 ct) en om 11:45 bijladen uit het net voor 37 ct;
    de accu kwam niet verder dan ~70 % en was om 21:30 leeg.

    Een kwartier met zon terugleveren (ook een verkoop met zonoverschot) mag
    alleen als de accu daarna vol raakt voordat hij weer levert, uit het net
    laadt of het huis het net op gaat.
    """
    vol = _vol_kwh(accu)
    n = len(rijen)
    uit = []
    for t, r in enumerate(rijen):
        actie = r.get("actie")
        if actie != "zon_export" and not _zon_mee(r):
            continue
        overschot = False
        for u in range(t, n):
            ru = rijen[u]
            if (ru.get("inhoud_kwh") or 0.0) >= vol:
                overschot = True
                break
            if u > t and (ru.get("actie") in ("huis", "verkopen", "laden_net")
                          or (ru.get("net_kwh") or 0.0) > EPS_KWH):
                break
        if not overschot:
            uit.append(t)
    return uit


def netladen_voor_zonoverloop(rijen: list[dict], kwartieren: list[Kwartier], accu: Accu) -> list[int]:
    """Netladen vlak voor zon die toch over de rand gaat (v5.186.0, punt 9).

    Raakt de accu na een netlading vol en levert de zon dan terug voordat de
    accu weer iets levert, dan had die zon de ruimte zelf gevuld: de netlading
    wordt zo via de zon alsnog verkocht. Verboden worden de LAATSTE
    netladingen vóór die overloop, tot ze samen de teruggeleverde zon dekken
    (de eerdere blijven: die heeft het huis nog nodig). Een negatieve
    inkoopprijs telt niet (dan verdient laden zelf al).
    """
    vol = _vol_kwh(accu)
    uit: list[int] = []
    open_: list[tuple[int, float]] = []    # netladingen sinds de accu voor het laatst leverde
    overloop = 0.0

    def afsluiten():
        nonlocal overloop
        if overloop > EPS_KWH:
            gedekt = 0.0
            for t, kwh in reversed(open_):
                if gedekt >= overloop - 1e-9:
                    break
                uit.append(t)
                gedekt += kwh
        open_.clear()
        overloop = 0.0

    for t, r in enumerate(rijen):
        actie = r.get("actie")
        if actie in ("huis", "verkopen") and (r.get("accu_kwh") or 0.0) < -EPS_KWH:
            afsluiten()
            continue
        if actie == "laden_net" and kwartieren[t].inkoop_eur >= 0:
            if overloop > EPS_KWH:
                afsluiten()
            open_.append((t, float(r.get("kwh") or 0.0)))
        elif open_ and (r.get("inhoud_kwh") or 0.0) >= vol and (r.get("net_kwh") or 0.0) < -EPS_KWH:
            overloop += -(r.get("net_kwh") or 0.0)
    afsluiten()
    return sorted(uit)


def _zon_export_voor_tekort(rijen: list[dict], leeg_kwh: float = 0.01) -> list[int]:
    """De terugleverkwartieren vóór het huis met een lege accu aan het net komt
    (v5.179.1, zie `zon_export_laat_huis_tekort`); leeg = er is geen."""
    gezien: list[int] = []
    for t, r in enumerate(rijen):
        actie = r.get("actie")
        if actie == "zon_export" or _zon_mee(r):
            gezien.append(t)
            continue
        if not gezien:
            continue
        if actie == "laden_net":
            return []
        if actie != "verkopen" and (r.get("net_kwh") or 0.0) > EPS_KWH and (r.get("inhoud_kwh") or 0.0) <= leeg_kwh:
            return gezien
    return []


def _overtredingen(rijen: list[dict], kwartieren: list[Kwartier], accu: Accu,
                   uitgebreid: bool = False) -> dict[str, set]:
    """Alle toetsen achteraf op een plan (v5.186.0), per soort de kwartieren.
    `uitgebreid`: de vlaggen voor de volgende ronde (zie de toetsen)."""
    uit = {"zinloze_verkopen": set(zinloze_verkopen(rijen, kwartieren, accu, uitgebreid))}
    if accu.huis_eerst:
        uit["verkopen_voor_huis"] = set(verkopen_voor_huis(rijen, kwartieren, accu, uitgebreid))
        uit["zon_export_zonder_overschot"] = set(zon_export_zonder_overschot(rijen, accu))
        uit["netladen_voor_zonoverloop"] = set(netladen_voor_zonoverloop(rijen, kwartieren, accu))
    if accu.bewaarmarge_eur:
        uit["te_duur_bewaard"] = set(te_duur_bewaard(rijen, kwartieren, accu))
    if accu.zon_export_afdwingbaar:
        # v5.186.0 (punt 14): was `_waardeplan_huis_eerst` in de sturing - die
        # zette terugleveren en verkopen bij zon voor de hele horizon uit en
        # rekende opnieuw. Nu per kwartier, zoals de andere toetsen.
        uit["zon_export_laat_huis_tekort"] = set(_zon_export_voor_tekort(rijen))
    return uit


#: v5.186.0: welke vlag een overtreding in de volgende ronde zet.
_VLAG_VAN = {
    "zinloze_verkopen": "verkoop_verboden",
    "verkopen_voor_huis": "verkoop_verboden",
    "te_duur_bewaard": "dekken",
    "zon_export_zonder_overschot": "geen_zon_export",
    "zon_export_laat_huis_tekort": "geen_zon_export",
    "netladen_voor_zonoverloop": "geen_netladen",
}


#: v5.186.0: de volgorde waarin de toetsen vlaggen zetten (zie `plan`).
_GROEPEN = (
    ("zinloze_verkopen", "verkopen_voor_huis"),
    ("te_duur_bewaard", "zon_export_zonder_overschot", "zon_export_laat_huis_tekort"),
    ("netladen_voor_zonoverloop",),
)


def plan(kwartieren: list[Kwartier], accu: Accu) -> Uitkomst:
    """Het goedkoopste accuplan over de gegeven kwartieren.

    v5.181.2 (g): met toetsen achteraf - een overtreding zet een vlag op dat
    kwartier (geen verkoop, dekken, geen zon terug, geen netlading) en het plan
    wordt opnieuw berekend; hooguit MAX_RONDES rondes.

    v5.186.0 (punt 5/15): elke ronde toetst het plan van die ronde op de
    kwartieren met de vlaggen tot dan toe. De vlaggen blijven staan (de
    vereniging over de rondes): dat is de rem tegen heen-en-weer schuiven,
    niet de toets zelf - een vlag verbiedt alleen die ene keuze (dekken
    alleen nog bewaren met inhoud). De uitkomst zegt hoeveel rondes het kostte,
    welke overtredingen er nog staan en of de grens bereikt is.
    """
    basis = list(kwartieren)
    werk = basis
    res = _plan(werk, accu)
    vlaggen: dict[str, set] = {v: set() for v in set(_VLAG_VAN.values())}
    rondes = 1
    limiet = False
    while res.beschikbaar:
        over = _overtredingen(res.kwartieren, werk, accu, uitgebreid=True)
        nieuw = False
        voorstel = {v: set(s) for v, s in vlaggen.items()}
        # v5.186.0: per ronde alleen de eerste groep met nieuwe overtredingen;
        # een latere groep hangt van de eerdere af (een netlading voor de
        # verkoop lijkt anders 'overbodig' omdat de accu vol raakt, en verdwijnt
        # samen met de verkoop, terwijl het huis hem daarna wel nodig heeft).
        for groep in _GROEPEN:
            for soort in groep:
                kwartieren_ = over.get(soort) or set()
                vlag = _VLAG_VAN[soort]
                if kwartieren_ - voorstel[vlag]:
                    nieuw = True
                    voorstel[vlag] |= kwartieren_
            if nieuw:
                break
        if not nieuw:
            break
        if rondes >= MAX_RONDES:
            limiet = True
            break
        vlaggen = voorstel
        werk = [replace(k,
                        verkoop_verboden=k.verkoop_verboden or t in vlaggen["verkoop_verboden"],
                        dekken=k.dekken or t in vlaggen["dekken"],
                        geen_zon_export=k.geen_zon_export or t in vlaggen["geen_zon_export"],
                        geen_netladen=k.geen_netladen or t in vlaggen["geen_netladen"])
                for t, k in enumerate(basis)]
        res = _plan(werk, accu)
        rondes += 1
    res.rondes = rondes
    res.rondelimiet = limiet
    res.zon_export_geweigerd = len(vlaggen["geen_zon_export"])
    if res.beschikbaar:
        over = _overtredingen(res.kwartieren, werk, accu)
        res.resterend = {soort: len(s) for soort, s in over.items() if s}
    return res


def _plan(kwartieren: list[Kwartier], accu: Accu) -> Uitkomst:
    """Het goedkoopste accuplan over de gegeven kwartieren (zonder de toetsen)."""
    n = len(kwartieren)
    if n == 0:
        return Uitkomst(False, "geen prijzen vooruit")
    if accu.bruikbaar_kwh <= STAP_KWH:
        return Uitkomst(False, "geen bruikbare accu-inhoud")
    eta_l, eta_o = rendementen(accu)
    niveaus = int(accu.bruikbaar_kwh / STAP_KWH + 1e-9) + 1
    raster = np.arange(niveaus) * STAP_KWH
    cap = float(raster[-1])
    # v5.165.0: verkopen per vermogensband (v5.183.5: op het handmatige vermogen).
    af_s, af_b = _ontlaadstappen(accu, eta_o, accu.verkoop_kw)
    kws = [_Kw(k, accu, eta_l, eta_o, af_s, af_b) for k in kwartieren]
    _zonruimte(kws, accu, eta_l)
    eind = eindwaarde(kwartieren, accu, eta_o)
    knik, laag = eindwaarde_knik(kwartieren, accu, eta_l, eta_o, eind, cap)
    waarde = _eindkosten(raster, eind, knik, laag)
    # v5.186.0: de inhoud loopt door (was naar beneden afgerond op 0,1 kWh,
    # v5.177.0 A12): de slimme dekking is nu exact, ook voor een restje.
    c = min(max(accu.inhoud_kwh, 0.0), cap)
    c_start = c
    if accu.vol_na_kwartier is not None and accu.netladen and 0 <= accu.vol_na_kwartier < n:
        t_eis = accu.vol_na_kwartier
        kws[t_eis].eis = _eis_niveau(kws, accu, t_eis, c_start, cap, eta_l)
    waardes: list = [None] * n
    vangnet: list = [None] * n
    keuze, waarde0 = _terugrekenen(kws, accu, raster, waarde, cap, eta_l, waardes, vangnet)
    if float(np.interp(c_start, raster, waarde0)) >= GROOT_EUR / 2:
        return Uitkomst(False, "geen haalbaar plan")
    rijen, kosten_plan, kosten_zonder, c = _vooruit(kws, accu, keuze, raster, waardes, c_start, cap, eta_l)
    # verschil in inhoud tegen de eindwaarde verrekenen (begin en eind)
    kosten_plan += float(_eindkosten(c, eind, knik, laag)) - float(_eindkosten(c_start, eind, knik, laag))
    return Uitkomst(
        True,
        "",
        rijen,
        round(kosten_plan, 3),
        round(kosten_zonder, 3),
        round(eind, 4),
        eindwaarde_knik_kwh=round(knik, 2),
        eindwaarde_laag_eur_per_kwh=round(laag, 4),
    )
