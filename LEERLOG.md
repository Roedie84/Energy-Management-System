# Leerlog Energy Management System

Doorlopende leerronde (elke 4 uur). Alleen gemeten getallen; KPI's in KPI.csv, referenties in BASELINE.md, voorstellen in VOORSTELLEN.md.

## 07-10 · samenvatting dag (3 tussenronden 23:15-23:45, eerste baseline uit ~10 d)
- Baseline: PV-MAE 10,5 % (30 d) / 5,2 % (7 d), bias −4,4/−1,7 %; tekortnachten 4/7 (2 economisch, 2 planning); MC 22:00 Brier 0,038 (n=8).
- −50 W P1-verschuiving 's nachts bleek bewust (`regelverschuiving_w` in de reserve) → L-EMS-001 vervallen; H-EMS-1 verworpen: planning-tekortnachten kwamen van `expensive_quarter_peak` (hersteld v5.28.4).
- PV-uurprofiel werkelijk/Solcast: middag 0,90-0,98, randuren 0,52-0,69 (integratie leert dit zelf). Meetbaarheid: MC-kans 22:00 niet bewaard → L-EMS-002.

## 08-10 · samenvatting dag (8 rondes; ingekort na 14 dagen)
- PV 30 d MAE 10,8% (bias −4,5), 7 d 5,9% (−2,4) → H-EMS-2 blijft: klein en stabiel. Bewolkt >70% bias −7,2 vs −4,6 (n=15/13), MAE gelijk 9,5% → geen bewolkingseffect op de fout.
- Verbruik (nieuw gemeten): uurprofiel MAE 0,13 kWh/u; nacht 22-09 bias −0,08 kWh (−3%) → reserve-invoer klopt. Dagtotaal −0,49 kWh/dag (mediaan per uur mist witgoed; reserve telt gepland witgoed apart).
- H-EMS-4 (nieuw): achteraf-optimum per uur over 4 dagen (29-09, 30-09, 01-10, 07-10; salderen = symmetrische prijs, slijtage 4,22 ct): werkelijk 1,16 € duurder dan zonder accu, optimum 2,20 € goedkoper. Bij 0 ct slijtage werke…
- Meetfout gevonden: `sensor.solaredge_production_energy` (cloud-dagteller) staat 00:04-07:07 op unknown → schaduw-dagrapport slaat nachtkwartieren stil over (dekking 80,6%, `kwartieren_gemeten` 76 is misleidend). Zichtbaar gem…
- Gebouwd v5.45 (L-EMS-002): MC-kans 22:00 per avond bewaard + `mc_22u` in dagrecord + `kalibratie_22u` (Brier); dagrapport `kwartieren_bruikbaar/ongebruikt`. 4815 tests groen, workflow groen, HACS ververst.
- Geïnstalleerd: v5.45 (~06:23) en v5.46 (07:03). L-EMS-003 ingesteld om 07:04 (`pv_energy_sensor_entity` = Modbus-teller): kwartier 07:15 pv al `measured` (cloudteller was tot 07:07 unknown), dagopwek 0,0 → geen sprong. Dekkin…
- L-EMS-004: sluipverbruik direct na update `normaal`, `methode_versie` 2, reeks en accumulator leeg → eerste meetpunt gehaald; referentie > 0 W pas na dagen.
- Nacht 07→08 (t/m 07:40): import 22-07 u 0,12 kWh, accu niet leeg (SoC 34% om 07:01) → geen tekort, zoals om 04:00 verwacht. Nacht-export 00-07 0,43 kWh (regelverschuiving −50 W nog actief; L-EMS-005 is een instelling bij Ruud).

