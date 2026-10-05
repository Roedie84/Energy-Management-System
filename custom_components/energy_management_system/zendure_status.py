"""Ziet de Zendure-integratie de accu als online? (v5.29)

Gemeld op 5 oktober: vanaf 07:10 elke minuut "No devices online, not
possible to start the operation", terwijl de accu in de Zendure-app online
was en lokaal gewoon antwoordde. Oorzaak: de zekeringgroep van de SolarFlow
stond op "unused". De Zendure-integratie zet het apparaat dan op status 3
en behandelt het als offline; elke opdracht van het EMS werd geweigerd.
Het EMS merkte dat niet, want de modus-select zelf bleef beschikbaar.

De Zendure-integratie (device.py, `setStatus`) zet per apparaat een sensor
`connection_status`:

    0   geen verbinding (time-out)          offline
    1   accu kalibreert (socStatus 1)       offline
    2   HEMS aan: de Zendure-cloud stuurt   offline
    3   geen zekeringgroep ("unused")       offline
    10  cloud-MQTT                          online
    11  lokale MQTT                         online
    12  ZenSDK (lokale HTTP-API)            online

`online` is daar `connectionStatus >= 10`, en de manager weigert een
opdracht alleen als ALLE apparaten offline zijn. Deze module spiegelt dat.

Onbekend is geen offline: zonder bruikbare meting zegt dit niets en houdt
het de aansturing niet tegen. Status 0 is wel een meting.
"""
from __future__ import annotations

ZENDURE_ONLINE_VANAF = 10
STATUS_ACHTERVOEGSEL = "_connection_status"

STATUS_REDENEN: dict[int, tuple[str, str]] = {
    0: (
        "geen verbinding: de Zendure-integratie krijgt geen antwoord van de accu",
        "Herlaad de Zendure-integratie; helpt dat niet, herstart de accu.",
    ),
    1: (
        "de accu kalibreert",
        "Dit lost zich vanzelf op zodra de kalibratie klaar is.",
    ),
    2: (
        "HEMS staat aan: de Zendure-cloud stuurt mee",
        "Zet HEMS uit in de Zendure-app.",
    ),
    3: (
        "geen zekeringgroep ingesteld (Fuse Group staat op 'unused')",
        "Kies bij de SolarFlow een zekeringgroep die laden en ontladen niet "
        "begrenst, zoals 'owncircuit' of 'group2400'.",
    ),
}


def object_id(entity_id: str | None) -> str:
    return str(entity_id or "").split(".", 1)[-1]


def is_statusentiteit(entity_id: str | None) -> bool:
    eid = str(entity_id or "")
    return eid.startswith("sensor.") and eid.endswith(STATUS_ACHTERVOEGSEL)


def hoort_bij_accu(entity_id: str, accu_entiteiten: list[str]) -> bool:
    """Hoort deze statussensor bij een van de ingestelde accu-entiteiten?

    `sensor.solarflow_2400_ac_connection_status` hoort bij
    `sensor.solarflow_2400_ac_electric_level`: dezelfde apparaatnaam vooraan.
    """
    voorvoegsel = object_id(entity_id)[: -len(STATUS_ACHTERVOEGSEL)] + "_"
    if voorvoegsel == "_":
        return False
    return any(object_id(e).startswith(voorvoegsel) for e in accu_entiteiten if e)


def lees_status(stand) -> int | None:
    """De status als geheel getal, of None als er geen meting is."""
    if stand is None:
        return None
    if isinstance(stand, (int, float)) and not isinstance(stand, bool):
        return int(stand)
    tekst = str(stand).strip()
    if tekst in ("", "unavailable", "unknown", "none", "None"):
        return None
    try:
        return int(float(tekst))
    except (TypeError, ValueError):
        return None


def reden_van(status: int) -> tuple[str, str]:
    return STATUS_REDENEN.get(
        status,
        (f"status {status}", "Kijk in de Zendure-integratie naar het apparaat."),
    )


def beoordeel(standen: dict[str, object]) -> dict:
    """Oordeel over alle gevonden statussensoren.

    Offline alleen als er minstens één meting is en ALLE metingen onder de
    online-grens liggen - precies de voorwaarde waarop de Zendure-manager
    een opdracht weigert.
    """
    metingen = {
        eid: s for eid, s in ((e, lees_status(v)) for e, v in standen.items())
        if s is not None
    }
    if not metingen:
        return {
            "bekend": False,
            "online": None,
            "status": None,
            "reden": None,
            "oplossing": None,
            "entiteiten": sorted(standen),
        }
    online = any(s >= ZENDURE_ONLINE_VANAF for s in metingen.values())
    if online:
        return {
            "bekend": True,
            "online": True,
            "status": max(metingen.values()),
            "reden": None,
            "oplossing": None,
            "entiteiten": sorted(standen),
        }
    eid, status = sorted(metingen.items())[0]
    reden, oplossing = reden_van(status)
    return {
        "bekend": True,
        "online": False,
        "status": status,
        "entiteit": eid,
        "reden": reden,
        "oplossing": oplossing,
        "entiteiten": sorted(standen),
    }
