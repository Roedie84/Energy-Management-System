"""v5.181.2 - cockpit-standen eenduidig, ladingslijn begint live (live 04-11 11:31-11:34).

(a) Tegel, kopchip, staaf, tijdlijn en Vooruitblik uit één weergave per kwartier;
    in de leermodus/handmatig zegt de tegel dat het EMS niet stuurt.
(b) De accustand-lijn begint bij "nu" op de live laadstand; de plan-soc telt
    vanaf dezelfde (effectieve) ondergrens als de inhoud.
(c) Planvolging 'gepland' uit het laatste plan; handmatig = geen afwijking.
(d) Eenheden boven de assen van Prijs en lading.
(e) Verschil in de goede richting.
(f) Het eigen logo in de kop, zelf geserveerd.
"""
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import planvolging as pv
from custom_components.energy_management_system import standweergave as sw

PAKKET = Path(pkg.__file__).parent
JS_PAD = PAKKET / "www" / "ems-cockpit.js"
JS = JS_PAD.read_text(encoding="utf-8")
T0 = datetime(2026, 11, 4, 10, 31, 0, tzinfo=timezone.utc)
NODE = shutil.which("node") is None


def _const(naam):
    regels = JS.splitlines()
    begin = next(i for i, r in enumerate(regels) if r.startswith(f"const {naam} = "))
    if regels[begin].rstrip().endswith(";"):
        return regels[begin] + "\n"
    eind = next(i for i in range(begin, len(regels)) if regels[i] in ("};", "];"))
    return "\n".join(regels[begin:eind + 1]) + "\n"


def _node(expr):
    namen = ("STREEP", "hoofd", "MODI", "modus", "getal", "num", "DOEN", "doen", "STAND_TOELICHTING",
             "STAND_RUST", "standSoort", "standWeergave", "kwartierWeergave", "STAND_HANDMATIG",
             "handmatigWeergave", "SOC_BLEND_MS", "socLijn", "verschilTekst")
    code = "const ONBRUIKBAAR = ['unknown', 'unavailable'];\nconst bruikbaar = (s) => !!s;\n"
    code += "".join(_const(n) for n in namen)
    uit = subprocess.run(["node", "-e", code + f"console.log(JSON.stringify({expr}));"],
                         capture_output=True, text=True, check=True)
    return json.loads(uit.stdout)


# --- (e) verschil in de goede richting -----------------------------------------

GEVALLEN = [
    (-2400, -1360, "minder laden"),     # live 11:34
    (-1000, -1800, "meer laden"),
    (1000, 1600, "meer ontladen"),
    (1600, 900, "minder ontladen"),
    (-2400, 800, "ontlaadt in plaats van laden"),
    (900, -700, "laadt in plaats van ontladen"),
    (-2400, 0, "laadt niet"),
    (1200, 20, "ontlaadt niet"),
    (0, -600, "laadt in plaats van rust"),
    (10, 700, "ontlaadt in plaats van rust"),
    (-1000, -1030, "geen"),
]


@pytest.mark.parametrize("gepland,gemeten,tekst", GEVALLEN)
def test_verschil_tekst_python(gepland, gemeten, tekst):
    assert pv.verschil_tekst(gepland, gemeten) == tekst


@pytest.mark.skipif(NODE, reason="Node.js niet aanwezig")
def test_verschil_tekst_cockpit_gelijk_aan_python():
    paren = json.dumps([[g, m] for g, m, _t in GEVALLEN])
    assert _node(f"{paren}.map(([g, m]) => verschilTekst(g, m))") == [t for _g, _m, t in GEVALLEN]


def test_beoordeel_gebruikt_de_juiste_richting():
    uit = pv.beoordeel({"accu_w": -2400, "zon_w": 1420, "huis_w": 300, "modus": "smart"}, -1360, 1720, 300)
    assert uit["verschil_tekst"] == "minder laden"
    assert uit["zon_verschil_tekst"] == "meer zon"


def test_cockpit_laat_het_verschil_niet_meer_omrekenen():
    assert "verschil_tekst: verschilTekst(gepland, live.accu)" in JS
    assert '"meer laden" : "meer ontladen"' not in JS


# --- (c) planvolging uit het laatste plan; handmatig ------------------------------


def _c(make_coordinator):
    c = make_coordinator({})
    c._read_corrected_battery_power = lambda: -1360.0
    c._live_pv_w = lambda: 1720.0
    c._read_corrected_consumption_power = lambda: 300.0
    c._planvolging_stand = lambda: "smart"
    c._opgedragen_vermogen_w = lambda now: None
    return c


