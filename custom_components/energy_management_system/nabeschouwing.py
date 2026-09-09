"""Achteraf: wat had de accu die dag het best kunnen doen? (v3.99.19)

Gevraagd: "Het gaat er mij om of het verstandiger was geweest om
bijvoorbeeld de accu in een andere modus te hebben gezet, en of dit
financieel dan meer had opgeleverd."

Dit is geen voorspelling. Het rekent met wat er WERKELIJK gebeurde: de
zon per kwartier, het huisverbruik per kwartier, de prijs per kwartier.
Met die kennis is de goedkoopste accuplanning exact te berekenen - een
dynamisch programma over de laadstand, per kwartier, met de fysieke
grenzen van de accu. De uitkomst is een ONDERGRENS voor de kosten: wat
er met perfecte kennis vooraf haalbaar was. Het verschil met wat de
integratie deed, is de prijs van niet vooruit kunnen kijken plus de
prijs van de regels die ze volgde. Dat verschil zegt waar de winst zit.

Zuiver Python, geen afhankelijkheden. Bij 96 kwartieren en een
laadstand in stappen van 0,1 kWh is dit ruim onder een seconde.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Kwartier:
    huis_kwh: float
    pv_kwh: float
    prijs_eur: float          # inkoop en - onder salderen - teruglevering
    accu_kwh: float           # wat het NET van de accu zag: + ontladen, - laden
                              # (de sensor meet aan de AC-kant, rendement inbegrepen)


def kosten_zonder_accu(kwartieren: list[Kwartier]) -> float:
    return sum((k.huis_kwh - k.pv_kwh) * k.prijs_eur for k in kwartieren)


def kosten_werkelijk(kwartieren: list[Kwartier]) -> float:
    """Wat er werkelijk aan het net is afgerekend."""
    return sum((k.huis_kwh - k.pv_kwh - k.accu_kwh) * k.prijs_eur for k in kwartieren)


def beste_planning(
    kwartieren: list[Kwartier],
    *,
    capaciteit_kwh: float,
    begin_kwh: float,
    bodem_kwh: float,
    laad_kw: float,
    ontlaad_kw: float,
    rendement: float,
    slijtage_eur_per_kwh: float = 0.0,
    stap_kwh: float = 0.1,
    sta_netladen_toe: bool = True,
) -> dict:
    """De goedkoopste accuplanning met kennis achteraf.

    Toestand: laadstand in stappen van `stap_kwh`. Per kwartier drie
    keuzes: laden, ontladen of niets, elk begrensd door het vermogen.
    Rendement zit aan de laadkant (de wortel van het rondgangsrendement)
    en aan de ontlaadkant, zodat de som klopt. Slijtage telt per
    ontladen kWh.

    De eindstand is vrij: energie die aan het eind in de accu zit, wordt
    tegen de gemiddelde dagprijs gewaardeerd, anders leert het programma
    dat leeg eindigen altijd het goedkoopst is.
    """
    n_stappen = int(round((capaciteit_kwh - bodem_kwh) / stap_kwh)) + 1
    if n_stappen < 2 or not kwartieren:
        return {"te_becijferen": False, "reden": "te weinig ruimte of geen kwartieren"}
    eta = rendement ** 0.5
    laad_stap_max = int(round(laad_kw * 0.25 * eta / stap_kwh))
    ontlaad_stap_max = int(round(ontlaad_kw * 0.25 / stap_kwh))
    gemiddelde_prijs = sum(k.prijs_eur for k in kwartieren) / len(kwartieren)

    INF = float("inf")
    # kosten[s] = minimale kosten tot nu toe om in toestand s te eindigen
    begin_s = min(n_stappen - 1, max(0, int(round((begin_kwh - bodem_kwh) / stap_kwh))))
    kosten = [INF] * n_stappen
    kosten[begin_s] = 0.0
    keuzes: list[list[int | None]] = []

    for k in kwartieren:
        nieuw = [INF] * n_stappen
        herkomst: list[int | None] = [None] * n_stappen
        netto_huis = k.huis_kwh - k.pv_kwh
        # v4.5: zonder netladen mag er alleen uit OVERSCHOT geladen
        # worden - zon boven het huisverbruik. Zo werkt de integratie
        # (arbitrage is er vroeg uit gehaald), dus zo hoort de meetlat.
        laad_grens = laad_stap_max
        if not sta_netladen_toe:
            overschot_kwh = max(0.0, k.pv_kwh - k.huis_kwh)
            laad_grens = min(
                laad_stap_max, int(round(overschot_kwh * eta / stap_kwh))
            )
        for s, c in enumerate(kosten):
            if c == INF:
                continue
            for d in range(-ontlaad_stap_max, laad_grens + 1):
                s2 = s + d
                if s2 < 0 or s2 >= n_stappen:
                    continue
                if d > 0:      # laden: d stappen erin kost d/eta uit het net
                    accu_net = -(d * stap_kwh) / eta
                    extra = 0.0
                elif d < 0:    # ontladen: -d stappen eruit levert -d*eta
                    accu_net = (-d * stap_kwh) * eta
                    extra = (-d * stap_kwh) * slijtage_eur_per_kwh
                else:
                    accu_net = 0.0
                    extra = 0.0
                kost = c + (netto_huis - accu_net) * k.prijs_eur + extra
                if kost < nieuw[s2]:
                    nieuw[s2] = kost
                    herkomst[s2] = s
        kosten = nieuw
        keuzes.append(herkomst)

    # eindstand vrij, maar de restenergie is iets waard
    beste_s = min(
        range(n_stappen),
        key=lambda s: kosten[s] - s * stap_kwh * gemiddelde_prijs * eta,
    )
    totaal = kosten[beste_s]
    restwaarde = beste_s * stap_kwh * gemiddelde_prijs * eta

    # pad terug
    pad = [beste_s]
    s = beste_s
    for herkomst in reversed(keuzes):
        s = herkomst[s]
        pad.append(s)
    pad.reverse()
    acties = []
    for i, k in enumerate(kwartieren):
        d = pad[i + 1] - pad[i]
        acties.append(
            {
                "laden_kwh": round(d * stap_kwh, 2) if d > 0 else 0.0,
                "ontladen_kwh": round(-d * stap_kwh, 2) if d < 0 else 0.0,
                "laadstand_kwh": round(bodem_kwh + pad[i + 1] * stap_kwh, 2),
            }
        )
    return {
        "te_becijferen": True,
        "kosten_eur": round(totaal - restwaarde, 4),
        "restwaarde_eur": round(restwaarde, 4),
        "eindstand_kwh": round(bodem_kwh + beste_s * stap_kwh, 2),
        "acties": acties,
    }


def nabeschouwing(
    kwartieren: list[Kwartier],
    *,
    capaciteit_kwh: float,
    begin_kwh: float,
    eind_kwh: float,
    bodem_kwh: float,
    laad_kw: float,
    ontlaad_kw: float,
    rendement: float,
    slijtage_eur_per_kwh: float,
    tijdstippen: list[str],
    reserve_kwh: float | None = None,
) -> dict:
    """Werkelijk tegenover best mogelijk, met de plekken waar het
    verschil zat.

    v4.2: `reserve_kwh` is de reserve die de integratie die dag aanhield
    (de mediaan over de dag). Met die reserve als harde ondergrens wordt
    de beste planning nog een keer gerekend; het verschil met de vrije
    beste planning is wat de RESERVE heeft gekost. De rest van het
    gemiste bedrag is voorspelling en regels - dat deel is grotendeels
    onvermijdelijk, want de beste planning kent de zon van morgen.
    """
    zonder = kosten_zonder_accu(kwartieren)
    gemiddelde_prijs = sum(k.prijs_eur for k in kwartieren) / len(kwartieren)
    eta = rendement ** 0.5
    werkelijk = kosten_werkelijk(kwartieren) - (eind_kwh - bodem_kwh) * gemiddelde_prijs * eta \
        + sum(max(0.0, k.accu_kwh) for k in kwartieren) * slijtage_eur_per_kwh
    # v4.5: de meetlat is hoe de integratie werkt - laden uit overschot,
    # geen netarbitrage. Wat arbitrage zou opleveren staat er apart bij.
    beste = beste_planning(
        kwartieren,
        capaciteit_kwh=capaciteit_kwh,
        begin_kwh=begin_kwh,
        bodem_kwh=bodem_kwh,
        laad_kw=laad_kw,
        ontlaad_kw=ontlaad_kw,
        rendement=rendement,
        slijtage_eur_per_kwh=slijtage_eur_per_kwh,
        sta_netladen_toe=False,
    )
    met_arbitrage = beste_planning(
        kwartieren,
        capaciteit_kwh=capaciteit_kwh,
        begin_kwh=begin_kwh,
        bodem_kwh=bodem_kwh,
        laad_kw=laad_kw,
        ontlaad_kw=ontlaad_kw,
        rendement=rendement,
        slijtage_eur_per_kwh=slijtage_eur_per_kwh,
        sta_netladen_toe=True,
    )
    if not beste.get("te_becijferen"):
        return {"te_becijferen": False, "reden": beste.get("reden")}

    # v4.2: de prijs van de reserve, apart.
    gemist_door_reserve = 0.0
    if reserve_kwh is not None and reserve_kwh > bodem_kwh:
        met_reserve = beste_planning(
            kwartieren,
            capaciteit_kwh=capaciteit_kwh,
            begin_kwh=max(begin_kwh, reserve_kwh),
            bodem_kwh=min(reserve_kwh, capaciteit_kwh - 0.2),
            laad_kw=laad_kw,
            ontlaad_kw=ontlaad_kw,
            rendement=rendement,
            slijtage_eur_per_kwh=slijtage_eur_per_kwh,
        )
        if met_reserve.get("te_becijferen"):
            gemist_door_reserve = max(0.0, met_reserve["kosten_eur"] - beste["kosten_eur"])

    # waar zat het grootste verschil?
    verschillen = []
    for i, (k, a) in enumerate(zip(kwartieren, beste["acties"])):
        best_net = a["ontladen_kwh"] - a["laden_kwh"]
        werk_net = k.accu_kwh
        v = (best_net - werk_net) * k.prijs_eur
        if abs(v) > 0.005:
            verschillen.append(
                {
                    "tijd": tijdstippen[i],
                    "prijs_ct": round(k.prijs_eur * 100, 1),
                    "werkelijk_kwh": round(werk_net, 2),
                    "beste_kwh": round(best_net, 2),
                    "verschil_eur": round(v, 3),
                }
            )
    verschillen.sort(key=lambda r: -abs(r["verschil_eur"]))
    # v4.1: de gerichte som, voor het zelflerende deel. Positief: de
    # beste planning ontlaadde meer dan wij (wij hielden te veel vast).
    # Negatief: wij ontlaadden meer dan de beste planning (te veel
    # verkocht, of te vroeg).
    # Alleen de ONTLAADkant: vastgehouden = de beste planning ontlaadde
    # en wij minder; te veel ontladen = wij ontlaadden en de beste
    # planning minder. Laden dat de beste planning wel deed en wij niet,
    # is een vraag voor de brug, niet voor de reserve.
    te_veel_vastgehouden = sum(
        max(0.0, (a["ontladen_kwh"] - a["laden_kwh"]) - max(0.0, k.accu_kwh))
        for k, a in zip(kwartieren, beste["acties"])
        if a["ontladen_kwh"] > a["laden_kwh"]
    )
    te_veel_ontladen = sum(
        max(0.0, k.accu_kwh - max(0.0, a["ontladen_kwh"] - a["laden_kwh"]))
        for k, a in zip(kwartieren, beste["acties"])
        if k.accu_kwh > 0
    )
    return {
        "te_veel_vastgehouden_kwh": round(te_veel_vastgehouden, 2),
        "te_veel_ontladen_kwh": round(te_veel_ontladen, 2),
        "te_becijferen": True,
        "kosten_zonder_accu_eur": round(zonder, 2),
        "kosten_werkelijk_eur": round(werkelijk, 2),
        "kosten_best_mogelijk_eur": round(beste["kosten_eur"], 2),
        "accu_leverde_op_eur": round(zonder - werkelijk, 2),
        "had_kunnen_opleveren_eur": round(zonder - beste["kosten_eur"], 2),
        "gemist_eur": round(werkelijk - beste["kosten_eur"], 2),
        "gemist_door_reserve_eur": round(min(gemist_door_reserve, max(0.0, werkelijk - beste["kosten_eur"])), 2),
        "gemist_door_voorspelling_eur": round(
            max(0.0, werkelijk - beste["kosten_eur"]) - min(gemist_door_reserve, max(0.0, werkelijk - beste["kosten_eur"])), 2
        ),
        "reserve_kwh": reserve_kwh,
        "netarbitrage_eur": round(
            max(0.0, beste["kosten_eur"] - met_arbitrage["kosten_eur"]), 2
        ),
        "grootste_verschillen": verschillen[:8],
        "toelichting": (
            "Best mogelijk laadt alleen uit OVERSCHOT - geen netarbitrage, "
            "want die is uit de integratie gehaald. Wat netarbitrage zou "
            "opleveren staat apart in `netarbitrage_eur`. Best mogelijk "
            "rekent met PERFECTE kennis vooraf van zon, "
            "verbruik en prijs; dat is een ondergrens die geen sturing "
            "haalt. Het gemiste bedrag is de som van niet vooruit kunnen "
            "kijken en van de regels die de integratie volgde. De "
            "grootste verschillen zeggen waar."
        ),
    }