## 09-10 · samenvatting dag (6 rondes; ingekort na 14 dagen)
- PV 30 d MAE 9,5% (bias −6,2), 14 d 5,5% (−2,7), 7 d 6,0% (−2,5); 10 van de laatste 14 dagen te hoog voorspeld. H-EMS-2 (klein, stabiel) blijft; integratie leert zelf −5,7%.
- Verbruik: uurprofiel MAE 0,155 kWh/u (07-10: 0,105), dag +0,41 kWh boven profiel. Nacht 22-09 opvallend stabiel: 7 nachten 2,40-2,66 kWh (gem. 2,48).
- H-EMS-4 (achteraf, uur, 4,22 ct): 08-10 werkelijk +0,03 € t.o.v. zonder accu, optimum −0,61 €; prijs 22,0 ct (14 u) tot 40,9 ct (20 u). 5 dagen samen werkelijk +1,19 €, optimum −2,81 €. Gat zit in laden in het middagdal en le…
- L-EMS-005 effect (nacht): export tijdens ontlading 00-03 u 27/22/22 Wh/u (was 59-65) → −60%. Volledige nacht 00-07 in de volgende ronde.
- L-EMS-003: dagrapport 08-10 nog 27× `pv_onbekend` (00-07, cloudteller tot 07:04); vannacht 03:15 pv `measured` → nacht werkt. Dagdekking 09-10 is de echte toets.
- Meetfout gevonden en gebouwd (L-EMS-009, v5.57): dagrapport 08-10 `kwartieren_gemeten` 74 van 96. Oorzaak in de code: na een herstart is er geen beginstand, dus valt het kwartier van elke herstart weg (18 kwartieren met een h…
- L-EMS-007 dagwissel geverifieerd: `geschiedenis_liter_per_dag` +1 waarde (215 L = utility_meter last_period 0,215 m³). Water loopt sinds 03:07 ~9 L/min (161 L om 03:45) — tijdstip gelijk aan de vorige ontharder-regeneratie (2…
- Nieuw voorstel L-EMS-010: sinds v5.55 heten de nachten →03-10 en →04-10 "verkocht met winst … bewust, geen stuurfout", maar die verkoop gebeurde onder de reserve door de piekregel-bug (hersteld v5.28.4, zie 07-10 23:45). Voor…

## 10-10 · samenvatting dag (6 rondes; ingekort na 14 dagen)
- Dag 09-10: PV 1,24 kWh (−48 % tegen day-ahead, 100 % bewolkt), import 6,37, huis 9,16; 22 herstarts. PV 30 d MAE 10,7 % (bias −7,4); vlakke biascorrectie bewust ingehouden bij twee soorten dagen (v3.33).
- Geverifieerd: L-EMS-009 (meetlog 93/96), L-EMS-003 (`pv_onbekend` 0), L-EMS-002 (eerste Brier-paar), L-EMS-013 (marge dynamisch 0 %). H-EMS-8 (SoC-sprong vlak boven leeg, n=2) → L-EMS-014.
- Nacht 09→10: tekort 2,36 kWh tegen voorspeld 2,38 (fout −0,02). `tekort_soort` sprong naar null op het resterende tekort → L-EMS-015.
- Acuut gebouwd v5.72.1 (L-EMS-016): de geplande vaatwasser telde in alle 22 MC-uursegmenten (vaste extra 1,9 → 25,8 kWh).
- **Harde regel 1× geschonden 18:45-19:00:** verkoop 6,91 → 6,22 kWh tegen reserve tot blok 6,78 → 0,56 kWh onder de reserve (vermogen niet op de vrije ruimte begrensd; opgelost in v5.79.0). Verkoop 22:45-23:00 daarna 0× onder de reserve. → H-EMS-9, L-EMS-017/018.
- Gebouwd v5.69.1 (L-EMS-011/012, rapportage); elders v5.70-v5.80 (chatsessies). PV 10-10 9,35 kWh (+3 %). Meetbaarheid: sinds v5.76.0 geen attributen in de recorder.

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

## 22-10 15:40 · tussenronde
- Actief **v5.117.0** (andere sessie 15:18; geïnstalleerd, herstart 15:27; v5.116.1 ~14:34). 0 EMS-fouten (alleen bronbuffer-WARNINGs Zonneplan bij de herstart, 1× cockpit-update 1,8 s).
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 22-10 0,04 kWh).
- **Laadblok:** import 11-15 u 8,43 kWh, accu AC-in 8,79 kWh, SoC 14 → 85 % (8,64 kWh). Volgend blok pas 23-10 21:15 → reserve 10,37 (afgekapt; nodig tot blok 11,46), MC 95 % tot blok, verwacht tekort 2,82 kWh "capaciteit". Plan: geen netlading, 22:00 57 %, sparen 02:00-05:30, 09:00 41 %, blok 15 %.
- **PV vandaag** t/m 15:00 3,15 kWh tegen Solcast-uren 3,09 (+2 %): ochtend 08-11 u +52 %, 11-15 u −7 %. 15:43 3,63 kWh, Solcast dag 4,47, day-ahead 4,58 → mogelijk de eerste dag in 16 zonder te hoge day-ahead (H-EMS-2; telt in de dagafsluiting).
- **H-EMS-13 gebouwd** (L-EMS-028 in v5.117.0, andere sessie, plus blokdrempel na het blok). 15:00 nog 1× "afwijking sturing" (precies het blokgeval dat v5.117.0 oplost); na 15:27 0 (n=1 kwartier). Planvolging vandaag 62,9 % (62 kw.; sturing 9, accu 9). Toets nacht 22→23.
- **Nieuw, meetfout digital twin:** 6-uursvoorspelling accu-inhoud MAE 1,00 kWh (n=60, 20..22-10); tijdens laden +1,34 te hoog (22-10 14:45: 10,16 tegen 8,18), nacht −0,73, avond −1,21. Code: in het blok `soc += laadvermogen × tijd` zonder laadrendement (gemeten AC-in 2,4 → inhoud +1,8-2,1 kWh/u); spaarstand niet gemodelleerd. → **L-EMS-030** (zelf bouwen, dagafsluiting).
- **MC-kalibratie, meetfout (L-EMS-029):** vanavond 22:00 meet de "kans tot het blok" 31 u (tot 23-10 21:15, nu 95 %) terwijl de tekortnacht 22-09 u telt; plan 09:00 41 % → vrijwel zeker de 3e "≈100 % zonder tekortnacht", nu door de horizon. Toets 03:40.
- Reservesprongen 2 (15:28-15:29, beide na herstart, alleen behoefte, reserve gelijk) → v5.115.1 telt ze apart, zoals bedoeld.
- Hypotheses: H-EMS-2 (PV te hoog), H-EMS-11 (nacht vs ochtendpiek; plan spaart nacht 22→23 zelf), H-EMS-13 (gebouwd; toets). Geen release (tussenronde; v5.116.1 en v5.117.0 vandaag al door andere sessie).

laatste ronde: 22-10 15:40, gemeten t/m 22-10 15:45

## 22-10 19:40 · tussenronde
- Actief **v5.119.0** (andere sessie 18:08; v5.118.0 17:09; beide geïnstalleerd). Daarmee gebouwd: L-EMS-025 en -026 (v5.118.0, akkoord Ruud 16:45), L-EMS-024, -029, -030 (v5.119.0, akkoord 18:05). 0 EMS-fouten; bij de herstart 19:06 4× bronbuffer-WARNING (Solcast/PV even onbeschikbaar, Solcast API-limiet 10/10).
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 22-10 0,075 kWh). Reservesprongen 0.
- **PV dag 22-10:** 4,21 kWh (SolarEdge) tegen day-ahead 4,58 (−8,1 %) en Solcast 4,47 (−5,8 %) → 16e dag op rij te hoog, maar klein. De nieuwe `eenzijdige_correctie` (−8,1 %, 14/14 dagen) had hem precies goed gezet (n=1). H-EMS-2 → toets L-EMS-025 over 7 dagen.
- Avond: import 15-19 u 1,11 kWh (17-19 u 0,31), piek uit de accu; SoC 85 → 68 %. MC 99 % tot het blok 23-10 21:30, verwacht tekort 2,94 kWh "economisch" (laden loonde niet) → bewust bijkopen, geen reservefout.
- **H-EMS-13 tussenstand:** sinds v5.117.0 (15:27) 0 nieuwe kwartieren "afwijking sturing" (n≈17). Planvolging vandaag 61,0 % (77 kw.). Toets nacht 22→23.
- Digital twin: laadblok 11:45-16:45 nog +1,07..+2,15 te hoog (vóór v5.119.0); effect pas bij het volgende blok (23-10 21:30).
- Hypotheses: H-EMS-2 (PV te hoog; correctie gebouwd), H-EMS-11 (nacht vs ochtendpiek; L-EMS-026 gebouwd, eerste nacht 22→23), H-EMS-13 (plan = beslissing; toets nacht). Geen release (tussenronde; vandaag al 6 releases door andere sessies).

laatste ronde: 22-10 19:40, gemeten t/m 22-10 19:45

## 22-10 23:40 · tussenronde
- Actief **v5.119.0** (geen nieuwe EMS-release; herstarts 20:10 en 22:11 door installaties elders). 0 EMS-fouten; 2× "accu niet aanstuurbaar" (Zendure offline 21:42 en 22:27, 8 time-outs) en bij 20:10 bronbuffer-WARNINGs Zonneplan/Solcast (API 10/10) — extern.
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 22-10 0,139 kWh).
- Avond 19-23 u: import 0,10 kWh, export 0,08 kWh; huis uit de accu, SoC 68 → 52 %.
- **H-EMS-13:** planvolging 59,1 % (93 kw.), "sturing" blijft 9 → sinds v5.117.0 (15:27) 0 nieuwe in ~33 kwartieren. Nachttoets 03:40.
- **Plan nacht 22→23 anders dan om 19:40:** blok schoof 23-10 21:30 → 23:00 (20:30, 20:45, 21:30 telkens later; kortere laadbehoefte), plan nu de hele nacht smart (~0,25 kW ontladen), 09:00 33 % (was: sparen 02:00-05:30, 09:00 41 %). Sparen pas 23-10 11:30-17:00 en 20:30-22:30 (25-28 ct), laden 23:00. Nachtprijs 29-31 ct, ochtendpiek 35-40 ct; de accu haalt de ochtend zonder sparen → `nacht_ochtendpiek` (L-EMS-026) hoeft niet. H-EMS-11-uitslag (ochtendpiek-import 07-10 u) in de ronde van 11:40.
- MC 99,9 % tot het blok (23-10 23:00, 25 u), verwacht tekort 3,39 kWh "economisch". `kalibratie_22u.laatste_avond` 22-10 100 % (basis tot_blok); `nachten_andere_horizon` nog leeg → toets na 09:00 (L-EMS-029).
- **Nieuw gezien:** sinds de herstart van 20:10 17 reservesprongen "alleen behoefte" (20:11-23:00; 19:45-20:10 en 15:30-19:45 0): `needed_kwh_before_margin` wisselt telkens ~1,49 kWh (8,90 ↔ 10,39) zonder verandering in lange horizon, airco of temperatuur; zonvoorspelling morgen wisselde niet. Reserve blijft 10,37 (afgekapt) → nu geen effect. Bron ligt in `_estimate_worst_case_deficit_kwh` (blok 25 u weg). Dagafsluiting: nalezen of dit een niet-afgekapte reserve (en dus de verkoopgrens) laat springen.
- Hypotheses: H-EMS-2 (PV te hoog; correctie gebouwd), H-EMS-11 (nacht vs ochtendpiek), H-EMS-13 (plan = beslissing). Geen release (tussenronde).

