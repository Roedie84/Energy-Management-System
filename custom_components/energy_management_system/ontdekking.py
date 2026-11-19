"""Nieuwe apparaten in Home Assistant herkennen (v5.247.0).

Ruud 19-11: "stel ik sluit nu een extra accu, een nieuwe lamp, een extra
airco aan" - het EMS moest dat tot nu toe met de hand verteld worden (de
modulewissel van 7 november ook). Afspraak met Ruud:

    wat alleen GEMETEN wordt, voegt het EMS zelf toe en meldt het;
    wat GESTUURD wordt, vraagt het eerst;
    een schakelaar wordt nooit vanzelf 'schakelbaar' (koelkasten en vriezers).

Dit bestand beslist alleen: wat is er nieuw, van welke soort, en wat hoort
ermee te gebeuren. Het lezen van Home Assistant en het toepassen doet de
coordinator. Zuivere functies.
"""
from __future__ import annotations

import re

#: Een accumodule van Zendure: sensor.ab3000_<nummer>_<veld>.
MODULE_RE = re.compile(r"^sensor\.ab3000_([0-9a-z]+)_(soc_level|max_temp|max_vol|min_vol|power)$")
#: Welk veld in welke instelling van het EMS hoort.
MODULE_INSTELLING = {
    "soc_level": "battery_module_soc_sensor_entities",
    "power": "battery_module_power_sensor_entities",
    "max_temp": "battery_module_temperature_sensor_entities",
    "max_vol": "battery_module_cell_voltage_max_sensor_entities",
    "min_vol": "battery_module_cell_voltage_min_sensor_entities",
}
#: Instellingen waarin een airco al kan staan.
AIRCO_INSTELLINGEN = ("airco_climate_entity", "slaapkamer_climate_entity")
#: Zoveel bevindingen bewaren.
MAX_BEVINDINGEN = 60
EIGEN_PLATFORM = "energy_management_system"

AUTOMATISCH = "automatisch toegevoegd"
VOORSTEL = "wacht op jouw akkoord"
GEMELD = "gemeld, geen instelling nodig"
WACHT = "wacht tot alle sensoren er zijn"


def modules(entity_ids, config: dict) -> list[dict]:
    """De accumodules die in Home Assistant bestaan, met wat het EMS ervan kent."""
    per: dict[str, dict[str, str]] = {}
    for e in entity_ids:
        m = MODULE_RE.match(str(e))
        if m:
            per.setdefault(m.group(1), {})[m.group(2)] = e
    uit = []
    for nummer in sorted(per):
        velden = per[nummer]
        bekend = {veld: e in (config.get(MODULE_INSTELLING[veld]) or []) for veld, e in velden.items()}
        uit.append({
            "nummer": nummer,
            "velden": velden,
            "volledig": set(velden) == set(MODULE_INSTELLING),
            "ingesteld": bool(bekend) and all(bekend.values()) and set(velden) == set(MODULE_INSTELLING),
            "deels_ingesteld": any(bekend.values()),
        })
    return uit


def instellingen_met_modules(config: dict, nieuwe: list[dict]) -> dict:
    """De vijf modulelijsten met de nieuwe modules achteraan (bestaande volgorde blijft)."""
    uit = {}
    for veld, sleutel in MODULE_INSTELLING.items():
        lijst = list(config.get(sleutel) or [])
        for module in nieuwe:
            e = module["velden"].get(veld)
            if e and e not in lijst:
                lijst.append(e)
        uit[sleutel] = lijst
    return uit


def _groepsnaam(regel: dict) -> str:
    return str(regel.get("apparaat") or regel.get("naam") or regel.get("entity_id"))


