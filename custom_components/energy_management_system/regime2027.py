"""Generale repetitie voor 2027: de regels van na de saldering in de schaduw (v5.100).

Na 31 december 2026 stopt de saldering (instelbaar). Wat je dan teruglevert,
levert alleen nog het kale teruglevertarief op, terwijl inkopen de volle,
belaste prijs blijft kosten. De regels daarvoor zitten al in het EMS
(`_verkoop_loont_na_saldering`, `should_capture_surplus_over_selling`,
`cap_discharge_to_own_consumption`), maar slapen tot 1 januari. Dan moeten
ze op dag één goed werken.

Daarom draaien ze nu al mee. Elke ronde vraagt het EMS die regels, met het
regime van 2027 aangezet ALLEEN voor die vraag, wat ze nu zouden besluiten.
Dat komt per kwartier in het dagverloop:

    r27_opvangen   zou het zonoverschot nu in de accu gaan?
    r27_verkoop    zou verkopen uit de accu nu nog mogen?
    r27_export     wat een teruggeleverde kWh in 2027 zou opleveren (€)

Bij de dagwissel rekent dit bestand de dag vier keer door, met de gemeten
energie en het tarief van 2027:

    zonder accu        het huis zonder thuisaccu
    huidige sturing    wat de accu werkelijk deed, afgerekend als in 2027
    regels 2027        de dag nagespeeld met de regels van 2027
    best mogelijk      de beste planning met kennis achteraf (laden alleen
                       uit overschot, zoals de integratie werkt)

Het verschil tussen "regels 2027" en "best mogelijk" is wat de regels van
2027 nog laten liggen; het verschil met "huidige sturing" is wat de
overgang zelf oplevert.

Zuivere functies, zonder Home Assistant.
"""
from __future__ import annotations

from dataclasses import dataclass

#: De marge die `cap_discharge_to_own_consumption` boven het huisverbruik toelaat.
OVERSCHOT_MARGE_KWH = 150.0 / 4000
STAP_KWH = 0.05


@dataclass
class Kwartier:
    huis_kwh: float
    pv_kwh: float
    import_eur: float          # de volle prijs van een ingekochte kWh
    export_eur: float          # wat een teruggeleverde kWh in 2027 oplevert
    accu_kwh: float            # wat het EMS werkelijk deed: + ontladen, - laden (AC)
    opvangen: bool | None = None   # r27_opvangen
    verkoop: bool | None = None    # r27_verkoop
    dekt: bool = False             # de stand dekte het huis (smart/smart_discharging)
    begrens: bool | None = None    # r27_begrens: teruglevering naar ~0 (v5.121.0)
    ruimte: bool | None = None     # r27_ruimte: zon niet opslaan, ruimte voor straks (v5.121.0)
    regelt: bool = False           # de Zendure regelde op de P1-meter (v5.121.0)


def _netkosten(net_kwh: float, k: Kwartier) -> float:
    """Inkoop tegen de volle prijs, teruglevering tegen het kale tarief."""
    return net_kwh * k.import_eur if net_kwh >= 0 else net_kwh * k.export_eur


def _begrensd(net_kwh: float, k: Kwartier) -> float:
    """v5.121.0: met de terugleverbegrenzing van 2027 (punt 6) gaat er bij
    een negatieve terugleverwaarde niets het net op - de panelen worden tot
    het huis plus de accu teruggeregeld."""
    if net_kwh < 0 and k.begrens and k.export_eur is not None and k.export_eur < 0:
        return 0.0
    return net_kwh


def zonder_accu(kwartieren: list[Kwartier]) -> float:
    return sum(_netkosten(k.huis_kwh - k.pv_kwh, k) for k in kwartieren)


def _restwaarde(e_kwh: float, kwartieren: list[Kwartier], eta: float) -> float:
    """Energie die aan het eind in de accu zit, bespaart later inkoop."""
    gem = sum(k.import_eur for k in kwartieren) / len(kwartieren)
    return max(0.0, e_kwh) * eta * gem


