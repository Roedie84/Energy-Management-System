"""Echte dagen opnieuw afspelen: een regressietest in euro's (v5.123.0, punt 5).

Gevraagd 23-10: "Bouw een tool/test die 30-40 echte dagen uit het dagverloop
en de meetlog door de beslisboom en het plan haalt. Score ze in € per dag
onder salderen en onder 2027, met keuzeoordeel. Het doel is wijzigingen vóór
en na te vergelijken."

Wat hier WEL kan, zonder Home Assistant:

    werkelijk        wat de dag werkelijk kostte (gemeten huis, zon, accu),
                     afgerekend onder salderen en onder 2027
    beslisboom       de standen die de beslisboom die dag koos, opnieuw door
                     het accumodel (`vooruitplan.stap_modus`) met de gemeten
                     zon en het gemeten verbruik - de keuzes, los van wat de
                     omvormer er in werkelijkheid van maakte
    scenarioplan     het DP van punt 2 over dezelfde dag, met kennis achteraf
                     (één scenario: wat er gebeurde) - de bovengrens van een
                     plan in de eigen modi
    best_mogelijk    het keuzeoordeel (laden alleen uit overschot); onder
                     2027 de generale repetitie
    gemist           wat het keuzeoordeel per dag "gemist" noemt

Elke strategie begint met dezelfde laadstand en de eindstand telt tegen
dezelfde restwaarde (gemiddelde inkoop van de dag x √rendement), zodat de
bedragen naast elkaar te leggen zijn.

Wat NIET kan zonder grote verbouwing: de beslisboom zelf opnieuw laten
beslissen (`_async_update_locked` leest live toestanden, het kwartierplan,
reserve, verkooptoets en prijsreeks uit Home Assistant). Daarom speelt
"beslisboom" de VASTGELEGDE keuzes opnieuw af; een wijziging aan de regels
zelf toont zich pas in de dagen die met de nieuwe versie zijn vastgelegd. Een
wijziging aan het model, de waardering of het plan (vooruitplan, regime2027,
keuzeoordeel, overschotwaarde) is wel meteen voor en na te vergelijken: draai
`tools_herspeel.py` met beide versies op dezelfde export.

Zuivere functies, zonder Home Assistant.
"""
from __future__ import annotations

from . import keuzeoordeel as K
from . import regime2027 as R
from . import vooruitplan as V

PREMIE_EUR = 0.02
#: Een dag telt mee met zoveel kwartieren met een prijs.
MIN_KWARTIEREN = 80


def modus_van(stand: str | None, accu_kwh: float, tekort_kwh: float) -> str:
    """De vastgelegde stand als een van de eigen modi."""
    s = str(stand or "")
    if s.startswith("manual"):
        if accu_kwh < -0.02:
            return "laden"
        return "verkopen" if accu_kwh > tekort_kwh + 0.02 else "smart"
    if s.startswith("smart_discharging"):
        return "uitstellen"
    if s.startswith("smart_charging"):
        return "sparen"
    return "smart"


def dag_kwartieren(rijen: list[dict], gemeten: dict | None = None) -> list[dict]:
    """De kwartieren van één dag uit het dagverloop, met de meetlaag als die
    er is (`gemeten["HH:MM"]` met huis_kwh, pv_kwh, accu_kwh)."""
    uit = []
    for r in sorted(rijen or [], key=lambda x: str(x.get("tijd"))):
        if not isinstance(r, dict) or r.get("prijs_ct") is None:
            continue
        m = (gemeten or {}).get(r.get("tijd"))
        if m is None:
            if r.get("huis_w") is None:
                continue
            m = {"huis_kwh": r["huis_w"] / 4000, "pv_kwh": (r.get("pv_w") or 0.0) / 4000,
                 "accu_kwh": (r.get("accu_w") or 0.0) / 4000}
            bron = "vermogen"
        else:
            bron = "meetlaag"
        uit.append({
            "tijd": r.get("tijd"),
            "huis_kwh": float(m["huis_kwh"]), "pv_kwh": float(m["pv_kwh"]), "accu_kwh": float(m["accu_kwh"]),
            "prijs_eur": float(r["prijs_ct"]) / 100,
            "export_2027_eur": r.get("r27_export"),
            "stand": r.get("stand"), "reden": r.get("reden"), "soc": r.get("soc"),
            "reserve_kwh": r.get("reserve_kwh"), "bron": bron,
            "r27_opvangen": r.get("r27_opvangen"), "r27_verkoop": r.get("r27_verkoop"),
            "r27_begrens": r.get("r27_begrens"), "r27_ruimte": r.get("r27_ruimte"),
        })
    return uit


