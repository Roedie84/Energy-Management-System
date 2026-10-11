"""Het lokale Tuya-protocol, zelf gesproken (v5.84).

Gevraagd op 11 oktober: "Ik wil dat je het EMS de luchtreiniger zelf laat
uitlezen, zonder integratie van derden." Geen tinytuya, geen Tuya Local:
alleen de standaardbibliotheek en `cryptography`, die Home Assistant zelf al
meelevert.

Wat hier staat is puur protocol - geen Home Assistant, geen netwerk - zodat
het met vaste testvectoren is na te rekenen:

- frames: `0x000055AA` (3.1-3.4, CRC32 of HMAC-SHA256) en `0x00006699`
  (3.5, AES-GCM);
- versleuteling: AES-ECB met de local key (3.3), met een sessiesleutel
  (3.4), AES-GCM met een sessiesleutel (3.5);
- de sessiesleutel-onderhandeling van 3.4 en 3.5 (drie berichten, HMAC op
  beide nonces);
- de UDP-aankondigingen waarmee een apparaat zijn IP-adres en versie meldt
  (poort 6666/6667, en 7000 voor 3.5).

Opgebouwd naar de openbare beschrijving van het protocol zoals tinytuya
(MIT) het implementeert; geen code overgenomen, wel dezelfde berichten.
"""
from __future__ import annotations

import binascii
import hashlib
import hmac
import json
import os
import struct
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# --- opdrachten ---------------------------------------------------------------

SESSIE_START = 3
SESSIE_ANTWOORD = 4
SESSIE_KLAAR = 5
STURING = 7
STATUS = 8
HARTSLAG = 9
DP_VRAAG = 10
STURING_NIEUW = 13
DP_VRAAG_NIEUW = 16
DPS_VERVERSEN = 18

# Opdrachten zonder de "3.x"-kop vóór de inhoud.
ZONDER_KOP = frozenset({DP_VRAAG, DP_VRAAG_NIEUW, DPS_VERVERSEN, HARTSLAG,
                        SESSIE_START, SESSIE_ANTWOORD, SESSIE_KLAAR, 0x40})

PREFIX_55AA = 0x000055AA
SUFFIX_55AA = 0x0000AA55
PREFIX_6699 = 0x00006699
SUFFIX_6699 = 0x00009966
PREFIX_55AA_BIN = struct.pack(">I", PREFIX_55AA)
PREFIX_6699_BIN = struct.pack(">I", PREFIX_6699)
KOP_55AA = ">4I"        # prefix, volgnummer, opdracht, lengte
KOP_6699 = ">IHIII"     # prefix, 0, volgnummer, opdracht, lengte
KOP_55AA_LEN = struct.calcsize(KOP_55AA)   # 16
KOP_6699_LEN = struct.calcsize(KOP_6699)   # 18
MAX_LENGTE = 64 * 1024

UDP_SLEUTEL = hashlib.md5(b"yGAdlopoPVldABfn").digest()

VERSIES = ("3.3", "3.4", "3.5")


class ProtocolFout(Exception):
    """Een frame dat niet te lezen of niet te vertrouwen is."""


@dataclass
class Bericht:
    volgnummer: int
    opdracht: int
    retcode: int | None
    inhoud: bytes
    goed: bool
    prefix: int


# --- versleuteling ------------------------------------------------------------


def _vul(data: bytes) -> bytes:
    n = 16 - len(data) % 16
    return data + bytes([n]) * n


def _ontvul(data: bytes) -> bytes:
    if not data:
        raise ProtocolFout("lege inhoud")
    n = data[-1]
    if n < 1 or n > 16:
        raise ProtocolFout("ongeldige opvulling")
    return data[:-n]


def ecb_versleutel(sleutel: bytes, data: bytes, opvullen: bool = True) -> bytes:
    if opvullen:
        data = _vul(data)
    e = Cipher(algorithms.AES(sleutel), modes.ECB()).encryptor()
    return e.update(data) + e.finalize()


def ecb_ontsleutel(sleutel: bytes, data: bytes, opvullen: bool = True) -> bytes:
    if len(data) % 16:
        raise ProtocolFout(f"lengte {len(data)} is geen veelvoud van 16")
    d = Cipher(algorithms.AES(sleutel), modes.ECB()).decryptor()
    uit = d.update(data) + d.finalize()
    return _ontvul(uit) if opvullen else uit


def gcm_versleutel(sleutel: bytes, data: bytes, iv: bytes, extra: bytes | None = None) -> tuple[bytes, bytes]:
    e = Cipher(algorithms.AES(sleutel), modes.GCM(iv)).encryptor()
    if extra:
        e.authenticate_additional_data(extra)
    return e.update(data) + e.finalize(), e.tag


