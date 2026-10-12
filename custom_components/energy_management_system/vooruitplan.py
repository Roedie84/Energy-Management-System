"""Vooruitplannen over de horizon, MET de nachtreserve (v5.90).

Gevraagd (12-10): "Vooruitplannen over 24 uur eerst laten rekenen met de
nachtreserve, zodat we zien wat het echt oplevert" en "Opbrengst na de
saldering als eerste klaarmaken".

De oude MPC-vergelijking legde twee verschillende getallen naast elkaar:
de winst van een greedy koppeling (alleen de arbitragewinst, zonder tijd-
volgorde en zonder reserve) tegen de NETTO uitkomst van het plan (inclusief
alle stroom die het huis van het net haalt). Dat verschil zei niets - vandaar
"+2,50 euro per dag" terwijl de nabeschouwing 0,56 als bovengrens gaf.

Hier rekenen beide kanten met DEZELFDE kwartieren, DEZELFDE natuurkunde en
DEZELFDE waardering:

- `waardeer` geeft een gegeven laadstandverloop (het plan) een netto bedrag;
- `optimaliseer` zoekt met dynamisch programmeren het beste verloop, met de
  nachtreserve als harde grens voor verkopen uit de accu.

Het verschil is wat vooruitplannen met dezelfde voorspelling had kunnen
opleveren. Met een andere waardering van teruglevering (na de saldering)
geeft dezelfde rekensom wat het kost als de sturing NIET meebeweegt.

Zuivere functies, zonder Home Assistant.

Natuurkunde per kwartier, met `d` de verandering van de laadstand:

- laden (d > 0): er gaat d / rendement in, het verlies valt bij het laden;
- ontladen (d < 0): er komt -d uit, naar het huis of het net;
- net = verbruik - zon + (d / rendement als d > 0, anders d);
- verkopen uit de accu (meer ontladen dan het huis tekortkomt) mag alleen
  zolang de stand daarna niet onder de reserve komt;
- slijtage telt op wat er UIT de accu komt;
- wat er aan het eind in de accu zit, telt mee tegen `eindwaarde_eur`.
"""
from __future__ import annotations

STAP_KWH = 0.1
_EPS = 1e-9


def _kosten(kw: dict, d: float, rendement: float, slijtage_eur: float) -> float:
    """Wat dit kwartier kost bij een standverandering d (negatief = opbrengst)."""
    tekort = kw["verbruik_kwh"] - kw["zon_kwh"]
    net = tekort + (d / rendement if d > 0 else d)
    prijs = kw["import_eur"] if net > 0 else kw["export_eur"]
    return net * prijs + max(0.0, -d) * slijtage_eur


def waardeer(
    kwartieren: list[dict],
    start_kwh: float,
    standen_kwh: list[float],
    *,
    rendement: float,
    slijtage_eur: float,
    eindwaarde_eur: float,
) -> dict:
    """Het netto bedrag van een gegeven laadstandverloop.

    `standen_kwh[i]` is de stand NA kwartier i - precies wat de
    kwartierplanning als `soc_kwh` bewaart.
    """
    kosten = 0.0
    vorige = start_kwh
    doorzet = 0.0
    for kw, stand in zip(kwartieren, standen_kwh):
        d = stand - vorige
        kosten += _kosten(kw, d, rendement, slijtage_eur)
        doorzet += abs(d)
        vorige = stand
    return {
        "netto_eur": round(-kosten + vorige * eindwaarde_eur, 4),
        "eind_kwh": round(vorige, 3),
        "doorzet_kwh": round(doorzet, 3),
    }


