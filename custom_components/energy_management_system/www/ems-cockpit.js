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
  // v5.129.0: de batterijlader in de keuken
  lader: "batterijlader_status",
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
  // v5.100: zelfanalyse, prijsverwachting en de generale repetitie 2027
  zelfanalyse: "zelfanalyse",
  prijsverwachting: "prijsverwachting",
  repetitie: "repetitie_2027",
  dagarchief: "dagarchief",
  // v5.105.0: is er iemand thuis (bovenin de cockpit)
  aanwezig: "aanwezigheid",
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
  laderOverrule: "batterijlader_override",
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
/* v5.118.0: een tijdstip met de dag erbij als het niet vandaag is
   ("21:15", "morgen 21:15", "vr 21:15"). */
const klokDag = (w) => {
  const d = alsDatum(w);
  return d ? dagLabel(d) + klok(d) : null;
};
/* v5.118.0: eindtijd met een eigen dag alleen als die anders is dan het begin. */
const klokEind = (start, eind) => {
  const s = alsDatum(start);
  const e = alsDatum(eind);
  if (!e) return null;
  return s && s.toDateString() === e.toDateString() ? klok(e) : klokDag(e);
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

/** Tijden van de kwartieren in het plan: van (HH:MM), opgebouwd vanaf vandaag. */
const planTijden = (rijen) => {
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
  return tijden;
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
  // v5.93.0: de standen van fietsladers en steelstofzuiger
  test_aan: "kijkt of er iets aan hangt",
  wacht_op_apparaat: "niets aangesloten",
  aan_het_laden: "laadt",
  voltooid: "opgeladen",
  voltooid_vandaag: "vandaag al geladen",
  overruled: "handmatig (overrule)",
};
/* v5.93.0: een kleur per stand (gevraagd 12-10 11:50). Groen = bezig of
   laden, amber = wacht op het goedkope blok, cyaan = test, blauw = klaar,
   violet = handmatig, grijs = niets aangesloten of uit. */
const APPARAAT_KLEUR = [
  [/^(laadt|aan_het_laden|bezig|draait|running|run|actief)$/, "var(--groen)"],
  [/^test_aan$/, "var(--cyaan)"],
  [/^wacht_op_apparaat$/, "var(--tekst3)"],
  [/wacht|gepland|delayed/, "var(--amber)"],
  [/^(klaar|vol|voltooid|voltooid_vandaag|finished|ready)$/, "var(--blauw)"],
  [/^overruled$/, "var(--violet)"],
  [/^(uit|idle|off|inactive)$/, "var(--tekst3)"],
];
const apparaatKleur = (s) => {
  if (!bruikbaar(s)) return "";
  const st = String(s.state).toLowerCase();
  const hit = APPARAAT_KLEUR.find(([re]) => re.test(st));
  return hit ? hit[1] : "";
};
const apparaatTekst = (s) => {
  if (!bruikbaar(s)) return STREEP;
  return hoofd(APPARAAT_STATUS[s.state] || String(s.state).replace(/_/g, " "));
};
/* v5.131.3: bezig of aan het laden - dan het vermogen erbij (gevraagd 26-10:
   "Laat hierbij ook de vermogens zien als actief of als er geladen wordt"). */
const APPARAAT_ACTIEF = /^(laadt|aan_het_laden|bezig|draait|running|run|actief)$/;
const apparaatVermogen = (s, states) => {
  if (!bruikbaar(s) || !APPARAAT_ACTIEF.test(String(s.state).toLowerCase())) return null;
  const id = attr(s, "vermogen_sensor");
  const p = id && states ? getal(states[id]) : null;
  return p == null ? null : p;
};
const APPARAAT_SLEUTELS = ["fietsen", "stofzuiger", "lader", "vaatwasser", "wasmachine"];
const vermogenTekst = (w) => {
  if (Math.abs(w) >= 1000) return `${fmt(w / 1000, 2)} kW`;
  return `${fmt(w, Math.abs(w) < 10 ? 1 : 0)} W`;
};

/* ------------------------------------------------------------------ */
/* Iconen (zelf getekend, geen externe bestanden)                      */
/* ------------------------------------------------------------------ */

const ICOON = {
  bout: '<path d="M13 2 4 14h6l-1 8 9-12h-6z"/>',
  accu: '<rect x="3" y="7" width="16" height="10" rx="2"/><path d="M21 10v4"/><path d="M7 10v4M10.5 10v4"/>',
  zon: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/>',
  net: '<path d="M8 22 12 2l4 20"/><path d="M6.5 9h11M5 15h14M9.5 2h5"/>',
  persoon: '<circle cx="12" cy="7.5" r="3.5"/><path d="M5 21a7 7 0 0 1 14 0"/>',
  maan: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
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
.wrap { container-type: inline-size; max-width: 1760px; margin: 0 auto; padding: 14px 18px 20px; }
.ic { width: 18px; height: 18px; flex: none; }
small { font-size: .55em; font-weight: 600; color: var(--tekst2); margin-left: 3px; letter-spacing: 0; }
.leeg { color: var(--tekst3); opacity: .75; }
[hidden] { display: none !important; }
.num, .big, td, .mini .w, .kv b { font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; }

/* ---- kop ---- */
.kop { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; padding: 2px 2px 10px; }
.merk { display: flex; align-items: center; gap: 12px; min-width: 0; }
.logo {
  width: 38px; height: 38px; border-radius: 12px; display: grid; place-items: center; color: #fff;
  background: linear-gradient(135deg, #f59e0b, #10b981 70%, #0ea5e9);
  box-shadow: 0 6px 22px rgba(16, 185, 129, .40), inset 0 1px 0 rgba(255,255,255,.3);
}
.logo .ic { width: 22px; height: 22px; fill: #fff; stroke: none; }
.merknaam { font-size: 17px; font-weight: 800; letter-spacing: .14em; line-height: 1.1; }
.merksub { font-size: 12px; color: var(--tekst2); letter-spacing: .04em; margin-top: 2px; }
.kop-mid { display: flex; gap: 8px; flex-wrap: wrap; flex: 1 1 0; min-width: 0; }
.kop-r { display: flex; align-items: center; gap: 18px; margin-left: auto; }
.klok { text-align: right; line-height: 1.1; }
.klok .tijd { font-size: 26px; font-weight: 700; letter-spacing: .02em; font-variant-numeric: tabular-nums; }
.klok .datum { font-size: 12px; color: var(--tekst2); margin-top: 3px; }
.chip {
  display: inline-flex; align-items: center; gap: 6px; white-space: nowrap;
  font-size: 12px; font-weight: 600; color: var(--tekst2);
  padding: 5px 10px; border-radius: 999px; background: rgba(255,255,255,.05); border: 1px solid var(--rand);
  max-width: 100%; overflow: hidden; text-overflow: ellipsis;
}
.chip .ic { width: 14px; height: 14px; }
.chip.groot { font-size: 13px; padding: 6px 11px; color: var(--tekst); background: var(--paneel2); }
.chip.ok { color: var(--groen); border-color: rgba(52, 211, 153, .35); }
.chip.let { color: var(--oranje); border-color: rgba(251, 146, 60, .4); }
.chip.gevaar { color: #fff; background: rgba(251, 77, 101, .22); border-color: rgba(251, 77, 101, .55); }
.chip.uit { opacity: .55; }
.chip.aanwezig .ic { width: 14px; height: 14px; }
.chip.aanwezig .leeg { font-weight: 500; margin-left: 2px; }
.stip { width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex: none; background: var(--kleur, var(--tekst3)); box-shadow: 0 0 8px var(--kleur, transparent); }

/* ---- meldingen ---- */
.meldingen { display: grid; gap: 8px; margin-bottom: 10px; }
.meldingen:empty { display: none; }
.melding {
  display: flex; align-items: flex-start; gap: 10px; padding: 9px 14px; border-radius: 14px;
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
.hero { display: grid; gap: 10px; grid-template-columns: 1fr; margin-bottom: 10px; }
.tegel {
  position: relative; overflow: hidden; padding: 12px 14px 12px 17px; border-radius: var(--r);
  background: linear-gradient(160deg, rgba(26, 40, 64, .74), rgba(10, 16, 30, .74));
  border: 1px solid var(--rand);
  backdrop-filter: blur(16px) saturate(130%); -webkit-backdrop-filter: blur(16px) saturate(130%);
  box-shadow: 0 12px 34px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.05); min-width: 0;
}
.tegel::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--accent, var(--tekst3)); box-shadow: 0 0 18px var(--accent, transparent); }
.tegel::after { content: ""; position: absolute; inset: 0; pointer-events: none; background: radial-gradient(120% 90% at 0% 0%, color-mix(in srgb, var(--accent, transparent) 18%, transparent), transparent 55%); }
.tegel > * { position: relative; z-index: 1; }
.lbl { font-size: 11px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--tekst2); }
.big { font-size: 26px; font-weight: 800; line-height: 1.1; letter-spacing: .01em; margin: 4px 0 3px; }
.big.accent { color: var(--accent); }
.sub { font-size: 13px; color: var(--tekst2); line-height: 1.45; }
.sub b { color: var(--tekst); font-weight: 600; }
.tekst-m { font-size: 16px; font-weight: 700; line-height: 1.3; margin: 5px 0 4px; }
.klem { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.accu-t { display: grid; grid-template-columns: 96px 1fr; gap: 12px; align-items: center; }
.ring { width: 96px; height: 96px; display: block; }
.ring-t { font-size: 30px; font-weight: 800; fill: var(--tekst); font-variant-numeric: tabular-nums; }
.ring-p { font-size: 14px; fill: var(--tekst2); font-weight: 700; }
.ring-o { font-size: 10px; fill: var(--tekst2); font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.ring-boog { transition: stroke-dasharray .8s ease; }
.rijen { display: grid; gap: 3px; font-size: 12.5px; color: var(--tekst2); min-width: 0; }
.rijen span { display: flex; justify-content: space-between; gap: 10px; }
.rijen b { color: var(--tekst); font-variant-numeric: tabular-nums; white-space: nowrap; }
.za-blok { margin-top: 8px; padding-top: 7px; border-top: 1px solid var(--lijn, rgba(127,127,127,.25)); display: grid; gap: 8px; min-width: 0; }
.za-k { display: flex; justify-content: space-between; gap: 10px; font-size: 12.5px; color: var(--tekst2); }
.za-k b { color: var(--tekst); white-space: nowrap; }
.za-s { font-size: 11.5px; color: var(--tekst2); overflow-wrap: anywhere; }
.za-l { margin: 2px 0 0 16px; padding: 0; font-size: 11.5px; color: var(--tekst2); }
.za-l i { opacity: .75; }
.chip-reden { font-weight: 500; opacity: .85; margin-left: 2px; }
.pv-wrap { position: relative; display: grid; grid-template-columns: 34px 1fr; grid-template-rows: 150px 22px; margin-top: 2px; min-width: 0; }
.pv-wrap .g-x { grid-column: 2; }
.pv-svg { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
.pv-svg rect:hover { fill-opacity: 1; }
.pv-klein { grid-template-rows: 80px 20px; }
.uitklap { border-top: 1px solid var(--rand); padding-top: 6px; }
.uitklap > summary { cursor: pointer; font-size: 11.5px; font-weight: 700; color: var(--tekst2); letter-spacing: .04em; list-style: none; }
.uitklap > summary::-webkit-details-marker { display: none; }
.uitklap > summary::before { content: "+ "; color: var(--violet); }
.uitklap[open] > summary::before { content: "- "; }
.uitklap[open] > summary { margin-bottom: 6px; }
.pv-grens { position: absolute; top: 0; bottom: 0; width: 1px; background: rgba(167, 139, 250, .45); }
.pv-grens span { position: absolute; top: 2px; left: 5px; font-size: 10px; font-weight: 700; color: var(--violet); white-space: nowrap; }
.redenen { margin: 8px 0 0; padding: 0; list-style: none; display: grid; gap: 4px; font-size: 12.5px; color: var(--tekst2); }
.redenen li { display: flex; gap: 8px; }
.redenen li::before { content: ""; width: 5px; height: 5px; border-radius: 50%; background: var(--accent, var(--tekst3)); margin-top: 7px; flex: none; }

/* ---- raster ---- */
.raster {
  display: grid; gap: 10px; grid-template-columns: minmax(0, 1fr);
  grid-template-areas: "stroom" "planning" "prijzen" "verkoop" "modules" "zon" "huis" "bediening" "geld";
}
.paneel {
  min-width: 0; border-radius: var(--r);
  background: linear-gradient(180deg, var(--paneel), var(--paneel2)); border: 1px solid var(--rand);
  backdrop-filter: blur(16px) saturate(130%); -webkit-backdrop-filter: blur(16px) saturate(130%);
  box-shadow: 0 12px 34px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.05);
  padding: 0 0 12px; display: flex; flex-direction: column;
}
.kol { display: contents; }
.p-stroom { grid-area: stroom; }
.p-planning { grid-area: planning; }
.p-verkoop { grid-area: verkoop; }
.p-modules { grid-area: modules; }
.p-zon { grid-area: zon; }
.p-huis { grid-area: huis; }
.p-bediening { grid-area: bediening; }
.p-geld { grid-area: geld; }
.p-prijzen { grid-area: prijzen; }
.ph { display: flex; align-items: center; gap: 8px; padding: 10px 14px 7px; color: var(--tekst2); min-width: 0; flex-wrap: wrap; }
.ph h2 { margin: 0; font-size: 12px; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; color: var(--tekst); }
.ph .ic { color: var(--amber); }
.ph-r { margin-left: auto; display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; align-items: center; min-width: 0; }
.meer { display: grid; place-items: center; width: 26px; height: 26px; border-radius: 9px; border: 1px solid var(--rand); background: rgba(255,255,255,.04); color: var(--tekst2); cursor: pointer; padding: 0; }
.meer:hover { color: var(--tekst); border-color: var(--rand2); }
.meer .ic { width: 15px; height: 15px; color: currentColor; }
.pb { padding: 0 14px; display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px; }
.leegmelding { padding: 6px 16px 0; color: var(--tekst3); font-size: 13px; }
.mini { padding: 7px 10px; border-radius: 11px; background: rgba(255,255,255,.035); border: 1px solid var(--rand); min-width: 0; }
.mini .lbl { font-size: 10px; letter-spacing: .1em; }
.mini .w { font-size: 18px; font-weight: 750; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mini .s { font-size: 12px; color: var(--tekst2); margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.duo { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.trio { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.kwart { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.balk { position: relative; height: 8px; border-radius: 99px; background: rgba(255,255,255,.07); overflow: hidden; }
.balk b { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 99px; box-shadow: 0 0 12px currentColor; transition: width .6s ease; }
.balk i { position: absolute; top: -2px; bottom: -2px; width: 2px; background: #fff; border-radius: 2px; opacity: .85; }
.meterrij { display: grid; gap: 4px; }
.meterkop { display: flex; justify-content: space-between; align-items: baseline; gap: 2px 10px; flex-wrap: wrap; }
.meterkop .lbl { font-size: 11px; }
.meterkop .w { font-size: 16px; font-weight: 750; font-variant-numeric: tabular-nums; white-space: nowrap; }
.meternoot { font-size: 12px; color: var(--tekst3); line-height: 1.45; }
.zin { font-size: 13px; color: var(--tekst2); line-height: 1.45; padding: 7px 10px; border-radius: 12px; background: rgba(255,255,255,.035); border: 1px solid var(--rand); }
.zin b { color: var(--tekst); }

/* ---- energiestroom (v5.91) ---- */
.stroom { position: relative; width: 100%; max-width: 480px; margin: 0 auto; aspect-ratio: 1.12 / 1; }
.stroom svg.lijnen { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }
.spoor { fill: none; stroke: rgba(255,255,255,.07); stroke-width: 7; stroke-linecap: round; vector-effect: non-scaling-stroke; }
.loop {
  fill: none; stroke-linecap: round; vector-effect: non-scaling-stroke;
  stroke-dasharray: 0.1 13; animation: loop var(--snel, 1.6s) linear infinite;
  filter: drop-shadow(0 0 4px var(--kl, transparent));
}
.loop.terug { animation-direction: reverse; }
@keyframes loop { to { stroke-dashoffset: -26.2; } }
@media (prefers-reduced-motion: reduce) { .loop { animation: none; stroke-dasharray: none; opacity: .55; } }
.knoop {
  position: absolute; transform: translate(-50%, -50%); width: 32%; min-height: 25%;
  display: flex; flex-direction: column; justify-content: center; gap: 3px;
  padding: 7px 10px; border-radius: 14px; text-align: left;
  background: linear-gradient(160deg, rgba(22, 34, 56, .92), rgba(8, 13, 25, .92));
  border: 1px solid var(--rand2);
  box-shadow: 0 10px 26px rgba(0,0,0,.38), inset 0 1px 0 rgba(255,255,255,.05), 0 0 26px var(--gloed, transparent);
}
.knoop::before { content: ""; position: absolute; left: 12px; right: 12px; top: 0; height: 2px; border-radius: 0 0 2px 2px; background: var(--k); opacity: var(--actief, .25); }
.knoop .kk { display: flex; align-items: center; gap: 7px; }
.knoop .badge { width: 26px; height: 26px; border-radius: 8px; display: grid; place-items: center; flex: none; background: color-mix(in srgb, var(--k) 16%, transparent); }
.knoop .badge .ic { width: 16px; height: 16px; color: var(--k); }
.knoop .n { font-size: 10.5px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; color: var(--tekst2); }
.knoop .v { font-size: 20px; font-weight: 800; line-height: 1.1; font-variant-numeric: tabular-nums; white-space: nowrap; }
.knoop .v small { font-size: 11px; }
.knoop .s { font-size: 11.5px; color: var(--tekst2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.knoop .s.rest { color: var(--tekst3); font-size: 11px; white-space: normal; }
.knoop .soc { height: 4px; border-radius: 99px; background: rgba(255,255,255,.08); overflow: hidden; margin-top: 2px; }
.knoop .soc i { display: block; height: 100%; border-radius: 99px; background: linear-gradient(90deg, var(--groen), #6ee7b7); }
.hub {
  position: absolute; left: 50%; top: 50%; width: 18px; height: 18px; border-radius: 50%; transform: translate(-50%,-50%);
  background: radial-gradient(circle at 35% 35%, #fff7d6, var(--amber) 55%, #b45309);
  box-shadow: 0 0 0 4px rgba(251,191,36,.12), 0 0 18px rgba(251,191,36,.7);
}
.planvolg {
  display: grid; grid-template-columns: auto 1fr; gap: 7px 10px; align-items: center;
  padding: 8px 10px; border-radius: 13px; background: rgba(255,255,255,.035); border: 1px solid var(--rand);
}
.planvolg .zinpv { font-size: 13px; color: var(--tekst); line-height: 1.4; min-width: 0; }
.planvolg .rij3 { grid-column: 1 / -1; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.planvolg .cel { padding: 5px 8px; border-radius: 10px; background: rgba(0,0,0,.18); border: 1px solid var(--rand); min-width: 0; }
.planvolg .cel .l { font-size: 10px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: var(--tekst3); }
.planvolg .cel .s { font-size: 11px; color: var(--tekst2); }
.planvolg .cel .w { font-size: 15px; font-weight: 750; font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.planvolg .dag { grid-column: 1 / -1; font-size: 11.5px; color: var(--tekst3); }
/* v5.99.1: kleuren zoals in het schema (zon amber, accu laden groen, ontladen amber) */
.planvolg .cel.k { border-top: 2px solid var(--k); background: color-mix(in srgb, var(--k) 7%, rgba(0,0,0,.18)); }
.planvolg .cel.k > .w, .planvolg .cel.k .w { color: var(--k); }
.planvolg .rk { grid-column: 1 / -1; margin-bottom: -4px; font-size: 10.5px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: var(--tekst2); }

/* ---- planning ---- */
.pl-legenda { display: flex; flex-wrap: wrap; gap: 12px; font-size: 11.5px; color: var(--tekst2); }
.pl-legenda i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 5px; vertical-align: -1px; }
.pl-legenda .lijn-i { height: 3px; border-radius: 2px; vertical-align: 3px; }
.gwrap { position: relative; display: grid; grid-template-columns: 34px 1fr 34px; grid-template-rows: 180px 22px; }
.g-y, .g-y2 { position: relative; }
.g-y span, .g-y2 span, .g-x span { position: absolute; font-size: 10.5px; color: var(--tekst3); font-variant-numeric: tabular-nums; white-space: nowrap; }
.g-y span { right: 7px; transform: translateY(-50%); }
.g-y2 span { left: 7px; transform: translateY(-50%); }
.g-plot { position: relative; border-left: 1px solid rgba(255,255,255,.08); border-bottom: 1px solid rgba(255,255,255,.12); }
.g-raster { position: absolute; left: 0; right: 0; height: 1px; background: rgba(255,255,255,.05); }
/* v5.99.6: de tussenruimte schaalt mee met de staaf (clip-path in procenten
   van de staaf zelf) in plaats van een vaste gap van 1px. Bij een
   browserzoom onder 100% viel die 1px weg en liepen de staven in elkaar
   over (gemeld 16-10). */
.staven { position: absolute; inset: 0; display: flex; align-items: flex-end; padding: 0 1px; }
.staaf { flex: 1 1 0; min-width: 0; opacity: .88; position: relative; clip-path: inset(0 12% -8px 12% round 3px 3px 0 0); }
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
.tabel th { text-align: left; font-size: 10.5px; letter-spacing: .1em; text-transform: uppercase; color: var(--tekst3); font-weight: 700; padding: 0 8px 5px; }
.tabel td { padding: 5px 8px; border-top: 1px solid rgba(255,255,255,.06); white-space: nowrap; }
.tabel td.r, .tabel th.r { text-align: right; }
.tabel tr.nu td { background: rgba(56, 215, 240, .07); }
.tabel tr.nu td:first-child { box-shadow: inset 3px 0 0 var(--cyaan); }
.modus { display: inline-flex; align-items: center; gap: 7px; font-weight: 650; }
.modus i { width: 9px; height: 9px; border-radius: 3px; background: var(--kleur); box-shadow: 0 0 8px var(--kleur); }
.soc-pijl { color: var(--tekst2); }
.soc-pijl b { color: var(--tekst); }
.tabelvak { overflow-x: auto; margin: 0 -4px; }

/* ---- modules ---- */
.module { display: grid; gap: 5px; padding: 8px 10px; border-radius: 12px; background: rgba(255,255,255,.035); border: 1px solid var(--rand); }
.module.zwak { border-color: rgba(251, 146, 60, .45); background: rgba(251, 146, 60, .06); }
.module-kop { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.module-kop b { font-size: 14px; }
.module-kop .w { font-size: 18px; font-weight: 800; font-variant-numeric: tabular-nums; }
.module-cijfers { display: flex; gap: 12px; flex-wrap: wrap; font-size: 12px; color: var(--tekst2); }
.module-cijfers b { color: var(--tekst); font-variant-numeric: tabular-nums; }
.vlaggen { display: flex; gap: 6px; flex-wrap: wrap; }

/* ---- bediening ---- */
.knoppen { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.knop {
  font: inherit; color: var(--tekst); text-align: left; cursor: pointer;
  display: grid; grid-template-columns: 30px 1fr auto; align-items: center; gap: 9px;
  padding: 7px 10px; border-radius: 12px; border: 1px solid var(--rand);
  background: rgba(255,255,255,.035); transition: background .2s, border-color .2s, transform .1s;
  min-width: 0;
}
.knop:hover { border-color: var(--rand2); background: rgba(255,255,255,.06); }
.knop:active { transform: scale(.985); }
.knop:focus-visible { outline: 2px solid var(--cyaan); outline-offset: 2px; }
.knop .kic { width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center; background: rgba(255,255,255,.05); color: var(--tekst2); }
.knop .kic .ic { width: 18px; height: 18px; }
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
.lijst { display: grid; gap: 6px; }
.regel { display: grid; grid-template-columns: 28px 1fr auto; gap: 9px; align-items: center; padding: 6px 9px; border-radius: 12px; background: rgba(255,255,255,.035); border: 1px solid var(--rand); min-width: 0; }
.regel .ric { width: 28px; height: 28px; border-radius: 9px; display: grid; place-items: center; background: rgba(255,255,255,.05); color: var(--rk, var(--tekst2)); }
.regel .rn { font-size: 13px; font-weight: 700; }
.regel .rs { font-size: 12px; color: var(--tekst2); line-height: 1.35; }
.regel .rw { font-size: 13px; font-weight: 700; color: var(--rk, var(--tekst)); white-space: nowrap; }
.regel > div { min-width: 0; }

/* ---- voet ---- */
.voet { margin-top: 10px; }
.links { display: flex; gap: 6px; flex-wrap: wrap; padding: 0 14px; }
.links button { font: inherit; font-size: 12px; font-weight: 650; color: var(--tekst2); background: rgba(255,255,255,.04); border: 1px solid var(--rand); padding: 6px 11px; border-radius: 999px; cursor: pointer; }
.links button:hover { color: var(--tekst); border-color: var(--rand2); }
.voetregel { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; font-size: 12px; color: var(--tekst3); padding: 8px 14px 0; }

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
      "prijzen prijzen"
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
      "k1 k2 k3"
      "bediening bediening bediening";
    align-items: start;
  }
  .kol { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
  .k1 { grid-area: k1; } .k2 { grid-area: k2; } .k3 { grid-area: k3; }
  .gwrap { grid-template-rows: 210px 22px; }
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
  stroom: ["pv", "net", "accu_vermogen", "huis", "soc", "plan", "beschikbaar", "capaciteit"],
  planning: ["plan", "schema", "uitleg", "blok"],
  verkoop: ["gacs", "mc", "tekort", "uitleg", "blok"],
  modules: ["modules", "koeling", "accuGezondheid", "rendement"],
  zon: ["gacs", "zon_vandaag", "zon_rest", "zon_morgen", "zon_werkelijk", "pvNauw", "bewolking", "pv"],
  huis: ["fietsen", "stofzuiger", "lader", "vaatwasser", "wasmachine", "aircoBesluit", "klimaat", "water", "temp_binnen", "temp_buiten", "huis"],
  bediening: ["nuLaden", "handLaden", "handSmart", "forceManual", "leermodus", "kalibratie", "vakantie",
    "aircoAutomaat", "fietsenOverrule", "stofzuigerOverrule", "laderOverrule", "meldingenAan", "achterhoeks"],
  geld: ["besparing", "maand", "perioden", "zelfvoorziening", "zelfanalyse", "repetitie", "dagarchief"],
  prijzen: ["prijsverwachting", "plan", "uitleg"],
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
  { k: "laderOverrule", n: "Batterijlader handmatig", s: "EMS laat de lader met rust", ic: "accu", kl: "var(--groen)" },
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

/* ---- rustig scrollen (v5.71.1) ----
   Op mobiel (vooral iOS, dat geen scroll anchoring kent) verspringt de pagina
   als een paneel tijdens het scrollen opnieuw wordt opgebouwd. Daarom:
   tijdens aanraken en scrollen niets tekenen, pas kort na het loslaten. */
const SCROLL = { tot: 0, aan: false, klaar: false };
const volgScroll = () => {
  if (SCROLL.klaar || typeof window === "undefined") return;
  SCROLL.klaar = true;
  const opt = { passive: true, capture: true };
  const rust = (ms) => () => {
    SCROLL.tot = Math.max(SCROLL.tot, Date.now() + ms);
  };
  window.addEventListener("scroll", rust(400), opt);
  window.addEventListener("wheel", rust(400), opt);
  window.addEventListener("touchmove", rust(400), opt);
  window.addEventListener("touchstart", () => {
    SCROLL.aan = true;
    rust(400)();
  }, opt);
  const los = () => {
    SCROLL.aan = false;
    rust(500)();
  };
  window.addEventListener("touchend", los, opt);
  window.addEventListener("touchcancel", los, opt);
};
const scrolltNog = () => SCROLL.aan || Date.now() < SCROLL.tot;

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
    // v5.131.3: het vermogen van een apparaat dat bezig is of laadt, live
    for (const k of APPARAAT_SLEUTELS) {
      const st = hass.states[this._ids[k]];
      if (!bruikbaar(st) || !APPARAAT_ACTIEF.test(String(st.state).toLowerCase())) continue;
      const vid = attr(st, "vermogen_sensor");
      if (!vid) continue;
      const s = hass.states[vid];
      if (s !== this._vorige[`vermogen:${vid}`]) {
        this._vorige[`vermogen:${vid}`] = s;
        this._vuil.add("huis");
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
    this._html = {};
    volgScroll();
    this.shadowRoot.innerHTML =
      `<style>${STIJL}</style>` +
      `<div class="root">${ACHTERGROND}<div class="wrap">` +
      `<header class="kop" data-p="kop"></header>` +
      `<div class="geenbron" data-p="geenbron" hidden></div>` +
      `<div class="meldingen" data-p="meldingen"></div>` +
      `<section class="hero" data-p="hero" aria-label="Status"></section>` +
      // v5.104.2: drie kolommen die elk hun eigen hoogte volgen. In een
      // gewoon raster liep de planning over twee rijen en bleef eronder
      // een groot gat ("Cockpit is opzich super! alleen de grote lege
      // ruimte"). Op smallere schermen doen de kolommen niet mee
      // (display: contents) en geldt het raster zoals het was.
      `<main class="raster">` +
      `<div class="kol k1">` +
      `<section class="paneel p-stroom" data-p="stroom"></section>` +
      `<section class="paneel p-modules" data-p="modules"></section>` +
      `</div><div class="kol k2">` +
      `<section class="paneel p-planning" data-p="planning"></section>` +
      // v5.113.0: prijzen een week vooruit en hoe goed de verwachting is -
      // eigen paneel in de brede middenkolom; het paneel Geld was er bijna
      // twee keer zo lang door ("cockpit is vrij groot geworden").
      `<section class="paneel p-prijzen" data-p="prijzen"></section>` +
      `<section class="paneel p-huis" data-p="huis"></section>` +
      `</div><div class="kol k3">` +
      `<section class="paneel p-verkoop" data-p="verkoop"></section>` +
      `<section class="paneel p-geld" data-p="geld"></section>` +
      // v5.105.0: zon rechts - met echte gegevens was de middelste kolom
      // ruim 500 px langer dan de rechter.
      `<section class="paneel p-zon" data-p="zon"></section>` +
      `</div>` +
      `<section class="paneel p-bediening" data-p="bediening"></section>` +
      `</main>` +
      `<footer class="paneel voet" data-p="voet"></footer>` +
      `</div></div>`;
    this._el = {};
    for (const el of this.shadowRoot.querySelectorAll("[data-p]")) this._el[el.dataset.p] = el;

    // v5.113.0: uitklapblokken blijven open of dicht bij een nieuwe opbouw
    this._uitgeklapt = this._uitgeklapt || {};
    this.shadowRoot.addEventListener("toggle", (ev) => {
      const d = ev.target;
      if (d && d.dataset && d.dataset.uitklap) this._uitgeklapt[d.dataset.uitklap] = d.open;
    }, true);
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
      if (scrolltNog()) {
        // Pas tekenen als de gebruiker klaar is met scrollen
        setTimeout(doe, 250);
        return;
      }
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
      if (geen.hidden) {
        geen.hidden = false;
        geen.innerHTML =
          `<b>De sensor Dashboardbronnen van het Energy Management System is (nog) niet gevonden.</b><br>` +
          `Werk de integratie bij naar v5.71 of nieuwer en herstart Home Assistant.`;
      }
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
        // Vergelijken met de vorige opbouw, niet met innerHTML (dat schrijft
        // de browser anders terug, waardoor elk paneel steeds opnieuw werd
        // opgebouwd)
        if (this._html[paneel] === html) continue;
        this._html[paneel] = html;
        if (html === null) {
          el.hidden = true;
          el.innerHTML = "";
        } else {
          el.hidden = false;
          el.innerHTML = html;
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

  /* Loopt het goedkope laadblok nu? Geeft {eind: "16:15"} of null (v5.93.0). */
  _blokLoopt() {
    const b = this._s("blok");
    if (!bruikbaar(b)) return null;
    const begin = Date.parse(b.state);
    const eind = Date.parse(attr(b, "end") || "");
    const nu = Date.now();
    if (!(begin <= nu) || !(eind > nu)) return null;
    return { eind: new Date(eind).toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" }) };
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
    // v5.114.1: bij iets anders dan goed de reden er kort achter
    // (gevraagd 21-10 15:35: "waar is de storing? Graag korte tekst achter de storingsmelding")
    const redenVol = stKlasse && stKlasse !== "ok" ? String(attr(cockpit, "reden") || "").split(" \u00b7 ")[0] : "";
    const redenKort = redenVol.length > 70 ? redenVol.slice(0, 68) + "..." : redenVol;
    const status = st ? chip(`<span class="stip" style="--kleur:${stKlasse === "ok" ? "var(--groen)" : stKlasse === "let" ? "var(--oranje)" : "var(--rood)"}"></span>${esc(hoofd(st.toLowerCase()))}` +
      (redenKort ? ` <span class="chip-reden" title="${esc(redenVol)}">${esc(redenKort)}</span>` : ""), `groot ${stKlasse}`) : "";

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
      `<div class="kop-mid">${status}${this._aanwezigChip()}${modusChip}${prijsChip}</div>` +
      `<div class="kop-r"><div class="klok"><div class="tijd">${tijd}</div><div class="datum">${esc(datum)}</div></div></div>`
    );
  }

  /* v5.105.0: de aanwezigheid zoals het EMS die afleidt - gevraagd 19-10:
     "tevens de analyse van het EMS of er iemand thuis is of niet (boven aan
     in dashboard)". Staat, sinds wanneer, en waarop het rust. */
  _aanwezigChip() {
    const a = attr(this._s("aanwezig"), "aanwezigheid");
    if (!a || !a.beschikbaar || !a.nu) return "";
    const STAAT = {
      /* v5.127.0: "Iemand thuis" - het huis is bezet, niet per se jij. */
      thuis: ["Iemand thuis", "var(--groen)", "persoon", "ok"],
      weg: ["Niemand thuis", "var(--amber)", "huis", "let"],
      slaapt: ["Slaapt", "var(--violet)", "maan", ""],
    };
    const [label, kleur, ic, klasse] = STAAT[a.nu] || [hoofd(String(a.nu)), "var(--tekst3)", "huis", ""];
    const tl = Array.isArray(a.tijdlijn) && a.tijdlijn.length ? a.tijdlijn[0] : null;
    const sinds = tl && tl.staat === a.nu && tl.van ? ` sinds ${tl.van}` : "";
    const laatst = Array.isArray(a.laatst_gezien) && a.laatst_gezien.length ? a.laatst_gezien[0] : null;
    const minuten = laatst ? num(laatst.minuten_geleden) : null;
    let beweging = laatst && minuten != null
      ? `${PUNT}beweging ${minuten < 1 ? "zojuist" : minuten < 60 ? `${Math.round(minuten)} min geleden` : `${fmt(minuten / 60, 1)} u geleden`}`
      : "";
    /* v5.106.0: beweging die bij een leeg huis niet als thuiskomst telde
       (geen deur, te kort, op een plek - bijvoorbeeld de hond). */
    const gen = a.thuiskomst && Array.isArray(a.thuiskomst.genegeerd) ? a.thuiskomst.genegeerd[0] : null;
    const genT = gen && gen.tijd ? new Date(gen.tijd) : null;
    const genRecent = a.nu === "weg" && genT && !isNaN(genT) && Date.now() - genT.getTime() < 3600000;
    if (genRecent) {
      beweging = `${PUNT}beweging ${genT.toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" })} genegeerd (geen deur)`;
    }
    /* v5.127.0: per telefoon, gevraagd 25-10 ("ik ben al behoorlijk veel
       weggeweest, toch thuis sinds 08:52"). */
    const tel = Array.isArray(a.telefoons) ? a.telefoons : [];
    const telTekst = tel.map((t) => {
      const voornaam = String(t.naam || "").split(" ")[0];
      const waar = t.thuis ? "thuis" : (t.staat && !["not_home", "unknown", "unavailable"].includes(t.staat) ? `bij ${String(t.staat).replace(/^thuis\s+/i, "")}` : "weg");
      return `${voornaam} ${waar}${t.sinds ? ` sinds ${t.sinds}` : ""}`;
    }).join(PUNT);
    const titel = [
      telTekst ? `Telefoons: ${telTekst} (een telefoon thuis telt als thuis; weg zegt niets)` : "",
      genRecent ? `Genegeerd: ${gen.naam} - ${gen.reden}. Thuis pas bij een deur, tv, kraan, lamp met de hand of 5 min beweging op 2 plekken.` : "",
      tl && tl.aanleiding ? `Waarom: ${tl.aanleiding}` : "",
      laatst ? `Laatst gezien: ${laatst.naam}` : "",
      num(a.afwezig_na_minuten) != null ? `Weg na ${a.afwezig_na_minuten} min zonder beweging` : "",
      num(a.typisch_thuis_percentage) != null ? `Normaal op dit uur ${a.typisch_thuis_percentage}% thuis` : "",
    ].filter(Boolean).join(" \n");
    return `<span class="chip groot aanwezig ${klasse}" title="${esc(titel)}">` +
      `<span class="stip" style="--kleur:${kleur}"></span>${icoon(ic)}${esc(label + sinds)}` +
      `<span class="leeg">${esc((telTekst ? PUNT + telTekst : "") + beweging)}</span></span>`;
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
    const kort = waarom.kop ? hoofd(waarom.kop) : waarom.kort ? hoofd(waarom.kort) : m.label;
    const redenen = Array.isArray(waarom.redenen) ? waarom.redenen.slice(0, 3) : [];
    const blok = this._blokken()[1];
    return (
      `<div class="tegel" style="--accent:${m.kleur}" data-info="verhaal">` +
      `<div class="lbl">Wat doet het EMS nu</div>` +
      `<div class="tekst-m">${esc(kort)}</div>` +
      (redenen.length ? `<ul class="redenen">${redenen.map((r) => `<li>${esc(hoofd(r))}</li>`).join("")}</ul>` : "") +
      (blok
        ? `<div class="sub" style="margin-top:10px">Daarna: <b>${esc(modus(blok.mode).label)}</b> vanaf ${esc(blok.van_tekst || klokDag(blok.start) || "")}</div>`
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
      blokTekst = `${dagLabel(start)}${klok(start)}${eind ? "\u2013" + klokEind(start, eind) : ""}`;
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
      `<div class="sub">stroomkosten tot nu${zonder != null ? `, zonder accu ${euro(zonder)}` : ""}</div>` +
      `<div class="rijen" style="margin-top:10px">` +
      `<span>Besparing deze maand <b style="color:${maand != null && maand >= 0 ? "var(--groen)" : "var(--oranje)"}">${euroTeken(maand)}</b></span>` +
      `<span>Zon opgewekt <b>${fmt(zon.opgewekt_kwh, 1)} / ${fmt(zon.voorspeld_kwh, 1)} kWh</b></span>` +
      `<span>Zelfvoorzienend <b>${zv == null ? STREEP : fmt(zv) + "%"}</b></span>` +
      `</div></div>`
    );
  }

  /* ---- energiestroom (v5.91) ---- */

  _stroom() {
    const pv = Math.max(0, getal(this._s("pv")) || 0);
    const net = getal(this._s("net"));
    const accu = this._accuW();
    const huis = getal(this._s("huis"));
    const soc = getal(this._s("soc"));

    // Coordinaten in procenten van het vlak
    const P = { zon: [50, 15], net: [17, 50], huis: [83, 50], accu: [50, 85] };
    const tak = (p) => `M${p[0]} ${p[1]} L50 50`;
    const snel = (w) => `${Math.max(0.45, 2.2 - Math.min(Math.abs(w || 0), 4000) / 2200).toFixed(2)}s`;
    const dikte = (w) => (3 + Math.min(Math.abs(w || 0), 3000) / 1000).toFixed(1);
    // w > 0: stroomt naar het midden
    const loop = (p, w, kleur) => {
      if (w == null || Math.abs(w) < 20) return "";
      return `<path class="loop${w < 0 ? " terug" : ""}" d="${tak(p)}" stroke="${kleur}" ` +
        `style="--snel:${snel(w)};--kl:${kleur};stroke-width:${dikte(w)}"/>`;
    };
    const netKleur = net != null && net < 0 ? "var(--cyaan)" : "var(--rood)";
    const accuKleur = accu != null && accu < 0 ? "var(--groen)" : "var(--amber)";
    const lijnen =
      `<svg class="lijnen" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">` +
      Object.values(P).map((p) => `<path class="spoor" d="${tak(p)}"/>`).join("") +
      loop(P.zon, pv, "var(--amber)") +
      loop(P.net, net, netKleur) +
      loop(P.huis, huis == null ? null : -huis, "var(--blauw)") +
      loop(P.accu, accu, accuKleur) +
      `</svg>`;
    const knoop = (pos, ic, naam, waarde, sub, kleur, actief, extra = "") =>
      `<div class="knoop" style="left:${pos[0]}%;top:${pos[1]}%;--k:${kleur};--actief:${actief ? 1 : 0.25};` +
      `--gloed:${actief ? `color-mix(in srgb, ${kleur} 22%, transparent)` : "transparent"}">` +
      `<div class="kk"><span class="badge">${icoon(ic)}</span><span class="n">${naam}</span></div>` +
      `<div class="v">${waarde}</div><div class="s">${sub}</div>${extra}</div>`;

    const netSub = net == null ? STREEP : net < -20 ? "teruglevering" : net > 20 ? "afname van het net" : "in balans";
    const accuSub = accu == null ? STREEP : accu < -20 ? "laadt" : accu > 20 ? "ontlaadt" : "in rust";
    const socBalk = soc == null ? "" : `<div class="soc" title="Laadstand ${fmt(soc)}%"><i style="width:${Math.max(0, Math.min(100, soc))}%"></i></div>`;
    const resttijd = this._accuResttijd(accu, soc);
    return (
      paneelKop("pulse", "Energiestroom", chip("live", "ok")) +
      `<div class="pb"><div class="stroom">${lijnen}<div class="hub"></div>` +
      knoop(P.zon, "zon", "Zon", watt(pv), pv > 20 ? "wekt op" : "geen opwek", "var(--amber)", pv > 20) +
      knoop(P.net, "net", "Net", watt(net == null ? null : Math.abs(net)), netSub, netKleur, net != null && Math.abs(net) > 20) +
      knoop(P.huis, "huis", "Huis", watt(huis), "verbruik", "var(--blauw)", huis != null && huis > 20) +
      knoop(P.accu, "accu", "Accu", watt(accu == null ? null : Math.abs(accu)),
        `${accuSub}${soc != null ? PUNT + fmt(soc) + "%" : ""}`, accuKleur, accu != null && Math.abs(accu) > 20,
        socBalk + (resttijd ? `<div class="s rest" title="Bij het huidige vermogen">${resttijd}</div>` : "")) +
      `</div>${this._planvolgingRegel()}</div>`
    );
  }

  /* Hoe lang nog tot vol of leeg bij het huidige vermogen (v5.92) */
  _accuResttijd(accu, soc) {
    if (accu == null || Math.abs(accu) < 50) return "";
    const kw = Math.abs(accu) / 1000;
    let kwh = null;
    if (accu < 0) {
      // laden: wat er nog in past tot 100%
      const cap = getal(this._s("capaciteit"));
      if (cap == null || soc == null) return "";
      kwh = cap * Math.max(0, 100 - soc) / 100;
    } else {
      // ontladen: wat er boven de ondergrens nog in zit
      kwh = getal(this._s("beschikbaar"));
    }
    if (kwh == null) return "";
    const uren = kwh / kw;
    if (!(uren > 0) || uren > 24) return "";
    const klaar = new Date(Date.now() + uren * 3600000);
    const u = Math.floor(uren);
    const m = Math.round((uren - u) * 60);
    const duur = u ? `${u}u${String(m).padStart(2, "0")}` : `${Math.max(1, m)} min`;
    return `${accu < 0 ? "vol" : "leeg"} om ${klaar.toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" })} (${duur})`;
  }

  /* Gepland tegen gemeten accuvermogen (v5.91) */
  _planvolgingRegel() {
    const pv = attr(this._s("plan"), "planvolging");
    const nu = pv && pv.nu;
    if (!nu || !nu.beschikbaar) return "";
    const kl = nu.status === "volgens plan" ? "ok" : nu.status === "verklaard" ? "" : "let";
    // v5.93.2: "andere keuze" als de sturing iets anders koos dan het plan
    const label = nu.status === "volgens plan" ? "volgens plan" : nu.status === "verklaard" ? "verklaard"
      : nu.status === "afwijking sturing" ? "andere keuze" : "afwijking";
    // Teken zoals het EMS: positief ontladen, negatief laden
    const rw = (w) => {
      const n = num(w);
      if (n == null) return `<div class="w">${STREEP}</div>`;
      if (Math.abs(n) < 50) return `<div class="w">0<small>W</small></div><div class="s">in rust</div>`;
      return `<div class="w">${watt(Math.abs(n))}</div><div class="s">${n < 0 ? "laden" : "ontladen"}</div>`;
    };
    const verschil = num(nu.verschil_w);
    const dag = pv.vandaag;
    // v5.99.1: kleur zoals de accu in het schema: laden groen, ontladen amber
    const accuK = (w) => {
      const n = num(w);
      if (n == null || Math.abs(n) < 50) return "cel";
      return `cel k" style="--k:${n < 0 ? "var(--groen)" : "var(--amber)"}`;
    };
    return (
      `<div class="planvolg">` +
      chip(label, kl) +
      `<div class="zinpv">${esc(nu.tekst || "")}</div>` +
      `<div class="rk">Accu</div>` +
      `<div class="rij3">` +
      `<div class="${accuK(nu.gepland_accu_w)}"><div class="l">Gepland</div><div class="w">${rw(nu.gepland_accu_w)}</div></div>` +
      `<div class="${accuK(nu.gemeten_accu_w)}"><div class="l">Gemeten</div><div class="w">${rw(nu.gemeten_accu_w)}</div></div>` +
      `<div class="${accuK(verschil)}"><div class="l">Verschil</div><div class="w">${verschil == null ? STREEP : watt(Math.abs(verschil))}</div>` +
      `<div class="s">${nu.verschil_tekst ? esc(nu.verschil_tekst) : verschil == null || Math.abs(verschil) < 50 ? "geen" : verschil < 0 ? "meer laden" : "meer ontladen"}</div></div>` +
      `</div>` +
      this._planvolgingZon(nu) +
      (dag ? `<div class="dag">Vandaag ${fmt(dag.volgens_plan_procent)}% van ${dag.kwartieren} kwartieren volgens plan` +
        `${dag.afwijking_accu ? `${PUNT}${dag.afwijking_accu}\u00d7 wijkt de accu zelf af` : ""}` +
        `${num(dag.zon_verschil_kwh) != null ? `${PUNT}zon ${fmtTeken(dag.zon_verschil_kwh, 1)} kWh t.o.v. voorspeld` : ""}</div>` : "") +
      `</div>`
    );
  }

  /* Gepland (voorspelling in het plan) tegen gemeten zonvermogen (v5.99) */
  _planvolgingZon(nu) {
    if (num(nu.gepland_zon_w) == null && num(nu.gemeten_zon_w) == null) return "";
    const zw = (w) => {
      const n = num(w);
      if (n == null) return `<div class="w">${STREEP}</div>`;
      return `<div class="w">${watt(Math.max(0, n))}</div><div class="s">${n >= 50 ? "opwek" : "geen opwek"}</div>`;
    };
    const d = num(nu.zon_verschil_w);
    // v5.99.1: zon amber zoals in het schema; minder zon gedempt
    const zonK = (w, gedempt = false) => {
      const n = num(w);
      if (n == null || Math.abs(n) < 50) return "cel";
      return `cel k" style="--k:${gedempt ? "var(--tekst2)" : "var(--amber)"}`;
    };
    const tekst = nu.zon_verschil_tekst || (d == null ? "onbekend" : Math.abs(d) < 50 ? "geen" : d > 0 ? "meer zon" : "minder zon");
    return (
      `<div class="rk">Zon</div>` +
      `<div class="rij3">` +
      `<div class="${zonK(nu.gepland_zon_w)}"><div class="l">Gepland</div>${zw(nu.gepland_zon_w)}</div>` +
      `<div class="${zonK(nu.gemeten_zon_w)}"><div class="l">Gemeten</div>${zw(nu.gemeten_zon_w)}</div>` +
      `<div class="${zonK(d, d != null && d < 0)}"><div class="l">Verschil</div><div class="w">${d == null ? STREEP : watt(Math.abs(d))}</div>` +
      `<div class="s">${esc(tekst)}</div></div>` +
      `</div>`
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
    const tijden = planTijden(rijen);

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
      `<div class="meternoot">Staaf: prijs per kwartier (ct/kWh) in de kleur van de geplande stand. Witte lijn: verwachte accustand. Geel: verwachte zon.${drempel != null ? ` Stippellijn: drempel voor duur (${ct(drempel)} ct).` : ""}</div>` +
      this._laadplanRegel();

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
              `<tr class="${loopt ? "nu" : ""}"><td>${esc(b.van_tekst || klokDag(b.start) || "")}</td>` +
              `<td>${esc(b.tot_tekst || klokDag(b.end) || "")}</td>` +
              `<td><span class="modus" style="--kleur:${m.kleur}"><i></i>${esc(m.label)}</span></td>` +
              `<td class="r">${prijs}</td><td class="r soc-pijl">${esc(accu)}</td></tr>`
            );
          })
          .join("") +
        `</tbody></table></div>`
      : "";
    return kop + `<div class="pb">${grafiek}${tabel}</div>`;
  }

  /* v5.88: wanneer de laadplanning (laden uit het net) het laatst veranderde. */
  _laadplanRegel() {
    const w = attr(this._s("plan"), "laadplan_gewijzigd") || {};
    const d = alsDatum(w.om);
    if (!d) return "";
    const wanneer = `${dagLabel(d)}${klok(w.om)}`;
    return (
      `<div class="sub laadplan">Laadplanning gewijzigd: <b>${esc(wanneer)}</b> (${esc(geleden(w.om) || "")})` +
      ` \u00b7 nu: ${esc(w.blokken || "")}` +
      (w.was ? ` \u00b7 was: ${esc(w.was)}` : "") +
      `</div>`
    );
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
    // v5.96.2: de tegel toont het TOTAAL vrij te verkopen (zoals de
    // uitleg eronder); het deel na het blok dat het blok terugladt staat
    // er als "waarvan" onder. Eerder stond hier alleen dat deel (0,90 tegen
    // 2,80 in de tekst). Mag er niet verkocht worden: 0.
    const vrij = num(toets.vrij_te_verkopen_kwh) ?? (toets.mag_verkopen === false ? 0 : null);
    const naBlokVrij = toets.verkoop_na_blok_toegepast ? num(toets.verkoop_na_blok_vrij_kwh) : null;
    const blokLoopt = this._blokLoopt();
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
      (blokLoopt
        ? mini("Tot het blok", "nu", `laadblok loopt${blokLoopt.eind ? " tot " + blokLoopt.eind : ""}`) +
          mini("Na het blok", STREEP, "volgend blok nog niet bepaald")
        : mini("Tot het blok", tot == null ? STREEP : `${fmt(tot, 2)}<small>kWh</small>`, "altijd beschermd") +
          mini("Na het blok", na == null ? STREEP : `${fmt(na, 2)}<small>kWh</small>`, "laadt het blok bij")) +
      mini("Vrij te verkopen", vrij == null ? STREEP : `${fmt(vrij, 2)}<small>kWh</small>`, naBlokVrij && terug != null ? `waarvan ${fmt(naBlokVrij, 2)} kWh terugladen ${ct(terug)} ct` : toets.verkoop_na_blok_reden ? esc(toets.verkoop_na_blok_reden) : "", vrij ? "var(--oranje)" : "") +
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
    return paneelKop("cellen", "Accumodules", rechts, "detail-accu") + `<div class="pb"><div class="lijst">${lijst}</div>${koel}${this._accukosten()}</div>`;
  }

  /* v5.115.0: wat de accu werkelijk kost en oplevert, nagerekend uit het
     dagverloop. Gevraagd: "Op basis van data dus inkoop/ontlaadt/rendement
     kosten etc bepalen". */
  _accukosten() {
    const a = attr(this._s("rendement"), "accukosten");
    if (!a || !a.beschikbaar) return "";
    const ct = (v) => (num(v) == null ? STREEP : `${fmt(v, 1)} ct`);
    const bron = (naam, b) =>
      !b || !num(b.erin_kwh)
        ? ""
        : `<tr><td>${esc(naam)}</td><td class="r">${fmt(b.erin_kwh, 1)} kWh</td><td class="r">${ct(b.inkoop_ct)}</td>` +
          `<td class="r">${fmt(b.ontladen_kwh, 1)} kWh</td><td class="r">${ct(b.opbrengst_ct)}</td>` +
          `<td class="r">${fmtTeken(b.marge_ct_per_kwh, 1)} ct</td><td class="r">\u20ac ${fmt(b.marge_eur, 2)}</td></tr>`;
    const net = a.net || {};
    const corr = a.correctie || {};
    const tabel =
      `<div class="tabelvak"><table class="tabel"><thead><tr><th>Herkomst</th><th class="r">Erin</th><th class="r">Inkoop</th>` +
      `<th class="r">Eruit</th><th class="r">Opbrengst</th><th class="r">Marge/kWh</th><th class="r">Totaal</th></tr></thead><tbody>` +
      bron("Net", net) + bron("Zon", a.zon) + `</tbody></table></div>`;
    const verwacht = num(net.verwacht_ct) != null
      ? `<div class="za-s">Netladen: verwacht ${ct(net.verwacht_ct)}, gerealiseerd ${ct(net.gerealiseerd_ct)} per kWh.</div>`
      : "";
    const inhoud =
      `<div class="za-s">Rendement laden ${fmt(a.laadrendement_procent, 1)}% \u00b7 ontladen ${fmt(a.ontlaadrendement_procent, 1)}% ` +
      `\u00b7 slijtage ${ct(a.slijtage_ct)} \u00b7 rustverbruik ${fmt(a.rust_kwh, 1)} kWh (\u20ac ${fmt(a.rust_eur, 2)})</div>` +
      tabel + verwacht +
      `<div class="za-s">Datacorrectie op netladen: <b>${ct((num(corr.eur) || 0) * 100)}</b> \u00b7 ${esc(corr.status || "")}</div>`;
    return this._uitklap("accukosten", `Wat de accu kost en oplevert (40 dagen): net ${fmtTeken(net.marge_eur, 2)} \u20ac`, inhoud);
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
      const p = apparaatVermogen(s, this._hass.states);
      return [apparaatTekst(s) + (p != null ? `${PUNT}${vermogenTekst(p)}` : ""), apparaatKleur(s)];
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
    const lader = this._s("lader");
    if (lader) {
      const [t, k] = status(lader);
      uit.push(regel("accu", "Batterijlader keuken", "", esc(t), k));
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
      // v5.93.0: gaat de airco naar verwachting aan tot het volgende blok,
      // en hoeveel rekent de reserve daarvoor mee?
      const vw = attr(besluit, "verwachting") || {};
      if (vw.beschikbaar) {
        const res = num(vw.in_reserve_kwh);
        uit.push(
          regel("airco", "Airco",
            // v5.93.1: tot wanneer, en waar de verwachting op rust
            `tot ${esc(vw.tot_tekst || "")}${vw.basis && vw.basis.tekst ? `${PUNT}${esc(vw.basis.tekst)}` : ""}` +
              (vw.knop_automaat === false ? `${PUNT}knop automaat uit` : ""),
            res != null && res > 0 ? `${fmt(res, 2)}<small>kWh</small> <span class="leeg">in reserve</span>` : vw.verwacht ? "verwacht" : "niet verwacht",
            vw.verwacht ? "var(--oranje)" : "")
        );
      }
      // v5.101: het geleerde patroon - wanneer jullie de airco aanzetten
      const ritme = attr(besluit, "dagritme") || {};
      if (ritme.patroon_tekst) {
        uit.push(regel("airco", "Airco-patroon", esc(ritme.patroon_tekst), "", ""));
      }
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
      // v5.104.1: wanneer de waterontharder het laatst regenereerde
      // (gevraagd 19-10: "Energycockpit bij apparaten graag").
      const reg = alsDatum(attr(water, "waterontharder_laatste_regeneratie"));
      if (reg) {
        const momenten = attr(water, "recente_gebruiksmomenten") || [];
        const sessie = momenten.find((m) => alsDatum(m && m.gestart)?.getTime() === reg.getTime()) || {};
        const gisteren = new Date();
        gisteren.setDate(gisteren.getDate() - 1);
        const dag = reg.toDateString() === new Date().toDateString()
          ? "vandaag"
          : reg.toDateString() === gisteren.toDateString()
            ? "gisteren"
            : reg.toLocaleDateString("nl-NL", { weekday: "short", day: "numeric", month: "numeric" });
        const l = num(sessie.liter);
        const duur = num(sessie.duur_minuten);
        const sub = `${dag} ${klok(reg)}` +
          (l != null ? `${PUNT}${fmt(l)} L` : "") +
          (duur != null ? ` in ${fmt(duur)} min` : "");
        uit.push(regel("druppel", "Waterontharder", `laatst geregenereerd: ${esc(sub)}`, esc(geleden(reg) || ""), "var(--blauw)"));
      }
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
      // v5.105.2: de besparing vergelijkt met een huis ZONDER accu (alles
      // wat de accu doet, ook het huis voeden in de stand slim). Gevraagd
      // 19-10: "Wordt in deze kosten ook meegenomen de besparing omdat de
      // accu het huis voedt....." - het onderschrift zei "zonder sturing".
      mini("Besparing maand", euroTeken(bmaand), "t.o.v. zonder accu", bmaand != null && bmaand >= 0 ? "var(--groen)" : "var(--oranje)") +
      mini("Besparing totaal", euroTeken(ball), "sinds de start", ball != null && ball >= 0 ? "var(--groen)" : "var(--oranje)") +
      `</div>` +
      // v5.105.2: alleen wat het EMS ACTIEF doet; het huis voeden in de
      // stand slim zit hier niet in (wel in de besparing hierboven).
      `<div class="za-s">Actieve sturing deze maand - alleen wat het EMS zelf ingrijpt:</div>` +
      `<div class="rijen" title="Alleen ontladen in dure kwartieren en laden uit het net. Dat de accu het huis voedt in de stand slim, of zon opslaat, staat hier niet in maar wel in de besparing.">` +
      `<span>Ontladen in dure kwartieren <b>${euro(verkocht)}</b></span>` +
      `<span>Laden uit het net <b>${euro(geladen)}</b></span>` +
      `<span>Actieve sturing netto <b style="color:${netto != null && netto >= 0 ? "var(--groen)" : "var(--oranje)"}">${euroTeken(netto)}</b></span>` +
      `</div>` +
      `<div class="trio">` +
      mini("Vandaag", euro(vandaag.kosten_eur), `${fmt(vandaag.import_kwh, 1)} kWh van het net`) +
      mini("Week", euro(week.kosten_eur), `${fmt(week.opwek_kwh, 0)} kWh zon`) +
      mini("Maand", euro(maand.kosten_eur), `${fmt(maand.opwek_kwh, 0)} kWh zon`) +
      `</div>` +
      this._zelfanalyse() +
      `</div>`
    );
  }

  /* v5.100: zelfanalyse, prijsverwachting en repetitie 2027 - de teksten
     komen kant-en-klaar uit de integratie (kaart_primair/kaart_secundair). */
  _zelfanalyse() {
    const blokken = [
      ["zelfanalyse", "Zelfanalyse"],
      ["repetitie", "Generale repetitie 2027"],
      ["dagarchief", "Dagarchief"],
    ];
    const regels = blokken.map(([k, naam]) => {
      const s = this._s(k);
      if (!s) return "";
      return (
        `<div class="za"><div class="za-k">${esc(naam)}<b>${esc(attr(s, "kaart_primair") || "")}</b></div>` +
        `<div class="za-s">${esc(attr(s, "kaart_secundair") || "")}</div></div>`
      );
    }).join("");
    if (!regels) return "";
    const gisteren = attr(this._s("zelfanalyse"), "gisteren") || {};
    const keuzes = (gisteren.niet_de_beste || []).slice(0, 3).map(
      (k) => `<li>${esc(k.tekst || "")} <i>${esc(k.oorzaak || "")}</i></li>`
    ).join("");
    return (
      `<div class="za-blok">${regels}` +
      (keuzes ? `<div class="za-s" style="margin-top:6px">Achteraf niet de beste (${esc(gisteren.datum || "")}):</div><ul class="za-l">${keuzes}</ul>` : "") +
      `</div>`
    );
  }

  /* v5.113.0: eigen paneel voor de prijzen een week vooruit. */
  _prijzen() {
    const s = this._s("prijsverwachting");
    if (!s) return null;
    return (
      paneelKop("grafiek", "Prijzen 7 dagen", chip(esc(attr(s, "kaart_primair") || ""))) +
      `<div class="pb">` +
      `<div class="za-s">${esc(attr(s, "kaart_secundair") || "")}</div>` +
      this._prijsGrafiek() +
      this._prijsKwaliteit() +
      `</div>`
    );
  }

  /* Uitklapbaar blok dat open blijft over een nieuwe opbouw heen. */
  _uitklap(sleutel, kop, inhoud) {
    if (!inhoud) return "";
    const open = this._uitgeklapt && this._uitgeklapt[sleutel];
    return (
      `<details class="uitklap" data-uitklap="${esc(sleutel)}"${open ? " open" : ""}>` +
      `<summary>${esc(kop)}</summary>${inhoud}</details>`
    );
  }

  /* v5.108.0 / v5.109.0: prijs per kwartier, een week vooruit, als staven in
     de kleuren van de planning. Gevraagd: "staafdiagram van 7 dagen vooruit
     met kleuren als in de andere grafiek". Binnen het plan: de geplande stand.
     Daarna (verwachting, lichter): de dagregel van het EMS - goedkoop (laagste
     prijs van de dag + 20 % van het bereik) = laden, boven de drempel voor duur
     = verkopen, anders slim. */
  _prijsGrafiek() {
    const r = attr(this._s("prijsverwachting"), "kwartieren");
    const ct = (r && Array.isArray(r.ct)) ? r.ct.map(num) : [];
    const n = ct.length;
    const waarden = ct.filter((v) => v != null);
    if (n < 2 || !waarden.length) return "";
    const start = new Date(r.start).getTime();
    const stap = (num(r.stap_min) || 15) * 60000;
    const vanaf = num(r.verwacht_vanaf);
    const tijd = (i) => new Date(start + i * stap);
    // de geplande stand per kwartier
    const plan = new Map();
    const rijen = this._planRijen();
    planTijden(rijen).forEach((d, i) => plan.set(Math.round(d.getTime() / stap), rijen[i].modus));
    // per dag: de goedkope grens (laagste + 20 % van het bereik)
    const perDag = new Map();
    ct.forEach((v, i) => {
      if (v == null) return;
      const dag = tijd(i).toDateString();
      const g = perDag.get(dag) || { min: v, max: v };
      perDag.set(dag, { min: Math.min(g.min, v), max: Math.max(g.max, v) });
    });
    const drempel = num(attr(this._s("uitleg"), "expensive_price_threshold"));
    const stand = (i) => {
      const gepland = plan.get(Math.round(tijd(i).getTime() / stap));
      if (gepland != null) return { m: modus(gepland), plan: true };
      const g = perDag.get(tijd(i).toDateString());
      if (g && ct[i] <= g.min + 0.2 * (g.max - g.min)) return { m: modus("laden)"), plan: false };
      if (drempel != null && ct[i] >= drempel * 100) return { m: modus("verkopen"), plan: false };
      return { m: modus("slim"), plan: false };
    };
    const pMin = Math.min(0, ...waarden);
    const top = Math.max(10, Math.ceil(Math.max(...waarden) / 10) * 10);
    const bodem = pMin < 0 ? Math.floor(pMin / 5) * 5 : 0;
    const bereik = Math.max(top - bodem, 1);
    const y = (v) => 100 - ((v - bodem) / bereik) * 100;
    const nul = y(0);
    const staven = ct.map((v, i) => {
      if (v == null) return "";
      const s = stand(i);
      const verwacht = vanaf != null && i >= vanaf;
      const y1 = Math.min(y(v), nul);
      const h = Math.max(Math.abs(nul - y(v)), 0.6);
      const d = tijd(i);
      const tip = `${d.toLocaleDateString("nl-NL", { weekday: "short", day: "numeric", month: "short" })} ` +
        `${d.toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" })} \u00b7 ${fmt(v, 1)} ct \u00b7 ` +
        `${s.m.label}${s.plan ? "" : verwacht ? " (verwachting)" : " (geen plan)"}`;
      return `<rect x="${(i + 0.1).toFixed(1)}" y="${y1.toFixed(2)}" width="0.8" height="${h.toFixed(2)}" ` +
        `fill="${s.m.kleur}" fill-opacity="${verwacht ? 0.45 : 0.9}"><title>${esc(tip)}</title></rect>`;
    }).join("");
    const x = (i) => ((i + 0.5) / n) * 100;
    const yLab = [0, 0.5, 1].map((f) => `<span style="top:${((1 - f) * 100).toFixed(1)}%">${fmt(bodem + f * bereik)}</span>`).join("");
    const yRaster = [0.5].map((f) => `<div class="g-raster" style="top:${((1 - f) * 100).toFixed(1)}%"></div>`).join("");
    const xLab = [];
    for (let i = 0; i < n; i++) {
      const d = tijd(i);
      if (d.getMinutes() !== 0 || d.getHours() !== 0) continue;
      xLab.push(`<span class="dag" style="left:${x(i).toFixed(2)}%">${esc(d.toLocaleDateString("nl-NL", { weekday: "short", day: "numeric" }))}</span>`);
    }
    const scheiding = vanaf != null && vanaf > 0
      ? `<div class="pv-grens" style="left:${(vanaf / n * 100).toFixed(2)}%"><span>verwachting</span></div>`
      : "";
    return (
      `<div class="pl-legenda" style="margin-top:2px">` +
      `<span><i style="background:var(--groen)"></i>laden</span>` +
      `<span><i style="background:var(--oranje)"></i>verkopen</span>` +
      `<span><i style="background:var(--blauw)"></i>sparen</span>` +
      `<span><i style="background:var(--violet)"></i>slim</span>` +
      `<span><i style="background:var(--violet);opacity:.45"></i>verwachting</span></div>` +
      `<div class="pv-wrap">` +
      `<div class="g-y">${yLab}</div>` +
      `<div class="g-plot">${yRaster}` +
      `<svg class="pv-svg" viewBox="0 0 ${n} 100" preserveAspectRatio="none" role="img" aria-label="prijs per kwartier, een week vooruit">${staven}</svg>` +
      `${scheiding}</div>` +
      `<div class="g-x">${xLab.join("")}</div>` +
      `</div>` +
      `<div class="meternoot">ct/kWh per kwartier. Vol: bekend, in de kleur van het plan. Licht: verwachting, ` +
      `gekleurd naar de dagregel (goedkoopste deel = laden, boven de drempel voor duur = verkopen). Alleen meten.</div>`
    );
  }

  /* v5.112.0: hoe goed is de prijsverwachting? Gevraagd: "ik wil de
     performance zien hoe goed de voorspellingen zijn en ook terug rekenen".
     Live (bewaarde verwachtingen tegen de echte prijzen), de terugtoets over
     de afgelopen weken en de bijstelling op de eigen fout. */
  _prijsKwaliteit() {
    const s = this._s("prijsverwachting");
    if (!s) return "";
    const live = attr(s, "nauwkeurigheid_live") || {};
    const bt = attr(s, "backtest_21_dagen") || {};
    const bij = attr(s, "bijstelling") || {};
    const ct = (v) => (num(v) == null ? STREEP : `${fmt(v, 1)} ct`);
    const regel = (naam, r) => {
      if (!r || !num(r.dagen)) return `<div class="za-s"><b>${esc(naam)}</b>: nog geen dagen gemeten</div>`;
      const beter = num(r.winst_procent);
      return (
        `<div class="za-s"><b>${esc(naam)}</b>: gemiddeld ${ct(r.afwijking_model_ct)} ernaast, zoals gisteren ${ct(r.afwijking_zoals_gisteren_ct)}` +
        (beter != null ? ` (${beter >= 0 ? fmt(beter) + "% beter" : fmt(-beter) + "% slechter"})` : "") +
        ` over ${fmt(r.dagen)} dag${r.dagen === 1 ? "" : "en"} \u00b7 duurste uren ${fmt(r.duurste_uren_geraakt_van_4, 1)}/4, goedkoopste ${fmt(r.goedkoopste_uren_geraakt_van_4, 1)}/4` +
        (num(r.bijgesteld_dagen) ? ` \u00b7 met bijstelling ${ct(r.met_bijstelling_ct)}, zonder ${ct(r.zonder_bijstelling_ct)}` : "") +
        (r.rijp ? " \u00b7 rijp" : "") +
        `</div>`
      );
    };
    const bijRegel = ["d1", "d2"].map((k) => {
      const b = bij[k] || {};
      if (!num(b.dagen)) return "";
      return `${k === "d1" ? "morgen" : "overmorgen"} ${fmtTeken(b.gemiddeld_ct, 1)} ct (uit ${fmt(b.dagen)} dagen)`;
    }).filter(Boolean).join(", ");
    // per dag: live (morgen) aangevuld met de terugtoets
    const rijenLive = ((live.d1 || {}).per_dag || []).map((r) => ({ ...r, soort: "live" }));
    const gezien = new Set(rijenLive.map((r) => r.datum));
    const rijenBt = (bt.per_dag || []).filter((r) => !gezien.has(r.datum)).map((r) => ({ ...r, soort: "terugtoets" }));
    const rijen = [...rijenBt, ...rijenLive].sort((a, b) => String(a.datum).localeCompare(String(b.datum))).slice(-14);
    let grafiek = "";
    if (rijen.length) {
      const top = Math.max(2, ...rijen.map((r) => Math.max(num(r.afwijking_ct) || 0, num(r.zoals_gisteren_ct) || 0)));
      const n = rijen.length;
      const staaf = (i, v, plek, kleur, extra) => {
        const h = ((num(v) || 0) / top) * 100;
        return `<rect x="${(i + 0.12 + plek * 0.38).toFixed(2)}" y="${(100 - h).toFixed(2)}" width="0.36" height="${Math.max(h, 0.5).toFixed(2)}" fill="${kleur}"${extra}/>`;
      };
      const staven = rijen.map((r, i) =>
        staaf(i, r.afwijking_ct, 0, "var(--violet)", r.soort === "terugtoets" ? ' fill-opacity="0.55"' : "") +
        staaf(i, r.zoals_gisteren_ct, 1, "var(--tekst3)", ' fill-opacity="0.6"')
      ).join("");
      const xLab = rijen.map((r, i) => `<span style="left:${(((i + 0.5) / n) * 100).toFixed(2)}%">${esc(String(r.datum).slice(8, 10))}</span>`).join("");
      grafiek =
        `<div class="pl-legenda" style="margin-top:4px"><span><i style="background:var(--violet)"></i>afwijking verwachting</span>` +
        `<span><i style="background:var(--tekst3)"></i>zoals gisteren</span><span><i style="background:var(--violet);opacity:.55"></i>terugtoets</span></div>` +
        `<div class="pv-wrap pv-klein"><div class="g-y"><span style="top:0%">${fmt(top, 0)}</span><span style="top:100%">0</span></div>` +
        `<div class="g-plot"><svg class="pv-svg" viewBox="0 0 ${n} 100" preserveAspectRatio="none" role="img" aria-label="afwijking per dag in ct">${staven}</svg></div>` +
        `<div class="g-x">${xLab}</div></div>`;
    }
    const tabel = rijen.length
      ? `<div class="tabelvak"><table class="tabel"><thead><tr><th>Dag</th><th class="r">Verwacht</th><th class="r">Echt</th>` +
        `<th class="r">Ernaast</th><th class="r">Zoals gisteren</th><th class="r">Duurst</th><th></th></tr></thead><tbody>` +
        rijen.slice(-10).reverse().map((r) =>
          `<tr><td>${esc(String(r.datum).slice(5).split("-").reverse().join("-"))}</td><td class="r">${fmt(r.verwacht_ct, 1)}</td>` +
          `<td class="r">${fmt(r.echt_ct, 1)}</td><td class="r">${fmt(r.afwijking_ct, 1)}</td><td class="r">${fmt(r.zoals_gisteren_ct, 1)}</td>` +
          `<td class="r">${fmt(r.duurste_geraakt)}/4</td><td>${esc(r.soort)}</td></tr>`
        ).join("") +
        `</tbody></table></div>`
      : "";
    return (
      `<div class="za-k" style="margin-top:6px">Hoe goed is de verwachting?</div>` +
      regel("Morgen (live)", live.d1) +
      regel("Overmorgen (live)", live.d2) +
      regel("Terugtoets", bt) +
      `<div class="za-s"><b>Bijstelling op de eigen fout</b>: ${bijRegel ? esc(bijRegel) : "nog niets bij te stellen"}</div>` +
      // v5.113.0: staven en tabel per dag ingeklapt
      this._uitklap("prijs_per_dag", `Per dag (${rijen.length} dagen)`, grafiek + tabel +
        `<div class="meternoot">Ernaast: gemiddelde afwijking per uur in ct/kWh. Live: de verwachting zoals hij toen was, tegen de echte prijs. ` +
        `Terugtoets: teruggerekend over de afgelopen weken met het gemeten weer (de fout in het weerbericht zit daar niet in).</div>`)
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
