"""v5.231.0: een korte onderbreking van de lokale verbinding maakt de luchtreiniger niet onbeschikbaar.

Gemeten 11 t/m 13-11: de keuzelijst was 242 keer in 48 uur onbeschikbaar, telkens ~60 s.
"""

import asyncio
import inspect
import time
from types import SimpleNamespace

from custom_components.energy_management_system import luchtreiniger_lokaal as ll

STRATEGIE = {"1": "switch", "3": "mode"}


def _m():
    m = ll.LuchtreinigerLokaalMeelezer(SimpleNamespace())
    m.strategie = dict(STRATEGIE)
    m.dps = {"1": True, "3": "auto"}
    return m


def test_verbonden_is_beschikbaar():
    m = _m()
    m.verbonden = True
    assert m.beschikbaar is True


def test_kort_na_de_laatste_waarden_blijft_de_stand_bruikbaar():
    m = _m()
    m.verbonden = False
    m.dps_t = time.time() - 60
    assert m.beschikbaar is True and m.stand == "auto"


def test_na_de_marge_is_hij_onbeschikbaar():
    m = _m()
    m.dps_t = time.time() - ll.BESCHIKBAAR_MARGE_S - 1
    assert m.beschikbaar is False


def test_nooit_gelezen_is_onbeschikbaar():
    m = _m()
    m.dps_t = None
    assert m.beschikbaar is False


def test_een_klok_die_terugspringt_telt_niet_als_vers():
    m = _m()
    m.dps_t = time.time() + 3600
    assert m.beschikbaar is False


def test_wachttijd_begint_weer_kort_na_een_verbinding_die_werkte():
    assert ll.volgende_wachttijd(60.0, True) == ll.WACHT_BEGIN_S
    assert ll.volgende_wachttijd(40.0, False) == 40.0
    bron = inspect.getsource(ll.LuchtreinigerLokaalMeelezer._lus)
    assert "wacht = volgende_wachttijd(wacht, self._ronde_gelukt)" in bron
    assert "self._ronde_gelukt = True" in inspect.getsource(ll.LuchtreinigerLokaalMeelezer._verbinding)


def test_sturen_wacht_op_het_opnieuw_verbinden(monkeypatch):
    monkeypatch.setattr(ll, "WACHT_OP_VERBINDING_S", 2.0)

    async def _proef():
        m = _m()
        m.dps_t = time.time()

        async def _herstel():
            await asyncio.sleep(0.4)
            m._writer, m._sessie, m.verbonden = object(), object(), True

        taak = asyncio.create_task(_herstel())
        gelukt = await m._wacht_op_verbinding()
        await taak
        return gelukt

    assert asyncio.run(_proef()) is True


def test_sturen_geeft_op_als_de_verbinding_wegblijft(monkeypatch):
    monkeypatch.setattr(ll, "WACHT_OP_VERBINDING_S", 0.5)
    m = _m()
    m.dps_t = time.time()
    begin = time.monotonic()
    try:
        asyncio.run(m.async_zet_stand("mid"))
    except ConnectionError:
        assert 0.4 <= time.monotonic() - begin < 3
        return
    raise AssertionError("geen fout zonder verbinding")


def test_zonder_recente_waarden_meteen_een_fout():
    m = _m()
    begin = time.monotonic()
    try:
        asyncio.run(m.async_zet_stand("mid"))
    except ConnectionError:
        assert time.monotonic() - begin < 0.3
        return
    raise AssertionError("geen fout zonder verbinding")


def test_keuzelijst_gebruikt_beschikbaar():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "select.py").read_text()
    assert "m.beschikbaar and m.stand is not None" in bron
    assert "m.verbonden and m.stand is not None" not in bron
