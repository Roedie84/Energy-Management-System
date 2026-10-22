# Leerlog Energy Management System

Doorlopende leerronde (elke 4 uur). Alleen gemeten getallen; KPI's in KPI.csv, referenties in BASELINE.md, voorstellen in VOORSTELLEN.md.

## 07-10 · samenvatting dag (3 tussenronden 23:15-23:45, eerste baseline uit ~10 d)
- Baseline: PV-MAE 10,5 % (30 d) / 5,2 % (7 d), bias −4,4/−1,7 %; tekortnachten 4/7 (2 economisch, 2 planning); MC 22:00 Brier 0,038 (n=8).
- −50 W P1-verschuiving 's nachts bleek bewust (`regelverschuiving_w` in de reserve) → L-EMS-001 vervallen; H-EMS-1 verworpen: planning-tekortnachten kwamen van `expensive_quarter_peak` (hersteld v5.28.4).
- PV-uurprofiel werkelijk/Solcast: middag 0,90-0,98, randuren 0,52-0,69 (integratie leert dit zelf). Meetbaarheid: MC-kans 22:00 niet bewaard → L-EMS-002.

## 08-10 03:40 · dagafsluiting 07-10
- Dag 07-10: PV 11,87 kWh (voorspeld 12,83, −7,5% bij 100% bewolking), import 0,72, export 2,23, accu 6,61 in / 5,67 uit, huis 9,41 kWh. Nacht 06→07 zonder tekort (SoC 30% om 09:00). 0× verkoop onder de reserve (harde regel gehaald). 15 herstarts.
- PV 30 d MAE 10,8% (bias −4,5), 7 d 5,9% (−2,4) → H-EMS-2 blijft: klein en stabiel. Bewolkt >70% bias −7,2 vs −4,6 (n=15/13), MAE gelijk 9,5% → geen bewolkingseffect op de fout.
- Verbruik (nieuw gemeten): uurprofiel MAE 0,13 kWh/u; nacht 22-09 bias −0,08 kWh (−3%) → reserve-invoer klopt. Dagtotaal −0,49 kWh/dag (mediaan per uur mist witgoed; reserve telt gepland witgoed apart).
- H-EMS-4 (nieuw): achteraf-optimum per uur over 4 dagen (29-09, 30-09, 01-10, 07-10; salderen = symmetrische prijs, slijtage 4,22 ct): werkelijk 1,16 € duurder dan zonder accu, optimum 2,20 € goedkoper. Bij 0 ct slijtage werkelijk ≈ zonder accu (+0,09/dag). Gat: zon opslaan bij ~30 ct levert onder salderen weinig; optimum laadt in de goedkoopste uren en levert in de piek. n=4, aannames (uur, perfecte kennis) → eerst 14 dagen meten, geen voorstel.
- Meetfout gevonden: `sensor.solaredge_production_energy` (cloud-dagteller) staat 00:04-07:07 op unknown → schaduw-dagrapport slaat nachtkwartieren stil over (dekking 80,6%, `kwartieren_gemeten` 76 is misleidend). Zichtbaar gemaakt in v5.45; instelling → L-EMS-003.
- Gebouwd **v5.45** (L-EMS-002): MC-kans 22:00 per avond bewaard + `mc_22u` in dagrecord + `kalibratie_22u` (Brier); dagrapport `kwartieren_bruikbaar/ongebruikt`. 4815 tests groen, workflow groen, HACS ververst.
- Lopend: nacht →08-10 om 04:00 verwacht tekort 0 (MC 2,4%; om 23:45 nog 0,31 kWh/41,7%) → toetsen na 09:00. 09-10 Solcast 1,8 kWh (somber): laadbesluit en reserve volgen.
- Cockpit LET OP 's nachts door tweede PV-voorspelling (forecast.solar) die elk ander uur `unavailable` is (01:04, 03:04) — externe bron, geen EMS-fout.

laatste ronde: 08-10 04:40, gemeten t/m 08-10 04:10

## 08-10 07:40 · tussenronde
- Geïnstalleerd: v5.45 (~06:23) en v5.46 (07:03). L-EMS-003 ingesteld om 07:04 (`pv_energy_sensor_entity` = Modbus-teller): kwartier 07:15 pv al `measured` (cloudteller was tot 07:07 unknown), dagopwek 0,0 → geen sprong. Dekking volgt in de dagafsluiting.
- L-EMS-004: sluipverbruik direct na update `normaal`, `methode_versie` 2, reeks en accumulator leeg → eerste meetpunt gehaald; referentie > 0 W pas na dagen.
- Nacht 07→08 (t/m 07:40): import 22-07 u 0,12 kWh, accu niet leeg (SoC 34% om 07:01) → geen tekort, zoals om 04:00 verwacht. Nacht-export 00-07 0,43 kWh (regelverschuiving −50 W nog actief; L-EMS-005 is een instelling bij Ruud).
- Verbruik tegen wandeling: beschikbaar 5,01 → 1,90 kWh (3,11 gebruikt) terwijl de korte-horizonbehoefte 2,82 daalde → 0,29 kWh (+10%) meer dan voorspeld.
- **H-EMS-5 (nieuw):** MC-tekortkans steeg 3% (04:00) → 96% (07:40) en het verhaal meldt "verwacht tekort tot het goedkope blok 0,61 kWh", maar dat getal is volledig de lange horizon (na 12:15): marge tot het blok zonder lange horizon +1,79 (22:00) → +1,50 kWh (07:42); `lange_horizon_extra` 1,85 → 2,11. MC rekent de lange horizon bewust mee (v5.40), maar `kalibratie_22u` (v5.45) toetst hem tegen de nacht 22-09 → appels/peren. Ook: de Brier 0,038 (n=8) is grotendeels van vóór v5.40; 07-10 22:00 (14,6%) is de eerste avond mét lange horizon.
- Kandidaat (zelf bouwen, rapportage/meetbaarheid, dagafsluiting): tekort en kans apart tot het blok en na het blok tonen + kalibratie op beide → L-EMS-006.
- Geen release (tussenronde, niets acuut).

laatste ronde: 08-10 07:40, gemeten t/m 08-10 07:42

## 08-10 ~10:30 · gebouwd door chatsessie (geen leerronde)
- **v5.47** uitgebracht (workflow groen, release v5.47, HACS ververst): L-EMS-006 (tekort/tekortkans tot het blok vs. na het blok, kalibratie 22:00 alleen tot het blok, nachtmelding tot het blok) en L-EMS-007 (water: m³/gal → liter, debiet → L/min, nieuwe dag alleen bij nieuwe `last_reset`/datum). Sturing, reserve, drempels en marges ongewijzigd. 24 nieuwe tests, 4855 groen.
- Live vóór bouw 10:08: MC 100%, verwacht tekort 1,0 kWh terwijl `nodig_kwh` 2,47 volledig lange horizon (2,468) was; `vandaag_liter` 0,06 (sensor 0,060 m³), trend −100%.
- Leerronde 11:40: L-EMS-006/007 niet opnieuw bouwen; na installatie meten zoals in VOORSTELLEN.md.


## 08-10 11:45 · tussenronde
- Geïnstalleerd: v5.47 (herstart 10:55). Herstarts sinds 07:40: 3 (08:55, 09:01, 10:55).
- **L-EMS-006 eerste meetpunt gehaald:** 11:41 `verwacht_tekort_tot_blok_kwh` 0, MC-stand 0% (vóór bouw 10:08: 100% / 1,0 kWh); `nodig_na_blok_kwh` 2,44 = `lange_horizon_extra` 2,441; beschikbaar 2,94 kWh. Kalibratie (Brier tot blok) pas na 7 avonden vanaf 08-10 22:00.
- **L-EMS-007 eerste meetpunt gehaald:** na herstart 10:55 (utility_meter kort 0,060 m³) `vandaag_liter` 60 = meter 60 L; laatste waarde in `geschiedenis_liter_per_dag` 357 = werkelijke 07-10 (357 L om 23:15). Groei per dagwissel toetsen na 00:00.
- Opgevallen (rapportage): `trend_procent` −84,5 vergelijkt het dagdeel (60 L om 11:40) met de mediaan van hele dagen (386,8, attribuut heet "gemiddeld") → overdag altijd sterk negatief. Kandidaat L-EMS-008 (zelf bouwen, dagafsluiting).
- **L-EMS-003:** meetlog "dekking 100%"; laatste kwartier 11:15 alle tellers `measured`. Dagdekking 08-10 in de dagafsluiting.
- Nacht 07→08 afgerond: geen tekort (dagrecord 07-10 `shortfall` false, 0 kWh). Tekortnachten laatste 7: 3 (4,24 kWh), ongewijzigd.
- PV t/m 11:41: 2,33 kWh tegen Solcast-actueel 2,75 (−15%); uurratio 09:00 0,67, 10:00 0,70 (geleerd profiel 07/08 UTC 0,68/0,90). EMS-dagvoorspelling 10,21, Solcast nu 11,49.
- Beslissingen sinds 07:40 alleen `default_smart` → 0× verkoop onder de reserve (harde regel gehaald).
- **L-EMS-005 ingesteld door Ruud:** regelsensor `sensor.hw_p1_vermogen_100w` −1003 W bij P1 −1023 W (+20 W, was +50). Nacht-export 00-07 meten in de dagafsluiting (basis 0,43-0,45 kWh).
- Lopend: laadblok 12:15; 09-10 zon 2,61 tegen verbruik 8,31 kWh (meetlog) → laadhoeveelheid en nacht 08→09 volgen.
- Geen release (tussenronde, niets acuut; v5.47 net geïnstalleerd).

laatste ronde: 08-10 11:45, gemeten t/m 08-10 11:42
## 08-10 13:45 (chatsessie)
- L-EMS-008 (watertrend gelijk-met-gelijk) gebouwd in v5.49, plus cockpit-balans pas "wijkt af" na 3 rondes/3 min en laatste oordeel 5 min vasthouden. Meten: trend overdag niet meer structureel sterk negatief (eerste 3 dagen na update vóór 20:00 geen trend); cockpit LET OP niet meer door korte zonwisselingen.

## 08-10 15:40 · tussenronde
- Geïnstalleerd: v5.52.1 (v5.49-v5.52.1 door chatsessie, alleen rapportage/meelezen). HA-herstarts sinds 11:45: 6 (12:16, 14:19, 14:59, 15:08, 15:25, 15:39), elk ~30 s `unknown`.
- Beslissingen 11:40-15:40: `default_smart`, plus 13:45-14:00 `grid_charging_low_solar` (1 kwartier, 20,7 ct = goedkoopste kwartier van het blok vanaf 12:15; morgen Solcast 2,39 kWh < drempel 5). Netimport 13-14 u 0,51 kWh. 0× verkoop onder de reserve (harde regel gehaald).
- PV t/m 15:41: 8,07 kWh tegen Solcast-tot-nu 8,65 (−6,7%); dagvoorspelling Solcast 10,92. SoC 27% (09-10 u) → 86% (15:40), 6,57 kWh beschikbaar voor nacht →09-10; MC tot blok 0%. Toetsen in de dagafsluiting.
- **Accurendement (nieuw gemeten):** AC in → AC uit (Zendure-tellers net-in/naar-huis) 30 d 215,6 → 176,7 kWh = **81,9%**, 7 d 84,1%; EMS-geleerd 84,2% (wordt overal gebruikt; optie 90% alleen terugval). v5.50 momentane omzet laden 83,2% · ontladen 93,7% (retour 78%, n=67/142, 1 middag). Geleerde waarde klopt met de tellers → geen voorstel.
- **L-EMS-007** na herstart 15:39 opnieuw goed: utility_meter 0,105 m³ → `vandaag_liter` 105. **L-EMS-008** (v5.49) eerste meetpunt: overdag `trend_procent` null met toelichting (nog geen 3 dagen profiel) i.p.v. −84%.
- v5.50-52.1 (meelezen) eerste stand: 192/192 rondes, latentie 16 ms, 96,9% gelijk; beste bron Zendure-integratie (64 tegen 130 W naast de stekker). Opvallend: `opslagmodus` flash (smartMode 0) en 13 relaiswissels; hoort bij stap 2 (chatsessie), niets gebouwd.
- Logboek: 1× sjabloonfout `bedrag_per_dag_eur` (15:39, Proefstand-kaart) — al opgelost in v5.52.1 in `dashboard_template.yaml`; het dashboard in HA draait nog de oude kaart.
- Geen release (tussenronde; v5.49-52.1 vandaag al uitgebracht en geïnstalleerd).

