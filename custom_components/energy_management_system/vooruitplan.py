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


# --- v5.122.0: plan gewogen over drie scenario's (punt 2, proefstand) --------
#
# Gevraagd 23-10: "Laat de DP de verwachte kosten minimaliseren over p10,
# mediaan en p90 (0,15/0,7/0,15), met een verbruiksschaal per scenario. Per
# kwartier kiest hij een van de eigen modi. Eindwaarde = laagste toekomstige
# inkoopprijs min verliezen. Nooit verkopen onder de reserve blijft hard.
# Alleen als proefstandkandidaat."
#
# Stochastisch DP over de laadstand: per kwartier één modus (de modus weet de
# stand, niet welk scenario uitkomt), de kosten verwacht over de drie
# scenario's. Zelfde natuurkunde als hierboven (verlies bij het laden).

MODI = ("smart", "sparen", "uitstellen", "laden", "verkopen")
#: Welke stand van het kwartierplan bij welke modus hoort.
PLAN_MODUS = {
    "smart": "smart",
    "smart_charging (sparen)": "sparen",
    "smart_discharging": "uitstellen",
    "manual (laden)": "laden",
    "manual (verkopen)": "verkopen",
}
SCENARIO_GEWICHTEN = (0.15, 0.70, 0.15)
#: Verbruik per scenario: een sombere dag (p10) is ook een dag met meer verbruik.
SCENARIO_VERBRUIK = (1.10, 1.00, 0.95)
#: Zonfactor zonder band uit de voorspelling.
SCENARIO_ZON_TERUGVAL = (0.6, 1.0, 1.3)


def stap_modus(modus: str, s: float, kw: dict, k: int, *, cap: float, laad_kwh: float, ontlaad_kwh: float,
               rendement: float) -> tuple[float, float, float]:
    """Eén kwartier in één scenario: (nieuwe stand, net kWh, uit de accu kWh).

    `kw["zon"][k]` en `kw["verbruik"][k]` per scenario; `kw["reserve_kwh"]`
    is de harde grens voor VERKOPEN (het huis dekken mag eronder).
    """
    zon = kw["zon"][k]
    verbruik = kw["verbruik"][k]
    over = max(0.0, zon - verbruik)
    tekort = max(0.0, verbruik - zon)
    ruimte_ac = max(0.0, (cap - s) / rendement)
    erin_ac = uit = export = 0.0
    if modus in ("smart", "sparen"):
        erin_ac = min(over, laad_kwh, ruimte_ac)
    elif modus == "laden":
        erin_ac = min(laad_kwh, ruimte_ac)
    if modus in ("smart", "uitstellen", "verkopen"):
        uit = min(tekort, ontlaad_kwh, s)
    if modus == "verkopen":
        vrij = max(0.0, s - uit - (kw.get("reserve_kwh") or 0.0))
        export = min(max(0.0, ontlaad_kwh - uit), vrij)
    s2 = min(cap, max(0.0, s + erin_ac * rendement - uit - export))
    net = verbruik - zon + erin_ac - uit - export
    return s2, net, uit + export


def _kost(net: float, kw: dict, uit: float, slijtage_eur: float) -> float:
    prijs = kw["import_eur"] if net > 0 else kw["export_eur"]
    return net * prijs + uit * slijtage_eur


def _interp(v: list[float], s: float, stap: float) -> float:
    x = s / stap
    i = int(x)
    if i >= len(v) - 1:
        return v[-1]
    f = x - i
    return v[i] * (1 - f) + v[i + 1] * f


def scenario_kwartieren(kwartieren: list[dict]) -> list[dict]:
    """Per kwartier de zon en het verbruik in de drie scenario's.

    `zon_p10_kwh`/`zon_p90_kwh` uit de band als ze er zijn, anders de
    terugvalfactoren."""
    uit = []
    for kw in kwartieren:
        mid = kw["zon_kwh"]
        p10 = kw.get("zon_p10_kwh")
        p90 = kw.get("zon_p90_kwh")
        zon = (
            p10 if p10 is not None else mid * SCENARIO_ZON_TERUGVAL[0],
            mid,
            p90 if p90 is not None else mid * SCENARIO_ZON_TERUGVAL[2],
        )
        verbruik = tuple(kw["verbruik_kwh"] * f for f in SCENARIO_VERBRUIK)
        uit.append({**kw, "zon": zon, "verbruik": verbruik})
    return uit


def eindwaarde_laagste_inkoop(kwartieren: list[dict], slijtage_eur: float) -> float:
    """Wat een kWh die aan het eind nog in de accu zit waard is: hij vermijdt
    later hooguit de LAAGSTE inkoopprijs die nog komt, min de slijtage van het
    ontladen (het laadverlies is al betaald)."""
    prijzen = [kw["import_eur"] for kw in kwartieren if kw.get("import_eur") is not None]
    return max(0.0, (min(prijzen) if prijzen else 0.0) - slijtage_eur)


