"""De Zendure-accu rechtstreeks meelezen, naast de Zendure-integratie (v5.50).

Stap 1 van "Zendure in het EMS": ALLEEN LEZEN. Gevraagd op 8 oktober,
na een dag waarop de Zendure-integratie bij het hernoemen van entiteiten
vastliep en meldingen gaf over code die in Home Assistant 2027.8 stopt.
Het idee: het EMS praat op termijn zelf met de accu, zonder tussenlaag.
Eerst moet blijken dat wat het EMS zelf leest klopt met wat de
Zendure-integratie laat zien.

Wat deze module doet:

- elke 5 seconden `GET http://<accu>/properties/report` (de lokale
  ZenSDK-API van de SolarFlow, die al aan staat);
- de ruwe waarden omrekenen naar dezelfde eenheden als de
  Zendure-integratie (temperatuur in tiende kelvin, spanning in
  centivolt, stroom in tiende ampère met teken, laadgrenzen in promille);
- per waarde vergelijken met de entiteit van de Zendure-integratie en
  bijhouden hoe vaak ze binnen de marge overeenkomen;
- wat de Zendure-integratie niet laat zien, afgeleid uit hetzelfde
  rapport (idee uit Gielz1986/Zendure-HA-zenSDK): celbalans per module,
  relaisschakelingen per dag (elke wissel laden/ontladen slijt het
  relais), opslagmodus (RAM of flash), kalibratie, foutmelding,
  laad-/ontlaadgrens en het omzetrendement laden en ontladen;
- bij elke duidelijke wijziging (vermogen, limiet, laad-/ontlaadstand)
  meten welke bron hem het eerst ziet en hoeveel seconden eerder: het
  eigen lezen of de Zendure-integratie (die volgt het EMS via
  toestandswijzigingen, dus op de seconde);
- de tellingen bewaren, zodat een herstart ze niet wist.

Wat deze module NOOIT doet: schrijven naar de accu. Geen POST, geen
`properties/write`, geen dienstaanroep. Een broncodetoets bewaakt dat.
De sturing van het EMS leest niets uit deze module.

Het adres van de accu wordt niet ingesteld maar afgeleid, zoals de
Zendure-integratie dat zelf ook doet: `zendure-<model zonder spaties>-<serienummer>.local`,
uit het apparaat in het apparaatregister.
"""
from __future__ import annotations

import logging
import re
import statistics
import time
import unicodedata
from datetime import timedelta
from typing import Any, Callable

_LOGGER = logging.getLogger(__name__)

ZENDURE_DOMEIN = "zendure_ha"
INTERVAL = timedelta(seconds=5)
TIMEOUT_S = 5
OPSLAG_SLEUTEL = "energy_management_system.zendure_lokaal"
OPSLAG_VERSIE = 1
BEWAAR_ELKE_RONDES = 60
# Pas na zoveel vergelijkingen per veld een oordeel.
MIN_VERGELIJKINGEN = 20
# Overeenkomst per veld waarboven het "gelijk" heet.
DREMPEL_GELIJK = 0.95
# Na zoveel mislukte rondes op rij: geen verbinding.
MISLUKT_OP_RIJ_GEEN_VERBINDING = 3
LATENTIE_STEEKPROEF = 200

# veld: (eenheid, omrekening, marge). Omrekening van de ruwe ZenSDK-waarde
# naar wat de Zendure-integratie toont (entity.py, createEntity).


def _getekend(waarde: float, deler: float) -> float:
    """16-bits waarde met teken, zoals de Zendure-sjablonen voor batcur/BatVolt."""
    w = int(waarde)
    if w >= 32768:
        w = (w ^ 0x8000) - 0x8000
    return w / deler


def _kelvin(waarde: float) -> float:
    return round((float(waarde) - 2731) / 10, 1)


def _deel(deler: float) -> Callable[[float], float]:
    return lambda w: float(w) / deler


def _gelijk(w: float) -> float:
    return float(w)


def _vermogensmarge(a: float, b: float) -> float:
    """Vermogens schommelen en worden niet op hetzelfde moment gelezen."""
    return max(25.0, 0.10 * max(abs(a), abs(b)))


APPARAAT_VELDEN: dict[str, tuple[str, Callable[[float], float], Any]] = {
    "electricLevel": ("%", _gelijk, 1.0),
    "outputHomePower": ("W", _gelijk, _vermogensmarge),
    "gridInputPower": ("W", _gelijk, _vermogensmarge),
    "outputPackPower": ("W", _gelijk, _vermogensmarge),
    "packInputPower": ("W", _gelijk, _vermogensmarge),
    "solarInputPower": ("W", _gelijk, _vermogensmarge),
    "inputLimit": ("W", _gelijk, _vermogensmarge),
    "outputLimit": ("W", _gelijk, _vermogensmarge),
    "minSoc": ("%", _deel(10), 0.5),
    "socSet": ("%", _deel(10), 0.5),
    "hyperTmp": ("°C", _kelvin, 1.0),
    "BatVolt": ("V", lambda w: _getekend(w, 100), 0.3),
    "smartMode": ("", _gelijk, 0.0),
    "acMode": ("", _gelijk, 0.0),
    "packNum": ("", _gelijk, 0.0),
}

