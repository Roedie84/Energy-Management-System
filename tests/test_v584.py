"""v5.84: de luchtreiniger zelf meelezen via het lokale Tuya-protocol.

Gevraagd op 11 oktober: "Ik wil dat je het EMS de luchtreiniger zelf laat
uitlezen, zonder integratie van derden." De testvectoren hieronder zijn
gemaakt met tinytuya 1.20.0 (als apparaat-kant), zodat het eigen protocol
tegen een onafhankelijke implementatie is getoetst; tinytuya zelf is GEEN
afhankelijkheid van het EMS.
"""
import asyncio
import json
import re
import time
from pathlib import Path
from types import SimpleNamespace

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import luchtreiniger_lokaal as ll
from custom_components.energy_management_system import tuya_lokaal as tl

MAP = Path(pkg.__file__).parent
SLEUTEL = "0123456789abcdef"
DEV = "bf46d22d435c249d12mwmw"
DPS = {"1": True, "2": 7, "3": "auto", "5": 0}

V33_ANTWOORD = bytes.fromhex("000055aa000000020000000a0000006c00000000fd59c01067c6911656c40e3568ef770d910744d9a34fcd460cb281e2e9628056d6cc680b6a8992bf9dd1a04ff8a3c9edb8b59f68887bcc8e72a91fba0e624a2545dbf4bc8cb47b4b00c2ccc0ae6055744c6b3a66114c76c3975e109a48e381a879450cdc0000aa55")
V33_STATUS = bytes.fromhex("000055aa00000003000000080000007b00000000332e33000000000000000000000000fd59c01067c6911656c40e3568ef770d910744d9a34fcd460cb281e2e9628056d6cc680b6a8992bf9dd1a04ff8a3c9edb8b59f68887bcc8e72a91fba0e624a2545dbf4bc8cb47b4b00c2ccc0ae6055744c6b3a66114c76c3975e109a48e381a8ada279a90000aa55")
V34_ONDERHANDELING = bytes.fromhex("000055aa0000000100000004000000680000000073a52251699d8c81ef2bf3579d0213de8496ef84587966764c310859ca6bfb37805450ffe5252db94a36ea94f934c527377222e061a924c591cd9c27ea163ed431ce38d2bf493831c19d2c39ad016d0af8650d0321f158825e81f425cd5492c00000aa55")
V34_STATUS = bytes.fromhex("000055aa0000000400000008000000980000000019e9a922443e8151612bc5d14ac50e86a85717fccbf4a6ac93a8466a2f09d9830d7652081bc0724256af4f464ce5f4d30dadc4cd7d910d74672fca1cb84d5e8b061f76ea22bbacc270522ffd53c3583a92a653e7c7e2e135ca6f0b2f627f89ff4056105a518e2e39ba4283c7cbef4e791c1f7f63249a79b9ad8461f93424d57ad73c9c7a43cd58ad2a9b9a2c1598be140000aa55")
V35_ONDERHANDELING = bytes.fromhex("000066990000000000010000000400000050495649564956495649564956330007114be2e48fcc028351831eda9646383c59f61ddb0bc8d07dba1b506edda8b5e45814a43a0d6ffcdf8f2c1c5f4f47cf39e9ba06221afe01825c8f35828309a84e1400009966")
V35_ANTWOORD = bytes.fromhex("0000669900000000000500000010000000834142434445464748494a4b4ca9c351a5c11491a4afd6fe4e980f464bfeec8e410d049f7a50249abae59e8995cfd9ba02dfa66d54e125af263178246ad0eb4573e09b629e77bb2897a81dec57340439297895cc75760f5179d03b14bd38dcf9c36855820b6fc4ab0539ad2e00c7320403caa76dffdcc2a41de4c8572565ae717567081f00009966")
UDP_34 = bytes.fromhex("000055aa00000000000000130000007c000000002a9f8305368a6a303dfe78a9cb5fc1521bd4000ceb45f805183f19315c6256d1eac20657141530831d8c62237338e698b9b252d507ad338e444a4ccb330daf0ae34f3c429e31238774f07003d8888a6711bbed88b285afaf7a382de13269cee40ffc5c634ee6f9183ac174619ec3e3eebd1a43e50000aa55")
SK34 = bytes.fromhex("bc6a855faf3e089afe8721f5925ffef2")
SK35 = bytes.fromhex("86fce4ea964f68132ec71b85283981d4")