def _export(kw: dict, regime: str, gem_export: float | None) -> float:
    if regime == "salderen":
        return kw["prijs_eur"] + PREMIE_EUR
    e = kw.get("export_2027_eur")
    return e if e is not None else (gem_export if gem_export is not None else 0.0)


def _netkosten(net: float, kw: dict, regime: str, gem_export) -> float:
    return net * kw["prijs_eur"] if net >= 0 else net * _export(kw, regime, gem_export)


def score_dag(kwartieren: list[dict], *, begin_kwh: float, eind_kwh: float, capaciteit_kwh: float,
              laad_kw: float, ontlaad_kw: float, rendement: float, slijtage_eur: float) -> dict:
    """Eén dag, vier strategieën, twee waarderingen. Kosten in € (positief = kosten)."""
    if len(kwartieren) < MIN_KWARTIEREN or capaciteit_kwh <= 0:
        return {"te_becijferen": False, "reden": f"{len(kwartieren)} kwartieren (minimaal {MIN_KWARTIEREN})"}
    eta = max(0.01, rendement) ** 0.5
    gem = sum(k["prijs_eur"] for k in kwartieren) / len(kwartieren)
    rest = gem * eta   # per kWh die aan het eind nog in de accu zit
    exp = [k["export_2027_eur"] for k in kwartieren if k.get("export_2027_eur") is not None]
    gem_export = sum(exp) / len(exp) if exp else None
    met_2027 = len(exp) >= len(kwartieren) - 16
    begin = min(capaciteit_kwh, max(0.0, begin_kwh))
    uit: dict = {"te_becijferen": True, "kwartieren": len(kwartieren),
                 "uit_meetlaag": sum(1 for k in kwartieren if k.get("bron") == "meetlaag"),
                 "met_2027": met_2027}

    regimes = ("salderen", "2027") if met_2027 else ("salderen",)
    # werkelijk: gemeten netstroom, met dezelfde restwaarde
    for regime in regimes:
        kosten = sum(_netkosten(k["huis_kwh"] - k["pv_kwh"] - k["accu_kwh"], k, regime, gem_export)
                     + max(0.0, k["accu_kwh"]) * slijtage_eur for k in kwartieren)
        uit[f"werkelijk_{regime}_eur"] = round(kosten - (eind_kwh - begin) * rest, 3)

    # het accumodel per kwartier (één scenario: wat er gebeurde)
    # v5.131.0: `vooruitplan` rekent het hele heen-en-terugverlies bij het
    # laden en levert bij ontladen 1 op 1. Zijn eenheid is dus "wat er nog
    # uit kan" = opgeslagen x √rendement. Begin en capaciteit gingen er als
    # opgeslagen kWh in (ongeveer 10 % te veel), en de eindvoorraad werd
    # nog eens met √rendement verminderd. Nu in zijn eigen eenheid.
    begin_v = begin * eta
    cap_v = capaciteit_kwh * eta
    model = [{"zon": (k["pv_kwh"],), "verbruik": (k["huis_kwh"],), "reserve_kwh": k.get("reserve_kwh") or 0.0,
              "import_eur": k["prijs_eur"]} for k in kwartieren]
    arg = dict(laad_kwh=laad_kw / 4, ontlaad_kwh=ontlaad_kw / 4, rendement=rendement, slijtage_eur=slijtage_eur)
    modi_boom = [modus_van(k.get("stand"), k["accu_kwh"], max(0.0, k["huis_kwh"] - k["pv_kwh"])) for k in kwartieren]
    uit["beslisboom_modi"] = {m: modi_boom.count(m) for m in V.MODI if modi_boom.count(m)}
    for regime in regimes:
        kws = [{**m, "export_eur": _export(k, regime, gem_export)} for m, k in zip(model, kwartieren)]
        boom = V.waardeer_modi(kws, modi_boom, begin_v, cap_v, gewichten=(1.0,), klaar=True,
                               eindwaarde_eur=gem, **arg)
        uit[f"beslisboom_{regime}_eur"] = round(boom["verwacht_eur"] + begin * rest, 3)
        opt = V.optimaliseer_scenarios(kws, begin_v, cap_v, gewichten=(1.0,), klaar=True,
                                       eindwaarde_eur=gem, **arg)
        if opt.get("beschikbaar"):
            plan = V.waardeer_modi(kws, opt["modi"], begin_v, cap_v, gewichten=(1.0,), klaar=True,
                                   eindwaarde_eur=gem, **arg)
            uit[f"scenarioplan_{regime}_eur"] = round(plan["verwacht_eur"] + begin * rest, 3)

    # keuzeoordeel (salderen): best mogelijk en gemist
    ko = [K.Kwartier(tijd=k["tijd"], huis_kwh=k["huis_kwh"], pv_kwh=k["pv_kwh"], prijs_eur=k["prijs_eur"],
                     accu_kwh=k["accu_kwh"], reden=k.get("reden"), stand=k.get("stand")) for k in kwartieren]
    spijt = K.spijt_per_kwartier(ko, begin_kwh=begin, capaciteit_kwh=capaciteit_kwh, bodem_kwh=0.0,
                                 laad_kw=laad_kw, ontlaad_kw=ontlaad_kw, rendement=rendement,
                                 slijtage_eur_per_kwh=slijtage_eur)
    if spijt.get("te_becijferen"):
        uit["gemist_salderen_eur"] = round(spijt.get("gemist_eur") or 0.0, 3)
        # zelfde restwaarde-afspraak als hierboven: het begin telt mee
        uit["best_mogelijk_salderen_eur"] = round(spijt["beste_kosten_eur"] + begin * rest, 3)
    # v5.131.0: ook met laden uit het net - de eerlijke maat voor het
    # scenarioplan (dat mag het ook)
    met_net = K.beste_kosten(ko, capaciteit_kwh=capaciteit_kwh, begin_kwh=begin, bodem_kwh=0.0,
                             laad_kw=laad_kw, ontlaad_kw=ontlaad_kw, rendement=rendement,
                             slijtage_eur_per_kwh=slijtage_eur, netladen=True)
    if met_net is not None:
        uit["best_mogelijk_netladen_salderen_eur"] = round(met_net + begin * rest, 3)

    # generale repetitie (2027): regels 2027 en best mogelijk
    if met_2027:
        r27 = [R.Kwartier(huis_kwh=k["huis_kwh"], pv_kwh=k["pv_kwh"], import_eur=k["prijs_eur"],
                          export_eur=k.get("export_2027_eur"), accu_kwh=k["accu_kwh"],
                          opvangen=k.get("r27_opvangen"), verkoop=k.get("r27_verkoop"),
                          dekt=str(k.get("stand") or "") in ("smart", "smart_discharging"),
                          begrens=k.get("r27_begrens"), ruimte=k.get("r27_ruimte")) for k in kwartieren]
        rep = R.repetitie(r27, begin_kwh=begin, eind_kwh=eind_kwh, capaciteit_kwh=capaciteit_kwh,
                          laad_kw=laad_kw, ontlaad_kw=ontlaad_kw, rendement=rendement,
                          slijtage_eur_per_kwh=slijtage_eur)
        if rep.get("te_becijferen"):
            uit["regels_2027_eur"] = rep.get("regels_2027_eur")
            uit["best_mogelijk_2027_eur"] = rep.get("best_mogelijk_eur")
            uit["zonder_accu_2027_eur"] = rep.get("zonder_accu_eur")
    return uit