laatste ronde: 08-10 15:40, gemeten t/m 08-10 15:44

## 08-10 19:40 · tussenronde
- Geïnstalleerd: v5.53.4 (v5.53-5.53.4 door chatsessie: meelezen, witgoedstatus, tekst, recorder). Herstarts sinds 15:40: 3 (16:31, 17:41, 18:31/18:36). Logboek: 0 EMS-fouten.
- Dag t/m 19:00: PV 9,58 kWh (Modbus) tegen Solcast 10,2 (−6,1%); import 1,28 / export 1,27 kWh (00-19 u). Beslissingen 15:40-19:40 alleen `default_smart` → 0× verkoop onder de reserve (harde regel gehaald).
- Nacht →09-10 om 19:40: beschikbaar 5,01 kWh, basis tot blok 11:45 4,18, zon 0,43 → marge tot blok ≈ +1,26 kWh; MC tot blok 0,1%. Reserve 8,64 (+45%, 3 tekortdagen) → geen verkoop. Toetsen in de dagafsluiting van 09-10.
- **Nieuw opgemerkt (externe instelling, 18:26):** zendure_ha regelt nu op `sensor.hw_p1_regel_zonder_quooker_piek` (template, zonder Quooker-piek); EMS `control_p1_sensor_entity` staat nog op `hw_p1_vermogen_100w`. Beide −30 W in rust → `regelverschuiving` blijft goed gemeten. Gevolg: Quooker-pieken gaan bewust naar het net. P1 18:20-19:42 per kwartier import 6-18 Wh → geen merkbare import. Quooker-import per dag meten in de dagafsluiting. Recorder bewaart de templatesensor niet (alleen begintoestand).
- **H-EMS-6 (nieuw):** MC-stand tot het blok springt na huishoudpieken kort omhoog terwijl de nacht ruim haalbaar is: 15:54-16:01 21-26% (na 2,4-4,8 kW 15:45-15:51), 17:18-17:27 89-92% (na koken ~1,7 kW 16:47-17:13), 17:58-18:00 55% (Quooker 2,35 kW 17:48-17:56); daarbuiten 0-1%. Oorzaak in de code: livecorrectie = mediaan van 4 monsters/30 min, max +1,5 kWh, vervaagt over 4 u — springt in als ≥2 van 4 monsters hoog zijn, dus juist ná de piek. Sturing niet geraakt (geen verkoop mogelijk), maar `mc_22u`/kalibratie pakt de waarde van 22:00: een piek om 21:45 vervuilt de Brier. Toets: per avond de MC-stand 21:50-22:10 naast `mc_22u`; afwijking > 20 pp = vervuild meetpunt.
- Lopende hypotheses: H-EMS-2 (PV-bias klein, stabiel), H-EMS-4 (achteraf-optimum, 14 dagen), H-EMS-6 (MC-livecorrectie). H-EMS-3 loopt nu via L-EMS-006 (Brier tot blok).
- Meetbaarheid: Solcast-limiet 10/10 om 18:36 bereikt ("polling limit exhausted") → voorspelling morgen bevroren op de laatste ophaalbeurt; telt mee bij de PV-fout van 09-10.
- Geen release (tussenronde, niets acuut).

laatste ronde: 08-10 19:40, gemeten t/m 08-10 19:44

## 08-10 23:40 · tussenronde
- Geïnstalleerd: v5.56 (v5.54 marginale slijtage 4,2 ct in de sturing op verzoek van Ruud, v5.55-56 statistieken/rapportage; chatsessie). HA-herstarts sinds 19:40: 5 (19:51, 20:19, 21:12, 22:00, 22:02). Logboek: 0 EMS-fouten.
- Beslissingen 19:40-23:40 alleen `default_smart` → 0× verkoop onder de reserve (harde regel gehaald). v5.54 (sturen op marginale slijtage) had vanavond nog geen arbitragekwartier; effect meten in de dagafsluitingen (aantal niet-smart-besluiten, verkocht met winst).
- **L-EMS-005 eerste effectmeting (avond):** export tijdens ontlading 20-23 u 27/23/24 Wh/u (basis ~60 Wh/u bij −50 W). Nacht 00-07 volgt in de dagafsluiting (basis 0,43 kWh).
- Avond 19-23 u: accu-ontlading 1,39 kWh, import 0,14, export 0,11 → huis ~355 W gem. (geleerd nachtverbruik 306 W). Beschikbaar 5,01 → 3,54 kWh; nodig tot blok 2,72 → marge +0,82 kWh (om 19:40 geschat +1,26). MC tot blok 0%.
- **H-EMS-6 toets 22:00 (eerste avond met `mc_22u`):** MC-stand 21:12-22:10 doorlopend 0,0% (ook na de herstarts 22:00/22:02) → meetpunt niet vervuild. Wel 23:00-23:21 een sprong naar 1,2-4,4% zónder huishoudpiek (huis 340-390 W 22:30-23:00, daarna 155 W): de livecorrectie reageert dus ook op een avond boven het profiel, niet alleen op pieken. Klein; H-EMS-6 blijft lopen.
- Meetbaarheid: `mc_22u_per_avond` staat niet in attributen of diagnostics; pas zichtbaar in het dagrecord van 09-10 (09:00). Kandidaat (zelf bouwen, meetbaarheid): laatste avondstand tonen in `kalibratie_22u`. Bouwen in een dagafsluiting.
- Geen release (tussenronde, niets acuut; v5.54-5.56 vandaag al uitgebracht en geïnstalleerd).

laatste ronde: 08-10 23:40, gemeten t/m 08-10 23:44

## 09-10 03:40 · dagafsluiting 08-10
- Dag 08-10: PV 9,58 kWh (day-ahead Solcast 10,21 → −6,1% bij 96% bewolking), import 1,46, export 1,53, accu 6,56 in / 5,85 uit, huis 8,80 kWh; accu max 86% (niet vol). Beslissingen: `default_smart` + 1× `grid_charging_low_solar` (13:45) → 0× verkoop onder de reserve (harde regel gehaald). 20 HA-herstarts. Nacht 07→08 geen tekort; tekortnachten 7 d nog 3 (4,24 kWh).
- PV 30 d MAE 9,5% (bias −6,2), 14 d 5,5% (−2,7), 7 d 6,0% (−2,5); 10 van de laatste 14 dagen te hoog voorspeld. H-EMS-2 (klein, stabiel) blijft; integratie leert zelf −5,7%.
- Verbruik: uurprofiel MAE 0,155 kWh/u (07-10: 0,105), dag +0,41 kWh boven profiel. Nacht 22-09 opvallend stabiel: 7 nachten 2,40-2,66 kWh (gem. 2,48).
- H-EMS-4 (achteraf, uur, 4,22 ct): 08-10 werkelijk +0,03 € t.o.v. zonder accu, optimum −0,61 €; prijs 22,0 ct (14 u) tot 40,9 ct (20 u). 5 dagen samen werkelijk +1,19 €, optimum −2,81 €. Gat zit in laden in het middagdal en leveren in de avondpiek; de reserve (+40-45% marge, lange horizon) hield verkoop tegen — bewust. n=5, door tot 14 dagen.
- Quooker (19:40-opmerking): de nachtimport (~12 Wh/u) is vrijwel geheel het opwarmen van de Quooker (~6 Wh per keer, 2× per uur, 5-minutenstatistiek) — vóór en ná de regelsensor-wissel van 18:26 gelijk; de Zendure kan pulsen van ~12 s niet volgen. ~0,3 kWh/dag, geen voorstel.
- **L-EMS-005 effect (nacht):** export tijdens ontlading 00-03 u 27/22/22 Wh/u (was 59-65) → −60%. Volledige nacht 00-07 in de volgende ronde.
- **L-EMS-003:** dagrapport 08-10 nog 27× `pv_onbekend` (00-07, cloudteller tot 07:04); vannacht 03:15 pv `measured` → nacht werkt. Dagdekking 09-10 is de echte toets.
- **Meetfout gevonden en gebouwd (L-EMS-009, v5.57):** dagrapport 08-10 `kwartieren_gemeten` 74 van 96. Oorzaak in de code: na een herstart is er geen beginstand, dus valt het kwartier van elke herstart weg (18 kwartieren met een herstart). v5.57 bewaart de tellerstanden per grens en rekent dat kwartier alsnog uit (alleen bij precies 1 kwartier en dezelfde tellers; accutellers `partially_estimated`). Plus `kwartieren_niet_gemeten`/`_over_herstart` en `kalibratie_22u.laatste_avond` (kandidaat van 23:40). 4997 tests groen, workflow groen, HACS ververst.
- **L-EMS-007 dagwissel geverifieerd:** `geschiedenis_liter_per_dag` +1 waarde (215 L = utility_meter last_period 0,215 m³). Water loopt sinds 03:07 ~9 L/min (161 L om 03:45) — tijdstip gelijk aan de vorige ontharder-regeneratie (29-09 03:07); herkenning volgende ronde toetsen.
- **Nieuw voorstel L-EMS-010:** sinds v5.55 heten de nachten →03-10 en →04-10 "verkocht met winst … bewust, geen stuurfout", maar die verkoop gebeurde onder de reserve door de piekregel-bug (hersteld v5.28.4, zie 07-10 23:45). Voorstel: verkoop onder de reserve nooit als "bewust" labelen.
- Nacht 08→09 om 03:41: beschikbaar 2,51, nodig tot blok 12:15 1,73 → marge +0,78 (23:40 geschat +0,82); MC tot blok 0%. 09-10 zon 2,39 kWh (somber).

laatste ronde: 09-10 03:40, gemeten t/m 09-10 03:50

## 09-10 07:40 · tussenronde
- Geïnstalleerd 06:02: **v5.57** (L-EMS-009). HA-herstarts sinds 03:50: 4 (06:03, 06:57, 07:02, 07:42; installaties EMS/Stormchase/Gold Scalper) → goede toets voor L-EMS-009 in het dagrapport 09-10.
- **L-EMS-005 geverifieerd (nacht 08→09):** export 00-07 0,163 kWh (basis 0,433 → −62%), 17-31 Wh/u. Import 00-07 0,186 kWh, waarvan 0,118 in de twee kwartieren hieronder; rest 10-17 Wh/u = Quooker-niveau → niet meer netimport.
- **Eerste arbitragekwartieren na v5.54:** 2× `battery_saved_for_peak` (03:45 22,42 ct, 04:45 22,76 ct = de twee goedkoopste nachtkwartieren; ochtend 25-31 ct). Huis ~240 W uit het net, ~0,12 kWh bewaard. Overig alleen `default_smart` → 0× verkoop onder de reserve (harde regel gehaald).
- Nacht 08→09: om 07:42 beschikbaar 1,47 kWh, blok 12:15, zon somber → marge klein; MC tot blok 0%. Tekort ja/nee toetsen om 11:40.
- **v5.57 `kalibratie_22u.laatste_avond`** werkt: 08-10 22:00 kans 0% (tot blok), incl. lange horizon 100%, beschikbaar 4,06. Dagrecord (Brier) om 09:00.
- **Ontharder 03:07** herkend (`waarschijnlijk_waterontharder` true, 154 L in 38 min, vorige 29-09 03:07), maar dezelfde regel zegt `bron` null, zekerheid "onbekend", reden "geen herkenbaar patroon": `classify_water_session` krijgt de ontharder-vlag niet mee (coordinator.py ~33990). Rapportagefout → L-EMS-011 (zelf bouwen, dagafsluiting).
- Logboek: 1× `GacsAssessmentSensor` update 0,61 s bij de start (07:42); volgen of het terugkomt buiten herstarts.
- Hypotheses: H-EMS-2, H-EMS-4, H-EMS-6 ongewijzigd (geen nieuwe dag/avond). Geen release (tussenronde, niets acuut).