MODULE_VELDEN: dict[str, tuple[str, Callable[[float], float], Any]] = {
    "socLevel": ("%", _gelijk, 1.0),
    "power": ("W", _gelijk, _vermogensmarge),
    "maxTemp": ("°C", _kelvin, 1.0),
    "totalVol": ("V", _deel(100), 0.3),
    "maxVol": ("V", _deel(100), 0.02),
    "minVol": ("V", _deel(100), 0.02),
    "batcur": ("A", lambda w: _getekend(w, 10), 1.5),
    "state": ("", _gelijk, 0.0),
}

# De Zendure-integratie toont acMode als select met tekst.
AC_MODE_TEKST = {"input": 1.0, "output": 2.0}


def snakecase(waarde: str) -> str:
    """Zoals de Zendure-integratie unique_ids maakt (entity.py, snakecase)."""
    waarde = unicodedata.normalize("NFKD", waarde).encode("ascii", "ignore").decode("ascii")
    waarde = waarde.replace("+", "_plus")
    waarde = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", waarde)
    waarde = re.sub(r"[^a-z0-9]", "_", waarde.lower())
    return re.sub(r"_+", "_", waarde).strip("_")


def hostnaam(model: str | None, serienummer: str | None) -> str | None:
    """`zendure-<model zonder spaties>-<sn>.local`, als de Zendure-integratie."""
    if not model or not serienummer:
        return None
    return f"zendure-{model.replace(' ', '')}-{serienummer}.local"


# --- omrekenen ---------------------------------------------------------------


def _getal(waarde: Any) -> float | None:
    if waarde is None or isinstance(waarde, bool):
        return None
    try:
        return float(waarde)
    except (TypeError, ValueError):
        return None


def normaliseer(rapport: dict) -> dict:
    """Het ruwe ZenSDK-rapport in de eenheden van de Zendure-integratie.

    Uit: {"sn", "apparaat": {veld: waarde}, "modules": {sn: {veld: waarde}}}.
    Onbekende of ontbrekende velden worden weggelaten, niet als 0 gelezen.
    """
    eigenschappen = rapport.get("properties") or {}
    apparaat: dict[str, float] = {}
    for veld, (_eenheid, omreken, _marge) in APPARAAT_VELDEN.items():
        ruw = _getal(eigenschappen.get(veld))
        if ruw is not None:
            apparaat[veld] = round(omreken(ruw), 3)
    modules: dict[str, dict[str, float]] = {}
    for pak in rapport.get("packData") or []:
        sn = pak.get("sn") if isinstance(pak, dict) else None
        if not sn:
            continue
        waarden: dict[str, float] = {}
        for veld, (_eenheid, omreken, _marge) in MODULE_VELDEN.items():
            ruw = _getal(pak.get(veld))
            if ruw is not None:
                waarden[veld] = round(omreken(ruw), 3)
        modules[str(sn)] = waarden
    return {"sn": rapport.get("sn"), "apparaat": apparaat, "modules": modules}


def ha_waarde(veld: str, toestand: str | None) -> float | None:
    """De toestand van een Zendure-entiteit als getal (acMode als tekst)."""
    if toestand is None or toestand in ("unknown", "unavailable", ""):
        return None
    if veld == "acMode":
        return AC_MODE_TEKST.get(str(toestand).lower())
    return _getal(toestand)


def marge_voor(marge: Any, lokaal: float, ha: float) -> float:
    return float(marge(lokaal, ha)) if callable(marge) else float(marge)


def vergelijk(
    lokaal: dict,
    zoek_toestand: Callable[[str | None, str], str | None],
) -> list[dict]:
    """Per veld: lokaal tegen de Zendure-integratie.

    `zoek_toestand(sn_of_None, veld)` geeft de toestand van de
    Zendure-entiteit (None = apparaat, anders het serienummer van de module),
    of None als die entiteit er niet is.
    """
    uit: list[dict] = []

    def _een(sn: str | None, veld: str, waarde: float, marge: Any) -> None:
        ha = ha_waarde(veld, zoek_toestand(sn, veld))
        if ha is None:
            return
        verschil = abs(waarde - ha)
        uit.append({
            "sleutel": veld if sn is None else f"{sn}.{veld}",
            "lokaal": waarde,
            "zendure": ha,
            "verschil": round(verschil, 3),
            "gelijk": verschil <= marge_voor(marge, waarde, ha) + 1e-9,
        })

    for veld, waarde in (lokaal.get("apparaat") or {}).items():
        _een(None, veld, waarde, APPARAAT_VELDEN[veld][2])
    for sn, waarden in (lokaal.get("modules") or {}).items():
        for veld, waarde in waarden.items():
            _een(sn, veld, waarde, MODULE_VELDEN[veld][2])
    return uit