def gcm_ontsleutel(sleutel: bytes, data: bytes, iv: bytes, tag: bytes, extra: bytes | None = None) -> bytes:
    d = Cipher(algorithms.AES(sleutel), modes.GCM(iv, tag)).decryptor()
    if extra:
        d.authenticate_additional_data(extra)
    try:
        return d.update(data) + d.finalize()
    except Exception as err:  # InvalidTag
        raise ProtocolFout("GCM-controle mislukt") from err


# --- frames -------------------------------------------------------------------


def pak_55aa(volgnummer: int, opdracht: int, inhoud: bytes, hmac_sleutel: bytes | None = None) -> bytes:
    """Een 55AA-frame van de client (zonder retcode): kop, inhoud, CRC32 of
    HMAC-SHA256, staart."""
    staart_len = 32 + 4 if hmac_sleutel else 4 + 4
    kop = struct.pack(KOP_55AA, PREFIX_55AA, volgnummer, opdracht, len(inhoud) + staart_len)
    data = kop + inhoud
    if hmac_sleutel:
        controle = hmac.new(hmac_sleutel, data, hashlib.sha256).digest()
    else:
        controle = struct.pack(">I", binascii.crc32(data) & 0xFFFFFFFF)
    return data + controle + struct.pack(">I", SUFFIX_55AA)


def pak_6699(volgnummer: int, opdracht: int, inhoud: bytes, sleutel: bytes, iv: bytes | None = None) -> bytes:
    """Een 6699-frame (3.5): kop, iv, AES-GCM(inhoud), tag, staart. De kop
    (zonder prefix) is de extra geauthenticeerde data."""
    iv = iv or os.urandom(12)
    lengte = 12 + len(inhoud) + 16
    kop = struct.pack(KOP_6699, PREFIX_6699, 0, volgnummer, opdracht, lengte)
    versleuteld, tag = gcm_versleutel(sleutel, inhoud, iv, kop[4:])
    return kop + iv + versleuteld + tag + struct.pack(">I", SUFFIX_6699)


def frame_lengte(buffer: bytes) -> int | None:
    """Hoeveel bytes het eerste frame in de buffer telt, of None als de kop
    nog niet compleet is. Fout als de buffer niet met een prefix begint."""
    if len(buffer) < 4:
        return None
    prefix = buffer[:4]
    if prefix == PREFIX_55AA_BIN:
        if len(buffer) < KOP_55AA_LEN:
            return None
        lengte = struct.unpack(KOP_55AA, buffer[:KOP_55AA_LEN])[3]
        totaal = KOP_55AA_LEN + lengte
    elif prefix == PREFIX_6699_BIN:
        if len(buffer) < KOP_6699_LEN:
            return None
        lengte = struct.unpack(KOP_6699, buffer[:KOP_6699_LEN])[4]
        totaal = KOP_6699_LEN + lengte + 4
    else:
        raise ProtocolFout("geen Tuya-prefix")
    if lengte > MAX_LENGTE:
        raise ProtocolFout(f"frame claimt {lengte} bytes")
    return totaal


def zoek_prefix(buffer: bytes) -> int:
    """Waar het eerste frame begint (-1 = nergens)."""
    posities = [p for p in (buffer.find(PREFIX_55AA_BIN), buffer.find(PREFIX_6699_BIN)) if p >= 0]
    return min(posities) if posities else -1