laatste ronde: 22-10 23:40, gemeten t/m 22-10 23:45

## 23-10 03:40 · dagafsluiting 22-10
- Actief **v5.119.0** (geïnstalleerd). 0 EMS-fouten; WARNINGs extern: Zendure offline 21:42/22:27, Zonneplan-sensoren en prijzen even onbeschikbaar rond 20:10/00:00 (bronbuffer vangt het op).
- Dag 22-10: PV 4,21 kWh (day-ahead 4,58 → −8,1 %), import 11,62 (laadblok 8,43), export 0,30, accu 9,89 in / 4,88 uit, huis 10,51 (verbruiksverwachting dagarchief 7,98 → 21 % te laag). Planvolging 60,0 % (sturing 9, alle vóór v5.117.0). **Harde regel: 0× onder de reserve** (regeloverschot 0,14 kWh). Geen tekortnacht.
- **H-EMS-2:** 16 dagen op rij te hoog; 7 d MAE/bias 20,5/−20,5 %, 14 d 19,4/−19,4, 30 d 12,1/−10,7. L-EMS-025 dag 1: correctie −8,1 % was raak (n=1). Vandaag ruw 3,94 → gecorrigeerd ~3,63 kWh.
- **Nabeschouwing 7 d (16..22-10): € 6,54 van € 7,55 = 86,6 %.** 22-10 leverde € 0,64 tegen € 0,18 "haalbaar": het optimum kent geen netladen, de netarbitrage (€ 0,94) valt erbuiten → realisatie > 100 % op laaddagen is een definitiegrens. **Nieuw zichtbaar:** avondpiek 6 van 7 dagen "te veel ontladen" (2,1-3,6 kWh/dag, samen −€ 1,92); hoort bij H-EMS-11 (ochtendpiek vastgehouden): het optimum schuift energie van de avond naar de ochtend erna.
- **L-EMS-024 effect:** `zon_verwacht_kwh` 22-10 = 5,28 (niet meer 0), maar 15 % boven day-ahead 4,58 en Solcast 4,47: `_ochtendverwachting` kiest het kwartier tot 09:00 met de MEESTE zon → neigt omhoog (n=1). Accu-opbrengst 0,49 incl. voorraad 0,90 ✓. Eerdere meetlogdagen (20-10 −1,02) niet herrekend (alleen nieuwe dagen). Toets nog 2 dagen vóór een voorstel.
- **H-EMS-13 (plan = beslissing):** sinds v5.117.0 0 nieuwe "afwijking sturing" in ~48 kwartieren; nacht 22→23 had geen dip-lading gepland → nachttoets niet mogelijk. L-EMS-028 blijft gebouwd, 7-daagse toets loopt.
- **H-EMS-14 (nieuw) bevestigd in code:** de 17 sprongen "alleen behoefte" (20:11-23:00) wisselen telkens 1,47-1,51 kWh = `CONSUMPTION_CORRECTION_MAX_EXTRA_KWH` (1,5): de live verbruikscorrectie gaat aan/uit (mediaan live > uurprofiel). Na 00:00 (blok 23-10 23:00, niet meer afgekapt) veranderde zo ook de reserve: 10,37→9,85, 9,81→10,21, 9,64→9,26. Nu geen effect (beschikbaar 3,8 ≪ reserve 8,9). **Gebouwd v5.120.0** (meetbaarheid, L-EMS-031): `live_correctie_extra_kwh`/`-verhouding` in uitsplitsing en sprongen. Bekend fenomeen (v5.14.2, compressorbeurten); meten hoe vaak het een niet-afgekapte reserve of verkoopgrens raakt vóór een voorstel (hysterese = sturing → Ruud).
- MC 22:00 Brier 0,286 (n=7; 2× kans 100 % zonder tekortnacht). Avond 22-10: 100 % tot het blok over 25 u → valt onder L-EMS-029 "andere horizon"; afrekening na 09:00.
- Hypotheses: H-EMS-2 (PV te hoog; correctie gebouwd), H-EMS-11 (nacht/avond vs ochtendpiek), H-EMS-14 (reservesprong door live correctie). H-EMS-13 → toets via L-EMS-028. **Release v5.120.0** (L-EMS-031).

laatste ronde: 23-10 03:40, gemeten t/m 23-10 03:55

## 23-10 07:40 · tussenronde
- Actief **v5.120.0** (geïnstalleerd; herstarts 06:09 en 07:39 door installaties elders). 0 EMS-fouten; WARNINGs bronbuffer (Solcast/Zonneplan even onbeschikbaar bij de herstart) — extern.
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 23-10 0,093 kWh).
- Nacht 03-07 u: import 0,243 kWh, waarvan 0,194 in 04-05 u: **L-EMS-026 voor het eerst actief** (`battery_saved_for_peak` 04:00-05:00, SoC 42 % vast); om 23:40 stond nog "hele nacht smart". Daarna smart, SoC 42 → 37 % (07:42), beschikbaar 3,11 kWh tegen reserve 7,52 (blok 23:00). Uitslag ochtendpiek 07-10 u (H-EMS-11) om 11:40.
- **H-EMS-14:** 03:50-07:39 geen 1,5-kWh-wissels (reserve uit de state-string: glijdend −0,01/2 min, grootste stap +0,32 om 05:13; herstarts −0,16 en −0,03). Reserve ≫ beschikbaar → geen effect. **Meetbaarheid:** `reserve_sprongen` staat alleen in het geheugen en is na elke herstart leeg (2× vannacht); attributen niet in de recorder → reconstructie alleen via de state-string. Kandidaat L-EMS-033 (bewaren over herstart).
- **Nieuw (classificatie):** `plantoetsing.structureel` zegt "loopt niet structureel uit de pas" terwijl 14 van 14 dagen zon < voorspeld (gem. −20,0 %, precies op de tolerantie 20; mediaan 30 d −7,4 %). Het oordeel kijkt alleen naar |gemiddelde| > 20, niet naar de vaste richting → kandidaat L-EMS-032 (rapportage, zelf bouwen in de dagafsluiting).
- MC 99,7 % tot het blok (23:00). H-EMS-13: geen dip-lading gepland → niets te toetsen.
- Hypotheses: H-EMS-2 (PV te hoog), H-EMS-11 (nacht/avond vs ochtendpiek; L-EMS-026 1 u actief), H-EMS-14 (reservesprong live correctie). Geen release (tussenronde).

