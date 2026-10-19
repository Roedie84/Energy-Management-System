"""Keuzeoordeel: welke keuze was achteraf niet de beste, en waarom (v5.100).

Gevraagd: "het EMS moet zichzelf analyseren, waar betere keuzes te maken,
en ook aangeven wanneer een keuze achteraf niet de beste keuze was."

De nabeschouwing (v3.99.19) zegt per dag hoeveel er gemist is tegenover de
beste planning met kennis achteraf, en in welke kwartieren het verschil zat.
Dat wijst niet aan WELKE KEUZE het kostte: een kWh die om 16:00 te vroeg
werd gebruikt, mist pas om 19:00 - de kwartiervergelijking legt de schuld
dan bij 19:00.

Hier gebeurt het met een waardefunctie. Achterwaarts over de dag:
V[t][s] = de laagste kosten vanaf kwartier t met laadstand s tot het eind
van de dag (zelfde model als `nabeschouwing.beste_planning`: laden alleen
uit overschot, rendement, slijtage, restwaarde tegen de gemiddelde
dagprijs). Voor elk kwartier is dan exact te zeggen wat de keuze van het
EMS kostte, gegeven de laadstand die er op dat moment werkelijk was:

    spijt[t] = kosten van wat het EMS deed + V[t+1][s_echt(t+1)] - V[t][s_echt(t)]

De spijt telt over de dag precies op tot het gemiste bedrag (de V-termen
vallen tegen elkaar weg), en elke euro staat bij de keuze die hem
veroorzaakte. Een keuze is een aaneengesloten reeks kwartieren met
dezelfde reden en stand.

Waarom het misging: als de verwachting (zon, verbruik) op het moment van
de keuze er flink naast zat, is het een VOORSPELLING. Klopte de
verwachting, dan koos een REGEL anders dan achteraf het beste was - daar
valt te verbeteren. Met de hand gestuurde kwartieren worden niet aan het
EMS toegerekend.

Zuivere functies, zonder Home Assistant.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Een keuze die minder kostte dan dit is ruis (afronding, meetfout).
DREMPEL_EUR = 0.10
#: Een regelkeuze die meer kostte dan dit, wordt gemeld.
MELD_EUR = 0.25
#: Een verwachting zat ernaast bij minstens dit verschil, absoluut én relatief.
VOORSPELFOUT_KWH = 0.5
VOORSPELFOUT_RELATIEF = 0.25
STAP_KWH = 0.05


@dataclass
class Kwartier:
    tijd: str                 # "HH:MM" lokaal
    huis_kwh: float
    pv_kwh: float
    prijs_eur: float
    accu_kwh: float           # wat het net van de accu zag: + ontladen, - laden
    reden: str | None = None
    stand: str | None = None


def _model(kwartieren, capaciteit_kwh, bodem_kwh, laad_kw, ontlaad_kw, rendement, stap_kwh):
    n = int(round((capaciteit_kwh - bodem_kwh) / stap_kwh)) + 1
    eta = rendement ** 0.5
    return {
        "n": n,
        "eta": eta,
        "laad_max": int(round(laad_kw * 0.25 * eta / stap_kwh)),
        "ontlaad_max": int(round(ontlaad_kw * 0.25 / stap_kwh)),
        "gem": sum(k.prijs_eur for k in kwartieren) / len(kwartieren),
        "stap": stap_kwh,
    }


def _laadgrens(k: Kwartier, m: dict) -> int:
    overschot = max(0.0, k.pv_kwh - k.huis_kwh)
    return min(m["laad_max"], int(round(overschot * m["eta"] / m["stap"])))


def _kost(k: Kwartier, d: int, m: dict, slijtage: float) -> float:
    """Kosten van één kwartier als de laadstand d stappen verandert."""
    if d > 0:
        accu_net = -(d * m["stap"]) / m["eta"]
        extra = 0.0
    elif d < 0:
        accu_net = (-d * m["stap"]) * m["eta"]
        extra = (-d * m["stap"]) * slijtage
    else:
        accu_net = extra = 0.0
    return (k.huis_kwh - k.pv_kwh - accu_net) * k.prijs_eur + extra


def waardefunctie(kwartieren: list[Kwartier], m: dict, slijtage: float) -> list[list[float]]:
    """V[t][s]: de laagste kosten van kwartier t tot het eind, vanuit stand s."""
    n, stap = m["n"], m["stap"]
    eind = [-(s * stap) * m["gem"] * m["eta"] for s in range(n)]
    v = [eind]
    for k in reversed(kwartieren):
        volgende = v[0]
        grens = _laadgrens(k, m)
        rij = []
        for s in range(n):
            beste = float("inf")
            for d in range(-m["ontlaad_max"], grens + 1):
                s2 = s + d
                if 0 <= s2 < n:
                    w = _kost(k, d, m, slijtage) + volgende[s2]
                    if w < beste:
                        beste = w
            rij.append(beste)
        v.insert(0, rij)
    return v


def _stand(kwh: float, m: dict) -> int:
    return min(m["n"] - 1, max(0, int(round(kwh / m["stap"]))))


def spijt_per_kwartier(
    kwartieren: list[Kwartier],
    *,
    capaciteit_kwh: float,
    begin_kwh: float,
    bodem_kwh: float,
    laad_kw: float,
    ontlaad_kw: float,
    rendement: float,
    slijtage_eur_per_kwh: float = 0.0,
    stap_kwh: float = STAP_KWH,
) -> dict:
    """Per kwartier: wat de keuze van het EMS kostte tegenover de beste keuze
    vanuit de werkelijke laadstand, en wat die beste keuze was."""
    if not kwartieren or capaciteit_kwh - bodem_kwh < 2 * stap_kwh:
        return {"te_becijferen": False, "reden": "geen kwartieren of geen bruikbare capaciteit"}
    m = _model(kwartieren, capaciteit_kwh, bodem_kwh, laad_kw, ontlaad_kw, rendement, stap_kwh)
    v = waardefunctie(kwartieren, m, slijtage_eur_per_kwh)
    s = _stand(begin_kwh - bodem_kwh, m)
    begin_s = s
    regels = []
    for t, k in enumerate(kwartieren):
        # wat er werkelijk in de accu veranderde (opgeslagen kant)
        opgeslagen = -k.accu_kwh / m["eta"] if k.accu_kwh > 0 else -k.accu_kwh * m["eta"]
        s2 = min(m["n"] - 1, max(0, s + int(round(opgeslagen / m["stap"]))))
        eigen = (k.huis_kwh - k.pv_kwh - k.accu_kwh) * k.prijs_eur \
            + max(0.0, -opgeslagen) * slijtage_eur_per_kwh
        spijt = eigen + v[t + 1][s2] - v[t][s]
        grens = _laadgrens(k, m)
        beste_d = min(
            (d for d in range(-m["ontlaad_max"], grens + 1) if 0 <= s + d < m["n"]),
            key=lambda d: _kost(k, d, m, slijtage_eur_per_kwh) + v[t + 1][s + d],
            default=0,
        )
        beste_net = (-beste_d * m["stap"]) * m["eta"] if beste_d < 0 else -(beste_d * m["stap"]) / m["eta"]
        regels.append({
            "tijd": k.tijd, "reden": k.reden, "stand": k.stand, "prijs_eur": k.prijs_eur,
            "werkelijk_kwh": round(k.accu_kwh, 3), "beste_kwh": round(beste_net, 3),
            "spijt_eur": round(spijt, 4),
        })
        s = s2
    return {
        "te_becijferen": True,
        "regels": regels,
        "gemist_eur": round(sum(r["spijt_eur"] for r in regels), 3),
        "beste_kosten_eur": round(v[0][begin_s], 3),
    }


def _richting(werk: float, beste: float) -> str:
    # werk/beste: + ontladen, - laden (wat het net van de accu zag)
    if werk > beste + 0.05:    # wij ontlaadden meer of laadden minder
        return "te veel ontladen" if werk > 0.05 else "te weinig zon opgevangen"
    if beste > werk + 0.05:    # de beste keuze ontlaadde meer of laadde minder
        return "te veel vastgehouden" if beste > 0.05 else "onnodig geladen"
    return "gelijk"


def _kwh_tekst(kwh: float) -> str:
    if kwh > 0.05:
        return f"ontladen {kwh:.2f} kWh".replace(".", ",")
    if kwh < -0.05:
        return f"geladen {-kwh:.2f} kWh".replace(".", ",")
    return "niets"


def _eind(tijd: str) -> str:
    uur, minuut = (int(x) for x in tijd.split(":"))
    totaal = uur * 60 + minuut + 15
    return f"{totaal // 60 % 24:02d}:{totaal % 60:02d}"


def keuzes(regels: list[dict], namen: dict | None = None) -> list[dict]:
    """Aaneengesloten kwartieren met dezelfde reden en stand: één keuze."""
    namen = namen or {}
    uit: list[dict] = []
    for r in regels:
        sleutel = (r.get("reden"), r.get("stand"))
        if uit and uit[-1]["_sleutel"] == sleutel:
            k = uit[-1]
        else:
            k = {"_sleutel": sleutel, "van": r["tijd"], "reden": r.get("reden"), "stand": r.get("stand"),
                 "kwartieren": 0, "werkelijk_kwh": 0.0, "beste_kwh": 0.0, "spijt_eur": 0.0,
                 "prijzen": []}
            uit.append(k)
        k["tot"] = _eind(r["tijd"])
        k["kwartieren"] += 1
        k["werkelijk_kwh"] += r["werkelijk_kwh"]
        k["beste_kwh"] += r["beste_kwh"]
        k["spijt_eur"] += r["spijt_eur"]
        k["prijzen"].append(r["prijs_eur"])
    for k in uit:
        k.pop("_sleutel")
        prijzen = k.pop("prijzen")
        k["prijs_ct"] = round(sum(prijzen) / len(prijzen) * 100, 1)
        k["werkelijk_kwh"] = round(k["werkelijk_kwh"], 2)
        k["beste_kwh"] = round(k["beste_kwh"], 2)
        k["spijt_eur"] = round(k["spijt_eur"], 3)
        k["handmatig"] = str(k.get("reden") or "").startswith("handmatig")
        k["naam"] = namen.get(k.get("reden") or "", k.get("reden") or "onbekend")
        k["richting"] = _richting(k["werkelijk_kwh"], k["beste_kwh"])
        k["niet_de_beste"] = k["spijt_eur"] >= DREMPEL_EUR
    return uit


def oorzaak(verwacht: dict | None, werkelijk: dict) -> dict:
    """Zat de verwachting op het moment van de keuze ernaast?

    `verwacht` en `werkelijk`: {"zon_kwh", "verbruik_kwh"} over dezelfde
    periode (van de keuze tot het eind van de dag).
    """
    if not verwacht:
        return {"oorzaak": "onbekend", "toelichting": "geen verwachting van dat moment bewaard"}
    fouten = []
    for veld, naam in (("zon_kwh", "zon"), ("verbruik_kwh", "verbruik")):
        v, w = verwacht.get(veld), werkelijk.get(veld)
        if v is None or w is None:
            continue
        verschil = w - v
        if abs(verschil) >= VOORSPELFOUT_KWH and abs(verschil) >= VOORSPELFOUT_RELATIEF * max(abs(w), abs(v), 0.1):
            fouten.append(f"{naam} verwacht {v:.1f} kWh, werkelijk {w:.1f} kWh".replace(".", ","))
    if fouten:
        return {"oorzaak": "voorspelling", "toelichting": "; ".join(fouten)}
    return {"oorzaak": "regel", "toelichting": "de verwachting klopte; de regel koos anders dan achteraf het beste was"}


def tekst(k: dict) -> str:
    deel = (
        f"{k['van']}-{k['tot']} {k['naam']}: {_kwh_tekst(k['werkelijk_kwh'])}, "
        f"achteraf beter {_kwh_tekst(k['beste_kwh'])} (gem. {k['prijs_ct']:.1f} ct)"
    )
    return (deel + f" - kostte € {k['spijt_eur']:.2f}").replace(".", ",")


def dagoordeel(datum: str, keuzelijst: list[dict], gemist_eur: float) -> dict:
    """De dag samengevat: alle keuzes, de dure apart, per reden opgeteld."""
    niet_beste = sorted((k for k in keuzelijst if k["niet_de_beste"]), key=lambda k: -k["spijt_eur"])
    per_reden: dict = {}
    for k in keuzelijst:
        if k["handmatig"]:
            continue
        r = per_reden.setdefault(k["naam"], {"keuzes": 0, "niet_de_beste": 0, "spijt_eur": 0.0,
                                             "door_regel_eur": 0.0, "door_voorspelling_eur": 0.0,
                                             "richtingen": {}})
        r["keuzes"] += 1
        if k["spijt_eur"] > 0:
            r["spijt_eur"] += k["spijt_eur"]
        if k["niet_de_beste"]:
            r["niet_de_beste"] += 1
            sleutel = "door_regel_eur" if k.get("oorzaak") == "regel" else (
                "door_voorspelling_eur" if k.get("oorzaak") == "voorspelling" else None)
            if sleutel:
                r[sleutel] += k["spijt_eur"]
            r["richtingen"][k["richting"]] = r["richtingen"].get(k["richting"], 0) + 1
    for r in per_reden.values():
        for veld in ("spijt_eur", "door_regel_eur", "door_voorspelling_eur"):
            r[veld] = round(r[veld], 3)
    return {
        "datum": datum,
        "te_becijferen": True,
        "gemist_eur": round(gemist_eur, 2),
        "keuzes": len(keuzelijst),
        "niet_de_beste": [
            {**{v: k.get(v) for v in ("van", "tot", "naam", "reden", "werkelijk_kwh", "beste_kwh",
                                     "spijt_eur", "richting", "oorzaak", "toelichting", "handmatig")},
             "tekst": tekst(k)}
            for k in niet_beste[:12]
        ],
        "te_melden": [
            tekst(k) + f". {k.get('toelichting', '')}".rstrip(". ") for k in niet_beste
            if k.get("oorzaak") == "regel" and not k["handmatig"] and k["spijt_eur"] >= MELD_EUR
        ],
        "per_reden": per_reden,
    }


def zelfanalyse(dagen: list[dict], laatste: int = 30) -> dict:
    """Over de laatste dagen: welke regels kostten het meest, en hoe.

    Alleen het deel met een goede verwachting ("door_regel") is een
    verbeterpunt van de sturing; het deel door de voorspelling hoort bij de
    zon- en verbruiksvoorspelling.
    """
    bruikbaar = [d for d in dagen if d.get("te_becijferen")][-laatste:]
    if not bruikbaar:
        return {"dagen": 0, "verbeterpunten": [], "toelichting": "nog geen beoordeelde dagen"}
    totaal: dict = {}
    for d in bruikbaar:
        for naam, r in (d.get("per_reden") or {}).items():
            t = totaal.setdefault(naam, {"keuzes": 0, "niet_de_beste": 0, "spijt_eur": 0.0,
                                         "door_regel_eur": 0.0, "door_voorspelling_eur": 0.0,
                                         "richtingen": {}})
            for veld in ("keuzes", "niet_de_beste", "spijt_eur", "door_regel_eur", "door_voorspelling_eur"):
                t[veld] += r.get(veld) or 0
            for richting, n in (r.get("richtingen") or {}).items():
                t["richtingen"][richting] = t["richtingen"].get(richting, 0) + n
    punten = []
    for naam, t in sorted(totaal.items(), key=lambda kv: -kv[1]["door_regel_eur"]):
        if t["door_regel_eur"] < DREMPEL_EUR:
            continue
        meest = max(t["richtingen"].items(), key=lambda kv: kv[1])[0] if t["richtingen"] else None
        punten.append({
            "reden": naam,
            "door_regel_eur": round(t["door_regel_eur"], 2),
            "door_voorspelling_eur": round(t["door_voorspelling_eur"], 2),
            "niet_de_beste": t["niet_de_beste"],
            "keuzes": t["keuzes"],
            "meestal": meest,
            "tekst": (
                f"{naam}: {t['niet_de_beste']} van {t['keuzes']} keuzes achteraf niet de beste, "
                f"€ {t['door_regel_eur']:.2f} met een goede verwachting"
                + (f" - meestal {meest}" if meest else "")
            ).replace(".", ","),
        })
    gemist = sum(d.get("gemist_eur") or 0 for d in bruikbaar)
    regel = sum(t["door_regel_eur"] for t in totaal.values())
    voorspelling = sum(t["door_voorspelling_eur"] for t in totaal.values())
    helft = len(bruikbaar) // 2
    trend = None
    if helft >= 3:
        eerst = sum(d.get("gemist_eur") or 0 for d in bruikbaar[:helft]) / helft
        laatst = sum(d.get("gemist_eur") or 0 for d in bruikbaar[-helft:]) / helft
        trend = {"eerste_helft_per_dag_eur": round(eerst, 2), "tweede_helft_per_dag_eur": round(laatst, 2),
                 "richting": "beter" if laatst < eerst - 0.02 else ("slechter" if laatst > eerst + 0.02 else "gelijk")}
    return {
        "dagen": len(bruikbaar),
        "gemist_eur": round(gemist, 2),
        "door_regel_eur": round(regel, 2),
        "door_voorspelling_eur": round(voorspelling, 2),
        "verbeterpunten": punten[:6],
        "trend": trend,
        "per_reden": {k: {**v, "spijt_eur": round(v["spijt_eur"], 2), "door_regel_eur": round(v["door_regel_eur"], 2),
                          "door_voorspelling_eur": round(v["door_voorspelling_eur"], 2)}
                      for k, v in totaal.items()},
    }


def _eu(x) -> str:
    return f"{x:.2f}".replace(".", ",") if isinstance(x, (int, float)) else "-"


def kaart(gisteren: dict | None, dertig: dict) -> dict:
    """De teksten voor de dashboardkaart, hier en niet in een sjabloon."""
    punten = dertig.get("verbeterpunten") or []
    primair = f"€ {_eu(dertig.get('door_regel_eur') or 0.0)} te verbeteren (30 dagen)"
    delen = ["Zelfanalyse"]
    if gisteren and gisteren.get("te_becijferen"):
        delen.append(f"gisteren gemist € {_eu(gisteren.get('gemist_eur'))}")
    delen.append(punten[0]["tekst"] if punten else "nog geen verbeterpunt")
    regels = []
    for k in (gisteren or {}).get("niet_de_beste") or []:
        extra = f" ({k.get('toelichting')})" if k.get("oorzaak") == "voorspelling" and k.get("toelichting") else ""
        regels.append(f"- {k.get('tekst')} · {k.get('oorzaak') or 'onbekend'}{extra}")
    kop = f"**Achteraf niet de beste keuze ({(gisteren or {}).get('datum') or '-'})**"
    lijst = "\n".join([kop, ""] + (regels[:6] or ["Geen keuze die achteraf meer dan 10 cent kostte."]))
    return {"kaart_primair": primair, "kaart_secundair": " · ".join(delen), "kaart_lijst": lijst}
