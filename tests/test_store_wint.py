"""De opslag is leidend; de sensor is het vangnet (v4.1).

Op de lijst als tweede structurele punt. Tweeëntwintig sensoren zetten
bij het opstarten hun geleerde reeks terug uit hun eigen attributen -
onvoorwaardelijk, dus ook over wat de Store net had teruggezet heen.
Dat beet in v3.99.11 (de wasmachine kreeg zijn zes-minuten-cycli terug),
en het hangt aan de 16 kB-grens van de recorder (v3.99.16).

Niet 57 toekenningen in 22 sensoren stuk voor stuk ombouwen: dat is
precies het werk waar in elke sensor een andere fout in sluipt. In
plaats daarvan één regel op alle herstelroutes tegelijk. `_store_wint`
neemt vóór het herstel een afdruk van de coördinator, laat de sensor
zijn gang gaan, en zet daarna elk veld dat de sensor veranderde terug
naar de Store-waarde - tenzij die Store-waarde nog de beginwaarde was.
De sensor wint dus alleen als de Store niets had.
"""
import asyncio

import pytest


class _Kaal:
    def __init__(self):
        self._beginwaarden = {}
        self.reeks = []
        self.getal = 0.0
        self.woordenboek = {}
        self._beginwaarden = {"reeks": [], "getal": 0.0, "woordenboek": {}}


class _Sensor:
    def __init__(self, c, uit_entiteit):
        self._coordinator = c
        self._uit = uit_entiteit

    async def _herstel(self):
        for k, v in self._uit.items():
            setattr(self._coordinator, k, v)


def _wrap(sensor):
    from custom_components.energy_management_system.sensor import _store_wint

    return _store_wint(sensor.__class__._herstel)


def test_de_sensor_wint_als_de_store_leeg_was():
    c = _Kaal()
    s = _Sensor(c, {"reeks": [1, 2], "getal": 3.5})

    asyncio.run(_wrap(s)(s))

    assert c.reeks == [1, 2]
    assert c.getal == 3.5


def test_de_store_wint_als_die_al_iets_had():
    c = _Kaal()
    c.reeks = [9, 9, 9]           # net uit de Store
    c.getal = 7.0
    s = _Sensor(c, {"reeks": [1, 2], "getal": 3.5})

    asyncio.run(_wrap(s)(s))

    assert c.reeks == [9, 9, 9]
    assert c.getal == 7.0


def test_velden_die_de_sensor_niet_raakt_blijven(make_coordinator, hass):
    c = _Kaal()
    c.woordenboek = {"a": 1}
    s = _Sensor(c, {"reeks": [1]})

    asyncio.run(_wrap(s)(s))

    assert c.woordenboek == {"a": 1}
    assert c.reeks == [1]


def test_elke_sensorherstelroute_draagt_de_regel():
    """Alle `async_added_to_hass` in sensor.py die iets op de coordinator
    zetten, staan onder `_store_wint`."""
    import ast
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    boom = ast.parse((Path(pkg.__file__).parent / "sensor.py").read_text())
    # Sensoren die bewust SAMENVOEGEN (vereniging van Store en entiteit)
    # in plaats van terugzetten. Daar hoort de omhulling niet op.
    SAMENVOEGERS = {"NilmConfirmedDevicesSensor", "ReserveShortfallSensor", "ReserveExcessSensor"}
    zonder = []
    for kl in ast.walk(boom):
        if not isinstance(kl, ast.ClassDef):
            continue
        for fn in kl.body:
            if isinstance(fn, ast.AsyncFunctionDef) and fn.name == "async_added_to_hass":
                bron = ast.unparse(fn)
                zet = "self._coordinator" in bron and ("setattr(" in bron or "= " in bron)
                gedecoreerd = any(getattr(d, "id", "") == "_store_wint" for d in fn.decorator_list)
                if zet and not gedecoreerd and kl.name not in SAMENVOEGERS:
                    zonder.append(kl.name)
    assert not zonder, zonder


def test_de_beginwaarden_worden_vastgelegd(make_coordinator, hass):
    c = make_coordinator({})
    assert isinstance(c._beginwaarden, dict)
    assert "reserve_daily_records" in c._beginwaarden
