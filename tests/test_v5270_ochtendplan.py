"""v5.270.0: het plan van 06:00 in de grafiek Prijs en lading.

Ruud, 27-11: "De voorspelling stelt telkens bij, is er ook een mogelijkheid
dat zichtbaar wordt wat de planning oorspronkelijk was (bijvoorbeeld om 6 uur
's morgens)?" Na een voorbeeld: ook de staafkleuren, alleen 06:00.
"""
import json
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from custom_components.energy_management_system import const

JS_PAD = Path(__file__).parent.parent / "custom_components" / "energy_management_system" / "www" / "ems-cockpit.js"
JS = JS_PAD.read_text(encoding="utf-8")
NODE = shutil.which("node") is None


def _plan(start, n=8, gat_na=None):
    rijen = []
    for i in range(n):
        t = start + timedelta(minutes=15 * i)
        if gat_na is not None and i > gat_na:
            t += timedelta(minutes=15)
        rijen.append({"start": t.isoformat(), "soc_procent": 80 - i, "tekort": i == 5,
                      "modus": "smart_charging (sparen)" if i < 3 else "smart_discharging"})
    return rijen


def _coord(make_coordinator, plan, tz):
    c = make_coordinator({})
    c.get_quarter_plan = lambda now=None: plan
    c._plan_startvoorraad_kwh = lambda: 6.0
    return c


def test_vastgelegd_om_zes_uur_met_modus_vermogen_en_tekort(make_coordinator, monkeypatch):
    from custom_components.energy_management_system import coordinator as cm
    monkeypatch.setattr(cm.planvolging, "vermogens_per_kwartier",
                        lambda plan, voorraad: [{"accu_w": -300.4 if i < 3 else 900.0} for i in range(len(plan))])
    zes = datetime(2026, 11, 27, 6, 0)
    c = _coord(make_coordinator, _plan(zes), None)
    c._werk_ochtendplan_bij(zes.replace(hour=5, minute=59))
    assert c.ochtendplan is None                      # voor 06:00 niets
    c._werk_ochtendplan_bij(zes)
    o = c.ochtendplan
    assert o["om"] == "06:00" and o["datum"] == "2026-11-27" and o["begin"] == zes.isoformat()
    assert o["soc"] == [80, 79, 78, 77, 76, 75, 74, 73]
    assert o["modi"] == ["smart_charging (sparen)", "smart_discharging"]
    assert o["m"] == [0, 0, 0, 1, 1, 1, 1, 1] and o["a"][0] == -300 and o["a"][3] == 900
    assert o["tekort"] == [5]
    # de rest van de dag niet overschrijven
    c.get_quarter_plan = lambda now=None: _plan(zes + timedelta(hours=3))
    c._werk_ochtendplan_bij(zes + timedelta(hours=3))
    assert c.ochtendplan["om"] == "06:00"
    assert c.get_ochtendplan(zes + timedelta(hours=5))["om"] == "06:00"
    assert c.get_ochtendplan(zes + timedelta(days=1)) is None       # van gisteren
    # de volgende dag om 06:00 een nieuw plan
    c._werk_ochtendplan_bij(zes + timedelta(days=1))
    assert c.ochtendplan["datum"] == "2026-11-28"


def test_na_een_herstart_later_op_de_dag_met_het_echte_tijdstip(make_coordinator):
    t = datetime(2026, 11, 27, 7, 12)
    c = _coord(make_coordinator, _plan(t.replace(minute=15)), None)
    c._werk_ochtendplan_bij(t)
    assert c.ochtendplan["om"] == "07:12"


def test_een_gat_in_het_plan_beeindigt_de_reeks(make_coordinator):
    zes = datetime(2026, 11, 27, 6, 0)
    c = _coord(make_coordinator, _plan(zes, gat_na=3), None)
    c._werk_ochtendplan_bij(zes)
    assert len(c.ochtendplan["soc"]) == 4


def test_overleeft_een_herstart_en_staat_op_de_planningssensor():
    assert const.PERSISTED_FIELDS["ochtendplan"] == {"type": "plain"}
    assert const.OCHTENDPLAN_UUR == 6
    sensor = (JS_PAD.parent.parent / "sensor.py").read_text(encoding="utf-8")
    assert '"kwartierplanning", "laadplan_gewijzigd", "planvolging", "ochtendplan"' in sensor


def test_cockpit_is_puur_ascii():
    assert all(ord(t) < 128 for t in JS)


@pytest.mark.skipif(NODE, reason="Node.js niet aanwezig")
def test_grafiek_tekent_stippellijn_strook_en_legenda(tmp_path):
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
const rijen = [];
for (let i = 0; i < 16; i++) {
  const d = new Date(nu.getTime() + i * 900000);
  rijen.push({ start: d.toISOString(), van: d.toTimeString().slice(0, 5), prijs_ct: 25, soc_procent: 60 - i,
               modus: "smart_discharging", accu_w: 500 });
}
const begin = new Date(nu.getTime() - 2 * 900000);
const ochtend = { datum: "x", om: "06:00", begin: begin.toISOString(),
  soc: Array.from({ length: 20 }, (_, i) => 80 - i),
  modi: ["smart_charging (sparen)", "manual (verkopen)"], m: Array.from({ length: 20 }, (_, i) => (i < 6 ? 0 : 1)),
  a: Array.from({ length: 20 }, () => 0), tekort: [] };
let states = { plan: { state: "ok", attributes: { kwartierplanning: rijen, ochtendplan: ochtend } }, soc: { state: "60" } };
o._ids = {}; o._s = (k) => states[k];
o._live = () => ({ accu: 500, zon: 0, net: 0, huis: 0 });
const tijden = rijen.map((r) => new Date(r.start));
const g = o._planGrafiek(rijen, tijden);
const blokjes = ((g.match(/<div class="g-strook">(.*?)<\\/div>/) || [])[1] || "").match(/<i /g) || [];
states = { plan: { state: "ok", attributes: { kwartierplanning: rijen } }, soc: { state: "60" } };
const zonder = o._planGrafiek(rijen, tijden);
console.log(JSON.stringify({
  lijn: /soc-ochtend" points="[^"]+"/.test(g), metOchtend: g.includes('class="gwrap met-ochtend"'),
  label: g.includes('<div class="g-strook-l">06:00</div>'), blokjes: blokjes.length, staven: (g.match(/class="staaf/g) || []).length,
  legenda: g.includes("plan van 06:00"), verkopenInLegenda: />verkopen</.test(g.split('pl-legenda')[1] || ""),
  zonderLijn: zonder.includes("soc-ochtend"), zonderStrook: zonder.includes("g-strook"), zonderKlasse: zonder.includes("met-ochtend") }));
""",
        encoding="utf-8",
    )
    uit = subprocess.run(["node", str(script), str(JS_PAD)], capture_output=True, text=True, check=True)
    r = json.loads(uit.stdout.strip().splitlines()[-1])
    assert r["lijn"] and r["metOchtend"] and r["label"] and r["legenda"]
    assert r["blokjes"] == r["staven"] == 16          # een blokje per staaf
    assert r["verkopenInLegenda"]                     # kleur die alleen het ochtendplan had
    assert not (r["zonderLijn"] or r["zonderStrook"] or r["zonderKlasse"])
