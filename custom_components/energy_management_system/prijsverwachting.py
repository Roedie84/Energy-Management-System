"""Prijsverwachting voor de dagen zonder gepubliceerde prijzen (v5.100).

Gevraagd: "Kunnen we nog zaken verbeteren aan het EMS, denk compleet out of
the box" - en daarna "integreren". De dagprijzen van morgen komen pas rond
13:00; overmorgen is altijd onbekend. Wat het EMS 's nachts of in het weekend
besluit (sparen of niet), hangt daar wel van af.

De Nederlandse stroomprijs volgt grotendeels drie dingen die vooraf goed te
voorspellen zijn: wind (veel wind = goedkoop), zon (middagdal) en het uur en
de dag van de week (vraag). Daarbovenop een niveau dat met de gasprijs
meeschuift; dat volgt uit het gemiddelde van de afgelopen zeven dagen.

Model: lineaire regressie met een kleine ridge-term, in zuiver Python
(normaalvergelijkingen, Gauss-eliminatie). Kenmerken per uur:

    constante, wind, wind², zon, temperatuur, weekend, niveau (7 dagen),
    en het lokale uur als 23 indicatoren.

Gegevens: de uurprijzen uit de statistiek van Home Assistant (de eigen
prijssensor, inclusief belasting - precies wat het EMS betaalt) en het weer
van Open-Meteo (verleden en verwachting, gemiddeld over drie punten: de
Noordzee bij IJmuiden, De Bilt en Groningen).

Alleen meten: dit stuurt niets. Elke dag wordt de verwachting vergeleken
met de echte prijzen zodra die er zijn; pas als de verwachting aantoonbaar
beter is dan de simpele aanname "zoals gisteren", komt hij in aanmerking om
mee te sturen (zie `get_meet_stuurt_niet`).

Zuivere functies, zonder Home Assistant.
"""
from __future__ import annotations

import statistics
from functools import lru_cache
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Amsterdam")

#: Drie punten voor het landelijke weer: wind op zee, midden, noorden.
PUNTEN = ((52.6, 4.0), (52.1, 5.2), (53.2, 6.6))
#: v5.110.0: de buurlanden. Nederland hangt aan dezelfde markt als Duitsland
#: en België; wind in Noord-Duitsland en zon in Zuid-Duitsland zetten de prijs
#: hier net zo goed. Duitse Bocht, Noord-, Midden- en Zuid-Duitsland, België.
BUUR_PUNTEN = ((54.3, 8.0), (53.3, 10.0), (51.0, 10.5), (48.7, 11.0), (50.8, 4.4))
OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
    "&hourly=wind_speed_100m,shortwave_radiation,temperature_2m"
    "&past_days={verleden}&forecast_days={vooruit}&timezone=UTC"
)
VERLEDEN_DAGEN = 92
#: v5.109.0: een week vooruit (gevraagd: "staafdiagram van 7 dagen vooruit").
VOORUIT_DAGEN = 8
#: Zo ver vooruit wordt verwacht (dagen na vandaag).
VERWACHT_DAGEN = 7
#: De kaart en de staat van de sensor blijven bij overmorgen + 1 (zoals v5.100).
KAART_VOORUIT = 3
RIDGE = 0.5
NIVEAU_DAGEN = 7
#: Zo veel uren met prijs en weer minimaal voordat er een model is.
MIN_UREN = 24 * 21
#: Pas na zoveel vergeleken dagen zegt de nauwkeurigheid iets.
MIN_GETOETSTE_DAGEN = 14
#: Zoveel beter dan "zoals gisteren" (gemiddelde afwijking) om rijp te zijn.
RIJP_WINST_PROCENT = 15.0


def open_meteo_url(verleden: int = VERLEDEN_DAGEN, vooruit: int = VOORUIT_DAGEN) -> str:
    return OPEN_METEO_URL.format(
        lat=",".join(str(p[0]) for p in PUNTEN + BUUR_PUNTEN),
        lon=",".join(str(p[1]) for p in PUNTEN + BUUR_PUNTEN),
        verleden=verleden, vooruit=vooruit,
    )