laatste ronde: 09-10 07:40, gemeten t/m 09-10 07:45

## 09-10 11:40 · tussenronde
- Geïnstalleerd: v5.57; **v5.57.1** (zelfbeoordeling-cache, chatsessie 09:28) staat klaar in HACS. HA-herstarts sinds 07:45: 2 (10:09, 10:40). Logboek: 1× `GacsAssessmentSensor` 2,3 s bij de start van 10:40 — dat lost v5.57.1 op; geen andere EMS-fouten.
- **Nacht 08→09 afgerond: geen tekort.** Om 09:00 accu 23 % (1,12 kWh beschikbaar); import 22-09 0,268 kWh, waarvan 0,118 de twee `battery_saved_for_peak`-kwartieren (03:45/04:45). Export 22-09 0,270 kWh (17-34 Wh/u, regelverschuiving 20 W). Om 22:00 MC tot blok 0 % → kwam uit.
- **Correctie verwachting:** het dagrecord met `mc_22u` ontstaat bij de **datumwissel (00:00)**, niet om 09:00: het record van datum D draagt de nacht die op D 09:00 afliep en de MC-stand van D−1 22:00. Record 08-10 (00:00 vannacht) kreeg dus de avond van 07-10 (nog zonder v5.45) → `kalibratie_22u.nachten` 0 is correct. Eerste Brier-paar: 10-10 00:00 (avond 08-10, 0 %, geen tekort). Geen bug.
- Beslissingen 07:45-11:42 `default_smart`, sinds 11:30 `battery_saved_for_peak` (accu haalt het blok niet: rest 0,86 kWh naar de duurste kwartieren, huis nu uit het net bij 22,6 ct) → 0× verkoop onder de reserve (harde regel gehaald).
- Donkere dag: PV t/m 11:43 0,296 kWh tegen Solcast-tot-nu 0,547 (−46 %, dag 2,68). Blok schoof 12:15 → 14:30 (08:15) → 14:45 (08:45). MC tot blok 0 % (07:42) → 39,8 % (11:42), deterministisch tekort tot blok 0,33 kWh: echt (zon), geen H-EMS-6-sprong. Overdag kan dit geen tekortnacht worden.
- MC-drempel nagerekend: kans = P(behoefte > beschikbaar + 0,5 kWh) — zelfde grens als een tekortdag (v5.36). Mediaan 1,21 > 0,86 beschikbaar maar < 1,36 → 39,8 % klopt.
- Meetlog: dekking 96 % (759 evaluaties) na 2 herstarts; dagrapport 09-10 (L-EMS-009) in de dagafsluiting van 10-10.
- Hypotheses H-EMS-2, H-EMS-4, H-EMS-6 ongewijzigd (geen nieuwe dag/avond). Geen release (tussenronde, niets acuut; v5.57.1 nog niet geïnstalleerd).

laatste ronde: 09-10 11:40, gemeten t/m 09-10 11:44

## 09-10 15:40 · tussenronde
- Geïnstalleerd: **v5.62** (v5.57.1-v5.62 via chatsessies). HA-herstarts sinds 11:44: 6 (12:11, 12:25, 12:40, 12:51, 13:55, 14:43). Logboek: geen EMS-fouten na 14:43; meetlog dekking 97 % (1016 evaluaties).
- **L-EMS-010 geverifieerd:** nachten →03-10 en →04-10 heten nu `onbekend` ("niet na te gaan of dat boven de reserve lag: reserve of laadstand ontbreekt in het dagverloop"), `tekortnachten_verkocht_met_winst` 0. Geen "bewust" meer. Kanttekening: de leerronde van 07-10 toonde uit de recorder dat het onder de reserve was; het dagverloop van toen mist die velden → onbekend is het eerlijkste wat de code kan.
- Beslissingen 11:44-15:42: `battery_saved_for_peak` tot 12:15, `default_smart`, 2× `grid_charging_profitable` (13:28-13:45, 14:45-15:34; import 13-15 u 1,78 kWh) → accu 20 → 37-38 %. 0× verkoop onder de reserve (harde regel gehaald). Planning: nog 16:00 laden (18,8 ct), daarna smart tot morgen 12:00, laadblok morgen 12:00-15:00 (12,5-12,9 ct).
- Donkere dag: PV t/m 15:00 0,99 kWh (Modbus), Solcast day-ahead 2,68, nu 2,16 → dag ~1,2 = **−55 %** t.o.v. day-ahead. Past bij H-EMS-2 (somber → te hoog); weegt mee in de dagafsluiting.
- MC tot "blok" 100 % (mediaan tekort 7,0 kWh, beschikbaar 2,42): het blok van vandaag (12:15-16:45) loopt nog, dus valt de horizon terug op 09:00 met de tekst **"prijzen morgen nog onbekend"** — terwijl nordpool `tomorrow_valid` true is en de planning morgen al kent. Rapportagefout in `_monte_carlo_horizon_kiezen` (terugval ook bij een lopend blok). De uitleg zegt ook "3x onverwacht stroom … terwijl de accu genoeg had moeten hebben" terwijl de 3 nachten nu economisch/onbekend heten. → L-EMS-012 (zelf bouwen: rapportage, dagafsluiting).
- Verwachting vannacht: tekortnacht waarschijnlijk (accu leeg rond 22 u, nachtprijs 13-15 ct = goedkoopste van het etmaal) → soort zou `economisch` moeten worden. Toets 10-10. Eerste `kalibratie_22u`-paar 10-10 00:00 (avond 08-10, 0 %, geen tekort).
- Hypotheses H-EMS-2, H-EMS-4, H-EMS-6 ongewijzigd. Geen release (tussenronde, niets acuut).

laatste ronde: 09-10 15:40, gemeten t/m 09-10 15:44

## 09-10 19:40 · tussenronde
- Geïnstalleerd: **v5.68.1** (v5.63-v5.68.1 via chatsessies: airco/klimaat, v5.68 temperatuurmodel in de nachtreserve + bewolking uit het ensemble). HA-herstarts sinds 15:44: 7 (16:16, 17:24, 18:02, 18:36, 19:00, 19:07, 19:29). Logboek: 0 EMS-fouten; Solcast-limiet 10/10 bereikt (extern).
- Beslissingen 15:44-19:44: `default_smart`, `grid_charging_profitable` 16:00-16:15 (20,2 ct spot), `battery_saved_for_peak` 16:45-17:15 en 17:30-17:45 (24,7-28,4 ct; bewaard voor 18-20 u 32-36 ct) → 0× verkoop onder de reserve (harde regel gehaald). 16-19 u: import 2,00 kWh, accu 0,59 in / 1,01 uit.
- PV dag 1,24 kWh (Modbus, af) tegen Solcast day-ahead 2,68 → **−54 %**; tweede donkere dag op rij met grote overschatting (H-EMS-2 weegt mee in de dagafsluiting).
- **v5.68 eerste meetpunt:** `temperatuur_extra_kwh` 0, `temperatuur_model_kw` null (model acht zichzelf nog niet bruikbaar), `airco_ochtend_extra_kwh` 0 → reserve vanavond ongewijzigd door v5.68. Meetbaar via diagnostics (`coordinator.last_reserve_margin_breakdown`).
- Nacht →10-10 om 19:42: beschikbaar 1,56 kWh, nodig tot blok 10:30 3,55 → verwacht tekort 1,99 kWh, soort `economisch` (live, nachtprijs 12,8-14,4 ct spot = goedkoopst tot het blok). MC tot blok 100 %. Toets 10-10: tekortnacht ja, soort economisch.
- **L-EMS-012 deels:** nu het blok van vandaag voorbij is valt de horizon goed op het blok van morgen (10:30); de terugvalfout zit alleen in de uren dat een blok loopt. De "Let op: 3x onverwacht stroom … accu genoeg had moeten hebben"-zin staat er nog (1 economisch + 2 onbekend).
- **Nieuw H-EMS-7 → voorstel L-EMS-013:** de marge-opslag `shortfall_bonus_percent` telt alle 3 tekortnachten (+15 %, 0,84 kWh vanavond), ook de economische. Een economische tekortnacht zegt niets over een te krappe reserve. Ruud beslist (marge = sturing).
- Geen release (tussenronde, niets acuut).

laatste ronde: 09-10 19:40, gemeten t/m 09-10 19:44

## 09-10 23:40 · tussenronde
- Geïnstalleerd: **v5.69** (v5.68.1-v5.69 via chatsessie: accumodules, airco). HA-herstarts sinds 19:44: 3 (19:48, 20:53, 22:43). Logboek: 0 EMS-fouten (diagnose "fout 1" = REST-time-out P1-API bij de start 22:43, extern).
- Beslissingen 19:44-23:52 alleen `default_smart` → 0× verkoop onder de reserve (harde regel gehaald). P1 19-23 u: import 0,203 kWh (0,153 in 22-23 u), export 0,081.
- **Accu leeg om 22:34**, met een SoC-sprong 11 → 7 % en `available_kwh` −0,26 daarna. Volgens de uuranalyse liep module AB3000 00996 als eerste leeg (0 % tegen 10-11 %, laagste cel 2,73 V, cel-delta 0,46 V): het totaal-SoC (gemiddelde) overschatte de bruikbare inhoud. Beschikbaar 19:42 1,56 → 22:00 0,35 kWh (~0,5 kW avondverbruik; geleerd nacht 306 W).
- **H-EMS-8 (nieuw):** bij een achterblijvende module overschat het totaal-SoC de laatste ~0,3 kWh → beschikbaar en marge zijn vlak boven leeg te optimistisch. Toets in de dagafsluiting: SoC-sprongen ≥ 3 pp omlaag bij < 15 % en de spreiding tussen de modules (recorder). Module-instelling zelf ligt bij de uuranalyse.
- Nacht →10-10: verwacht tekort tot blok 10:30 **2,38 kWh, soort `economisch` (live)**; MC tot blok 100 % doorlopend sinds 19:48 → `kalibratie_22u.laatste_avond` 100 % (beschikbaar 0,35). H-EMS-6: 22:00-stand niet vervuild. Eerste Brier-paar (avond 08-10) om 00:00.
- v5.68 temperatuurmodel: `temperatuur_extra_kwh` 0, `temperatuur_model_kw` null (nog niet bruikbaar); reserve 6,43 kWh = 4,59 × 1,40 (basis 10 + tekort 15 + nasleep 15 %).
- Lopend: L-EMS-013 (open, Ruud). H-EMS-2, H-EMS-4, H-EMS-6 ongewijzigd. Geen release (tussenronde, niets acuut).

laatste ronde: 09-10 23:40, gemeten t/m 09-10 23:52

