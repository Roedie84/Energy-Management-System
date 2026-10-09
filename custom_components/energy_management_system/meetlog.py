"""Meetlog (v5.28): wat het EMS wist, besloot en daarna gebeurde.

Vier soorten gegevens, elk per dag bewaard:

    snapshot     wat het EMS voor de komende uren aannam - write-once
    evaluatie    elke ronde: besluit, stand, actie, schaduw
    kwartier     energie uit tellers per kwartier
    dagrapport   per dag: slijtagevarianten en reservekandidaat

Uit de review: "Een snapshot dat bij een beslissing hoort mag achteraf nooit
worden vervangen, aangepast of verrijkt met een nieuwere forecast." Een
snapshot wordt eenmaal geschreven onder de hash van zijn inhoud. Bestaat het
id al, dan moet de inhoud gelijk zijn; anders is dat een fout, die wordt
geteld en nooit overschreven. Wat een aanroeper terugkrijgt is een kopie.

Bewaren: snapshots en evaluaties 30 dagen, kwartieren en dagrapporten 400
dagen. Harde limiet 25 MB: daarboven verdwijnen eerst de oudste dagen met
snapshots en evaluaties; kwartieren worden nooit door de limiet geraakt.

De opslag zelf is verwisselbaar (`opslag`): in bedrijf de Home Assistant
Store, in de toetsen een woordenboek. Geen Home Assistant in dit bestand.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime, timedelta

SOORTEN = ("snapshot", "evaluatie", "kwartier", "dagrapport")
BEWAREN_DAGEN = {"snapshot": 30, "evaluatie": 30, "kwartier": 400, "dagrapport": 400}
DOOR_LIMIET_TE_WISSEN = ("snapshot", "evaluatie")
LIMIET_BYTES = 25 * 1024 * 1024


class SnapshotConflict(Exception):
    """Zelfde id, andere inhoud - mag nooit overschreven worden."""


def _json(waarde) -> str:
    return json.dumps(waarde, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def snapshot_id(inhoud: dict) -> str:
    """Inhoudshash: gelijke inhoud = zelfde id; elke wijziging = nieuw id."""
    return hashlib.sha1(_json(inhoud).encode("utf-8")).hexdigest()[:12]


class MeetLog:
    def __init__(self, limiet_bytes: int = LIMIET_BYTES) -> None:
        self.limiet_bytes = limiet_bytes
        self._dagen: dict[tuple[str, str], dict] = {}
        self._groottes: dict[tuple[str, str], int] = {}
        self._snapshot_dag: dict[str, str] = {}
        self._gewijzigd: set[tuple[str, str]] = set()
        self.fouten = 0
        self.laatste_fout: str | None = None
        self.door_limiet_gewist: list[str] = []

    # --- schrijven -------------------------------------------------------

    def leg_snapshot_vast(self, inhoud: dict, moment: datetime) -> str:
        """Eenmalig vastleggen; een bestaand id met andere inhoud is een fout."""
        sid = snapshot_id(inhoud)
        dag = self._snapshot_dag.get(sid)
        if dag is not None:
            bestaand = self._dagen.get(("snapshot", dag), {}).get(sid)
            if bestaand is not None and _json(bestaand["inhoud"]) != _json(inhoud):
                raise SnapshotConflict(sid)
            return sid
        sleutel = ("snapshot", moment.date().isoformat())
        regel = {"tijd": moment.isoformat(), "inhoud": copy.deepcopy(inhoud)}
        self._dagen.setdefault(sleutel, {})[sid] = regel
        self._snapshot_dag[sid] = sleutel[1]
        self._groei(sleutel, len(_json(regel)) + 20)
        return sid

    def voeg_toe(self, soort: str, moment: datetime, record: dict) -> None:
        """Een evaluatie, kwartier of dagrapport achteraan toevoegen."""
        if soort not in SOORTEN or soort == "snapshot":
            raise ValueError(soort)
        sleutel = (soort, moment.date().isoformat())
        regel = copy.deepcopy(record)
        self._dagen.setdefault(sleutel, {}).setdefault("regels", []).append(regel)
        self._groei(sleutel, len(_json(regel)) + 2)

    def _groei(self, sleutel, extra: int) -> None:
        self._groottes[sleutel] = self._groottes.get(sleutel, 0) + extra
        self._gewijzigd.add(sleutel)

    # --- lezen (altijd kopieën) ------------------------------------------

    def snapshot(self, sid: str) -> dict | None:
        dag = self._snapshot_dag.get(sid)
        regel = self._dagen.get(("snapshot", dag), {}).get(sid) if dag else None
        return copy.deepcopy(regel) if regel else None

    def regels(self, soort: str, dag: date) -> list[dict]:
        return copy.deepcopy(self._dagen.get((soort, dag.isoformat()), {}).get("regels", []))

    def regels_alleen_lezen(self, soort: str, dag: date) -> list[dict]:
        """De regels ZONDER kopie (v5.62), voor tellen en samenvatten.

        `regels()` kopieert alles, en een dag evaluaties is groot: de
        meetlogsensor deed dat elke 30 seconden en hield de event loop tot
        twee seconden vast. Niets wijzigen aan wat hier terugkomt.
        """
        return self._dagen.get((soort, dag.isoformat()), {}).get("regels", [])

    def grootte_bytes(self) -> int:
        return sum(self._groottes.values())

    def samenvatting(self) -> dict:
        per_soort: dict = {s: {"dagen": 0, "bytes": 0} for s in SOORTEN}
        for (soort, _dag), grootte in self._groottes.items():
            per_soort[soort]["dagen"] += 1
            per_soort[soort]["bytes"] += grootte
        return {
            "bytes": self.grootte_bytes(),
            "limiet_bytes": self.limiet_bytes,
            "per_soort": per_soort,
            "snapshots": len(self._snapshot_dag),
            "fouten": self.fouten,
            "laatste_fout": self.laatste_fout,
            "door_limiet_gewist": list(self.door_limiet_gewist[-10:]),
        }

    # --- onderhoud -------------------------------------------------------

    def opruimen(self, vandaag: date) -> list[tuple[str, str]]:
        """Bewaartermijn per soort, daarna de opslaglimiet. Geeft de gewiste
        dagbestanden terug, zodat de opslag ze ook kan verwijderen."""
        gewist = []
        for sleutel in list(self._groottes):
            soort, dag = sleutel
            if date.fromisoformat(dag) < vandaag - timedelta(days=BEWAREN_DAGEN[soort]):
                self._wis(sleutel)
                gewist.append(sleutel)
        while self.grootte_bytes() > self.limiet_bytes:
            kandidaten = sorted(
                (dag, soort) for soort, dag in self._groottes
                if soort in DOOR_LIMIET_TE_WISSEN and dag != vandaag.isoformat()
            )
            if not kandidaten:
                break
            dag, soort = kandidaten[0]
            self._wis((soort, dag))
            gewist.append((soort, dag))
            self.door_limiet_gewist.append(f"{soort} {dag}")
        return gewist

    def _wis(self, sleutel) -> None:
        if sleutel[0] == "snapshot":
            for sid in list(self._dagen.get(sleutel, {})):
                self._snapshot_dag.pop(sid, None)
        self._dagen.pop(sleutel, None)
        self._groottes.pop(sleutel, None)
        self._gewijzigd.discard(sleutel)

    # --- opslag ----------------------------------------------------------

    def te_bewaren(self) -> dict:
        """De gewijzigde dagbestanden, als (soort, dag) -> inhoud; daarna schoon."""
        uit = {s: copy.deepcopy(self._dagen.get(s, {})) for s in self._gewijzigd}
        self._gewijzigd.clear()
        return uit

    def laad_dag(self, soort: str, dag: str, inhoud: dict | None) -> None:
        """Een bewaard dagbestand terugzetten na een herstart - SAMENVOEGEN met
        wat er sinds de herstart al is vastgelegd (v5.28.2). Vervangen liet
        records uit de eerste rondes na de herstart verdwijnen.

        Snapshots: beide verzamelingen; zelfde id moet zelfde inhoud hebben.
        Regels: eerst de bewaarde, dan de nieuwe, zonder dubbele.
        """
        if not inhoud:
            return
        sleutel = (soort, dag)
        huidig = self._dagen.get(sleutel, {})
        if soort == "snapshot":
            samen = copy.deepcopy(inhoud)
            for sid, regel in huidig.items():
                if sid in samen and _json(samen[sid]["inhoud"]) != _json(regel["inhoud"]):
                    self.fouten += 1
                    self.laatste_fout = f"snapshot {sid}: bewaarde en nieuwe inhoud verschillen"
                    continue
                samen.setdefault(sid, regel)
            for sid in samen:
                self._snapshot_dag[sid] = dag
        else:
            bewaard = copy.deepcopy(inhoud.get("regels", []))
            gezien = {_json(r) for r in bewaard}
            nieuw = [r for r in huidig.get("regels", []) if _json(r) not in gezien]
            samen = {"regels": bewaard + nieuw}
        self._dagen[sleutel] = samen
        self._groottes[sleutel] = len(_json(samen))
        if huidig:
            self._gewijzigd.add(sleutel)   # de samengevoegde dag opnieuw bewaren

    @staticmethod
    def opslagsleutel(soort: str, dag: str) -> str:
        return f"energy_management_system_meetlog_{soort}_{dag.replace('-', '')}"
