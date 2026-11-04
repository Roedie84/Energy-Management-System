"""v5.179.1: zon terugleveren heet in de cockpit ook zo.

Gemeld 04-11 09:30 (screenshot): de Vooruitblik toonde 'Handmatig · in rust' voor
de kwartieren waarin het waardeplan de zon terug laat leveren
(modus 'manual (terugleveren)'), en de grafiek kleurde ze als rust.
"""
import json
import subprocess
from pathlib import Path

import custom_components.energy_management_system as pkg

JS = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")


def _const(naam):
    regels = JS.splitlines()
    begin = next(i for i, r in enumerate(regels) if r.startswith(f"const {naam} = "))
    if regels[begin].rstrip().endswith(";"):
        return regels[begin] + "\n"
    eind = next(i for i in range(begin, len(regels)) if regels[i] in ("};", "];"))
    return "\n".join(regels[begin:eind + 1]) + "\n"


def _node(expr):
    code = "".join(_const(n) for n in ("STREEP", "hoofd", "MODI", "modus", "getal", "num", "DOEN", "doen"))
    uit = subprocess.run(["node", "-e", code + f"console.log(JSON.stringify({expr}));"],
                         capture_output=True, text=True, check=True)
    return json.loads(uit.stdout)


def test_modus_terugleveren():
    assert _node('modus("manual (terugleveren)").label') == "Zon terugleveren"
    assert _node('modus("manual (laden)").k') == "laden"
    assert _node('modus("manual").label') == "Handmatig"


def test_grafiek_kleurt_terugleveren_apart():
    assert _node('doen({modus: "manual (terugleveren)", accu_w: 0})') == "terug"
    assert _node('doen({modus: "smart", accu_w: -600})') == "zon"


def test_vooruitblik_toont_terugleververmogen():
    vb = JS.split("  _vooruitblik(rijen, tijden) {")[1].split("  /* v5.146.0")[0]
    assert 'b.k === "terug"' in vb and "levert ${" in vb
    assert "b.net.push" in JS
