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

## 11-10 · samenvatting dag (6 rondes; ingekort na 14 dagen)
- Dag 10-10: PV 9,35 kWh (−6,5 % day-ahead), import 9,10, huis 12,5, piek 8451 W; verkoop onder de reserve 1 kwartier (18:45, 0,56 kWh; opgelost v5.79). PV 30 d MAE 10,5 % (bias −8,0).
- H-EMS-4 afgerond: nabeschouwing 7 d € 3,10 van € 6,51 (48 %), gemist reserve 0,48 / voorspelling 2,91. Meetbaarheid L-EMS-019 gepland. Gebouwd v5.81.0 (L-EMS-018: verkooptoets/spaarplan per kwartier, kleinste marge).
- H-EMS-9 verworpen: behoefte uit de accu 18:45 → 10:45 4,58 kWh tegen verkooptoets ≤ 5,46 en spaarplan 8,1 (+77 %) → L-EMS-017 bijgesteld (spaarplan rekent met de behoefte van de verkooptoets).
- 38 HA-herstarts (supervisor), sturing liep door; netladen 11-15 u 7,49 kWh, vol 1 min vóór blokeinde. Avondverkoop 0,34 kWh, 0× onder de reserve (19:45 grens op −0,02 = binnen meetstap).
- H-EMS-10 nieuw: reserve/behoefte springt ±0,6-1,9 kWh zonder verbruiksstap → meetbaarheid L-EMS-020. v5.86.0 (L-EMS-021) actief 23:31, leermodus eenmalig tot 12-10 05:00.

## 12-10 · samenvatting dag (6 rondes; ingekort na 14 dagen)
- Dag 11-10: PV 7,49 kWh (−17,4 % bij 13 % bewolking: ook heldere dagen te hoog → H-EMS-2 verbreed), import 8,66, huis 12,2; 40 HA-herstarts. PV 30 d MAE 10,7 % (bias −8,2). Harde regel 11-10 0× onder de reserve (direct getoetst met `verkoopkwartieren`, kleinste marge +0,035).
- Gebouwd v5.87.0 (L-EMS-017 spaarplan = behoefte verkooptoets, L-EMS-020 reservesprongen). Andere sessies v5.88-v5.93.3 (planvolging, MC vanaf blokeinde).
- Meetfouten gevonden: L-EMS-022 (negatieve `marge_bij_export` bij regelruis, 14/14 zonder echte verkoop) en L-EMS-023 (planvolging: oorzaak en status tegenstrijdig).
- PV 12-10 11,75 kWh tegen Solcast 12,69 (−7,4 %). Avondverkoop ~1,46 kWh bij 40-48 ct, 0× onder de reserve. Nacht 11→12 en 12→13 geen tekort (Brier 0, n=4). H-EMS-10: 1 sprong (herstart 23:18), geen avondsprong.

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

## 26-10 03:40 · dagafsluiting 25-10
- Actief **v5.127.3**; **release v5.127.4** (03:55, uitlegtekst; suite 6172 groen, workflow groen, HACS ververst; wacht op installatie). 0 EMS-fouten. Dag 25-10 = 25 uur (wintertijd).
- Dag 25-10 (HA-statistiek): PV **5,50 kWh** (day-ahead tracker 7,43 → **−26,1 %**; gecorrigeerd L-EMS-025 6,83 → −19,6 %; bewolking 27 %), import 12,48 (laadblok 12:15-14:53), export 5,29, accu 6,81 in / 9,44 uit, huis **15,3** (dagarchief 14,57; verwacht 8,61 → **+69 %**; witgoed 3,50 kWh: wasmachine 2,33, vaatwasser 1,17; rest 09-13 u 1,3-2,3 kWh/u onverklaard). Planvolging **54,4 %** (90 kw.; accu 28, sturing 7). **Harde regel: 0× onder de reserve** (5,03 kWh verkocht, kleinste marge 0,57, `kwartieren_onder_verkoopreserve` 0). Geen tekortnacht.
- **H-EMS-2 (PV te hoog) scherper:** 7 d MAE/bias 14,5/−11,9 %, 14 d 17,1/−15,8, 30 d 12,6/−10,7 (25/30 negatief). Nieuw per bewolking (30 d): **≤ 50 % −13,1 % (n=9), 50-90 % −13,8 (n=8), > 90 % −7,1 (n=13)** → de overschatting zit vooral op (half)heldere dagen, niet op donkere. L-EMS-025 na 4 dagen: MAE gecorrigeerd 10,5 % tegen ruw 12,0 % (eerste kleine winst).
- **Nabeschouwing 7 d (19..25-10): € 5,87 van € 6,64 = 88,4 %** (was 76,8). 25-10 € 1,40 tegen optimum € 1,23 (avondverkoop 7,68 kWh accu tegen 6,2 optimaal). 7 d: ochtendpiek +€ 2,94, avondpiek −€ 1,42, nacht −€ 1,73.
- **L-EMS-038 uitgezocht (code):** in het lopende blok geeft `_bereken_dynamische_reserve_kwh` None (blok begonnen) → `_get_soc_scaled_discharge_power` "onbekend = niet verkopen" (v5.26.6): de sturing verkoopt in het lopende blok nooit geforceerd. Het plan rekent daar met de bodem (`_planning_reserve_kwh`, v5.28.5 "net als de sturing" - klopt niet) en plant verkoop → "afwijking sturing". Fix in het plan raakt via `_netladen_volgt_in_blok` (sparen in het blok) en Rem 4 (`last_plan_shortfall`) de sturing → **voorstel (open)**, niet gebouwd. Zelf gebouwd: de misleidende uitleg ("alle 2,30 kWh nodig voor de rest van de nacht") → v5.127.4.
- **H-EMS-14:** 25-10 18 echte sprongen (00:00-02:00 lange horizon), 27 `alleen_behoefte`, 3 na herstart; **26-10 00:00 geen middernachtsprong** (na 22-10 en 25-10). MC 22:00 Brier 0,500 (n=6, ongewijzigd). Digital twin MAE **2,36 kWh** (was 1,51; dag met +69 % verbruik).
- v5.127.2-toets (geen netlading-start ≥ 95 %): blok loopt nog (03:55 SoC 79 %, plan 03:00-05:00) → ronde 07:40.
- Hypotheses: H-EMS-2 (PV te hoog, vooral heldere dagen), H-EMS-11 (avond/ochtendpiek), H-EMS-14 (reservesprongen). Release v5.127.4.

laatste ronde: 26-10 03:40, gemeten t/m 26-10 03:55

## 26-10 07:40 · tussenronde
- HA herstartte 07:12 → **v5.127.4 actief**; diagnose fout 0 / storing 0. Na de herstart Solcast 429 en prijs-/Solcastbuffer gebruikt (afgevangen).
- **v5.127.2-toets geslaagd:** nachtblok 25→26 6× `grid_charging_profitable` gestart (23:45-02:00) bij SoC 31-47 %, **0 starts ≥ 95 %**; laden 02:00-05:10 tot 100 %, daarna 05:11 `default_smart`, 06:00 `discharging_window`, 06:30 `solar_capture_deferred` - geen bijtoplading meer.
- Laadblok: 00:00-02:00 wisselend `sparen_in_blok`/netladen (7 wissels), plan 23:31 zei laden 00:30-04:45 → planvolging vandaag t/m 07:15 **53,3 %** (30 kw.; **accu 13**, sturing 0, verbruik 1). De 13 accu-afwijkingen liggen in het blok (laden later/anders dan gepland); **0 "afwijking sturing"** (L-EMS-038 speelde vannacht niet: geen verkoopkwartieren in het blok gepland).
- **Ochtendverkoop gestart 07:15** (plan 07:15-08:15, 45,8-49,4 ct): 07:15 0,49 + 07:30 0,39 kWh uit de accu. **Harde regel: 0× onder de reserve** (`mag_verkopen_bij_export` 2/2, kleinste marge **7,26 kWh**; verkoopreserve 1,73 tot het blok van 11:00). SoC 98 → 88 % om 07:40.
- Reserve nu 7,08 kWh (blok 11:00), beschikbaar 8,99; MC 0,0 %; reservesprongen 26-10: 2 (07:15 na herstart, 07:30 ±0,27 kWh lange horizon). Digital twin MAE 2,32 kWh.
- Andere sessie releasete om 07:43 **v5.128.0** (akkoord Ruud 26-10): L-EMS-037 en L-EMS-038 gebouwd, nachtcontrole telt bewust-niet-ontladen niet mee, sensor 'Besparing deze maand', en bijladen tot 100 % bij een heel lage prijs (≤ belasting+btw, max 15 ct) - die uitzondering op v5.127.2 telt in de toets 'starts ≥ 95 %' apart mee. **Actief sinds de herstart van 07:47.**
- Hypotheses: H-EMS-2 (PV te hoog, vooral heldere dagen; vandaag bewolking 94 %), H-EMS-11 (ochtend/avondpiek; ochtendverkoop loopt), H-EMS-14 (reservesprongen; 0 echte nieuw). Geen release (tussenronde, niets acuut).

