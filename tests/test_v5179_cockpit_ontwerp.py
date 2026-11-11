"""Energiecockpit als een rustig, samenhangend product (gemeld 04-11: "ziet eruit
als een samengeraapt zooitje").

Een kaartsoort, een typeschaal, een spatieschaal en kleur alleen waar het iets
betekent. Alle gegevens blijven zichtbaar; dat bewaken de inhoudstoetsen van
v5.178 (test_v5178_cockpit_compact.py) - hier alleen het ontwerp.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import custom_components.energy_management_system as pkg

JS_PAD = Path(pkg.__file__).parent / "www" / "ems-cockpit.js"
JS = JS_PAD.read_text(encoding="utf-8")
STIJL = JS.split("const STIJL = `")[1].split("`;")[0]


def test_geen_versiering_meer():
    for weg in ("radial-gradient", "backdrop-filter", "ACHTERGROND", "text-transform: uppercase",
                "letter-spacing: .1", "drop-shadow", "box-shadow: 0 0", ".tegel::before", ".tegel::after"):
        assert weg not in JS, weg
    # geen gekleurde randen per tegel meer
    assert "border-top: 2px solid" not in STIJL and "--accent" not in JS


def test_een_kaartsoort():
    kaart = STIJL.split(".tegel, .paneel {")[1].split("}")[0]
    for regel in ("padding: 16px", "border-radius: var(--r)", "background: var(--kaart)", "border: 1px solid var(--rand)"):
        assert regel in kaart
    assert "--kaart: #111827;" in STIJL and "--bg: #0b0f17;" in STIJL
    # elke kaart dezelfde kop (icoon + titel in zinsvorm, 13/600, vaste hoogte)
    assert ".ph { display: flex; align-items: center; gap: 8px; min-height: 28px;" in STIJL  # v5.215.0: chips mogen naar een tweede regel
    assert ".ph h2 { margin: 0; font-size: 13px; font-weight: 600;" in STIJL
    for kop in ('paneelKop("accu", "Accu nu")', 'paneelKop("klok", "Plan vandaag")',
                'paneelKop("euro", "Geld", "", "detail-besparing")'):
        assert kop in JS


def test_typeschaal_en_twee_gewichten():
    maten = {int(m) for m in re.findall(r"font-size: (\d+)px", STIJL)}
    assert maten <= {11, 12, 13, 15, 22, 30}, maten
    gewichten = set(re.findall(r"font-weight: (\d+)", STIJL))
    assert gewichten <= {"400", "600"}, gewichten


def test_spatieschaal():
    for waarde in re.findall(r"(?:padding|gap|margin)[a-z-]*: ([^;]+);", STIJL):
        for px in re.findall(r"(-?\d+)px", waarde):
            assert abs(int(px)) in {0, 1, 2, 4, 6, 8, 10, 12, 16, 24}, waarde


def test_een_statistiektegel_voor_alle_rasters():
    assert "const mini = (label, waarde, sub = \"\", kleur = \"\") => stat(label, waarde, sub, kleur);" in JS
    accu = JS.split("  _accu() {")[1].split("\n  }\n")[0]
    assert "const cel = (naam, waarde, sub, k) => stat(naam, waarde, sub, k);" in accu
    # betekenis: zon amber, net blauw, huis neutraal, accu violet
    for naam, kleur in (("Zon", "amber"), ("Net", "blauw"), ("Accu", "violet")):
        stuk = accu.split(f'cel("{naam}"')[1].split("cel(")[0]
        assert f"var(--{kleur})" in stuk


def test_bediening_gelijke_knoppen_en_aan_met_stip():
    assert ".knoppen { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }" in STIJL
    breed = JS.split("@container (min-width: 1260px)")[1].split("@container")[0]
    assert ".knoppen { grid-template-columns: repeat(3, minmax(0, 1fr)); }" in breed
    assert ".knop .aan-t { position: absolute;" in STIJL and ".knop.aan {" in STIJL


def test_modules_tijdens_opstarten_geen_foutmelding():
    m = JS.split("  _modules() {")[1].split("\n  }\n")[0]
    assert "Modulegegevens laden nog (EMS net gestart)." in m and "Geen modulegegevens." in m
    assert "10 * 60000" in m


def test_puur_ascii():
    JS.encode("ascii")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js niet aanwezig")
def test_modules_opstarten_en_gevuld(tmp_path):
    script = tmp_path / "m.js"
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
const S = {};
o._s = (k) => S[k];
S.modules = { state: "0", last_changed: new Date().toISOString(), attributes: { modules: [] } };
const net = o._modules();
S.modules.last_changed = new Date(Date.now() - 3600000).toISOString();
const later = o._modules();
S.modules.attributes.modules = [1, 2, 3].map((i) => ({ module: i, naam: "AB3000 0" + i, soc_percent: 16 + i,
  cel_min_v: 3.2, cel_max_v: 3.24, cel_delta_v: 0.04, temperatuur_c: 14, vermogen_w: 0, drift_op: [] }));
const vol = o._modules();
console.log(JSON.stringify({ net: net.includes("laden nog"), later: later.includes("Geen modulegegevens"),
  rijen: (vol.match(/class="modrij/g) || []).length }));
""",
        encoding="utf-8",
    )
    uit = subprocess.run(["node", str(script), str(JS_PAD)], capture_output=True, text=True, check=True)
    import json
    r = json.loads(uit.stdout.strip().splitlines()[-1])
    assert r == {"net": True, "later": True, "rijen": 3}