SCOREVELDEN = (
    "werkelijk_salderen_eur", "beslisboom_salderen_eur", "scenarioplan_salderen_eur",
    "best_mogelijk_salderen_eur", "best_mogelijk_netladen_salderen_eur", "gemist_salderen_eur",
    "werkelijk_2027_eur", "beslisboom_2027_eur", "scenarioplan_2027_eur", "regels_2027_eur",
    "best_mogelijk_2027_eur",
)


def herspeel(dagverloop: dict, gemeten: dict | None, *, capaciteit_kwh: float, min_soc_procent: float,
             laad_kw: float, ontlaad_kw: float, rendement: float, slijtage_eur: float,
             dagen: int = 40, tot_en_met: str | None = None) -> dict:
    """De laatste `dagen` volledige dagen opnieuw afspelen en samenvatten."""
    schaal = max(1.0, 100.0 - min_soc_procent)
    gekozen = [d for d in sorted(dagverloop or {}) if tot_en_met is None or d <= tot_en_met][-dagen:]
    per_dag = []
    for dag in gekozen:
        rijen = dagverloop.get(dag) or []
        kw = dag_kwartieren(rijen, (gemeten or {}).get(dag))
        socs = [r.get("soc") for r in sorted(rijen, key=lambda x: str(x.get("tijd")))
                if isinstance(r, dict) and r.get("soc") is not None]

        def _kwh(soc):
            return max(0.0, (float(soc) - min_soc_procent) / schaal * capaciteit_kwh)

        score = score_dag(kw, begin_kwh=_kwh(socs[0]) if socs else 0.0,
                          eind_kwh=_kwh(socs[-1]) if socs else 0.0, capaciteit_kwh=capaciteit_kwh,
                          laad_kw=laad_kw, ontlaad_kw=ontlaad_kw, rendement=rendement, slijtage_eur=slijtage_eur)
        per_dag.append({"datum": dag, **score})
    return {"dagen": per_dag, "samenvatting": samenvatting(per_dag),
            "model": {"capaciteit_kwh": round(capaciteit_kwh, 2), "min_soc_procent": min_soc_procent,
                      "laad_kw": laad_kw, "ontlaad_kw": ontlaad_kw, "rendement": rendement,
                      "slijtage_eur": slijtage_eur}}


