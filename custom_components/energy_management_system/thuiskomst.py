"""Thuiskomst bevestigen: is er écht iemand thuisgekomen? (v5.106.0)

Gemeld 20-10 13:58, met screenshot "Thuis sinds 13:54 · beweging 4 min
geleden": "Waarschijnlijk heeft de hond een rondje door de kamer gelopen,
ik weet zeker dat er niemand thuis is, hoe kunnen we dit borgen?" en
daarna "zo waterdicht mogelijk".

Gemeten: alleen de radar in de woonkamer, 13:53:32-13:53:54 (22 s). Geen
deur, geen andere sensor, tv uit. Eén melding van één sensor zette het
huis op "thuis".

De regel: staat het huis op **weg**, dan telt beweging pas als thuiskomst
als er iets bij komt wat een hond niet kan:

1. **Een deur ging open** (voor-, achter- of binnendeur) in de tien
   minuten ervoor, of gaat nu open. Wie thuiskomt, komt door een deur.
2. **Aanhoudende beweging op meerdere plekken**: samen minstens vijf
   minuten in een kwartier, gezien door minstens twee verschillende
   apparaten. Dit is de vangrand voor wie onterecht als "weg" stond
   (stil aan het werk, geen tv, geen lamp) en dan weer gaat bewegen.
   Eén apparaat telt nooit, hoe lang ook: een hond die voor de radar ligt,
   houdt die radar aan.

Tv, water en licht beslissen in de coordinator zelf (een hond zet geen tv
aan en draait geen kraan open); daar komen twee aanscherpingen bij voor de
weg-stand: water van de vaatwasser of wasmachine telt niet, en een lamp
die door een automatisering aanging ook niet.

Zuiver Python, zonder Home Assistant: los te testen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

#: Zo lang na het openen van een deur geldt beweging als thuiskomst.
DEUR_VENSTER = timedelta(minutes=10)
#: Venster en minimum voor aanhoudende beweging.
AANHOUDEND_VENSTER = timedelta(minutes=15)
AANHOUDEND_MINIMUM = timedelta(minutes=5)
#: Zoveel verschillende apparaten moeten beweging zien.
MIN_APPARATEN = 2
#: Zoveel genegeerde bewegingen worden onthouden (dashboard, diagnostiek).
GENEGEERD_LENGTE = 20

#: Boven dit vermogen draait de vaatwasser of wasmachine (dan is water geen
#: bewijs van aanwezigheid).
APPARAAT_AAN_W = 5.0

#: device_class van een deur- of openingssensor.
DEUR_KLASSEN = frozenset({"door", "garage_door", "opening"})


def is_deur(entity_id: str, device_class: str | None) -> bool:
    """Een deursensor: op device_class, anders op de naam (deur/door)."""
    if device_class in DEUR_KLASSEN:
        return True
    if device_class:
        return False
    naam = entity_id.lower()
    return "deur" in naam or "door" in naam


@dataclass
class _Interval:
    entity_id: str
    apparaat: str
    van: datetime
    tot: datetime | None = None


@dataclass
class ThuiskomstPoort:
    """Houdt bij wat er bewoog terwijl het huis op "weg" stond."""

    intervallen: list[_Interval] = field(default_factory=list)
    laatste_deur: datetime | None = None
    genegeerd: list[dict] = field(default_factory=list)
    #: Waarom de laatste thuiskomst bevestigd werd (voor de tijdlijn).
    laatste_reden: str | None = None

    # -- invoer ---------------------------------------------------------- #

    def deur(self, nu: datetime) -> None:
        self.laatste_deur = nu

    def aan(self, entity_id: str, apparaat: str | None, nu: datetime) -> None:
        if any(i.entity_id == entity_id and i.tot is None for i in self.intervallen):
            return   # staat al aan (vangnet van de tick)
        self.intervallen.append(_Interval(entity_id, apparaat or entity_id, nu))
        self._ruim_op(nu)

    def uit(self, entity_id: str, nu: datetime) -> None:
        for iv in self.intervallen:
            if iv.entity_id == entity_id and iv.tot is None:
                iv.tot = nu

    def wis(self) -> None:
        """Na een bevestigde thuiskomst begint de volgende afwezigheid schoon."""
        self.intervallen.clear()

    # -- oordeel ----------------------------------------------------------- #

    def bevestigd(self, nu: datetime) -> str | None:
        """De reden waarom dit een thuiskomst is, of None."""
        if self.laatste_deur is not None and nu - self.laatste_deur <= DEUR_VENSTER:
            return "deur open"
        totaal, apparaten = self._aanhoudend(nu)
        if apparaten >= MIN_APPARATEN and totaal >= AANHOUDEND_MINIMUM:
            return (f"aanhoudende beweging ({totaal.total_seconds() / 60:.0f} min, "
                    f"{apparaten} plekken)")
        return None

    def noteer_genegeerd(self, naam: str, nu: datetime) -> None:
        vorige = self.genegeerd[0] if self.genegeerd else None
        if vorige and vorige["naam"] == naam and \
                (nu - datetime.fromisoformat(vorige["tijd"])).total_seconds() < 120:
            return   # dezelfde beweging (de tick ziet hem nog aan staan)
        totaal, apparaten = self._aanhoudend(nu)
        self.genegeerd.insert(0, {
            "naam": naam, "tijd": nu.isoformat(),
            "reden": "geen deur open, geen tv/kraan/lamp, te kort of op één plek",
            "beweging_s": round(totaal.total_seconds()), "plekken": apparaten,
        })
        del self.genegeerd[GENEGEERD_LENGTE:]

    def _aanhoudend(self, nu: datetime) -> tuple[timedelta, int]:
        begin = nu - AANHOUDEND_VENSTER
        totaal = timedelta()
        apparaten: set[str] = set()
        for iv in self.intervallen:
            tot = iv.tot or nu
            van = max(iv.van, begin)
            if tot <= van:
                continue
            totaal += tot - van
            apparaten.add(iv.apparaat)
        return totaal, len(apparaten)

    def _ruim_op(self, nu: datetime) -> None:
        grens = nu - AANHOUDEND_VENSTER
        self.intervallen = [i for i in self.intervallen if i.tot is None or i.tot > grens][-200:]

    def export(self) -> dict:
        return {
            "laatste_deur": self.laatste_deur.isoformat() if self.laatste_deur else None,
            "genegeerd": list(self.genegeerd),
        }