laatste ronde: 26-10 07:40, gemeten t/m 26-10 07:45

## 26-10 11:40 · tussenronde
- HA herstartte 10:27 → **v5.129.1 actief** (andere sessie: batterijlader als gepland laadapparaat, 09:58/10:25). Fout 0 / storing 0.
- **Ochtendverkoop 07:15-08:15** (4 kw., 45,8-52,3 ct): **harde regel 0× onder de reserve** (`mag_verkopen_bij_export` 4/4, kleinste marge **5,99 kWh**, verkoopreserve 1,73). 07:45 `export_zonder_vrijgave_rondes` 2 = de herstart van 07:47 (marge 6,56, geen schending). Daarna 08:15 `expensive_quarter_soc_protected`, zonopvang; 11:00 blok → `sparen_in_blok` bij SoC 89 %.
- **L-EMS-037 eerste toets:** planvolging vandaag 46 kw. **47,8 %**; **accu 13 = gelijk aan 07:40 → 0 nieuwe 'afwijking accu' na v5.128.0**; sturing **0 → 2** (tijdstip niet te herleiden: attributen niet in de recorder; vermoedelijk rond de herstarts 07:47/10:27). Laadplan 11:24: netladen 12:30-13:00 (2 kw., 89 → 97 % met afbouw) → toets 15:40.
- **Nieuw (meetfout):** *Besparing t.o.v. zonder accu-sturing* schrijft bij elke herstart 30 s het ongecorrigeerde dagcijfer: 07:12 −1,30, 07:47 −0,69, 10:27 −0,41 (ervoor/erna −0,01/0,42/0,71). Oorzaak: vóór de eerste ronde geen accustand → geen voorraadcorrectie; het totaal kreeg hiervoor in v5.127.3 al `available` = na de eerste ronde, de dagsensor niet → **L-EMS-039 gepland**, klaargezet op `wip/l-ems-039` (73c0774, suite 6219 groen, 3 tests).
- MC 0,0-0,2 % in het blok; reservesprongen sinds 07:40: 5 (4 rond de herstart 07:43-07:55 met `na_herstart`, 1 om 09:06 +0,70 lange horizon). Digital twin MAE 2,32 → **2,18 kWh**.
- Hypotheses: H-EMS-2 (PV te hoog; vandaag tot nu `zon_verschil` +0,36 kWh = iets méér zon dan gepland), H-EMS-11 (ochtendpiek verkocht, 4 kw.), H-EMS-14 (reservesprongen; vooral herstarts). Geen release (tussenronde).

laatste ronde: 26-10 11:40, gemeten t/m 26-10 11:45

## 26-10 15:40 · tussenronde
- **v5.131.0 actief** (andere sessie: v5.129.2 13:09, v5.130.0 14:52, v5.131.0 15:11; HA-herstarts 13:32, 15:00, 15:13). Fout 0 / storing 0; Solcast-limiet 10/10 (buffer gebruikt).
- **L-EMS-037 toets laadblok (n=1):** plan 11:24 netladen 12:30-13:00 tot 97 %; gemeten 12:30 start bij 93 % (zon had 89 → 93 gedaan), 12:59 **97 %** = plan, daarna zon tot 100 % (13:01). Netlading-start < 95 % (v5.127.2 ✓).
- **L-EMS-039 geverifieerd:** 3 herstarts → *Besparing* onbeschikbaar → eindwaarde (0,53 / 0,59 / 0,57); 0 rauwe tussenwaarden (vóór: −1,30/−0,69/−0,41).
- **Harde regel: 0× onder de reserve** (geen verkoopkwartieren sinds 08:00). Reserve 10,37 = capaciteit (ongekapt 17-18 kWh; volgend blok morgen 10:45, 20 u) > beschikbaar 9,56 → vanavond geen verkoop gepland (17-18 u 40-44 ct, nacht 31-34 ct). → nabeschouwing 03:40 (H-EMS-11).
- Planvolging vandaag **39,3 %** (61 kw.; accu 13 → **18**, sturing 2 = gelijk). Nieuwe 'accu' 13:15 (zonopvang op 100 %), 14:15, 15:00 (herstart) - niet in het laadblok.
- **Nieuw (H-EMS-14, n=1):** herstart 15:00:25 → 14 s reserve **76,1 / 78,8 kWh** (accu 10,37): `regelverschuiving_w` 1462/1497 W × 20 u + lange horizon 24,5 kWh; 15:00:39 weer 10,37. Richting voorzichtig (geen verkoop), maar foute data. Herstarts 13:32 en 15:13 gaven dit niet. Vermoeden: regelsensor (P1 + verschuiving / P1 regeldoel) en verbruikssensor lezen bij het opstarten uit de pas; geen plausibiliteitsgrens op de verschuiving. → dagafsluiting: code nalezen; bewijs = kandidaat-meetfout (zelf bouwen alleen als het puur de opstartwaarde betreft).
- MC 0,0 %; reservesprongen 3 echt / 32 `alleen_behoefte` / 13 `na_herstart`. Digital twin MAE 2,18 → **2,01 kWh**.
- Hypotheses: H-EMS-2 (PV te hoog; vandaag zon +0,51 kWh boven plan), H-EMS-11 (avondpiek: vandaag niets te verkopen door de lange horizon), H-EMS-14 (reservesprongen; opstartpiek 15:00). Geen release (tussenronde, niets acuut).

laatste ronde: 26-10 15:40, gemeten t/m 26-10 15:45

## 26-10 19:40 · tussenronde
- **v5.131.2 actief** (andere sessie 17:28: batterijlader; HA-herstart 19:15). Fout 0 / storing 0. DNS-storing 19:33 (extern, afgevangen).
- **Harde regel: 0× onder de reserve** - geen verkoopkwartieren sinds 08:00; reserve 10,37 = capaciteit (ongekapt 13-18 kWh, blok morgen 10:45) > beschikbaar → vanavond terecht niets verkocht.
- **Avondpiek 15:45-19:40:** accu 9,45 → 5,30 kWh (4,15 kWh naar het huis), netafname **0,41 kWh** (5-min gemiddelden), vooral korte pieken tot 2,1-2,2 kW; grootste 17:50 (gem. 756 W) en 18:00 (483 W). ~€ 0,16 bij 39-44 ct. Herkomst pieken (accu-reactietijd of last > accuvermogen) → dagafsluiting met `regeloverschot_kwh`.
- **v5.131.1-toets (H-EMS-14) geslaagd, n=1:** herstart 19:15 → 3 min 'opstarten', reserve daarna direct 10,37 (geen opstartpiek; 15:00 was 79 kWh). `regelverschuiving_w` 10 W.
- **Nieuw (MC):** tekortkans springt per minuut tussen 2 en 94 % (17:05-18:33; o.a. 18:15 14 → 18:16 86 → 18:18 11 → 18:20 89 %). Oorzaak: beschikbaar 5,4 kWh ligt vlak bij het deterministische tekort tot het blok (4,9 kWh) en de spreiding is smal (p10-p90 11,3-12,6 kWh = 1,3 kWh over 16 u); `live_correctie_extra_kwh` wisselt 0 ↔ 1,5 kWh per minuut. Kalibratie 22:00 Brier 0,500 (n=6, kansen alleen 0 of 100). Adviserend (stuurt niets) → onderdeel van H-EMS-14 (stabiliteit), voorstel na meer nachten.
- **Nachttoets vannacht:** nodig tot het blok 5,03 kWh tegen beschikbaar 5,30 (19:42) → krappe nacht; meten 03:40/07:40: laagste SoC, netafname bij lege accu (tekortnacht ja/nee) tegen MC 7 %.
- Batterijlader (v5.131.2 pas actief na 19:15): 17:19-19:13 elk kwartier test_aan → laden 3 min → voltooid (5×); na 19:15 doorlopend 'aan_het_laden' → effect dagafsluiting.
- Besparing vandaag 1,51 → 1,54; herstart 19:15 → 30 s onbeschikbaar, geen rauw tussencijfer (L-EMS-039 ✓). Digital twin MAE 1,95 kWh. Reservesprongen: 0 echt, 46 `alleen_behoefte`, 2 `na_herstart`.
- Hypotheses: H-EMS-2 (PV te hoog; vandaag 100 % bewolking), H-EMS-11 (avondpiek: niets te verkopen, accu dekt huis), H-EMS-14 (reservesprongen/stabiliteit: opstartpiek opgelost, MC-schommeling nieuw). Geen release (tussenronde, niets acuut).