def huidige_sturing(kwartieren: list[Kwartier], begin_kwh: float, eind_kwh: float,
                    eta: float, slijtage: float) -> float:
    kosten = sum(_netkosten(k.huis_kwh - k.pv_kwh - k.accu_kwh, k) + max(0.0, k.accu_kwh) * slijtage
                 for k in kwartieren)
    return kosten - _restwaarde(eind_kwh, kwartieren, eta)


def regels_2027(kwartieren: list[Kwartier], *, begin_kwh: float, capaciteit_kwh: float,
                laad_kw: float, ontlaad_kw: float, eta: float, slijtage: float) -> dict:
    """De dag nagespeeld zoals het EMS hem in 2027 zou sturen.

    Uitgangspunt is wat het EMS die dag werkelijk deed; daarop de drie
    regels van na de saldering:

    - zonoverschot gaat de accu in als `r27_opvangen` dat zegt, of als het
      EMS het toch al deed;
    - ontladen wordt begrensd tot het huisverbruik plus een kleine marge
      (`cap_discharge_to_own_consumption`);
    - verkopen boven het huis stopt helemaal als `r27_verkoop` nee zegt.

    Laden uit het net blijft zoals het EMS het deed (die regel verandert
    niet met de saldering).
    """
    e = begin_kwh
    laad_max, ontlaad_max = laad_kw * 0.25, ontlaad_kw * 0.25
    kosten = 0.0
    verschil_kwartieren = 0
    for k in kwartieren:
        tekort = max(0.0, k.huis_kwh - k.pv_kwh)
        overschot = max(0.0, k.pv_kwh - k.huis_kwh)
        accu = 0.0
        if k.accu_kwh < 0:   # het EMS laadde: uit zon en/of net
            uit_zon = min(overschot, -k.accu_kwh)
            uit_net = -k.accu_kwh - uit_zon
            laden = uit_net if k.ruimte else uit_zon + uit_net
            if k.opvangen and not k.ruimte:
                laden = max(laden, overschot)
            laden = min(laden, laad_max, (capaciteit_kwh - e) / eta)
            accu = -max(0.0, laden)
        elif overschot > 0 and k.opvangen and not k.ruimte:
            accu = -min(overschot, laad_max, (capaciteit_kwh - e) / eta)
        elif k.accu_kwh > 0 or (k.dekt and tekort > 0):
            # een dekkende stand dekt het huis zolang er energie is - ook met
            # de extra zon die de regels van 2027 hebben opgevangen
            wens = max(k.accu_kwh, tekort if k.dekt else 0.0)
            grens = tekort + OVERSCHOT_MARGE_KWH
            if k.verkoop is False:
                grens = tekort
            accu = max(0.0, min(wens, grens, ontlaad_max, e * eta))
        if abs(accu - k.accu_kwh) > 0.01:
            verschil_kwartieren += 1
        e = e - accu / eta if accu > 0 else e - accu * eta
        kosten += _netkosten(_begrensd(k.huis_kwh - k.pv_kwh - accu, k), k) + max(0.0, accu) * slijtage
    return {
        "kosten_eur": kosten - _restwaarde(e, kwartieren, eta),
        "eind_kwh": e,
        "anders_dan_nu_kwartieren": verschil_kwartieren,
    }