laatste ronde: 23-10 07:40, gemeten t/m 23-10 07:45

## 23-10 11:40 · tussenronde
- Actief **v5.120.0**; v5.121.0 (11:12) en v5.122.0 (11:25) van een andere sessie zijn via HACS gedownload maar pas actief na een herstart (diagnose meldt nog v5.120.0). 0 EMS-fouten; 1× Zendure offline 07:56 (extern).
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 23-10 0,108 kWh).
- **H-EMS-11 / L-EMS-026, ochtendpiek 07-10 u:** netimport 0,078 kWh (0,018/0,038/0,022); de accu dekte de piek (SoC 37 → 33 %). Vergelijking 14..22-10 zonder sparen: 0,06-0,30 kWh (mediaan 0,10). Het spaaruur 04-05 u (0,19 kWh netstroom à ~30 ct) was deze nacht niet nodig: de accu had om 09:00 nog 2,65 kWh beschikbaar. Effect ~€ 0,01 (n=1); de energie blijft in de accu. Meer nachten nodig; een nacht waarin de accu vóór 10:00 leeg zou raken is de echte toets.
- Na 10:45 weer `battery_saved_for_peak` (10:45-11:00, sinds 11:15) bij 26,6 ct: sparen voor de middag-/avondpiek (plan 03:40: sparen 11:30-17:00 en 20:30-22:30).
- **H-EMS-14:** 07:42-11:39 geen 1,5-kWh-wissels; reservestappen +0,25/−0,18/−0,25 en +0,08 bij blokverschuiving 23:00 → 23:15. Reserve 6,42 ≫ beschikbaar 2,76 → geen effect.
- MC 99,8 % tot het blok (23:15). PV tot 11:43 0,74 kWh, Solcast-rest 3,77 → ~4,5 kWh; afrekening in de dagafsluiting (correctie −8,1 %).
- Hypotheses: H-EMS-2 (PV te hoog), H-EMS-11 (nacht/avond vs ochtendpiek; 1e nacht: sparen onnodig, geen schade), H-EMS-14 (reservesprong live correctie). Geen release (tussenronde; vandaag al 3 EMS-releases door andere sessies). L-EMS-032/033 blijven gepland voor de dagafsluiting.

laatste ronde: 23-10 11:40, gemeten t/m 23-10 11:45

## 23-10 15:40 · tussenronde
- Actief **v5.124.1** (geïnstalleerd; v5.123.0/124.0/124.1 van andere sessies, herstarts 11:51, 14:54, 15:17). 0 EMS-fouten; WARNINGs bronbuffer Solcast dag 3-7 en Zonneplan-prijzen bij de herstart (extern, opgevangen).
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 23-10 0,108 kWh).
- Middag 11-15 u: import 0,10 / export 0,09 kWh (P1 ≈ 0); zon naar de accu, SoC 34 → 49 %. Sparen 11:15-13:00 en weer vanaf 14:30.
- **PV:** t/m 15:00 3,84 kWh (piek 13-14 u 1,52); zonspreiding 4,0 (p10 2,7 / p90 5,6). Gecorrigeerde day-ahead was 3,63 (ruw 3,94) → vandaag mogelijk de eerste dag in 17 dat de zon de verwachting haalt; afrekening 03:40 (L-EMS-025 dag 2).
- **Blok verschoven:** 13:31 23-10 23:15 → **24-10 10:30** (morgenprijzen binnen). Reserve 7,84 → 10,37 (afgekapt), MC 100 % tot het blok, verwacht tekort 2,95 kWh "economisch, bijladen loonde niet". Nacht valt deels op het net; zo bedoeld. Kalibratie: deze avond hoort bij "andere horizon" (blok na 12:00).
- **L-EMS-029 rechtgezet:** het dagrecord van nacht →D wordt om 00:00 van D+1 geschreven (niet om 09:00) → nacht 22→23 verschijnt vannacht in `kalibratie_22u`; geen fout.
- **H-EMS-14:** 12:33 reserve 6,42 → 7,89 (+1,47 = live correctie, blok 23:15, niet afgekapt); beschikbaar 3,00 ≪ reserve → geen effect. Uitsplitsing gewist door de herstart van 14:54 → bevestigt L-EMS-033 (n=2 keer verloren).
- Hypotheses: H-EMS-2 (PV te hoog; correctie gebouwd), H-EMS-11 (nacht/avond vs ochtendpiek), H-EMS-14 (reservesprong live correctie). Geen release (tussenronde; vandaag al 6 EMS-releases door andere sessies). L-EMS-032/033 gepland voor de dagafsluiting.

laatste ronde: 23-10 15:40, gemeten t/m 23-10 15:45

## 23-10 19:40 · tussenronde
- Actief **v5.124.1** (geen herstart sinds 15:17, geen nieuwe release). 0 EMS-fouten; WARNINGs extern (Solcast API-limiet 10/10 om 17:22, Zonneplan 500 om 17:42; bronbuffer vangt op).
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 23-10 0,136 kWh).
- **PV dag 23-10: 4,30 kWh** (18-19 u 0) tegen gecorrigeerde day-ahead 3,63 (**+18,5 %**) en ruw 3,94 (+9,1 %) → eerste dag in 17 boven de verwachting; L-EMS-025 dag 2 werkte de verkeerde kant op (dag 1 raak). n=2, eenzijdige correctie blijft; definitieve afrekening 03:40 (met Solcast-dagwaarde).
- **Avondpiek 15-19 u:** import 0,127 kWh, export 0,058; de accu dekte het huis (SoC 49 → 43 %, beschikbaar 4,49 → 3,80). Reserve vast 10,37 (afgekapt, boven capaciteit) → geen reservesprongen sinds 15:17 (H-EMS-14 nu niet toetsbaar).
- MC 88 % tot het blok (24-10 10:45, schoof 19:15 van 10:30); afrekening "andere horizon" morgen.
- Hypotheses: H-EMS-2 (PV-bias; correctie vandaag te scherp), H-EMS-11 (nacht/avond vs ochtendpiek; ochtend 24-10 toetsen), H-EMS-14 (reservesprong live correctie; alleen zichtbaar onder de kap). Geen release (tussenronde). L-EMS-032/033 voor de dagafsluiting.

laatste ronde: 23-10 19:40, gemeten t/m 23-10 19:45

