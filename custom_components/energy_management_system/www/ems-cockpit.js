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
  // v5.145.0: kasprijs en kostprijs van de stroom in de accu
  accuprijs: "battery_savings",
  zelfvoorziening: "self_sufficiency",
  huis: "household_consumption",
  verhaal: "live_narrative",
  tekort: "reserve_shortfall",
  rendement: "learned_battery_efficiency",
  stofzuiger: "steelstofzuiger_status",
  fietsen: "fietsladers_status",
  // v5.129.0: de batterijlader in de keuken
  lader: "batterijlader_status",
  // v5.135.0: continu-verbruik, verklaard en zonder eigen meting
  sluip: "sluipverbruik",
  cockpit: "cockpit",
  aircoBesluit: "airco_besluit",
  meetlog: "meetlog",
  gezondheid: "diagnose_gezondheid",
  pvNauw: "pv_forecast_accuracy",
  vaatwasser: "dishwasher_cycle_state",
  wasmachine: "washing_machine_cycle_state",
  // v5.139.0: start, eind en voortgang in gewone taal
  vaatwasserPlan: "dishwasher_planning",
  wasmachinePlan: "washing_machine_planning",
  bewolking: "weather_ensemble",
  meldingen: "meldingen",
  accuGezondheid: "battery_health",
  plan: "kwartierplanning_tabel",
  schema: "upcoming_schedule",
  uitleg: "explanation",
  // v5.100: zelfanalyse, prijsverwachting en de generale repetitie 2027
  zelfanalyse: "zelfanalyse",
  prijsverwachting: "prijsverwachting",
  repetitie: "repetitie_2027",
  dagarchief: "dagarchief",
  // v5.105.0: is er iemand thuis (bovenin de cockpit)
  aanwezig: "aanwezigheid",
  // v5.203.0: kosten vandaag inclusief de vaste kosten
  kostenTotaal: "kosten_vandaag_totaal",
  // knoppen
  nuLaden: "nu_laden",
  // v5.207.1: knop "Verkopen uit (vandaag)"
  verkoopUit: "verkoop_pauze",
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
  // v5.181.1 (punt 8): modulevermogens en apparaatvermogens live in de browser
  const modulesW = Array.isArray(extern.modules_vermogen) ? extern.modules_vermogen : [];
  for (const k of ["vaatwasser_w", "wasmachine_w", "stofzuiger_w", "fietsen_w", "lader_w", "airco_w"]) {
    if (extern[k]) ids[k] = extern[k];
  }
  return {
    ids,
    modules,
    modulesW,
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
  // v5.179.1: zon terugleveren in plaats van opslaan (waardeplan_terugleveren,
  // stand manual) - viel eerder onder "Handmatig" en kleurde als rust.
  { test: /terugleveren/, label: "Zon terugleveren", kleur: "#b9c46a", k: "terug" },
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
  nachtrust: "nachtrust (22-06 u)",
  vol_blijft_aan: "vol, blijft aan",
};
/* v5.93.0: een kleur per stand (gevraagd 12-10 11:50). Groen = bezig of
   laden, amber = wacht op het goedkope blok, cyaan = test, blauw = klaar,
   violet = handmatig, grijs = niets aangesloten of uit. */