# --- afgeleid: wat de Zendure-integratie niet laat zien -------------------
#
# Overgenomen uit Gielz1986/Zendure-HA-zenSDK (een volledig lokale
# YAML-oplossing op dezelfde API), op verzoek van 8 oktober: "Neem het
# beste uit deze integratie ook mee". Alleen de dingen die iets zeggen over
# de gezondheid van de accu of over wat het sturen kost; hun eigen
# regelmodi en schrijfopdrachten horen bij stap 2, niet hier.

# Celbalans: verschil tussen de hoogste en laagste celspanning in een module.
CELBALANS_GRENZEN_MV = ((20, "uitstekend"), (50, "goed"), (80, "lichte onbalans"))
SOC_LIMIET = {0: "normaal", 16: "normaal", 1: "laadgrens bereikt", 17: "laadgrens bereikt",
              2: "ontlaadgrens bereikt", 18: "ontlaadgrens bereikt"}
RELAIS_STAND = {1: "laden", 2: "ontladen"}
# smartMode bepaalt waar een schrijfopdracht wordt bewaard. 1 = in het
# werkgeheugen (geen slijtage), 0 = in het flashgeheugen (slijt bij elke
# opdracht). Belangrijk voor stap 2: elke regelopdracht hoort smartMode 1
# mee te sturen.
OPSLAGMODUS = {1: "werkgeheugen (RAM)", 0: "flash"}
# Omzetrendement alleen meten bij een duidelijk vermogen en zonder zon,
# anders zegt de verhouding niets.
RENDEMENT_MIN_W = 300
RENDEMENT_STEEKPROEF = 500


def celbalans(max_cv: float | None, min_cv: float | None) -> dict | None:
    if max_cv is None or min_cv is None:
        return None
    verschil_mv = round((max_cv - min_cv) * 10)
    for grens, naam in CELBALANS_GRENZEN_MV:
        if verschil_mv <= grens:
            return {"verschil_mv": verschil_mv, "oordeel": naam}
    return {"verschil_mv": verschil_mv, "oordeel": "onbalans"}


def afgeleid(rapport: dict) -> dict:
    """Gezondheid en toestand uit het ruwe rapport (geen vergelijking)."""
    p = rapport.get("properties") or {}

    def _int(w):
        g = _getal(w)
        return int(g) if g is not None else None

    dc_laden = dc_ontladen = 0.0
    modules = {}
    for pak in rapport.get("packData") or []:
        if not isinstance(pak, dict) or not pak.get("sn"):
            continue
        toestand = _int(pak.get("state"))
        vermogen = _getal(pak.get("power")) or 0.0
        if toestand == 1:
            dc_laden += vermogen
        elif toestand == 2:
            dc_ontladen += vermogen
        modules[str(pak["sn"])] = {
            "celbalans": celbalans(_getal(pak.get("maxVol")), _getal(pak.get("minVol"))),
            "toestand": {0: "rust", 1: "laden", 2: "ontladen"}.get(toestand, toestand),
            "verwarming": bool(_int(pak.get("heatState"))),
        }
    uit = {
        "relais_stand": RELAIS_STAND.get(_int(p.get("acMode")), p.get("acMode")),
        "opslagmodus": OPSLAGMODUS.get(_int(p.get("smartMode")), p.get("smartMode")),
        "kalibreert": _int(p.get("socStatus")) == 1,
        "foutmelding": _int(p.get("is_error")) == 1,
        "storingsniveau": _int(p.get("faultLevel")),
        "soc_limiet": SOC_LIMIET.get(_int(p.get("socLimit")), p.get("socLimit")),
        "dc_laden_w": dc_laden,
        "dc_ontladen_w": dc_ontladen,
        "wifi_dbm": _int(p.get("rssi")),
        "modules": modules,
    }
    # Omzetrendement van dit moment: wisselstroom in -> gelijkstroom in de
    # modules (laden), en gelijkstroom uit de modules -> wisselstroom naar
    # huis (ontladen).
    zon = _getal(p.get("solarInputPower")) or 0.0
    net_in = _getal(p.get("gridInputPower")) or 0.0
    naar_huis = _getal(p.get("outputHomePower")) or 0.0
    if zon == 0 and net_in >= RENDEMENT_MIN_W and dc_laden > 0:
        uit["rendement_laden"] = round(dc_laden / net_in, 3)
    if zon == 0 and naar_huis >= RENDEMENT_MIN_W and dc_ontladen > 0:
        uit["rendement_ontladen"] = round(naar_huis / dc_ontladen, 3)
    return uit


