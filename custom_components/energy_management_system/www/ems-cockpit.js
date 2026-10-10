/**
 * Energy Management System: de energiecockpit.
 *
 * Een pagina met alles wat telt: wat de accu nu doet en waarom, de planning
 * met prijs, zon en laadstand per kwartier, de verkoop- en reservetoets, de
 * accumodules, zon, huis en apparaten, geld, en de knoppen die je het meest
 * gebruikt. Dezelfde stijl als het StormchaseNL- en Gold Scalper-dashboard.
 *
 * Dit bestand levert:
 *
 *  1. De kaart <ems-cockpit-card>: eigen element met Shadow DOM, zonder
 *     HACS-kaarten en zonder externe bestanden. Hij vindt alle entiteiten via
 *     de sensor "Dashboardbronnen" van de integratie (attribuut ems_cockpit),
 *     en tekent alleen het paneel opnieuw waarvan een waarde veranderde.
 *  2. De strategie custom:ems voor een eigen dashboard:
 *
 *       strategy:
 *         type: custom:ems
 *
 * Let op: dit bestand bevat alleen ASCII. Bijzondere tekens staan als escape
 * in de broncode, zodat een editor met een andere codering niets verminkt.
 */

/* ------------------------------------------------------------------ */
/* Versie                                                              */
/* ------------------------------------------------------------------ */

const eigenVersie = () => {
  try {
    const tag = document.querySelector('script[src*="ems-cockpit"]');
    if (tag) {
      const v = new URL(tag.src, location.href).searchParams.get("v");
      if (v) return v;
    }
    for (const item of performance.getEntriesByType("resource") || []) {
      if (String(item.name).includes("ems-cockpit")) {
        const v = new URL(item.name).searchParams.get("v");
        if (v) return v;
      }
    }
  } catch (e) {
    /* geen versie te achterhalen */
  }
  return "onbekend";
};
const VERSIE = eigenVersie();

/* ------------------------------------------------------------------ */
/* Entiteiten                                                          */
/* ------------------------------------------------------------------ */

/**
 * Eigen entiteiten: sleutel op de kaart -> vaste sleutel van de integratie
 * (de unique_id zonder het config-entry-id). De sensor Dashboardbronnen zet
 * die om naar de echte entity-id, ook na hernoemen.
 */
const EIGEN = {
  status: "system_status",
  prijs: "current_price_used",
  blok: "cheapest_block_start",
  reden: "last_decision_reason",
  verwacht: "expected_operation_mode",
  modules: "battery_module_health",
  koeling: "battery_cooling",
  gacs: "gacs_assessment",
  perioden: "perioden",
  mc: "monte_carlo_advisory",
  klimaat: "climate_forecast",
  water: "water_usage",
  besparing: "counterfactual_savings",
  zelfvoorziening: "self_sufficiency",
  huis: "household_consumption",
  verhaal: "live_narrative",
  tekort: "reserve_shortfall",
  rendement: "learned_battery_efficiency",
  stofzuiger: "steelstofzuiger_status",
  fietsen: "fietsladers_status",
  cockpit: "cockpit",
  aircoBesluit: "airco_besluit",
  meetlog: "meetlog",
  gezondheid: "diagnose_gezondheid",
  pvNauw: "pv_forecast_accuracy",
  vaatwasser: "dishwasher_cycle_state",
  wasmachine: "washing_machine_cycle_state",
  bewolking: "weather_ensemble",
  meldingen: "meldingen",
  accuGezondheid: "battery_health",
  plan: "kwartierplanning_tabel",
  schema: "upcoming_schedule",
  maand: "monthly_summary",
  uitleg: "explanation",
  // knoppen
  nuLaden: "nu_laden",
  handLaden: "handmatig_laden",
  handSmart: "handmatig_smart_charge",
  forceManual: "force_manual",
  leermodus: "learning_only",
  kalibratie: "kalibratie",
  vakantie: "vacation_mode",
  aircoAutomaat: "airco_automaat",
  fietsenOverrule: "fietsladers_override",
  stofzuigerOverrule: "steelstofzuiger_override",
  meldingenAan: "notifications_master",
  achterhoeks: "achterhoeks",
};

/* Geconfigureerde entiteiten, zoals de sensor Dashboardbronnen ze noemt. */
const EXTERN = [
  "soc", "beschikbaar", "capaciteit", "accu_vermogen", "net", "pv",
  "zon_vandaag", "zon_rest", "zon_morgen", "zon_werkelijk", "prijs_bron",
  "modus", "inkoop_vandaag", "teruglever_vandaag", "water_bron", "airco",
  "temp_binnen", "temp_buiten",
];
/* Twee namen botsen met eigen sleutels; die krijgen een achtervoegsel. */
const EXTERN_ALIAS = { prijs_bron: "prijs", water_bron: "water" };

const ONBRUIKBAAR = ["unknown", "unavailable", "none", ""];

/** Zoek de sensor Dashboardbronnen en zet alles om naar entity-id's. */
const zoekEntiteiten = (hass) => {
  let bron = null;
  for (const s of Object.values(hass.states)) {
    if (s && s.attributes && s.attributes.ems_cockpit) {
      bron = s;
      break;
    }
  }
  const ids = {};
  const eigen = (bron && bron.attributes.eigen) || {};
  const extern = (bron && bron.attributes.bronnen) || {};
  for (const [sleutel, vast] of Object.entries(EIGEN)) {
    if (eigen[vast]) ids[sleutel] = eigen[vast];
  }
  for (const sleutel of EXTERN) {
    const naam = EXTERN_ALIAS[sleutel] || sleutel;
    if (extern[naam]) ids[sleutel] = extern[naam];
  }
  const modules = Array.isArray(extern.modules_soc) ? extern.modules_soc : [];
  return {
    ids,
    modules,
    omkeren: !!extern.accu_omkeren,
    gevonden: !!bron,
    bronId: bron ? bron.entity_id : null,
  };
};

/* ------------------------------------------------------------------ */
/* Kleine hulpjes                                                      */
/* ------------------------------------------------------------------ */

const bruikbaar = (s) => !!s && !ONBRUIKBAAR.includes(String(s.state));
const getal = (s) => {
  if (!bruikbaar(s)) return null;
  const v = parseFloat(s.state);
  return Number.isFinite(v) ? v : null;
};
const attr = (s, naam) => (s && s.attributes ? s.attributes[naam] : undefined);
const num = (v) => (v == null || v === "" || !Number.isFinite(Number(v)) ? null : Number(v));
const esc = (tekst) =>
  String(tekst == null ? "" : tekst)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

const MIN = "\u2212";
const STREEP = "\u2014";
const PUNT = " \u00b7 ";
const PIJL = " \u2192 ";
const EURO = "\u20ac";
const GRAAD = "\u00b0";

const fmt = (v, dec = 0) => {
  const n0 = num(v);
  if (n0 == null) return STREEP;
  let n = n0;
  if (Math.abs(n) < 0.5 * Math.pow(10, -dec)) n = 0;
  return n
    .toLocaleString("nl-NL", { minimumFractionDigits: dec, maximumFractionDigits: dec })
    .replace("-", MIN);
};
const fmtTeken = (v, dec = 0) => {
  const n = num(v);
  if (n == null) return STREEP;
  const t = fmt(Math.abs(n), dec);
  if (t === fmt(0, dec)) return t;
  return (n > 0 ? "+" : MIN) + t;
};
const euro = (v, dec = 2) => (num(v) == null ? STREEP : `${EURO}\u00a0${fmt(v, dec)}`);
const euroTeken = (v, dec = 2) => {
  const n = num(v);
  if (n == null) return STREEP;
  return `${n < 0 ? MIN : n > 0 ? "+" : ""}${EURO}\u00a0${fmt(Math.abs(n), dec)}`;
};
const ct = (eurPerKwh, dec = 1) => (num(eurPerKwh) == null ? STREEP : fmt(eurPerKwh * 100, dec));
const watt = (w) => {
  const n = num(w);
  if (n == null) return STREEP;
  if (Math.abs(n) >= 1000) return `${fmt(n / 1000, 2)}<small>kW</small>`;
  return `${fmt(n)}<small>W</small>`;
};
const hoofd = (t) => {
  const s = String(t || "");
  if (!s) return "";
  if (s.slice(0, 2).toLowerCase() === "ij") return "IJ" + s.slice(2);
  return s[0].toUpperCase() + s.slice(1);
};
const alsDatum = (w) => {
  if (w == null || w === "") return null;
  const d = typeof w === "number" ? new Date(w < 1e12 ? w * 1000 : w) : new Date(w);
  return Number.isNaN(d.getTime()) ? null : d;
};
const klok = (w) => {
  const d = alsDatum(w);
  return d ? d.toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" }) : null;
};
const geleden = (w) => {
  const d = alsDatum(w);
  if (!d) return null;
  const min = Math.max(0, Math.round((Date.now() - d.getTime()) / 60000));
  if (min < 1) return "zojuist";
  if (min < 60) return `${min} min geleden`;
  const u = Math.round(min / 60);
  return u < 48 ? `${u} u geleden` : `${Math.round(u / 24)} d geleden`;
};
const overTijd = (w) => {
  const d = alsDatum(w);
  if (!d) return "";
  const min = Math.round((d.getTime() - Date.now()) / 60000);
  if (min <= 0) return "nu";
  if (min < 60) return `over ${min} min`;
  const u = Math.floor(min / 60);
  return `over ${u} u${min % 60 ? " " + (min % 60) + " min" : ""}`;
};
const dagLabel = (d) => {
  if (!d) return "";
  const vandaag = new Date();
  const morgen = new Date();
  morgen.setDate(vandaag.getDate() + 1);
  if (d.toDateString() === vandaag.toDateString()) return "";
  if (d.toDateString() === morgen.toDateString()) return "morgen ";
  return d.toLocaleDateString("nl-NL", { weekday: "short" }) + " ";
};

/* ------------------------------------------------------------------ */
/* Modi                                                                */
/* ------------------------------------------------------------------ */

/** Een plan- of accumodus: label, kleur en klasse. */
const MODI = [
  { test: /verkopen/, label: "Verkopen", kleur: "var(--oranje)", k: "verkopen" },
  { test: /laden\)|^manual \(laden|nu laden|handmatig laden/, label: "Laden van net", kleur: "var(--groen)", k: "laden" },
  { test: /sparen|smart_charging/, label: "Sparen", kleur: "var(--blauw)", k: "sparen" },
  { test: /smart_discharging|ontladen/, label: "Ontladen", kleur: "var(--geel)", k: "ontladen" },
  { test: /smart|slim/, label: "Slim", kleur: "var(--violet)", k: "slim" },
  { test: /manual/, label: "Handmatig", kleur: "var(--cyaan)", k: "hand" },
];
const modus = (tekst) => {
  const t = String(tekst || "").toLowerCase();
  return MODI.find((m) => m.test.test(t)) || { label: hoofd(t) || STREEP, kleur: "var(--tekst3)", k: "onbekend" };
};

const APPARAAT_STATUS = {
  wacht_op_goedkoop_blok: "wacht op goedkoop blok",
  laadt: "laadt",
  klaar: "klaar",
  vol: "vol",
  uit: "uit",
  idle: "rust",
  bezig: "bezig",
  draait: "draait",
  gepland: "gepland",
};
const apparaatTekst = (s) => {
  if (!bruikbaar(s)) return STREEP;
  return hoofd(APPARAAT_STATUS[s.state] || String(s.state).replace(/_/g, " "));
};

/* ------------------------------------------------------------------ */
/* Iconen (zelf getekend, geen externe bestanden)                      */
/* ------------------------------------------------------------------ */

