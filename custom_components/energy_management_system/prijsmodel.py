"""Prijsverwachting per dag vooruit, met prijsvertraging (v5.174.0).

Gevraagd (standing authority, "doe wat het beste is voor het EMS"): leer van
de methode van jeroen.nl (LEAR-achtige regressie op groothandelsprijzen, met
de prijs van gisteren en van vorige week als kenmerk en een apart model per
dag vooruit). Geen code overgenomen; alleen het idee.

Wat er bij komt ten opzichte van v5.100 - v5.173 (`prijsverwachting.py`):

1. Prijsvertraging. Per uur de prijs van hetzelfde lokale uur op de laatste
   dag die op het moment van voorspellen bekend was (voor morgen: vandaag;
   voor overmorgen: ook vandaag, want morgen is dan nog niet bekend) en op
   dezelfde weekdag een week eerder. Ontbreekt een vertraging, dan telt het
   prijsniveau van die week in zijn plaats.
2. Een model per dag vooruit: morgen (k=1), overmorgen (k=2) en drie tot en
   met zeven dagen (k=3..7 samen, met k als kenmerk). Het niveau en de
   gassprong komen steeds uit wat op dag d-k bekend was - geen lek uit de
   toekomst, ook niet in de training.
3. Optioneel: de verre buren (Denemarken, de Britse Noordzee, Zuid-Engeland,
   Noord-Frankrijk) als derde weergroep, en het gasniveau als kenmerk.

Welke opzet het EMS gebruikt, beslist de dagelijkse terugtoets: alle
kandidaten op dezelfde dagen, dezelfde vooruitkijktijden; de laagste
gemiddelde afwijking over morgen tot en met overmorgen + 3 wint. Zo blijft
alleen wat aantoonbaar helpt - met het echte weer van Open-Meteo, in Home
Assistant zelf.

Snelheid: de rijen hangen niet af van het moment van voorspellen (alles in
een rij is op d-k bekend). Ze worden eens per groep opgebouwd en per
oorsprong gefilterd op datum; het oplossen gaat met numpy als dat er is
(Home Assistant levert het mee; `waardeplan` gebruikt het al), anders met de
zuivere Gauss-eliminatie uit `prijsverwachting`.

Zuivere functies, zonder Home Assistant.
"""
from __future__ import annotations

import statistics
from datetime import date, timedelta

from . import prijsverwachting as P

#: De kandidaten. `basis` is precies het model van v5.173.
OPZETTEN: dict[str, dict] = {
    "basis": {"vertraging": False, "per_dag": False, "ver": False, "gasniveau": False},
    "vertraging": {"vertraging": True, "per_dag": True, "ver": False, "gasniveau": False},
    "vertraging_ver": {"vertraging": True, "per_dag": True, "ver": True, "gasniveau": False},
    "vertraging_gas": {"vertraging": True, "per_dag": True, "ver": False, "gasniveau": True},
    "vertraging_ver_gas": {"vertraging": True, "per_dag": True, "ver": True, "gasniveau": True},
}
#: Zonder terugtoets (vlak na een herstart, voor de eerste toets klaar is).
STANDAARD_OPZET = "vertraging"
#: Zo ver vooruit wordt getoetst en verwacht.
MAX_VOORUIT = 7
#: De groepen modellen: morgen, overmorgen, de rest van de week.
GROEPEN = {1: (1,), 2: (2,), 3: (3, 4, 5, 6, 7)}
#: De keuze kijkt naar deze vooruitkijktijden (de rest weegt mee in het
#: rapport, maar morgen tot en met over drie dagen raakt het EMS het meest).
KEUZE_VOORUIT = (1, 2, 3)


def groep_van(k: int) -> int:
    return 1 if k <= 1 else 2 if k == 2 else 3