def verwerk_afgeleid(tellingen: dict, afg: dict, nu: float) -> None:
    """Relaisschakelingen per dag en het omzetrendement over de tijd."""
    from datetime import datetime

    dag = datetime.fromtimestamp(nu).date().isoformat()
    relais = tellingen.setdefault("relais", {"dag": dag, "vandaag": 0, "totaal": 0, "stand": None, "per_dag": {}})
    if relais.get("dag") is None:
        relais["dag"] = dag
    if relais.get("dag") != dag:
        relais.setdefault("per_dag", {})[relais["dag"]] = relais.get("vandaag", 0)
        for oud in sorted(relais["per_dag"])[:-14]:
            relais["per_dag"].pop(oud, None)
        relais["dag"], relais["vandaag"] = dag, 0
    stand = afg.get("relais_stand")
    if stand in ("laden", "ontladen"):
        if relais.get("stand") in ("laden", "ontladen") and relais["stand"] != stand:
            relais["vandaag"] += 1
            relais["totaal"] += 1
        relais["stand"] = stand
    rend = tellingen.setdefault("rendement", {"laden": [], "ontladen": []})
    for soort in ("laden", "ontladen"):
        w = afg.get(f"rendement_{soort}")
        if w is not None and 0.5 <= w <= 1.05:
            rend[soort].append(w)
            del rend[soort][:-RENDEMENT_STEEKPROEF]


def rendement_samenvatting(tellingen: dict) -> dict:
    rend = tellingen.get("rendement") or {}
    uit = {}
    for soort in ("laden", "ontladen"):
        reeks = rend.get(soort) or []
        uit[soort] = {"mediaan": round(statistics.median(reeks), 3), "n": len(reeks)} if reeks else None
    if uit.get("laden") and uit.get("ontladen"):
        uit["retour"] = round(uit["laden"]["mediaan"] * uit["ontladen"]["mediaan"], 3)
    return uit


# --- reactiesnelheid: wie ziet een wijziging het eerst? ---------------------
#
# Gevraagd op 8 oktober: "Ik wil eigenlijk ook zien welke er sneller
# reageert". Per veld: zodra een bron een duidelijke sprong ziet, opent er
# een wijziging; zodra de andere bron dezelfde waarde laat zien, sluit hij
# met de voorsprong in seconden. De Zendure-integratie wordt gevolgd via
# toestandswijzigingen (tijdstempel van Home Assistant), het eigen lezen per
# ronde - de resolutie daarvan is het leesinterval.

REACTIE_VELDEN = ("gridInputPower", "outputPackPower", "packInputPower", "outputHomePower",
                  "inputLimit", "outputLimit", "acMode")
REACTIE_MIN_SPRONG_W = 150.0
REACTIE_MAX_WACHT_S = 60.0
REACTIE_LAATSTE = 20
REACTIE_STEEKPROEF = 300
BRONNEN = ("lokaal", "zendure")


def _sprong(veld: str, oud: float | None, nieuw: float) -> bool:
    if oud is None:
        return False
    if veld == "acMode":
        return oud != nieuw
    return abs(nieuw - oud) >= max(REACTIE_MIN_SPRONG_W, 0.15 * max(abs(oud), abs(nieuw)))


def _zelfde(veld: str, a: float | None, b: float) -> bool:
    if a is None:
        return False
    if veld == "acMode":
        return a == b
    return abs(a - b) <= max(50.0, 0.10 * max(abs(a), abs(b)))


def lege_reactie() -> dict:
    return {"laatst": {}, "open": {}, "eerst": {"lokaal": 0, "zendure": 0}, "niet_gevolgd": 0,
            "voorsprong": {"lokaal": [], "zendure": []}, "recent": []}


def reactie_waarneming(r: dict, bron: str, veld: str, waarde: float | None, t: float) -> None:
    """Eén waarneming van een bron. Opent of sluit een wijziging."""
    if waarde is None or veld not in REACTIE_VELDEN or bron not in BRONNEN:
        return
    ander = "zendure" if bron == "lokaal" else "lokaal"
    laatst = r.setdefault("laatst", {}).setdefault(veld, {})
    open_ = r.setdefault("open", {})
    # verlopen wijzigingen opruimen
    for v in [v for v, w in open_.items() if t - w["t"] > REACTIE_MAX_WACHT_S]:
        open_.pop(v)
        r["niet_gevolgd"] = r.get("niet_gevolgd", 0) + 1
    w = open_.get(veld)
    if w is not None and w["bron"] == ander and _zelfde(veld, w["waarde"], waarde):
        voorsprong = round(max(0.0, t - w["t"]), 1)
        r["eerst"][ander] = r["eerst"].get(ander, 0) + 1
        reeks = r["voorsprong"].setdefault(ander, [])
        reeks.append(voorsprong)
        del reeks[:-REACTIE_STEEKPROEF]
        r["recent"].append({"veld": veld, "eerst": ander, "voorsprong_s": voorsprong,
                            "waarde": waarde, "t": round(t)})
        del r["recent"][:-REACTIE_LAATSTE]
        open_.pop(veld)
    elif _sprong(veld, laatst.get(bron), waarde) and not _zelfde(veld, laatst.get(ander), waarde):
        open_[veld] = {"bron": bron, "waarde": waarde, "t": t}
    laatst[bron] = waarde


