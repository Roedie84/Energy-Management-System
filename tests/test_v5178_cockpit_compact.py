"""v5.178.0 - de compacte energiecockpit (akkoord Ruud 04-11).

Korter door herhaling weg te halen, dichtere rasters, samengevoegde panelen en
tabbladen - niet door gegevens weg te laten: de cockpit is een detailpagina.
Alle getallen en standen blijven zichtbaar zonder klikken; alleen lange
uitleg gaat in een uitklap. Kop met de prijs, goedkoopste/duurste kwartier en
het goedkope blok; drie tegels (Accu nu met de energiestroom, Plan vandaag met
de planvolging, Geld); Prijs en lading met tabbladen Vandaag, Morgen en 7 dagen;
alle apparaten en alle knoppen zichtbaar.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import custom_components.energy_management_system as pkg

JS_PAD = Path(pkg.__file__).parent / "www" / "ems-cockpit.js"
JS = JS_PAD.read_text(encoding="utf-8")


def _methode(naam):
    begin = JS.index(f"\n  {naam}(") + 1
    return JS[begin:JS.index("\n  }\n", begin)]


def test_drie_tegels_en_geen_stroomprijstegel():
    hero = JS.split('`<section class="hero" aria-label="Status">`')[1].split("`</section>`")[0]
    assert hero.index('data-p="accu"') < hero.index('data-p="planvandaag"') < hero.index('data-p="geld"')
    for weg in ("_tegelPrijs", "_tegelNu", "_tegelVandaag", "_tegelAccu", "Stroomprijs nu", "_stroom("):
        assert weg not in JS
    # wat in de tegel Stroomprijs stond, staat nu in de kop
    kop = _methode("_kop")
    for tekst in ("Goedkoopst", "Duurst", "Goedkoopste blok", "this._blokTekst()", "onder duur"):
        assert tekst in kop


def test_accu_tegel_toont_de_hele_energiestroom():
    a = _methode("_accu")
    for naam in ('cel("Zon"', 'cel("Net"', 'cel("Huis"', 'cel("Accu"'):
        assert naam in a
    # resttijd, kasprijs en "daarna" zichtbaar; alleen de redenen ingeklapt
    assert "this._accuPrijsRegel() +" in a and "this._accuResttijd(w, soc)" in a and "Daarna:" in a
    waarom = a.split('this._uitklap("waarom"')[0]
    assert "resttijd ?" in waarom and "this._accuPrijsRegel()" in waarom


def test_plan_vandaag_met_tijdlijn_en_planvolging_zichtbaar():
    p = _methode("_planvandaag")
    assert 'class="strip"' in p and "tegen geen accu" in p
    assert "this._planvolgingRegel() +" in p and "this._laadplanRegel() +" in p
    assert "_uitklap" not in p


def test_tabbladen_met_aria_en_onthouden():
    # v5.181.4: één tab met alle bekende prijzen in plaats van Vandaag/Morgen
    assert 'const TABS = [["prijzen", "Prijzen"], ["week", "7 dagen"]];' in JS
    p = _methode("_planning")
    assert 'role="tablist"' in p and 'role="tab"' in p and "aria-selected" in p and "aria-pressed" in p
    # de Vooruitblik staat zichtbaar onder de dag-grafiek, alleen de uitleg is ingeklapt
    assert "lichaam += this._vooruitblik(rijen, tijden)" in p
    assert 'this._uitklap("grafiekuitleg", "Uitleg bij de grafiek", uitleg)' in p
    # 7 dagen: grafiek plus hoe goed de verwachting is, zichtbaar
    w = _methode("_week")
    assert "this._prijsGrafiek()" in w and "this._prijsKwaliteit()" in w
    t = _methode("_tab")
    assert 'try { t = localStorage.getItem("ems-cockpit-tab"); } catch (e)' in t
    assert 'try { localStorage.setItem("ems-cockpit-tab", this._tabKeuze); } catch (e)' in JS


def test_zon_verkopen_en_reserve_alle_getallen_zichtbaar():
    v = JS.split("  _verkoop() {")[1].split("  /* ---- accumodules ---- */")[0]
    zichtbaar = v.split('this._uitklap("zon_reserve"')[0].split("const uitleg =")[0]
    for tekst in ('mini("Zon vandaag"', 'mini("Nog te komen"', 'mini("Morgen"', 'mini("Reserve tot blok"',
                  'mini("Tot het blok"', 'mini("Na het blok"', 'mini("Vrij te verkopen"', 'mini("Kans op tekort"',
                  'mini("Veiligheidsmarge"', "Bewolking", "Zonvoorspelling gisteren", "Tekortnachten 7 dagen",
                  "Zon opvangen uitstellen", "o.naam"):
        assert tekst in zichtbaar, tekst


def test_modules_cijfers_en_alle_apparaten_zichtbaar():
    m = _methode("_modules")
    for tekst in ("cel_min_v", "cel_max_v", "verschil", "temperatuur_c", "vermogen_w", "cycli", "koeling"):
        assert tekst in m
    assert "modules_detail" not in JS
    h = JS.split("  _huis() {")[1].split("  /* ---- geld ---- */")[0]
    assert '<div class="lijst huislijst">${uit.join("")}</div>' in h and "_uitklap" not in h
    assert "_huisActief" not in JS


def test_geld_getallen_zichtbaar_toelichting_ingeklapt():
    g = _methode("_geld")
    zichtbaar = g.split('this._uitklap("geld_detail"')[0]
    for tekst in ("zonder accu", "Besparing deze maand", "Besparing totaal", "Week", "Maand",
                  "Van het net vandaag", "Zelfvoorzienend", "Ontladen in dure kwartieren",
                  "Actieve sturing netto", "this._zelfanalyseRijen()"):
        assert tekst in zichtbaar, tekst
    assert '"kaart_primair"' in _methode("_zelfanalyseRijen")
    z = _methode("_zelfanalyse")
    assert '"kaart_secundair"' in z and "niet_de_beste" in z


def test_alle_knoppen_zichtbaar_en_gedrag_ongewijzigd():
    b = _methode("_bediening")
    assert "Alle knoppen" not in JS and "_uitklap" not in b
    assert "KNOPPEN.filter((k) => this._s(k.k))" in b
    k = _methode("_knop")
    assert 'aria-pressed="${aan}"' in k and "<button" in k
    s = JS.split("  async _schakel(sleutel) {")[1].split("\n  }\n")[0]
    assert "window.confirm(" in s and 'callService("switch", aan ? "turn_off" : "turn_on"' in s


def test_voet_toont_status_en_meetlog():
    v = _methode("_voet")
    assert 'class="links"' in v and "meetlog.state" in v and "gez.state" in v


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js niet aanwezig")
def test_de_cockpit_tekent_met_echte_gegevens(tmp_path):
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
for (let i = 0; i < 40; i++) {
  const d = new Date(nu.getTime() + i * 900000);
  rijen.push({ van: d.toTimeString().slice(0, 5), prijs_ct: 30 + i, soc_procent: 20 + i,
               modus: i < 4 ? "manual (laden)" : "smart", accu_w: i < 4 ? -2400 : i < 20 ? -800 : 900,
               tekort: false });
}
const S = {
  plan: { state: "ok", attributes: { kwartierplanning: rijen, planvolging: {
    nu: { beschikbaar: true, status: "volgens plan", tekst: "ok", gepland_accu_w: -800, gemeten_accu_w: -760, verschil_w: 40 },
    vandaag: { volgens_plan_procent: 91, kwartieren: 20 } } } },
  besparing: { state: "1", attributes: { werkelijke_kosten_vandaag_eur: 0.5, tegenfeitelijke_kosten_vandaag_eur: 0.8 } },
  soc: { state: "19", attributes: {} },
  nuLaden: { state: "off", attributes: {} }, kalibratie: { state: "on", attributes: {} },
  leermodus: { state: "off", attributes: {} },
};
o._s = (k) => S[k];
o._ids = {}; o._bezig = new Set(); o._uitgeklapt = {};
o._hass = { states: {} };
const plan = o._planvandaag();
const knoppen = o._bediening();
o._tabKeuze = "morgen";
const grafiek = o._planning();
console.log(JSON.stringify({
  strip: (plan.match(/<i style=/g) || []).length,
  legenda: plan.includes("net laden") && plan.includes("zon laden") && plan.includes("huis voeden"),
  planvolg: plan.includes("91% van 20 kwartieren") && plan.includes("Gepland"),
  netladen: plan.includes("Netladen"),
  scheelt: plan.includes("0,30"),
  knoppen: (knoppen.match(/data-knop=/g) || []).length,
  aan: (knoppen.match(/aria-pressed="true"/g) || []).length,
  tabs: (grafiek.match(/role="tab"/g) || []).length,
  weekUit: /data-tab="week"[^>]*disabled/.test(grafiek),
  geselecteerd: (grafiek.match(/aria-selected="true"/g) || []).length,
  vooruitblik: grafiek.includes("Vooruitblik"),
}));
""",
        encoding="utf-8",
    )
    uit = subprocess.run(["node", str(script), str(JS_PAD)], capture_output=True, text=True, check=True)
    r = json.loads(uit.stdout.strip().splitlines()[-1])
    assert r["strip"] >= 24 and r["legenda"] and r["planvolg"] and r["netladen"] and r["scheelt"]
    assert r["knoppen"] == 3 and r["aan"] == 1                # alle drie zichtbaar, kalibratie aan
    assert r["tabs"] == 2 and r["weekUit"] is True  # v5.181.4: Prijzen + 7 dagen
    assert r["geselecteerd"] == 1
    assert r["vooruitblik"] is True