class Context:
    """Snelle opzoektabellen over de bekende uurprijzen en het gas."""

    def __init__(self, prijzen: dict, gas: dict | None = None) -> None:
        self.prijzen = prijzen
        self.per_uur: dict = {}
        som: dict = {}
        self.dag_min: dict = {}
        self.dag_max: dict = {}
        for sleutel, prijs in prijzen.items():
            lok = P._lokaal(sleutel)
            d = lok.date()
            self.per_uur[(d, lok.hour)] = prijs
            s = som.setdefault(d, [0.0, 0])
            s[0] += prijs
            s[1] += 1
            self.dag_min[d] = min(self.dag_min.get(d, prijs), prijs)
            self.dag_max[d] = max(self.dag_max.get(d, prijs), prijs)
        self.dagsom = som
        self.gas = dict(gas or {})
        self._gasdagen = sorted(self.gas)
        self._niveau: dict = {}
        self._sprong: dict = {}

    def niveau_tot(self, laatste: date) -> float | None:
        """Gemiddelde over de zeven dagen tot en met `laatste`; met de
        terugval van v5.100.1 (een eerder niveau als de week dun is)."""
        if laatste in self._niveau:
            return self._niveau[laatste]
        uit = None
        for terug in range(0, 22):
            eind = laatste - timedelta(days=terug)
            tot, n = 0.0, 0
            for i in range(P.NIVEAU_DAGEN):
                s = self.dagsom.get(eind - timedelta(days=i))
                if s:
                    tot += s[0]
                    n += s[1]
            if n >= 24 * 3:
                uit = tot / n
                break
        self._niveau[laatste] = uit
        return uit

    def niveau_strikt(self, laatste: date) -> float | None:
        """Precies `niveau_voor(prijzen, laatste + 1)` van v5.100 (zonder terugval)."""
        tot, n = 0.0, 0
        for i in range(P.NIVEAU_DAGEN):
            s = self.dagsom.get(laatste - timedelta(days=i))
            if s:
                tot += s[0]
                n += s[1]
        return tot / n if n >= 24 * 3 else None

    def niveau_oud(self, dag: date, bekend: date) -> float | None:
        """Het niveau zoals `verwacht_dag` van v5.100 het bij het voorspellen
        nam: de zeven dagen voor `dag` (of eerder), met alleen wat op
        `bekend` bekend was."""
        for terug in range(0, 22):
            eind = dag - timedelta(days=terug + 1)
            tot, n = 0.0, 0
            for i in range(P.NIVEAU_DAGEN):
                d = eind - timedelta(days=i)
                s = self.dagsom.get(d) if d <= bekend else None
                if s:
                    tot += s[0]
                    n += s[1]
            if n >= 24 * 3:
                return tot / n
        return None

    def gas_tot(self, dag: date, tot: date) -> tuple[float, float]:
        """(gassprong, gasniveau) voor `dag` met de gasprijzen tot en met `tot`."""
        sleutel = (dag, tot)
        if sleutel not in self._sprong:
            bekend = [d for d in self._gasdagen if d <= tot and d <= dag]
            if not bekend:
                self._sprong[sleutel] = (0.0, 0.0)
            else:
                nu = self.gas[bekend[-1]]
                week = [self.gas[d] for d in bekend if dag - timedelta(days=P.GAS_DAGEN) <= d < dag]
                self._sprong[sleutel] = ((nu - statistics.fmean(week)) if week else 0.0, nu)
        return self._sprong[sleutel]

    def grenzen_tot(self, tot: date) -> tuple[float, float]:
        laag = [p for d, p in self.dag_min.items() if d <= tot]
        hoog = [p for d, p in self.dag_max.items() if d <= tot]
        if sum(self.dagsom[d][1] for d in self.dagsom if d <= tot) < 24:
            return float("-inf"), float("inf")
        return min(laag) - P.GRENS_ONDER_EUR, max(hoog) + P.GRENS_BOVEN_EUR