def pak_uit(data: bytes, hmac_sleutel: bytes | None = None, retcode: bool = True) -> Bericht:
    """Eén frame van het apparaat lezen. Bij 55AA staat er (normaal) een
    retcode vóór de inhoud; bij 6699 zit die in de versleutelde inhoud."""
    if data[:4] == PREFIX_55AA_BIN:
        _p, volg, opdracht, lengte = struct.unpack(KOP_55AA, data[:KOP_55AA_LEN])
        einde = KOP_55AA_LEN + lengte
        if len(data) < einde:
            raise ProtocolFout("frame onvolledig")
        controle_len = 32 if hmac_sleutel else 4
        if lengte < controle_len + 4:
            raise ProtocolFout("frame te kort")
        romp = data[KOP_55AA_LEN:einde - controle_len - 4]
        controle = data[einde - controle_len - 4:einde - 4]
        te_controleren = data[:einde - controle_len - 4]
        if hmac_sleutel:
            goed = hmac.compare_digest(
                controle, hmac.new(hmac_sleutel, te_controleren, hashlib.sha256).digest()
            )
        else:
            goed = struct.unpack(">I", controle)[0] == (binascii.crc32(te_controleren) & 0xFFFFFFFF)
        code = None
        if retcode and len(romp) >= 4:
            code = struct.unpack(">I", romp[:4])[0]
            romp = romp[4:]
        return Bericht(volg, opdracht, code, romp, goed, PREFIX_55AA)
    if data[:4] == PREFIX_6699_BIN:
        if not hmac_sleutel:
            raise ProtocolFout("6699 zonder sleutel")
        _p, _n, volg, opdracht, lengte = struct.unpack(KOP_6699, data[:KOP_6699_LEN])
        einde = KOP_6699_LEN + lengte
        if len(data) < einde + 4 or lengte < 28:
            raise ProtocolFout("frame onvolledig")
        iv = data[KOP_6699_LEN:KOP_6699_LEN + 12]
        tag = data[einde - 16:einde]
        versleuteld = data[KOP_6699_LEN + 12:einde - 16]
        inhoud = gcm_ontsleutel(hmac_sleutel, versleuteld, iv, tag, data[4:KOP_6699_LEN])
        code = None
        # Een retcode staat vóór de inhoud, behalve als die meteen met de
        # versiekop of JSON begint (zelf gestuurde berichten van het apparaat).
        if retcode and len(inhoud) >= 4 and inhoud[:1] != b"{" and inhoud[:3] != b"3.5":
            code = struct.unpack(">I", inhoud[:4])[0]
            inhoud = inhoud[4:]
        return Bericht(volg, opdracht, code, inhoud, True, PREFIX_6699)
    raise ProtocolFout("geen Tuya-prefix")


# --- sessie -------------------------------------------------------------------


def versiekop(versie: str) -> bytes:
    return versie.encode("ascii") + b"\x00" * 12


class Sessie:
    """De versleuteling van één verbinding (3.3, 3.4 of 3.5).

    Voor 3.4 en 3.5 eerst `start()` sturen, het antwoord aan `antwoord()`
    geven en wat die teruggeeft sturen; daarna geldt de sessiesleutel.
    """

    def __init__(self, local_key: str | bytes, versie: str, nonce: bytes | None = None) -> None:
        if versie not in VERSIES:
            raise ProtocolFout(f"versie {versie} wordt niet ondersteund")
        self.echte_sleutel = local_key.encode("latin1") if isinstance(local_key, str) else bytes(local_key)
        if len(self.echte_sleutel) != 16:
            raise ProtocolFout("local key moet 16 tekens zijn")
        self.versie = versie
        self.sleutel = self.echte_sleutel
        self.volgnummer = 1
        self.lokale_nonce = nonce or os.urandom(16)
        self.klaar = versie == "3.3"

    @property
    def nieuw(self) -> bool:
        return self.versie in ("3.4", "3.5")

    def _volgende(self) -> int:
        n = self.volgnummer
        self.volgnummer += 1
        return n

    def pak(self, opdracht: int, inhoud: bytes, iv: bytes | None = None) -> bytes:
        """Inhoud versleutelen en verpakken zoals deze versie het verwacht."""
        if self.versie == "3.3":
            versleuteld = ecb_versleutel(self.sleutel, inhoud)
            if opdracht not in ZONDER_KOP:
                versleuteld = versiekop("3.3") + versleuteld
            return pak_55aa(self._volgende(), opdracht, versleuteld)
        if opdracht not in ZONDER_KOP:
            inhoud = versiekop(self.versie) + inhoud
        if self.versie == "3.4":
            return pak_55aa(self._volgende(), opdracht, ecb_versleutel(self.sleutel, inhoud), self.sleutel)
        return pak_6699(self._volgende(), opdracht, inhoud, self.sleutel, iv)

    def lees(self, frame: bytes) -> Bericht:
        """Een frame lezen en de inhoud ontsleutelen (zonder versiekop)."""
        hmac_sleutel = self.sleutel if self.nieuw else None
        b = pak_uit(frame, hmac_sleutel)
        if not b.goed:
            raise ProtocolFout("controle klopt niet")
        inhoud = b.inhoud
        if self.versie == "3.4" and inhoud:
            inhoud = ecb_ontsleutel(self.sleutel, inhoud)
        if inhoud.startswith(self.versie.encode("ascii")):
            inhoud = inhoud[15:]
        if self.versie == "3.3" and inhoud and inhoud[:1] != b"{":
            inhoud = ecb_ontsleutel(self.sleutel, inhoud)
        b.inhoud = inhoud
        return b

    # onderhandeling (3.4 / 3.5)

    def start(self) -> bytes:
        return self.pak(SESSIE_START, self.lokale_nonce)

    def antwoord(self, frame: bytes) -> bytes:
        """Het antwoord van het apparaat controleren; geeft het slotbericht en
        zet de sessiesleutel."""
        b = pak_uit(frame, self.echte_sleutel)
        if not b.goed:
            raise ProtocolFout("onderhandeling: controle klopt niet")
        if b.opdracht != SESSIE_ANTWOORD:
            raise ProtocolFout(f"onderhandeling: opdracht {b.opdracht} in plaats van 4")
        inhoud = b.inhoud
        if self.versie == "3.4":
            inhoud = ecb_ontsleutel(self.echte_sleutel, inhoud)
        if len(inhoud) < 48:
            raise ProtocolFout("onderhandeling: antwoord te kort")
        remote = inhoud[:16]
        verwacht = hmac.new(self.echte_sleutel, self.lokale_nonce, hashlib.sha256).digest()
        if not hmac.compare_digest(inhoud[16:48], verwacht):
            raise ProtocolFout("onderhandeling: verkeerde local key")
        slot = self.pak(SESSIE_KLAAR, hmac.new(self.echte_sleutel, remote, hashlib.sha256).digest())
        self.sleutel = sessiesleutel(self.echte_sleutel, self.lokale_nonce, remote, self.versie)
        self.klaar = True
        return slot


