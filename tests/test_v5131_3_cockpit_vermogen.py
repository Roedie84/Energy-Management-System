"""v5.131.3: het vermogen in Huis en apparaten, als een apparaat bezig is of laadt.

Gevraagd 26-10 (bij de cockpitregels Fietsladers, Steelstofzuiger, Batterijlader
keuken, Vaatwasser, Wasmachine): "Laat hierbij ook de vermogens zien in de
tekst als actief of als er geladen wordt indien mogelijk".
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import custom_components.energy_management_system as pkg

COMP = Path(pkg.__file__).parent
JS = (COMP / "www" / "ems-cockpit.js").read_text(encoding="utf-8")
SENSOR = (COMP / "sensor.py").read_text(encoding="utf-8")


def _const(naam):
    """Een losse top-level const uit de cockpit: één regel, of tot de "};"."""
    regels = JS.splitlines()
    begin = next(i for i, r in enumerate(regels) if r.startswith(f"const {naam} = "))
    if regels[begin].rstrip().endswith(";"):
        return regels[begin] + "\n"
    eind = next(i for i in range(begin, len(regels)) if regels[i] == "};")
    return "\n".join(regels[begin:eind + 1]) + "\n"


def _node(expr):
    code = "".join(
        _const(n)
        for n in ("ONBRUIKBAAR", "bruikbaar", "getal", "attr", "num", "STREEP", "MIN", "fmt",
                  "APPARAAT_ACTIEF", "apparaatVermogen", "vermogenTekst")
    )
    uit = subprocess.run(["node", "-e", code + f"console.log(JSON.stringify({expr}));"],
                         capture_output=True, text=True, check=True)
    return json.loads(uit.stdout)


def test_status_sensoren_noemen_hun_vermogenssensor():
    assert SENSOR.count('"vermogen_sensor": self._coordinator.config.get(') == 4
    for conf in ("CONF_STEELSTOFZUIGER_POWER_SENSOR", "CONF_FIETSLADERS_POWER_SENSOR",
                 "CONF_BATTERIJLADER_POWER_SENSOR"):
        assert f'"vermogen_sensor": self._coordinator.config.get({conf})' in SENSOR
    assert "_power_conf = CONF_DISHWASHER_POWER_SENSOR" in SENSOR
    assert "_power_conf = CONF_WASHING_MACHINE_POWER_SENSOR" in SENSOR


def test_huis_gebruikt_het_vermogen():
    huis = JS.split("  _huis() {")[1].split("  /* ---- geld ---- */")[0]
    assert "apparaatVermogen(s, this._hass.states)" in huis
    assert "vermogenTekst(p)" in huis


def test_huis_wordt_ververst_bij_nieuw_vermogen():
    zet = JS.split("  set hass(hass) {")[1].split("  get hass() {")[0]
    assert "APPARAAT_SLEUTELS" in zet and '"vermogen_sensor"' in zet
    assert 'this._vuil.add("huis")' in zet


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js niet aanwezig")
def test_alleen_bij_laden_of_bezig():
    states = {"sensor.p": {"state": "5.13", "attributes": {}}}
    def st(stand, sensor="sensor.p"):
        return json.dumps({"state": stand, "attributes": {"vermogen_sensor": sensor}})
    s = json.dumps(states)
    assert _node(f"apparaatVermogen({st('aan_het_laden')}, {s})") == 5.13
    assert _node(f"apparaatVermogen({st('actief')}, {s})") == 5.13
    assert _node(f"apparaatVermogen({st('test_aan')}, {s})") is None
    assert _node(f"apparaatVermogen({st('voltooid')}, {s})") is None
    assert _node(f"apparaatVermogen({st('aan_het_laden', 'sensor.weg')}, {s})") is None
    assert _node(f"apparaatVermogen({st('aan_het_laden', None)}, {s})") is None


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js niet aanwezig")
def test_vermogenstekst():
    assert _node("vermogenTekst(5.13)") == "5,1 W"
    assert _node("vermogenTekst(42.4)") == "42 W"
    assert _node("vermogenTekst(1834)") == "1,83 kW"
