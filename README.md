# Energy Management System

Home Assistant custom integration die een Zendure-accu (SolarFlow 2400 AC
of vergelijkbaar) automatisch aanstuurt op basis van dynamische
energieprijzen: laden tijdens goedkope kwartieren, verkopen tijdens dure
kwartieren, en de Zendure's eigen `smart`-modus laten doen wat die doet in
alle andere kwartieren. Je wijst een prijssensor, een operation-select en
een manual-power-number aan; de rest — welk kwartier duur genoeg is, hoe
lang de accu de nacht moet overbruggen, hoeveel marge daarvoor nodig is —
berekent en leert de integratie zelf, continu, elke 5 minuten.

Dit document beschrijft hoe de integratie **nu** werkt. Voor de volledige
ontwikkelgeschiedenis (waarom elke beslissing is genomen, welke bugs
onderweg zijn gevonden en hoe) zie [`CHANGELOG.md`](CHANGELOG.md).

## Vereisten

Een sensor met een `forecast`-attribuut: een lijst van entries met een
`datetime` + een prijsveld. Standaard getest tegen de
[Zonneplan ONE integratie](https://github.com/fsaris/home-assistant-zonneplan-one)
(`sensor.zonneplan_current_electricity_tariff`), die zowel
`price_tax_included` als `price_tax_excluded` levert per kwartier.

> Gebruik je een andere leverancier/integratie (Nordpool, ENTSO-e,
> EnergyZero)? Die leveren vaak uurprijzen i.p.v. kwartierprijzen en/of
> andere attribuutnamen. De integratie leidt de interval-lengte
> automatisch af uit de data, maar de prijs-attribuutnaam
> (`price_attribute` in de config) moet overeenkomen met wat jouw sensor
> daadwerkelijk levert — check dit via **Ontwikkelaarshulpmiddelen →
> Staten** op je prijssensor.

Verplicht voor basiswerking: de prijssensor, een `select`-entity om de
Zendure-modus te zetten, en een `number`-entity voor het handmatige
vermogen. Alle overige sensoren hieronder zijn optioneel en schakelen
specifieke functionaliteit bij.

## Installatie via HACS (custom repository)

1. HACS → drie puntjes rechtsboven → **Custom repositories**.
2. URL: `https://github.com/Roedie84/Energy-Management-System`, categorie **Integration**.
3. Installeer, herstart Home Assistant.
4. **Instellingen → Apparaten & Diensten → Integratie toevoegen → Energy Management System**.
5. Doorloop de configuratiestappen (zie hieronder). Alle velden zijn later
   aan te passen via de **Configureren**-knop op de integratie.
6. Herstart Home Assistant nogmaals na elke update van de integratie —
   Python-modules worden door HA gecached, dit geldt voor alle
   HACS-integraties.

## Configuratie

### Verplicht

| Veld | Betekenis |
|---|---|
| `price_sensor_entity` | Je dynamische-prijssensor met `forecast`-attribuut |
| `price_attribute` | Welk prijsveld binnen elke forecast-entry (incl./excl. belasting) |
| `operation_select_entity` | De Zendure `select`-entity die de modus zet (`smart`/`manual`/`smart_discharging`) |
| `manual_power_number_entity` | De Zendure `number`-entity voor het handmatige vermogen (positief = ontladen, negatief = laden) |

### Vermogens & drempels

| Veld | Standaard | Betekenis |
|---|---|---|
| `manual_discharge_power` | 1600 W | Basisvermogen tijdens een duur kwartier (vóór SoC-/reserve-/vloer-aanpassing) |
| `manual_charge_power` | -2000 W | Vermogen bij netladen (weinig zon, noodladen) |
| `negative_price_charge_power` | -2000 W | Vermogen bij een negatieve prijs |
| `expensive_quarters_count` | 4 | Alleen nog gebruikt als informatieve context; de daadwerkelijke drempel is dynamisch (zie hieronder) |
| `min_soc_percent` | 15% | Ondergrens waaronder niet meer geforceerd wordt ontladen |
| `battery_round_trip_efficiency_percent` | 90% | Fallback-rendement totdat er genoeg geleerde metingen zijn |
| `low_solar_threshold_kwh` | 5,0 kWh | Fallback "weinig zon"-drempel totdat er genoeg leergeschiedenis is |
| `vacation_consumption_reduction_percent` | 60% | Geschatte verbruiksreductie tijdens vakantiemodus |

### Sensoren voor extra nauwkeurigheid (optioneel, elk schakelt iets bij)

| Veld | Schakelt bij |
|---|---|
| `available_energy_sensor_entity` | Energie-gebaseerde (i.p.v. tijd-gebaseerde) laad-uitstel-beslissing, dynamische reserve, huishoudverbruik-vloer |
| `battery_soc_sensor_entity` | SoC-taper op het ontlaadvermogen, noodladen |
| `consumption_power_sensor_entity` | Live-verbruikscorrectie, huishoudverbruik-vloer, grootverbruiker-detectie |
| `battery_power_sensor_entity` + `invert_battery_power_sign` | Correctie van P1-verbruik voor accu-invloed, accu-efficiëntie-leren |
| `pv_power_sensor_entity` | Correctie van P1-verbruik voor PV-invloed |
| `solar_forecast_sensor_entity` / `solar_today_forecast_sensor_entity` | Zon-gebaseerde beslissingen (Solcast `detailedForecast`-attribuut) |
| `solar_remaining_today_sensor_entity` | Live bijstelling van vandaags PV-restschatting |
| `solar_actual_sensor_entity` | Voorspelling-vs-werkelijkheid-tracking (leert de Solcast-bias) |
| `solar_power_limit_entity` | Zonnepanelen afregelen bij een negatieve prijs |
| `battery_total_capacity_sensor_entity` + `battery_min_soc_number_entity` | Capaciteit-bewuste "dure kwartieren"-telling (v0.63.27) |

### Grootverbruiker-bevestiging (optioneel, elk apart te configureren)

| Veld | Type | Betekenis |
|---|---|---|
| `dishwasher_power_sensor_entity` / `dishwasher_ready_sensor_entity` | vermogen / binary | Vaatwasser: apparaat-bewustzijn + grootverbruiker-bevestiging |
| `washing_machine_power_sensor_entity` / `washing_machine_ready_sensor_entity` | vermogen / binary | Wasmachine: idem |
| `quooker_power_sensor_entity` | vermogen | Quooker: bevestigd na 2 minuten aanhoudend gebruik |
| `airco_climate_entity` | climate | Airco: bevestigd via `hvac_action` (heating/cooling) |
| `slaapkamer_climate_entity` | climate | Slaapkamer-klimaatregeling: zelfde detectie als airco (v0.63.31) |
| `oven_state_sensor_entity` / `kookplaat_state_sensor_entity` | sensor | Home Connect `operation_state` (bevestigd bij `Run`) |
| `appliance_notify_service` | tekst | Notify-service voor apparaat-klaar-meldingen én accumodus-wijziging-meldingen (leeg = pop-up in HA) |

**"Goedkoop moment voor de vaatwasser/wasmachine"-melding uit te
zetten (v0.63.54, gevraagd):** de switch
`switch.vaatwasser_wasmachine_meldingen` (standaard aan) schakelt
uitsluitend déze ene meldingssoort uit — niet de gedeelde
`appliance_notify_service`, die ook gebruikt wordt voor de
modus-wijziging-melding, de steelstofzuiger/fietsladers-klaar-melding,
sluipverbruik en NILM-afwijkingen. Die blijven gewoon werken als je
alleen deze ene melding niet meer wilt.

## Hoe de beslislogica werkt

Elke 5 minuten (`UPDATE_INTERVAL_MINUTES`) doorloopt de coordinator deze
boom, van boven naar beneden — de eerste regel die van toepassing is,
bepaalt de actie:

```
Force manual aan?                          → niets doen, jij hebt controle
Negatieve prijs?                            → hard laden + zonnepanelen afregelen
Dit kwartier duur genoeg? (primair/secundair, zie onder)
  → SoC/prijs-prioriteit staat het toe?     → manual ontladen
  → nee, maar accu kritiek laag + weinig zon?→ noodladen
  → nee                                     → smart (bescherm de accu)
Weinig zon verwacht + huidig goedkoopste blok? → netladen
Accu kritiek laag + weinig zon verwacht?    → noodladen
Vóór het goedkoopste blok, genoeg energie om te overbruggen? → smart_discharging
Anders                                      → smart (Zendure regelt zelf)
```

### Duur-kwartier-drempel: dynamisch en tweeledig

Geen vast aantal kwartieren, maar een **dynamische drempel**: de top 20%
van de vandaag-prijsrange (`EXPENSIVE_PRICE_THRESHOLD_FRACTION`) geldt als
"duur" — bij weinig verwachte zon verscherpt dat naar top 8%
(`EXPENSIVE_PRICE_THRESHOLD_FRACTION_LOW_SOLAR`), extra voorzichtig omdat
er minder marge is om een misser te herstellen.

Daarnaast een **secundaire, ruimere laag** (top 45% van de prijsrange,
`SECONDARY_EXPENSIVE_PRICE_THRESHOLD_FRACTION`): als er na reservering
voor alle nog resterende primaire (echt dure) kwartieren van vandaag nog
*vrije* headroom over is, mag die ook verkocht worden tegen deze ruimere
drempel — nooit ten koste van de primaire piek of de nachtreserve, vult
alleen aan wat anders toch onbenut zou blijven.

Binnen beperkte headroom geldt **prijs-prioriteit**: de duurste kwartieren
gaan eerst, niet chronologisch — een kwartier kan bewust worden
overgeslagen ten gunste van een duurder kwartier later diezelfde dag.

**"Dure kwartieren"-telling (dashboard/diagnostiek), capaciteit-bewust
sinds v0.63.27:** de ruwe telling (hoeveel kwartieren van de hele dag de
drempel halen) kan bij een relatief vlakke prijsdag flink hoger uitvallen
dan wat de accu ooit fysiek zou kunnen verkopen. Met
`battery_total_capacity_sensor_entity` + `battery_min_soc_number_entity`
geconfigureerd (beide live uitgelezen, niet statisch ingesteld) wordt de
telling begrensd op `(totale_capaciteit × (1 − hardware_min_soc%)) /
(manual_discharge_power × 0,25h)` — een grove, fysieke bovengrens, geen
precieze voorspelling (houdt bewust geen rekening met de dynamische
nachtreserve, die verandert per kwartier). Zonder deze twee velden:
ongebreidelde ruwe telling, zoals voorheen.

### Winter-guard

Is er vandaag al netgeladen (weinig zon)? Dan wordt diezelfde dag niet
ook nog verkocht — dat zou de net-gekochte energie met verlies terugzetten.

### Ontlaadvermogen: SoC-taper, dynamische reserve, en de huishoudverbruik-vloer

Het basisvermogen (`manual_discharge_power`) wordt per tick geschaald:

1. **Dynamische reserve** (met `available_energy_sensor_entity`): hoeveel
   energie moet er minimaal in de accu blijven om de rest van de nacht +
   marge te overbruggen? Gebruikt de **diepste-tekort-berekening** — het
   diepste punt onderweg (meestal net vóór zonsopkomst), niet het
   eindsaldo, want een grote verwachte zonnedag verbergt anders een reëel
   tekort ervoor. Basismarge 10% (`DYNAMIC_DISCHARGE_RESERVE_MARGIN`),
   plus zelflerende correcties (zie hieronder).
2. **Zonder** `available_energy_sensor_entity`: een simpele SoC-percentage-
   aftopping richting `min_soc_percent` (band van
   `SOC_TAPER_BAND_PERCENT` = 15 procentpunt).
3. **Huishoudverbruik-vloer**: het geschaalde vermogen zakt nooit onder je
   actuele huisverbruik (mediaan van de laatste 4 metingen, tenzij een
   grootverbruiker dit expliciet bevestigt — zie onder), begrensd door wat
   fysiek beschikbaar is. Voorkomt dat je tijdens een duur kwartier een
   deel van je verbruik alsnog tegen piekprijs importeert, terwijl de accu
   net had besloten te gaan verkopen.

**Vol vermogen of niets (v0.63.18):** zodra een kwartier via de
prijs-prioriteit (`_is_worth_discharging_now`) is aangemerkt als
betaalbaar op het volle `manual_discharge_power` — d.w.z. het hoort bij
de zoveel duurste kwartieren van vandaag als de headroom op vól vermogen
kan bekostigen — wordt ook daadwerkelijk het volle bedrag toegepast, niet
alsnog afgeknepen tot een klein deel daarvan door de per-tick-
headroomformule. "1600W of niets", geen uitgesmeerde trickle-ontlading
die amper iets oplevert. Alleen begrensd door wat fysiek in de accu zit
op dat moment, en (als minimum) door de huishoudverbruik-vloer hierboven.
Is een kwartier niet betaalbaar bevonden, dan gebeurt er niets (geen
gedeeltelijke ontlading) — de headroom blijft gereserveerd voor een
duurder kwartier later die dag.

**Geen headroom meer over? Dan smart, geen geforceerd commando (v0.63.19):**
staat de headroom exact op 0 (de reserve-berekening zegt: alles is al
nodig, geen ruimte voor extra verkoop), dan stuurt de integratie geen
handmatig commando meer om puur je huisverbruik te dekken — dat werd
voorheen wel gedaan (de huishoudverbruik-vloer, v0.59.0), maar bleek
overbodig: `smart`-modus regelt dit via de eigen P1-volgende aansturing
van de Zendure toch al, continu bijgesteld in plaats van een vast
getal dat tot de volgende tick blijft staan. De huishoudverbruik-vloer
blijft wél actief zodra er wél íets aan headroom is (hoe klein ook) —
alleen bij exact nul headroom valt de integratie terug op `smart`.

### Zelfcorrigerende veiligheidsmarge

Twee onafhankelijke, dagelijkse detecties passen de marge op de
diepste-tekort-berekening automatisch aan:

- **Tekort**: onverwachte netimport tijdens een periode die
  zelfvoorzienend had moeten zijn (grens: `GRID_IMPORT_SHORTFALL_THRESHOLD_W`
  = 100 W) → marge omhoog, +5 procentpunt per recente tekortdag
  (`SHORTFALL_MARGIN_BONUS_PER_RECENT_DAY`), over de laatste
  `LEARNING_HISTORY_DAYS` = 7 dagen.
- **Overschot**: beschikbare energie bleef ≥3× (`RESERVE_EXCESS_RATIO_THRESHOLD`)
  hoger dan nodig terwijl laden nog werd uitgesteld → marge omlaag, -3
  procentpunt per recente overschotdag, met een ondergrens van -5
  procentpunt totale correctie (`MIN_TOTAL_MARGIN_BONUS_PERCENT`).

Plus een vaste "onbeschermde nasleep"-marge van 15%
(`UNPROTECTED_AFTERMATH_MARGIN_PERCENT`): na een duur-kwartier-ontlading
neemt de Zendure's eigen smart-modus het over, buiten onze reserve-
bescherming om — deze marge compenseert dat structurele blinde vlek.

### Zonoverschot vastleggen tijdens "laden uitstellen"

**Geschiedenis (afgerond, v0.63.15 t/m .76)**: dit was ooit een
"arbitrage-laden"-mechanisme dat actief bijkocht van het net tijdens
een goedkoop kwartier, puur omdat er later diezelfde dag een bekend
duurder kwartier aankwam en dat na laad/ontlaad-verlies winstgevend
was. Na verschillende praktijkrapporten — een onjuiste aanname over
hoe manual-modus zon en net combineert (v0.63.72 loste dat eerst op),
gevolgd door herhaalde meldingen dat de accu bij een ontoereikende
reserve alsnog grotendeels van het net bleef bijladen in plaats van
puur op smart te draaien — is **definitief besloten (v0.63.77) het
hele mechanisme te verwijderen**. Expliciet bevestigd: voor deze
accu-capaciteit wordt gekochte energie in de praktijk toch nooit met
winst doorverkocht — het dient sowieso gewoon als overbrugging voor de
nacht, wat de hele winst-framing overbodig maakte. Zelfs bij een
écht ontoereikende reserve koopt dit mechanisme niet meer actief bij;
`should_force_charge` (weinig zon verwacht tijdens het goedkope blok)
en `_is_emergency_low_battery` (kritiek lage SoC) blijven als de enige,
aparte vangnetten over, via hun eigen criteria.

**Wat overblijft**: uitsluitend het voorkomen dat al aanwezig
zonoverschot verloren gaat. Zodra "laden uitstellen"
(`smart_discharging`) van toepassing zou zijn — er is al genoeg reserve
om de nacht te overbruggen — maar er is op dat moment ook zonoverschot,
dan gaat de accu toch in `smart`-modus in plaats van
`smart_discharging` (reden: `arbitrage_solar_capture`). Dat is nodig
omdat `smart_discharging` uitsluitend het huishoudverbruik dekt en
niet bijlaadt vanuit een zonoverschot (bevestigd, v0.63.59) — zonder
deze uitzondering zou dat overschot gewoon worden teruggeleverd in
plaats van vastgelegd. Geen netaankoop, nooit — puur het niet laten
liggen van zon die er al is.

Gebruikt de Solcast-gebaseerde verwachte PV-productie voor dit exacte
half-uur (`_get_expected_pv_power_w`, v0.63.71, gecorrigeerd met de
al geleerde bias per uur) in plaats van de live, ogenblikkelijke
PV-meting — een voorbijtrekkende wolk beïnvloedt zo het half-uur-
gemiddelde nauwelijks. Valt terug op de live meting als er geen
`solar_forecast_sensor_entity` is geconfigureerd.

### Kookpiek blies de "diepste tekort"-berekening op (v0.63.78)

Gerapporteerd: "Het basis verbruik schiet tussen ca. 16:00 en 17:00
omhoog door koken etc." — de "Basisverbruik"/"Diepste tekort
onderweg"-cijfers in de uitlegtekst-tabel kunnen flink oplopen als de
berekening toevallig samenvalt met een actieve kookpiek.

**Root cause**: de live-verbruikscorrectie
(`_get_smoothed_consumption_correction_ratio`) heeft een bewuste
uitzondering — is een **bevestigde** zware verbruiker (vaatwasser,
wasmachine, Quooker, airco, oven, kookplaat) actief, dan wordt de
mediaan-demping overgeslagen en de laatste, ongefilterde meting direct
vertrouwd (geen ambiguïteit meer om tegen te beschermen). Terecht voor
airco (kan uren aanhouden), maar **niet** voor de inherent kortdurende
apparaten: een kooksessie duurt doorgaans ruim onder het uur. Die
ogenblikkelijke, hoge meting werd vervolgens gebruikt om de **hele
resterende periode** (vaak 15+ uur tot het volgende goedkope blok) mee
op te schalen — voor een gebeurtenis die allang voorbij is tegen de
tijd dat de nacht daadwerkelijk aanbreekt.

**Fix**: een nieuwe constante `SUSTAINED_HEAVY_LOAD_SOURCES` (`airco`,
`slaapkamer`) bepaalt nu welke bevestigde verbruikers de mediaan-demping
nog mogen overslaan. Vaatwasser, wasmachine, Quooker, oven en kookplaat
vallen voortaan terug op dezelfde mediaan-gedempte route als een
onbevestigde meting — een kortstondige piek beïnvloedt de meerurige
schatting daardoor niet meer onevenredig.

## Grootverbruiker-bevestiging

Bevestigt een geconfigureerde vaatwasser/wasmachine/Quooker/airco/oven/
kookplaat zich als **daadwerkelijk actief** (vermogen boven 15W
(`APPLIANCE_RUNNING_POWER_THRESHOLD_W`), Quooker pas na 2 minuten
aanhoudend, airco via `hvac_action`, oven/kookplaat via Home Connect
`operation_state == Run`)? Dan wordt de live-verbruikscorrectie niet meer
gedempt door de gebruikelijke mediaan-voorzichtigheid (die specifiek
bestaat om een korte, onbevestigde piek te negeren) — de meting wordt
direct vertrouwd, in plaats van pas na meerdere ticks.

## Geplande laadapparaten (steelstofzuiger, fietsladers)

Twee optioneel te configureren apparaten worden **daadwerkelijk
aangestuurd** (niet alleen informatief, in tegenstelling tot de
apparaat-bewustzijn-functie hierboven): een schakelaar gaat aan zodra
het goedkoopste prijsblok van de dag begint, en weer uit zodra het
laden **daadwerkelijk klaar is** — gedetecteerd doordat het vermogen
minstens 2 minuten aanhoudend onder een drempel zakt (zelfde principe
als de Quooker-detectie, maar omgekeerd: aanhoudend láág bevestigt
"klaar" in plaats van aanhoudend hóóg "actief"). Laadt maximaal 1x per
dag; eenmaal klaar blijft de schakelaar uit voor de rest van de dag, ook
al valt die nog binnen het goedkope blok.

**Wacht op het apparaat, geen valse "klaar"-melding (v0.63.37):**
gerapporteerd scenario — het goedkoopste blok begint en de schakelaar
gaat aan, maar de fietsen worden pas 2 uur later (nog steeds binnen
hetzelfde goedkope blok) daadwerkelijk aan de lader gehangen. Zonder
onderscheid zag "aan, maar nog niets aangesloten" er identiek uit als
"was aan het laden, nu klaar" — na slechts 2 minuten (één tick) werd het
dan ten onrechte als "voltooid" gemarkeerd en ging de schakelaar weer
uit, nog vóórdat er ooit iets was aangesloten. Nu wordt bijgehouden of
het vermogen tijdens de huidige sessie **ooit** daadwerkelijk boven de
drempel is gekomen — pas dán telt aanhoudend laag vermogen als "echt
klaar", niet als "nooit begonnen". Status `wacht_op_apparaat` maakt dit
onderscheid zichtbaar.

**Polling in plaats van continu aan (v0.63.38, brandveiligheid):**
terechte vervolgvraag na de fix hierboven — als er niets is aangesloten,
bleef de schakelaar daarmee wél de hele tijd continu aan staan, mogelijk
urenlang, wat een lader/omvormer onnodig lang onder spanning laat staan
zonder toezicht. In plaats daarvan **polt** de integratie nu: kort aan
(één update-tick, ~5 minuten) om te testen of er iets is aangesloten,
en bij niets gevonden weer uit voor een afkoelperiode van
`SCHEDULED_CHARGE_POLL_OFF_MINUTES` (15 minuten) voordat de volgende
testpoging volgt — een duty-cycle van ~25% in plaats van continu
onder spanning. Status `test_aan` toont een lopende testpoging. Zodra
er daadwerkelijk stroom wordt getrokken, schakelt het systeem over naar
normaal laden en blijft het gewoon aan tot de lading (of het goedkope
blok) voorbij is.

**Zelflerende voltooiingsdrempel (v0.63.46):** gerapporteerd — het
standaard-verbruik van de fietsladers bleek in de praktijk rond 2W te
liggen, terwijl de vaste drempel (`FIETSLADERS_COMPLETE_THRESHOLD_W` =
20W) een gok was die daar niet bij paste. Elke meting die tijdens een
testpoging wordt gedaan terwijl er nog geen sprake is van bevestigde
activiteit, is een echte stand-by-meting — die worden bijgehouden
(laatste 20, `IDLE_POWER_HISTORY_LENGTH`). Zodra er minstens
`LEARNED_THRESHOLD_MIN_SAMPLES` (5) zijn verzameld, wordt de
voltooiingsdrempel automatisch afgeleid als de mediaan van die
stand-by-metingen plus een veiligheidsmarge
(`LEARNED_THRESHOLD_MARGIN_W` = 5W) — bij 2W stand-by dus een geleerde
drempel van ~7W in plaats van de gegokte 20W. Zolang er nog onvoldoende
metingen zijn, blijft de vaste drempel gewoon gelden (geen regressie).
Zichtbaar als `idle_power_history_w` en
`learned_completion_threshold_w` op de status-sensoren.

**Persistentie-gat gevonden en gefixt (v0.63.64):** gerapporteerd,
tijdens een controle of vandaag toegevoegde data een herstart
overleeft — `SteelstofzuigerStatusSensor`/`FietsladersStatusSensor`
waren géén `RestoreEntity`, waardoor zowel `idle_power_history_w`
(hierboven) als de al langer bestaande `duration_history_minutes`
(geleerde laadduur) bij elke herstart stilzwijgend terugvielen naar
leeg. Beide sensoren zijn nu wél `RestoreEntity` en herstellen beide
histories bij het opstarten.

| Veld | Drempel | Betekenis |
|---|---|---|
| `steelstofzuiger_switch_entity` / `steelstofzuiger_power_sensor_entity` | 15W (`APPLIANCE_RUNNING_POWER_THRESHOLD_W`) | Steelstofzuiger-lader |
| `fietsladers_switch_entity` / `fietsladers_power_sensor_entity` | 20W (`FIETSLADERS_COMPLETE_THRESHOLD_W`) | E-bike-laders |

De laadduur per sessie wordt bijgehouden als leerdata (mediaan over de
laatste 7 sessies, dezelfde uitschieter-resistente aanpak als het
zelflerend gedrag hieronder) — puur informatief; de aan/uit-beslissing
zelf leunt op de live vermogensmeting, niet op de schatting. Stuurt bij
voltooiing een melding via `appliance_notify_service` (dezelfde
instelling als voor de overige apparaat-meldingen).

Beide zijn bewust onafhankelijk van `force_manual` (dat gaat specifiek
over de accu-besturing), maar respecteren wel `learning_only` (simuleert
dan alleen, stuurt nooit echt iets naar de schakelaar). Elk apparaat
heeft een eigen **overrule-schakelaar**
(`switch.steelstofzuiger_overrule` / `switch.fietsladers_overrule`) —
staat die aan, dan laat de integratie die ene schakelaar volledig met
rust (per-apparaat equivalent van `Force manual`, maar zonder de rest
van de besturing te raken).

## Zelflerend gedrag

Alle onderstaande waarden gebruiken de **mediaan** over de laatste 7
metingen/dagen, niet het gemiddelde — een enkele uitschieterdag/-cyclus
(wasdag, regenbui, ruisige laadcyclus) beweegt de geleerde waarde daardoor
niet noemenswaardig; pas als een meerderheid van het venster het nieuwe
niveau bevestigt, verschuift de mediaan mee.

- **Uurprofiel huishoudverbruik** — continu bemonsterd, alle 24 uur van de
  dag, alle dagen (niet alleen 's nachts).
- **PV-voorspellingsbias per uur** — werkelijk-versus-Solcast-verhouding,
  minimaal 3 dagen historie nodig (`MIN_SOLAR_HISTORY_FOR_DYNAMIC_THRESHOLD`)
  voordat een uur "vol vertrouwd" wordt.
- **Accu-efficiëntie** — uit echte laad/ontlaad-cycli (energiebalans:
  geladen × rendement = ontladen + verandering in beschikbare energie),
  uitschieters buiten 50-100% worden weggegooid.
- **Nachtverbruik** (legacy fallback, alleen gebruikt als het uurprofiel
  geen data heeft voor het relevante uur).

Alle leerdata overleeft een HA-herstart via `RestoreEntity` — inclusief de
volledige onderliggende dagreeksen (niet alleen het laatst berekende
gemiddelde), zodat een net-vóór-herstart-trend niet resetten naar "geen
verandering" totdat er weer nieuwe metingen binnenkomen.

## Meldingen

Zodra de integratie de modus **of** het toegepaste vermogen daadwerkelijk
wijzigt, stuurt de coordinator een melding via `appliance_notify_service`
(hetzelfde veld als voor apparaat-klaar-meldingen) — geen aparte
automatisering nodig. Bevat een reden-specifieke emoji, het toegepaste
vermogen, en de volledige, live berekende uitlegtekst. Meldt bewust niet:
op de allereerste tick na een herstart (nog niets om mee te vergelijken),
tijdens `learning_only`, of zolang `Force manual` aanstaat.

Een `button`-entiteit ("Test notificatie versturen") stuurt een testbericht
via exact dezelfde code, om de configuratie te verifiëren zonder op een
echte wijziging te hoeven wachten.

## Vakantiemodus / Learning-only / Force manual

Drie `switch`-entiteiten, alle drie los te bedienen en persistent over
herstarts:

- **Force manual** — de coordinator doet dan helemaal niets; jij hebt
  volledige controle over de Zendure.
- **Learning only (no control)** — blijft doorrekenen en leren, stuurt
  nooit iets naar de Zendure. `sensor.simulated_action` toont wat er wél
  zou zijn gedaan. Handig om het gedrag een paar dagen te observeren
  voordat je het vertrouwt.
- **Vakantiemodus** — schat het huishoudverbruik lager in
  (`vacation_consumption_reduction_percent`) en pauzeert
  verbruiksgerelateerd leren, zodat de ongebruikelijk lage
  vakantie-metingen het geleerde "normale" profiel niet vervuilen.

## Dashboard

`dashboards/energy_management_system_dashboard.yaml` wordt bij elke
HA-herstart automatisch gekopieerd naar je config-map (overschrijft
bestaande handmatige wijzigingen — koppel die dus eerst terug voordat je
een nieuwe versie installeert). Bevat: een live-overzicht met een
icoon-samenvatting en de volledige, actuele uitlegtekst; accu- en
rendement-gauges; een financieel overzicht; en bedienings-/detail-secties.

**Financieel dag/week/maand-overzicht** vereist een handmatige,
eenmalige stap: voeg `dashboards/utility_meter_ems.yaml` toe aan je
`configuration.yaml` (native Home Assistant Utility Meter-helper, geen
onderdeel van deze integratie) en herstart. Controleer de `source`-
entity-ID's in dat bestand tegen je eigen installatie — een verkeerde
naam faalt stil (de meter blijft dan voor altijd op 0 staan).

## Wat bespaart de accu (kostprijs-model)

Naast `discharge_value_expensive_quarters`/`charge_cost_grid_charging`
(directe waarde van expliciete verkoop-/koopacties, bewust **niet**
"besparing" genoemd omdat dat een onverifieerbaar tegenfeitelijk
scenario zou impliceren) bestaat er een tweede, wél als besparing te
noemen metriek: `sensor.battery_savings_cost_basis_model`.

Dit gebruikt een **gewogen-gemiddelde-kostprijs-model**: elke kWh die de
accu in gaat (ongeacht bron — netladen óf zon-overschot) wordt
gewaardeerd tegen de actuele dynamische prijs op dat moment. Elke kWh
die eruit gaat — verkocht tijdens een duur kwartier, óf simpelweg
gebruikt om 0 op de meter te houden — realiseert het verschil tussen de
actuele prijs en die kostprijs.

Dit is uitdrukkelijk **wél** geldig als "besparing" (in tegenstelling
tot de sensoren hierboven): het gebruikt uitsluitend prijzen die de
integratie zelf heeft waargenomen op het exacte moment van laden/
ontladen, geen hypothetisch "zonder accu"-scenario.

**Vereist een salderen-contract** (teruglevering tegen hetzelfde
dynamische tarief als inkoop) om correct te zijn: dan heeft
zon-energie die de accu in gaat (in plaats van terug te leveren)
exact dezelfde opportuniteitskosten als het inkopen van diezelfde
energie op dat moment — waardoor zon-geladen en net-geladen energie in
één model passen, zonder ze apart te hoeven bijhouden (wat sowieso niet
kan: de accu is één gedeelde pool, geen partijen per bron). Zodra
salderen stopt, moet deze aanname worden herzien.

Kan net als de onderliggende werkelijkheid ook **dalen** (een verkoop
onder de kostprijs realiseert een verlies) — gebruikt daarom
`state_class: total`, niet `total_increasing`. Bewuste vereenvoudiging:
onderscheidt niet tussen "ontlading die nuttig verbruik dekte" en
"ontlading verloren aan zelfontlading" — beide zien er in de
`available_kwh`-data identiek uit.

**Zonneplan's Zonnebonus** (v0.63.25, criteria bevestigd via
webonderzoek — niet aangenomen): bovenop de kale marktprijs geldt een
vaste terugleverpremie van €0,02/kWh voor elke kWh die daadwerkelijk
wordt teruggeleverd, óók vanuit een accu. De aparte 10%-bonus die
Zonneplan erbovenop geeft, geldt echter **niet** voor teruglevering
vanuit een thuisbatterij — die wordt hier dan ook nooit meegerekend.

Het model onderscheidt daarom **echte netto-teruglevering** (het deel
van een ontlading dat boven het actuele huisverbruik uitkomt — krijgt de
€0,02/kWh) van **puur eigen-verbruik-dekken** (geen teruglevering, dus
ook geen premie, alleen de vermeden inkoopprijs telt). Benaderd door het
gemiddelde ontlaadtempo over de verstreken tijd te vergelijken met het
live gecorrigeerde huisverbruik — vereist dus wel
`consumption_power_sensor_entity` om dit onderscheid te kunnen maken;
zonder die sensor telt de hele ontlading als "geen teruglevering" (dus
geen premie, conservatieve onderschatting). Nog niet toegepast aan de
laadkant (de vraag of zon-geladen energie tegen de gederfde
teruglever-waarde in plaats van de marktprijs gewaardeerd zou moeten
worden) — een mogelijke vervolgstap.

## Zonoverschot-schatting gebruikte trage i.p.v. live correctie (v0.63.104)

Gerapporteerd met screenshot: "dit komt niet overeen met de
werkelijkheid 55W, het overschot is veel groter op dit moment."

**Root cause, gevonden door twee PV-schattingsfuncties te vergelijken**:
deze codebase heeft AL een mechanisme dat Solcast's eigen live
"resterend vandaag"-sensor gebruikt om de voorspelling real-time bij
te stellen op basis van daadwerkelijk waargenomen omstandigheden
(`_get_pv_remaining_correction_ratio`) — en dat wordt AL correct
gebruikt in de tekortberekening (`_estimate_pv_kwh_for_period`). Maar
`_get_expected_pv_power_w` — specifiek gebruikt voor de "moet ik nu
zonoverschot vangen"-beslissing waar dit rapport over gaat — gebruikte
uitsluitend de trage, over VEEL dagen langetermijn-geleerde
uur-bias-ratio, zonder deze live correctie. Op een dag die zonniger is
dan het langetermijngemiddelde voor dat uur, gaf dit stelselmatig een
te lage verwachting — precies het gerapporteerde symptoom.

**Fix**: `_get_expected_pv_power_w` probeert nu, in volgorde van
voorkeur, eerst de live "resterend vandaag"-correctieratio (als
`solar_remaining_today_sensor_entity` is geconfigureerd), en valt pas
terug op de trage geleerde uur-ratio als die live correctie niet
beschikbaar is — exact dezelfde prioriteitsvolgorde die de
tekortberekening elders al hanteerde. Geen nieuwe configuratie nodig
als je die sensor al had ingevuld; zonder die sensor blijft het oude
gedrag ongewijzigd (geen regressie).

**Getest**: nieuwe test bevestigt dat de live correctie voorrang
krijgt boven de langetermijn-geleerde ratio wanneer beide beschikbaar
zijn, en dat zonder geconfigureerde live-sensor het bestaande,
geleerde-ratio-gedrag ongewijzigd blijft.

## NILM: eigen sensoren + SolarFlow/Solcast bleven als kandidaat terugkomen (v0.63.103)

Gerapporteerd: "elke keer terug krijg onbevestigde kandidaten na
herstart", met een concrete lijst — daarin bleken twee echte,
structurele bugs te zitten.

**Bug 1 — de integratie ontdekte haar eigen sensoren als NILM-
kandidaat.** "Energy Management System Hourly consumption profile" en
"Energy Management System Piekvermogen" (v0.63.101) rapporteren zelf
ook in Watt en werden daardoor voorgesteld als "apparaat" — de
discovery-scan had geen check tegen de eigen entiteiten van deze
integratie.

**Fix**: nieuwe `_is_own_integration_entity()` — elke entity_id van
deze integratie volgt het patroon
`sensor.<apparaat>_energy_management_system_<naam>`, dus `DOMAIN` als
substring is een betrouwbare, generieke uitsluiting die geen
onderhoud per nieuwe sensor vereist. Toegepast in zowel de discovery-
scan als de terugwerkende opruimfunctie.

**Bug 2 — "SolarFlow" stond niet in de naampatroon-uitsluiting.**
De batterij verschijnt in entity-namen onder de merknaam "SolarFlow"
("SolarFlow 2400 AC PV1 Solar Power" etc.), niet onder "zendure" —
alleen dat laatste stond in `NILM_PATTERN_EXCLUDED_KEYWORDS`. Solcast-
voorspellingssensoren (geen echte apparaten, maar rapporteren ook in
W) en gespiegelde accu-signalen ("... (omgekeerd)") hadden hetzelfde
probleem.

**Fix**: `NILM_PATTERN_EXCLUDED_KEYWORDS` uitgebreid met "solarflow",
"solcast" en "(omgekeerd)".

**Getest** (6 nieuwe tests): SolarFlow/Solcast/gespiegelde-accu-
entiteiten worden nooit meer kandidaat; eigen-integratie-sensoren
worden nooit kandidaat; een legitiem apparaat (bijv. een tv) blijft
gewoon gevonden worden naast deze uitsluitingen; bestaande, al-
bevestigde eigen-integratie-entiteiten worden met terugwerkende kracht
opgeruimd.

## Airco-verwachting-tegel toonde temperatuur i.p.v. kans (v0.63.102)

Gerapporteerd met screenshot: de "Airco-verwachting"-tegel op het
Klimaat-tabblad toonde als hoofdwaarde een temperatuur (23,2°C —
identiek aan de losstaande "Woonkamertemperatuur (live)"-tegel
ernaast), terwijl de kans-op-airco-binnen-1-uur (het eigenlijke doel
van deze tegel) alleen in de kleinere subtekst stond.

**Verklaring**: de onderliggende sensor se `native_value` is bewust de
temperatuur-bucket die wordt bijgehouden (voor HA-statistieken/
grafieken), met de voorspelling als apart attribuut — een geldige
technische keuze, maar verwarrend als dashboardweergave: een tegel die
"Airco-verwachting" heet, hoort de verwachting zelf prominent te tonen.

**Fix**: alleen de dashboardkaart aangepast (de sensor zelf blijft
ongewijzigd, dient nog steeds hetzelfde doel) — primary toont nu de
kans-procent (of "onvoldoende data" als die nog ontbreekt), secondary
toont de temperatuur waarbij die kans hoort.

## Vijf klassieke EMS-kengetallen toegevoegd (v0.63.101)

Gevraagd: "heb je nog zaken voor een typisch EMS welke we kunnen
toevoegen?" — vijf metrics die gebruikelijk zijn in professionele
energiemanagementsystemen, alle vijf gebouwd ("ze allemaal wel willen
integreren"). Nieuw dashboardtabblad "EMS-KPI's" bundelt ze.

### 1. Piekvermogen-tracking (capaciteitstarief)

Nederlandse netbeheerders stappen steeds meer over op tarieven
gebaseerd op het hoogste piekvermogen (kW), niet alleen kWh. Nieuwe
`_update_peak_power_tracking`: houdt het hoogste gemeten netto-
netimport-vermogen bij op drie niveaus (vandaag/maand/all-time).
Bewust de RUWE P1-meter-aflezing, niet de elders gebruikte
"gecorrigeerde" huishoudverbruik-schatting — een capaciteitstarief
wordt afgerekend op wat het net zelf ziet. Nieuwe `PeakPowerSensor`
(RestoreEntity, all-time/maand-records overleven een herstart).

### 2. Tegenfeitelijke besparingsvergelijking

"Als je dit systeem niet had, had je deze maand €X betaald; nu
betaalde je €Y." Reconstrueert per tick wat de netmeter zou hebben
getoond zónder de accu (zelfde PV-opbrengst, geen accu-sturing:
P1 + accu-vermogen), en rekent beide scenario's tegen dezelfde
dynamische prijs af. Bewust deze specifieke tegenfeitelijke situatie
(niet een vaag "vs. een vast tarief" — dat zou een aparte, losse
aanname vereisen die niet uit bestaande sensoren is af te leiden).
Nieuwe `CounterfactualSavingsSensor` (RestoreEntity).

### 3. Zelfconsumptie-/zelfvoorzieningsratio

Klassieke EMS-KPI's: welk deel van de eigen PV-productie wordt zelf
verbruikt (zelfconsumptie), en welk deel van het totale verbruik wordt
gedekt door eigen bronnen i.p.v. het net (zelfvoorziening). Nieuwe
`_update_self_sufficiency_tracking`, afgeleid uit cumulatieve
dag-kWh's (PV-productie, PV-export, bruto-verbruik, net-import).
Nieuwe `SelfSufficiencySensor`.

### 4. Accu-gezondheid over de lange termijn

Cyclus-telling (cumulatieve ontladen energie / accucapaciteit) en een
geschatte capaciteitsdegradatie. **Bewust en nadrukkelijk een ruwe
schatting, geen gemeten waarde** — deze integratie kan de werkelijke
accucapaciteit niet meten. Lineair model: 80% capaciteit na 4000
volledige cycli (representatief voor LFP-chemie zoals de Zendure
SolarFlow-serie, kan afwijken van de daadwerkelijke celspecificaties).
Nieuwe `BatteryHealthSensor` (RestoreEntity — de cumulatieve teller is
levenslang).

### 5. CO2-intensiteit van het net

Optioneel — nieuwe config `co2_intensity_sensor_entity` (bijv.
ElectricityMaps, CO2 Signal). Houdt de geschatte uitstoot bij van
geïmporteerde energie (huidige intensiteit × geïmporteerde kWh) — niet
van totaal verbruik, energie die zelf via PV/accu wordt gedekt
importeert niets. Nieuwe `CO2IntensitySensor`.

**Getest** (35 nieuwe tests over 5 testbestanden): elke feature apart
getest inclusief dag/maand-rollover, randgevallen (geen sensor
geconfigureerd, export i.p.v. import, grote hiaten na een herstart),
en voor de accu-gezondheid specifiek: het degradatiemodel clampt
correct op 80% i.p.v. door te extrapoleren voorbij het gemodelleerde
bereik.

## NILM-alarm lost zichzelf voortaan live op (v0.63.100)

Vervolgvraag na v0.63.99: "kan dit soort zaken eerder in diagnostiek
worden opgevangen, het mooiste zou natuurlijk iets in de integratie
zijn wel dit live zelf in Home Assistant oplost?"

**Aanleiding**: het v0.63.99-plafond voorkomt toekomstige uitschieter-
gestuurde alarmen, maar een al opgebouwde, verouderde accumulator
bouwt via de normale, kleine dagelijkse afbouw extreem traag af —
doorgerekend voor het gerapporteerde CV-ketel-scenario: **bijna 90
dagen**. Te traag om "live" te noemen.

### Auto-reset bij aanhoudende terugkeer naar normaal

Nieuwe constante `NILM_CUSUM_RESET_STREAK_DAYS` (5). Zodra een
apparaat dit aantal opeenvolgende dagen een **genuine** terugkeer naar
normaal laat zien (de dagwaarde zelf op of onder de referentie — niet
slechts "iets minder ver boven de marge"), wordt de accumulator direct
volledig gereset in plaats van traag te laten wegebben. Bewust
meerdere dagen vereist (niet na 1 dag al resetten), zodat een
kortstondige dip het alarm niet onterecht meteen wegneemt terwijl het
onderliggende probleem nog speelt. Een dag die de streak onderbreekt
(weer boven de referentie) reset de teller naar 0 — vereist dus
daadwerkelijk aaneengesloten dagen.

### Meer context in de diagnostiek-samenvatting

Een apparaat dat al een paar dagen op rij normaliseert (op weg naar
auto-reset) toont dat nu expliciet in `get_diagnostic_summary()` —
"X dag(en) op rij weer normaal - herstelt vanzelf over nog Y dag(en)
als dit aanhoudt" — in plaats van alleen een kale "mogelijk defect"-
melding zonder aan te geven of het een vers, actief probleem is of al
bezig met zelfherstel.

**Getest** (3 nieuwe tests voor de auto-reset in
`test_nilm_cusum_outlier_cap.py`, 2 nieuwe voor de diagnostiek-context
in `test_diagnostic_summary.py`): reset na aanhoudende terugkeer naar
normaal; de streak-teller reset correct bij een onderbreking; geen
onbedoelde reset zonder actief alarm; herstelvoortgang wordt getoond
bij een lopende streak; geen melding zonder streak.

## Drie verbeteringen naar aanleiding van het Live-tabblad (v0.63.99)

Het nieuwe Live-tabblad (v0.63.97) leverde meteen concrete input op: 51
onbevestigde NILM-kandidaten, 18 waarschijnlijke duplicaatparen, en 6
aanhoudend "mogelijk defect"-apparaten. Op verzoek ("de integratie moet
eigenlijk met de minuut beter worden") alle drie opgepakt.

### 1 & 2. Zichtbaarheid voor onbevestigde kandidaten en duplicaten

Beide datasets bestonden al (`kandidaten`-attribuut,
`waarschijnlijke_duplicaten`), maar stonden nergens op het dashboard —
alleen bereikbaar via diagnostiek. Twee nieuwe markdown-tabellen op het
Apparaten-tabblad:
- **Onbevestigde NILM-kandidaten** (voorbeeld van max 20 van het
  totaal, met naam + huidig vermogen) — voor efficiëntere, holistische
  beoordeling in plaats van één-voor-één via de bevestig/negeer-kaart.
- **Waarschijnlijke NILM-duplicaten** — elk paar met gedeelde-dagen-
  telling, plus een concrete verwijzing naar de juiste service
  (`reject_nilm_device`, permanent uitsluiten — niet
  `unconfirm_nilm_device`, die laat een apparaat juist terugkomen).

### 3. CUSUM-uitschieter-plafond

**Root cause, gevonden via herberekening van de bestaande formule**:
een geïsoleerde uitschieterdag (bijv. een eenmalige 45W-meting tegen
een referentie van 6,2W — mogelijk extra warmwaterverbruik) leverde
zonder plafond een **ongeplafonneerde** bijdrage van >6 aan de CUSUM-
accumulator in één klap — ver boven de alarmdrempel (1,0) — en liet
het alarm daardoor langdurig afgaan, ook al was het structurele
gemiddelde over de hele periode maar +2,4%.

**Fix**: nieuwe constante `NILM_CUSUM_MAX_DAILY_CONTRIBUTION` (0,5) —
begrenst hoeveel één enkele dag maximaal aan de accumulator mag
bijdragen. Een structurele, aanhoudende afwijking (die dag na dag
boven de marge blijft) bouwt de accumulator nog steeds normaal op en
laat het alarm terecht afgaan; een eenmalige uitschieter niet meer in
zijn eentje. Alleen de positieve kant is begrensd — een dag met
ongewoon lage meting (die de accumulator omlaag trekt) blijft
ongeplafonneerd, want dat kan nooit de oorzaak van een onterecht alarm
zijn.

**Let op voor bestaande installaties**: deze fix corrigeert de
berekening voor toekomstige dagen, maar herberekent de **al
opgeslagen** accumulator-waarde niet met terugwerkende kracht. Een
apparaat dat nu al "mogelijk defect" toont vanwege een oude uitschieter
zal dus nog enkele dagen nodig hebben om via de normale afbouw
(dagen onder de marge) vanzelf weer onder de alarmdrempel te zakken -
of gebruik `unconfirm_nilm_device` voor een meteen schone lei.

**Getest** (3 nieuwe tests, `test_nilm_cusum_outlier_cap.py`): een
enkele geïsoleerde uitschieter triggert het alarm niet meer; een
structurele, aanhoudende afwijking triggert het nog steeds terecht;
een negatieve afwijking blijft ongeplafonneerd.

## Water-sessiedetectie: live event-driven i.p.v. tick-gebaseerd (v0.63.98)

Gerapporteerd met screenshot + aangeleverde ruwe sensorgeschiedenis:
"in de tabel ontbreekt mijn inziens data" — het dagtotaal (60,87L)
klopte, maar "Recente gebruiksmomenten" toonde slechts 1 sessie terwijl
de ruwe geschiedenis 64 losse verbruiksstoten liet zien.

**Root cause**: de oorspronkelijke sessiedetectie las het live debiet
uitsluitend op de gewone 5-minuten-tick. Analyse van de aangeleverde
ruwe geschiedenis liet zien dat verbruiksstoten vaak maar 15-90
seconden duren (handen wassen, toilet doorspoelen) — een steekproef
elke 5 minuten heeft simpelweg te weinig kans om zo'n kort venster te
raken, dus werden vrijwel alle stoten volledig gemist. Het dagtotaal
bleef wél correct, omdat dat van een aparte, cumulatieve tellersensor
komt (nooit iets mist, ongeacht timing).

**Bredere relevantie, op verzoek onderzocht**: apparaat-tracking
(vaatwasser/wasmachine, uren lang) en NILM (dagelijkse gemiddelden)
zijn veel minder gevoelig voor dit probleem — die lopen lang genoeg dat
een 5-minuten-tick ze sowieso vangt. Alleen water is uniek kwetsbaar
door de extreem korte, losse stoten.

**Gekozen aanpak, na afweging** ("Wat gebeurt er als we naar live
tikken gaan?"): een hybride, geen pure event-driven oplossing. Onderzoek
van de ruwe sensorgeschiedenis liet gaten tot bijna 7 uur zien tussen
updates zolang het debiet stil op 0 staat — de sensor "hartslag"-t niet
betrouwbaar bij rust. Een pure event-driven afronding zou daardoor een
sessie soms uren kunnen laten "vastzitten".

**Fix**: nieuwe, gedeelde `_process_water_flow_sample(flow, now)` —
dezelfde toestandsmachine als voorheen, nu aangeroepen vanuit twee
plekken:
1. **Live listener** (`_handle_water_flow_change`, nieuw
   `async_track_state_change_event` op de watersensor) — reageert
   direct op élke wijziging, vangt zo vrijwel elke stoot nauwkeurig
   (start + volume), ongeacht duur.
2. **De bestaande 5-minuten-tick** (`_update_water_tracking`) — blijft
   als vangnet draaien voor de *afronding* van een sessie, zodat niets
   vast kan blijven staan wachtend op een event dat mogelijk uren niet
   komt.

**Getest** (6 nieuwe tests, `test_water_live_tracking.py`): een
stoot van 20 seconden (het exacte scenario uit het rapport) wordt via
de listener correct gedetecteerd; de tick rondt een sessie alsnog af
als er geen verdere events meer binnenkomen; ongeldige/lege state-
waarden worden veilig genegeerd; de listener wordt alleen geregistreerd
als er een watersensor is geconfigureerd.

## Nieuw "Live"-tabblad: lopend verhaal over wat de integratie doet (v0.63.97)

Gevraagd: "een tabblad wat live vertelt wat de gehele integratie doet,
dit om mijzelf ook bewuster te maken wat er gebeurt op alle vlakken en
mogelijk weer extra input aan jou kan geven." Op verzoek server-side
gegenereerd (niet losse dashboard-teksten aan elkaar geplakt) voor een
écht vloeiend verhaal.

**Ontwerp**: nieuwe `get_live_narrative(now)` combineert bestaande
state uit meerdere onderdelen tot één lopend verhaal, elk met een
eigen, apart testbare deelfunctie:
- `_narrate_battery_decision` — hergebruikt de al bestaande, rijke
  `last_explanation` als kernalinea (geen tekst dupliceren).
- `_narrate_appliances` — meldt een lopende vaatwasser/wasmachine-
  cyclus, met hoelang al.
- `_narrate_water` — actief waterverbruik, of anders het dagtotaal.
- `_narrate_nilm` — openstaande onbeoordeelde kandidaten en mogelijk
  defecte apparaten.
- `_narrate_climate` — de klimaat-projectie-status of verwachte
  temperatuur over een uur.
- `_narrate_attention` — sluit af met eventuele aandachtspunten uit de
  bestaande gezondheidscheck-samenvatting (v0.63.91).

Puur informatief/samenvattend — herformuleert en combineert bestaande
state, berekent zelf niets nieuws en stuurt niets aan.

**Nieuwe sensor** `LiveNarrativeSensor`
(`sensor.woonkamer_energy_management_system_wat_doet_de_integratie_nu`) —
state afgekapt op 255 tekens (HA's limiet), het volledige verhaal staat
altijd in het `verhaal`-attribuut. Niet een RestoreEntity — elke tick
vers herberekend uit levende state, net als de Advies-gereedheid-
sensor. Toegevoegd aan diagnostiek.

**Nieuw dashboardtabblad "Live"** — toont het volledige verhaal in
gewone tekst.

**Getest**: 14 tests voor de verhaal-generator zelf (elk onderdeel
apart, inclusief correcte grammatica bij 1 vs. meerdere NILM-
kandidaten), 2 voor de sensor (afkapping + volledige tekst als
attribuut).

## Uitschieter-filter voor de achtertuinsensor (v0.63.96)

Gerapporteerd met grafiek: de nieuwe achtertuinsensor (v0.63.95) kan 's
ochtends kort in direct zonlicht hangen, wat een plotselinge,
kortstondige sprong in de gemeten temperatuur veroorzaakt — de
sensorbehuizing warmt zelf op, los van de werkelijke luchttemperatuur.
Zonder filtering zou dit zowel het live-anker als de bias-leer-
geschiedenis (v0.63.95) kunnen vervuilen.

**Ontwerp**: een sprong die de plausibele afkoel/opwarm-snelheid van
buitenlucht (`BACKYARD_TEMP_MAX_PLAUSIBLE_RATE_C_PER_HOUR`, 4°C/uur)
ver overschrijdt, wordt niet meteen vertrouwd — de vorige,
geaccepteerde waarde blijft gelden totdat de nieuwe waarde minstens
`BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES` (45 min) aanhoudt (binnen een
kleine tolerantiemarge, `BACKYARD_TEMP_SPIKE_TOLERANCE_C`, zodat kleine
meetruis tijdens het wachten de teller niet steeds laat resetten). Een
kortstondige zonneflits zakt vanzelf terug voordat dit venster
verstrijkt en wordt dan genegeerd; een echte, aanhoudende verandering
(bijv. een koufront) wordt na dit venster alsnog geaccepteerd — dit
filtert dus ruis, het bevriest de meting niet permanent.

Nieuwe, gedeelde `_get_filtered_backyard_temp_c(now)` — zowel het
live-anker (`_get_live_outdoor_temp_c`) als de bias-sample-berekening
(v0.63.95) lopen nu door dit filter, zodat beide mechanismen
consistent beschermd zijn tegen dezelfde soort uitschieters.

**Bewust géén RestoreEntity** voor de filter-state zelf (vergelijkbaar
met `sensor_health_score` eerder deze sessie) — de tijdschalen hier
zijn kort (minuten tot ~45 min), dus een reset bij herstart is een
verwaarloosbaar, kortstondig verlies, niet de moeite van extra
complexiteit waard.

**Zichtbaarheid**: nieuwe waarschuwingskaart op het dashboard, alleen
zichtbaar wanneer een uitschieter daadwerkelijk wordt genegeerd. Nieuw
attribuut `achtertuinsensor_uitschieter_genegeerd` op de klimaat-
projectie-sensor. Toegevoegd aan diagnostiek.

**Getest** (5 nieuwe tests): eerste meting wordt direct geaccepteerd;
een plausibele, geleidelijke verandering wordt direct geaccepteerd;
een kortstondige zonneflits wordt genegeerd (en de vorige waarde blijft
gelden) totdat die zelf weer terugzakt; een aanhoudende verandering
wordt na het bevestigingsvenster alsnog geaccepteerd; geen filter-
activiteit zonder geconfigureerde achtertuinsensor.

## Achtertuinsensor + geleerde bias-correctie voor de klimaat-projectie (v0.63.95)

Gevraagd: "zijn er zaken waardoor ik de voorspelling kan verbeteren,
door bijvoorbeeld correlaties? Ik heb ook een temperatuursensor in
mijn achtertuin hangen." Combinatie van twee complementaire
verbeteringen, beide gebouwd.

### 1. Achtertuinsensor als voorkeursbron voor de live temperatuur

`_get_live_outdoor_temp_c()` gebruikt nu, indien geconfigureerd
(`backyard_temperature_sensor_entity`), eerst de eigen fysieke
achtertuinsensor — een lokale meting is nauwkeuriger voor de eigen
locatie dan een regionale weerentiteit-schatting (relevant na de
v0.63.93-ervaring, waar de weerentiteit een significante afwijking
bleek te hebben). Valt terug op KNMI/OpenWeatherMap als er geen
achtertuinsensor is geconfigureerd of niet uitleesbaar is — volledig
optioneel, geen breaking change.

### 2. Geleerde bias-correctie op de hele 24-uurs-voorspelling

De 24-uurs-*projectie* blijft noodzakelijkerwijs van de weerentiteit
komen (een fysieke sensor kan de toekomst niet voorspellen), maar de
**nauwkeurigheid** van die voorspelling kan wél systematisch worden
gecorrigeerd. Elke keer dat de voorspelling ververst wordt (maximaal
1x per `CLIMATE_FORECAST_FETCH_INTERVAL_MINUTES`, 30 min), wordt de
eerstvolgende voorspelde waarde vergeleken met de actuele
achtertuinsensor-meting op datzelfde moment. Dat verschil (°C,
additief — temperatuur kent geen natuurlijke nulpuntschaal waarop een
percentage zinvol zou zijn, dus bewust geen procentuele correctie
zoals bij de zonvoorspelling) wordt bijgehouden in een rollend venster
(`CLIMATE_FORECAST_BIAS_HISTORY_LENGTH`, 100 samples) en toegepast op
**elk uur** van de projectie, niet alleen het startpunt — corrigeert zo
systematisch voor een structurele afwijking van de geconfigureerde
weerbron/locatie. Vereist minimaal 5 samples
(`CLIMATE_FORECAST_BIAS_MIN_SAMPLES`) voordat de correctie actief
wordt; een bias uit te weinig samples is zelf onbetrouwbaar.

**Zichtbaarheid**: nieuwe dashboardtegel toont de huidige geleerde
bias + het aantal samples waarop die is gebaseerd. Nieuwe attributen
op de bestaande klimaat-projectie-sensor (`voorspelling_bias_c`,
`voorspelling_bias_geschiedenis`) — RestoreEntity, overleeft een
herstart. Toegevoegd aan diagnostiek.

**Getest** (14 nieuwe tests, `test_climate_tab.py`): achtertuinsensor
krijgt voorrang boven de weerentiteiten; correcte terugval zonder
achtertuinsensor-meting; geen bias-sample zonder geconfigureerde
sensor; geleerde bias is `None` bij te weinig samples; gemiddelde-
berekening klopt; geschiedenis wordt afgekapt tot het maximum; en de
correctie werkt daadwerkelijk door op de héle trajectory (niet alleen
het startpunt) — inclusief welke geleerde rate-cel per uur wordt
opgezocht.

## Twee klimaat-tabellen toonden dezelfde betrouwbaarheid (v0.63.94)

Gerapporteerd met screenshot: "de 2 tabellen lijken hetzelfde weer te
geven." De "Woonkamer (°C)"-kolom verschilde inderdaad al correct
tussen de twee tabellen, maar de "Betrouwbaarheid"-kolom niet — beide
lazen hetzelfde, enkele `betrouwbaarheid`-veld (het niveau voor de
soepele "kort termijn"-drempel, ≥5 metingen). Een cel met bijv. 8
metingen toonde daardoor `🟡 indicatief` in **beide** tabellen — ook in
de tabel die specifiek ≥15 metingen belooft, terwijl die daar
`⚪ onvoldoende_data` had moeten tonen (8 < 15).

**Fix**: nieuw, apart veld `betrouwbaarheid_streng` per traject-rij —
alleen `betrouwbaar` als de ≥15-drempel écht gehaald is, anders altijd
`onvoldoende_data` (nooit `indicatief`, dat zou in de strenge tabel
alsnog de verkeerde indruk wekken). De "Betrouwbaar"-tabel gebruikt nu
dit nieuwe veld; de "Korte termijn"-tabel blijft ongewijzigd het
bestaande `betrouwbaarheid`-veld gebruiken.

**Getest**: nieuwe test bevestigt dat een cel met 8 metingen
(indicatief, niet betrouwbaar) `betrouwbaarheid_streng` op
`onvoldoende_data` zet. Testdata voor de klimaat-projectietabellen
toegevoegd aan de dashboard-render-test (voorheen werd alleen het lege
pad getest) — bevestigt nu ook zichtbaar dat beide tabellen bij
dezelfde onderliggende rij een andere betrouwbaarheidsstatus tonen.

## Buitentemperatuur-voorspelling klopte niet + tijdzone-bug blootgelegd (v0.63.93)

Gerapporteerd: "de temperature verwachting van KNMI klopt niet in de
tabellen, het is nu 15.3 graden en in de tabellen wordt 23
weergegeven". Uitgezocht met een live `weather.get_forecasts`-aanroep
op de daadwerkelijke KNMI-entiteit (`weather.knmi_thuis`) — bleek geen
verwerkingsfout in deze integratie: de ruwe KNMI-data zelf toonde al
23°C voor het eerstvolgende uur, tegenover een live meting van 15,3°C
— een sprong die weerkundig niet klopt. Root cause: de brondata van
deze specifieke KNMI-integratie zelf, niet mijn code.

**Oplossing, op initiatief van de gebruiker**: overgestapt naar een
nauwkeurigere weerentiteit (`weather.forecast_thuis`), waarvan de
eerste voorspelling (15,9°C) wél goed aansloot bij de live meting.

**Tijdens het vergelijken een échte, latente bug blootgelegd**: de
nieuwe bron rapporteert tijdstippen in UTC (`+00:00`), terwijl KNMI
toevallig al in lokale tijd (`+02:00`) rapporteerde. De code zette de
ontvangen tijdstempel nergens expliciet om naar lokale tijd
(`hour_dt.isoformat()` rechtstreeks op de geparste waarde) — dit werkte
dus tot nu toe alleen "toevallig" goed omdat KNMI zelf al lokale tijd
gebruikte. Met de nieuwe, UTC-gebaseerde bron zou de "Uur"-kolom op het
dashboard 2 uur hebben achtergelopen op de werkelijke lokale tijd.

**Fix**: `dt_util.as_local()` toegepast direct na het parsen, in
`_async_fetch_hourly_outdoor_forecast` — ongeacht welke tijdzone de
brondata zelf gebruikt, dus niet langer afhankelijk van toeval bij een
specifieke weerintegratie.

**Getest**: nieuwe test bevestigt dat de tijdzone-conversie
daadwerkelijk wordt aangeroepen voor elke geparste voorspellings-
entry.

## Woonkamertemperatuur: absurd veel decimalen op het dashboard (v0.63.92)

Gerapporteerd met screenshot: de live woonkamertemperatuur toonde
`24.1230773925781 °C` op het Klimaat-tabblad, in twee losse tegels
tegelijk ("Woonkamertemperatuur (live)" en "Airco-verwachting").

**Root cause**: `living_room_current_temp_c` wordt nergens afgerond bij
toewijzing (`_update_living_room_airco_prediction`) — de onderliggende
temperatuursensor rapporteert zelf met hoge precisie (bijv. een
Zigbee-sensor). De buitentemperatuur toonde wél netjes afgerond, omdat
die via de weerentiteit binnenkomt (die zelf al op 1 decimaal
rapporteert). Beide dashboardtegels bleken bij nader inzien dezelfde
onderliggende, ongeronde coordinator-waarde te lezen — één root cause,
niet twee losse problemen.

**Fix**: afgerond op 1 decimaal bij toewijzing, consistent met elke
andere temperatuurweergave in deze integratie.

**Getest**: nieuwe test bevestigt dat een sensorwaarde met 13 decimalen
correct wordt afgerond naar 1 decimaal.

## Vier verbeteringen na de diagnostiek-review (v0.63.91)

Op de vraag "zijn er nog zaken om de integratie te verbeteren, dus
bijvoorbeeld de diagnostiek gedetailleerder maken" — vier concrete
verbeteringen, alle vier gebouwd ("integratie moet alleen maar beter
kunnen worden").

### 1. Snelle gezondheidscheck-samenvatting

Nieuwe `get_diagnostic_summary()`, bovenaan elke diagnostiek-export
(`diagnostic_summary`). Verzamelt een korte lijst "aandachtspunten" uit
bestaande, al berekende signalen (sensor-gezondheid, mogelijk-defecte
NILM-apparaten, NILM-duplicaten, recente tekort-dagen, sluipverbruik,
laatste fout) — `{"status": "nominaal"}` als niets opvalt, anders een
concrete lijst. Voorkomt dat een toekomstige review weer 150+ velden
handmatig moet doorlopen.

### 2. NILM-duplicaatdetectie

Naar aanleiding van de 5 "Eetkamer lamp"-sensoren die een identieke
vermogensgeschiedenis bleken te delen. Nieuwe
`get_nilm_duplicate_pairs()`: vergelijkt elk paar bevestigde apparaten
op hun `daily_avg_history` over de gedeelde dagen — binnen een kleine
tolerantie (`NILM_DUPLICATE_TOLERANCE_FRACTION`, 2%) en met genoeg
gedeelde dagen (`NILM_DUPLICATE_MIN_SHARED_DAYS`, 3) geldt een paar als
waarschijnlijk duplicaat. Puur informatief — de gebruiker beslist zelf
of/welk apparaat af te wijzen. Blootgesteld via de bestaande NILM-
sensor (`waarschijnlijke_duplicaten`) en diagnostiek.

### 3. Advies-gereedheid uitgebreid naar 10 modules

De bestaande "Advies-gereedheid"-sensor beoordeelde tot nu toe 8
modules; de nieuwe extra-dip-marge (v0.63.87) en temperatuur-regressie
(v0.63.88) hadden nog geen gereedheidsstatus. Zelfde patroon als de
overige modules met een genuine data-maturiteitssignaal: `klaar` zodra
er genoeg samples zijn (3 voor de marge-trend, `TEMP_CONSUMPTION_MIN_
SAMPLES` voor de temperatuur-regressie), anders `onvoldoende_data`.
Sensor hernoemd naar "Advies-gereedheid (10 modules)".

### 4. Shortfall/excess-tracking samengevoegd tot één atomische structuur

De vier losse lijsten (`reserve_shortfall_history`/`_dates`,
`reserve_excess_history`/`_dates`) — die tijdens de diagnostiek-review
een schijnbare desynchronisatie leken te tonen (bleek uiteindelijk geen
actieve bug, wel een structuur die gevoelig is voor toekomstige,
per-ongeluk-uit-sync-lopende uitbreidingen) — zijn vervangen door één
`reserve_daily_records`-lijst (dicts met datum + shortfall + excess
samen, altijd atomisch toegevoegd). De vier oude namen bestaan nog als
afgeleide, read-only properties voor volledige achterwaartse
compatibiliteit met bestaande sensoren/diagnostiek-attributen.

**Restore-subtiliteit**: twee aparte sensoren (`ReserveShortfallSensor`,
`ReserveExcessSensor`) herstellen elk hun eigen helft van de data, in
een volgorde die HA niet garandeert. Nieuwe
`_merge_reserve_daily_records()`-hulpfunctie in `sensor.py` merget
beide herstelacties correct samen (op datum), ongeacht welke sensor
als eerste herstelt — zonder dat de een de al herstelde data van de
ander overschrijft.

**Getest**: 6 nieuwe tests voor de refactor (afgeleide properties,
atomische toevoeging, leervenster-afkapping, en drie voor de merge-
functie inclusief beide restore-volgordes), 9 voor de gezondheidscheck-
samenvatting, 7 voor de NILM-duplicaatdetectie, 4 voor de uitgebreide
advies-gereedheid.

## NILM-trendlabel: misleidend percentage naast "stijgend" (v0.63.90)

Gevonden tijdens een grondige analyse van een aangeleverd diagnostiek-
bestand (op verzoek: "wil je het gehele statistiek bestand nakijken,
dan hoeft ik HA niet zo vaak te herstarten"): 5 "Eetkamer lamp"-
sensoren toonden `⚠️ aanhoudend stijgend (-0%) - mogelijk defect` — een
negatief/nul percentage naast het woord "stijgend".

**Verklaring**: de CUSUM-detector is bewust **eenzijdig** (accumuleert
alleen bij afwijkingen boven de referentie, geklemd op minimaal 0) —
dus "stijgend" is conceptueel altijd correct zodra het alarm afgaat.
Maar het getoonde percentage (`estimated_drift_percent`) is puur de
afwijking van de **laatste dag** — die kan toevallig rond nul liggen,
ook al was de opgebouwde geschiedenis (over meerdere eerdere dagen)
wél voldoende om het alarm te triggeren. Dat maakt een niet-positief
getal naast "stijgend" misleidend/tegenstrijdig ogend.

**Fix**: het percentage wordt nu alleen getoond als het ook echt een
stijging weergeeft (`drift > 0`); bij een niet-positieve waarde toont
het label gewoon "⚠️ aanhoudend stijgend - mogelijk defect" zonder het
verwarrende getal.

**Bijkomende observatie, geen bug**: de 5 betrokken "Eetkamer lamp"-
sensoren delen een identieke vermogensgeschiedenis — vermoedelijk 5
HA-entiteiten die hetzelfde fysieke circuit rapporteren. Geen actie
vereist, maar het overwegen waard om er een paar af te wijzen voor een
overzichtelijkere lijst.

**Ook onderzocht tijdens dezelfde analyse, bevestigd géén bug**: twee
schijnbaar tegenstrijdige "veiligheidsmarge"-percentages
(energiebrug-check's vaste 15% vs. de dynamische ontlaadreserve's
10-32%) bleken twee daadwerkelijk verschillende, bewust gescheiden
mechanismen te zijn (zie `_get_dynamic_discharge_reserve_kwh`'s eigen
docstring) — de ene beantwoordt "is het veilig om nu niet bij te
laden", de andere "hoeveel mag ik nu veilig ontladen", bewust met een
andere scope (wel/niet rekening houden met latere dure kwartieren
vandaag). Op uitdrukkelijk verzoek ongewijzigd gelaten.

**Getest**: bestaande NILM-tabeltest uitgebreid met een gerichte test
voor het niet-positieve-drift-scenario.

## NILM structurele naampatroon-uitsluiting (v0.63.89)

Gerapporteerd: "de afgewezen NILM apparaten komen bij elke herstart
terug". Onderzocht met een volledige diagnostiek-export (niet de
afgekapte dashboard-preview) — bleek **geen bug**: de daadwerkelijk
afgewezen entiteit (`sensor.aquarium_jill_vermogen_fase_1`) stond
correct en blijvend in de volledige `nilm_rejected_entities`-lijst. Wat
de gebruiker zag terugkomen was "Aquarium Jill Vermogen" zelf — een
apparaat dat destijds was **bevestigd**, niet afgewezen, en dus
terecht altijd in de "Bevestigde apparaten"-lijst blijft staan (dat is
precies wat bevestigen betekent).

Vervolgvraag: "alles waar fase 1 bij staat mag sowieso uitgesloten
worden net als solaredge en zendure entiteiten" — een structurele
uitsluiting in plaats van losse afwijzingen per sub-fase-sensor of
accu-/omvormer-signaal.

**Nieuwe, aparte uitsluitingslaag** (`_is_nilm_pattern_excluded`,
substring-match tegen zowel entity_id als friendly_name, kleine
letters): `fase 1`, `fase_1`, `solaredge`, `zendure`
(`NILM_PATTERN_EXCLUDED_KEYWORDS`) - naast de bestaande, exacte-match
uitsluiting van specifiek geconfigureerde entiteiten
(`_nilm_excluded_entity_ids`).

**Ruimt ook met terugwerkende kracht op**: `_prune_nilm_pattern_
excluded_entries()` draait één keer per tick, vóór de discovery-scan
zelf, en verwijdert alles wat al in de kandidaten-, bevestigde- of
afgewezen-lijst stond en nu aan het patroon voldoet - niet alleen
nieuw ontdekte entiteiten vanaf nu. Eerder afgewezen entiteiten die nu
patroon-uitgesloten zijn, worden ook uit de aparte
`nilm_rejected_entities`-lijst verwijderd (overbodig geworden, houdt
die lijst klein en betekenisvol).

**Getest** (8 permanente tests, `test_nilm_pattern_exclusion.py`):
fase_1 in entity_id/friendly_name uitgesloten; solaredge/zendure
uitgesloten; niet-gerelateerde sensoren blijven werken; bestaande
kandidaten/bevestigde/afgewezen entiteiten die aan het patroon voldoen
worden met terugwerkende kracht opgeruimd.

## Model- en parameternauwkeurigheid — trends (v0.63.88)

Gevraagd: "wel wil ik allerlei waardes welke je nu hebt toegevoegd ook
inzicht zien op het dashboard met trends of ze naar beneden of naar
boven gaan en wat het verschil in % over tijd is dus of het
model/parameter nauwkeuriger wordt."

**Gedeelde `_compute_trend_summary()`-helper**: een kleinste-
kwadraten-regressielijn door een korte tijdreeks — statistisch de meest
verdedigbare manier om een genuine trend te detecteren, in plaats van
simpelweg de nieuwste met de oudste waarde te vergelijken (te gevoelig
voor één toevallig ruizig datapunt aan een van beide uiteinden).
Gebruikt alle beschikbare punten; rapporteert het %-verschil dat de
gefitte lijn impliceert van begin tot eind van het venster.

**Belangrijke, tijdens het testen ontdekte statistische nuance**: een
regressielijn is juist gevoelig voor een uitschieter precies áán het
uiteinde van de reeks (een bekende "leverage"-eigenschap) — robuuster
dan een naïeve 2-punts-vergelijking in het algemeen, maar geen
wondermiddel tegen elke soort ruis. Documenteerd in de tests zodat dit
niet opnieuw als verrassing opduikt.

Toegepast op drie nieuwe metrics uit deze release, elk met een eigen,
dagelijks bijgehouden geschiedenis:
1. **Zonvoorspelling-spreiding** (`deviation_stdev_history`) — wordt de
   voorspelling consistenter (dalend) of wisselvalliger (stijgend)?
2. **Extra-dip-laadmarge** (`extra_dip_margin_history`) — hoeveel marge
   is er typisch beschikbaar, en verandert dat?
3. **Temperatuur-regressie-nauwkeurigheid**
   (`temp_consumption_prediction_error_history`) — wordt de
   voorspelling nauwkeuriger over tijd (dalend = beter)?

Alle drie gebundeld in de nieuwe sensor
`sensor.woonkamer_energy_management_system_model_en_parameternauwkeurigheid`,
met een eigen dashboardkaart op het Advies-tabblad. RestoreEntity — de
onderliggende geschiedenissen overleven een herstart (deviation_stdev_
history piggybackt op de bestaande `PvForecastAccuracySensor`-restore,
naast `deviation_history` zelf).

## Temperatuur-verbruik-regressie voor extreme-koude-dagen (v0.63.88)

Uitgebreid besproken en ontworpen door de gebruiker, als vervolg op de
extreme-koude-dag-analyse. **Bewust puur adviserend voor nu**
("eerst observeren" — expliciet zo afgesproken) — beïnvloedt de
bestaande reserve-/dieptekort-berekening nog op geen enkele manier.

**Data verzamelen**: tijdens hetzelfde nachtvenster waar het
verbruik al wordt gevolgd (`_update_night_consumption_tracking`),
wordt nu ook de buitentemperatuur meegesampled (hergebruikt de
bestaande `_get_live_outdoor_temp_c()`, geen nieuwe sensor-
configuratie nodig). Bij afsluiten van het venster wordt het
(gemiddelde temperatuur, totaal verbruik)-paar toegevoegd aan
`temp_consumption_history` (rollend venster,
`LEARNING_HISTORY_DAYS`).

**Regressie**: een gedeelde `_ols_fit()`-helper (gewone kleinste-
kwadraten) door de (temperatuur, verbruik)-paren, vanaf minimaal 4
samples (`TEMP_CONSUMPTION_MIN_SAMPLES`).

**Eerlijke, niet-lekkende validatie**: bij het afsluiten van elk
nachtvenster wordt éérst — met de geschiedenis zoals die vóór die
nacht al bekend was — voorspeld wat die nacht had moeten kosten, pas
dáárna wordt het nieuwe paar zelf toegevoegd. Zo meet
`temp_consumption_prediction_error_history` een eerlijke validatie
(voorspellen met wat toen al bekend was), niet een achteraf-passende
schijnnauwkeurigheid.

`last_temp_consumption_note` toont in gewone taal wat er is voorspeld
vs. wat er werkelijk gebeurde, elke nacht.

## Extra-dip laden op weinig-zon-dagen (v0.63.87)

Uitgebreid besproken en ontworpen door de gebruiker, naar aanleiding
van een extreme-koude-dag-analyse (11 januari 2026, laagste
etmaalgemiddelde van het jaar, -4,1 °C).

**Aanleiding**: sinds v0.63.77 laadt het systeem tijdens een
weinig-zon-dag alleen nog gedwongen bij binnen het ene, hoofd-goedkope
blok van de dag (`should_force_charge`). Een aparte, losse prijsdip
elders die dag werd volledig genegeerd, ook al zou bijladen daar
aantoonbaar voordeliger zijn dan wachten — een direct, onbedoeld
neveneffect van het volledig verwijderen van het oude arbitrage-
mechanisme.

**Ontwerp, na uitgebreide discussie**:
- Alleen relevant wanneer `_is_low_solar_expected()` al `True` is
  (dezelfde genuine behoefte als het hoofdblok) én we ons **buiten**
  het hoofdblok bevinden.
- Rendement-gecorrigeerde marge-check (net als het oude, verwijderde
  arbitrage-mechanisme): `geleerde_efficiëntie × beste-resterende-prijs-
  vandaag − huidige-prijs ≥ 0,03 €/kWh`
  (`LOW_SOLAR_EXTRA_DIP_MIN_MARGIN_EUR_PER_KWH`). Gebruikt dezelfde
  `learned_battery_efficiency_percent` die al continu op de achtergrond
  wordt bijgehouden (elke tick, ongeacht reden), met terugval op de
  geconfigureerde `battery_round_trip_efficiency_percent`.
- Bewust **géén** rendement-check op het bestaande hoofdblok zelf
  (expliciet zo besloten) — dat is al per definitie het goedkoopste
  moment van de dag.
- Laadt met hetzelfde vaste `manual_charge_power` als het hoofdblok.
- Zet ook de winter-guard-vlag (`_grid_charged_today`) — deze energie
  wordt om dezelfde reden gekocht (genuine behoefte bij weinig zon),
  dus mag ook niet diezelfde dag worden terugverkocht.
- **Belangrijke correctie tijdens het bouwen**: de vlag-poort was
  aanvankelijk `not self._grid_charged_today` — maar op een
  weinig-zon-dag heeft het hoofdblok (vroeg op de dag) die vlag vrijwel
  altijd al gezet, wat dit mechanisme in de praktijk onbereikbaar zou
  maken. De vlag onderdrukt alleen **verkopen** later, niet verdere
  **legitieme** lading — dus de poort is uitsluitend
  `is_low_solar and not in_cheap_block` (plus de marge-check).
- Eigen reden-label `grid_charging_low_solar_extra_dip`, met een eigen
  uitlegtekst-tak (toont de berekende marge).

**Belangrijke test-subtiliteit** (relevant bij toekomstig onderhoud):
`_cheapest_block_range()` kijkt alleen naar *toekomstige* prijzen vanaf
"nu". Zodra "nu" het oorspronkelijke hoofdblok is gepasseerd, telt dat
niet meer mee als "upcoming" — zonder een nóg-goedkopere stretch later
die dag zou het huidige testmoment zélf als (nieuw) hoofdblok worden
herkend. Tests simuleren daarom bewust een prijspatroon met een latere,
nóg goedkopere stretch, zodat het extra-dip-mechanisme specifiek wordt
beproefd in plaats van het hoofdblok opnieuw te raken.

## Spreidingsgebaseerde "weinig zon"-drempel (v0.63.87)

Eveneens uitgebreid besproken: de fractie die bepaalt of de geleerde
"typische dag" als "weinig zon" geldt (`LOW_SOLAR_RELATIVE_FRACTION`)
was een vaste 40%. Nu beweegt die mee met hoe **consistent** de
(bias-gecorrigeerde) voorspelling recent is gebleken, via de
standaarddeviatie van de al bestaande `deviation_history` (tot nu toe
alleen gebruikt voor het gemiddelde/de systematische bias, niet voor de
spreiding).

Drie vaste, uitlegbare niveaus (bewust geen continue formule, "black
box", consistent met de rest van deze integratie):
```
stdev(deviation_history) < 10%  → fractie 0,6 (consistente voorspelling, ruimer vertrouwen)
stdev(deviation_history) 10–25% → fractie 0,4 (huidige, voorzichtige standaard)
stdev(deviation_history) > 25%  → fractie 0,3 (onbetrouwbaar, extra conservatief)
```
Vereist minimaal 5 samples (`MIN_SOLAR_HISTORY_FOR_SPREAD_BASED_FRACTION`)
voor een betrouwbare standaarddeviatie — met minder valt het terug op de
vaste 40%.

**Doorgesproken alternatieven, bewust niet gebouwd**: de gebruiker gaf
een uitgebreide lijst statistische methoden (procesprestaties,
hypothesetoetsen, SPC-kaarten, DOE, Gage R&R, FMEA/Weibull) om te
overwegen. Beoordeeld en verworpen: process capability/SPC vereisen
formele specificatiegrenzen die hier niet natuurlijk bestaan;
hypothesetoetsen hebben te weinig power bij 7-30 dagsamples;
DOE vereist actief experimenteren (dit systeem observeert alleen
passief); Gage R&R valideert meetsystemen zelf (niet relevant, sensor-
waarden worden vertrouwd as-is); FMEA/Weibull vereisen kwalitatieve
risico-oefeningen resp. faaltijd-data die hier niet wordt bijgehouden.
Wél als kansrijk genoemd voor een vervolgstap: een eenvoudige
temperatuur-verbruik-regressie voor extreme-koude-dagen (nog niet
gebouwd).



Gevraagd: "Meldingen/tracking zoals bij vaatwasser/wasmachine" —
herzien na verduidelijking naar "geen meldingen alleen een watertabblad
met relevante info". Puur informatief: stuurt niets aan en heeft geen
enkele invloed op de accu-beslissing.

Twee onafhankelijke onderdelen:

1. **Dagelijks verbruik + geschiedenis** — volgt de geconfigureerde
   "vandaag"-sensor rechtstreeks (die zelf om middernacht reset, zoals
   bevestigd via de aangeleverde `last_reset`/`next_reset`-attributen).
   Zodra die sensor zelf reset (de uitlezing daalt t.o.v. de vorige
   meting), wordt de laatst bekende waarde gearchiveerd als "gisteren se
   totaal" — geen eigen reset-logica nodig, leunt op de brondata zelf.
2. **Losse gebruiksmomenten** — een RUSTEND/ACTIEF-toestandsmachine op
   het live debiet, hetzelfde principe als de vaatwasser/wasmachine-
   detectie (`_update_appliance_state_machine`), maar met eigen,
   lagere drempel (1 L/min — bewust laag: de gebruiker wil juist
   volledig inzicht, inclusief kleinere kranen en de nachtelijke
   waterontharder-regeneratie, een relatief kort, herkenbaar patroon
   van ongeveer 1x per 2 weken) en een kortere afrondingsmarge (2 min
   i.p.v. 5 — watergebruik heeft geen tussentijdse stille fases zoals
   een wasprogramma). Geschat volume per moment via het verschil in de
   optionele totaal-verbruiksensor tussen start en einde (nauwkeuriger
   dan het live debiet over de 5-minuten-tick-resolutie zelf
   integreren).

Configuratie: `water_active_usage_sensor_entity` (live debiet, L/min),
`water_daily_total_sensor_entity` (dagelijks totaal, reset zichzelf),
`water_total_usage_sensor_entity` (optioneel, all-time totaal, voor
volume-schatting per moment) — alle drie optioneel, niets wordt
bijgehouden zonder configuratie.

`sensor.woonkamer_energy_management_system_waterverbruik` toont het
live debiet als state, met als attributen: vandaag-totaal, gemiddelde
over de laatste dagen, trend-percentage, dag-geschiedenis, en de
recente gebruiksmomenten (nieuwste eerst). RestoreEntity — de
geschiedenis overleeft een herstart.

### Waterontharder-regeneratie herkennen (v0.63.86)

Gevraagd: "wanneer hij zijn werk heeft gedaan en hoelang dat geleden
is". Er is geen betrouwbare manier om de regeneratie puur op basis van
debiet of duur te onderscheiden van ander watergebruik — dat verschilt
per merk/model, en er is geen trainingsdata voor. In plaats daarvan:
elk afgerond gebruiksmoment dat **start binnen een nachtelijk venster**
(standaard middernacht–6 uur, `WATER_SOFTENER_NIGHT_WINDOW_START_HOUR`/
`_END_HOUR`) wordt aangemerkt als de waterontharder — niemand doucht of
vult structureel een bad midden in de nacht, dus tijdstip alleen is al
een betrouwbare indicator.

Elk gebruiksmoment in `recente_gebruiksmomenten` krijgt een
`waarschijnlijk_waterontharder`-vlag; het tijdstip van de laatst
herkende regeneratie staat apart in `waterontharder_laatste_regeneratie`
(ISO-tijdstip) op dezelfde sensor. Het dashboard toont dit als "Laatste
regeneratie: [datum/tijd] ([X] geleden)" via HA's eigen
`relative_time()`-functie, plus een 🧂-markering bij het betreffende
moment in de gebruiksmomenten-tabel.

## Sensor-gezondheid (energiebalans-validatie)

Optioneel, actief zodra zowel `available_energy_sensor_entity` als
`battery_power_sensor_entity` zijn geconfigureerd (v0.63.28) — geen
nieuwe sensoren nodig, puur een interne consistentiecontrole op wat er
al gemeten wordt.

Vergelijkt elke tick het batterijvermogen-sensor met wat de verandering
in beschikbare energie sinds de vorige tick **impliceert** dat het
vermogen geweest moet zijn. Een structurele afwijking is deels verwacht
(laad/ontlaad-rendementsverlies is niet 0) — dit is dus een
**signaal**, geen harde alarmering.

`sensor.sensor_health_score` (0-100%): het percentage van de laatste 20
metingen dat binnen `ENERGY_BALANCE_ERROR_BAD_THRESHOLD_W` (300W) bleef.
Een ontbrekende/niet-beschikbare sensorwaarde telt mee als "slecht" —
precies het soort fout die deze check moet vangen (een vastgelopen
sensor, verkeerde entity gekozen bij het instellen, een
eenheden-mismatch, of een tekenfout die `invert_battery_power_sign`
had moeten corrigeren maar niet deed). `measurement_quality` vertaalt
de score naar "goed" (≥80%) / "verminderd" (≥50%) / "slecht" (<50%).

Een herstart-grote onderbreking (>20 minuten sinds de vorige meting)
wordt overgeslagen in plaats van als fout geteld — net als bij de
uurprofiel-tracking zou dat anders ten onrechte een lange stilstand aan
één enkel vermogensniveau toeschrijven.

## Sluipverbruik-detectie (CUSUM)

Optioneel, actief zodra `consumption_power_sensor_entity` is
geconfigureerd (v0.63.29) — geen nieuwe sensoren nodig.

Volgt dagelijks het laagste gecorrigeerd-verbruik-moment (meestal diep
in de nacht, waar sluimer-/stand-by-verbruik domineert) en past daar een
klassieke **cumulatieve-som-controlekaart (CUSUM)** op toe — een
techniek die specifiek een **aanhoudende** verschuiving in een
gemiddelde detecteert, niet een losse uitschieter. Gebruikt bewust een
**langere, aparte geschiedenis** (`CUSUM_BASELINE_HISTORY_DAYS` = 30
dagen) dan de adaptieve 7-dagen-mediaan die de rest van de integratie
voor beslissingen gebruikt — die zou een langzame sluipende stijging
namelijk binnen een week stilzwijgend als "de nieuwe norm" opnemen,
precies het faalscenario dat CUSUM moet vangen.

- `CUSUM_SLACK_KW` (20W): een bewuste dode zone — normale ruis
  accumuleert niet.
- `CUSUM_ALARM_THRESHOLD_KW` (150W cumulatief): een kleine, geleidelijke
  afwijking heeft ongeveer een week nodig om te alarmeren; een grotere,
  plotselinge sprong (bijv. een nieuw sluimerend apparaat) alarmeert
  binnen een paar dagen.
- Referentie sluit de meest recente 5 dagen uit, zodat een lopende
  afwijking niet al in zijn eigen vergelijkingsbasis zit.
- Gepauzeerd tijdens vakantiemodus (kunstmatig laag verbruik zou de
  referentie vervuilen).

Stuurt een melding (via `appliance_notify_service`) zodra detectie voor
het eerst omslaat naar "gedetecteerd" — bewust **niet** elke dag
opnieuw zolang de afwijking aanhoudt, dat zou er alleen toe leiden dat
je 'm gaat negeren.

`sensor.sluipverbruik_detectie` toont "normaal" of "gedetecteerd", met
het geschatte verschil (W), de referentiewaarde, en de ruwe
CUSUM-accumulator als attributen.

## Weather ensemble (bewolkingsgraad-tegencheck)

Optioneel, actief zodra `knmi_weather_entity` en/of
`openweathermap_weather_entity` zijn geconfigureerd (v0.63.30) — geen
nieuwe API-koppelingen, alleen HA `weather`-entiteiten die je
waarschijnlijk al hebt via de KNMI- en/of OpenWeatherMap-integraties.

**Bewust géén vervangende PV-opbrengstschatting.** KNMI/OpenWeatherMap
geven algemeen weer (bewolkingsgraad), geen kant-en-klare kWh-opbrengst
zoals Solcast — om die twee eerlijk te combineren zijn paneelgegevens
nodig (oriëntatie, hellingshoek, wattpiek) die deze integratie niet
verzamelt. In plaats daarvan een directer verifieerbare vergelijking:

- **`sensor.weather_ensemble_bewolkingsgraad`**: het gemiddelde van de
  live `cloud_coverage`-attributen van de geconfigureerde bronnen, met
  een label (helder <30% / half bewolkt / bewolkt >70%).
- **Onenigheid-signaal**: vergelijkt je live PV-vermogen met wat
  Solcast voor **dit exacte moment** voorspelt. Presteert de PV fors
  onder de Solcast-voorspelling terwijl KNMI/OpenWeatherMap juist
  heldere lucht melden, dan wijst dat eerder op een paneel- of
  omvormer-kwestie dan op het weer — en wordt als zodanig gemeld.
  Andersom (beter dan verwacht ondanks gemelde zware bewolking) wordt
  ook gesignaleerd, als minder urgente kalibratie-notitie.

Puur informatief — niet verweven in enige beslissing van de
integratie.

## Vaatwasser/wasmachine-cyclusstatus (RUSTEND/ACTIEF/KLAAR)

Optioneel, actief zodra `dishwasher_power_sensor_entity` en/of
`washing_machine_power_sensor_entity` zijn geconfigureerd (v0.63.32) —
al bestaande sensoren, geen nieuwe koppeling nodig.

**Bewust geen echte fase-detectie** (vullen/wassen/spoelen/
centrifugeren apart herkennen) — dat vereist merk/model-specifieke
vermogenspatronen waar geen trainingsdata voor is; een verkeerd model
zou minder betrouwbaar zijn dan geen model. In plaats daarvan een
eenvoudige, robuuste toestandsmachine:

- **RUSTEND → ACTIEF**: vermogen komt boven de bekende
  apparaat-actief-drempel (15W).
- **ACTIEF → KLAAR**: vermogen blijft
  `APPLIANCE_CYCLE_COMPLETE_SUSTAINED_MINUTES` (5 minuten) aanhoudend
  daaronder — dezelfde aanhoudend-laag-bevestigt-klaar-logica als de
  steelstofzuiger/fietsladers (v0.63.12/.13), maar met een ruimere marge:
  een cyclus kan tussentijdse stille fases hebben (vullen, weken) die
  een kortere marge ten onrechte als "klaar" zou kunnen aanmerken.
- **KLAAR → ACTIEF**: een nieuwe cyclus start direct door.

Leert de cyclusduur (mediaan over de laatste 7 cycli, dezelfde
uitschieter-resistente aanpak als elders) en toont een grove
voortgangsschatting (huidige duur ÷ geleerde duur) zolang een cyclus
actief is. Stuurt een melding via `appliance_notify_service` zodra een
cyclus klaar is.

`sensor.vaatwasser_cyclus_status` / `sensor.wasmachine_cyclus_status`
tonen "rustend"/"actief"/"klaar", met de geleerde duur, geschatte
voortgang, en de ruwe cyclusduur-geschiedenis als attributen.

## MPC-adviesmotor (prijsarbitrage-plan)

**Uitsluitend adviserend** — stuurt nooit een commando naar de Zendure
en overschrijft nooit de bestaande, beproefde beslisboom. Vereist
`battery_total_capacity_sensor_entity` + `battery_min_soc_number_entity`
(dezelfde velden als de v0.63.27 capaciteit-bewuste "dure
kwartieren"-telling) om te weten hoeveel laadruimte er in totaal is —
zonder die twee: leeg plan met een duidelijke reden, geen giswerk.

**Algoritme: greedy interval pairing** over de beschikbare
prijsvoorspellingshorizon (vandaag + morgen, tot `MPC_HORIZON_HOURS` =
48 uur). Koppelt herhaaldelijk het goedkoopste nog-niet-toegewezen
kwartier aan het duurste nog-niet-toegewezen kwartier en wijst daar een
laad-/ontlaadhoeveelheid tussen toe (begrensd door het fysieke
laad-/ontlaadtempo en de resterende accu-headroom), zolang het paar
`MPC_MIN_MARGIN_EUR_PER_KWH` (3 cent/kWh) na rendementsverlies
overhoudt. Stopt zodra het best overgebleven paar niet meer rendabel
is — correct afbreekpunt, want de kwartieren zijn vooraf op prijs
gesorteerd, dus geen later paar kan nog winstgevender zijn.

Een bewezen goede heuristiek voor het voorraad-arbitrageprobleem, geen
echte lineaire-programmering-oplossing (geen scipy/pulp-afhankelijkheid
toegevoegd, om een HACS-integratie licht te houden) — elke
toewijzingsstap blijft individueel controleerbaar, in tegenstelling tot
de uitvoer van een ondoorzichtige solver.

**Bewust pure prijsarbitrage**: modelleert geen huishoudverbruik of
PV-opwek, en trekt niet de nachtreserve af die de echte beslisboom apart
beschermt. De geprojecteerde winst is dus een theoretisch maximum aan
arbitrage-kans, geen letterlijke aanbeveling — `sensor.mpc_advies`'s
`note`-attribuut vermeldt dit expliciet.

`sensor.mpc_advies_prijsarbitrage_plan` toont de geprojecteerde totale
winst (€), met het volledige geplande schema (per kwartier: laden/
ontladen, prijs, energie) als attribuut. Geen `RestoreEntity` — elke
tick wordt een vers plan berekend op basis van live voorspellingsdata;
een hersteld verouderd plan zou misleidend zijn.

## Monte Carlo-adviesmotor (tekortkans)

**Uitsluitend adviserend** — stuurt nooit een commando en past de
werkelijke reserve-marge niet aan. Vult het bestaande, deterministieke
diepste-tekort-cijfer (mediaan-gebaseerd, zie "Reserve & veiligheid"
hierboven) aan met een **kansverdeling**: 1000 gesimuleerde trajecten
over dezelfde uur-voor-uur diepste-tekort-berekening, elk getrokken uit
de al bestaande, geleerde geschiedenis.

**Bootstrap-resampling, geen aangenomen verdeling**: elk gesimuleerd
traject trekt willekeurig (met teruglegging) uit de daadwerkelijk
waargenomen dagelijkse steekproeven per uur —
`hourly_consumption_profile` voor verbruik, `pv_hourly_bias_history`
voor de Solcast-voorspellingsfout — in plaats van een aangenomen
verdeling (bijv. een Gauss-curve met een gegokte standaardafwijking) te
verzinnen. Geen aparte weer-/bezettingsruis toegevoegd: de
PV-bias-geschiedenis weerspiegelt al impliciet weersvariatie (dat is
precies *waarom* die ratio van dag tot dag verschilt), en er is geen
bezettingsmodel in deze integratie om uit te putten.

Horizon begrensd op `MONTE_CARLO_MAX_HOURS` (48 uur) puur voor
prestaties — 1000 simulaties over meer uren zou merkbaar bijdragen aan
de rekentijd van een enkele 5-minuten-tick zonder echte nauwkeurigheids-
winst (in de praktijk ~15ms voor een realistisch 14-uursscenario).

`sensor.monte_carlo_risico_tekortkans` toont het percentage simulaties
waarin het gesimuleerde tekort de daadwerkelijk beschikbare energie
overschreed, met de mediaan/p10/p90 van het diepste tekort (kWh) als
attributen. Geen `RestoreEntity` — elke tick een verse simulatiebatch.

## Kalman filtering (SoC/PV/verbruik)

**Uitsluitend adviserend** — een gladgestreken schatting naast de ruwe
sensorwaarde, nooit meegenomen in enige beslissing. Die blijven hun
eigen, al beproefde gladstrijkmethode gebruiken (bijv. de
mediaan-gebaseerde verbruikscorrectie, v0.59.0/v0.62.0).

Gebruikt een minimaal, afhankelijkheidsvrij scalair Kalman-filter (geen
numpy nodig) per signaal — beschikbare energie/SoC, live PV-vermogen,
live huishoudverbruik — een principieel andere techniek dan de
mediaan-gebaseerde gladstrijking elders: weegt de vorige schatting
tegen de nieuwe meting af op basis van hun relatieve onzekerheid (de
Kalman-gain), in plaats van een vast steekproefvenster.

Proces-ruis (hoeveel de werkelijke waarde naar verwachting tussen twee
ticks verschuift) en meet-ruis (hoe onbetrouwbaar de ruwe sensorwaarde
wordt geacht) zijn onderbouwde standaardwaarden per signaal — **niet**
empirisch bepaald voor jouw specifieke sensoren, aangezien die data er
niet is.

`sensor.kalman_filtering_soc_pv_verbruik` toont "actief"/"geen data",
met de gefilterde én ruwe waarde voor alle drie signalen als
attributen. Geen `RestoreEntity` — elk filter herstelt zichzelf
natuurlijk binnen enkele ticks vanaf de eerstvolgende live meting.

## Digital Twin (gesimuleerde SoC/winst)

**Uitsluitend adviserend** — simuleert vooruit wat de **bestaande,
regelgebaseerde logica** aan SoC/financieel resultaat zou opleveren,
als natuurlijk vergelijkingspunt naast het MPC-adviesplan
(theoretisch optimum, v0.63.33). Het verschil tussen de twee laat zien
hoeveel arbitrage-ruimte (indien aanwezig) de huidige logica al
daadwerkelijk benut.

**Hergebruikt bewust `self.last_timeline`** (al elke tick berekend voor
de "Overzicht komende uren"-tabel op het dashboard, compleet met
reserve-bewuste, prijs-prioriteit-bewuste kwartier-classificatie) in
plaats van een eigen, mogelijk afwijkende classificatielogica te
verzinnen — een échte tweeling van de bestaande projectie, geen tweede
benadering ernaast.

Loopt die tijdlijn door en simuleert per kwartier:
- **`manual`** (dure kwartieren): ontladen tegen `manual_discharge_power`,
  begrensd door de resterende gesimuleerde SoC.
- **`smart` binnen het geïdentificeerde goedkoopste blok**: laden tegen
  `manual_charge_power`, begrensd door de resterende capaciteit-headroom.
- **Overig** (`smart_discharging`, of `smart` buiten het goedkoopste
  blok): geen expliciete SoC-wijziging in deze vereenvoudigde tweeling —
  dezelfde scope-beperking als de MPC-adviesmotor: geen
  huishoudverbruik-/PV-net-load-modellering.

`sensor.digital_twin_gesimuleerde_soc_winst` toont de geprojecteerde
winst (€), met het volledige gesimuleerde traject (per kwartier: modus,
SoC) als attribuut. Geen `RestoreEntity` — elke tick een verse
simulatie vanaf de live tijdlijn.

## NILM-achtige apparaat-auto-detectie

**Geen "echte" NILM.** Blinde disaggregatie van één geaggregeerd
vermogenssignaal naar losse apparaten (op basis van signaalherkenning
alleen) is een onderzoeksmatig vraagstuk waar deze integratie geen
trainingsdata voor heeft — dat is bewust niet gebouwd, om dezelfde reden
dat MPC/Monte Carlo/Kalman/Digital Twin bewust adviserend zijn gebleven.

**Wat er wél gebeurt:** elke tick worden bestaande vermogen-sensoren
(W/kW) in je Home Assistant-installatie ontdekt die nog niet ergens
anders in deze integratie zijn geconfigureerd — slimme stekkers,
apparaten die hun eigen verbruik al rapporteren. Breed (elke
W/kW-sensor), dus met kans op ruis (irrelevante of verkeerd
geïnterpreteerde entiteiten) — vandaar het bevestigingssysteem
hieronder.

### Bevestigen via Home Assistant-services

Nieuw ontdekte kandidaten belanden in `nilm_unconfirmed_candidates` en
worden **pas gevolgd nadat je ze expliciet bevestigt** — via
Ontwikkelaarshulpmiddelen → Acties (of een eigen script/knop):

- **`energy_management_system.confirm_nilm_device`** (`entity_id`
  verplicht) — verplaatst de kandidaat naar de bevestigde lijst en start
  de drift-detectie ervoor.
- **`energy_management_system.reject_nilm_device`** (`entity_id`
  verplicht) — negeert de kandidaat permanent (wordt nooit meer
  voorgesteld); verwijdert 'm ook uit de bevestigde lijst als je van
  gedachten verandert.
- **`energy_management_system.unconfirm_nilm_device`** (`entity_id`
  verplicht, v0.63.68, gevraagd "hoe kan ik een NILM apparaat
  verwijderen en opnieuw beoordelen?") — verwijdert een bevestigd
  apparaat inclusief zijn volledige geleerde geschiedenis (basislijn,
  drift-status, dagelijkse gemiddelden). In tegenstelling tot negeren
  wordt het apparaat **niet** permanent geblokkeerd — bij de
  eerstvolgende scan verschijnt het gewoon weer als nieuwe,
  onbevestigde kandidaat, zodat je 'm met een verse basislijn opnieuw
  kunt bevestigen. Bruikbaar bijvoorbeeld wanneer het fysieke apparaat
  is vervangen of gerepareerd en de oude, geleerde basislijn niet meer
  klopt.

`sensor.nilm_onbevestigde_kandidaten` toont het echte totaal-aantal
als state, met een **begrensd voorbeeld** (standaard de eerste
`NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT` = 20, alfabetisch) als attribuut
— niet de volledige lijst. Dat is bewust (v0.63.45, gerapporteerd): met
de brede detectie kan de volledige kandidatenlijst het 16KB-limiet voor
Home Assistant-attributen overschrijden (met name met de
Zendure-integratie's eigen granulaire per-pack-vermogenssensoren), wat
HA er dan stilzwijgend toe brengt het hele attribuut niet meer op te
slaan. De volledige lijst blijft wel beschikbaar via de
diagnostiek-export (Instellingen → Apparaten → Energy Management
System → Diagnostische gegevens downloaden), die niet aan die limiet
gebonden is.

### Bevestigen/negeren via het dashboard (v0.63.41/.43/.47/.48)

Een kale Home Assistant-installatie kan geen dynamische, onbekende-
lengte-lijst automatisch in knoppen omzetten (dat vereist een externe
HACS-frontend-kaart) — daarom werkt dit met een **vaste set van 8
sleuven**: `button.nilm_kandidaat_1_bevestigen` t/m `_8_bevestigen`
(en hetzelfde met `_negeren`). Ruim genoeg voor een realistisch aantal
tegelijk nieuw ontdekte apparaten; bij meer dan 8 tegelijk zijn de
extra kandidaten gewoon nog niet zichtbaar totdat er een sleuf vrijkomt.

**Elke knop toont zijn eigen kandidaat direct in de naam** (bijv. "✅
Koelkast 82W") — géén aparte tabel meer om te kruisverwijzen, dat bleek
op een smal/mobiel dashboard onleesbaar (v0.63.43). Een lege sleuf toont
"(leeg)". Alfabetisch gesorteerd op `entity_id`, dus stabiel tussen
ticks. Het dashboard (paneel "Apparaten") toont de 16 knoppen als losse
kaarten in een raster; een sleuf verschuift automatisch naar de
volgende kandidaat zodra je 'm bevestigt of negeert.

`has_entity_name` staat bewust **uit** voor deze 16 knoppen — enige
uitzondering in de hele integratie (v0.63.47, gerapporteerd): normaal
gesproken plakt Home Assistant de apparaatnaam ("Energy Management
System") vóór elke entiteitsnaam, wat de knoptekst in de praktijk
afkapte tot onleesbare fragmenten.

**Ververst nu ook daadwerkelijk live (v0.63.48, gerapporteerd — sleuven
bleven leeg tonen, ook na verversen):** `ButtonEntity` pollt in
tegenstelling tot `SensorEntity` niet standaard, dus zonder een
expliciete melding bleef de weergave bevroren op wat 'm was bij de
allereerste keer dat Home Assistant de status wegschreef (typisch
"(leeg)", nog vóór er ooit een detectie had gelopen). De coordinator
heeft nu een luisteraar-mechanisme (zelfde patroon als de
PV-nauwkeurigheids-tracker): na elke update-cyclus — inclusief bij een
vroege terugkeer in een van de vele beslistakken, of zelfs bij een
onverwachte fout — worden alle geregistreerde knoppen actief ververst.

**Dashboard-kaarten omgezet naar sjabloonkaarten (v0.63.49):**
ondanks v0.63.47/.48 bleef de knoptekst op het dashboard toch
"Energy Man..." tonen — vermoedelijk cachet Home Assistant's
entity-registry de weergavenaam bij de eerste registratie, en pakt een
herstart die verandering niet automatisch op (een bekend knelpunt bij
het wijzigen van `has_entity_name`/`name` op een al-bestaande
entiteit). In plaats van te vertrouwen op hóe Home Assistant de
entiteitsnaam zelf berekent, tonen de 16 dashboardkaarten nu de tekst
via een eigen sjabloon (`custom:mushroom-template-card`, hetzelfde
patroon dat verder overal in dit dashboard al wordt gebruikt) dat
rechtstreeks uit de al-correct-verversende attributen
(`kandidaat_naam`, `kandidaat_vermogen_w`) leest — volledig los van
entity-naam-caching. Tikken op een kaart roept de knop nog steeds aan
via een `tap_action`-service-call.

**Sleufgenoot ververst nu ook direct (v0.63.50):** gerapporteerd —
"als ik iets weiger past de accepteer-kaart zich niet aan". Oorzaak:
een druk op een knop laat Home Assistant automatisch alléén díe ene
knop-entiteit zijn eigen status wegschrijven — de andere knop
(bevestigen/negeren) voor diezelfde sleuf weet daar niets van, en bleef
daardoor tot de volgende reguliere update-cyclus (max. 5 minuten)
de oude kandidaat tonen, terwijl de sleuf zelf al was doorgeschoven.
`confirm_nilm_device()`/`reject_nilm_device()` roepen nu direct na de
wijziging alle geregistreerde luisteraars aan (niet pas bij de
volgende tick), dus beide knoppen van een sleuf verversen meteen
samen, ongeacht welke van de twee je indrukte.

**Lege sleuven verdwijnen nu uit beeld (v0.63.52, teruggedraaid in
v0.63.82):** gevraagd — met 8 sleuven × 2 knoppen kan het dashboard er
snel vol uitzien als de meeste sleuven leeg zijn. Elke kaart had een
`visibility`-voorwaarde die rechtstreeks las of die sleuf een kandidaat
had (`kandidaat_entity_id` niet `None`). **Verwijderd in v0.63.82**:
na de langdurige entity_id-migratie (v0.63.74 t/m .81, uiteindelijk
succesvol) bleek de kaart nog steeds niets te tonen — de
`visibility`-conditie zelf werkte niet betrouwbaar in deze
dashboard-configuratie (genest in een grid binnen de Sections-layout).
In plaats van verder te blijven zoeken naar waarom, is betrouwbaarheid
boven cosmetiek gekozen: alle 16 knoppen zijn nu altijd zichtbaar (met
"Sleuf N (leeg)" waar niets in zit) — gegarandeerd werkend.

**Van 8 sleuven terug naar 1 (v0.63.83):** gerapporteerd — met 8
sleuven × 2 knoppen naast elkaar (2 per rij) werd de kandidaatnaam
afgekapt ("Houten la..." in plaats van de volledige naam), simpelweg
te weinig breedte per kaart. Gevraagd: "1 optie tonen is voldoende,
als de 1e beoordeeld is verschijnt de 2e automatisch" — beoordelen
gebeurt toch al één voor één. `NILM_DASHBOARD_SLOT_COUNT` is verlaagd
van 8 naar 1, en de overgebleven bevestig/negeer-kaart krijgt nu de
volle breedte (12 kolommen i.p.v. 6) — ruim voldoende voor de langste
kandidaatnaam. Het bestaande sleuf-doorschuifmechanisme (confirmeren/
negeren laat de eerstvolgende kandidaat automatisch instromen) blijft
ongewijzigd werken, nu gewoon met één zichtbare sleuf in plaats van
acht.

**Écht fundamentele oorzaak van bijna alle breedteproblemen (v0.63.84):**
zelfs met 12 kolommen bleef de kandidaatnaam afgekapt, en de kaart
toonde veel lege verticale ruimte. Nagetrokken tegen de officiële
Home Assistant-documentatie: dit dashboard gebruikt voor elk tabblad
behalve "Overzicht" géén `type: sections`, maar het klassieke
**Masonry**-weergavetype (`cards:` rechtstreeks onder de view, geen
`sections:`). De `- type: grid`-kaarten in die tabbladen zijn dus geen
Sections-"secties" maar de gewone **Grid-kaart**
(https://www.home-assistant.io/dashboards/grid/) — met een compleet
ander eigenschappenmodel. Die kaart heeft standaard `columns: 3` én
`square: true` (kaarten vierkant gedwongen) als er geen `columns`/
`square` expliciet op de kaart zélf wordt gezet — de `grid_options` die
ik op de onderliggende kaarten had gezet, is een **Sections-specifieke**
eigenschap en heeft in een Grid-kaart-context geen enkel effect. Dat
verklaart zowel de afgekapte tekst als de vierkante, halflege kaarten
in bijna elke NILM-screenshot deze hele sessie — inclusief de
"NI... 80" / "NI... 20"-afkapping bovenaan het "Apparaten"-tabblad.

Gefixt door `columns: 1` en `square: false` rechtstreeks op de
betreffende Grid-kaarten te zetten (niet op de kinderen) — zowel de
bevestig/negeer-kaart als de NILM-tellingen/kandidaten-kaart erboven.
Andere Grid-kaarten in de overige tabbladen (Financieel, Zelflerend,
Advies, Klimaat, Geschiedenis) hadden dit al eerder correct
ingesteld — alleen deze twee ontbraken nog.

**Fundamentele oorzaak gevonden: onvoorspelbare entity_id's
(v0.63.74):** gerapporteerd — er verscheen helemaal niets meer onder
"Bevestigen / negeren", waardoor bevestigen/negeren van nieuwe
apparaten onmogelijk was. Root cause: sinds `has_entity_name` uit
staat (v0.63.47) én er geen expliciete `object_id` was ingesteld, leidt
Home Assistant de entity_id af van de entiteit's eigen `name`-property
bij de **eerste registratie** — maar die naam is bewust **dynamisch**
(toont steeds de kandidaat die op dat moment in de sleuf zit, v0.63.43).
Bij een verse registratie werd daardoor een onvoorspelbare entity_id
vastgelegd (afhankelijk van welke kandidaat er toevallig in zat, of
"sleuf-n-leeg" als er nog niets was) — niet de stabiele
`nilm_kandidaat_N_bevestigen`/`_negeren`-id die het meegeleverde
dashboard hardcodeert. Elke dashboardverwijzing naar deze knoppen wees
daardoor stilzwijgend naar een niet-bestaande entiteit.

Gefixt door een expliciete, stabiele `suggested_object_id` te zetten,
afgeleid puur van het vaste sleufnummer — nooit van de dynamische
kandidaatnaam.

**Belangrijk voor bestaande installaties**: deze fix werkt alleen voor
**nieuw geregistreerde** entiteiten — een al-bestaande, verkeerd
benoemde entiteit behoudt zijn oude entity_id voor altijd (gekoppeld
aan de `unique_id`, niet aan de naam). Heb je dit probleem, verwijder
dan eenmalig de 16 NILM-sleufknoppen via Instellingen → Apparaten &
Diensten → Energy Management System → apparaat → de betreffende
knop-entiteiten (of het hele apparaat) verwijderen, en herstart HA
daarna — ze worden dan opnieuw aangemaakt met de correcte, stabiele
entity_id.

**Correctie: de v0.63.74-fix werkte niet (v0.63.79).** Gerapporteerd:
na de handmatige verwijder-en-herstart-stap bleef "Bevestigen /
negeren" alsnog leeg. Root cause: `_attr_suggested_object_id` blijkt
**geen bestaand Home Assistant-attribuut** te zijn — nagetrokken tegen
de officiële developer-documentatie
(https://developers.home-assistant.io/docs/core/entity) en de
broncode: het enige vergelijkbare, intern mechanisme
(`internal_integration_suggested_object_id`) is expliciet gedocumenteerd
als "only handled internally, never to be used by integrations".
Home Assistant negeerde het attribuut dus gewoon volledig en bleef de
entity_id afleiden van de dynamische naam, exact als voorheen.

**Echte fix**: `self.entity_id` wordt nu rechtstreeks als
instantie-attribuut gezet in `__init__`, vóórdat de entiteit ooit aan
hass wordt toegevoegd — dit is een genuine, gerespecteerde
override (`entity_id` is een gewoon, instelbaar attribuut op `Entity`;
Home Assistant genereert er alleen automatisch één als de integratie
nog niets heeft ingesteld). Matcht daarbij exact de
`woonkamer_energy_management_system_`-prefix die het dashboard al voor
elke andere entiteit hardcodeert (die daar normaal automatisch ontstaat
via `has_entity_name` + de geconfigureerde apparaatnaam) — voor deze 16
knoppen expliciet uitgeschreven, omdat ze bewust geen `has_entity_name`
gebruiken (v0.63.47).

**Correctie: geen handmatige verwijdering meer nodig (v0.63.80).**
Gerapporteerd — "Je kunt enkel 0 van de 16 entiteiten verwijderen. De
andere vereisen dat de integratie stopt met ze aan te leveren." Home
Assistant blokkeert het handmatig verwijderen van entiteiten die nog
actief door een geladen integratie worden geleverd, waardoor de
verwijder-en-herstart-instructie hierboven onuitvoerbaar was. Bovendien
zou een kale herstart ook niet hebben geholpen: Home Assistant's
entity-registry zoekt eerst een bestaand item op via de `unique_id` en
hergebruikt daarvan de opgeslagen (oude, foute) entity_id — een nieuw
gezette `self.entity_id` wordt nooit toegepast op een al-geregistreerde
`unique_id`.

**Fix**: de `unique_id` van deze 16 knoppen zelf is opgehoogd (een
`_v2`-suffix). Home Assistant heeft daardoor geen match meer in de
registry en registreert deze knoppen dus daadwerkelijk vers, met
correcte toepassing van de expliciet gezette entity_id — **geen
handmatige verwijdering meer nodig**, alleen een gewone HA-herstart. De
oude v1-entiteiten stoppen simpelweg met bestaan (worden niet meer
geleverd) en kunnen naar wens genegeerd of later opgeruimd worden — er
was nooit state gekoppeld aan de unique_id van deze knoppen zelf.

**Verwacht bij brede detectie**: met "alle sensoren met een
vermogens-eenheid" als detectiebereik kunnen ook granulaire
deelmetingen van je eigen Zendure-accu verschijnen als kandidaat (bijv.
losse laad-/ontlaad-/PV-vermogenssensoren per accupack) — geen losse
"apparaten", maar facetten van de accu die je al via
`battery_power_sensor_entity` volgt. Negeer die gewoon; ze worden dan
nooit meer voorgesteld.

### Drift-detectie na bevestiging (mogelijk defect)

Zelfde CUSUM-principe als de sluipverbruik-detectie hierboven, maar per
apparaat en **percentage-gebaseerd** in plaats van een vaste
Watt-drempel — vermogensniveaus verschillen te veel tussen apparaten
(een koelkast en een router) om één vaste drempel voor allebei te laten
gelden. Volgt het dagelijkse gemiddelde vermogen per bevestigd apparaat;
een aanhoudende stijging van >10% boven de langere-termijn-referentie
(30 dagen) wordt gesignaleerd als mogelijk beginnend defect — bijv. een
koelkast met een falende compressor, of een warmtepomp die harder moet
werken door vervuilde filters. Stuurt een melding via
`appliance_notify_service`, edge-triggered net als sluipverbruik.

`sensor.nilm_bevestigde_apparaten` toont het aantal bevestigde apparaten
+ per apparaat de geleerde geschiedenis en of er een afwijking is
gedetecteerd, als attributen.

**Opslag via een aparte Store, niet via het HA-entiteit-attribuut
(v0.63.66):** gerapporteerd — "State attributes ... exceed maximum
size of 16384 bytes" — bij genoeg bevestigde apparaten (elk met een
eigen geleerde CUSUM-geschiedenis, plus de `tabel`-attribuut) groeide
dit ruim voorbij de 16KB-limiet die Home Assistant's recorder per
entiteit-attribuut hanteert. In tegenstelling tot de
kandidatenlijst-preview (v0.63.45) is deze data gebruikerscuratie en
bedoeld om maandenlang op te bouwen — die kon niet zomaar afgekapt
worden zonder daadwerkelijk data te verliezen. In plaats daarvan gaat
de opslag nu via een eigen `Store` (een los JSON-bestand onder
`.storage/`, hetzelfde mechanisme dat Home Assistant's eigen
`restore_state` gebruikt) — volledig los van de recorder's
staat-geschiedenis-database en zijn grootte-limiet, dus geen enkele
plafond meer. Het `apparaten`/`tabel`-attribuut op de sensor zelf toont
nog altijd een begrensd voorbeeld (net als de kandidatenlijst) — maar
dat is nu puur cosmetisch, niet meer de bron van waarheid voor wat
daadwerkelijk hersteld wordt bij een herstart.

Bestaande installaties migreren automatisch, eenmalig: als de nieuwe
Store leeg blijkt (nog nooit geschreven), valt de sensor terug op zijn
eigen, oude herstelde HA-status, en slaat die meteen op in de nieuwe
Store zodat die terugval-route nooit meer nodig is.

### Overzichtstabel: naam, huidig vermogen, trend (v0.63.51/.52)

Op verzoek — een overzicht van alle bevestigde apparaten (naam, huidig
vermogen, trend), direct op het "Apparaten"-dashboard. Geen nieuwe
trackinglaag: het huidige vermogen wordt live uitgelezen, en de trend
is een lichtere, granulaire aftakking van de al bestaande
CUSUM-drift-detectie hierboven — een kleine verschuiving (>5% t.o.v. de
langere-termijn-referentie) is al zichtbaar (`↗ licht stijgend` /
`↘ dalend` / `→ stabiel`), ruim vóórdat die groot genoeg zou zijn om de
alarmdrempel (10% aanhoudend) te bereiken. Bij een daadwerkelijk
gesignaleerde afwijking staat er expliciet "mogelijk defect" met het
geschatte percentage.

Beschikbaar als `tabel`-attribuut op `sensor.nilm_bevestigde_apparaten`
(lijst met `naam`/`huidig_vermogen_w`/`trend` per apparaat, alfabetisch
gesorteerd).

**Echte oorzaak van de eerdere onleesbaarheid gevonden (v0.63.53):**
niet de tabelopmaak zelf (v0.63.52's omzetting naar een lopende lijst
loste het verkeerde probleem op) — de kaart zat in een grid-layout met
een **vaste hoogte** (`grid_options: rows: 5`) die te krap was voor het
aantal apparaatrijen, waardoor de tabel inklapte/overlapte. Vergeleken
met de wél goed werkende tabel op het "Advies"-tabblad (die geen vaste
hoogte heeft) en teruggezet naar een echte tabel, met
`grid_options: rows: auto`.

**Definitief teruggezet naar een lopende lijst (v0.63.62):**
gerapporteerd, met screenshot — ook mét de hoogte-fix bleef de tabel
op een smal scherm onleesbaar, omdat de apparaatnamen (bijv. "Airco
Woonkamer Compressor geschat energieverbruik") veel langer zijn dan de
korte modulenamen op de Advies-tabel, en een 3-koloms-tabel daar op
smalle schermen alsnog op vastloopt. Elke rij toont nu weer
"**Naam** — vermogen — trend" als los lijstitem, wat ongeacht de
naamlengte gewoon natuurlijk meebuigt (woordafbreking) in plaats van in
een vaste kolombreedte te knijpen.

**Kaart losgetrokken uit de gedeelde grid-wrapper (v0.63.63):**
gerapporteerd, met vergelijkingsscreenshot van de wél-goed-werkende
Advies-tab — de apparatentabel zat genest in dezelfde `type: grid`-
kaart als de NILM-sensorenlijst en de sleufknoppen. Die hele wrapper
werd door Home Assistant's Sections-layout als één enkel item
behandeld en kreeg daardoor zelf een smalle breedte toegewezen,
ongeacht wat de kinderen daarbinnen als "columns: 12" opgaven (dat
regelt alleen hun onderlinge verdeling binnen die al-smalle kaart, niet
de breedte van de kaart zelf op de pagina). Op de Advies-tab staat
"Alle acht modules" juist als **eigen, losstaande kaart** direct in de
tabblad-lijst, zonder gedeelde wrapper — en krijgt daardoor zijn volle,
onafhankelijke breedte. De apparatentabel is nu op exact dezelfde
manier losgetrokken tot een eigen, top-level kaart.

**Puur informatief** — nergens meegewogen in accubeslissingen, zoals
afgesproken.

## Advies-gereedheid: wanneer is een adviesmodule betrouwbaar genoeg?

Acht modules zijn uitsluitend adviserend/informatief (Kirchhoff,
sluipverbruik-detectie, Weather Ensemble, MPC, Monte Carlo, Kalman
filtering, Digital Twin, NILM) — geen ervan stuurt ooit een commando of
weegt mee in een accubeslissing. `sensor.advies_gereedheid_8_modules`
(v0.63.40) geeft per module een eerlijke inschatting van hoe betrouwbaar
de uitkomst inmiddels is, gebaseerd op wat er al aan data is verzameld.

**Bewuste eerlijkheidsscheiding — twee categorieën, niet één schaal:**

- **Echte data-volwassenheid** (Kirchhoff, sluipverbruik, Monte Carlo,
  Kalman, NILM): deze hebben allemaal al een intern signaal dat laat
  zien hoeveel data er is verzameld t.o.v. wat het ontwerp nodig heeft
  (bijv. 30 dagen voor de sluipverbruik-referentie, een Kalman-filter
  dat aantoonbaar geconvergeerd is). Status: `klaar` / `bijna_klaar` /
  `onvoldoende_data` / `kwaliteit_te_laag` (bij Kirchhoff, als de
  sensoren zelf inconsistent blijken) / `niet_geconfigureerd`.
- **Structureel beschikbaar, geen bewezen nauwkeurigheid** (Weather
  Ensemble, MPC, Digital Twin): deze drie hebben **geen** mechanisme dat
  ooit een eerdere voorspelling tegen wat er daadwerkelijk gebeurde
  legt. Ze werken en berekenen prima, maar "klaar" zou een valse claim
  van bewezen betrouwbaarheid zijn die deze integratie niet heeft
  verdiend — vandaar bewust altijd `structureel_beschikbaar` in plaats
  van een schijnbaar gereedheids-oordeel.

De sensor toont het aantal modules met status `klaar`, met de volledige
uitsplitsing (status + reden per module) als attribuut. Geen
`RestoreEntity` — elke tick opnieuw berekend uit de actuele staat van
elke module.

**Dashboard-tabblad "Advies" (v0.63.44)**: apart tabblad met een
volledige tabel van alle acht modules (naam, status, reden), de
legenda van de twee categorieën, en directe links naar elke module's
onderliggende sensor om verder in te zoomen. **Let op**: gereedheid
zegt iets over hoe betrouwbaar het cijfer zelf is — niet over of het
veilig is om ergens op te sturen. Alle acht blijven, ongeacht hun
status, uitsluitend adviserend; geen van deze modules stuurt ooit een
commando of wordt in een accubeslissing meegewogen.

## Klimaat-tabblad: geleerde woonkamertemperatuur-projectie (v0.63.56/.57/.58)

Op verzoek — een apart "Klimaat"-tabblad dat 24 uur vooruit projecteert
wat de woonkamertemperatuur gaat doen, gebaseerd op de KNMI/
OpenWeatherMap-buitentemperatuur-voorspelling, de rolluikstand (2
geconfigureerde entiteiten, gecombineerd tot "beide_dicht"/
"gedeeltelijk"/"beide_open"), en de airco-status ("uit"/"verwarmen"/
"koelen", granulairder dan de bestaande grootverbruiker-detectie).

**Bewust vereenvoudigd om bruikbaar te blijven**: een volledig model
(buitentemperatuur × rolluikstand × bewolking × airco-status) zou
honderden cellen opleveren die elk apart genoeg data nodig hebben — bij
een normaal huishouden zou het merendeel daarvan maandenlang
"onvoldoende data" blijven tonen. Bewolking is daarom **expliciet
weggelaten** als aparte leerdimensie (bevestigd met de gebruiker); de
buitentemperatuur-vóórspelling wordt wel gebruikt om de projectie uur
voor uur door te rekenen.

**Wat er wordt geleerd**: de verandersnelheid (°C/uur) van de
woonkamertemperatuur per combinatie van buitentemperatuur-bucket (2°C)
× rolluikstand × airco-status, in een kort, glijdend venster (niet
seizoensgebonden) — reageert dus snel op veranderend weer in
lente/herfst, in plaats van door weken-oude data uit een heel ander
regime verwaterd te worden. Gemeten over ongeveer een uur (niet elke
5-minuten-tick) — een tik-voor-tik-berekening zou voor zo'n langzaam
fysiek proces veel te ruisgevoelig zijn geweest.

**Twee betrouwbaarheidsniveaus, parallel berekend** (niet twee losse
modellen): `kort_termijn_temp_c` past de geleerde snelheid al toe
vanaf 5 samples per cel ("indicatief" — bruikbaar, maar met nog weinig
data), `betrouwbaar_temp_c` pas vanaf 15 samples. Een uur onder de
eigen drempel bevriest op de temperatuur van het vorige uur, in plaats
van te gokken.

**Correctie op de actueel gemeten waarde (v0.63.58)**: het ophalen van
de buitentemperatuur-voorspelling (een échte `weather.get_forecasts`-
service-aanroep met een respons, nieuw terrein voor deze integratie)
gebeurt om prestatieredenen maar eens per 30 minuten. De projectie
zélf wordt echter **elke tick** opnieuw doorgerekend, steeds verankerd
aan de actueel gemeten woonkamertemperatuur — zonder deze scheiding zou
de projectie tot 30 minuten kunnen "wegdrijven" van wat er intussen
echt gemeten wordt.

**Beperking, expliciet benoemd**: rolluikstand en airco-status worden
voor de hele 24-uurs-projectie constant gehouden op hun huidige stand
— onbekend wat je daar over een paar uur mee doet.

`sensor.klimaat_projectie_woonkamertemperatuur` toont het volledige
traject (tijd, voorspelde buitentemperatuur, beide temperatuurreeksen,
betrouwbaarheidsniveau, aantal metingen per uur) als attribuut. Wél een
`RestoreEntity` — het geleerde snelheidsmodel per cel moet weken kunnen
opbouwen.

Puur informatief, stuurt nooit een commando.

## Diagnostiek

"Instellingen → Apparaten & Diensten → Energy Management System → drie
puntjes → Diagnostiek downloaden" geeft een volledige momentopname:
huidige beslissing + reden + volledige uitleg, prijsdrempels, reserve-
marge-opbouw, alle geleerde profielen (inclusief onderliggende
dagreeksen), een bounded logboek van elke modus/vermogen-wijziging
(`mode_change_log`), gedateerde tekort-/overschot-historie, de ruwe
Solcast-halfuur-voorspelling, en een gescande lijst van mogelijk
relevante andere entiteiten in je installatie. Deel dit bestand bij een
bugreport — voorkomt in de meeste gevallen dat er om een tweede export op
precies het juiste moment gevraagd hoeft te worden.

## Bekende beperkingen

- **Secundaire-laag-drempel kan theoretisch flikkeren binnen één
  kwartier** — die gebruikt live beschikbare energie, die tijdens het
  ontladen zelf verandert. Nog niet bevestigd als daadwerkelijk
  voorkomend probleem.
- **Zonneplan's "tomorrow"-forecast** komt vaak pas 's middags binnen —
  tot die tijd zoekt de integratie het goedkoopste blok alleen binnen de
  al bekende data. Dit is verwacht gedrag, geen bug.
- **Oven/kookplaat-detectie** vereist een Home Connect `operation_state`-
  sensor (of vergelijkbaar met dezelfde `Run`-waarde); zonder vermogen-
  sensor is er geen wattage-detectie mogelijk voor deze twee, alleen
  aan/uit-bevestiging.

`iot_class: local_polling` is bewust zo gekozen, niet een beperking: de
kernberekeningen (tijd-tot-goedkoopste-blok, diepste-tekort-onderweg)
veranderen puur door het verstrijken van tijd, onafhankelijk van welke
entity-state dan ook — een tijd-gebaseerde 5-minuten-cyclus past hier
beter dan `local_push`.

## Ontwikkelen / lokaal testen

Kopieer `custom_components/energy_management_system` naar de
`custom_components`-map van je Home Assistant-config, of symlink de map
tijdens ontwikkeling:

```bash
ln -s $(pwd)/custom_components/energy_management_system /path/to/homeassistant/config/custom_components/energy_management_system
```

Permanente testsuite (pytest, geen echte HA-installatie nodig):

```bash
pip install pytest --break-system-packages
python3 -m pytest -v
```

Zie `tests/README.md` voor een overzicht per testbestand.