## 10-10 03:40 · dagafsluiting 09-10
- Dag 09-10: PV 1,24 kWh (day-ahead Solcast 2,39 → **−48 %**, 100 % bewolking), import 6,37, export 0,53, accu 3,30 in / 5,38 uit, huis 9,16 kWh. 22 HA-herstarts. Beslissingen 23:52-03:50 alleen `default_smart`; hele dag 0× verkoop onder de reserve (harde regel gehaald).
- PV 30 d MAE 10,7 % (bias −7,4), 14 d 8,1 % (−5,4), 7 d 12,1 % (−8,5). Door de −48 % houdt de integratie de vlakke biascorrectie in (`learned_bias_percent` null: twee soorten dagen) — zo ontworpen (v3.33). H-EMS-2 bijgesteld: klein op gewone dagen (7 d t/m 08-10: −2,5 %), groot op een zeer donkere dag (n=1); volgen of donkere dagen (< 3 kWh voorspeld) stelselmatig te hoog zijn.
- **L-EMS-009 geverifieerd:** dagrapport 09-10 gemeten 93/96 (was 74), `kwartieren_over_herstart` 20 bij 22 herstarts, 3 niet gemeten. **L-EMS-003 geverifieerd:** `pv_onbekend` 0 (was 27). **L-EMS-002 geverifieerd:** eerste Brier-paar (avond 08-10 0 %, geen tekort) → `kalibratie_22u.nachten` 1, Brier 0.
- **H-EMS-8 getoetst (10 d recorder):** 2× een SoC-sprong ≥ 3 pp omlaag vlak boven leeg, beide keren aan het eind van de ontlading: 30-09 04:11 (12 → 7 %) en 09-10 22:34 (11 → 7 %; module 00996 12 → 0 %). Elke keer ~0,35 kWh minder dan beschikbaar leek. n=2 → voorstel L-EMS-014 (reserve/beschikbaar = sturing, Ruud beslist).
- Tekortnachten 7 d nu 2 (beide `onbekend`, piekregel-bug 03/04-10); de economische nacht viel uit het venster → marge-opslag 10 %. Nacht 09→10 loopt: tekort tot nu 1,19 kWh (live economisch, verwacht 1,27 tot blok 10:30), MC 100 % → komt morgen terug in L-EMS-013.
- **Gebouwd v5.69.1** (L-EMS-011 ontharder als bron, L-EMS-012 horizon-reden bij lopend blok + Let-op-zin per soort): alleen rapportage, 10 nieuwe tests, 5275 groen, workflow groen, HACS ververst.
- Niet gemeten: H-EMS-4 (achteraf-optimum) voor 09-10 — de kwartierprijs (`zonneplan_current_quarter_hourly_electricity_tariff`) en nordpool staan niet als reeks in de recorder; eerdere rondes rekenden uit attributen. Verbruiksprofiel-MAE overgeslagen (donkere dag, netladen).
- Hypotheses: H-EMS-2 (bijgesteld), H-EMS-4 (n=5, wacht op prijsreeks), H-EMS-8 (bevestigd n=2 → L-EMS-014).

laatste ronde: 10-10 03:40, gemeten t/m 10-10 03:50

## 10-10 07:40 · tussenronde
- Geïnstalleerd: v5.69 (v5.69.1 van 03:50 nog niet). Geen HA-herstarts sinds 03:50; logboek 0 EMS-fouten (wel extern: SolarEdge-Modbus 1× verbinding weg 07:21, Solcast-limiet nog van gisteren). Meetlog dekking 100 %.
- Beslissingen 03:50-07:44 alleen `default_smart` (sinds 22:44), export 0 → 0× verkoop onder de reserve (harde regel gehaald).
- **Nacht 09→10:** accu leeg sinds 22:34 (7 %, beschikbaar 0). Import 22-07 1,81 kWh (0,15-0,28 per uur), tekort tot nu 2,07 kWh; resterend tot blok 10:30 0,33 → ~2,40 tegen de voorspelling van 23:40 (2,38): **verwacht tekort klopt binnen 0,02 kWh**. MC 22:00 100 % → eerste Brier-paar met tekort om 09:00 (verwacht 0).
- **Gevonden:** `verwacht_tekort.tekort_soort` sprong van "economisch" (03:50) naar null, omdat de soort op het nog resterende tekort (< 0,5 kWh) wordt bepaald i.p.v. lopend + resterend. De nachtafsluiting van 09:00 rekent met de gemeten nacht → dagrecord niet geraakt. → L-EMS-015 (gepland, rapportage).
- Toets 11:40: nacht →10-10 ingedeeld als `economisch` (laadbesluit "loont_niet", volging sinds 09-10 09:00 heel), Brier 22u met 2 paren.
- PV vandaag: Solcast day-ahead 9,1 kWh (nog niet ververst vandaag). H-EMS-2, H-EMS-4, H-EMS-8 ongewijzigd; L-EMS-013/014 open. Geen release (tussenronde, niets acuut).

laatste ronde: 10-10 07:40, gemeten t/m 10-10 07:44

## 10-10 11:40 · tussenronde
- Geïnstalleerd: **v5.71.1** (v5.70 verkoopreserve + L-EMS-013, v5.71 cockpit). Niet: v5.72.0 (chatsessie 11:27: L-EMS-014/015, onbekend telt niet in de marge) en v5.72.1 (deze ronde). HA-herstarts 08:20, 08:44, 09:18, 10:52. Logboek: 0 EMS-fouten (1× REST-time-out P1-API, extern).
- Beslissingen 07:44-11:44 alleen `default_smart` → 0× verkoop onder de reserve (harde regel gehaald). Accu 7 → 23 % op zon (laden vanaf 09:57); plan: laden uit het net 12:00-13:00 en 13:30-15:00 (12,5-13,0 ct) tot 100 %.
- **Nacht 09→10 gemeten:** tekort 2,363 kWh (live `tekortnacht_tot_nu`) tegen voorspeld 2,38 (23:40) → fout −0,02 kWh. **Correctie vorige ronde:** de nacht komt pas om 00:00 in het dagrecord (`reserve_daily_records` met datum 10-10), dus ook het Brier-paar (22:00 = 100 %, tekort) en de soort zijn pas in de dagafsluiting van 11-10 te toetsen, niet om 09:00.
- PV tot 11:50 2,85 kWh tegen Solcast 2,72 → +5 % (zonnig, bewolking 14 %). H-EMS-2: gewone dag klein, n=1 deel van een dag.
- **Gevonden (acuut) → L-EMS-016, gebouwd v5.72.1:** om 11:18 sprong MC vaste extra 1,9 → 25,8 kWh en diepste tekort 6,3 → 30,0 kWh: de geplande vaatwasser (12:16) telde in elk van de 22 uursegmenten, omdat de start per segment opnieuw "begin segment + seconden" was. Verder dan een uur vooruit telde hij juist nergens. Zelfde wandeling voedt de reserve → release in de tussenronde (5 tests, suite 5351 groen, workflow groen, HACS ververst).
- L-EMS-012 horizon-reden geverifieerd (blok loopt: "het goedkoopste blok loopt nu"). L-EMS-014/015 gebouwd in v5.72.0 (chat). Meetbaarheid: diagnostics heeft nu `prijsreeks` → H-EMS-4 (achteraf-optimum) in de dagafsluiting van 11-10 opnieuw proberen.
- Hypotheses: H-EMS-2 (PV donkere dagen), H-EMS-4 (achteraf-optimum, wacht op prijsreeks-toets). H-EMS-8 afgerond in L-EMS-014.

- Naschrift 12:15: **v5.73.0** geïnstalleerd (chatsessie 11:58: sparen in het goedkope blok; bevat v5.72.0 en v5.72.1). MC vaste extra 2,34 kWh, diepste tekort 6,70 met de vaatwasser nog gepland → L-EMS-016 eerste meetpunt gehaald.

laatste ronde: 10-10 11:40, gemeten t/m 10-10 12:15

## 10-10 15:40 · tussenronde
- Geïnstalleerd: **v5.76.1** (v5.74-v5.76.1 via chatsessies: verbruiksaudit, niet ontladen vóór netladen in hetzelfde blok, recorder-attributen, bootstraps). HA-herstarts 12:04, 13:37, 14:41. Logboek: 0 EMS-fouten (P1-REST-time-out 1×, extern).
- Beslissingen 12:15-15:45: `grid_charging_profitable` (12:10-13:00, 13:15-13:20, 13:30-15:06), kort `default_smart`, `sparen_in_blok` sinds 15:06 (blok 14:30-17:15, netladen 16:00; ontladen 13,4 ct tegen rondtrip 20,0 ct). **0× verkoop onder de reserve** (harde regel gehaald): export 12-15 u 0,049 kWh, ontladen alleen 0,115 kWh (13-14 u).
- Laadblok: netimport 12-15 u 6,50 kWh, accu laden 6,22 → SoC 23 → 97 %. MC-tekortkans 0 %, beschikbaar 7,52 kWh.
- PV 08-15 u 7,23 kWh (Modbus) tegen Solcast-intraday 6,73 → **+7 %** (ochtend −12 %, middag +28 %; MAE 0,19 kWh/uur). Day-ahead 9,1 → dagcijfer in de dagafsluiting. H-EMS-2 (donkere dagen te hoog): vandaag een gewone dag, telt als controle.
- L-EMS-013 (marge-opslag) meten op de avond: tekortnachten 7 d nu 1 (`onbekend`) → opslag verwacht 0 %. `last_reserve_margin_breakdown` nu leeg (reserve "geen blok" tijdens het lopende blok) → toets 19:40/23:40.
- L-EMS-014/015/016: geen nieuwe meetgelegenheid (geen lege accu, geen tekortnacht, vaatwasser klaar 14:47 zonder uitgestelde start > 1 uur).
- Hypotheses: H-EMS-2, H-EMS-4 (achteraf-optimum, toets dagafsluiting 11-10). Geen release (tussenronde, niets acuut).

laatste ronde: 10-10 15:40, gemeten t/m 10-10 15:45

## 10-10 19:40 · tussenronde
- Geïnstalleerd **v5.78.0** (v5.77/5.78 airco bij open raam, chatsessie). HA-herstarts 16:19, 16:40, 18:07. Logboek: 0 EMS-fouten.
- Beslissingen 15:45-19:45: `sparen_in_blok`/`grid_charging_profitable` tot 16:41, daarna `default_smart`, `expensive_quarter_soc_protected` (17:30, 17:49-18:27, 19:23) en **één verkoopkwartier `expensive_quarter` 18:45-19:00**: P1-export 18-19 u 0,483 kWh bij 0,016 kWh zon, beschikbaar 6,83 → 6,22.
- **Harde regel getoetst:** volgens de eigen verkoopreserve (v5.70, tot het blok × 1,25) mocht dit (anders was de verkoop geblokkeerd). Maar het spaarplan meldde om 18:34 "haalt het blok van 10:45 niet: 7,0 in de accu, **8,1 kWh nodig tot het blok**", terwijl de verkooptoets toen ≤ 5,5 tot het blok rekende. Om 19:41: nodig incl. marge 6,69 > beschikbaar 5,79 (zonder marge 5,35 < 5,79). De sturing toetst elke minuut en verkocht door tot 19:00 (beschikbaar 6,22) → verkoopreserve om 18:59 < 6,22; om 19:10 6,97 (uuranalyse), om 19:41 6,69: **sprong van ≥ 0,7 kWh binnen ~10 min**. Of het huis vóór 10:45 tekortkomt, meet de nacht → **H-EMS-9**, voorstel **L-EMS-017** (open), meetbaarheid **L-EMS-018** (gepland, dagafsluiting).
- Meetbaarheid: sinds v5.76.0 geen attributen meer in de recorder → de verkooptoets van 18:45 is niet te reconstrueren; `safe_sell_shadow` telt alleen het terugvalpad (0 momenten).
- **L-EMS-013 geverifieerd:** marge dynamisch 0 % bij 1 tekortnacht `onbekend`; totaal 25 % (basis 10 + onbeschermde nacht 15).
- PV dag 9,35 kWh tegen Solcast day-ahead 9,1 (+3 %) en intraday 8,50 (+10 %); tweede bron 10,31 (−9 %). H-EMS-2 (donkere dagen te hoog): gewone dag, controle.
- Hypotheses: H-EMS-2, H-EMS-4 (achteraf-optimum, dagafsluiting 11-10), **H-EMS-9 (nieuw):** de behoefte tot het blok wordt 's avonds onderschat in de verkooptoets (5,11 om 16:45 → 5,35 om 19:41 ondanks ~1,6 kWh verbruik ertussen; spaarplan 8,1). Geen release (tussenronde; niets acuut aantoonbaar, sturing = voorstel).