laatste ronde: 26-10 19:40, gemeten t/m 26-10 19:45

## 26-10 23:40 · tussenronde
- **v5.135.1 actief**; v5.136.0 (andere sessie 23:15, NILM-kandidaten) gedownload, wacht op een herstart. HA-herstarts 20:06, 20:25, 21:08, 21:52. Fout 0 / storing 0; Zonneplan-prijssensor 21:52 kort leeg (laatste prijzen gebruikt), Solcast 10/10.
- **Harde regel: 0× onder de reserve** - geen verkoopkwartieren sinds 08:00; reserve 10,37 = capaciteit > beschikbaar.
- **Avond/nacht tot 23:41:** accu 5,30 → 3,34 kWh (1,96 kWh naar het huis), netafname 19:45-23:00 **0,12 kWh**, export 0,06 (regelverschuiving ~20 Wh/u). Krappe nacht: marge **0,54 kWh** tot het blok 10:45 (nodig 2,80); MC tot blok 0,3 %. Om 22:00 bewaarde kans **26,7 %** (beschikbaar 3,92) = eerste avond met een kans tussen 0 en 100 → uitslag tekortnacht ja/nee in de dagafsluiting.
- **Stilstandcontrole (nieuw, alle modules):** 1 echt vastzittend: *Accugezondheid over de tijd* - nooit een gemeten capaciteit, want alleen de handmatige kalibratie (< 30 %, ≥ 70 procentpunt) levert er een; 30 d SoC-reeks heeft ~12 natuurlijke laadrondes die dat ook halen → **L-EMS-040** (open). Airco: aanzetgrens 19,0 °C gevuld (v5.134.0 ✓), dagritme werkdag/weekend geleerd (ochtend nooit aan = geen data, geen fout), knop bewust uit. Overige "wachten" lopen op: sluipverbruik 25/30 d, NILM 39/52, digital twin 2,0 kWh (19 %, label bijna_klaar), weerensemble 78,5 %; *battery protection* unknown = geen begrenzing actief (normaal), *PV hourly bias* unknown 's nachts (geen profieluur).
- Reservesprongen: 0 echt / 40 `alleen_behoefte` / 8 `na_herstart`. Digital twin MAE 1,95 → **2,02 kWh**. Batterijlader 'nachtrust'.
- Hypotheses: H-EMS-2 (PV te hoog), H-EMS-11 (avondpiek: accu dekte het huis, niets te verkopen), H-EMS-14 (stabiliteit; MC-kans 22:00 niet meer binair). Geen release (tussenronde, niets acuut; v5.136.0 nog niet geïnstalleerd).

laatste ronde: 26-10 23:40, gemeten t/m 26-10 23:45

## 27-10 03:40 · dagafsluiting 26-10
- Actief **v5.135.1**; v5.136.0 gedownload (HACS), wacht op een herstart → **geen EMS-release** (niet stapelen; niets acuut). Fout 0 / storing 0. Geen purge/repack in de log; DNS-storing ~02:12 (extern).
- Dag 26-10: PV **5,40 kWh** (day-ahead 5,24 → **+3,2 %** bij 99,6 % bewolking; gecorrigeerd L-EMS-025 4,81 → +12,3 %), import 11,62 (nachtblok + 12:30-13:00), export 2,80, accu 12,54 in / 9,78 uit, huis **11,5** (dagarchief 10,7; verwacht 8,76 → +22..31 %). Besparing € 1,26. **Harde regel: 0× onder de reserve** (4 verkoopkwartieren 07:15-08:00, 2,10 kWh, kleinste marge 5,99). Geen tekortnacht (nacht 25→26).
- **Planvolging 26-10 43,6 %** (laagste in 14 d; mediaan verschil 249 W tegen 57-152 W): verbruik 24, accu 22, sturing 2. 11 HA-herstarts en nieuwe functies (batterijlader, airco op zonoverschot) op één dag; 7 d 58,6 %.
- **H-EMS-2:** 7 d MAE/bias 13,8/−10,3 %, 14 d 16,8/−15,1, 30 d 12,5/−10,8; per bewolking ≤ 50 % −13,1 (n=9), 50-90 % −13,8 (n=8), > 90 % −7,3 (n=13). **L-EMS-025 dag 5: gecorrigeerd MAE 10,8 tegen ruw 10,2 → correctie nu iets slechter** (26-10 +12,3 tegen +3,2). Afronden 29-10.
- **Nieuw (meetlat, L-EMS-042 open):** nabeschouwing 7 d realisatie **116,6 %** (€ 6,74 van € 5,78): 'best mogelijk' laadt bewust niet uit het net (v4.5), de sturing wel (26-10 netarbitrage € 1,81). Met netladen benaderd 73,2 %. De avondpiek-/ochtendpiekcijfers van H-EMS-11 komen uit die meetlat → H-EMS-11 eerst op een eerlijke meetlat.
- **Nieuw (meetbaarheid, L-EMS-041 gepland):** MC-kalibratie mist de nacht 25→26: om 22:00 liep het blok al (21:30-06:00), `_leg_mc_22u_vast` wordt dan overgeslagen (`start > now`). Brier 0,600 (n=5). 22:00-kans avond 26-10 26,7 % → uitslag vanochtend.
- Nacht 26→27 03:45: beschikbaar 2,30 kWh (SoC 30 %), blok 10:45, MC tot blok 2,1 %. Digital twin MAE 2,02 → **1,83 kWh**. Reservesprongen 2 echt / 38 `alleen_behoefte` / 8 `na_herstart`.
- Stilstand: alleen *Accugezondheid over de tijd* (L-EMS-040, open; deel a gepland na v5.136.0). Nieuw in *Nog niet bepaald* (< 7 d, lopen op): verbruik per dagtype, regressiewoud, scenarioplan.
- Hypotheses: H-EMS-2 (PV te hoog; correctie L-EMS-025 helpt nog niet), H-EMS-11 (avond-/ochtendpiek; wacht op L-EMS-042), H-EMS-14 (reservesprongen; rustig). Geen release.

laatste ronde: 27-10 03:40, gemeten t/m 27-10 03:50