const ICOON = {
  bout: '<path d="M13 2 4 14h6l-1 8 9-12h-6z"/>',
  accu: '<rect x="3" y="7" width="16" height="10" rx="2"/><path d="M21 10v4"/><path d="M7 10v4M10.5 10v4"/>',
  zon: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/>',
  net: '<path d="M8 22 12 2l4 20"/><path d="M6.5 9h11M5 15h14M9.5 2h5"/>',
  huis: '<path d="M3 11 12 4l9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-5h4v5"/>',
  euro: '<path d="M17 6.5a6.5 6.5 0 1 0 0 11"/><path d="M4 10h9M4 14h9"/>',
  klok: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
  grafiek: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  schild: '<path d="M12 3 4 6v6c0 4.5 3.4 8.2 8 9 4.6-.8 8-4.5 8-9V6z"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
  cellen: '<rect x="3" y="4" width="5" height="16" rx="1.5"/><rect x="9.5" y="4" width="5" height="16" rx="1.5"/><rect x="16" y="4" width="5" height="16" rx="1.5"/>',
  wolk: '<path d="M7 18h10a4 4 0 0 0 .5-8A6 6 0 0 0 6 9.5 4.3 4.3 0 0 0 7 18z"/>',
  stekker: '<path d="M9 2v5M15 2v5M6 7h12v4a6 6 0 0 1-12 0z"/><path d="M12 17v5"/>',
  knop: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5"/><path d="M8.5 9.5a5 5 0 1 0 7 0"/>',
  waarschuwing: '<path d="M12 3 2 20h20z"/><path d="M12 10v4.5"/><path d="M12 17.2v.3"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8v.3"/>',
  pijl: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  thermo: '<path d="M10 14V5a2 2 0 0 1 4 0v9a4 4 0 1 1-4 0z"/>',
  druppel: '<path d="M12 3c-3.5 5-6 8.2-6 11a6 6 0 0 0 12 0c0-2.8-2.5-6-6-11z"/>',
  fiets: '<circle cx="6" cy="16" r="3.5"/><circle cx="18" cy="16" r="3.5"/><path d="M6 16l4-7h5l3 7M10 9 8.5 6H6.5M12.5 16 10 9"/>',
  vaat: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M4 8h16"/><circle cx="12" cy="14" r="3.5"/>',
  was: '<rect x="4" y="3" width="16" height="18" rx="2"/><circle cx="12" cy="13.5" r="4.5"/><path d="M7.5 6.5h.01M10 6.5h.01"/>',
  airco: '<rect x="3" y="5" width="18" height="7" rx="2"/><path d="M7 16v3M12 16v4M17 16v3"/>',
  stof: '<path d="M14 3 8 15"/><path d="M5 15h7l-1.5 6h-4z"/>',
  ventilator: '<circle cx="12" cy="12" r="2"/><path d="M12 10c0-4 1-7 4-7 2 0 2.5 3 0 5M14 12c4 0 7 1 7 4 0 2-3 2.5-5 0M12 14c0 4-1 7-4 7-2 0-2.5-3 0-5M10 12c-4 0-7-1-7-4 0-2 3-2.5 5 0"/>',
  vakantie: '<path d="M2 21h20M6 21l6-14 6 14"/><path d="M12 7V3"/>',
  bel: '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  leren: '<path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c3 2.5 9 2.5 12 0v-5"/>',
  hand: '<path d="M8 13V5.5a1.5 1.5 0 0 1 3 0V11M11 10V4.5a1.5 1.5 0 0 1 3 0V11M14 10.5V6a1.5 1.5 0 0 1 3 0v8a7 7 0 0 1-7 7h-.5a6 6 0 0 1-4.6-2.2L2.5 15.5a1.6 1.6 0 0 1 2.3-2.2L8 16"/>',
  ijk: '<path d="M4 20 20 4"/><path d="M7 20H4v-3M17 4h3v3"/><circle cx="12" cy="12" r="2"/>',
  taal: '<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9h8M8 12h5"/>',
  kaart: '<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>',
  pulse: '<path d="M2 12h4l3-8 4 16 3-8h6"/>',
};
const icoon = (naam, klasse = "ic") =>
  `<svg class="${klasse}" viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
  `stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">` +
  `${ICOON[naam] || ""}</svg>`;

/* ------------------------------------------------------------------ */
/* Bouwstenen                                                          */
/* ------------------------------------------------------------------ */

const paneelKop = (ic, titel, rechts = "", link = "") =>
  `<div class="ph">${icoon(ic)}<h2>${esc(titel)}</h2><div class="ph-r">${rechts}` +
  (link ? `<button class="meer" data-nav="${esc(link)}" title="Details">${icoon("pijl")}</button>` : "") +
  `</div></div>`;

const chip = (tekst, klasse = "") => (tekst ? `<span class="chip ${klasse}">${tekst}</span>` : "");

const mini = (label, waarde, sub = "", kleur = "") =>
  `<div class="mini"><div class="lbl">${esc(label)}</div>` +
  `<div class="w"${kleur ? ` style="color:${kleur}"` : ""}>${waarde}</div>` +
  (sub ? `<div class="s">${sub}</div>` : "") +
  `</div>`;

const balk = (deel, kleur, streep = null) => {
  const d = Math.max(0, Math.min(1, num(deel) || 0));
  const s = streep == null ? "" : `<i style="left:${(Math.max(0, Math.min(1, streep)) * 100).toFixed(1)}%"></i>`;
  return `<div class="balk"><b style="width:${(d * 100).toFixed(1)}%;background:${kleur}"></b>${s}</div>`;
};

/** Ronde meter: de laadstand. */
const ring = (pct, kleur, onder = "") => {
  const r = 52;
  const omtrek = 2 * Math.PI * r;
  const deel = Math.max(0, Math.min(100, num(pct) || 0)) / 100;
  return (
    `<svg class="ring" viewBox="0 0 128 128" role="img" aria-label="${pct == null ? "onbekend" : Math.round(pct) + " procent"}">` +
    `<defs><linearGradient id="rg" x1="0" y1="0" x2="1" y2="1">` +
    `<stop offset="0" stop-color="${kleur}" stop-opacity=".55"/><stop offset="1" stop-color="${kleur}"/></linearGradient></defs>` +
    `<circle cx="64" cy="64" r="${r}" fill="none" stroke="rgba(255,255,255,.07)" stroke-width="11"/>` +
    `<circle cx="64" cy="64" r="${r}" fill="none" stroke="url(#rg)" stroke-width="11" stroke-linecap="round" ` +
    `stroke-dasharray="${(omtrek * deel).toFixed(1)} ${omtrek.toFixed(1)}" transform="rotate(-90 64 64)" class="ring-boog"/>` +
    `<text x="64" y="66" text-anchor="middle" class="ring-t">${pct == null ? STREEP : Math.round(pct)}<tspan class="ring-p">%</tspan></text>` +
    (onder ? `<text x="64" y="86" text-anchor="middle" class="ring-o">${esc(onder)}</text>` : "") +
    `</svg>`
  );
};

/* ------------------------------------------------------------------ */
/* Stijl                                                               */
/* ------------------------------------------------------------------ */