## 23-10 23:40 · tussenronde
- Actief **v5.124.1** (geen herstart sinds 15:17). 0 EMS-fouten; WARNINGs extern (Zonneplan 500 om 21:02, Solcast dag 6/7 onbeschikbaar).
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 23-10 0,187 kWh). Avond 19-23 u: import 0,064 kWh, export 0,057; accu dekte het huis (SoC 44 → 30 % om 22:50).
- **Nieuw (beslissing):** om 23:00:29 sprong het blok van 24-10 10:45 terug naar **23-10 23:00** zonder herstart → `_lopend_blok` valt terug op het blok van vandaag over de hele dag (23:00-24:00). Daarin balanceerlading (8 dagen niet vol): 23:00-23:40 **1,73 kWh** uit het net tegen 21,9-23,1 ct; nacht 14,7-16,6 ct, morgen 13:00 13,4 ct; plan laadt morgen tot 83 % (niet vol). Meerkosten ~0,19 €. → **L-EMS-034** (open, Ruud beslist).
- **H-EMS-14:** 16 reservesprongen `alleen_behoefte` 20:43-22:15 door de live correctie (verhouding 1,13-1,98; 21:17 eenmalig 4,975); reserve afgekapt (10,37) → geen sturingseffect, maar MC tot het blok springt mee: 4× ≥ 30 pp per minuut (20:42 11 → 97 %). MC 22:00 = 100 % op een correctiepiek (0,22 → 1,44 kWh) → de 22:00-stand voor `kalibratie_22u` is ruis-gevoelig; telt bovendien als "andere horizon" (blok verschoof om 23:00).
- **Digital twin** (6 u vooruit): 14-23 u alle te laag, laatste 10 bias −1,71 kWh (avond −1,98..−2,80); totaal 60: bias −0,47, MAE 1,06. Avond = bekende "spaarstand niet gemodelleerd"; laaduren (L-EMS-030) worden pas vanaf 05:00 afgerekend.
- Hypotheses: H-EMS-2 (PV-bias), H-EMS-11 (nacht/ochtendpiek; ochtend 24-10), H-EMS-14 (live correctie → reservesprong/MC-ruis). Geen release (tussenronde, niets acuut: lading stopt om 24:00). L-EMS-032/033 voor de dagafsluiting.

laatste ronde: 23-10 23:40, gemeten t/m 23-10 23:45

## 24-10 03:40 · dagafsluiting 23-10
- Actief **v5.124.1**; **release v5.125.0** (03:55, L-EMS-032 + L-EMS-033, workflow groen, HACS ververst; wacht op installatie). 0 EMS-fouten.
- Dag 23-10: PV 4,30 kWh (ruw day-ahead 3,94 → **+9,0 %**, gecorrigeerd 3,63 → +18,5 %), import 3,26 (balanceerlading 1,73), export 0,37, accu 5,14 in / 4,03 uit, huis **6,08** (verwacht 8,57 → **−29 %**; planvolging oorzaak verbruik 34 kw.). **Harde regel: 0× onder de reserve** (regeloverschot 0,19). Geen tekortnacht.
- **H-EMS-2:** eerste dag in 17 boven de verwachting; 7 d MAE/bias 21,5/−18,9 %, 14 d 16,6/−15,4, 30 d 12,4/−10,5. `eenzijdige_correctie` blijft −8,1 % (13/14 aan één kant). L-EMS-025: dag 1 raak, dag 2 +18,5 % ernaast (n=2).
- **L-EMS-028:** eerste hele dag "sturing" 0 (96 kw.) → effect houdt; 7-daagse toets loopt tot 29-10.
- **Nabeschouwing 7 d (17..23-10): € 5,39 van € 6,58 = 81,9 %** (was 86,6). Patroon blijft: avondpiek 6/7 dagen te veel ontladen (−€ 1,92), ochtendpiek op 3 dagen 2,3-3,2 kWh vastgehouden (+€ 2,83; 23-10 3,20 kWh na het sparen van L-EMS-026). Ochtendimport 23-10 was maar 0,08 kWh: de vastgehouden energie ging niet naar het huis maar bleef in de accu. Het optimum verkoopt in de ochtendpiek; sturing → H-EMS-11 blijft, geen voorstel bij n=1 na L-EMS-026.
- **H-EMS-14:** 17 sprongen "alleen behoefte" door de live correctie (verhouding tot 4,98), reserve afgekapt → geen sturingseffect; v5.125.0 bewaart ze voortaan over een herstart.
- MC 22:00 Brier 0,333 (n=6; 2× 100 % zonder tekortnacht); nacht →23 telt als "andere horizon". Digital twin MAE 1,20 kWh (n=60): de balanceerlading van 23:00 (L-EMS-034) en de spaarstand staan niet in de twin → L-EMS-030 laadtoets niet zuiver.
- Hypotheses: H-EMS-2 (PV-bias), H-EMS-11 (avond/ochtendpiek), H-EMS-14 (live correctie). L-EMS-034 blijft open.

## 24-10 07:40 · tussenronde (niet gemeten)
- HA-MCP kon niet verbinden (502 bij opbouw van de verbinding) → geen history, logs of dashboard; niets gemeten, geen release, dashboardkaart niet bijgewerkt. Volgende ronde meet door vanaf 03:55 (recorder bewaart ~10 d, dus geen verlies).

laatste ronde: 24-10 07:40, gemeten t/m 24-10 03:55

## 24-10 11:40 · tussenronde
- Actief **v5.126.0** (herstarts 07:41 en 10:16; v5.125.0 en v5.126.0 nu beide actief). 0 EMS-fouten; WARNINGs extern (Zonneplan 500 om ~10:46, laatst bekende prijzen gebruikt).
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 24-10 0,128 kWh).
- **Nacht 23→24:** het herleefde blok 23:00-24:00 laadde in totaal **2,59 kWh** uit het net (accu +2,38), niet 1,73: lading liep tot 24:00. Daarna smart; netimport 00-09 u 0,42 kWh, waarvan 0,22 in de spaarkwartieren 01:45-03:00. Geen tekortnacht (SoC min 30 %).
- **H-EMS-11, ochtendpiek 07-10 u:** import 0,087 kWh; accu dekte het huis (0,81 kWh, SoC 37 → 31 %). 2e nacht met ochtendsparen: weer niet nodig, energie bleef in de accu (2,42 kWh om 11:43, blok 10:45). n=2.
- **L-EMS-032 geverifieerd:** plantoetsing "structureel te hoog: 26 van 30 dagen minder zon (mediaan −7 %)". **L-EMS-033 geverifieerd:** na de herstart van 10:16 staan de 7 sprongen van 07:43-10:16 er nog.
- **L-EMS-034 gebouwd v5.126.0** (andere sessie 07:28, geïnstalleerd 07:41). Code nagelezen: `_gekozen_blok_start` wordt elke ronde gezet, dus de fix dekt ook de 23:00-terugval zonder herstart. Na 2 herstarts bleef het blok 10:45. Echte toets: vanavond 23:00, als het blok van morgen al vastligt.
- **H-EMS-14:** sprongen nu door `lange_horizon_extra_kwh` (10:14 +1,88 / 10:15 −1,81 / 10:16 +2,99), niet door de live correctie; reserve niet afgekapt maar ≫ beschikbaar → geen effect.
- PV t/m 11:43 0,45 kWh, Solcast dag 6,30 (rest 5,23), bewolking 96 %. Afrekening 03:40.
- Hypotheses: H-EMS-2 (PV te hoog), H-EMS-11 (ochtendsparen; 2/2 nachten onnodig, geen schade), H-EMS-14 (reservesprongen; nu lange horizon). Geen release (tussenronde, niets acuut).

laatste ronde: 24-10 11:40, gemeten t/m 24-10 11:45

