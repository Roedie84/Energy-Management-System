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

## Gezondheidsoordeel verdween na een herstart (v1.15.0)

**Gevraagd**: een volledige analyse van een verse export (v1.14.9).

### De vondst

`sensor_health_score` en `measurement_quality` stonden op **None**,
terwijl de foutreeks van twintig metingen wél was hersteld — en de
uitsplitsing daaruit gewoon 78,6% nauwkeurigheid berekende.

De oorzaak: de **reeks** wordt bewaard, het daaruit afgeleide **oordeel**
niet. En dat werd alleen berekend bij een *nieuwe* meting.

Gevolg: na een herstart was er wel data maar geen oordeel, en verdween
het aandachtspunt over de sensor-gezondheid uit de lijst — terwijl het
probleem gewoon doorliep. Precies het omgekeerde van wat je wilt: de
melding weg, het probleem niet.

Het oordeel wordt nu herberekend uit de reeks zodra de opgeslagen
toestand is geladen. Herberekenen in plaats van bewaren, want dan kan het
nooit uit de pas lopen met de gegevens waarop het rust.

### Wat er verder in orde is

De correctie uit v1.14.9 werkt: geen zelftegensprekende meldingen meer.
Alle vijf leercheks op OK, accu-rendement inmiddels 86,9%. De
Zonneplan-vergelijking op 10 cent verschil, zelfconsumptie 74,4%,
zelfvoorziening 95,2%. De stilstaande-reeks-detectie vindt nu wél de
ruststroom van de steelstofzuiger — en merkt terecht op dat een constante
daar te verwachten is.

### Twee observaties, geen fouten

**Vandaag kostte de accu geld.** Met accu −0,61 €, zonder accu zou het
−1,08 € zijn geweest: 47 cent nadeel. Op een dag met 15,5 kWh opwek kan
opslaan ongunstiger uitpakken dan direct terugleveren. Over de maand
staat het wél positief: −3,96 tegen −3,44, dus 52 cent voordeel.

**De PV-energiemeter is nog niet ingesteld.** `pv_production_source`
staat op "geïntegreerd vermogen", wat structureel onderschat. Het veld
staat klaar bij Configureren.

### Getest

Vier tests erbij: het oordeel wordt herberekend uit de geschiedenis, het
aandachtspunt komt terug na een herstart, te weinig metingen geeft nog
steeds geen oordeel, en de herberekening draait daadwerkelijk na het
laden.

**Volledige testsuite**: 1338 tests, allemaal groen.

## Volledige analyse vóór installatie (v1.14.9)

**Gevraagd**: een volledige analyse voor het installeren.

### Wat er in orde is

Alle Python-, YAML- en JSON-bestanden parsen. 1334 tests groen. En het
dashboard is sluitend:

| Controle | Uitkomst |
|---|---|
| Sensoren zonder plek op het dashboard | 0 van 55 |
| Verwijzingen naar niet-bestaande sensoren | 0 |
| Navigatiepaden die nergens heen gaan | 0 |
| Verborgen tabbladen zonder ingang | 0 |
| Eerste view is geen subview | ✅ |
| NILM-knoppen bereikbaar | ✅ |
| Schakelaars op het dashboard | 7 van 7 |
| Meldingsschakelaars | 22 van 22 |

### Eén echte fout: de melding sprak zichzelf tegen

De sensor-gezondheid meldde:

> *"Niet door onnauwkeurige metingen — alle 14 vergelijkingen vielen
> binnen de marge"*

Terwijl de nauwkeurigheid op **78,6%** stond. Drie metingen zaten er ruim
boven de drempel van 300 W: 368, 798 en 593 W.

Mijn tekst uit v1.6.5 nam aan dat bij uitval als hoofdoorzaak álle
metingen goed waren. Dat hoeft niet: het kan allebei tegelijk. De melding
zegt nu *"Vooral doordat een sensor 6 van de 20 keer geen waarde gaf (11
van de 14 vergelijkingen vielen binnen de marge)"*.

Een melding die zichzelf tegenspreekt maakt álle meldingen verdacht — je
weet niet meer welk deel je kunt geloven.

### Eén terechte nieuwe waarschuwing

**Accumodule 1: celspanningsverschil 0,190 V.** Bij 100% SoC lopen
celspanningen natuurlijk verder uiteen, en module 1 is 4 °C warmer dan
module 3.

Maar de vergelijking is **differentieel** — module tegen het gemiddelde
van de andere twee op hetzelfde moment — dus SoC- en
temperatuurinvloeden vallen weg. Module 1 wijkt +0,17 V af waar de
andere op 0,03 en 0,01 V zitten. Die waarschuwing is terecht en het
opvolgen waard.

### Getest

Twee tests erbij: de melding spreekt de cijfers niet tegen, en bij écht
alle metingen binnen de marge staat dat er nog steeds. Eén oudere test
eiste de exacte oude formulering; die toetst nu de strekking.

**Volledige testsuite**: 1334 tests, allemaal groen.

## Alle 24 verdwenen sensoren terug (v1.14.8)

**Gevraagd**: *"Misschien alles wat we vanmorgen hebben verwijderd qua
dashboards maar weer terug zetten? Zodat de informatie toch weer volledig
is."*

### Eerst gemeten in plaats van teruggedraaid

Een blanco herstel zou ook de zeven tabbladen, de doorklik en de kortere
labels terugdraaien — en daar was je juist tevreden over. Dus eerst
uitgezocht wélke informatie ontbrak: van de **55 sensoren** stonden er
**24 nergens** op het dashboard.

Veel meer dan de drie die je zelf opmerkte:

| Groep | Aantal |
|---|---|
| Beslissing en planning | 7 |
| Adviesmodules | 7 |
| Apparaten (cyclus + status) | 5 |
| Zon en klimaat | 3 |
| Overig | 2 |

Een sensor die de integratie wél berekent maar die je nergens ziet, is
verspilde moeite: hij kost rekentijd en levert niets op.

### Terug op de verborgen tabbladen

- **Systeem** — vaatwasser, wasmachine, steelstofzuiger, fietsladers,
  NILM-kandidaten
- **Verloop** — laatste reden, komend schema, gesimuleerde actie,
  goedkoopste blok, ontlaadvenster, energie-check, accubescherming
- **Kwaliteit** — de zeven adviesmodules met hun gereedheid
- **Financieel** — piekvermogen, geleerd nachtverbruik
- **Details** — PV-installatieprofiel, voorspelbias, airco-verwachting

Overzicht blijft de samenvatting met doorklik. Van 85 naar **138
kaarten** — bijna terug op het oude niveau, maar met de structuur van
vandaag.

### De grenzen zijn meebewogen

Het maximum per tabblad gaat van 10 naar 20 kaarten. Ruimer, niet weg:
hij hoort nu bij "details achter een tik" in plaats van "alleen
samenvattingen".

### Twee tests deden hun werk

De regel uit v1.13.1 — een tabblad met meerdere koppen moet `sections`
gebruiken — sloeg meteen aan op Financieel, dat door de nieuwe kop
"Overig" twee koppen kreeg in een masonry-indeling. Precies de fout die
op Systeem zichtbaar werd. Omgezet.

En de eis dat elke kop een ondertitel heeft, dwong me uit te leggen wát
er in elke nieuwe sectie staat.

### Nu bewaakt

Een test controleert dat **élke sensor** ergens op het dashboard staat.
Dat vangt het bij de bron: een volgende opruimronde kan niet stilletjes
informatie laten verdwijnen.

**Volledige testsuite**: 1332 tests, allemaal groen.

## NILM-beoordeling was onbereikbaar geworden (v1.14.7)

**Gevraagd**: *"Waar kan ik nu Nilm apparaten beoordelen, net als
mogelijke duplicaties?"*

Nergens — en dat is een echt gemis. Bij het opruimen van het
Apparaten-tabblad in v1.12.0 zijn de knoppen verdwenen.

### Waarom dat erger is dan een weggevallen tabel

Zonder die knoppen kan een herkende kandidaat niet worden **bevestigd of
afgewezen**, en blijft een gemeld duplicaat staan. De detectie draait dan
wel — je export meldt twee waarschijnlijke duplicaatparen — maar je kunt
er niets mee.

Een ontbrekende tabel kost je informatie; een ontbrekende knop kost je de
mogelijkheid om te handelen.

### Terug op de detailpagina

Een kaart **"Te beoordelen"** met de huidige kandidaat (naam en vermogen)
en de gevonden duplicaatparen, en daaronder de vier knoppen: kandidaat
bevestigen of negeren, duplicaat bevestigen of afwijzen.

Een knop "bevestigen" zonder te tonen wát je bevestigt is niet te
gebruiken, dus die gegevens staan erboven.

### Bijna de verkeerde entity_id's gebruikt

Mijn eerste poging leidde de entity_id's af uit de weergavenaam. Dat kan
niet: die namen zijn **dynamisch** — ze tonen de kandidaat, dus ze
veranderen mee.

`button.py` legt de entity_id's expliciet vast, juist om de
"_2"-deduplicatie te voorkomen die in v0.63.81 werd gemeld. Ze heten
`nilm_kandidaat_1_*` en `nilm_duplicaat_1_*`, niet wat ik ervan maakte.
Er staat nu een test op dat het dashboard geen zelfbedachte varianten
gebruikt.

### Getest

Drie tests erbij: de vier knoppen staan op het dashboard, de
entity_id's komen overeen met wat `button.py` vastlegt, en de kandidaat
en duplicaten worden getoond.

**Volledige testsuite**: 1331 tests, allemaal groen.

## Uurvoorspelling woonkamertemperatuur terug (v1.14.6)

**Gemeld**: *"Ik mis nu ook de uur temperatuur voorspelling van de
woonkamer?"* — en daarna: *"Snelle voorspelling en lange termijn zoals
origineel"*.

Die was met het opruimen van het Klimaat-tabblad gesneuveld. Terecht
gemist: een verloop per uur laat zich niet in één samenvattende zin
vangen, want juist het verloop is de informatie.

### Beide reeksen terug

De twee kolommen meten iets anders, en één ervan weglaten maakt de tabel
waardeloos:

- **Snel** valt terug op naburige situaties zodra de exacte combinatie
  van buitentemperatuur, rolluikstand en airco te dun bezet is — de
  terugval uit v1.1.2, die voorkwam dat de projectie na vijf dagen
  bevroor op één cel.
- **Betrouwbaar** komt pas bij genoeg metingen in precies die situatie.

Plus de voorspelde buitentemperatuur, de kolom **Basis** die zegt waarop
de snelle schatting rust, en het aantal metingen. Met een regel uitleg
eronder, want "Snel" naast "Betrouwbaar" is zonder toelichting niet te
interpreteren.

Op de detailpagina, bij de andere tabellen.

### Een blinde vlek in mijn eigen test

De test uit v1.14.4 verbood meer dan drie kolommen in detailtabellen. Die
sloeg niet aan op deze tabel met zes — en dat bleek geen toeval.

Hij keek of een regel **begint** met `|`. Maar tabelrijen in deze
sjablonen beginnen met een Jinja-tag: `{% for u in t %}| ...`. Daardoor
werd vrijwel geen enkele rij gecontroleerd; de accumodule-tabel met zes
kolommen glipte er al die tijd door.

Nu telt hij de pipes ongeacht waarmee de regel begint. De grens is zes in
plaats van drie: de detailpagina staat sinds v1.14.4 op één kolom, dus een
tabel krijgt de volle breedte. Op een telefoon blijft dat krap, maar de
alternatieven zijn informatie weglaten of omzetten naar een lijst — en bij
deze tabellen is de kolomvergelijking juist het nut.

### Getest

Twee tests erbij: de projectie toont alle vijf de velden, en de uitleg
bij de twee kolommen staat erbij. Plus de gedichte blinde vlek in de
kolomtest.

**Volledige testsuite**: 1328 tests, allemaal groen.

## Meer informatie terug op het beginscherm (v1.14.5)

**Gemeld**: *"Ik wil toch weer meer informatie op de dashboard, wel met
doorklikken naar onzichtbare tabbladen. Ik mis teveel om nu goed te
kunnen beoordelen."*

Terecht. Het opruimen is te ver gegaan.

### Wat er misging in mijn aanpak

In v1.12.0 haalde ik de tabellen weg en verving ze door één zin per
onderwerp. Goed idee. Maar die zinnen belandden op **vier verschillende
verborgen tabbladen** — en in v1.13.0 werden die ook nog uit de tabbalk
gehaald.

Het gevolg: je moest klikken om te weten óf er iets aan de hand was. Dat
is precies de verkeerde kant op. De **conclusie** hoort op het
beginscherm, het **detail** achter een tik.

En de aandachtspunten waren teruggebracht tot een telling. "4
aandachtspunten" zegt niet wát er is, dus moest je alsnog doorklikken om
te weten of er iets van je verwacht werd.

### Wat er nu op Overzicht staat

**Nieuwe sectie "Status per onderwerp"** met zeven tegels: accumodules,
apparaten, zelflerend, financieel, klimaat, water en meetkwaliteit. Elk
met de conclusie in één regel, groen/oranje/rood, en een tik naar de
detailpagina.

> *"Alle 3 modules lopen gelijk; grootste celspreiding 0,04 V."*
> *"1 van de 38 apparaten verbruikt meer dan normaal: Koelkast schuur."*

**Aandachtspunten weer uitgeschreven**, met de informatieve regels erbij.

Overzicht gaat van 24 naar 40 kaarten. Dat is meer dan v1.12.1, maar de
opbouw is anders: alles is een korte regel met doorklik, geen tabel.

### De grens blijft bestaan

De tekstlimiet per tabblad gaat van 800 naar 1400 tekens — ruimer, niet
weg. Het gaat om **genoeg**, niet om alles: zonder grens wordt het
opnieuw een muur tekst, en dat was het oorspronkelijke probleem.

### Getest

Drie tests aangepast of erbij: de aandachtspunten staan uitgeschreven
inclusief de informatieve regels, Overzicht toont een status per
onderwerp voor alle zeven, en die tegels klikken nog door — meer
informatie op het beginscherm mag de doorklik niet vervangen.

**Volledige testsuite**: 1326 tests, allemaal groen.

## Detailpagina paste niet op het scherm (v1.14.4)

**Gemeld**: *"Uitbreiding betrouwbaarheid is niet meer goed te zien,
uitlijning niet goed."* — met een screenshot waarop de kolom "Niveau"
afbrak op *"Ni…"* en de toelichting helemaal wegviel.

### De pagina stond in masonry

Die verdeelt kaarten over drie kolommen. Een tabel met vier kolommen
krijgt dan een derde van het scherm, en wat niet past verdwijnt achter de
rand.

De pagina staat nu op **één kolom**, zodat elke tabel de volle breedte
heeft.

### En de betrouwbaarheidstabel is een lijst geworden

Vier kolommen passen sowieso niet op een telefoon. Het is nu een
gegroepeerde opsomming: de groepsnaam als kop, daaronder per regel het
niveau, de naam met eventuele waarde, en de toelichting eronder.

Dat schaalt mee met elke breedte, en de groep staat één keer boven zijn
regels in plaats van in elke rij herhaald.

### Over de apparatentabel

Die stond nog op "None" omdat je v1.14.1 draait; de correctie zit in
v1.14.2. Na installatie zie je daar het huidige vermogen en de trend.

### Onderweg misgegaan

Mijn eerste poging voegde `grid_options` toe achter elke kaart, en bij de
laatste belandde dat binnen de sjabloontekst — YAML kapot. Hersteld uit
de laatste zip en opnieuw gedaan met `max_columns: 1` op viewniveau, wat
sowieso netter is dan per kaart.

Daarna moesten drie testhelpers leren dat de kaarten nu in secties zitten
in plaats van op viewniveau; zeven tests vielen daarop om.

### Getest

Drie tests erbij: de detailpagina is één kolom, geen enkele detailtabel
heeft meer dan drie kolommen, en de omgezette lijst toont nog steeds alle
vijf de velden.

**Volledige testsuite**: 1324 tests, allemaal groen.

## Stilstaande reeksen werden niet gevonden (v1.14.3)

**Gevraagd**: *"Tevens kijken of er meer zaken zijn die nu niet correct
meer lopen"* — bij een verse export.

### Eerst het goede nieuws

De drift-drempel uit v1.12.3 werkt: van **vijf** apparaten "mogelijk
defect" naar **één**, en dat is de koelkast in de schuur die er echt
uitspringt. De aanlooptijd uit v1.11.0 doet ook zijn werk — de
sensor-gezondheid staat niet meer in de aandachtspunten.

### Twee vondsten

**De stilstaande-reeks-detectie vond niets**, terwijl
`_steelstofzuiger_idle_power_history` op tien identieke waarden stond —
precies de reeks waarvoor die controle in v1.11.1 is gemaakt.

De oorzaak: ik sloeg alles over dat met een **underscore** begint. Maar
de echte velden heten intern `_steelstofzuiger_idle_power_history`; in de
export wordt de underscore weggehaald en `_w` toegevoegd. Ik keek dus
naar namen die alleen in de export bestaan.

Interne naamgeving zegt niets over of een reeks het bewaken waard is.

En toen hij eenmaal werd gevonden, gold hij als **verdacht** — want de
uitzonderingslijst stond op `idle_power_history_w`, met dat
export-achtervoegsel dat intern niet bestaat. Twee keer dezelfde fout,
op twee plekken.

**`pv_production_source` stond niet in de export.** Daardoor is niet na
te gaan of de kWh-meter uit v1.9.1 daadwerkelijk wordt gebruikt of dat er
nog wordt geïntegreerd. Toegevoegd.

### Eén vals alarm van mijn kant

De PV-velden leken te ontbreken, maar die staan in de KPI-sectie in
plaats van bij de coordinator — mijn leescommando keek op het verkeerde
niveau. Zelfconsumptie staat op 76,8%, en dat is sinds v1.9.2 weer een
plausibel getal.

### Getest

Drie tests erbij: velden met een underscore worden meegenomen, de
uitzondering past op de interne naam, en Python-interne velden worden
nog steeds overgeslagen.

**Volledige testsuite**: 1321 tests, allemaal groen.

## Apparatentabel toonde overal "None" (v1.14.2)

**Gemeld**: *"Moet deze data nog opbouwen?"* — met een screenshot van 38
apparaten met "None W" en "None%" in elke kolom.

### Nee, de data was er wel

Het sjabloon vroeg sleutels op die niet bestaan: `gemiddeld_w`,
`referentie_w` en `drift_procent`. De tabel levert `naam`,
`huidig_vermogen_w` en `trend` — die had ik bij het bouwen van de
detailpagina verzonnen in plaats van opgezocht.

Een sjabloon dat een niet-bestaande sleutel opvraagt geeft stilzwijgend
`None`. Dat is het verraderlijke: de tabel ziet er compleet uit, met alle
38 apparaten netjes op een rij, en het lijkt alsof de meting nog moet
opstarten.

### Beter dan wat er stond

De echte kolommen zeggen ook meer: het **huidige** vermogen en een
beschrijving van de trend, in plaats van drie getallen waarvan er twee
alleen bij drift interessant zijn. Er staat nu ook bij hoeveel apparaten
er in totaal zijn, want de tabel toont er maar een deel.

### Nu bewaakt

Vijf tests die per detailtabel de opgevraagde sleutels vergelijken met
wat de bron werkelijk levert. Dat werkt voor de apparatentabel, de
accumodules, het betrouwbaarheidsoverzicht en de watersessies.

De andere drie bleken correct — bij de accumodules kwam dat doordat de
tabel `**module` uitklapt, dus die sleutels bestaan wel degelijk. Zonder
te controleren had ik daar onnodig aan zitten sleutelen.

**Volledige testsuite**: 1318 tests, allemaal groen.

## Alleen de detailpagina was nog zichtbaar (v1.14.1)

**Gemeld**: *"Zie nu alleen maar een details tabblad meer?"*

### De oorzaak

Home Assistant opent altijd de **eerste** view uit het bestand. In
v1.12.7 zette ik "Details" vóór Overzicht, wat toen niet opviel omdat er
nog een tabbalk was om op door te klikken.

Sinds v1.13.0 is Overzicht de enige zichtbare view. En een subview toont
géén tabbalk — dus je opende het dashboard, kwam op Details terecht, en
had geen enkele manier om ergens anders heen te gaan. Het leek daardoor
uit één losse detailpagina te bestaan.

Details staat nu achteraan; Overzicht opent weer als eerste.

### Nu bewaakt

Twee tests: de eerste view mag **geen subview** zijn, en het is Overzicht.
Die eerste vangt precies deze fout — een subview vooraan maakt het hele
dashboard onbereikbaar, en dat merk je pas als je het opent.

### Onderweg

Drie tests zochten de detailpagina op als "de eerste subview". Sinds
v1.13.0 alles subview is, was dat Visueel geworden. Die zoeken nu op
naam.

**Volledige testsuite**: 1313 tests, allemaal groen.

## Zelfevaluatie: de integratie beoordeelt haar eigen instellingen (v1.14.0)

**Gevraagd**: *"Kun je een mechanisme bedenken waardoor de integratie
zichzelf verbetert? Dus tips geeft welke verbetermogelijkheden er zijn?"*

### Eerst de afbakening

Zichzelf herschrijven kan ze niet. En automatisch bijstellen wíl je niet:
de reserveberekening is eerder expliciet afgeschermd, en een systeem dat
ongevraagd zijn eigen veiligheidsmarges verlaagt is precies wat er mis
kan gaan.

Wat wél kan — en waar alle data al voor ligt — is **achteraf toetsen of
een keuze goed uitpakte**. Dat is meetbaar, geen giswerk.

### Vier dingen die worden nagerekend

**Staat de nachtreserve te ruim?** Er wordt per dag bijgehouden of de
reserve tekortschoot of juist over was. Dertig dagen overschot en nul
tekorten betekent: die energie had in het dure blok verkocht kunnen
worden. Omgekeerd, bij meer dan 20% tekort-dagen, moet er tegen de
ochtendprijs worden bijgekocht.

**Wordt de accu wel benut?** Blijft de laagste stand over veertien dagen
boven de 40%, dan ligt er capaciteit stil — mogelijk staat de minimale
SoC hoger dan nodig.

**Verzamelen er modules eeuwig zonder resultaat?** Een module die na
dertig dagen nog op "onvoldoende data" staat, wacht waarschijnlijk op een
sensor die er niet is.

**Is er variatie in de beslissingen?** Komen er in veertien dagen maar
één of twee redenen voor, dan zijn de prijsverschillen te klein om op te
sturen — of staat een drempel zo dat er zelden iets verandert.

### Elk voorstel noemt zijn bewijs

> *"In 30 dagen was er 30x energie over aan het eind van de nacht en geen
> enkele keer tekort."*

Zodat je het kunt narekenen vóór je iets verandert. Er staat ook bij
wanneer je moet oppassen: een zachte periode vertekent, dus controleer
eerst of die dagen representatief waren.

Een voorstel zonder bewijs is een mening; bewijs zonder voorstel laat je
met de vraag zitten wat je ermee moet. Daar staat een test op.

### Waar het verschijnt

De bevindingen komen in dezelfde lijst als de bestaande
configuratie-adviezen — voor jou is het onderscheid tussen "je mist een
sensor" en "je instelling pakt slecht uit" niet interessant; beide zijn
verbetermogelijkheden. Te zien op de detailpagina en in de
diagnostiek-export.

### Getest

Nieuw `tests/test_self_evaluation.py`, 12 tests: een te ruime reserve
wordt gemeld, een te krappe ook, een gezonde balans zegt niets, te weinig
dagen geeft geen oordeel, een onbenutte accu wordt gemeld en een goed
benutte niet, weinig variatie wordt gesignaleerd, elk bevinding heeft
bewijs én voorstel, er wordt **niets automatisch gewijzigd**, de
bevindingen komen in de adviezenlijst, en het staat in de export.

**Volledige testsuite**: 1311 tests, allemaal groen.

## Labels op Financieel pasten niet (v1.13.2)

**Gemeld**: *"Op dit tabblad zijn alle teksten ook niet goed zichtbaar,
net als op de landingspagina, graag dit op alle tabbladen herzien."*

### Waarom de test dit had moeten vangen

In v1.12.6 heb ik een test gebouwd die labels toetst aan de breedte van
hun tegel. Die keek alleen naar kaarten met een **expliciete**
kolombreedte — en kaarten binnen een `grid` hebben die niet.

Precies waar het misging: op Financieel zit bijna alles in grids. Twaalf
te lange labels bleven daardoor onopgemerkt tot ze op een screenshot
opvielen.

Erger nog: de test ging bij een ontbrekende breedte uit van de **volle**
breedte (48 tekens), terwijl kaarten in een grid juist smal zijn. De
aanname stond dus precies verkeerd om.

### Wat er afgekapt werd

| Label | Tekens |
|---|---|
| Besparing t.o.v. zonder accu-sturing (vandaag) | 46 |
| Onverwachte netimport-dagen (laatste 7) | 39 |
| Piekvermogen deze maand (netimport) | 35 |
| Geschatte resterende capaciteit | 31 |

Twaalf labels ingekort, plus twee **sjabloonlabels** die hun tekst
dynamisch opbouwen en daarom nooit werden getoetst: *"Accubesparing
(kostprijs-model) — huidige kostprijs: € …/kWh"* en *"Uitstoot vandaag
(huidige intensiteit: … g/kWh)"*.

### Nu bewaakt

De helper kijkt nu ook ín grids — 44 labels in plaats van een handvol —
en gaat bij een ontbrekende breedte uit van **smal** in plaats van breed.
Het langste label is nu 22 tekens, precies de grens.

Twee tests erbij: één die vastlegt dat er daadwerkelijk in de grids wordt
gekeken (anders zou de helper stilletjes terug kunnen vallen), en één op
de twee sjabloonlabels.

### Getest

**Volledige testsuite**: 1299 tests, allemaal groen.

## Koppen raakten los van hun kaarten (v1.13.1)

**Gemeld**: *"De zelflerend titel staat nog niet correct op de pagina."*
Met een screenshot waarop "Zelflerend" onderaan de linkerkolom stond,
terwijl de bijbehorende kaart bovenaan de rechterkolom hing — onder een
andere kop.

### De oorzaak

Het Systeem-tabblad gebruikte de standaard **masonry**-indeling. Die
verdeelt kaarten over kolommen op basis van hoogte, zonder te weten dat
een kop bij de kaart eronder hoort. Bij vier koppen op één tabblad gaat
dat gegarandeerd mis.

Met `type: sections` blijft elk groepje bij elkaar, hoe de kolommen ook
vallen.

### Verloop had hetzelfde probleem

Drie koppen, acht kaarten. Ook omgezet — daar was het nog niet opgevallen
omdat de grafieken toevallig gunstig uitvielen.

Onderweg bleek "Live" een kop **zonder eigen kaart**: de live-uitleg zat
in de groep erna. Samengevoegd, want een kop zonder inhoud toont een
titel waar niets onder staat.

### Nu bewaakt

Twee tests: een tabblad met meer dan één kop moet `type: sections`
gebruiken, en geen enkele sectie mag alleen uit een kop bestaan.

Die eerste vangt het probleem bij de bron. Voeg je later een derde kop
toe aan een masonry-tabblad, dan faalt hij meteen in plaats van dat je
het pas op een screenshot ziet.

### Getest

Twee tests erbij in `test_compact_dashboard.py`; één bestaande test las
`view["cards"]` en moest leren dat secties ook kaarten bevatten.

**Volledige testsuite**: 1295 tests, allemaal groen.

## Alleen Overzicht in de tabbalk (v1.13.0)

**Gevraagd**: *"De tabbladen moeten standaard niet zichtbaar zijn, ik wil
het alleen zien als ik daadwerkelijk op 'meer info' klik. Een popup zou
ook kunnen."*

### Alles is een subview geworden

Visueel, Meldingen, Kwaliteit, Systeem, Financieel en Verloop staan niet
meer in de tabbalk. Je opent het dashboard en ziet één scherm.

### Met een sectie "Meer bekijken"

Zes tegels onderaan Overzicht, elk met een regel die zegt waar je
terechtkomt:

- **Systeem** — accu en apparaten
- **Financieel** — kosten en besparing
- **Verloop** — wat er gebeurde
- **Kwaliteit** — betrouwbaarheid
- **Meldingen** — aan/uit en historie
- **Visueel** — plattegrond

Zonder die tegels zouden de pagina's alleen via de URL te vinden zijn, en
dus praktisch onbereikbaar. Er staat nu een test op dat **elke verborgen
pagina een ingang heeft**, en een tweede dat geen enkele tegel naar een
niet-bestaande pagina wijst.

### Over de popup

Dat kan met `browser_mod`, maar dat is een extra installatie via HACS.
Subviews zijn ingebouwd en werken op elk apparaat, dus die keuze leek me
beter — zeker omdat het gedrag hetzelfde is: je ziet het pas als je
erom vraagt.

### Onderweg

De testhelper filterde op `subview` om de detailpagina uit te sluiten.
Nu álle tabbladen subviews zijn, viel daarmee bijna alles buiten de
controle; die filtert nu op naam.

En mijn eigen labeltest uit v1.12.6 ving meteen vier te lange
ondertitels op de nieuwe tegels — "Aan- en uitzetten, en de
geschiedenis" is 37 tekens waar er 22 passen.

### Getest

Nieuw `tests/test_navigation.py`, 5 tests: alleen Overzicht is zichtbaar,
elke verborgen pagina is bereikbaar, de navigatiesectie bestaat, elke
tegel zegt waar hij heen gaat, en geen enkel pad wijst nergens heen.

**Volledige testsuite**: 1290 tests, allemaal groen.

## Het doorklik-principe voor élke kaart (v1.12.8)

**Gevraagd**: *"Graag voor alle cards doen die dit principe moeten
hanteren."*

### Negen tegels deden nog niets

Binnen de grid-kaarten op Financieel zaten tegels met losse bedragen —
ontlaadwaarde, netlaadkosten, accubesparing — die geen `tap_action`
hadden. Je kon erop tikken en er gebeurde niets.

Die tonen één getal, dus daar is **more-info** het juiste detail: de
grafiek van dat bedrag over tijd. Niet de detailpagina; die zou je juist
weghalen van wat je wilt zien.

### Twee keer hetzelfde

De verbetermogelijkheden stonden zowel op Kwaliteit als op de
detailpagina. Nu alleen op de detailpagina, waar de GACS-tegel heen
wijst. Ook de uitleg bovenaan Kwaliteit is weg — die was in v1.12.4 al
bedoeld te verdwijnen maar bleek er nog te staan.

Kwaliteit houdt drie tegels over: betrouwbaarheid, zelflerende waarden,
GACS.

### Drie soorten volgen het principe bewust niet

| Soort | Waarom |
|---|---|
| Schakelaars | tikken **schakelt**; navigeren zou verhinderen waar ze voor zijn |
| Grafieken | die **zijn** al het detail |
| Markdown | ondersteunt geen `tap_action` in Home Assistant |

Die uitzonderingen staan nu als lijst in een test. Komt er een vierde
soort bij zonder doorklik, dan faalt hij — en moet iemand uitleggen
waarom dat terecht is.

### De regel, samengevat

- **Samenvatting** → detailpagina
- **Meetwaarde** → eigen geschiedenis
- **Schakelaar** → schakelt
- **Grafiek** → is het detail

### Onderweg

Mijn eerste poging verwijderde de verbetermogelijkheden van de
*detailpagina* in plaats van van Kwaliteit — die kaart staat eerder in
het bestand. De test die controleert of de detailpagina compleet is, ving
dat meteen.

### Getest

Drie tests erbij: élke tegel overal is aanklikbaar, de uitzonderingen
zijn een expliciete lijst, en niets staat twee keer.

**Volledige testsuite**: 1287 tests, allemaal groen.

## "Tik voor details" leverde niets op (v1.12.7)

**Gemeld**: *"Bij een tik zie ik nog geen details?"* — met een screenshot
van de standaard more-info van Home Assistant: geschiedenis, een balkje,
en "Geen activiteit gevonden".

### De oorzaak

Home Assistant toont in more-info **geen attributen**. Alleen de
toestand, de geschiedenis en het logboek.

Sinds v1.12.4 was elke tegel aanklikbaar, en in v1.12.0 haalde ik alle
tabellen weg met het argument dat de onderbouwing "in de attributen
blijft". Dat klopte technisch — de gegevens zaten er wel degelijk in —
maar er was geen manier om ze te zíén. De belofte was dus loos.

### Een verborgen detailpagina

Een **subview** staat niet in de tabbalk maar is bereikbaar via navigate.
Zo blijven de tabbladen summier én is het detail één tik weg — zonder
dat de tabbalk weer voller wordt, wat in v1.12.2 juist is teruggebracht.

Daarop staat alles wat is weggehaald: de volledige aandachtspunten met de
informatieve regels, de betrouwbaarheidstabel per grootheid, de
verbetermogelijkheden, de accumodules met celdelta en temperatuur, de
herkende apparaten met hun drift, en de watersessies van vandaag.

Negen samenvattingstegels wijzen er nu heen.

### Wat bewust more-info houdt

Tegels met een **losse meetwaarde** — accustand, netstroom, prijs. Daar
is de grafiek in more-info juist wél het nuttige detail; die zou je
kwijtraken door naar een tabel te navigeren.

Het onderscheid is dus: een **samenvatting** leidt naar de detailpagina,
een **meetwaarde** naar zijn eigen geschiedenis.

### Zes tests moesten mee

Twee namen aan dat `views[0]` het Overzicht is — de subview staat er nu
vóór. Drie pasten de compactheidsregels ook op de detailpagina toe,
terwijl die juist de tabellen hóórt te bevatten. En één eiste `more-info`
op de statuskaart.

### Getest

Nieuw `tests/test_detail_subview.py`, 6 tests: de pagina is een subview,
staat niet in de tabbalk, bevat de zes weggehaalde onderdelen, toont de
aandachtspunten volledig, de samenvattingstegels navigeren erheen, en de
meetwaardetegels houden more-info.

**Volledige testsuite**: 1287 tests, allemaal groen.

## Labels pasten niet in de tegels (v1.12.6)

**Gemeld**: *"De rendement card is wel volledig leesbaar, de rest niet,
graag optimaliseren."*

Precies de goede waarneming: die ene kaart stond op **volle breedte**, de
rest op de halve.

### Wat er afgekapt werd

| Label | Tekens |
|---|---|
| Grootverbruiker bevestigd actief (omzeilt mediaan-vertraging) | 61 |
| Boven prijsdrempel (hele dag, capaciteit-begrensd) | 50 |
| Zonnepaneel-vermogenslimiet (bij negatieve prijs) | 49 |
| Netstroom, P1 (kan negatief zijn bij export) | 44 |
| Werkelijke modus (Zendure — alleen weergave) | 44 |