def test_planvolging_gepland_uit_het_laatste_plan(make_coordinator, hass):
    c = _c(make_coordinator)
    plannen = iter([
        {"accu_w": -2400, "zon_w": 1420, "huis_w": 300, "modus": "manual (laden)"},   # 11:30:00
        {"accu_w": -1300, "zon_w": 1420, "huis_w": 300, "modus": "smart_charging (sparen)"},  # na de herberekening
    ])
    c._planvolging_gepland = lambda now, kwartier: next(plannen)
    c._volg_plan(T0.replace(minute=30))
    c._volg_plan(T0.replace(minute=32))
    nu = c.planvolging_nu()
    assert nu["gepland_accu_w"] == -1300
    assert nu["eerst_voorspeld_accu_w"] == -2400
    assert nu["status"] == "volgens plan"
    # het kwartieroordeel houdt het eerste plan
    assert c._planvolging["gepland"]["accu_w"] == -2400


def test_planvolging_in_de_leermodus_zonder_oordeel(make_coordinator, hass):
    c = _c(make_coordinator)
    c._planvolging_gepland = lambda now, kwartier: {"accu_w": -2400, "zon_w": 1420, "huis_w": 300, "modus": "manual (laden)"}
    c._volg_plan(T0)
    c.learning_only = True
    c.handmatige_stand = "smart_charge"
    nu = c.planvolging_nu()
    assert nu["niet_gestuurd"] is True and nu["status"] == "niet gestuurd"
    assert nu["tekst"] == "EMS stuurt niet (handmatig)"
    assert nu["verschil_w"] is None and nu["gemeten_accu_w"] == -1360
    assert "smart_charge" in nu["niet_gestuurd_reden"]


def test_cockpit_planvolging_handmatig():
    assert "if (ems && ems.niet_gestuurd)" in JS
    assert 'hand ? "handmatig"' in JS and 'hand ? "EMS stuurt niet"' in JS


# --- (a) een weergave per kwartier -------------------------------------------------


def test_weergave_rij_en_handmatig_python():
    assert sw.weergave_rij({"modus": "smart_charging (sparen)", "accu_w": -300}, "waardeplan_houden") == {
        "k": "zon", "label": "Zon laden – lading bewaren voor later"}
    assert sw.weergave_rij({"modus": "smart_charging (sparen)", "accu_w": 20}, "waardeplan_houden")["label"] == "Bewaren voor later"
    assert sw.weergave_rij({"modus": "manual (laden)", "accu_w": -2400})["k"] == "net"
    assert sw.weergave_rij({"modus": "smart", "accu_w": 0, "tekort": True})["k"] == "leeg"
    assert sw.handmatig_weergave("smart_charge")["label"] == "Handmatig: slim laden – EMS stuurt niet"
    assert sw.handmatig_weergave("laden")["k"] == "net"
    assert sw.handmatig_weergave(None)["label"] == "Leermodus – EMS stuurt niet"


@pytest.mark.skipif(NODE, reason="Node.js niet aanwezig")
def test_weergave_rij_cockpit_gelijk_aan_python():
    rijen = [
        ({"modus": "smart_charging (sparen)", "accu_w": -300}, "waardeplan_houden"),
        ({"modus": "smart_charging (sparen)", "accu_w": 20}, "waardeplan_houden"),
        ({"modus": "smart", "accu_w": 600}, "waardeplan_huis"),
        ({"modus": "manual (laden)", "accu_w": -2400}, None),
        ({"modus": "manual (verkopen)", "accu_w": 2000}, None),
        ({"modus": "manual (terugleveren)", "accu_w": 0}, None),
        ({"modus": "smart", "accu_w": 0, "tekort": True}, None),
        ({"modus": "smart_discharging", "accu_w": None}, None),
    ]
    js = _node(f"{json.dumps(rijen)}.map(([r, reden]) => {{ const w = kwartierWeergave(r, reden); return {{k: w.k, label: w.label}}; }})")
    assert js == [sw.weergave_rij(r, reden) for r, reden in rijen]
    hand = _node('["smart_charge", "laden", ""].map((s) => handmatigWeergave(s).label)')
    assert hand == [sw.handmatig_weergave(s)["label"] for s in ("smart_charge", "laden", "")]