def optimaliseer_scenarios(
    kwartieren: list[dict],
    start_kwh: float,
    bruikbaar_kwh: float,
    *,
    laad_kwh: float,
    ontlaad_kwh: float,
    rendement: float,
    slijtage_eur: float,
    gewichten: tuple = SCENARIO_GEWICHTEN,
    stap_kwh: float = STAP_KWH,
    klaar: bool = False,
    eindwaarde_eur: float | None = None,
) -> dict:
    """Het modusplan met de laagste VERWACHTE kosten over drie scenario's.

    `klaar`: de kwartieren dragen al `zon` en `verbruik` per scenario (één
    per gewicht) - zo rekent de herspeeltool met kennis achteraf."""
    if not kwartieren or bruikbaar_kwh <= 0 or rendement <= 0:
        return {"beschikbaar": False}
    kws = kwartieren if klaar else scenario_kwartieren(kwartieren)
    eind = eindwaarde_laagste_inkoop(kws, slijtage_eur) if eindwaarde_eur is None else eindwaarde_eur
    n = max(1, int(round(bruikbaar_kwh / stap_kwh)))
    stap = bruikbaar_kwh / n
    arg = dict(cap=bruikbaar_kwh, laad_kwh=laad_kwh, ontlaad_kwh=ontlaad_kwh, rendement=rendement)
    v = [-(i * stap) * eind for i in range(n + 1)]
    beleid: list[list[str]] = []
    for kw in reversed(kws):
        nieuw = [0.0] * (n + 1)
        keuze = ["smart"] * (n + 1)
        for i in range(n + 1):
            s = i * stap
            beste, beste_m = float("inf"), "smart"
            for m in MODI:
                verwacht = 0.0
                for k, w in enumerate(gewichten):
                    s2, net, uit = stap_modus(m, s, kw, k, **arg)
                    verwacht += w * (_kost(net, kw, uit, slijtage_eur) + _interp(v, s2, stap))
                if verwacht < beste - 1e-12:
                    beste, beste_m = verwacht, m
            nieuw[i], keuze[i] = beste, beste_m
        v = nieuw
        beleid.append(keuze)
    beleid.reverse()
    # het plan langs de mediaan: de modus per kwartier vanaf de echte startstand
    modi = []
    s = min(bruikbaar_kwh, max(0.0, start_kwh))
    for kw, keuze in zip(kws, beleid):
        m = keuze[min(n, max(0, int(round(s / stap))))]
        modi.append(m)
        s, _net, _uit = stap_modus(m, s, kw, min(1, len(gewichten) - 1), **arg)
    return {
        "beschikbaar": True,
        "modi": modi,
        "verwacht_eur": round(_interp(v, min(bruikbaar_kwh, max(0.0, start_kwh)), stap), 4),
        "eindwaarde_eur": round(eind, 4),
    }


def waardeer_modi(
    kwartieren: list[dict],
    modi: list[str],
    start_kwh: float,
    bruikbaar_kwh: float,
    *,
    laad_kwh: float,
    ontlaad_kwh: float,
    rendement: float,
    slijtage_eur: float,
    gewichten: tuple = SCENARIO_GEWICHTEN,
    klaar: bool = False,
    eindwaarde_eur: float | None = None,
) -> dict:
    """Een vaste modusreeks per scenario doorrekenen: verwachte en
    per-scenario kosten (positief = kosten), met de eindwaarde verrekend."""
    kws = kwartieren if klaar else scenario_kwartieren(kwartieren)
    eind = eindwaarde_laagste_inkoop(kws, slijtage_eur) if eindwaarde_eur is None else eindwaarde_eur
    arg = dict(cap=bruikbaar_kwh, laad_kwh=laad_kwh, ontlaad_kwh=ontlaad_kwh, rendement=rendement)
    per = []
    for k in range(len(gewichten)):
        s = min(bruikbaar_kwh, max(0.0, start_kwh))
        kosten = 0.0
        for kw, m in zip(kws, modi):
            s, net, uit = stap_modus(m, s, kw, k, **arg)
            kosten += _kost(net, kw, uit, slijtage_eur)
        per.append(kosten - s * eind)
    return {
        "verwacht_eur": round(sum(w * p for w, p in zip(gewichten, per)), 4),
        "per_scenario_eur": [round(p, 4) for p in per],
    }


def vergelijk_scenarios(
    kwartieren: list[dict],
    start_kwh: float,
    plan_standen: list[str],
    bruikbaar_kwh: float,
    *,
    laad_kwh: float,
    ontlaad_kwh: float,
    rendement: float,
    slijtage_eur: float,
) -> dict:
    """Het scenarioplan tegen de modi van het echte kwartierplan (de
    beslisboom), beide als vaste modusreeks over dezelfde drie scenario's."""
    plan_modi = [PLAN_MODUS.get(str(m), "smart") for m in plan_standen]
    arg = dict(laad_kwh=laad_kwh, ontlaad_kwh=ontlaad_kwh, rendement=rendement, slijtage_eur=slijtage_eur)
    opt = optimaliseer_scenarios(kwartieren, start_kwh, bruikbaar_kwh, **arg)
    if not opt.get("beschikbaar"):
        return {"beschikbaar": False}
    plan = waardeer_modi(kwartieren, plan_modi, start_kwh, bruikbaar_kwh, **arg)
    scen = waardeer_modi(kwartieren, opt["modi"], start_kwh, bruikbaar_kwh, **arg)
    anders = sum(1 for a, b in zip(plan_modi, opt["modi"]) if a != b)
    telling = {m: opt["modi"].count(m) for m in MODI if opt["modi"].count(m)}
    return {
        "beschikbaar": True,
        "plan_verwacht_eur": plan["verwacht_eur"],
        "scenario_verwacht_eur": scen["verwacht_eur"],
        # positief = het scenarioplan is goedkoper
        "verschil_eur": round(plan["verwacht_eur"] - scen["verwacht_eur"], 4),
        "plan_per_scenario_eur": plan["per_scenario_eur"],
        "scenario_per_scenario_eur": scen["per_scenario_eur"],
        "kwartieren_anders": anders,
        "modi_scenarioplan": telling,
        "eindwaarde_eur": opt["eindwaarde_eur"],
    }