def best_mogelijk(kwartieren: list[Kwartier], *, begin_kwh: float, capaciteit_kwh: float,
                  laad_kw: float, ontlaad_kw: float, eta: float, slijtage: float,
                  stap_kwh: float = STAP_KWH) -> float | None:
    """Laagste kosten met kennis achteraf, tarief 2027, laden alleen uit overschot."""
    n = int(round(capaciteit_kwh / stap_kwh)) + 1
    if n < 3 or not kwartieren:
        return None
    laad_max = int(round(laad_kw * 0.25 * eta / stap_kwh))
    ontlaad_max = int(round(ontlaad_kw * 0.25 / stap_kwh))
    gem = sum(k.import_eur for k in kwartieren) / len(kwartieren)
    v = [-(s * stap_kwh) * eta * gem for s in range(n)]
    for k in reversed(kwartieren):
        grens = min(laad_max, int(round(max(0.0, k.pv_kwh - k.huis_kwh) * eta / stap_kwh)))
        nieuw = []
        for s in range(n):
            beste = float("inf")
            for d in range(-ontlaad_max, grens + 1):
                s2 = s + d
                if not 0 <= s2 < n:
                    continue
                if d > 0:
                    accu = -(d * stap_kwh) / eta
                    extra = 0.0
                elif d < 0:
                    accu = (-d * stap_kwh) * eta
                    extra = (-d * stap_kwh) * slijtage
                else:
                    accu = extra = 0.0
                net = k.huis_kwh - k.pv_kwh - accu
                if net < 0 and k.export_eur < 0:
                    net = 0.0   # v5.121.0: teruglevering kan altijd worden begrensd
                w = _netkosten(net, k) + extra + v[s2]
                if w < beste:
                    beste = w
            nieuw.append(beste)
        v = nieuw
    return v[min(n - 1, max(0, int(round(begin_kwh / stap_kwh))))]


def repetitie(kwartieren: list[Kwartier], *, begin_kwh: float, eind_kwh: float, capaciteit_kwh: float,
              laad_kw: float, ontlaad_kw: float, rendement: float, slijtage_eur_per_kwh: float = 0.0,
              verschuiving_kw: float = 0.0) -> dict:
    """De dag onder het tarief van 2027, vier keer doorgerekend."""
    met_export = [k.export_eur for k in kwartieren if k.export_eur is not None]
    if len(met_export) < 80 or len(met_export) < len(kwartieren) - 16:
        return {"te_becijferen": False,
                "reden": f"{len(met_export)} van {len(kwartieren)} kwartieren met het teruglevertarief "
                         "van 2027, minimaal 80 en hooguit 16 zonder"}
    # alle kwartieren houden (de laadstand loopt door); een enkel kwartier
    # zonder teruglevertarief krijgt het daggemiddelde
    gem_export = sum(met_export) / len(met_export)
    bruikbaar = [k if k.export_eur is not None else Kwartier(**{**k.__dict__, "export_eur": gem_export})
                 for k in kwartieren if k.import_eur is not None]
    eta = rendement ** 0.5
    # de energie die er bij het begin al in zat, is niet gratis: aftrekken
    # wat hij aan het eind waard is zonder hem aan het begin te rekenen,
    # maakte elke dag met een volle accu "winstgevend"
    begin_waarde = _restwaarde(begin_kwh, bruikbaar, eta)
    arg = dict(begin_kwh=begin_kwh, capaciteit_kwh=capaciteit_kwh, laad_kw=laad_kw,
               ontlaad_kw=ontlaad_kw, eta=eta, slijtage=slijtage_eur_per_kwh)
    zonder = zonder_accu(bruikbaar)
    nu = huidige_sturing(bruikbaar, begin_kwh, eind_kwh, eta, slijtage_eur_per_kwh) + begin_waarde
    regels = regels_2027(bruikbaar, **arg)
    regels["kosten_eur"] += begin_waarde
    best = best_mogelijk(bruikbaar, **arg)
    if best is not None:
        best += begin_waarde
    teruggeleverd_uit_accu = sum(
        min(max(0.0, k.accu_kwh), max(0.0, k.accu_kwh - max(0.0, k.huis_kwh - k.pv_kwh))) for k in bruikbaar
    )
    uit = {
        "te_becijferen": True,
        "kwartieren": len(bruikbaar),
        "zonder_accu_eur": round(zonder, 2),
        "huidige_sturing_eur": round(nu, 2),
        "regels_2027_eur": round(regels["kosten_eur"], 2),
        "best_mogelijk_eur": round(best, 2) if best is not None else None,
        "accu_levert_op_nu_eur": round(zonder - nu, 2),
        "accu_levert_op_2027_eur": round(zonder - regels["kosten_eur"], 2),
        "overgang_levert_op_eur": round(nu - regels["kosten_eur"], 2),
        # Best mogelijk laadt alleen uit overschot (zoals de integratie werkt);
        # laadde het EMS die dag uit het net, dan kan de nagespeelde dag er
        # iets onder uitkomen. Nooit negatief tonen.
        "regels_laten_liggen_eur": round(max(0.0, regels["kosten_eur"] - best), 2) if best is not None else None,
        "anders_dan_nu_kwartieren": regels["anders_dan_nu_kwartieren"],
        "uit_accu_teruggeleverd_kwh": round(teruggeleverd_uit_accu, 2),
        "gemiddelde_export_ct": round(sum(k.export_eur for k in bruikbaar) / len(bruikbaar) * 100, 1),
        "gemiddelde_import_ct": round(sum(k.import_eur for k in bruikbaar) / len(bruikbaar) * 100, 1),
        # v5.121.0: negatieve teruglevering (punt 6) en het P1-doel (punt 3), in de schaduw
        "begrenzen_kwartieren": sum(1 for k in bruikbaar if k.begrens),
        "ruimte_kwartieren": sum(1 for k in bruikbaar if k.ruimte),
        "p1_doel": p1_doel_kosten(bruikbaar, verschuiving_kw, rendement),
    }
    return uit