## 24-10 15:40 · tussenronde
- Actief **v5.126.0** (geen herstart sinds 10:16). 0 EMS-fouten; WARNINGs extern (Zonneplan 500, laatst bekende waarden gebruikt).
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 24-10 0,128 kWh). Export 12-15 u 0,006 kWh.
- **Laadblok 10:45-16:30:** 10:45-12:15 `sparen_in_blok` (netladen volgt), vanaf 12:15 netladen tegen 13,5-14,7 ct: netimport 12-15 u **6,04 kWh**, accu +6,54; SoC 31 → 85 % (15:39), plan **100 % om 16:15** = de balanceerlading valt nu in het goedkope dagblok (23-10: om 23:00 tegen 21,9-23,1 ct). Past bij L-EMS-034; echte 23:00-toets vanavond.
- **Na het blok:** plan houdt SoC 64 % om 24:00 en 52 % om 06:30 bij nachtprijzen 12,7-14,1 ct → ~5 kWh à ~14 ct (+ rendement 84 %) gaat de nacht in. Gevolg van de balanceerlading (vol moet), geen eigen fout; afrekenen in de nabeschouwing van 24-10.
- **PV:** t/m 15:00 3,40 kWh; Solcast dag 6,30 → 5,70 (rest 1,08). Afrekening 03:40.
- **Nieuw (weergave):** stand van *PV hourly forecast bias* = factor van het klokuur (0,487, sleutel 15) terwijl de sleutels UTC zijn (nu 13 → 0,823). De verwachting zelf gebruikt `_utc_uur` goed. → **L-EMS-035** (gepland, klaargezet op branch `wip/l-ems-035`, suite 6134 groen). Vannacht DST (25-10 03:00 → 02:00): 03:40-ronde let op de 25-uursdag.
- H-EMS-14: geen nieuwe reservesprongen na 10:16. MC tekortkans 0 % (horizon tot 25-10 09:00).
- Hypotheses: H-EMS-2 (PV te hoog), H-EMS-11 (ochtendsparen 2/2 onnodig), H-EMS-14 (reservesprongen; stil). Geen release (tussenronde, niets acuut).

laatste ronde: 24-10 15:40, gemeten t/m 24-10 15:45

## 24-10 19:40 · tussenronde
- Actief **v5.126.0** (geen herstart sinds 10:16). 0 EMS-fouten; WARNINGs extern (Solcast API-limiet 10/10, Zonneplan 500).
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 0,144 kWh). Avondpiek 17-19 u: import 0,029, export 0,026; accu dekte het huis (SoC 97 → 90 %).
- **Balanceerlading niet vol:** plan (15:40) beloofde 100 % om 16:15; werkelijk 96 % bij het einde van het blok (16:30), max 97 % (zon). Gemiddeld ~1,4 kW tegen gepland 2 kW → afvlakking bovenin staat niet in het plan (n=1). Morgen opnieuw gepland 12:45-16:45.
- **Blok van morgen vast om 16:30** (25-10 03:00 CET) → de 23:00-toets van L-EMS-034 is vanavond zuiver.
- **Nieuw (bug, L-EMS-036):** kwartierplanning 25-10 heeft 95 van de 100 kwartieren; de wintertijd-dubbelen vallen weg (Python negeert `fold` binnen één zoneinfo-zone). Vastgesteld met de echte prijsreeks, gereproduceerd in 6 tests; fix klaargezet op `wip/l-ems-036` (suite 6140 groen; ook een tijdgebonden test gerepareerd). Niet vanavond gereleased: klein effect vannacht, alleen nuttig bij installatie vóór 02:00.
- PV t/m 18:00 **4,66 kWh** tegen Solcast 5,70 (−18 %) → H-EMS-2 (te hoog) houdt; afrekening 03:40.
- Hypotheses: H-EMS-2 (PV te hoog), H-EMS-11 (ochtendsparen 2/2 onnodig), H-EMS-14 (reservesprongen; stil sinds 10:16). Geen release (tussenronde). 03:40: DST-nacht (25 u) + L-EMS-034/036 nameten, release v5.126.1 (L-EMS-035 + 036).

laatste ronde: 24-10 19:40, gemeten t/m 24-10 19:50

## 24-10 23:40 · tussenronde
- Actief **v5.126.0** (geen herstart sinds 10:16). 0 EMS-fouten sinds 19:50.
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 24-10 0,196 kWh). Reserve 9,7 > beschikbaar 6,9 kWh: accu dekt het huis, verkoopt niet.
- **L-EMS-034 geverifieerd:** om 23:00 geen terugval op het blok van vandaag; blok bleef 25-10 03:00 CET, modus smart, geen netlading (SoC 71 → 70 %). Eerste 23:00 zonder balanceerlading sinds 22-10.
- **L-EMS-036 bevestigd in de live planning (23:30):** morgen 02:30 → 03:00, 95 van 100 kwartieren. Effect vannacht klein (smart, prijzen 12,8-12,9 ct). Release v5.126.1 (035 + 036) in de dagafsluiting — kan pas ná de DST-nacht geïnstalleerd worden.
- PV dag **4,7 kWh** tegen Solcast 5,70 (−18 %) / ochtend 6,30 (−25 %) → H-EMS-2 (te hoog) houdt; afrekening 03:40.
- Let op voor 03:40: HACS-downloads faalden om 20:01 af en toe (GitHub-header te lang; Gold Scalper slaagde daarna wel) → na de release controleren dat HACS de versie echt binnenhaalde.
- Hypotheses: H-EMS-2 (PV te hoog), H-EMS-11 (ochtendsparen 2/2 onnodig), H-EMS-14 (reservesprongen; stil sinds 10:16). Geen release (tussenronde).

laatste ronde: 24-10 23:40, gemeten t/m 24-10 23:45