Een tegel op zes kolommen toont er ongeveer 22. Je zag dus *"Netstroom,
P1 (kan n…"* — je weet dát er iets staat maar niet wát, en dan is de
tegel onbruikbaar zonder erop te klikken.

### Negen labels ingekort, besturing verbreed

De uitleg tussen haakjes is eruit; die staat toch in de attributen, en
elke tegel is sinds v1.12.4 aanklikbaar.

De besturingssectie stond op vier kolommen — te smal voor
"Steelstofzuiger overrule" en "Vaatwasser/wasmachine-meldingen". Nu zes
kolommen, en die namen zijn "Steelstofzuiger", "Fietsladers" en
"Apparaatmeldingen" geworden.

### Nu bewaakt

Een test rekent per kaart uit hoeveel tekens er passen bij zijn
kolombreedte (15 bij vier, 22 bij zes, 48 bij twaalf) en faalt op elk
label dat eroverheen gaat. Sjablonen worden overgeslagen: die berekenen
hun eigen tekst.

Plus een test dat het inkorten de betekenis niet heeft weggenomen — "PV-
limiet" moet herkenbaar blijven — en dat de volledige uitleg bereikbaar
blijft doordat elke tegel doorklikt.

### Getest

Nieuw `tests/test_dashboard_label_length.py`, 4 tests.

**Volledige testsuite**: 1281 tests, allemaal groen.

## Uitgezette meldingen blijven nalees baar (v1.12.5)

**Gevraagd**: *"Als ik door een button een melding uitzet moet hij niet
meer naar mijn iPhone, maar nog wel zichtbaar zijn in [de
geschiedenis]."*

Terecht onderscheid, en het was er niet.

### Uitzetten was hetzelfde als weggooien

Een geblokkeerde melding sloeg de geschiedenis over. Zette je een soort
uit, dan verdween hij compleet — ook uit de lijst die je juist gebruikt
om achteraf te kijken wat er gebeurde.

Nu bepaalt de schakelaar alleen of je **telefoon rinkelt**. Vastleggen
gebeurt altijd, met een 🔕 in de tabel en de reden erbij: *"deze melding
staat uit"* of *"hoofdschakelaar staat uit"*.

Zonder die markering zou het lijken alsof de schakelaar niets doet.

### Demping werkt bewust anders

Het dempingsvenster bestaat juist om **herhaling** te voorkomen. Die
herhaling dan alsnog vastleggen zou de geschiedenis volschrijven met
dubbele regels — precies waar hij onbruikbaar van wordt.

Hetzelfde geldt voor de aanlooptijd na een herstart: die gaat over
timing, niet over een keuze van jou.

Het onderscheid is dus: **een keuze van de gebruiker** wordt vastgelegd,
**een timingregel** niet.

### Onderweg

Twee bestaande tests eisten een lege geschiedenis bij een uitgeschakelde
melding — precies de aanname die nu omkeert. Die controleren nu dat er
niets naar de telefoon gaat én dat de regel wél in de geschiedenis staat.

### Getest

Nieuw `tests/test_notification_history_when_disabled.py`, 9 tests: een
uitgezette melding wordt vastgelegd maar niet verstuurd, de reden staat
erbij, de hoofdschakelaar gedraagt zich hetzelfde, een verstuurde melding
wordt als verstuurd gemarkeerd, een gedempte herhaling wordt níét
vastgelegd, de aanlooptijd evenmin, de tabel markeert het, en het geldt
voor alle tweeëntwintig soorten.

**Volledige testsuite**: 1277 tests, allemaal groen.

## Overal hetzelfde: conclusie op de kaart, detail door te tikken (v1.12.4)

**Gemeld**: *"Misschien dit nu voor alles toepassen (dus sumiere
informatie op de dashboards/tabbladen) en wanneer meer informatie gewenst
is dit door middel van op de card klikken zichtbaar maken?"*

Dat is het principe dat er al half in zat. Nu overal.

### Elke tegel is te openen

Eenentwintig kaarten toonden een conclusie zonder dat je erop kon
klikken. Dat laat je met de vraag zitten zonder een manier om hem te
beantwoorden — precies wat er bij de statuskaart misging.

Er staat nu een test op dat élke tegel met een entiteit een `tap_action`
heeft.

### Financieel was het laatste bastion

Drie tabellen van samen **ruim 4000 tekens**: de Zonneplan-afrekening,
week/maand/jaar met trends, en het maandoverzicht.

Nu twee tegels:

- *"−0,03 € vandaag — stroom −0,16 €, gas 0,13 €. Eigen berekening klopt
  met Zonneplan."*
- *"−1,53 € stroom deze week — gas 0,23 €. Week 📉 −12%"*

Het maandoverzicht verviel: die cijfers stonden al in de tweede tegel.
Alle onderliggende bedragen blijven in de attributen.

### Nog twee toelichtingen weg

De uitleg bovenaan Kwaliteit ("alleen de conclusie per onderwerp…") was
zelf de langste tekst op dat tabblad geworden. En de rendementsregel op
Overzicht stond pal naast de rendementstegel.

### De stand

| Tabblad | Kaarten | Tekst |
|---|---|---|
| Overzicht | 24 | 0 |
| Meldingen | 26 | 1217 |
| Financieel | 12 | **0** |
| Systeem | 9 | 0 |
| Verloop | 8 | 493 |
| Kwaliteit | 5 | 293 |
| Visueel | 1 | 0 |

Van 145 kaarten en duizenden tekens naar **85 kaarten en 2000 tekens**,
waarvan de helft op het Meldingen-tabblad — een bedieningspaneel, geen
leespagina.

### Vier tests moesten mee

Die bewaakten de Zonneplan-tabel. De garantie geldt nog, alleen ergens
anders: de beperking ("dit toetst niet de accu-boekhouding") staat nu in
het **oordeel zelf**, want dat is wat je ziet als je doorklikt. Verzwijgen
zou de vergelijking geloofwaardiger laten lijken dan ze is.

### Getest

Drie tests erbij: elke tegel is aanklikbaar, geen tabblad heeft meer dan
800 tekens tekst, en Financieel gebruikt tegels in plaats van tabellen.

**Volledige testsuite**: 1265 tests, allemaal groen.

## Statuskaart terug, en drift-meldingen over tienden van watts (v1.12.3)

**Gemeld**: *"Welke status kaart?"* — plus een nieuwe diagnostiek.

### De verwijzing klopte niet

De aandachtspunten-kaart zei *"Tik op de statuskaart voor de details"*,
maar die kaart had ik in v1.12.1 zelf weggehaald. En een markdown-kaart
is niet aanklikbaar, dus de verwijzing wees nergens heen.

Nu is de kaart zélf de ingang: een tegel die je kunt aantikken voor alle
details, met de eerste regel van het aandachtspunt er al in. De test
controleert nu ook dat hij een `tap_action` heeft — anders is "tik voor
details" opnieuw een loze belofte.

### Vijf apparaten "mogelijk defect", waarvan vier onzin

De export toonde vijf van de 38 apparaten als afwijkend:

| Apparaat | Referentie | Drift | Werkelijk verschil |
|---|---|---|---|
| Televisie | 0,79 W | −24,2% | **0,19 W** |
| Diepvries | 0,85 W | −15,4% | **0,13 W** |
| IPTV | 2,49 W | +14,9% | **0,37 W** |
| Oplader tablet | 2,84 W | +46,8% | **1,33 W** |
| Koelkast schuur | 8,30 W | +716% | 59,4 W |

Alleen die laatste is echt iets. Een **procentuele** drempel is bij zulke
kleine vermogens betekenisloos — meetruis van een tiende watt is al
vijftien procent.

Er gelden nu twee ondergrenzen: het apparaat moet minstens 5 W
verbruiken, **en** het verschil moet minstens 5 W zijn. Beide zijn nodig:
een apparaat van 200 W dat 2 watt meer trekt is evenmin een beginnend
defect.

Getoetst tegen je echte cijfers: van vijf meldingen naar één. Een
koelkast die van 80 naar 110 W gaat, blijft gewoon melden.

### Waarom dit ertoe doet

Vijf meldingen waarvan er vier over tienden van watts gaan, leert je die
meldingen te negeren — en dan mis je de keer dat er echt iets stukgaat.
Dat is hetzelfde patroon als bij de nachtreserve (v1.9.3) en de
sensoruitval (v1.11.0).

### Onderweg

Drie bestaande CUSUM-tests draaiden op 6,2 W en vielen daarmee onder de
nieuwe drempel. Die zijn opgeschaald naar 62 W — een realistisch
apparaat. Daarbij schaalde ik per ongeluk ook de CUSUM-waarden mee, die
geen watts zijn; twee tests vingen dat.

### Getest

Nieuw `tests/test_nilm_drift_thresholds.py`, 7 tests: een klein apparaat
triggert niet, een klein percentage op een klein apparaat evenmin, een
echt apparaat wél, een grote sprong op een bescheiden apparaat ook, een
groot apparaat met een kleine verandering blijft stil, de drempels zijn
vastgelegd, en de vijf echte gevallen leveren nog één melding op.

**Volledige testsuite**: 1266 tests, allemaal groen.

## Van tien naar zeven tabbladen (v1.12.2)

**Gemeld**: *"Sommige tabbladen zijn nu zo leeg dat het beter is deze
samen te voegen op 1 tabblad, en dan met een titel aangeven wat deze
toont."*

Terecht — het opruimen van v1.12.0 was zo grondig dat er tabbladen
overbleven met één kaart. Ernaartoe klikken om één regel te lezen kost
meer aandacht dan het oplevert.

### Nieuw tabblad "Systeem"

| Samengevoegd | Had |
|---|---|
| Accumodules | 1 kaart |
| Apparaten | 1 kaart |
| Zelflerend | 1 kaart |
| Klimaat & water | 2 kaarten |

Elk onderwerp krijgt een kop die zegt **wat je ziet** — zonder
tabbladnaam is dat anders niet meer af te leiden:

- *Accumodules — celspreiding en onderlinge afwijking*
- *Apparaten — herkende huishoudapparaten en hun verbruik*
- *Zelflerend — waarden die de integratie zelf leert*
- *Klimaat & water — woonkamertemperatuur en waterverbruik*

### De stand

| Tabblad | Kaarten |
|---|---|
| Overzicht | 24 |
| Meldingen | 26 |
| Financieel | 13 |
| Systeem | 9 |
| Verloop | 8 |
| Kwaliteit | 5 |
| Visueel | 1 |

Van vijftien tabbladen en 145 kaarten naar **zeven en 86**.

### Nu bewaakt

Drie tests erbij: geen tabblad houdt minder dan drie kaarten over
(Visueel uitgezonderd, dat is één schermvullende plattegrond), elk
onderwerp op Systeem heeft een eigen kop, en elke kop heeft een
ondertitel die uitlegt wat je ziet.

Die eerste voorkomt dat een volgende opruimronde opnieuw lege tabbladen
achterlaat — precies wat er nu gebeurde.

**Volledige testsuite**: 1256 tests, allemaal groen.

## Overzicht past nu op één scherm (v1.12.1)

**Gemeld**: *"Tevens het overzichts dashboard herzien: Ik wil eigenlijk
niet hoeven scrollen. Het info veld bijvoorbeeld, mag nu wel weg, omdat
de info nu bekend is."*

De screenshot liet zien wat het probleem was: de aandachtspunten-kaart
was uitgegroeid tot een blok van vijftien regels waarin vijf apparaten,
twee weerbronnen en een waterverklaring achter elkaar stonden.

### Van 31 naar 24 kaarten, van ~2700 naar 751 tekens

| Weg | Waarom |
|---|---|
| Uitleg over de kwartiertelling | die uitleg is inmiddels bekend |
| Lang statusblok (1234 tekens) | herhaalde wat de tegels ernaast al tonen |
| Aandachtspunten uitgeschreven | nu een telling; de inhoud komt als melding |
| Sectie "Kernbeslissing (detail)" | uitklaplijst met onderliggende sensoren |
| Sectie "Advies-modules (detail)" | idem |

De aandachtspunten-kaart is nu één regel: *"⚠️ 3 aandachtspunt(en) —
hiervan krijg je een melding. Tik op de statuskaart voor de details."*

Dat sluit aan bij wat je eerder aangaf: liever een melding bij een
probleem dan een muur informatie die je moet doorlezen.

### Wat bleef

De tegels met accustand, rendement, netstroom, prijs en modus — dat is
waar je op een landingspagina naar kijkt. En de besturingssectie met de
schakelaars, want dat is het enige tabblad waar je iets *doet*.

### Twee keer misgegaan onderweg

Mijn eerste knip liep één regel te ver door, waardoor twee secties
samenvloeiden. Hersteld uit de laatst opgeleverde zip en opnieuw gedaan,
ditmaal met de inspringing als grens in plaats van een tekstpatroon.

En mijn vervanging van de aandachtspunten-kaart voegde een tweede kaart
toe in plaats van de eerste te overschrijven — de nieuwe test vond die
meteen.

### Getest

Drie tests erbij: de landingspagina heeft minder dan 1600 tekens tekst,
de aandachtspunten-kaart is een telling en geen uitgeschreven lijst, en
er staan geen detailsecties meer op.

**Volledige testsuite**: 1256 tests, allemaal groen.

## Dashboards opgeruimd: conclusie in plaats van tabel (v1.12.0)

**Gemeld**: *"Ik vind de dashboards veel te druk, het is zoveel dat het
niet meer overzichtelijk is. Graag opruimen. Het de meeste info
(tabellen) graag in een zin weergeven of het betrouwbaar is of niet. Ik
zie liever iets verschijnen in meldingen als het niet correct is."*

Terecht, en het legt een patroon bloot: er is de hele tijd informatie
bijgekomen zonder dat er ooit iets áfging.

### Van 145 naar 90 kaarten

| Tabblad | Was | Nu |
|---|---|---|
| Kwaliteit | 13 | 4 |
| Accumodules | 6 | 1 |
| Zelflerend | 8 | 1 |
| Apparaten | 8 | 1 |
| Klimaat & water | 10 | 2 |
| Verloop | 8 | 6 |
| Financieel | 16 | 10 |

Elk onderwerp toont nu **één zin met de conclusie**:

- *"Alle 3 modules lopen gelijk; grootste celspreiding 0,05 V."*
- *"2 van de 38 apparaten verbruikt meer dan normaal: IPTV, Koelkast schuur."*
- *"4 gebruiksmoment(en) vandaag, 82 liter."*

Bij een probleem staat er **wát** er mis is, niet alleen dát er iets is —
anders moet je alsnog gaan zoeken, en dat was precies het probleem.

### Er gaat niets verloren

De onderbouwing blijft volledig beschikbaar: tik op een kaart voor alle
attributen, of pak de diagnostiek-export. De tabellen staan niet meer
standaard open, dat is het verschil.

### Wat bewust bleef staan

**Financieel** houdt zijn tabellen: daar *zijn* de bedragen de inhoud.
Week-, maand- en jaarcijfers naast elkaar is precies wat je van dat
tabblad verwacht; die in een zin persen zou informatie kosten in plaats
van ruis besparen. De lange toelichting bij de Zonneplan-vergelijking is
wel teruggebracht van ~25 naar 4 regels.

**Meldingen** blijft ongewijzigd — dat is een bedieningspaneel, geen
informatiepagina. En **Overzicht** is de landingspagina.

Op Apparaten, Zelflerend en Klimaat & water bleven de grafieken staan:
die tonen verloop, en dat vang je niet in een zin.

### De opruiming raakte twintig tests

Die bewaakten tabellen die nu niet meer bestaan. Waar de onderliggende
garantie nog geldt, zijn ze omgezet naar de **data** in plaats van de
weergave — elke adviesmodule moet nog steeds in het
betrouwbaarheidsoverzicht staan, de duplicaatknoppen moeten blijven
bestaan, de watersessies moeten in de export blijven. Dat is wat er
werkelijk toe doet en het blijft gelden ongeacht hoe het dashboard het
toont.

Tests die puur over verdwenen sjablonen gingen, zijn verwijderd in plaats
van uitgeschakeld: een uitgezette test die blijft staan is verwarrender
dan geen test.

### Nu bewaakt

Nieuw `tests/test_compact_dashboard.py`, 9 tests: geen tabellen van meer
dan drie regels buiten Overzicht, Meldingen en Financieel; opgeruimde
tabbladen blijven onder de tien kaarten; geen tabblad raakt leeg; elke
samenvatting heeft een zin én een niveau; een zin is echt een zin (geen
tabel of opsomming); de zwakste schakel bepaalt het niveau; een probleem
wordt bij naam genoemd; het detail staat nog in de export; en de zinnen
zitten op een sensor.

**Volledige testsuite**: 1253 tests, allemaal groen.

## Stilstaande geleerde waarden opsporen (v1.11.1)

**Gevraagd**: *"kijken naar alle waarden welke gegenereerd worden en
mogelijk niet goed werken doordat ze lang stilstaan of juist al zo
betrouwbaar zijn dat ze niet meer wijzigen."*

Dat is precies het onderscheid dat nergens te maken viel.

### Wat de export liet zien

Van alle geleerde reeksen stond er één volledig stil:
`steelstofzuiger_idle_power_history_w`, acht keer 0,0 W.

Dat is volstrekt plausibel — een lader die niets doet verbruikt niets.
Maar het is **niet te onderscheiden** van een meting die stilletjes is
gestopt. Beide zien er in de export exact hetzelfde uit.

De andere reeksen bewegen gezond: klimaatbias 43 unieke waarden op 100,
energiebalans 14 op 14, accu-rendement 7 op 7.

### De oplossing is niet oordelen maar melden

Er wordt nu gezocht naar reeksen die niet meer veranderen, met het
**aantal metingen** erbij — acht identieke waarden zegt weinig, tachtig
identieke waarden bij een grootheid die hoort te fluctueren zegt veel.

En er is onderscheid tussen twee soorten:

| Soort | Voorbeeld | Oordeel |
|---|---|---|
| Constante waarde is **normaal** | ruststroom van een lader, laadduur | geen melding |
| Grootheid **hoort te fluctueren** | accu-rendement, nachtverbruik | informatieve regel |

Die eerste categorie is een expliciete lijst met twee fragmenten. Wie
daar iets aan toevoegt moet kunnen uitleggen waarom stilstand daar te
verwachten is, in plaats van dat het stilzwijgend meeglipt — daar staat
een test op.

Lijsten van `True`/`False` tellen niet mee: die "staan stil" per
definitie vaak en zijn geen meetreeks.

### Eén ding dat geen bug bleek

De export toont nog een waterontharder-regeneratie van 00:28 met 3,1
liter — precies het geval dat v1.9.2 afwijst. Nagekeken: die detectie
gebruikt wél de nieuwe volumedrempel. Het is een registratie van vóór de
update.

### Getest

Nieuw `tests/test_stalled_series.py`, 9 tests: een constante ruststroom
is verwacht, een constante geleerde waarde is verdacht, alleen de
verdachte worden gemeld, een fluctuerende reeks niet, een korte reeks
krijgt geen oordeel, het aantal metingen staat erbij, booleans tellen
niet mee, de uitzonderingenlijst blijft klein en expliciet, en het staat
in de export.

**Volledige testsuite**: 1257 tests, allemaal groen.

## Opstart telt niet meer mee, melding pas bij echte uitval (v1.11.0)

**Gemeld**: *"sensor.zendure_manager_available_kwh heeft langer nodig om
op te starten... Ik wil dat na een herstart niet mee telt in analyses van
sensor kwaliteit en de melding ook pas laten komen als hij ECHT
onbeschikbaar zou zijn."*

De export bevestigde het precies:

| | |
|---|---|
| Score | 70% ("verminderd") |
| Werkelijke vergelijkingen | 14, **allemaal binnen de marge** (4–110 W) |
| Ontbrekende metingen | 6, **aaneengesloten aan het eind** |

Die zes stonden niet verspreid maar op een rij — de opstartperiode. De
Zendure-integratie had nog geen waarde toen deze coordinator al draaide.

### Tijdens de opstart wordt er niets geregistreerd

Niet als goede meting en niet als slechte. **Geen meting is eerlijker dan
een slechte meting** — en als "goed" tellen zou een echte storing vlak na
een herstart verbergen.

Tien minuten, ruimer dan de drie minuten voor meldingen. De reden: de
gezondheidsscore kijkt terug over twintig metingen, dus daar weegt een
verkeerde registratie veel langer door dan bij een melding die eenmalig
afgaat. Daar staat een test op.

### De melding komt pas bij aanhoudende uitval

Vijftien minuten onbeschikbaar voordat er iets afgaat, gemeten vanaf het
**eerste** moment dat de sensor wegviel — niet vanaf de laatste tick. Komt
hij tussendoor terug, dan begint de teller opnieuw; anders zou een korte
hapering later alsnog als lange uitval gelden.

Een enkele gemiste uitlezing komt voor bij elke cloudgebonden integratie.
Daarover melden leert je meldingen te negeren, en dan mis je de keer dat
het wél echt misgaat.

### Onderweg

Acht bestaande tests gingen ervan uit dat één ontbrekende meting meteen
meldt — die aanname is nu bewust veranderd, dus ze simuleren aanhoudende
uitval.

En de nieuwe tests faalden eerst op iets subtielers:
`_dispatch_notification` gebruikt intern de echte klok voor het
dempingsvenster, terwijl de test een eigen tijdstip hanteerde. Het
verschil daartussen viel binnen de aanlooptijd, waardoor de melding
terecht werd geweigerd. Opgelost door de klok te bevriezen.

### Getest

Nieuw `tests/test_startup_and_real_outage.py`, 9 tests: tijdens de
opstart wordt niets geregistreerd, daarna weer wel, de aanlooptijd is
ruimer dan die voor meldingen, zonder starttijd verandert er niets, een
enkele gemiste uitlezing wordt niet gemeld, aanhoudende uitval wél (met
de sensornaam en de duur), een herstelde sensor wist de teller, de teller
loopt vanaf het eerste gemis, en een beschikbare sensor wordt nooit
gemarkeerd.

**Volledige testsuite**: 1248 tests, allemaal groen.

## Overbodige koppen uit de tabbladen (v1.10.2)

**Gevraagd**: *"Kun je nog eens kijken naar de dashboards, en irrelevante
informatie uit tabbladen halen behalve uit Overzicht."*

### Eerst gemeten wat er dubbel stond

Van alle entiteitverwijzingen kwamen er maar **drie** op meerdere
niet-Overzicht-tabbladen voor, en die bleken bij inspectie geen
duplicatie: NILM staat op Kwaliteit als *adviesmodule* en op Apparaten
als *apparaatlijst* — twee verschillende invalshoeken op dezelfde sensor.

Ook geen kaarten die naar niet-bestaande sensoren wijzen. Twee
verdachten (`washing_machine_typical_usage_hours` en
`..._last_notification`) bleken dynamisch aangemaakt per apparaat en dus
correct.

### Wat er wél overbodig was: tien koppen

De samenvoeging van v1.10.1 leverde koppen op die hetzelfde zeiden als
de kaart eronder — "Betrouwbaarheid" boven "Hoe hard is dit cijfer?",
"GACS" boven "GACS-zelfbeoordeling", "Advies" boven "Advies-gereedheid",
"Water" boven "Waterverbruik".

En vijf tabbladen begonnen met een kop die gelijk was aan de
tabbladnaam zelf: Financieel, Meldingen, Zelflerend, Apparaten, Klimaat.
De naam staat al bovenaan het scherm.

Tien koppen weg, geen enkele kaart met inhoud verwijderd.

### De tests vonden er meer dan ik

Ik had er zelf vijf gevonden. De twee borgingstests die ik daarna schreef
vonden er nog **vijf bij** — Advies, Water, Meldingen, Zelflerend,
Apparaten. Dat is precies waarom zo'n regel als test beter werkt dan als
handmatige controle.

### Getest

Twee tests erbij in `test_dashboard_tables.py`: geen kop mag herhalen wat
de kop eronder zegt, en geen kop mag gelijk zijn aan de tabbladnaam. De
verwachte kaartaantallen per samengevoegd tabblad zijn meebewogen.

**Volledige testsuite**: 1239 tests, allemaal groen.

## Van vijftien naar tien tabbladen (v1.10.1)

**Gevraagd**: *"Is het mogelijk om tabbladen logisch samen te voegen, ik
krijg er nu wel heel veel."*

Terecht — vijftien is te veel om nog te overzien.

### De samenvoeging

| Nieuw | Uit | Waarom |
|---|---|---|
| **Kwaliteit** | Betrouwbaarheid + Advies + GACS | Alle drie beantwoorden "hoe goed werkt dit systeem" |
| **Financieel** | Financieel + EMS-KPI's | Allebei prestatiecijfers in euro's en kWh |
| **Verloop** | Live + Geschiedenis | Wat gebeurt er nu, en wat gebeurde er |
| **Klimaat & water** | Klimaat + Water | Beide informatieve huismonitoring |

Onveranderd: Overzicht, Visueel, Meldingen, Apparaten, Accumodules,
Zelflerend.

Alle 141 kaarten zijn behouden; er kwamen vier kopjes bij zodat binnen een
samengevoegd tabblad zichtbaar blijft waar het ene onderwerp ophoudt en
het volgende begint.

### Twee dingen bewust niet samengevoegd

**Meldingen** heeft 27 kaarten waarvan 22 schakelaars — dat is een
instellingenpagina, geen informatiepagina. En **Accumodules** blijft
apart van Apparaten: het eerste gaat over de thuisaccu, het tweede over
NILM-huishoudapparaten. Die combineren leest verwarrend.

### Bijna misgegaan

Mijn eerste aanpak las de YAML in en schreef hem opnieuw weg. Dat werkte
functioneel, maar verdubbelde alle aanhalingstekens in de
Jinja-sjablonen — `z.get('...')` werd `z.get(''...'')`. Een bestaande test
ving dat meteen.

Hersteld uit de laatst opgeleverde zip en opnieuw gedaan, ditmaal
**tekstueel**: de blokken verplaatsen zonder de YAML te herschrijven. Dat
laat de sjablonen letterlijk intact.

### Nu bewaakt

Vier tests erbij: geen enkel tabblad is leeg (het teken dat er kaarten
zijn kwijtgeraakt), elk samengevoegd tabblad bevat de inhoud van al zijn
bronnen, Overzicht behoudt zijn `sections`-indeling, en Visueel blijft een
panel-weergave. Die laatste twee zijn eigenschappen die bij een
herindeling makkelijk sneuvelen.

Drie bestaande tests zochten op de oude tabbladnamen. Eén daarvan vroeg
extra zorg: op Kwaliteit staan nu **twee** kaarten met de titel
"Legenda" — die van de betrouwbaarheidsschaal en die van de
adviesmodules. Zoeken op titel alleen pakt dan de verkeerde, dus de
inhoud onderscheidt ze.

**Volledige testsuite**: 1237 tests, allemaal groen.

## GACS-tabblad: de vier eisen als spiegel (v1.10.0)

**Gevraagd**: *"Ja graag uitwerken, met een nieuw tabblad voor GACS zodat
ik hier in het bedrijfsleven van kan leren."*

### Eerst het belangrijkste: dit geldt niet voor een woning

Een gebouwautomatiserings- en controlesysteem is sinds 1 januari 2026
verplicht voor **utiliteitsgebouwen zonder woonfunctie** met een
verwarmings- of koelinstallatie boven **290 kW** — vanaf 2030 boven 70
kW. Een woonhuis valt daar per definitie buiten, en 290 kW is een orde
van grootte hoger dan een woning.

Dat staat bovenaan het tabblad en in de sensor, en er is een test op dat
het er blijft staan. Suggereren dat een woning aan een
utiliteitsverplichting voldoet zou ronduit misleidend zijn.

### Waarom het tabblad er dan toch is

De vier functionele eisen uit het Besluit Bouwwerken Leefomgeving
beschrijven wat zo'n systeem moet kunnen, en die eisen zijn net zo zinnig
voor een woning:

| Eis | Stand |
|---|---|
| Verbruik permanent volgen, analyseren én bijsturen | ✅ |
| Efficiëntie toetsen en rendementsverliezen opsporen | ✅ |
| **Beheerder informeren over verbetermogelijkheden** | **was het zwakst** |
| Communiceren en samenwerken met andere bouwsystemen | ✅ |

Opvallend is hoe laag RVO een energiemanagementsysteem inschat: *"de kans
is klein dat zo'n combinatie voldoet"*, vooral omdat analyseren en
communiceren met andere fabrikanten meestal ontbreken. Hier is juist het
analyseren het sterkste deel.

### De derde eis was het gat

De meldingen zeiden vooral **wat** er is, niet **wat je eraan kunt doen**.
Dat hebben we vandaag drie keer los opgelost — bij de drift-acceptatie,
de wegvallende sensor, het bewolkingslabel. Nu is het structureel.

Zeven soorten advies, allemaal afgeleid uit wat er al gemeten wordt, met
het cijfer erbij zodat je het kunt narekenen. Bij de huidige stand levert
dat er vier op:

- **Accu-rendement 82,9%** — onder 85% gaat er veel verloren; kijk of de
  accu vaak op vol vermogen laadt terwijl er meer tijd is
- **Zelfconsumptie 54%** — de rest gaat het net op tegen het lage tarief;
  apparaten verplaatsen naar de overschot-uren levert meer op
- **IPTV en koelkast verbruiken meer dan normaal** — denk aan
  condensorroosters of een deurrubber
- **PV-dagopwek wordt geïntegreerd** — een kWh-meter instellen geeft een
  exacte waarde

Bewust terughoudend: een lijst met twintig adviezen leest niemand, en dan
is juist deze eis niet ingevuld.

### Eerlijk blijven over de eigen score

Zonder adviezen kan de derde eis **niet** als volledig ingevuld gelden —
dat zou de beoordeling mooier maken dan ze is. Dan staat er dat het
óf goed staat óf dat er te weinig is gemeten, met een verwijzing naar het
Betrouwbaarheid-tabblad om te zien welke van de twee.

### Getest

Nieuw `tests/test_gacs_assessment.py`, 12 tests: de beoordeling meldt dat
de verplichting niet geldt, alle vier de eisen zijn gedekt, elke eis legt
uit hoe eraan wordt voldaan, een laag rendement geeft advies en een goed
rendement niet, lage zelfconsumptie, een driftend apparaat en
geïntegreerde PV geven advies, elk advies heeft een waarneming én een
handeling, de derde eis weerspiegelt de werkelijkheid, monitoring en
interoperabiliteit staan structureel vast, en het tabblad bestaat.

**Volledige testsuite**: 1233 tests, allemaal groen.

## Laatste controle vóór installatie (v1.9.6)

**Gevraagd**: alles nog één keer volledig beoordelen zodat er geen
onvolkomenheden in zitten.

### Wat er goed bleek

Alle Python-bestanden, YAML's en JSON's parsen. 1214 tests groen. Versie,
cachesleutel, CHANGELOG en README lopen gelijk. Elk nieuw onderdeel van
vandaag wordt daadwerkelijk aangeroepen. Geen `print` of `breakpoint`
blijven staan.

### Eén vondst

**Acht configuratievelden hadden geen Nederlands label.** Die tonen dan
de kale sleutel in het formulier — `water_total_usage_sensor_entity` in
plaats van "Watermeterstand in liter". Onder meer de achtertuinsensor,
alle drie de watersensoren, de salderingsdatum en de terugleverkosten.

Aangevuld in alle drie de taalbestanden.

### Zeven controles die nu automatisch draaien

Dit was tot nu toe handwerk, en juist vóór een installatie wil je niet
dat iets afhangt van of iemand eraan dacht:

- elk configuratieveld heeft een Nederlands label
- de Engelse vertaling is compleet (Home Assistant valt daarop terug)
- versie, cachesleutel en CHANGELOG lopen gelijk
- de dashboardkopie in `custom_components` is in sync met de bron
- hetzelfde voor de achtergrondtekening
- elke dienst uit `services.yaml` is ook echt geregistreerd
- geen `print` of `breakpoint` in de uitgerolde code

Die eerste twee vonden meteen iets. De rest is borging tegen de fouten
die vandaag voorkwamen: een dashboardkopie die achterliep, een
cachesleutel die niet meebewoog.

### Getest

Nieuw `tests/test_release_readiness.py`, 7 tests.

**Volledige testsuite**: 1221 tests, allemaal groen.

## De integratie controleert zichzelf op onmogelijke waarden (v1.9.5)

**Gevraagd**: *"Heb je de diagnostiek nu zo goed nagekeken dat daar niets
meer uit te herleiden valt?"*

Eerlijke antwoord: **nee.** De export heeft ~200 coordinator-velden en ik
had er handmatig zo'n veertig echt bekeken.

### Waarom dat niet goed genoeg is

Het accu-rendement van 8290% viel pas op toen ik de **hele**
betrouwbaarheidslijst uitprintte in plaats van alleen de statussen. Had
ik dat niet gedaan, dan had het er nog gestaan. Datzelfde geldt voor de
zelfconsumptie van −244,6% — die kwam alleen boven water omdat jij hem
meldde.

Dat is geen werkwijze. Zo'n fout hoort niet af te hangen van of iemand
toevallig goed kijkt.

### Wat er nu automatisch gebeurt

Elke tick worden alle numerieke velden getoetst aan wat er **fysiek
mogelijk** is: een rendement tussen 0 en 100%, een aandeel tussen 0 en
100, een laadtoestand die niet boven de 100% kan. Overschrijding is geen
ongebruikelijke waarde maar een **rekenfout**, en dat wordt als
aandachtspunt gemeld.

Getoetst tegen beide fouten van vandaag: allebei zouden ze automatisch
gevonden zijn.

Eén detail dat uitmaakt: de **specifiekste regel wint**. `_ratio_percent`
gaat voor `_percent`, anders zou een aandeel de ruime percentagegrenzen
krijgen en glipte −244% er alsnog doorheen.

De grenzen zijn bewust ruim. Het doel is fouten vangen, niet commentaar
leveren op een uitzonderlijke dag — een negatieve spreiding tussen
inkoop en teruglevering kan echt voorkomen en geeft dus geen alarm.

### Wat dit niet is

Dit vangt **onmogelijke** waarden, geen verkeerde. Een rendement van 45%
is plausibel maar zou nog steeds fout kunnen zijn. Voor dat soort fouten
blijft de dagelijkse export nodig, en blijft jouw waarneming van wat je
buiten ziet of op je omvormer leest onmisbaar — dat leverde vandaag drie
van de vijf vondsten op.

### Getest

Nieuw `tests/test_plausibility_scan.py`, 10 tests: beide fouten van
vandaag worden gevangen, de specifiekste regel wint, een SoC boven 100
is onmogelijk, een verse coordinator is schoon, een realistische set
geeft geen alarm, een negatieve spreiding mag, tekst en booleans worden
overgeslagen, het wordt een aandachtspunt, en elke regel heeft een
zinnig bereik.

**Volledige testsuite**: 1214 tests, allemaal groen.

## Volledige diagnostiek-controle (v1.9.4)

**Gevraagd**: het hele bestand nakijken vóór het installeren.

### Twee echte vondsten

**Accu-rendement stond op 8290%.** In dezelfde export meldde
`learning_health` 82,9. In v1.3.0 had ik daar een vermenigvuldiging met
100 gezet, op basis van een testwaarde van 0,85 — maar
`learned_battery_efficiency_percent` geeft wel degelijk een percentage.

Het venijnige: de test die dat vastlegde gebruikte **dezelfde verkeerde
aanname**, dus hij bevestigde de fout in plaats van hem te vangen. Er
staat nu ook een test op dat het rendement nooit boven de 100% uitkomt,
want dat is fysiek onmogelijk.

**Gaskosten met zeven decimalen** (0,0466657 €) in het kostenoverzicht.
Afgerond op centen, met behoud van `None` als er geen gas is — nul zou
suggereren dat er niets verbruikt is.

### Eén vals alarm van mijn kant