const STIJL = `
:host {
  display: block;
  min-height: 100%;
  --bg0: #06090f;
  --bg1: #0a1220;
  --bg2: #0f1a2c;
  --paneel: rgba(18, 28, 46, .62);
  --paneel2: rgba(10, 16, 28, .70);
  --rand: rgba(150, 190, 255, .12);
  --rand2: rgba(150, 190, 255, .22);
  --tekst: #eef3ff;
  --tekst2: #aab6d3;
  --tekst3: #7a87a8;
  --groen: #34d399;
  --geel: #facc15;
  --amber: #fbbf24;
  --oranje: #fb923c;
  --rood: #fb4d65;
  --blauw: #60a5fa;
  --cyaan: #38d7f0;
  --violet: #a78bfa;
  --r: 16px;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  color: var(--tekst);
  -webkit-font-smoothing: antialiased;
}
* { box-sizing: border-box; }
.root {
  position: relative; isolation: isolate; min-height: 100vh; overflow: hidden;
  background:
    radial-gradient(1000px 600px at 82% -10%, rgba(251, 191, 36, .16), transparent 62%),
    radial-gradient(900px 560px at -8% 18%, rgba(52, 211, 153, .14), transparent 60%),
    radial-gradient(900px 640px at 50% 112%, rgba(56, 120, 240, .20), transparent 62%),
    linear-gradient(180deg, var(--bg0) 0%, var(--bg1) 45%, var(--bg2) 100%);
}
.bg { position: absolute; inset: 0; z-index: -1; pointer-events: none; overflow: hidden; }
.bg svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.wrap { container-type: inline-size; max-width: 1760px; margin: 0 auto; padding: 20px 24px 28px; }
.ic { width: 18px; height: 18px; flex: none; }
small { font-size: .55em; font-weight: 600; color: var(--tekst2); margin-left: 3px; letter-spacing: 0; }
.leeg { color: var(--tekst3); opacity: .75; }
[hidden] { display: none !important; }
.num, .big, td, .mini .w, .kv b { font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; }

/* ---- kop ---- */
.kop { display: flex; align-items: center; gap: 18px; flex-wrap: wrap; padding: 4px 2px 16px; }
.merk { display: flex; align-items: center; gap: 12px; min-width: 0; }
.logo {
  width: 44px; height: 44px; border-radius: 13px; display: grid; place-items: center; color: #fff;
  background: linear-gradient(135deg, #f59e0b, #10b981 70%, #0ea5e9);
  box-shadow: 0 6px 22px rgba(16, 185, 129, .40), inset 0 1px 0 rgba(255,255,255,.3);
}
.logo .ic { width: 26px; height: 26px; fill: #fff; stroke: none; }
.merknaam { font-size: 19px; font-weight: 800; letter-spacing: .14em; line-height: 1.1; }
.merksub { font-size: 12px; color: var(--tekst2); letter-spacing: .04em; margin-top: 2px; }
.kop-mid { display: flex; gap: 8px; flex-wrap: wrap; flex: 1 1 0; min-width: 0; }
.kop-r { display: flex; align-items: center; gap: 18px; margin-left: auto; }
.klok { text-align: right; line-height: 1.1; }
.klok .tijd { font-size: 30px; font-weight: 700; letter-spacing: .02em; font-variant-numeric: tabular-nums; }
.klok .datum { font-size: 12px; color: var(--tekst2); margin-top: 3px; }
.chip {
  display: inline-flex; align-items: center; gap: 6px; white-space: nowrap;
  font-size: 12px; font-weight: 600; color: var(--tekst2);
  padding: 5px 10px; border-radius: 999px; background: rgba(255,255,255,.05); border: 1px solid var(--rand);
  max-width: 100%; overflow: hidden; text-overflow: ellipsis;
}
.chip .ic { width: 14px; height: 14px; }
.chip.groot { font-size: 13px; padding: 7px 12px; color: var(--tekst); background: var(--paneel2); }
.chip.ok { color: var(--groen); border-color: rgba(52, 211, 153, .35); }
.chip.let { color: var(--oranje); border-color: rgba(251, 146, 60, .4); }
.chip.gevaar { color: #fff; background: rgba(251, 77, 101, .22); border-color: rgba(251, 77, 101, .55); }
.chip.uit { opacity: .55; }
.stip { width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex: none; background: var(--kleur, var(--tekst3)); box-shadow: 0 0 8px var(--kleur, transparent); }

/* ---- meldingen ---- */
.meldingen { display: grid; gap: 10px; margin-bottom: 14px; }
.meldingen:empty { display: none; }
.melding {
  display: flex; align-items: flex-start; gap: 12px; padding: 12px 16px; border-radius: 14px;
  border: 1px solid var(--rand2); background: var(--paneel);
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); font-size: 13.5px; line-height: 1.45;
}
.melding .ic { width: 20px; height: 20px; margin-top: 1px; }
.melding.let { border-color: rgba(251, 146, 60, .45); }
.melding.let .ic { color: var(--oranje); }
.melding.info .ic { color: var(--blauw); }
.melding.gevaar { background: linear-gradient(90deg, rgba(251, 77, 101, .28), rgba(251, 77, 101, .08)); border-color: rgba(251, 77, 101, .6); }
.melding.gevaar .ic { color: var(--rood); }

/* ---- statusrij ---- */
.hero { display: grid; gap: 14px; grid-template-columns: 1fr; margin-bottom: 14px; }
.tegel {
  position: relative; overflow: hidden; padding: 16px 18px 16px 20px; border-radius: var(--r);
  background: linear-gradient(160deg, rgba(26, 40, 64, .74), rgba(10, 16, 30, .74));
  border: 1px solid var(--rand);
  backdrop-filter: blur(16px) saturate(130%); -webkit-backdrop-filter: blur(16px) saturate(130%);
  box-shadow: 0 12px 34px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.05); min-width: 0;
}
.tegel::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--accent, var(--tekst3)); box-shadow: 0 0 18px var(--accent, transparent); }
.tegel::after { content: ""; position: absolute; inset: 0; pointer-events: none; background: radial-gradient(120% 90% at 0% 0%, color-mix(in srgb, var(--accent, transparent) 18%, transparent), transparent 55%); }
.tegel > * { position: relative; z-index: 1; }
.lbl { font-size: 11px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--tekst2); }
.big { font-size: 30px; font-weight: 800; line-height: 1.1; letter-spacing: .01em; margin: 6px 0 4px; }
.big.accent { color: var(--accent); }
.sub { font-size: 13px; color: var(--tekst2); line-height: 1.45; }
.sub b { color: var(--tekst); font-weight: 600; }
.tekst-m { font-size: 17px; font-weight: 700; line-height: 1.3; margin: 8px 0 6px; }
.klem { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.accu-t { display: grid; grid-template-columns: 116px 1fr; gap: 16px; align-items: center; }
.ring { width: 116px; height: 116px; display: block; }
.ring-t { font-size: 30px; font-weight: 800; fill: var(--tekst); font-variant-numeric: tabular-nums; }
.ring-p { font-size: 14px; fill: var(--tekst2); font-weight: 700; }
.ring-o { font-size: 10px; fill: var(--tekst2); font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.ring-boog { transition: stroke-dasharray .8s ease; }
.rijen { display: grid; gap: 5px; font-size: 12.5px; color: var(--tekst2); min-width: 0; }
.rijen span { display: flex; justify-content: space-between; gap: 10px; }
.rijen b { color: var(--tekst); font-variant-numeric: tabular-nums; white-space: nowrap; }
.redenen { margin: 8px 0 0; padding: 0; list-style: none; display: grid; gap: 4px; font-size: 12.5px; color: var(--tekst2); }
.redenen li { display: flex; gap: 8px; }
.redenen li::before { content: ""; width: 5px; height: 5px; border-radius: 50%; background: var(--accent, var(--tekst3)); margin-top: 7px; flex: none; }

/* ---- raster ---- */
.raster {
  display: grid; gap: 14px; grid-template-columns: minmax(0, 1fr);
  grid-template-areas: "stroom" "planning" "verkoop" "modules" "zon" "huis" "bediening" "geld";
}
.paneel {
  min-width: 0; border-radius: var(--r);
  background: linear-gradient(180deg, var(--paneel), var(--paneel2)); border: 1px solid var(--rand);
  backdrop-filter: blur(16px) saturate(130%); -webkit-backdrop-filter: blur(16px) saturate(130%);
  box-shadow: 0 12px 34px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.05);
  padding: 0 0 16px; display: flex; flex-direction: column;
}
.p-stroom { grid-area: stroom; }
.p-planning { grid-area: planning; }
.p-verkoop { grid-area: verkoop; }
.p-modules { grid-area: modules; }
.p-zon { grid-area: zon; }
.p-huis { grid-area: huis; }
.p-bediening { grid-area: bediening; }
.p-geld { grid-area: geld; }
.ph { display: flex; align-items: center; gap: 9px; padding: 14px 16px 10px; color: var(--tekst2); min-width: 0; flex-wrap: wrap; }
.ph h2 { margin: 0; font-size: 12px; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; color: var(--tekst); }
.ph .ic { color: var(--amber); }
.ph-r { margin-left: auto; display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; align-items: center; min-width: 0; }
.meer { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 9px; border: 1px solid var(--rand); background: rgba(255,255,255,.04); color: var(--tekst2); cursor: pointer; padding: 0; }
.meer:hover { color: var(--tekst); border-color: var(--rand2); }
.meer .ic { width: 15px; height: 15px; color: currentColor; }
.pb { padding: 0 16px; display: grid; grid-template-columns: minmax(0, 1fr); gap: 14px; }
.leegmelding { padding: 6px 16px 0; color: var(--tekst3); font-size: 13px; }
.mini { padding: 10px 12px; border-radius: 12px; background: rgba(255,255,255,.035); border: 1px solid var(--rand); min-width: 0; }
.mini .lbl { font-size: 10px; letter-spacing: .1em; }
.mini .w { font-size: 20px; font-weight: 750; margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mini .s { font-size: 12px; color: var(--tekst2); margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.duo { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.trio { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.kwart { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.balk { position: relative; height: 8px; border-radius: 99px; background: rgba(255,255,255,.07); overflow: hidden; }
.balk b { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 99px; box-shadow: 0 0 12px currentColor; transition: width .6s ease; }
.balk i { position: absolute; top: -2px; bottom: -2px; width: 2px; background: #fff; border-radius: 2px; opacity: .85; }
.meterrij { display: grid; gap: 6px; }
.meterkop { display: flex; justify-content: space-between; align-items: baseline; gap: 2px 10px; flex-wrap: wrap; }
.meterkop .lbl { font-size: 11px; }
.meterkop .w { font-size: 16px; font-weight: 750; font-variant-numeric: tabular-nums; white-space: nowrap; }
.meternoot { font-size: 12px; color: var(--tekst3); line-height: 1.45; }
.zin { font-size: 13px; color: var(--tekst2); line-height: 1.5; padding: 10px 12px; border-radius: 12px; background: rgba(255,255,255,.035); border: 1px solid var(--rand); }
.zin b { color: var(--tekst); }

/* ---- energiestroom ---- */
.stroom { position: relative; width: 100%; max-width: 560px; margin: 0 auto; aspect-ratio: 1.35 / 1; }
.stroom svg.lijnen { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }
.lijn { fill: none; stroke: rgba(255,255,255,.08); stroke-width: 3; }
.loop { fill: none; stroke-width: 3; stroke-linecap: round; stroke-dasharray: 2 12; animation: loop var(--snel, 1.6s) linear infinite; }
.loop.terug { animation-direction: reverse; }
@keyframes loop { to { stroke-dashoffset: -28; } }
@media (prefers-reduced-motion: reduce) { .loop { animation: none; stroke-dasharray: none; opacity: .6; } }
.knoop {
  position: absolute; transform: translate(-50%, -50%); display: grid; justify-items: center; gap: 2px;
  width: 31%; padding: 10px 6px 9px; border-radius: 16px; text-align: center;
  background: rgba(8, 14, 26, .78); border: 1px solid var(--rand2);
  box-shadow: 0 0 0 1px rgba(0,0,0,.2), 0 10px 26px rgba(0,0,0,.35), 0 0 22px var(--gloed, transparent);
}
.knoop .ic { width: 24px; height: 24px; color: var(--k, var(--tekst2)); }
.knoop .n { font-size: 10.5px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; color: var(--tekst2); }
.knoop .v { font-size: 21px; font-weight: 800; font-variant-numeric: tabular-nums; white-space: nowrap; }
.knoop .v small { font-size: 11px; }
.knoop .s { font-size: 11.5px; color: var(--tekst2); white-space: nowrap; }
.hub { position: absolute; left: 50%; top: 50%; width: 14px; height: 14px; border-radius: 50%; transform: translate(-50%,-50%); background: var(--amber); box-shadow: 0 0 16px var(--amber); }

/* ---- planning ---- */
.pl-legenda { display: flex; flex-wrap: wrap; gap: 12px; font-size: 11.5px; color: var(--tekst2); }
.pl-legenda i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 5px; vertical-align: -1px; }
.pl-legenda .lijn-i { height: 3px; border-radius: 2px; vertical-align: 3px; }
.gwrap { position: relative; display: grid; grid-template-columns: 34px 1fr 34px; grid-template-rows: 210px 22px; }
.g-y, .g-y2 { position: relative; }
.g-y span, .g-y2 span, .g-x span { position: absolute; font-size: 10.5px; color: var(--tekst3); font-variant-numeric: tabular-nums; white-space: nowrap; }
.g-y span { right: 7px; transform: translateY(-50%); }
.g-y2 span { left: 7px; transform: translateY(-50%); }
.g-plot { position: relative; border-left: 1px solid rgba(255,255,255,.08); border-bottom: 1px solid rgba(255,255,255,.12); }
.g-raster { position: absolute; left: 0; right: 0; height: 1px; background: rgba(255,255,255,.05); }
.staven { position: absolute; inset: 0; display: flex; align-items: flex-end; gap: 1px; padding: 0 1px; }
.staaf { flex: 1 1 0; min-width: 0; border-radius: 2px 2px 0 0; opacity: .88; position: relative; }
.staaf.verkopen { box-shadow: 0 0 10px rgba(251, 146, 60, .6); }
.staaf.laden { box-shadow: 0 0 10px rgba(52, 211, 153, .5); }
.staaf.tekort::after { content: ""; position: absolute; left: 0; right: 0; bottom: -6px; height: 3px; background: var(--rood); border-radius: 2px; }
.staaf:hover { opacity: 1; filter: brightness(1.25); }
.g-svg { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; pointer-events: none; }
.soc-lijn { fill: none; stroke: #fff; stroke-width: 2.4; vector-effect: non-scaling-stroke; filter: drop-shadow(0 0 4px rgba(255,255,255,.5)); }
.zon-vlak { fill: rgba(250, 204, 21, .14); stroke: rgba(250, 204, 21, .55); stroke-width: 1.2; vector-effect: non-scaling-stroke; }
.drempel { stroke: rgba(251, 77, 101, .55); stroke-width: 1; stroke-dasharray: 4 4; vector-effect: non-scaling-stroke; }
.nu-lijn { position: absolute; top: -6px; bottom: 0; width: 2px; background: var(--cyaan); box-shadow: 0 0 8px var(--cyaan); }
.nu-lijn span { position: absolute; top: 4px; left: 5px; font-size: 10px; font-weight: 800; color: var(--cyaan); letter-spacing: .08em; }
.g-x { position: relative; grid-column: 2; }
.g-x span { top: 6px; transform: translateX(-50%); }
.g-x span.dag { color: var(--violet); font-weight: 800; }
.tabel { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13px; }
.tabel th { text-align: left; font-size: 10.5px; letter-spacing: .1em; text-transform: uppercase; color: var(--tekst3); font-weight: 700; padding: 0 10px 8px; }
.tabel td { padding: 8px 10px; border-top: 1px solid rgba(255,255,255,.06); white-space: nowrap; }
.tabel td.r, .tabel th.r { text-align: right; }
.tabel tr.nu td { background: rgba(56, 215, 240, .07); }
.tabel tr.nu td:first-child { box-shadow: inset 3px 0 0 var(--cyaan); }
.modus { display: inline-flex; align-items: center; gap: 7px; font-weight: 650; }
.modus i { width: 9px; height: 9px; border-radius: 3px; background: var(--kleur); box-shadow: 0 0 8px var(--kleur); }
.soc-pijl { color: var(--tekst2); }
.soc-pijl b { color: var(--tekst); }
.tabelvak { overflow-x: auto; margin: 0 -4px; }

/* ---- modules ---- */
.module { display: grid; gap: 7px; padding: 11px 12px; border-radius: 12px; background: rgba(255,255,255,.035); border: 1px solid var(--rand); }
.module.zwak { border-color: rgba(251, 146, 60, .45); background: rgba(251, 146, 60, .06); }
.module-kop { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.module-kop b { font-size: 14px; }
.module-kop .w { font-size: 18px; font-weight: 800; font-variant-numeric: tabular-nums; }
.module-cijfers { display: flex; gap: 12px; flex-wrap: wrap; font-size: 12px; color: var(--tekst2); }
.module-cijfers b { color: var(--tekst); font-variant-numeric: tabular-nums; }
.vlaggen { display: flex; gap: 6px; flex-wrap: wrap; }

/* ---- bediening ---- */
.knoppen { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.knop {
  font: inherit; color: var(--tekst); text-align: left; cursor: pointer;
  display: grid; grid-template-columns: 36px 1fr auto; align-items: center; gap: 10px;
  padding: 10px 12px; border-radius: 13px; border: 1px solid var(--rand);
  background: rgba(255,255,255,.035); transition: background .2s, border-color .2s, transform .1s;
  min-width: 0;
}
.knop:hover { border-color: var(--rand2); background: rgba(255,255,255,.06); }
.knop:active { transform: scale(.985); }
.knop:focus-visible { outline: 2px solid var(--cyaan); outline-offset: 2px; }
.knop .kic { width: 36px; height: 36px; border-radius: 11px; display: grid; place-items: center; background: rgba(255,255,255,.05); color: var(--tekst2); }
.knop .kic .ic { width: 20px; height: 20px; }
.knop .kt { min-width: 0; }
.knop .kn { font-size: 13.5px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.knop .ks { font-size: 11.5px; color: var(--tekst3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.knop .schakel { width: 38px; height: 22px; border-radius: 99px; background: rgba(255,255,255,.12); position: relative; transition: background .2s; }
.knop .schakel::after { content: ""; position: absolute; top: 3px; left: 3px; width: 16px; height: 16px; border-radius: 50%; background: #fff; transition: left .2s; box-shadow: 0 1px 3px rgba(0,0,0,.4); }
.knop.aan { border-color: color-mix(in srgb, var(--kk) 55%, transparent); background: color-mix(in srgb, var(--kk) 12%, transparent); }
.knop.aan .kic { background: color-mix(in srgb, var(--kk) 22%, transparent); color: var(--kk); }
.knop.aan .schakel { background: var(--kk); }
.knop.aan .schakel::after { left: 19px; }
.knop.bezig { opacity: .6; pointer-events: none; }
.knop.weg { opacity: .4; pointer-events: none; }
.knopgroep { font-size: 10.5px; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; color: var(--tekst3); margin: 2px 0 -4px; }

/* ---- huis ---- */
.lijst { display: grid; gap: 8px; }
.regel { display: grid; grid-template-columns: 34px 1fr auto; gap: 10px; align-items: center; padding: 9px 11px; border-radius: 12px; background: rgba(255,255,255,.035); border: 1px solid var(--rand); min-width: 0; }
.regel .ric { width: 34px; height: 34px; border-radius: 10px; display: grid; place-items: center; background: rgba(255,255,255,.05); color: var(--rk, var(--tekst2)); }
.regel .rn { font-size: 13px; font-weight: 700; }
.regel .rs { font-size: 12px; color: var(--tekst2); line-height: 1.4; }
.regel .rw { font-size: 13px; font-weight: 700; color: var(--rk, var(--tekst)); white-space: nowrap; }
.regel > div { min-width: 0; }

/* ---- voet ---- */
.voet { margin-top: 14px; }
.links { display: flex; gap: 8px; flex-wrap: wrap; padding: 0 16px; }
.links button { font: inherit; font-size: 12px; font-weight: 650; color: var(--tekst2); background: rgba(255,255,255,.04); border: 1px solid var(--rand); padding: 6px 11px; border-radius: 999px; cursor: pointer; }
.links button:hover { color: var(--tekst); border-color: var(--rand2); }
.voetregel { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; font-size: 12px; color: var(--tekst3); padding: 12px 16px 0; }

/* ---- geen bron ---- */
.geenbron { padding: 40px 24px; text-align: center; color: var(--tekst2); font-size: 14px; line-height: 1.6; }
.geenbron b { color: var(--tekst); }

/* ---- breedtes ---- */
@container (min-width: 620px) {
  .kwart { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .knoppen { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@container (min-width: 820px) {
  .hero { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .raster {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    grid-template-areas:
      "planning planning"
      "stroom verkoop"
      "modules zon"
      "huis geld"
      "bediening bediening";
  }
  .knoppen { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
@container (min-width: 1260px) {
  .hero { grid-template-columns: 1.2fr 1.15fr 1fr 1fr; }
  .raster {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.55fr) minmax(0, 1fr);
    grid-template-areas:
      "stroom planning verkoop"
      "modules planning geld"
      "zon huis huis"
      "bediening bediening bediening";
  }
  .gwrap { grid-template-rows: 250px 22px; }
  .knoppen { grid-template-columns: repeat(6, minmax(0, 1fr)); }
  .p-huis .lijst { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@container (max-width: 1259px) { .kop-mid { flex: 1 1 100%; order: 2; } }
@container (max-width: 560px) {
  .wrap { padding: 14px 12px 20px; }
  .kop-r { margin-left: 0; width: 100%; justify-content: space-between; order: 1; }
  .klok { order: -1; text-align: left; }
  .big { font-size: 26px; }
  .accu-t { grid-template-columns: 96px 1fr; gap: 12px; }
  .ring { width: 96px; height: 96px; }
  .trio { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .knop { grid-template-columns: 32px 1fr; }
  .knop .schakel { display: none; }
  .gwrap { grid-template-columns: 28px 1fr 28px; grid-template-rows: 180px 22px; }
  .tabel td, .tabel th { padding-left: 6px; padding-right: 6px; }
  .knoop .v { font-size: 17px; }
}
`;