laatste ronde: 10-10 19:40, gemeten t/m 10-10 19:45

## 10-10 23:40 · tussenronde
- Geïnstalleerd **v5.80.0** (v5.79.0 19:45 en v5.80.0 20:20, chatsessies). HA-herstarts 19:48, 20:26. Logboek: 0 EMS-fouten.
- **Correctie 19:40:** volgens v5.79.0 (CHANGELOG, chatsessie) zakte de verkoop van 18:45-19:00 van 6,91 naar 6,22 kWh tegen een reserve tot het blok van **6,78** → **0,56 kWh onder de reserve (harde regel geschonden, 1 kwartier)**. Oorzaak: het vermogen (2,4 kW vast) werd niet op de vrije ruimte afgestemd. Opgelost in v5.79.0 (`_begrens_tot_verkoopruimte`). KPI rechtgezet.
- Beslissingen 19:45-23:45: `default_smart`, `expensive_quarter_soc_protected` (21:24-21:26, 22:15-22:45) en **`expensive_quarter` 22:45-23:00**: P1-export 0,50 kWh, beschikbaar 3,89 → 3,20. Ontlaadgrens 22:59: vrij 0,05 kWh, `mag_verkopen` true → eerste verkoop onder v5.79: stopte op de verkoopreserve tot het blok (≈ 2,4-2,6 × 1,25), **0× onder de reserve**. Export rest van de avond 0,12 kWh, import 0,06.
- **H-EMS-9:** om 23:41 spaarplan en verkooptoets gelijk (nodig tot blok 2,40, beschikbaar 3,11; marge 0,71 kWh). Avondverbruik 19:41-23:41 ≈ 2,2 kWh (5,79 → 3,11 min 0,50 verkocht). Toets: nacht → blok 10:45 (dagafsluiting 11-10). MC tot blok 0 %.
- L-EMS-018 deels gedekt door v5.79 (dagverloop per kwartier `mag_verkopen`, `beschikbaar_kwh`, `reserve_kwh` = totaal; diagnostics `ontlaadgrens` = alleen laatste moment). Rest: verkoopreserve tot het blok en `vrij_kwh` per kwartier → scope verkleind, blijft gepland voor de dagafsluiting.
- v5.80.0 (accubesparing met rondreisverlies): effect meten in de dagafsluiting (dagstijging kostprijsmodel tegen eigen afrekening; basis 01-10..09-10: € 5,23 tegen € 2,57).
- Hypotheses: H-EMS-2 (PV donkere dagen), H-EMS-4 (achteraf-optimum, dagafsluiting 11-10), H-EMS-9 (behoefte tot blok). Geen release (tussenronde, niets acuut: de verkoopfout is al opgelost in v5.79).

laatste ronde: 10-10 23:40, gemeten t/m 10-10 23:45

## 11-10 03:40 · dagafsluiting 10-10
- Dag 10-10: PV 9,35 kWh (day-ahead tracker 10,00 → **−6,5 %**, bewolking 52 %; Solcast-vandaag 9,05 → +3,3 %), import 9,10 (netladen blok 6,50), export 1,71, accu 8,96 in / 4,76 uit, huis 12,5 kWh, piek 8451 W (record). 12 HA-herstarts, logboek 0 EMS-fouten. Verkoop onder de reserve: **1 kwartier** (18:45, 0,56 kWh, opgelost v5.79); 22:45 en de nacht tot 04:05 niet (alleen `default_smart`).
- PV 30 d MAE 10,5 % (bias −8,0), 14 d 8,2 % (−6,2), 7 d 12,4 % (−8,9; de −48 % van 09-10 telt mee). H-EMS-2 (donkere dagen te hoog) ongewijzigd n=1; integratie houdt de biascorrectie bewust in (twee soorten dagen).
- **H-EMS-4 afgerond (meetbaar):** de integratie rekent het achteraf-optimum zelf (`nabeschouwingen`, 31 dagen). 10-10: leverde € 0,39 van € 0,48 (gemist 0,09, alles reserve). 7 d: € 3,10 van € 6,51 (**48 %**), gemist 3,39 = reserve 0,48 + voorspelling 2,91; 14 d 32 % → beter. Besparing t.o.v. zonder accu 10-10 € 1,06 (05-09: −0,26..+0,30). Dagrapport-schaduw 4,22 ct: kosten € 0,26.
- Toets verkooptiming (dagverloop, 13 d): export in een minder duur kwartier dan de dagtop kostte maar ~€ 0,41 (10,95 kWh); waar de rest van het gemiste bedrag zit, is met momentopnamen niet te ontleden → meetbaarheid **L-EMS-019** (gepland).
- Nacht 09→10 in het dagrecord: tekort 2,363 kWh `economisch`, MC 22:00 100 % → Brier 0 (n=2). Tekortnachten 7 d: 2 (onbekend + economisch); reserve te hoog 0. Dekking dagrapport 99,2 %.
- **H-EMS-9 (nacht 10→11 loopt):** 23:41 nodig tot blok 2,40 bij 3,11; 04:03 nodig 1,29 bij 2,16 (marge 0,87, was 0,71). Accu 23:40→03:39 −0,95 kWh (~237 W DC). Uitslag na het blok (10:45) in de ronde van 11:40.
- v5.80 eerste avond: kostprijsmodel +€ 0,37 (20:29→03:39); vergelijking met eigen afrekening over ≥ 3 dagen.
- **Gebouwd v5.81.0 (L-EMS-018):** verkooptoets en spaarplan per kwartier in het dagverloop + kleinste marge bij export (negatief = onder de reserve). Alleen meten; 5 tests, suite 5519 groen, workflow groen, HACS ververst.
- Hypotheses: H-EMS-2 (PV donkere dagen), H-EMS-9 (behoefte tot blok, uitslag 11:40). Open voor Ruud: L-EMS-017.

laatste ronde: 11-10 03:40, gemeten t/m 11-10 04:05

## 11-10 07:40 · tussenronde
- **v5.81.0 door HACS gedownload om 04:59, maar nog niet actief**: geen HA-herstart sinds 10-10 20:26, `diagnose_gezondheid` meldt nog v5.80.0 → L-EMS-018-velden pas na de volgende herstart. Logboek 0 EMS-fouten (wel Solcast API-limiet 10/10 om 00:05, extern).
- Beslissingen 04:05-07:45: alleen `default_smart`; accu 35 → 24 %, beschikbaar 2,16 → 1,30 kWh (~236 W). P1 04-07 u import 0,045 / export 0,068 kWh (alleen regelruis), **0× verkoop, 0× onder de reserve**, geen netimport in dure kwartieren (prijs 28 ct < drempel 36,8).
- **Spaarplan-verloop getoetst:** 04:03 nodig tot blok 1,29 → 07:42 0,40; voorspeld verbruik 04:03→07:42 **0,89 kWh, werkelijk 0,86 (−3 %)**. Marge tot het blok 0,90 kWh (04:03: 0,87). MC tot blok 0 % (p90 0,77 kWh < 1,30).
- **H-EMS-9 tussenstand** (uitslag 11:40): huisverbruik uit de accu 18:45 → 07:42 = 6,91 − 1,30 − 1,38 verkocht = **4,23 kWh**; + 0,40 tot het blok ≈ **4,6 kWh** tegen spaarplan 18:34 **8,1** en verkooptoets ≤ 5,5. Eerste beeld: de behoefte werd 's avonds niet onderschat; het spaarplan van 18:34 zat ~3,5 kWh te hoog. Bevestigt de richting van L-EMS-017 (één behoefte), niet een te krappe verkooptoets.
- Hypotheses: H-EMS-2 (PV donkere dagen), H-EMS-9 (uitslag 11:40). Geen release (tussenronde, niets acuut).

laatste ronde: 11-10 07:40, gemeten t/m 11-10 07:45

## 11-10 11:40 · tussenronde
- HA-herstarts 08:40 en 10:15 → actief **v5.81.1** (L-EMS-018-velden nu live; nog geen verkoopkwartier om te toetsen). v5.82.0/v5.83.0 (chatsessies, 10:28/11:02) gedownload, niet actief. Logboek 0 EMS-fouten (Zendure 2× ServerDisconnected, extern).
- Beslissingen 07:45-11:40: `default_smart` → `sparen_in_blok` 10:45 → `grid_charging_profitable` 11:30. **0× verkoop, 0× onder de reserve**; P1-import 07-10 u 0,06 kWh (regelruis), geen netimport in dure kwartieren.
- **H-EMS-9 uitslag (verworpen):** accu haalde het blok met **0,95 kWh** beschikbaar (laagste punt 08:49-10:45, daarna dekte PV het huis). Behoefte uit de accu 18:45 → 10:45 = 6,91 − 0,95 − 1,38 verkocht = **4,58 kWh** tegen verkooptoets ≤ 5,46 en spaarplan 18:34 **8,1 (+77 %)**. De avondbehoefte werd dus niet onderschat; het spaarplan overschatte. Geen tekortnacht (MC 22:00 0,1 % → klopt).
- Gevolg L-EMS-017: de oorspronkelijke richting (verkoop blokkeren als het spaarplan "haalt het niet" zegt) had hier ~1 kWh terecht verkochte energie tegengehouden → voorstel bijgesteld: spaarplan laten rekenen met de behoefte van de verkooptoets (één functie), niet andersom.
- Opgemerkt: sturingsreserve springt kort +1,4 kWh (09:14-09:24 4,91 → 6,33; 10:39-10:44 4,99 → 6,13) en keert terug; geen gevolg (geen verkoop), volgen of dit witgoed-/airco-verwachting is (v5.83 nog niet actief).
- Hypotheses: H-EMS-2 (PV donkere dagen). H-EMS-9 gesloten. Geen release (tussenronde, niets acuut; vandaag al 3 releases via chat).

laatste ronde: 11-10 11:40, gemeten t/m 11-10 11:40

## 11-10 15:40 · tussenronde
- **20 HA-herstarts 11:47-15:33** (supervisor "Restarting homeassistant", elke 5-15 min; geen crash) → actief **v5.85.1** (luchtreiniger, chatsessies). Logboek 0 EMS-fouten. Sturing liep door: SoC 23 % (11:30) → 100 % (15:29) zonder hapering; per herstart ~30 s `unknown`.
- Beslissingen 11:40-15:40: `grid_charging_profitable`/`sparen_in_blok` tot 15:29, daarna `default_smart`. Netladen 11-15 u **7,49 kWh**, accu vol 1 min vóór het einde van het blok (15:30) → goed getimed. **0× verkoop, 0× onder de reserve**; export 11-15 u 0,20 kWh, daarna PV-overschot bij volle accu (accu 0 W).
- PV 08-15 u 5,81 kWh (Modbus) tegen Solcast-intraday 5,79 → **+0,5 %** (ochtend −7,5 %, middag +5,2 %; MAE 0,09 kWh/uur). Zelfde patroon als 10-10 (ochtend te hoog, middag te laag), kleiner. Day-ahead → dagafsluiting.
- L-EMS-018-velden: nog geen verkoopkwartier sinds activering → eerste toets bij de avondverkoop (19:40/23:40).
- Hypotheses: H-EMS-2 (PV donkere dagen). Geen release (tussenronde, niets acuut). Open voor Ruud: L-EMS-017.