## 27-10 07:40 · tussenronde
- HA herstartte 06:04 → **v5.136.0 actief** (fout 0 / storing 0). Andere sessie releasete v5.137.0 + **v5.138.0** (batterijlader: aan zolang er iets aan hangt, minder testschakelingen); v5.138.0 om 07:31 gedownload, wacht op een herstart. Na de herstart prijs-/Solcastbuffer gebruikt (afgevangen). Geen purge/repack.
- **Nacht 26→27:** `default_smart` de hele ronde, geen netladen, **0 verkoopkwartieren → harde regel niet geraakt**. SoC 32 → 24 % (03:40-07:40, ~1 %/25 min), beschikbaar 1,50 kWh, blok 10:45, MC tot blok **0,4 %**. 22:00-kans (26,7 %) wordt na de nacht afgerekend; tekort tot nu toe 0.
- Digital twin MAE 1,83 → **1,76 kWh**. Plantoetsing 30 d: zon structureel te hoog (26/30 dagen, mediaan −6,8 %) = H-EMS-2.
- **Nieuw: bug airco-voorverwarmen (L-EMS-043, gepland).** *Airco besluit* toont "nu 38 ct, straks tot **390089400 ct**". `_airco_buffer_ronde` geeft de ruwe prijsreeks (1e-7 €, PRICE_SCALE_FACTOR) aan `airco_sturing.buffer`, terwijl `prijs_nu` in €/kWh is → elk verwarmbesluit krijgt +0,5 °C en "duur kwartier, halve graad lager" komt nooit. Sinds v5.66; de tests geven de reeks al in € (`_met_prijzen`) en zien het daarom niet. Nu geen gevolg (knop Airco automaat uit) → niet acuut; v5.138.0 nog niet geïnstalleerd → bouwen in de dagafsluiting.
- Stilstand: ongewijzigd (alleen *Accugezondheid over de tijd*, L-EMS-040). Airco besluit rekent (aanzet 19,0 °C geleerd).
- Hypotheses: H-EMS-2 (PV te hoog; vandaag 100 % bewolking), H-EMS-11 (wacht op L-EMS-042), H-EMS-14 (rustig). Geen release (tussenronde, niets acuut).

laatste ronde: 27-10 07:40, gemeten t/m 27-10 07:40

## 27-10 11:40 · tussenronde
- Herstarts 08:00 en 11:34 → **v5.139.0 actief** (andere sessie, 10:51: planning vaatwasser/wasmachine). Fout 0 / storing 0; na de herstart Zonneplan-/prijsbuffer gebruikt (afgevangen). Geen release (tussenronde, niets acuut, niets gestapeld).
- **Nacht 26→27 afgerekend: geen tekort.** SoC 23 → **19 %** tot het blok, P1 rond 0 (5-min −31..+93 W) → geen netafname bij lege accu. 22:00-kans 26,7 % → Brier-bijdrage 0,071 (reeks n=6 ≈ 0,51, was 0,600).
- **Harde regel:** 0 verkoopkwartieren vandaag. Laadblok vanaf 10:45 (`grid_charging_profitable`), SoC 19 → 33 % om 11:40.
- Nieuw (n=1, observatie): `cheapest_block_start` schoof tijdens het lopende blok 10:45 → 11:00 (11:00:27, zonder herstart) → 11:30 (herstart), eind 14:30; laden liep ononderbroken door → geen gevolg. MC gaf in de eerste blokronde 100,0 (10:45:27), daarna 3-6 %. Dagafsluiting: in code nagaan welke start de sensor publiceert (lopend blok of resterend venster).
- Digital twin MAE 1,76 → **1,59 kWh**. L-EMS-043 (airco-prijseenheid) nog in main; besluit nu "niets" (zelf bediend), knop uit → bouwen 28-10 03:40 zoals gepland.
- Stilstand: ongewijzigd, alleen *Accugezondheid over de tijd* (L-EMS-040).
- Hypotheses: H-EMS-2 (PV te hoog; bewolking 78 %), H-EMS-11 (wacht op L-EMS-042), H-EMS-14 (reservesprongen: 7 echt / 30 alleen_behoefte / 11 na_herstart, rustig).

laatste ronde: 27-10 11:40, gemeten t/m 27-10 11:42

## 27-10 15:58 · tussenronde
- Herstart 12:32 → **v5.139.1 actief** (andere sessie, 12:00: witgoedcyclus overleeft herstart). Fout 0 / storing 0. Zonneplan-API 500 (12:47-13:13, extern) → EMS gebruikte de laatste waarden (afgevangen). Geen release (tussenronde, niets acuut).
- **Laadblok liep door tot de accu vol was:** `grid_charging_profitable` 10:45 → **15:45**; `cheapest_block_start` schoof mee (11:00 → 11:30 → 12:30 → 14:30 → 15:30; sensor publiceert de start van het resterende venster, by design). Netafname 11:40-14:30 5,71 kWh, **14:30-15:45 2,36 kWh tegen gem. 29,1 ct** (26,7-33,7); SoC 33 → 99 %. Met rendement 83,5 % = 34,9 ct tegen avondprijs 41+ ct → nog winstgevend. Reserve 10,37 kWh > beschikbaar 10,25 → vanavond niets te verkopen (zelfde patroon als H-EMS-11).
- **Harde regel:** 0 verkoopkwartieren 11:40-15:55 (P1 5-min altijd ≥ 0).
- **PV vandaag ~5,18 kWh** (t/m 16:00): day-ahead 5,95 → **−13,0 %** bij 96,5 % bewolking (H-EMS-2); gecorrigeerd (L-EMS-025, −8,1 %) 5,47 → **−5,3 %** → correctie helpt vandaag. Solcast intraday 4,17 (te laag, +24 %). Solcast-API limiet 10/10 bereikt (bekend, niet melden).
- Weerensemble 78,5 % (26-10) → **54,0 %** ("kwaliteit te laag"), beide bronnen identiek 54,0 %. Venster = 200 daglichtwaarnemingen (~2 dagen); 'oneens' = PV > 1,3× Solcast-nu bij > 70 % bewolking → spiegelt de te lage intraday-Solcast van de laatste dagen, geen bug. Label schommelt per weertype (meetbaarheid; geen voorstel).
- Digital twin MAE 1,59 → **1,71 kWh**. Airco: aanzetgrens 19,0 → **19,5 °C** (geleerd), besluit "verwarmen", knop uit; L-EMS-043 nog zichtbaar ("straks tot 483247300 ct") → bouwen 28-10 03:40.
- Stilstand: ongewijzigd, alleen *Accugezondheid over de tijd* (L-EMS-040). Nog niet bepaald 14 (wachten, lopen op).
- Hypotheses: H-EMS-2 (PV te hoog; correctie vandaag beter), H-EMS-11 (wacht op L-EMS-042), H-EMS-14 (rustig).

laatste ronde: 27-10 15:58, gemeten t/m 27-10 15:55

## 27-10 19:41 · tussenronde
- **v5.139.1 actief**, geen herstart sinds 12:32, geen nieuwe release op main. Fout 0 / storing 0. SolarEdge-Modbus 18:26 geen verbinding (omvormer na zonsondergang), HomeWizard-REST time-outs - extern, afgevangen. Geen release (tussenronde, niets acuut).
- **Harde regel: 0× onder de reserve.** Eerste verkoop sinds 26-10: **18:30 en 18:45, 0,99 kWh** tegen 47,6/48,3 ct, beschikbaar 7,60/7,03 tegen verkoopreserve 6,38/5,92 (deel tot het blok × 1,25; na-blokdeel vrij volgens v5.70) → marge 1,22/1,11 kWh, bij export min. 1,05.
- **Nieuw (H-EMS-14, n=1):** om 19:41 beschikbaar 6,34 tegen nodig tot blok **5,77** (× 1,25 = 7,21) → 0,57 kWh boven de ruwe behoefte, 0,87 onder de marge. De behoefte tot het blok steeg 4,73 (18:45) → 5,77 doordat de live correctie om 19:01 van ~0,2 naar 1,5 kWh ging. 16:32-19:36 22 wissels `alleen_behoefte` (0 ↔ 1,5 kWh, verhouding tot 4,4); 18:03-19:01 geen wissel → de verkoop viel in die rustige periode, de grens wisselde tijdens de verkoopkwartieren niet (meetcriterium L-EMS-031 dus niet geraakt). Oorzaak in code: met airco als zware last (`SUSTAINED_HEAVY_LOAD_SOURCES`) neemt `_get_smoothed_consumption_correction_ratio` de laatste huismeting zonder mediaan, dus ook kook-/tv-pieken. Uitslag (tekortnacht ja/nee, netafname bij lege accu) in de dagafsluiting; bij een tekort → voorstel.
- **Nieuw (H-EMS-15):** digital twin MAE 1,71 → **1,888 kWh**; laadblokuren **5,04** (n=12: 26-10 00-05, 27-10 14:15-19:15) tegen 1,10 overig (n=48). 16:15 voorspeld 0,50 tegen 10,14; openstaand 20:15 0,00 / 21:15 0,05 (werkelijk ~6). Twin laadt alleen binnen de blokgrenzen van het voorspelmoment; vandaag liep `grid_charging_profitable` met het schuivende blok door tot 15:45. Dagafsluiting: replay in code (meetfout = zelf bouwen als bevestigd).
- MC tot blok 1,9 %, blok 28-10 10:15. Besparing vandaag € 0,93. Airco besluit "niets" (20,6 °C, aanzet 19,0), knop uit; L-EMS-043 bouwen 28-10 03:40.
- Stilstand: ongewijzigd, alleen *Accugezondheid over de tijd* (L-EMS-040). Nog niet bepaald 14 (wachten).
- Hypotheses: H-EMS-2 (PV te hoog; uitslag 27-10 in dagafsluiting), H-EMS-14 (live correctie + verkoop; nacht toetst), H-EMS-15 (twin in laadblokuren). H-EMS-11 wacht op L-EMS-042 (geparkeerd, max 3 actief).

