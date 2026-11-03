"""Onzekerheidsband om de prijsverwachting (v5.174.0).

Idee van jeroen.nl: de 51 leden van de ECMWF-ensembleverwachting door het
model sturen; de spreiding van de uitkomsten is de onzekerheid door het weer.
Daarbovenop zit de fout van het model zelf (die ook bij perfect weer
bestaat). Beide samen, als onafhankelijke delen (wortel uit de som van de
kwadraten), geven de band P10 - P90.

- Ensemble: Open-Meteo, model `ecmwf_ifs025`, alleen windsnelheid op 100 m
  en instraling, op vijf punten (twee in Nederland, twee in Duitsland, één
  bij Denemarken) - klein houden. Per weergroep verschuift elk lid het
  deterministische weer met zijn afwijking van het ensemblegemiddelde.
- Modelfout: de kwantielen van de residuen uit de terugtoets, per dag
  vooruit. Lukt het ensemble niet, dan alleen dit deel (de terugval).
- Kalibratie: de gepubliceerde band wordt bewaard (onschaalde breedte en de
  gebruikte schaal); achteraf telt hoe vaak de echte prijs erbinnen viel.
  De schaal is de factor waarmee de onschaalde band 80% van de uren had
  gedekt - gedempt bij weinig dagen.

Zuivere functies, zonder Home Assistant.
"""
from __future__ import annotations

import math
import statistics
from datetime import date, timedelta

from . import prijsmodel as M
from . import prijsverwachting as P

ENSEMBLE_URL = (
    "https://ensemble-api.open-meteo.com/v1/ensemble?latitude={lat}&longitude={lon}"
    "&hourly=wind_speed_100m,shortwave_radiation&models=ecmwf_ifs025"
    "&forecast_days={dagen}&timezone=UTC"
)
#: Per weergroep de punten van het ensemble (een deel van de punten van het
#: deterministische weer).
ENSEMBLE_PUNTEN = {
    "nl": ((52.6, 4.0), (52.1, 5.2)),
    "buur": ((54.3, 8.0), (51.0, 10.5)),
    "ver": ((55.5, 7.7),),
}
ENSEMBLE_DAGEN = 8
#: De velden van het deterministische weer per groep: (wind, zon).
GROEP_VELDEN = {"nl": ("wind", "zon"), "buur": ("wind_buur", "zon_buur"), "ver": ("wind_ver", "zon_ver")}
#: P10/P90 van een normale verdeling in standaarddeviaties; P25/P75 idem.
Z80 = 1.2816
Z50 = 0.6745
DOEL_DEKKING = 0.80
SCHAAL_MIN = 0.5
SCHAAL_MAX = 4.0
SCHAAL_DEMPING = 3
SCHAAL_DAGEN = 21


def ensemble_url() -> str:
    punten = [p for groep in ENSEMBLE_PUNTEN.values() for p in groep]
    return ENSEMBLE_URL.format(lat=",".join(str(p[0]) for p in punten),
                               lon=",".join(str(p[1]) for p in punten), dagen=ENSEMBLE_DAGEN)


def _leden(uurlijks: dict, veld: str) -> list[list]:
    """De reeksen van één grootheid: de controle (`veld`) en `veld_memberNN`."""
    sleutels = [veld] if veld in uurlijks else []
    sleutels += sorted(s for s in uurlijks if s.startswith(f"{veld}_member"))
    return [uurlijks.get(s) or [] for s in sleutels]


def ensemble_uit_open_meteo(antwoord) -> dict:
    """Per UTC-uur en groep de ledenwaarden, gemiddeld over de groepspunten.

    {sleutel: {"nl": {"wind": [..], "zon": [..]}, "buur": {...}, "ver": {...}}}
    Een uur telt per groep alleen als alle punten even veel leden hebben.
    """
    lijst = antwoord if isinstance(antwoord, list) else [antwoord]
    uit: dict = {}
    i = 0
    for groep, punten in ENSEMBLE_PUNTEN.items():
        deel = lijst[i:i + len(punten)]
        i += len(punten)
        if len(deel) < len(punten):
            continue
        for veld, bron in (("wind", "wind_speed_100m"), ("zon", "shortwave_radiation")):
            _vul_groep(uit, groep, veld, [_reeks_per_uur(p, bron) for p in deel])
    return uit


def _reeks_per_uur(punt: dict, bron: str) -> dict:
    uurlijks = (punt or {}).get("hourly") or {}
    tijden = uurlijks.get("time") or []
    leden = _leden(uurlijks, bron)
    per_uur = {}
    for j, t in enumerate(tijden):
        waarden = [r[j] for r in leden if j < len(r) and isinstance(r[j], (int, float))]
        if len(waarden) == len(leden) and waarden:
            per_uur[str(t)[:13]] = waarden
    return per_uur