De accumodules leken leeg: celspanning en SoC op `None`. Dat bleek mijn
leescommando, dat naar `celdelta_v` en `soc_procent` keek terwijl de
velden `cel_delta_v` en `soc_percent` heten. Alle drie de modules leveren
gewoon: celdelta 0,05 / 0,01 / 0,00 V, temperatuur 19-20 °C, SoC 17-20%.

### Wat er goed staat

Alle vijf de leercheks op OK. Geen fouten. 38 bevestigde NILM-apparaten,
13 klimaatcellen, de Zonneplan-vergelijking op 2 cent verschil, en het
nieuwe beslislogboek en dagrapport draaien.

De zonvoorspelling-zelfcontrole meldt "de correctie werkt" met 2,3
procentpunt drift — precies waarvoor die gebouwd is.

### En de Kalman-vraag is nu beantwoord

Van gisteren: *"levert filteren hier eigenlijk iets op?"* Na 500 metingen
per signaal:

| Signaal | Verschil | Oordeel |
|---|---|---|
| SoC | 0,82% | verwaarloosbaar |
| PV | 9,4% | noemenswaardig |
| Huisverbruik | 25,4% | noemenswaardig |

Voor de **accu-inhoud** — het enige signaal dat de beslislogica raakt —
valt er niets te winnen. Dat was precies de vraag, en het antwoord is
nee. De andere twee zijn puur informatief.

### Getest

Nieuw `tests/test_review_1_9_4.py`, 4 tests: het rendement wordt niet
dubbel omgerekend, blijft binnen een plausibel bereik, het gasbedrag
wordt afgerond, en ontbrekend gas blijft `None`.

**Volledige testsuite**: 1204 tests, allemaal groen.

## Meldingsruis rond drempels (v1.9.3)

**Gevraagd**: *"De melding omtrent de prijs rond middernacht
nagekeken?"*

Gevonden in de meldingsgeschiedenis, en er zat meteen een tweede geval
naast.

### De middernachtmelding

```
00:02  💶 Kostenberekening wijkt af van Zonneplan
       eigen berekening -0,00 € is 1,53 € hoger dan de -1,53 € bij Zonneplan
00:04  ✅ Kostenberekening klopt weer
```

Geen rekenfout. Onze dagteller springt om 00:00 naar nul, die van
Zonneplan een paar minuten later. Zolang de twee niet gelijk staan is
elke vergelijking betekenisloos — en een melding die zichzelf binnen twee
minuten intrekt, leert je meldingen te negeren.

De vergelijking slaat het eerste half uur na middernacht nu over, met die
reden erbij. Ruim genomen, want de kostensensor werkt maar ongeveer per
uur bij.

### En hetzelfde patroon bij de nachtreserve

Diezelfde nacht ging **"Accu haalt de nacht niet" zeven keer af**,
telkens gevolgd door "haalt de nacht weer":

| Beschikbaar | Nodig | Tekort |
|---|---|---|
| 4,58 | 4,61 | 0,03 kWh (0,7%) |
| 4,49 | 4,50 | **0,01 kWh (0,2%)** |
| 4,41 | 4,50 | 0,09 kWh (2,0%) |
| 3,63 | 3,66 | 0,03 kWh (0,8%) |

Vijf van de zes binnen 1% van de drempel. Een tekort van 0,01 kWh melden
is geen waarschuwing maar geruis rond een grens — de schatting van de
overbruggingsbehoefte is zelf onnauwkeuriger dan dat. En de accu laadt
sowieso bij als het nodig is, dus de melding is informatief en niet
urgent.

Er moet nu een echt gat zijn: minstens 0,5 kWh, of 10% van de behoefte.
Die tweede voorwaarde schaalt mee — een half kWh is veel bij een behoefte
van 2 kWh en weinig bij 20.

### Getest

Nieuw `tests/test_notification_noise.py`, 6 tests: geen vergelijking vlak
na middernacht, wél weer daarna, een haarscheurtje van 0,01 kWh wordt
niet gemeld, een echt tekort nog steeds wel, de drempel schaalt mee met
de behoefte, en de absolute ondergrens geldt ook bij een kleine behoefte.

**Volledige testsuite**: 1200 tests, allemaal groen.

## Vier gemelde punten (v1.9.2)

### 1. Zelfconsumptie op −244,6%

Een aandeel ligt per definitie tussen 0 en 100%.

`pv_export_today_kwh` telt **alles** wat de P1-meter het net op ziet
gaan. Bij een thuisaccu die 's ochtends verkoopt komt dat deels uit de
**accu** — energie die gisteren is geladen. De formule nam aan dat alle
export zon was, en zodra de export de dagopwek overstijgt wordt de
uitkomst negatief.

De zon die het net op gaat kan nooit meer zijn dan wat er die dag is
opgewekt; het meerdere komt uit de accu. De export wordt daarop begrensd.
Dat is geen truc om de uitkomst mooi te maken, maar de enige
verdedigbare aanname zonder aparte meting per bron.

### 2. "Avondpiek" om 07:15

De melding kwam om 05:47 met de tekst *"Lage accustand vlak voor de
avondpiek"*, terwijl het duurste blok om 07:15 begon. De inhoud klopte,
het label niet.

Ik had "avond" hardgecodeerd omdat het duurste blok daar meestal ligt.
Het dagdeel volgt nu uit het werkelijke tijdstip: nacht, ochtend, middag
of avond.

### 3. Waterontharder: 3,1 liter is geen regeneratie

Een moment van 3,1 liter om 00:28 werd als regeneratie aangemerkt, puur
omdat het binnen het nachtvenster viel. Maar 's nachts wordt er ook
doorgespoeld of een glas water getapt.

Het tijdvenster alleen is geen bewijs — het **volume** is de
onderscheidende eigenschap. Er geldt nu een ondergrens van tien liter, de
waarde die je uit ervaring noemde.

### 4. Weerbronnen: de meting spreekt de indruk tegen

Over 180 waarnemingen per bron:

| Bron | Klopt met wat de panelen deden |
|---|---|
| `weather.forecast_thuis` | **82,8%** |
| `weather.openweathermap` | 79,4% |

Drie procentpunt verschil, in het voordeel van de bron die er volgens de
losse momenten "altijd naast zat". Precies waarom ik wilde meten in
plaats van de indruk overnemen: die vier waarnemingen van gisteren waren
allemaal tijdens bewolking, en dat is niet representatief.

Dat resultaat was alleen niet te zien, want er verscheen alleen een
melding bíj een groot verschil. Stilte was daardoor dubbelzinnig: geen
verschil, of nog niet genoeg gemeten? Nu wordt ook gemeld dát ze
vergelijkbaar presteren, mét de percentages.

### Getest

Nieuw `tests/test_reported_issues_1_9_2.py`, 10 tests: zelfconsumptie
nooit negatief, het gewone geval ongewijzigd, geen opwek geeft geen
ratio, volledige zelfconsumptie, het dagdeel wordt afgeleid in alle vier
de kwadranten, de melding gebruikt het echte dagdeel, een klein
nachtelijk moment is geen regeneratie, de drempel past bij een echte
regeneratie, vergelijkbare bronnen worden ook gemeld, en een echt
verschil geeft nog steeds advies.

**Volledige testsuite**: 1194 tests, allemaal groen.

## PV-dagopwek was structureel te laag (v1.9.1)

**Gemeld**: *"Dagrapport geeft aan opwek 12.9 kWh terwijl mijn PV
installatie zegt 13.5 kWh."*

0,6 kWh op 13,5 is **4,4%** — te veel om ruis te zijn.

### Waarom integreren onderschat

De dagopwek werd berekend als vermogen × tijd, elke tick. Dat neemt aan
dat het vermogen die vijf minuten **constant** was.

Uit het meetfrequentie-rapport van v1.1.9 bleek al dat de
SolarEdge-sensor maar eens per 15 à 20 minuten bijwerkt. We bevriezen dus
een verouderde waarde over drie ticks, en elke piek daartussen — een wolk
die wegtrekt — valt weg. De omvormer meet continu en telt die wél mee.

Dat is geen meetfout maar een methodefout, en hij is per definitie
eenzijdig: hij mist alleen naar boven.

### De meterstand telt gewoon door

`sensor.solaredge_i1_ac_energy` staat op 22.633 kWh — een cumulatieve
teller die tussen onze metingen door blijft optellen. Het **dagverschil**
daarvan is exact, ongeacht hoe traag wij lezen.

Die wordt nu gebruikt als hij is ingesteld. Integreren blijft de terugval
voor wie zo'n meter niet heeft, en het betrouwbaarheidsoverzicht zegt
welke van de twee actief is — met bij integreren de uitleg dat het
structureel onderschat en hoe je dat oplost.

### Twee dingen die makkelijk misgaan

**Een teller kan terugvallen** bij een herstart van de omvormer. Dan is
het verschil betekenisloos. Er wordt opnieuw geijkt, en wat er die dag al
stond blijft behouden in plaats van weggegooid.

**De meterstand loopt door over middernacht.** Zonder nieuw ijkpunt zou
de opwek van gisteren gewoon doortellen. Dat is aan de bestaande
dagreset gekoppeld.

### Onderweg

Mijn eerste invoeging van de overzichtsregel belandde in de
*meldingen*-functie in plaats van in het overzicht — twee tests vielen
daarop om.

### Getest

Nieuw `tests/test_pv_production_from_meter.py`, 7 tests: het dagtotaal
komt uit de meter, een teller-reset geeft geen negatieve opwek, wat er al
stond blijft behouden, de dagwissel ijkt opnieuw, zonder meter wordt er
nog steeds geïntegreerd, de bron wordt gerapporteerd, en integreren wordt
als minder betrouwbaar gemarkeerd.

**Volledige testsuite**: 1184 tests, allemaal groen.

## Diagnostiek werd een dagrapport (v1.9.0)

**Gevraagd**: *"Ik wil nu elke dag met je het diagnostiek file delen, is
deze voldoende gevuld zodat je elke dag kunt verbeteren? Of kan het
diagnostiek gedeelte nog uitgebreider?"*

### Wat er al goed was

198 coordinator-velden, alle betrouwbaarheidsoordelen, 25 regels in het
overzicht, en per onderwerp een bewaarde reeks: klimaatbias (57),
energiebalans (20), watersessies (20), moduswijzigingen (30), NILM (38
apparaten). Daar viel goed op te sturen — de meeste vondsten van vandaag
kwamen rechtstreeks uit die exports.

### Wat ontbrak: een momentopname is geen dag

De export toonde de **huidige** stand. Wat er om 03:00 gebeurde was
onzichtbaar tenzij het toevallig in een bewaarde reeks stond. Concreet
gemist bij de analyses van vandaag:

- op welke **tijdstippen** de sensoruitvallen zaten — alleen het aantal
  was bekend
- hoe de **SoC over de dag** verliep, en of de reserve knelde
- of een **beslissing uitpakte** zoals verwacht

### Twee nieuwe lagen

**Beslislogboek per tick** — 600 regels, ongeveer twee dagen. Per regel:
tijdstip, modus, reden, SoC, beschikbare kWh, prijs, PV-vermogen,
huisverbruik, accuvermogen en de overbruggingsbehoefte. Compacte
sleutels en afgeronde waarden, want een leesbare export is meer waard dan
een volledige die niemand doorkomt.

**Dagsamenvatting** — 30 dagen. Per dag: aantal ticks, laagste en hoogste
SoC, welke beslissingen hoe vaak (grootste eerst, want dat tekent het
karakter van de dag), fouten, sensoruitval per sensor, kosten, opwek,
verbruik en netimport.

Die eerste laat zien wát er binnen een dag gebeurde, de tweede of iets
**structureel** is.

### Omvang

Het logboek kost ongeveer 110 kB, de dagrapporten 9 kB. Jouw export gaat
daarmee van ~280 kB naar ongeveer 400 kB. Gezien de uitdrukkelijke
toestemming ruim bemeten.

Het beslislogboek gaat bewust **niet** mee in de opslag: een momentopname
van twee dagen heeft na een herstart weinig waarde, en het zou de opslag
met honderden regels per herstart belasten. De dagrapporten wél — dertig
dagen patronen zijn waardeloos als ze bij elke herstart verdwijnen.

### Onderweg

Twee veldnamen had ik verzonnen (`last_operation_mode`,
`last_price_per_kwh` in plaats van `last_expected_mode` en
`last_current_price_per_kwh`); 51 tests vielen daarop om. En de
borgingstest uit v1.0.4 ving meteen dat `daily_report_history` niet
persistent was — precies waarvoor die bestaat.

### Getest

Nieuw `tests/test_daily_diagnostics.py`, 14 tests: elke tick wordt
gelogd, het logboek is begrensd en houdt de nieuwste, ontbrekende waarden
laten het niet crashen, een dag wordt bij de wissel samengevat, de
beslissingen worden geteld met de grootste vooraan, het SoC-bereik wordt
bijgehouden, fouten geteld, sensoruitval per sensor opgenomen, de
geschiedenis begrensd, de dagrapporten overleven een herstart, het
logboek bewust niet, en beide staan in de export.

**Volledige testsuite**: 1177 tests, allemaal groen.

## Aandachtspunt noemt nu wélke sensor wegviel (v1.8.2)

**Gerapporteerd**: *"Sensor-gezondheid: verminderd (55.0%)... doordat een
sensor 9 van de 20 keer geen waarde gaf. Maar kan niet ingrijpen, dit
omdat ik niet weet om welke sensor het gaat."*

Precies dezelfde omissie als bij de herstelmelding twee versies terug: de
melding zegt dát er iets is, maar niet waar je moet zijn.

### Wat er ontbrak

Bij een ontbrekende meting werd alleen een `None` in de foutreeks
gezet — de naam van de sensor ging verloren. Het aandachtspunt kon dus
wel het aantal noemen, maar niet de bron.

Er wordt nu per sensor geteld hoe vaak die geen waarde gaf. De melding
luidt bij jouw situatie:

> Sensor-gezondheid: verminderd (55,0%). Niet door onnauwkeurige metingen
> — alle 11 vergelijkingen vielen binnen de marge — maar doordat een
> sensor 9 van de 20 keer geen waarde gaf:
> `sensor.zendure_manager_available_kwh` (9x).

Bij meerdere sensoren staat de grootste veroorzaker vooraan, want daar
zit de meeste winst.

### Twee kleinere dingen die opvielen

De telling gaat mee in de opslag. De foutreeks zelf wordt al bewaard, dus
zonder de namen erbij zou de melding na een herstart weer generiek
worden — terwijl het cijfer bleef staan.

En bij een lege geschiedenis ontbrak de sleutel `uitval_per_sensor`
helemaal, waar hij verder altijd bestaat. Een aanroeper mag niet hoeven
raden of een veld er is; dat is nu consistent.

### Getest

Vijf tests erbij: de ontbrekende sensor wordt bij naam genoemd, meerdere
sensoren worden allemaal genoemd, de grootste veroorzaker staat vooraan,
zonder uitval blijft de lijst leeg, en de telling overleeft een herstart.

**Volledige testsuite**: 1163 tests, allemaal groen.

## Controle: draait alles nog na alle wijzigingen? (v1.8.1)

**Gevraagd**: *"kun je kijken of alles op alle tabbladen nog actief wordt
bijgestuurd na alle aanpassingen welke we hebben gedaan."*

Terechte controle na veertien versies op één dag.

### Wat er is nagelopen

**Veertien tabbladen, 132 kaarten.** Elke `state_attr`-aanroep uit het
dashboard — 104 stuks — is vergeleken met wat de sensoren werkelijk
teruggeven. Daarna elke sensor geïnstantieerd en zijn attributen
opgevraagd, en een volledige tick gedraaid om te zien of de waarden ook
echt bewegen.

Resultaat: meetfrequentie vult zich (4 sensoren), Kalman-divergentie
(3 signalen), Zonneplan-totaal rekent, dagkosten-ijkpunt staat, en het
betrouwbaarheidsoverzicht levert 13 regels. Alle twaalf nieuwe
mechanismen worden daadwerkelijk aangeroepen.

### Twee vals alarm

Negen sensoren gaven een fout bij het opvragen van attributen — die
hébben er simpelweg geen. En `PvForecastAccuracySensor` leek stuk, maar
die krijgt een *tracker* mee in plaats van de coordinator; mijn
controlescript gaf het verkeerde argument.

### Eén echte vondst

Het **PV-installatieprofiel** vult zich niet zonder zonvoorspelling. Dat
is correct gedrag — zonder verwachting valt niet te bepalen of een dag
helder genoeg was — maar de melding zei dat niet. Er stond alleen
"0/5 heldere dagen verzameld", en wie geen Solcast heeft zou eeuwig
wachten op een profiel dat nooit komt.

Dat staat er nu expliciet: *"Geen zonvoorspelling geconfigureerd. Zonder
die verwachting valt niet te bepalen of een dag helder genoeg was."*

### Getest

Eén test erbij, plus vijf bestaande tests die de zonvoorspelling nu
meestubben — die gingen over het gedrag ná die drempel en liepen er
anders op stuk.

**Volledige testsuite**: 1158 tests, allemaal groen.

## Week-, maand- en jaarcijfers plus trends (v1.8.0)

**Gevraagd**: *"Graag ook voor gas, week, maand en jaar cijfers. Voor
zowel gas als electra wil ik ook een soort dagelijkse/wekelijkse trend
zien. Iets als meer verbruikt dan gister, minder verbruikt dan vorige
week. Dit wil ik dan in % zien."*

### Gas: zelf opgebouwd

Zonneplan levert voor gas alleen een **dagtotaal** — geen maand of jaar,
anders dan bij stroom. Die dagtotalen worden nu bij elke dagwissel
vastgelegd, en daaruit volgen de week-, maand- en jaarcijfers.

Één detail dat makkelijk misgaat: de teller springt om middernacht terug
naar nul, dus de waarde moet vlak vóór de wissel worden vastgelegd. Ná de
wissel is de vorige dag niet meer op te vragen. Daar staat een test op.

### Het ontwerppunt dat er echt toe doet

Trends rusten uitsluitend op **voltooide dagen**.

"Vandaag tot nu toe" vergelijken met een volledige gisteren geeft de hele
dag een negatieve trend die om middernacht vanzelf verdwijnt:

| Tijdstip | Verbruikt van je dagtotaal | Naïeve trend |
|---|---|---|
| 10:00 | 35% | −65% |
| 18:00 | 75% | −25% |
| 23:00 | 98% | −2% |

Altijd negatief, altijd betekenisloos. En je zou er conclusies aan
verbinden. Daarom: **gisteren tegen eergisteren**, en **de laatste zeven
dagen tegen de zeven daarvoor**. Vandaag staat er wel bij, maar zonder
trend — met de reden erbij op het tabblad.

### Kleine bedragen krijgen geen percentage

Van 2 naar 4 cent is "+100%", en dat is ruis. Onder de twintig cent
verschijnt er geen trend.

### Op het tabblad

Een tabel met stroom en gas naast elkaar voor 7, 30 en 365 dagen, en
daaronder de twee trends met 📈 voor duurder en 📉 voor goedkoper.

Zonder gas bij dezelfde leverancier blijft die kolom leeg in plaats van
nul te tonen — nul suggereert dat er niets verbruikt is.

### Getest

Nieuw `tests/test_energy_cost_trends.py`, 14 tests: week/maand/jaar voor
beide, gastotalen uit dagwaarden, ontbrekend gas geeft geen nul, de
dagtrend vergelijkt twee volledige dagen, een goedkopere dag geeft een
negatief percentage, de weektrend vergelijkt twee volle weken, geen
weektrend vóór veertien dagen, een klein bedrag geeft geen percentage,
gas en stroom worden apart getrend, vandaag heeft geen trend, de
toelichting legt uit waarom, een dag wordt bij de wissel afgesloten, de
waarde van vóór middernacht blijft behouden, en de geschiedenis overleeft
een herstart.

**Volledige testsuite**: 1157 tests, allemaal groen.

## Gas meegenomen in het financiële overzicht (v1.7.0)

**Gevraagd**: *"Zonneplan levert ook gas aan mij, dit graag meenemen in
het financiele gedeelte."*

Zonder die post waren de energiekosten maar half zichtbaar.

### Wat het oplevert

Met de werkelijke cijfers uit de export:

| Post | Bedrag |
|---|---|
| Stroom afname | 0,04 € |
| Stroom teruglevering | −0,19 € |
| **Stroom netto** | **−0,16 €** |
| Gas | 0,13 € |
| **Totale energiekosten vandaag** | **−0,03 €** |

Op stroom verdiende je 16 cent, op gas ging 13 cent uit. Netto sta je op
drie cent in de plus — een heel ander beeld dan de −0,16 € die je zonder
de gaspost zag.

De gasentiteit wordt automatisch gevonden, net als de rest: geen
configuratie.

### Twee dingen die eerlijk moeten blijven

**Gas wordt alleen getóónd, niet getoetst.** Deze integratie berekent
niets aan gas, dus er valt niets naast te leggen zoals bij stroom. Het
staat er om je totale energiekosten zichtbaar te maken. Een test legt
vast dat gas het oordeel over de stroomberekening niet beïnvloedt — ook
niet als het bedrag groot is.

**Voor gas bestaat alleen een dagtotaal.** Geen maand- of jaarvariant
zoals bij stroom. Dat is een beperking van de Zonneplan-integratie zelf,
en het staat op het tabblad in plaats van dat de post er stilzwijgend
ontbreekt bij een maandoverzicht.

Heb je geen gas bij dezelfde leverancier, dan verdwijnen die regels
gewoon — een regel met "None €" is erger dan geen regel.

### Getest

Zes tests erbij: gas wordt automatisch gevonden, het totaal telt gas bij
netto stroom op, gas beïnvloedt het stroomoordeel niet (ook niet bij een
groot bedrag), zonder gas is het totaal gewoon de stroom, het dashboard
verbergt de regels als er geen gas is, en het benoemt dat gas niet
getoetst wordt en alleen als dagtotaal bestaat.

**Volledige testsuite**: 1143 tests, allemaal groen.

## Watertabellen groeiden ongelimiteerd (v1.6.7)

**Gevraagd**: *"Voorkomen dat de tabellen te groot worden, recente
gebruiksmomenten alleen vandaag tonen, daggeschiedenis alleen laatste 7
dagen."*

Op de screenshot stonden twintig gebruiksmomenten over twee dagen, en een
kale opsomming van dagtotalen zonder datum.

### Gebruiksmomenten: alleen vandaag

De tabel toont nu uitsluitend de momenten van vandaag, met alleen de tijd
in plaats van dag én tijd — die dag is nu immers bekend. Erboven staat
hoeveel het er zijn.

Is er vandaag nog niets gemeten, dan staat dat er expliciet, mét hoeveel
eerdere momenten er bewaard zijn. Een lege tabel zonder uitleg zou lijken
alsof de detectie stuk is.

### Daggeschiedenis: zeven dagen, mét datum

Van een kale lijst getallen naar een tabel met de dag erbij. `441 L` zegt
weinig als je niet weet wanneer dat was — en juist die uitschieter viel
eerder op.

### Drie pogingen voor het filteren

Home Assistant kent Jinja-uitbreidingen die kale Jinja niet heeft. Zowel
`selectattr('gestart', 'search', ...)` als de `match`-variant liepen stuk
in de bestaande opmaaktest, die de sjablonen echt rendert. Uiteindelijk
een gewone lus met een namespace — werkt in beide omgevingen.

Onderweg bleek de testhulp `now()` niet te kennen, waardoor élk sjabloon
dat die functie gebruikt stilzwijgend niet werd gecontroleerd. Dat is nu
gestubd, dus die kaarten worden voortaan wél getoetst.

En de bestaande opmaaktest deed precies zijn werk: hij las de kopie in
`custom_components`, die ik nog niet had bijgewerkt. Dat is exact waarom
die kopie er is.

### Getest

Nieuw `tests/test_water_tab_filtering.py`, 8 tests: alleen de momenten
van vandaag, een expliciete melding als er vandaag niets was, onderscheid
met een lege geschiedenis, een sessie zonder starttijd laat de kaart niet
crashen, zeven dagen getoond van twintig bewaard, de daggeschiedenis
heeft datums, een lege geschiedenis zegt dat, en een borging tegen
Jinja-uitbreidingen die alleen in Home Assistant bestaan.

**Volledige testsuite**: 1137 tests, allemaal groen.

## Herstelmelding noemt de sensor, en wacht na een herstart (v1.6.6)

**Gerapporteerd**: *"Ik doelde vooral op dat '✅ Sensor is weer
uitleesbaar' niet aangeeft welke sensor weer uitleesbaar is. Nu wist ik
het omdat het er maar 1 is."* En: *"Het uitvallen komt door een herstart
(start relatief traag op), misschien deze melding iets vertragen?"*

### De herstelmelding was generiek

De probleemmelding noemde de entity_id netjes —
`sensor.zendure_manager_available_kwh geeft op dit moment geen waarde` —
maar het herstel zei alleen *"Alle geconfigureerde sensoren geven weer
een waarde"*. Waar dat over ging moest je zelf onthouden.

Welke sensoren wegvielen wordt nu bijgehouden, zodat de herstelmelding
dezelfde namen noemt. Daarna wordt die lijst gewist — anders zou een
volgende herstelmelding de sensoren van de vórige storing opsommen.

### Aanlooptijd van drie minuten

Sensoren zijn na een herstart even weg omdat hun integratie nog aan het
opstarten is. Dat is normaal, geen storing. Een melding sturen over iets
dat vanzelf goed komt, leert je die meldingen te negeren — en dan mis je
de keer dat het wél echt misgaat.

Alleen **beschikbaarheidsmeldingen** wachten: sensor weg en integratie
vastgelopen. Een prijspiek of een apparaat dat klaar is heeft niets met
opstarten te maken, en zou onnodig vertraagd worden.

Drie minuten, en daarna komt de melding gewoon — de aanlooptijd mag een
echte storing niet verbergen. Er staat een test op beide kanten. Wordt
een melding uitgesteld, dan is dat op het tabblad te zien met de reden en
de resterende tijd.

### Wat de meldingen ondertussen lieten zien

De drie uitvallen tussen 09:50 en 10:22 betroffen **de hele
Zendure-koppeling**, niet één sensor: zowel `available_kwh` als
`batterij_vermogen` haperden. Passend bij herstarts, en met deze
aanlooptijd verdwijnen ze uit je meldingen.

### Getest

Vijf tests erbij: de herstelmelding noemt de sensor, de namen worden
daarna gewist, vlak na een herstart komt er geen melding, ná de
aanlooptijd wél, andere meldingen worden niet vertraagd, en de reden
legt het uitstel uit.

**Volledige testsuite**: 1128 tests, allemaal groen.

## Gezondheidsscore verborg de echte oorzaak (v1.6.5)

**Gevraagd**: een algehele controle van een verse export (v1.6.4).

### Wat er goed staat

De **Zonneplan-vergelijking werkt**, en meteen goed: alle zes
kostensensoren automatisch gevonden, en de uitkomst is **−0,19 € eigen
berekening tegen −0,16 € bij Zonneplan**. Drie cent verschil op een dag
waarop je netto verdiende. Dat is een sterke bevestiging dat de
prijsafhandeling klopt.

De **weerbronmeting** loopt: 12 van de 20 waarnemingen per bron. Nog een
paar uur zonlicht en er staat een oordeel.

### De vondst: 65% zei het verkeerde

Het aandachtspunt meldde *"Sensor-gezondheid: verminderd (65,0%, 20
metingen)"*. Dat leest als "je metingen zijn onnauwkeurig".

Maar de foutreeks vertelt iets anders:

| | |
|---|---|
| Werkelijke vergelijkingen | 13 |
| Waarvan boven de drempel | **0** |
| Foutmarge | 47 tot 141 W (drempel 300) |
| Sensor gaf geen waarde | **7 keer** |

Alle dertien vergelijkingen zijn uitstekend. De hele daling naar 65% komt
door zeven momenten waarop de sensor wegviel — precies de storing waarvan
je vanochtend de melding kreeg.

Dat zijn twee volstrekt verschillende problemen met heel verschillende
oplossingen, en ze werden tot één cijfer samengeknepen. Je zou gaan
zoeken naar een meetfout die er niet is.

### De score is nu uitgesplitst

**Nauwkeurigheid** (hoeveel vergelijkingen binnen de marge vielen) en
**beschikbaarheid** (hoe vaak er überhaupt iets te vergelijken viel)
worden apart berekend, en de melding noemt de grootste veroorzaker.

Tegen jouw echte reeks levert dat op:

> Sensor-gezondheid: verminderd (65,0%). Niet door onnauwkeurige metingen
> — alle 13 vergelijkingen vielen binnen de marge — maar doordat een
> sensor 7 van de 20 keer geen waarde gaf.

De gecombineerde score blijft bestaan, want die zegt wél hoe bruikbaar de
check als geheel is. Alleen de dúiding is nu correct.

### Nog open aandachtspunt

Twee apparaten met drift: **IPTV Vermogen** en **Koelkast schuur
Vermogen**. Klopt dat hogere verbruik, gebruik dan
`accept_nilm_device_drift` — dat ijkt het als nieuw normaal zonder de
leergeschiedenis weg te gooien.

### Getest

Nieuw `tests/test_sensor_health_breakdown.py`, 9 tests, waaronder de
echte reeks uit de export: die wordt aan uitval toegeschreven en de
melding zegt dat ook. Verder: echte onnauwkeurigheid wordt wél als
zodanig benoemd (de correctie mag het echte probleem niet verbergen), bij
beide problemen tegelijk wordt de grootste genoemd, een perfecte
geschiedenis heeft geen oorzaak, alleen uitval geeft geen
nauwkeurigheidsoordeel, een lege geschiedenis zegt niets, en de
uitsplitsing staat in het overzicht en de export.

**Volledige testsuite**: 1123 tests, allemaal groen.

## Dashboard wees de verkeerde kant op (v1.6.4)

**Gerapporteerd**: het Financieel-tabblad toonde *"Geen
Zonneplan-kostensensoren gevonden"*.

Dat klopte niet. In de diagnostiek-export staan ze gewoon, mét waarden:
`electricity_delivery_costs_today` op €0,033,
`electricity_production_costs_today` op €0,163, plus de maand- en
jaarvarianten.

### De echte oorzaak lag ergens anders

Het dashboard las
`sensor.woonkamer_energy_management_system_tegenfeitelijke_besparing` —
een entiteit die niet bestaat. Die sensor heet **"Besparing t.o.v. zonder
accu-sturing"** en heeft dus een heel andere entity_id.

`state_attr` op een niet-bestaande entiteit geeft stilzwijgend `None`, en
mijn sjabloon toonde daarop zijn terugvaltekst. Het resultaat was een
melding over Zonneplan terwijl het probleem bij mijn eigen entiteitnaam
lag — het vervelendste soort fout, want het dashboard wijst je de
verkeerde kant op.

Ik had die naam bij het bouwen geraden in plaats van opgezocht.

### Nu bewaakt

Een test controleert dat élke
`sensor.woonkamer_energy_management_system_X` in het dashboard
correspondeert met een sensor die daadwerkelijk zo heet, door de
`_attr_name`-waarden te slugificeren zoals Home Assistant dat doet.

Die test vond meteen twee andere verwijzingen: `advies_gereedheid_8_modules`
en `piekvermogen`. Die blijken **correct** — Home Assistant kent de
entity_id toe bij de eerste aanmaak en laat die daarna ongemoeid, ook als
de weergavenaam verandert. De eerste heette ooit "(8 modules)", de tweede
alleen "Piekvermogen".

Ze staan daarom op een expliciete uitzonderingenlijst mét die reden. Wie
daar iets aan toevoegt, moet kunnen aantonen dat het om zo'n historische
naam gaat en niet om een typefout.

### Getest

Nieuw `tests/test_dashboard_entity_references.py`, 3 tests: elke verwezen
sensornaam bestaat, de besparingssensor wordt correct aangeroepen, en het
Zonneplan-blok leest de juiste entiteit.

**Volledige testsuite**: 1114 tests, allemaal groen.

## Meldingsgeschiedenis werd onbruikbaar zonder het bericht (v1.6.3)

**Gerapporteerd**: *"Hoelang blijft dit melding venster bestaan, en kan
het iets duidelijker? Nu was er een sensor niet uitleesbaar maar kan in
de gecreeerde tabel niet zien om welke het ging."*

```
7 Aug 10:10   ✅ Sensor is weer uitleesbaar
7 Aug 09:50   ⚠️ Sensor niet uitleesbaar
```

Precies het probleem: de **titel** zegt dát er een sensor wegviel, het
**bericht** zegt welke. En alleen de titel werd bewaard — waardoor de
geschiedenis onbruikbaar was voor precies het geval waarvoor je hem
opzoekt.

### Drie aanpassingen

**Het bericht wordt nu meebewaard** en getoond, dus je ziet
`sensor.zendure_manager_available_kwh geeft op dit moment geen waarde`
in plaats van alleen "Sensor niet uitleesbaar".

**Langer bewaard**: van 50 naar 200 meldingen. Met tweeëntwintig soorten
en herstelmeldingen erbij was vijftig krap — een drukke dag vulde de lijst
en duwde de melding waar je naar zocht er alweer uit. De tabel toont er
dertig in plaats van vijftien.

**De vraag "hoelang blijft dit staan" wordt beantwoord**, want dat stond
nergens. Meldingen verdwijnen **niet na een bepaalde tijd** — alleen als
er tweehonderd nieuwere bijkomen. Dat staat nu boven de tabel, samen met
hoeveel er op dat moment in staan.

Meldingen van vóór deze versie hebben geen bewaard bericht; die tonen dat
eerlijk in plaats van een lege regel.

### Getest

Vier tests erbij: de geschiedenis bewaart het bericht (met de entity_id
erin), de herstelmelding ook, de lengte is toereikend voor een drukke dag
(minstens vijf per soort), en het dashboard toont zowel het bericht als
de uitleg over de bewaartermijn.

**Volledige testsuite**: 1111 tests, allemaal groen.

## Herstelmeldingen (v1.6.2)

**Gerapporteerd**: *"Er is nu een melding verstuurd dat een sensor niet
uitleesbaar is, maar er komt geen melding wanneer de sensor weer
uitleesbaar is."*

Terecht, en het geldt breder dan die ene.

### Waarom dit ertoe doet

Zonder herstelmelding blijf je in het ongewisse: is het opgelost, of is
de melding gewoon **gedempt**? Bij een dempingsvenster van twee uur is
dat niet uit elkaar te houden. En dat is precies het soort onzekerheid
waardoor mensen meldingen gaan negeren — wat de hele functie waardeloos
maakt.

### Zeven soorten krijgen een herstelmelding

Sensor weer uitleesbaar, integratie draait weer, kostenberekening klopt
weer, zonopbrengst weer op niveau, PV-oriëntatie komt weer overeen,
accumodules lopen weer gelijk, accu haalt de nacht weer.

Meldingen die een **gebeurtenis** beschrijven horen er bewust niet bij —
apparaat klaar, goedkoop blok begint, dagoverzicht. Daar valt niets aan
te herstellen. Een test legt dat onderscheid vast.

### Drie keuzes die het bruikbaar maken

**Dezelfde schakelaar.** Wie "sensor valt weg" uitzet, krijgt ook het
herstel niet. Dat is wat je verwacht als je een melding uitschakelt.