laatste ronde: 27-10 19:41, gemeten t/m 27-10 19:45

## 27-10 23:41 · tussenronde
- Herstart 21:01 → **v5.140.0 actief** (andere sessie 20:23: L-EMS-042 nabeschouwing met netladen + meetlog-opslag). Fout 0 / storing 0. DNS-storing 21:02-21:44 (extern: Nabu Casa, Bitvavo, IG), na de herstart prijsbuffer gebruikt - afgevangen. Geen release (tussenronde, niets acuut).
- **Harde regel: 0× onder de reserve.** Geen verkoop 19:41-23:45; P1-export per uur 0,019-0,027 kWh (regeloverschot), import 0,016-0,040.
- **Nacht 27→28:** 23:41 beschikbaar 4,26 kWh tegen nodig tot blok (10:15) 2,37 ruw → marge 1,89; reserve 8,21 incl. na-blokdeel 4,20 (wordt in het blok bijgeladen). 19:41-23:41 2,08 kWh uit de accu. MC 0,0 %.
- **H-EMS-14:** 20 reservesprongen 19:47-23:00 (2 na herstart); live correctie wisselt 0 ↔ 1,5 kWh tot 21:25, daarna ≤ 1,0 en na 22:30 ≤ 0,3 (huis rustig). Uitslag nacht in de dagafsluiting.
- **L-EMS-042:** actief sinds 21:01; `nabeschouwing_7d` toont nog alleen 20..26-10 op de oude meetlat (geen `zonder_netladen`-velden). Eerste dag op de nieuwe meetlat = 27-10 → toets in de dagafsluiting (realisatie ≤ 100 %).
- Digital twin MAE 1,888 → **1,801 kWh** (n=60); H-EMS-15 replay in de dagafsluiting. Besparing vandaag € 1,29. Airco besluit "verwarmen" (projectie 18,8 °C), knop uit; L-EMS-043 bouwen 28-10 03:40.
- Stilstand: **geen** (Accugezondheid over de tijd = L-EMS-040, afgewezen 27-10 → niet meer melden). Nog niet bepaald 14 (wachten).
- Hypotheses: H-EMS-2 (PV te hoog), H-EMS-14 (live correctie; nacht toetst), H-EMS-15 (twin in laadblokuren). H-EMS-11 kan na L-EMS-042 op de nieuwe meetlat (dagafsluiting).

laatste ronde: 27-10 23:41, gemeten t/m 27-10 23:45

## 28-10 03:40 · dagafsluiting 27-10
- **v5.140.0 actief** (herstart 21:01), geen purge/repack in de log. Fout 0 / storing 0. **Release v5.141.0** (L-EMS-043 + L-EMS-041, zie onder).
- Dag 27-10: PV **5,19 kWh** bij 4,7 % bewolking (day-ahead 5,95 → **−12,9 %**; gecorrigeerd L-EMS-025 5,46 → −5,0 %), import 11,42 (laadblok 14:15-19:15), export 1,39, accu 10,93 in / 8,03 uit, huis **12,3** (verwacht 9,39 → +31 %, 4,3 graaddagen). Besparing € 0,99. **Harde regel: 0× onder de reserve** (0,99 kWh 18:30-18:45, kleinste marge 1,05). Geen tekortnacht (26→27, laagste SoC 20 %).
- **L-EMS-042 eerste dag op de nieuwe meetlat:** realisatie **52,6 %** (€ 1,21 van € 2,30; ≤ 100 % ✓), gemist reserve 0,73 / voorspelling 0,35. Per dagdeel: optimum laadt 's nachts 6,7 kWh uit het net (−1,94) en zet die in de ochtend- (+2,10) en avondpiek (+1,96) in; de sturing laadde pas 14:15. → **H-EMS-11 herstart** op deze meetlat (n=1; oude dagen rollen er tot 03-11 uit).
- **H-EMS-2:** 7 d MAE/bias 14,2/−10,7 %, 14 d 15,8/−14,1, 30 d 12,7/−10,9; per bewolking ≤ 50 % −13,1 (n=10), 50-90 % −14,6 (n=7), > 90 % −7,3 (n=13) → te hoog vooral bij zon. L-EMS-025 dag 6: gecorrigeerd MAE **9,9** tegen ruw 10,7 → weer iets beter; afronden 29-10.
- **H-EMS-15 bevestigd in code:** twin-MAE 1,75 kWh; vensters met een laadblok **2,63** (n=30) tegen 0,87 (n=30). `_run_digital_twin_simulation` laadt in `smart` binnen het blok van het voorspelmoment elk kwartier op vol vermogen, los van het kwartierplan (26-10 00:00 voorspeld 10,3 tegen 2,8 - laden liep tot 05:00) en mist een blok dat later verschuift (27-10 16:15: 0,5 tegen 10,1). → **L-EMS-044** (gepland, adviserende simulatie).
- **H-EMS-14:** nacht 26→27 geen tekort; nacht 27→28 om 04:05 beschikbaar 3,34 tegen nodig tot blok 1,19 (marge 2,15), MC 0 %. 21 sprongen (23 `alleen_behoefte`). Uitslag nacht 27→28 om 07:40.
- MC Brier **0,414** (n=5; 27-10 26,7 % zonder tekort). Kans 27-10 22:00 0,3 %.
- **Gebouwd v5.141.0:** L-EMS-043 (airco-buffer deelt de prijsreeks door `PRICE_SCALE_FACTOR`; geen 'straks 390089400 ct' meer, 'duur kwartier' werkt weer) en L-EMS-041 (22:00-stand ook als het blok al loopt, apart als `nachten_in_blok`). Suite 6331 groen (+6 tests).
- Stilstand: **geen** (14 'wachten' lopen op; sluipverbruik 27/30, NILM 39/53). Airco: aanzet 19,5 °C geleerd, knop uit.
- Hypotheses: H-EMS-2 (PV te hoog bij zon), H-EMS-14 (live correctie), H-EMS-11 (piek-/nachtladen op de nieuwe meetlat). H-EMS-15 → L-EMS-044.

laatste ronde: 28-10 03:40, gemeten t/m 28-10 04:05

## 28-10 07:41 · tussenronde
- Herstarts 06:10 en 06:52 → **v5.141.1 actief** (v5.141.0 = L-EMS-043 + L-EMS-041 sinds 06:10; v5.141.1 batterijlader, andere sessie 06:48). Fout 0 / storing 0; na de herstart prijsbuffer gebruikt (afgevangen). Geen release (tussenronde, niets acuut).
- **Nacht 27→28 afgerekend: geen tekort.** SoC 40 % (04:05) → **30 %** (07:40), P1-import per uur 0,012-0,027 kWh → geen netafname bij lege accu. 22:00-kans 0,3 % → Brier-bijdrage ~0 (reeks wordt in de dagafsluiting bijgewerkt). H-EMS-14: tweede nacht op rij zonder tekort ondanks de schommelende live correctie.
- **Harde regel: 0× onder de reserve.** Geen verkoop 04:05-07:40 (export per uur 0,013-0,018, regeloverschot).
- **L-EMS-043 eerste meting na installatie:** "duur kwartier: nu 50 ct, straks 38 ct", doel 20,5 °C bij basis 21,0 → prijsschaal klopt en de tak 'halve graad lager' werkt (n=1). Aandeel +0,5 °C per dag in de dagafsluiting → dan geverifieerd.
- Stilstand: **geen.** Gecontroleerd: airco-dagritme werkdag `bedtijd` leeg (keer_uit 2) - bewust: de vaste uittijd 22:00 gaat voor en die uitschakeling door het EMS telt niet als eigen bediening (climate.woonkamer elke avond 22:00:01 uit). Ochtend `warm_om` leeg: 's ochtends wordt de airco niet gebruikt (0/13 ochtenden). 14 'wachten' lopen op.
- Digital twin MAE **1,746 kWh** (L-EMS-044 gepland). Blok 10:15 (`cheapest_block_start` 09:15Z).
- Hypotheses: H-EMS-2 (PV te hoog bij zon), H-EMS-14 (live correctie; 2 nachten zonder tekort), H-EMS-11 (piek-/nachtladen op de nieuwe meetlat).

