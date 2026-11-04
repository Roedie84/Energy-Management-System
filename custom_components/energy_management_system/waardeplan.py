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

from dataclasses import dataclass, field
from statistics import median

import numpy as np

STAP_KWH = 0.1
EPS_KWH = 0.02
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


@dataclass
class Uitkomst:
    beschikbaar: bool
    reden: str = ""
    kwartieren: list = field(default_factory=list)
    kosten_plan_eur: float | None = None
    kosten_zonder_accu_eur: float | None = None
    eindwaarde_eur_per_kwh: float | None = None


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


def _ontlaadstappen(accu: Accu, eta_o: float) -> tuple[np.ndarray, np.ndarray]:
    """De ontlaadstappen (negatief, in STAP_KWH) en hun AC-stroom (v5.165.0).

    Per stap het rendement van de band waarin het vermogen valt. De band
    volgt uit het vermogen aan de netkant, dat zelf van het rendement
    afhangt: twee keer bijstellen is genoeg (drie banden).
    """
    grens_kwh = accu.ontladen_kw * accu.duur_h
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


def _zon_regel(k, accu: Accu, s: int, b: float, s_min, min_kwh: float, min_laad_kwh: float = 0.0):
    """Welke inhouden deze stap mogen bij de zonregel, en wat hij extra kost
    (v5.175.0). (geldig-masker of None = alle, extra kosten per inhoud of 0)."""
    if s_min is None or s >= 0 and (s_min <= s).all():
        return None, 0.0
    tekort = max(k.verbruik_kwh - k.zon_kwh, 0.0)
    if b < 0 and -b - tekort >= min_kwh - 1e-9:
        return None, 0.0            # echt verkopen: handmatig, de zon gaat mee het net op
    if accu.zon_export_afdwingbaar and s >= 0:
        # Terugleveren wat de slimme stand zou opslaan mag, met de marge.
        gemist = np.maximum(s_min - s, 0) * STAP_KWH
        # v5.177.0 (A11/A12): minder opslaan dan het overschot gaat met een
        # vast laadvermogen (handmatig); onder de laadgrens alleen 0 W.
        geldig = None
        if 0 < s and b < min_laad_kwh - 1e-9:
            geldig = s_min <= s
        return geldig, gemist * accu.verkoopmarge_eur
    if s < 0:
        # Een ontlaadrestje onder de opdrachtgrens wordt 'huis' (smart): die
        # ontlaadt niet bij een overschot, maar slaat het op.
        return np.zeros(len(s_min), dtype=bool), 0.0
    return s_min <= s, 0.0


def _kwartier_grenzen(k, accu: Accu, eta_l: float) -> tuple[float, float, float, int]:
    """(uren, laadgrens, ontlaadgrens (kWh AC), grootste laadstap) van een
    kwartier. v5.177.0 (A4): het lopende kwartier telt maar zijn resterende
    uren; met een vast kwartier plande het meer dan er in de tijd past."""
    uren = getattr(k, "uren", 0.25) or 0.25
    max_op = int(accu.laden_kw * uren * eta_l / STAP_KWH + 1e-9)
    return uren, accu.laden_kw * uren + 1e-9, accu.ontladen_kw * uren + 1e-9, max_op


def _min_laad_kwh(accu: Accu, uren: float) -> float:
    """De kleinste netlading (kWh AC) in een kwartier van `uren` (v5.177.0)."""
    return (accu.min_laad_w or accu.min_actie_w) / 1000 * uren


def _stap_toegestaan(accu: Accu, b: float, overschot: float, tekort: float, grenzen, eta_l: float) -> bool:
    """Mag deze stap in dit kwartier? (v5.177.0, A4 en A12)

    A12: een netlading tussen een afrondingsrestje (een halve stap boven het
    zonoverschot) en de laadgrens voert de sturing niet uit ('zon'/'houden');
    het plan rekende er wel mee: 13-23 kwartieren per dag 'afwijking accu'.
    Zo'n stap bestaat nu niet meer in het plan.
    """
    uren, op, af, _max = grenzen
    if b > op or -b > af:
        return False
    if b > 0 and not accu.netladen and b > overschot + 1e-9:
        return False
    if b < 0 and not accu.verkopen and -b > tekort + 1e-9:
        return False
    min_laad = _min_laad_kwh(accu, uren)
    if b > 0 and min_laad > 0:
        net = b - overschot
        if STAP_KWH / eta_l / 2 + EPS_KWH < net < min_laad - 1e-9:
            return False
    return True