def soort_van(regel: dict) -> tuple[str, str, str] | None:
    """(soort, actie, uitleg) voor een nieuwe entiteit, of None als hij het EMS niet raakt."""
    e = str(regel.get("entity_id") or "")
    domein = e.split(".")[0]
    klasse = regel.get("device_class")
    if regel.get("platform") == EIGEN_PLATFORM:
        return None
    if MODULE_RE.match(e):
        return None  # modules lopen via `modules()`
    if domein == "climate":
        return ("airco of thermostaat", VOORSTEL,
                "Het EMS stuurt een airco alleen als jij dat wilt (comfort). Zeg het in de chat, dan wordt hij ingesteld.")
    if domein == "sensor" and klasse == "power":
        return ("vermogensmeting", GEMELD, "Telt mee als meetpunt; het EMS schakelt hier niets.")
    if domein == "sensor" and klasse == "energy":
        return ("energiemeter", GEMELD, "Een teller erbij; het EMS schakelt hier niets.")
    if domein == "switch":
        return ("schakelaar of stekker", GEMELD,
                "Wordt nooit vanzelf schakelbaar voor het EMS (koelkasten en vriezers); alleen op jouw verzoek.")
    if domein == "light":
        return ("lamp", GEMELD, "Het EMS stuurt geen lampen; voor groepen, tablet en automatiseringen: meld het in de chat.")
    if domein == "binary_sensor" and klasse in ("door", "window", "opening", "garage_door"):
        return ("deur- of raamsensor", VOORSTEL,
                "Kan meetellen voor 'raam open: airco niet aan' of aanwezigheid; alleen op jouw verzoek.")
    if domein == "binary_sensor" and klasse in ("motion", "occupancy", "presence"):
        return ("bewegingssensor", VOORSTEL, "Kan meetellen voor aanwezigheid; alleen op jouw verzoek.")
    if domein in ("water_heater", "vacuum", "cover"):
        return (domein, GEMELD, "Gezien; het EMS doet er niets mee.")
    return None


def beoordeel(inventaris: list[dict], config: dict, bekend: list | None) -> dict:
    """Wat is er nieuw sinds de vorige keer?

    `bekend` None = eerste keer: alles wat er nu is geldt als bekend (geen
    stortvloed), behalve een accumodule die het EMS nog niet kent - die is
    altijd het melden waard.
    """
    ids = [str(r.get("entity_id")) for r in inventaris if r.get("entity_id")]
    eerste_keer = bekend is None
    bekend_set = set(ids) if eerste_keer else set(bekend)
    bevindingen: list[dict] = []
    for m in modules(ids, config):
        if m["ingesteld"]:
            continue
        if m["volledig"]:
            bevindingen.append({"soort": "accumodule", "naam": f"AB3000 {m['nummer']}", "actie": AUTOMATISCH,
                                "uitleg": "Toegevoegd aan de modulebewaking (laadstand, temperatuur, celspanning, vermogen).",
                                "module": m, "entiteiten": sorted(m["velden"].values())})
        else:
            ontbreekt = sorted(set(MODULE_INSTELLING) - set(m["velden"]))
            bevindingen.append({"soort": "accumodule", "naam": f"AB3000 {m['nummer']}", "actie": WACHT,
                                "uitleg": "Nog niet alle sensoren van deze module bestaan: " + ", ".join(ontbreekt) + ".",
                                "entiteiten": sorted(m["velden"].values())})
    if not eerste_keer:
        groepen: dict[tuple[str, str], dict] = {}
        ingesteld = {str(config.get(k)) for k in AIRCO_INSTELLINGEN if config.get(k)}
        for regel in inventaris:
            e = str(regel.get("entity_id") or "")
            if not e or e in bekend_set or e in ingesteld:
                continue
            oordeel = soort_van(regel)
            if oordeel is None:
                continue
            soort, actie, uitleg = oordeel
            g = groepen.setdefault((soort, _groepsnaam(regel)), {
                "soort": soort, "naam": _groepsnaam(regel), "actie": actie, "uitleg": uitleg, "entiteiten": []})
            g["entiteiten"].append(e)
        bevindingen.extend(groepen[k] for k in sorted(groepen))
    return {"bevindingen": bevindingen, "bekend": sorted(bekend_set | set(ids)), "eerste_keer": eerste_keer}


def log_bij(log: list | None, bevindingen: list[dict], moment: str) -> list[dict]:
    """De bevindingen in het logboek; dezelfde (soort, naam, actie) niet twee keer."""
    uit = [dict(r) for r in (log or [])]
    gezien = {(r.get("soort"), r.get("naam"), r.get("actie")) for r in uit}
    for b in bevindingen:
        sleutel = (b.get("soort"), b.get("naam"), b.get("actie"))
        if sleutel in gezien:
            continue
        gezien.add(sleutel)
        uit.append({"moment": moment, "soort": b.get("soort"), "naam": b.get("naam"), "actie": b.get("actie"),
                    "uitleg": b.get("uitleg"), "entiteiten": list(b.get("entiteiten") or [])[:12]})
    return uit[-MAX_BEVINDINGEN:]


def bericht(nieuw: list[dict]) -> str:
    regels = [f"- {b['naam']} ({b['soort']}): {b['actie']}. {b['uitleg']}" for b in nieuw[:6]]
    if len(nieuw) > 6:
        regels.append(f"- en nog {len(nieuw) - 6}; zie de sensor Systeemstatus of de diagnose.")
    return "\n".join(regels)
