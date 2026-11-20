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

#: v5.248.0: integraties waaraan een omvormer, thuisaccu of laadpaal te herkennen is.
#: Bewust een lijst van integraties: `device_class: battery` hebben ook alle
#: batterijsensoren van deurcontacten en afstandsbedieningen.
OMVORMER_PLATFORMS = frozenset({
    "solaredge", "solaredge_modbus_multi", "solaredge_modbus", "enphase_envoy", "growatt_server", "goodwe",
    "fronius", "sma", "solax", "solax_modbus", "huawei_solar", "solis", "apsystems", "hoymiles", "opendtu",
    "omnik_inverter", "solarman", "deye", "sungrow", "kostal_plenticore", "froeling",
})
ACCU_PLATFORMS = frozenset({
    "zendure_ha", "zendure", "powerwall", "tesla_powerwall", "sonnen", "sonnenbatterie", "victron", "victron_ble",
    "marstek", "marstek_local", "anker_solix", "ecoflow", "ecoflow_cloud", "byd_battery_box", "pylontech",
    "homewizard_battery", "sessy", "huawei_luna",
})
LAADPAAL_PLATFORMS = frozenset({
    "easee", "wallbox", "zaptec", "alfen_wallbox", "alfen", "goecharger", "go_e", "ocpp", "tesla_wall_connector",
    "myenergi", "v2c", "keba", "peblar", "ohme", "evbox", "shell_recharge", "easee_hass",
})
#: v5.248.0: zoveel rondes achter elkaar weg voordat een ingesteld apparaat als verdwenen telt.
VERDWENEN_RONDES = 3

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
    platform = str(regel.get("platform") or "")
    # v5.248.0: eerst de drie die de sturing en het plan raken.
    if platform in LAADPAAL_PLATFORMS and (domein in ("switch", "number", "select") or klasse in ("power", "energy")):
        return ("laadpaal", VOORSTEL,
                "Een laadpaal verandert het verbruik en het plan. Het EMS doet er niets mee tot het is afgesproken; zeg het in de chat.")
    if platform in OMVORMER_PLATFORMS and domein == "sensor" and klasse in ("power", "energy"):
        return ("omvormer of zonnepanelen", VOORSTEL,
                "Extra opwek telt nog niet mee in de zonverwachting en het plan. Zeg het in de chat, dan wordt hij ingesteld.")
    if platform in ACCU_PLATFORMS and domein == "sensor" and klasse in ("battery", "power", "energy"):
        return ("thuisaccu", VOORSTEL,
                "Een tweede accu stuurt het EMS niet vanzelf aan; capaciteit en plan veranderen. Zeg het in de chat.")
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


def ingestelde_entiteiten(config: dict) -> dict[str, str]:
    """Elke entiteit die in de instellingen staat, met de instelling waarin (v5.248.0)."""
    uit: dict[str, str] = {}
    for sleutel, waarde in (config or {}).items():
        for w in (waarde if isinstance(waarde, (list, tuple)) else [waarde]):
            if isinstance(w, str) and re.match(r"^[a-z_]+\.[a-z0-9_]+$", w) and w.split(".")[0] in _DOMEINEN:
                uit.setdefault(w, str(sleutel))
    return uit


_DOMEINEN = frozenset({
    "sensor", "binary_sensor", "switch", "number", "select", "climate", "cover", "light", "weather", "person",
    "remote", "input_boolean", "input_number", "device_tracker", "media_player", "fan", "water_heater",
})