def samenvatting(per_dag: list[dict]) -> dict:
    """Per strategie: som en gemiddelde per dag over de dagen die er een getal voor hebben."""
    goed = [d for d in per_dag if d.get("te_becijferen")]
    uit: dict = {"dagen": len(goed), "dagen_overgeslagen": len(per_dag) - len(goed)}
    for veld in SCOREVELDEN:
        w = [d[veld] for d in goed if d.get(veld) is not None]
        if w:
            uit[veld.replace("_eur", "_per_dag_eur")] = round(sum(w) / len(w), 3)
            uit[veld.replace("_eur", "_som_eur")] = round(sum(w), 2)
    return uit


def vergelijk(oud: dict, nieuw: dict) -> dict:
    """Twee herspeelresultaten (voor en na een wijziging) per dag naast elkaar.
    Negatief = de nieuwe versie is goedkoper."""
    o = {d["datum"]: d for d in oud.get("dagen") or [] if d.get("te_becijferen")}
    n = {d["datum"]: d for d in nieuw.get("dagen") or [] if d.get("te_becijferen")}
    gedeeld = sorted(set(o) & set(n))
    uit: dict = {"dagen": len(gedeeld), "verschil_per_veld_eur": {}, "grootste_verschillen": []}
    for veld in SCOREVELDEN:
        paren = [(d, n[d][veld] - o[d][veld]) for d in gedeeld
                 if o[d].get(veld) is not None and n[d].get(veld) is not None]
        if paren:
            uit["verschil_per_veld_eur"][veld] = round(sum(v for _d, v in paren), 3)
            uit["grootste_verschillen"] += [{"datum": d, "veld": veld, "verschil_eur": round(v, 3)}
                                            for d, v in paren if abs(v) >= 0.01]
    uit["grootste_verschillen"] = sorted(uit["grootste_verschillen"], key=lambda x: -abs(x["verschil_eur"]))[:10]
    return uit