laatste ronde: 11-10 15:40, gemeten t/m 11-10 15:40

## 11-10 19:40 · tussenronde
- 10 HA-herstarts 15:49-18:09 (supervisor, geen crash), daarna rustig; actief v5.85.1, 0 EMS-fouten. Sturing liep door (per herstart ~30 s `unknown`).
- Beslissingen 15:40-19:56: `default_smart` → `grid_charging_profitable` 16:14-16:45 (accu 99 %) → `discharging_window`/`expensive_quarter_soc_protected` 17:01-19:45 zonder export (accu dekt huis, 99 → 86 %) → **`expensive_quarter` 19:45:06-19:53:06** → `default_smart`. P1 15:40-19:44 export 0,80 kWh (0,73 PV-overschot vóór 17:30, daarna 0,08 regelruis), import 0,08.
- **Eerste avondverkoop onder v5.81 (L-EMS-018):** 19:45 verkooptoets nodig tot blok 4,18 (×1,25 = 5,23), beschikbaar 6,57 → 1,34 kWh vrij (deel na het blok, terugladen 39,8 ct < verkoop 42,1 ct); plan 19:45-20:15 verkopen. Verkocht **0,23 kWh** (P1, 8 min ~1,85 kW). 19:56: nodig tot blok **4,99** (+0,81 in 11 min terwijl de accu 0,35 leverde) → 6,24 nodig bij 6,22 → gestopt. Grens geraakt op −0,02 kWh = binnen de stap van `beschikbaar` (~0,09 kWh) → **geen schending**; marge per kwartier toetsen in de dagafsluiting (L-EMS-018-velden).
- **H-EMS-10 (nieuw):** de reserve/behoefte springt binnen minuten ±0,6-1,0 kWh (17:04-19:56 9×: 6,3-6,8 ↔ 7,78 = plafond), zonder verbruiksstap. Vermoeden: een live-invoer die × ~15 u tot het blok gaat, waarschijnlijk `regelverschuiving_kw` (regel-P1 − P1 per ronde; 50 W × 15,6 u × 1,25 ≈ 1 kWh). Niet te toetsen: uitsplitsing (`regelverschuiving_w`, `ongekapt_kwh`) staat niet in een attribuut met historie en beide P1-sensoren zijn uitgesloten van de recorder → meetbaarheid **L-EMS-020** (gepland, dagafsluiting). Gevolg vanavond: ~1,1 kWh minder verkocht dan toegestaan (~€ 0,03; huis niet geraakt).
- Hypotheses: H-EMS-2 (PV donkere dagen), H-EMS-10 (springende behoefte). Geen release (tussenronde, niets acuut). Open voor Ruud: L-EMS-017.

laatste ronde: 11-10 19:40, gemeten t/m 11-10 19:56

## 11-10 23:40 · tussenronde
- 8 HA-herstarts 21:02-23:31 (supervisor); actief **v5.86.0** sinds 23:31 (L-EMS-021, chatsessie), **leermodus aan tot 12-10 05:00** (eenmalig, Ruud). 0 EMS-fouten.
- Beslissingen 19:56-23:40: `default_smart`, één verkoopkwartier `expensive_quarter` **20:08:48-20:13:48: 0,11 kWh** (beschikbaar 5,96 → 5,79). Avond totaal 0,34 kWh verkocht. Rest: export 0,095 (regelruis), import 0,056.
- **Harde regel:** 20:09 niet direct toetsbaar (de kwartiermarge van L-EMS-018 staat alleen in de diagnostics, niet via de MCP). Terugrekening: nodig tot blok 23:35 2,28 + huisverbruik 20:14-23:35 1,64 = 3,92 × 1,25 = 4,90 < 5,79 → **0× onder de reserve** (afgeleid). Kwartiermarge bevestigen in de dagafsluiting.
- **H-EMS-10 bevestigd in omvang:** 9 sprongen ≥ 0,6 kWh in 4 u (grootste 21:42 +1,87, 4,98 → 6,85), zonder verbruiksstap; de 4,99 van 19:56 die de verkoop stopte, past niet bij 3,9 die terugrekening om 20:14 geeft. L-EMS-020 (meetbaarheid) blijft eerste stap.
- Nacht 11→12: beschikbaar 4,15, nodig tot blok (11:30) 2,28 → marge 1,87; MC 22:00 0 % (beschikbaar 4,67). Dagrecord 11-10 (nacht 10→11, MC 10-10) komt na middernacht in de kalibratie → nachten 2 is nu correct (code nagelezen).
- L-EMS-021: plan toont 6 laadkwartieren, maar leermodus tot 05:00 → effect pas vanaf de nacht 12→13 meetbaar.
- Hypotheses: H-EMS-2 (PV donkere dagen), H-EMS-10 (springende behoefte). Geen release (tussenronde, niets acuut). L-EMS-017 akkoord → bouwen in de dagafsluiting.

laatste ronde: 11-10 23:40, gemeten t/m 11-10 23:45

## 12-10 03:40 · dagafsluiting 11-10
- Dag 11-10: PV 7,49 kWh (day-ahead tracker 9,07 → **−17,4 %** bij 13 % bewolking: een heldere dag te hoog, niet alleen donkere dagen), import 8,66 (netladen 11-15 u 7,49), export 1,90, accu 7,40 in / 5,36 uit, huis 12,2 kWh. **40 HA-herstarts** (supervisor, 08:40-23:31; 12-10 03:33 nog 1), logboek 0 EMS-fouten. Besparing t.o.v. zonder accu € 1,09 (10-10 € 1,06).
- PV 30 d MAE 10,7 % (bias −8,2), 14 d 8,8 % (−6,9), 7 d 14,7 % (−11,6) → slechter (09-10 −48, 11-10 −17). H-EMS-2 verbreed: ook heldere dagen te hoog (11-10); n=2 in 7 d, nog geen voorstel.
- **Harde regel 11-10: 0× onder de reserve** (afgeleid): 19:45-19:53 0,23 kWh (stop 19:56 op −0,02 = binnen de stap van `beschikbaar`), 20:09-20:14 0,11 kWh (terugrekening 4,90 < 5,79). `marge_bij_export_min_kwh` zat alleen in de diagnostiek → nu als attribuut `verkoopkwartieren` (v5.87).
- Nacht 10→11 geen tekort (MC 22:00 0,1 %) → Brier 0, n=3. Tekortnachten 7 d: 1 (10-10 economisch). Nacht 11→12 03:45: nodig tot blok 1,28 bij 3,28 (marge 2,00), MC 0 %; 23:45-03:55 alleen `default_smart`, export 0,07 (regelruis).
- H-EMS-10 opnieuw gezien: sturingsreserve 19:40-19:42 6,68 → 7,70 → 7,04 → 6,65 en 20:07-20:19 7,78 → 7,22 → 7,56 zonder verbruiksstap. Toetsen met de nieuwe `reserve_sprongen` na installatie van v5.87.
- Niet gemeten: dagrapport-dekking (`laatste_dagrapport` leeg na de herstart van 03:33), nabeschouwing 11-10 en 7 d (alleen in de diagnostiek; vanaf v5.87 `nabeschouwing_7d` als attribuut).
- **Gebouwd v5.87.0** (03:53, workflow groen, HACS ververst; niet geïnstalleerd): L-EMS-017 (spaarplan tot het blok = behoefte van de verkooptoets, verkooptoets ongewijzigd) + L-EMS-020 (reservesprongen met uitsplitsing) + meetattributen op Diagnose sturing. 10 nieuwe tests, suite 5599 groen. L-EMS-019 niet gebouwd: botst met de privacykeuze van v5.28 (geen kwartierverbruik in de export) → open voor Ruud.
- Hypotheses: H-EMS-2 (PV te hoog, nu ook heldere dag), H-EMS-10 (springende reserve; meetbaar na installatie). Open voor Ruud: L-EMS-019.

laatste ronde: 12-10 03:40, gemeten t/m 12-10 03:55

## 12-10 07:40 · tussenronde
- 2 HA-herstarts (06:14-06:15, 06:47-06:49); actief **v5.88.0** (andere sessie 06:46; bevat v5.87). 06:15:48 accu kort "offline" (Zendure status 0) direct na de herstart, daarna normaal. Geen EMS-fouten.
- Beslissingen 03:45-07:42: alleen `default_smart` (2× ~30 s `unknown` bij herstart). Import 0,073 kWh, export 0,106 kWh (regelruis, 5-14 Wh/kwartier). Geen netladen in de nacht (leermodus tot 05:00).
- **Nacht 11→12 zonder tekort:** 07:30 beschikbaar 2,42 kWh, nodig tot blok (11:30) 0,36 → marge ~2,0 (MC 22:00 0 %, uitkomst nee → Brier 0, n=4).
- **Harde regel 11-10 nu direct getoetst (v5.87-attribuut `verkoopkwartieren`):** echte verkoopkwartieren 19:45 (230 Wh export) en 20:00 (114 Wh) hadden kleinste marge +0,47 en +0,035 kWh → **0× onder de reserve** (bevestigt de afleiding van 03:40).
- **Meetfout gevonden:** 8 kwartieren tonen `marge_bij_export_min_kwh` < 0 (11-10 09:00, 09:30, 10:45, 11:00, 11:15, 18:00, 22:30; 12-10 06:15 −1,51) terwijl er per kwartier maar 6-18 Wh werd teruggeleverd (P1-teller). Eén ronde met ≥ 100 W export (regelpiek, herstart) telt al als "verkoop". 8 van 8 negatieve meldingen vals, 2 van 2 echte verkopen goed → **L-EMS-022** (zelf bouwen: export-kWh per kwartier, alleen ≥ 25 Wh telt; dagafsluiting).
- `nabeschouwing_7d` nu leesbaar: gemist t.o.v. achteraf-optimum 05..11-10 € 0,78 / 0,67 / 0,89 / 0,39 / 0,29 / 0,09 / −0,26 (7 d € 2,85 van € 7,18 haalbaar). Dalend. 11-10 negatief: het optimum rekent zonder netladen (`sta_netladen_toe=False`, bewust), terwijl 11-10 7,49 kWh van het net laadde → op netlaaddagen geen bovengrens; `netarbitrage_eur` staat niet in het attribuut → meenemen in L-EMS-022.
- H-EMS-10: `reserve_sprongen` 0 sinds installatie (06:49-07:42, ochtend, geen avond) → eerste echte toets bij de avond van 12-10.
- Hypotheses: H-EMS-2 (PV te hoog), H-EMS-10 (springende reserve). Geen release (tussenronde; meetfout niet acuut, sturing raakt hij niet; vandaag al v5.87 + v5.88).

laatste ronde: 12-10 07:40, gemeten t/m 12-10 07:42