def verdwenen(config: dict, aanwezig, tellers: dict | None) -> tuple[list[dict], dict]:
    """Ingestelde entiteiten die al VERDWENEN_RONDES rondes niet meer bestaan.

    Geeft (bevindingen, nieuwe tellers). Een entiteit die terugkomt, begint
    opnieuw. 'Onbeschikbaar' is geen verdwenen: de entiteit bestaat dan nog.
    """
    aanwezig = set(aanwezig)
    oud = dict(tellers or {})
    nieuw: dict[str, int] = {}
    bevindingen = []
    for e, sleutel in sorted(ingestelde_entiteiten(config).items()):
        if e in aanwezig:
            continue
        nieuw[e] = int(oud.get(e) or 0) + 1
        if nieuw[e] == VERDWENEN_RONDES:
            bevindingen.append({
                "soort": "verdwenen", "naam": e, "actie": "bestaat niet meer",
                "uitleg": f"Staat in de instelling '{sleutel}' maar bestaat niet meer in Home Assistant "
                          "(hernoemd of verwijderd?). Het EMS haalt hem niet zelf weg.",
                "entiteiten": [e]})
    return bevindingen, nieuw


def is_stekker(regel: dict, apparaten_met_meting: set) -> bool:
    """Een schakelaar telt als stekker als hij 'outlet' heet of zijn apparaat vermogen/energie meet (v5.250.0)."""
    if regel.get("device_class") == "outlet":
        return True
    return bool(regel.get("apparaat")) and regel.get("apparaat") in apparaten_met_meting


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
        # v5.248.0: een nieuwe sensor van een apparaat dat er al was, is geen tweede accu of omvormer.
        bekende_apparaten = {r.get("apparaat") for r in inventaris
                             if r.get("apparaat") and str(r.get("entity_id")) in bekend_set}
        ingesteld = {str(config.get(k)) for k in AIRCO_INSTELLINGEN if config.get(k)}
        # v5.250.0: een schakelaar is pas een 'stekker' als zijn apparaat vermogen of energie meet
        # (of hij zichzelf 'outlet' noemt). 19-11 kwam 'Nieuw apparaat gevonden' voor drie
        # instelknoppen 'Beeldherkenning' van de camera's: geen stekker, niets voor het EMS.
        met_meting = {r.get("apparaat") for r in inventaris
                      if r.get("apparaat") and str(r.get("entity_id") or "").startswith("sensor.")
                      and r.get("device_class") in ("power", "energy")}
        for regel in inventaris:
            e = str(regel.get("entity_id") or "")
            if not e or e in bekend_set or e in ingesteld:
                continue
            oordeel = soort_van(regel)
            if oordeel is None:
                continue
            soort, actie, uitleg = oordeel
            if soort == "schakelaar of stekker" and not is_stekker(regel, met_meting):
                continue
            if soort in ("thuisaccu", "omvormer of zonnepanelen", "laadpaal") and regel.get("apparaat") in bekende_apparaten:
                continue
            g = groepen.setdefault((soort, _groepsnaam(regel)), {
                "soort": soort, "naam": _groepsnaam(regel), "actie": actie, "uitleg": uitleg, "entiteiten": []})
            g["entiteiten"].append(e)
        bevindingen.extend(groepen[k] for k in sorted(groepen))
    return {"bevindingen": bevindingen, "bekend": sorted(bekend_set | set(ids)), "eerste_keer": eerste_keer}


# --- antwoorden vanaf de telefoon (v5.249.0) -------------------------------

#: Wat een knop in de melding instelt. Afgesproken met Ruud (19-11): een
#: bewegingssensor telt mee voor aanwezigheid; een deur of raam telt mee voor
#: aanwezigheid of als 'raam bij de airco'. Airco, omvormer, accu en laadpaal
#: krijgen geen knop: die vragen maatwerk.
KEUZES = {
    "aanwezig": ("Telt mee voor aanwezigheid", "presence_motion_sensor_entities"),
    "raam": ("Raam bij de airco", "airco_raam_entities"),
}
KNOPPEN_PER_SOORT = {
    "bewegingssensor": ("aanwezig",),
    "deur- of raamsensor": ("aanwezig", "raam"),
}
ACTIE_VOORVOEGSEL = "EMS_ONTDEKKING_"
AFGEWEZEN = "afgewezen"