laatste ronde: 28-10 07:41, gemeten t/m 28-10 07:45

## 28-10 11:42 · tussenronde
- Herstart 10:25 (HACS-installatie); **v5.141.1 actief**, geen release open. Fout 0 / storing 0; na de herstart Solcast/Zonneplan kort onbeschikbaar en prijsbuffer gebruikt (afgevangen). Geen release (tussenronde, niets acuut).
- **Harde regel: 0× onder de reserve** 07:45-11:45 (geen verkoopkwartieren op 28-10; export per uur 0,022-0,036 = regeloverschot). SoC 29-33 % tot 10:00, daarna 33 → 46 % (PV + blok 10:15-15:15, +6,11 kWh gepland).
- **PV tot nu (H-EMS-2):** 07-11 u werkelijk 2,43 kWh tegen Solcast 2,59 → **−6,3 %** (per uur 0,01/0,04 · 0,21/0,30 · 0,89/0,90 · 1,32/1,35): ochtendranden te hoog, 09-11 u ≈ goed. Dag-ahead EMS 9,56, Solcast nu 9,20; afrekening dagafsluiting.
- Digital twin MAE **1,682 kWh** (1,746 → lager; L-EMS-044 gepland). MC tot blok 0 %; tekortnachten 7 d 0.
- **Stilstand: geen.** Gecontroleerd: NILM *koffiezetapparaat* staat sinds 27-08 op 3 dagen → sensor gaf van 30-08 tot 26-10 geen data (stekker), telt sinds 26-10 weer: geen fout, volgroeit vanzelf. 'Nog niet bepaald' 11 wachten (sluipverbruik 27/30, NILM 39/53).
- Hypotheses: H-EMS-2 (PV te hoog bij zon; vandaag tot nu −6 %), H-EMS-14 (live correctie; 2 nachten zonder tekort), H-EMS-11 (piek-/nachtladen op de nieuwe meetlat).

laatste ronde: 28-10 11:42, gemeten t/m 28-10 11:45

## 28-10 15:43 · tussenronde
- **v5.141.1 actief**, geen herstart sinds 10:25, geen nieuwe release op main. Fout 0 / storing 0. Zonneplan-prijzen 13:16-14:01 4× fout bij de externe integratie (`sustainability_score` None) → EMS gebruikte de laatst bekende prijzen (43 kwartieren vooruit), om 15:45 weer 228 kwartieren t/m 29-10 - extern, afgevangen. Geen release (tussenronde, niets acuut).
- **Harde regel: 0× onder de reserve** 11:45-15:45 (geen verkoopkwartieren op 28-10; P1-export 12-15 u 0,000-0,002 kWh). Blok 10:15-15:15 afgerond: import 12-15 u 0,77/2,63/2,33/1,37 kWh, SoC **100 %** om 15:45, beschikbaar 10,37 kWh.
- **PV (H-EMS-2):** 07-15 u werkelijk **7,38** kWh tegen Solcast 8,07 → **−8,5 %**; 11-15 u 4,95 tegen 5,49 (−9,7 %, uur-MAE 0,33): 12 u 0,95 tegen 1,79 (wolk), 13-14 u juist boven Solcast. Dag-ahead EMS 9,56 → dag komt op ~7,9 (≈ −17 %) → weer te hoog bij zon; afrekening dagafsluiting.
- **Besparing tot nu −€ 0,42** (rauw −2,93 + SoC-correctie 2,52 voor 6,22 kWh extra in de accu à 40,4 ct): normaal na een middagblok, de opbrengst volgt bij het ontladen in de avondpiek; dagwaarde in de dagafsluiting.
- Digital twin MAE **1,394 kWh** (1,682 → lager; vensters met het blok 26/27-10 rollen eruit). MC tot blok 0 %; Brier 0,414 (n=5), nacht 27→28 (22:00 0,3 %, geen tekort) komt in het dagrecord van 28-10.
- Airco besluit "verwarmen" (19,4 °C < aanzet 19,5; voorverwarmen 'nu 43 ct, straks 56 ct' → +0,5 °C = L-EMS-043 werkt, n=2), knop uit.
- **Stilstand: geen.** 'Nog niet bepaald' 11 wachten (ongewijzigd t.o.v. 11:42; Accugezondheid = L-EMS-040, niet melden).
- Hypotheses: H-EMS-2 (PV te hoog bij zon; vandaag ≈ −17 % op dag-ahead), H-EMS-14 (live correctie; avond/nacht toetst), H-EMS-11 (piek-/nachtladen; vandaag middagblok, dagafsluiting).

laatste ronde: 28-10 15:43, gemeten t/m 28-10 15:45

## 28-10 19:43 · tussenronde
- **v5.142.1 actief** (herstart 19:18). Andere sessie bracht vanmiddag **v5.142.0** (instelbare minimale verkoopwinst, standaard 10 ct; sturing, op verzoek van Ruud) en **v5.142.1** (balanscheck met laad-/ontlaadrendement: sensor-gezondheid nu 100). Fout 0 / storing 0. Geen release.
- **Harde regel: 0× onder de reserve** 15:45-19:45 (geen verkoopkwartieren op 28-10). Export 15-16 u 0,245 kWh = zon bij volle accu; 17-18 u 0,068 kWh verspreid rond de herstart van 17:58 (≤ 0,026/kwartier, regeloverschot).
- **PV dag (H-EMS-2): 7,96 kWh** tegen Solcast 8,87 (**−10,3 %**) en dag-ahead EMS 9,56 (**−16,7 %**) → weer te hoog bij zon; telt mee in de dagafsluiting.
- **Besparing tot nu +€ 0,04** (rauw −1,39 + SoC-correctie 1,43). Avondpiek tot 54 ct, niet verkocht: reserve 10,37 (gekapt op capaciteit, lange horizon 8,9 kWh) > beschikbaar 7,60. Laadplan vannacht 23:45-04:30 in stukjes, 57 → 98 %.
- **Digital twin MAE 1,486** (↑ van 1,394). Nieuw patroon: voorspellingen van 11:15-13:15 voor 17:15-19:15 te laag (8,32/5,92/3,48 tegen 9,56/8,76/8,06): de twin ontlaadt 's avonds op `manual`-kwartieren uit de tijdlijn die de sturing door de reserve niet uitvoert. Openstaand 23:15-01:15 voorspeld 10,37 = blok op vol vermogen (L-EMS-044, toetst vannacht opnieuw). Aanvulling bij L-EMS-044 genoteerd.
- Reserve-sprongen 17:19-19:33: 20× alleen de behoefte, vooral `live_correctie` die per minuut tussen 0 en 1,5 kWh springt (verhouding 1,0 ↔ 1,95); reserve blijft 10,37 (boven capaciteit) → nu zonder effect. Meenemen in H-EMS-14.
- Airco besluit "niets" (21,8 °C), knop uit. **Stilstand: geen** (11 wachten, ongewijzigd).
- Hypotheses: H-EMS-2 (PV te hoog bij zon; vandaag −10 % Solcast / −17 % dag-ahead), H-EMS-14 (live correctie; schommelt per minuut, nacht toetst), H-EMS-11 (piek-/nachtladen; dagafsluiting).

laatste ronde: 28-10 19:43, gemeten t/m 28-10 19:45