def zonder_lopende_wijzigingen(vergelijking: list[dict], r: dict, nu: float) -> list[dict]:
    """Niet vergelijken wat net verspringt (v5.50).

    Loopt er een wijziging die de andere bron nog niet heeft gezien, dan
    meet een vergelijking alleen het tijdsverschil - dat meet de
    reactiesnelheid al. Bij een lopende vermogenssprong geldt dat ook voor
    het vermogen en de stroom per module.
    """
    lopend = {v for v, w in (r.get("open") or {}).items() if nu - w["t"] <= REACTIE_MAX_WACHT_S}
    if not lopend:
        return vergelijking
    vermogen = bool(lopend - {"acMode"})
    uit = []
    for regel in vergelijking:
        veld = regel["sleutel"].rsplit(".", 1)[-1]
        if "." not in regel["sleutel"] and veld in lopend:
            continue
        if "." in regel["sleutel"] and vermogen and veld in ("power", "batcur"):
            continue
        uit.append(regel)
    return uit


def reactie_samenvatting(r: dict, interval_s: float) -> dict:
    eerst = r.get("eerst") or {}
    totaal = sum(eerst.values())
    uit = {"wijzigingen": totaal, "niet_gevolgd": r.get("niet_gevolgd", 0),
           "resolutie_lokaal_s": interval_s}
    for bron in BRONNEN:
        reeks = (r.get("voorsprong") or {}).get(bron) or []
        uit[bron] = {
            "eerst": eerst.get(bron, 0),
            "aandeel_procent": round(100 * eerst.get(bron, 0) / totaal, 1) if totaal else None,
            "mediaan_voorsprong_s": round(statistics.median(reeks), 1) if reeks else None,
        }
    if totaal:
        winnaar = max(BRONNEN, key=lambda b: eerst.get(b, 0))
        uit["sneller"] = winnaar if eerst.get(winnaar, 0) * 2 > totaal else "gelijk op"
    else:
        uit["sneller"] = None
    uit["recent"] = list(r.get("recent") or [])[-5:]
    return uit


# --- tellingen ---------------------------------------------------------------


def lege_tellingen() -> dict:
    return {
        "rondes": 0,
        "gelukt": 0,
        "mislukt": 0,
        "mislukt_op_rij": 0,
        "laatste_fout": None,
        "laatste_gelukt": None,
        "velden": {},
        "latentie_ms": [],
        "sinds": None,
        "relais": {"dag": None, "vandaag": 0, "totaal": 0, "stand": None, "per_dag": {}},
        "rendement": {"laden": [], "ontladen": []},
        "reactie": lege_reactie(),
    }


def verwerk_ronde(tellingen: dict, vergelijking: list[dict], nu: float, latentie_ms: float) -> None:
    tellingen["rondes"] += 1
    tellingen["gelukt"] += 1
    tellingen["mislukt_op_rij"] = 0
    tellingen["laatste_gelukt"] = nu
    if tellingen.get("sinds") is None:
        tellingen["sinds"] = nu
    reeks = tellingen.setdefault("latentie_ms", [])
    reeks.append(round(latentie_ms, 1))
    del reeks[:-LATENTIE_STEEKPROEF]
    for regel in vergelijking:
        v = tellingen["velden"].setdefault(
            regel["sleutel"], {"n": 0, "gelijk": 0, "max_verschil": 0.0}
        )
        v["n"] += 1
        v["gelijk"] += 1 if regel["gelijk"] else 0
        v["max_verschil"] = max(float(v.get("max_verschil") or 0.0), regel["verschil"])
        v["laatst"] = {"lokaal": regel["lokaal"], "zendure": regel["zendure"]}


def verwerk_fout(tellingen: dict, fout: str, nu: float) -> None:
    tellingen["rondes"] += 1
    tellingen["mislukt"] += 1
    tellingen["mislukt_op_rij"] += 1
    tellingen["laatste_fout"] = {"wanneer": nu, "fout": fout[:200]}