**Het dempingsvenster wordt omzeild.** Een probleem dat vijf minuten na
de melding is opgelost zou anders stilzwijgend verdwijnen — en juist dan
wil je het horen.

**Na een herstel wordt de demping van de probleemmelding gewist.** Komt
hetzelfde probleem terug, dan meldt hij meteen weer in plaats van pas na
twee uur.

### Wat er niet mis bleek

De screenshot toonde 21 van 22 meldingen ingeschakeld, terwijl er zes
standaard aan horen te staan. Nagemeten op een verse installatie: precies
die zes. De rest stond dus aan door eigen keuze — geen bug.

### Getest

Nieuw `tests/test_recovery_notifications.py`, 11 tests: een herstelde
sensor wordt gemeld, de herstelmelding negeert het dempingsvenster, geen
herstel zonder probleem, niet herhaald, een uitgeschakelde melding krijgt
geen herstel, de hoofdschakelaar blokkeert ook herstelmeldingen, een
terugkerend probleem meldt meteen weer, alleen toestandsmeldingen hebben
een herstel, elke herstelsoort bestaat echt, elke heeft titel en tekst,
en de actieve toestanden overleven een herstart — anders zou een
herstart als "opgelost" gelden voor een probleem dat nog speelt.

**Volledige testsuite**: 1107 tests, allemaal groen.

## Aangescherpt wat de Zonneplan-vergelijking bewijst (v1.6.1)

**Opgemerkt**: *"Let wel op dat zonneplan financieel niets over de accu
kan zeggen, hun kunnen niet zien wat accu verbruik, naar woning en pv
naar woning etc is."*

Klopt volledig — en het legde een zwakte bloot in hóé ik het presenteerde,
niet in de vergelijking zelf.

### De vergelijking is geldig, om precies deze reden

Zonneplan ziet uitsluitend de P1-meter. Wat erachter gebeurt — accu naar
woning, PV naar woning, PV naar accu — is voor hen onzichtbaar; ze weten
niet eens dat er een accu staat.

Juist daarom klopt de vergelijking. `actual_cost_today_eur` wordt
berekend uit `p1_power_w`: **precies dezelfde meter** die Zonneplan
afrekent. Twee metingen van hetzelfde punt. Zou onze berekening uit
accu- of PV-vermogen komen, dan zou de vergelijking niets betekenen — en
daar staat nu een test op.

### Maar de tekst suggereerde te veel

Ik noemde het "voor geld wat de Kirchhoff-check voor energie is", zonder
te zeggen wat er buiten valt. En op het Financieel-tabblad staat de
**tegenfeitelijke besparing** vlak boven deze vergelijking — dan kan
iemand makkelijk denken dat Zonneplan dát bevestigt.

Dat kan het niet. "Wat had je betaald zonder accu" bestaat in hun wereld
niet. Ook de accu-boekhouding zelf — de kostprijs per kWh, de splitsing
tussen zon en net — blijft ongetoetst.

Dat staat nu expliciet in de code, in de melding, op het tabblad en als
apart veld in de diagnostiek. Een vergelijking geloofwaardiger laten
lijken dan ze is, is erger dan geen vergelijking.

### Getest

Vier tests erbij: beide kanten meten aantoonbaar dezelfde meter (via de
code zelf), de uitleg noemt wat er níét onder valt, het oordeel noemt de
P1-reikwijdte, en het dashboard legt de beperking uit.

**Volledige testsuite**: 1096 tests, allemaal groen.

## Werkelijke afrekening van Zonneplan op het Financieel-tabblad (v1.6.0)

**Gevraagd**: het financiële tabblad uitbreiden met waarden uit de
Zonneplan-integratie — met de uitdrukkelijke eis: *"Ik wil de entiteiten
niet zelf invullen, deze moeten automatisch uit de zonneplan integratie
gehaald worden zonder manuele config."*

### Geen enkel configuratieveld erbij

De prijssensor was al ingevuld, en die verraadt het voorvoegsel: uit
`sensor.zonneplan_current_quarter_hourly_electricity_tariff` volgt
`sensor.zonneplan_`. De rest wordt daaruit afgeleid.

Twee valkuilen bepaalden de opzet. De integratie levert entity_id's in
**twee talen door elkaar** —
`sensor.zonneplan_electricity_delivery_costs_today` naast
`sensor.zonneplan_elektriciteitsleveringskosten_deze_maand`, afhankelijk
van wanneer de entiteit is aangemaakt. Er worden daarom per waarde
meerdere kandidaten geprobeerd. En veel van deze sensoren **staan
standaard uit** in Home Assistant, dus een ontbrekende sensor is normaal
en levert een uitleg op in plaats van een foutmelding.

Getoetst tegen de 58 echte entiteitnamen uit een diagnostiek-export: alle
zes doelen gevonden, zonder configuratie. Er staat ook een test op dat er
géén configuratieveld is bijgekomen — dat zou de eis stilzwijgend
omzeilen.

### Wat het oplevert

Onze eigen kostenberekening naast wat Zonneplan **werkelijk afrekent**.
Dat is voor geld wat de Kirchhoff-check voor energie is: twee
onafhankelijke bronnen die hetzelfde zouden moeten zeggen.

Loopt het uiteen, dan klopt er iets niet in de prijsafhandeling — een
verkeerd prijsattribuut, vergeten netbeheerkosten, of een aanname over
teruglevering die niet meer geldt. Precies het soort fout dat je maanden
niet opmerkt omdat er nergens een tweede bron tegenover staat.

Zonneplan splitst afname en teruglevering; onze berekening is het netto
bedrag, dus die twee worden eerst verrekend.

### Ruime drempels, met opzet

Vijftig cent of 15% van het bedrag, wat het grootst is. De kostensensor
werkt maar ongeveer eens per uur bij en rekent sommige posten anders toe,
dus een deel van het verschil is normaal. Een **schaalgevoelige** drempel
is hier nodig: bij honderd euro is vijftig cent verwaarloosbaar, bij twee
euro niet. Een vaste drempel zou het aan één van beide kanten fout doen.

### Getest

Nieuw `tests/test_zonneplan_cost_comparison.py`, 14 tests: het
voorvoegsel komt uit de prijssensor, beide taalvarianten worden gevonden,
een uitgeschakelde sensor wordt overgeslagen, een andere leverancier
vindt niets, kloppende kosten worden bevestigd, een groot verschil
gesignaleerd, de drempel schaalt mee met het bedrag, zonder sensoren
volgt uitleg in plaats van een fout, sensoren zonder waarde geven
"onvoldoende data", teruglevering wordt afgetrokken, het staat in het
betrouwbaarheidsoverzicht en op de financiële sensor, en er is géén
configuratieveld bijgekomen.

**Volledige testsuite**: 1092 tests, allemaal groen.

## Betrouwbaarheid per weerbron (v1.5.2)

**Gerapporteerd**: *"Weerbronnen lopen 70 procentpunt uiteen over de
bewolking (weather.forecast_thuis: 12%, weather.openweathermap: 83%)...
Openweathermap lijkt het bij het juiste eind te hebben."*

De melding uit v1.1.8 deed precies zijn werk. Maar hij zegt alleen dát ze
uiteenlopen, niet **welke** deugt.

### Wat er nu gemeten wordt

Er bestond al een meting die vergelijkt of de gemelde bewolking klopt met
wat de panelen werkelijk doen. Die stond alleen op het **gemiddelde** —
en een gemiddelde van 12% en 83% zegt niets over welke van de twee ernaast
zit.

Dezelfde toets, met exact dezelfde drempels, wordt nu ook **per bron**
gedaan. Een test dwingt af dat het één definitie blijft: twee
berekeningen naast elkaar zouden tegenstrijdige uitkomsten kunnen geven
over dezelfde waarneming.

### Bewust meten en niet meteen wegen

Dat was de vraag erbij: *"Gezien het nu op 1 dag natuurlijk niet
betrouwbaar is."* Precies.

Er zijn twintig waarnemingen bij daglicht per bron nodig voordat er een
oordeel volgt, en er wordt pas vergeleken als **beide** bronnen die
drempel hebben gehaald — anders zou een bron met drie waarnemingen "de
beste" kunnen heten.

Het gemiddelde blijft daarbij een **ongewogen** gemiddelde. Een bron die
deze week beter is, kan volgende week slechter zijn; automatisch gaan
wegen op basis van een paar dagen zou hetzelfde soort overhaaste conclusie
zijn als waar deze hele meting tegen beschermt. Daar staat een test op.

Blijkt één bron structureel meer dan 20 procentpunt beter, dan verschijnt
dat als informatieve regel met het advies de andere uit de configuratie te
halen. Jouw keuze, niet die van de integratie.

### Waar je het ziet

Per bron een regel in het betrouwbaarheidsoverzicht, plus de volledige
uitsplitsing op de weerensemble-sensor en in de diagnostiek-export.

### Getest

Nieuw `tests/test_weather_source_reliability.py`, 11 tests: elke bron
wordt apart beoordeeld (met de gerapporteerde 12%-tegen-83%-situatie),
geen oordeel op één dag, twee goede bronnen worden allebei betrouwbaar
genoemd, dezelfde drempels als de ensemble, een duidelijk betere bron
wordt genoemd, vergelijkbare bronnen krijgen geen advies, geen
vergelijking tot beide genoeg hebben, het is informatief en geen
aandachtspunt, er wordt niets automatisch gewogen, elke bron staat in het
overzicht, en de meting overleeft een herstart.

**Volledige testsuite**: 1078 tests, allemaal groen.

## De laatste drie meldingen aangesloten (v1.5.1)

Van de eenentwintig soorten uit v1.2.0 stonden er nog drie op de
uitzonderingenlijst. Die zijn nu ook echt aangesloten, en de uitzondering
is uit de test verwijderd — alle eenentwintig worden daadwerkelijk
verstuurd.

### Dagoverzicht

Na 22:00, met de dag op een rij: opwek, verbruik, netimport, en wat de
accu heeft gescheeld ten opzichte van dezelfde dag zonder accu.

### Maandoverzicht

Op de eerste van de maand, met dezelfde vergelijking over de hele maand.

### Adviesmodule is klaar met leren

Deze had de meeste zorg nodig. Alleen de **overgang** naar "klaar" wordt
gemeld, door de huidige stand te vergelijken met de vorige. Zonder dat
zou elke tick opnieuw melden dat een module klaar is — binnen een dag
waardeloos.

Twee dingen die daarbij misgaan als je er niet op let. Bij een **verse
installatie** is elke module in één klap "nieuw klaar"; dan hoort er geen
melding te komen met de hele lijst, alleen een stille registratie van de
uitgangssituatie. En de lijst moet **bewaard blijven**, anders meldt elke
herstart dezelfde overgang opnieuw. Beide hebben een eigen test.

### Getest

Zes tests erbij in `test_notifications.py`: het dagoverzicht komt alleen
's avonds, het rapporteert de besparing, het maandoverzicht alleen op de
eerste, alleen de overgang naar klaar wordt gemeld (twee rondes achter
elkaar geeft één melding), de eerste ronde kondigt niet alles aan maar
onthoudt de stand wel, en die stand overleeft een herstart.

De testhulp stubt onderweg de prijsvoorspelling — zonder dat loopt de
meldingsronde stuk op een ontbrekende sensor voordat de samenvattingen
aan de beurt zijn.

**Volledige testsuite**: 1067 tests, allemaal groen.

## De integratie bewaakt haar eigen zonvoorspelling (v1.5.0)

**Gevraagd**: *"Neem je dit zelf mee in een diagnostiek, zodat je dit
zelf detecteert wanneer dit niet correct is"* — nadat ik had uitgelegd
hoe je `last_deviation_percent` handmatig naast `learned_bias_percent`
legt.

Terecht: parameters handmatig bewaken is precies wat de integratie zelf
hoort te doen.

### Wat er nu zelf wordt gecontroleerd

De geleerde bias haalt de systematische afwijking eruit — bij jou −11,6%,
omdat Solcast structureel iets te optimistisch is over jouw installatie.
Wat daarna overblijft hoort **dagruis** te zijn, rond nul. In de laatste
export was dat −10,3% tegen −11,6%: dicht bij elkaar, dus de correctie
werkt.

Blijven de recente dagen structureel aan één kant van die bias hangen,
dan is er iets veranderd aan de installatie zelf: vervuiling, een
uitgevallen streng, of een boom die is uitgegroeid. Dat is precies het
soort langzame verslechtering dat je met het blote oog mist.

Twee ontwerpkeuzes: alleen de **laatste vijf dagen** tellen, zodat een
verslechtering niet wordt weggemiddeld door een lange goede
geschiedenis. En ook een afwijking naar bóven telt mee — structureel
beter dan verwacht betekent evengoed dat de geleerde bias niet meer
klopt.

### Hoe dicht zit vandaag bij de weinig-zon-grens?

Bij die vraag van vanochtend bleek 15,4 kWh verwacht tegen 21,8 kWh op
een typische dag: **71%**, vlak op de grens. Dat was nergens te zien,
waardoor niet te beoordelen viel of het uitblijven van extra-dip-laden
terecht was of dat de drempel te laks stond.

Die verhouding staat nu in de diagnostiek, inclusief of het een
grensgeval is. Bewust met **dezelfde fractie** die de beslissing zelf
gebruikt — een eigen tweede drempelberekening zou precies het risico
geven dat overzicht en beslissing uit elkaar lopen. Daar staat een test
op.

### Negen meldingen hadden een schakelaar maar werden nooit verstuurd

Bij het aansluiten hiervan bleek dat van de eenentwintig soorten uit
v1.2.0 er **negen** wel een schakelaar hadden maar nergens werden
verzonden. Een schakelaar voor een melding die nooit komt is erger dan
geen schakelaar.

Zes daarvan zijn nu aangesloten: zonopbrengst wijkt structureel af,
weinig-zon-dag herkend, uitzonderlijk duur kwartier, goedkoopste blok
begint bijna, lage accustand vlak voor de piek, en sensor niet
uitleesbaar. Er is een test die de lijst afdwingt; dag- en
maandoverzicht plus "module is klaar" staan er bewust nog als
uitzondering in, want die volgen nog.

### Getest

Nieuw `tests/test_solar_forecast_health.py`, 11 tests: een stabiele
correctie wordt als werkend gemeld (met de echte cijfers uit de export),
structurele drift naar beneden én naar boven wordt gesignaleerd, alleen
recente dagen tellen, geen oordeel onder de drempel, zonder tracker
"niet geconfigureerd", het staat in het betrouwbaarheidsoverzicht, de
marge toont hoe dicht vandaag bij de grens zat, zonder voorspelling geen
marge, de marge gebruikt dezelfde fractie als de beslissing, en elke
meldingssoort wordt daadwerkelijk verstuurd.

**Volledige testsuite**: 1061 tests, allemaal groen.

## Configuratieformulier was niet meer te verzenden (v1.4.2)

**Gerapporteerd** met screenshot: twee velden toonden **"expected
float"** en het formulier liet zich niet meer opslaan.

Dat waren de PV-oriëntatie en hellingshoek uit v1.4.1 — een fout die ik
er de vorige versie zelf in heb gezet.

### Wat er misging

Beide velden zijn optioneel: leeg laten hoort te mogen, want niet
iedereen weet welke kant zijn panelen op liggen. Maar een leeg optioneel
veld krijgt `None` als standaardwaarde, en een `NumberSelector` wijst dat
af.

Alle bestaande getalvelden in dit formulier hebben een concrete
standaard — `feedin_cost` valt terug op nul, en zo verder — en liepen
daar dus nooit tegenaan. Deze twee waren de eerste die écht leeg mochten
blijven.

Het vervelende is dat het niet alleen die twee velden trof: zolang de
validatie klaagt, is het **hele formulier** geblokkeerd. Alle andere
instellingen op dat scherm waren daardoor ook niet op te slaan.

### De fix

Het worden tekstvelden, met de controle in de validatie die er sinds
v1.1.5 toch al is. Leeg laten betekent gewoon "geen ijkpunt". Een
ingevulde waarde wordt gecontroleerd op bereik en meteen naar een getal
omgezet, zodat de coordinator er later geen tekst uit krijgt.

Een komma als decimaalteken wordt geaccepteerd — op een Nederlands
toetsenbord ligt die meer voor de hand dan een punt.

### Borging tegen herhaling

Een test scant het formulier op optionele `NumberSelector`-velden zonder
terugvalwaarde. Zo'n veld blokkeert het hele formulier zodra het leeg
blijft, en dat is precies het soort fout dat je pas merkt als iemand het
probeert op te slaan.

### Getest

Vijf tests erbij in `test_review_findings.py`: lege velden worden
geaccepteerd en verdwijnen uit de configuratie, een geldige waarde wordt
een getal, een komma-decimaal werkt, onzin en waarden buiten bereik
worden afgewezen, en de borging tegen optionele NumberSelectors zonder
terugval.

**Volledige testsuite**: 1050 tests, allemaal groen.

## Opgegeven PV-oriëntatie als ijkpunt (v1.4.1)

**Aanleiding**: een luchtfoto en een camerabeeld van de opstelling. Die
lieten iets zien dat mijn eerste schatting onderuit haalde.

### Wat de foto's corrigeerden

Ik had de oriëntatie afgeleid uit de **daknok** van het woningblok en kwam
op ~235° (WZW). Maar de panelen liggen op een **plat dak op een schans**,
los van de nok — dan zegt de daklijn niets. Op basis van de aangegeven
richting is het eerder **190–210°, zuid tot zuid-zuidwest**.

Dat is precies waarom een ijkpunt nodig is: een afgeleide waarde zonder
iets om tegen te houden, is een gok met een cijfer erbij.

### Twee nieuwe velden

Bij Configureren kun je nu je **werkelijke oriëntatie** en
**hellingshoek** invullen. De integratie vergelijkt haar eigen afleiding
daarmee en meldt wanneer die afwijkt.

Dat is meer dan een controle op de methode. Verschuift de afgeleide
piekrichting later weg van de opgegeven waarde terwijl de panelen niet
zijn verplaatst, dan wijst dat op iets **fysieks**: een boom die is
uitgegroeid, vervuiling op een deel van het vlak, of een uitgevallen
streng. Daar hoort een melding bij, die je zoals alles op het
Meldingen-tabblad aan of uit kunt zetten.

### De hellingshoek doet er wél toe — indirect

Nog steeds wordt hij niet geschat. Maar als je hem invult, bepaalt hij de
**tolerantie**.

Bij een flauwe helling is de opbrengstcurve veel breder en ligt het
piekmoment minder scherp vast: het schommelt dan per dag sterk. Een
vlakke opstelling zou anders voortdurend "afwijkend" melden terwijl er
niets aan de hand is. Onder 20 graden helling wordt de tolerantie daarom
opgerekt van 25 naar 40 graden.

Dat is een eigenschap van de methode, geen fout — en die hoort in de
tolerantie te zitten in plaats van in een verkeerde conclusie.

### Geen oordeel bij een zwakke schatting

Zolang de afleiding zelf nog op "onvoldoende data" staat, komt er geen
oordeel over afwijking. Een verschil zegt dan niets, en het zou de eerste
dagen na installatie gegarandeerd loos alarm geven.

### Getest

Zes tests erbij in `test_pv_installation_profile.py`: een kloppende
oriëntatie wordt bevestigd, een grote afwijking gesignaleerd, een flauwe
helling verruimt de tolerantie (met steil en vlak naast elkaar bij
dezelfde afwijking), geen oordeel bij een zwakke schatting, zonder
opgegeven waarde wordt er niets vergeleken, en het verschil rekent
cirkelvormig — 350° en 10° liggen twintig graden uit elkaar, niet 340.

De bestaande test die vastlegt dat er géén hellingshoek wordt geschat is
aangescherpt: hij accepteert nu `opgegeven_hellingshoek`, want dat is een
ingevulde waarde en geen schatting.

**Volledige testsuite**: 1045 tests, allemaal groen.

## PV-installatieprofiel afgeleid uit de zonnestand (v1.4.0)

**Gevraagd**: *"kun je nu ook zelf een berekening maken voor de
verwachtte azimuth en andere relevante informatie hoe mijn PV installatie
geinstalleerd ligt"*.

Dat kan, want de zon vertelt het. Er is geen extra sensor voor nodig.

### Oriëntatie

Het vermogen piekt op het moment dat de zon **recht voor de panelen**
staat. De zon-azimut op dat moment is dus een directe schatting van de
paneelrichting. Over meerdere dagen de mediaan nemen maakt het robuust.

Alleen dagen die **helder genoeg** waren tellen mee: de opbrengst moet
minstens 70% van de Solcast-verwachting hebben gehaald. Op een dag met
wisselende bewolking ligt de piek waar het toevallig opklaarde, en dat
zegt niets over je daklijn.

Uit de **spreiding** van die dagelijkse piekrichtingen volgt nog iets: bij
één dakvlak liggen ze dicht bij elkaar. Meer dan 40 graden spreiding
wijst op meerdere oriëntaties — een oost/west-opstelling bijvoorbeeld.

### Beschaduwing per windrichting

Per vakje van 10 graden azimut wordt de verhouding tussen werkelijke en
verwachte opbrengst bijgehouden. Een richting die structureel onder de
60% blijft, verraadt een obstakel: een boom, een schoorsteen, een
dakkapel van de buren.

Twee dingen worden bewust overgeslagen. Vakjes met minder dan twintig
metingen krijgen geen oordeel. En momenten waarop Solcast minder dan
200 W verwacht tellen niet mee — vroeg in de ochtend is de verhouding
anders betekenisloos en zou álles als beschaduwd gelden.

### Wat ik bewust NIET bereken

**De hellingshoek.** Die is uit deze data niet betrouwbaar af te leiden:
het vraagt maanden aan seizoensvariatie, of aannames over instraling die
de integratie niet kan controleren. Een getal geven dat er zomaar vijftien
graden naast zit is erger dan geen getal — en er is een test die vastlegt
dat het profiel geen hellingshoek bevat.

### Wanneer je iets ziet

Vijf voldoende heldere dagen voor een eerste schatting, twintig voor
"betrouwbaar". Het profiel gaat mee in de opslag, want zonder dat zou die
telling na elke herstart opnieuw beginnen en nooit iets opleveren.

Te vinden op het Zelflerend-tabblad en als eigen sensor, met een regel in
het betrouwbaarheidsoverzicht.

### Getest

Nieuw `tests/test_pv_installation_profile.py`, 14 tests: geen oordeel
zonder genoeg heldere dagen, de oriëntatie wordt afgeleid, een
zuidwest-dak wordt herkend, een bewolkte dag telt niet mee, meerdere
dakvlakken worden gesignaleerd en één dakvlak niet, beschaduwing per
richting, een te dun bezet vakje geeft geen oordeel, lage verwachtingen
worden genegeerd, 's nachts wordt niets geleerd, er wordt géén
hellingshoek geschat, de windrichting-omrekening klopt in alle vier de
kwadranten, het profiel overleeft een herstart, en het staat in het
betrouwbaarheidsoverzicht.

**Volledige testsuite**: 1039 tests, allemaal groen.

## Uitschieter-filter weet nu of de zon wel schijnt (v1.3.1)

Het filter op de achtertuinsensor bestaat expliciet voor *"kortstondig
direct zonlicht op de sensor"*. Maar het wist niet of de zon überhaupt
scheen.

### Wat er niet klopte

Een temperatuursprong om drie uur 's nachts kreeg exact dezelfde
behandeling, inclusief de melding dat het mogelijk zonlicht was. Dat is
aantoonbaar onjuist — en het kostte 45 minuten wachten voor iets dat
vrijwel zeker gewoon weer was.

### Twee aanpassingen

**Staat de zon onder de horizon, dan kan het geen flits zijn.** Het
wachtvenster gaat dan van 45 naar 10 minuten, en de melding zegt eerlijk
"de zon staat onder de horizon" in plaats van iets te suggereren dat
onmogelijk is. Niet nul minuten, want een langsrijdende auto of een
openslaande deur kan ook een sprong geven — maar wel veel korter.

**De blootstellingsrichting wordt geleerd.** Zodra een uitschieter niet
aanhoudt, was het een echte kortstondige flits — en dan wordt onthouden
uit welke richting de zon op dat moment kwam. Na vijf van die
waarnemingen weet de integratie waar deze sensor zon vangt. Staat de zon
daar ver buiten, dan is een sprong minder verdacht en geldt het korte
venster.

Bewust geleerd en niet gevraagd: de integratie weet niet waar die sensor
hangt, en ernaar vragen zou een configuratieveld opleveren dat moeilijk
goed in te vullen is. De meeste mensen weten niet uit welke windrichting
hun sensorbehuizing zon vangt.

### Eén detail dat makkelijk misgaat

De afstand tussen twee windrichtingen is **cirkelvormig**: 350° en 10°
liggen twintig graden uit elkaar, niet 340. Zonder die correctie zou een
sensor die op het noorden staat nooit herkend worden. Daar staat een test
op.

### Getest

Nieuw `tests/test_backyard_spike_sun_aware.py`, 12 tests: 's nachts
beweert de melding geen zonlicht meer, het wachten is dan veel korter,
overdag geldt het volle venster, de richting wordt geleerd uit een
niet-aanhoudende flits, een sprong uit een andere richting is minder
verdacht, uit de geleerde richting juist wel, de cirkelvormige afstand
klopt, te weinig waarnemingen betekent geen conclusie, 's nachts wordt er
niets geleerd, zonder zondata keert het oude gedrag terug, de geleerde
richting overleeft een herstart, en een echte zonneflits wordt nog steeds
genegeerd.

**Volledige testsuite**: 1025 tests, allemaal groen.

### Nog open

Alleen de vraag of vandaag terecht niet als weinig-zon-dag telt — daar is
een diagnostiek-export voor nodig van een dag met bewolking.

## Eén betrouwbaarheidsschaal voor alle gegenereerde data (v1.3.0)

**Gevraagd**: *"ik wil dit eigenlijk voor vele data welke wordt
gecreeerd, hoe betrouwbaar is de gegenereerde data"* — en: *"Ik heb de
sun integratie in HA, kan dit nog helpen?"*

### Vijf woordenlijsten voor dezelfde vraag

De inventarisatie:

| Waar | Woorden |
|---|---|
| Adviesmodules | klaar / bijna_klaar / onvoldoende_data / kwaliteit_te_laag / structureel_beschikbaar |
| Sensor-gezondheid | goed / verminderd / slecht |
| Klimaatprojectie | betrouwbaar / indicatief / onvoldoende_data |
| Kalman-divergentie | verwaarloosbaar / klein / noemenswaardig |
| Meetfrequentie | volgt_de_tick / traag |

En van de 56 sensoren hadden er **40 helemaal geen aanduiding** —
waaronder het geleerde accu-rendement, dat wél meerekent in de
extra-dip-laadbeslissing maar nergens liet zien of het op zeven of op
zeventig metingen rustte.

### Eén schaal, zes niveaus

`niet_geconfigureerd` · `onvoldoende_data` · `indicatief` ·
`betrouwbaar` · `onbetrouwbaar` · `niet_toetsbaar`

Alleen de middelste drie vormen een **ladder**. `niet_geconfigureerd` en
`niet_toetsbaar` staan er bewust buiten: het eerste betekent "er is
niets", het tweede "er valt principieel niets tegen af te zetten". Ze op
de ladder zetten zou suggereren dat ze met wachten beter worden — precies
de verwarring die het oude "structureel_beschikbaar" opriep.

Bewust een **vertaling** en geen hernoeming. De interne sleutels blijven
zoals ze zijn, zodat bestaande automatiseringen en tests blijven werken;
wat je ziet is voortaan wél overal hetzelfde.

### Het onderscheid dat er echt toe doet

De meeste regels meten **data-rijpheid**: hoeveel er is verzameld. Veel
metingen betekent niet dat een waarde klopt, alleen dat er genoeg is om
er iets van te vinden. Waar een échte nauwkeurigheidsmeting bestaat —
Digital Twin, weerensemble, sensor-gezondheid — telt díe meting, en die
zegt wél iets over juistheid. Dat staat expliciet op het tabblad, want
het verschil is makkelijk over het hoofd te zien.

### Nieuw tabblad "Betrouwbaarheid"

Alles op één plek, gegroepeerd in Adviesmodules, Metingen en Geleerde
waarden, met per regel het niveau, de waarde en waaróp het oordeel rust.
Plus een sensor waarvan de toestand het aantal betrouwbare regels is — in
één getal hoe ver de integratie is ingeleerd.

Het bewolkingslabel toont nu ook zijn eigen betrouwbaarheid: "helder
(bronnen kloppen in 67% van de gevallen)". Dat was de aanleiding voor dit
hele punt.

### De zonnestand repareert een blinde vlek

In v1.1.9 werd de meetfrequentie van de PV-sensor overgeslagen als die op
nul staat, omdat de nacht het cijfer vertekende. Maar dat gebruikt **de
sensor zelf** als criterium. Hangt je SolarEdge-koppeling er midden op de
dag uit, dan is de waarde 0, concludeert de code "geen zon dus terecht
stil", en blijft de storing volledig onzichtbaar — precies het soort
stille uitval dat die meting moest opsporen.

Nu bepaalt de **zonnestand** of de sensor zou moeten bewegen.
Voorkeursvolgorde: de fase-sensor (schone opsomming, dus geen eigen
drempel nodig), dan de zonshoogte, dan `sun.sun` als vangnet — die zit
standaard in Home Assistant. Twee nieuwe configuratievelden.

### Getest

Nieuw `tests/test_reliability_scale.py`, 17 tests: elk niveau heeft een
uitleg, elk oud woord vertaalt, de ladder sluit de twee buitenstaanders
uit, alle vijf woordenlijsten vertalen correct, een onbekend woord geldt
conservatief als onvoldoende, de drie drempels van het
metingen-oordeel, de eenheid komt in de toelichting, het overzicht spreekt
één taal, de geleerde waarden staan erin, het rendement toont zijn
rijpheid, elke regel heeft een leesbaar label, MPC verschijnt als "niet
toetsbaar", en het tabblad bestaat.

Nieuw `tests/test_sun_daylight_gate.py`, 10 tests: een vastgelopen
PV-sensor valt nu wél op, de nacht wordt nog steeds overgeslagen, de
fase-sensor wint, schemering is geen daglicht, de hoogtedrempel werkt in
beide richtingen, `sun.sun` is het vangnet, terugval op de toestand
zonder hoogte, zonder bron "niet vast te stellen", zonder zondata keert
het oude gedrag terug, en een onleesbare eigen sensor valt door naar het
vangnet.

Eén bestaande test zocht de legenda op titel; het nieuwe tabblad heeft er
ook een, dus die zoekt nu eerst het juiste tabblad op.

**Volledige testsuite**: 1013 tests, allemaal groen.

### Nog op de lijst

Uitschieter-filter slimmer met zonnestand (`golden_hour`/`blue_hour` plus
azimut), en de vraag of vandaag terecht niet als weinig-zon-dag telt.

## Meldingen-tabblad met een schakelaar per melding (v1.2.0)

**Gevraagd**: *"Ik wil nog een tabblad waar ik meldingen in en uit kan
schakelen... echter wil ik ze wel aan/uit kunnen zetten"*, gevolgd door
*"zoveel mogelijk relevante meldingen toevoegen"*.

### Wat er was

Zeven meldingen, allemaal aan één configuratieveld: alles aan of alles
uit. De modus-wijziging kon bij wisselende prijzen meerdere keren per dag
afgaan, en de enige manier om daar vanaf te komen was álle meldingen
uitzetten.

### Wat er nu is

**Twintig soorten**, elk met een eigen schakelaar, plus een
hoofdschakelaar om alles in één keer stil te zetten. Naast de bestaande
zeven onder meer: accu haalt de nacht niet, accu vol terwijl de zon nog
schijnt, negatieve prijzen vandaag, integratie loopt vast, accumodule
loopt uit de pas, dag- en maandoverzicht.

Twee ontwerpkeuzes die het verschil maken tussen bruikbaar en wegswipen:

**Alleen de zes bestaande soorten staan standaard aan.** Al het nieuwe
begint uit. Twintig meldingen die zichzelf aanzetten is een garantie dat
je er binnen een week niets meer van leest — en dan is de hele functie
waardeloos.

**Elke melding heeft een eigen dempingsvenster**, van 5 minuten voor
"apparaat klaar" tot een etmaal voor de maandsamenvatting. Binnen dat
venster gaat dezelfde melding niet nog een keer af. Wat er onderdrukt is
wordt geteld en op het tabblad getoond, zodat het niet stilzwijgend
verdwijnt.

### De borging die ertoe doet

De controle op schakelaar en dempingsvenster zit in de **gedeelde
verzendfunctie**, niet op elke aanroepplek. Een melding die de schakelaar
omzeilt kan dus alleen ontstaan door die functie helemaal niet te
gebruiken.

Daar staan twee tests op: elke aanroep moet een soort meegeven (de test
telt haakjes om de hele aanroep te lezen, want ze staan op sterk
wisselende inspringing), en elke gebruikte soort moet in het register
bestaan — een typefout zou anders stilzwijgend een melding opleveren die
altijd doorgaat.

Een onbekende soort wordt bewust wél doorgelaten. Beter een melding te
veel dan een stille regressie zodra iemand een nieuwe soort toevoegt en
het register vergeet.

### Alles blijft staan na een herstart

Zowel de aan/uit-standen als de verzendmomenten gaan mee in de opslag uit
v1.0.4. Dat tweede is geen detail: zonder dat zou het dempingsvenster na
elke herstart opnieuw beginnen en kon dezelfde melding alsnog meteen weer
afgaan.

De hoofdschakelaar laat de losse keuzes met rust, zodat je na het weer
aanzetten precies hebt wat je had.

### Getest

Nieuw `tests/test_notifications.py`, 20 tests: ingeschakeld versturen,
uitgeschakeld niet, de hoofdschakelaar blokkeert alles en laat de losse
keuzes intact, dezelfde melding wordt gedempt, na het venster weer
toegestaan, onderdrukte meldingen worden geteld, verschillende soorten
dempen elkaar niet, alleen de bestaande zes staan standaard aan, elke
soort heeft een venster en een uitleg, sleutels zijn uniek, elke aanroep
geeft een soort mee, elke gebruikte soort bestaat, een onbekende soort
wordt doorgelaten, de instellingen én het dempingsvenster overleven een
herstart, het overzicht dekt alles, en er is een schakelaar op het
tabblad voor élke soort.

**Volledige testsuite**: 986 tests, allemaal groen.

### Nog op de lijst

Dit is het eerste van vier besproken punten. Volgend: één
betrouwbaarheidsschaal voor alle gegenereerde data, met de daglicht-poort
op basis van de zonshoogte.

## De meetfrequentie mat vooral hoeveel uur het nacht was (v1.1.9)

**Aangekaart**: *"sensor.solaredge_i1_ac_power beweegt maar bij 13,8% van
de metingen"* — met terechte twijfel of dat cijfer klopt.

Het klopte niet. En het is mijn eigen meting uit v1.1.4.

### De vertekening

De teller telde élke tick mee, ook de momenten waarop de sensor
**terecht** stilstaat. Het PV-vermogen is 's nachts per definitie
constant nul:

| | |
|---|---|
| Meetperiode | ~16 uur (194 metingen) |
| Waarvan nacht | ~96 metingen, PV kán niet bewegen |
| Gemeten wijzigingen | 26 |
| **Gerapporteerd** | 26/194 = **13,4%** |
| **Werkelijk, overdag** | 26/98 = **27%** — één wijziging per ~19 min |