## 12-10 11:40 · tussenronde
- 7 HA-herstarts (08:26-10:53) voor v5.89-v5.92 (andere sessie); actief **v5.92.0**. 0 EMS-fouten (1× trage logboeksensor 2,0 s, 09:40). Solcast 429 sinds 10:54 (extern; laatste verversing 07:52).
- 07:40-11:45: import 0,099 kWh, export 0,119 kWh (regelruis); accu laadt in het blok vanaf 11:30 (57 %, 4,06 kWh beschikbaar). Geen echte verkoopkwartieren → harde regel niet geraakt.
- L-EMS-022: 10:45 opnieuw valse vlag (−1,01 kWh bij 14 Wh export) → 9 van 9 vals.
- PV t/m 11:45 2,80 kWh tegen Solcast 2,58 voor dezelfde uren (+8,5 %, intraday, verouderd door 429) → vandaag tot nu géén overschatting (H-EMS-2 tegenvoorbeeld, n=1 halve dag).
- Nieuw meetbaar (v5.91 planvolging): 3 kwartieren, 66,7 % volgens plan. Classificatiefout gevonden: 11:15 oorzaak "accu" met status "verklaard" → **L-EMS-023** (zelf bouwen, dagafsluiting).
- H-EMS-10: `reserve_sprongen` 0 (ochtend); avond 12-10 blijft de toets.
- Hypotheses: H-EMS-2 (PV te hoog), H-EMS-10 (springende reserve). Geen release (tussenronde; niets acuut; vandaag al v5.87-v5.92).

laatste ronde: 12-10 11:40, gemeten t/m 12-10 11:45

## 12-10 15:40 · tussenronde
- 6 HA-herstarts (12:38, 13:06, 13:29, 14:45, 15:02, 15:43); actief **v5.93.2** (andere sessie, 13:27). 0 EMS-fouten in het systeemlog; Solcast 429 (extern, laatste verversing 07:52).
- Accu 57 % (11:44) → **100 % om 14:29** (7,78 kWh) alleen op zon; daarna zon naar het net: export 14-15 u 1,06 kWh, import 11:45-15:00 ~0,05 kWh. Verkoopkwartieren 12:30-15:15 hadden marge +4,3..+6,5 kWh → **0× onder de reserve**. Geen nieuwe negatieve vlag sinds 10:45 (L-EMS-022: 9 van 9 vals).
- **PV t/m 15:45 10,22 kWh tegen Solcast 10,36** voor dezelfde uren (dag 12,69 − rest 2,33) → −1,4 % (ochtend +8,5 %). Vandaag goed voorspeld; H-EMS-2 (te hoog) krijgt een tegenvoorbeeld (n=1 dag, verouderde Solcast-run).
- **Planvolging** (v5.93.1 bewaart over herstarts): 10 kwartieren, 50 % volgens plan; `oorzaken` geen 5 / verbruik 4 / accu 1, maar `afwijking_accu` 2 → nog een tegenstrijdig kwartier (status "afwijking accu", oorzaak verbruik). v5.93.2 voegde "sturing" toe; `oorzaak = max(zon, verbruik, rest)` staat nog los van de status (code 524c2e2 nagelezen) → L-EMS-023 blijft nodig.
- Nacht 12→13: MC 0 %, accu vol → geen tekort in zicht. H-EMS-10: `reserve_sprongen` leeg (nog geen avond sinds installatie) → toets in de ronden van 19:40/23:40.
- Hypotheses: H-EMS-2 (PV te hoog), H-EMS-10 (springende reserve). Geen release (tussenronde, niets acuut; vandaag al v5.87-v5.93.2). L-EMS-022/023 in de dagafsluiting.

laatste ronde: 12-10 15:40, gemeten t/m 12-10 15:45

## 12-10 19:40 · tussenronde
- 2 HA-herstarts (16:12, 18:35; andere integraties); actief **v5.93.2**, 0 EMS-fouten. Solcast-run nog van 07:52 (429).
- **PV dag 12-10: 11,75 kWh tegen Solcast 12,69 → −7,4 %** (15:45 nog −1,4 %; middag 1,53 tegen 2,33 verwacht). Weer te hoog, nu bij een heldere dag → H-EMS-2 houdt (verouderde run; dagafsluiting rekent de day-ahead tracker).
- 15:45-19:46: import 0,68 kWh, export 1,47 kWh. **Avondverkoop** 18:45-19:46 ~1,18 kWh bij 46-48 ct (18:45 526 Wh, 19:00 329, 19:15 27, 19:30 ~300), stop 19:45 op `expensive_quarter_soc_protected`.
- **Harde regel: 0× onder de reserve.** Kleinste marge in de echte verkoopkwartieren +0,33 / +0,006 / +0,028 kWh; 19:15 −0,02 bij 27 Wh (binnen de SoC-stap van `beschikbaar`, ~0,09 kWh per %). Live gevolgd 19:41-19:46: marge 0,17 → 0,09 → 0,03, verkoop stopte vóór 0.
- L-EMS-022: 4 nieuwe negatieve vlaggen 16:15-17:00 (−0,09..−0,87) bij 56/15/24/15 Wh export: accu ontlaadt dan ~0,9-1,4 kW **voor het huis** (stand niet "verkopen"), export = regeloverschot bij starten/stoppen. 13 van 13 negatieve vlaggen zonder verkoop; 16:15 (56 Wh) en 19:15 (27 Wh) halen de geplande 25-Wh-grens wél → bouw aangevuld: alleen kwartieren met stand verkopen/`mag_verkopen` tellen als verkoop, regeloverschot apart.
- H-EMS-10 (springende reserve), eerste avond na v5.87: `reserve_sprongen` 0; verkoopreserve daalde gelijkmatig 5,71 → 5,06 met `nodig_tot_blok` (4,39 → 4,05). Morgen weinig zon (Solcast 4,0 kWh, `nodig_na_blok` 5,19). Niet gezien (n=1 avond).
- Planvolging: 26 kwartieren, 30,8 % volgens plan; `afwijking_accu` 8 tegen `oorzaken.accu` 3 (17:45 "afwijking accu" met oorzaak zon) → L-EMS-023 blijft. Verkoopkwartieren tellen als afwijking (plan 0,4 kW, gemeten 2,4 kW): plan kent de verkoopbeslissing niet.
- MC 0 % (19:46). Hypotheses: H-EMS-2 (PV te hoog), H-EMS-10 (springende reserve). Geen release (tussenronde, niets acuut). L-EMS-022/023 in de dagafsluiting van 13-10.

laatste ronde: 12-10 19:40, gemeten t/m 12-10 19:46

## 12-10 23:40 · tussenronde
- 6 HA-herstarts (21:10, 21:52, 22:38, 22:40, 22:41, 23:17; o.a. Gold Scalper 2.3-2.4.1); actief **v5.93.3** (19:08, andere sessie), 0 EMS-fouten.
- 19:45-23:40: import 0,05 kWh, export 0,33 kWh; accu dekt het huis (53 → 52 % om 23:41).
- **Harde regel: 0× onder de reserve.** Verkoop 20:45 ~0,28 kWh bij 40 ct (`mag_verkopen`, marge +0,046, kleinste +0,016); 21:00 ~8 Wh met marge −0,03 bij `mag_verkopen` false = regeloverschot binnen de SoC-stap (L-EMS-022-patroon, nu 14 van 14 zonder echte verkoop). Daarna geen verkoop: beschikbaar 3,63 < reserve 7,78 (boven capaciteit).
- Nacht 12→13: MC 0 %, nodig tot blok (13-10 12:00) 2,50 bij 3,63 beschikbaar → marge 1,13 kWh; kalibratie 22:00 kans 0 % (Brier 0, n=3). Morgen Solcast 4,0 kWh, `nodig_na_blok` 5,18 → laadblok moet bijladen.
- **H-EMS-10** (springende reserve): 1 `reserve_sprong` om 23:18:20, 11 s na de eerste ronde na de herstart; behoefte 10,16 → 7,77 (lange horizon 6,95 → 5,18), reserve zelf gelijk (7,78, afgekapt). Herstartartefact, geen avondsprong (avond 19:46-23:18: 0). Meetbaarheid: eerste ronde na start markeren of overslaan → meenemen in L-EMS-023-bouw (zelf bouwen: meetfout).
- Planvolging dag 42 kwartieren 47,6 % (19:46-23:40: 12 van 16 volgens plan); `afwijking_accu` 9 tegen `oorzaken.accu` 4 → L-EMS-023 blijft.
- Hypotheses: H-EMS-2 (PV te hoog), H-EMS-10 (springende reserve; 1 avond zonder sprong). Geen release (tussenronde, niets acuut). L-EMS-022/023 in de dagafsluiting van 13-10.

laatste ronde: 12-10 23:40, gemeten t/m 12-10 23:41

## 21-10 19:40 · dagafsluiting-inhaalronde (gat 13-10 11:30 → 21-10; DAG 12..20-10 gemeten)
- Gemeten (HA-statistiek, dagarchief, nabeschouwing_7d, planvolging, MC-kalibratie): PV, net, accu, huis per dag 12..20-10; 12-10 overgenomen uit analyse/2026-10-13 (bestand verwijderd). Context: 4e accumodule 14-10 (nominaal 11,52 kWh, v5.97.1); chatsessies bouwden v5.95-v5.114.1.
- **PV day-ahead te hoog: 14 van 14 dagen negatief**, bias −17,3 % (14 d) / −17,4 % (7 d), mediaan −9 %; 30 d MAE 11,3 % bias −8,7 %. 17-10 −40 % (helder), 18-10 −40 %. `learned_bias_percent` null: correctie bewust ingehouden bij "twee soorten dagen" → H-EMS-2 bevestigd, voorstel L-EMS-025 (open). Vandaag t/m 19:00 5,03 tegen 7,82 kWh (−36 %).
- **Nabeschouwing 14..20-10: accu leverde € 6,98 van € 7,69 haalbaar = 91 %** (06..12-10: 70 %); gemist € 0,71, waarvan voorspelling € 1,11 en reserve € 0,40 (rest: netladen boven het optimum zonder netladen).
- **H-EMS-11 bevestigd (4/7 dagen):** ochtendpiek houdt 1,2-2,3 kWh vast (+€ 0,64-1,08), terwijl de nacht 1,2-1,5 kWh "te veel" ontlaadt (−€ 0,40-0,56); netto nacht+ochtend ~€ 0,3/dag → voorstel L-EMS-026 (open).
- **Harde regel:** `verkoopkwartieren` 20/21-10 leeg (0 verkoop, regeloverschot 0,20/0,16 kWh). Verkoop uit de accu (uurstatistiek) op 14, 15, 16, 17 en 19-10 (1,0-2,9 kWh/dag); verkoopreserve per kwartier voor die dagen niet meer leesbaar. 14-10 19:30-20:08 verkocht met beschikbaar 7,7→6,0 onder de getoonde totaalreserve 9,7→7,5 (incl. lange horizon). Geen tekortnacht 14..19-10; 20-10 0,05 kWh (zonder verkoop). Onbeslist → meetbaarheid L-EMS-027 (zelf bouwen).
- **H-EMS-10:** v5.98.1 (na herstart) en v5.99.11 (hysterese lange horizon, 47 sprongen op 17-10) gebouwd. Vandaag nog 29 "sprongen", alle met reserve gelijk (10,37 kWh, boven capaciteit) en bijdragen 0: de behoefte vóór marge schommelt 0,3-1,5 kWh per minuut; `grootste_onderdeel` zegt dan ten onrechte "lange_horizon" → meetfout, mee in L-EMS-027. Sturing raakt het niet (reserve afgekapt).
- L-EMS-023 **geverifieerd**: `oorzaken.accu` == `afwijking_accu` op 13..21-10 (9 dagen; 12-10 nog 4 tegen 9). L-EMS-022 **deels**: 0 valse verkoopvlaggen 20/21-10, maar geen echte verkoop in die dagen om te toetsen.
- Meetfout dagarchief (code nagelezen): `zon_verwacht_kwh` 0 op 19 en 20-10 (eerste kwartier 00:00 van de verwachting heeft nog geen zon) en `accu_opbrengst_eur` = kosten zonder accu − kosten, zonder voorraadverschil (20-10 −€ 1,02 terwijl er ~4 kWh extra in de accu stond) → L-EMS-024 (zelf bouwen).
- MC 22:00: Brier 0,144 (n=7, was 0); nacht →20-10 kans 100 % zonder tekortnacht. Planvolging 60,2 % (7 d). Niet gemeten: HA-herstarts (logboek na 13-10 19:48 leeg), verkoopmarge per kwartier 13..19-10.
- Hypotheses: H-EMS-2 (PV te hoog, bevestigd), H-EMS-11 (nacht ontlaadt wat de ochtend nodig heeft), H-EMS-12 (MC te stellig bij lage accu, n=1). Geen release (inhaalronde; vandaag al v5.114.1 door andere sessie).