def sessiesleutel(echte_sleutel: bytes, lokaal: bytes, remote: bytes, versie: str) -> bytes:
    xor = bytes(a ^ b for a, b in zip(lokaal, remote))
    if versie == "3.4":
        return ecb_versleutel(echte_sleutel, xor, opvullen=False)
    versleuteld, _tag = gcm_versleutel(echte_sleutel, xor, lokaal[:12])
    return versleuteld[:16]


# --- inhoud -------------------------------------------------------------------


def vraag_inhoud(versie: str, dev_id: str, opdracht: int = DP_VRAAG, dps: dict | None = None) -> tuple[int, bytes]:
    """De JSON van een statusvraag (of hartslag) voor deze versie. Geeft de
    werkelijke opdracht terug (3.4/3.5 vragen met DP_VRAAG_NIEUW)."""
    if opdracht == HARTSLAG:
        data: dict = {"gwId": dev_id, "devId": dev_id}
    elif versie in ("3.4", "3.5"):
        return DP_VRAAG_NIEUW, b"{}"
    elif opdracht == STURING_NIEUW:  # "device22": vraagt met een lijst dps
        data = {"devId": dev_id, "uid": dev_id, "t": str(int(time.time())), "dps": dps or {"1": None}}
    else:
        data = {"gwId": dev_id, "devId": dev_id, "uid": dev_id, "t": str(int(time.time()))}
    return opdracht, json.dumps(data, separators=(",", ":")).encode()


def dps_uit(inhoud: bytes) -> dict | None:
    """De datapunten uit een antwoord of melding ({"dps": {...}} of
    {"data": {"dps": {...}}}), of None."""
    if not inhoud:
        return None
    try:
        tekst = inhoud.decode("utf-8", errors="replace").rstrip("\x00")
        data = json.loads(tekst)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    dps = data.get("dps")
    if dps is None and isinstance(data.get("data"), dict):
        dps = data["data"].get("dps")
    return dict(dps) if isinstance(dps, dict) else None


def ongeldige_vraag(inhoud: bytes) -> bool:
    """Het "data unvalid"-antwoord van 22-tekens-apparaten op 3.3: die willen
    de statusvraag als STURING_NIEUW met een lijst dps."""
    return b"data unvalid" in (inhoud or b"")


# --- UDP-aankondigingen -------------------------------------------------------


def lees_aankondiging(data: bytes) -> dict | None:
    """Een UDP-aankondiging van een Tuya-apparaat: {"ip", "gwId", "version",
    ...}, of None als het geen leesbare aankondiging is."""
    try:
        if data[:4] == PREFIX_6699_BIN:
            b = pak_uit(data, UDP_SLEUTEL, retcode=True)
            tekst = b.inhoud
        elif data[:4] == PREFIX_55AA_BIN:
            b = pak_uit(data, None, retcode=True)
            tekst = b.inhoud
            if not (tekst[:1] == b"{" and tekst.rstrip(b"\x00")[-1:] == b"}"):
                tekst = ecb_ontsleutel(UDP_SLEUTEL, tekst)
        else:
            tekst = ecb_ontsleutel(UDP_SLEUTEL, data)
        uit = json.loads(tekst.decode("utf-8", errors="replace").rstrip("\x00"))
    except (ProtocolFout, ValueError, struct.error):
        return None
    if not isinstance(uit, dict) or not uit.get("gwId") or not uit.get("ip"):
        return None
    return uit