def _vul_groep(uit: dict, groep: str, veld: str, reeksen: list[dict]) -> None:
    if not reeksen:
        return
    for sleutel in reeksen[0]:
        rijen = [r.get(sleutel) for r in reeksen]
        if any(r is None or len(r) != len(rijen[0]) for r in rijen):
            continue
        gem = [sum(r[m] for r in rijen) / len(rijen) for m in range(len(rijen[0]))]
        uit.setdefault(sleutel, {}).setdefault(groep, {})[veld] = gem


def leden_weer(w: dict, ens: dict | None) -> list[dict]:
    """Het weer van één uur per ensemblelid: het deterministische weer,
    per groep verschoven met (lid - ensemblegemiddelde)."""
    if not ens:
        return []
    aantal = min((len(v) for g in ens.values() for v in g.values()), default=0)
    if aantal < 2:
        return []
    uit = []
    for m in range(aantal):
        lid = dict(w)
        for groep, velden in GROEP_VELDEN.items():
            g = ens.get(groep) or {}
            for veld, doel in zip(("wind", "zon"), velden):
                reeks = g.get(veld)
                if not reeks or (doel not in w and groep != "nl"):
                    continue
                basis = w[doel] if doel in w else w[veld]
                lid[doel] = max(0.0, basis + reeks[m] - statistics.fmean(reeks))
        uit.append(lid)
    return uit


def ensemble_afwijking(coefs: list[float], opzet: dict, ctx, sleutel: str, k: int,
                       w: dict | None, ens: dict | None) -> tuple[float, float] | None:
    """(P10 - gemiddelde, P90 - gemiddelde) van de modelprijs over de leden."""
    if w is None:
        return None
    prijzen = []
    for lid in leden_weer(w, ens):
        r = M.rij(sleutel, k, lid, ctx, opzet, training=False)
        if r is None or len(r) != len(coefs):
            return None
        prijzen.append(P.voorspel_rij(coefs, r))
    if len(prijzen) < 2:
        return None
    gem = statistics.fmean(prijzen)
    prijzen.sort()
    return M.kwantiel(prijzen, 0.10) - gem, M.kwantiel(prijzen, 0.90) - gem


def onschaalde_band(res: dict | None, ens_afw: tuple | None) -> tuple[float, float] | None:
    """(onder, boven) ten opzichte van de verwachting, zonder schaal.

    Modelfout en weeronzekerheid als onafhankelijke delen. Zonder
    residuen geen band (dan is er nog geen terugtoets)."""
    if not res:
        return None
    r_lo, r_hi = min(res["res_p10"], 0.0), max(res["res_p90"], 0.0)
    e_lo, e_hi = (min(ens_afw[0], 0.0), max(ens_afw[1], 0.0)) if ens_afw else (0.0, 0.0)
    return -math.hypot(r_lo, e_lo), math.hypot(r_hi, e_hi)


def band_dag(uren: list[dict], modellen: dict, opzet: dict, ctx, weer: dict, dag: date,
             bekend_tot: date, residuen: dict, ensemble: dict | None, schaal: float) -> dict | None:
    """De band van één verwachte dag: per uur onschaald (voor het archief)
    en geschaald als P10/P25/P75/P90 (euro)."""
    k = (dag - bekend_tot).days
    res = residuen.get(k) or residuen.get(str(k))
    coefs = modellen.get(M.model_voor(opzet, k))
    if not res or coefs is None:
        return None
    rijen, met_ensemble = [], 0
    for u in uren:
        afw = ensemble_afwijking(coefs, opzet, ctx, u["sleutel"], k, weer.get(u["sleutel"]),
                                 (ensemble or {}).get(u["sleutel"]))
        met_ensemble += afw is not None
        band = onschaalde_band(res, afw)
        if band is None:
            return None
        rijen.append((u, band))
    return {
        "bron": "ensemble" if met_ensemble >= len(uren) // 2 else "restfout",
        "schaal": round(schaal, 3),
        "onschaald": [[u["sleutel"], round(lo, 4), round(hi, 4)] for u, (lo, hi) in rijen],
        "uren": [_kwantielen(u, lo, hi, schaal) for u, (lo, hi) in rijen],
    }


def _kwantielen(u: dict, lo: float, hi: float, schaal: float) -> dict:
    p = u["prijs_eur"]
    return {"uur": u["uur"], "sleutel": u["sleutel"], "p10": round(p + schaal * lo, 4),
            "p25": round(p + schaal * lo * Z50 / Z80, 4), "p75": round(p + schaal * hi * Z50 / Z80, 4),
            "p90": round(p + schaal * hi, 4)}


def verschuif(band: dict | None, uren: list[dict]) -> dict | None:
    """De band opnieuw om een (bijgestelde) verwachting leggen."""
    if not band:
        return band
    per = {s: (lo, hi) for s, lo, hi in band["onschaald"]}
    nieuw = [_kwantielen(u, *per[u["sleutel"]], band["schaal"]) for u in uren if u["sleutel"] in per]
    return {**band, "uren": nieuw}