def test_33_antwoord_en_melding():
    s = tl.Sessie(SLEUTEL, "3.3")
    assert tl.dps_uit(s.lees(V33_ANTWOORD).inhoud) == DPS
    b = s.lees(V33_STATUS)
    assert b.opdracht == tl.STATUS and tl.dps_uit(b.inhoud) == DPS


def test_34_onderhandeling_en_sessiesleutel():
    s = tl.Sessie(SLEUTEL, "3.4", nonce=b"L" * 16)
    s.start()
    s.antwoord(V34_ONDERHANDELING)
    assert s.sleutel == SK34
    assert tl.dps_uit(s.lees(V34_STATUS).inhoud) == DPS


def test_35_onderhandeling_en_gcm():
    s = tl.Sessie(SLEUTEL, "3.5", nonce=b"L" * 16)
    s.start()
    s.antwoord(V35_ONDERHANDELING)
    assert s.sleutel == SK35
    assert tl.dps_uit(s.lees(V35_ANTWOORD).inhoud) == DPS


def test_verkeerde_sleutel_wordt_herkend():
    s = tl.Sessie("fedcba9876543210", "3.4", nonce=b"L" * 16)
    s.start()
    try:
        s.antwoord(V34_ONDERHANDELING)
    except tl.ProtocolFout:
        pass
    else:
        raise AssertionError("verkeerde sleutel niet herkend")


def test_beschadigd_frame_wordt_geweigerd():
    s = tl.Sessie(SLEUTEL, "3.3")
    kapot = bytearray(V33_ANTWOORD)
    kapot[20] ^= 0xFF
    try:
        s.lees(bytes(kapot))
    except tl.ProtocolFout:
        pass
    else:
        raise AssertionError("CRC niet gecontroleerd")


def test_udp_aankondiging():
    a = tl.lees_aankondiging(UDP_34)
    assert a["ip"] == "192.168.2.55" and a["gwId"] == DEV and a["version"] == "3.4"
    assert tl.lees_aankondiging(b"onzin") is None


def test_framelengte_en_prefix():
    assert tl.frame_lengte(V33_ANTWOORD) == len(V33_ANTWOORD)
    assert tl.frame_lengte(V35_ANTWOORD) == len(V35_ANTWOORD)
    assert tl.frame_lengte(V33_ANTWOORD[:10]) is None
    assert tl.zoek_prefix(b"xx" + V33_ANTWOORD) == 2


def test_vraag_per_versie():
    assert tl.vraag_inhoud("3.4", DEV) == (tl.DP_VRAAG_NIEUW, b"{}")
    op, inhoud = tl.vraag_inhoud("3.3", DEV)
    assert op == tl.DP_VRAAG and json.loads(inhoud)["devId"] == DEV
    op, inhoud = tl.vraag_inhoud("3.3", DEV, tl.STURING_NIEUW, {"1": None})
    assert op == tl.STURING_NIEUW and json.loads(inhoud)["dps"] == {"1": None}


def test_vergelijken_en_oordeel():
    t = ll.lege_tellingen()
    strategie = {"1": "switch", "2": "pm25", "3": "mode"}
    for _ in range(25):
        ll.vergelijk(t, {"1": True, "2": 7, "3": "auto"}, {"switch": True, "pm25": 8, "mode": "auto"}, strategie)
    assert ll.oordeel(t, None) == "gelijk"
    for _ in range(10):
        ll.vergelijk(t, {"3": "sleep"}, {"mode": "auto"}, strategie)
    assert ll.oordeel(t, None) == "wijkt af"
    assert ll.oordeel(t, "geen sleutel") == "geen sleutel"
    assert ll.gelijk(True, True) and not ll.gelijk(True, 1) and ll.gelijk(100, 109)


def test_reactie_wie_eerst():
    t, open_ = ll.lege_tellingen(), {}
    ll.reactie_waarneming(open_, t, "lokaal", "mode", "sleep", 100.0)
    ll.reactie_waarneming(open_, t, "cloud", "mode", "sleep", 101.5)
    s = ll.reactie_samenvatting(t["reactie"])
    assert s["metingen"] == 1 and s["sneller"] == "lokaal" and s["lokaal_mediaan_voorsprong_s"] == 1.5