De conclusie klopte dus wel (trager dan de vijf-minutencyclus, wat past
bij de SolarEdge-cloud die elk kwartier pollt), maar het getal
suggereerde meer dan twee keer zo traag als het is.

Hetzelfde gold voor de beschikbare energie: staat je accu stil, dan
hóórt die waarde niet te bewegen. Dat als "trage sensor" tellen is
onzin.

### De correctie

Er wordt nu alleen gemeten op momenten waarop de sensor überhaupt kán
bewegen: de PV-sensor als er opwek is, de beschikbare-energiesensor als
de accu daadwerkelijk laadt of ontlaadt. Netvermogen en accuvermogen
worden onvoorwaardelijk gemeten — die fluctueren altijd, dus daar ís
stilstand een signaal.

De correctie poetst het probleem niet weg: er is een test die vastlegt
dat een sensor die tijdens *actieve* momenten nauwelijks beweegt nog
steeds als traag geldt.

### Waarom dit ertoe doet

Dit getal is geen weetje. Het is precies het cijfer dat vorige week de
21%-gezondheidsstoring verklaarde, en het is de onderbouwing onder de
keuze om afgeleide tempo's over de werkelijke beweging te rekenen. Een
maat die systematisch te pessimistisch is, stuurt een volgende diagnose
de verkeerde kant op.

### Getest

Vier tests erbij in `test_sensor_cadence.py`: honderd nachtelijke
metingen tellen niet mee voor de PV-sensor (en het percentage over de
dagmetingen klopt daarna), een stilstaande accu telt niet tegen de
energiesensor, netvermogen en accuvermogen worden onvoorwaardelijk
gemeten, en een sensor die tijdens actieve momenten nauwelijks beweegt
geldt nog steeds als traag.

De bestaande tests gebruikten de energiesensor zonder accuvermogen — na
deze wijziging terecht niet meer gemeten — en zijn meebewogen naar een
actieve accu.

**Volledige testsuite**: 966 tests, allemaal groen.

## Weerbronnen apart zichtbaar + wismechanisme werkte niet (v1.1.8)

**Gerapporteerd**: *"Weather ensemble (bewolkingsgraad) 25,4% — het is nu
zo goed als volledig bewolkt."*

### Het gemiddelde verborg het meningsverschil

De ensemble middelt twee weerbronnen. Dat gemiddelde alleen kan een groot
verschil volledig verbergen:

| Bron A | Bron B | Gemiddelde |
|---|---|---|
| 25% | 26% | 25,5% |
| **0%** | **51%** | **25,5%** |

Precies hetzelfde cijfer, twee totaal verschillende situaties — en in het
tweede geval is er iets mis met een bron. De afzonderlijke waarden waren
nergens zichtbaar, ook niet in de diagnostiek-export, waardoor niet te
achterhalen was wélke bron ernaast zat.

Per bron wordt nu de eigen meting vastgelegd, plus de spreiding ertussen.
Lopen ze meer dan 40 procentpunt uiteen, dan verschijnt dat als
informatieve regel mét beide waarden. Informatief en geen aandachtspunt:
het is geen storing van deze integratie, maar wel de verklaring als de
gerapporteerde bewolking niet klopt met wat je buiten ziet.

### En een fix die nooit werkte

In dezelfde export viel op dat `energy_balance_method_version` op **3**
stond in de opslag, terwijl het wismechanisme uit v1.1.6 juist bedoeld
was voor een opslag die dat veld nog **niet** kende.

De oorzaak: het veld begon in de code al op de huidige waarde. De
vergelijking "opgeslagen versie ≠ huidige versie" was daardoor altijd
onwaar, precies in het geval waarvoor het gemaakt was. De reeks met oude
metingen — inclusief die 15330 W — is dus nooit gewist; hij is vanzelf
uit het venster van twintig gelopen.

Het veld begint nu op "onbekend". Een opslag van vóór v1.1.6 wordt
daardoor wél herkend. Op een verse installatie wist het een lege lijst,
wat niets uitmaakt.

### Wat er in dezelfde export goed bleek

Twee dingen die de moeite van het vermelden waard zijn.

**De sensor-gezondheid staat op 100% ("goed")**. Alle twintig metingen
liggen nu tussen 46 en 247 W, ruim onder de drempel van 300. De fix van
v1.1.6 doet precies wat hij moest doen.

**Het meetfrequentie-rapport bevestigt de diagnose**:
`zendure_manager_available_kwh` beweegt bij 29,9% van de metingen,
`solaredge_i1_ac_power` bij 13,4%. De accuvermogen- en P1-sensor volgen
de tick wél (99,5% en 91,8%). Precies het getal dat vorige week ontbrak.

### Getest