# --- kalibratie en dekking ---------------------------------------------

def compact_band(band: dict | None) -> dict | None:
    if not band:
        return None
    return {"s": band["schaal"], "u": band["onschaald"]}


def _paren(archief: dict, prijzen: dict, vandaag: date, dagen: int):
    """(vooruit, fout, onder, boven, schaal) per uur uit het archief."""
    for terug in range(1, dagen + 1):
        datum = (vandaag - timedelta(days=terug)).isoformat()
        for sleutel, plek in (archief.get(datum) or {}).items():
            band = (plek or {}).get("band")
            model = (plek or {}).get("model")
            if not band or not model:
                continue
            punt = dict(model.get("uren") or [])
            for s, lo, hi in band.get("u") or []:
                if s in prijzen and s in punt:
                    yield sleutel, prijzen[s] - punt[s], lo, hi, float(band.get("s") or 1.0)


def kalibreer(archief: dict, prijzen: dict, vandaag: date, dagen: int = SCHAAL_DAGEN) -> dict:
    """De geleerde schaal en de gemeten dekking per vooruitkijktijd.

    Per uur de factor waarmee de onschaalde band de echte prijs net had
    gevangen; het 80e percentiel daarvan is de schaal die 80% had gedekt.
    Gedempt naar 1 bij weinig dagen (n / (n + 3)) en begrensd."""
    nodig, per_k, datums = [], {}, set()
    for terug in range(1, dagen + 1):
        if (archief.get((vandaag - timedelta(days=terug)).isoformat()) or {}):
            datums.add(terug)
    for sleutel, fout, lo, hi, s in _paren(archief, prijzen, vandaag, dagen):
        rand = hi if fout >= 0 else lo
        factor = (fout / rand) if rand else (0.0 if fout == 0 else SCHAAL_MAX)
        nodig.append(abs(factor))
        binnen = s * lo <= fout <= s * hi
        t = per_k.setdefault(sleutel, [0, 0])
        t[0] += binnen
        t[1] += 1
    n_dagen = len(datums)
    if len(nodig) < 24 * 3:
        return {"schaal": 1.0, "uren": len(nodig), "dagen": n_dagen, "dekking": _dekking(per_k)}
    ruw = M.kwantiel(sorted(nodig), DOEL_DEKKING)
    demping = n_dagen / (n_dagen + SCHAAL_DEMPING)
    schaal = max(SCHAAL_MIN, min(SCHAAL_MAX, 1.0 + (ruw - 1.0) * demping))
    return {"schaal": round(schaal, 3), "schaal_ongedempt": round(ruw, 3), "uren": len(nodig),
            "dagen": n_dagen, "dekking": _dekking(per_k)}


def _dekking(per_k: dict) -> dict:
    return {k: {"uren": n, "dekking_procent": round(100.0 * b / n, 1)}
            for k, (b, n) in sorted(per_k.items()) if n}


# --- gebruik in een plan -------------------------------------------------

def risicowaarden(uur: dict) -> dict:
    """Voorzichtige waarden voor een plan dat verder kijkt dan de bekende prijzen.

    Ontladen (verkopen of zelf gebruiken) in de toekomst telt tegen P30 -
    lager dan de verwachting; laden tegen P70 - hoger. Een plan dat op het
    verschil wacht, wacht dan alleen als het verschil buiten de onzekerheid
    valt. Tussenliggende kwantielen lineair tussen P25/P75 en de verwachting
    (de mediaan); zonder band: de verwachting zelf.
    """
    p = uur.get("prijs_eur")
    p25, p75 = uur.get("p25"), uur.get("p75")
    if p is None or p25 is None or p75 is None:
        return {"ontladen_eur": p, "laden_eur": p, "spreiding_eur": 0.0}
    # P30 ligt op 0,524 sd onder de mediaan; P25 op 0,674 - dus 78% van de weg
    ontladen = p + (p25 - p) * (0.5244 / Z50)
    laden = p + (p75 - p) * (0.5244 / Z50)
    return {"ontladen_eur": round(ontladen, 4), "laden_eur": round(laden, 4),
            "spreiding_eur": round(laden - ontladen, 4)}


def spread_zeker(ontlaad_uur: dict, laad_uur: dict, rendement: float = 0.85) -> float:
    """Wat een verschuiving (laden in het ene uur, ontladen in het andere) per
    kWh opbrengt met de voorzichtige waarden; kleiner of gelijk aan nul =
    het verschil valt binnen de onzekerheid, niet op wachten."""
    return risicowaarden(ontlaad_uur)["ontladen_eur"] * rendement - risicowaarden(laad_uur)["laden_eur"]
