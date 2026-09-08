"""Het PV-model blokkeerde de event loop (v3.99.20).

Gemeld met een cProfile-meting van zestig seconden:

    9,567 s   energy_management_system   (nummer twee: 0,135 s)
    5 calls   get_proefstand             2,72 s per aanroep
   10 calls   pv_model.leer              1,04 s per aanroep

`get_proefstand` traint het regressiewoud - synchroon, in de event loop,
en hij wordt door drie sensoren en de diagnostiek aangeroepen. Vijf keer
per minuut een woud van 18.900 bomen: HA stond dertien van die zestig
seconden stil. "Updating state for sensor...gacs_zelfbeoordeling took
2.624 seconds" was dezelfde klacht in een andere jas.

Drie dingen:
1. Trainen gebeurt in een executor, niet in de loop.
2. Hooguit eens per uur, of als er nieuwe monsters zijn.
3. Alles wat het resultaat leest - sensoren, proefstand, diagnostiek -
   leest een CACHE. Niemand traint nog inline.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def test_de_lezer_traint_niet(make_coordinator, hass):
    """`get_pv_model_evaluation` mag nooit meer zelf leren."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    i = bron.index("    def get_pv_model_evaluation(self)")
    j = bron.index("\n    def ", i + 10)
    assert "woud.leer(" not in bron[i:j]
    assert "RegressieWoud(" not in bron[i:j]


def test_zonder_cache_zegt_hij_dat(make_coordinator, hass):
    c = make_coordinator({})
    c._pv_model_evaluatie = None

    uit = c.get_pv_model_evaluation()

    assert uit["beschikbaar"] is False
    assert "berekend" in uit["reden"]


def test_de_cache_wordt_gelezen(make_coordinator, hass):
    c = make_coordinator({})
    c._pv_model_evaluatie = {"beschikbaar": True, "winst_procent": 5.8, "berekend_op": NU.isoformat()}

    assert c.get_pv_model_evaluation()["winst_procent"] == 5.8


@pytest.mark.asyncio
async def test_verversen_gaat_via_de_executor(make_coordinator, hass):
    c = make_coordinator({})
    c._pv_model_evaluatie = None
    aanroepen = []

    async def executor(func, *args):
        aanroepen.append(func.__name__)
        return {"beschikbaar": False, "reden": "toets"}

    hass.async_add_executor_job = executor

    await c.async_ververs_pv_model(NU)

    assert aanroepen == ["_bereken_pv_model_evaluatie"]
    assert c._pv_model_evaluatie["berekend_op"] == NU.isoformat()


@pytest.mark.asyncio
async def test_hooguit_eens_per_uur(make_coordinator, hass):
    from custom_components.energy_management_system.const import PV_MODEL_VERVERS_MINUTEN

    c = make_coordinator({})
    aanroepen = []

    async def executor(func, *args):
        aanroepen.append(1)
        return {"beschikbaar": False}

    hass.async_add_executor_job = executor
    c._pv_model_evaluatie = None

    await c.async_ververs_pv_model(NU)
    await c.async_ververs_pv_model(NU + timedelta(minutes=5))
    await c.async_ververs_pv_model(NU + timedelta(minutes=PV_MODEL_VERVERS_MINUTEN + 1))

    assert len(aanroepen) == 2


def test_de_zonvoorspelling_wordt_per_ronde_gecachet(make_coordinator, hass):
    """1.425 aanroepen van `_get_pv_forecast_entries` in zestig seconden -
    bijna 24 per seconde - voor een reeks die per half uur verandert."""
    c = make_coordinator({})
    teller = []
    origineel = c._lees_pv_forecast_entries
    c._lees_pv_forecast_entries = lambda: (teller.append(1), [])[1]

    c._begin_ronde_cache(NU)
    for _ in range(50):
        c._get_pv_forecast_entries()

    assert len(teller) == 1
