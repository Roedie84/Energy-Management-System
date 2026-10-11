"""v5.85: de luchtreiniger sturen over het lokale netwerk.

Gemeten op 11 oktober (Ruud zette hem met de hand langs alle standen): de
modus kent lokaal low, mid, high, turbo, auto en sleep; de cloud beschrijft
alleen auto en sleep en blijft bij de andere hangen.
"""
import asyncio
import json
from types import SimpleNamespace

from custom_components.energy_management_system import luchtreiniger_lokaal as ll
from custom_components.energy_management_system import tuya_lokaal as tl

SLEUTEL = "0123456789abcdef"
DEV = "bf46d22d435c249d12mwmw"
STRATEGIE = {"1": "switch", "2": "pm25", "3": "mode"}
LOCAL_STRATEGY = {
    "1": {"status_code": "switch", "config_item": {"valueType": "Boolean", "valueDesc": "{}"}},
    "3": {"status_code": "mode", "config_item": {"valueType": "Enum",
                                                  "valueDesc": "{\"range\":[\"auto\",\"sleep\"]}"}},
}


def test_standen_zoals_gemeten():
    assert ll.STANDEN == ("uit", "low", "mid", "high", "turbo", "auto", "sleep")


def test_opdracht_per_stand():
    assert ll.opdracht_voor("turbo", {"1": True, "3": "auto"}, STRATEGIE) == {"3": "turbo"}
    assert ll.opdracht_voor("low", {"1": False, "3": "auto"}, STRATEGIE) == {"1": True, "3": "low"}
    assert ll.opdracht_voor("uit", {"1": True}, STRATEGIE) == {"1": False}
    for fout in ("snel", "pm25"):
        try:
            ll.opdracht_voor(fout, {}, STRATEGIE)
        except ValueError:
            continue
        raise AssertionError(fout)


def test_stand_uit_datapunten():
    assert ll.stand_uit({"1": False, "3": "mid"}, STRATEGIE) == "uit"
    assert ll.stand_uit({"1": True, "3": "mid"}, STRATEGIE) == "mid"
    assert ll.stand_uit({}, STRATEGIE) is None


def test_buiten_het_cloudbereik_niet_vergelijken():
    bereik = ll.bereik_uit(LOCAL_STRATEGY)
    assert bereik == {"mode": {"auto", "sleep"}}
    t = ll.lege_tellingen()
    ll.vergelijk(t, {"3": "low"}, {"mode": "high"}, STRATEGIE, bereik)
    ll.vergelijk(t, {"3": "auto"}, {"mode": "auto"}, STRATEGIE, bereik)
    assert t["per_code"]["mode"] == {"n": 1, "gelijk": 1, "buiten_cloud": 1}


def test_oude_modustelling_begint_opnieuw():
    t = ll.herstel({"rondes": 57, "per_code": {"mode": {"n": 57, "gelijk": 29}}})
    assert t["per_code"] == {} and t["rondes"] == 57 and t["schema"] == ll.SCHEMA
    t = ll.herstel({"schema": ll.SCHEMA, "per_code": {"mode": {"n": 5, "gelijk": 5}}})
    assert t["per_code"] == {"mode": {"n": 5, "gelijk": 5}}


def test_sturing_inhoud_per_versie():
    op, inhoud = tl.sturing_inhoud("3.5", DEV, {"3": "turbo"})
    data = json.loads(inhoud)
    assert op == tl.STURING_NIEUW and data["protocol"] == 5 and data["data"]["dps"] == {"3": "turbo"}
    op, inhoud = tl.sturing_inhoud("3.3", DEV, {"1": False})
    data = json.loads(inhoud)
    assert op == tl.STURING and data["devId"] == DEV and data["dps"] == {"1": False}


def test_stand_zetten_tegen_een_nep_apparaat(monkeypatch):
    """Een 3.3-apparaat dat een stuuropdracht uitvoert en meldt."""
    async def _proef():
        ontvangen = []
        toestand = {"1": True, "2": 3, "3": "auto"}

        def _antwoord(cmd, dps):
            s = tl.Sessie(SLEUTEL, "3.3")
            body = json.dumps({"devId": DEV, "dps": dps}).encode()
            versleuteld = tl.ecb_versleutel(s.sleutel, body)
            if cmd == tl.STATUS:
                versleuteld = tl.versiekop("3.3") + versleuteld
            return tl.pak_55aa(1, cmd, b"\x00\x00\x00\x00" + versleuteld)

        async def _apparaat(reader, writer):
            buf = b""
            while True:
                stuk = await reader.read(4096)
                if not stuk:
                    break
                buf += stuk
                while tl.frame_lengte(buf) and len(buf) >= tl.frame_lengte(buf):
                    n = tl.frame_lengte(buf)
                    frame, buf = buf[:n], buf[n:]
                    b = tl.pak_uit(frame, None, retcode=False)
                    inhoud = b.inhoud
                    if inhoud.startswith(b"3.3"):
                        inhoud = inhoud[15:]
                    data = json.loads(tl.ecb_ontsleutel(SLEUTEL.encode(), inhoud))
                    if b.opdracht == tl.STURING:
                        ontvangen.append(data["dps"])
                        toestand.update(data["dps"])
                        writer.write(_antwoord(tl.STATUS, data["dps"]))
                    else:
                        writer.write(_antwoord(tl.DP_VRAAG, toestand))
                    await writer.drain()

        server = await asyncio.start_server(_apparaat, "127.0.0.1", 0)
        monkeypatch.setattr(ll, "TCP_POORT", server.sockets[0].getsockname()[1])
        monkeypatch.setattr(ll, "VRAAG_S", 0.3)
        m = ll.LuchtreinigerLokaalMeelezer(SimpleNamespace())
        m._apparaat = SimpleNamespace(status={"switch": True, "mode": "auto"})
        m.dev_id, m._sleutel, m.strategie = DEV, SLEUTEL, dict(STRATEGIE)
        m.tellingen["ip"], m.tellingen["versie"] = "127.0.0.1", "3.3"
        gezien = []
        m.luister(lambda: gezien.append(m.stand))
        taak = asyncio.create_task(m._verbinding())
        await asyncio.sleep(0.4)
        assert m.stand == "auto"
        assert await m.async_zet_stand("turbo") is True
        assert await m.async_zet_stand("uit") is True
        taak.cancel()
        server.close()
        return m, ontvangen, gezien

    m, ontvangen, gezien = asyncio.run(_proef())
    assert ontvangen == [{"3": "turbo"}, {"1": False}]
    assert m.stand == "uit" and "turbo" in gezien
    a = m.attributen()
    assert a["sturen"]["opdrachten"] == 2 and a["sturen"]["bevestigd"] == 2


def test_zonder_verbinding_een_duidelijke_fout():
    m = ll.LuchtreinigerLokaalMeelezer(SimpleNamespace())
    try:
        asyncio.run(m.async_zet_stand("low"))
    except ConnectionError:
        return
    raise AssertionError("geen fout zonder verbinding")


def test_keuzelijst_meldt_zich_ook_later_aan():
    """v5.85.1: na een herstart start het meelezen pas na de platforms; de
    keuzelijst bleef dan onbeschikbaar. Nu kijkt hij elke 10 s opnieuw."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "select.py").read_text()
    assert "_attr_should_poll = True" in bron
    assert "async def async_update" in bron and "self._meld_aan()" in bron