#: v5.121.0: het P1-doel vanaf 1-1-2027 (W op de echte meter, 0 = nul op de meter).
P1_DOEL_2027_W = 0.0


def p1_doel_kosten(kwartieren: list[Kwartier], verschuiving_kw: float, rendement: float) -> dict:
    """Wat de structurele extra teruglevering op de P1-meter kost (v5.121.0, punt 3).

    De Zendure regelt op een template "P1 + verschuiving" en houdt die op nul;
    de echte meter staat dan op -verschuiving. In elk kwartier waarin hij
    regelt, gaat er `verschuiving x 0,25 h` extra het net op die anders in de
    accu was gebleven (of er niet uit was gekomen). Die kWh had later inkoop
    vermeden: de gemiddelde inkoopprijs van de dag x het ontlaadrendement.

    Onder het salderen levert die kWh de inkoopprijs plus premie op - dus
    vrijwel niets kwijt. Vanaf 2027 alleen kaal + premie + bonus. Het verschil
    per dag, en x 365 per jaar.
    """
    bruikbaar = [k for k in kwartieren if k.import_eur is not None]
    if not bruikbaar or verschuiving_kw <= 0:
        return {"te_becijferen": bool(bruikbaar), "verschuiving_w": round(max(0.0, verschuiving_kw) * 1000),
                "kosten_2027_eur_per_dag": 0.0, "kosten_2026_eur_per_dag": 0.0, "regelkwartieren": 0}
    eta = max(0.0, min(1.0, rendement)) ** 0.5
    gem = sum(k.import_eur for k in bruikbaar) / len(bruikbaar)
    vasthouden = gem * eta
    kwh = verschuiving_kw * 0.25
    k27 = k26 = 0.0
    regel = 0
    for k in bruikbaar:
        if not k.regelt:
            continue
        regel += 1
        export27 = k.export_eur if k.export_eur is not None else 0.0
        k27 += kwh * (vasthouden - export27)
        k26 += kwh * (vasthouden - k.import_eur)   # salderen: de kWh brengt de inkoopprijs op
    return {
        "te_becijferen": True,
        "verschuiving_w": round(verschuiving_kw * 1000),
        "regelkwartieren": regel,
        "extra_teruglevering_kwh": round(kwh * regel, 3),
        "kosten_2027_eur_per_dag": round(k27, 3),
        "kosten_2026_eur_per_dag": round(k26, 3),
        "kosten_2027_eur_per_jaar": round(k27 * 365, 2),
        "doel_2027_w": P1_DOEL_2027_W,
    }


