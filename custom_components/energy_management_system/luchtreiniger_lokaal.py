"""De luchtreiniger zelf meelezen, via het lokale Tuya-protocol (v5.84).

Gevraagd op 11 oktober: "Ik wil dat je het EMS de luchtreiniger zelf laat
uitlezen, zonder integratie van derden" - en daarna sturen (laag, midden,
hoog, auto). Zoals bij Zendure (v5.50): eerst ALLEEN LEZEN en vergelijken
met wat de Tuya-integratie (cloud) laat zien; sturen pas als dat bewezen is.

Wat deze module doet:

- het apparaat vinden: de eerste luchtreiniger (Tuya-categorie "kj") in de
  officiële Tuya-integratie. Daar staan ook de local key en welke datapunt
  welke betekenis heeft (`local_strategy`); de sleutel verlaat dit object
  nooit (niet in attributen, niet in de diagnose);
- het IP-adres en de protocolversie uit de UDP-aankondigingen die het
  apparaat zelf elke paar seconden verstuurt (poort 6666, 6667, 7000); de
  laatst bekende worden bewaard voor na een herstart;
- een blijvende TCP-verbinding (poort 6668) met eigen versleuteling
  (`tuya_lokaal`, 3.3/3.4/3.5), elke VRAAG_S seconden een statusvraag, en
  tussendoor de meldingen die het apparaat zelf stuurt bij een wijziging;
- per datapunt vergelijken met de cloud, en meten welke bron een wijziging
  het eerst ziet;
- ALLE datapunten tonen, ook die de cloud niet kent - daar zou een
  ventilatorsnelheid kunnen zitten, wat nodig is voor laag/midden/hoog.

Wat deze module NOOIT doet: iets naar de luchtreiniger sturen dat hem
verandert. Alleen statusvragen en hartslagen. Een broncodetoets bewaakt dat.
"""
from __future__ import annotations

import asyncio
import logging
import statistics
import time
from datetime import timedelta
from typing import Any

from . import tuya_lokaal as tl

_LOGGER = logging.getLogger(__name__)

TUYA_DOMEIN = "tuya"
CATEGORIE = "kj"  # Tuya: luchtreiniger
TCP_POORT = 6668
UDP_POORTEN = (6666, 6667, 7000)
VRAAG_S = 10.0
TIMEOUT_S = 5.0
WACHT_MAX_S = 60.0
VOLG_INTERVAL = timedelta(seconds=2)
OPSLAG_SLEUTEL = "energy_management_system.luchtreiniger_lokaal"
OPSLAG_VERSIE = 1
BEWAAR_ELKE_RONDES = 60
MIN_VERGELIJKINGEN = 20
DREMPEL_GELIJK = 0.95
LATENTIE_STEEKPROEF = 200
REACTIE_STEEKPROEF = 200
REACTIE_MAX_S = 120.0
MISLUKT_OP_RIJ_GEEN_VERBINDING = 3


# --- zuiver: vergelijken en tellen ----------------------------------------------


def gelijk(lokaal: Any, cloud: Any) -> bool:
    """Booleans en tekst exact; getallen binnen max(2, 10%) - PM2.5 springt."""
    if isinstance(lokaal, bool) or isinstance(cloud, bool):
        return bool(lokaal) == bool(cloud) and isinstance(lokaal, bool) and isinstance(cloud, bool)
    if isinstance(lokaal, (int, float)) and isinstance(cloud, (int, float)):
        return abs(float(lokaal) - float(cloud)) <= max(2.0, 0.10 * max(abs(lokaal), abs(cloud)))
    return str(lokaal) == str(cloud)


def lege_tellingen() -> dict:
    return {
        "rondes": 0, "gelukt": 0, "mislukt": 0, "mislukt_op_rij": 0,
        "verbindingen": 0, "uitval": 0, "meldingen": 0, "aankondigingen": 0,
        "latenties": [], "per_code": {}, "reactie": [], "sinds": None,
        "laatste_gelukt": None, "laatste_fout": None,
        "ip": None, "versie": None,
    }