def knoppen(regel: dict) -> list[dict]:
    """De knoppen voor een melding over deze bevinding; leeg = geen knoppen."""
    keuzes = KNOPPEN_PER_SOORT.get(str(regel.get("soort")), ())
    if not keuzes or regel.get("actie") != VOORSTEL or regel.get("id") is None:
        return []
    uit = [{"action": f"{ACTIE_VOORVOEGSEL}{regel['id']}_{k}", "title": KEUZES[k][0]} for k in keuzes]
    uit.append({"action": f"{ACTIE_VOORVOEGSEL}{regel['id']}_nee", "title": "Nee"})
    return uit


def lees_actie(tekst: str) -> tuple[int, str] | None:
    """(id, keuze) uit de actie van een knop, of None als hij niet van het EMS is."""
    m = re.match(rf"^{ACTIE_VOORVOEGSEL}(\d+)_(aanwezig|raam|nee)$", str(tekst or ""))
    return (int(m.group(1)), m.group(2)) if m else None


def verwerk_antwoord(log: list | None, config: dict, nummer: int, keuze: str) -> dict:
    """Wat een antwoord betekent: de nieuwe instelling en het bijgewerkte logboek.

    Alleen een bevinding die nog op akkoord wacht en waarvoor deze keuze
    bestaat, verandert iets. Twee keer tikken doet de tweede keer niets.
    """
    uit_log = [dict(r) for r in (log or [])]
    regel = next((r for r in uit_log if r.get("id") == nummer), None)
    if regel is None or regel.get("actie") != VOORSTEL:
        return {"gedaan": False, "reden": "deze melding is al afgehandeld of bestaat niet meer", "log": uit_log}
    if keuze == "nee":
        regel["actie"] = AFGEWEZEN
        return {"gedaan": True, "instelling": {}, "log": uit_log, "tekst": f"{regel.get('naam')}: niet meegenomen."}
    if keuze not in KNOPPEN_PER_SOORT.get(str(regel.get("soort")), ()):
        return {"gedaan": False, "reden": "deze keuze hoort niet bij dit apparaat", "log": uit_log}
    titel, sleutel = KEUZES[keuze]
    toe = [e for e in (regel.get("entiteiten") or []) if str(e).startswith("binary_sensor.")]
    if not toe:
        return {"gedaan": False, "reden": "geen sensor om toe te voegen", "log": uit_log}
    lijst = list(config.get(sleutel) or [])
    for e in toe:
        if e not in lijst:
            lijst.append(e)
    regel["actie"] = f"ingesteld: {titel.lower()}"
    return {"gedaan": True, "instelling": {sleutel: lijst}, "log": uit_log,
            "tekst": f"{regel.get('naam')}: {titel.lower()} ({', '.join(toe)})."}


def log_bij(log: list | None, bevindingen: list[dict], moment: str) -> list[dict]:
    """De bevindingen in het logboek; dezelfde (soort, naam, actie) niet twee keer."""
    uit = [dict(r) for r in (log or [])]
    gezien = {(r.get("soort"), r.get("naam"), r.get("actie")) for r in uit}
    for b in bevindingen:
        sleutel = (b.get("soort"), b.get("naam"), b.get("actie"))
        if sleutel in gezien:
            continue
        gezien.add(sleutel)
        # v5.249.0: een vast nummer, zodat een knop in de melding naar deze regel wijst.
        nummer = max([int(r.get("id") or 0) for r in uit] or [0]) + 1
        uit.append({"id": nummer, "moment": moment, "soort": b.get("soort"), "naam": b.get("naam"), "actie": b.get("actie"),
                    "uitleg": b.get("uitleg"), "entiteiten": list(b.get("entiteiten") or [])[:12]})
    return uit[-MAX_BEVINDINGEN:]


def bericht(nieuw: list[dict]) -> str:
    regels = [f"- {b['naam']} ({b['soort']}): {b['actie']}. {b['uitleg']}" for b in nieuw[:6]]
    if len(nieuw) > 6:
        regels.append(f"- en nog {len(nieuw) - 6}; zie de sensor Systeemstatus of de diagnose.")
    return "\n".join(regels)
