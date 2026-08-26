"""Eén fout mag de ronde niet platleggen (v3.8.0).

Gemeld met twee screenshots: "unknown / Verwachte modus" en "nog geen
beslissing / nog geen schema". De planning was niet berekend - en dat had
niets met de planning te maken.

Aan het eind van elke ronde stonden twintig aanroepen ongeschermd op een
rij: dagkosten, beslislogboek, accukoeling, zelfvoorziening, CO2,
klimaatleren. De NameError in de accukoeling (v3.7.1) brak de hele ronde
af, dus alles daarna verviel - en de ronde eindigde nooit succesvol.

Gevolg: geen beslissing, geen schema, geen planning. Een leerroutine die
omvalt legde de aansturing plat.
"""
import asyncio

from custom_components.energy_management_system.const import CONF_PRICE_SENSOR


def test_a_failing_step_does_not_stop_the_others(make_coordinator, hass):
    c = make_coordinator({})
    gedaan = []

    def _valt_om():
        raise ValueError("proef")

    c._voer_staartstap_uit("eerste", lambda: gedaan.append("eerste"))
    c._voer_staartstap_uit("omvaller", _valt_om)
    c._voer_staartstap_uit("derde", lambda: gedaan.append("derde"))

    assert gedaan == ["eerste", "derde"]


def test_a_failing_step_is_recorded(make_coordinator, hass):
    """Stil overslaan zou net zo erg zijn: dan werkt de integratie half
    zonder dat iemand het merkt - de fout die v2.2.4 al opleverde."""
    c = make_coordinator({})

    c._voer_staartstap_uit("proefonderdeel", lambda: 1 / 0)

    assert any("proefonderdeel" in k for k in c.internal_failures)


def test_the_tick_still_finishes_when_cooling_fails(
    make_coordinator, hass
):
    """Het gemelde geval: de accukoeling viel om en de hele ronde ging
    mee."""
    c = make_coordinator({CONF_PRICE_SENSOR: "sensor.prijs"})

    async def _valt_om():
        raise RuntimeError("koeling stuk")

    c._async_apply_battery_cooling = _valt_om

    asyncio.run(c.async_setup())
    asyncio.run(c.async_update())

    assert c.last_successful_update is not None


def test_no_tail_step_is_left_unguarded():
    """Vangnet: komt er een aanroep bij aan het eind van de ronde, dan
    hoort die door dezelfde afscherming te lopen."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    kop = bron.index("# v3.8.0: elk staartonderdeel apart afgeschermd.")
    blok = bron[kop : kop + 3000]

    # Alles wat hier draait, loopt via de afscherming of een eigen
    # try/except.
    losse = [
        r.strip()
        for r in blok.splitlines()
        if r.startswith("        self._update_")
        or r.startswith("        await self._async_")
    ]

    assert not losse, f"ongeschermde stap in het staartstuk: {losse}"
