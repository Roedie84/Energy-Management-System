"""v5.194.1: de cockpit sprong op de mobiel tijdens het scrollen naar boven.

Gemeld 08-11. Een sprong in één keer van ver omlaag naar boven, op hetzelfde
adres en zonder tik buiten de kaart, zet de kaart terug. Zelf naar boven
scrollen, een ander tabblad of het actieve tabblad opnieuw aantikken niet.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import custom_components.energy_management_system as pkg

JS = Path(pkg.__file__).parent / "www" / "ems-cockpit.js"
GEEN_NODE = shutil.which("node") is None


def _node(expr):
    js = JS.read_text(encoding="utf-8")
    regels = [r for r in js.splitlines() if r.startswith(("const SPRONG_", "const BUITEN_TIK_MS"))]
    begin = js.index("const isSprongNaarBoven")
    regels.append(js[begin:js.index(";\n", begin) + 1])
    code = "\n".join(regels) + f"\nconsole.log(JSON.stringify({expr}));"
    uit = subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True)
    return json.loads(uit.stdout)


@pytest.mark.skipif(GEEN_NODE, reason="Node.js niet aanwezig")
def test_alleen_een_echte_sprong_wordt_teruggezet():
    gevallen = [
        (1200, 0, True, 99999),    # sprong naar boven, zelfde pagina: terugzetten
        (1200, 0, False, 99999),   # andere pagina: niet
        (1200, 0, True, 200),      # net buiten de kaart getikt (actief tabblad): niet
        (150, 0, True, 99999),     # bijna boven: gewoon scrollen
        (1200, 900, True, 99999),  # stapje omhoog: gewoon scrollen
    ]
    uit = _node(f"{json.dumps(gevallen)}.map(([a, b, p, t]) => isSprongNaarBoven(a, b, p, t))")
    assert uit == [True, False, False, False, False]


def test_kaart_houdt_hoogte_vast_en_volgt_de_plek():
    js = JS.read_text(encoding="utf-8")
    assert "volgPlek();" in js and "PLEK.kaarten.add(this)" in js and "PLEK.kaarten.delete(this)" in js
    assert "el.style.minHeight = `${hoogte}px`" in js
