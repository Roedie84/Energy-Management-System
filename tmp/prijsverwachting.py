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
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Amsterdam")

#: Drie punten voor het landelijke weer: wind op zee, midden, noorden.
PUNTEN = ((52.6, 4.0), (52.1, 5.2), (53.2, 6.6))
OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
    "&hourly=wind_speed_100m,shortwave_radiation,temperature_2m"
    "&past_days={verleden}&forecast_days={vooruit}&timezone=UTC"
)
VERLEDEN_DAGEN = 92
VOORUIT_DAGEN = 4
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
        lat=",".join(str(p[0]) for p in PUNTEN),
        lon=",".join(str(p[1]) for p in PUNTEN),
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


def _lokaal(sleutel: str) -> datetime:
    return datetime.strptime(sleutel, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc).astimezone(TZ)


def niveau_voor(prijzen: dict, dag: date) -> float | None:
    """Gemiddelde prijs van de zeven dagen vóór `dag` (lokaal)."""
    begin = dag - timedelta(days=NIVEAU_DAGEN)
    waarden = [p for s, p in prijzen.items() if begin <= _lokaal(s).date() < dag]
    return statistics.fmean(waarden) if len(waarden) >= 24 * 3 else None


def kenmerken(sleutel: str, weer: dict, niveau: float) -> list[float] | None:
    w = weer.get(sleutel)
    if w is None or niveau is None:
        return None
    lok = _lokaal(sleutel)
    wind = w["wind"] / 10.0
    rij = [1.0, wind, wind * wind, w["zon"] / 100.0, w["temp"] / 10.0,
           1.0 if lok.weekday() >= 5 else 0.0, niveau * 10.0]
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
        for i in range(n):
            ri = rij[i]
            if ri == 0.0:
                continue
            xty[i] += ri * y
            xi = xtx[i]
            for j in range(n):
                xi[j] += ri * rij[j]
    for i in range(1, n):
        xtx[i][i] += ridge
    return _los_op(xtx, xty)


def voorspel_rij(coefs: list[float], rij: list[float]) -> float:
    return sum(c * x for c, x in zip(coefs, rij))


def dataset(prijzen: dict, weer: dict, tot: date | None = None) -> tuple[list, list]:
    """Rijen en doelen voor alle uren met prijs, weer en niveau (vóór `tot`)."""
    niveaus: dict = {}
    rijen, doelen = [], []
    for sleutel in sorted(prijzen):
        dag = _lokaal(sleutel).date()
        if tot is not None and dag >= tot:
            continue
        if dag not in niveaus:
            niveaus[dag] = niveau_voor(prijzen, dag)
        rij = kenmerken(sleutel, weer, niveaus[dag])
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


def verwacht_dag(coefs: list[float], weer: dict, prijzen: dict, dag: date) -> dict | None:
    """Per lokaal uur de verwachte prijs van `dag`, plus een samenvatting.

    Het niveau komt uit de bekende prijzen vóór `dag`; ontbreken de dagen
    vlak ervoor (overmorgen), dan het laatste niveau dat te bepalen is.
    """
    niveau = None
    for terug in range(0, 4):
        niveau = niveau_voor(prijzen, dag - timedelta(days=terug))
        if niveau is not None:
            break
    if niveau is None:
        return None
    uren = []
    for sleutel in uren_van_dag(dag):
        rij = kenmerken(sleutel, weer, niveau)
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


def backtest(prijzen: dict, weer: dict, dagen: int = 21, vooruit: int = 2) -> dict:
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
        rijen, doelen = dataset(bekend, weer)
        if len(rijen) < MIN_UREN:
            continue
        coefs = fit(rijen, doelen)
        if coefs is None:
            continue
        v = verwacht_dag(coefs, weer, bekend, dag)
        n = naief(bekend, dag)
        echt = {s: p for s, p in prijzen.items() if _lokaal(s).date() == dag}
        if not v or not n:
            continue
        mv, mn = vergelijk(v, echt), vergelijk(n, echt)
        if mv and mn:
            uitkomsten.append({"model": mv, "naief": mn})
    return beoordeel(uitkomsten)


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