const APPARAAT_KLEUR = [
  [/^(laadt|aan_het_laden|bezig|draait|running|run|actief)$/, "var(--groen)"],
  [/^test_aan$/, "var(--cyaan)"],
  [/^(wacht_op_apparaat|nachtrust)$/, "var(--tekst3)"],
  [/wacht|gepland|delayed/, "var(--amber)"],
  [/^(klaar|vol|voltooid|voltooid_vandaag|vol_blijft_aan|finished|ready)$/, "var(--blauw)"],
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

/* v5.179: een statistiektegel overal - label / waarde+eenheid / onderschrift.
   Kleur alleen als stip bij het label, nooit als rand. */
const stat = (label, waarde, sub = "", kleur = "") =>
  `<div class="stat"><span class="l">${kleur ? `<span class="stip" style="--kleur:${kleur}"></span>` : ""}${esc(label)}</span>` +
  `<b>${waarde}</b><span class="s">${sub || "&nbsp;"}</span></div>`;
const mini = (label, waarde, sub = "", kleur = "") => stat(label, waarde, sub, kleur);

const balk = (deel, kleur, streep = null) => {
  const d = Math.max(0, Math.min(1, num(deel) || 0));
  const s = streep == null ? "" : `<i style="left:${(Math.max(0, Math.min(1, streep)) * 100).toFixed(1)}%"></i>`;
  return `<div class="balk"><b style="width:${(d * 100).toFixed(1)}%;background:${kleur}"></b>${s}</div>`;
};

/** De laadstand: groot getal met een dunne balk (v5.179, was een ring). */
const socBlok = (pct, kleur) =>
  `<div class="soc-w">${pct == null ? STREEP : Math.round(pct)}<small>%</small></div>` +
  `<div class="balk"><b style="width:${Math.max(0, Math.min(100, num(pct) || 0)).toFixed(1)}%;background:${kleur}"></b></div>` +
  `<div class="lbl">laadstand</div>`;

/* ------------------------------------------------------------------ */
/* Stijl                                                               */
/* ------------------------------------------------------------------ */

const STIJL = `
:host {
  display: block;
  min-height: 100%;
  /* v5.179: een rustig, donker productontwerp - een kaartsoort, een typeschaal,
     een spatieschaal (4/8/12/16/24) en kleur alleen waar het iets betekent. */
  --bg: #0b0f17;
  --kaart: #111827;
  --vlak: rgba(255, 255, 255, .03);
  --vlak2: rgba(255, 255, 255, .055);
  --rand: rgba(255, 255, 255, .07);
  --rand2: rgba(255, 255, 255, .13);
  --lijn: rgba(255, 255, 255, .06);
  --tekst: #e6e8ec;
  --tekst2: #9aa3b2;
  --tekst3: #6b7383;
  /* betekenis: zon amber, net blauw, accu violet, goed groen, let op oranje, fout rood */
  --amber: #d6a64f;
  --geel: #d6a64f;
  --oranje: #d9894f;
  --rood: #e0656c;
  --groen: #4fb48a;
  --blauw: #6f95d8;
  --cyaan: #63adbd;
  --violet: #9b8cec;
  --r: 12px;
  --r2: 8px;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  font-size: 13px;
  line-height: 1.45;
  color: var(--tekst);
  -webkit-font-smoothing: antialiased;
}
* { box-sizing: border-box; }
.root { min-height: 100vh; background: var(--bg); }
.wrap { container-type: inline-size; max-width: 1760px; margin: 0 auto; padding: 16px 24px 24px; }
.ic { width: 16px; height: 16px; flex: none; }
b, strong { font-weight: 600; }
small { font-size: 11px; font-weight: 400; color: var(--tekst3); margin-left: 2px; letter-spacing: 0; }
.leeg { color: var(--tekst3); }
[hidden] { display: none !important; }
.num, .big, td, .stat b, .mini .w, .kv b, .rijen b, .w { font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; }
button { font: inherit; }

/* ---- kop ---- */
.kop { display: flex; align-items: center; gap: 12px 16px; padding: 0 0 16px; }
.merk { display: flex; align-items: center; gap: 12px; min-width: 0; flex: none; }
.logo { width: 34px; height: 34px; flex: none; display: grid; place-items: center; }
.logo img { width: 34px; height: 34px; display: block; border-radius: 50%; }
.merknaam { font-size: 15px; font-weight: 600; line-height: 1.2; }
.merksub { font-size: 11px; color: var(--tekst3); }
.kop-mid { display: flex; gap: 8px; flex-wrap: wrap; flex: 1 1 0; min-width: 0; justify-content: flex-start; padding-left: 16px; }
.kop-r { display: flex; align-items: center; gap: 16px; margin-left: auto; flex: none; }
.klok { text-align: right; line-height: 1.2; }
.klok .tijd { font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; }
.klok .datum { font-size: 11px; color: var(--tekst3); }
.chip {
  display: inline-flex; align-items: center; gap: 8px; white-space: nowrap; height: 28px;
  font-size: 12px; font-weight: 400; color: var(--tekst2); line-height: 1;
  padding: 0 12px; border-radius: 999px; background: var(--vlak); border: 1px solid var(--rand);
  max-width: 100%; overflow: hidden; text-overflow: ellipsis;
}
.chip .ic { width: 14px; height: 14px; color: var(--tekst3); }
.chip.groot { color: var(--tekst); }
.chip.ok:not(:has(.stip))::before, .chip.let:not(:has(.stip))::before, .chip.gevaar:not(:has(.stip))::before {
  content: ""; width: 6px; height: 6px; border-radius: 50%; flex: none; background: var(--groen);
}
.chip.let:not(:has(.stip))::before { background: var(--oranje); }
.chip.gevaar:not(:has(.stip))::before { background: var(--rood); }
.chip.gevaar { color: var(--tekst); border-color: rgba(224, 101, 108, .35); }
.chip.uit { color: var(--tekst3); }
.chip .leeg, .chip-reden { color: var(--tekst3); font-weight: 400; }
.stip { width: 6px; height: 6px; border-radius: 50%; display: inline-block; flex: none; background: var(--kleur, var(--tekst3)); }

/* ---- meldingen ---- */
.meldingen { display: grid; gap: 8px; margin-bottom: 12px; }
.meldingen:empty { display: none; }
.melding { display: flex; align-items: flex-start; gap: 8px; padding: 12px 16px; border-radius: var(--r); border: 1px solid var(--rand); background: var(--kaart); }
.melding .ic { margin-top: 2px; }
.melding.let .ic { color: var(--oranje); }
.melding.info .ic { color: var(--blauw); }
.melding.gevaar { border-color: rgba(224, 101, 108, .35); }
.melding.gevaar .ic { color: var(--rood); }

/* ---- kaarten: een soort, overal ---- */
.tegel, .paneel {
  min-width: 0; display: flex; flex-direction: column; gap: 12px;
  padding: 16px; border-radius: var(--r); background: var(--kaart); border: 1px solid var(--rand);
}
.ph { display: flex; align-items: center; gap: 8px; min-height: 28px; min-width: 0; color: var(--tekst3); }
.ph h2 { margin: 0; font-size: 13px; font-weight: 600; color: var(--tekst); white-space: nowrap; }
/* v5.215.0: de chips lopen door naar een tweede regel in plaats van afgekapt te worden. */
.ph-r { margin-left: auto; display: flex; flex-wrap: wrap; gap: 4px 8px; justify-content: flex-end; align-items: center; min-width: 0; }
.meer { display: grid; place-items: center; width: 28px; height: 28px; flex: none; border-radius: var(--r2); border: 1px solid var(--rand); background: transparent; color: var(--tekst3); cursor: pointer; padding: 0; }
.meer:hover { color: var(--tekst); border-color: var(--rand2); }
.meer .ic { width: 14px; height: 14px; }
.pb { padding: 0; display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; align-content: start; flex: 1 1 auto; }
.leegmelding { color: var(--tekst3); font-size: 13px; }
.meta { display: flex; flex-wrap: wrap; gap: 8px; }
.p-planning > .pb > .uitklap { margin-top: 0; }

/* ---- statusrij: drie gelijke kaarten ---- */
.hero { display: grid; gap: 12px; grid-template-columns: minmax(0, 1fr); margin-bottom: 12px; }
.hero > .hv { display: flex; min-width: 0; }
.hero > .hv > .tegel { flex: 1 1 auto; }
.lbl { font-size: 11px; font-weight: 400; color: var(--tekst3); }
.big { font-size: 22px; font-weight: 600; line-height: 1.2; }
.sub { font-size: 13px; color: var(--tekst2); }
.sub b { color: var(--tekst); }
.tekst-m { font-size: 15px; font-weight: 600; line-height: 1.3; color: var(--tekst); }
.accu-t { display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: 16px; align-items: start; }
.soc { display: grid; gap: 8px; cursor: pointer; }
.soc-w { font-size: 30px; font-weight: 600; line-height: 1; font-variant-numeric: tabular-nums; }
.soc-w small { font-size: 15px; color: var(--tekst3); }
.soc .balk { height: 4px; }
.rest, .s.rest { font-size: 12px; color: var(--tekst2); }
.regels-k { display: grid; gap: 4px; }
.rijen { display: grid; gap: 0; font-size: 13px; color: var(--tekst2); min-width: 0; }
.rijen span { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; padding: 4px 0; border-bottom: 1px solid var(--lijn); }
.rijen span:last-child { border-bottom: 0; }
.rijen b { color: var(--tekst); white-space: nowrap; text-align: right; }
.rijen.vrij b { white-space: normal; }
.bij { font-style: normal; font-weight: 400; color: var(--tekst3); margin-left: 8px; }
.za-blok { border-top: 1px solid var(--lijn); }
.za-k { font-size: 13px; color: var(--tekst); font-weight: 600; }
.za-s { font-size: 12px; color: var(--tekst2); overflow-wrap: anywhere; }
.za-l { margin: 4px 0 0 16px; padding: 0; font-size: 12px; color: var(--tekst2); }
.za-l i { color: var(--tekst3); }
/* v5.215.0: twee kolommen alleen als de tegel zelf breed genoeg is (was: vanaf 1260 px
   kaartbreedte, waar de tegel een derde is en de kolommen over elkaar vielen). */
.geld-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap: 0 24px; align-items: start; }
.geld-r b { white-space: normal; }
.geld-r b:not(:has(.bij)) { white-space: nowrap; }
.geld-r.za-blok b { white-space: normal; }
.geld-r .bij { white-space: nowrap; display: inline-block; }
.geld-kop { font-size: 11px; color: var(--tekst3); padding: 8px 0 0; }

/* ---- uitklap ---- */
.uitklap { border-top: 1px solid var(--lijn); padding-top: 8px; margin-top: auto; }
.uitklap > summary { cursor: pointer; font-size: 12px; color: var(--tekst3); list-style: none; display: flex; align-items: center; gap: 8px; }
.uitklap > summary:hover { color: var(--tekst2); }
.uitklap > summary::-webkit-details-marker { display: none; }
.uitklap > summary::before { content: ""; width: 6px; height: 6px; border-right: 1.5px solid currentColor; border-bottom: 1.5px solid currentColor; transform: rotate(-45deg); transition: transform .15s; }
.uitklap[open] > summary::before { transform: rotate(45deg); }
.uitklap[open] > summary { margin-bottom: 8px; }
.redenen { margin: 0; padding: 0; list-style: none; display: grid; gap: 4px; font-size: 13px; color: var(--tekst2); }
.redenen li { display: flex; gap: 8px; }
.redenen li::before { content: ""; width: 4px; height: 4px; border-radius: 50%; background: var(--tekst3); margin-top: 8px; flex: none; }

/* ---- statistiektegel: label / waarde+eenheid / onderschrift ---- */
.stat, .mini {
  display: flex; flex-direction: column; gap: 2px; min-width: 0;
  padding: 8px 12px; border-radius: var(--r2); background: var(--vlak);
}
.stat .l, .mini .lbl { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--tekst3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.stat .l .stip { width: 6px; height: 6px; }
.stat b, .mini .w { display: block; font-size: 15px; font-weight: 600; color: var(--tekst); line-height: 1.3; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.stat .s, .mini .s { display: block; font-size: 11px; color: var(--tekst2); line-height: 1.35; overflow-wrap: anywhere; }
.vier { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.duo, .kwart { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.trio, .trio.vast { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }

/* ---- balk en meter ---- */
.balk { position: relative; height: 6px; border-radius: 99px; background: var(--vlak2); overflow: hidden; }
.balk b { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 99px; transition: width .6s ease; }
.balk i { position: absolute; top: 0; bottom: 0; width: 2px; background: var(--tekst); opacity: .8; }
.meterrij { display: grid; gap: 4px; }
.meterkop { display: flex; justify-content: space-between; align-items: baseline; gap: 4px 12px; flex-wrap: wrap; }
.meterkop .w { font-size: 13px; font-weight: 600; white-space: nowrap; }
.meternoot { font-size: 12px; color: var(--tekst3); }
.zin { font-size: 13px; color: var(--tekst2); padding: 8px 12px; border-radius: var(--r2); background: var(--vlak); }
.zin b { color: var(--tekst); }

/* ---- plan vandaag ---- */
.strip { display: flex; height: 12px; border-radius: 4px; overflow: hidden; gap: 1px; }
.strip i { flex: 1 1 0; min-width: 0; opacity: .85; }
.strip-x { position: relative; height: 16px; font-size: 11px; color: var(--tekst3); font-variant-numeric: tabular-nums; margin-top: -8px; }
.strip-x span { position: absolute; top: 2px; transform: translateX(-50%); white-space: nowrap; }
.strip-x span:first-child { transform: none; }
.planvolg { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 8px 12px; align-items: center; }
.planvolg .zinpv { font-size: 13px; color: var(--tekst); min-width: 0; }
.planvolg .rk { font-size: 11px; color: var(--tekst3); align-self: center; }
.planvolg .rij3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; min-width: 0; }
.planvolg .cel { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0 6px; min-width: 0; padding: 6px 10px; border-radius: var(--r2); background: var(--vlak); }
.planvolg .cel .l { flex: 1 0 100%; font-size: 11px; color: var(--tekst3); }
.planvolg .cel > .w { display: contents; }
.planvolg .cel .w { font-size: 15px; font-weight: 600; white-space: nowrap; }
.planvolg .cel .s { font-size: 11px; color: var(--tekst2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.planvolg .cel.k .w { color: var(--k); }
.planvolg .dag { grid-column: 1 / -1; font-size: 12px; color: var(--tekst3); }
.planvolg .pvkop { grid-column: 1 / -1; display: flex; align-items: center; gap: 12px; min-width: 0; }
.planvolg .pvkop .chip { flex: none; white-space: nowrap; }

/* ---- raster: 12 kolommen, rijen die gelijk eindigen ---- */
.raster { display: grid; gap: 12px; grid-template-columns: minmax(0, 1fr); align-items: stretch; }
.stapel { display: contents; }
.p-planning { order: 1; }
.p-bediening { order: 2; }
.p-modules { order: 3; }
.p-verkoop { order: 4; }
.p-huis { order: 5; }

/* ---- grafieken ---- */
.pl-legenda { display: flex; flex-wrap: wrap; gap: 4px 16px; font-size: 11px; color: var(--tekst2); }
.pl-legenda i { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 6px; vertical-align: 0; }
.pl-legenda .lijn-i { height: 2px; width: 12px; border-radius: 1px; vertical-align: 3px; }
.pl-legenda.klein { gap: 4px 12px; }
.gwrap { position: relative; display: grid; grid-template-columns: 32px 1fr 36px; grid-template-rows: 180px 24px; }
.g-y, .g-y2 { position: relative; }
/* v5.181.2 (d): eenheid boven de prijs- en de accu-as */
.g-eenheid { display: flex; justify-content: space-between; font-size: 11px; color: var(--tekst3); line-height: 1; margin: 6px 0 6px; }
.g-y span, .g-y2 span, .g-x span { position: absolute; font-size: 11px; color: var(--tekst3); font-variant-numeric: tabular-nums; white-space: nowrap; }
.g-y span { right: 8px; transform: translateY(-50%); }
.g-y2 span { left: 8px; transform: translateY(-50%); }
.g-plot { position: relative; border-bottom: 1px solid var(--rand2); }
.g-raster { position: absolute; left: 0; right: 0; height: 1px; background: var(--lijn); }
.staven { position: absolute; inset: 0; display: flex; align-items: flex-end; padding: 0 1px; }
.staaf { flex: 1 1 0; min-width: 0; opacity: .78; position: relative; clip-path: inset(0 14% -8px 14% round 2px 2px 0 0); }
.staaf.tekort::after { content: ""; position: absolute; left: 0; right: 0; bottom: -6px; height: 2px; background: var(--rood); }
.staaf:hover { opacity: 1; }
.g-svg { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; pointer-events: none; }
.vloer { stroke: var(--tekst3); stroke-width: 1; stroke-dasharray: 2 3; vector-effect: non-scaling-stroke; }
.soc-lijn { fill: none; stroke: var(--tekst); stroke-width: 1.8; vector-effect: non-scaling-stroke; }
.zon-vlak { fill: rgba(214, 166, 79, .10); stroke: rgba(214, 166, 79, .45); stroke-width: 1; vector-effect: non-scaling-stroke; }
.drempel { stroke: rgba(224, 101, 108, .5); stroke-width: 1; stroke-dasharray: 3 4; vector-effect: non-scaling-stroke; }
.nu-lijn { position: absolute; top: -4px; bottom: 0; width: 1px; background: var(--tekst2); }
.nu-lijn span { position: absolute; top: -2px; left: 6px; font-size: 11px; font-weight: 600; color: var(--tekst2); }
.g-x { position: relative; grid-column: 2; }
.g-x span { top: 6px; transform: translateX(-50%); }
.g-x span.dag { color: var(--tekst2); }
.pv-wrap { position: relative; display: grid; grid-template-columns: 32px 1fr; grid-template-rows: 150px 24px; min-width: 0; }
.pv-wrap .g-x { grid-column: 2; }
.pv-svg { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
.pv-klein { grid-template-rows: 80px 24px; }
.pv-grens { position: absolute; top: 0; bottom: 0; width: 1px; background: var(--rand2); }
.pv-grens span { position: absolute; top: 2px; left: 6px; font-size: 11px; color: var(--tekst3); white-space: nowrap; }

/* ---- tabbladen ---- */
.tabs { display: inline-flex; gap: 2px; padding: 2px; height: 28px; border-radius: var(--r2); background: var(--vlak); border: 1px solid var(--rand); }
.tabs button { font-size: 12px; color: var(--tekst2); background: none; border: 0; border-radius: 6px; padding: 0 10px; cursor: pointer; }
.tabs button[aria-selected="true"] { background: var(--vlak2); color: var(--tekst); font-weight: 600; }
.tabs button:disabled { opacity: .35; cursor: default; }
.tabs button:focus-visible, .links button:focus-visible, .vb-knoppen button:focus-visible { outline: 2px solid var(--blauw); outline-offset: 2px; }

/* ---- tabellen ---- */
.tabel { width: 100%; border-collapse: collapse; font-size: 13px; }
.tabel th { text-align: left; font-size: 11px; color: var(--tekst3); font-weight: 400; padding: 0 8px 8px; white-space: nowrap; }
.tabel td { height: 36px; padding: 0 8px; border-top: 1px solid var(--lijn); white-space: nowrap; }
.tabel td.r, .tabel th.r { text-align: right; }
.tabel tr.nu td { background: var(--vlak); }
.modus { display: inline-flex; align-items: center; gap: 8px; }
.modus i { width: 8px; height: 8px; border-radius: 2px; background: var(--kleur); }
.soc-pijl { color: var(--tekst2); }
.soc-pijl b { color: var(--tekst); }
.tabelvak { overflow-x: auto; }
.vb-vak { display: grid; gap: 8px; }
.vb-kop { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; font-size: 13px; }
.vb-knoppen { display: inline-flex; gap: 2px; padding: 2px; border-radius: var(--r2); background: var(--vlak); border: 1px solid var(--rand); }
.vb-knoppen button { background: none; color: var(--tekst2); border: 0; border-radius: 6px; padding: 2px 8px; font-size: 12px; cursor: pointer; }
.vb-knoppen button.actief { color: var(--tekst); background: var(--vlak2); font-weight: 600; }
.vb-knoppen button[disabled] { opacity: .35; cursor: default; }
.vb-bereik { color: var(--tekst3); font-size: 12px; }
.vb-nu { font-size: 11px; font-weight: 600; padding: 1px 6px; border-radius: 4px; background: var(--vlak2); color: var(--tekst2); }
.vb-soc { display: inline-block; width: 40px; height: 4px; border-radius: 99px; background: var(--vlak2); overflow: hidden; margin-right: 8px; vertical-align: 2px; }
.vb-soc i { display: block; height: 100%; border-radius: 99px; }
.tabel.vb td small { color: var(--tekst3); }
.vb-samen { font-size: 12px; color: var(--tekst2); }
.vb-samen b { color: var(--tekst); }

/* ---- accumodules ---- */
.lijst { display: grid; gap: 8px; }
.modrij { display: grid; grid-template-columns: minmax(64px, auto) minmax(40px, 1fr) 44px; gap: 4px 12px; align-items: center; padding: 8px 12px; border-radius: var(--r2); background: var(--vlak); font-size: 13px; }
.modrij > b { font-weight: 600; }
.modrij.zwak { box-shadow: inset 0 0 0 1px rgba(217, 137, 79, .35); }
.modrij .w { text-align: right; font-weight: 600; font-size: 15px; }
.modrij .module-cijfers { grid-column: 1 / -1; }
.module-cijfers { display: flex; gap: 2px 12px; flex-wrap: wrap; align-items: center; font-size: 12px; color: var(--tekst3); }
.module-cijfers b { color: var(--tekst2); font-weight: 600; }
.module-cijfers b.hoog { color: var(--oranje); }
.module-cijfers .chip { height: 22px; padding: 0 8px; font-size: 11px; }

/* ---- bediening: gelijke schakelaars ---- */
.knoppen { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.knop {
  position: relative; color: var(--tekst2); text-align: left; cursor: pointer;
  display: flex; align-items: center; gap: 8px; min-width: 0; min-height: 48px;
  padding: 8px 12px; border-radius: var(--r2); border: 1px solid var(--rand); background: var(--vlak);
  transition: background .15s, border-color .15s;
}
.knop:hover { border-color: var(--rand2); color: var(--tekst); }
.knop:focus-visible { outline: 2px solid var(--blauw); outline-offset: 2px; }
.knop .kic { display: grid; place-items: center; flex: none; color: var(--tekst3); }
.knop .kic .ic { width: 16px; height: 16px; }
.knop .kn { font-size: 12px; font-weight: 600; line-height: 1.25; min-width: 0; overflow-wrap: anywhere; }
.knop .aan-t { position: absolute; top: 8px; right: 8px; width: 6px; height: 6px; border-radius: 50%; background: var(--blauw); font-size: 0; overflow: hidden; }
.knop.aan { color: var(--tekst); border-color: rgba(111, 149, 216, .45); background: rgba(111, 149, 216, .12); }
.knop.aan .kic { color: var(--blauw); }
.knop.bezig { opacity: .6; pointer-events: none; }
.knop.weg { opacity: .4; pointer-events: none; }

/* ---- huis en apparaten ---- */
.lijst.huislijst { gap: 8px; }
.regel { display: grid; grid-template-columns: 16px minmax(0, 1fr) auto; gap: 4px 12px; align-items: center; padding: 8px 12px; border-radius: var(--r2); background: var(--vlak); min-width: 0; }
.regel .ric { display: grid; place-items: center; color: var(--tekst3); }
.regel .rn { font-size: 13px; font-weight: 600; color: var(--tekst); }
.regel .rs { font-size: 12px; color: var(--tekst2); line-height: 1.35; }
.regel .rw { font-size: 13px; font-weight: 600; color: var(--rk, var(--tekst)); white-space: nowrap; text-align: right; }
.regel .rw .leeg { font-weight: 400; }
.regel > div { min-width: 0; }

/* ---- voet ---- */
.voet { margin-top: 16px; display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; }
.links { display: flex; gap: 4px; flex-wrap: wrap; flex: 1 1 auto; min-width: 0; }
.links button { font-size: 12px; color: var(--tekst2); background: transparent; border: 1px solid var(--rand); height: 28px; padding: 0 10px; border-radius: var(--r2); cursor: pointer; }
.links button:hover { color: var(--tekst); border-color: var(--rand2); }
.voetregel { font-size: 11px; color: var(--tekst3); margin-left: auto; }

/* ---- geen bron ---- */
.geenbron { padding: 24px; text-align: center; color: var(--tekst2); font-size: 13px; }
.geenbron b { color: var(--tekst); }

/* ---- breedtes ---- */
@container (min-width: 620px) {
  .huislijst { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .knoppen { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@container (min-width: 820px) {
  .hero { grid-template-columns: repeat(2, minmax(0, 1fr)); grid-template-areas: "accu geld" "plan plan"; }
  .t-accu { grid-area: accu; } .t-plan { grid-area: plan; } .t-geld { grid-area: geld; }
  .raster { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .p-planning, .p-huis, .p-bediening { grid-column: 1 / -1; }
  .knoppen { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
@container (min-width: 1260px) {
  .hero { grid-template-columns: repeat(3, minmax(0, 1fr)); grid-template-areas: "accu plan geld"; }
  .raster { grid-template-columns: repeat(12, minmax(0, 1fr)); }
  .p-planning, .p-huis { grid-column: span 8; order: 0; }
  .stapel { display: flex; flex-direction: column; gap: 12px; grid-column: span 4; min-width: 0; }
  .stapel > .paneel:last-child { flex: 1 1 auto; }
  .p-bediening { grid-column: span 4; order: 0; }
  .gwrap { grid-template-rows: 220px 24px; }
  /* de grafiek vult de kaart tot de rechterkolom: geen gat onderaan */
  .p-planning > .pb { display: flex; flex-direction: column; }
  .p-planning .gwrap { flex: 1 1 auto; grid-template-rows: minmax(220px, 1fr) 24px; }
  .huislijst { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .knoppen { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@container (max-width: 1259px) { .kop { flex-wrap: wrap; } .kop-mid { flex: 1 1 100%; order: 2; justify-content: flex-start; } }
@container (max-width: 560px) {
  .wrap { padding: 16px 16px 24px; }
  .kop-r { margin-left: auto; }
  .tegel, .paneel { padding: 12px; }
  .accu-t { grid-template-columns: 80px minmax(0, 1fr); gap: 12px; }
  .vier { gap: 4px; }
  .stat .l { white-space: normal; overflow: visible; text-overflow: clip; align-items: flex-start; overflow-wrap: anywhere; hyphens: auto; }
  .stat .l .stip { margin-top: 4px; }
  .vier .stat, .trio .stat { padding: 6px 8px; }
  .ph { height: auto; min-height: 28px; flex-wrap: wrap; row-gap: 8px; }
  .ph-r { overflow: visible; flex-wrap: wrap; }
  .planvolg { grid-template-columns: minmax(0, 1fr); }
  .planvolg .rk { margin-bottom: -4px; }
  .gwrap { grid-template-columns: 28px 1fr 32px; grid-template-rows: 180px 24px; }
  .tabel td, .tabel th { padding-left: 6px; padding-right: 6px; }
  /* v5.215.0: op een smal scherm vielen Vermogen en Prijs buiten beeld. */
  .tabel.vb { display: block; overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .tabs button { padding: 0 8px; }
  .ph h2 { overflow: hidden; text-overflow: ellipsis; }
  .kop-mid { padding-left: 0; }
  .chip { white-space: normal; height: auto; min-height: 28px; padding: 6px 12px; line-height: 1.3; }
}
`;

/* ------------------------------------------------------------------ */
/* De kaart                                                            */
/* ------------------------------------------------------------------ */

/* v5.146.1: Vooruitblik in blokken per verwachte status, met een horizonkeuze. */
const VB_HORIZONNEN = [2, 6, 12, 24];
const VB_STANDAARD_UREN = 6;

/* v5.181.2 (f): het logo, geserveerd door de integratie zelf (cockpit_frontend.py). */
const LOGO_URL = "/energy_management_system/ems-logo.png";
const LOGO_URL_2X = "/energy_management_system/ems-logo@2x.png";

/* v5.178.0: de tabbladen van Prijs en lading, onthouden per browser. */
/* v5.181.4 (Ruud 04-11): geen aparte tabs Vandaag/Morgen meer; "Prijzen" toont
   alle bekende kwartierprijzen achter elkaar (vandaag en, zodra bekend, morgen). */
const TABS = [["prijzen", "Prijzen"], ["week", "7 dagen"]];

/* v5.178.0: wat de accu per kwartier doet, voor de tijdlijn en de grafiek. */
const DOEN = {
  rust: { label: "Rust", kleur: "var(--blauw)" },
  bewaren: { label: "Bewaren voor later", kleur: "#7d8fd0" },
  zon: { label: "Zon laden", kleur: "var(--amber)" },
  net: { label: "Net laden", kleur: "var(--groen)" },
  voeden: { label: "Huis voeden", kleur: "var(--cyaan)" },
  verkopen: { label: "Verkopen", kleur: "var(--oranje)" },
  terug: { label: "Zon terugleveren", kleur: "#b9c46a" },
  leeg: { label: "Accu leeg", kleur: "#3d4555" },
};
const doen = (r) => {
  const m = modus(r.modus);
  if (m.k === "verkopen") return "verkopen";
  if (m.k === "terug") return "terug";
  if (m.k === "laden") return "net";
  if (r.tekort) return "leeg";
  const a = num(r.accu_w);
  // v5.181.4: sparen zonder laden of ontladen heet overal "bewaren" (was
  // "Rust" in tijdlijn en Vooruitblik, "Bewaren voor later" in de tegel).
  const stil = m.k === "sparen" ? "bewaren" : "rust";
  if (a != null) return a <= -50 ? "zon" : a >= 50 ? "voeden" : stil;
  return m.k === "ontladen" ? "voeden" : stil;
};
/* v5.181.1 (punt 9): wat de accu nu doet, in een zin voor tegel, kopchip,
   tijdlijn en uitleg. Dezelfde tabellen als standweergave.py (een toets houdt
   ze gelijk): de planrij (handmatig laden, verkopen, terugleveren) bepaalt, en
   anders het gemeten vermogen; de reden geeft hooguit een toelichting. */
const STAND_TOELICHTING = {
  waardeplan_houden: "lading bewaren voor later",
  battery_saved_for_peak: "lading bewaren voor de piek",
  sparen_in_blok: "lading bewaren voor na het blok",
  celbescherming_houden: "lading vasthouden (celbescherming)",
};
const STAND_RUST = {
  waardeplan_houden: "Bewaren voor later",
  battery_saved_for_peak: "Bewaren voor de piek",
  sparen_in_blok: "Bewaren voor na het blok",
  celbescherming_houden: "Lading vasthouden",
};
/* v5.181.2 (a): een mapping - `doen` - voor staaf, tijdlijn, Vooruitblik,
   tegel en kopchip. */
const standSoort = (planModus, accuW, tekort) => doen({ modus: planModus, accu_w: accuW, tekort });
const standWeergave = (reden, planModus, accuW, tekort = false) => {
  let k = standSoort(planModus, accuW, tekort);
  const stil = k === "rust" || k === "bewaren";
  if (reden === "waardeplan_leeg" && stil) k = "leeg";
  const toel = STAND_TOELICHTING[reden || ""];
  let label;
  if (stil && k !== "leeg" && STAND_RUST[reden]) label = STAND_RUST[reden];
  else if (k === "zon" && toel) label = `${DOEN[k].label} \u2013 ${toel}`;
  else label = DOEN[k].label;
  return { k, label, kleur: DOEN[k].kleur };
};
/* v5.181.2 (a): de weergave van een planrij (= standweergave.weergave_rij). */
const kwartierWeergave = (r, reden) => standWeergave(reden, r && r.modus, r ? num(r.accu_w) : null, !!(r && r.tekort));
/* v5.181.2 (a): stuurt het EMS niet, dan zegt de tegel dat (= standweergave.HANDMATIG). */
const STAND_HANDMATIG = {
  smart_charge: "Handmatig: slim laden \u2013 EMS stuurt niet",
  laden: "Handmatig: laden \u2013 EMS stuurt niet",
  "": "Leermodus \u2013 EMS stuurt niet",
};
const handmatigWeergave = (stand) => {
  const s = String(stand || "");
  const k = s === "laden" ? "net" : s === "smart_charge" ? "zon" : "rust";
  return { k, label: STAND_HANDMATIG[s] || STAND_HANDMATIG[""], kleur: DOEN[k].kleur, handmatig: true };
};
/* v5.181.2 (b): de accustand-lijn begint bij "nu" op de live laadstand. Het
   verschil met het plan op dat moment loopt over `blendMs` lineair weg; de
   kwartieren voor "nu" vallen weg. punten: [{t (ms, eind kwartier), soc}]. */
const SOC_BLEND_MS = 3 * 3600000;
const socLijn = (punten, nuT, socLive, blendMs = SOC_BLEND_MS) => {
  const p = punten.filter((q) => q && q.soc != null && Number.isFinite(q.t));
  if (socLive == null || !Number.isFinite(nuT)) return p;
  const voor = p.filter((q) => q.t <= nuT);
  const na = p.filter((q) => q.t > nuT);
  // het plan op "nu": tussen het laatste punt ervoor en het eerste erna
  let planNu = null;
  const a = voor[voor.length - 1];
  const b = na[0];
  if (a && b) planNu = a.soc + (b.soc - a.soc) * ((nuT - a.t) / Math.max(1, b.t - a.t));
  else if (b) planNu = b.soc;
  else if (a) planNu = a.soc;
  const verschil = planNu == null ? 0 : socLive - planNu;
  return [{ t: nuT, soc: socLive }].concat(na.map((q) => {
    const w = Math.max(0, 1 - (q.t - nuT) / blendMs);
    return { t: q.t, soc: Math.max(0, Math.min(100, q.soc + verschil * w)) };
  }));
};

/* v5.181.1 (punt 8): gepland (EMS, elke ronde) tegen gemeten (live in de
   browser). Dezelfde regels als planvolging.beoordeel. */
const PV_DREMPEL_W = 150;
const handmatig = (m) => String(m || "").startsWith("manual");
const kwTekst = (w) => `${fmt(Math.abs(w) / 1000, 1)} kW`;
const richting = (w) => (Math.abs(w) < PV_DREMPEL_W ? "in rust" : w < 0 ? `laadt ${kwTekst(w)}` : `ontlaadt ${kwTekst(w)}`);
/* v5.181.2 (e): het verschil vanuit wat er gepland was (= planvolging.verschil_tekst).
   Live 04-11 11:34: 2,40 kW laden gepland, 1,36 kW gemeten -> "meer ontladen";
   het is "minder laden". + is ontladen, - laden. */
const verschilTekst = (gepland, gemeten) => {
  const v = gemeten - gepland;
  if (Math.abs(v) < 50) return "geen";
  const soort = (w) => (w <= -50 ? "laden" : w >= 50 ? "ontladen" : "rust");
  const plan = soort(gepland);
  const echt = soort(gemeten);
  if (plan === "laden" && echt === "laden") return v > 0 ? "minder laden" : "meer laden";
  if (plan === "ontladen" && echt === "ontladen") return v > 0 ? "meer ontladen" : "minder ontladen";
  if (plan === "laden" && echt === "ontladen") return "ontlaadt in plaats van laden";
  if (plan === "ontladen" && echt === "laden") return "laadt in plaats van ontladen";
  if (echt === "rust") return plan === "laden" ? "laadt niet" : "ontlaadt niet";
  return echt === "laden" ? "laadt in plaats van rust" : "ontlaadt in plaats van rust";
};
const planvolgingLive = (ems, live) => {
  // v5.181.2 (c): stuurt het EMS niet, dan geen afwijking - alleen de meting.
  if (ems && ems.niet_gestuurd) {
    return { ...ems, gemeten_accu_w: live.accu == null ? ems.gemeten_accu_w : Math.round(live.accu),
      gemeten_zon_w: live.zon == null ? ems.gemeten_zon_w : Math.round(live.zon), verschil_w: null,
      tekst: "EMS stuurt niet (handmatig)", live: true };
  }
  if (!ems || !ems.beschikbaar || live.accu == null || num(ems.gepland_accu_w) == null) return ems;
  const gepland = num(ems.gepland_accu_w);
  const verschil = live.accu - gepland;
  const zonD = live.zon == null || num(ems.gepland_zon_w) == null ? null : live.zon - num(ems.gepland_zon_w);
  const huisD = live.huis == null || num(ems.gepland_huis_w) == null ? null : live.huis - num(ems.gepland_huis_w);
  const plan = ems.modus;
  const bijdragen = handmatig(plan) ? {} : { zon: -(zonD || 0), verbruik: huisD || 0 };
  const rest = verschil - Object.values(bijdragen).reduce((a, b) => a + b, 0);
  const andere = live.stand != null && plan != null && handmatig(live.stand) !== handmatig(plan);
  let oorzaak;
  let status;
  if (Math.abs(verschil) < PV_DREMPEL_W) { oorzaak = "geen"; status = "volgens plan"; }
  else if (andere) { oorzaak = "sturing"; status = "afwijking sturing"; }
  else if (Math.abs(rest) >= PV_DREMPEL_W) { oorzaak = "accu"; status = "afwijking accu"; }
  else {
    oorzaak = Object.keys(bijdragen).reduce((a, b) => (Math.abs(bijdragen[b]) > Math.abs(bijdragen[a] || 0) ? b : a), "zon");
    status = "verklaard";
  }
  const kop = `Accu ${richting(live.accu)}`;
  const reden = oorzaak === "geen" ? "volgens plan"
    : oorzaak === "zon" ? `${zonD > 0 ? "meer" : "minder"} zon dan voorspeld`
    : oorzaak === "verbruik" ? `huis verbruikt ${huisD > 0 ? "meer" : "minder"} dan verwacht`
    : oorzaak === "sturing" ? "de sturing koos een andere stand"
    : `de accu wijkt zelf ${kwTekst(rest)} af`;
  return {
    ...ems,
    gemeten_accu_w: Math.round(live.accu),
    gemeten_zon_w: live.zon == null ? null : Math.round(live.zon),
    verschil_w: Math.round(verschil),
    verschil_tekst: verschilTekst(gepland, live.accu),
    zon_verschil_w: zonD == null ? null : Math.round(zonD),
    zon_verschil_tekst: null,
    oorzaak,
    status,
    tekst: oorzaak === "geen" ? `${kop}, volgens plan` : `${kop} \u2013 ${reden}`,
    live: true,
  };
};

/* Eindtijd; middernacht als 24:00. */
const eindKlok = (d) => (d.getHours() === 0 && d.getMinutes() === 0 ? "24:00" : klok(d));

/* v5.181.1 (punt 8): minimale tijd tussen twee tekenbeurten (2 per seconde). */
const TEKEN_MIN_MS = 500;

/* Per paneel de sleutels waar het van afhangt. */
const AFHANKELIJK = {
  kop: ["status", "cockpit", "prijs", "modus", "verwacht", "gezondheid", "uitleg", "plan", "blok", "aanwezig",
    "accu_vermogen"],
  meldingen: ["status", "tekort"],
  accu: ["soc", "beschikbaar", "capaciteit", "accu_vermogen", "pv", "net", "huis", "gacs", "reden", "verwacht",
    "uitleg", "modus", "schema", "plan", "accuprijs", "cockpit"],
  // v5.181.1 (punt 7): de planvolging komt elke ronde van de cockpitsensor.
  planvandaag: ["plan", "schema", "soc", "besparing", "uitleg", "cockpit", "accu_vermogen", "pv", "net", "modus"],
  geld: ["kostenTotaal", "besparing", "perioden", "zelfvoorziening", "zelfanalyse", "repetitie", "dagarchief", "rendement", "gacs"],
  planning: ["plan", "schema", "uitleg", "blok", "soc", "prijsverwachting"],
  verkoop: ["gacs", "plan", "mc", "tekort", "uitleg", "blok", "zon_vandaag", "zon_rest", "zon_morgen", "zon_werkelijk",
    "pvNauw", "bewolking", "pv"],
  modules: ["modules", "koeling", "accuGezondheid", "rendement"],
  huis: ["fietsen", "stofzuiger", "lader", "vaatwasser", "wasmachine", "vaatwasserPlan", "wasmachinePlan", "aircoBesluit", "klimaat", "water", "temp_binnen", "temp_buiten", "huis", "sluip",
    "vaatwasser_w", "wasmachine_w", "stofzuiger_w", "fietsen_w", "lader_w", "airco_w"],
  bediening: ["nuLaden", "verkoopUit", "handLaden", "handSmart", "forceManual", "leermodus", "kalibratie", "vakantie",
    "aircoAutomaat", "fietsenOverrule", "stofzuigerOverrule", "laderOverrule", "meldingenAan", "achterhoeks"],
  voet: ["meetlog", "gezondheid", "status", "cockpit"],
};

/* De knoppen: sleutel, naam, uitleg, icoon, kleur, vraag om bevestiging.
   v5.178.0: zonder groepskoppen, de vaakst gebruikte eerst. */
const KNOPPEN = [
  { k: "nuLaden", n: "Nu laden", s: "Direct uit het net bijladen", ic: "bout", kl: "var(--groen)" },
  { k: "verkoopUit", n: "Verkopen uit", s: "Vandaag niets verkopen (tot middernacht)", ic: "euro", kl: "var(--rood)" },
  { k: "handLaden", n: "Handmatig laden", s: "Laden met vast vermogen", ic: "accu", kl: "var(--groen)", vraag: true },
  { k: "handSmart", n: "Smart charge", s: "Alleen zon de accu in", ic: "zon", kl: "var(--amber)", vraag: true },
  { k: "vakantie", n: "Vakantie", s: "Minder verbruik verwacht", ic: "vakantie", kl: "var(--blauw)", vraag: true },
  { k: "fietsenOverrule", n: "Fietsen nu laden", s: "Niet wachten op het blok", ic: "fiets", kl: "var(--groen)" },
  { k: "stofzuigerOverrule", n: "Stofzuiger nu laden", s: "Niet wachten op het blok", ic: "stof", kl: "var(--groen)" },
  { k: "meldingenAan", n: "Meldingen", s: "Alle meldingen aan of uit", ic: "bel", kl: "var(--amber)" },
  { k: "aircoAutomaat", n: "Airco automaat", s: "EMS stuurt de airco", ic: "airco", kl: "var(--cyaan)" },
  { k: "laderOverrule", n: "Batterijlader handmatig", s: "EMS laat de lader met rust", ic: "accu", kl: "var(--groen)" },
  { k: "forceManual", n: "Force manual", s: "Sturing zelf overnemen", ic: "hand", kl: "var(--oranje)", vraag: true },
  { k: "kalibratie", n: "Kalibratie", s: "Accu vol laden en ijken", ic: "ijk", kl: "var(--cyaan)", vraag: true },
  { k: "leermodus", n: "Leermodus", s: "Alleen leren, niet sturen", ic: "leren", kl: "var(--violet)", vraag: true },
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

/* ---- scrollplek vasthouden (v5.194.1) ----
   Gemeld 08-11: op de mobiel sprong de cockpit tijdens het scrollen telkens
   terug naar boven. Een sprong naar boven zonder dat er gebladerd of een
   andere pagina gekozen is (zelfde adres, geen tik buiten de kaart) zetten we
   terug. Duimscrollen gaat in kleine stappen; alleen een sprong in een keer
   van ver omlaag naar (bijna) 0 telt. Het actieve tabblad opnieuw aantikken
   (HA scrolt dan bewust naar boven) blijft werken: dat is een tik buiten de
   kaart. */
const PLEK = { y: 0, pad: "", buitenTik: 0, kaarten: new Set(), klaar: false, hersteld: 0 };
const SPRONG_VANAF_PX = 300;
const SPRONG_BOVEN_PX = 8;
const BUITEN_TIK_MS = 1500;
const isSprongNaarBoven = (vorige, nu, padGelijk, sindsBuitenTik) =>
  padGelijk && vorige >= SPRONG_VANAF_PX && nu <= SPRONG_BOVEN_PX && sindsBuitenTik > BUITEN_TIK_MS;
const herstelPlek = (y, pogingen = 20) => {
  // De pagina kan even korter zijn (opnieuw opgebouwd); dan een paar beelden wachten
  const doe = (n) => {
    const max = (document.documentElement.scrollHeight || 0) - (window.innerHeight || 0);
    if (max >= y - 2 || n <= 0) {
      window.scrollTo({ top: Math.min(y, Math.max(0, max)), behavior: "auto" });
      PLEK.y = window.scrollY;
      return;
    }
    requestAnimationFrame(() => doe(n - 1));
  };
  requestAnimationFrame(() => doe(pogingen));
};
const volgPlek = () => {
  if (PLEK.klaar || typeof window === "undefined") return;
  PLEK.klaar = true;
  PLEK.y = window.scrollY || 0;
  PLEK.pad = location.pathname;
  window.addEventListener("pointerdown", (ev) => {
    const pad = ev.composedPath ? ev.composedPath() : [];
    if (![...PLEK.kaarten].some((k) => pad.includes(k))) PLEK.buitenTik = Date.now();
  }, { passive: true, capture: true });
  window.addEventListener("scroll", () => {
    const nu = window.scrollY || 0;
    const padGelijk = location.pathname === PLEK.pad;
    const zichtbaar = [...PLEK.kaarten].some((k) => k.isConnected);
    if (zichtbaar && isSprongNaarBoven(PLEK.y, nu, padGelijk, Date.now() - PLEK.buitenTik)) {
      PLEK.hersteld += 1;
      console.info("EMS cockpit: sprong naar boven teruggezet", PLEK.y);
      herstelPlek(PLEK.y);
      return;
    }
    PLEK.y = nu;
    PLEK.pad = location.pathname;
  }, { passive: true });
  window.addEventListener("location-changed", () => { PLEK.pad = location.pathname; PLEK.y = window.scrollY || 0; });
  window.addEventListener("popstate", () => { PLEK.pad = location.pathname; });
};

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
      this._moduleWIds = uit.modulesW;
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
    // v5.181.1 (punt 8): de modulesensoren live
    for (const id of [...(this._moduleIds || []), ...(this._moduleWIds || [])]) {
      const s = hass.states[id];
      if (s !== this._vorige[id]) {
        this._vorige[id] = s;
        this._vuil.add("modules");
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
    PLEK.kaarten.add(this);
    if (!this._tik) {
      // Klok, "over x min", de tijdlijn en de nu-lijn lopen ook zonder nieuwe states door
      this._tik = setInterval(() => {
        for (const p of ["kop", "accu", "planvandaag", "planning", "voet"]) this._vuil.add(p);
        this._plan();
      }, 30000);
    }
  }

  disconnectedCallback() {
    PLEK.kaarten.delete(this);
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
    volgPlek();
    this.shadowRoot.innerHTML =
      `<style>${STIJL}</style>` +
      `<div class="root"><div class="wrap">` +
      `<header class="kop" data-p="kop"></header>` +
      `<div class="geenbron" data-p="geenbron" hidden></div>` +
      `<div class="meldingen" data-p="meldingen"></div>` +
      // v5.178.0: drie tegels - accu nu, plan vandaag, geld (gevraagd 04-11:
      // de pagina zo'n 40 % korter, minder herhaling, tekst ingeklapt).
      `<section class="hero" aria-label="Status">` +
      `<div class="hv t-accu" data-p="accu"></div>` +
      `<div class="hv t-plan" data-p="planvandaag"></div>` +
      `<div class="hv t-geld" data-p="geld"></div>` +
      `</section>` +
      // v5.179: een raster van 12 kolommen met rijen die gelijk eindigen -
      // Prijs en lading (8) naast accumodules en reserve (4), daaronder Huis
      // en apparaten (8) naast de bediening (4). Smal: een of twee kolommen.
      `<main class="raster">` +
      `<section class="paneel p-planning" data-p="planning"></section>` +
      `<div class="stapel">` +
      `<section class="paneel p-modules" data-p="modules"></section>` +
      `<section class="paneel p-verkoop" data-p="verkoop"></section>` +
      `</div>` +
      `<section class="paneel p-huis" data-p="huis"></section>` +
      `<section class="paneel p-bediening" data-p="bediening"></section>` +
      `</main>` +
      `<footer class="voet" data-p="voet"></footer>` +
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
      // v5.178.0: tabblad van Prijs en lading
      const tab = doel.closest("[data-tab]");
      if (tab) {
        if (tab.disabled) return;
        this._tabKeuze = tab.dataset.tab;
        try { localStorage.setItem("ems-cockpit-tab", this._tabKeuze); } catch (e) { /* geen opslag */ }
        this._vuil.add("planning");
        this._plan();
        return;
      }
      // v5.146.1: horizon van de Vooruitblik (2/6/12/24 uur)
      const horizon = doel.closest("[data-horizon]");
      if (horizon) {
        this._vbUren = parseInt(horizon.dataset.horizon, 10) || VB_STANDAARD_UREN;
        try { localStorage.setItem("ems-vooruitblik-uren", String(this._vbUren)); } catch (e) { /* geen opslag */ }
        this._vuil.add("planning");
        this._plan();
        return;
      }
      if (doel.closest("summary")) return;
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
      // v5.181.1 (punt 8): live metingen komen per seconde binnen; hoogstens
      // twee tekenbeurten per seconde, en alleen panelen die echt veranderen
      // (de html-vergelijking in _teken).
      const wacht = TEKEN_MIN_MS - (Date.now() - (this._laatstGetekend || 0));
      if (wacht > 0) {
        setTimeout(doe, wacht);
        return;
      }
      this._gepland = false;
      this._laatstGetekend = Date.now();
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
    const vastgehouden = [];
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
        // v5.194.1: de hoogte even vasthouden, zodat de pagina tijdens het
        // vervangen niet korter wordt (dat zette de scrollplek terug)
        const hoogte = el.offsetHeight;
        if (hoogte > 0 && html !== null) {
          el.style.minHeight = `${hoogte}px`;
          vastgehouden.push(el);
        }
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
    if (vastgehouden.length) {
      const los = () => { for (const el of vastgehouden) el.style.minHeight = ""; };
      if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => requestAnimationFrame(los));
      else setTimeout(los, 0);
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

  /* v5.181.1 (punt 8): een live momentopname uit de bronentiteiten (zon, net,
     accu, laadstand), bij elke update van Home Assistant. Het huis uit
     dezelfde opname: zon + net + accu (accu + is ontladen, na omkeren - zoals
     het EMS). Ontbreekt een bron, dan de opname van de laatste EMS-ronde. */
  _live() {
    const ems = attr(this._s("cockpit"), "stroom") || {};
    const accu = this._accuW();
    const zon = getal(this._s("pv"));
    const net = getal(this._s("net"));
    const live = {
      accu: accu != null ? accu : num(ems.accu_w),
      zon: zon != null ? Math.max(0, zon) : num(ems.zon_w),
      net: net != null ? net : num(ems.net_w),
      soc: getal(this._s("soc")),
      stand: bruikbaar(this._s("modus")) ? this._s("modus").state : null,
    };
    live.huis = live.accu != null && live.zon != null && live.net != null
      ? Math.max(0, live.zon + live.net + live.accu)
      : num(ems.huis_w);
    return live;
  }

  /* v5.181.1 (punt 9): de stand zoals de hele cockpit hem noemt. */
  /* v5.181.2 (a): tegel, kopchip, staaf, tijdlijn en Vooruitblik uit
     dezelfde weergave per kwartier: de planrij van nu (`kwartierWeergave`).
     Stuurt het EMS niet (leermodus, ook via Handmatig laden / Smart charge),
     dan zegt de stand dat. Zonder planrij het gemeten vermogen. */
  _stand(live) {
    const st = attr(this._s("cockpit"), "stand") || {};
    const reden = st.reden || (bruikbaar(this._s("reden")) ? this._s("reden").state : null);
    const aan = (k) => bruikbaar(this._s(k)) && this._s(k).state === "on";
    if (aan("leermodus") || aan("handSmart") || aan("handLaden")) {
      const hand = aan("handLaden") ? "laden" : aan("handSmart") ? "smart_charge" : "";
      return { reden, ...handmatigWeergave(hand) };
    }
    const rij = this._huidigeRij();
    // v5.181.4: het lopende kwartier volgt het gemeten vermogen (laadt de zon
    // de accu, dan staat er "Zon laden", ook als het plan 0 W verwachtte).
    if (rij) return { reden, ...kwartierWeergave(this._rijNu(rij, live), reden) };
    return { reden, ...standWeergave(reden, st.plan_modus, (live || this._live()).accu) };
  }

  /* v5.181.4: de planrij van nu met het gemeten accuvermogen. */
  _rijNu(rij, live) {
    const a = num((live || this._live()).accu);
    return a == null ? rij : { ...rij, accu_w: a };
  }

  /* v5.181.2 (a): de planrij van het lopende kwartier, of null. */
  _huidigeRij() {
    const rijen = this._planRijen();
    const tijden = planTijden(rijen);
    const nu = Date.now();
    const i = tijden.findIndex((d) => d.getTime() <= nu && d.getTime() + 15 * 60000 > nu);
    return i >= 0 ? rijen[i] : null;
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

  /* v5.178.0: tot wanneer "vandaag" loopt: middernacht, maar minstens 6 uur. */
  _vensterTot() {
    const m = new Date();
    m.setHours(24, 0, 0, 0);
    return Math.max(m.getTime(), Date.now() + 6 * 3600000);
  }

  /* Het goedkope laadblok in woorden: "11:30-12:30 (over 4 u 23 min)". */
  _blokTekst() {
    const b = this._s("blok");
    const start = bruikbaar(b) ? alsDatum(b.state) : null;
    if (!start) return "";
    const eind = alsDatum(attr(b, "end"));
    const loopt = start.getTime() <= Date.now() && (!eind || eind.getTime() > Date.now());
    return `${dagLabel(start)}${klok(start)}${eind ? "\u2013" + klokEind(start, eind) : ""}` +
      (loopt ? " (loopt)" : ` (${overTijd(start)})`);
  }

  /* Laagste en hoogste prijs in de rest van het plan, met het tijdstip. */
  _komendePrijzen() {
    const rijen = this._planRijen();
    const tijden = planTijden(rijen);
    let laag = null;
    let hoog = null;
    rijen.forEach((r, i) => {
      const p = num(r.prijs_ct);
      if (p == null || tijden[i].getTime() + 15 * 60000 <= Date.now()) return;
      if (!laag || p < laag.ct) laag = { ct: p, tijd: dagLabel(tijden[i]) + klok(tijden[i]) };
      if (!hoog || p > hoog.ct) hoog = { ct: p, tijd: dagLabel(tijden[i]) + klok(tijden[i]) };
    });
    return { laag, hoog };
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
    // v5.181.1 (punt 9): dezelfde weergave als de tegel "Accu nu"
    const stand = this._stand();
    // v5.181.2 (a): altijd de weergave van het lopende kwartier
    const kopStand = stand.label ? stand : { label: m.label, kleur: m.kleur };
    const modusChip = chip(`<span class="stip" style="--kleur:${kopStand.kleur}"></span>Accu: ${esc(kopStand.label)}`, "groot");

    // v5.178.0: de prijs staat in de kop (de tegel Stroomprijs is weg)
    const prijs = getal(this._s("prijs"));
    const drempel = num(attr(this._s("uitleg"), "expensive_price_threshold"));
    const duur = prijs != null && drempel != null && prijs >= drempel;
    const prijsChip = prijs != null
      ? `<span class="chip groot ${duur ? "let" : ""}">${icoon("euro")}Nu ${ct(prijs)} ct` +
        `${drempel != null ? `<span class="leeg">${duur ? "duur" : "onder duur"} (${ct(drempel)})</span>` : ""}</span>`
      : "";
    const kom = this._komendePrijzen();
    const blok = this._blokTekst();
    const blokChip = blok ? `<span class="chip groot">${icoon("klok")}Goedkoopste blok <span class="leeg">${esc(blok)}</span></span>` : "";
    const laag = kom.laag
      ? `<span class="chip groot" title="Laagste prijs in het plan">` +
        `<span class="stip" style="--kleur:var(--groen)"></span>Goedkoopst ${fmt(kom.laag.ct, 1)} ct${PUNT}${esc(kom.laag.tijd)}</span>`
      : "";
    const hoog = kom.hoog
      ? `<span class="chip groot" title="Hoogste prijs in het plan">` +
        `<span class="stip" style="--kleur:var(--oranje)"></span>Duurst ${fmt(kom.hoog.ct, 1)} ct${PUNT}${esc(kom.hoog.tijd)}</span>`
      : "";

    return (
      // v5.181.2 (f): het eigen logo van de integratie (brand/icon.png, zelf geserveerd)
      `<div class="merk"><div class="logo"><img src="${LOGO_URL}" srcset="${LOGO_URL_2X} 2x" width="34" height="34" alt="Energy Management System"></div>` +
      `<div><div class="merknaam">Energiecockpit</div>` +
      `<div class="merksub">Energy Management System${this._hass.config && this._hass.config.location_name ? PUNT + esc(this._hass.config.location_name) : ""}</div></div></div>` +
      `<div class="kop-mid">${status}${this._aanwezigChip()}${modusChip}${prijsChip}${laag}${hoog}${blokChip}</div>` +
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

  /* ---- statusrij: accu nu ---- */

  _accu() {
    const soc = getal(this._s("soc"));
    const ruw = getal(this._s("beschikbaar"));
    const besch = ruw == null ? null : Math.max(0, ruw);
    const cap = getal(this._s("capaciteit"));
    // v5.181.1 (punt 4): een momentopname van het EMS (zon, net, accu, huis
    // uit dezelfde ronde); zonder opname de losse sensoren zoals voorheen.
    const live = this._live();
    const w = live.accu;
    const pv = live.zon;
    const net = live.net;
    const huis = live.huis;
    const stand = this._stand(live);
    const kleur = "var(--violet)";
    const waarom = this._gacs("waarom_nu");
    const verwacht = attr(this._s("uitleg"), "expected_mode") || (bruikbaar(this._s("verwacht")) ? this._s("verwacht").state : "");
    const m = modus(verwacht);
    // v5.181.1 (punt 9): in een slimme stand wat er werkelijk gebeurt
    // v5.181.2 (a): de titel is de weergave van het lopende kwartier
    const kort = stand.label ? stand.label
      : waarom.kop ? hoofd(waarom.kop) : waarom.kort ? hoofd(waarom.kort) : m.label;
    const redenen = Array.isArray(waarom.redenen) ? waarom.redenen.slice(0, 3) : [];
    // v5.181.2 (a): "Daarna" = het volgende blok van de Vooruitblik (zelfde weergave)
    const rijenNu = this._planRijen();
    const vb = rijenNu.length ? this._vooruitBlokken(rijenNu, planTijden(rijenNu), 24, soc) : [];
    const blok = stand.handmatig ? null : vb.find((b, j) => j > 0 && b.k !== stand.k) || null;
    const haalt = attr(this._s("gacs"), "haalt_de_accu_het");
    const resttijd = this._accuResttijd(w, soc);
    const regel = [
      besch != null ? `${fmt(besch, 2)} kWh bruikbaar${cap != null ? ` van ${fmt(cap, 2)}` : ""}` : "",
      this._planUitkomst(soc),
    ].filter(Boolean).join(PUNT);
    // v5.181.1 (punt 1): rekent het EMS wel maar stuurt het niet, dan zeggen we dat.
    const niet = (attr(this._s("uitleg"), "waardeplan") || {}).niet_gestuurd;
    const daarna = blok
      ? `<div class="sub">Daarna: <b>${esc(blok.label)}</b> vanaf ${esc(klokDag(blok.start) || "")}</div>`
      : "";

    // v5.178.0: de energiestroom als vier vakjes (alle waarden van het schema)
    const cel = (naam, waarde, sub, k) => stat(naam, waarde, sub, k);
    const vier =
      `<div class="vier">` +
      cel("Zon", watt(pv == null ? null : Math.max(0, pv)), pv != null && pv > 20 ? "wekt op" : "geen opwek", "var(--amber)") +
      cel("Net", watt(net == null ? null : Math.abs(net)), net == null ? STREEP : net < -20 ? "teruglevering" : net > 20 ? "afname" : "in balans",
        "var(--blauw)") +
      cel("Huis", watt(huis), "verbruik", "var(--tekst)") +
      cel("Accu", watt(w == null ? null : Math.abs(w)), w == null ? STREEP : w < -20 ? "laadt" : w > 20 ? "ontlaadt" : "in rust",
        "var(--violet)") +
      `</div>`;
    const waaromInhoud =
      (redenen.length ? `<ul class="redenen">${redenen.map((r) => `<li>${esc(hoofd(r))}</li>`).join("")}</ul>` : "") +
      (typeof haalt === "string" && haalt ? `<div class="sub" style="margin-top:6px">${esc(haalt)}</div>` : "");
    return (
      `<div class="tegel">` +
      paneelKop("accu", "Accu nu") +
      `<div class="accu-t"><div class="soc" data-info="soc" title="Laadstand">${socBlok(soc, kleur)}</div>` +
      `<div class="regels-k" data-info="verhaal"><div class="tekst-m">${esc(kort)}</div><div class="sub">${esc(regel)}</div>${daarna}` +
      (niet ? `<div class="sub">Niet naar de accu gestuurd: <b>${esc(niet)}</b></div>` : "") + `</div></div>` +
      vier +
      `<div class="regels-k">` +
      (resttijd ? `<div class="rest">Bij het huidige vermogen ${esc(resttijd)}</div>` : "") +
      this._accuPrijsRegel() + `</div>` +
      this._uitklap("waarom", "Waarom?", waaromInhoud, true) +
      `</div>`
    );
  }

  /* Waar het plan de accu vandaag naartoe brengt: "vult tot 41% (14:45)". */
  _planUitkomst(socNu) {
    const rijen = this._planRijen();
    if (!rijen.length) return "";
    const tijden = planTijden(rijen);
    const tot = this._vensterTot();
    let hoog = null;
    let laag = null;
    rijen.forEach((r, i) => {
      const t = tijden[i].getTime();
      const s = num(r.soc_procent);
      if (s == null || t + 15 * 60000 <= Date.now() || t >= tot) return;
      if (!hoog || s > hoog.s) hoog = { s, t: new Date(t + 15 * 60000) };
      if (!laag || s < laag.s) laag = { s, t: new Date(t + 15 * 60000) };
    });
    if (!hoog) return "";
    const basis = socNu == null ? hoog.s : socNu;
    if (hoog.s >= basis + 2) return `plan vult tot ${fmt(hoog.s)}% (${eindKlok(hoog.t)})`;
    if (laag.s <= basis - 2) return `plan zakt tot ${fmt(laag.s)}% (${eindKlok(laag.t)})`;
    return `plan houdt ${fmt(basis)}%`;
  }

  /* ---- statusrij: plan vandaag ---- */

  _planvandaag() {
    const rijen = this._planRijen();
    const tijden = planTijden(rijen);
    const kop = paneelKop("klok", "Plan vandaag");
    const tot = this._vensterTot();
    const nu = Date.now();
    const segs = [];
    const uren = [];
    rijen.forEach((r, i) => {
      const t0 = tijden[i].getTime();
      if (t0 + 15 * 60000 <= nu || t0 >= tot) return;
      // v5.214.1: het lopende kwartier met het gemeten vermogen, net als de Vooruitblik.
      const d = DOEN[doen(t0 <= nu ? this._rijNu(r) : r)];
      if (tijden[i].getMinutes() === 0) uren.push([segs.length, tijden[i].getHours()]);
      segs.push(
        `<i style="background:${d.kleur}" title="${esc(`${dagLabel(tijden[i])}${r.van}${PUNT}${d.label}` +
          (num(r.prijs_ct) != null ? `${PUNT}${fmt(r.prijs_ct, 1)} ct` : "") +
          (num(r.soc_procent) != null ? `${PUNT}accu ${fmt(r.soc_procent)}%` : ""))}"></i>`
      );
    });
    const n = segs.length;
    const stap = n > 48 ? 4 : n > 24 ? 3 : 2;
    const labels = [`<span style="left:0">nu</span>`].concat(
      uren
        .filter(([j, h]) => h % stap === 0 && j / n > 0.06 && j / n < 0.95)
        .map(([j, h]) => `<span style="left:${((j / n) * 100).toFixed(1)}%">${h === 0 ? "24" : String(h).padStart(2, "0")}</span>`)
    ).join("");
    const gezien = new Set(rijen.filter((r, i) => tijden[i].getTime() + 15 * 60000 > nu && tijden[i].getTime() < tot).map(doen));
    const legenda = `<div class="pl-legenda klein">` +
      Object.keys(DOEN).filter((k) => gezien.has(k)).map((k) => `<span><i style="background:${DOEN[k].kleur}"></i>${DOEN[k].label.toLowerCase()}</span>`).join("") +
      `</div>`;
    const strip = n
      ? `<div class="strip" role="img" aria-label="Wat de accu doet tot ${esc(eindKlok(new Date(tot)))}">${segs.join("")}</div>` +
        `<div class="strip-x" aria-hidden="true">${labels}</div>${legenda}`
      : `<div class="sub">Nog geen kwartierplanning.</div>`;

    // Een regel: het eerstvolgende netladen en wat de accu vandaag scheelt
    const i = rijen.findIndex((r, j) => modus(r.modus).k === "laden" && tijden[j].getTime() + 15 * 60000 > nu);
    const bes = this._s("besparing");
    const kosten = num(attr(bes, "werkelijke_kosten_vandaag_eur"));
    const zonder = num(attr(bes, "tegenfeitelijke_kosten_vandaag_eur"));
    const regel = [
      i >= 0 ? `Netladen <b>${dagLabel(tijden[i])}${klok(tijden[i])}</b>` : "Geen netladen gepland",
      // v5.216.0 (Ruud 11-11, punt 1): hetzelfde bedrag als de tegel Besparing - met wat
      // er nog in de accu zit. Het kale verschil (zonder - kosten) las op een dag met
      // een volle accu als "de accu kost vandaag geld".
      bruikbaar(bes) && getal(bes) != null
        ? `<span title="Afgerekend ${kosten != null && zonder != null ? euroTeken(zonder - kosten) : STREEP} plus de waarde van wat er extra in de accu zit">accu ${getal(bes) < 0 ? "kost" : "levert"} vandaag <b>${euroTeken(getal(bes))}</b>${getal(bes) < 0 ? "" : " op"} tegen geen accu</span>`
        : kosten != null && zonder != null ? `accu scheelt vandaag <b>${euroTeken(zonder - kosten)}</b> tegen geen accu` : "",
    ].filter(Boolean).join(PUNT);

    return (
      `<div class="tegel">` +
      kop + `<div class="regels-k">${strip}</div>` +
      this._planvolgingRegel() +
      `<div class="regels-k">` + this._laadplanRegel() +
      `<div class="sub">${regel}</div></div>` +
      `</div>`
    );
  }

  /* Wat de stroom in de accu kostte (v5.145.0) */
  _accuPrijsRegel() {
    const s = this._s("accuprijs");
    const kas = num(attr(s, "kasprijs_eur_per_kwh"));
    const kost = num(attr(s, "cost_basis_eur_per_kwh"));
    if (kas == null && kost == null) return "";
    const ct = (v) => (v == null ? STREEP : `${Math.round(v * 100)} ct`);
    // v5.147.0: tot de eerste lading een schatting
    const geschat = attr(s, "kasprijs_geschat") === true;
    const uitleg = "Betaald: wat de stroom in de accu werkelijk kostte (net tegen de kwartierprijs, zon gratis, incl. laadverlies). " +
      "EMS: waar het EMS mee rekent, op dezelfde grondslag als het plan: zon telt als gemiste teruglevering; tijdens de saldering met jaaroverschot zonder belastingdeel, vanaf 2027 tegen de terugleverwaarde.";
    const extra = geschat ? " Nog een schatting: na de eerste lading wordt de betaalde prijs echt bijgehouden." : "";
    return `<div class="s rest" title="${uitleg}${extra}">in accu ${geschat ? "\u2248" : ""}${ct(kas)} betaald${PUNT}EMS ${ct(kost)}</div>`;
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
    const pv = attr(this._s("plan"), "planvolging") || {};
    // v5.181.1 (punt 7): 'nu' van de cockpitsensor - elke ronde, uit dezelfde
    // opname als de tegel "Accu nu"; de kwartierplanning schrijft trager.
    const ems = attr(this._s("cockpit"), "planvolging_nu");
    // v5.181.1 (punt 8): gemeten = live uit de bronnen, gepland = EMS-ronde
    const nu = planvolgingLive(ems && ems.beschikbaar ? ems : pv.nu, this._live());
    if (!nu || !nu.beschikbaar) return "";
    // v5.181.2 (c): stuurt het EMS niet, dan geen oordeel
    const hand = !!nu.niet_gestuurd;
    const kl = hand ? "" : nu.status === "volgens plan" ? "ok" : nu.status === "verklaard" ? "" : "let";
    // v5.93.2: "andere keuze" als de sturing iets anders koos dan het plan
    const label = hand ? "handmatig" : nu.status === "volgens plan" ? "volgens plan" : nu.status === "verklaard" ? "verklaard"
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
      `<div class="pvkop">` + chip(label, kl) +
      `<div class="zinpv">${esc(nu.tekst || "")}</div></div>` +
      `<div class="rk">Accu</div>` +
      `<div class="rij3">` +
      `<div class="${accuK(nu.gepland_accu_w)}"><div class="l">Gepland</div><div class="w">${rw(nu.gepland_accu_w)}</div></div>` +
      `<div class="${accuK(nu.gemeten_accu_w)}"><div class="l">Gemeten nu</div><div class="w">${rw(nu.gemeten_accu_w)}</div></div>` +
      `<div class="${accuK(verschil)}"><div class="l">Verschil</div><div class="w">${verschil == null ? STREEP : watt(Math.abs(verschil))}</div>` +
      `<div class="s">${hand ? "EMS stuurt niet" : nu.verschil_tekst ? esc(nu.verschil_tekst === "geen" ? "vrijwel gelijk" : nu.verschil_tekst)
        : verschil == null || num(nu.gepland_accu_w) == null || num(nu.gemeten_accu_w) == null ? "geen"
        : esc(verschilTekst(num(nu.gepland_accu_w), num(nu.gemeten_accu_w)))}</div></div>` +
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
    // v5.215.0: "30 W geen" las als een fout; onder 50 W heet het "vrijwel gelijk".
    const ruwTekst = nu.zon_verschil_tekst || (d == null ? "onbekend" : Math.abs(d) < 50 ? "geen" : d > 0 ? "meer zon" : "minder zon");
    const tekst = ruwTekst === "geen" ? "vrijwel gelijk" : ruwTekst;
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

  /* ---- prijs en lading ---- */

  /* v5.178.0: gekozen tabblad, onthouden per browser. */
  _tab() {
    if (this._tabKeuze == null) {
      let t = null;
      try { t = localStorage.getItem("ems-cockpit-tab"); } catch (e) { t = null; }
      this._tabKeuze = TABS.some(([k]) => k === t) ? t : "prijzen";
    }
    return this._tabKeuze;
  }

  _planning() {
    const rijen = this._planRijen().filter((r) => num(r.prijs_ct) != null);
    const tijden = planTijden(rijen);
    const kw = attr(this._s("prijsverwachting"), "kwartieren");
    const heeft = {
      prijzen: rijen.length > 0,
      week: !!(kw && Array.isArray(kw.ct) && kw.ct.length > 1),
    };
    let tab = this._tab();
    if (!heeft[tab]) tab = (TABS.find(([k]) => heeft[k]) || ["prijzen"])[0];
    const knoppen =
      `<div class="tabs" role="tablist" aria-label="Periode">` +
      TABS.map(([k, naam]) =>
        `<button type="button" role="tab" data-tab="${k}" aria-selected="${k === tab}" aria-pressed="${k === tab}"` +
        `${heeft[k] ? "" : ` disabled title="Geen gegevens"`}>${naam}</button>`
      ).join("") +
      `</div>`;
    const kop = paneelKop("grafiek", "Prijs en lading", knoppen, "detail-planning");

    // Prijzen: alle bekende kwartieren met de Vooruitblik eronder. 7 dagen: de
    // prijsverwachting met hoe goed die is.
    let lichaam;
    if (tab === "week" && heeft.week) lichaam = this._week();
    else {
      lichaam = heeft.prijzen
        ? this._planGrafiek(rijen, tijden)
        : `<div class="sub">Nog geen kwartierplanning.</div>`;
      if (rijen.length) lichaam += this._vooruitblik(rijen, tijden);
    }

    const drempel = num(attr(this._s("uitleg"), "expensive_price_threshold"));
    const uitleg =
      `<div class="meternoot">Prijzen: alle bekende kwartierprijzen (morgen zodra die bekend zijn); staaf = prijs per kwartier (ct/kWh) in de kleur van wat de accu dan doet; ` +
      `witte lijn = verwachte accustand, geel = verwachte zon${drempel != null ? `, stippellijn = drempel voor duur (${ct(drempel)} ct)` : ""}. ` +
      `7 dagen: vol = bekend, in de kleur van het plan; licht = verwachting, gekleurd naar de dagregel ` +
      `(goedkoopste deel = laden, boven de drempel voor duur = verkopen). Alleen meten.</div>`;
    return kop + `<div class="pb">${lichaam}${this._uitklap("grafiekuitleg", "Uitleg bij de grafiek", uitleg)}</div>`;
  }

  /* De grafiek van een dag: prijs per kwartier, accustand en zon. */
  _planGrafiek(rijen, tijden) {
    const prijzen = rijen.map((r) => num(r.prijs_ct));
    const pMax = Math.max(...prijzen, 1);
    const pMin = Math.min(0, ...prijzen);
    // v5.215.0: veelvouden van 20 ct, zodat de vier aslijnen ronde getallen
    // tonen (was 70/53/35/18).
    const top = Math.ceil(pMax / 20) * 20;
    const bodem = pMin < 0 ? Math.floor(pMin / 20) * 20 : 0;
    const bereik = Math.max(top - bodem, 1);
    const n = rijen.length;
    const gezien = new Set();

    const staven = rijen
      .map((r, i) => {
        const m = modus(r.modus);
        // v5.214.1 (Ruud 11-11 12:57): de staaf van het lopende kwartier stond op
        // "rust" (plan 2 W) terwijl de Vooruitblik "Huis voeden" zei (gemeten
        // 0,5 kW). Nu allebei het gemeten vermogen.
        const t0 = tijden[i].getTime();
        const lopend = t0 <= Date.now() && t0 + 15 * 60000 > Date.now();
        const dk = doen(lopend ? this._rijNu(r) : r);
        gezien.add(dk);
        const h = ((prijzen[i] - bodem) / bereik) * 100;
        const tip =
          `${dagLabel(tijden[i])}${r.van} \u00b7 ${fmt(prijzen[i], 1)} ct \u00b7 ${DOEN[dk].label} (${m.label})` +
          (num(r.soc_procent) != null ? ` \u00b7 accu ${fmt(r.soc_procent)}%` : "") +
          (num(r.zon_kwh) ? ` \u00b7 zon ${fmt(r.zon_kwh, 2)} kWh` : "") +
          (r.tekort ? " \u00b7 tekort" : "");
        const glans = dk === "verkopen" ? " verkopen" : dk === "net" ? " laden" : "";
        return `<div class="staaf${glans}${r.tekort ? " tekort" : ""}" style="height:${Math.max(2, h).toFixed(1)}%;background:${DOEN[dk].kleur}" title="${esc(tip)}"></div>`;
      })
      .join("");

    // Laadstand als lijn, zon als vlak (0..100 in beide richtingen)
    const x = (i) => ((i + 0.5) / n) * 100;
    // v5.181.1 (punt 8): de lijn begint op de nu-lijn bij de live laadstand
    // (04-11 10:56: ~19 % bij "nu" terwijl de accu op ~31 % stond).
    const t0 = tijden[0].getTime();
    const tEind = tijden[n - 1].getTime() + 15 * 60000;
    const nuX = ((Date.now() - t0) / (tEind - t0)) * 100;
    const socLive = getal(this._s("soc"));
    // v5.181.2 (b): soc_procent is de stand aan het EIND van het kwartier.
    // De lijn begint bij "nu" op de live laadstand; het verschil met het plan
    // loopt in drie uur weg (`socLijn`). Daarvoor kwam het eerste punt uit
    // het plan (04-11 11:31: ~20 % bij een accu van 35 %).
    const tX = (t) => ((t - t0) / (tEind - t0)) * 100;
    const ruw = rijen.map((r, i) => ({ t: tijden[i].getTime() + 15 * 60000, soc: num(r.soc_procent) }));
    const lijn = socLive != null && nuX >= 0 && nuX <= 100 ? socLijn(ruw, Date.now(), socLive) : ruw.filter((q) => q.soc != null);
    const socPunten = lijn.map((q) => `${Math.max(0, Math.min(100, tX(q.t))).toFixed(2)},${(100 - q.soc).toFixed(2)}`).join(" ");
    // v5.215.0: de zon als vermogen (zon_w). zon_kwh van het lopende kwartier is
    // alleen het restant, waardoor het vlak bij "nu" naar nul dook; en het vlak
    // begint bij het eerste kwartier in plaats van schuin vanuit de hoek.
    const zonW = (r) => (num(r.zon_w) != null ? Math.max(0, num(r.zon_w)) : (num(r.zon_kwh) || 0) * 4000);
    const zonMax = Math.max(200, ...rijen.map(zonW));
    const zonPunten =
      `${x(0).toFixed(2)},100 ` +
      rijen.map((r, i) => `${x(i).toFixed(2)},${(100 - (zonW(r) / zonMax) * 45).toFixed(2)}`).join(" ") +
      ` ${x(n - 1).toFixed(2)},100`;
    const drempel = num(attr(this._s("uitleg"), "expensive_price_threshold"));
    const drempelY = drempel != null ? 100 - ((drempel * 100 - bodem) / bereik) * 100 : null;
    // v5.183.1: de ondergrens van de accu (leeg = deze laadstand, niet 0 %).
    const vloer = num((rijen[0] || {}).ondergrens_procent);
    const vloerLijn = vloer != null && vloer > 0 && vloer < 100
      ? `<line class="vloer" x1="0" x2="100" y1="${(100 - vloer).toFixed(2)}" y2="${(100 - vloer).toFixed(2)}"/>` : "";
    const svg =
      `<svg class="g-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">` +
      `<polygon class="zon-vlak" points="${zonPunten}"/>` +
      (drempelY != null && drempelY > 0 && drempelY < 100 ? `<line class="drempel" x1="0" x2="100" y1="${drempelY.toFixed(2)}" y2="${drempelY.toFixed(2)}"/>` : "") +
      vloerLijn +
      (socPunten ? `<polyline class="soc-lijn" points="${socPunten}"/>` : "") +
      `</svg>`;

    // Nu-lijn
    const eerste = tijden[0].getTime();
    const laatste = tijden[n - 1].getTime() + 15 * 60000;
    const nuDeel = (Date.now() - eerste) / (laatste - eerste);
    const nuLijn = nuDeel >= 0 && nuDeel <= 1 ? `<div class="nu-lijn" style="left:${(nuDeel * 100).toFixed(2)}%"><span>nu</span></div>` : "";

    // Assen
    const yLab = [0, 0.25, 0.5, 0.75, 1]
      .map((f) => `<span style="top:${((1 - f) * 100).toFixed(1)}%">${fmt(bodem + f * bereik)}</span>`)
      .join("");
    const yRaster = [0.25, 0.5, 0.75].map((f) => `<div class="g-raster" style="top:${((1 - f) * 100).toFixed(1)}%"></div>`).join("");
    const y2Lab = [0, 50, 100].map((v) => `<span style="top:${(100 - v).toFixed(1)}%">${v}%</span>`).join("");
    const xLab = [];
    const stap = n > 72 ? 4 : n > 40 ? 3 : 2;
    for (let i = 0; i < n; i++) {
      const d = tijden[i];
      if (d.getMinutes() !== 0) continue;
      const uur = d.getHours();
      if (uur % stap === 0 && x(i) > 3 && x(i) < 97) xLab.push(`<span style="left:${x(i).toFixed(2)}%">${String(uur).padStart(2, "0")}:00</span>`);
    }
    const legenda =
      `<div class="pl-legenda">` +
      Object.keys(DOEN).filter((k) => gezien.has(k))
        .map((k) => `<span><i style="background:${DOEN[k].kleur}"></i>${DOEN[k].label.toLowerCase()}</span>`).join("") +
      `<span><i class="lijn-i" style="background:var(--tekst)"></i>accu %</span>` +
      (vloer != null ? `<span><i class="lijn-i" style="background:var(--tekst3)"></i>leeg (${fmt(vloer)} %)</span>` : "") +
      `<span><i style="background:rgba(214,166,79,.45)"></i>zon</span></div>`;
    // v5.181.2 (d): de eenheden boven de assen
    return (
      `<div class="g-eenheid" aria-hidden="true"><span>ct/kWh</span><span>accu %</span></div>` +
      `<div class="gwrap">` +
      `<div class="g-y">${yLab}</div>` +
      `<div class="g-plot">${yRaster}<div class="staven">${staven}</div>${svg}${nuLijn}</div>` +
      `<div class="g-y2">${y2Lab}</div>` +
      `<div class="g-x">${xLab.join("")}</div>` +
      `</div>` + legenda
    );
  }

  /* Het tabblad 7 dagen: de prijsverwachting een week vooruit, en hoe goed die is. */
  _week() {
    const s = this._s("prijsverwachting");
    const regel = [attr(s, "kaart_primair"), attr(s, "kaart_secundair")].filter(Boolean).map(esc).join(PUNT);
    return (regel ? `<div class="za-s">${regel}</div>` : "") + this._prijsGrafiek() + this._prijsKwaliteit() + "";
  }

  /* v5.146.1: gekozen horizon, onthouden per browser. */
  _vooruitUren() {
    if (this._vbUren == null) {
      let u = null;
      try { u = parseInt(localStorage.getItem("ems-vooruitblik-uren"), 10); } catch (e) { u = null; }
      this._vbUren = VB_HORIZONNEN.includes(u) ? u : VB_STANDAARD_UREN;
    }
    return this._vbUren;
  }

  /* v5.146.1: de komende kwartieren samengevoegd tot blokken met dezelfde verwachte status. */
  _vooruitBlokken(rijen, tijden, uren, socNu) {
    const tot = Date.now() + uren * 3600000;
    const blokken = [];
    let vorigeSoc = socNu;
    rijen.forEach((r, i) => {
      const t0 = tijden[i].getTime();
      if (t0 + 15 * 60000 <= Date.now() || t0 >= tot) {
        vorigeSoc = num(r.soc_procent) != null ? num(r.soc_procent) : vorigeSoc;
        return;
      }
      // v5.181.2 (a): gegroepeerd op de weergave per kwartier (staaf en tijdlijn)
      // v5.181.4: het lopende kwartier met het gemeten vermogen, net als de tegel.
      const lopend = t0 <= Date.now();
      const m = kwartierWeergave(lopend ? this._rijNu(r) : r);
      let b = blokken[blokken.length - 1];
      if (!b || b.k !== m.k) {
        b = { k: m.k, label: DOEN[m.k].label, kleur: m.kleur, start: tijden[i], eind: null,
              socBegin: vorigeSoc, socEind: null, accu: [], net: [], prijzen: [], tekort: false };
        blokken.push(b);
      }
      b.eind = new Date(t0 + 15 * 60000);
      if (num(r.soc_procent) != null) { b.socEind = num(r.soc_procent); vorigeSoc = num(r.soc_procent); }
      if (num(r.accu_w) != null) b.accu.push(num(r.accu_w));
      if (num(r.net_w) != null) b.net.push(num(r.net_w));
      if (num(r.prijs_ct) != null) b.prijzen.push(num(r.prijs_ct) / 100);
      if (r.tekort) b.tekort = true;
    });
    return blokken;
  }

  _vooruitblik(rijen, tijden) {
    if (!rijen.length) return "";
    const uren = this._vooruitUren();
    const blokken = this._vooruitBlokken(rijen, tijden, uren, getal(this._s("soc")));
    const hhmm = (d) => `${dagLabel(d)}${d.toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" })}`;
    const eur = (v) => `${EURO}\u00a0${fmt(v, 2)}`;
    const vermogen = (lijst, b) => {
      // v5.179.1: bij zon terugleveren staat de accu stil; toon wat er het net op gaat.
      if (b && b.k === "terug" && b.net.length) {
        const terug = -b.net.reduce((a, v) => a + v, 0) / b.net.length;
        if (terug >= 50) return `levert ${fmt(terug / 1000, 1)} kW terug`;
      }
      if (!lijst.length) return STREEP;
      const gem = lijst.reduce((a, v) => a + v, 0) / lijst.length;
      if (Math.abs(gem) < 50) return "in rust";
      // v5.204.0 (Ruud 10-11: "1.6 kW in de planning, 1.27 kW gepland"):
      // het blok is een gemiddelde van kwartieren met 1,2 en 2,0 kW. Wisselt
      // het vermogen binnen het blok, dan het bereik in plaats van het
      // gemiddelde, zodat het kwartier van nu er altijd binnen valt.
      const zelfde = lijst.filter((v) => (gem < 0 ? v < -50 : v > 50)).map((v) => Math.abs(v));
      const lo = zelfde.length ? Math.min(...zelfde) : Math.abs(gem);
      const hi = zelfde.length ? Math.max(...zelfde) : Math.abs(gem);
      const kw = hi - lo >= 300 ? `${fmt(lo / 1000, 1)}\u2013${fmt(hi / 1000, 1)}` : fmt(Math.abs(gem) / 1000, 1);
      return `${gem < 0 ? "laadt" : "ontlaadt"} ${kw} kW`;
    };
    const regels = blokken.map((b) => {
      const lo = b.prijzen.length ? Math.min(...b.prijzen) : null;
      const hi = b.prijzen.length ? Math.max(...b.prijzen) : null;
      // v5.216.0 (punt 4): in cent, zoals de rest van de cockpit (was euro: 0,57-0,61).
      const prijs = lo == null ? STREEP : hi - lo < 0.005 ? `${fmt(lo * 100, 0)} ct` : `${fmt(lo * 100, 0)}\u2013${fmt(hi * 100, 0)} ct`;
      const soc = b.socEind == null ? STREEP :
        `<span class="vb-soc"><i style="width:${Math.max(0, Math.min(100, b.socEind))}%;background:${b.kleur}"></i></span>` +
        `${b.socBegin != null ? fmt(b.socBegin) + "\u2192" : ""}${fmt(b.socEind)}%`;
      const nu = b.start.getTime() <= Date.now();
      return (
        `<tr class="${nu ? "nu" : ""}"><td>${esc(hhmm(b.start))}\u2013${esc(b.eind.toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" }))}</td>` +
        `<td><span class="modus" style="--kleur:${b.kleur}"><i></i>${esc(b.label)}</span>${nu ? ` <span class="vb-nu">nu</span>` : ""}${b.tekort ? ` <b title="accu leeg, huis aan het net">!</b>` : ""}</td>` +
        `<td class="vb-socc">${soc}</td><td class="r">${vermogen(b.accu, b)}</td><td class="r">${prijs}</td></tr>`
      );
    }).join("");
    const knoppen = VB_HORIZONNEN.map((u) =>
      `<button data-horizon="${u}" class="${u === uren ? "actief" : ""}">${u}u</button>`).join("");
    const kopregel = `<div class="vb-kop"><b>Vooruitblik</b><span class="vb-knoppen">${knoppen}</span>` +
      `<span class="vb-bereik">${blokken.length} ${blokken.length === 1 ? "blok" : "blokken"} in de komende ${uren} uur</span></div>`;
    const tabel = blokken.length
      ? `<div class="tabelvak"><table class="tabel vb"><thead><tr><th>Tijd</th><th>Verwacht</th><th>Accu</th>` +
        `<th class="r">Vermogen</th><th class="r">Prijs</th></tr></thead><tbody>${regels}</tbody></table></div>`
      : `<div class="leegmelding">Geen planning voor de komende ${uren} uur.</div>`;
    return `<div class="vb-vak">${kopregel}${tabel}${this._vooruitSamenvatting(rijen, tijden)}</div>`;
  }

  /* v5.146.0: het eerstvolgende laden en verkopen, in woorden. */
  _vooruitSamenvatting(rijen, tijden) {
    const hhmm = (d) => d.toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" });
    const eerst = (k) => {
      const i = rijen.findIndex((r, j) => modus(r.modus).k === k && tijden[j].getTime() + 15 * 60000 > Date.now());
      if (i < 0) return "niet in de planning";
      const p = num(rijen[i].prijs_ct);
      return `${esc(dagLabel(tijden[i]))}${hhmm(tijden[i])}${p != null ? ` bij ${EURO}\u00a0${fmt(p / 100, 3)}/kWh` : ""}`;
    };
    return `<div class="vb-samen"><b>Eerstvolgende laden van net:</b> ${eerst("laden")}${PUNT}<b>verkopen:</b> ${eerst("verkopen")}.</div>`;
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
      (w.reden ? ` \u00b7 reden: ${esc(w.reden)}` : "") +
      `</div>`
    );
  }

  /* ---- zon, verkopen en reserve (v5.178: een paneel) ---- */

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
    const zon = this._gacs("zon_vandaag");
    const verwacht = num(zon.voorspeld_kwh) ?? getal(this._s("zon_vandaag"));
    const opgewekt = num(zon.opgewekt_kwh) ?? getal(this._s("zon_werkelijk"));
    const rest = getal(this._s("zon_rest"));
    // v5.198.1: de eigen rest (waar het plan mee rekent) en opgewekt + rest
    const zonRest = num(zon.rest_kwh);
    const verwachtNu = num(zon.verwacht_nu_kwh);
    const planRijen = attr(this._s("plan"), "kwartierplanning") || [];
    const verkoopRij = Array.isArray(planRijen) ? planRijen.find((r) => /verkopen/.test(String(r.modus || ""))) : null;
    const morgen = getal(this._s("zon_morgen"));
    const pv = getal(this._s("pv"));
    const nauw = getal(this._s("pvNauw"));
    const bew = this._s("bewolking");
    const uitstel = this._gacs("zon_uitstelplan");
    const zonDeel = verwacht ? Math.min(1, (opgewekt || 0) / verwacht) : 0;
    const onderdelen = Array.isArray(marge.onderdelen) ? marge.onderdelen : [];
    const totaal = num(marge.totaal_procent);
    const kans = getal(mc);
    const kansKleur = kans == null ? "" : kans >= 50 ? "var(--rood)" : kans >= 20 ? "var(--oranje)" : "var(--groen)";
    const kwh = (v, dec = 2) => (v == null ? STREEP : `${fmt(v, dec)}<small>kWh</small>`);

    // v5.216.0: uit het plan - de waarde van de lading, wat er verkocht wordt en wanneer de accu leeg is
    const wpNu = (attr(this._s("uitleg"), "waardeplan") || {}).nu || {};
    const waardeLading = num(wpNu.waarde_inhoud_eur_per_kwh);
    const wpRijen = this._planRijen();
    const wpTijd = planTijden(wpRijen);
    const verkoopKwh = wpRijen.reduce((som, r, i) =>
      som + (modus(r.modus).k === "verkopen" && wpTijd[i].getTime() + 15 * 60000 > Date.now() ? Math.max(0, num(r.accu_w) || 0) / 4000 : 0), 0);
    const leegI = wpRijen.findIndex((r, i) => r.tekort && wpTijd[i].getTime() + 15 * 60000 > Date.now());
    const leegOm = leegI >= 0 ? `${dagLabel(wpTijd[leegI])}${klok(wpTijd[leegI])}` : null;
    const pauze = bruikbaar(this._s("verkoop_pauze")) && this._s("verkoop_pauze").state === "on";
    // v5.198.1: het waardeplan beslist over verkopen; de oude verkooptoets niet meer
    const verkoopt = verkoopRij ? `verkoopt ${verkoopRij.van || ""}`.trim() : (mag ? "verkopen mag" : "geen verkoop gepland");
    const rechts = chip(verkoopt, verkoopRij || mag ? "ok" : "") +
      (pv != null ? chip(`${watt(Math.max(0, pv))} zon nu`, pv > 20 ? "ok" : "") : "");
    // v5.178.0: zon en verkopen in een raster van negen getallen
    const cijfers =
      `<div class="trio vast">` +
      mini("Zon vandaag", kwh(opgewekt, 1),
        verwachtNu != null ? `van ${fmt(verwachtNu, 1)} kWh${verwacht != null ? " \u00b7 vanochtend " + fmt(verwacht, 1) : ""}` : `van ${fmt(verwacht, 1)} kWh`,
        "var(--amber)") +
      mini("Nog te komen", kwh(zonRest ?? rest, 1), zonRest != null && rest != null ? `vandaag \u00b7 Solcast ${fmt(rest, 1)}` : "vandaag") +
      mini("Morgen", kwh(morgen, 1), "voorspeld") +
      // v5.216.0 (Ruud 11-11, punt 2): de reserve stuurt het verkopen niet meer (v5.198);
      // hier staat nu wat het plan wel gebruikt.
      mini("Waarde lading", waardeLading == null ? STREEP : `${fmt(waardeLading * 100, 1)}<small>ct/kWh</small>`, /^marginaal/.test(String((attr(this._s("uitleg"), "waardeplan") || {}).rekenbasis || "")) ? "volgens het plan, zonder belastingdeel" : "wat het plan een kWh in de accu waard vindt") +
      (blokLoopt
        ? mini("Tot het blok", "nu", `laadblok loopt${blokLoopt.eind ? " tot " + blokLoopt.eind : ""}`) +
          mini("Na het blok", STREEP, "volgend blok nog niet bepaald")
        : mini("Tot het blok", kwh(tot), "huis tot het blok") +
          mini("Na het blok", kwh(na), "laadt het blok bij")) +
      mini("Verkoop gepland", `${fmt(verkoopKwh, 1)}<small>kWh</small>`, pauze ? "verkopen staat uit (knop)" : verkoopKwh > 0 ? "uit de accu, in het plan" : "niets in het plan") +
      mini("Kans op tekort", kans == null ? STREEP : `${fmt(kans)}<small>%</small>`, "tot het blok", kansKleur) +
      mini("Accu leeg om", leegOm || "niet", leegOm ? "volgens het plan" : "binnen het plan") +
      `</div>`;
    const tekortNu = num(attr(tekort, "tekortnacht_tot_nu_kwh"));
    const regels =
      `<div class="rijen vrij">` +
      `<span>Bewolking <b>${bruikbaar(bew) ? `${fmt(getal(bew))}%${attr(bew, "label") ? PUNT + esc(attr(bew, "label")) : ""}` : STREEP}</b></span>` +
      (nauw != null ? `<span>Zonvoorspelling gisteren <b>${fmtTeken(nauw, 1)}%</b></span>` : "") +
      `<span>Tekortnachten 7 dagen <b>${fmt(getal(tekort))}${tekortNu ? `${PUNT}deze nacht ${fmt(tekortNu, 2)} kWh` : ""}</b></span>` +
      (uitstel.reden ? `<span>Zon opvangen uitstellen <b>${uitstel.uitstellen ? "ja" : "nee"}</b></span>` : "") +
      `</div>`;

    const meter =
      besch != null && nodig != null
        ? `<div class="meterrij"><div class="meterkop"><span class="lbl">Beschikbaar tegen nodig voor het huis</span>` +
          `<span class="w">${fmt(besch, 2)} / ${fmt(nodig, 2)}<small>kWh</small></span></div>` +
          balk(nodig > 0 ? besch / Math.max(besch, nodig) : 1, mag ? "var(--groen)" : "var(--blauw)", nodig > 0 ? nodig / Math.max(besch, nodig) : null) +
          `<div class="meternoot">Het witte streepje is wat het huis tot het blok nodig heeft. Sinds v5.198 verkoopt het EMS ook daaronder als terugkopen goedkoper is.</div></div>`
        : "";
    const zonMeter =
      `<div class="meterrij"><div class="meterkop"><span class="lbl">Zon vandaag opgewekt</span><span class="w">${fmt(opgewekt, 1)} / ${fmt(verwachtNu ?? verwacht, 1)}<small>kWh</small></span></div>` +
      balk(verwachtNu ? Math.min(1, (opgewekt || 0) / verwachtNu) : zonDeel, "var(--amber)") + `</div>`;
    // Alleen de uitleg in tekst gaat in de uitklap
    const uitleg =
      (toets.reden ? `<div class="zin">${esc(toets.reden)}</div>` : "") +
      meter + zonMeter +
      (kans != null ? `<div class="meternoot">Kans op tekort: Monte Carlo over verbruik en zon, tot het volgende goedkope blok.</div>` : "") +
      (uitstel.reden ? `<div class="zin"><b>Zon opvangen uitstellen: ${uitstel.uitstellen ? "ja" : "nee"}.</b> ${esc(uitstel.reden)}</div>` : "");
    return paneelKop("schild", "Zon, verkopen en reserve", rechts, "detail-reservemarge") +
      `<div class="pb">${cijfers}${regels}${this._uitklap("zon_reserve", "Uitleg reserve en zon", `<div class="lijst">${uitleg}</div>`)}</div>`;
  }

  /* ---- accumodules ---- */

  _modules() {
    const mods = attr(this._s("modules"), "modules");
    const koeling = this._s("koeling");
    const gez = this._s("accuGezondheid");
    const rend = getal(this._s("rendement"));
    // v5.178.0: koeling als chip in de kop
    const koelAan = !!attr(koeling, "ventilator_aan");
    const rechts = [
      bruikbaar(koeling)
        ? `<span class="chip ${koelAan ? "ok" : ""}">${icoon("ventilator")}koeling ${koelAan ? "aan" : "uit"}` +
          `${num(attr(koeling, "accu_c")) != null ? `${PUNT}omvormer ${fmt(attr(koeling, "accu_c"))}${GRAAD}C` : ""}</span>`
        : "",
      rend != null ? chip(`rendement ${fmt(rend, 1)}%`) : "",
      bruikbaar(gez) ? chip(`${fmt(getal(gez))} cycli`) : "",
    ].join("");
    if (!Array.isArray(mods) || !mods.length) {
      // v5.178.1: net na een herstart is de lijst nog leeg tot de eerste
      // EMS-ronde met de modulesensoren; dat is geen ontbrekende module.
      const s = this._s("modules");
      const sinds = s ? Date.parse(s.last_changed || "") : NaN;
      const start = s && (Date.now() - sinds < 10 * 60000 || attr(this._s("status"), "opstarten"));
      return paneelKop("cellen", "Accumodules", "", "detail-accu") +
        `<div class="pb"><div class="meta">${rechts}</div></div><div class="leegmelding">${start ? "Modulegegevens laden nog (EMS net gestart)." : "Geen modulegegevens."}</div>`;
    }
    const regels = mods.map((m) => {
      // v5.181.1 (punt 8): laadstand en vermogen live uit de modulesensoren
      const i = num(m.module) != null ? num(m.module) - 1 : -1;
      const liveSoc = i >= 0 && this._moduleIds && this._moduleIds[i] ? getal(this._hass.states[this._moduleIds[i]]) : null;
      const liveW = i >= 0 && this._moduleWIds && this._moduleWIds[i] ? getal(this._hass.states[this._moduleWIds[i]]) : null;
      if (liveW != null) m = { ...m, vermogen_w: liveW };
      const soc = liveSoc != null ? liveSoc : num(m.soc_percent);
      const laag = num(m.cel_min_v) != null && num(m.cel_min_v) < 3.0;
      const drift = Array.isArray(m.drift_op) && m.drift_op.length;
      const zwak = drift || laag;
      // v5.179: accu = violet; alleen een afwijkende module krijgt oranje
      const kleur = zwak ? "var(--oranje)" : "var(--violet)";
      const mv = Math.round((num(m.cel_delta_v) || 0) * 1000);
      const temp = num(m.temperatuur_c);
      const opval = (tekst, ja) => (ja ? `<b class="hoog">${tekst}</b>` : `<b>${tekst}</b>`);
      // Een regel met alle cijfers; wat afwijkt in oranje
      const cijfers =
        `<span>cel ${opval(`${fmt(m.cel_min_v, 2)}\u2013${fmt(m.cel_max_v, 2)} V`, laag)}</span>` +
        `<span>verschil ${opval(`${fmt(mv)} mV`, mv >= 50)}</span>` +
        `<span>${opval(`${fmt(m.temperatuur_c)}${GRAAD}C`, temp != null && (temp >= 40 || temp <= 5))}</span>` +
        `<span>${opval(`${fmt(m.vermogen_w)} W`, false)}</span>` +
        (drift ? chip("loopt uit de pas", "let") : "") +
        (laag ? chip(`cel ${fmt(m.cel_min_v, 2)} V`, "gevaar") : "") +
        (m.melding_uit ? chip("melding uit", "uit") : "");
      return (
        `<div class="modrij${zwak ? " zwak" : ""}"><b>${esc(m.naam || "Module " + m.module)}</b>${balk((soc || 0) / 100, kleur)}` +
        `<span class="w">${soc == null ? STREEP : fmt(soc) + "<small>%</small>"}</span>` +
        `<div class="module-cijfers">${cijfers}</div></div>`
      );
    }).join("");
    const koel = bruikbaar(koeling) && attr(koeling, "reden")
      ? `<div class="za-s">Koeling ${koelAan ? "aan" : "uit"}: ${esc(attr(koeling, "reden"))}</div>`
      : "";
    return paneelKop("cellen", "Accumodules", "", "detail-accu") +
      `<div class="pb"><div class="meta">${rechts}</div><div class="lijst">${regels}</div>${koel}${this._accukosten()}</div>`;
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
    return this._uitklap("accukosten", `Wat de accu kost en oplevert (40 dagen): net ${euroTeken(net.marge_eur)}`, inhoud);
  }

  /* ---- huis en apparaten ---- */

  _huis() {
    const regel = (ic, naam, sub, waarde, kleur = "") =>
      `<div class="regel"${kleur ? ` style="--rk:${kleur}"` : ""}><div class="ric">${icoon(ic)}</div>` +
      `<div><div class="rn">${esc(naam)}</div>${sub ? `<div class="rs">${sub}</div>` : ""}</div><div class="rw">${waarde}</div></div>`;
    const uit = [];
    // v5.202.2 (Ruud 09-11: "Ook in 1 tegel?"): fietsladers, stofzuiger,
    // batterijlader, vaatwasser en wasmachine in een tegel "Apparaten",
    // een regel per apparaat in zijn eigen kleur; waarde = wat ze samen nu
    // trekken.
    const apparaten = [];
    let samenW = null;
    for (const [sleutel, naam] of [["fietsen", "Fietsladers"], ["stofzuiger", "Steelstofzuiger"],
      ["lader", "Batterijlader keuken"], ["vaatwasser", "Vaatwasser"], ["wasmachine", "Wasmachine"]]) {
      const s = this._s(sleutel);
      if (!s) continue;
      const p = apparaatVermogen(s, this._hass.states);
      if (p != null) samenW = (samenW || 0) + p;
      let t = apparaatTekst(s) + (p != null ? `${PUNT}${vermogenTekst(p)}` : "");
      let k = apparaatKleur(s);
      if (sleutel === "vaatwasser" || sleutel === "wasmachine") {
        // v5.139.0: de planning (start, klaar, programma)
        const voortgang = num(attr(s, "geschatte_voortgang_procent"));
        const plan = this._s(`${sleutel}Plan`);
        const planTekst = plan && !ONBRUIKBAAR.includes(String(plan.state).toLowerCase()) && attr(plan, "status") !== "niets" ? plan.state : "";
        const extra = planTekst || (voortgang != null && voortgang > 0 && voortgang < 100 ? `${fmt(voortgang)}% klaar` : "");
        if (extra) t += `${PUNT}${extra}`;
        if (attr(plan, "status") === "gepland") k = "var(--blauw)";
      }
      apparaten.push(`${esc(naam)}: <span style="color:${k || "inherit"}">${esc(t)}</span>`);
    }
    if (apparaten.length) {
      uit.push(regel("stekker", "Apparaten", apparaten.join("<br>"),
        samenW != null && samenW > 0 ? watt(samenW) : "", ""));
    }
    // v5.202.2 (Ruud 09-11: "Nu 4 airco gerelateerde tegels, kan dit niet
    // in 1?"): Airco, Airco-patroon, Airco nu en Klimaat in een tegel.
    // Waarde: het vermogen nu (anders de binnentemperatuur); regels:
    // temperaturen en warmteadvies, compressor, verwachting, patroon.
    const besluit = this._s("aircoBesluit");
    const klimaat = this._s("klimaat");
    const aw = this._s("airco_w");
    const awW = getal(aw);
    const binnen = getal(this._s("temp_binnen"));
    const buiten = getal(this._s("temp_buiten"));
    if (besluit || klimaat || awW != null) {
      const regels = [];
      const advies = attr(klimaat, "verwarmingsadvies") || {};
      const temps = binnen != null
        ? `${fmt(binnen, 1)}${GRAAD} binnen${buiten != null ? ` / ${fmt(buiten, 1)}${GRAAD} buiten` : ""}`
        : "";
      const warmte = advies.advies
        ? `${advies.advies === "airco" ? "airco" : "cv"} goedkoopst${num(advies.airco_eur_per_kwh_warmte) != null ? ` (${ct(advies.airco_eur_per_kwh_warmte)} tegen ${ct(advies.gas_eur_per_kwh_warmte)} ct/kWh warmte)` : ""}`
        : (attr(besluit, "tekst") || "");
      const r1 = [temps, warmte].filter(Boolean).join(PUNT);
      if (r1) regels.push(esc(r1));
      const hz = num(attr(aw, "frequentie_hz"));
      if (hz != null) {
        const wph = num(attr(aw, "w_per_hz"));
        regels.push(esc((hz > 0 ? `compressor ${fmt(hz)} Hz` : "compressor stil") +
          (wph != null ? `${PUNT}${fmt(wph, 1)} W/Hz ${attr(aw, "omrekening_geleerd") ? "geleerd" : "startwaarde"}` : "")));
      }
      // v5.93.0: verwachting tot het volgende blok en wat de reserve meetelt
      const vw = attr(besluit, "verwachting") || {};
      if (vw.beschikbaar) {
        const res = num(vw.in_reserve_kwh);
        regels.push(esc(`verwacht tot ${vw.tot_tekst || ""}` +
          (vw.basis && vw.basis.tekst ? `${PUNT}${vw.basis.tekst}` : "") +
          (res != null && res > 0 ? `${PUNT}${fmt(res, 2)} kWh in reserve` : vw.verwacht ? "" : `${PUNT}niet verwacht`) +
          (vw.knop_automaat === false ? `${PUNT}knop automaat uit` : "")));
      }
      // v5.101: het geleerde patroon
      const ritme = attr(besluit, "dagritme") || {};
      if (ritme.patroon_tekst) regels.push(esc(ritme.patroon_tekst));
      const waarde = awW != null
        ? watt(awW)
        : `${binnen != null ? fmt(binnen, 1) + GRAAD : STREEP}`;
      uit.push(regel("airco", "Airco", regels.join("<br>"), waarde,
        awW != null && awW > 0 ? "var(--oranje)" : "var(--cyaan)"));
    }
    // v5.135.0: het continu-verbruik, en hoeveel daarvan een eigen meting heeft
    const vk = attr(this._s("sluip"), "verklaring") || {};
    if (vk.beschikbaar) {
      uit.push(regel("stekker", "Continu-verbruik",
        `${fmt(vk.verklaard_w)} W gemeten${PUNT}${fmt(vk.onverklaard_w)} W zonder eigen meting (${fmt(vk.onverklaard_kwh_per_jaar)} kWh/jaar)`,
        watt(vk.huis_vloer_w), "var(--amber)"));
    }
    const water = this._s("water");
    if (water) {
      const liter = num(attr(water, "vandaag_liter"));
      const gem = num(attr(water, "gemiddeld_liter_per_dag"));
      // v5.150.0: wat het water vandaag kost, en de douche.
      const wEur = num(attr(water, "vandaag_eur"));
      uit.push(regel("druppel", "Water",
        (gem != null ? `gemiddeld ${fmt(gem)} L per dag` : "") + (wEur != null ? `${gem != null ? PUNT : ""}${euro(wEur)} vandaag` : ""),
        `${liter == null ? STREEP : fmt(liter) + " L"}`, "var(--blauw)"));
      const dou = attr(water, "douche") || {};
      if (dou.beschikbaar) {
        const lst = dou.laatste || {};
        const lstD = alsDatum(lst.gestart);
        uit.push(regel("druppel", "Douche",
          `gemiddeld ${fmt(dou.gem_minuten, 0)} min${PUNT}${fmt(dou.gem_liter, 0)} L${PUNT}${euro(dou.gem_eur)} per beurt (${fmt(dou.aantal)}\u00d7 in ${fmt(dou.dagen)} d)`,
          lstD ? `${esc(dagLabel(lstD) + klok(lstD))} <span class="leeg">${fmt(lst.duur_minuten, 0)} min${lst.kosten_eur != null ? PUNT + euro(lst.kosten_eur) : ""}</span>` : "",
          "var(--blauw)"));
      }
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
    // v5.178.0: alle regels blijven zichtbaar, in een dichter raster
    return (
      paneelKop("huis", "Huis en apparaten", huis != null ? chip(`${watt(huis)} nu`) : "", "detail-apparaten") +
      (uit.length ? `<div class="pb"><div class="lijst huislijst">${uit.join("")}</div></div>` : `<div class="leegmelding">Geen apparaten ingesteld.</div>`)
    );
  }

  /* ---- geld ---- */

  _geld() {
    const bes = this._s("besparing");
    const per = (attr(this._s("perioden"), "perioden") || {}).perioden || {};
    const week = per.week || {};
    const maand = per.maand || {};
    const vandaag = per.vandaag || {};
    const kosten = num(attr(bes, "werkelijke_kosten_vandaag_eur"));
    const zonder = num(attr(bes, "tegenfeitelijke_kosten_vandaag_eur"));
    const kt = this._s("kostenTotaal");
    const bmaand = num(attr(bes, "besparing_deze_maand_eur"));
    // v5.186.0: het totaal op dezelfde (gecorrigeerde) maat als "deze maand".
    const ball = num(attr(bes, "besparing_totaal_gecorrigeerd_eur")) ?? num(attr(bes, "besparing_all_time_eur"));
    // v5.185.1: netladen deze maand uit de accuboekhouding (inkoop en wat de
    // netlading opleverde toen hij eruit ging). Het oude blok telde alleen
    // ontladen in dure kwartieren (oude regels) en zette de netlading als
    // kosten zonder de opbrengst: deze maand "-0,92" terwijl de marge positief is.
    const nl = (attr(this._s("rendement"), "accukosten") || {}).netladen_maand || {};
    const geladenKwh = num(nl.net_erin_kwh);
    const geladen = num(nl.net_inkoop_eur);
    const netto = num(nl.net_marge_eur);
    const zv = getal(this._s("zelfvoorziening"));
    const kleur = (v) => (v != null && v >= 0 ? "var(--groen)" : "var(--oranje)");
    // v5.186.0: op hoeveel dagen het saldo werkelijk rust.
    // v5.187.3: welke dagen een periode beslaat ("29 okt - 4 nov", "1-4 nov").
    // Gemeld 05-11: week 19,00 en maand 13,75 leek raar; de week liep nog
    // door in oktober, de maand had pas 4 dagen.
    const MND = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"];
    const periodeTekst = (p) => {
      const d = num(p && p.dagen);
      if (!p || !p.van || !d) return "";
      const van = new Date(`${p.van}T12:00:00`);
      if (isNaN(van)) return "";
      const tot = new Date(van.getTime() + (d - 1) * 86400000);
      if (d === 1) return `${van.getDate()} ${MND[van.getMonth()]}`;
      if (van.getMonth() === tot.getMonth()) return `${van.getDate()}\u2013${tot.getDate()} ${MND[tot.getMonth()]}`;
      return `${van.getDate()} ${MND[van.getMonth()]} \u2013 ${tot.getDate()} ${MND[tot.getMonth()]}`;
    };
    const periodeLabel = (naam, p) => {
      const t = periodeTekst(p);
      return t ? `${naam}<i class="bij">${t}</i>` : naam;
    };
    const dagenMet = (p) => {
      const n = (p.dagen_met_waarde || {}).netto_eur;
      return n != null && p.dagen ? ` - ${n} van ${p.dagen} dagen met een saldo` : "";
    };
    // Een regel over de accu zelf: marge per kWh, slijtage en rendement
    const ak = attr(this._s("rendement"), "accukosten") || {};
    const rend = getal(this._s("rendement"));
    const marge = ak.beschikbaar && ak.net ? num(ak.net.marge_ct_per_kwh) : null;
    const accuRegel = [
      marge != null ? `Accu-marge ${fmtTeken(marge, 1)} ct/kWh` : "",
      ak.beschikbaar && num(ak.slijtage_ct) != null ? `slijtage ${fmt(ak.slijtage_ct, 1)} ct` : "",
      rend != null ? `rendement ${fmt(rend)}%` : "",
    ].filter(Boolean).join(PUNT);
    return (
      `<div class="tegel">` +
      paneelKop("euro", "Geld", "", "detail-besparing") +
      `<div class="geld-grid"><div class="rijen geld-r">` +
      // v5.203.0 (Ruud 09-11: "een totaal plaatje voor gas en elektra"):
      // stroom en gas van vandaag inclusief vastrecht, netbeheer en de
      // vermindering energiebelasting (vaste kosten voor de hele dag).
      (kt ? `<span title="${esc(`Stroom ${euro(num(attr(kt, "stroom_variabel_eur")))} + vast ${euro(num(attr(kt, "stroom_vast_eur")))}; gas ${euro(num(attr(kt, "gas_variabel_eur")))} + vast ${euro(num(attr(kt, "gas_vast_eur")))}. Vast: vastrecht en netbeheer min de vermindering energiebelasting, voor de hele dag.`)}">Totaal vandaag <b>${euro(getal(kt))}<i class="bij">stroom ${euro(num(attr(kt, "stroom_eur")))}${PUNT}gas ${euro(num(attr(kt, "gas_eur")))}${PUNT}incl. vast</i></b></span>` : "") +
      `<span data-info="besparing" title="Stroomkosten vandaag tot nu (zonder vaste kosten)">Stroom variabel <b>${euro(kosten)}${zonder != null ? `<i class="bij">zonder accu ${euro(zonder)}</i>` : ""}</b></span>` +
      // v5.105.2: de besparing vergelijkt met een huis ZONDER accu
      `<span title="${esc("t.o.v. zonder accu")}">Besparing deze maand <b style="color:${kleur(bmaand)}">${euroTeken(bmaand)}</b></span>` +
      `<span title="sinds de start">Besparing totaal <b style="color:${kleur(ball)}">${euroTeken(ball)}</b></span>` +
      // v5.185.0: saldo (afname min teruglevering), dezelfde maat als "Vandaag";
      // zonder saldo de afname. Week en maand zijn de afgesloten dagen.
      `<span title="${esc(`Saldo van de laatste 7 afgesloten dagen (afname min teruglevering)${dagenMet(week)}`)}">${periodeLabel("Week", week)} <b>${euro(num(week.netto_eur) ?? num(week.kosten_eur))}<i class="bij">${fmt(week.opwek_kwh, 0)} kWh zon</i></b></span>` +
      `<span title="${esc(`Saldo van de afgesloten dagen deze maand (afname min teruglevering)${dagenMet(maand)}`)}">${periodeLabel("Maand", maand)} <b>${euro(num(maand.netto_eur) ?? num(maand.kosten_eur))}<i class="bij">${fmt(maand.opwek_kwh, 0)} kWh zon</i></b></span>` +
      `<span>Van het net vandaag <b>${fmt(vandaag.import_kwh, 1)} kWh</b></span>` +
      `<span>Zelfvoorzienend <b>${zv == null ? STREEP : fmt(zv) + "%"}</b></span>` +
      `</div><div>` +
      // v5.105.2: alleen wat het EMS ACTIEF doet; het huis voeden in de
      // stand slim zit hier niet in (wel in de besparing hierboven).
      `<div class="za-s geld-kop" title="Laden uit het net deze maand, uit de accuboekhouding">Netladen deze maand:</div>` +
      `<div class="rijen geld-r" title="Wat er deze maand uit het net de accu in ging, wat dat kostte, en de marge op diezelfde ladingen zodra ze eruit gingen (na rendement en slijtage); wat nog in de accu zit telt pas mee als het ontladen is. Zon opslaan en het huis voeden zitten in de besparing hierboven.">` +
      `<span>Uit het net geladen <b>${geladenKwh == null ? STREEP : fmt(geladenKwh, 1) + " kWh"}</b></span>` +
      `<span>Inkoop <b>${euro(geladen)}</b></span>` +
      `<span>Marge op netladen <b style="color:${kleur(netto)}">${euroTeken(netto)}</b></span>` +
      `</div>` +
      this._zelfanalyseRijen() +
      `</div></div>` +
      (accuRegel ? `<div class="sub">${esc(accuRegel)}</div>` : "") +
      this._uitklap("geld_detail", "Toelichting zelfanalyse en archief", this._zelfanalyse()) +
      `</div>`
    );
  }

  /* v5.100: zelfanalyse, repetitie 2027 en dagarchief - het kerngetal
     (kaart_primair) zichtbaar, de toelichting (kaart_secundair) ingeklapt. */
  _zelfanalyseRijen() {
    const regels = [["zelfanalyse", "Zelfanalyse"], ["repetitie", "Na de saldering"], ["dagarchief", "Dagarchief"]]
      .map(([k, naam]) => {
        const s = this._s(k);
        if (!s || !attr(s, "kaart_primair")) return "";
        return `<span>${esc(naam)} <b>${esc(attr(s, "kaart_primair"))}</b></span>`;
      }).join("");
    return regels ? `<div class="rijen geld-r za-blok">${regels}</div>` : "";
  }

  _zelfanalyse() {
    const blokken = [
      ["zelfanalyse", "Zelfanalyse"],
      ["repetitie", "Generale repetitie 2027"],
      ["dagarchief", "Dagarchief"],
    ];
    const regels = blokken.map(([k, naam]) => {
      const s = this._s(k);
      if (!s || !attr(s, "kaart_secundair")) return "";
      // v5.215.0: de toelichting begint soms zelf met de naam ("Zelfanalyse: Zelfanalyse \u00b7 ...").
      const ruw = String(attr(s, "kaart_secundair"));
      const dubbel = `${naam} \u00b7 `;
      return `<div class="za-s"><b>${esc(naam)}:</b> ${esc(ruw.startsWith(dubbel) ? ruw.slice(dubbel.length) : ruw)}</div>`;
    }).join("");
    const gisteren = attr(this._s("zelfanalyse"), "gisteren") || {};
    const keuzes = (gisteren.niet_de_beste || []).slice(0, 3).map(
      (k) => `<li>${esc(k.tekst || "")}${k.oorzaak ? ` <i>\u00b7 door de ${esc(k.oorzaak)}</i>` : ""}</li>`
    ).join("");
    if (!regels && !keuzes) return "";
    return (
      regels +
      (keuzes ? `<div class="za-s" style="margin-top:6px">Achteraf niet de beste (${esc(/^\d{4}-\d{2}-\d{2}$/.test(gisteren.datum || "") ? `${gisteren.datum.slice(8, 10)}-${gisteren.datum.slice(5, 7)}` : gisteren.datum || "")}):</div><ul class="za-l">${keuzes}</ul>` : "")
    );
  }

  /* Uitklapbaar blok dat open blijft over een nieuwe opbouw heen.
     v5.178.0: "standaard" = open zolang er nog niet zelf is gekozen. */
  _uitklap(sleutel, kop, inhoud, standaard = false) {
    if (!inhoud) return "";
    const keuze = this._uitgeklapt && this._uitgeklapt[sleutel];
    const open = keuze == null ? standaard : keuze;
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
      `<div class="g-eenheid" aria-hidden="true"><span>ct/kWh</span></div>` +
      `<div class="pv-wrap">` +
      `<div class="g-y">${yLab}</div>` +
      `<div class="g-plot">${yRaster}` +
      `<svg class="pv-svg" viewBox="0 0 ${n} 100" preserveAspectRatio="none" role="img" aria-label="prijs per kwartier, een week vooruit">${staven}</svg>` +
      `${scheiding}</div>` +
      `<div class="g-x">${xLab.join("")}</div>` +
      `</div>` +
      ""
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

  _knop(k) {
    const s = this._s(k.k);
    const aan = s.state === "on";
    const weg = !bruikbaar(s);
    const bezig = this._bezig.has(k.k);
    return (
      `<button type="button" class="knop${aan ? " aan" : ""}${bezig ? " bezig" : ""}${weg ? " weg" : ""}" data-knop="${k.k}" ` +
      `style="--kk:${k.kl}" aria-pressed="${aan}" title="${esc(k.s + (aan ? " (aan)" : ""))}">` +
      `<span class="kic">${icoon(k.ic)}</span><span class="kn">${esc(k.n)}</span>${aan ? `<span class="aan-t">aan</span>` : ""}</button>`
    );
  }

  _bediening() {
    // v5.178.0: alle knoppen zichtbaar, compact (zonder onderschrift)
    const knoppen = KNOPPEN.filter((k) => this._s(k.k)).map((k) => this._knop(k)).join("");
    return paneelKop("knop", "Bediening") + `<div class="pb"><div class="knoppen">${knoppen}</div></div>`;
  }

  /* ---- voet ---- */

  _voet() {
    const meetlog = this._s("meetlog");
    const gez = this._s("gezondheid");
    const st = this._s("status");
    // v5.173.0: eerst de cockpit zelf (wordt bij elke meting getekend); de
    // systeemstatus schrijft nog alleen bij een echte wijziging.
    const bijgewerkt = attr(this._s("cockpit"), "bijgewerkt") || attr(st, "last_successful_update");
    const links = LINKS.map(([n, p]) => `<button type="button" data-nav="${p}">${esc(n)}</button>`).join("");
    const regel = [
      // v5.216.0 (punt 6): alleen versie, fouten en storingen; de rest staat op de pagina Gezondheid.
      bruikbaar(gez) ? esc(String(gez.state).split(" \u00b7 ").slice(0, 3).join(" \u00b7 ")) : "",
      bijgewerkt ? `Bijgewerkt ${esc(geleden(bijgewerkt) || "")}` : "",
      VERSIE === "onbekend" ? "Cockpit: versie onbekend" : `Cockpit v${esc(VERSIE)}`,
    ].filter(Boolean).join(PUNT);
    return `<nav class="links" aria-label="Detailpagina's">${links}</nav><span class="voetregel">${regel}</span>`;
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

/* v5.188.0 (Ruud 05-11): tabblad Jaarafrekening - betaald tegenover werkelijk,
   stand nu, verwachte jaarafrekening, opbouw, maandreeks en advies. Leest
   sensor ..._jaarafrekening (staat = verwacht saldo, + = terug). */
const JAAR_KAART = "ems-jaarafrekening-card";
const JE = (v, d = 0) => (v == null || isNaN(v)) ? "\u2013" : "\u20ac\u00a0" + Number(Math.abs(v)).toLocaleString("nl-NL", { minimumFractionDigits: d, maximumFractionDigits: d });
const JS_ = (v) => (v == null || isNaN(v)) ? "" : (v < 0 ? "\u2212\u00a0" : "");
const JD = (iso) => { if (!iso) return ""; const d = new Date(iso + "T12:00:00"); return d.toLocaleDateString("nl-NL", { day: "numeric", month: "short", year: "numeric" }); };
const JD2 = (iso) => { if (!iso) return ""; const d = new Date(iso + "T12:00:00"); return d.toLocaleDateString("nl-NL", { day: "numeric", month: "short" }); };
const JESC = (t) => String(t == null ? "" : t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const JAAR_CSS = `
:host { display:block; }
.card { background:#111827; border:1px solid #232b3a; border-radius:16px; padding:18px 20px; color:#e6e8ec; font-family:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif; }
.hd { display:flex; align-items:baseline; justify-content:space-between; gap:12px; flex-wrap:wrap; }
.hd h2 { font-size:15px; font-weight:600; margin:0; }
.hd h2 ha-icon { color:#d6a64f; --mdc-icon-size:18px; margin-right:6px; vertical-align:-3px; }
.hd .r { font-size:12px; color:#9aa3b2; }
.prog { height:5px; background:#1b2231; border-radius:3px; margin:8px 0 16px; overflow:hidden; }
.prog i { display:block; height:100%; background:linear-gradient(90deg,#d6a64f,#e8c47e); }
.hero { display:grid; grid-template-columns:1.3fr 1fr 1fr 1fr; gap:10px; }
.k { background:#0f1521; border:1px solid #232b3a; border-radius:12px; padding:12px 14px; }
.k .l { font-size:11px; color:#9aa3b2; text-transform:uppercase; letter-spacing:.08em; }
.k .v { font-size:24px; font-weight:650; margin-top:4px; font-variant-numeric:tabular-nums; }
.k .s { font-size:11.5px; color:#6b7383; margin-top:3px; }
.k.big { border-color:rgba(79,180,138,.45); background:linear-gradient(160deg,rgba(79,180,138,.12),#0f1521 60%); }
.k.big.min { border-color:rgba(224,101,108,.45); background:linear-gradient(160deg,rgba(224,101,108,.12),#0f1521 60%); }
.k.big .v { font-size:30px; }
.groen { color:#4fb48a; } .rood { color:#e0656c; }
.cols { display:grid; grid-template-columns:1fr 1.25fr; gap:14px; margin-top:14px; }
h3 { font-size:12px; color:#9aa3b2; text-transform:uppercase; letter-spacing:.1em; margin:2px 0 8px; font-weight:600; }
table { width:100%; border-collapse:collapse; font-size:13px; }
td { padding:5px 0; border-bottom:1px dashed #1f2635; } td.n { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
td .m { color:#6b7383; font-size:11.5px; }
tr.t td { border-bottom:none; border-top:1px solid #2b3446; font-weight:650; padding-top:8px; }
.adv { margin-top:14px; display:grid; grid-template-columns:1fr 1fr; gap:10px; }
.a { border:1px solid #232b3a; border-radius:12px; padding:10px 12px; font-size:12.5px; line-height:1.5; color:#9aa3b2; display:flex; gap:10px; }
.a ha-icon { color:#d6a64f; --mdc-icon-size:20px; flex:none; } .a b { color:#e6e8ec; }
.lg { display:flex; gap:14px; font-size:11px; color:#9aa3b2; margin-top:6px; flex-wrap:wrap; }
.lg span::before { content:""; display:inline-block; width:14px; height:3px; border-radius:2px; margin-right:5px; vertical-align:middle; background:var(--c); }
.note { font-size:10.5px; color:#6b7383; margin-top:10px; line-height:1.5; }
.leeg { color:#9aa3b2; font-size:13px; }
@media (max-width:760px) { .hero { grid-template-columns:1fr 1fr; } .cols, .adv { grid-template-columns:1fr; } }
`;

class EmsJaarafrekeningCard extends HTMLElement {
  setConfig(config) { this._config = config || {}; }
  getCardSize() { return 9; }
  set hass(hass) {
    this._hass = hass;
    const id = (this._config && this._config.entity) ||
      Object.keys(hass.states).find((e) => e.startsWith("sensor.") && e.endsWith("energy_management_system_jaarafrekening"));
    const st = id ? hass.states[id] : null;
    const sleutel = st ? st.last_updated : "geen";
    if (sleutel === this._laatst) return;
    this._laatst = sleutel;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>${JAAR_CSS}</style><div class="card">${this._inhoud(st)}</div>`;
  }

  _inhoud(st) {
    const a = st ? st.attributes || {} : {};
    if (!st || a.verwacht_saldo_eur == null) {
      return `<div class="hd"><h2><ha-icon icon="mdi:file-document-check-outline"></ha-icon>Jaarafrekening</h2></div>` +
        `<div class="leeg">Nog geen berekening (${JESC(a.status || "sensor niet gevonden")}). De eerste komt binnen een uur na het opstarten.</div>`;
    }
    return this._kop(a) + this._hero(a) + `<div class="cols"><div>${this._opbouw(a)}</div><div>${this._grafiek(a)}</div></div>` +
      this._advies(a) + this._noot(a);
  }

  _kop(a) {
    const aandeel = Math.max(0, Math.min(1, Number(a.dag_aandeel) || 0));
    return `<div class="hd"><h2><ha-icon icon="mdi:file-document-check-outline"></ha-icon>Jaarafrekening \u00b7 contractjaar ${JD(a.contractjaar_begin)} \u2013 ${JD(a.contractjaar_eind)}</h2>` +
      `<span class="r">maand ${a.maand_nr} van 12</span></div><div class="prog"><i style="width:${(aandeel * 100).toFixed(1)}%"></i></div>`;
  }

  _hero(a) {
    const saldo = Number(a.verwacht_saldo_eur), stand = Number(a.stand_eur);
    const terug = saldo >= 0;
    const laag = Number(a.band_laag_eur), hoog = Number(a.band_hoog_eur);
    const band = `bandbreedte ${JS_(laag)}${JE(laag)} \u2013 ${JS_(hoog)}${JE(hoog)} ${terug ? "terug" : ""}`;
    const volgende = a.volgende_afschrijving ? ` \u00b7 volgende \u00b1 ${JD2(a.volgende_afschrijving)}` : "";
    return `<div class="hero">` +
      `<div class="k big${terug ? "" : " min"}"><div class="l">Verwacht bij jaarafrekening</div><div class="v ${terug ? "groen" : "rood"}">${JE(saldo)} ${terug ? "terug" : "bijbetalen"}</div><div class="s">${band}</div></div>` +
      `<div class="k"><div class="l">Betaald</div><div class="v">${JE(a.betaald_eur)}</div><div class="s">${a.termijnen_betaald} \u00d7 ${JE(a.termijn_eur)}${volgende}</div></div>` +
      `<div class="k"><div class="l">Werkelijk tot nu</div><div class="v">${JS_(a.werkelijk_eur)}${JE(a.werkelijk_eur)}</div><div class="s">stroom + gas + vast \u2212 korting</div></div>` +
      `<div class="k"><div class="l">Stand nu</div><div class="v ${stand >= 0 ? "groen" : "rood"}">${JE(stand)} ${stand >= 0 ? "tegoed" : "tekort"}</div><div class="s">als je vandaag zou afrekenen</div></div>` +
      `</div>`;
  }

  _opbouw(a) {
    const o = a.opbouw || {};
    const rij = (naam, sub, v, neg) => `<tr><td>${naam}<div class="m">${sub}</div></td><td class="n${neg ? " groen" : ""}">${neg ? "\u2212\u00a0" : ""}${JE(v)}</td></tr>`;
    const kwh = (v) => Number(v || 0).toLocaleString("nl-NL", { maximumFractionDigits: 0 });
    const gem = (e, k) => (Number(k) > 0 ? ` \u00b7 gem. ${JE(Number(e) / Number(k), 2)}` : "");
    const totaal = (o.afname_eur || 0) - (o.terug_eur || 0) + (o.gas_eur || 0) + (o.vast_eur || 0) - (o.eb_eur || 0);
    return `<h3>Opbouw tot nu (${JD2(a.contractjaar_begin)} \u2013 gisteren)</h3><table>` +
      rij("Stroom afname", `${kwh(o.afname_kwh)} kWh${gem(o.afname_eur, o.afname_kwh)}`, o.afname_eur, false) +
      rij("Teruglevering", `${kwh(o.terug_kwh)} kWh \u00b7 met saldering`, o.terug_eur, true) +
      rij("Gas", `${Number(o.gas_m3 || 0).toLocaleString("nl-NL", { maximumFractionDigits: 0 })} m\u00b3${gem(o.gas_eur, o.gas_m3)}`, o.gas_eur, false) +
      rij("Vaste kosten", "levering + netbeheer, naar rato", o.vast_eur, false) +
      rij("Vermindering energiebelasting", `${JE((a.aannames || {}).vermindering_eb_jaar, 2)} per jaar, naar rato`, o.eb_eur, true) +
      `<tr class="t"><td>Totaal</td><td class="n">${JS_(totaal)}${JE(totaal)}</td></tr></table>`;
  }

  _grafiek(a) {
    const m = Array.isArray(a.maanden) ? a.maanden : [];
    if (!m.length) return "";
    const W = 470, H = 200, L = 46, R = 460, T = 18, B = 170;
    const top = Math.max(100, ...m.map((r) => Math.max(r.betaald_cum, r.kosten_cum))) * 1.1;
    const bodem = Math.min(0, ...m.map((r) => r.kosten_cum));
    const x = (i) => L + 11 + i * ((R - L - 22) / 11);
    const y = (v) => B - ((v - bodem) / (top - bodem)) * (B - T);
    const lijn = (veld, echt, kleur, dik) => {
      const vast = m.map((r, i) => [i, r]).filter(([, r]) => r[echt]);
      const n = vast.length;
      const p = (lst) => lst.map(([i, r]) => `${x(i).toFixed(1)},${y(r[veld]).toFixed(1)}`).join(" ");
      let s = n ? `<polyline fill="none" stroke="${kleur}" stroke-width="${dik}" points="${p(vast)}"/>` : "";
      const rest = m.map((r, i) => [i, r]).slice(Math.max(0, n - 1));
      if (rest.length > 1) s += `<polyline fill="none" stroke="${kleur}" stroke-width="${dik}" stroke-dasharray="5 5" opacity=".75" points="${p(rest)}"/>`;
      return s;
    };
    const stap = Math.pow(10, Math.floor(Math.log10(top / 3)));
    const grid = [];
    for (let v = Math.ceil(bodem / stap) * stap; v <= top; v += stap * (top / stap > 8 ? 2 : 1)) {
      grid.push(`<line x1="${L}" y1="${y(v).toFixed(1)}" x2="${R}" y2="${y(v).toFixed(1)}" stroke="#1f2635"/>` +
        `<text x="${L - 6}" y="${(y(v) + 3).toFixed(1)}" fill="#6b7383" font-size="10" text-anchor="end">${v < 0 ? "\u2212" : ""}\u20ac ${Math.abs(v)}</text>`);
    }
    const labels = m.map((r, i) => `<text x="${x(i).toFixed(1)}" y="${H - 10}" fill="#6b7383" font-size="10" text-anchor="middle">${JESC(r.maand)}</text>`).join("");
    const eind = m[m.length - 1];
    const saldo = eind.betaald_cum - eind.kosten_cum;
    const pijl = `<line x1="${x(11).toFixed(1)}" y1="${y(eind.betaald_cum).toFixed(1)}" x2="${x(11).toFixed(1)}" y2="${y(eind.kosten_cum).toFixed(1)}" stroke="${saldo >= 0 ? "#4fb48a" : "#e0656c"}" stroke-dasharray="2 2"/>` +
      `<text x="${(x(11) - 6).toFixed(1)}" y="${((y(eind.betaald_cum) + y(eind.kosten_cum)) / 2).toFixed(1)}" fill="${saldo >= 0 ? "#4fb48a" : "#e0656c"}" font-size="10.5" text-anchor="end">${JE(saldo)} ${saldo >= 0 ? "terug" : "bij"}</text>`;
    return `<h3>Cumulatief per maand</h3><svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}">${grid.join("")}${labels}` +
      lijn("betaald_cum", "betaald_echt", "#d6a64f", 2.2) + lijn("kosten_cum", "kosten_echt", "#4fb48a", 2.6) + pijl + `</svg>` +
      `<div class="lg"><span style="--c:#d6a64f">betaald (termijnen)</span><span style="--c:#4fb48a">kosten</span><span style="--c:#6b7383">gestippeld = verwacht</span></div>`;
  }

  _advies(a) {
    const uit = [];
    const adv = a.advies || {};
    if (adv.advies_termijn_eur != null) {
      const t = Number(adv.advies_termijn_eur), nu = Number(a.termijn_eur);
      const gas = a.gas_overstap ? ` Gas gaat op ${JD2(a.gas_overstap)} over; daarna betaal je hier alleen nog stroom.` : "";
      const tekst = t < nu
        ? `<b>Termijn kan naar \u00b1 ${JE(t)}.</b> Dan kom je bij de afrekening rond \u20ac\u00a00 uit (nog ${adv.resterende_termijnen} termijnen).`
        : t > nu ? `<b>Termijn beter naar \u00b1 ${JE(t)}.</b> Anders volgt een bijbetaling (nog ${adv.resterende_termijnen} termijnen).`
          : `<b>Termijn klopt.</b> Met ${JE(nu)} kom je rond \u20ac\u00a00 uit.`;
      const sald = a.saldering_eind ? ` Na ${JD2(a.saldering_eind)} stopt de saldering; dat zit al in de verwachting.` : "";
      uit.push(`<div class="a"><ha-icon icon="mdi:calendar-sync-outline"></ha-icon><div>${tekst}${gas}${sald}</div></div>`);
    }
    const g = a.gas_nieuw;
    if (g) {
      const verschil = g.verschil_per_maand_eur;
      const kop = g.termijn_eur != null
        ? (verschil > 5 ? `<b>Gas nieuwe leverancier: ${JE(g.termijn_eur)} per maand lijkt ruim.</b>` : verschil < -5 ? `<b>Gas nieuwe leverancier: ${JE(g.termijn_eur)} per maand lijkt krap.</b>` : `<b>Gas nieuwe leverancier: ${JE(g.termijn_eur)} per maand klopt.</b>`)
        : `<b>Gas nieuwe leverancier: verwacht ${JE(g.per_maand_eur)} per maand.</b>`;
      uit.push(`<div class="a"><ha-icon icon="mdi:fire"></ha-icon><div>${kop} Verwacht \u00b1 ${JE(g.per_maand_eur)} per maand (${Number(g.m3_per_jaar).toLocaleString("nl-NL", { maximumFractionDigits: 0 })} m\u00b3 per jaar \u00d7 ${JE(g.prijs_m3, 2)} + vast + netbeheer \u2212 korting).</div></div>`);
    }
    return uit.length ? `<div class="adv">${uit.join("")}</div>` : "";
  }

  _noot(a) {
    const s = a.aannames || {};
    const mist = a.vorig_jaar_ontbreekt_dagen ? ` Van ${a.vorig_jaar_ontbreekt_dagen} resterende dagen ontbreekt het vorige jaar; die tellen als nul.` : "";
    return `<div class="note">Werkelijk = dagkosten van de leverancier (met saldering) + vaste kosten naar rato. De rest van het contractjaar is geschat met dezelfde dagen een jaar eerder. ` +
      `Vaste kosten: vastrecht ${JE(s.vastrecht_stroom_mnd, 2)} + ${JE(s.vastrecht_gas_mnd, 2)} per maand, netbeheer ${JE(s.netbeheer_stroom_jaar)} + ${JE(s.netbeheer_gas_jaar)} per jaar (aan te passen in de EMS-instellingen zodra de jaarafrekening er is).${mist}</div>`;
  }
}

const registreer = (naam, klasse) => {
  if (!customElements.get(naam)) customElements.define(naam, klasse);
};

registreer(KAART, EmsCockpitCard);
registreer(JAAR_KAART, EmsJaarafrekeningCard);
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

if (!window.customCards.some((k) => k.type === JAAR_KAART)) {
  window.customCards.push({
    type: JAAR_KAART,
    name: "EMS jaarafrekening",
    description: "Betaald tegenover werkelijk, stand nu en de verwachte jaarafrekening van het contractjaar.",
    preview: false,
  });
}

console.info(
  `%c EMS %c energiecockpit geladen \u00b7 v${VERSIE} `,
  "background:#0f3b2e;color:#fbbf24;font-weight:700",
  ""
);