def _terugrekenen(kwartieren, accu: Accu, stappen, b_stap, waarde, niveaus, eis=None,
                  eta_l: float = 1.0, max_op: int = 0, waardes: list | None = None):
    """Achterwaarts: per kwartier en inhoud de goedkoopste stap.

    `eis` = (kwartier, niveau): na dat kwartier minstens dat niveau.
    v5.175.0: met `accu.zon_opslaan` slaat elke stap die niet echt verkoopt
    minstens het zonoverschot op (zie `zon_opslag_stappen`).
    v5.177.0: `waardes[t]` = de kosten-to-go na kwartier t (voor de waarde
    van een netlading, A3); de grenzen per kwartier (A4, A12).
    """
    n = len(kwartieren)
    keuze = np.zeros((n, niveaus), dtype=np.int16)
    for t in range(n - 1, -1, -1):
        k = kwartieren[t]
        if waardes is not None:
            waardes[t] = waarde
        if eis is not None and t == eis[0]:
            waarde = waarde.copy()
            waarde[: eis[1]] = np.inf
        overschot = max(k.zon_kwh - k.verbruik_kwh, 0.0)
        tekort = max(k.verbruik_kwh - k.zon_kwh, 0.0)
        grenzen = _kwartier_grenzen(k, accu, eta_l)
        beste = np.full(niveaus, np.inf)
        beste_s = np.zeros(niveaus, dtype=np.int16)
        s_min = None
        if accu.zon_opslaan and overschot > EPS_KWH:
            s_min = zon_opslag_stappen(overschot, eta_l, grenzen[3], niveaus, not accu.netladen)
        min_kwh = accu.min_actie_w / 1000 * grenzen[0]
        min_laad = _min_laad_kwh(accu, grenzen[0])
        tl_accu = getattr(k, "teruglever_accu_eur", None)
        for s, b in zip(stappen, b_stap):
            if not _stap_toegestaan(accu, float(b), overschot, tekort, grenzen, eta_l):
                continue
            doel = np.arange(niveaus) + s
            geldig = (doel >= 0) & (doel < niveaus)
            if not geldig.any():
                continue
            # v5.160.0: het plan verkoopt niet wat de sturing tegenhoudt.
            if k.verkoop_vloer_kwh > 0 and b < 0 and -b > tekort + EPS_KWH:
                geldig = geldig & (doel * STAP_KWH >= k.verkoop_vloer_kwh - 1e-9)
                if not geldig.any():
                    continue
            zon_geldig, extra = _zon_regel(k, accu, int(s), float(b), s_min, min_kwh, min_laad)
            if zon_geldig is not None:
                geldig = geldig & zon_geldig
                if not geldig.any():
                    continue
            kosten = np.full(niveaus, np.inf)
            kosten[geldig] = (
                _kosten_stap(k.verbruik_kwh, k.zon_kwh, k.inkoop_eur,
                             k.teruglever_eur, np.full(geldig.sum(), b), accu, tl_accu)
                + waarde[doel[geldig]]
                + (extra[geldig] if isinstance(extra, np.ndarray) else extra)
            )
            beter = kosten < beste
            beste[beter] = kosten[beter]
            beste_s[beter] = s
        keuze[t] = beste_s
        waarde = beste
    return keuze


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


def _laadwaarde(waardes, t: int, i: int, eta_l: float) -> float | None:
    """v5.177.0 (A3): wat het plan verwacht dat een kWh die in kwartier t uit
    het net de accu in gaat later oplevert (EUR per kWh AC, na rendement en
    slijtage): de marginale waarde van de inhoud na dat kwartier."""
    v = waardes[t] if waardes is not None else None
    if v is None or len(v) < 2:
        return None
    a, b = (i - 1, i) if i > 0 else (0, 1)
    verschil = float(v[a] - v[b])
    if not np.isfinite(verschil):
        return None
    return round(verschil / STAP_KWH * eta_l, 4)


