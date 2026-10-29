"""v5.146.0 - Vooruitblik in de cockpit (akkoord Ruud 29-10, alle vier punten).

Naar een voorbeeld uit het Tweakers-topic (EMHASS): 8 kwartieren als tabel
met bladeren, per kwartier gepland accu-, net-, zon- en huisvermogen, de
accustand als balkje in de kleur van de stand, en een samenvatting van de
komende 2 uur en het eerstvolgende laden en verkopen. Alleen weergave.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import planvolging

JS_PAD = Path(pkg.__file__).parent / "www" / "ems-cockpit.js"


def test_vermogens_per_kwartier():
    rijen = [
        {"soc_kwh": 5.0, "uren": 0.25, "net_kwh": 0.0, "zon_kwh": 0.15, "verbruik_kwh": 0.4},
        {"soc_kwh": 4.75, "uren": 0.25, "net_kwh": 0.013, "zon_kwh": 0.0, "verbruik_kwh": 0.3},
        {"soc_kwh": 5.35, "uren": 0.25, "net_kwh": 0.6, "zon_kwh": 0.0, "verbruik_kwh": 0.0},
    ]

    uit = planvolging.vermogens_per_kwartier(rijen, start_kwh=5.25)

    assert [r["accu_w"] for r in uit] == [1000, 1000, -2400]  # + ontladen, - laden
    assert [r["net_w"] for r in uit] == [0, 52, 2400]
    assert uit[0]["zon_w"] == 600 and uit[0]["huis_w"] == 1600


def test_lopend_kwartier_telt_alleen_de_rest():
    """Het lopende kwartier telt voor de resterende tijd (`uren`), zoals de planvolging."""
    uit = planvolging.vermogens_per_kwartier(
        [{"soc_kwh": 4.9, "uren": 0.1, "net_kwh": 0.0}], start_kwh=5.0
    )
    assert uit[0]["accu_w"] == 1000


def test_zonder_startvoorraad_geen_accuwaarde_voor_het_eerste_kwartier():
    uit = planvolging.vermogens_per_kwartier(
        [{"soc_kwh": 5.0}, {"soc_kwh": 4.5}], start_kwh=None
    )
    assert uit[0]["accu_w"] is None
    assert uit[1]["accu_w"] == 2000


def test_compacte_planning_draagt_de_vermogens(make_coordinator, hass, monkeypatch):
    c = make_coordinator({})
    monkeypatch.setattr(
        c, "get_quarter_plan",
        lambda now=None: [{"van": "19:15", "soc_kwh": 4.0, "uren": 0.25, "net_kwh": 0.0,
                           "zon_kwh": 0.0, "verbruik_kwh": 0.3, "modus": "smart"}],
    )
    monkeypatch.setattr(c, "_plan_startvoorraad_kwh", lambda: 4.25)

    rij = c.get_quarter_plan_compact()[0]

    assert rij["accu_w"] == 1000 and rij["net_w"] == 0 and rij["huis_w"] == 1200
    assert rij["van"] == "19:15"


def test_de_cockpit_heeft_de_vooruitblik():
    js = JS_PAD.read_text(encoding="utf-8")
    assert "this._vooruitblik(rijen, tijden)" in js
    assert "data-blader" in js and "const VB_KWARTIEREN = 8;" in js
    assert "Komende 2 uur:" in js and "Eerstvolgende laden van net:" in js


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js niet aanwezig")
def test_de_vooruitblik_tekent(tmp_path):
    script = tmp_path / "rook.js"
    script.write_text(
        """
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
global.HTMLElement = class {}; global.HTMLTemplateElement = class {};
global.window = { customCards: [] };
global.customElements = { define: (n, c) => { if (!global.K) global.K = c; }, get: () => undefined };
global.document = { createElement: () => ({}) };
console.log = (() => { const echt = console.log; return (...a) => { if (String(a[0]).startsWith("{")) echt(...a); }; })();
eval(src);
const o = Object.create(global.K.prototype);
const nu = new Date(); nu.setMinutes(Math.floor(nu.getMinutes() / 15) * 15, 0, 0);
const rijen = [], tijden = [];
const modi = ["smart", "smart_discharging", "verkopen (expensive_quarter)", "manual (laden)"];
for (let i = 0; i < 20; i++) {
  const d = new Date(nu.getTime() + i * 900000); tijden.push(d);
  rijen.push({ van: d.toTimeString().slice(0, 5), prijs_ct: 30 + i, modus: modi[Math.floor(i / 3) % 4],
               soc_procent: 90 - i, accu_w: -800, net_w: 52, zon_w: 600, huis_w: 700 });
}
o._vbStart = 0;
const eerste = o._vooruitblik(rijen, tijden);
o._vbStart = 16;
const laatste = o._vooruitblik(rijen, tijden);
console.log(JSON.stringify({
  rijen1: (eerste.match(/<tr/g) || []).length, nu: eerste.includes("vb-nu"),
  rijen3: (laatste.match(/<tr/g) || []).length,
  samen: o._vooruitSamenvatting(rijen, tijden).replace(/<[^>]+>/g, "")
}));
""",
        encoding="utf-8",
    )
    uit = subprocess.run(["node", str(script), str(JS_PAD)], capture_output=True, text=True, check=True)
    r = json.loads(uit.stdout.strip().splitlines()[-1])
    assert r["rijen1"] == 9  # kop + 8 kwartieren
    assert r["nu"] is True
    assert r["rijen3"] == 5  # laatste bladzijde: 4 kwartieren
    assert r["samen"].startswith("Komende 2 uur: slim")
    assert "Eerstvolgende laden van net:" in r["samen"]