Nieuw `tests/test_weather_ensemble_spread.py`, 9 tests: elke bron wordt
apart vastgelegd, het gemiddelde alleen verbergt het verschil (twee
scenario's met identiek gemiddelde), een grote spreiding wordt gemeld met
beide waarden erbij, het is informatief en geen aandachtspunt, eensgezinde
bronnen worden niet gemeld, de drempel wordt gerespecteerd, één bron geeft
geen spreiding (in plaats van een misleidende nul), de waarden worden
gewist als geen bron meer meldt, en de sensor toont de uitsplitsing.

Twee tests erbij in `test_state_persistence.py`: een oude opslag wist de
balansreeks, een actuele opslag behoudt hem. De testopzet is meebewogen
zodat hij een opslag van de huidige versie nabootst.

**Volledige testsuite**: 962 tests, allemaal groen.

## Drift accepteren als nieuw normaal (v1.1.7)

**Gevraagd**: *"1 apparaat/apparaten mogelijk defect: Koelkast schuur
Vermogen. Hoe kan dit als acceptabel worden gezien?"*

Antwoord op de vraag zoals hij bedoeld was: **dat kon niet**, en dat was
een gat.

### Waarom de melding bleef staan

De drift-detectie herstelt zichzelf alleen als het verbruik **vijf dagen
op rij terugkeert** naar het oude niveau. Doet het dat niet — omdat het
apparaat werkelijk structureel meer is gaan gebruiken, of gewoon omdat
het zomer is en een koelkast dan harder werkt — dan blijft de melding
weken staan, tot de mediaan van de geschiedenis vanzelf is meegekropen.

De enige zichtbare uitwegen waren bot:

- `unconfirm_nilm_device` — wist de hele leergeschiedenis;
- `reject_nilm_device` — haalt het apparaat er helemaal uit.

Allebei gooien maanden aan opgebouwde kennis weg voor iets wat eigenlijk
"ja, dit klopt, ga verder" is.

### De nieuwe actie

`energy_management_system.accept_nilm_device_drift` met één veld,
`entity_id`. Het apparaat **blijft bevestigd en wordt gewoon verder
gevolgd**; alleen de referentie wordt opnieuw verankerd op het recente
niveau, en de melding verdwijnt.

Concreet: de oudste dagen verdwijnen uit de geschiedenis zodat de mediaan
meteen het nieuwe normaal weerspiegelt in plaats van er dertig dagen over
te doen. De opgebouwde CUSUM-som en het alarm worden gewist.

Bewust wordt **niet** de hele geschiedenis leeggegooid: dan zou er tien
dagen lang geen referentie zijn, en kon een échte verslechtering in die
periode ongemerkt blijven. Er is een test die vastlegt dat een nieuwe,
verdere stijging na het accepteren gewoon weer een alarm geeft — accepteren
mag het apparaat niet doof maken.

### De melding vertelt nu ook wat je kunt doen

Dat was het eigenlijke probleem: er stond wél wat er aan de hand was,
maar niet wat de uitweg is. Het aandachtspunt noemt nu zelf de vraag
("klopt het hogere verbruik, bijvoorbeeld een koelkast die het in de
zomer zwaarder heeft?") en de actie erbij.

### Getest

Nieuw `tests/test_accept_nilm_drift.py`, 9 tests: het alarm verdwijnt,
het apparaat blijft bevestigd en komt niet op de zwarte lijst, de
geschiedenis wordt verankerd op het recente niveau, ze wordt niet gewist,
het moment van accepteren wordt vastgelegd, een nieuwe verslechtering
daarna geeft weer een alarm, een onbekend apparaat geeft netjes False,
het aandachtspunt noemt de uitweg, en de actie is geregistreerd én
gedocumenteerd.

**Volledige testsuite**: 951 tests, allemaal groen.

## Sensor-gezondheid: het was de resolutie, niet de sensoren (v1.1.6)

**Gevraagd**: *"Waarom nog steeds een slechte score?"* — 20%, ondanks de
fix van v1.1.3.

### Wat de foutreeks verried

De resterende fouten lagen rond **880, 976, 1003, 1123 en 1175 W**. Weer
geen ruis, weer een patroon.

Je beschikbare-energiesensor stapt in hele **SoC-procenten**. Bij ~7,7
kWh is dat ~0,077 kWh per stap:

| Interval | Eén stap komt neer op |
|---|---|
| 5 min | **920 W** |
| 10 min | 460 W |
| 30 min | 155 W |

De drempel ligt op 300 W. Elke enkele stap over één tick was dus
automatisch een "slechte meting" — de check mat niet je sensoren maar de
**resolutie van de sensor gedeeld door een kort interval**.

v1.1.3 loste het stilstandsprobleem op, maar liet een beweging van 0,005
kWh al meetellen: ver onder één stap. Daardoor werd feitelijk elke stap
meteen afgerekend, met de kwantisatieruis als uitkomst.

### De fix: wachten tot het interval lang genoeg is

Er wordt nu pas geoordeeld na **30 minuten**. Diezelfde stap komt dan uit
op ~155 W en valt ruim binnen de drempel.

Dat is exact het principe dat het klimaat-tempo al toepaste — meten over
een anker van ongeveer een uur, met in de code de reden erbij: *"een
tempo uit tick-tot-tick-verschillen is numeriek instabiel voor een
langzaam bewegende grootheid"*. Diezelfde redenering gold hier net zo
goed; ze was alleen nooit toegepast.

Er is ook een eigen bovengrens van twee uur gekomen. De bestaande grens
van twintig minuten is bedoeld voor energie-integratie en zou hier — lager
dan het nieuwe minimum — betekenen dat er nooit meer iets gemeten wordt.

### Oude metingen tellen niet meer mee

De meetmethode is tussen v1.1.2 en v1.1.6 twee keer wezenlijk veranderd,
en de foutreeks wordt sinds v1.0.4 bewaard. Er stonden dus nog metingen
in van de oude methode — waaronder die 15330 W — die het venster van
twintig blijven vullen en de score omlaag drukken zonder dat er iets mis
is.

De methode heeft nu een versienummer. Verandert dat, dan wordt de reeks
eenmalig gewist en begint de meting schoon. **Na installatie staat de
score dus even op leeg**, tot er tien nieuwe metingen zijn — en die komen
nu langzamer binnen, wat terecht is.

### Getest

Vier tests erbij in `test_energy_balance_stale_sensor.py`: één
kwantisatiestap over vijf minuten wordt genegeerd, dezelfde stap over 35
minuten valt binnen de drempel, geschiedenis van een oudere methode wordt
gewist, en geschiedenis van de huidige methode blijft staan (anders zou
elke herstart de meting terugzetten).

Zes bestaande tests rekenden met intervallen van vijf of zes minuten —
precies het scenario dat nu bewust wordt overgeslagen. Die zijn
meebewogen naar realistische intervallen, met de energiehoeveelheden
meegeschaald.

**Volledige testsuite**: 942 tests, allemaal groen.

## Integratie-brede review: twee stille problemen (v1.1.5)

**Gevraagd**: *"Kun je nu eens de hele integratie nakijken of je nog
zaken ziet welke bij nader inzien niet goed/anders/beter kunnen?"*

Systematisch nagelopen: ongebruikte constanten, dode methodes, brede
except-clausules, achtergebleven TODO's, en de plekken waar
gelijktijdigheid iets kan verstoren. Twee echte vondsten — allebei
**stil**: ze geven geen fout en geen melding, maar doen wel iets anders
dan bedoeld.

### 1. De koelventilator kon dubbel schakelen

De accu-koeling draait op **twee** plekken: binnen de gewone tick, en
sinds v0.63.122 ook vanuit een eigen live listener. De tick loopt binnen
het bestaande slot, de listener niet.

Die twee kunnen elkaar kruisen op de `await` van de service-aanroep:
beide lezen "ventilator staat uit", beide schakelen hem aan. Resultaat:
een dubbele melding op je telefoon en een dubbele regel in de
schakelgeschiedenis — precies wat de "niet opnieuw schakelen als hij al
goed staat"-controle moest voorkomen.

De koeling heeft nu een eigen slot. Bewust een tweede slot en niet het
bestaande: dat wordt de hele tick lang vastgehouden, en de listener
daarop laten wachten zou de live-reactie die in v0.63.122 juist is
ingebouwd weer tenietdoen.

Bewezen door het slot tijdelijk te verwijderen: `assert 2 == 1` — twee
schakelingen waar er één hoort.

### 2. De configuratie werd nergens gecontroleerd

In de config-flow werd `errors` netjes aangemaakt en dan **nooit
gevuld**. Elk veld ging ongecontroleerd door.

Voor de meeste velden geeft Home Assistant zelf een keuzelijst of
entiteitkiezer, dus daar valt weinig fout te doen. Maar de
**salderingsdatum is vrije tekst** — en die stuurt sinds v1.1.0 óók de
beslislogica. Een typefout als `31-12-2026` viel stilzwijgend terug op
"salderen actief". Verdedigbaar als noodgreep, maar niet als je geen
enkel signaal krijgt dat je invoer niet is aangekomen: het gedrag na
saldering zou dan gewoon nooit aangaan.

Datum en terugleverkosten worden nu gecontroleerd, in beide flows, met
vertaalde foutmeldingen. Bij een fout komt het formulier terug **met je
ingevulde waarden**, zodat alleen het foute veld hoeft te worden
aangepast.

### Wat er goed bleek

Om ook dat te melden: geen dode methodes (232 gecontroleerd), geen
ongebruikte constanten, geen achtergebleven TODO's, en alle acht brede
except-clausules hebben een expliciete onderbouwing waarom ze breed
moeten zijn. De hoofdupdate zelf is al met een slot beschermd — de
koeling was de enige die eromheen liep.

### Eén ding dat ik bewust laat staan

`coordinator.py` is 11.559 regels. Dat is veel, en opsplitsen is
verleidelijk. Maar de beslislogica hangt sterk samen en er zit geen
duidelijke breuklijn in; een opsplitsing zou vooral verplaatsen zonder
te vereenvoudigen, met een groot risico op precies het soort
"verplaatste methode"-regressie waar `test_structural_integrity.py` ooit
voor is gebouwd. Als je dit wilt, is het een eigen project met een eigen
plan — niet iets om er even bij te doen.

### Getest

Nieuw `tests/test_review_findings.py`, 9 tests: de koeling schakelt niet
dubbel bij gelijktijdige aanroep, en werkt nog gewoon bij één aanroep;
vier soorten foute datums worden afgewezen en een geldige geaccepteerd;
leeg laten mag; terugleverkosten moeten een getal zijn en mogen niet
negatief; elke foutcode heeft een vertaling in alle drie de
taalbestanden; en het formulier komt terug met de ingevulde waarden.

De concurrency-test doet dat met een nep-service die de schakelaar
daadwerkelijk omzet en onderweg de gebeurtenislus vrijgeeft — zonder die
twee dingen zou hij de nepversie toetsen in plaats van de code.

**Volledige testsuite**: 938 tests, allemaal groen.

## Audit op dezelfde foutklasse, en betere diagnostiek (v1.1.4)

**Gevraagd**: *"Had je dit eerder kunnen afvangen als de diagnostiek
beter was, en zitten er elders meer van dit soort zaken die verstoringen
kunnen geven?"*

Twee eerlijke antwoorden: ja, en ja.

### Kon de diagnostiek dit eerder afvangen?

Ja. De export toonde de **uitkomst** — sensor-gezondheid 21%, een reeks
foutwaarden — maar nergens hoe vaak elke bronsensor eigenlijk bijwerkte.
En precies dat getal onderscheidt "de sensoren spreken elkaar tegen" van
"de sensoren meten op een ander tempo". Alleen het tweede was waar.

Ik vond het uiteindelijk door de foutwaarden met de hand te bekijken en
op te merken dat ze zich herhaalden. Dat had niet nodig moeten zijn.

Er is nu een **meetfrequentie-rapport**: per bronsensor bij hoeveel
procent van de metingen de waarde daadwerkelijk verandert. Een sensor die
bij 20% beweegt is meteen herkenbaar als traag. Dat staat in de
diagnostiek-export en als informatieve regel op het dashboard — geen
aandachtspunt, want traag is geen storing, maar wel iets om te weten.

### Zitten er meer van?

De foutklasse is scherp te omschrijven: **een tempo afleiden uit het
verschil van een niveaumeting, gedeeld door een aangenomen interval.**
Alle plekken die dat doen zijn nagelopen:

| Plek | Oordeel |
|---|---|
| Kirchhoff-balanscheck | opgelost in v1.1.3 |
| Achtertuin-uitschieterfilter | opgelost in v1.0.6 |
| Klimaat-tempo (°C/uur) | **al veilig** — meet over een anker van ~1 uur, met de reden expliciet gedocumenteerd |
| Kostprijs/besparing | **nieuwe treffer** |

De vier plekken die *vermogen × tijd = energie* rekenen zijn een andere
zaak: daar is een stilstaande meting een redelijke benadering, en ze zijn
al begrensd tegen grote hiaten. Die blijven zoals ze zijn.

### De nieuwe treffer: de financiële splitsing

De kostprijs- en besparingsboekhouding berekende het ontlaadtempo over de
tick van vijf minuten in plaats van over de werkelijke beweging van de
sensor. Stond die vier ticks stil en sprong hij daarna, dan was de
opgebouwde energie over ~25 minuten ontstaan terwijl er met vijf werd
gerekend.

Dat tempo bepaalt hoeveel van een ontlading als **export** wordt geboekt
— het deel boven het huisverbruik. Concreet, bij 500 W huisverbruik en
een accu die werkelijk 500 W ontlaadt:

| | Afgeleid tempo | Geboekt als export |
|---|---|---|
| Oud (5 min) | 2500 W | 0,167 kWh |
| Nieuw (werkelijk 25 min) | 500 W | **0,000 kWh** |

Er ging niets het net op, en toch werd er export geboekt — met
bijbehorende terugleverpremie. Na saldering zou dat de waardering van die
kWh nog verder scheeftrekken, want dan verschillen export en eigen
verbruik €0,19.

### Getest

Nieuw `tests/test_cost_basis_stale_sensor.py`, 4 tests: een stille tick
boekt niets, het interval loopt sinds de laatste beweging, échte export
wordt nog steeds geboekt, en het tijdijkpunt blijft staan zolang de sensor
stilstaat (zou dat meeschuiven, dan was de fix zinloos).

Nieuw `tests/test_sensor_cadence.py`, 6 tests: een sensor die de tick
volgt, een trage sensor wordt herkend, geen oordeel onder de drempel, een
trage sensor is informatief en geen aandachtspunt, het venster blijft
recent (anders verbergt een maandgemiddelde een recente verslechtering),
en het getal staat in de export.

**Volledige testsuite**: 929 tests, allemaal groen.

## Sensor-gezondheid stond op 21% door een trage sensor (v1.1.3)

**Gevraagd**: *"Kun je uitzoeken waarom de sensor gezondheid zo laag is?
Of komt dit door een recente herstart?"*

Geen herstart. De grafiek besloeg een hele dag met wilde uitslagen tussen
0 en 100%.

### Het patroon verried het

De foutwaarden in de diagnostiek-export herhaalden zich verdacht exact:

```
2019,1 · 2020,3 · 2020,9 · 2025,6 W      en      1111,1 · 1112,9 W
```

Ruis ziet er niet zo uit. Dat zijn bijna dezelfde getallen, keer op keer.

### Root cause

De Kirchhoff-check vergelijkt het gemeten accuvermogen met wat de
*verandering* van de beschikbare-energiesensor impliceert. Maar die
sensor werkt veel trager bij dan de tick van vijf minuten.

Stond hij stil, dan kwam het afgeleide vermogen op **0** uit terwijl de
accu werkelijk ~2000 W leverde — en dan is de "fout" precies gelijk aan
het accuvermogen. Vandaar die herhaalde 2020 W. Geen sensorstoring, maar
een verschil in meetfrequentie, dat wel als slechte meting werd geteld.

Daarna volgde het spiegelbeeld: de opgespaarde sprong kwam in één tick
binnen, goed voor de **15330 W** die ook in de reeks stond.

Zo werd een gezond systeem afgestraft voor iets dat het niet kon meten.

### Twee correcties

**De check kijkt nu alleen als er iets te kijken valt.** Beweegt de
sensor niet, dan wordt er geen meting geregistreerd. Dat is geen slechte
meting — dat is géén meting. Beweegt hij wel, dan wordt gerekend over het
werkelijke interval sinds de vorige beweging, waardoor de inhaalsprong
vanzelf klopt.

**Het gemeten vermogen wordt over datzelfde venster gemiddeld.** Het
afgeleide tempo is per definitie een gemiddelde over het interval; daar
hoort geen momentopname naast. Die vergelijking was op zichzelf al een
bron van schijnfouten zodra het interval langer werd.

Onderweg bleek er nog een dubbele startblok in de functie te staan,
waardoor de eerste vermogensmeting na elke herstart wegviel. Ook
opgeruimd.

### Getoetst

Jouw situatie nagebootst — sensor die eens per kwartier beweegt, accu op
2000 W:

| | Oude logica | Nieuw |
|---|---|---|
| Geregistreerde metingen | 12 | 4 |
| Waarvan "fout" | 8 × ~2000 W + inhaalpiek | **0** |

### Wat een échte storing nog steeds oplevert

De check verliest zijn tanden niet. Beweegt de sensor 1 kWh terwijl de
accu niets doet, dan volgt nog steeds een fout van boven de 5000 W. En
een sensor die op `unavailable` valt telt onverminderd als slechte
meting — dat is wél een gezondheidssignaal en moet onderscheiden blijven
van een sensor die gewoon traag is.

### Getest

Nieuw `tests/test_energy_balance_stale_sensor.py`, 7 tests: een
stilstaande sensor registreert niets, de inhaalsprong telt niet als
enorme fout, een echte afwijking wordt nog steeds gevangen, een kloppende
beweging is een goede meting, het vermogen wordt over het juiste venster
gemiddeld, een wegvallende sensor blijft een slechte meting, en een
urenlange stilstand wordt niet aan één tempo toegeschreven.

Twee bestaande tests legden de oude aanname vast dat een onveranderde
sensor een góéde meting is; die zijn meebewogen naar bewegingen die
kloppen met het gemeten vermogen.

**Volledige testsuite**: 919 tests, allemaal groen.

## "Korte termijn" bevroor maandenlang (v1.1.2)

**Gevraagd**: *"Maar korte termijn zou toch op relatief korte termijn een
indicatie geven?"*

Terecht — dat is precies wat "indicatief" hoort te betekenen, en het
gebeurde niet.

### De rekensom

Het klimaatmodel leert per cel: **buitentemperatuur × rolluikstand ×
airco-status**. Met buckets van 2 °C tussen −5 en 35 zijn dat 21
buitentemperaturen × 4 rolluikstanden × 3 airco-standen = **252 mogelijke
cellen**.

In de echte export na vijf dagen draaien:

| | |
|---|---|
| Cellen met enige data | 6 |
| Cellen met ≥5 metingen (de indicatief-drempel) | **1** |

En de projectie loopt 24 uur vooruit langs **telkens een ander**
buitentemperatuur-vakje. Vrijwel elk uur viel dus terug op bevriezen —
niet omdat er niets geleerd was, maar omdat het geleerde net niet bij dát
uur paste.

### De fix: terugvallen op een grovere samenvatting

De **strenge** reeks blijft exact zoals hij was. Dat is zijn
bestaansreden: "betrouwbaar" mag nooit op een samenvatting rusten, en
daar staat een test op.

De **indicatieve** reeks valt nu terug, van dichtbij naar ver:

1. exact deze cel;
2. naburige buitentemperatuur (±2 °C), zelfde rolluik- en airco-stand;
3. zelfde buitentemperatuur, elke stand;
4. alle metingen samen.

Stap 2 gaat bewust vóór stap 3: de rolluikstand bepaalt hoeveel zon er
binnenvalt en heeft daarmee meer invloed op de opwarmsnelheid dan twee
graden verschil buiten. Er is een test die die volgorde vastlegt.

De drempel van vijf metingen geldt ook voor de samenvatting — terugvallen
mag geen sluiproute worden om die te omzeilen. En is er echt nog nergens
iets gemeten, dan bevriest de reeks alsnog; er wordt niets verzonnen.

### Getoetst aan de echte data

Met jouw huidige zes cellen, voor rolluiken dicht en airco uit:

| Buitentemp | Streng | Indicatief (nieuw) |
|---|---|---|
| 12 °C | onvoldoende_data | indicatief (alle metingen) |
| 16 °C | onvoldoende_data | indicatief (naburige buitentemp) |
| 18 °C | indicatief | indicatief (deze combinatie) |
| 24 °C | onvoldoende_data | indicatief (alle metingen) |

Van één bruikbaar uur naar een volledige kolom.

### Eerlijk blijven over hoe hard het is

Er staat een extra kolom **Gebaseerd op** in de korte-termijntabel. Die
laat per uur zien of de schatting op precies deze combinatie rust of op
een grovere samenvatting. Een terugval verzwijgen zou de indicatie
geloofwaardiger laten lijken dan ze is — en dat is precies wat de
tweedeling tussen "indicatief" en "betrouwbaar" moet voorkomen.

### Getest

Nieuw `tests/test_climate_rate_fallback.py`, 10 tests: de strenge reeks
blijft ongewijzigd, een exacte cel wint, terugval naar een buur-bucket,
buren gaan vóór de bucket-brede samenvatting, terugval naar zelfde
bucket, terugval naar alles, zonder enige data wordt niets verzonnen, de
minimumdrempel geldt ook voor de samenvatting, verspreide cellen tellen
samen op tot een bruikbare indicatie, en end-to-end: de korte-termijnreeks
beweegt terwijl de betrouwbare bevroren blijft.

**Volledige testsuite**: 912 tests, allemaal groen.

## Het label noemde de verkeerde temperatuurbron (v1.1.1)

**Gerapporteerd** met screenshot: *"We hebben mijn buitentemperatuur
sensor toegevoegd maar die zie ik niet terug?"*

Je zág hem wel — de tegel toonde gewoon de verkeerde naam erbij.

### Wat er aan de hand was

De achtertuinsensor is sinds v0.63.95 de **voorkeursbron** voor de live
buitentemperatuur: een meting op je eigen erf is nauwkeuriger dan een
regionale schatting. De weerentiteit is alleen nog de terugval. Dat werkt
ook zo — geverifieerd in de configuratie-export: de sensor stond netjes
ingevuld en werd gebruikt.

Maar het dashboardlabel stond er nog hardgecodeerd als
*"Buitentemperatuur (live, KNMI/OpenWeatherMap)"*, uit de tijd vóór
v0.63.95. Het beweerde dus iets anders dan de code deed.

Dezelfde soort fout als de verouderde legenda in v1.0.5 en de
vastgeroeste klimaatmelding in v0.63.120: de code veranderde, de tekst
ernaast bleef staan.

### De fix is niet een nieuw label

Een nieuwe hardgecodeerde tekst zou over een jaar opnieuw achterlopen.
`_get_live_outdoor_temp_c` legt nu vast wélke entiteit de waarde
daadwerkelijk leverde, en de tegel toont die naam. Wisselt de bron
(bijvoorbeeld doordat de achtertuinsensor even wegvalt), dan wisselt het
label mee.

### En de verwarring erachter

Die kwam voort uit iets dat nergens uitgelegd stond: **live-meting en
uurvoorspelling komen uit verschillende bronnen, en dat is bewust.** Je
achtertuinsensor kan geen voorspelling voor over zes uur leveren, dus die
komt van KNMI/OpenWeatherMap. Het verschil tussen die twee wordt
bijgehouden als geleerde bias-correctie (bij jou +0,4 °C) en over de hele
voorspelling toegepast, zodat een structurele afwijking van de
weerentiteit wordt rechtgetrokken.

Die uitleg staat nu op het Klimaat-tabblad.

### Getest

Nieuw `tests/test_outdoor_temperature_source.py`, 8 tests: de
achtertuinsensor krijgt voorrang, terugval naar KNMI, dan naar
OpenWeatherMap, zonder bron blijft het leeg, de bron wordt **opnieuw
bepaald** bij elke uitlezing (blijft hij op de achtertuinsensor staan
nadat die wegvalt, dan toont het label opnieuw iets onwaars), de bron
staat op de sensor, het dashboard codeert geen bron meer hard, en de
uitleg maakt het onderscheid tussen live en voorspelling.

**Volledige testsuite**: 902 tests, allemaal groen.

## Beslislogica na het einde van saldering (v1.1.0)

**Gevraagd**: de aansturing laten meebewegen met het verschil dat na
saldering ontstaat — maar uitdrukkelijk: *"In acht houden dat dit pas
vanaf 01-01-2027 geldt, ik weet niet of dit zo ingebouwd kan worden dat
het systeem dan pas anders gaat denken."*

Dat kan, en het is precies zo gebouwd. Alles hangt achter
`_is_salderen_active(now)`, dezelfde poort die het financiële model uit
v0.63.117 al gebruikt. **Tot en met 31 december 2026 verandert er
letterlijk niets.**

Het sterkste bewijs daarvoor: alle 877 bestaande tests slagen ongewijzigd.
Die draaien allemaal met data in 2026, dus met saldering actief — als er
ook maar iets aan het huidige gedrag was veranderd, hadden ze dat
gemeld.

### Waarom het daarna wél moet veranderen

Onder saldering levert een teruggeleverde kWh evenveel op als een
ingekochte kost. Exporteren of zelf verbruiken is dan om het even. Daarna
niet meer: exporteren levert het lage teruglevertarief, terwijl diezelfde
kWh thuis de volle, belaste inkoopprijs bespaart. Bij €0,30 inkoop en
€0,11 teruglevering scheelt dat €0,19 per kWh — meer dan het duurste
kwartier van de dag ooit aan extra opbrengst kan geven.

### Wijziging 1: zonoverschot krijgt voorrang op verkopen

Is er tijdens een duur kwartier noemenswaardig zonoverschot, dan gaat de
accu naar `smart` om dat op te vangen in plaats van te verkopen.
Opgeslagen zon vermijdt later inkoop tegen de volle prijs; nu verkopen
levert alleen het lage tarief — ook in het duurste kwartier, want ook dat
wordt tegen dat lage tarief afgerekend.

Dezelfde overschot-bepaling als het bestaande
`_should_capture_solar_instead_of_postponing`: bij voorkeur de
bias-gecorrigeerde Solcast-verwachting, zodat een overdrijvende wolk de
beslissing niet elke paar minuten laat omslaan. Onder 150 W gebeurt er
niets — bij een paar watt zou de keuze heen en weer gaan.

### Wijziging 2: ontladen begrensd tot het eigen verbruik

Geforceerd ontladen wordt afgetopt op het huisverbruik plus een kleine
marge. Alles daarboven gaat het net op tegen het lage tarief, terwijl
diezelfde kWh in de accu later de volle inkoopprijs had kunnen vermijden.

Die marge van 150 W is er met opzet: precies op het verbruik mikken zou
door meetruis en de reactietijd van de omvormer voortdurend een beetje
export of import opleveren, en dat maakt de aansturing onrustig zonder
iets op te lossen.

Een test bracht hier een fout in mijn eerste opzet aan het licht. De
ondergrens voor "zinvol ontladen" stond op het begrensde totaal, maar dan
haalt de marge in zijn eentje die grens al — bij nul eigen verbruik zou
er alsnog 150 W puur geëxporteerd worden, precies wat deze begrenzing
moet voorkomen. De grens geldt nu op het **eigen verbruik**.

### Wat je op het dashboard ziet

Twee nieuwe beslissingsredenen, elk met een eigen uitleg:
`post_salderen_solar_capture` en `expensive_quarter_no_own_load`. Die
tweede is bewust onderscheiden van het bestaande
`expensive_quarter_soc_protected`: de uitkomst is dezelfde (niet
forceren), maar "de accu is te leeg" en "er is te weinig eigen verbruik"
zijn heel verschillende situaties, en juist dat verschil wil je kunnen
zien.

### Wat bewust NIET is aangepast

De **reserveberekening**. Na saldering wordt energie vasthouden
waardevoller, dus je zou meer willen reserveren — maar dat raakt de
energiebrug-check en de dynamische ontlaadreserve, de twee mechanismen
die eerder expliciet ongewijzigd moesten blijven. Die blijven dus zoals
ze zijn.

### Alvast uitproberen

Zet de salderingsdatum tijdelijk op een dag in het verleden. Het systeem
schakelt dan meteen om en je ziet het gedrag in de praktijk, zonder tot
januari te wachten. Terugzetten herstelt alles.

### Getest

Nieuw `tests/test_post_salderen_decision_logic.py`, 17 tests. De
belangrijkste groep gaat over inertheid: niets verandert tijdens
saldering, ook niet op 31 december, wél de dag erna, en een uitgestelde
einddatum stelt het gedrag zonder meer mee uit. Verder: overschot krijgt
voorrang, geen overschot verandert niets, een straaltje is niet genoeg,
onleesbare sensoren laten de bestaande logica met rust, ontladen wordt
afgetopt, een bescheiden ontlading blijft ongemoeid, te weinig eigen
verbruik betekent niet forceren, de drempel geldt op het eigen verbruik,
zonder verbruikssensor verandert er niets, None blijft None, beide nieuwe
redenen hebben een uitleg, en beide wijzigingen hangen aantoonbaar achter
dezelfde poort.

**Volledige testsuite**: 894 tests, allemaal groen.

## Kalman: meten of filteren hier eigenlijk iets oplevert (v1.0.7)

**Gevraagd** bij "Kalman filtering — klaar — alle 3 filters
geconvergeerd": *"Doen we hier actief iets mee? En wat zou het betekenen
als we hier actief iets mee gaan doen?"*

Antwoord op het eerste: nee, geverifieerd. `kalman_soc_filtered_kwh` en
de twee andere worden nergens in een beslispad gelezen.

### "Geconvergeerd" betekende minder dan het leek

Die status zei alleen dat de interne onzekerheid van elk filter was
uitgezakt — **niet** dat de gefilterde waarde beter is dan de ruwe. Dat
is een wezenlijk verschil met de Digital Twin, waar "klaar" inmiddels
"aantoonbaar nauwkeurig" betekent. Er was geen enkel cijfer dat de vraag
"heeft filteren hier zin?" kon beantwoorden.

### Nu wel: de divergentiemeting

Per signaal wordt bij elke meting het paar (verschil, signaalgrootte)
vastgelegd. Het oordeel volgt uit de verhouding daartussen: onder 1 % is
het verschil verwaarloosbaar, tussen 1 en 5 % klein, daarboven
noemenswaardig.

Twee ontwerpkeuzes:

**De verhouding wordt over de sommen genomen, niet per meting.** Zou je
per meting delen, dan levert één moment met bijna nul opwek een absurde
verhouding op die het gemiddelde volledig domineert. Er is een test die
dat vastlegt.

**Beide getallen worden bewaard, niet alleen het verschil.** 50 W
afwijking op 10 kW PV is verwaarloosbaar; dezelfde 50 W op 200 W
huisverbruik is fors. Een absolute drempel zou dat verschil missen.

Vijftig metingen per signaal zijn nodig voor een oordeel, en de meting
gaat mee in de toestandspersistentie uit v1.0.4 — zonder dat zou elke
herstart de telling terugzetten.

### Wat het antwoord straks betekent

Is het verschil **verwaarloosbaar**, dan is de discussie klaar: filteren
zou niets veranderen en het risico is dus per definitie niet de moeite
waard.

Is het **noemenswaardig**, dan pas is de vervolgvraag interessant — en
dan nog uitsluitend **asymmetrisch**. Voor de accu-inhoud zou dat
betekenen: alleen de laagste van ruw en gefilterd gebruiken. Een
achterlopende schatting kan dan nooit méér energie voorspiegelen dan er
is, alleen minder. Dat is precies het faalpatroon waar de
diepste-tekort-reserve en de energiebrug-marge tegen beschermen, en het
is de enige richting waarin lag onschadelijk is.

Voor het huisverbruik zou ik het sowieso niet doen: die correctie
gebruikt bewust een mediaan omdat oven- en Quooker-pieken anders de
meer-uurs reserveschatting opblazen. Dat is beproefde logica.

### Getest

Nieuw `tests/test_kalman_divergence.py`, 12 tests: het paar wordt
vastgelegd, ontbrekende waarden overgeslagen, de historie begrensd, geen
oordeel onder de drempel, een klein verschil heet verwaarloosbaar en een
groot noemenswaardig, dezelfde absolute afwijking wordt naar schaal
verschillend beoordeeld, een signaal dat op nul stond geeft geen
oordeel, de verhouding wordt over de sommen genomen, de meting blijft
adviserend (raakt nergens een commando), staat op de sensor, en overleeft
een herstart.

**Volledige testsuite**: 877 tests, allemaal groen.

## Uitschieter-filter sloeg aan op gewone meetruis (v1.0.6)

**Gerapporteerd**: *"Uitschieter genegeerd: 24.3°C wijkt te snel af van
24.7°C ... Net was het andersom, betekent dit dan dat er ca. 60 minuten
geen correcte waarde wordt geïnterpreteerd?"*

Scherp gezien: 0,4 °C is geen zonneflits.

### Root cause

Het filter toetste alleen op **tempo**: de afwijking gedeeld door de tijd
sinds de laatste geaccepteerde meting, tegen een grens van 4 °C per uur.
Die toets is op korte intervallen onbruikbaar, want de deler is dan
minuscuul:

| Interval | 0,4 °C komt neer op | Oordeel |
|---|---|---|
| 1 min | 24,0 °C/uur | geweigerd |
| 5 min | 4,8 °C/uur | geweigerd |
| 6 min | 4,0 °C/uur | net geaccepteerd |

Omgekeerd: op een tick van vijf minuten mocht de temperatuur maar
**0,33 °C** veranderen, en over één minuut zelfs maar 0,07 °C. Elke
normale sensorruis haalde die drempel.

Het gevolg was precies wat er gemeld werd: het filter sloeg heen en weer
tussen twee volstrekt normale waarden — 24,7 wordt geweigerd ten opzichte
van 24,3, daarna 24,3 ten opzichte van 24,7 — en hield ondertussen een
verouderde waarde vast.

### Was het echt 60 minuten mis?

Niet zo lang, maar wel structureel verkeerd. Bij afwijzing wordt het
tijdstip van de laatst geaccepteerde meting **niet** bijgewerkt, dus de
noemer groeit en het impliciete tempo daalt vanzelf onder de grens —
meestal binnen één of twee ticks. Het bevestigingsvenster van 45 minuten
werd dus zelden gehaald. Maar in die tussentijd stond er wél een oude
waarde, en dat herhaalde zich bij elke kleine schommeling.

### Fix: twee voorwaarden in plaats van één

Een zonneflits herken je aan een **grote sprong in korte tijd**. Alleen
"kort" toetsen is niet genoeg. Er geldt nu ook een ondergrens van
1,5 °C: ruim boven de ruis van een buitensensor, ruim onder de sprong die
direct zonlicht op de behuizing veroorzaakt. Pas als beide voorwaarden
gelden, is het een verdachte meting.

Meegenomen: de melding wordt nu gewist zodra er weer een normale waarde
binnenkomt. Voorheen bleef een opgeloste uitschieter op het dashboard
staan.

### Getest

Nieuw `tests/test_backyard_spike_filter_noise_floor.py`, 9 tests waarvan
er **6 aantoonbaar falen op v1.0.5**: het gerapporteerde geval wordt
geaccepteerd, er wordt niet meer heen en weer geslagen, zelfs een
interval van één minuut is in orde, een echte zonneflits van 8 °C wordt
nog steeds genegeerd, een aanhoudende verandering komt er na het venster
alsnog doorheen (het filter bevriest niets permanent), een grote maar
trage verandering van 8 °C over een halve dag gaat er gewoon door, de
melding verdwijnt weer, en de fix zelf — beide voorwaarden moeten in de
code staan.

**Volledige testsuite**: 865 tests, allemaal groen.

## Twee onzichtbare modules, en een onjuiste claim (v1.0.5)

**Gevraagd**: "welke modules werken daadwerkelijk mee of blijven
adviserend?"

Bij het nalopen daarvan kwamen drie dingen boven water.

### 1. Er waren tien modules, het dashboard toonde er acht

`extra_dip_marge` en `temperatuur_regressie` (toegevoegd in v0.63.91)
stonden niet in de hardcoded namenlijst van het Advies-tabblad. Ze
bestonden, werden berekend, kregen een gereedheidsstatus — en waren
nergens te zien. Op drie plekken stond bovendien "acht" waar het er tien
zijn.

### 2. De belangrijkste vondst: één module is níét adviserend

Boven de tabel stond: *"Tien modules zijn uitsluitend adviserend — geen
ervan stuurt ooit een commando of weegt mee in een accubeslissing."*

Dat klopt voor negen. Niet voor de **extra-dip-laadmarge**. Die roept
`_async_apply_manual(charge_power)` aan en zet een eigen beslissingsreden
(`grid_charging_low_solar_extra_dip`) — het is een volwaardig
laadmechanisme. Op een weinig-zon-dag buiten het goedkope blok vergelijkt
het het huidige tarief met de beste resterende prijs van vandaag,
gecorrigeerd voor het geleerde accu-rendement; is de marge groot genoeg,
dan wordt er bijgeladen.

Bij een integratie die de accu aanstuurt is dat precies het soort
onwaarheid dat er niet mag staan. De tekst zegt nu "negen van de tien",
met een aparte alinea over de uitzondering, en de module is in de tabel
gemarkeerd met ⚡ en "(stuurt aan)".

Belangrijk verschil dat er ook bij staat: de gereedheidsstatus van die
module zegt alleen hoeveel marge-geschiedenis er is opgebouwd. **Het
mechanisme zelf werkt vanaf dag één**, ongeacht wat die status toont.

### 3. De negen andere zijn geverifieerd adviserend

Niet aangenomen maar nagelopen: van elke module is het uitkomstveld
getraceerd. MPC, Monte Carlo, Digital Twin, Kalman en Weather Ensemble
worden nergens buiten hun eigen berekening en weergave gelezen. De
temperatuur-regressie gebruikt haar voorspelling uitsluitend om haar
eigen voorspelfout te meten. Kirchhoff en sluipverbruik komen alleen in
de diagnostiek-samenvatting terecht. NILM raakt geen enkele
accubeslissing.

### Getest

Zes tests erbij in `test_advisory_readiness.py`: elke gereedheidsmodule
moet een label op het dashboard hebben (en omgekeerd geen label zonder
module), de aantallen in de teksten moeten kloppen met het werkelijke
aantal, de kale telwaarde moet uitleggen waar hij vandaan komt, de
aansturende module moet aantoonbaar een commando sturen, de negen
adviserende mogen hun uitkomst nergens in een commando-pad laten
meewegen, en het dashboard moet expliciet benoemen welke module wél
aanstuurt.

Die eerste twee zijn de eigenlijke borging: een elfde module zonder
label laat de suite nu falen in plaats van stilzwijgend onzichtbaar te
blijven.

**Volledige testsuite**: 856 tests, allemaal groen.

## Geen verliezen meer na een herstart (v1.0.4)

**Gevraagd**: "kijk naar de gehele integratie welke waardes eventueel
verloren gaan na een herstart, ik wil algeheel geen verliezen".

### De inventarisatie

Alle **286 attributen** van de coordinator doorgelopen en gesplitst in
twee soorten. Het overgrote deel wordt elke tick opnieuw berekend —
projecties, live metingen, `last_*`-waarden. Die verliezen is
onschadelijk; sterker nog, ze terugzetten zou schadelijk zijn, want dan
staat er een verouderde momentopname alsof die actueel is.

Maar een deel is echt **opgebouwd**, en dat verdween tot nu toe bij elke
herstart:

| Wat | Waarom het pijn deed |
|---|---|
| `battery_module_health` | maandenlange leergeschiedenis + CUSUM-status van de accumodules |
| `mode_change_log` | het hele Geschiedenis-tabblad begon leeg |
| `actual_cost_*` / `counterfactual_cost_*` | cumulatieve besparingscijfers, ook all-time |
| `charge_pv_kwh_total` en de drie andere splitsingstellers | de bron/bestemming-boekhouding uit v0.63.117 |
| vaatwasser- en wasmachine-leergeschiedenis | cyclusduur en gebruiksuren |
| `energy_balance_error_history` | ~50 minuten blind na elke herstart |
| dag-KPI's (piekvermogen, CO2, PV, netimport) | begonnen midden op de dag opnieuw |

### Eén Store, geen tientallen losse herstelpaden

Twee eerder geleerde lessen komen hier samen. Entiteit-attributen hebben
een recorder-limiet van 16 KB (v0.63.66) — `battery_module_health` alleen
al zou daar overheen groeien. En de laadvolgorde moet vóór platform-setup
liggen (v0.63.115), anders draaien entiteiten met een eigen herstelpad
eerder en handelen ze op verkeerde aannames.

Daarom één gedeelde Store met een **expliciete lijst** van velden. Niet
"alles opslaan": dat zou precies de per-tick waarden meenemen die je juist
níét terug wilt.

De opslag gaat vertraagd (30 seconden): één tick raakt meerdere velden,
en de live listeners voor water en accu-koeling kunnen meermaals per
minuut vuren. Zonder die bundeling zou dat onnodig veel schrijfacties naar
je SD-kaart of SSD opleveren. Bij het afsluiten wordt hard weggeschreven,
want een geplande opslag die nog niet is uitgevoerd zou alsnog verloren
gaan.

### De datum-sleutels zijn niet optioneel

De dag- en maandsleutels (`_peak_power_day_key` en vijf andere) gaan
mee, en worden bij het laden terug omgezet naar echte `date`-objecten.
Zouden ze als tekst terugkomen, dan is de vergelijking met `now.date()`
altijd ongelijk en springen de dagtellers bij de eerstvolgende tick
alsnog op nul — dan was het terugzetten zinloos geweest. Daar zit een
aparte test op.

### Zodat dit niet opnieuw kan ontstaan

De inventarisatie hierboven was handwerk. Een test herhaalt hem nu bij
elke run: elk publiek veld dat op naam opgebouwde toestand is (eindigend
op `_history`, `_total`, of beginnend met `total_`) moet óf in de
Store-lijst staan, óf ergens door een RestoreEntity worden teruggezet.
Voldoet er één niet, dan faalt de suite — in plaats van dat het pas
opvalt als iemand na een herstart zijn gegevens kwijt is.

Er is één uitzondering (`was_bootstrapped_from_history`, een vlag en geen
geschiedenis), en een tweede test controleert dat die uitzondering nog
bestaat — een naam die na een hernoeming blijft staan zou stilzwijgend
een echt veld kunnen gaan afdekken.

De volledige momentopname staat ook in de diagnostiek-export, zodat je
kunt zien wat er precies bewaard wordt.

### Getest

Nieuw `tests/test_state_persistence.py`, 17 tests: maandenlange
modulegezondheid overleeft, cumulatieve financiële totalen overleven,
apparaat-leergeschiedenis overleeft, het mode-logboek overleeft, **elk**
veld in de lijst rondreist zonder verlies, datum-sleutels komen terug als
datums en niet als tekst, dagtellers worden niet alsnog gewist bij de
eerstvolgende tick, een onleesbare datum laat het opstarten niet
crashen, ontbrekende sleutels behouden hun beginwaarde, laden is
idempotent, een lege Store zet niets op nul, er wordt ook tijdens
normaal draaien opgeslagen (juist een onverwachte herstart is het geval
dat telt), de laadvolgorde ligt vóór platform-setup, afsluiten schrijft
hard weg, per-tick waarden staan bewust níét in de lijst, plus de twee
borgingstests hierboven.

**Volledige testsuite**: 848 tests, allemaal groen.

## Legenda liep achter op de code (v1.0.3)

**Gerapporteerd** met een screenshot van het Advies-tabblad.

De statustabel klopte (die leest de live waarden), maar de **legenda
eronder** is vaste dashboardtekst en beweerde nog:

> 🔵 `structureel_beschikbaar` — geldt voor de drie modules zonder
> mechanisme dat een voorspelling ooit tegen de werkelijkheid legt
> (Weather Ensemble, MPC, Digital Twin).

Sinds v1.0.1 en v1.0.2 klopt dat niet meer: die twee meten zichzelf
inmiddels wel. Precies dezelfde soort fout als de verouderde docstrings
in v0.63.117 en de vastgeroeste klimaatmelding in v0.63.120 — de code
veranderde, de uitleg ernaast niet.

### Wat er nu staat

De categorie wordt uitgelegd als "er is wél een uitkomst, maar niets om
die tegen af te zetten", met twee gevallen:

- **MPC**, per ontwerp — een theoretisch optimum dat met opzet niet
  wordt uitgevoerd;
- **Digital Twin**, maar alleen als de accucapaciteit onbekend is. Dan is
  de afwijking in kWh wel gemeten, maar valt niet te zeggen of dat veel
  of weinig is.

Dat laatste is bewust genoemd. "Geldt nog voor één module: MPC" zou
korter en mooier klinken, maar de twin kán daar wel degelijk in
belanden — en dan zou de legenda opnieuw iets beweren dat niet klopt.

Daaronder staat kort dat Weather Ensemble en Digital Twin daar tot v1.0.0
structureel bij hoorden en nu door de gewone vijf statussen klimmen, met
een aanloopperiode.

### Nu bewaakt

Vier tests koppelen de legenda aan de werkelijkheid: de oude bewering
mag er niet meer staan, MPC moet er mét reden in blijven (anders wordt
"consistentie" later een argument om er alsnog een meting bij te
verzinnen die niets meet), de twin-uitzondering moet genoemd worden, en
— als gedragsbewijs achter de tekst — Weather Ensemble moet
daadwerkelijk "klaar" kúnnen bereiken, iets wat vóór v1.0.2 onmogelijk
was.

De legendatekst wordt daarbij eerst tot één doorlopende regel
samengevouwen: de YAML-bron breekt zinnen over meerdere regels af, en een
letterlijke zoekopdracht zou anders stuklopen op een regelafbreking die
niets met de inhoud te maken heeft.

**Volledige testsuite**: 831 tests, allemaal groen.

## Weather Ensemble meet nu of hij het bij het rechte eind heeft (v1.0.2)

Van de acht adviesmodules stonden er nog twee op het vage "structureel
beschikbaar — nauwkeurigheid wordt niet bijgehouden". Voor één daarvan
kan dat wél.

### De vraag was verkeerd gesteld

Bij Weather Ensemble stond "nauwkeurigheid t.o.v. de werkelijkheid wordt
niet bijgehouden". Maar de ensemble doet helemaal geen voorspelling: hij
meldt de **actuele** bewolkingsgraad van KNMI en OpenWeatherMap. "Hoe
nauwkeurig is de voorspelling" past daar niet op.

De vraag die er wél toe doet: **zegt die melding iets dat klopt met wat
mijn eigen panelen doen?** En dat werd al berekend — de
onenigheids-signalering vergelijkt per moment het live PV-vermogen met
de Solcast-verwachting en zet dat naast de bewolking. Alleen werd die
uitkomst nooit over tijd bijgehouden.

### Wat er nu gebeurt

Elke geldige waarneming — overdag, met een zinvolle Solcast-verwachting
— wordt geclassificeerd als "eens" of "oneens". Oneens zijn precies de
twee gevallen die de bestaande signalering ook meldt: heldere lucht
terwijl de PV fors onderpresteert, of zware bewolking terwijl de PV juist
overpresteert. Alles daartussen spreekt elkaar niet tegen en telt als
eens.

Dat gebeurt bewust **op dezelfde plek en met dezelfde drempels** als die
signalering, niet in een eigen berekening ernaast — twee losse
berekeningen zouden uit de pas kunnen gaan lopen en tegenstrijdige dingen
beweren. Er is een test die vastlegt dat de meting die constanten
daadwerkelijk hergebruikt.

Boven 80 % overeenstemming heet het "klaar", tot 60 % "bijna_klaar",
daaronder "kwaliteit_te_laag". Ruim genomen: bewolking en PV-opbrengst
hangen samen maar zijn niet hetzelfde, dus perfecte overeenstemming hoort
niet verwacht te worden. Slaan de bronnen er structureel naast, dan
blijkt dat nu — in plaats van dat het verstopt blijft achter "structureel
beschikbaar".

De sensor is daarvoor een RestoreEntity geworden. De bewolkingsgraad zelf
is een momentopname, maar er zijn twintig waarnemingen **bij daglicht**
nodig voor een oordeel, en die komen alleen binnen als de zon schijnt.
Zonder herstel zou elke herstart die telling terugzetten.

### En MPC blijft staan zoals het staat

Dat is nu de enige module zonder nauwkeurigheidsmeting, en dat blijft zo.
Het MPC-plan is een **theoretisch optimum dat met opzet niet wordt
uitgevoerd** — er is geen werkelijkheid om het tegen af te zetten. Er
staat een test op die tekst, zodat "consistentie" later geen reden wordt
om er alsnog een meting bij te verzinnen die niets meet.

### Getest

Nieuw `tests/test_weather_ensemble_agreement.py`, 13 tests: alle vier de
combinaties van bewolking en opbrengst, het middengebied dat elkaar niet
tegenspreekt, de begrensde historie, geen oordeel onder de drempel, de
drie oordeelsniveaus, de inbedding in de adviesmodule, het hergebruik van
de bestaande drempels, en het herstel over een herstart heen.

**Volledige testsuite**: 827 tests, allemaal groen.

## Digital Twin meet nu zijn eigen nauwkeurigheid (v1.0.1)

**Gerapporteerd**: de adviesmodule meldde *"Digital Twin — structureel
beschikbaar — Simuleert over 34.8 uur, nauwkeurigheid t.o.v. het
daadwerkelijke resultaat wordt niet bijgehouden."*

Die tekst was eerlijk, maar onnodig: de twin voorspelt een **SoC**, en
die is later gewoon na te meten.

### Hoe het werkt

Dezelfde "leg een voorspelling vast, controleer 'm later"-techniek als de
zonvoorspelling-tracker. Elk uur wordt vastgelegd welke accu-inhoud de
twin **zes uur vooruit** verwacht. Zodra dat moment is bereikt, wordt de
werkelijke meting ernaast gelegd en de afwijking bewaard.

Vier ontwerpkeuzes die er echt toe doen:

- **Niet elke tick vastleggen.** Dat zou binnen een dag honderden sterk
  overlappende voorspellingen opleveren die vrijwel hetzelfde zeggen —
  het gemiddelde zou dan vooral meten hoe vaak er gemeten is.
- **Te late voorspellingen weggooien.** Komt een voorspelling door een
  herstart pas driekwartier te laat aan de beurt, dan zegt ze niets meer
  over het moment waarvoor ze bedoeld was. Alsnog afrekenen zou een fout
  meten die niets met de modelkwaliteit te maken heeft.
- **Geen oordeel onder acht vergelijkingen.** Zelfde principe als de
  sensor-gezondheidsdrempel uit v0.63.121.
- **De fout wordt afgezet tegen de bruikbare accucapaciteit**, niet tegen
  een vast aantal kWh. Een afwijking van 0,5 kWh is prima bij een accu
  van 10 kWh en te veel bij een van 2 — een vaste drempel zou dat
  verschil missen. Er is een test die precies dat vastlegt.

Het oordeel wordt "klaar" onder 10 % afwijking, "bijna_klaar" tot 20 %,
en daarboven "kwaliteit_te_laag". De adviesmodule toont dat nu in plaats
van het vage "structureel beschikbaar", mét de simulatieduur ernaast.

### Persistentie is hier geen luxe

Er zijn acht vergelijkingen nodig, per uur vastgelegd met een horizon van
zes uur. Zonder herstel zou elke herstart de meting op nul zetten en zou
het oordeel bij frequent herstarten **nooit** verschijnen — precies de
fout die de NILM-persistentie in v0.63.115 zo lang verborgen hield. De
nieuwe sensor is daarom een RestoreEntity die zowel de afgeronde
vergelijkingen als de openstaande voorspellingen terugzet.

### Waarom MPC dit bewust niet krijgt

Bij MPC staat dezelfde zin, en die blijft staan. Het MPC-plan is een
**theoretisch optimum dat met opzet niet wordt uitgevoerd** — er valt dus
niets tegen af te rekenen. Er is een test die die tekst vastlegt, zodat
"consistentie" later geen reden wordt om er alsnog een meting bij te
verzinnen die niets meet.

### Getest

Nieuw `tests/test_digital_twin_accuracy.py`, 17 tests: vastleggen op de
juiste horizon, niet opnieuw binnen het interval, wél erna, niets zonder
tijdlijn, niets bij een te korte tijdlijn, afrekenen tegen de
werkelijkheid, niet te vroeg afrekenen, een veel te late voorspelling
weggooien, geen nepfout bij een onleesbare sensor, geen oordeel onder de
drempel, een kleine fout als "klaar" en een grote als
"kwaliteit_te_laag", dat dezelfde fout bij een kleine accu wél en bij een
grote níet doorslaat, eerlijk zijn zonder bekende capaciteit, de
inbedding in de adviesmodule, het herstel over een herstart heen, en dat
MPC bewust ongemoeid blijft.

**Volledige testsuite**: 814 tests, allemaal groen.

## Versienummering en automatische releases (v1.0.0)

**Gerapporteerd**: "Nu zie ik met de update telkens een code als
48eb9da. Ik zou daar vanaf nu graag V.1.00 of iets dergelijks zien welke
daarna automatisch ophoogt."

### Waarom die hash er stond

`48eb9da` is een Git-commit-hash. HACS toont die als **terugval** zodra
een repository geen GitHub-releases heeft — er viel simpelweg geen
versienummer te tonen. Het was dus geen verkeerde instelling in de
integratie of in HACS.

Deze repository had wel drie workflows (HACS-validatie, hassfest, tests)
maar geen enkele die een release aanmaakte, terwijl het versienummer in
`manifest.json` netjes bij elke wijziging werd opgehoogd. Dat nummer
kwam alleen nooit in GitHub terecht.

### De oplossing: releases uit manifest.json

Nieuwe workflow `.github/workflows/release.yml`. Bij elke push naar
`main`:

1. leest het versienummer uit `manifest.json`;
2. stopt als die tag al bestaat — dus geen dubbele releases bij een push
   die de versie niet verandert;
3. draait de **volledige testsuite**, want een release zonder groene
   tests zou de hele borging van dit project omzeilen;
4. haalt de bijbehorende sectie uit `CHANGELOG.md` als release-notitie;
5. maakt tag `v<versie>` plus GitHub-release aan.

`manifest.json` blijft daarmee de enige bron van waarheid — er komt geen
tweede nummering naast die uit de pas kan lopen. Elke versieverhoging
wordt vanzelf een release die HACS toont, zonder handwerk.

### Nummering: 1.0.0

Van `0.63.132` naar `1.0.0`. De opbouw blijft `major.minor.patch` en
niet iets als "V.1.00": HACS sorteert releases op versienummer, en een
afwijkend formaat maakt "welke is nieuwer" onbetrouwbaar. Een test
bewaakt dat het versienummer precies drie cijferdelen houdt.

Vanaf hier hoogt de patch bij elke wijziging op (1.0.1, 1.0.2, ...);
`minor` bij een nieuwe functie, `major` bij iets dat je installatie
raakt.

### Eenmalig in GitHub

De workflow draait pas ná het pushen van deze versie. Verschijnt er geen
release, kijk dan onder **Settings → Actions → General** of workflows
schrijfrechten hebben ("Read and write permissions") — zonder dat mag de
actie geen tag aanmaken.

Zodra de eerste release er staat, schakelt HACS over van commit-modus
naar release-modus. Mogelijk moet je de integratie in HACS één keer
opnieuw downloaden voordat hij dat oppikt.

**Volledige testsuite**: 797 tests, allemaal groen.

## Diagnostiek-review: dagteller en een verkeerde waterconclusie (v0.63.132)

**Gevraagd**: "Algehele controle aub" bij een verse export van v0.63.130.

### Eerst wat er goed staat

Status **nominaal**, geen enkel aandachtspunt, geen fouten. Alle vijf de
leercheks op OK na vijf dagen. De accu-modulebewaking draait en meet:
drie modules, celdelta's van 0,03 / 0,01 / 0,00 V, temperaturen 30/29/28
°C, SoC 62/63/61 % — netjes in balans, geen waarschuwingen, de
SoC-bucketing vult zich. De koeling werkt (30,0 °C accu, 23,2 °C buiten,
delta 6,8 °C, "blijft koelen"). De bron/bestemming-splitsing van
v0.63.117 boekt inmiddels echt: 0,086 kWh uit PV geladen, €0,0128
gederfde teruglevering. Sensor-gezondheid staat op leeg omdat er pas één
meting is sinds de herstart — de drempel uit v0.63.121 doet precies zijn
werk.

Twee dingen klopten niet.

### 1. De dagteller overleefde de herstart niet

In de export stonden **zes watermomenten van vandaag** in de
geschiedenis, terwijl `water_sessions_today_count` op **0** stond.

`water_sessions_today_l/_count` zijn gewone geheugenvelden en worden bij
elke herstart nul, terwijl `water_session_history` wél wordt hersteld.
De diagnostiek-check viel daardoor terug op de optelling over de
weergavelijst van 20 momenten — precies het gedrag dat die teller in
v0.63.119 moest vervangen.

Opgelost door de teller bij het herstellen van de geschiedenis opnieuw
op te bouwen. Geen extra opslag nodig: de gegevens waren er al.

### 2. De conclusie in de watermelding was omgekeerd

De melding zei: *"er zijn wél 6 gebruiksmomenten herkend, dus de
detectie werkt — het volume per moment valt te laag uit."*

Dat is aantoonbaar onjuist. Diezelfde export bevat het bewijs:

| Moment | Geïntegreerd debiet | Meterstand |
|---|---|---|
| 12:08 | 12,2 L | 12,0 L |
| 12:57 | 0,5 L | 1,0 L |

De volumebepaling klopt dus juist uitstekend. Het tekort zit in **gemiste
momenten**, niet in te lage volumes.

De oorzaak was de heuristiek uit v0.63.121: die trok haar conclusie uit
"veel of weinig momenten", met een drempel op vijf. Bij zes momenten
sloeg hij om naar de verkeerde verklaring. Die drempel had niets met de
werkelijke oorzaak te maken — het was een proxy waar echt bewijs
voorhanden is.

De conclusie rust nu op dat bewijs: het geïntegreerde debiet wordt
vergeleken met de meterstand over de momenten waar beide een waarde
gaven. Komen ze overeen (binnen 25 %, ruim genomen omdat de meterstand
zelf ongeveer een liter resolutie heeft), dan is de volumebepaling
bevestigd en worden er momenten gemist. Wijken ze af, dan is de
volumebepaling de zwakke schakel. Is er nog geen enkel moment met beide
waarden, dan zegt de melding dat eerlijk in plaats van te gokken.

Tegen de echte exportdata gedraaid levert dat nu op: *"de 6 herkende
moment(en) kloppen qua volume — er worden gebruiksmomenten gemist, de
debietsensor pikt waarschijnlijk niet elke stoot op."* Dat is de juiste
diagnose.

### Getest

Vier nieuwe tests in `test_water_session_volume_accounting.py` (herbouw
uit herstelde historie, andere dagen worden genegeerd, een lege dag zet
de dagsleutel niet, en de sensor roept de herbouw ook echt aan) en drie
in `test_diagnostics_review_improvements.py` (overeenkomende volumes →
gemiste momenten, afwijkende volumes → volumebepaling, geen
vergelijkingsmateriaal → geen conclusie). Twee bestaande tests die de
oude telling-drempel vastlegden zijn meebewogen.

**Volledige testsuite**: 791 tests, allemaal groen.

## Achtergrondtekening bleef in de cache hangen (v0.63.131)

**Gerapporteerd**, met screenshot waarop de nieuwe waarden ("laden
390 W") wél zichtbaar waren maar de oude, enkelzijdige pijlen nog stonden:
"Afbeelding (richtingen van de stromen) nog niet geupdate?"

### Root cause

Een picture-elements-kaart bestaat uit twee heel verschillende soorten
inhoud, en die verversen niet op dezelfde manier:

- de **entiteitswaarden** komen live over de websocket binnen — altijd
  actueel;
- de **achtergrond** is een statisch bestand dat via `/local/` wordt
  geserveerd onder een **vaste bestandsnaam**.

Browsers en de Home Assistant-app cachen dat bestand. De integratie
schrijft bij elke start netjes de nieuwe SVG naar `www/`, maar de client
vraagt hem niet opnieuw op — de naam is immers ongewijzigd. Resultaat:
nieuwe cijfers op een oude tekening, precies wat op de screenshot te zien
was. Niets stukgaan, geen foutmelding, alleen een stille inconsistentie.

Dat is geen incident maar een structureel probleem: het zou zich bij
élke volgende wijziging aan de tekening opnieuw voordoen.

### Fix

De kaart verwijst nu naar
`/local/energy_management_system_overview.svg?v=0.63.131`. De
versiesleutel maakt de URL uniek per release en dwingt zo een verse
ophaal af.

Die sleutel handmatig bijhouden zou natuurlijk precies zo'n ding zijn dat
je één keer vergeet. Er is daarom een test die hem **hard koppelt aan
`manifest.json`**: wordt de versie opgehoogd zonder de sleutel bij te
werken, dan faalt de testsuite voordat er iets uitgaat. Dat is
geverifieerd door de versie tijdelijk op 0.63.999 te zetten — de test
sloeg aan.

### Eenmalig nog even zelf verversen

Deze fix werkt vanaf de volgende keer. De nu al gecachte afbeelding
verdwijnt niet vanzelf uit je browser: doe één keer een harde vernieuwing
(Ctrl+Shift+R, of in de mobiele app de app-cache wissen). Daarna regelt
de versiesleutel het.

**Volledige testsuite**: 790 tests, allemaal groen.

## Grootste verbruiker altijd zichtbaar op de visual (v0.63.130)

**Gerapporteerd**: "In de visual is nu de zwaarste bron nog niet
zichtbaar, mijn inziens is er altijd een zwaarste bron ook al zou die
maar 10 W zijn."

Klopt, en de oorzaak was een verkeerd gekozen bron van mijn kant. Het vak
toonde `heavy_load_source`, en dat is een **beslislogica-signaal**: het
geeft alleen iets terug als een specifiek zwaar apparaat aantoonbaar
draait (vaatwasser, wasmachine, Quooker, airco, oven, kookplaat). Het
bestaat om de mediaan-voorzichtigheid van de verbruikscorrectie over te
slaan als er geen twijfel meer is, en hoort dus juist mééstal leeg te
zijn. Het label beloofde iets anders dan het attribuut betekende.

**Nu een eigen berekening**: van alle bevestigde NILM-apparaten — dat
zijn precies de apparaten met een eigen vermogensmeting — degene die op
dit moment het meeste trekt, met de waarde erbij: "Televisie (120 W)".

Twee dingen worden bewust overgeslagen. **Negatieve waarden**, want onder
de bevestigde apparaten zitten ook productie-entiteiten (een
omvormerkanaal dat −4 W teruglevert is geen verbruiker). En **precies
0 W**, want "grootste verbruiker: 0 W" is geen informatie. Zijn er
helemaal geen gemeten apparaten actief, dan valt hij terug op het
zwaar-apparaat-signaal, en anders staat er eerlijk "geen gemeten apparaat
actief" — nooit meer een leeg vak.

**Bewuste beperking**: dit ziet alleen apparaten die zelf hun vermogen
meten. Is de werkelijk grootste verbruiker een apparaat zonder meting,
dan staat die er niet bij. Het is de grootste *bekende* verbruiker, en
het label op de tekening is daarom aangepast van "ZWAARSTE BRON" naar
"GROOTSTE VERBRUIKER" — tekening en inhoud moeten hetzelfde zeggen.

**Getest**: nieuw `tests/test_largest_known_consumer.py`, 12 tests: de
hoogste wint, een kleine verbruiker van 10 W telt gewoon mee (de kern van
de melding), productie-entiteiten en 0 W worden overgeslagen, onleesbare
sensoren ook, de terugval op het zwaar-apparaat-signaal, dat een concreet
gemeten apparaat wint van dat categorielabel, dat er nóóit None uit komt
(een leeg vak was precies de klacht), en twee borgingen dat kaart en
tekening het nieuwe attribuut respectievelijk label gebruiken.

**Volledige testsuite**: 789 tests, allemaal groen.

## Waterdekking telt niet meer mee voor de systeemstatus (v0.63.129)

**Gevraagd**: "En dit mag geen aandachtspunt zijn, ik ben me er van
bewust" — over de melding dat het waterdagtotaal hoger is dan wat de
herkende gebruiksmomenten verklaren.

Terecht, en dezelfde redenering als bij de NILM-duplicaten in v0.63.116:
dit is een **observatie over de dekking van de waterdetectie**, niet iets
dat mis is met de integratie of met de accu-aansturing. Het kan bovendien
dagen aanhouden zonder dat er iets te doen valt — en zolang het meetelde,
bleef de systeemstatus permanent op "Aandacht gewenst" staan en verloor
die precies zijn signaalwaarde.

De melding verhuist naar `informatief`: onverkort zichtbaar, inclusief de
richtinggevende duiding uit v0.63.121, maar de status blijft "OK".
Onderdrukken was hier nadrukkelijk niet de bedoeling — als de dekking
ooit ineens veel slechter wordt, wil je dat nog steeds kunnen zien.

Daarmee zijn er nu twee bewoners van de informatieve categorie:
NILM-duplicaten en waterdekking. Beide delen hetzelfde kenmerk — een
permanente, bewust geaccepteerde toestand waar geen actie tegenover
staat.

**Getest**: twee extra tests in
`test_diagnostic_informational_category.py` (de status blijft OK met
alleen deze melding; de melding blijft volledig bestaan inclusief beide
getallen). Vier bestaande tests die de oude categorie vastlegden, zijn
meebewogen.

**Volledige testsuite**: 777 tests, allemaal groen.

## Ook de netpijl wijst beide kanten op (v0.63.128)

**Gerapporteerd**: "Dit geldt ook voor 'NET' (de pijl suggereert één
richting terwijl de accu beide kanten op gaat)."

Klopt, en het was in de screenshot zelfs zichtbaar: de netstroom stond op
**−826 W**, dus er werd op dat moment teruggeleverd terwijl de pijl naar
het huis wees. Het net is net zo goed tweerichtingsverkeer als de accu —
importeren én terugleveren. Nu een dubbele pijlpunt.

**De zonnepijl blijft bewust enkelzijdig.** De zon produceert alleen; een
dubbele pijl zou daar juist onjuist zijn. Er staat nu een test op die dat
onderscheid vastlegt, zodat "consistentie" later geen reden wordt om er
alsnog een dubbele pijl van te maken.

Bij het maken van de nieuwe pijlpunten zijn die van het net iets kleiner
gezet (14 in plaats van 18 eenheden): de opening tussen de vakken Huis en
Net is 40 pixels tegen 60 bij de accu, dus twee punten op ware grootte
zouden elkaar daar weer raken.

Extra borging: een test controleert dat **elke** marker in de tekening
`markerUnits="userSpaceOnUse"` heeft. Zonder dat schalen pijlpunten mee
met de lijndikte — precies de valkuil uit v0.63.127 die een dubbele pijl
in een zandloper veranderde.

**Volledige testsuite**: 775 tests, allemaal groen.

## Accuvermogen zichtbaar + leesbare tijdnotatie (v0.63.127)

**Gerapporteerd** bij de nieuwe grafische kaart: "Vermogen naar/van accu
is niet inzichtelijk en de datum notatie is niet duidelijk."

Beide zijn bij de **bron** opgelost, niet op het dashboard. Een
`state-label` op een picture-elements-kaart toont de ruwe attribuutwaarde
en heeft geen sjabloonmogelijkheid — er is dus geen dashboardtruc die dit
kan oplossen.

### Accuvermogen met richting

De pijl tussen huis en accu had geen waarde. Nieuw attribuut
`accu_vermogen_weergave` dat niet alleen het getal maar ook de
**richting** geeft: "laden 597 W", "ontladen 800 W" of "rust".

Een kaal getal helpt hier niet: het teken alleen zegt niets zonder te
weten welke conventie de sensor aanhoudt, en op een schematische kaart is
juist "laden of ontladen" wat je wilt weten. De waarde komt uit
`_read_corrected_battery_power` — dezelfde bron als de beslislogica,
inclusief de teken-omkering, zodat kaart en besluit nooit iets anders
kunnen beweren. Onder 25 W heet het "rust": een stilstaande accu
schommelt altijd een paar watt, en "laden 3 W" suggereert een richting
die er niet is.

### Tijdnotatie

`2026-08-06T12:48:28.434441+02:00` werd `do 6 aug 12:48`, via het nieuwe
attribuut `last_successful_update_short` (op zowel de statussensor als de
uitlegsensor). De ruwe ISO-waarde blijft ook gewoon staan voor wie ermee
wil rekenen.

### En de pijl zelf

De enkele pijl omlaag suggereerde permanent ontladen. Nu een dubbele
pijlpunt, want de accu gaat beide kanten op; de richting staat in het
label ernaast.

Daarbij kwam een echte SVG-valkuil boven water: markers schalen
standaard mee met de **lijndikte**, dus bij `stroke-width: 6` werd een
pijlpunt van 10 eenheden er één van 60. Bij de dubbele pijl raakten de
twee punten elkaar en werd het een zandloper. Opgelost met
`markerUnits="userSpaceOnUse"`, wat de maten absoluut maakt — ook de
twee horizontale pijlen zijn daarmee netter geworden.

### Getest

Nieuw `tests/test_display_formatting.py`, 12 tests: de ISO-tijdstempel
wordt leesbaar, microseconden en tijdzone-offset verdwijnen, UTC-invoer
wordt lokaal getoond, None blijft None, en een rondgang van 370 dagen om
te bewijzen dat geen enkele maand of weekdag een IndexError geeft. Voor
het vermogen: laden, ontladen, rust net onder de drempel, richting net
erboven, ontbrekende sensor, en dat de teken-omkering dezelfde is als in
de beslislogica.

Plus drie tests in `test_overview_picture_card.py`: het vermogen staat op
de kaart, de kaart gebruikt het geformatteerde tijdattribuut (en niet
meer het ruwe), en de accupijl wijst beide kanten op.

**Volledige testsuite**: 772 tests, allemaal groen.

## Grafische kaart naar een eigen tabblad "Visueel" (v0.63.126)

**Gevraagd**: "Ik wil een extra tabblad voor hetgeen je net gemaakt
hebt."

De picture-elements-kaart stond boven aan Overzicht, waar hij de
werkkaarten naar beneden duwde. Nu een eigen tabblad **Visueel**, direct
na Overzicht.

Uitgevoerd als **panel-view** (`panel: true`) in plaats van een gewone
kaartenlijst. Dat is precies waar een panel-view voor bedoeld is: de ene
kaart vult de volle breedte en hoogte van het scherm, wat de tekening op
een groot scherm pas echt tot zijn recht laat komen. In een gewone view
zou hij in een kolom blijven hangen. Een panel-view mag exact één kaart
bevatten — een test borgt dat.

`grid_options` is van de kaart verwijderd: die hoort bij een
sections-view en doet in een panel-view niets, dus laten staan zou alleen
verwarren.

Overzicht is verder onaangeroerd: alle tabellen, tegels en schakelaars
staan er nog precies zo. De grafische kaart is een toevoeging, geen
vervanging — en daar zit nu ook een test op, die controleert dat de
picture-elements-kaart níet meer op Overzicht staat én dat de drie
kernsecties er nog zijn.

**Volgorde**: het tabblad staat na Overzicht, zodat Overzicht de
landingspagina blijft. Wil je Visueel als eerste (bijvoorbeeld voor een
wandpaneel), dan is dat één regel verplaatsen — zeg het maar.

**Volledige testsuite**: 758 tests, allemaal groen.

## Grafische overzichtskaart: entiteiten in een afbeelding (v0.63.125)

**Gevraagd**: "een grote afbeelding waarin alle gegevens zijn
opgenomen... 1 grote card met alle gegevens in verwerkt per
subcategorie", eerst voor tabblad 1.

Gebouwd als **`picture-elements`** — een kernkaart van Home Assistant,
dus geen HACS-afhankelijkheid erbij. Een SVG-achtergrond met daarop
absoluut gepositioneerde `state-label`- en `state-icon`-elementen.

### Indeling: zes zones, als energieschema

De tekening is geen decoratie maar een schema: bovenin de drie bronnen
en verbruikers met stroompijlen ertussen, onderin de logica en bewaking.

| Zone | Wat erin staat |
|---|---|
| **Zon** | opwek nu, bewolkingsgraad, resterende zon vandaag |
| **Huis** | werkelijk huisverbruik, zwaarste verbruiker |
| **Net** | netstroom P1, prijs nu, drempel duur |
| **Thuisaccu** | lading, beschikbare energie, geleerd rendement, koeling |
| **Besluit** | verwachte modus, dure kwartieren, force manual, vakantiemodus |
| **Bewaking** | sensor-gezondheid, sluipverbruik, accumodules, laatste update |

Force manual en vakantiemodus zijn direct schakelbaar vanaf de kaart;
alle andere elementen klikken door naar de details.

### De achtergrond wordt automatisch klaargezet

Home Assistant serveert alleen `<config>/www/` als statische map (via
`/local/`). De integratie kopieert de SVG daar bij elke start naartoe,
net zoals ze het dashboard zelf al kopieerde — je hoeft dus niets
handmatig te plaatsen.

**Bestond `www/` nog niet, dan is één extra herstart nodig**: Home
Assistant registreert die map alleen bij het opstarten, dus de eerste
keer wordt de map wel aangemaakt maar nog niet geserveerd. Zie je een
gebroken afbeelding met de waarden er wél overheen, herstart dan
nogmaals.

### De valkuil, en hoe die bewaakt wordt

De posities zijn **percentages van de afbeelding**. Verandert de SVG
zonder dat de percentages meebewegen, dan staan de waarden ernaast
zonder dat er iets stukgaat — precies het soort fout dat pas opvalt als
je ernaar kijkt. De SVG documenteert daarom elk ankerpunt in commentaar
(`anker soc: x 830..1000, y 596..636`), en een test controleert dat bij
**elk** anker ook echt een element in de buurt staat. Lopen tekening en
kaart uiteen, dan faalt de testsuite.

### Getest

Nieuw `tests/test_overview_picture_card.py`, 13 tests: de achtergrond
wordt meegeleverd en is geldige XML, repo-kopie en meegeleverde kopie
zijn identiek, de kaart wijst naar `/local/`, de integratie kopieert
naar `www/` via een executor (blokkerende bestandsoperatie), elk element
valt binnen 0-100%, alle zes de zones bestaan én zijn gevuld, elk
gedocumenteerd anker heeft een element in de buurt, elk label heeft een
expliciete kleur en schaduw (het HA-thema is niet gegarandeerd leesbaar
op een eigen achtergrond), labels breken niet af, alles is klikbaar,
geen twee elementen op dezelfde plek, en — belangrijk — de bestaande
kaarten staan er nog: de grafische kaart komt **erbij**, niet in plaats
van. De tabellen en schakelaars blijven nodig voor het echte werk.

**Volledige testsuite**: 756 tests, allemaal groen.

## Accu-koeling verplaatst naar de live-cijfers (v0.63.124)

**Gevraagd**: de accu-koeling een andere plek geven op het dashboard,
als tegel binnen "Accu, rendement & live cijfers".

Als eigen sectie zette de masonry-layout de koeling linksboven, waar hij
een volle kolombreedte innam voor één regel informatie — en daarmee de
kerncijfers naar rechts duwde. Nu een halve-breedte tegel (6 kolommen,
net als de tegels ernaast) achter "Huidige prijs", met de
accutemperatuur als hoofdwaarde en de koelstatus eronder. De volledige
toelichting, de reden en de laatste tien schakelmomenten blijven
bereikbaar via de tegel zelf.

Een test borgt de plaatsing: "Accu-koeling" mag geen eigen sectiekop
meer zijn, en er moet precies één koeltegel van 6 kolommen in de
live-cijfers-sectie staan.

**Volledige testsuite**: 743 tests, allemaal groen.

## Accu-modulegezondheid + tabbladnamen zichtbaar (v0.63.123)

**Gevraagd**: "Zit hier nog relevante info tussen om de gezondheid van
de accus te monitoren?" bij een screenshot met per module hoogste/laagste
celspanning, hoogste celtemperatuur, SoC, stroom, vermogen en
pakspanning. En: "Zou je bij de tabbladen ook de namen willen laten zien
zodat het helder blijft en niet alleen icoontjes zichtbaar zijn?"

### Tabbladnamen

Home Assistant toont **uitsluitend het icoon** zodra een view er een
heeft — de titel verdwijnt dan volledig uit de tabbalk. De tien
view-iconen zijn daarom verwijderd; alle tabbladen tonen nu hun naam.
Een test borgt dat: elke view moet een titel hebben en mag géén icoon
hebben.

### Wat er in die metingen zat

Veel, en van een heel ander kaliber dan wat er al was.
`battery_estimated_capacity_percent` is een **lineaire schatting** uit
cyclustelling — geen meting. Dit zijn wél metingen.

Het waardevolst is het **celspanningsverschil** (hoogste min laagste)
per module: bij LFP dé standaardindicator voor balans en veroudering.
Loopt dat verschil structureel op, dan blijft er een cel achter, en dat
is doorgaans het eerste signaal — ruim voordat je het aan de capaciteit
merkt.

### Het lastige probleem, en hoe het is opgelost

Bij LFP is dat celspanningsverschil **sterk SoC-afhankelijk**: vlak in
het midden, steil aan de uiteinden. Een absolute waarde is daardoor niet
met zichzelf over de tijd te vergelijken — dezelfde module geeft bij 95%
een heel andere delta dan bij 50%, zonder dat er iets mis is.

De oplossing is een **differentiële vergelijking**: elke module tegen het
gemiddelde van de **andere** modules op hetzelfde moment. Alle modules
draaien onder identieke omstandigheden — zelfde SoC, zelfde
omgevingstemperatuur, zelfde belasting — dus alles wat ze gemeenschappelijk
hebben valt weg, en wat overblijft is een eigenschap van díe module. De
SoC-afhankelijkheid verdwijnt daarmee volledig uit de vergelijking.

Bewust tegen de *andere* modules en niet tegen het gemiddelde inclusief
zichzelf: bij drie modules trekt een uitschieter het gemiddelde waar hij
zelf in zit met zich mee, waardoor zijn eigen afwijking met factor
(n−1)/n wordt onderschat. Uitsluiten van zichzelf maakt de maat scherp
en onafhankelijk van het aantal modules. Er is een test die precies dat
verschil vastlegt (+14,0 °C in plaats van +9,3 °C).

### Wat er bewaakt wordt

Per module, per dag de **mediaan** (niet het gemiddelde — één laadpiek
of een moment met zon op één module mag een dagwaarde niet verslepen)
van drie afwijkingen: celspanningsverschil, celtemperatuur en SoC.
Daarop draait een **CUSUM-drifttest**, hetzelfde mechanisme als bij de
NILM-apparaatbewaking, inclusief het zelfherstel uit v0.63.100: keert
een module vijf dagen op rij terug naar normaal, dan wist de detectie
zichzelf. Dat is precies gebouwd voor langzame, aanhoudende drift.

Daarnaast directe, absolute controles die niet op een trend van weken
hoeven te wachten: celspanningsverschil boven 0,10 V (aandacht) of
0,20 V (fors uit balans), celtemperatuur boven 40 °C, onderlinge
temperatuurspreiding boven 5 °C ("wijst op een module met hogere
inwendige weerstand") en SoC-spreiding boven 10 %. Die drempels zijn
**heuristiek, geen fabrieksspecificatie** — dat staat ook zo in
`const.py`.

De absolute celdelta wordt per SoC-bucket van 10 % bewaard, puur ter
referentie: zo is wél te zien hoe de delta zich bij 90 % verhoudt tot
die bij 40 %, zonder dat die twee ooit met elkaar vergeleken worden.

### Configuratie: vijf lijsten in plaats van twaalf velden

Vijf optionele lijstvelden (hoogste celspanning, laagste celspanning,
celtemperatuur, SoC, vermogen). **De volgorde bepaalt het
modulenummer** — de eerste entiteit in elke lijst is module 1. Dat
schaalt naar elk aantal modules zonder dat de configuratie bij een
uitbreiding moet worden aangepast. Lijsten mogen verschillend lang zijn
(bijvoorbeeld wel celspanningen, geen vermogen per module), en één
weggevallen sensor laat de module niet uit de weergave verdwijnen.

### Zichtbaarheid

Nieuw tabblad **Accumodules** met vier tabellen: live waarden per module,
de afwijking ten opzichte van de andere modules, de onderlinge
spreiding, en de bevindingen. Plus een sensor
**Accu-modulegezondheid** waarvan de waarde het aantal modules is dat
aandacht verdient — een "0" zegt dan meteen dat alles in orde is. Alles
staat ook in de diagnostiek-export.

### Getest

Nieuw `tests/test_battery_module_health.py`, 27 tests: uitlezen en
afleiden, ontbrekende sensoren, ongelijke lijstlengtes, de differentiële
berekening inclusief het uitsluiten van de module zelf, dat de
SoC-afhankelijkheid daadwerkelijk wegvalt, alle absolute drempels
(inclusief net-onder/net-boven), de spreidingsmeldingen, dagafronding
met mediaan, het verwerpen van een dag met te weinig metingen, drift die
wordt gedetecteerd, stabiele modules die nooit driften, drift die
zichzelf herstelt, SoC-bucketing, de sensorweergave, en de twee
dashboardborgingen.

Op de screenshot-situatie zelf (0,01 / 0,01 / 0,00 V, 28 / 27 / 26 °C,
49 / 48 / 47 %) komt er geen enkele melding uit — er is een aparte test
die dat vastlegt.

**Volledige testsuite**: 742 tests, allemaal groen.

## Accu-koeling geïntegreerd (v0.63.122)

**Gevraagd**: "Integreren zodat ik dit niet meer als losse
automatisering hoef te doen, het heeft mijn inziens toch met de accu te
maken."

Terechte heroverweging. De koelventilator stond sinds het begin bewust
**buiten** deze integratie om de complexiteit te beperken, maar het is
wel de enige aansturing in huis die direct met de accu samenhangt — en
hij gebruikt gegevens (accuvermogen, buitentemperatuur) die hier toch al
binnenkomen. De automatisering "Accu: Temperatuurbeheer Thuisaccu
(Buiten) - PRO v9" is nu één-op-één overgenomen.

### Drempels ongewijzigd

Alle zes de drempels zijn **exact** die van de automatisering, als
constanten in `const.py`. Aanzetten zodra één van vier redenen geldt:

| # | Voorwaarde |
|---|---|
| 1 | accu staat meer dan **5 °C** boven buiten |
| 2 | accu boven **35 °C** absoluut |
| 3 | meer dan **500 W** door de accu én al **2 °C** boven buiten |
| 4 | meer dan **1500 W** door de accu én boven **30 °C** |

Uitzetten alleen als **alle drie** tegelijk gelden: delta onder 2 °C,
vermogen onder 300 W, accu onder 33 °C. De marge tussen aan en uit is
bewuste hysterese — zonder die ruimte zou de ventilator rond één grens
blijven pendelen. Er is een aparte test die precies dat vastlegt: bij
een delta van 3 °C blijft staan wat er staat, in beide richtingen.

### Twee bewuste afwijkingen

**1. Geen `float(0)`-terugval.** De automatisering las sensoren met
`states(...)|float(0)`, waardoor een onbeschikbare sensor stilzwijgend
als 0 werd gelezen. Dat is in beide richtingen gevaarlijk: valt de
*buitensensor* weg, dan wordt buiten 0 °C, is de delta ineens gelijk aan
de volledige accutemperatuur en slaat de ventilator aan op een meting
die er niet is. Valt de *accusensor* weg, dan wordt de accu 0 °C en
wordt er juist nooit meer gekoeld. Deze integratie laat de schakelaar
bij ontbrekende data met rust — de bestaande stand blijft staan, wat in
beide gevallen de veilige keuze is. Datzelfde geldt als de
ventilatorschakelaar zelf onleesbaar is: dan wordt er niet gegokt op
"hij zal wel uit staan".

**2. Geen 20-seconden-vertraging.** De aparte trigger op "vermogen boven
500 W gedurende 20 seconden" is niet nagebouwd. De evaluatie draait bij
elke wijziging, en de hysterese in de uitschakelvoorwaarden voorkomt al
dat een korte piek de ventilator laat pendelen.

### Even snel als voorheen

De automatisering draaide elke 2 minuten plus op elke sensorwijziging.
Alleen meeliften op de 5-minuten-tick zou merkbaar trager reageren, juist
bij een plotselinge belastingpiek. Er is daarom een **eigen
state-listener** op de accutemperatuur, de buitentemperatuur en het
accuvermogen — hetzelfde patroon als de live waterdetectie uit v0.63.98.

### Ingebed in wat er al was

- **`force_manual` en `learning only`** blokkeren het schakelen, net als
  bij elke andere aansturing. De beslissing wordt wél doorgerekend en
  getoond, zodat het dashboard blijft kloppen — met de reden erbij dat er
  niet is uitgevoerd.
- **Meldingen** lopen via de bestaande `_dispatch_notification`, dus via
  de al geconfigureerde notify-service. Geen apart mobiel-apparaat meer
  hard in een automatisering.
- **Niet elke tick opnieuw schakelen**: staat de ventilator al goed, dan
  wordt er geen service-call gedaan.

### Zichtbaarheid

Nieuwe sensor **Accu-koeling** met de stand én **welke van de vier
redenen** geldt — met vier mogelijke oorzaken zegt "aan" alleen te weinig
om iets van te leren. Plus de laatste tien schakelmomenten, een tegel op
het Overzicht-tabblad, en `battery_cooling_state` /
`battery_cooling_history` in de diagnostiek-export.

### Configuratie

Drie nieuwe optionele velden: accutemperatuur-sensor,
ventilatorschakelaar, en een eigen buitentemperatuursensor. Die laatste
mag leeg blijven — dan valt hij terug op de buitentemperatuur die de
integratie al gebruikt (achtertuinsensor met uitschieterfilter, anders de
weerentiteit). Zolang de eerste twee niet zijn ingevuld, gebeurt er
niets.

### Getest

Nieuw `tests/test_battery_cooling_control.py`, 21 tests: elk van de vier
aanzet-redenen apart, uitzetten alleen bij alle drie de voorwaarden,
twee gevallen waarin doorgekoeld moet worden terwijl één voorwaarde al
is teruggevallen, de hysterese in beide richtingen, alle drie de
onleesbare-sensor-gevallen, het daadwerkelijke schakelen plus
geschiedenis, `force_manual` en `learning only`, geen overbodige
service-call, de terugval op de bestaande buitentemperatuur, en de
sensorweergave.

**Volledige testsuite**: 715 tests, allemaal groen.

### Na installatie

Vul de drie velden in bij **Configureren** en **zet daarna je eigen
automatisering uit** — anders sturen ze allebei dezelfde schakelaar aan.

## Vier verbeteringen uit een diagnostiek-review (v0.63.121)

**Gevraagd**: "Graag analyseren en waar mogelijk verbeteringen
doorvoeren", bij een verse diagnostiek-export van v0.63.120.

Eerst het goede nieuws uit die export: de klimaat-projectie werkt
(24-uurs traject, geleerde bias 0,3 °C), alle vijf de leercheks staan op
OK na vijf dagen, er zijn geen ontbrekende optionele sensoren meer, er
staat geen enkele fout, en de duplicaten-melding is inderdaad uit de
statusbepaling verdwenen. Vier dingen vielen wél op.

### 1. Luchtvochtigheid met veertien decimalen

`living_room_current_humidity_percent: 45.9213256835938`. Exact dezelfde
klacht die in v0.63.92 voor de *temperatuur* werd opgelost ("absurd veel
decimalen"), maar de luchtvochtigheid die er direct naast wordt
uitgelezen bleef toen ongemoeid — zelfde sensor, zelfde hoge precisie,
zelfde probleem. Nu ook op 1 decimaal.

### 2. Oude tijdstempels in UTC bleven de watertelling scheeftrekken

De sessiegeschiedenis in de export bevatte tijdstempels met **zowel
`+02:00` als `+00:00`**. Dat is het litteken van de tijdzonebug uit
v0.63.119: momenten die vóór die fix door de listener zijn vastgelegd
staan in UTC, en die entries blijven gewoon in de geschiedenis staan.

De "verklaart maar X L"-check las de eerste tien tekens van de
tijdstempel als datum. Voor een UTC-tijdstempel tussen middernacht en
02:00 lokaal levert dat de datum van **gisteren** op — dus die momenten
telden niet mee voor vandaag, en de waarschuwing sloeg ten onrechte aan.
De datum wordt nu geparsed en naar lokale tijd omgerekend, waarmee ook
de oude, al opgeslagen entries alsnog goed meetellen.

### 3. De waterwaarschuwing gokte in plaats van te diagnosticeren

"Mogelijk worden nog steeds stoten gemist" — een gok die twee keer de
verkeerde kant op wees. Het **aantal** herkende momenten onderscheidt de
twee mogelijke oorzaken juist meteen van elkaar:

- weinig momenten → de detectie mist stoten;
- veel momenten met weinig liters → de detectie werkt, maar de
  volumebepaling schiet tekort (en dan is `liter` naast
  `liter_uit_meterstand` precies het paar getallen dat het uitwijst).

De melding noemt nu het aantal en trekt de bijbehorende conclusie.

### 4. Sensor-gezondheid oordeelde op één of twee metingen

Twee keer waargenomen: "slecht (0,0%, 1 metingen)" en "verminderd
(50,0%, 2 metingen)". Bij zo weinig metingen zegt dat percentage niets —
één ongelukkige meting maakt het meteen 0% of 50% — maar het bracht de
systeemstatus wél op "Aandacht gewenst". En het venster loopt na élke
herstart onvermijdelijk door die fase heen.

Onder `MEASUREMENT_QUALITY_MIN_SAMPLES` (10) wordt er nu **geen oordeel**
geveld: score en label blijven leeg tot er genoeg metingen zijn. Een
échte storing wordt daardoor niet verborgen — die overleeft tien
metingen moeiteloos.

### Getest

Nieuw `tests/test_diagnostics_review_improvements.py`, 11 tests waarvan
er **7 aantoonbaar falen op de vorige versie**: afronding van
luchtvochtigheid (en dat een ontbrekende sensor gewoon leeg blijft), een
in UTC opgeslagen moment dat alsnog voor vandaag telt, beide varianten
van de nieuwe waterdiagnose, een onleesbare tijdstempel die wordt
overgeslagen in plaats van te crashen, geen oordeel bij één meting en
vlak onder de drempel, wél een oordeel precies óp de drempel, en de twee
kanten van het praktische gevolg: één slechte meting verlaagt de
systeemstatus niet meer, een echt slechte sensor nog steeds wel.

Vier bestaande tests in `test_energy_balance_validation.py` rekenden met
1 tot 4 metingen; die zijn opgehoogd tot boven de drempel, zodat ze de
rekenregel blijven controleren in plaats van de drempel. De
water-assertie in `test_diagnostic_summary.py` is meebewogen naar de
nieuwe formulering.

**Volledige testsuite**: 694 tests, allemaal groen.

### Wat de export nog niet kon uitwijzen

Het waterverschil zelf (85 L dagtotaal versus 5 L verklaard) is met deze
export níet op te lossen: alle vier de opgeslagen momenten dateren van
vóór v0.63.119 — te zien aan het ontbrekende `liter_uit_meterstand` — en
`water_sessions_today_count` stond nog op 0. De nieuwe volumebepaling
had simpelweg nog geen kans gehad. Een export na een volle dag draaien
wijst met de nieuwe, scherpere melding meteen de richting aan.

## Klimaat-projectie wees naar een configuratieveld dat allang goed stond (v0.63.120)

**Gerapporteerd**, met screenshot van het ingevulde configuratiescherm:
"Maar ze staan wel ingevuld?"

Het Klimaat-tabblad meldde *"Geen living_room_temperature_sensor_entity
geconfigureerd of niet uitleesbaar"*, terwijl die sensor wél was
gekoppeld én een actuele waarde gaf (23,46 °C, twee seconden oud). De
melding was simpelweg onwaar — en stuurde de zoekrichting compleet de
verkeerde kant op.

### Root cause: een verouderde melding

`_recompute_climate_trajectory` liet de reden bij een ontbrekende
buitentemperatuur-voorspelling over aan wat de **fetch** ooit in
`climate_forecast_note` had achtergelaten. In de code stond dat ook zo
toegelicht: *"climate_forecast_note is already set by the fetch step
above"*.

Die aanname klopt niet. De fetch is bewust **gethrottled op eens per 30
minuten** (het is een echte service-call, v0.63.58). Op alle
tussenliggende ticks draait hij helemaal niet — en blijft in dat veld
dus de melding staan van een situatie die allang voorbij is.

De keten die dat opleverde:

1. Vlak na een herstart is de temperatuursensor kort onbereikbaar —
   volstrekt normaal terwijl het apparaat verbinding maakt.
2. Die tick zet de melding "sensor niet geconfigureerd of niet
   uitleesbaar".
3. Vijf minuten later werkt de sensor prima, maar de
   buitentemperatuur-voorspelling ontbreekt nog. De functie valt uit op
   de vroege return en laat de melding **ongemoeid**.
4. De fetch die de melding had moeten corrigeren, draait pas over 30
   minuten — en zet 'm alleen als hij zélf faalt.

Resultaat: een permanent onjuiste diagnose, die naar een
configuratiescherm wijst waar niets mis is.

### Tweede probleem in dezelfde tekst

"Niet geconfigureerd" en "niet uitleesbaar" zaten in één zin. Dat zijn
twee totaal verschillende situaties: de eerste vraagt om actie van de
gebruiker, de tweede lost zichzelf op. Ze op één hoop gooien maakte een
tijdelijke storing niet te onderscheiden van een configuratiefout.

### Fix

- De reden waarom de buitenvoorspelling ontbreekt wordt nu apart bewaard
  (`_climate_forecast_fetch_note`) en bij **elke** tick opnieuw getoond,
  in plaats van te vertrouwen op wat er toevallig nog in het gedeelde
  meldingsveld stond. Bij een geslaagde fetch wordt die reden gewist, zodat
  een opgeloste storing niet blijft hangen.
- Drie losse, accurate meldingen in plaats van één:
  - sensor niet geconfigureerd → verwijst naar Configureren;
  - sensor geconfigureerd maar nu niet uitleesbaar → **noemt de
    entity_id** en meldt dat het vanzelf herstelt;
  - nog geen buitenvoorspelling → noemt dát als reden.

### Getest

Nieuw `tests/test_climate_projection_note_accuracy.py`, 8 tests waarvan
er **6 aantoonbaar falen op v0.63.119**, inclusief de exact
gerapporteerde volgorde (tick 1 sensor onbereikbaar → tick 2 sensor
werkt weer): de melding van tick 1 mag in tick 2 niet blijven staan.
Verder: de ontbrekende weerentiteit wordt als échte reden genoemd, niet
geconfigureerd krijgt een eigen tekst, niet-uitleesbaar noemt de
entity_id en suggereert géén configuratiefout, een geslaagde fetch wist
de oude reden, en end-to-end herstelt de projectie volledig zodra alles
beschikbaar is.

**Volledige testsuite**: 683 tests, allemaal groen.

## Waterverbruik: drie oorzaken waarom gebruiksmomenten het dagtotaal niet verklaarden (v0.63.119)

**Gerapporteerd (derde keer)**: "Waterverbruik: dagtotaal (85 L) is een
stuk hoger dan wat de geregistreerde gebruiksmomenten van vandaag
verklaren (5 L) - mogelijk worden nog steeds stoten gemist."

De eerdere aanname was dat er stoten gemist werden. Dat bleek niet de
kern: de momenten werden grotendeels wél gedetecteerd, maar hun volume
kwam op nul uit. Drie afzonderlijke oorzaken, elk apart aantoonbaar.

### Oorzaak 1 — de meterstand is te grof voor korte stoten

De liters per moment kwamen uitsluitend uit het verschil van de
**cumulatieve meterstand** tussen start en einde. Dat is zo nauwkeurig
als de resolutie van die meter. Bij een stand in m³ met twee decimalen
is de kleinste waarneembare stap 10 liter — dus handen wassen, een
toiletspoeling of een korte kraanstoot komt uit op precies 0,0 L. De
momenten stonden netjes in de lijst, met volume nul.

**Fix**: de liters worden nu bepaald door het **debiet te integreren**
(L/min × verstreken minuten, opgeteld bij elke meting). Dat werkt op de
resolutie van de debietsensor zelf en is dus ongevoelig voor de
stapgrootte van de meterstand. Een te groot gat tussen twee metingen
(bijvoorbeeld na een herstart) wordt niet meegerekend, zodat een
achtergebleven debiet niet urenlang wordt doorgerekend.

De meterstand-methode verdwijnt niet: die blijft als kruiscontrole in
`liter_uit_meterstand` staan, zodat een afwijking tussen beide zichtbaar
is in plaats van stilzwijgend.

### Oorzaak 2 — het weergavevenster werd als rekenbasis gebruikt

De diagnostiek-check telde de liters van vandaag op uit
`water_session_history`. Die lijst bewaart met opzet maar de laatste
20 momenten (weergave op het Water-tabblad). Zodra er meer momenten op
een dag zijn, valt de rest er stilletjes uit en is het "verklaarde"
dagtotaal structureel te laag — volledig los van de vraag of de detectie
zelf goed werkte.

**Fix**: een losstaande dagteller (`water_sessions_today_l` /
`_count`) die buiten dat venster om loopt. De check gebruikt die nu, met
de oude optelling als terugval vlak na een herstart.

### Oorzaak 3 — tijdzone

`new_state.last_changed` levert Home Assistant **altijd in UTC** aan,
terwijl de 5-minuten-tick lokale tijd doorgeeft. Een moment dat via de
listener startte kreeg dus een UTC-tijdstip mee. Twee concrete gevolgen:

- Een moment tussen middernacht en 02:00 lokaal werd opgeslagen met de
  datum van **gisteren** en telde daardoor niet mee voor "vandaag".
- Het waterontharder-venster (0–6 uur) schoof twee uur mee: een douche
  om 07:30 lokaal (05:30 UTC) werd onterecht als regeneratie aangemerkt,
  terwijl een spoeling om 01:15 lokaal juist buiten het venster viel.

Zelfde soort fout als de achtertuinsensor-tijdzonebug uit v0.63.93.

**Fix**: `dt_util.as_local()` op het binnenkomende tijdstip.

### Getest

Nieuw `tests/test_water_session_volume_accounting.py`, 10 tests, waarvan
er **9 aantoonbaar falen op v0.63.118**:

- een korte stoot levert echte liters op ondanks een grove meterstand;
- twaalf kleine stoten tellen samen op tot 72 L in plaats van bijna nul;
- de meterstand blijft als kruiscontrole vastgelegd;
- een groot gat wordt niet geïntegreerd;
- de dagteller wordt niet begrensd door de weergavelijst (35 momenten);
- de dagteller reset op een nieuwe dag;
- het listener-tijdstip wordt naar lokale tijd omgerekend;
- een ochtenddouche is géén waterontharder;
- een nachtelijke regeneratie wordt juist wél herkend;
- en end-to-end: het aandachtspunt verdwijnt zodra de momenten het
  dagtotaal verklaren.

Twee bestaande tests legden de oude meterstand-methode vast en zijn
meebewogen naar de nieuwe bedoeling — ze controleren nu beide waarden
(geïntegreerd én uit de meterstand).

**Volledige testsuite**: 675 tests, allemaal groen.

## Duplicaatparen kunnen nu ook beoordeeld worden (v0.63.118)

**Gevraagd**: "NILM apparaten kan ik bevestigen danwel negeren, dit kan
nog niet met de waarschijnlijke duplicaten - kun je hiervoor een zelfde
optie maken zodat ik ook dit kan afwijzen, en dit dan ook daadwerkelijk
niet meer terug komt als mogelijk duplicaat?"

De duplicaat-detectie (v0.63.91) was tot nu toe een doodlopende straat:
hij meldde paren, maar er was geen enkele manier om er iets mee te doen.
Het dashboard verwees naar de `reject_nilm_device`-service, maar dat
sluit een heel apparaat uit — niet hetzelfde als zeggen "deze twee zijn
geen duplicaat van elkaar". Een bewust geaccepteerd paar bleef dus
eeuwig terugkomen.

### Twee acties, spiegelbeeld van confirm/reject

- **✅ Bevestigen** — het is echt hetzelfde signaal. Het tweede apparaat
  van het paar wordt permanent uitgesloten (via het bestaande
  `reject_nilm_device`, dus inclusief zwarte lijst), zodat hetzelfde
  verbruik niet dubbel geteld blijft worden. De knop zet de naam van het
  apparaat dat verdwijnt **in zijn eigen label** — daar hoort niets te
  raden te zijn.
- **❌ Negeren** — het is geen duplicaat. Het paar verdwijnt permanent
  uit de suggesties; beide apparaten blijven gewoon bevestigd en worden
  gewoon verder gevolgd.

### Hoe het permanent blijft

Beoordeelde paren worden opgeslagen als richting-onafhankelijke sleutel
(`"<a>|<b>"`, alfabetisch gesorteerd) in `nilm_dismissed_duplicate_
pairs`, en gaan mee door **dezelfde Store** als de bevestigde/afgewezen
apparaten — inclusief de laadvolgorde-borging uit v0.63.115. De
richting-onafhankelijkheid is bewust: zonder dat zou een paar alsnog
terugkomen zodra de detectie de volgorde omdraait, bijvoorbeeld na een
hernoeming die de alfabetische sortering verandert.

Een beoordeling wordt bewust **niet** opgeruimd als een van beide
apparaten tijdelijk uit de bevestigde lijst verdwijnt. De gebruiker
heeft een oordeel gegeven; dat moet blijven gelden, ook als het apparaat
later opnieuw bevestigd wordt.

### Waar je het vindt

- **Apparaten-tabblad**: onder de duplicatenlijst staat nu "Duplicaatpaar
  beoordelen" met dezelfde twee tegels als bij losse kandidaten. Eén
  sleuf, om dezelfde reden als bij de kandidaten (v0.63.46): een paar
  toont twee namen naast elkaar, dus de breedte is hier nog schaarser.
  Zodra je een paar beoordeelt, schuift het volgende automatisch in
  beeld.
- **Services**: `dismiss_nilm_duplicate_pair` en
  `confirm_nilm_duplicate_pair` (beide met `entity_id_1` +
  `entity_id_2`), voor automatiseringen of om er meerdere snel
  achter elkaar weg te werken.
- **Diagnostiek + sensorattribuut**: `afgewezen_duplicaatparen` toont
  hoeveel paren al beoordeeld zijn, zodat een verdwenen suggestie
  herkenbaar een keuze is en niet iets dat stilletjes wegviel.

### Herbruikte lessen

De nieuwe knoppen volgen bewust exact het patroon van de
kandidaat-knoppen, inclusief alles wat daar met vallen en opstaan is
geleerd: `has_entity_name` uit met een expliciete `entity_id`
(v0.63.47/.79), registratie als coordinator-listener omdat een
`ButtonEntity` niet pollt (v0.63.48), en — belangrijk — het **getoonde**
paar wordt vastgelegd bij weergave, zodat een druk nooit op een
inmiddels verschoven sleuf landt (v0.63.107). Deze knoppen zijn nieuw,
dus geen `_v2`/`_v3`-suffix nodig: er is geen bestaande registry-entry om
mee te botsen.

### Getest

Nieuw `tests/test_nilm_duplicate_pair_judgement.py`, 21 tests: detectie
vóór beoordeling, afwijzen verwijdert het paar maar houdt beide
apparaten bevestigd, richting-onafhankelijkheid, dubbel drukken is een
no-op, opslag in de Store, **niet terugkomen na een herstart**, **vijf
herstarts achter elkaar**, andere paren blijven ongemoeid, bevestigen
sluit het tweede apparaat uit én voorkomt herontdekking, beide
knoplabels noemen de juiste namen, lege sleuven, de v0.63.107-borging op
beide knoppen, vaste entity_ids en de dashboardverwijzing.

**Volledige testsuite**: 665 tests, allemaal groen.

## Einde saldering ingebouwd + laadkant financieel rechtgetrokken (v0.63.117)

**Gevraagd**: "Als de accu terug levert aan mijn woning bespaart dit
inkopen, als de accu laadt beperkt dit opbrengst van terug levering PV
energie. Zit dit ook in alle kosten/financiele berekeningen zo
verwerkt?" — gevolgd door: "Alles oppakken en integreren dat vanaf
01-01-2027 saldering niet meer geldt."

### Wat er mis was

Ontladen was goed verwerkt: elke daling van de accu-inhoud realiseerde
al het verschil tussen de actuele prijs en de kostprijs, ongeacht of dat
nu verkoop was of gewoon huisverbruik dekken.

De laadkant niet. Elke geladen kWh werd tegen de kale inkoopprijs
geboekt, ook als het PV-overschot betrof dat anders was teruggeleverd.
Daardoor werd de teruglever­premie van €0,02/kWh bij export wél
bijgeteld, maar bij het opofferen van export nooit afgetrokken — een
structurele overschatting die altijd dezelfde kant op werkte. Dit stond
sinds v0.63.25 als bekende beperking in de docstring, maar was nooit
afgemaakt.

Daarbovenop rustte het hele model op één onuitgesproken aanname:
**teruglevering is evenveel waard als inkoop**. Dat klopt exact zolang
salderen geldt, en helemaal niet meer daarna.

### Het nieuwe model: bron in, bestemming uit

Elke kWh die de accu **ingaat** krijgt de kostprijs van zijn **bron**:

| Bron | Kostprijs |
|---|---|
| Netinkoop | de inkoopprijs (incl. belasting) |
| PV-overschot | de gederfde teruglevering |

Elke kWh die de accu **uitgaat** krijgt de waarde van zijn
**bestemming**:

| Bestemming | Opbrengst |
|---|---|
| Eigen huisverbruik | de vermeden inkoopprijs |
| Teruglevering aan het net | het teruglevertarief |

De splitsing gebeurt met twee spiegelbeeldige helpers:
`_split_charge_pv_vs_grid` (PV-opwek minus huisverbruik, begrensd op wat
er werkelijk geladen is) en het al bestaande
`_split_discharge_export_vs_load`. Ontbreekt de PV- of verbruikssensor,
dan wordt alles als netinkoop geteld — bewust de conservatieve kant,
want dat houdt de kostprijs hoog en overschat de besparing dus niet.

### De saldering-overgang

`_get_feedin_value_per_kwh` bepaalt wat één teruggeleverde kWh op dit
moment waard is:

- **Zolang salderen geldt**: de inkoopprijs plus de premie. Alles valt
  samen zoals voorheen, dus historische cijfers blijven vergelijkbaar.
- **Daarna**: het kale marktarief zonder energiebelasting (uit hetzelfde
  forecast-attribuut, `price_tax_excluded`), plus de premie, minus
  eventuele terugleverkosten.

Ontbreekt dat attribuut na saldering, dan wordt er **niet teruggevallen
op de inkoopprijs** — dat is precies de aanname die dan niet meer klopt.
In plaats daarvan verschijnt er een echt aandachtspunt in de
diagnostiek.

### Waarom dit zoveel uitmaakt — met getallen

Bij een inkoopprijs van €0,30/kWh en een kaal marktarief van €0,09/kWh:

| | Salderen actief | Na saldering |
|---|---|---|
| Terugleverwaarde | €0,32/kWh | €0,11/kWh |
| Spread inkoop − teruglevering | −€0,02 | **+€0,19** |
| PV → accu → eigen verbruik | **−€0,02/kWh** | **+€0,19/kWh** |

Onder saldering *kost* PV opslaan voor eigen gebruik dus geld (je loopt
de premie mis en krijgt er niets voor terug — de winst zit puur in
tijd-arbitrage tussen goedkope en dure kwartieren). Na saldering levert
exact dezelfde handeling €0,19/kWh op. Dat is geen nuance maar een
omkering.

### Configuratie (drie nieuwe velden)

- `salderen_end_date` — laatste dag dat salderen geldt, standaard
  `2026-12-31`. Configureerbaar en niet hard ingebakken, omdat politiek
  uitstel al meermaals is voorgekomen; een verkeerde ingebakken datum zou
  stilzwijgend élk financieel getal scheeftrekken. Bij een onleesbare
  datum wordt teruggevallen op "salderen actief" (bestaand gedrag
  behouden in plaats van ongemerkt omschakelen).
- `feedin_price_attribute` — welk attribuut het teruglevertarief
  benadert, standaard `price_tax_excluded`.
- `feedin_cost_eur_per_kwh` — vaste terugleverkosten per kWh, standaard
  0. Niet te raden, dus leeg gelaten tot je eigen contract bekend is.

### Ook aangepast

- **Tegenfeitelijke KPI**: rekende import en export tegen hetzelfde
  tarief af. Dat trok de vergelijking na saldering scheef in het voordeel
  van "geen accu", want het tegenfeitelijke scenario exporteert per
  definitie méér. Nu aparte tarieven per richting via
  `_grid_flow_cost_eur`.
- **Zichtbaarheid**: regime, terugleverwaarde, kWh geladen uit PV vs.
  net, kWh ontladen naar het net en de cumulatief gederfde teruglevering
  staan nu op het Financieel-tabblad en in de diagnostiek-export.

### Getest

`tests/test_salderen_end_financial_model.py`, 23 tests: de datumgrens
(laatste dag vs. dag erna vs. ongeldige datum), de terugleverwaarde in
beide regimes inclusief negatieve waarden, beide splitsingen met en
zonder sensoren, de kostprijsvorming per bron, de opbrengst per
bestemming, de richtingsafhankelijke netstroomkosten, en — belangrijk —
dat het exportgedrag onder saldering **exact de oude formule** oplevert.
Plus twee dashboardborgingen.

**Volledige testsuite**: 644 tests, allemaal groen.

### Wat bewust nog niet is aangepast

De **beslislogica** is ongemoeid gelaten. Die beslist nu nog puur op
prijsdrempels en weet niets van het bovenstaande verschil. Zodra
saldering vervalt, verandert de optimale strategie echt: zonoverschot
opslaan wordt dan op zichzelf al €0,19/kWh waard, ook zonder enig
prijsverschil tussen kwartieren. `_should_capture_solar_instead_of_
postponing` en de prijs-prioriteit zouden daar iets mee moeten. Dat
raakt de mechanismen die eerder expliciet ongewijzigd moesten blijven,
dus dat is een aparte, bewuste beslissing — niet iets om er stilletjes
bij te doen.

## Duplicaten-melding telt niet meer mee voor de systeemstatus (v0.63.116)

**Gevraagd**: "de melding duplicaten zie ik niet als een melding welke
systeem status niet naar ok kan brengen."

Terecht. Waarschijnlijke NILM-duplicaatparen zijn een **observatie over
de Home Assistant-installatie** (twee entiteiten die hetzelfde fysieke
signaal meten), niet iets dat mis is met deze integratie of met de
accu-aansturing. Het is bovendien een permanente toestand die bewust zo
gelaten kan worden — 18 duplicaatparen die er morgen ook nog zijn. Zolang
zo'n melding meetelde, bleef de systeemstatus voor altijd op "Aandacht
gewenst" staan, waarmee die status precies zijn nut verliest: hij zegt
dan niets meer over of er echt iets aan de hand is.

**Wijziging**: `get_diagnostic_summary()` kent nu twee categorieën in
plaats van één:

- **`aandachtspunten`** — zaken die actie of aandacht verdienen. Deze
  brengen de systeemstatus naar "Aandacht gewenst", precies zoals
  voorheen.
- **`informatief`** — observaties die het vermelden waard zijn maar niets
  zeggen over de gezondheid van de integratie. Blijven volledig
  zichtbaar, maar laten de status op "OK".

De duplicaten-melding is de eerste bewoner van die tweede categorie.
Onderdrukken was nadrukkelijk niet de bedoeling — alleen
herclassificeren.

**Zichtbaarheid blijft intact, op drie plekken**:
- Statussensor: nieuw attribuut `informatief` naast `aandachtspunten`.
- Overzicht-tabblad: een eigen blok "ℹ️ Ter info (geen invloed op de
  status)" onder de aandachtspunten.
- Live-tabblad: informatieve regels krijgen "Ter info:" in plaats van
  "Let op:", zodat ze niet als probleem lezen. Voorheen verdwenen ze uit
  het verhaal zodra er verder niets aan de hand was (het verhaal stopte
  bij status "nominaal") — dat is nu ook opgelost.

**Getest**: nieuw `tests/test_diagnostic_informational_category.py`, 9
tests: duplicaten alleen houden de status op OK; ze worden nog steeds
gemeld; end-to-end op de statussensor; een écht aandachtspunt (mogelijk
defect apparaat) brengt de status nog wél omlaag; een actieve fout wint
nog steeds; en de drie varianten van het Live-verhaal ("Let op",
"Ter info", beide, geen van beide). De bestaande test
`test_flags_nilm_duplicates` is meebewogen naar het nieuwe, bedoelde
gedrag.

**Volledige testsuite**: 621 tests, allemaal groen.

## NILM-keuzes overleefden geen herstart: de Store werd bij élke herstart afgekapt op 20 (v0.63.115)

**Gerapporteerd** (ná de knop-race-fix van v0.63.107): "Keuzes voor NILM
apparaten worden nog steeds niet opgeslagen, de onbevestigde lijst
blijft terug komen na een herstart."

Screenshot bij de melding: **23 onbevestigde kandidaten** en **exact 20
bevestigde apparaten**. Dat getal 20 was de doorslaggevende aanwijzing —
het is precies `NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT`.

### Root cause — een andere dan v0.63.107

v0.63.107 loste een echte bug op (de knop legde het getoonde entity_id
niet vast, dus een keuze kon op het verkeerde apparaat landen), maar dat
was niet de oorzaak van het verdwijnen. De echte oorzaak zat in de
opstartvolgorde in `async_setup_entry`:

```python
await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)  # platforms EERST
await coordinator.async_setup()                                          # Store-load PAS DAARNA
```

De keten die daaruit volgde, bij élke herstart:

1. De platforms werden opgezet vóórdat de NILM-Store van schijf was
   gelezen. `NilmConfirmedDevicesSensor.async_added_to_hass` draaide dus
   altijd met een nog volledig **lege** `nilm_confirmed_devices` en
   `nilm_rejected_entities`.
2. Die methode gebruikte "de lijsten zijn leeg" als bewijs dat de Store
   leeg was. Dat gokje was structureel fout. Gevolg: het
   **eenmalig bedoelde** migratiepad (voor installaties van vóór de
   Store, v0.63.66) sloeg bij iedere herstart opnieuw toe.
3. Dat migratiepad leest uit de eigen herstelde entiteit-state — en die
   attributen (`apparaten`, `rejected_entities`) zijn met opzet
   **afgekapt op 20 items**, omdat de recorder een limiet van 16 KB per
   attribuut heeft (v0.63.45/.66).
4. Vervolgens schreef die methode het resultaat **onvoorwaardelijk**
   terug naar de Store — en overschreef daarmee de volledige, goede
   inhoud met de afgekapte kopie.
5. Pas dáárna las `coordinator.async_setup()` de zojuist verminkte Store
   terug.

Netto per herstart: bevestigde apparaten hard afgekapt op 20, afgewezen
entiteiten óók op 20. Alles daarboven verdween — de bevestigde apparaten
inclusief hun maandenlang opgebouwde CUSUM-geschiedenis, en de afgewezen
entiteiten kwamen terug als "onbevestigde kandidaat". Precies het
gerapporteerde beeld.

Het effect was bovendien **progressief**: elke herstart kapte opnieuw af,
dus de lijst kon nooit boven de 20 uitkomen, hoeveel de gebruiker ook
beoordeelde.

### Waarom de bestaande test dit niet ving

`test_nilm_confirmed_devices_persistence.py` bevatte al een test met de
naam `test_sensor_does_not_migrate_when_store_already_has_data`. Die
zette de Store-inhoud **handmatig** in het geheugen en controleerde dan
het gedrag — precies de toestand die in productie nooit bereikt werd. De
test bevestigde dus de *bedoelde* volgorde, niet de *werkelijke*. Een
klassieke blinde vlek: het gedrag klopte, de bedrading niet.

### Bewijs vóór de fix

De echte productievolgorde nagebootst tegen de v0.63.114-code, met 60
bevestigde apparaten en 55 afgewezen entiteiten in de Store:

```
AssertionError: assert 20 == 60
```

Van 60 bevestigde apparaten bleven er na één herstart 20 over. Exact wat
het dashboard toonde.

### Fix — drie lagen, elk afzonderlijk voldoende

1. **Volgorde omgedraaid** (`__init__.py`): de Store wordt nu geladen
   vóór `async_forward_entry_setups`, via de nieuwe publieke
   `coordinator.async_load_persisted_nilm_state()`. De load in
   `async_setup()` blijft staan als vangnet en is idempotent gemaakt
   (een tweede aanroep leest nooit meer over verser geheugen heen).
2. **Niet meer gissen** (`coordinator.py`): twee expliciete vlaggen
   (`_nilm_store_loaded`, `_nilm_store_had_data`) en de publieke property
   `nilm_store_had_data`. Het migratiepad kijkt nu naar of de Store
   aantoonbaar leeg wás, niet naar of het geheugen toevallig leeg is.
3. **Migratie kan geen data meer wegnemen** (`sensor.py`): het pad slaat
   volledig over zodra de Store data had; afgewezen entiteiten worden
   **samengevoegd** (union) in plaats van vervangen; en er wordt alleen
   naar de Store geschreven als de migratie daadwerkelijk iets heeft
   hersteld. Die onvoorwaardelijke schrijfactie was het schadelijke deel.

### Getest

Nieuw testbestand `tests/test_nilm_restart_persistence_truncation.py`,
11 tests — alle elf falen aantoonbaar op v0.63.114:

- bevestigde apparaten voorbij de afkap-grens overleven een herstart;
- afgewezen entiteiten voorbij de grens overleven een herstart;
- een afgewezen entiteit duikt na een herstart niet opnieuw op als
  kandidaat (end-to-end, inclusief discovery-scan);
- een gevulde Store wordt nooit overschreven door de herstelde state;
- geleerde CUSUM-geschiedenis blijft intact voor apparaten voorbij de
  grens;
- **vijf herstarts achter elkaar** nemen niets weg (het progressieve
  karakter);
- het echte eenmalige migratiepad (lege Store, wél herstelde state)
  werkt nog steeds;
- de Store-load is idempotent;
- de `nilm_store_had_data`-vlag klopt in beide richtingen;
- de afgewezen-lijst kan tijdens migratie alleen groeien;
- **structurele borging van de volgorde zelf**: een AST-vrije
  bronvolgorde-check op `__init__.py`, zodat het omdraaien van die twee
  regels nooit ongemerkt kan terugkeren.

**Volledige testsuite**: 612 tests, allemaal groen.

### Wat dit voor bestaande data betekent

Eerlijk: wat al weg is, is weg. De Store bevat op dit moment nog maar 20
bevestigde apparaten en maximaal 20 afgewezen entiteiten; de rest is bij
eerdere herstarts overschreven en is niet te reconstrueren. De 23
kandidaten die nu getoond worden moeten dus één keer opnieuw beoordeeld
worden. Vanaf deze versie blijft die beoordeling wél staan, ook boven de
20 en ook over meerdere herstarts heen.

## Gauge-kaarten vervangen door compacte tegels (v0.63.114)

Vervolg op v0.63.113: "De gauge kaarten zijn ook veel te groot dit
mogen wat mij betreft de zelfde kaarten worden als de live cijfers."

**Fix**: alle drie de `type: gauge`-kaarten in het bundled dashboard
(Accu SoC en Geleerd rendement op het Overzicht-tabblad; Geleerd
accu-rendement op het Zelflerend-tabblad, waar 'ie al inconsistent
naast een mushroom-template-card stond) vervangen door dezelfde
compacte `mushroom-template-card`-stijl als de "Live cijfers"-tegels.
Kleurindicatie (groen/geel/rood) blijft behouden, nu via `icon_color`
in plaats van de gauge se `severity`-instelling, met dezelfde
drempelwaarden als voorheen.

## Overzicht-tabblad herzien: balans + compactheid (v0.63.113)

Gerapporteerd met screenshot: "het past niet meer op 1 pagina en vele
lege ruimte." Het Overzicht-tabblad gebruikt HA's "sections"-layout,
die nieuwe kaartblokken automatisch in de kortste kolom plaatst
(masonry-gedrag) — de eerste kolom (uitgebreide beslistabel + -tekst)
was veel langer dan de andere, wat de scheve verdeling en lege ruimte
veroorzaakte. Gevraagd om zowel de kolommen beter in balans te
brengen als het geheel compacter te maken.

**Compacter**:
- De aparte titelkaart ("Energy Management System" + laatste
  beslisreden) verwijderd — overlapte al met de tabnaam en de
  uitgebreide uitlegtekst eronder.
- Het "Modus & besluit"-uitlegblok van een vaste `rows: 3` (moest
  scrollen) naar `rows: auto` (past zich aan de inhoud aan).
- "Accu & rendement" en "Live cijfers" samengevoegd tot één sectie
  ("Accu, rendement & live cijfers") — één heading in plaats van twee.

**Beter gebalanceerd**:
- De lange "Actuele beslissing (detail)"-kaart (15 regels in één
  entities-kaart) gesplitst in twee kleinere, thematische kaarten:
  "Kernbeslissing (detail)" (9 direct relevante regels) en
  "Advies-modules (detail, adviserend)" (de 6 adviserende modules) —
  kleinere blokken verdelen natuurlijker over de masonry-kolommen dan
  één lang blok.

Resultaat: van 4/3/4/6/7/2 kaarten per sectie naar 3/8/7/8/2/2 - een
veel gelijkmatiger verdeling, zonder functionaliteit te verliezen.

## Systeemstatus-tegel toonde aantal aandachtspunten zonder de inhoud (v0.63.112)

Gerapporteerd, met screenshot: "De update van de integratie is leuk,
maar waar is aandacht voor vereist?" — de v0.63.109-fix toonde het
aantal aandachtspunten ("5 aandachtspunt(en)") in de subtekst van de
systeemstatus-tegel, maar niet WAT die aandachtspunten daadwerkelijk
zijn — de gebruiker moest daarvoor apart naar het Live-tabblad of
diagnostiek.

**Fix**: nieuwe markdown-kaart direct onder de systeemstatus-tegel op
het Overzicht-tabblad, die de volledige aandachtspunten-lijst toont
zodra die niet leeg is (leeg = geen kaart, geen ruis). Hergebruikt het
al bestaande `aandachtspunten`-attribuut op de sensor zelf — geen
nieuwe berekening nodig.

## Werkelijk huishoudverbruik toegevoegd + "Huidig verbruik" verduidelijkt (v0.63.111)

Vervolg op v0.63.110's naamgevingsfix: "Kun je ergens wel toevoegen wat
mijn actuele huisverbruik is... Huidig verbruik heeft hier misschien
ook een verkeerde naamgeving?" — de bestaande "Huidig verbruik"-tegel
op het Overzicht-tabblad toonde de kale P1-meter-aflezing (-24,0W in
het gerapporteerde screenshot) — negatief bij export, dus niet het
werkelijke huishoudverbruik (dat nooit negatief kan zijn).

**Nieuwe sensor** `HouseholdConsumptionSensor` — hergebruikt
`_read_corrected_consumption_power()` (dezelfde formule als HA's eigen
Energiedashboard: P1 + accu + PV, met dezelfde teken-conventie/
inversie-instelling als elders in deze integratie). Altijd ≥ 0, het
daadwerkelijke vermogen dat het huishouden nu verbruikt, ongeacht of
dat via het net, de accu of PV wordt gedekt.

**Dashboard**: de bestaande P1-tegel hernoemd naar "Netstroom, P1 (kan
negatief zijn bij export)" — behoudt zijn functie, maar de naam liegt
niet meer. Nieuwe tegel ernaast toont het werkelijke huishoudverbruik.

**Getest** (2 nieuwe tests): de berekening klopt in een export-
scenario (P1 negatief, PV dekt het verbruik); geeft `None` netjes
terug zonder leesbare P1-sensor.

## Piekvermogen verduidelijkt: netimport, niet totaal huishoudverbruik (v0.63.110)

Gerapporteerd, met twee screenshots (EMS-KPI's-tabblad naast HA's
eigen Energiedashboard): "Piekvermogen verbruik klopt niet, het
standaard energie dashboard van Home Assistant zelf geeft aan dat het
huidige verbruik al 247W is" (tegenover een geregistreerde piek van
107W).

**Uitgezocht, bleek geen bug**: HA's eigen "Stroomverbruik" berekent
het TOTALE huishoudverbruik (P1 + accu + PV samen — dezelfde formule
als `_read_corrected_consumption_power` elders in deze integratie).
Piekvermogen volgt bewust alleen de NETIMPORT via de P1-meter
(relevant voor capaciteitstarief — dat wordt afgerekend op wat het net
zelf ziet, niet op het onderliggende huishoudverbruik). Die kan
legitiem veel lager zijn zodra de accu/zon een deel van het verbruik
dekt — precies wat hier gebeurde.

**Fix**: geen gedragswijziging, uitsluitend verduidelijking. Sensor
hernoemd naar "Piekvermogen (netimport)", een `note`-attribuut
toegevoegd die het verschil expliciet uitlegt, en de dashboardkaart
(titel + beide tegel-labels) aangepast om dit onderscheid meteen
zichtbaar te maken in plaats van dat het als bug oogt.

## Systeemstatus-tegel toonde "OK" ondanks inhoudelijke aandachtspunten (v0.63.109)

Gevraagd, met screenshot van de groene "OK"-status: "misschien iets
van een self-diagnose toevoegen zodat ik ook in de button relevante
en dus systeem status ok niet klopt eigenlijk kan zien."

**Root cause**: `system_status` was tot dan toe puur een TECHNISCHE
health-check (is er een recente crash, of is de integratie
vastgelopen?) — die toonde "OK" ook als `get_diagnostic_summary()` wél
degelijk inhoudelijke aandachtspunten had (bijv. veel onbevestigde
NILM-kandidaten, een mogelijk defect apparaat).

**Fix**: een derde, tussenliggende status "Aandacht gewenst" — bewust
apart van "Fout"/"Mogelijk vastgelopen" (die blijven ernstiger: de
integratie werkt dan zelf niet correct). Alleen wanneer de integratie
technisch prima draait maar er inhoudelijke aandachtspunten zijn.

**Subtiliteit, opgelost**: een oude, allang herstelde fout die enkel
nog als historisch "laatste fout"-veld blijft staan (zelf al een
aandachtspunt in `get_diagnostic_summary()`) mag niet op zichzelf
"Aandacht gewenst" triggeren — dat wordt al preciezer, tijdgevoelig
afgedekt door de bestaande "Fout"-check. Die ene aandachtspunt wordt
daarom specifiek genegeerd bij het bepalen van "Aandacht gewenst".

**Zichtbaarheid**: de volledige aandachtspunten-lijst staat nu als
attribuut op de systeemstatus-sensor zelf. De dashboardkaart (exact
degene uit de screenshot) toont nu drie kleuren i.p.v. twee — groen
(OK), oranje (Aandacht gewenst), rood (Fout/Mogelijk vastgelopen) —
plus het aantal aandachtspunten in de subtekst.

**Getest** (3 nieuwe tests): "Aandacht gewenst" verschijnt zodra er
aandachtspunten zijn, ook bij een verder technisch gezonde integratie;
een oude, herstelde fout triggert dit niet op zichzelf; een actieve
fout blijft correct "Fout" tonen, niet gedegradeerd naar "Aandacht
gewenst".

## Drie proactieve checks toegevoegd aan de diagnostiek-samenvatting (v0.63.108)

Gevraagd: "ik denk dat je vele zaken welke ik vandaag en gister heb
aangedragen moet zien te detecteren in de diagnose, kun je dit
herzien?" — drie nieuwe checks in `get_diagnostic_summary()`, elk
direct terug te voeren op een concreet patroon dat deze en de vorige
sessie naar boven kwam, zodat vergelijkbare situaties in het vervolg
zichtbaar worden zonder dat de gebruiker ze eerst zelf hoeft te
melden.

**1. Klimaat-projectie zonder enkele geleerde cel, ondanks tijd**
Als `living_room_temperature_sensor_entity` is geconfigureerd, er
al minstens 2 dagen zijn verstreken sinds de eerste opstart
(`first_seen_date`), en nog géén enkele cel in `climate_rate_history`
data heeft — een expliciete melding die uitlegt waarom "Korte termijn"
en "Betrouwbaar" er identiek uitzien (niets te onderscheiden zolang
geen cel data heeft), precies de vraag die vandaag opkwam.

**2. Ongewoon groot aantal onbevestigde NILM-kandidaten**
Vanaf `NILM_CANDIDATE_COUNT_ATTENTION_THRESHOLD` (15) onbevestigde
kandidaten — een signaal om de patroon-uitsluiting te herzien in
plaats van elk apparaat apart te beoordelen, naar aanleiding van de
51 kandidaten die eerder deze sessie een reeks ontbrekende
structurele patronen (SolarFlow/Solcast/fase 2-3/P1 meter) bleken te
verklaren.

**3. Waterverbruik: dagtotaal veel hoger dan geregistreerde sessies**
Als het dagtotaal (≥20L) een stuk hoger is dan wat de gebruiks-
momenten van vandaag bij elkaar optellen (<30%) — een resterend
signaal dat er mogelijk nog steeds stoten worden gemist, ook na de
v0.63.98-fix (bijv. als de live listener om wat voor reden dan ook
niet actief is).

**Terzijde, testinfrastructuur**: bij het testen van deze datum-
gevoelige checks bleek dat 18 andere testbestanden `dt_util.now`
globaal monkeypatchen zonder het na afloop te herstellen - een
bestaand patroon in deze testsuite. De nieuwe tests zijn zelf
expliciet gepatcht (niet afhankelijk van de systeemklok) én ruimen
zichzelf netjes op met een lokale, autouse fixture, om niet zelf ook
bij te dragen aan datzelfde probleem voor tests die hierna draaien.

**Getest** (8 nieuwe tests, `test_diagnostic_summary.py`): elke check
apart voor zowel het wel-als-niet-triggeren, inclusief het randgeval
"te vroeg om data te verwachten" voor de klimaat-check.

## NILM-knop: bevestigde/afgewezen keuzes konden op het verkeerde apparaat landen (v0.63.107)

Gevraagd, na de v0.63.103/.106-fixes: "heb je ook gekeken waarom
keuzes welke ik reeds gemaakt heb niet werden opgeslagen en na een
herstart dus weer terug kwamen?" — een expliciet gecontroleerde,
scherpere vraag dan de eerdere patroon-gaten (die verklaren alleen
waarom *nieuw ontdekte* entiteiten bleven verschijnen, niet waarom
*al bevestigde/afgewezen* apparaten terugkwamen).

**Root cause, gevonden door de knop-implementatie (`button.py`)
opnieuw grondig te bekijken, niet de opslag zelf** (die was al
eerder deze sessie met echte diagnostiekdata bevestigd correct te
werken): `NilmConfirmCandidateButton`/`NilmRejectCandidateButton`'s
`async_press()` vroeg de sleuf-inhoud **opnieuw** op het moment van
drukken (`get_nilm_candidate_at_slot(self._slot)`), in plaats van het
entity_id te gebruiken dat op het scherm werd getoond. Als er tussen
het TONEN van de knop en het DRUKKEN een coordinator-tick plaatsvond
die de sleuf-inhoud liet verschuiven (bijv. een nieuw ontdekte
kandidaat die alfabetisch eerder komt in de sortering) — bevestigde/
wees de gebruiker in werkelijkheid een ANDER apparaat af dan wat ze
zagen. Het apparaat dat ze écht bedoelden bleef gewoon in de lijst
staan, en kwam dus na een herstart terug — niet omdat de opslag
faalde, maar omdat de afwijzing nooit voor het juiste apparaat
gebeurde.

**Fix**: het entity_id wordt nu vastgelegd (`_last_displayed_
entity_id`) zodra het voor weergave wordt opgevraagd
(`_slot_label`/`extra_state_attributes`, beide door HA aangeroepen
vlak vóór elke state-schrijving) — en `async_press()` gebruikt exact
diezelfde, vastgelegde waarde, nooit een verse opvraag op het moment
van drukken. Veilige terugval op een verse opvraag voor het
onwaarschijnlijke geval dat er nog nooit iets is vastgelegd.

**Getest** (3 nieuwe tests, `test_nilm_dashboard_buttons.py`):
reproduceert het exacte scenario (sleuf-inhoud verschuift tussen tonen
en drukken) en bevestigt dat het GETOONDE apparaat wordt bevestigd/
afgewezen, niet het verschoven apparaat — voor zowel bevestigen als
afwijzen, plus de terugval-veiligheidsnet-test.

## NILM: fase 2/3 en een tweede zon-voorspellingsintegratie glipten erdoor (v0.63.106)

Gerapporteerd, met screenshot: "Solar Production entiteiten en P1
meter vermogen mogen sowieso uitgesloten worden." Twee nieuwe gaten in
de bestaande patroonuitsluiting (v0.63.89/.103) gevonden:

1. **Alleen "fase 1" stond in het patroon**, niet "fase 2"/"fase 3" —
   "P1 meter Vermogen fase 3" glipte er daardoor doorheen.
2. **Een andere zon-voorspellingsintegratie** ("Solar production
   forecast", andere naamgeving dan "solcast") werd nog niet herkend.

**Fix**: `NILM_PATTERN_EXCLUDED_KEYWORDS` uitgebreid met "fase 2",
"fase_2", "fase 3", "fase_3", "solar production", en "p1 meter".

**Getest** (3 nieuwe tests): P1-meter-fase-3 en de nieuwe zon-
voorspellingsintegratie worden nooit meer kandidaat; fase 2 wordt ook
correct uitgesloten.

## Overzicht van ontbrekende optionele functies (v0.63.105)

Gevraagd: "er zijn natuurlijk meerdere entiteiten welke ik manueel
moet invullen, kun je een melding ergens op een geschikt dashboard
plaatsen wanneer er 1 ontbreekt?" — dit project heeft inmiddels veel
optionele verbeteringen opgebouwd, elk pas actief zodra de bijbehorende
entiteit is ingevuld, makkelijk te missen zonder overzicht.

**Nieuwe `get_missing_optional_features()`** — een curated lijst van
negen optionele, niet-verplichte sensoren die een zichtbare functie
ontgrendelen (achtertuinsensor, Solcast-live-correctie, CO2-
intensiteit, accu-capaciteit, woonkamertemperatuur, water, meldings-
service, vaatwasser/wasmachine-vermogen, plus een KNMI-of-
OpenWeatherMap-check waarbij één van beide voldoende is). Bewust geen
volledige lijst van elke config-key — alleen kernvereisten
(prijs/accu/PV/verbruik/SoC) blijven buiten beschouwing, die zijn
sowieso nodig om de integratie te laten draaien, geen "optionele
verbetering".

**Nieuwe sensor** `MissingOptionalFeaturesSensor` — state is het
aantal ontbrekende functies, met de volledige lijst (naam + wat het
ontgrendelt) als attribuut. Niet een RestoreEntity, recomputed vers
uit de huidige config.

**Nieuwe waarschuwingskaart op het Live-tabblad** — verschijnt alleen
als er daadwerkelijk iets ontbreekt, direct onder het lopende verhaal.
Ook toegevoegd aan diagnostiek.

**Getest** (6 nieuwe tests): alles ontbreekt zonder configuratie; een
geconfigureerde sensor verdwijnt uit de lijst; de KNMI/OpenWeatherMap-
OR-check werkt in beide richtingen; elke melding heeft een naam en
uitleg; een volledig geconfigureerde installatie geeft een lege lijst.

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