def _accu_ac_slim(rij: dict, k, accu: Accu, actie: str, i_voor: int, uren: float, eta_o: float) -> None:
    """v5.177.0 (A12): wat de slimme standen werkelijk doen, aan de netkant.

    'huis' (smart) dekt het hele tekort uit de accu (tot het vermogen en de
    inhoud), 'houden' (smart_charging) zonder overschot doet niets. De stap
    van 0,1 kWh in de inhoud gaf de planvolging een gepland vermogen dat de
    accu niet kan volgen (400 W gepland bij een huis van 200 W)."""
    if uren <= 0:
        return
    tekort = max(k.verbruik_kwh - k.zon_kwh, 0.0)
    if actie == "huis":
        ac = min(tekort, accu.ontladen_kw * uren, i_voor * STAP_KWH * eta_o)
    elif actie == "houden" and k.zon_kwh <= k.verbruik_kwh + EPS_KWH:
        ac = 0.0
    else:
        return
    # accu_kwh en net_kwh blijven de stap van het plan (rendement per band).
    rij["accu_ac_w"] = round(ac / uren * 1000)


def _rij_zon(rij: dict, k, accu: Accu, i_voor: int, uren: float, eta_l: float) -> None:
    """v5.175.0: wat de slimme stand aan de netkant laadt (W, - = laden): het
    hele overschot, tot het laadvermogen en tot vol. Ongeschaald door de stap
    van 0,1 kWh, voor tabel en planvolging."""
    ruimte_ac = max(0.0, (accu.bruikbaar_kwh - i_voor * STAP_KWH) / eta_l)
    overschot = max(k.zon_kwh - k.verbruik_kwh, 0.0)
    ac = min(overschot, accu.laden_kw * uren, ruimte_ac)
    rij["accu_ac_w"] = round(-ac / uren * 1000) if uren > 0 else 0
    # v5.175.2: het net volgt dezelfde lading, niet de afgeronde stap
    # (tabel: +212 W net bij 276 W overschot in de slimme stand).
    rij["accu_kwh"] = round(ac, 3)
    rij["net_kwh"] = round(k.verbruik_kwh - k.zon_kwh + ac, 3)


def _zon_export(k, accu: Accu, actie: str, s: int, i_voor: int, niveaus: int, eta_l: float, max_op: int) -> bool:
    """v5.177.0 (A11): slaat het plan minder op dan de slimme stand zou doen?
    Dan moet de sturing het overschot laten terugleveren (handmatig, 0 W of
    een vast laadvermogen) - de slimme standen laden het anders zelf op."""
    if actie != "zon" or not (accu.zon_opslaan and accu.zon_export_afdwingbaar):
        return False
    overschot = max(k.zon_kwh - k.verbruik_kwh, 0.0)
    if overschot <= EPS_KWH:
        return False
    s_min = zon_opslag_stappen(overschot, eta_l, max_op, niveaus, not accu.netladen)
    return s < int(s_min[i_voor])


def _vooruit(kwartieren, accu: Accu, keuze, index, b_stap, i: int, niveaus: int,
             eta_l: float, eta_o: float, waardes) -> tuple[list, float, float, int]:
    """Vooruit langs de gekozen stappen: de planrijen en de kosten."""
    rijen = []
    kosten_plan = 0.0
    kosten_zonder = 0.0
    for t, k in enumerate(kwartieren):
        s = int(keuze[t, i])
        b = float(b_stap[index[s]])
        uren, _op, _af, max_op = _kwartier_grenzen(k, accu, eta_l)
        actie, kwh = actie_van(b, k.verbruik_kwh, k.zon_kwh, accu.min_actie_w / 1000 * uren,
                               _min_laad_kwh(accu, uren))
        g = k.verbruik_kwh - k.zon_kwh + b
        kosten_plan += float(_kosten_stap(k.verbruik_kwh, k.zon_kwh, k.inkoop_eur, k.teruglever_eur,
                                          np.array([b]), accu, getattr(k, "teruglever_accu_eur", None))[0])
        g0 = k.verbruik_kwh - k.zon_kwh
        kosten_zonder += g0 * (k.inkoop_eur if g0 >= 0 else k.teruglever_eur)
        i_voor = i
        i = min(max(i + s, 0), niveaus - 1)
        if _zon_export(k, accu, actie, s, i_voor, niveaus, eta_l, max_op):
            actie, kwh = "zon_export", max(b, 0.0)
        rij = {
            "begin": k.begin,
            "actie": actie,
            "kwh": round(kwh, 3),
            "accu_kwh": round(b, 3),
            "net_kwh": round(g, 3),
            "inhoud_kwh": round(i * STAP_KWH, 2),
            "inhoud_delta_kwh": round((i - i_voor) * STAP_KWH, 2),
            # v5.162.0: de grootste laadstap = vol vermogen. De stap van
            # 0,1 kWh rondt af: bij 2,4 kW zou er 2.196 W op de accu staan.
            # v5.177.0 (A4): de grootste stap van DIT kwartier.
            "vol_vermogen": s > 0 and s == max_op,
            # v5.168.0: wat het kwartier kost (incl. belasting) en waarmee
            # het plan rekende (de marginale prijs, bij een overschot lager).
            "prijs_eur": round(k.inkoop_eur if k.prijs_incl_eur is None else k.prijs_incl_eur, 4),
            "rekenprijs_eur": round(k.inkoop_eur, 4),
            # v5.165.0: de duur waarover verbruik en zon gelden.
            "uren": round(uren, 4),
            # v5.177.0 (A1): de verkoopvloer waarmee het plan rekende; de
            # sturing houdt een verkoop alleen daaronder tegen.
            "verkoop_vloer_kwh": round(k.verkoop_vloer_kwh, 2),
        }
        if actie == "laden_net":
            rij["waarde_eur_per_kwh"] = _laadwaarde(waardes, t, i, eta_l)
        if accu.zon_opslaan and actie == "zon":
            _rij_zon(rij, k, accu, i_voor, uren, eta_l)
        else:
            _accu_ac_slim(rij, k, accu, actie, i_voor, uren, eta_o)
        rijen.append(rij)
    return rijen, kosten_plan, kosten_zonder, i