## 28-10 23:40 · tussenronde
- **v5.142.2 actief** (andere sessie 21:42, herstart 21:45: kwartierplan spaart ook tussen twee laadblokken). Fout 0 / storing 0. Externe DNS-storing ~23:25 (Zonneplan onbeschikbaar → laatste waarden gebruikt, afgevangen). Geen release.
- **Harde regel: 0× onder de reserve** 19:45-23:45 (geen verkoopkwartieren; export per uur ≤ 0,024 kWh = regeloverschot).
- Avond: SoC 77 → 67 % tot 21:21 (huis uit de accu). Vanaf 21:30 **sparen_in_blok** (blok 21:45-06:15, netladen vanaf 23:45): import 21-23 u 0,355/0,345 kWh bij 41,5 ct terwijl de accu 6,57 kWh had - bewust: terugladen kost 52,6 ct (40,4 ct / rendement + slijtage) → ~€ 0,08 voordeel. Geen schending, geen bug.
- **Besparing tot nu +€ 0,19** (rauw −0,80 + SoC-correctie 0,98). MC in blok 0 %.
- **L-EMS-041:** 22:00-stand van 28-10 vastgelegd met `basis: in_blok` (kans 0 %) = eerste avond met een lopend blok → telt na het dagrecord van 29-10 in `nachten_in_blok`; toets in de dagafsluiting.
- **Digital twin MAE 1,813** (↑ van 1,486). Avondfout 20:15/21:15/22:15 **5,85/5,86/4,84 kWh** (voorspeld 1,52/0,82/1,73 tegen 7,37/6,68/6,57): tweede avond op rij dezelfde vorm (27-10 19:15-21:15 6,20/5,99/5,25) → aanvulling L-EMS-044 bevestigd (n=2 avonden). 23:15 voorspeld 10,37 tegen 6,57 (blok op vol vermogen; de sturing spaart tot 23:45). 6 open voorspellingen 00:15-05:15 alle 10,37 → toets vannacht.
- Airco besluit "niets", knop uit. **Stilstand: geen** (11 wachten, ongewijzigd; `pv_hourly_forecast_bias`/`battery_protection` unknown = nacht/niet actief, normaal).
- Hypotheses: H-EMS-2 (PV te hoog bij zon; dag 28-10 −10 % Solcast / −17 % dag-ahead), H-EMS-14 (live correctie; vannacht in blok, geen toets), H-EMS-11 (piek-/nachtladen; dagafsluiting).

laatste ronde: 28-10 23:40, gemeten t/m 28-10 23:45

## 29-10 03:40 · dagafsluiting 28-10
- **v5.142.2 actief**, geen purge/repack in de log. Fout 0 / storing 0; externe DNS-storingen 23:25-01:00 (Zonneplan onbeschikbaar → laatste waarden, afgevangen). **Release v5.143.0** (L-EMS-044, zie onder).
- Dag 28-10: PV **7,96 kWh** (day-ahead 9,56 → **−16,7 %**; gecorrigeerd L-EMS-025 ~8,78 → −9,3 %), import 8,38, export 0,66, accu 9,77 in / 5,67 uit, huis **11,58** (verwacht 10,31 → +12 %, 6,4 graaddagen). Besparing **−€ 0,01** (accu-opbrengst 0,73 = voorraadcorrectie: accu 's avonds vol vastgehouden). **Harde regel: 0× onder de reserve** (geen verkoopkwartieren). Geen tekortnacht (27→28, laagste SoC 29 %); nacht 28→29 loopt in het blok (SoC 91 % om 03:40).
- **H-EMS-11 (n=2 op de nieuwe meetlat):** realisatie **46,4 %** (€ 0,90 van € 1,94; 27-10 52,6 %), zelfde vorm: optimum laadt 's nachts 3,8 kWh uit het net (−2,00) en zet die in ochtend- (+2,70) en avondpiek (+3,57, 6,94 kWh vastgehouden) in. Avondpiek 54 ct tegen terugladen ~52 ct: onder de minimale verkoopwinst van 10 ct (v5.142.0, keuze Ruud) → dagarchief telt € 0,60 als `gemist_door_regel`. Netladen 's nachts minder: afgewezen 28-10 → geen voorstel.
- **H-EMS-2:** 7 d MAE/bias 11,5/−8,0 %, 14 d 16,4/−14,7, 30 d 13,2/−11,5; per bewolking ≤ 50 % −13,1 (n=10), 50-90 % −14,6 (n=7), > 90 % −8,5 (n=13).
- **L-EMS-025 toets afgerond (7 d):** gecorrigeerd MAE **9,8 %** (bias +0,1) tegen ruw 11,5 % (bias −8,0) → **geverifieerd**. **L-EMS-028:** 'sturing' 0 op 27 en 28-10, 0 sinds v5.128 → **geverifieerd**. **L-EMS-043:** 3 momentopnames met juiste ct-bedragen, +0,5 °C bij 'nu 43 / straks 56 ct' → **geverifieerd** (aandeel per dag niet meetbaar: attributen niet in de recorder).
- MC Brier **0,414** (n=5); 22:00-stand 28-10 `in_blok` (L-EMS-041) telt na het dagrecord van 29-10.
- **Gebouwd v5.143.0 (L-EMS-044):** de digital twin volgt waar het kwartierplan reikt de geplande accustap per kwartier (geen vol vermogen meer in elk blokkwartier, geen ontladen waar de sturing vasthoudt); per voorspelling `plan_aandeel`, nieuw attribuut `kwartierplan_gevolgd` (fout per bron). Twin-MAE vóór de bouw **1,962** (nacht 00:15-03:15 voorspeld 10,37 tegen 6,9-8,9). Suite 6359 groen (+9 tests). Workflow groen, HACS ververst; wacht op installatie.
- Stilstand: **geen** (11 wachten, ongewijzigd; sluipverbruik 28/30, NILM 39/53). Airco: aanzet geleerd 19,0 °C (was 19,5), knop uit.
- Hypotheses: H-EMS-2 (PV te hoog bij zon), H-EMS-14 (live correctie; nachten in blok toetsen niet), H-EMS-11 (piek-/nachtladen; deels door de 10 ct-regel verklaard).

laatste ronde: 29-10 03:40, gemeten t/m 29-10 03:55

## 29-10 07:41 · tussenronde
- **v5.143.1 actief** (andere sessie 06:37: zonuitstel rekent met wat de accu tijdens het wachten levert; herstart 06:40) → **v5.143.0 (L-EMS-044) is geïnstalleerd**. Fout 0 / storing 0. Externe DNS-storing ~07:35 (Zonneplan onbeschikbaar → laatste waarden, afgevangen). Geen release.
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg; regeloverschot 29-10 0,053 kWh).
- **Nacht 28→29:** geen tekort. Blok: accu 6,57 (23:15) → 10,25 kWh (05:15); 07:41 SoC 94 %, beschikbaar 9,68, reserve 7,44 (+25 %). Ochtendpiek 56 ct: accu dekt het huis (`solar_capture_deferred`), blok 09:30. MC tot blok 0 %.
- **Besparing tot nu −€ 0,32** (rauw −1,52 + SoC-correctie 1,20: 2,76 kWh meer in de accu dan bij dagbegin).
- **Digital twin:** nachtvoorspellingen (oude methode) 03:15-07:15 fout 1,50/0,92/0,12/0,29/0,25; MAE 1,939 (n=60, alle `voor_bouw`). Eerste voorspelling met `plan_aandeel` 1 om 07:14 → afrekenen 13:15; groepen `kwartierplan`/`tijdlijn` nog 0. Toets L-EMS-044 vanaf 13:15.
- **L-EMS-041:** `nachten_in_blok` nog leeg; het dagrecord van 29-10 volgt om 09:00 → toets 11:40.
- Airco besluit "verwarmen" (17,8 °C < aanzet 19,0), knop uit. **Stilstand: geen** (11 wachten, ongewijzigd).
- Hypotheses: H-EMS-2 (PV te hoog bij zon; vandaag 48 % bewolking), H-EMS-14 (live correctie; nacht in blok, geen toets), H-EMS-11 (piek-/nachtladen; ochtendpiek vandaag uit de accu, dagafsluiting).

laatste ronde: 29-10 07:41, gemeten t/m 29-10 07:45