def test_strategie_uit_tuya():
    strategie = ll.strategie_uit({"1": {"status_code": "switch"}, "18": {"status_code": "countdown_set"}, "x": None})
    assert strategie == {"1": "switch", "18": "countdown_set"}


def test_herstel_na_herstart():
    t = ll.herstel({"rondes": 12, "ip": "192.168.2.55", "versie": "3.4", "mislukt_op_rij": 9, "onzin": 1})
    assert t["rondes"] == 12 and t["ip"] == "192.168.2.55" and t["mislukt_op_rij"] == 0 and "onzin" not in t


def test_stuurt_nooit():
    """Alleen statusvragen en hartslagen - nooit STURING met data."""
    code = (MAP / "luchtreiniger_lokaal.py").read_text()
    code = re.sub(r'"""[\s\S]*?"""', "", code)
    for verboden in ("tl.STURING,", "STURING)", "async_call", "services.call", '"dps": {'):
        assert verboden not in code, verboden
    assert "_device22" in code  # de enige STURING_NIEUW is de statusvraag van 22-tekens-apparaten


def test_geen_sleutel_in_attributen():
    m = ll.LuchtreinigerLokaalMeelezer(SimpleNamespace())
    m._sleutel = SLEUTEL
    assert SLEUTEL not in json.dumps(m.attributen(), default=str)


def test_aangesloten():
    assert "LuchtreinigerLokaalSensor(coordinator, entry.entry_id)" in (MAP / "sensor.py").read_text()
    assert '"luchtreiniger_lokaal"' in (MAP / "diagnostics.py").read_text()
    assert "luchtreiniger.async_stop" in (MAP / "__init__.py").read_text()
    assert "sensor.woonkamer_energy_management_system_luchtreiniger_lokaal" in (
        MAP / "dashboard_template.yaml").read_text()


def test_hele_lus_tegen_een_nep_apparaat(monkeypatch):
    """Een 3.3-apparaat op localhost dat elke vraag beantwoordt."""
    async def _proef():
        gevraagd = []

        async def _apparaat(reader, writer):
            buf = b""
            while True:
                stuk = await reader.read(4096)
                if not stuk:
                    break
                buf += stuk
                while tl.frame_lengte(buf) and len(buf) >= tl.frame_lengte(buf):
                    n = tl.frame_lengte(buf)
                    gevraagd.append(tl.pak_uit(buf[:n], None, retcode=False).opdracht)
                    buf = buf[n:]
                    writer.write(V33_ANTWOORD)
                    await writer.drain()

        server = await asyncio.start_server(_apparaat, "127.0.0.1", 0)
        poort = server.sockets[0].getsockname()[1]
        monkeypatch.setattr(ll, "TCP_POORT", poort)
        monkeypatch.setattr(ll, "VRAAG_S", 0.2)
        apparaat = SimpleNamespace(
            id=DEV, name="PureFlow70Pro", category="kj", local_key=SLEUTEL,
            local_strategy={"1": {"status_code": "switch"}, "2": {"status_code": "pm25"},
                            "3": {"status_code": "mode"}},
            status={"switch": True, "pm25": 7, "mode": "auto"},
        )
        m = ll.LuchtreinigerLokaalMeelezer(SimpleNamespace())
        m._apparaat, m.dev_id, m._sleutel = apparaat, DEV, SLEUTEL
        m.strategie = ll.strategie_uit(apparaat.local_strategy)
        m.tellingen["ip"], m.tellingen["versie"] = "127.0.0.1", "3.3"
        taak = asyncio.create_task(m._verbinding())
        await asyncio.sleep(0.7)
        taak.cancel()
        server.close()
        return m, gevraagd

    m, gevraagd = asyncio.run(_proef())
    assert gevraagd and set(gevraagd) == {tl.DP_VRAAG}
    assert m.tellingen["gelukt"] >= 2 and m.dps == DPS
    a = m.attributen()
    assert a["waarden"] == {"switch": True, "pm25": 7, "mode": "auto"}
    assert a["onbekende_dps"] == {"5": 0}
    assert a["per_code"]["switch"]["overeenkomst_procent"] == 100.0