def herstel(bewaard: Any) -> dict:
    basis = lege_tellingen()
    if isinstance(bewaard, dict):
        for k, v in bewaard.items():
            if k not in basis:
                continue
            standaard = basis[k]
            if standaard is None or isinstance(v, type(standaard)):
                basis[k] = v
    basis["mislukt_op_rij"] = 0
    return basis


def vergelijk(tellingen: dict, lokaal: dict, cloud: dict, strategie: dict[str, str]) -> None:
    """Per code: lokaal tegen cloud, alleen waar beide een waarde hebben."""
    per = tellingen.setdefault("per_code", {})
    for dp, code in strategie.items():
        if dp not in lokaal or code not in cloud or cloud[code] is None:
            continue
        r = per.setdefault(code, {"n": 0, "gelijk": 0})
        r["n"] += 1
        if gelijk(lokaal[dp], cloud[code]):
            r["gelijk"] += 1
        else:
            r["laatst"] = {"lokaal": lokaal[dp], "cloud": cloud[code]}


def verwerk_ronde(tellingen: dict, nu: float, latentie_ms: float | None) -> None:
    tellingen["rondes"] += 1
    tellingen["gelukt"] += 1
    tellingen["mislukt_op_rij"] = 0
    tellingen["laatste_gelukt"] = nu
    if tellingen.get("sinds") is None:
        tellingen["sinds"] = nu
    if latentie_ms is not None:
        lat = tellingen.setdefault("latenties", [])
        lat.append(round(latentie_ms, 1))
        del lat[:-LATENTIE_STEEKPROEF]


def verwerk_fout(tellingen: dict, fout: str, nu: float) -> None:
    tellingen["rondes"] += 1
    tellingen["mislukt"] += 1
    tellingen["mislukt_op_rij"] = tellingen.get("mislukt_op_rij", 0) + 1
    tellingen["laatste_fout"] = {"wanneer": nu, "fout": fout[:200]}
    if tellingen.get("sinds") is None:
        tellingen["sinds"] = nu


def reactie_waarneming(open_: dict, tellingen: dict, bron: str, code: str, waarde: Any, t: float) -> None:
    """Een nieuwe waarde van één bron. Staat dezelfde waarde al open van de
    andere bron, dan is het een meting: wie was eerst, en hoeveel eerder."""
    ander = "cloud" if bron == "lokaal" else "lokaal"
    sleutel = (code, repr(waarde))
    eerder = open_.get((ander,) + sleutel)
    if eerder is not None:
        del open_[(ander,) + sleutel]
        verschil = t - eerder
        if 0 <= verschil <= REACTIE_MAX_S:
            r = tellingen.setdefault("reactie", [])
            r.append({"eerst": ander, "voorsprong_s": round(verschil, 2), "code": code})
            del r[:-REACTIE_STEEKPROEF]
        return
    open_[(bron,) + sleutel] = t
    for k in [k for k, v in open_.items() if t - v > REACTIE_MAX_S]:
        del open_[k]


def reactie_samenvatting(reactie: list) -> dict:
    if not reactie:
        return {"metingen": 0}
    lokaal = [r["voorsprong_s"] for r in reactie if r["eerst"] == "lokaal"]
    cloud = [r["voorsprong_s"] for r in reactie if r["eerst"] == "cloud"]
    return {
        "metingen": len(reactie),
        "lokaal_eerst_procent": round(100 * len(lokaal) / len(reactie), 1),
        "lokaal_mediaan_voorsprong_s": round(statistics.median(lokaal), 1) if lokaal else None,
        "cloud_mediaan_voorsprong_s": round(statistics.median(cloud), 1) if cloud else None,
        "sneller": "lokaal" if len(lokaal) > len(cloud) else ("cloud" if cloud else "lokaal"),
        "resolutie_cloud_s": VOLG_INTERVAL.total_seconds(),
    }