## 29-10 11:40 · tussenronde
- **v5.143.1 actief**, fout 0 / storing 0. Externe DNS-storing ~11:33 (afgevangen). Geen release.
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg; regeloverschot 29-10 0,065 kWh). Accu 93 %, laadt zonne-overschot (blok 09:30 loopt, reserve "geen blok").
- **Besparing tot nu −€ 0,32** (rauw −1,48 + SoC-correctie 1,16: 2,65 kWh meer in de accu dan bij dagbegin).
- **Weerbron geweerd (eigen leren):** 10:14 `weather.openweathermap` uit het ensemble (48,5 % van 200 waarnemingen klopte met de panelen; forecast_thuis 89 %). Ensemble-bewolking 26,6 % → **71,9 %** (10:56); de ochtend was bewolkt terwijl het ensemble 23-41 % gaf. Solcast vandaag 8,87 (28-10 21:00) → 7,51 (06:27) → **4,58** (11:17); PV tot 11:41 ~0,8 kWh → H-EMS-2 weer zon te hoog verwacht; dagafsluiting rekent af.
- **Digital twin:** MAE 1,889 (n=60, alle `voor_bouw`); 6 open, 5 met `plan_aandeel` 1,0 (eerste afrekening 13:15). Toets L-EMS-044 15:40.
- **L-EMS-041 (correctie planning):** het dagrecord van nacht 28→29 wordt pas bij de dagwissel van 29-10 geschreven (`_update_shortfall_detection`), niet om 09:00 → `nachten_in_blok` toetsen bij de dagafsluiting van 30-10.
- MC tot blok **0,4 %** (horizon tot 30-10 09:00, volgend blok nog niet bepaald). Airco besluit "niets", knop uit.
- Stilstand: **geen**; 12 wachten (+1 = weerbron OWM, nieuw vandaag).
- Hypotheses: H-EMS-2 (PV te hoog; vandaag bewolkt en sterk overschat), H-EMS-14 (live correctie), H-EMS-11 (piek-/nachtladen; dagafsluiting).

laatste ronde: 29-10 11:40, gemeten t/m 29-10 11:45

## 29-10 15:45 · tussenronde
- **v5.146.1 actief** (andere sessies vandaag 5.144.0-5.146.1: weergave/kasprijs, sturing ongewijzigd). HA-herstarts ~14:45 en ~15:10; geen EMS-fouten. Geen release.
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg; regeloverschot 29-10 0,065 kWh). Besparing tot nu **−€ 0,23** (rauw −1,36 + SoC-correctie 1,13).
- **L-EMS-044 eerste afrekening:** groep `kwartierplan` n=3 MAE **0,51 kWh** (13:15/14:15/15:15: 0,69/0,53/0,32) tegen 1,96 vóór de bouw. Alle drie overdag met zon en volle accu; de echte toets zijn de avondvensters 16:15-21:15 (voorspeld 8,12 → 5,68 kWh).
- **PV (H-EMS-2):** 3,59 kWh t/m 15:43; Solcast vandaag nu 3,63 (gisteravond 8,87). EMS-verwachting voor vandaag 6,95 → ca. −48 %. Dagafsluiting rekent af.
- **MC tot blok 12,9 %** (horizon tot 30-10 10:15, later dan 09:00): nodig 9,07 kWh, deterministisch tekort 8,94 (p90 10,12) bij ~9,9 kWh in de accu. Toets 30-10: tekortnacht ja/nee.
- **Weerbron:** Ruud haalde OWM uit de configuratie (`openweathermap_weather_entity` None; diagnose "weer 1/1"). Toch staat "Weerbron weather.openweathermap" (79 %, bevroren) nog in *Nog niet bepaald* en in `betrouwbaarheid_per_bron`/`_vergelijking` → **L-EMS-045** (rapportagefout, bouwen bij dagafsluiting). Gevonden: overeenstemming wordt elke tick (60 s) geteld, dus 200 waarnemingen ≈ 3,3 u daglicht en weren na 50 min; OWM ging van 48,5 % (10:14) naar 79 % → **L-EMS-046** (voorstel).
- Stilstand: **geen echte**; 12 wachten (waarvan 1 = OWM-restant, L-EMS-045). Airco besluit "verwarmen", knop uit.
- Hypotheses: H-EMS-2 (PV te hoog; vandaag sterk), H-EMS-14 (live correctie), H-EMS-11 (piek-/nachtladen; dagafsluiting).

laatste ronde: 29-10 15:45, gemeten t/m 29-10 15:45

## 29-10 19:40 · tussenronde
- **v5.147.0 actief** (andere sessie 15:51: witgoed uit de live verbruikscorrectie, kasprijs als schatting). Geen EMS-fouten; alleen Solcast-onbeschikbaar-waarschuwingen (niet melden). Geen release.
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg; regeloverschot 29-10 0,15 kWh). Besparing tot nu **+€ 0,38** (rauw 0,01 + SoC-correctie 0,37).
- **L-EMS-044 avondtoets:** groep `kwartierplan` n=7 MAE **0,95 kWh** (vóór de bouw 2,11). Avond 16:15-19:15 fout 1,33/1,54/1,23/0,97 tegen 28-10 dezelfde uren 1,24/2,83/4,59 → sterk beter, maar 3 van 4 nog > 1 kWh en **alle vier werkelijk > voorspeld (+1,27 gem.)**: de twin ontlaadt nog meer dan de sturing doet (sturing hield vast: "niet genoeg beschikbaar voor de reserve"). Status blijft gebouwd; 3-dagentoets loopt.
- **MC tot blok 0,0 %** (15:45 12,9 %): nodig tot blok 4,56 kWh (was 9,07) bij 7,72 beschikbaar; verbruik 17-20 u 0,36-0,69 kW. Daling past bij v5.147.0 (witgoed uit de live correctie); toets 30-10: tekortnacht ja/nee.
- **PV 29-10 compleet 3,68 kWh:** Solcast slot +1 %, dag-ahead 8,87 (−58 %), EMS 6,95 (−47 %) → H-EMS-2; dagafsluiting rekent af.
- Stilstand: **geen echte**; 12 wachten, OWM-regel staat er nog (L-EMS-045, bouwen bij dagafsluiting).
- Hypotheses: H-EMS-2 (PV te hoog; vandaag sterk), H-EMS-14 (live correctie; nu ook twin-avondbias en de lagere behoefte na v5.147.0), H-EMS-11 (piek-/nachtladen; dagafsluiting).

laatste ronde: 29-10 19:40, gemeten t/m 29-10 19:45

## 29-10 23:40 · tussenronde
- **v5.147.0 actief** (HACS: geen nieuwere; geen commits sinds 15:51). HA-herstart 19:49. Geen EMS-fouten; alleen Solcast/SolarEdge-onbeschikbaar-waarschuwingen (niet melden). Geen release.
- **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg; regeloverschot 29-10 0,234 kWh). Besparing tot nu **+€ 0,47** (rauw 1,06 + SoC-correctie −0,60).
- **L-EMS-044 avond compleet:** `kwartierplan` n=11 MAE **0,92** (vóór bouw 2,25). 16:15-23:15 alle 8 werkelijk > voorspeld, gem. **+1,07 kWh**; 4 van 8 < 1 kWh. Oorzaak: de planvolging toont dat de accu structureel minder levert dan het kwartierplan plant (energie_verschil 25..29-10 −0,86/−2,65/−0,79/−1,50/−2,69 kWh; 21:30 gepland 1.285 W, gemeten 471 W, oorzaak 'verbruik') → geplande avondbehoefte te hoog, niet de twin. Hoort bij H-EMS-14; dagafsluiting: avondverbruik plan tegen werkelijk per uur.
- **MC tot blok 0,0 %**; volgend blok pas 30-10 10:45 (geen nachtblok), nodig tot blok 2,24 kWh bij 5,64 beschikbaar. 22:00-stand 29-10 vastgelegd (`tot_blok`, 0 %) → telt na de dagwissel. Toets 30-10: tekortnacht ja/nee.
- Airco besluit "niets" (iedereen slaapt), knop uit. **Stilstand: geen echte**; 12 wachten (OWM-restant, L-EMS-045 dagafsluiting).
- Hypotheses: H-EMS-2 (PV te hoog; 29-10 −47 %), H-EMS-14 (live correctie + plan rekent 's avonds te veel verbruik: 5 dagen op rij minder ontladen dan gepland), H-EMS-11 (piek-/nachtladen; dagafsluiting).

laatste ronde: 29-10 23:40, gemeten t/m 29-10 23:45