def samenvatting(dagen: list[dict], laatste: int = 30) -> dict:
    """Over de laatste beoordeelde dagen: hoe goed zijn de regels van 2027?"""
    goed = [d for d in dagen if d.get("te_becijferen")][-laatste:]
    if not goed:
        return {"dagen": 0, "oordeel": "nog geen dag doorgerekend"}
    p1 = [d["p1_doel"] for d in goed if isinstance(d.get("p1_doel"), dict) and d["p1_doel"].get("te_becijferen")]

    def som(veld):
        waarden = [d.get(veld) for d in goed if d.get(veld) is not None]
        return round(sum(waarden), 2) if waarden else None

    liggen = som("regels_laten_liggen_eur")
    opbrengst = som("accu_levert_op_2027_eur")
    aandeel = (liggen / (opbrengst + liggen) * 100) if liggen is not None and opbrengst and opbrengst + liggen > 0 else None
    if len(goed) < 7:
        oordeel = f"pas {len(goed)} dag(en) doorgerekend; na zeven dagen zegt het iets"
    elif aandeel is not None and aandeel <= 15:
        oordeel = "klaar voor 2027: de regels halen het grootste deel van wat er te halen is"
    else:
        oordeel = "de regels van 2027 laten nog geld liggen; zie de dagen met het grootste verschil"
    slechtste = sorted((d for d in goed if d.get("regels_laten_liggen_eur") is not None),
                       key=lambda d: -d["regels_laten_liggen_eur"])[:3]
    return {
        "dagen": len(goed),
        "accu_levert_op_nu_eur": som("accu_levert_op_nu_eur"),
        "accu_levert_op_2027_eur": opbrengst,
        "overgang_levert_op_eur": som("overgang_levert_op_eur"),
        "regels_laten_liggen_eur": liggen,
        "gemist_aandeel_procent": round(aandeel, 1) if aandeel is not None else None,
        "per_dag_2027_eur": round(opbrengst / len(goed), 2) if opbrengst is not None else None,
        "slechtste_dagen": [{"datum": d.get("datum"), "laten_liggen_eur": d["regels_laten_liggen_eur"]} for d in slechtste],
        "oordeel": oordeel,
        # v5.121.0 (punt 3): wat de extra teruglevering op de P1-meter in 2027 kost
        "p1_doel_kosten_2027_eur_per_dag": (round(sum(p["kosten_2027_eur_per_dag"] for p in p1) / len(p1), 3)
                                            if p1 else None),
        "p1_doel_kosten_2027_eur_per_jaar": (round(sum(p["kosten_2027_eur_per_dag"] for p in p1) / len(p1) * 365, 2)
                                             if p1 else None),
        "begrenzen_kwartieren": sum(d.get("begrenzen_kwartieren") or 0 for d in goed),
        "ruimte_kwartieren": sum(d.get("ruimte_kwartieren") or 0 for d in goed),
    }


def kaart(samenvatting_: dict) -> dict:
    """De teksten voor de dashboardkaart."""
    per_dag = samenvatting_.get("per_dag_2027_eur")
    primair = (f"€ {per_dag:.2f} per dag in 2027".replace(".", ",") if per_dag is not None
               else "Generale repetitie 2027")
    delen = [samenvatting_.get("oordeel") or "wacht op de eerste dag"]
    if samenvatting_.get("regels_laten_liggen_eur") is not None:
        delen.append(f"laten liggen € {samenvatting_['regels_laten_liggen_eur']:.2f} in "
                     f"{samenvatting_.get('dagen')} dagen".replace(".", ","))
    return {"kaart_primair": primair, "kaart_secundair": " · ".join(delen)}