def plan(kwartieren: list[Kwartier], accu: Accu) -> Uitkomst:
    """Het goedkoopste accuplan over de gegeven kwartieren."""
    n = len(kwartieren)
    if n == 0:
        return Uitkomst(False, "geen prijzen vooruit")
    if accu.bruikbaar_kwh <= STAP_KWH:
        return Uitkomst(False, "geen bruikbare accu-inhoud")
    eta_l, eta_o = rendementen(accu)
    niveaus = int(accu.bruikbaar_kwh / STAP_KWH) + 1
    e = np.arange(niveaus) * STAP_KWH
    max_op = int(accu.laden_kw * accu.duur_h * eta_l / STAP_KWH + 1e-9)
    # v5.165.0: ontladen per vermogensband; laden en stilstaan zoals voorheen.
    af_s, af_b = _ontlaadstappen(accu, eta_o)
    op_s = np.arange(0, max_op + 1)
    stappen = np.concatenate([af_s, op_s])
    # AC-stroom per stap (kWh)
    b_stap = np.concatenate([af_b, op_s * STAP_KWH / eta_l])
    index = {int(st): j for j, st in enumerate(stappen)}

    eind = eindwaarde(kwartieren, accu, eta_o)
    waarde = -e * eind                 # kosten-to-go aan het eind (negatief = waard)
    # vooruit, vanaf de huidige inhoud. v5.177.0 (A12): naar beneden
    # afgerond - 0,06 kWh telde als 0,1 en het plan ontlaadde aan het eind
    # van de nacht een accu die al leeg stond (06:30: 267 W gepland, 0 gemeten).
    i = int(min(max(accu.inhoud_kwh, 0.0), accu.bruikbaar_kwh) / STAP_KWH + 1e-6)
    i = min(i, niveaus - 1)
    i_start = i
    eis = None
    if accu.vol_na_kwartier is not None and accu.netladen and 0 <= accu.vol_na_kwartier < n:
        # Nooit meer eisen dan de tijd toelaat: een onhaalbare eis laat geen
        # enkel plan over.
        t = accu.vol_na_kwartier
        eis = (t, min(niveaus - 1, i_start + (t + 1) * max_op))
    waardes: list = [None] * n
    keuze = _terugrekenen(kwartieren, accu, stappen, b_stap, waarde, niveaus, eis, eta_l, max_op, waardes)
    rijen, kosten_plan, kosten_zonder, i = _vooruit(
        kwartieren, accu, keuze, index, b_stap, i, niveaus, eta_l, eta_o, waardes
    )
    # verschil in inhoud tegen de eindwaarde verrekenen (begin en eind)
    kosten_plan -= (i - i_start) * STAP_KWH * eind
    return Uitkomst(
        True,
        "",
        rijen,
        round(kosten_plan, 3),
        round(kosten_zonder, 3),
        round(eind, 4),
    )