def test_alle_plekken_uit_dezelfde_weergave():
    stand = JS.split("  _stand(live) {", 1)[1].split("\n  }\n", 1)[0]
    assert "this._huidigeRij()" in stand and "kwartierWeergave(this._rijNu(rij, live), reden)" in stand
    assert 'aan("leermodus")' in stand and "handmatigWeergave(" in stand
    vb = JS.split("  _vooruitBlokken(rijen, tijden, uren, socNu) {", 1)[1].split("\n  }\n", 1)[0]
    assert "kwartierWeergave(lopend ? this._rijNu(r) : r)" in vb and "modus(r.modus)" not in vb
    accu = JS.split("  _accu() {", 1)[1].split("\n  }\n", 1)[0]
    assert "const kort = stand.label ? stand.label" in accu
    assert "this._vooruitBlokken(rijenNu" in accu and "this._blokken()" not in accu
    assert "const kopStand = stand.label ? stand" in JS
    # staaf en tijdlijn: doen(r); standSoort gaat via doen
    assert "const standSoort = (planModus, accuW, tekort) => doen(" in JS
    assert "KOP_UIT_WEERGAVE" not in JS


def test_uitleg_stand_in_de_leermodus(make_coordinator, hass):
    c = make_coordinator({})
    c.learning_only = True
    c.handmatige_stand = "smart_charge"
    assert c.stand_weergave("waardeplan_houden")["label"] == "Handmatig: slim laden – EMS stuurt niet"


