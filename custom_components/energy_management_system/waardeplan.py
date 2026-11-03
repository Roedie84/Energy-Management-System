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
Wat er aan het eind van de horizon in de accu zit, is de mediaan van de
inkoopprijs waard (maal rendement, min slijtage): niet alles op de laatste
dag weggeven, en ook niet eindeloos vasthouden.
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


@dataclass
class Uitkomst:
    beschikbaar: bool
    reden: str = ""
    kwartieren: list = field(default_factory=list)
    kosten_plan_eur: float | None = None
    kosten_zonder_accu_eur: float | None = None
    eindwaarde_eur_per_kwh: float | None = None


def _kosten_stap(verbruik, zon, inkoop, teruglever, b, accu: Accu):
    """Kosten van een stap voor een rij accustromen b (numpy)."""
    g = verbruik - zon + b
    kosten = np.where(g >= 0, g * inkoop, g * teruglever)
    uit = np.maximum(-b, 0.0)
    kosten = kosten + uit * accu.slijtage_eur
    if accu.verkoopmarge_eur:
        naar_net = np.minimum(np.maximum(-g, 0.0), uit)
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


def actie_van(b: float, verbruik: float, zon: float) -> tuple[str, float]:
    """Wat de accu in een kwartier doet, en hoeveel (kWh, AC)."""
    overschot = max(zon - verbruik, 0.0)
    tekort = max(verbruik - zon, 0.0)
    if b > overschot + EPS_KWH:
        return "laden_net", b - overschot
    if b < 0 and -b > tekort + EPS_KWH:
        return "verkopen", -b - tekort
    if b < -EPS_KWH:
        return "huis", -b
    if tekort > EPS_KWH:
        return "houden", 0.0
    return "zon", max(b, 0.0)


def _terugrekenen(kwartieren, accu: Accu, stappen, b_stap, waarde, niveaus, eis=None):
    """Achterwaarts: per kwartier en inhoud de goedkoopste stap.

    `eis` = (kwartier, niveau): na dat kwartier minstens dat niveau.
    """
    n = len(kwartieren)
    keuze = np.zeros((n, niveaus), dtype=np.int16)
    for t in range(n - 1, -1, -1):
        k = kwartieren[t]
        if eis is not None and t == eis[0]:
            waarde = waarde.copy()
            waarde[: eis[1]] = np.inf
        overschot = max(k.zon_kwh - k.verbruik_kwh, 0.0)
        tekort = max(k.verbruik_kwh - k.zon_kwh, 0.0)
        beste = np.full(niveaus, np.inf)
        beste_s = np.zeros(niveaus, dtype=np.int16)
        for s, b in zip(stappen, b_stap):
            if b > 0 and not accu.netladen and b > overschot + 1e-9:
                continue
            if b < 0 and not accu.verkopen and -b > tekort + 1e-9:
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
            kosten = np.full(niveaus, np.inf)
            kosten[geldig] = (
                _kosten_stap(k.verbruik_kwh, k.zon_kwh, k.inkoop_eur,
                             k.teruglever_eur, np.full(geldig.sum(), b), accu)
                + waarde[doel[geldig]]
            )
            beter = kosten < beste
            beste[beter] = kosten[beter]
            beste_s[beter] = s
        keuze[t] = beste_s
        waarde = beste
    return keuze


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

    inkoop = [k.inkoop_eur for k in kwartieren]
    # v5.165.0: wat er aan het eind in zit, gaat meestal naar het huis; dus
    # het rendement van de band van het gewone huisverbruik. Met het ene
    # (hogere) getal hield het plan de lading vast die het huis met 69 %
    # zou dekken.
    huis_w = median(k.verbruik_kwh / (getattr(k, "uren", 0.25) or 0.25) for k in kwartieren) * 1000
    eind = max(0.0, median(inkoop) * ontlaadrendement(huis_w, accu, eta_o) - accu.slijtage_eur)
    waarde = -e * eind                 # kosten-to-go aan het eind (negatief = waard)
    # vooruit, vanaf de huidige inhoud
    i = int(round(min(max(accu.inhoud_kwh, 0.0), accu.bruikbaar_kwh) / STAP_KWH))
    i = min(i, niveaus - 1)
    i_start = i
    eis = None
    if accu.vol_na_kwartier is not None and accu.netladen and 0 <= accu.vol_na_kwartier < n:
        # Nooit meer eisen dan de tijd toelaat: een onhaalbare eis laat geen
        # enkel plan over.
        t = accu.vol_na_kwartier
        eis = (t, min(niveaus - 1, i_start + (t + 1) * max_op))
    keuze = _terugrekenen(kwartieren, accu, stappen, b_stap, waarde, niveaus, eis)

    rijen = []
    kosten_plan = 0.0
    kosten_zonder = 0.0
    for t, k in enumerate(kwartieren):
        s = int(keuze[t, i])
        b = float(b_stap[index[s]])
        actie, kwh = actie_van(b, k.verbruik_kwh, k.zon_kwh)
        g = k.verbruik_kwh - k.zon_kwh + b
        kosten_plan += float(_kosten_stap(k.verbruik_kwh, k.zon_kwh, k.inkoop_eur,
                                          k.teruglever_eur, np.array([b]), accu)[0])
        g0 = k.verbruik_kwh - k.zon_kwh
        kosten_zonder += g0 * (k.inkoop_eur if g0 >= 0 else k.teruglever_eur)
        i_voor = i
        i = min(max(i + s, 0), niveaus - 1)
        rijen.append({
            "begin": k.begin,
            "actie": actie,
            "kwh": round(kwh, 3),
            "accu_kwh": round(b, 3),
            "net_kwh": round(g, 3),
            "inhoud_kwh": round(i * STAP_KWH, 2),
            "inhoud_delta_kwh": round((i - i_voor) * STAP_KWH, 2),
            # v5.162.0: de grootste laadstap = vol vermogen. De stap van
            # 0,1 kWh rondt af: bij 2,4 kW zou er 2.196 W op de accu staan.
            "vol_vermogen": s == max_op,
            # v5.168.0: wat het kwartier kost (incl. belasting) en waarmee
            # het plan rekende (de marginale prijs, bij een overschot lager).
            "prijs_eur": round(k.inkoop_eur if k.prijs_incl_eur is None else k.prijs_incl_eur, 4),
            "rekenprijs_eur": round(k.inkoop_eur, 4),
            # v5.165.0: de duur waarover verbruik en zon gelden.
            "uren": round(getattr(k, "uren", 0.25) or 0.25, 4),
        })
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
