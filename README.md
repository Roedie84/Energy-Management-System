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

### Arbitrage-laden (optioneel, standaard uit)

Naast "genoeg reserve aanhouden" en "verkopen wat er al is", kan de
integratie ook **actief bijkopen** tijdens een goedkoop kwartier, puur
omdat er later diezelfde dag een bekend duurder kwartier aankomt — ook
als de bestaande reserve al genoeg is om te overbruggen ("genoeg om te
overbruggen" en "winstgevend om nu meer te kopen" zijn onafhankelijke
vragen). Staat achter een eigen schakelaar,
`switch.arbitrage_laden` — **standaard uit**, bewust opt-in omdat dit
nieuw, echt-geld-gedrag is.

Alleen actief als de projectie, ná laad/ontlaad-verlies, een minimale
marge overhoudt:

```
netto_eur_per_kwh = (geleerd_rendement × beste_resterende_verkoopprijs_vandaag)
                    − huidige_prijs
```

Moet minimaal `MIN_ARBITRAGE_MARGIN_EUR_PER_KWH` (3 cent/kWh) opleveren
— een buffer tegen onzekerheid in de prijsvoorspelling en de
rendementsschatting.

**Zon-prioriteit** (expliciet gevraagd: "tijdens goedkope uren vooral
zonne-energie blijft opslaan"): het gewenste laadvermogen
(`manual_charge_power`) wordt eerst verminderd met het **live
zonoverschot** (PV-productie minus werkelijk huishoudverbruik, met
`pv_power_sensor_entity` geconfigureerd) — alleen het overblijvende gat
wordt daadwerkelijk van het net gekocht. Is het zonoverschot al groter
dan het gewenste vermogen, **en zou de accu anders in de gewone
`smart`-modus terechtkomen**, dan gebeurt er niets: die modus vangt de
zon toch al zelf op via P1-volgend laden, geen reden om dat te
verstoren met een geforceerde manual-modus.

**Uitzondering, gevonden n.a.v. een gerapporteerd geval (v0.63.59/.60):**
"accu wordt weer ingesteld op smart_discharging terwijl ik juist wil
doorladen" — de zon-prioriteit-aanname hierboven ging er stilzwijgend
van uit dat de terugval-modus altijd `smart` zou zijn. Zou de accu bij
het uitblijven van arbitrage in plaats daarvan `smart_discharging`
("laden uitstellen") ingaan, dan klopt die aanname niet — die modus
dekt alleen het huishoudverbruik en laadt (bevestigd met de gebruiker)
juist **niet** bij vanuit een zonoverschot.

v0.63.59 loste dit eerst op door in dat geval het volle gewenste
laadvermogen via **manual**-modus in te kopen — teruggekoppeld dat dit
de verkeerde modus was ("moet naar smart niet naar manual"): er is
namelijk helemaal geen actieve netaankoop nodig (het zonoverschot dekt
het doelvermogen al volledig), dus manual-modus afdwingen was zwaarder
dan nodig. v0.63.60 schakelt in dit specifieke geval in plaats daarvan
gewoon over naar de gewone **`smart`**-modus (reden:
`arbitrage_solar_capture`) — die vangt het zonoverschot vanzelf op via
P1-volgend laden, precies zoals ze dat altijd al doet wanneer er geen
sprake is van "laden uitstellen". Geen handmatig commando, geen
expliciete netaankoop — dit voorkomt alleen dat `smart_discharging`
gratis zon zou laten liggen.

Zet **nooit** de winter-guard-vlag (`_grid_charged_today`) — dat
mechanisme bestaat om te voorkomen dat noodzakelijk gekochte energie
diezelfde dag met verlies wordt terugverkocht; arbitrage-laden koopt
juist *omdat* er een winstgevende verkoop aankomt, dus zou die vlag de
hele functie tegenwerken.

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

**Lege sleuven verdwijnen nu uit beeld (v0.63.52):** gevraagd — met 8
sleuven × 2 knoppen kan het dashboard er snel vol uitzien als de
meeste sleuven leeg zijn. Elke kaart heeft nu een
`visibility`-voorwaarde die rechtstreeks leest of die sleuf een
kandidaat heeft (`kandidaat_entity_id` niet `None`) — een lege sleuf
neemt geen ruimte meer in, en zodra er een nieuwe kandidaat instroomt
verschijnt de kaart vanzelf weer.

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
gedetecteerd, als attributen. Wél een `RestoreEntity` (in tegenstelling
tot de kandidatenlijst) — die geschiedenis moet wekenlang opbouwen, dat
mag een herstart niet resetten.

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
gesorteerd), weergegeven als een echte markdown-tabel.

**Echte oorzaak van de eerdere onleesbaarheid gevonden (v0.63.53):**
niet de tabelopmaak zelf (v0.63.52's omzetting naar een lopende lijst
loste het verkeerde probleem op) — de kaart zat in een grid-layout met
een **vaste hoogte** (`grid_options: rows: 5`) die te krap was voor het
aantal apparaatrijen, waardoor de tabel inklapte/overlapte. Vergeleken
met de wél goed werkende tabel op het "Advies"-tabblad (die geen vaste
hoogte heeft) en teruggezet naar een echte tabel, nu met
`grid_options: rows: auto` zodat de kaart automatisch meegroeit met
het aantal bevestigde apparaten.

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