def rij(sleutel: str, k: int, w: dict | None, ctx: Context, opzet: dict,
        training: bool = True) -> list[float] | None:
    """Kenmerken van één uur, k dagen na de laatste bekende dag.

    `w` is het weer van dat uur (eventueel verstoord door een ensemblelid).
    Voor `basis` precies de kenmerken van v5.100 - v5.173, inclusief de
    toenmalige keuze voor het niveau (in de training de week direct voor de
    dag, bij het voorspellen de laatst bekende).
    """
    if w is None:
        return None
    lok = P._lokaal(sleutel)
    d = lok.date()
    bekend = d - timedelta(days=k)
    if opzet["per_dag"]:
        niveau = ctx.niveau_tot(bekend)
        sprong, gasniveau = ctx.gas_tot(d, bekend)
    elif training:
        niveau = ctx.niveau_strikt(d - timedelta(days=1))
        sprong, gasniveau = ctx.gas_tot(d, d)
    else:
        niveau = ctx.niveau_oud(d, bekend)
        sprong, gasniveau = ctx.gas_tot(d, bekend)
    if niveau is None:
        return None
    wind = w["wind"] / 10.0
    vrij = 1.0 if lok.weekday() >= 5 or P.vrije_dag(d) else 0.0
    uit = [1.0, wind, wind * wind, w["zon"] / 100.0, w["temp"] / 10.0, vrij, niveau * 10.0,
           w.get("wind_buur", w["wind"]) / 10.0, w.get("zon_buur", w["zon"]) / 100.0, sprong * 10.0]
    if opzet["ver"]:
        uit += [w.get("wind_ver", w.get("wind_buur", w["wind"])) / 10.0,
                w.get("zon_ver", w.get("zon_buur", w["zon"])) / 100.0]
    if opzet["gasniveau"]:
        uit.append(gasniveau)
    if opzet["vertraging"]:
        gisteren = ctx.per_uur.get((bekend, lok.hour), niveau)
        week = ctx.per_uur.get((d - timedelta(days=7), lok.hour), gisteren)
        uit += [gisteren * 10.0, week * 10.0]
    if opzet["per_dag"] and k >= 3:
        uit.append(k / 7.0)
    uit += [1.0 if lok.hour == u else 0.0 for u in range(1, 24)]
    return uit


def groepen_van(opzet: dict) -> dict:
    """De modellen van een opzet: per groep de k's waarop hij traint.
    Zonder `per_dag` één model op k=1 voor alle dagen (zoals v5.100)."""
    if not opzet["per_dag"]:
        return {1: (1,)}
    return GROEPEN


def model_voor(opzet: dict, k: int) -> int:
    return groep_van(k) if opzet["per_dag"] else 1


def bouw_rijen(prijzen: dict, weer: dict, ctx: Context, opzet: dict) -> dict:
    """Per groep: rijen, doelen en de datum van elke rij (voor de oorsprong)."""
    uit = {}
    for groep, ks in groepen_van(opzet).items():
        rijen, doelen, dagen = [], [], []
        for sleutel in sorted(prijzen):
            w = weer.get(sleutel)
            if w is None:
                continue
            d = P._lokaal(sleutel).date()
            for k in ks:
                r = rij(sleutel, k, w, ctx, opzet)
                if r is not None:
                    rijen.append(r)
                    doelen.append(prijzen[sleutel])
                    dagen.append(d.toordinal())
        uit[groep] = (rijen, doelen, dagen)
    return uit


def _numpy():
    try:
        import numpy as np  # noqa: PLC0415 - optioneel, alleen voor snelheid
        return np
    except ImportError:  # pragma: no cover - Home Assistant levert numpy mee
        return None


def fit_tot(groep_data: tuple, tot: date | None, ridge: float = P.RIDGE,
            cache: dict | None = None) -> list[float] | None:
    """Kleinste kwadraten met ridge op de rijen tot en met `tot`."""
    rijen, doelen, dagen = groep_data
    if not rijen:
        return None
    grens = tot.toordinal() if tot is not None else None
    np = _numpy()
    if np is None:
        if grens is None:
            return P.fit(rijen, doelen, ridge)
        keus = [i for i, d in enumerate(dagen) if d <= grens]
        return P.fit([rijen[i] for i in keus], [doelen[i] for i in keus], ridge)
    if cache is not None and "x" in cache:
        x, y, dd = cache["x"], cache["y"], cache["d"]
    else:
        x, y, dd = np.asarray(rijen, dtype=float), np.asarray(doelen, dtype=float), np.asarray(dagen)
        if cache is not None:
            cache.update(x=x, y=y, d=dd)
    if grens is not None:
        masker = dd <= grens
        x, y = x[masker], y[masker]
    if len(y) == 0:
        return None
    xtx = x.T @ x
    idx = np.arange(1, xtx.shape[0])
    xtx[idx, idx] += ridge
    try:
        return [float(c) for c in np.linalg.solve(xtx, x.T @ y)]
    except np.linalg.LinAlgError:
        return None