def oordeel(tellingen: dict, toestand: str | None) -> str:
    if toestand in ("niet gevonden", "geen sleutel", "zoekt adres"):
        return toestand
    if tellingen.get("mislukt_op_rij", 0) >= MISLUKT_OP_RIJ_GEEN_VERBINDING:
        return "geen verbinding"
    per = tellingen.get("per_code") or {}
    rijp = [r for r in per.values() if r.get("n", 0) >= MIN_VERGELIJKINGEN]
    if not rijp:
        return "verzamelt"
    if all(r["gelijk"] / r["n"] >= DREMPEL_GELIJK for r in rijp):
        return "gelijk"
    return "wijkt af"


def _tijd(ts: Any) -> str | None:
    if not isinstance(ts, (int, float)):
        return None
    from datetime import datetime

    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def _p(waarden: list, q: float) -> float | None:
    if not waarden:
        return None
    s = sorted(waarden)
    return round(s[min(len(s) - 1, int(q * len(s)))], 1)


def samenvatting(t: dict) -> dict:
    per = {}
    n_tot = g_tot = 0
    for code, r in sorted((t.get("per_code") or {}).items()):
        n, g = r.get("n", 0), r.get("gelijk", 0)
        n_tot += n
        g_tot += g
        per[code] = {"overeenkomst_procent": round(100 * g / n, 1) if n else None, "n": n}
        if r.get("laatst") and n and g / n < DREMPEL_GELIJK:
            per[code]["laatst"] = r["laatst"]
    lat = t.get("latenties") or []
    return {
        "rondes": t.get("rondes", 0),
        "gelukt": t.get("gelukt", 0),
        "mislukt": t.get("mislukt", 0),
        "verbindingen": t.get("verbindingen", 0),
        "uitval": t.get("uitval", 0),
        "meldingen_van_apparaat": t.get("meldingen", 0),
        "aankondigingen": t.get("aankondigingen", 0),
        "sinds": _tijd(t.get("sinds")),
        "laatste_gelukt": _tijd(t.get("laatste_gelukt")),
        "laatste_fout": (
            {"wanneer": _tijd(t["laatste_fout"].get("wanneer")), "fout": t["laatste_fout"].get("fout")}
            if t.get("laatste_fout") else None
        ),
        "latentie_mediaan_ms": round(statistics.median(lat), 1) if lat else None,
        "latentie_p90_ms": _p(lat, 0.9),
        "overeenkomst_totaal_procent": round(100 * g_tot / n_tot, 1) if n_tot else None,
        "per_code": per,
        "reactiesnelheid": reactie_samenvatting(t.get("reactie") or []),
    }


def tekst(status: str, a: dict) -> str:
    gelijk_ = a.get("overeenkomst_totaal_procent")
    regels = [
        f"**{status}** · {('-' if gelijk_ is None else str(gelijk_).replace('.', ','))}% gelijk met de "
        f"Tuya-cloud · {a.get('rondes', 0)} rondes · latentie {a.get('latentie_mediaan_ms') or '-'} ms",
        f"Apparaat: {a.get('apparaat') or '-'} · {a.get('ip') or 'adres onbekend'} · "
        f"protocol {a.get('versie') or '-'} · {a.get('verbindingen', 0)} keer verbonden, "
        f"{a.get('uitval', 0)} keer uitgevallen",
    ]
    waarden = a.get("waarden") or {}
    if waarden:
        regels.append("Nu: " + " · ".join(f"{k} {v}" for k, v in waarden.items()))
    extra = a.get("onbekende_dps") or {}
    if extra:
        regels.append(
            "Datapunten die de cloud niet kent: "
            + " · ".join(f"dp {k} = {v}" for k, v in extra.items())
        )
    r = a.get("reactiesnelheid") or {}
    if r.get("metingen"):
        regels.append(
            f"Wie ziet een wijziging eerst: {r.get('sneller')} "
            f"({r.get('lokaal_eerst_procent')}% lokaal eerst, n={r['metingen']})"
        )
    for code, v in (a.get("per_code") or {}).items():
        if v.get("laatst"):
            regels.append(
                f"⚠️ {code}: {str(v['overeenkomst_procent']).replace('.', ',')}% gelijk "
                f"(lokaal {v['laatst']['lokaal']}, cloud {v['laatst']['cloud']})"
            )
    fout = a.get("laatste_fout")
    if status == "geen verbinding" and fout:
        regels.append(f"Laatste fout: {fout.get('fout')}")
    return "\n\n".join(regels)