@pytest.mark.skipif(NODE, reason="Node.js niet aanwezig")
def test_tegel_en_vooruitblik_zeggen_hetzelfde(tmp_path):
    """Live 11:31: tegel 'Bewaren voor later', Vooruitblik 'Slim · laadt 0,3 kW',
    staaf 'rust'. Nu één weergave; in de leermodus de handmatige stand."""
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
  rijen.push({ start: d.toISOString(), van: d.toTimeString().slice(0, 5), prijs_ct: 25, soc_procent: 35 + i,
               modus: "smart_charging (sparen)", accu_w: i < 4 ? -300 : 0 });
}
let states = { plan: { state: "ok", attributes: { kwartierplanning: rijen } }, reden: { state: "waardeplan_houden" } };
o._ids = {};
o._s = (k) => states[k];
o._live = () => ({ accu: -300, zon: 0, net: 0, huis: 0 });  // v5.181.4: lopend kwartier uit de meting
const tijden = rijen.map((r) => new Date(r.start));
const a = o._stand();
const blokken = o._vooruitBlokken(rijen, tijden, 6, 35);
states.leermodus = { state: "on" }; states.handSmart = { state: "on" };
const b = o._stand();
states.soc = { state: "35" };
const g = o._planGrafiek(rijen, tijden);
const pl = (g.match(/soc-lijn" points="([^"]+)"/) || [])[1] || "";
const accu = o._accu();
console.log(JSON.stringify({ a: a.label, k: a.k, b0: blokken[0].label, b1: blokken[1].label, hand: b.label,
  eerste: pl.split(" ")[0], eenheid: g.includes(">ct/kWh</span><span>accu %</span>"),
  tegelHand: accu.includes("Handmatig: slim laden"), daarna: accu.includes("Daarna:") }));
""",
        encoding="utf-8",
    )
    uit = subprocess.run(["node", str(script), str(JS_PAD)], capture_output=True, text=True, check=True)
    r = json.loads(uit.stdout.strip().splitlines()[-1])
    assert r["k"] == "zon" and r["b0"] == "Zon laden"
    assert r["a"] == "Zon laden – lading bewaren voor later"
    assert r["b1"] == "Bewaren voor later"  # v5.181.4
    assert r["hand"] == "Handmatig: slim laden – EMS stuurt niet"


# --- (b) de lijn begint live -----------------------------------------------------


@pytest.mark.skipif(NODE, reason="Node.js niet aanwezig")
def test_soc_lijn_begint_live_en_loopt_naar_het_plan():
    uur = 3600000
    punten = [{"t": -900000, "soc": 21}, {"t": 900000, "soc": 20}, {"t": 2 * uur, "soc": 30}, {"t": 4 * uur, "soc": 50}]
    lijn = _node(f"socLijn({json.dumps(punten)}, 0, 35)")
    assert lijn[0] == {"t": 0, "soc": 35}
    assert all(q["t"] > 0 for q in lijn[1:])           # niets voor "nu"
    # plan op nu = 20,5 -> verschil 14,5; na een kwartier nog 11/12 ervan
    assert abs(lijn[1]["soc"] - (20 + 14.5 * (1 - 0.25 / 3))) < 1e-6
    assert abs(lijn[2]["soc"] - (30 + 14.5 / 3)) < 1e-6
    assert lijn[3]["soc"] == 50                           # na drie uur het plan
    assert _node(f"socLijn({json.dumps(punten)}, 0, null).length") == 4


def test_grafiek_gebruikt_de_live_lijn():
    g = JS.split("  _planGrafiek(rijen, tijden) {", 1)[1].split("\n  }\n", 1)[0]
    assert "socLijn(ruw, Date.now(), socLive)" in g
    assert "const socLive = getal(this._s(\"soc\"));" in g


def test_plan_soc_vanaf_de_effectieve_ondergrens(make_coordinator, hass):
    """Inhoud 1,15 kWh boven een bodem van 25 % bij 11,52 kWh = 35 %, niet 20 %."""
    c = make_coordinator({})
    c.bruikbare_capaciteit_kwh = lambda: 11.52
    c.effective_min_soc_percent = lambda: 10.0
    c.effectieve_ondergrens_procent = lambda now=None: 25.0
    nu = datetime(2026, 11, 4, 11, 30, tzinfo=timezone.utc)
    c._waardeplan_rijen = [{"begin": nu, "actie": "houden", "inhoud_kwh": 1.152, "net_kwh": 0.0}]
    uit = c._met_waardeplan([{"start": nu.isoformat(), "modus": "smart", "soc_kwh": 1.0}])
    assert uit[0]["soc_procent"] == 35


# --- (d) eenheden boven de assen ---------------------------------------------------


def test_eenheden_boven_de_assen():
    g = JS.split("  _planGrafiek(rijen, tijden) {", 1)[1].split("\n  }\n", 1)[0]
    assert '<div class="g-eenheid" aria-hidden="true"><span>ct/kWh</span><span>accu %</span></div>' in g
    w = JS.split("  _prijsGrafiek() {", 1)[1].split("\n  }\n", 1)[0]
    assert '<div class="g-eenheid" aria-hidden="true"><span>ct/kWh</span></div>' in w
    assert ".g-eenheid { display: flex; justify-content: space-between; font-size: 11px; color: var(--tekst3);" in JS


# --- (f) het eigen logo ------------------------------------------------------------


def test_logo_zelf_geserveerd():
    from custom_components.energy_management_system import cockpit_frontend as cf

    assert set(cf.LOGO_BESTANDEN) == {"/energy_management_system/ems-logo.png", "/energy_management_system/ems-logo@2x.png"}
    for naam in cf.LOGO_BESTANDEN.values():
        assert (PAKKET / "brand" / naam).is_file()
    assert 'const LOGO_URL = "/energy_management_system/ems-logo.png";' in JS
    assert 'srcset="${LOGO_URL_2X} 2x" width="34" height="34" alt="Energy Management System"' in JS
    assert 'icoon("bout")}</div>' not in JS


def test_logo_paden_geregistreerd(hass, monkeypatch):
    import asyncio
    import sys
    import types

    from custom_components.energy_management_system import cockpit_frontend as cf

    gezien = []

    class SPC:
        def __init__(self, url, pad, cache_headers=True):
            self.url, self.pad = url, pad

    class Http:
        async def async_register_static_paths(self, paden):
            gezien.extend(paden)

    mods = {
        "homeassistant.components.frontend": types.SimpleNamespace(add_extra_js_url=lambda h, u: None),
        "homeassistant.components.http": types.SimpleNamespace(StaticPathConfig=SPC),
    }
    from homeassistant.util import dt as dt_util

    monkeypatch.setattr(dt_util, "utcnow", lambda: datetime(2026, 11, 4, tzinfo=timezone.utc), raising=False)
    oud = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        h = types.SimpleNamespace(data={}, http=Http())
        asyncio.new_event_loop().run_until_complete(cf.async_registreer_cockpit(h, "test"))
    finally:
        for k, v in oud.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    urls = {p.url: p.pad for p in gezien}
    assert cf.COCKPIT_URL in urls
    assert urls["/energy_management_system/ems-logo.png"].endswith("brand/icon.png")
    assert urls["/energy_management_system/ems-logo@2x.png"].endswith("brand/icon@2x.png")
