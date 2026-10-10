# Leerlog Energy Management System

Doorlopende leerronde (elke 4 uur). Alleen gemeten getallen; KPI's in KPI.csv, referenties in BASELINE.md, voorstellen in VOORSTELLEN.md.

## 07-10 23:15 · tussenronde (eerste ronde, baseline uit ~10 dagen historie)
- Gemeten: PV, net, accu per dag 28-09..06-10 (statistics); PV-voorspelling 31 dagen (pv_forecast_accuracy); tekortnachten 7 n; uurlijkse teruglevering 's nachts.
- PV-voorspelling: MAE 10,5% (30 d) → 5,2% (7 d); bias −4,4% / −1,7% (voorspelling iets te hoog). Geen duidelijk verschil bewolkt >70% vs ≤70% (bias −6,8 vs −4,6, n=16/13).
- Tekortnachten 4 van 7 (5,68 kWh): 2 economisch, 2 planning, 0 capaciteit. Reserve te hoog: 0 van 7.
- Opvallend: als de accu 's nachts levert, gaat er constant ~60 Wh/u naar het net (mediaan 60, n=50 uren, 00-07 u gem. 0,35 kWh/nacht). Oorzaak: smart-modus van zendure-ha volgt een P1-doel van ~−50 W (CHANGELOG v0.63.19). Steekproef 07-10 02:00: accu 290 W, P1 −50 W.
- Gevolg: het geleerde nachtverbruik (`p1 + accu + pv`) is huisverbruik zonder dit lek; de accu levert ~50 W meer dan de reserve verwacht → ~0,5-0,8 kWh/nacht over het hele ontlaadvenster. Dit is energie die verkocht wordt terwijl de reserve nodig is (HARDE REGEL "huis gaat voor") → gemeld, voorstel L-EMS-001.
- Hypothese H-EMS-1: het nachtlek verklaart een deel van de tekort-kWh in planning-nachten. Toets volgende ronden: lek-kWh per nacht naast tekort-kWh.
- Hypothese H-EMS-2: PV-bias is nu klein (−2%) en daalt; geen correctie nodig. Volgen tot 14 dagen.
- Niet gemeten (meetbaarheid): uurlijkse PV-voorspelling per uur (geen historie van uurvoorspelling in attributen gevonden; volgt), kwartierbeslissingen tegen achteraf-optimum (nog geen replay gebouwd), SoC-voorspelling tegen werkelijk.
- Geen release (tussenronde; 10 releases vandaag door andere sessies, v5.44 geïnstalleerd).

laatste ronde: 07-10 23:15, gemeten t/m 07-10 23:00

## 07-10 23:40 · tussenronde (handmatig gestart)
- Correctie: de vorige ronde was om 23:15, niet 23:30 (tijdstempels aangepast).
- Sinds 23:15 geen nieuwe gebeurtenis om te meten; geen release.

laatste ronde: 07-10 23:40, gemeten t/m 07-10 23:40

## 07-10 23:45 · tussenronde
- **Correctie 23:15:** de −50 W op de P1 ("nachtlek") is een bewuste instelling (Zendure regelt op P1+50) en zit sinds v5.20 in de reserve (`regelverschuiving_w` = 50, live gecontroleerd in gacs_zelfbeoordeling); de tekorttelling telt hem niet als verkoop (v5.42). Geen schending HARDE REGEL. L-EMS-001 vervallen.
- H-EMS-1 getoetst met uurdata 29-09..07-10 (9 nachten): beide planning-tekortnachten volgden op avondverkoop via `expensive_quarter_peak` onder de reserve (03-10: 1,37 kWh → 0,68 kWh tekort; 04-10: 5,14 kWh, vanaf 19:55 beschikbaar < reserve → 1,68 kWh tekort). Al gevonden en hersteld in v5.28.4 (04-10 10:32). H-EMS-1 verworpen; oorzaak = piekregel.
- Effect v5.28.4 gemeten: sinds 04-10 10:32 0× `expensive_quarter_peak`; 4 nachten (05-10..07-10 + 04→05) zonder tekort; avondverkoop 04-10 alleen boven de reserve (`expensive_quarter`).
- MC-kalibratie (nieuw): tekortkans om 22:00 vs uitkomst, 8 nachten 30-09..07-10: tekortnachten 98/100/45/97%, overige 0/0/0/0% → Brier 0,038 (n=8). Goed onderscheid, n klein → H-EMS-3.
- PV per uur (meetbaar via attribuut `profile` van pv_hourly_forecast_bias): werkelijk/Solcast mediaan 0,90-0,98 rond de middag, 0,52-0,69 om 06-07 en 15-17 UTC. De integratie leert en gebruikt dit profiel al zelf. Tweede voorspelling 13 d: Solcast 6,1% mediaanfout, tweede bron 31,6%.
- Lopend vannacht (→08-10): beschikbaar 4,23 kWh, nodig 4,54 kWh tot blok 12:15 → verwacht tekort 0,31 kWh; MC 41,7%. Toetsen in de dagafsluiting van 09-10.
- Meetbaarheid: MC-tekortkans heeft geen state_class → geen lange statistiek, alleen ~10 d historie. Kandidaat (zelf te bouwen, dagafsluiting): MC-waarde om 22:00 in het dagrecord bewaren.
- Geen release (tussenronde, geen acute bug).

laatste ronde: 07-10 23:45, gemeten t/m 07-10 23:44

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

laatste ronde: 10-10 11:40, gemeten t/m 10-10 11:50