# --- Home Assistant -----------------------------------------------------------


class _Aankondigingen(asyncio.DatagramProtocol):
    def __init__(self, eigenaar: "LuchtreinigerLokaalMeelezer") -> None:
        self._eigenaar = eigenaar

    def datagram_received(self, data: bytes, _adres) -> None:
        try:
            self._eigenaar.aankondiging(tl.lees_aankondiging(data))
        except Exception:  # noqa: BLE001 - een vreemd pakket mag niets breken
            pass

    def error_received(self, _exc) -> None:
        pass


class LuchtreinigerLokaalMeelezer:
    """Leest de luchtreiniger zelf uit over het lokale netwerk. Stuurt nooit."""

    def __init__(self, hass) -> None:
        self._hass = hass
        self.tellingen: dict = lege_tellingen()
        self.toestand: str | None = None
        self.dev_id: str | None = None
        self.naam: str | None = None
        self.strategie: dict[str, str] = {}
        self.dps: dict[str, Any] = {}
        self.dps_t: float | None = None
        self.verbonden = False
        self._apparaat = None
        self._sleutel: str | None = None
        self._taak: asyncio.Task | None = None
        self._udp: list = []
        self._afmelden = None
        self._opslag = None
        self._open: dict = {}
        self._vorige = {"lokaal": {}, "cloud": {}}
        self._buffer = b""
        self._device22 = False

    # apparaat en sleutel uit de Tuya-integratie ------------------------------

    def _zoek_apparaat(self) -> bool:
        for entry in self._hass.config_entries.async_entries(TUYA_DOMEIN):
            data = getattr(entry, "runtime_data", None)
            manager = getattr(data, "manager", None)
            if manager is None:
                oud = (getattr(self._hass, "data", {}) or {}).get(TUYA_DOMEIN, {})
                manager = getattr((oud or {}).get(entry.entry_id), "manager", None)
            for dev in (getattr(manager, "device_map", None) or {}).values():
                if getattr(dev, "category", None) != CATEGORIE:
                    continue
                self._apparaat = dev
                self.dev_id = str(dev.id)
                self.naam = getattr(dev, "name", None)
                sleutel = getattr(dev, "local_key", None)
                self._sleutel = sleutel if isinstance(sleutel, str) and len(sleutel) == 16 else None
                self.strategie = strategie_uit(getattr(dev, "local_strategy", None))
                return True
        return False

    def _cloud_status(self) -> dict:
        status = getattr(self._apparaat, "status", None)
        return dict(status) if isinstance(status, dict) else {}

    # levenscyclus --------------------------------------------------------------

    async def async_start(self) -> None:
        from homeassistant.helpers.event import async_track_time_interval
        from homeassistant.helpers.storage import Store

        self._opslag = Store(self._hass, OPSLAG_VERSIE, OPSLAG_SLEUTEL)
        try:
            self.tellingen = herstel(await self._opslag.async_load())
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Luchtreiniger-meelezen: opslag niet te lezen: %s", err)
        loop = asyncio.get_running_loop()
        for poort in UDP_POORTEN:
            try:
                transport, _ = await loop.create_datagram_endpoint(
                    lambda: _Aankondigingen(self), local_addr=("0.0.0.0", poort),
                    reuse_port=True, allow_broadcast=True,
                )
                self._udp.append(transport)
            except OSError as err:
                _LOGGER.debug("Luchtreiniger-meelezen: UDP %s niet te openen: %s", poort, err)
        self._afmelden = async_track_time_interval(self._hass, self._volg_cloud, VOLG_INTERVAL)
        self._taak = self._hass.async_create_background_task(
            self._lus(), "energy_management_system_luchtreiniger_lokaal"
        )

    async def async_stop(self) -> None:
        afmelden, self._afmelden = self._afmelden, None
        if afmelden is not None:
            afmelden()
        for transport in self._udp:
            transport.close()
        self._udp = []
        taak, self._taak = self._taak, None
        if taak is not None:
            taak.cancel()
        await self._bewaar()

    async def _bewaar(self) -> None:
        if self._opslag is None:
            return
        try:
            await self._opslag.async_save(self.tellingen)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Luchtreiniger-meelezen: opslaan mislukt: %s", err)

    # adres --------------------------------------------------------------------

    def aankondiging(self, a: dict | None) -> None:
        if not a or self.dev_id is None or a.get("gwId") != self.dev_id:
            return
        self.tellingen["aankondigingen"] = self.tellingen.get("aankondigingen", 0) + 1
        self.tellingen["ip"] = str(a["ip"])
        versie = str(a.get("version") or "")
        if versie in tl.VERSIES:
            self.tellingen["versie"] = versie

    # de lus --------------------------------------------------------------------

    async def _lus(self) -> None:
        wacht = 5.0
        while True:
            try:
                if self._apparaat is None and not self._zoek_apparaat():
                    self.toestand = "niet gevonden"
                    await asyncio.sleep(WACHT_MAX_S)
                    continue
                if self._sleutel is None:
                    self._zoek_apparaat()
                    if self._sleutel is None:
                        self.toestand = "geen sleutel"
                        await asyncio.sleep(WACHT_MAX_S)
                        continue
                if not self.tellingen.get("ip"):
                    self.toestand = "zoekt adres"
                    await asyncio.sleep(5)
                    continue
                self.toestand = None
                await self._verbinding()
                wacht = 5.0
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 - dit mag het EMS nooit raken
                verwerk_fout(self.tellingen, f"{type(err).__name__}: {err}", time.time())
                if self.verbonden:
                    self.tellingen["uitval"] = self.tellingen.get("uitval", 0) + 1
                self.verbonden = False
                # Na een paar mislukte keren kan de sleutel nieuw zijn (opnieuw
                # gekoppeld in de app): opnieuw ophalen bij de volgende ronde.
                if self.tellingen.get("mislukt_op_rij", 0) % 5 == 0:
                    self._apparaat = None
                await asyncio.sleep(wacht)
                wacht = min(wacht * 2, WACHT_MAX_S)

    async def _lees_frame(self, reader, timeout: float) -> bytes:
        einde = time.monotonic() + timeout
        while True:
            begin = tl.zoek_prefix(self._buffer)
            if begin > 0:
                self._buffer = self._buffer[begin:]
            elif begin < 0:
                self._buffer = self._buffer[-3:]
            if begin >= 0:
                lengte = tl.frame_lengte(self._buffer)
                if lengte is not None and len(self._buffer) >= lengte:
                    frame, self._buffer = self._buffer[:lengte], self._buffer[lengte:]
                    return frame
            rest = einde - time.monotonic()
            if rest <= 0:
                raise asyncio.TimeoutError
            stuk = await asyncio.wait_for(reader.read(4096), rest)
            if not stuk:
                raise ConnectionError("verbinding gesloten door het apparaat")
            self._buffer += stuk

    async def _verbinding(self) -> None:
        ip = self.tellingen["ip"]
        versie = self.tellingen.get("versie") or "3.3"
        reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, TCP_POORT), TIMEOUT_S)
        self._buffer = b""
        try:
            sessie = tl.Sessie(self._sleutel, versie)
            if sessie.nieuw:
                writer.write(sessie.start())
                await writer.drain()
                writer.write(sessie.antwoord(await self._lees_frame(reader, TIMEOUT_S)))
                await writer.drain()
            self.verbonden = True
            self.tellingen["verbindingen"] = self.tellingen.get("verbindingen", 0) + 1
            while True:
                opdracht, inhoud = self._vraag(versie)
                verstuurd = time.monotonic()
                writer.write(sessie.pak(opdracht, inhoud))
                await writer.drain()
                beantwoord = False
                volgende = verstuurd + VRAAG_S
                while True:
                    rest = volgende - time.monotonic()
                    if rest <= 0:
                        break
                    try:
                        frame = await self._lees_frame(reader, rest if beantwoord else min(rest, TIMEOUT_S))
                    except asyncio.TimeoutError:
                        if not beantwoord:
                            raise
                        break
                    b = sessie.lees(frame)
                    if tl.ongeldige_vraag(b.inhoud) and versie == "3.3" and not self._device22:
                        self._device22 = True
                        break
                    dps = tl.dps_uit(b.inhoud)
                    if dps is None:
                        continue
                    nu = time.time()
                    self._verwerk_dps(dps, nu)
                    # Het eerste frame met datapunten na de vraag is het
                    # antwoord - 3.4-apparaten antwoorden soms met opdracht 8.
                    if not beantwoord:
                        beantwoord = True
                        verwerk_ronde(self.tellingen, nu, (time.monotonic() - verstuurd) * 1000)
                        vergelijk(self.tellingen, self.dps, self._cloud_status(), self.strategie)
                        if self.tellingen["rondes"] % BEWAAR_ELKE_RONDES == 0:
                            await self._bewaar()
                    elif b.opdracht == tl.STATUS:
                        self.tellingen["meldingen"] = self.tellingen.get("meldingen", 0) + 1
        finally:
            self.verbonden = False
            writer.close()

    def _vraag(self, versie: str) -> tuple[int, bytes]:
        if self._device22:
            dps = {dp: None for dp in (self.strategie or {"1": None})}
            return tl.vraag_inhoud(versie, self.dev_id, tl.STURING_NIEUW, dps)
        return tl.vraag_inhoud(versie, self.dev_id)

    def _verwerk_dps(self, dps: dict, nu: float) -> None:
        for dp, waarde in dps.items():
            dp = str(dp)
            if self.dps.get(dp, object()) != waarde:
                code = self.strategie.get(dp)
                if code is not None and dp in self.dps:
                    reactie_waarneming(self._open, self.tellingen, "lokaal", code, waarde, nu)
            self.dps[dp] = waarde
        self.dps_t = nu

    def _volg_cloud(self, _nu=None) -> None:
        """Elke 2 s: welke cloudwaarden zijn veranderd (voor de reactiesnelheid)."""
        try:
            nu = time.time()
            vorige = self._vorige["cloud"]
            for code, waarde in self._cloud_status().items():
                if code in vorige and vorige[code] != waarde:
                    reactie_waarneming(self._open, self.tellingen, "cloud", code, waarde, nu)
                vorige[code] = waarde
        except Exception:  # noqa: BLE001
            pass

    # weergave -----------------------------------------------------------------

    def status(self) -> str:
        return oordeel(self.tellingen, self.toestand)

    def attributen(self) -> dict:
        uit = samenvatting(self.tellingen)
        uit["modus"] = "alleen lezen - stuurt niets"
        uit["apparaat"] = self.naam
        uit["apparaat_id"] = f"…{self.dev_id[-6:]}" if self.dev_id else None
        uit["ip"] = self.tellingen.get("ip")
        uit["versie"] = self.tellingen.get("versie")
        uit["verbonden"] = self.verbonden
        uit["sleutel_gevonden"] = self._sleutel is not None
        uit["waarden"] = {
            self.strategie.get(dp, f"dp {dp}"): v for dp, v in sorted(self.dps.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0)
            if dp in self.strategie
        }
        uit["onbekende_dps"] = {dp: v for dp, v in self.dps.items() if dp not in self.strategie}
        uit["waarden_van"] = _tijd(self.dps_t)
        uit["tekst"] = tekst(self.status(), uit)
        return uit


def strategie_uit(local_strategy: Any) -> dict[str, str]:
    """dp-nummer -> code, uit `local_strategy` van het Tuya-apparaat."""
    uit: dict[str, str] = {}
    if isinstance(local_strategy, dict):
        for dp, s in local_strategy.items():
            code = s.get("status_code") if isinstance(s, dict) else None
            if code:
                uit[str(dp)] = str(code)
    return uit