def oordeel(tellingen: dict) -> str:
    """verzamelt / gelijk / wijkt af / geen verbinding / niet gevonden."""
    if tellingen.get("niet_gevonden"):
        return "niet gevonden"
    if tellingen.get("mislukt_op_rij", 0) >= MISLUKT_OP_RIJ_GEEN_VERBINDING:
        return "geen verbinding"
    velden = tellingen.get("velden") or {}
    rijp = {k: v for k, v in velden.items() if v.get("n", 0) >= MIN_VERGELIJKINGEN}
    if not rijp:
        return "verzamelt"
    if all(v["gelijk"] / v["n"] >= DREMPEL_GELIJK for v in rijp.values()):
        return "gelijk"
    return "wijkt af"


def _tijd(ts: Any) -> str | None:
    if not isinstance(ts, (int, float)):
        return None
    from datetime import datetime

    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def samenvatting(tellingen: dict, host: str | None) -> dict:
    velden = tellingen.get("velden") or {}
    afwijkend = sorted(
        (
            {
                "veld": k,
                "overeenkomst_procent": round(100 * v["gelijk"] / v["n"], 1),
                "n": v["n"],
                "max_verschil": v.get("max_verschil"),
                "laatst": v.get("laatst"),
            }
            for k, v in velden.items()
            if v.get("n", 0) >= MIN_VERGELIJKINGEN and v["gelijk"] / v["n"] < DREMPEL_GELIJK
        ),
        key=lambda r: r["overeenkomst_procent"],
    )
    totaal_n = sum(v.get("n", 0) for v in velden.values())
    totaal_gelijk = sum(v.get("gelijk", 0) for v in velden.values())
    lat = list(tellingen.get("latentie_ms") or [])
    lat_s = sorted(lat)
    return {
        "modus": "alleen lezen - stuurt niets",
        "adres": host,
        "rondes": tellingen.get("rondes", 0),
        "gelukt": tellingen.get("gelukt", 0),
        "mislukt": tellingen.get("mislukt", 0),
        "sinds": _tijd(tellingen.get("sinds")),
        "laatste_gelukt": _tijd(tellingen.get("laatste_gelukt")),
        "laatste_fout": (
            {**tellingen["laatste_fout"], "wanneer": _tijd(tellingen["laatste_fout"].get("wanneer"))}
            if isinstance(tellingen.get("laatste_fout"), dict) else None
        ),
        "velden_vergeleken": len(velden),
        "overeenkomst_totaal_procent": round(100 * totaal_gelijk / totaal_n, 1) if totaal_n else None,
        "afwijkende_velden": afwijkend,
        "latentie_mediaan_ms": round(statistics.median(lat), 0) if lat else None,
        "latentie_p90_ms": lat_s[int(0.9 * (len(lat_s) - 1))] if lat_s else None,
        "per_veld": {
            k: {
                "overeenkomst_procent": round(100 * v["gelijk"] / v["n"], 1) if v.get("n") else None,
                "n": v.get("n", 0),
                "max_verschil": v.get("max_verschil"),
            }
            for k, v in sorted(velden.items())
        },
    }


def _procent(r: dict | None) -> str:
    return f"{r['mediaan'] * 100:.1f}%".replace(".", ",") if r else "-"


def tekst(status: str, a: dict) -> str:
    """De Proefstand-kaart als markdown; het dashboard rekent zelf niets."""
    accu = a.get("accu") or {}
    relais = a.get("relaisschakelingen") or {}
    rend = a.get("omzetrendement") or {}
    gelijk = a.get("overeenkomst_totaal_procent")
    regels = [
        f"**{status}** · {('-' if gelijk is None else str(gelijk).replace('.', ','))}% gelijk "
        f"met de Zendure-integratie · {a.get('rondes', 0)} rondes · "
        f"latentie {a.get('latentie_mediaan_ms') or '-'} ms",
    ]
    if accu:
        extra = ""
        if accu.get("kalibreert"):
            extra += " · kalibreert"
        if accu.get("foutmelding"):
            extra += " · **foutmelding (zie Zendure-app)**"
        regels.append(
            f"Relais: {accu.get('relais_stand', '-')} · {relais.get('vandaag', 0)} wissels vandaag"
            f" · opslag {accu.get('opslagmodus', '-')} · {accu.get('soc_limiet', '-')}{extra}"
        )
        regels.append(
            f"Omzetrendement laden {_procent(rend.get('laden'))} · ontladen {_procent(rend.get('ontladen'))}"
        )
        for sn, m in (accu.get("modules") or {}).items():
            cb = m.get("celbalans") or {}
            regels.append(
                f"Module …{sn[-5:]}: {m.get('toestand', '-')}, celbalans "
                f"{cb.get('verschil_mv', '-')} mV ({cb.get('oordeel', '-')})"
            )
    reactie = a.get("reactiesnelheid") or {}
    if reactie.get("wijzigingen"):
        lok, zen = reactie.get("lokaal") or {}, reactie.get("zendure") or {}

        def _s(w):
            return "-" if w is None else f"{w:.1f}".replace(".", ",")

        oordeel_tekst = {"lokaal": "het EMS zelf", "zendure": "de Zendure-integratie"}.get(
            reactie.get("sneller"), "gelijk op")
        regels.append(
            f"Sneller: **{oordeel_tekst}** · {reactie['wijzigingen']} wijzigingen · "
            f"EMS eerst {lok.get('eerst', 0)}× (mediaan {_s(lok.get('mediaan_voorsprong_s'))} s voor) · "
            f"Zendure eerst {zen.get('eerst', 0)}× (mediaan {_s(zen.get('mediaan_voorsprong_s'))} s voor)"
        )
    for v in a.get("afwijkende_velden") or []:
        laatst = v.get("laatst") or {}
        regels.append(
            f"⚠️ {v['veld']}: {str(v['overeenkomst_procent']).replace('.', ',')}% gelijk "
            f"(lokaal {laatst.get('lokaal')}, Zendure {laatst.get('zendure')})"
        )
    fout = a.get("laatste_fout")
    if status == "geen verbinding" and fout:
        regels.append(f"Laatste fout: {fout.get('fout')}")
    return "\n\n".join(regels)


