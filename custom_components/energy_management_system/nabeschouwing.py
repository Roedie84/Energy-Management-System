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


#: v5.131.0: teruglevering levert onder het salderen de prijs plus de vaste
#: premie op (FEEDIN_PREMIUM_EUR_PER_KWH), zoals in de rest van het EMS.
PREMIE_EUR = 0.02


def _net(net: float, k: "Kwartier") -> float:
    return net * k.prijs_eur if net >= 0 else net * (k.prijs_eur + PREMIE_EUR)


def kosten_zonder_accu(kwartieren: list[Kwartier]) -> float:
    return sum(_net(k.huis_kwh - k.pv_kwh, k) for k in kwartieren)


def kosten_werkelijk(kwartieren: list[Kwartier]) -> float:
    """Wat er werkelijk aan het net is afgerekend."""
    return sum(_net(k.huis_kwh - k.pv_kwh - k.accu_kwh, k) for k in kwartieren)


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
    verkoop_onder_reserve_verboden: bool = False,
    reserve_kwh: float | None = None,
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
    # v5.131.0: het ontlaadvermogen is een AC-grens; uit de cellen gaat er
    # 1/√rendement zoveel (net als het laden: AC erin x √rendement opgeslagen)
    ontlaad_stap_max = int(round(ontlaad_kw * 0.25 / eta / stap_kwh))
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
        # v4.5: zonder netladen mag er alleen uit OVERSCHOT geladen
        # worden - zon boven het huisverbruik. Zo werkt de integratie
        # (arbitrage is er vroeg uit gehaald), dus zo hoort de meetlat.
        netto_huis = k.huis_kwh - k.pv_kwh
        laad_grens = laad_stap_max
        if not sta_netladen_toe:
            overschot_kwh = max(0.0, k.pv_kwh - k.huis_kwh)
            laad_grens = min(
                laad_stap_max, int(round(overschot_kwh * eta / stap_kwh))
            )
        # v4.12: de reserve als VERKOOPPOORT. Het huis mag altijd uit de
        # accu worden gedekt, ook onder de reserve; alleen leveren aan
        # het NET is verboden zolang de voorraad eronder zit - dat is wat
        # `may_sell_now` doet. Als BODEM gemodelleerd (tot v4.11)
        # verbood hij ook het dekken van het huis, en dat is een veel
        # zwaardere beperking: het gemiste bedrag kwam daardoor twintig
        # keer te hoog uit.
        reserve_stap = (
            int(round((reserve_kwh - bodem_kwh) / stap_kwh))
            if verkoop_onder_reserve_verboden and reserve_kwh is not None
            else 0
        )
        huis_stap = max(0, int(round(max(0.0, netto_huis) / eta / stap_kwh)))
        for s, c in enumerate(kosten):
            if c == INF:
                continue
            for d in range(-ontlaad_stap_max, laad_grens + 1):
                s2 = s + d
                if s2 < 0 or s2 >= n_stappen:
                    continue
                # meer ontladen dan het huis vraagt = leveren aan het net
                if d < -huis_stap and s2 < reserve_stap:
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
                kost = c + _net(netto_huis - accu_net, k) + extra
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
    netladen: bool = True,
) -> dict:
    """Werkelijk tegenover best mogelijk, met de plekken waar het
    verschil zat.

    v5.140.0 (L-EMS-042, akkoord Ruud 27-10): de meetlat mag uit het net
    laden zolang de integratie dat zelf doet (`netladen`). De meetlat van
    v4.5 laadde alleen uit overschot; sinds de integratie in goedkope blokken
    uit het net laadt, lag de werkelijkheid op 3 van 7 dagen BOVEN "best
    mogelijk" (26-10: € 1,92 tegen € 0,70) en kwamen de dagdeelcijfers uit
    een optimum dat niet kon bijladen. Het oude getal blijft staan onder
    `zonder_netladen`.

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
    # v4.5: de meetlat was hoe de integratie toen werkte - laden uit
    # overschot. v5.140.0: met netladen zolang de integratie uit het net laadt.
    zonder_net = beste_planning(
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
    if not zonder_net.get("te_becijferen"):
        return {"te_becijferen": False, "reden": zonder_net.get("reden")}
    beste = met_arbitrage if (netladen and met_arbitrage.get("te_becijferen")) else zonder_net

    # v4.2: de prijs van de reserve, apart.
    # v4.12: de reserve als POORT, niet als bodem. Zie de toelichting in
    # `beste_planning`. Het oude model gaf twintig keer te hoge bedragen
    # en maakte het probleem soms onoplosbaar.
    gemist_door_reserve = 0.0
    if reserve_kwh is not None and reserve_kwh > bodem_kwh:
        met_reserve = beste_planning(
            kwartieren,
            capaciteit_kwh=capaciteit_kwh,
            begin_kwh=begin_kwh,
            bodem_kwh=bodem_kwh,
            laad_kw=laad_kw,
            ontlaad_kw=ontlaad_kw,
            rendement=rendement,
            slijtage_eur_per_kwh=slijtage_eur_per_kwh,
            sta_netladen_toe=beste is met_arbitrage,
            verkoop_onder_reserve_verboden=True,
            reserve_kwh=reserve_kwh,
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
    per_dagdeel = _per_dagdeel(kwartieren, beste["acties"], tijdstippen)
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
        "reserve_als": "verkooppoort",
        "netarbitrage_eur": round(
            max(0.0, zonder_net["kosten_eur"] - met_arbitrage["kosten_eur"]), 2
        )
        if met_arbitrage.get("te_becijferen")
        else 0.0,
        "meetlat": "met netladen" if beste is met_arbitrage else "zonder netladen",
        # v5.140.0: de oude meetlat (alleen laden uit overschot), ter vergelijking.
        "zonder_netladen": {
            "kosten_best_mogelijk_eur": round(zonder_net["kosten_eur"], 2),
            "had_kunnen_opleveren_eur": round(zonder - zonder_net["kosten_eur"], 2),
            "gemist_eur": round(werkelijk - zonder_net["kosten_eur"], 2),
            "per_dagdeel": _per_dagdeel(kwartieren, zonder_net["acties"], tijdstippen),
        },
        "grootste_verschillen": verschillen[:8],
        "per_dagdeel": per_dagdeel,
        "toelichting": (
            (
                "Best mogelijk mag uit het net laden, net als de integratie zelf "
                "in goedkope blokken. Wat laden uit het net daarin oplevert staat "
                "apart in `netarbitrage_eur`; het optimum zonder netladen in "
                "`zonder_netladen`. "
                if beste is met_arbitrage
                else "Best mogelijk laadt alleen uit OVERSCHOT; wat netarbitrage "
                "zou opleveren staat apart in `netarbitrage_eur`. "
            )
            + "Best mogelijk rekent met PERFECTE kennis vooraf van zon, "
            "verbruik en prijs; dat is een ondergrens die geen sturing "
            "haalt. Het gemiste bedrag is de som van niet vooruit kunnen "
            "kijken en van de regels die de integratie volgde. De "
            "grootste verschillen zeggen waar."
        ),
    }


# v5.89 (L-EMS-019): het gemiste bedrag per dagdeel. Bewust GEEN
# kwartierregels met huisverbruik in de export (privacykeuze v5.28: daaruit
# valt aanwezigheid af te leiden) - alleen sommen per dagdeel.
DAGDELEN = (
    ("nacht", 0, 7),
    ("ochtendpiek", 7, 10),
    ("middag", 10, 17),
    ("avondpiek", 17, 24),
)


def _dagdeel(tijd: str) -> str | None:
    try:
        uur = int(str(tijd)[:2])
    except (TypeError, ValueError):
        return None
    for naam, van, tot in DAGDELEN:
        if van <= uur < tot:
            return naam
    return None


def _per_dagdeel(kwartieren: list[Kwartier], acties: list[dict], tijdstippen: list[str]) -> dict:
    """Per dagdeel: wat de beste planning anders deed en wat dat waard was.

    `verschil_eur` positief: de beste planning ontlaadde in dat dagdeel meer
    (of laadde minder) dan wij - daar hielden we te veel vast of laadden we
    te veel. Negatief: wij ontlaadden meer dan de beste planning.
    `vastgehouden_kwh` en `te_veel_ontladen_kwh` zijn dezelfde maten als in
    de dagtotalen, maar per dagdeel.
    """
    uit = {
        naam: {
            "kwartieren": 0, "verschil_eur": 0.0, "verschil_abs_eur": 0.0,
            "accu_werkelijk_kwh": 0.0, "accu_beste_kwh": 0.0,
            "vastgehouden_kwh": 0.0, "te_veel_ontladen_kwh": 0.0,
        }
        for naam, _v, _t in DAGDELEN
    }
    for k, a, t in zip(kwartieren, acties, tijdstippen):
        naam = _dagdeel(t)
        if naam is None:
            continue
        d = uit[naam]
        best_net = a["ontladen_kwh"] - a["laden_kwh"]
        v = (best_net - k.accu_kwh) * k.prijs_eur
        d["kwartieren"] += 1
        d["verschil_eur"] += v
        d["verschil_abs_eur"] += abs(v)
        d["accu_werkelijk_kwh"] += k.accu_kwh
        d["accu_beste_kwh"] += best_net
        if a["ontladen_kwh"] > a["laden_kwh"]:
            d["vastgehouden_kwh"] += max(0.0, best_net - max(0.0, k.accu_kwh))
        if k.accu_kwh > 0:
            d["te_veel_ontladen_kwh"] += max(0.0, k.accu_kwh - max(0.0, best_net))
    return {
        naam: {
            sleutel: (round(w, 3) if isinstance(w, float) else w)
            for sleutel, w in d.items()
        }
        for naam, d in uit.items()
    }
