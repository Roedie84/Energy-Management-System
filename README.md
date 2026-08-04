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

### Grootverbruiker-bevestiging (optioneel, elk apart te configureren)

| Veld | Type | Betekenis |
|---|---|---|
| `dishwasher_power_sensor_entity` / `dishwasher_ready_sensor_entity` | vermogen / binary | Vaatwasser: apparaat-bewustzijn + grootverbruiker-bevestiging |
| `washing_machine_power_sensor_entity` / `washing_machine_ready_sensor_entity` | vermogen / binary | Wasmachine: idem |
| `quooker_power_sensor_entity` | vermogen | Quooker: bevestigd na 2 minuten aanhoudend gebruik |
| `airco_climate_entity` | climate | Airco: bevestigd via `hvac_action` (heating/cooling) |
| `oven_state_sensor_entity` / `kookplaat_state_sensor_entity` | sensor | Home Connect `operation_state` (bevestigd bij `Run`) |
| `appliance_notify_service` | tekst | Notify-service voor apparaat-klaar-meldingen én accumodus-wijziging-meldingen (leeg = pop-up in HA) |

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
