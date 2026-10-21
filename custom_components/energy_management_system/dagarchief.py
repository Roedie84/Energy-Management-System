"""Dagarchief: per dag één compacte regel die altijd bewaard blijft (v5.102).

Gevraagd: "Nu wordt data 30 dagen opgeslagen maar is het voor het EMS niet
beter om data altijd op te slaan?" Niet de ruwe recorder - die groeit met
gigabytes. Wel één regel per dag (± 200 bytes, tien jaar ± 0,7 MB), zodat
het EMS seizoenen kan vergelijken: klopte november met vorig jaar november?

Bronnen, van nauwkeurig naar ruw:

    m  meetlog       kwartierenergie uit de tellers (400 dagen in de meetlog)
    s  statistiek    uurwaarden uit de langetermijnstatistiek van HA (voor
                     de dagen van vóór de meetlog; eenmalig gezaaid)

Een dag uit de meetlog vervangt altijd een dag uit de statistiek.

Velden (korte sleutels, uitgeschreven in `uitgeschreven`):

    v  verbruik huis (kWh)          p  zon (kWh)
    i  netafname (kWh)              e  teruglevering (kWh)
    l  accu geladen (kWh)           o  accu ontladen (kWh)
    n  verbruik 's nachts 22-07 (kWh, binnen deze datum)
    pg/pl/ph  prijs gemiddeld / laagste / hoogste (ct/kWh)
    k  kosten onder salderen (€)    kz  kosten zonder accu (€)
    b  wat de accu opleverde: kz - k (€)
    q  blokken met een meting       b_ bron (m/s)
    later aangevuld:
    pv/vv  zon / verbruik verwacht aan het begin van de dag (kWh)
    gm/gr  gemist achteraf / waarvan door een regel (€)
    r27    wat de accu met de regels van 2027 had opgeleverd (€)
    tn     netafname bij een lege accu in de nacht (kWh)
    ov     overschotdag (reserve achteraf te ruim)
    so     laagste laadstand in de ochtend (%)
    t/gd   gemiddelde temperatuur in Nederland (°C) / graaddagen (18 °C)
    vk/vkm/vko  verkocht uit de accu (kWh) / kleinste marge tegen de
           verkoopreserve bij verkoop (kWh) / kwartieren verkocht onder de
           reserve (v5.115.1, L-EMS-027; uit het dagverloop)

Zuivere functies, zonder Home Assistant.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Amsterdam")

#: Na tien jaar valt de oudste dag eraf - een vangnet, geen termijn.
MAX_DAGEN = 3660
#: Een dag uit de meetlog telt vanaf zoveel gemeten kwartieren.
MIN_KWARTIEREN = 80
#: Een dag uit de statistiek telt vanaf zoveel uren.
MIN_UREN = 22
#: Vorig jaar: 364 dagen terug, dan valt de weekdag gelijk.
JAAR_DAGEN = 364
VERGELIJK_DAGEN = 30
GRAADDAG_BASIS = 18.0
#: v5.103.1: omhoog als het zaaien uit de statistiek opnieuw moet.
ZAAI_VERSIE = 2

NAMEN = {
    "v": "verbruik_kwh", "p": "zon_kwh", "i": "netafname_kwh", "e": "teruglevering_kwh",
    "l": "accu_geladen_kwh", "o": "accu_ontladen_kwh", "n": "nacht_kwh",
    "pg": "prijs_gem_ct", "pl": "prijs_laagste_ct", "ph": "prijs_hoogste_ct",
    "k": "kosten_eur", "kz": "kosten_zonder_accu_eur", "b": "accu_opbrengst_eur",
    "q": "blokken", "b_": "bron",
    "pv": "zon_verwacht_kwh", "vv": "verbruik_verwacht_kwh",
    "gm": "gemist_eur", "gr": "gemist_door_regel_eur", "r27": "accu_2027_eur",
    "tn": "tekortnacht_kwh", "ov": "overschotdag", "so": "laagste_soc_ochtend",
    "t": "temp_c", "gd": "graaddagen",
    "vk": "verkocht_kwh", "vkm": "kleinste_verkoopmarge_kwh",
    "vko": "kwartieren_onder_verkoopreserve",
}
BRONNEN = {"m": "meetlog", "s": "statistiek"}
#: Velden die na de meting worden aangevuld en een nieuwe meting overleven.
AANVULLING = ("pv", "vv", "gm", "gr", "r27", "tn", "ov", "so", "t", "gd",
              "vk", "vkm", "vko")


def _r(x, n=2):
    return round(x, n) if x is not None else None


def _vat_samen(blokken: list[dict], minimum: int, bron: str) -> dict | None:
    """Blokken (kwartier of uur) met i, e, p, o, c, h, prijs en het lokale uur."""
    if len(blokken) < minimum:
        return None
    som = {s: sum(b[s] for b in blokken) for s in ("h", "p", "i", "e", "c", "o")}
    nacht = sum(b["h"] for b in blokken if b["uur"] >= 22 or b["uur"] < 7)
    met_prijs = [b for b in blokken if b.get("prijs") is not None]
    regel = {
        "v": _r(som["h"]), "p": _r(som["p"]), "i": _r(som["i"]), "e": _r(som["e"]),
        "l": _r(som["c"]), "o": _r(som["o"]), "n": _r(nacht),
        "q": len(blokken), "b_": bron,
    }
    if met_prijs:
        prijzen = [b["prijs"] for b in met_prijs]
        regel.update(pg=_r(100 * sum(prijzen) / len(prijzen), 1),
                     pl=_r(100 * min(prijzen), 1), ph=_r(100 * max(prijzen), 1))
    # kosten alleen als (bijna) elk blok een prijs had - anders zou een gat
    # als "gratis" tellen
    if len(met_prijs) >= 0.9 * len(blokken):
        k = sum((b["i"] - b["e"]) * b["prijs"] for b in met_prijs)
        kz = sum((b["h"] - b["p"]) * b["prijs"] for b in met_prijs)
        regel.update(k=_r(k), kz=_r(kz), b=_r(kz - k))
    return regel


def dag_uit_kwartieren(kwartieren: list[dict]) -> dict | None:
    """Een dag uit de uitgepakte kwartierregels van de meetlog."""
    blokken = []
    for r in kwartieren:
        if r.get("quality") == "invalid":
            continue
        waarden = [r.get(s) for s in ("grid_import_kwh", "grid_export_kwh", "pv_kwh",
                                      "battery_out_kwh", "battery_in_kwh", "house_kwh")]
        if any(w is None for w in waarden):
            continue
        try:
            uur = datetime.fromisoformat(r["kwartier"]).astimezone(TZ).hour
        except (KeyError, TypeError, ValueError):
            continue
        i, e, p, o, c, h = waarden
        blokken.append({"i": i, "e": e, "p": p, "o": o, "c": c, "h": h, "uur": uur, "prijs": r.get("prijs_eur")})
    return _vat_samen(blokken, MIN_KWARTIEREN, "m")


def dagen_uit_statistiek(uren: dict[str, dict[datetime, float]], prijzen: dict[datetime, float]) -> dict[str, dict]:
    """Dagen uit de uurwaarden van de langetermijnstatistiek.

    `uren`: per teller (grid_import, grid_export, pv, battery_out, battery_in)
    de verandering per uur (kWh), sleutel het begin van het uur. Een teller
    die er niet is (de accu van vóór de accu): 0. Netafname en zon zijn
    verplicht. `prijzen`: het uurgemiddelde van de prijssensor (€/kWh).
    """
    per_dag: dict[str, list] = {}
    imp, exp, pv = (uren.get(t) or {} for t in ("grid_import", "grid_export", "pv"))
    uit_, in_ = uren.get("battery_out") or {}, uren.get("battery_in") or {}
    if bool(uit_) != bool(in_):
        # v5.103.1: alleen ontladen (of alleen laden) telt het huis scheef;
        # dan de accu helemaal weglaten (het verschil is dan alleen het verlies)
        uit_, in_ = {}, {}
    for moment, i in imp.items():
        if moment not in pv:
            continue
        e = exp.get(moment, 0.0)
        p = pv[moment]
        o, c = uit_.get(moment, 0.0), in_.get(moment, 0.0)
        if min(i, e, p, o, c) < 0:
            continue   # een teller die terugliep: geen meting
        lokaal = moment.astimezone(TZ)
        h = i - e + p + o - c
        if h < 0:
            continue
        prijs = prijzen.get(moment)
        if prijs is not None and not 0.0 <= prijs <= 2.0:
            prijs = None   # een ander niveau of een andere eenheid: niet mengen
        per_dag.setdefault(lokaal.date().isoformat(), []).append(
            {"i": i, "e": e, "p": p, "o": o, "c": c, "h": h, "uur": lokaal.hour, "prijs": prijs})
    uit = {}
    for dag, blokken in per_dag.items():
        regel = _vat_samen(blokken, MIN_UREN, "s")
        if regel is not None:
            uit[dag] = regel
    return uit


def leeg() -> dict:
    return {"dagen": {}, "gezaaid": False, "zaai_versie": ZAAI_VERSIE}


def zet(archief: dict, datum: str, regel: dict) -> None:
    """De gemeten waarden van een dag; aanvullingen (verwachting, oordeel,
    weer) blijven staan. Een statistiekdag overschrijft nooit een meetlogdag."""
    dagen = archief.setdefault("dagen", {})
    oud = dagen.get(datum) or {}
    if oud.get("b_") == "m" and regel.get("b_") == "s":
        return
    basis = {k: v for k, v in oud.items() if k not in NAMEN or k in AANVULLING}
    dagen[datum] = {**basis, **regel}
    _snoei(archief)


def vul_aan(archief: dict, datum: str, **velden) -> None:
    """Aanvullingen bij een dag; None laat een bestaande waarde staan."""
    dag = archief.setdefault("dagen", {}).setdefault(datum, {})
    for k, v in velden.items():
        if v is not None:
            dag[k] = v


def verkoop_van_dag(regels: list, minimum: int = MIN_KWARTIEREN) -> dict | None:
    """Verkoop van één dag uit de kwartieren van het dagverloop (v5.115.1, L-EMS-027).

    De harde regel (nooit onder de verkoopreserve verkopen) was alleen te
    toetsen voor vandaag en gisteren (`verkoopkwartieren`); voor 14..19-10 niet
    meer. Nu per dag blijvend in het archief:

        vk   kWh die uit de accu verkocht werd (`export_uit_accu_kwh`)
        vkm  kleinste marge (beschikbaar min verkoopreserve) bij verkoop;
             None als er niet verkocht werd
        vko  kwartieren met verkoop onder de reserve (marge < 0)

    Zelfde selectie als `verkoopkwartieren`: alleen echte verkoop (`verkocht`,
    v5.94); oudere kwartieren zonder die vlag tellen als er een marge bij
    export is. Een dag met minder dan `minimum` kwartieren geeft None: dan
    zou "0 verkocht" niet te onderscheiden zijn van "niet gemeten".
    Alleen meten; stuurt niets.
    """
    rijen = [r for r in regels or [] if isinstance(r, dict)]
    if len(rijen) < minimum:
        return None
    vk, marges, vko = 0.0, [], 0
    for r in rijen:
        if "verkocht" in r:
            if not r.get("verkocht"):
                continue
        elif r.get("marge_bij_export_min_kwh") is None:
            continue
        kwh = r.get("export_uit_accu_kwh")
        if isinstance(kwh, (int, float)) and not isinstance(kwh, bool):
            vk += float(kwh)
        m = r.get("marge_bij_export_min_kwh")
        if isinstance(m, (int, float)) and not isinstance(m, bool):
            marges.append(float(m))
            if m < 0:
                vko += 1
    return {"vk": round(vk, 3), "vkm": round(min(marges), 3) if marges else None, "vko": vko}


def vul_weer(archief: dict, weer: dict[str, dict]) -> int:
    """Gemiddelde temperatuur en graaddagen uit het uurweer (UTC-uursleutels)."""
    per_dag: dict[str, list[float]] = {}
    for sleutel, w in weer.items():
        t = (w or {}).get("temp")
        if t is None:
            continue
        try:
            moment = datetime.strptime(sleutel, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc).astimezone(TZ)
        except ValueError:
            continue
        per_dag.setdefault(moment.date().isoformat(), []).append(t)
    dagen = archief.setdefault("dagen", {})
    gevuld = 0
    for datum, temps in per_dag.items():
        if datum not in dagen or len(temps) < 20:
            continue
        gem = sum(temps) / len(temps)
        dagen[datum]["t"] = round(gem, 1)
        dagen[datum]["gd"] = round(max(0.0, GRAADDAG_BASIS - gem), 1)
        gevuld += 1
    return gevuld


def _snoei(archief: dict) -> None:
    dagen = archief.get("dagen") or {}
    if len(dagen) > MAX_DAGEN:
        for datum in sorted(dagen)[: len(dagen) - MAX_DAGEN]:
            del dagen[datum]


def uitgeschreven(regel: dict) -> dict:
    uit = {NAMEN.get(k, k): v for k, v in regel.items()}
    if "bron" in uit:
        uit["bron"] = BRONNEN.get(uit["bron"], uit["bron"])
    return uit


def _periode(dagen: dict, van: date, tot: date) -> dict:
    """Gemiddelden per dag over de dagen met een meting in [van, tot]."""
    rijen = [r for d, r in dagen.items() if van.isoformat() <= d <= tot.isoformat() and r.get("v") is not None]
    if not rijen:
        return {"dagen": 0}

    def gem(sleutel, n=2):
        w = [r[sleutel] for r in rijen if r.get(sleutel) is not None]
        return round(sum(w) / len(w), n) if w else None

    return {
        "dagen": len(rijen), "van": van.isoformat(), "tot": tot.isoformat(),
        "verbruik_kwh_per_dag": gem("v"), "zon_kwh_per_dag": gem("p"),
        "netafname_kwh_per_dag": gem("i"), "teruglevering_kwh_per_dag": gem("e"),
        "nacht_kwh_per_dag": gem("n"), "kosten_eur_per_dag": gem("k"),
        "accu_opbrengst_eur_per_dag": gem("b"), "prijs_gem_ct": gem("pg", 1),
        "temp_c": gem("t", 1), "graaddagen_per_dag": gem("gd", 1),
    }


def _procent(nu, toen):
    if nu is None or not toen:
        return None
    return round(100.0 * (nu - toen) / toen, 1)


def vergelijking(archief: dict, vandaag: date) -> dict:
    """De laatste dertig dagen tegen dezelfde dagen een jaar eerder."""
    dagen = archief.get("dagen") or {}
    tot = vandaag - timedelta(days=1)
    van = vandaag - timedelta(days=VERGELIJK_DAGEN)
    nu = _periode(dagen, van, tot)
    toen = _periode(dagen, van - timedelta(days=JAAR_DAGEN), tot - timedelta(days=JAAR_DAGEN))
    uit = {"laatste_30_dagen": nu, "jaar_eerder": toen}
    if nu.get("dagen", 0) >= 20 and toen.get("dagen", 0) >= 20:
        uit["verschil_procent"] = {
            "verbruik": _procent(nu["verbruik_kwh_per_dag"], toen["verbruik_kwh_per_dag"]),
            "zon": _procent(nu["zon_kwh_per_dag"], toen["zon_kwh_per_dag"]),
            "netafname": _procent(nu["netafname_kwh_per_dag"], toen["netafname_kwh_per_dag"]),
            "nacht": _procent(nu["nacht_kwh_per_dag"], toen["nacht_kwh_per_dag"]),
        }
        # verbruik per graaddag: kouder weer verklaart een deel van meer verbruik
        if nu.get("graaddagen_per_dag") is not None and toen.get("graaddagen_per_dag") is not None:
            uit["graaddagen_verschil"] = round(nu["graaddagen_per_dag"] - toen["graaddagen_per_dag"], 1)
    return uit


def per_maand(archief: dict, maanden: int = 25) -> dict:
    """Totalen per maand (alleen dagen met een meting), nieuwste laatst."""
    totaal: dict[str, dict] = {}
    for datum, r in sorted((archief.get("dagen") or {}).items()):
        if r.get("v") is None:
            continue
        m = totaal.setdefault(datum[:7], {"dagen": 0})
        m["dagen"] += 1
        for k in ("v", "p", "i", "e", "k", "b"):
            if r.get(k) is not None:
                m[k] = m.get(k, 0.0) + r[k]
    sleutels = sorted(totaal)[-maanden:]
    return {s: uitgeschreven({k: (round(v, 2) if isinstance(v, float) else v) for k, v in totaal[s].items()})
            for s in sleutels}


def _getal(x, n=1):
    return f"{x:.{n}f}".replace(".", ",")


def kaart(archief: dict, verg: dict) -> dict:
    dagen = archief.get("dagen") or {}
    gemeten = sorted(d for d, r in dagen.items() if r.get("v") is not None)
    if not gemeten:
        return {"kaart_primair": "Dagarchief", "kaart_secundair": "nog geen volledige dag"}
    nu = verg.get("laatste_30_dagen") or {}
    toen = verg.get("jaar_eerder") or {}
    verschil = verg.get("verschil_procent") or {}
    if verschil.get("verbruik") is not None:
        teken = "+" if verschil["verbruik"] > 0 else ""
        primair = f"Verbruik {teken}{_getal(verschil['verbruik'])}% t.o.v. vorig jaar"
    else:
        primair = f"{len(gemeten)} dagen bewaard"
    delen = []
    if nu.get("dagen"):
        delen.append(f"30 dagen: {_getal(nu['verbruik_kwh_per_dag'])} kWh/dag verbruik, "
                     f"{_getal(nu['zon_kwh_per_dag'])} kWh zon")
        if nu.get("accu_opbrengst_eur_per_dag") is not None:
            delen.append(f"accu € {_getal(nu['accu_opbrengst_eur_per_dag'], 2)}/dag")
    if toen.get("dagen", 0) >= 20:
        delen.append(f"vorig jaar {_getal(toen['verbruik_kwh_per_dag'])} kWh/dag, "
                     f"{_getal(toen['zon_kwh_per_dag'])} kWh zon")
        if verg.get("graaddagen_verschil") is not None:
            delen.append(f"{_getal(abs(verg['graaddagen_verschil']))} graaddag per dag "
                         f"{'kouder' if verg['graaddagen_verschil'] > 0 else 'warmer'}")
    else:
        delen.append("vorig jaar nog niet in het archief")
    delen.append(f"sinds {gemeten[0]}")
    return {"kaart_primair": primair, "kaart_secundair": " · ".join(delen)}