/* Achtergrond: nachtelijk raster met zachte energielijnen. */
const ACHTERGROND = `
<div class="bg" aria-hidden="true">
  <svg preserveAspectRatio="xMidYMid slice" viewBox="0 0 1600 1000">
    <defs>
      <pattern id="ruit" width="44" height="44" patternUnits="userSpaceOnUse">
        <path d="M44 0H0V44" fill="none" stroke="rgba(150,200,255,.035)"/>
      </pattern>
      <linearGradient id="golf" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stop-color="#34d399" stop-opacity="0"/>
        <stop offset=".5" stop-color="#fbbf24" stop-opacity=".22"/>
        <stop offset="1" stop-color="#38d7f0" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <rect width="1600" height="1000" fill="url(#ruit)"/>
    <path d="M0 640 C 260 560, 420 720, 700 620 S 1180 520, 1600 600" fill="none" stroke="url(#golf)" stroke-width="2"/>
    <path d="M0 700 C 300 640, 520 780, 820 690 S 1260 600, 1600 680" fill="none" stroke="url(#golf)" stroke-width="1.2" opacity=".7"/>
    <path d="M0 210 C 340 160, 600 260, 900 190 S 1350 120, 1600 170" fill="none" stroke="url(#golf)" stroke-width="1" opacity=".5"/>
  </svg>
</div>`;

/* ------------------------------------------------------------------ */
/* De kaart                                                            */
/* ------------------------------------------------------------------ */

/* Per paneel de sleutels waar het van afhangt. */
const AFHANKELIJK = {
  kop: ["status", "cockpit", "prijs", "modus", "verwacht", "gezondheid"],
  meldingen: ["status", "tekort"],
  hero: ["soc", "beschikbaar", "capaciteit", "accu_vermogen", "gacs", "reden", "verwacht", "prijs", "uitleg",
    "blok", "besparing", "zelfvoorziening", "inkoop_vandaag", "teruglever_vandaag", "schema", "modus", "zon_werkelijk"],
  stroom: ["pv", "net", "accu_vermogen", "huis", "soc"],
  planning: ["plan", "schema", "uitleg", "blok"],
  verkoop: ["gacs", "mc", "tekort", "uitleg"],
  modules: ["modules", "koeling", "accuGezondheid", "rendement"],
  zon: ["gacs", "zon_vandaag", "zon_rest", "zon_morgen", "zon_werkelijk", "pvNauw", "bewolking", "pv"],
  huis: ["fietsen", "stofzuiger", "vaatwasser", "wasmachine", "aircoBesluit", "klimaat", "water", "temp_binnen", "temp_buiten", "huis"],
  bediening: ["nuLaden", "handLaden", "handSmart", "forceManual", "leermodus", "kalibratie", "vakantie",
    "aircoAutomaat", "fietsenOverrule", "stofzuigerOverrule", "meldingenAan", "achterhoeks"],
  geld: ["besparing", "maand", "perioden", "zelfvoorziening"],
  voet: ["meetlog", "gezondheid", "status"],
};

/* De knoppen: sleutel, naam, uitleg, icoon, kleur, vraag om bevestiging. */
const KNOPPEN = [
  { groep: "Accu" },
  { k: "nuLaden", n: "Nu laden", s: "Direct uit het net bijladen", ic: "bout", kl: "var(--groen)" },
  { k: "handLaden", n: "Handmatig laden", s: "Laden met vast vermogen", ic: "accu", kl: "var(--groen)", vraag: true },
  { k: "handSmart", n: "Smart charge", s: "Alleen zon de accu in", ic: "zon", kl: "var(--amber)", vraag: true },
  { k: "forceManual", n: "Force manual", s: "Sturing zelf overnemen", ic: "hand", kl: "var(--oranje)", vraag: true },
  { k: "kalibratie", n: "Kalibratie", s: "Accu vol laden en ijken", ic: "ijk", kl: "var(--cyaan)", vraag: true },
  { k: "leermodus", n: "Leermodus", s: "Alleen leren, niet sturen", ic: "leren", kl: "var(--violet)", vraag: true },
  { groep: "Huis" },
  { k: "vakantie", n: "Vakantiestand", s: "Minder verbruik verwacht", ic: "vakantie", kl: "var(--blauw)", vraag: true },
  { k: "aircoAutomaat", n: "Airco automaat", s: "EMS stuurt de airco", ic: "airco", kl: "var(--cyaan)" },
  { k: "fietsenOverrule", n: "Fietsen nu laden", s: "Niet wachten op het blok", ic: "fiets", kl: "var(--groen)" },
  { k: "stofzuigerOverrule", n: "Stofzuiger nu laden", s: "Niet wachten op het blok", ic: "stof", kl: "var(--groen)" },
  { k: "meldingenAan", n: "Meldingen", s: "Alle meldingen aan of uit", ic: "bel", kl: "var(--amber)" },
  { k: "achterhoeks", n: "Achterhoeks", s: "Meldingen in de streektaal", ic: "taal", kl: "var(--violet)" },
];

/* Snelkoppelingen naar de detailpagina's van het EMS-dashboard. */
const DETAIL = "/energy-management-system/";
const LINKS = [
  ["Planning", "detail-planning"], ["Kwartierplanning", "detail-kwartier"], ["Accu", "detail-accu"],
  ["Reservemarge", "detail-reservemarge"], ["Zon", "detail-zon"], ["Kosten", "detail-kosten"],
  ["Besparing", "detail-besparing"], ["Plantoetsing", "detail-plantoetsing"], ["Klimaat", "detail-klimaat"],
  ["Apparaten", "detail-apparaten"], ["Meldingen", "meldingen"], ["Gezondheid", "detail-gezondheid"],
  ["Logboek", "detail-logboek"], ["Overzicht", "overzicht"],
];

class EmsCockpitCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._vorige = {};
    this._vuil = new Set(Object.keys(AFHANKELIJK));
    this._ids = null;
    this._moduleIds = [];
    this._omkeren = false;
    this._aantal = -1;
    this._gepland = false;
    this._bezig = new Set();
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    this._config = { ...(config || {}) };
    this._ids = null;
    this._vuil = new Set(Object.keys(AFHANKELIJK));
    this._plan();
  }

  getCardSize() {
    return 26;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._gebouwd) this._bouw();

    const aantal = Object.keys(hass.states).length;
    const bron = this._bronId ? hass.states[this._bronId] : null;
    if (!this._ids || aantal !== this._aantal || bron !== this._vorigeBron) {
      const oud = JSON.stringify([this._ids, this._moduleIds, this._omkeren]);
      const uit = zoekEntiteiten(hass);
      this._ids = uit.ids;
      this._moduleIds = uit.modules;
      this._omkeren = uit.omkeren;
      this._gevonden = uit.gevonden;
      this._bronId = uit.bronId;
      this._vorigeBron = uit.bronId ? hass.states[uit.bronId] : null;
      this._aantal = aantal;
      if (JSON.stringify([this._ids, this._moduleIds, this._omkeren]) !== oud) {
        for (const p of Object.keys(AFHANKELIJK)) this._vuil.add(p);
      }
    }

    const gewijzigd = new Set();
    for (const id of Object.values(this._ids)) {
      const s = hass.states[id];
      if (s !== this._vorige[id]) {
        gewijzigd.add(id);
        this._vorige[id] = s;
      }
    }
    if (gewijzigd.size) {
      for (const [paneel, sleutels] of Object.entries(AFHANKELIJK)) {
        if (sleutels.some((k) => gewijzigd.has(this._ids[k]))) this._vuil.add(paneel);
      }
    }
    if (this._vuil.size) this._plan();
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    if (!this._tik) {
      // Klok, "over x min" en de nu-lijn lopen ook zonder nieuwe states door
      this._tik = setInterval(() => {
        this._vuil.add("kop");
        this._vuil.add("planning");
        this._vuil.add("voet");
        this._plan();
      }, 30000);
    }
  }

  disconnectedCallback() {
    if (this._tik) {
      clearInterval(this._tik);
      this._tik = null;
    }
  }

  /* ---- opbouw ---- */

  _bouw() {
    this._gebouwd = true;
    this.shadowRoot.innerHTML =
      `<style>${STIJL}</style>` +
      `<div class="root">${ACHTERGROND}<div class="wrap">` +
      `<header class="kop" data-p="kop"></header>` +
      `<div class="geenbron" data-p="geenbron" hidden></div>` +
      `<div class="meldingen" data-p="meldingen"></div>` +
      `<section class="hero" data-p="hero" aria-label="Status"></section>` +
      `<main class="raster">` +
      `<section class="paneel p-stroom" data-p="stroom"></section>` +
      `<section class="paneel p-planning" data-p="planning"></section>` +
      `<section class="paneel p-verkoop" data-p="verkoop"></section>` +
      `<section class="paneel p-modules" data-p="modules"></section>` +
      `<section class="paneel p-zon" data-p="zon"></section>` +
      `<section class="paneel p-huis" data-p="huis"></section>` +
      `<section class="paneel p-geld" data-p="geld"></section>` +
      `<section class="paneel p-bediening" data-p="bediening"></section>` +
      `</main>` +
      `<footer class="paneel voet" data-p="voet"></footer>` +
      `</div></div>`;
    this._el = {};
    for (const el of this.shadowRoot.querySelectorAll("[data-p]")) this._el[el.dataset.p] = el;

    this.shadowRoot.addEventListener("click", (ev) => {
      const doel = ev.target.closest ? ev.target : null;
      if (!doel) return;
      const knop = doel.closest("[data-knop]");
      if (knop) {
        this._schakel(knop.dataset.knop);
        return;
      }
      const nav = doel.closest("[data-nav]");
      if (nav) {
        this._ga(nav.dataset.nav);
        return;
      }
      const info = doel.closest("[data-info]");
      if (info) this._info(info.dataset.info);
    });
  }

  _plan() {
    if (this._gepland || !this._hass || !this._gebouwd) return;
    this._gepland = true;
    const doe = () => {
      this._gepland = false;
      this._teken();
    };
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(doe);
    else setTimeout(doe, 0);
  }

  _s(sleutel) {
    const id = this._ids && this._ids[sleutel];
    return id ? this._hass.states[id] : undefined;
  }

  _teken() {
    const geen = this._el.geenbron;
    if (!this._gevonden) {
      geen.hidden = false;
      geen.innerHTML =
        `<b>De sensor Dashboardbronnen van het Energy Management System is (nog) niet gevonden.</b><br>` +
        `Werk de integratie bij naar v5.71 of nieuwer en herstart Home Assistant.`;
    } else {
      geen.hidden = true;
    }
    const vuil = [...this._vuil];
    this._vuil.clear();
    for (const paneel of vuil) {
      const el = this._el[paneel];
      if (!el) continue;
      try {
        const html = this[`_${paneel}`].call(this, el);
        if (html === undefined) continue;
        if (html === null) {
          el.hidden = true;
          el.innerHTML = "";
        } else {
          el.hidden = false;
          if (el.innerHTML !== html) el.innerHTML = html;
        }
      } catch (err) {
        console.warn("EMS cockpit: paneel", paneel, "kon niet getekend worden", err);
      }
    }
  }

  /* ---- acties ---- */

  _ga(pad) {
    const doel = pad.startsWith("/") ? pad : DETAIL + pad;
    history.pushState(null, "", doel);
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
  }

  _info(sleutel) {
    const id = this._ids[sleutel];
    if (!id) return;
    const ev = new Event("hass-more-info", { bubbles: true, composed: true });
    ev.detail = { entityId: id };
    this.dispatchEvent(ev);
  }

  async _schakel(sleutel) {
    const id = this._ids[sleutel];
    const s = id && this._hass.states[id];
    const def = KNOPPEN.find((k) => k.k === sleutel);
    if (!s || !def || this._bezig.has(sleutel)) return;
    const aan = s.state === "on";
    if (def.vraag && !aan) {
      // Een stand die de sturing overneemt: eerst vragen
      if (!window.confirm(`${def.n} aanzetten?\n\n${def.s}.`)) return;
    }
    this._bezig.add(sleutel);
    this._vuil.add("bediening");
    this._plan();
    try {
      await this._hass.callService("switch", aan ? "turn_off" : "turn_on", { entity_id: id });
    } catch (err) {
      console.warn("EMS cockpit: schakelen mislukt", err);
    } finally {
      this._bezig.delete(sleutel);
      this._vuil.add("bediening");
      this._plan();
    }
  }

  /* ---- gegevens ---- */

  _accuW() {
    const v = getal(this._s("accu_vermogen"));
    if (v == null) return null;
    // Na correctie: negatief is laden, positief is ontladen (zoals het EMS rekent)
    return this._omkeren ? -v : v;
  }

  _planRijen() {
    const rijen = attr(this._s("plan"), "kwartierplanning");
    return Array.isArray(rijen) ? rijen : [];
  }

  _blokken() {
    const t = attr(this._s("schema"), "transitions");
    return Array.isArray(t) ? t : [];
  }

  _gacs(naam) {
    const v = attr(this._s("gacs"), naam);
    return v && typeof v === "object" ? v : {};
  }

  /* ---- kopregel ---- */

  _kop() {
    const nu = new Date();
    const tijd = nu.toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" });
    const datum = nu.toLocaleDateString("nl-NL", { weekday: "long", day: "numeric", month: "long" });

    const cockpit = this._s("cockpit");
    const st = bruikbaar(cockpit) ? String(cockpit.state) : null;
    const stKlasse = !st ? "" : /storing|fout/i.test(st) ? "gevaar" : /let op/i.test(st) ? "let" : "ok";
    const status = st ? chip(`<span class="stip" style="--kleur:${stKlasse === "ok" ? "var(--groen)" : stKlasse === "let" ? "var(--oranje)" : "var(--rood)"}"></span>${esc(hoofd(st.toLowerCase()))}`, `groot ${stKlasse}`) : "";

    const accuModus = this._s("modus");
    const m = modus(attr(this._s("uitleg"), "expected_mode") || (bruikbaar(accuModus) ? accuModus.state : ""));
    const modusChip = chip(`<span class="stip" style="--kleur:${m.kleur}"></span>Accu: ${esc(m.label)}`, "groot");

    const prijs = getal(this._s("prijs"));
    const drempel = num(attr(this._s("uitleg"), "expensive_price_threshold"));
    const prijsKlasse = prijs != null && drempel != null && prijs >= drempel ? "let" : "";
    const prijsChip = prijs != null ? chip(`${icoon("euro")}${ct(prijs)} ct/kWh`, `groot ${prijsKlasse}`) : "";

    return (
      `<div class="merk"><div class="logo">${icoon("bout")}</div>` +
      `<div><div class="merknaam">ENERGIECOCKPIT</div>` +
      `<div class="merksub">Energy Management System${this._hass.config && this._hass.config.location_name ? PUNT + esc(this._hass.config.location_name) : ""}</div></div></div>` +
      `<div class="kop-mid">${status}${modusChip}${prijsChip}</div>` +
      `<div class="kop-r"><div class="klok"><div class="tijd">${tijd}</div><div class="datum">${esc(datum)}</div></div></div>`
    );
  }

  /* ---- meldingen ---- */

  _meldingen() {
    const st = this._s("status");
    const punten = attr(st, "aandachtspunten") || [];
    const uit = [];
    for (const p of punten.slice(0, 4)) {
      uit.push(`<div class="melding let">${icoon("waarschuwing")}<div>${esc(p)}</div></div>`);
    }
    if (bruikbaar(st) && st.state === "Opstarten") {
      uit.unshift(`<div class="melding info">${icoon("info")}<div>${esc(attr(st, "opstarten") || "Het EMS start op.")}</div></div>`);
    }
    return uit.join("");
  }

  /* ---- statusrij ---- */

  _hero() {
    return this._tegelAccu() + this._tegelNu() + this._tegelPrijs() + this._tegelVandaag();
  }

  _tegelAccu() {
    const soc = getal(this._s("soc"));
    const ruw = getal(this._s("beschikbaar"));
    const besch = ruw == null ? null : Math.max(0, ruw);
    const cap = getal(this._s("capaciteit"));
    const w = this._accuW();
    const kleur = soc == null ? "var(--tekst3)" : soc >= 60 ? "var(--groen)" : soc >= 25 ? "var(--amber)" : "var(--rood)";
    let actie = "In rust";
    let actieKleur = "var(--tekst2)";
    if (w != null && w < -25) {
      actie = `Laadt ${fmt(Math.abs(w))} W`;
      actieKleur = "var(--groen)";
    } else if (w != null && w > 25) {
      actie = `Levert ${fmt(w)} W`;
      actieKleur = "var(--amber)";
    }
    const toets = this._gacs("verkooptoets");
    const reserve = num(toets.nodig_voor_woning_kwh);
    return (
      `<div class="tegel" style="--accent:${kleur}" data-info="soc">` +
      `<div class="lbl">Thuisaccu</div>` +
      `<div class="accu-t">${ring(soc, kleur, "laadstand")}` +
      `<div class="rijen">` +
      `<span>Nu <b style="color:${actieKleur}">${actie}</b></span>` +
      `<span>Beschikbaar <b>${fmt(besch, 2)} kWh</b></span>` +
      (cap != null ? `<span>Capaciteit <b>${fmt(cap, 2)} kWh</b></span>` : "") +
      (reserve != null ? `<span>Reserve tot blok <b>${fmt(reserve, 2)} kWh</b></span>` : "") +
      `</div></div>` +
      (typeof attr(this._s("gacs"), "haalt_de_accu_het") === "string"
        ? `<div class="sub klem" style="margin-top:10px">${esc(attr(this._s("gacs"), "haalt_de_accu_het"))}</div>`
        : "") +
      `</div>`
    );
  }

  _tegelNu() {
    const waarom = this._gacs("waarom_nu");
    const verwacht = attr(this._s("uitleg"), "expected_mode") || (bruikbaar(this._s("verwacht")) ? this._s("verwacht").state : "");
    const m = modus(verwacht);
    const kort = waarom.kort ? hoofd(waarom.kort) : m.label;
    const redenen = Array.isArray(waarom.redenen) ? waarom.redenen.slice(0, 3) : [];
    const blok = this._blokken()[1];
    return (
      `<div class="tegel" style="--accent:${m.kleur}" data-info="verhaal">` +
      `<div class="lbl">Wat doet het EMS nu</div>` +
      `<div class="tekst-m">${esc(kort)}</div>` +
      (redenen.length ? `<ul class="redenen">${redenen.map((r) => `<li>${esc(hoofd(r))}</li>`).join("")}</ul>` : "") +
      (blok
        ? `<div class="sub" style="margin-top:10px">Daarna: <b>${esc(modus(blok.mode).label)}</b> vanaf ${esc(blok.van_tekst || klok(blok.start) || "")}</div>`
        : "") +
      `</div>`
    );
  }

  _tegelPrijs() {
    const prijs = getal(this._s("prijs"));
    const uitleg = this._s("uitleg");
    const drempel = num(attr(uitleg, "expensive_price_threshold"));
    const duur = prijs != null && drempel != null && prijs >= drempel;
    const kleur = duur ? "var(--oranje)" : "var(--groen)";
    const blokStart = this._s("blok");
    const start = bruikbaar(blokStart) ? alsDatum(blokStart.state) : null;
    const eind = alsDatum(attr(blokStart, "end"));
    const rijen = this._planRijen();
    const prijzen = rijen.map((r) => num(r.prijs_ct)).filter((v) => v != null);
    const duurste = prijzen.length ? Math.max(...prijzen) : null;
    const goedkoopste = prijzen.length ? Math.min(...prijzen) : null;
    let blokTekst = STREEP;
    if (start) {
      const loopt = start.getTime() <= Date.now() && (!eind || eind.getTime() > Date.now());
      blokTekst = `${dagLabel(start)}${klok(start)}${eind ? "\u2013" + klok(eind) : ""}`;
      blokTekst += loopt ? " (loopt)" : ` (${overTijd(start)})`;
    }
    return (
      `<div class="tegel" style="--accent:${kleur}" data-info="prijs">` +
      `<div class="lbl">Stroomprijs nu</div>` +
      `<div class="big accent">${prijs == null ? STREEP : ct(prijs)}<small>ct/kWh</small></div>` +
      `<div class="sub">${duur ? "<b>Duur kwartier</b>" : "Onder de drempel voor duur"}${drempel != null ? ` (${ct(drempel)} ct)` : ""}</div>` +
      `<div class="rijen" style="margin-top:10px">` +
      `<span>Goedkoopste blok <b>${blokTekst}</b></span>` +
      (goedkoopste != null ? `<span>Laagste in plan <b>${fmt(goedkoopste, 1)} ct</b></span>` : "") +
      (duurste != null ? `<span>Hoogste in plan <b>${fmt(duurste, 1)} ct</b></span>` : "") +
      `</div></div>`
    );
  }

  _tegelVandaag() {
    const bes = this._s("besparing");
    const kosten = num(attr(bes, "werkelijke_kosten_vandaag_eur"));
    const zonder = num(attr(bes, "tegenfeitelijke_kosten_vandaag_eur"));
    const maand = num(attr(bes, "besparing_deze_maand_eur"));
    const zv = getal(this._s("zelfvoorziening"));
    const zon = this._gacs("zon_vandaag");
    const kleur = "var(--cyaan)";
    return (
      `<div class="tegel" style="--accent:${kleur}" data-info="besparing">` +
      `<div class="lbl">Vandaag</div>` +
      `<div class="big">${kosten == null ? STREEP : euro(kosten)}</div>` +
      `<div class="sub">stroomkosten tot nu${zonder != null ? `, zonder sturing ${euro(zonder)}` : ""}</div>` +
      `<div class="rijen" style="margin-top:10px">` +
      `<span>Besparing deze maand <b style="color:${maand != null && maand >= 0 ? "var(--groen)" : "var(--oranje)"}">${euroTeken(maand)}</b></span>` +
      `<span>Zon opgewekt <b>${fmt(zon.opgewekt_kwh, 1)} / ${fmt(zon.voorspeld_kwh, 1)} kWh</b></span>` +
      `<span>Zelfvoorzienend <b>${zv == null ? STREEP : fmt(zv) + "%"}</b></span>` +
      `</div></div>`
    );
  }

  /* ---- energiestroom ---- */

  _stroom() {
    const pv = Math.max(0, getal(this._s("pv")) || 0);
    const net = getal(this._s("net"));
    const accu = this._accuW();
    const huis = getal(this._s("huis"));
    const soc = getal(this._s("soc"));

    // Coordinaten in procenten van het vlak
    const P = { zon: [50, 15], net: [16, 50], huis: [84, 50], accu: [50, 85] };
    const lijn = (van, naar) => `M${van[0]} ${van[1]} L50 50 L${naar[0]} ${naar[1]}`;
    const tak = (punt) => `M${punt[0]} ${punt[1]} L50 50`;
    const snel = (w) => `${Math.max(0.5, 2.4 - Math.min(Math.abs(w || 0), 4000) / 2000).toFixed(2)}s`;
    const loop = (punt, w, kleur, naarHub) => {
      if (w == null || Math.abs(w) < 20) return "";
      const terug = naarHub ? w < 0 : w > 0;
      return `<path class="loop${terug ? " terug" : ""}" d="${tak(punt)}" stroke="${kleur}" style="--snel:${snel(w)}"/>`;
    };
    // Zon stroomt naar het midden; net: import naar het midden; huis: van het midden;
    // accu: ontladen naar het midden, laden van het midden.
    const lijnen =
      `<svg class="lijnen" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">` +
      `<path class="lijn" d="${tak(P.zon)}"/><path class="lijn" d="${tak(P.net)}"/>` +
      `<path class="lijn" d="${tak(P.huis)}"/><path class="lijn" d="${tak(P.accu)}"/>` +
      loop(P.zon, pv, "var(--amber)", true) +
      loop(P.net, net, net != null && net < 0 ? "var(--cyaan)" : "var(--rood)", true) +
      loop(P.huis, huis == null ? null : -huis, "var(--blauw)", true) +
      loop(P.accu, accu, accu != null && accu < 0 ? "var(--groen)" : "var(--amber)", true) +
      `</svg>`;
    const knoop = (pos, ic, naam, waarde, sub, kleur, gloed) =>
      `<div class="knoop" style="left:${pos[0]}%;top:${pos[1]}%;--k:${kleur};--gloed:${gloed || "transparent"}">` +
      `${icoon(ic)}<div class="n">${naam}</div><div class="v">${waarde}</div><div class="s">${sub}</div></div>`;

    const netSub = net == null ? STREEP : net < -20 ? "teruglevering" : net > 20 ? "afname" : "in balans";
    const accuSub = accu == null ? STREEP : accu < -20 ? "laadt" : accu > 20 ? "ontlaadt" : "in rust";
    return (
      paneelKop("pulse", "Energiestroom", chip("live", "ok")) +
      `<div class="pb"><div class="stroom">${lijnen}<div class="hub"></div>` +
      knoop(P.zon, "zon", "Zon", watt(pv), pv > 20 ? "wekt op" : "geen opwek", "var(--amber)", pv > 20 ? "rgba(251,191,36,.25)" : "") +
      knoop(P.net, "net", "Net", watt(net == null ? null : Math.abs(net)), netSub, net != null && net < -20 ? "var(--cyaan)" : "var(--rood)") +
      knoop(P.huis, "huis", "Huis", watt(huis), "verbruik", "var(--blauw)") +
      knoop(P.accu, "accu", "Accu", watt(accu == null ? null : Math.abs(accu)), `${accuSub}${soc != null ? PUNT + fmt(soc) + "%" : ""}`, "var(--groen)", accu != null && accu < -20 ? "rgba(52,211,153,.25)" : "") +
      `</div></div>`
    );
  }

  /* ---- planning ---- */

  _planning() {
    const rijen = this._planRijen().filter((r) => num(r.prijs_ct) != null);
    const kop = paneelKop(
      "grafiek",
      "Planning",
      `<div class="pl-legenda">` +
        `<span><i style="background:var(--groen)"></i>laden</span>` +
        `<span><i style="background:var(--oranje)"></i>verkopen</span>` +
        `<span><i style="background:var(--blauw)"></i>sparen</span>` +
        `<span><i style="background:var(--violet)"></i>slim</span>` +
        `<span><i class="lijn-i" style="background:#fff"></i>accu %</span>` +
        `<span><i style="background:rgba(250,204,21,.5)"></i>zon</span></div>`,
      "detail-planning"
    );
    if (!rijen.length) return kop + `<div class="leegmelding">Nog geen kwartierplanning.</div>`;

    // Tijden van de kwartieren: van/dag uit het plan, opgebouwd vanaf vandaag
    const tijden = [];
    let dagOffset = 0;
    let vorigeMin = -1;
    for (const r of rijen) {
      const [h, mi] = String(r.van || "00:00").split(":").map((x) => parseInt(x, 10) || 0);
      const min = h * 60 + mi;
      if (vorigeMin >= 0 && min < vorigeMin) dagOffset += 1;
      vorigeMin = min;
      const d = new Date();
      d.setHours(h, mi, 0, 0);
      d.setDate(d.getDate() + dagOffset);
      tijden.push(d);
    }

    const prijzen = rijen.map((r) => num(r.prijs_ct));
    const pMax = Math.max(...prijzen, 1);
    const pMin = Math.min(0, ...prijzen);
    const top = Math.ceil(pMax / 5) * 5;
    const bodem = pMin < 0 ? Math.floor(pMin / 5) * 5 : 0;
    const bereik = Math.max(top - bodem, 1);
    const n = rijen.length;

    const staven = rijen
      .map((r, i) => {
        const m = modus(r.modus);
        const h = ((prijzen[i] - bodem) / bereik) * 100;
        const tip =
          `${dagLabel(tijden[i])}${r.van} \u00b7 ${fmt(prijzen[i], 1)} ct \u00b7 ${m.label}` +
          (num(r.soc_procent) != null ? ` \u00b7 accu ${fmt(r.soc_procent)}%` : "") +
          (num(r.zon_kwh) ? ` \u00b7 zon ${fmt(r.zon_kwh, 2)} kWh` : "") +
          (r.tekort ? " \u00b7 tekort" : "");
        return `<div class="staaf ${m.k}${r.tekort ? " tekort" : ""}" style="height:${Math.max(2, h).toFixed(1)}%;background:${m.kleur}" title="${esc(tip)}"></div>`;
      })
      .join("");

    // Laadstand als lijn, zon als vlak (0..100 in beide richtingen)
    const x = (i) => ((i + 0.5) / n) * 100;
    const socPunten = rijen
      .map((r, i) => (num(r.soc_procent) == null ? null : `${x(i).toFixed(2)},${(100 - num(r.soc_procent)).toFixed(2)}`))
      .filter(Boolean)
      .join(" ");
    const zonMax = Math.max(0.05, ...rijen.map((r) => num(r.zon_kwh) || 0));
    const zonPunten =
      `0,100 ` +
      rijen.map((r, i) => `${x(i).toFixed(2)},${(100 - ((num(r.zon_kwh) || 0) / zonMax) * 45).toFixed(2)}`).join(" ") +
      ` 100,100`;
    const drempel = num(attr(this._s("uitleg"), "expensive_price_threshold"));
    const drempelY = drempel != null ? 100 - ((drempel * 100 - bodem) / bereik) * 100 : null;
    const svg =
      `<svg class="g-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">` +
      `<polygon class="zon-vlak" points="${zonPunten}"/>` +
      (drempelY != null && drempelY > 0 && drempelY < 100 ? `<line class="drempel" x1="0" x2="100" y1="${drempelY.toFixed(2)}" y2="${drempelY.toFixed(2)}"/>` : "") +
      (socPunten ? `<polyline class="soc-lijn" points="${socPunten}"/>` : "") +
      `</svg>`;

    // Nu-lijn
    const eerste = tijden[0].getTime();
    const laatste = tijden[n - 1].getTime() + 15 * 60000;
    const nuDeel = (Date.now() - eerste) / (laatste - eerste);
    const nuLijn = nuDeel >= 0 && nuDeel <= 1 ? `<div class="nu-lijn" style="left:${(nuDeel * 100).toFixed(2)}%"><span>NU</span></div>` : "";

    // Assen
    const yLab = [0, 0.25, 0.5, 0.75, 1]
      .map((f) => `<span style="top:${((1 - f) * 100).toFixed(1)}%">${fmt(bodem + f * bereik)}</span>`)
      .join("");
    const yRaster = [0.25, 0.5, 0.75].map((f) => `<div class="g-raster" style="top:${((1 - f) * 100).toFixed(1)}%"></div>`).join("");
    const y2Lab = [0, 50, 100].map((v) => `<span style="top:${(100 - v).toFixed(1)}%">${v}%</span>`).join("");
    const xLab = [];
    for (let i = 0; i < n; i++) {
      const d = tijden[i];
      if (d.getMinutes() !== 0) continue;
      const uur = d.getHours();
      const stap = n > 72 ? 4 : n > 40 ? 3 : 2;
      if (uur === 0) xLab.push(`<span class="dag" style="left:${x(i).toFixed(2)}%">${esc(d.toLocaleDateString("nl-NL", { weekday: "short" }))}</span>`);
      else if (uur % stap === 0) xLab.push(`<span style="left:${x(i).toFixed(2)}%">${String(uur).padStart(2, "0")}:00</span>`);
    }

    const grafiek =
      `<div class="gwrap">` +
      `<div class="g-y">${yLab}</div>` +
      `<div class="g-plot">${yRaster}<div class="staven">${staven}</div>${svg}${nuLijn}</div>` +
      `<div class="g-y2">${y2Lab}</div>` +
      `<div class="g-x">${xLab.join("")}</div>` +
      `</div>` +
      `<div class="meternoot">Staaf: prijs per kwartier (ct/kWh) in de kleur van de geplande stand. Witte lijn: verwachte accustand. Geel: verwachte zon.${drempel != null ? ` Stippellijn: drempel voor duur (${ct(drempel)} ct).` : ""}</div>`;

    // Tabel met de blokken
    const blokken = this._blokken();
    const nu = Date.now();
    const tabel = blokken.length
      ? `<div class="tabelvak"><table class="tabel"><thead><tr><th>Van</th><th>Tot</th><th>Stand</th><th class="r">Prijs (ct)</th><th class="r">Accu</th></tr></thead><tbody>` +
        blokken
          .slice(0, 10)
          .map((b) => {
            const m = modus(b.mode);
            const s = alsDatum(b.start);
            const e = alsDatum(b.end);
            const loopt = s && e && s.getTime() <= nu && e.getTime() > nu;
            const lo = num(b.min_price_per_kwh);
            const hi = num(b.max_price_per_kwh);
            const prijs = lo == null ? STREEP : hi == null || hi - lo < 0.0005 ? ct(lo) : `${ct(lo)}\u2013${ct(hi)}`;
            const accu = b.accu_tekst || this._accuTekst(b.soc_begin, b.soc_eind);
            return (
              `<tr class="${loopt ? "nu" : ""}"><td>${esc(b.van_tekst || klok(b.start) || "")}</td>` +
              `<td>${esc(b.tot_tekst || klok(b.end) || "")}</td>` +
              `<td><span class="modus" style="--kleur:${m.kleur}"><i></i>${esc(m.label)}</span></td>` +
              `<td class="r">${prijs}</td><td class="r soc-pijl">${esc(accu)}</td></tr>`
            );
          })
          .join("") +
        `</tbody></table></div>`
      : "";
    return kop + `<div class="pb">${grafiek}${tabel}</div>`;
  }

  _accuTekst(begin, eind) {
    if (num(eind) == null) return STREEP;
    if (num(begin) == null || Math.round(begin) === Math.round(eind)) return `${Math.round(eind)}%`;
    return `${Math.round(begin)}${PIJL}${Math.round(eind)}%`;
  }

  /* ---- verkoop en reserve ---- */

  _verkoop() {
    const toets = this._gacs("verkooptoets");
    const marge = this._gacs("reservemarge");
    const mc = this._s("mc");
    const tekort = this._s("tekort");
    const mag = toets.mag_verkopen === true;
    const besch = num(toets.beschikbaar_kwh);
    const nodig = num(toets.nodig_voor_woning_kwh);
    const tot = num(toets.nodig_tot_blok_kwh);
    const na = num(toets.nodig_na_blok_kwh);
    const vrij = num(toets.verkoop_na_blok_vrij_kwh);
    const terug = num(toets.terugladen_in_blok_eur);

    const rechts = chip(mag ? "verkopen mag" : "houdt vast", mag ? "ok" : "");
    const meter =
      besch != null && nodig != null
        ? `<div class="meterrij"><div class="meterkop"><span class="lbl">Beschikbaar tegen nodig voor het huis</span>` +
          `<span class="w">${fmt(besch, 2)} / ${fmt(nodig, 2)}<small>kWh</small></span></div>` +
          balk(nodig > 0 ? besch / Math.max(besch, nodig) : 1, mag ? "var(--groen)" : "var(--blauw)", nodig > 0 ? nodig / Math.max(besch, nodig) : null) +
          `<div class="meternoot">Het witte streepje is de reserve: daaronder verkoopt het EMS nooit.</div></div>`
        : "";
    const cijfers =
      `<div class="trio">` +
      mini("Tot het blok", tot == null ? STREEP : `${fmt(tot, 2)}<small>kWh</small>`, "altijd beschermd") +
      mini("Na het blok", na == null ? STREEP : `${fmt(na, 2)}<small>kWh</small>`, "laadt het blok bij") +
      mini("Vrij te verkopen", vrij == null ? STREEP : `${fmt(vrij, 2)}<small>kWh</small>`, terug != null ? `terugladen ${ct(terug)} ct` : toets.verkoop_na_blok_reden ? esc(toets.verkoop_na_blok_reden) : "", vrij ? "var(--oranje)" : "") +
      `</div>`;

    const onderdelen = Array.isArray(marge.onderdelen) ? marge.onderdelen : [];
    const totaal = num(marge.totaal_procent);
    const margeHtml = onderdelen.length
      ? `<div class="meterrij"><div class="meterkop"><span class="lbl">Veiligheidsmarge</span><span class="w">${fmtTeken(totaal)}%</span></div>` +
        `<div class="rijen">${onderdelen.map((o) => `<span>${esc(o.naam)} <b>${fmtTeken(o.procent)}%</b></span>`).join("")}</div></div>`
      : "";

    const kans = getal(mc);
    const kansHtml =
      kans != null
        ? `<div class="meterrij"><div class="meterkop"><span class="lbl">Kans op tekort tot het blok</span><span class="w" style="color:${kans >= 50 ? "var(--rood)" : kans >= 20 ? "var(--oranje)" : "var(--groen)"}">${fmt(kans)}%</span></div>` +
          balk(kans / 100, kans >= 50 ? "var(--rood)" : kans >= 20 ? "var(--oranje)" : "var(--groen)") +
          `<div class="meternoot">Monte Carlo over verbruik en zon. Tekortnachten 7 dagen: <b>${fmt(getal(tekort))}</b>${num(attr(tekort, "tekortnacht_tot_nu_kwh")) ? ` \u00b7 deze nacht ${fmt(attr(tekort, "tekortnacht_tot_nu_kwh"), 2)} kWh van het net` : ""}.</div></div>`
        : "";
    const reden = toets.reden ? `<div class="zin">${esc(toets.reden)}</div>` : "";
    return paneelKop("schild", "Verkopen en reserve", rechts, "detail-reservemarge") + `<div class="pb">${meter}${cijfers}${reden}${margeHtml}${kansHtml}</div>`;
  }

  /* ---- accumodules ---- */

  _modules() {
    const mods = attr(this._s("modules"), "modules");
    const koeling = this._s("koeling");
    const gez = this._s("accuGezondheid");
    const rend = getal(this._s("rendement"));
    const rechts = [
      rend != null ? chip(`rendement ${fmt(rend, 1)}%`) : "",
      bruikbaar(gez) ? chip(`${fmt(getal(gez))} cycli`) : "",
    ].join("");
    if (!Array.isArray(mods) || !mods.length) return paneelKop("cellen", "Accumodules", rechts, "detail-accu") + `<div class="leegmelding">Geen modulegegevens.</div>`;
    const lijst = mods
      .map((m) => {
        const soc = num(m.soc_percent);
        const zwak = (Array.isArray(m.drift_op) && m.drift_op.length) || (num(m.cel_min_v) != null && num(m.cel_min_v) < 3.0);
        const kleur = soc == null ? "var(--tekst3)" : soc >= 60 ? "var(--groen)" : soc >= 20 ? "var(--amber)" : "var(--rood)";
        const vlaggen = [
          zwak && Array.isArray(m.drift_op) && m.drift_op.length ? chip("loopt uit de pas", "let") : "",
          num(m.cel_min_v) != null && num(m.cel_min_v) < 3.0 ? chip(`cel ${fmt(m.cel_min_v, 2)} V`, "gevaar") : "",
          m.melding_uit ? chip("melding uit", "uit") : "",
        ].join("");
        return (
          `<div class="module${zwak ? " zwak" : ""}">` +
          `<div class="module-kop"><b>${esc(m.naam || "Module " + m.module)}</b><span class="w" style="color:${kleur}">${soc == null ? STREEP : fmt(soc) + "%"}</span></div>` +
          balk((soc || 0) / 100, kleur) +
          `<div class="module-cijfers"><span>cel <b>${fmt(m.cel_min_v, 2)}\u2013${fmt(m.cel_max_v, 2)} V</b></span>` +
          `<span>verschil <b>${fmt((num(m.cel_delta_v) || 0) * 1000)} mV</b></span>` +
          `<span><b>${fmt(m.temperatuur_c)}${GRAAD}C</b></span>` +
          `<span><b>${fmt(m.vermogen_w)} W</b></span></div>` +
          (vlaggen ? `<div class="vlaggen">${vlaggen}</div>` : "") +
          `</div>`
        );
      })
      .join("");
    const koel = bruikbaar(koeling)
      ? `<div class="regel" style="--rk:${attr(koeling, "ventilator_aan") ? "var(--cyaan)" : "var(--tekst2)"}"><div class="ric">${icoon("ventilator")}</div>` +
        `<div><div class="rn">Koeling ${attr(koeling, "ventilator_aan") ? "aan" : "uit"}</div><div class="rs">${esc(attr(koeling, "reden") || "")}</div></div>` +
        `<div class="rw">${fmt(attr(koeling, "accu_c"))}${GRAAD}C</div></div>`
      : "";
    return paneelKop("cellen", "Accumodules", rechts, "detail-accu") + `<div class="pb"><div class="lijst">${lijst}</div>${koel}</div>`;
  }

  /* ---- zon ---- */

  _zon() {
    const zon = this._gacs("zon_vandaag");
    const verwacht = num(zon.voorspeld_kwh) ?? getal(this._s("zon_vandaag"));
    const opgewekt = num(zon.opgewekt_kwh) ?? getal(this._s("zon_werkelijk"));
    const rest = getal(this._s("zon_rest"));
    const morgen = getal(this._s("zon_morgen"));
    const pv = getal(this._s("pv"));
    const nauw = getal(this._s("pvNauw"));
    const bew = this._s("bewolking");
    const uitstel = this._gacs("zon_uitstelplan");
    const deel = verwacht ? Math.min(1, (opgewekt || 0) / verwacht) : 0;
    return (
      paneelKop("zon", "Zon", pv != null ? chip(`${watt(pv)} nu`, pv > 20 ? "ok" : "") : "", "detail-zon") +
      `<div class="pb">` +
      `<div class="meterrij"><div class="meterkop"><span class="lbl">Vandaag opgewekt</span><span class="w">${fmt(opgewekt, 1)} / ${fmt(verwacht, 1)}<small>kWh</small></span></div>` +
      balk(deel, "var(--amber)") +
      `</div>` +
      `<div class="trio">` +
      mini("Nog te komen", rest == null ? STREEP : `${fmt(rest, 1)}<small>kWh</small>`, "vandaag") +
      mini("Morgen", morgen == null ? STREEP : `${fmt(morgen, 1)}<small>kWh</small>`, "voorspeld") +
      mini("Bewolking", bruikbaar(bew) ? `${fmt(getal(bew))}<small>%</small>` : STREEP, esc(attr(bew, "label") || "")) +
      `</div>` +
      (nauw != null ? `<div class="meternoot">Voorspelling gisteren: ${fmtTeken(nauw, 1)}% tegen de werkelijkheid.</div>` : "") +
      (uitstel.reden ? `<div class="zin"><b>Zon opvangen uitstellen: ${uitstel.uitstellen ? "ja" : "nee"}.</b> ${esc(uitstel.reden)}</div>` : "") +
      `</div>`
    );
  }

  /* ---- huis en apparaten ---- */

  _huis() {
    const regel = (ic, naam, sub, waarde, kleur = "") =>
      `<div class="regel"${kleur ? ` style="--rk:${kleur}"` : ""}><div class="ric">${icoon(ic)}</div>` +
      `<div><div class="rn">${esc(naam)}</div>${sub ? `<div class="rs">${sub}</div>` : ""}</div><div class="rw">${waarde}</div></div>`;
    const status = (s) => {
      const t = apparaatTekst(s);
      const kl = bruikbaar(s) && /laadt|bezig|draait/.test(s.state) ? "var(--groen)" : bruikbaar(s) && /wacht/.test(s.state) ? "var(--amber)" : "";
      return [t, kl];
    };
    const uit = [];
    const fiets = this._s("fietsen");
    if (fiets) {
      const [t, k] = status(fiets);
      uit.push(regel("fiets", "Fietsladers", "", esc(t), k));
    }
    const stof = this._s("stofzuiger");
    if (stof) {
      const [t, k] = status(stof);
      uit.push(regel("stof", "Steelstofzuiger", "", esc(t), k));
    }
    for (const [sleutel, ic, naam] of [["vaatwasser", "vaat", "Vaatwasser"], ["wasmachine", "was", "Wasmachine"]]) {
      const s = this._s(sleutel);
      if (!s) continue;
      const voortgang = num(attr(s, "geschatte_voortgang_procent"));
      const [t, k] = status(s);
      uit.push(regel(ic, naam, voortgang != null && voortgang > 0 && voortgang < 100 ? `${fmt(voortgang)}% klaar` : "", esc(t), k));
    }
    const besluit = this._s("aircoBesluit");
    const klimaat = this._s("klimaat");
    const binnen = getal(this._s("temp_binnen"));
    const buiten = getal(this._s("temp_buiten"));
    if (besluit || klimaat) {
      const advies = attr(klimaat, "verwarmingsadvies") || {};
      const sub = advies.advies
        ? `Warmte nu: ${advies.advies === "airco" ? "airco" : "cv"} goedkoopst${num(advies.airco_eur_per_kwh_warmte) != null ? ` (${ct(advies.airco_eur_per_kwh_warmte)} tegen ${ct(advies.gas_eur_per_kwh_warmte)} ct/kWh warmte)` : ""}`
        : esc(attr(besluit, "tekst") || "");
      uit.push(
        regel("airco", "Klimaat", sub,
          `${binnen != null ? fmt(binnen, 1) + GRAAD : STREEP}${buiten != null ? ` <span class="leeg">/ ${fmt(buiten, 1)}${GRAAD}</span>` : ""}`,
          "var(--cyaan)")
      );
    }
    const water = this._s("water");
    if (water) {
      const liter = num(attr(water, "vandaag_liter"));
      const gem = num(attr(water, "gemiddeld_liter_per_dag"));
      uit.push(regel("druppel", "Water", gem != null ? `gemiddeld ${fmt(gem)} L per dag` : "", `${liter == null ? STREEP : fmt(liter) + " L"}`, "var(--blauw)"));
    }
    const huis = getal(this._s("huis"));
    return (
      paneelKop("huis", "Huis en apparaten", huis != null ? chip(`${watt(huis)} nu`) : "", "detail-apparaten") +
      (uit.length ? `<div class="pb"><div class="lijst">${uit.join("")}</div></div>` : `<div class="leegmelding">Geen apparaten ingesteld.</div>`)
    );
  }

  /* ---- geld ---- */

  _geld() {
    const bes = this._s("besparing");
    const maandS = this._s("maand");
    const per = (attr(this._s("perioden"), "perioden") || {}).perioden || {};
    const week = per.week || {};
    const maand = per.maand || {};
    const vandaag = per.vandaag || {};
    const bmaand = num(attr(bes, "besparing_deze_maand_eur"));
    const ball = num(attr(bes, "besparing_all_time_eur"));
    const verkocht = num(attr(maandS, "current_month_discharge_value_eur"));
    const geladen = num(attr(maandS, "current_month_charge_cost_eur"));
    const netto = getal(maandS);
    return (
      paneelKop("euro", "Geld", "", "detail-besparing") +
      `<div class="pb">` +
      `<div class="duo">` +
      mini("Besparing maand", euroTeken(bmaand), "t.o.v. zonder sturing", bmaand != null && bmaand >= 0 ? "var(--groen)" : "var(--oranje)") +
      mini("Besparing totaal", euroTeken(ball), "sinds de start", ball != null && ball >= 0 ? "var(--groen)" : "var(--oranje)") +
      `</div>` +
      `<div class="rijen">` +
      `<span>Verkocht in dure kwartieren (maand) <b>${euro(verkocht)}</b></span>` +
      `<span>Laadkosten uit het net (maand) <b>${euro(geladen)}</b></span>` +
      `<span>Accu netto (maand) <b style="color:${netto != null && netto >= 0 ? "var(--groen)" : "var(--oranje)"}">${euroTeken(netto)}</b></span>` +
      `</div>` +
      `<div class="trio">` +
      mini("Vandaag", euro(vandaag.kosten_eur), `${fmt(vandaag.import_kwh, 1)} kWh van het net`) +
      mini("Week", euro(week.kosten_eur), `${fmt(week.opwek_kwh, 0)} kWh zon`) +
      mini("Maand", euro(maand.kosten_eur), `${fmt(maand.opwek_kwh, 0)} kWh zon`) +
      `</div></div>`
    );
  }

  /* ---- bediening ---- */

  _bediening() {
    const knoppen = KNOPPEN.map((k) => {
      if (k.groep) return `<div class="knopgroep" style="grid-column:1/-1">${esc(k.groep)}</div>`;
      const s = this._s(k.k);
      if (!s) return "";
      const aan = s.state === "on";
      const weg = !bruikbaar(s);
      const bezig = this._bezig.has(k.k);
      return (
        `<button class="knop${aan ? " aan" : ""}${bezig ? " bezig" : ""}${weg ? " weg" : ""}" data-knop="${k.k}" ` +
        `style="--kk:${k.kl}" aria-pressed="${aan}" title="${esc(k.s)}">` +
        `<span class="kic">${icoon(k.ic)}</span><span class="kt"><div class="kn">${esc(k.n)}</div><div class="ks">${esc(aan ? "Aan" : k.s)}</div></span>` +
        `<span class="schakel"></span></button>`
      );
    }).join("");
    return paneelKop("knop", "Bediening", chip("tik om te schakelen")) + `<div class="pb"><div class="knoppen">${knoppen}</div></div>`;
  }

  /* ---- voet ---- */

  _voet() {
    const meetlog = this._s("meetlog");
    const gez = this._s("gezondheid");
    const st = this._s("status");
    const bijgewerkt = attr(st, "last_successful_update");
    const links = LINKS.map(([n, p]) => `<button data-nav="${p}">${esc(n)}</button>`).join("");
    return (
      `<div class="links" style="padding-top:14px">${links}</div>` +
      `<div class="voetregel"><span>${bruikbaar(gez) ? esc(gez.state) : ""}${bruikbaar(meetlog) ? PUNT + esc(meetlog.state) : ""}</span>` +
      `<span>${bijgewerkt ? `Bijgewerkt ${esc(geleden(bijgewerkt) || "")}` + PUNT : ""}Cockpit v${esc(VERSIE)}</span></div>`
    );
  }
}