## 25-10 03:40 · dagafsluiting 24-10
- Actief **v5.126.0**; **release v5.126.1** (03:50, L-EMS-035 + L-EMS-036; suite 6140 groen, workflow groen, HACS ververst; wacht op installatie). 0 EMS-fouten; extern: DNS-storing ~00:45 (Nabu Casa, Bitvavo, feeds), Zonneplan 500 rond 00:01.
- Dag 24-10: PV 4,66 kWh (tracker day-ahead 4,89 → **−4,6 %**; gecorrigeerd 4,49 → +3,8 %; Solcast-ochtend 6,30 → −26 %), import 8,69 (laadblok 12:15-16:30), export 0,28, accu 9,55 in / 5,12 uit, huis 8,65 (verwacht 9,04 → −4 %). Planvolging 60,4 % (sturing 0, accu 15). **Harde regel: 0× onder de reserve** (`kwartieren_onder_verkoopreserve` 0, verkocht 0). Geen tekortnacht.
- **H-EMS-2 zwakker:** 7 d MAE/bias 16,4/−13,8 %, 14 d 16,5/−15,2, 30 d 12,1/−10,2 (7 d was 21,5/−18,9). L-EMS-025 na 3 dagen: gecorrigeerd 0 / +18,5 / +3,8 % (MAE 7,4) tegen ruw −8,1 / +9,0 / −4,6 (MAE 7,2) → nog geen winst zichtbaar; toets loopt tot 7 dagen.
- **Nabeschouwing 7 d (18..24-10): € 4,96 van € 6,46 = 76,8 %** (was 81,9). 24-10 € 0,47 van € 0,57; avondpiek voor het eerst positief (+€ 0,29, 3,13 kWh vastgehouden na de balanceerlading), nacht −€ 0,19. 7 d: avondpiek −€ 1,24, ochtendpiek +€ 2,94, nacht +€ 0,63.
- **L-EMS-036 nagemeten (DST-nacht):** prijs `unknown` 02:45-03:00 CEST én 02:45-03:00 CET; 02:00-02:45 CET kreeg de prijzen van het zomertijduur; planvolging mist alle 8 kwartieren 02:00-02:45 (2×; dag 25-10 11 kw. t/m 03:45). Sturing smart, geen schade (12,8-13,1 ct). Opgelost in v5.126.1; volgende echte toets okt 2027.
- **H-EMS-14:** reservesprongen 24-10: 20 (9 alleen behoefte, 3 na herstart). 00:00:00 weer het dagwissel-artefact: lange horizon 6,48 → 9,55 → 6,49 in 26 s (reserve 9,08 → 10,37 → 9,18); 2e keer (22-10 +1,73). Geen sturingseffect (beschikbaar ~6,9 < reserve); nog een middernacht met effect zien vóór een voorstel.
- MC 22:00 Brier 0,500 (n=6; 3× 100 % zonder tekortnacht: →20, →22, →24). Avond 24-10 `kans_pct` 0 tot het blok, incl. lange horizon 100 %. Digital twin 1,51 kWh (was 1,20).
- Hypotheses: H-EMS-2 (PV te hoog; kleiner), H-EMS-11 (avond/ochtendpiek), H-EMS-14 (reservesprongen + middernacht). Release v5.126.1.

laatste ronde: 25-10 03:40, gemeten t/m 25-10 03:50

## 25-10 07:40 · tussenronde
- **HA herstart 06:00 CET: v5.126.1 actief** (diagnose: fout 0, storing 0). Opstartwaarschuwingen alleen Zonneplan kort onbeschikbaar (laatste prijzen van 05:16 gebruikt) - extern, hersteld.
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 25-10 0,057 kWh). Geen tekortnacht.
- Nacht 24→25: accu dekte 22:00 CEST-03:00 CET **1,29 kWh** (net ~0); vanaf het blok 03:00 CET sparen: net ~0,19 kWh/u tegen 12,7-13,1 ct, SoC vast op 60-61 % voor de avondpiek (17:30-19:15 26-31 ct). Na de herstart koos het EMS het blok 06:00 CET (oud blok voorbij) - logisch, prijzen vlak.
- **L-EMS-035 geverifieerd:** stand 0,529 = sleutel 6 = UTC-uur om 07:41 CET. `in_progress.hour` 7 is het klokuur - bewust (meten per klokuur, opslaan onder UTC, `_finalize_pv_hourly_bucket`), geen fout.
- L-EMS-036 geïnstalleerd; echte toets okt 2027.
- Planvolging 25-10 t/m 07:30: 92,0 % (25 kw.; 06:00 na herstart 1× afwijking accu).
- Plan vandaag: zon tot 12:30 (SoC 60 → 87 %), 4 laadkwartieren 12:45-16:45 (12,5-15,6 ct), verkopen 18:00-21:15 tot 39 %. Solcast 7,2 kWh tegen tweede voorspelling 4,7 (oneens 43 %) → H-EMS-2-toets vandaag: bij minder zon komt de accu lager aan de avondpiek.
- Hypotheses: H-EMS-2 (PV te hoog), H-EMS-11 (avond/ochtendpiek), H-EMS-14 (reservesprongen; geen nieuwe na 02:00 CEST). Geen release (tussenronde, niets acuut).

laatste ronde: 25-10 07:40, gemeten t/m 25-10 07:45

## 25-10 11:40 · tussenronde
- **Vier HA-herstarts** (09:29, 09:55, 10:08, 10:53; installatie v5.126.2 en Gold Scalper 2.22.2/2.23.0 door andere sessies). **v5.126.2 actief**, diagnose fout 0 / storing 0. Na elke herstart prijsbuffer gebruikt (Zonneplan kort onbeschikbaar) - afgevangen.
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 25-10 0,057). Geen nieuwe reservesprongen sinds 02:00 CEST (nog 20; `na_herstart` 3 → de 4 herstarts gaven geen sprong, L-EMS-033 houdt).
- Blok na elke herstart op het lopende kwartier (09:30/09:45/10:00/10:45): **geen fout** - prijzen 12,5-13,3 ct van 00 tot 15 UTC, de vallei loopt terug tot nu (`_cheapest_block_range`, upcoming vanaf nu). Ochtend `sparen_in_blok`: huis op het net (12,7 ct), accu 60 → 64 % op zon. Plan nu: laden 12:15-13:45 tot 100 % (12,5-12,7 ct), avondpiek 17-19 u 26-29 ct.
- **Planvolging 25-10 t/m 11:15: 72,5 %** (40 kw.; 8× accu, vooral 09:45-10:15 en 10:45 rond de herstarts). **1× "afwijking sturing" (11:00)**: gepland 2,4 kW laden, gemeten 1,0 kW; 11:00-11:07 `grid_charging_profitable`, daarna `sparen_in_blok` (goedkopere kwartieren 12:15+). Eerste "sturing" sinds L-EMS-029/v5.117; direct na herstart, n=1 → volgen in de 7-daagse toets (t/m 29-10).
- **H-EMS-2 (PV te hoog) vandaag:** gemeten 07-11 CET 2,06 kWh (+0,70 in het uur 11 t/m 11:42 = 2,75). Solcast-dag zakte 7,49 (06:01) → 5,84 (11:16); tracker day-ahead 7,43, tweede voorspelling 5,20. Projectie met Solcast-rest ≈ 6,2 kWh → **≈ −16 % tegen day-ahead** (uitslag 03:40). Uren zelf: gemeten 2,06 tegen Solcast-schatting voor dezelfde uren 1,94 (+6 %) → de fout zit in de middag-/dagverwachting, niet in de ochtenduren.
- MC-tekortkans 0,0 %; geen blok-tekort in zicht.
- Hypotheses: H-EMS-2 (PV te hoog; vandaag ≈ −16 % in de maak), H-EMS-11 (avond/ochtendpiek), H-EMS-14 (reservesprongen; 0 nieuwe). Geen release (tussenronde, niets acuut).

laatste ronde: 25-10 11:40, gemeten t/m 25-10 11:45