# --- Home Assistant ----------------------------------------------------------


class ZendureLokaalMeelezer:
    """Leest de accu elke 5 s zelf uit en vergelijkt. Schrijft nooit."""

    def __init__(self, hass) -> None:
        self._hass = hass
        self._afmelden: Callable[[], None] | None = None
        self._opslag = None
        self.tellingen: dict = lege_tellingen()
        self.host: str | None = None
        self.apparaat_sn: str | None = None
        self.laatste: dict | None = None
        self.afgeleid: dict | None = None
        self._luisteraar: Callable[[], None] | None = None
        self._entiteiten: dict[tuple[str | None, str], str] = {}

    # adres en entiteiten uit de registers ---------------------------------

    def _zoek_apparaat(self) -> bool:
        from homeassistant.helpers import device_registry as dr

        dreg = dr.async_get(self._hass)
        omvormer = None
        sn_naar_apparaat: dict[str, Any] = {}
        for apparaat in dreg.devices.values():
            for domein, ident in apparaat.identifiers:
                if domein != ZENDURE_DOMEIN:
                    continue
                sn_naar_apparaat[str(ident)] = apparaat
                if omvormer is None and "solarflow" in str(apparaat.model or "").lower() and apparaat.serial_number:
                    omvormer = apparaat
        if omvormer is None:
            return False
        self.apparaat_sn = omvormer.serial_number
        self.host = hostnaam(omvormer.model, omvormer.serial_number)

        self._entiteiten = {}
        omv = self._entiteiten_van(omvormer)
        for veld in APPARAAT_VELDEN:
            eid = next((e for u, e in omv.items() if u.endswith("_" + snakecase(veld))), None)
            if eid:
                self._entiteiten[(None, veld)] = eid
        self._sn_naar_apparaat = sn_naar_apparaat
        return True

    def _entiteiten_van(self, apparaat) -> dict[str, str]:
        """unique_id -> entity_id van de Zendure-entiteiten van één apparaat."""
        from homeassistant.helpers import entity_registry as er

        ereg = er.async_get(self._hass)
        uit = {}
        for ent in er.async_entries_for_device(ereg, apparaat.id, include_disabled_entities=False):
            if ent.platform == ZENDURE_DOMEIN and ent.unique_id:
                uit[str(ent.unique_id)] = ent.entity_id
        return uit

    def _module_entiteit(self, sn: str, veld: str) -> str | None:
        sleutel = (sn, veld)
        if sleutel in self._entiteiten:
            return self._entiteiten[sleutel]
        apparaat = getattr(self, "_sn_naar_apparaat", {}).get(sn)
        if apparaat is None:
            return None
        for u, e in self._entiteiten_van(apparaat).items():
            for v in MODULE_VELDEN:
                if u.endswith("_" + snakecase(v)):
                    self._entiteiten[(sn, v)] = e
        return self._entiteiten.get(sleutel)

    def _zoek_toestand(self, sn: str | None, veld: str) -> str | None:
        eid = self._entiteiten.get((None, veld)) if sn is None else self._module_entiteit(sn, veld)
        if not eid:
            return None
        st = self._hass.states.get(eid)
        return st.state if st is not None else None

    # levenscyclus ----------------------------------------------------------

    async def async_start(self) -> None:
        from homeassistant.helpers.event import async_track_time_interval
        from homeassistant.helpers.storage import Store

        self._opslag = Store(self._hass, OPSLAG_VERSIE, OPSLAG_SLEUTEL)
        try:
            bewaard = await self._opslag.async_load()
        except Exception as err:  # noqa: BLE001 - meelezen mag het EMS niet raken
            _LOGGER.debug("Zendure-meelezen: opslag niet te lezen: %s", err)
            bewaard = None
        if isinstance(bewaard, dict):
            basis = lege_tellingen()
            basis.update({k: v for k, v in bewaard.items() if k in basis})
            basis["mislukt_op_rij"] = 0
            self.tellingen = basis
        self._afmelden = async_track_time_interval(self._hass, self._ronde, INTERVAL)

    def _volg_zendure(self) -> None:
        """Toestandswijzigingen van de Zendure-entiteiten volgen (alleen luisteren)."""
        from homeassistant.helpers.event import async_track_state_change_event

        per_entiteit = {
            self._entiteiten[(None, veld)]: veld
            for veld in REACTIE_VELDEN
            if (None, veld) in self._entiteiten
        }
        if not per_entiteit:
            return

        def _gewijzigd(event) -> None:
            nieuw = event.data.get("new_state")
            veld = per_entiteit.get(event.data.get("entity_id"))
            if nieuw is None or veld is None:
                return
            try:
                t = event.time_fired.timestamp()
            except AttributeError:
                t = time.time()
            reactie_waarneming(
                self.tellingen.setdefault("reactie", lege_reactie()),
                "zendure", veld, ha_waarde(veld, nieuw.state), t,
            )

        self._luisteraar = async_track_state_change_event(self._hass, list(per_entiteit), _gewijzigd)

    async def async_stop(self) -> None:
        afmelden, self._afmelden = self._afmelden, None
        if afmelden is not None:
            afmelden()
        luisteraar, self._luisteraar = self._luisteraar, None
        if luisteraar is not None:
            luisteraar()
        await self._bewaar()

    async def _bewaar(self) -> None:
        if self._opslag is None:
            return
        try:
            await self._opslag.async_save(self.tellingen)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Zendure-meelezen: opslaan mislukt: %s", err)

    async def _ronde(self, _nu=None) -> None:
        """Eén leesronde. Vangt alles af: dit mag nooit het EMS raken."""
        try:
            await self._ronde_binnen()
        except Exception as err:  # noqa: BLE001
            verwerk_fout(self.tellingen, f"{type(err).__name__}: {err}", time.time())
        if self.tellingen["rondes"] % BEWAAR_ELKE_RONDES == 0:
            await self._bewaar()

    async def _ronde_binnen(self) -> None:
        import asyncio
        import json

        from homeassistant.helpers.aiohttp_client import async_get_clientsession

        if self.host is None and not self._zoek_apparaat():
            self.tellingen["niet_gevonden"] = True
            return
        if self._luisteraar is None:
            self._volg_zendure()
        self.tellingen.pop("niet_gevonden", None)
        sessie = async_get_clientsession(self._hass)
        begin = time.monotonic()
        async with asyncio.timeout(TIMEOUT_S):
            antwoord = await sessie.get(f"http://{self.host}/properties/report")
            tekst = await antwoord.text()
        latentie = (time.monotonic() - begin) * 1000
        rapport = json.loads(tekst)
        if not isinstance(rapport, dict) or "properties" not in rapport:
            raise ValueError("geen ZenSDK-rapport")
        lokaal = normaliseer(rapport)
        self.laatste = lokaal
        nu = time.time()
        r = self.tellingen.setdefault("reactie", lege_reactie())
        verwerk_ronde(self.tellingen, zonder_lopende_wijzigingen(
            vergelijk(lokaal, self._zoek_toestand), r, nu), nu, latentie)
        self.afgeleid = afgeleid(rapport)
        verwerk_afgeleid(self.tellingen, self.afgeleid, nu)
        for veld in REACTIE_VELDEN:
            reactie_waarneming(r, "lokaal", veld, lokaal["apparaat"].get(veld), nu)

    # weergave --------------------------------------------------------------

    def status(self) -> str:
        return oordeel(self.tellingen)

    def attributen(self) -> dict:
        uit = samenvatting(self.tellingen, self.host)
        uit["laatste_lezing"] = self.laatste
        uit["accu"] = self.afgeleid
        relais = self.tellingen.get("relais") or {}
        uit["relaisschakelingen"] = {
            "vandaag": relais.get("vandaag", 0),
            "totaal": relais.get("totaal", 0),
            "per_dag": relais.get("per_dag", {}),
        }
        uit["omzetrendement"] = rendement_samenvatting(self.tellingen)
        uit["reactiesnelheid"] = reactie_samenvatting(
            self.tellingen.get("reactie") or {}, INTERVAL.total_seconds()
        )
        uit["tekst"] = tekst(self.status(), uit)
        return uit