/* ------------------------------------------------------------------ */
/* Strategie                                                           */
/* ------------------------------------------------------------------ */

const KAART = "ems-cockpit-card";

class EmsStrategie {
  static hoofdView() {
    return { type: "panel", cards: [{ type: `custom:${KAART}` }] };
  }
}

class EmsViewStrategy extends HTMLTemplateElement {
  static async generate() {
    return EmsStrategie.hoofdView();
  }
}

class EmsDashboardStrategy extends HTMLTemplateElement {
  static async generate(config) {
    return {
      views: [
        {
          title: (config && config.title) || "Energiecockpit",
          path: "cockpit",
          icon: "mdi:home-lightning-bolt",
          ...EmsStrategie.hoofdView(),
        },
      ],
    };
  }
}

const registreer = (naam, klasse) => {
  if (!customElements.get(naam)) customElements.define(naam, klasse);
};

registreer(KAART, EmsCockpitCard);
registreer("ll-strategy-view-ems", EmsViewStrategy);
registreer("ll-strategy-dashboard-ems", EmsDashboardStrategy);

window.customCards = window.customCards || [];
if (!window.customCards.some((k) => k.type === KAART)) {
  window.customCards.push({
    type: KAART,
    name: "EMS energiecockpit",
    description: "Alles van het Energy Management System op een pagina: accu, planning, verkoop, zon, apparaten, geld en de knoppen.",
    preview: false,
  });
}

console.info(
  `%c EMS %c energiecockpit geladen \u00b7 v${VERSIE} `,
  "background:#0f3b2e;color:#fbbf24;font-weight:700",
  ""
);