## 25-10 15:40 · tussenronde
- v5.126.2 actief, diagnose fout 0 / storing 0; geen herstart sinds 10:53. Extern: DNS-storing ~13:05-15:40 (Spotify, Zwaailicht, Bitvavo/IG), Solcast-API-limiet 10/10 om 15:18 (rest-sensor bleef bruikbaar).
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 0,06). Reservesprongen 20 (0 nieuw). MC 0,0 %.
- **Laadblok 12:15-14:53** (SoC 66 → 100 %, input_limit 2400): AC-in per kwartier **2,12-2,25 kW** (eerdere dagen 2,40 in volle uren), vanaf 14:00 afbouw 1,81 kW. Inhoud steeg **1,73 kW** (available_kwh 6,45 → 9,22 in 1,71 u). Plan van 11:40: 6 kwartieren (12:15-13:45) tot 100 %; werkelijk 10,5. SoC hing 14:02-14:25 op 90 % en sprong daarna 91 → 99 in 18 min (BMS-ijking).
- **Oorzaak in de code:** kwartierplan `soc += geladen` met `laad_kwh = laad_w × duur` (0,6 kWh/kw.) zonder laadrendement en zonder afbouw (L-EMS-030 deed dit alleen voor de twin). Planvolging telt zo elk laadkwartier als "afwijking accu" (13:30-14:45: gepland −2,4 kW, gemeten −2,1 → −0,85): **planvolging 72,5 → 55,4 %** (14 nieuwe accu-afwijkingen). Vandaag geen kosten (vlakke prijzen 12,5-13 ct); bij een kort goedkoop blok kiest het plan te weinig laadkwartieren → **L-EMS-037** (open: plan stuurt mee via `nodig`-kwartieren en sparen in het blok).
- 15:30 plan "sparen", accu levert 0,2-0,3 kW aan het huis (13,3 ct) bij 99 %; verkoop 18:00-21:15 gepland. Klein (≈ 0,5 kWh vóór de piek), valt onder H-EMS-11.
- **H-EMS-2:** PV t/m 15:44 **5,38 kWh**, Solcast-rest 0,23 → dag ≈ 5,5 tegen day-ahead 7,43 (**≈ −26 %**), tweede voorspelling 5,20 (+4 %). Plantoetsing 30 d: 26/30 dagen minder zon, mediaan −6,8 %.
- Hypotheses: H-EMS-2 (PV te hoog; vandaag ≈ −26 %), H-EMS-11 (avond/ochtendpiek), H-EMS-14 (reservesprongen; 0 nieuw). Nieuw voorstel L-EMS-037. Geen release (tussenronde, niets acuut).

laatste ronde: 25-10 15:40, gemeten t/m 25-10 15:45

## 25-10 19:40 · tussenronde
- Andere sessies releasten **v5.127.0-5.127.3** (aanwezigheid, geen netlading vanaf 95 %, besparingstotaal bij herstart); HA herstartte 15:54, 16:09, 17:25 en 18:47 → **v5.127.3 actief**, diagnose fout 0 / storing 0. Na 18:47 prijs- en Solcast-buffer gebruikt (kort onbeschikbaar, afgevangen).
- **Avondverkoop 17:30-19:45: 9 kwartieren, 3,25 kWh uit de accu tegen 25,5-30,6 ct. Harde regel: 0× onder de reserve** - kleinste marge bij export **3,26 kWh** (18:30, 19:30), `mag_verkopen_bij_export` 9/9, `export_zonder_vrijgave_rondes` 0. Verkoopreserve tot het blok zakte mee 4,99 → 1,88 kWh; beschikbaar 9,79 → 5,41. Regeloverschot 25-10 0,071 kWh.
- Planvolging 25-10 t/m 19:30 **54,8 %** (73 kw.; accu 26, sturing 2 (+1 sinds 15:40, vermoedelijk de bijtoplading van 16:15 bij 97 % die v5.127.2 oplost), verbruik 4). Verkoopkwartieren 17:45-19:45 allemaal "volgens plan" (gemeten 2,44 tegen gepland 2,38-2,41 kW).
- **H-EMS-2:** PV dag **5,5 kWh** tegen day-ahead 7,43 → **≈ −26 %** (tweede voorspelling 5,20 → +6 %). 30 d: 26/30 dagen minder zon (mediaan −6,8 %). Afrekening 03:40.
- Reserve (lange horizon) 10,37 kWh > beschikbaar 5,41 → na het blok 21:30 geen verkoop meer. Reservesprongen 20 (0 nieuw; `na_herstart` 3 → 5, telt niet). MC 0,0 %.
- L-EMS-037 blijft open; v5.127.2 raakt het laadblok niet (alleen nieuwe netlading ≥ 95 %). Effect v5.127.2 toetsen bij het volgende blok: 0 netlading-starts boven 95 %.
- Hypotheses: H-EMS-2 (PV te hoog; vandaag ≈ −26 %), H-EMS-11 (avond/ochtendpiek; vanavond 3,25 kWh verkocht bij 26-31 ct), H-EMS-14 (reservesprongen; 0 nieuw). Geen release (tussenronde, niets acuut).

laatste ronde: 25-10 19:40, gemeten t/m 25-10 19:45

## 25-10 23:40 · tussenronde
- v5.127.3 actief; geen herstart sinds 18:47. Diagnose fout 0 / storing 0. MC 0,0 %, tekortdagen 0.
- **Avondverkoop afgerond: 13 kwartieren 17:30-21:15, 5,03 kWh uit de accu tegen 23,7-30,6 ct. Harde regel: 0× onder de reserve** (`mag_verkopen_bij_export` 13/13, `export_zonder_vrijgave_rondes` 0; kleinste marge bij export **0,57 kWh** om 21:00, daarvoor ≥ 1,61). SoC 56 → 25 % om 21:45. Regeloverschot 25-10 0,118 kWh.
- Blok 21:30-06:00: 21:30-23:15 `sparen_in_blok` (SoC 25 → 27 %), 23:15 één kwartier netladen (16,5 ct), 23:30 `expensive_quarter_soc_protected` (19,1 ct; "2,30 kWh nodig voor de rest van de nacht"). Plan 23:31: laden 00:30-04:45 tot 100 % (14,7-17,1 ct), ochtendverkoop 07:15-08:15 (45-52 ct). v5.127.2-toets (0 netlading-starts ≥ 95 %) in de ronde van 07:40.
- **Plan ≠ sturing in het laadblok:** kwartierplan zet 23:30 (19,1 ct) en 23:45 (**15,9 ct**) op "verkopen" (2,3 kW, SoC 29 → 24 %) en laadt daarna terug tegen 15,7-16,6 ct (rendement 83,5 % → terugkoop ≈ 19-20 ct): verlies als het zou gebeuren. De sturing verkoopt niet (reserve). Ook 21:30, 21:45, 22:30, 22:45 gepland 914 W uit de accu, gemeten 0 (`sparen_in_blok`). → **6 "afwijking sturing"-kwartieren vandaag** (19:40: 2). Vermoeden: `_planning_verkoopreserve_kwh` trekt binnen het blok de herlading van het lopende blok af (reserve ≈ 0), de verkooptoets niet. → **L-EMS-038** (gepland: replay in de dagafsluiting; planfout → zelf bouwen, sturing ongewijzigd).
- Planvolging 25-10 t/m 23:30 **55,7 %** (88 kw.; accu 27, sturing 6, verbruik 5, zon 1).
- Hypotheses: H-EMS-2 (PV te hoog; 25-10 ≈ −26 %, afrekening 03:40), H-EMS-11 (avond/ochtendpiek; 5,03 kWh verkocht), H-EMS-14 (reservesprongen; 0 echte nieuw, alleen `alleen_behoefte`). Geen release (tussenronde, niets acuut; geen fout gedrag, alleen planweergave).

laatste ronde: 25-10 23:40, gemeten t/m 25-10 23:45