def optimaliseer(
    kwartieren: list[dict],
    start_kwh: float,
    bruikbaar_kwh: float,
    *,
    laad_kwh: float,
    ontlaad_kwh: float,
    rendement: float,
    slijtage_eur: float,
    eindwaarde_eur: float,
    stap_kwh: float = STAP_KWH,
) -> dict:
    """Het beste laadstandverloop over de kwartieren.

    `laad_kwh` en `ontlaad_kwh` zijn de grenzen per kwartier (aan de
    netkant). Elk kwartier mag een `reserve_kwh` dragen: daaronder komt de
    stand niet door verkopen uit de accu. Het huis bedienen mag wel - daar is
    de reserve voor.
    """
    if not kwartieren or bruikbaar_kwh <= 0 or rendement <= 0:
        return {"beschikbaar": False}
    n = max(1, int(round(bruikbaar_kwh / stap_kwh)))
    stap = bruikbaar_kwh / n
    start_i = min(n, max(0, int(round(start_kwh / stap))))
    omhoog = int((laad_kwh * rendement + _EPS) // stap)
    omlaag = int((ontlaad_kwh + _EPS) // stap)

    ONEINDIG = float("inf")
    # waarde[i] = beste opbrengst vanaf dit kwartier tot het eind bij stand i
    waarde = [i * stap * eindwaarde_eur for i in range(n + 1)]
    keuzes: list[list[int]] = []
    for kw in reversed(kwartieren):
        tekort = max(0.0, kw["verbruik_kwh"] - kw["zon_kwh"])
        reserve = kw.get("reserve_kwh") or 0.0
        nieuw = [-ONEINDIG] * (n + 1)
        keuze = [0] * (n + 1)
        for i in range(n + 1):
            beste, beste_j = -ONEINDIG, i
            for j in range(max(0, i - omlaag), min(n, i + omhoog) + 1):
                d = (j - i) * stap
                if d < -_EPS and -d > tekort + _EPS and j * stap < reserve - _EPS:
                    continue
                v = waarde[j] - _kosten(kw, d, rendement, slijtage_eur)
                if v > beste:
                    beste, beste_j = v, j
            nieuw[i], keuze[i] = beste, beste_j
        waarde = nieuw
        keuzes.append(keuze)
    keuzes.reverse()

    standen = []
    i = start_i
    for keuze in keuzes:
        i = keuze[i]
        standen.append(round(i * stap, 3))
    # opnieuw waarderen vanaf de ECHTE startstand, niet de afgeronde
    uit = waardeer(
        kwartieren,
        start_kwh,
        standen,
        rendement=rendement,
        slijtage_eur=slijtage_eur,
        eindwaarde_eur=eindwaarde_eur,
    )
    uit.update(beschikbaar=True, standen_kwh=standen)
    return uit


def vergelijk(
    kwartieren: list[dict],
    start_kwh: float,
    plan_standen_kwh: list[float],
    bruikbaar_kwh: float,
    *,
    laad_kwh: float,
    ontlaad_kwh: float,
    rendement: float,
    slijtage_eur: float,
    eindwaarde_eur: float,
) -> dict:
    """Plan en optimum naast elkaar, met wat er anders is."""
    instellingen = dict(rendement=rendement, slijtage_eur=slijtage_eur, eindwaarde_eur=eindwaarde_eur)
    plan = waardeer(kwartieren, start_kwh, plan_standen_kwh, **instellingen)
    beste = optimaliseer(
        kwartieren, start_kwh, bruikbaar_kwh, laad_kwh=laad_kwh, ontlaad_kwh=ontlaad_kwh, **instellingen
    )
    if not beste.get("beschikbaar"):
        return {"beschikbaar": False}
    # wat er anders gaat: per kwartier het verschil in standverandering
    verschoven = 0.0
    kwartieren_anders = 0
    vorige_p = vorige_b = start_kwh
    for p, b in zip(plan_standen_kwh, beste["standen_kwh"]):
        dp, db = p - vorige_p, b - vorige_b
        if abs(dp - db) > 0.05:
            kwartieren_anders += 1
            verschoven += abs(dp - db)
        vorige_p, vorige_b = p, b
    verschoven /= 2  # elke verschoven kWh telt aan twee kanten
    winst = beste["netto_eur"] - plan["netto_eur"]
    return {
        "beschikbaar": True,
        "plan_eur": plan["netto_eur"],
        "optimum_eur": beste["netto_eur"],
        "verschil_eur": round(winst, 3),
        "verschoven_kwh": round(verschoven, 3),
        "kwartieren_anders": kwartieren_anders,
        "voordeel_ct_per_kwh": round(100 * winst / verschoven, 2) if verschoven > 0.05 else None,
        "plan_eind_kwh": plan["eind_kwh"],
        "optimum_eind_kwh": beste["eind_kwh"],
    }