def voorspel_dag(modellen: dict, opzet: dict, weer: dict, ctx: Context, dag: date,
                 bekend_tot: date, tot: date | None = None) -> list[dict] | None:
    """Per uur van `dag` de verwachte prijs (geklemd op het bekende bereik)."""
    k = (dag - bekend_tot).days
    coefs = modellen.get(model_voor(opzet, k))
    if coefs is None or k < 1:
        return None
    laag, hoog = ctx.grenzen_tot(tot or bekend_tot)
    uren = []
    for sleutel in P.uren_van_dag(dag):
        r = rij(sleutel, k, weer.get(sleutel), ctx, opzet, training=False)
        if r is None or len(r) != len(coefs):
            return None
        prijs = min(hoog, max(laag, P.voorspel_rij(coefs, r)))
        uren.append({"uur": P._lokaal(sleutel).strftime("%H:%M"), "sleutel": sleutel,
                     "prijs_eur": round(prijs, 4)})
    return uren


def train(prijzen: dict, weer: dict, ctx: Context, opzet: dict,
          rijen: dict | None = None) -> dict:
    """Alle modellen van een opzet op alles wat bekend is."""
    rijen = rijen or bouw_rijen(prijzen, weer, ctx, opzet)
    return {g: fit_tot(data, None) for g, data in rijen.items()
            if len(data[0]) >= P.MIN_UREN}


# --- terugtoets per dag vooruit -----------------------------------------

def _naieven(ctx: Context, dag: date, k: int) -> dict:
    """De drie simpele verwachtingen per lokaal uur: zoals de laatste bekende
    dag, zoals vorige week, en het gemiddelde van die twee."""
    uit = {"gisteren": {}, "week": {}, "mix": {}}
    for uur in range(24):
        g = ctx.per_uur.get((dag - timedelta(days=k), uur))
        w = ctx.per_uur.get((dag - timedelta(days=7), uur))
        if g is not None:
            uit["gisteren"][uur] = g
        if w is not None:
            uit["week"][uur] = w
        if g is not None and w is not None:
            uit["mix"][uur] = (g + w) / 2
    return uit


def _dagfout(uren: list[dict], ctx: Context, dag: date, k: int) -> dict | None:
    """Afwijking van het model en de naieven op één dag, plus de residuen."""
    paren, res = [], []
    naief = _naieven(ctx, dag, k)
    fouten = {"gisteren": [], "week": [], "mix": []}
    for u in uren:
        uur = P._lokaal(u["sleutel"]).hour
        echt = ctx.per_uur.get((dag, uur))
        if echt is None:
            continue
        paren.append(abs(u["prijs_eur"] - echt))
        res.append(echt - u["prijs_eur"])
        for naam in fouten:
            if uur in naief[naam]:
                fouten[naam].append(abs(naief[naam][uur] - echt))
    if len(paren) < 20 or any(len(v) < 20 for v in fouten.values()):
        return None
    uit = {"model": statistics.fmean(paren), "residuen": res}
    uit.update({naam: statistics.fmean(v) for naam, v in fouten.items()})
    if k <= 2:
        # in de vorm van v5.100 (duurste/goedkoopste uren geraakt, per dag)
        echt = {u["sleutel"]: ctx.prijzen[u["sleutel"]] for u in uren if u["sleutel"] in ctx.prijzen}
        n_uren = [{**u, "prijs_eur": naief["gisteren"][P._lokaal(u["sleutel"]).hour]} for u in uren
                  if P._lokaal(u["sleutel"]).hour in naief["gisteren"]]
        vm = P.vergelijk({"datum": dag.isoformat(), "uren": uren}, echt)
        vn = P.vergelijk({"datum": dag.isoformat(), "uren": n_uren}, echt)
        if vm and vn:
            uit["vergelijk"] = {"model": vm, "naief": vn}
    return uit


