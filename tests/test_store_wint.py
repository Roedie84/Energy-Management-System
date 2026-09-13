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


# --- v4.9: de omhulling maakte kopieën van objecten --------------------
#
# Twee kaarten meldden "Nog geen voltooide dagen om mee te vergelijken"
# terwijl `deviation_history_percent` in de export zeven dagen bevatte.
# Twee lezers, twee uitkomsten - want de coordinator keek naar een ANDER
# object dan de export.
#
# De oorzaak is `_store_wint` zelf (v4.1). Die neemt vóór het herstel
# een `copy.copy()` van elk veld en zet daarna elk veld terug dat
# veranderd lijkt. Voor een lijst of dict is dat precies de bedoeling.
# Voor een OBJECT - de zonvoorspellingstracker, een Store, een lock -
# is de kopie nooit hetzelfde object, dus leek het altijd veranderd, en
# werd de coordinator op de kopie gezet. Die kopie leeft daarna zijn
# eigen leven: de tracker die de metingen bijhoudt is de originele, de
# tracker die de coordinator leest is een bevroren afdruk.
#
# De omhulling kijkt nu alleen naar velden met GEWONE gegevens - lijst,
# dict, set, getal, tekst, datum. Alle geleerde reeksen zijn dat; de
# objecten blijven onaangeroerd.


class _Tracker:
    def __init__(self):
        self.deviation_history = []


def test_objecten_worden_niet_gekopieerd():
    from custom_components.energy_management_system.sensor import _store_wint

    class _Kaal2:
        def __init__(self):
            self.tracker = _Tracker()
            self.reeks = []
            self._beginwaarden = {"tracker": None, "reeks": []}

    c = _Kaal2()
    origineel = c.tracker
    s = _Sensor(c, {"reeks": [1, 2]})

    asyncio.run(_store_wint(s.__class__._herstel)(s))

    assert c.tracker is origineel
    assert c.reeks == [1, 2]


def test_de_tracker_blijft_dezelfde_na_het_herstel():
    """Het gemelde geval: de reeks van de tracker moet blijven groeien
    op het object dat de coordinator leest."""
    from custom_components.energy_management_system.sensor import _store_wint

    class _Kaal3:
        def __init__(self):
            self.solar_tracker = _Tracker()
            self._beginwaarden = {"solar_tracker": None}

    c = _Kaal3()
    s = _Sensor(c, {})

    asyncio.run(_store_wint(s.__class__._herstel)(s))
    c.solar_tracker.deviation_history.append(-19.1)

    assert c.solar_tracker.deviation_history == [-19.1]


def test_alle_objectvelden_zijn_beschermd():
    """De ratel: elk veld op de coordinator dat een OBJECT is, moet
    buiten de omhulling blijven. Naast de zonvoorspellingstracker zijn
    dat de twee Stores en de twee locks - en die door een kopie
    vervangen zou stiller en erger zijn dan een lege kaart.
    """
    import re
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "sensor.py").read_text()
    i = bron.index("def _store_wint")
    j = bron.index("\ndef ", i + 10)
    blok = bron[i:j]

    assert "isinstance(v, GEWONE_GEGEVENS)" in blok
    for soort in ("list", "dict", "set", "int", "float", "str", "bool"):
        assert soort in blok, soort
