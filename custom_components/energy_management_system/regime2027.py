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


def _netkosten(net_kwh: float, k: Kwartier) -> float:
    """Inkoop tegen de volle prijs, teruglevering tegen het kale tarief."""
    return net_kwh * k.import_eur if net_kwh >= 0 else net_kwh * k.export_eur


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
            laden = uit_zon + uit_net
            if k.opvangen:
                laden = max(laden, overschot)
            laden = min(laden, laad_max, (capaciteit_kwh - e) / eta)
            accu = -max(0.0, laden)
        elif overschot > 0 and k.opvangen:
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
        kosten += _netkosten(k.huis_kwh - k.pv_kwh - accu, k) + max(0.0, accu) * slijtage
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
                w = _netkosten(k.huis_kwh - k.pv_kwh - accu, k) + extra + v[s2]
                if w < beste:
                    beste = w
            nieuw.append(beste)
        v = nieuw
    return v[min(n - 1, max(0, int(round(begin_kwh / stap_kwh))))]


def repetitie(kwartieren: list[Kwartier], *, begin_kwh: float, eind_kwh: float, capaciteit_kwh: float,
              laad_kw: float, ontlaad_kw: float, rendement: float, slijtage_eur_per_kwh: float = 0.0) -> dict:
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
    }
    return uit


def samenvatting(dagen: list[dict], laatste: int = 30) -> dict:
    """Over de laatste beoordeelde dagen: hoe goed zijn de regels van 2027?"""
    goed = [d for d in dagen if d.get("te_becijferen")][-laatste:]
    if not goed:
        return {"dagen": 0, "oordeel": "nog geen dag doorgerekend"}

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