def uur_sleutel(moment: datetime) -> str:
    """Het UTC-uur als sleutel: 'YYYY-MM-DDTHH'."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")


def weer_uit_open_meteo(antwoord) -> dict:
    """Per UTC-uur het gemiddelde over de punten: wind (km/u), zon (W/m²), temp (°C).

    Een uur telt alleen als alle drie de grootheden er voor minstens één
    punt zijn. Onbekend blijft onbekend.
    """
    lijst = antwoord if isinstance(antwoord, list) else [antwoord]
    uit = _weer_gemiddeld(lijst[:len(PUNTEN)])
    # v5.110.0: de buurlanden apart (wind en zon), bij hetzelfde uur
    for sleutel, w in _weer_gemiddeld(lijst[len(PUNTEN):]).items():
        if sleutel in uit:
            uit[sleutel]["wind_buur"] = w["wind"]
            uit[sleutel]["zon_buur"] = w["zon"]
    return uit


def _weer_gemiddeld(lijst: list) -> dict:
    som: dict = {}
    for punt in lijst:
        uurlijks = (punt or {}).get("hourly") or {}
        tijden = uurlijks.get("time") or []
        for i, t in enumerate(tijden):
            sleutel = str(t)[:13]
            rij = som.setdefault(sleutel, {"wind": [], "zon": [], "temp": []})
            for veld, bron in (("wind", "wind_speed_100m"), ("zon", "shortwave_radiation"),
                               ("temp", "temperature_2m")):
                reeks = uurlijks.get(bron) or []
                w = reeks[i] if i < len(reeks) else None
                if isinstance(w, (int, float)):
                    rij[veld].append(float(w))
    uit = {}
    for sleutel, rij in som.items():
        if all(rij[v] for v in ("wind", "zon", "temp")):
            uit[sleutel] = {v: sum(rij[v]) / len(rij[v]) for v in ("wind", "zon", "temp")}
    return uit


@lru_cache(maxsize=16384)
def _lokaal(sleutel: str) -> datetime:
    return datetime.strptime(sleutel, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc).astimezone(TZ)


def niveau_voor(prijzen: dict, dag: date) -> float | None:
    """Gemiddelde prijs van de zeven dagen vóór `dag` (lokaal)."""
    begin = dag - timedelta(days=NIVEAU_DAGEN)
    waarden = [p for s, p in prijzen.items() if begin <= _lokaal(s).date() < dag]
    return statistics.fmean(waarden) if len(waarden) >= 24 * 3 else None


def kenmerken(sleutel: str, weer: dict, niveau: float, gas_delta: float = 0.0) -> list[float] | None:
    w = weer.get(sleutel)
    if w is None or niveau is None:
        return None
    lok = _lokaal(sleutel)
    wind = w["wind"] / 10.0
    # v5.110.0: een feestdag (hier of in Duitsland) telt als weekend; zonder
    # buurlandweer (oud bewaard weer) het Nederlandse; de gassprong in
    # euro per m3 ten opzichte van de week ervoor
    vrij = 1.0 if lok.weekday() >= 5 or vrije_dag(lok.date()) else 0.0
    rij = [1.0, wind, wind * wind, w["zon"] / 100.0, w["temp"] / 10.0,
           vrij, niveau * 10.0,
           w.get("wind_buur", w["wind"]) / 10.0, w.get("zon_buur", w["zon"]) / 100.0,
           (gas_delta or 0.0) * 10.0]
    rij += [1.0 if lok.hour == u else 0.0 for u in range(1, 24)]
    return rij


def _los_op(a: list[list[float]], b: list[float]) -> list[float] | None:
    """Gauss-eliminatie met spilkeuze; None als het stelsel singulier is."""
    n = len(b)
    m = [rij[:] + [b[i]] for i, rij in enumerate(a)]
    for k in range(n):
        spil = max(range(k, n), key=lambda r: abs(m[r][k]))
        if abs(m[spil][k]) < 1e-12:
            return None
        m[k], m[spil] = m[spil], m[k]
        for r in range(k + 1, n):
            f = m[r][k] / m[k][k]
            if f:
                for c in range(k, n + 1):
                    m[r][c] -= f * m[k][c]
    x = [0.0] * n
    for k in range(n - 1, -1, -1):
        x[k] = (m[k][n] - sum(m[k][c] * x[c] for c in range(k + 1, n))) / m[k][k]
    return x


def fit(rijen: list[list[float]], doelen: list[float], ridge: float = RIDGE) -> list[float] | None:
    """Kleinste kwadraten met ridge (niet op de constante)."""
    if not rijen:
        return None
    n = len(rijen[0])
    xtx = [[0.0] * n for _ in range(n)]
    xty = [0.0] * n
    for rij, y in zip(rijen, doelen):
        # de uurindicatoren zijn op één na nul: alleen de niet-nullen tellen
        nz = [(i, x) for i, x in enumerate(rij) if x != 0.0]
        for i, xi in nz:
            xty[i] += xi * y
            rij_i = xtx[i]
            for j, xj in nz:
                rij_i[j] += xi * xj
    for i in range(1, n):
        xtx[i][i] += ridge
    return _los_op(xtx, xty)


def voorspel_rij(coefs: list[float], rij: list[float]) -> float:
    return sum(c * x for c, x in zip(coefs, rij))


def dataset(prijzen: dict, weer: dict, tot: date | None = None, gas: dict | None = None) -> tuple[list, list]:
    """Rijen en doelen voor alle uren met prijs, weer en niveau (vóór `tot`)."""
    niveaus: dict = {}
    rijen, doelen = [], []
    for sleutel in sorted(prijzen):
        dag = _lokaal(sleutel).date()
        if tot is not None and dag >= tot:
            continue
        if dag not in niveaus:
            niveaus[dag] = (niveau_voor(prijzen, dag), gas_sprong(gas, dag))
        rij = kenmerken(sleutel, weer, niveaus[dag][0], niveaus[dag][1])
        if rij is not None:
            rijen.append(rij)
            doelen.append(prijzen[sleutel])
    return rijen, doelen


def uren_van_dag(dag: date) -> list[str]:
    """De UTC-uursleutels van een lokale dag (23, 24 of 25 uur)."""
    begin = datetime.combine(dag, datetime.min.time(), TZ)
    eind = datetime.combine(dag + timedelta(days=1), datetime.min.time(), TZ)
    uit, t = [], begin.astimezone(timezone.utc)
    while t < eind.astimezone(timezone.utc):
        uit.append(t.strftime("%Y-%m-%dT%H"))
        t += timedelta(hours=1)
    return uit


def verwacht_dag(coefs: list[float], weer: dict, prijzen: dict, dag: date,
                 gas: dict | None = None) -> dict | None:
    """Per lokaal uur de verwachte prijs van `dag`, plus een samenvatting.

    Het niveau komt uit de bekende prijzen vóór `dag`; ontbreken de dagen
    vlak ervoor (overmorgen), dan het laatste niveau dat te bepalen is.
    """
    niveau = None
    # v5.100.1: na een herstart kan de laatste week nog dun zijn; het
    # niveau van iets eerder is beter dan geen verwachting
    for terug in range(0, 22):
        niveau = niveau_voor(prijzen, dag - timedelta(days=terug))
        if niveau is not None:
            break
    if niveau is None:
        return None
    uren = []
    sprong = gas_sprong(gas, dag)
    for sleutel in uren_van_dag(dag):
        rij = kenmerken(sleutel, weer, niveau, sprong)
        if rij is None:
            return None
        uren.append({"uur": _lokaal(sleutel).strftime("%H:%M"), "sleutel": sleutel,
                     "prijs_eur": round(voorspel_rij(coefs, rij), 4)})
    return samenvatting(dag, uren)


def samenvatting(dag: date, uren: list[dict]) -> dict:
    prijzen = [u["prijs_eur"] for u in uren]
    avond = [u["prijs_eur"] for u in uren if 17 <= int(u["uur"][:2]) < 22]
    goedkoopst = min(uren, key=lambda u: u["prijs_eur"])
    duurst = max(uren, key=lambda u: u["prijs_eur"])
    return {
        "datum": dag.isoformat(),
        "uren": uren,
        "gemiddeld_eur": round(statistics.fmean(prijzen), 4),
        "avondpiek_eur": round(max(avond), 4) if avond else None,
        "goedkoopste_uur": goedkoopst["uur"],
        "goedkoopste_eur": goedkoopst["prijs_eur"],
        "duurste_uur": duurst["uur"],
        "duurste_eur": duurst["prijs_eur"],
        "spreiding_eur": round(duurst["prijs_eur"] - goedkoopst["prijs_eur"], 4),
    }


def vergelijk(verwacht: dict, echte_prijzen: dict) -> dict | None:
    """Verwachting tegenover de echte uurprijzen van die dag."""
    paren = [(u["prijs_eur"], echte_prijzen[u["sleutel"]]) for u in verwacht.get("uren") or []
             if u.get("sleutel") in echte_prijzen]
    if len(paren) < 20:
        return None
    fout = [abs(v - e) for v, e in paren]
    echt_duurst = max(paren, key=lambda p: p[1])
    volgorde_v = sorted(range(len(paren)), key=lambda i: paren[i][0])
    volgorde_e = sorted(range(len(paren)), key=lambda i: paren[i][1])
    top_v, top_e = set(volgorde_v[-4:]), set(volgorde_e[-4:])
    bodem_v, bodem_e = set(volgorde_v[:4]), set(volgorde_e[:4])
    return {
        "datum": verwacht.get("datum"),
        "gemiddelde_afwijking_eur": round(statistics.fmean(fout), 4),
        "verwacht_gemiddeld_eur": round(statistics.fmean(p[0] for p in paren), 4),
        "echt_gemiddeld_eur": round(statistics.fmean(p[1] for p in paren), 4),
        "echt_duurste_eur": round(echt_duurst[1], 4),
        "duurste_uren_geraakt": len(top_v & top_e),
        "goedkoopste_uren_geraakt": len(bodem_v & bodem_e),
    }


def naief(prijzen: dict, dag: date) -> dict | None:
    """De simpele verwachting: elk uur zoals de laatste bekende dag."""
    for terug in range(1, 4):
        vorige = dag - timedelta(days=terug)
        uren_vorig = {_lokaal(s).hour: prijzen[s] for s in uren_van_dag(vorige) if s in prijzen}
        if len(uren_vorig) >= 20:
            uren = []
            for sleutel in uren_van_dag(dag):
                uur = _lokaal(sleutel).hour
                if uur not in uren_vorig:
                    continue
                uren.append({"uur": f"{uur:02d}:00", "sleutel": sleutel, "prijs_eur": uren_vorig[uur]})
            return samenvatting(dag, uren) if uren else None
    return None


def backtest(prijzen: dict, weer: dict, dagen: int = 21, vooruit: int = 2,
             gas: dict | None = None) -> dict:
    """Voor elk van de laatste `dagen` dagen: trainen op wat er `vooruit`
    dagen eerder bekend was, de dag voorspellen en vergelijken met echt.

    Bekend op het moment van voorspellen (vroeg in dag d - vooruit, vóór
    13:00): de prijzen tot en met dag d - vooruit. Het weer is het
    gemeten/geanalyseerde weer, niet de verwachting van toen; de fout van de
    weersverwachting zit er dus niet in (een eerlijk voorbehoud).
    """
    alle_dagen = sorted({_lokaal(s).date() for s in prijzen})
    uitkomsten = []
    for dag in alle_dagen[-dagen:]:
        bekend_tot = dag - timedelta(days=vooruit - 1)
        bekend = {s: p for s, p in prijzen.items() if _lokaal(s).date() < bekend_tot}
        # het gas tot en met de dag waarop voorspeld werd
        gas_toen = {d: g for d, g in (gas or {}).items() if d < bekend_tot}
        rijen, doelen = dataset(bekend, weer, gas=gas_toen)
        if len(rijen) < MIN_UREN:
            continue
        coefs = fit(rijen, doelen)
        if coefs is None:
            continue
        v = verwacht_dag(coefs, weer, bekend, dag, gas_toen)
        n = naief(bekend, dag)
        echt = {s: p for s, p in prijzen.items() if _lokaal(s).date() == dag}
        if not v or not n:
            continue
        mv, mn = vergelijk(v, echt), vergelijk(n, echt)
        if mv and mn:
            uitkomsten.append({"model": mv, "naief": mn})
    uit = beoordeel(uitkomsten)
    uit["per_dag"] = [dagrij(u) for u in uitkomsten]   # v5.112.0
    return uit


def dagrij(u: dict) -> dict:
    """v5.112.0: één vergeleken dag voor het dashboard, in ct."""
    m, n, r = u["model"], u["naief"], u.get("ruw")
    rij = {
        "datum": m.get("datum"),
        "verwacht_ct": round(m["verwacht_gemiddeld_eur"] * 100, 1),
        "echt_ct": round(m["echt_gemiddeld_eur"] * 100, 1),
        "afwijking_ct": round(m["gemiddelde_afwijking_eur"] * 100, 2),
        "zoals_gisteren_ct": round(n["gemiddelde_afwijking_eur"] * 100, 2),
        "duurste_geraakt": m["duurste_uren_geraakt"],
        "goedkoopste_geraakt": m["goedkoopste_uren_geraakt"],
    }
    if r:
        rij["zonder_bijstelling_ct"] = round(r["gemiddelde_afwijking_eur"] * 100, 2)
    return rij


def beoordeel(uitkomsten: list[dict]) -> dict:
    """Samenvatting van vergeleken dagen: model tegenover 'zoals gisteren'."""
    if not uitkomsten:
        return {"dagen": 0, "rijp": False}
    mae_m = statistics.fmean(u["model"]["gemiddelde_afwijking_eur"] for u in uitkomsten)
    mae_n = statistics.fmean(u["naief"]["gemiddelde_afwijking_eur"] for u in uitkomsten)
    winst = (1 - mae_m / mae_n) * 100 if mae_n > 0 else None
    return {
        "dagen": len(uitkomsten),
        "afwijking_model_ct": round(mae_m * 100, 2),
        "afwijking_zoals_gisteren_ct": round(mae_n * 100, 2),
        "winst_procent": round(winst, 1) if winst is not None else None,
        "duurste_uren_geraakt_van_4": round(statistics.fmean(u["model"]["duurste_uren_geraakt"] for u in uitkomsten), 2),
        "goedkoopste_uren_geraakt_van_4": round(statistics.fmean(u["model"]["goedkoopste_uren_geraakt"] for u in uitkomsten), 2),
        "rijp": bool(len(uitkomsten) >= MIN_GETOETSTE_DAGEN and winst is not None and winst >= RIJP_WINST_PROCENT),
    }


def prijzen_uit_statistiek(rijen: list[dict]) -> dict:
    """Uurgemiddelden uit de HA-statistiek: [{'start': ms of datetime, 'mean': x}]."""
    uit = {}
    for r in rijen or []:
        start, gem = r.get("start"), r.get("mean")
        if gem is None or start is None:
            continue
        if isinstance(start, (int, float)):
            moment = datetime.fromtimestamp(start / 1000 if start > 1e11 else start, tz=timezone.utc)
        elif isinstance(start, datetime):
            moment = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
        else:
            try:
                moment = datetime.fromisoformat(str(start))
            except ValueError:
                continue
        uit[uur_sleutel(moment)] = float(gem)
    return uit


# --- live bijhouden ---------------------------------------------------------

def compact(verwachting: dict | None) -> dict | None:
    """Opslagvorm van een dagverwachting: alleen de uren als [sleutel, prijs]."""
    if not verwachting:
        return None
    return {"datum": verwachting["datum"],
            "uren": [[u["sleutel"], u["prijs_eur"]] for u in verwachting.get("uren") or []]}


def uitpakken(kort: dict | None) -> dict | None:
    if not kort:
        return None
    uren = [{"sleutel": s, "uur": _lokaal(s).strftime("%H:%M"), "prijs_eur": p}
            for s, p in kort.get("uren") or []]
    if not uren:
        return None
    return samenvatting(date.fromisoformat(kort["datum"]), uren)


def archiveer(archief: dict, datum: str, vooruit: int, model: dict | None, zoals_gisteren: dict | None,
              ruw: dict | None = None) -> None:
    """De EERSTE verwachting per datum en vooruitkijktijd bewaren; een latere
    verwachting voor dezelfde dag en dezelfde termijn overschrijft hem niet
    (anders toets je achteraf de beste in plaats van die van toen)."""
    if not model or not zoals_gisteren:
        return
    plek = archief.setdefault(datum, {})
    sleutel = f"d{vooruit}"
    if sleutel not in plek:
        plek[sleutel] = {"model": compact(model), "naief": compact(zoals_gisteren)}
        if ruw is not None:
            plek[sleutel]["ruw"] = compact(ruw)   # v5.112.0: zonder bijstelling


def ruim_archief_op(archief: dict, vandaag: date, dagen: int = 45) -> None:
    grens = (vandaag - timedelta(days=dagen)).isoformat()
    for datum in [d for d in archief if d < grens]:
        archief.pop(datum, None)


def live_beoordeling(archief: dict, prijzen: dict) -> dict:
    """Per vooruitkijktijd: de bewaarde verwachtingen tegenover de echte prijzen."""
    uit = {}
    for sleutel in ("d1", "d2"):
        uitkomsten = []
        for datum in sorted(archief):
            plek = (archief[datum] or {}).get(sleutel)
            if not plek:
                continue
            echt = {s: p for s, p in prijzen.items() if _lokaal(s).date().isoformat() == datum}
            m, n = uitpakken(plek.get("model")), uitpakken(plek.get("naief"))
            if not m or not n or len(echt) < 20:
                continue
            mv, mn = vergelijk(m, echt), vergelijk(n, echt)
            if mv and mn:
                r = uitpakken(plek.get("ruw"))
                uitkomsten.append({"model": mv, "naief": mn, "ruw": vergelijk(r, echt) if r else None})
        uit[sleutel] = beoordeel(uitkomsten)
        uit[sleutel]["laatste"] = uitkomsten[-1]["model"] if uitkomsten else None
        uit[sleutel]["per_dag"] = [dagrij(u) for u in uitkomsten][-14:]
        ruw = [u["ruw"]["gemiddelde_afwijking_eur"] for u in uitkomsten if u.get("ruw")]
        if ruw:
            # hielp de bijstelling? dezelfde dagen, met en zonder
            met = [u["model"]["gemiddelde_afwijking_eur"] for u in uitkomsten if u.get("ruw")]
            uit[sleutel]["bijgesteld_dagen"] = len(ruw)
            uit[sleutel]["zonder_bijstelling_ct"] = round(statistics.fmean(ruw) * 100, 2)
            uit[sleutel]["met_bijstelling_ct"] = round(statistics.fmean(met) * 100, 2)
    return uit


# --- bijstellen op de eigen fout (v5.112.0) -----------------------------
#
# Gevraagd 20-10: "en ook terug rekenen". Zat de verwachting de laatste week
# structureel te laag of te hoog op een deel van de dag, dan schuift de
# volgende verwachting dat deel op. Per blok van drie uur, per termijn
# (morgen, overmorgen; verder dan dat als overmorgen), gemeten op de
# verwachting ZONDER bijstelling - anders stuurt de bijstelling zichzelf bij.
# Afgezwakt bij weinig dagen (n / (n + 3)) en hooguit 5 ct.

BIJSTEL_DAGEN = 7
BIJSTEL_MAX_EUR = 0.05
BIJSTEL_DEMPING = 3


def bijstelling(archief: dict, prijzen: dict, vooruit: int, vandaag: date) -> dict:
    """Gemiddelde fout (echt - verwacht) per blok van drie uur, lokaal."""
    sleutel = f"d{min(max(vooruit, 1), 2)}"
    per_blok: dict = {}
    dagen = 0
    for dag in range(1, BIJSTEL_DAGEN + 1):
        datum = (vandaag - timedelta(days=dag)).isoformat()
        plek = (archief.get(datum) or {}).get(sleutel) or {}
        kort = plek.get("ruw") or plek.get("model")
        if not kort:
            continue
        paren = [(s, p, prijzen[s]) for s, p in kort.get("uren") or [] if s in prijzen]
        if len(paren) < 20:
            continue
        dagen += 1
        for s, v, e in paren:
            per_blok.setdefault(_lokaal(s).hour // 3, []).append(e - v)
    if not dagen:
        return {"dagen": 0, "blokken_ct": [0.0] * 8}
    demping = dagen / (dagen + BIJSTEL_DEMPING)
    blokken = []
    for b in range(8):
        f = statistics.fmean(per_blok[b]) * demping if per_blok.get(b) else 0.0
        blokken.append(max(-BIJSTEL_MAX_EUR, min(BIJSTEL_MAX_EUR, f)))
    return {"dagen": dagen, "blokken_ct": [round(f * 100, 2) for f in blokken],
            "gemiddeld_ct": round(statistics.fmean(blokken) * 100, 2)}


def pas_bijstelling_toe(model: dict | None, bij: dict | None) -> dict | None:
    if not model or not bij or not bij.get("dagen"):
        return model
    blokken = bij["blokken_ct"]
    uren = [{**u, "prijs_eur": round(u["prijs_eur"] + blokken[int(u["uur"][:2]) // 3] / 100, 4)}
            for u in model.get("uren") or []]
    return samenvatting(date.fromisoformat(model["datum"]), uren)


def stel_bij(dagen: dict, archief: dict, prijzen: dict, vandaag: date) -> dict:
    """Stelt elke verwachte dag bij (model), met het origineel als `ruw`."""
    bij = {v: bijstelling(archief, prijzen, v, vandaag) for v in (1, 2)}
    # nog niets voor overmorgen gemeten: die van morgen
    gebruik = {1: bij[1], 2: bij[2] if bij[2].get("dagen") else bij[1]}
    for d in (dagen or {}).values():
        if d.get("model") and "ruw" not in d:
            d["ruw"] = d["model"]
            d["model"] = pas_bijstelling_toe(d["model"], gebruik[min(max(d.get("vooruit") or 1, 1), 2)])
    return {"d1": bij[1], "d2": bij[2]}


def uurprijzen_uit_kwartieren(kwartieren) -> dict:
    """Uurgemiddelden uit (begin, prijs_eur)-paren; alleen volledige uren."""
    per_uur: dict = {}
    for begin, prijs in kwartieren:
        if prijs is None:
            continue
        per_uur.setdefault(uur_sleutel(begin), []).append(float(prijs))
    return {s: sum(v) / len(v) for s, v in per_uur.items() if len(v) >= 4}


# --- per kwartier (v5.108.0) -------------------------------------------
#
# Gevraagd 20-10: "Graag maar wel per kwartier, ik heb immers kwartierprijzen".
# Het model rekent per uur (wind, zon en vraag bewegen niet per kwartier). Het
# kwartierpatroon binnen een uur is wel vast: de vier kwartieren van een uur
# lopen in de ochtend op en in de avond af. Dat patroon komt uit de bekende
# kwartierprijzen van de afgelopen weken, per lokaal uur en kwartier; het
# uurgemiddelde van de verwachting blijft daarbij precies gelijk.

#: Zoveel volle uren moet een (uur, kwartier) minstens hebben om mee te tellen.
KWARTIER_MIN_UREN = 5


def kwartiervorm(kwartieren) -> dict:
    """Gemiddelde afwijking van elk kwartier tot zijn uurgemiddelde.

    Sleutel "HH:k" (lokaal uur, kwartier 0-3), waarde in euro. Alleen volle
    uren tellen; een vak met te weinig uren telt als 0.
    """
    per_uur: dict = {}
    for begin, prijs in kwartieren:
        if prijs is None or begin is None:
            continue
        lok = begin.astimezone(TZ)
        per_uur.setdefault(uur_sleutel(begin), {})[lok.minute // 15] = (lok.hour, float(prijs))
    vakken: dict = {}
    for kw in per_uur.values():
        if len(kw) != 4:
            continue
        gem = sum(p for _u, p in kw.values()) / 4
        for k, (uur, p) in kw.items():
            vakken.setdefault(f"{uur:02d}:{k}", []).append(p - gem)
    return {s: round(statistics.fmean(v), 5) for s, v in vakken.items() if len(v) >= KWARTIER_MIN_UREN}


def kwartieren_van_dag(model: dict | None, vorm: dict | None) -> list[tuple[datetime, float]]:
    """De uurverwachting van een dag als kwartieren, met het kwartierpatroon."""
    uit = []
    for u in (model or {}).get("uren") or []:
        begin = datetime.strptime(u["sleutel"], "%Y-%m-%dT%H").replace(tzinfo=timezone.utc)
        uur = begin.astimezone(TZ).hour
        delta = [float((vorm or {}).get(f"{uur:02d}:{k}", 0.0)) for k in range(4)]
        midden = sum(delta) / 4
        uit += [(begin + timedelta(minutes=15 * k), u["prijs_eur"] + delta[k] - midden) for k in range(4)]
    return uit


def kwartierreeks(bekend, verwacht, vanaf: datetime) -> dict | None:
    """Eén doorlopende reeks per kwartier: eerst bekend, dan verwacht.

    `bekend` en `verwacht` zijn (begin, prijs_eur)-paren. Een kwartier met een
    bekende prijs wint altijd. Uit: start (ISO), stap in minuten, prijzen in
    ct (None bij een gat) en de index waar de verwachting begint.
    """
    vanaf = vanaf.astimezone(timezone.utc).replace(second=0, microsecond=0)
    vanaf -= timedelta(minutes=vanaf.minute % 15)
    punten: dict = {}
    for begin, prijs in verwacht or []:
        if prijs is not None:
            punten[begin.astimezone(timezone.utc)] = (float(prijs), True)
    for begin, prijs in bekend or []:
        if prijs is not None:
            punten[begin.astimezone(timezone.utc)] = (float(prijs), False)
    punten = {t: v for t, v in punten.items() if t >= vanaf}
    if not punten:
        return None
    eind = max(punten)
    ct, eerste_verwacht, t, i = [], None, vanaf, 0
    while t <= eind:
        p = punten.get(t)
        ct.append(round(p[0] * 100, 2) if p else None)
        if p and p[1] and eerste_verwacht is None:
            eerste_verwacht = i
        t += timedelta(minutes=15)
        i += 1
    return {"start": vanaf.isoformat(), "stap_min": 15, "ct": ct, "verwacht_vanaf": eerste_verwacht}


# --- feestdagen en gas (v5.110.0) ---------------------------------------
#
# Gevraagd 20-10: "Meenemen buurlanden, feestdagen en plotselinge sprongen in
# de gasprijzen".

def _pasen(jaar: int) -> date:
    """Paaszondag (gregoriaans, anonieme methode)."""
    a, b, c = jaar % 19, jaar // 100, jaar % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    maand = (h + l - 7 * m + 114) // 31
    dag = (h + l - 7 * m + 114) % 31 + 1
    return date(jaar, maand, dag)


@lru_cache(maxsize=64)
def feestdagen(jaar: int) -> frozenset:
    """Landelijke vrije dagen in Nederland en Duitsland (dezelfde markt).

    Nederland: Nieuwjaar, tweede paasdag, Koningsdag (26 april als de 27e een
    zondag is), Bevrijdingsdag in een lustrumjaar, Hemelvaart, tweede
    pinksterdag, beide kerstdagen. Duitsland daarnaast: Goede Vrijdag,
    1 mei en 3 oktober.
    """
    p = _pasen(jaar)
    koning = date(jaar, 4, 27)
    if koning.weekday() == 6:
        koning = date(jaar, 4, 26)
    dagen = {
        date(jaar, 1, 1), p - timedelta(days=2), p + timedelta(days=1), koning,
        date(jaar, 5, 1), p + timedelta(days=39), p + timedelta(days=50),
        date(jaar, 10, 3), date(jaar, 12, 25), date(jaar, 12, 26),
    }
    if jaar % 5 == 0:
        dagen.add(date(jaar, 5, 5))
    return frozenset(dagen)


def vrije_dag(dag: date) -> bool:
    return dag in feestdagen(dag.year)


#: De gassprong: de gasprijs van de dag tegen het gemiddelde van zoveel dagen ervoor.
GAS_DAGEN = 7


def gas_sprong(gas: dict | None, dag: date) -> float:
    """Hoeveel de gasprijs (euro/m3) van `dag` boven of onder die van de
    week ervoor ligt. Het prijsniveau van de afgelopen week volgt het gas
    pas na dagen; een sprong zit hier meteen in. Voor een dag in de toekomst
    geldt de laatst bekende gasprijs. Zonder gegevens: 0.
    """
    if not gas:
        return 0.0
    bekend = sorted(d for d in gas if d <= dag)
    if not bekend:
        return 0.0
    nu = gas[bekend[-1]]
    week = [gas[d] for d in bekend if dag - timedelta(days=GAS_DAGEN) <= d < dag]
    if not week:
        return 0.0
    return nu - statistics.fmean(week)


def gas_uit_statistiek(rijen: list[dict]) -> dict:
    """Gasprijs per lokale dag uit de uurstatistiek van de gasprijssensor.

    De gasdag loopt van 06:00 tot 06:00; daarom tellen de uren van 06:00 tot
    middernacht voor de datum.
    """
    per_dag: dict = {}
    for r in rijen or []:
        waarde = r.get("mean")
        start = r.get("start")
        if not isinstance(waarde, (int, float)) or start is None:
            continue
        if isinstance(start, (int, float)):
            moment = datetime.fromtimestamp(start / 1000 if start > 1e11 else start, timezone.utc)
        elif isinstance(start, datetime):
            moment = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
        else:
            try:
                moment = datetime.fromisoformat(str(start))
            except ValueError:
                continue
        lok = moment.astimezone(TZ)
        if lok.hour < 6:
            continue
        per_dag.setdefault(lok.date(), []).append(float(waarde))
    return {d: statistics.fmean(v) for d, v in per_dag.items() if v}


def snoei(prijzen: dict, vandaag: date, dagen: int = 130) -> dict:
    grens = uur_sleutel(datetime.combine(vandaag - timedelta(days=dagen), datetime.min.time(), TZ))
    return {s: p for s, p in prijzen.items() if s >= grens}


def maak_verwachting(prijzen: dict, weer: dict, vandaag: date, bekend_tot: date,
                     gas: dict | None = None) -> dict:
    """Train op alles wat bekend is en verwacht de dagen na `bekend_tot`
    (de laatste dag met gepubliceerde prijzen) tot en met zeven dagen vooruit.

    Geeft per datum de verwachting en de 'zoals gisteren'-verwachting, en
    hoeveel dagen vooruit die datum lag (voor het archief).
    """
    rijen, doelen = dataset(prijzen, weer, gas=gas)
    if len(rijen) < MIN_UREN:
        return {"beschikbaar": False, "reden": f"{len(rijen)} uren met prijs en weer, minimaal {MIN_UREN}"}
    coefs = fit(rijen, doelen)
    if coefs is None:
        return {"beschikbaar": False, "reden": "model niet op te lossen"}
    dagen = {}
    dag = bekend_tot + timedelta(days=1)
    while dag <= vandaag + timedelta(days=VERWACHT_DAGEN):
        v = verwacht_dag(coefs, weer, prijzen, dag, gas)
        if v:
            dagen[dag.isoformat()] = {"model": v, "naief": naief(prijzen, dag),
                                      "vooruit": (dag - vandaag).days}
        dag += timedelta(days=1)
    return {
        "beschikbaar": bool(dagen),
        "dagen": dagen,
        "uren_training": len(rijen),
        "gevoeligheid": {
            "wind_ct_per_10_kmh_bij_20_kmh": round((coefs[1] + coefs[2] * (2 * 2 + 1)) * 100, 2),
            "zon_ct_per_100_wm2": round(coefs[3] * 100, 2),
            "weekend_ct": round(coefs[5] * 100, 2),
            "buurlanden_wind_ct_per_10_kmh": round(coefs[7] * 100, 2),
            "buurlanden_zon_ct_per_100_wm2": round(coefs[8] * 100, 2),
            "gas_ct_per_10_ct_m3": round(coefs[9] * 100, 2),
        },
        "gas_dagen": len(gas or {}),
        "reden": None if dagen else (
            "geen prijsniveau: minder dan drie dagen prijzen in de weken ervoor"
            if all(niveau_voor(prijzen, vandaag + timedelta(days=d) - timedelta(days=t)) is None
                   for d in range(1, 4) for t in range(0, 22))
            else "geen weer voor de komende dagen"),
    }


def kaart(dagen: dict, backtest: dict | None, live: dict | None,
          fout: str | None = None, opnieuw_om: str | None = None) -> dict:
    """De teksten voor de dashboardkaart: de verste dag met een verwachting."""
    if not dagen:
        tekst = "nog geen verwachting"
        if fout:
            tekst = "weer (Open-Meteo) niet bereikbaar" if "open-meteo" in fout.lower() else f"mislukt: {fout[:80]}"
            if opnieuw_om:
                tekst += f" - nieuwe poging om {str(opnieuw_om)[11:16]}"
        return {"kaart_primair": "Prijsverwachting", "kaart_secundair": tekst}
    datum = sorted(dagen)[-1]
    d = dagen[datum]
    primair = f"{d['gemiddeld_eur'] * 100:.1f} ct verwacht".replace(".", ",")
    delen = [f"{datum}: duurst {d['duurste_uur']} ({d['duurste_eur'] * 100:.0f} ct), "
             f"goedkoopst {d['goedkoopste_uur']} ({d['goedkoopste_eur'] * 100:.0f} ct)"]
    d2 = (live or {}).get("d2") or {}
    if d2.get("dagen"):
        delen.append(f"live {d2.get('winst_procent')}% beter dan zoals-gisteren over {d2['dagen']} dagen")
    elif (backtest or {}).get("winst_procent") is not None:
        delen.append(f"terugtoets {backtest['winst_procent']}% beter dan zoals-gisteren")
    return {"kaart_primair": primair, "kaart_secundair": " · ".join(delen)}
