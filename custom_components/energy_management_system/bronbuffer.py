"""Buffer voor bronnen die tijdelijk wegvallen (v5.114.0).

Gevraagd 21-10 15:10, na de storing bij Zonneplan: "Kan dit voor meer bronnen
zijn? Als het er niet is is het er niet, maar als het er wel is geweest
tijdelijk in buffer/cache opslaan?"

Wat hier in komt, zijn bronnen waarvan de waarde een tijd GELDIG blijft:
een zonvoorspelling voor vandaag of morgen, een dagtotaal in euro, de
gasprijs van de dag, de CO2-intensiteit. Valt zo'n sensor weg (de dienst
erachter is even plat), dan geldt zijn laatste waarde nog tot hij verloopt:

* ``dag``: tot middernacht van de dag waarop hij gelezen is. Een voorspelling
  voor "morgen" van gisteren is vandaag iets anders, dus nooit langer.
* ``minuten``: zoveel minuten na de laatste lezing (voor een waarde die snel
  veroudert, zoals de rest van de zon vandaag).

Metingen (vermogens, laadstand, meterstanden) komen hier nooit in: een oude
meting is erger dan geen meting, en daar is de eigen terugval voor de accu.

Zuiver Python, zonder Home Assistant: los te testen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

ONBRUIKBAAR = (None, "", "unknown", "unavailable")

#: Alleen deze attributen gaan mee in de buffer (de rest is opmaak).
ATTRIBUTEN = ("detailedForecast", "detailedHourly", "forecast", "unit_of_measurement",
              "device_class", "estimate", "estimate10", "estimate90")


@dataclass
class BufferStaat:
    """Lijkt genoeg op een State van Home Assistant voor de lezers."""

    entity_id: str
    state: str
    attributes: dict
    gelezen: datetime
    uit_buffer: bool = True


@dataclass
class Bronbuffer:
    #: entity_id -> {"state", "attributes", "gelezen" (iso)}
    opslag: dict = field(default_factory=dict)
    #: entity_id -> (soort, minuten) - wordt per lezing uit de configuratie gezet
    regels: dict = field(default_factory=dict)
    #: entity_id -> moment waarop de buffer het overnam (voor melden en tonen)
    in_gebruik: dict = field(default_factory=dict)

    def lees(self, entity_id: str | None, staat, nu: datetime):
        """De echte staat als die bruikbaar is, anders de geldige buffer."""
        if not entity_id:
            return staat
        regel = self.regels.get(entity_id)
        if regel is None:
            return staat
        if staat is not None and getattr(staat, "state", None) not in ONBRUIKBAAR:
            self.opslag[entity_id] = {
                "state": str(staat.state),
                "attributes": {k: v for k, v in (getattr(staat, "attributes", None) or {}).items()
                               if k in ATTRIBUTEN},
                "gelezen": nu.isoformat(),
            }
            self.in_gebruik.pop(entity_id, None)
            return staat
        bewaard = self.opslag.get(entity_id)
        if not bewaard or not self.geldig(regel, bewaard.get("gelezen"), nu):
            self.in_gebruik.pop(entity_id, None)
            return staat
        self.in_gebruik.setdefault(entity_id, nu.isoformat())
        return BufferStaat(entity_id, bewaard["state"], dict(bewaard.get("attributes") or {}),
                           datetime.fromisoformat(bewaard["gelezen"]))

    @staticmethod
    def geldig(regel: tuple, gelezen: str | None, nu: datetime) -> bool:
        try:
            moment = datetime.fromisoformat(str(gelezen))
        except (TypeError, ValueError):
            return False
        if moment.tzinfo is None and nu.tzinfo is not None:
            moment = moment.replace(tzinfo=nu.tzinfo)
        soort, minuten = regel
        if soort == "dag":
            return moment.astimezone(nu.tzinfo).date() == nu.date() if nu.tzinfo else moment.date() == nu.date()
        return timedelta(0) <= nu - moment <= timedelta(minutes=float(minuten or 0))

    def export(self) -> dict:
        return {"opslag": self.opslag}

    def herstel(self, data) -> None:
        if isinstance(data, dict) and isinstance(data.get("opslag"), dict):
            self.opslag = {k: v for k, v in data["opslag"].items() if isinstance(v, dict)}

    def overzicht(self) -> dict:
        """Voor diagnose en dashboard: wat staat er, en wat wordt er gebruikt."""
        return {
            "bronnen": {e: {"regel": f"{r[0]}" + (f" {r[1]} min" if r[0] == "minuten" else ""),
                            "laatst_gelezen": (self.opslag.get(e) or {}).get("gelezen")}
                        for e, r in sorted(self.regels.items())},
            "uit_buffer": dict(self.in_gebruik),
        }
