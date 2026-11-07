"""v5.189.1: de economische schaduw plande alleen als het EERSTE plan van een
kwartier via `_async_bereken_waardeplan` liep.

Live 05-11 18:30 - 07-11 09:30: `open_dag` bleef op 05-11 met 8 kwartieren, 0
dagregels, virtueel 0,9/0,9 kWh, sensor niet meer geschreven. In de ronde vraagt
`_secundaire_laag` -> `_waardeplan_gaat_sturen` -> `_waardeplan_nu` het plan
eerst SYNCHROON (`bereken_waardeplan`, zonder schaduwhaak); dat vult de cache
en `_async_waardeplan_nu` krijgt daarna het gecachte plan. De schaduw plande
zo bijna nooit en de 14-daagse evaluatie kwam niet op gang.
"""
import asyncio
from datetime import timedelta

from tests.test_v5187_schaduw_sturing import T0, _Laag, _coordinator


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _productievolgorde(c, laag, n, synchroon_eerst=True):
    await c.async_laad_economische_schaduw()
    c._opstart_stuurstil = lambda now: False
    for i in range(n):
        grens = T0 + timedelta(minutes=15 * i)
        laag.meet(grens - timedelta(minutes=15))
        c._meetlaag_object = lambda: laag
        c._meetlaag_kwartier(grens)
        now = grens + timedelta(seconds=30)
        if synchroon_eerst:
            c._waardeplan_gaat_sturen(now, [])          # zoals _secundaire_laag
        await c._async_waardeplan_nu(now, [])            # zoals _waardeplan_als_nodig
        taak = c._schaduw_taak
        if taak is not None and hasattr(taak, "__await__"):
            await taak
        c._inhoud = max(0.0, c._inhoud - 0.15 / 0.919)


def test_synchroon_eerste_plan_voedt_de_schaduw(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    _run(_productievolgorde(c, _Laag(), 12, synchroon_eerst=True))
    rijen = c._schaduw_boek.rijen
    assert len(rijen) == 11                     # het eerste kwartier had nog geen plan
    assert {r[1] for r in rijen} == {"ok"}


def test_async_eerst_blijft_gelijk(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    _run(_productievolgorde(c, _Laag(), 12, synchroon_eerst=False))
    assert len(c._schaduw_boek.rijen) == 11


def test_een_schaduwplan_per_kwartier_ook_met_beide_paden(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    gestart = []
    origineel = c._schaduw_plannen_starten
    c._schaduw_plannen_starten = lambda *a: (gestart.append(a[0]["t"]), origineel(*a))
    _run(_productievolgorde(c, _Laag(), 6, synchroon_eerst=True))
    assert len(gestart) == len(set(gestart)) == 6


def test_dag_sluit_ook_via_het_synchrone_pad(make_coordinator, hass):
    c = _coordinator(make_coordinator, hass)
    _run(_productievolgorde(c, _Laag(), 100, synchroon_eerst=True))
    boek = c._schaduw_boek
    assert [d["date"] for d in boek.dagen] == ["2026-11-05"]
    assert boek.open_dag["dag"] == "2026-11-06"


def test_temperatuurnotitie_past_in_de_toestand():
    """v5.189.1: 'Geen voorspelling bij 2.3°C: ...' was > 255 tekens -> unknown."""
    from custom_components.energy_management_system.sensor import ModelTrendInsightSensor

    class _C:
        last_temp_consumption_note = (
            "Geen voorspelling bij 2.3°C: Het geleerde verband is positief: warmer gaat samen met "
            "meer verbruik. Dat kan in de zomer kloppen - koeling, koelkast - maar dit model is voor "
            "koude nachten, waar het verband omgekeerd hoort te zijn. Niet toegepast onder het gemeten bereik.")
    s = ModelTrendInsightSensor.__new__(ModelTrendInsightSensor)
    s._coordinator = _C()
    assert len(_C.last_temp_consumption_note) > 255
    waarde = s.native_value
    assert len(waarde) <= 255 and waarde.startswith("Geen voorspelling bij 2.3°C")
    assert s._coordinator.last_temp_consumption_note == _C.last_temp_consumption_note  # attribuut houdt alles