def terugtoets(prijzen: dict, weer: dict, opzet: dict, oorsprongen: int = 21,
               gas: dict | None = None, ctx: Context | None = None,
               rijen: dict | None = None) -> dict:
    """Voor elke oorsprong o (de laatste bekende dag) van de laatste
    `oorsprongen` dagen: train op wat er op o bekend was en voorspel o+1 tot
    en met o+7. Per k de dagafwijkingen van model en naieven.

    Het weer is het gemeten/geanalyseerde weer (zoals in v5.100): de fout
    van de weersverwachting zelf zit er niet in.
    """
    ctx = ctx or Context(prijzen, gas)
    rijen = rijen or bouw_rijen(prijzen, weer, ctx, opzet)
    alle = sorted(ctx.dagsom)
    if not alle:
        return {"per_k": {}}
    laatste = alle[-1]
    caches = {g: {} for g in rijen}
    per_k: dict = {k: [] for k in range(1, MAX_VOORUIT + 1)}
    for terug in range(oorsprongen, 0, -1):
        o = laatste - timedelta(days=terug)
        modellen = {}
        for g, data in rijen.items():
            n = sum(1 for d in data[2] if d <= o.toordinal())
            if n >= P.MIN_UREN:
                modellen[g] = fit_tot(data, o, cache=caches[g])
        for k in range(1, MAX_VOORUIT + 1):
            dag = o + timedelta(days=k)
            if dag > laatste:
                break
            uren = voorspel_dag(modellen, opzet, weer, ctx, dag, o)
            fout = _dagfout(uren, ctx, dag, k) if uren else None
            if fout:
                fout["datum"] = dag.isoformat()
                per_k[k].append(fout)
    return {"per_k": per_k}


def vat_samen(toets: dict) -> dict:
    """Per k: gemiddelde afwijking (ct) van model en naieven, en de residuen
    als kwantielen (voor de band)."""
    uit = {}
    for k, dagen in (toets.get("per_k") or {}).items():
        if not dagen:
            continue
        res = sorted(r for d in dagen for r in d["residuen"])
        uit[k] = {
            "dagen": len(dagen),
            "model_ct": round(statistics.fmean(d["model"] for d in dagen) * 100, 2),
            "gisteren_ct": round(statistics.fmean(d["gisteren"] for d in dagen) * 100, 2),
            "week_ct": round(statistics.fmean(d["week"] for d in dagen) * 100, 2),
            "mix_ct": round(statistics.fmean(d["mix"] for d in dagen) * 100, 2),
            "res_p10": round(kwantiel(res, 0.10), 4),
            "res_p90": round(kwantiel(res, 0.90), 4),
        }
    return uit


def oordeel_v5100(toets: dict, k: int = 2) -> dict:
    """De terugtoets van k dagen vooruit in de vorm van `backtest` (v5.100),
    voor de bestaande attributen en de kaart."""
    uitkomsten = [d["vergelijk"] for d in (toets.get("per_k") or {}).get(k) or [] if d.get("vergelijk")]
    uit = P.beoordeel(uitkomsten)
    uit["per_dag"] = [P.dagrij(u) for u in uitkomsten]
    return uit


#: Zonneplan rekent btw over alles; de energiebelasting is een vast bedrag
#: per kWh en valt weg in een verschil. Een afwijking excl. belasting en btw
#: is dus de afwijking incl. gedeeld door 1,21 (vergelijkbaar met jeroen.nl,
#: die groothandelsprijzen voorspelt).
BTW_FACTOR = 1.21
#: jeroen.nl, gemiddelde afwijking over een jaar (ct/kWh, excl. belasting en
#: btw), morgen en over zeven dagen; laatste 30 dagen; dekking van de band.
REFERENTIE_JEROEN = {"d1_ct": 1.64, "d7_ct": 2.66, "laatste_30_dagen_ct": 3.42,
                     "dekking_band_procent": 71, "doel_dekking_procent": 80}


def tabel_per_vooruit(terug: dict | None, live: dict | None) -> list[dict]:
    """Per dag vooruit: terugtoets en live, incl. en excl. belasting/btw."""
    rijen = []
    for k in range(1, MAX_VOORUIT + 1):
        t = (terug or {}).get(k) or (terug or {}).get(str(k)) or {}
        lv = (live or {}).get(f"d{k}") or {}
        if not t and not lv.get("dagen"):
            continue
        rij = {"vooruit": k}
        if t:
            rij.update({"terugtoets_ct": t["model_ct"], "terugtoets_excl_ct": round(t["model_ct"] / BTW_FACTOR, 2),
                        "zoals_gisteren_ct": t["gisteren_ct"], "zoals_vorige_week_ct": t["week_ct"],
                        "mix_ct": t["mix_ct"], "terugtoets_dagen": t["dagen"]})
        if lv.get("dagen"):
            rij.update({"live_ct": lv.get("afwijking_model_ct"),
                        "live_excl_ct": round((lv.get("afwijking_model_ct") or 0) / BTW_FACTOR, 2),
                        "live_zoals_gisteren_ct": lv.get("afwijking_zoals_gisteren_ct"),
                        "live_dagen": lv.get("dagen"), "dekking_band_procent": lv.get("dekking_band_procent")})
        rijen.append(rij)
    return rijen