laatste ronde: 21-10 19:40, gemeten t/m 21-10 19:00

## 21-10 23:40 · tussenronde
- 2 HA-herstarts (20:16, 20:58); actief **v5.115.0**, 0 EMS-fouten (alleen bronbuffer-WARNINGs bij de herstart). v5.115.1 (L-EMS-027) gereleased 22:23, nog niet geïnstalleerd; HACS ververst.
- **PV 21-10: 5,03 kWh tegen day-ahead 7,82 → −35,7 %** (15e dag op rij te hoog; H-EMS-2).
- 19-23 u: import 0,10, export 0,08, accu ontlaadt 2,41 kWh voor het huis. **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 0,25 kWh).
- 17:00-17:20 `battery_saved_for_peak`: 0,70 kWh import bij 38,4 ct terwijl de accu 5,2 kWh beschikbaar had, bewaard voor 17:30-17:45 (43-45 ct). Bewuste keuze; oordeel in de nabeschouwing van 21-10.
- Nacht 21→22: beschikbaar 1,38 kWh, nodig tot blok (10:45) 2,60 → marge −1,22; MC 100 %. Plan (gewijzigd 22:01, eerste nacht met v5.115.0-laadkosten): 00:30-03:30 sparen op 20 %, 03:45-05:30 laden (23-24 ct) tot 41 %, ochtendpiek (30-35 ct) uit de accu. Precies het L-EMS-026-patroon, nu door de lage stand afgedwongen → toets in de nabeschouwing 22-10.
- **H-EMS-12 aangescherpt:** MC rekent vanaf de huidige inhoud zonder geplande netlading; de tekortnacht telt "> 0,5 kWh bijgekocht met lege accu". Spaart het plan op 20 % (niet leeg), dan kans 100 % zonder tekortnacht (zoals →20-10) = definitieverschil, geen slechte voorspelling. Toets 03:40/dagafsluiting 22-10.
- Reservesprongen 21:18-23:00: 5, waarvan 4 met reserve gelijk (afgekapt) → v5.115.1 telt die apart; effect na installatie.
- Hypotheses: H-EMS-2 (PV te hoog), H-EMS-11 (nacht vs ochtendpiek), H-EMS-12 (MC-kalibratie: definitie). Geen release (tussenronde, niets acuut; v5.115.1 wacht op installatie).

laatste ronde: 21-10 23:40, gemeten t/m 21-10 23:43

## 22-10 03:40 · dagafsluiting 21-10
- Actief **v5.115.0**; v5.115.1 (L-EMS-027) staat klaar, niet geïnstalleerd → geen release (niet stapelen). 0 EMS-fouten; Solcast-limiet (10/10) en Zonneplan-sensoren even onbeschikbaar rond 00:02 (extern, bronbuffer vangt het op).
- Dag 21-10: PV 5,03 kWh (day-ahead 7,82 → −35,7 %), import 2,14, export 0,58, accu 3,33 in / 6,77 uit, huis 10,03 kWh. Planvolging 68,1 %. Geen tekortnacht (→21-10). **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 0,25 kWh).
- **H-EMS-2 sterker:** 15 dagen op rij te hoog; 7 d MAE/bias 21,3/−21,3 %, 14 d 19,3/−19,3 %, 30 d 12,1/−10,2 % (was 17,4/17,3/11,3). `learned_bias_percent` nog null → L-EMS-025 (open) blijft het voorstel.
- **H-EMS-11 (5 van 8 dagen):** 21-10 ochtendpiek 2,70 kWh vastgehouden (+€ 1,17), nacht 1,38 kWh te veel ontladen (−€ 0,48). Realisatie 7 d (15..21-10) 84 % (€ 7,15 van € 8,50; was 91 % over 14..20-10). Nacht 21→22 doet het L-EMS-026-patroon zelf (lage stand): 00:00-03:45 sparen op 21 % (0,61 kWh import bij ~24 ct), laden 03:45-05:30 tot 42 %, ochtendpiek uit de accu → uitslag nabeschouwing 22-10.
- **H-EMS-12:** avond 21-10 22:00 kans 100 % bij 1,84 kWh; accu staat op 21 % (boven min-SoC 15 %), import met niet-lege accu = geen tekortnacht volgens de definitie. Uitslag 09:00 → toets 11:40.
- Nieuw gezien: om 00:00:00 springt de lange horizon 5,39 → 7,12 kWh en 33 s later terug naar 5,17 (reserve 9,74 → 10,37 → 9,78) = dagwissel-artefact. Kort, maar telt als echte sprong; volgende middernacht nogmaals toetsen vóór een voorstel.
- Meetfout L-EMS-024 3e dag (zon_verwacht 0 op 19/20/21-10). 21-10 heeft geen kosten in het dagarchief (bewust: < 90 % kwartieren met prijs bij de prijsbronstoring). Bouw wacht tot v5.115.1 geïnstalleerd is.
- Hypotheses: H-EMS-2 (PV te hoog), H-EMS-11 (nacht vs ochtendpiek), H-EMS-12 (MC-definitie). Geen release.

laatste ronde: 22-10 03:40, gemeten t/m 22-10 03:43

## 22-10 07:40 · tussenronde
- Actief **v5.115.1** (geïnstalleerd, herstart 07:07); 0 EMS-fouten (alleen bronbuffer-WARNINGs Solcast/Zonneplan bij de herstart). Back-upvenster voorbij; geen release (tussenronde).
- **Nacht 21→22: gepland laden is niet gebeurd.** Plan (22:01/03:40): laden 03:45-05:30, om 05:56 nog 05:45-06:15. Werkelijk: accu 0 kWh geladen (grid_input 0), SoC 21 % → 18 % (07:43), beslissing hele nacht `battery_saved_for_peak`, `laadbesluit_sinds_9u` "loont_niet". Planvolging vandaag 50 % met 8 kwartieren "afwijking sturing", energieverschil +4,43 kWh. Import 23-07 u 1,35 kWh (03-07 u 0,73).
- **Oorzaak (code nagelezen, H-EMS-13):** de beslissing (`_dipbesluit`) rekent met het spaarplan dat sinds v5.87 de behoefte tot het blok schaalt naar de verkooptoets; het plan (`_plan_netregels` → `_plan_dip_laadt`) gebruikt per kwartier nog het eigen profiel. Grotere kwartierbehoefte in het plan → de beschikbare kWh dekt minder dure kwartieren → het "doelkwartier" is duurder → plan zegt laden, beslissing niet. Rendement, laadkosten (v5.115.0) en blok zijn in beide gelijk. Gevolg: plan en planvolging tonen een lading die de sturing nooit doet ("afwijking sturing" telt onterecht). Niet acuut (huis gedekt, geen verkoop) → **L-EMS-028** gepland voor de dagafsluiting, eerst offline nagerekend.
- H-EMS-11: het verwachte L-EMS-026-patroon kwam maar half: wel sparen op 21 %, geen nachtlading; de ochtendpiek (32-35 ct) draait op 0,92 kWh + net. Uitslag in de nabeschouwing 22-10.
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 0,02 kWh). Reservesprongen sinds 07:07: 0 (v5.115.1).
- H-EMS-12: tekortnacht tot nu 0 (accu 18 %, niet leeg); uitslag 09:00 → 11:40.
- Hypotheses: H-EMS-2 (PV te hoog), H-EMS-11 (nacht vs ochtendpiek), H-EMS-13 (plan ≠ beslissing bij dip-laden). H-EMS-12 loopt af na 09:00.

laatste ronde: 22-10 07:40, gemeten t/m 22-10 07:45

## 22-10 11:40 · tussenronde
- Actief **v5.116.0** (andere sessie, 08:36; geïnstalleerd, herstarts ~09:02 en ~11:03). 0 EMS-fouten; DNS-storing 10:24-10:40 (Zonneplan, Solcast e.a. via bronbuffer) en 2× "accu niet aanstuurbaar" (Zendure offline 10:50, 11:20) tijdens het laadblok — extern, laden liep door (11:30 −2381 W tegen plan −2386 W).
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 22-10 0,04 kWh).
- **Ochtendpiek 22-10 uit de accu:** import 07-10 u 0,10 kWh (07 u 0,02 · 08 u 0,05 · 09 u 0,03), SoC 18 → 14 %. Nacht 00-06 u 1,23 kWh import tegen ~23-24 ct (gespaard op 21 %). → H-EMS-11: het "sparen in de nacht, piek uit de accu"-deel werkte; de geplande nachtlading niet (H-EMS-13). Euro's in de nabeschouwing 22-10 (dagafsluiting 23-10).
- **H-EMS-12 (MC-definitie) 2e keer bevestigd:** avond 21-10 22:00 kans 100 % (tot blok), nacht →22 géén tekortnacht (accu niet leeg, < 0,5 kWh met lege accu). Met →20 al eens: n=2/2. Brier wordt ~0,25 (n=8) zodra →22 in `kalibratie_22u` staat (nu nog 0,144 n=7). Oorzaak: MC rekent vanaf de huidige inhoud zonder geplande netlading/sparen; de definitie telt sparen-op-20 % niet als tekort. Kandidaat L-EMS-029 (meetbaarheid: kalibratie apart voor nachten met spaarplan) — eerst 1 nacht zonder lage stand vergelijken.
- **H-EMS-13 nagelezen (code v5.116.0):** naast de schaling (L-EMS-028) nog twee verschillen tussen `_dipbesluit` en `_plan_dip_laadt`: (1) het spaarplan van de beslissing telt ook kwartieren ná het blok (`nodig_kwh`), het plan alleen tot het blok; (2) beslissing kiest het moment via `_goedkoopste_laadmomenten`, plan telt goedkopere kwartieren vóór het doel. **Meetbaarheid:** attributen van `diagnose_sturing` (o.a. `spaarplan_eigen/nodig_tot_blok_kwh`) staan niet in de recorder → offline narekening van de nacht kan alleen uit de diagnostiek/dagverloop; meenemen in L-EMS-028.
- PV vandaag t/m 11:00: 0,70 kWh tegen Solcast-gedaan 0,61 (4,89 totaal − 4,28 rest); day-ahead 4,58. Eerste uren iets bóven de verwachting (n=3 uur).
- Planvolging vandaag 58,7 % (46 kwartieren; sturing 8, accu 6) — geen nieuwe "afwijking sturing" sinds 07:40.
- Hypotheses: H-EMS-2 (PV te hoog), H-EMS-11 (nacht vs ochtendpiek), H-EMS-13 (plan ≠ beslissing). H-EMS-12 afgerond als definitieverschil (2/2). Geen release (tussenronde; v5.116.0 vandaag al door andere sessie).

laatste ronde: 22-10 11:40, gemeten t/m 22-10 11:45