def kwantiel(gesorteerd: list[float], q: float) -> float:
    """Lineair geinterpoleerd kwantiel van een gesorteerde lijst."""
    if not gesorteerd:
        return 0.0
    pos = (len(gesorteerd) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(gesorteerd) - 1)
    return gesorteerd[lo] + (gesorteerd[hi] - gesorteerd[lo]) * (pos - lo)


def keuzescore(samen: dict) -> float | None:
    """Gemiddelde modelafwijking over KEUZE_VOORUIT (lager is beter)."""
    waarden = [samen[k]["model_ct"] for k in KEUZE_VOORUIT if k in samen]
    return statistics.fmean(waarden) if len(waarden) == len(KEUZE_VOORUIT) else None


def kies_opzet(prijzen: dict, weer: dict, gas: dict | None = None,
               oorsprongen: int = 21, kandidaten: tuple | None = None) -> dict:
    """Alle kandidaten op dezelfde dagen; de laagste keuzescore wint.

    Een kandidaat die niets toevoegt aan `basis` wint alleen met een echte
    verbetering (minstens 1% lager), anders blijft het eenvoudigere model.
    """
    ctx = Context(prijzen, gas)
    rapport, scores, toetsen = {}, {}, {}
    for naam in kandidaten or tuple(OPZETTEN):
        toetsen[naam] = terugtoets(prijzen, weer, OPZETTEN[naam], oorsprongen, ctx=ctx)
        samen = vat_samen(toetsen[naam])
        rapport[naam] = samen
        score = keuzescore(samen)
        if score is not None:
            scores[naam] = score
    if not scores:
        return {"opzet": STANDAARD_OPZET, "scores": {}, "per_opzet": rapport, "reden": "nog geen terugtoets"}
    beste = min(scores, key=scores.get)
    if "basis" in scores and beste != "basis" and scores[beste] > scores["basis"] * 0.99:
        beste = "basis"
    return {"opzet": beste, "scores": {n: round(s, 3) for n, s in scores.items()},
            "per_opzet": rapport, "reden": None,
            "backtest": oordeel_v5100(toetsen[beste], 2),
            "schaal_terugtoets": schaal_uit_terugtoets(toetsen[beste]),
            "residuen": {k: {"res_p10": v["res_p10"], "res_p90": v["res_p90"]}
                         for k, v in rapport[beste].items()}}


def schaal_uit_terugtoets(toets: dict) -> float:
    """Een eerste schaal voor de band, zolang er live nog weinig gemeten is.

    De kwantielen van de residuen uit de oudere helft van de toetsdagen,
    toegepast op de nieuwere helft: met welke factor had die band 80%
    gedekt? (Met een vaste band dekte die over 21 dagen in de terugtoets maar
    ~58%; de prijzen bewegen per periode anders.)"""
    per_k = toets.get("per_k") or {}
    datums = sorted({d["datum"] for dagen in per_k.values() for d in dagen})
    if len(datums) < 8:
        return 1.0
    midden = datums[len(datums) // 2]
    nodig = []
    for dagen in per_k.values():
        oud = sorted(r for d in dagen if d["datum"] < midden for r in d["residuen"])
        if len(oud) < 48:
            continue
        lo, hi = min(kwantiel(oud, 0.10), -1e-4), max(kwantiel(oud, 0.90), 1e-4)
        nodig += [abs(r / hi) if r >= 0 else abs(r / lo)
                  for d in dagen if d["datum"] >= midden for r in d["residuen"]]
    if len(nodig) < 72:
        return 1.0
    return round(max(0.5, min(4.0, kwantiel(sorted(nodig), 0.80))), 3)
