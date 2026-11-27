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

## 13-10 t/m 20-10 · samenvatting (inhaalronde 21-10 19:40; ingekort na 14 dagen)
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

## 21-10 · samenvatting dag (dagafsluiting 22-10 03:40; tussenronden weggelaten, ingekort na 14 dagen)
- Actief **v5.115.0**; v5.115.1 (L-EMS-027) staat klaar, niet geïnstalleerd → geen release (niet stapelen). 0 EMS-fouten; Solcast-limiet (10/10) en Zonneplan-sensoren even onbeschikbaar rond 00:02 (extern, bronbuffer vangt het op).
- Dag 21-10: PV 5,03 kWh (day-ahead 7,82 → −35,7 %), import 2,14, export 0,58, accu 3,33 in / 6,77 uit, huis 10,03 kWh. Planvolging 68,1 %. Geen tekortnacht (→21-10). **Harde regel: 0× onder de reserve** (`verkoopkwartieren` leeg, regeloverschot 0,25 kWh).
- **H-EMS-2 sterker:** 15 dagen op rij te hoog; 7 d MAE/bias 21,3/−21,3 %, 14 d 19,3/−19,3 %, 30 d 12,1/−10,2 % (was 17,4/17,3/11,3). `learned_bias_percent` nog null → L-EMS-025 (open) blijft het voorstel.
- **H-EMS-11 (5 van 8 dagen):** 21-10 ochtendpiek 2,70 kWh vastgehouden (+€ 1,17), nacht 1,38 kWh te veel ontladen (−€ 0,48). Realisatie 7 d (15..21-10) 84 % (€ 7,15 van € 8,50; was 91 % over 14..20-10). Nacht 21→22 doet het L-EMS-026-patroon zelf (lage stand): 00:00-03:45 sparen op 21 % (0,61 kWh import bij ~24 ct), laden 03:45-05:30 tot 42 %, ochtendpiek uit de accu → uitslag nabeschouwing 22-10.
- **H-EMS-12:** avond 21-10 22:00 kans 100 % bij 1,84 kWh; accu staat op 21 % (boven min-SoC 15 %), import met niet-lege accu = geen tekortnacht volgens de definitie. Uitslag 09:00 → toets 11:40.
- Nieuw gezien: om 00:00:00 springt de lange horizon 5,39 → 7,12 kWh en 33 s later terug naar 5,17 (reserve 9,74 → 10,37 → 9,78) = dagwissel-artefact. Kort, maar telt als echte sprong; volgende middernacht nogmaals toetsen vóór een voorstel.
- Meetfout L-EMS-024 3e dag (zon_verwacht 0 op 19/20/21-10). 21-10 heeft geen kosten in het dagarchief (bewust: < 90 % kwartieren met prijs bij de prijsbronstoring). Bouw wacht tot v5.115.1 geïnstalleerd is.
- Hypotheses: H-EMS-2 (PV te hoog), H-EMS-11 (nacht vs ochtendpiek), H-EMS-12 (MC-definitie). Geen release.

## 22-10 · samenvatting dag (dagafsluiting 23-10 03:40; tussenronden weggelaten, ingekort na 14 dagen)
- Actief **v5.119.0** (geïnstalleerd). 0 EMS-fouten; WARNINGs extern: Zendure offline 21:42/22:27, Zonneplan-sensoren en prijzen even onbeschikbaar rond 20:10/00:00 (bronbuffer vangt het op).
- Dag 22-10: PV 4,21 kWh (day-ahead 4,58 → −8,1 %), import 11,62 (laadblok 8,43), export 0,30, accu 9,89 in / 4,88 uit, huis 10,51 (verbruiksverwachting dagarchief 7,98 → 21 % te laag). Planvolging 60,0 % (sturing 9, alle vóór v5.117.0). **Harde regel: 0× onder de reserve** (regeloverschot 0,14 kWh). Geen tekortnacht.
- **H-EMS-2:** 16 dagen op rij te hoog; 7 d MAE/bias 20,5/−20,5 %, 14 d 19,4/−19,4, 30 d 12,1/−10,7. L-EMS-025 dag 1: correctie −8,1 % was raak (n=1). Vandaag ruw 3,94 → gecorrigeerd ~3,63 kWh.
- **Nabeschouwing 7 d (16..22-10): € 6,54 van € 7,55 = 86,6 %.** 22-10 leverde € 0,64 tegen € 0,18 "haalbaar": het optimum kent geen netladen, de netarbitrage (€ 0,94) valt erbuiten → realisatie > 100 % op laaddagen is een definitiegrens. **Nieuw zichtbaar:** avondpiek 6 van 7 dagen "te veel ontladen" (2,1-3,6 kWh/dag, samen −€ 1,92); hoort bij H-EMS-11 (ochtendpiek vastgehouden): het optimum schuift energie van de avond naar de ochtend erna.
- **L-EMS-024 effect:** `zon_verwacht_kwh` 22-10 = 5,28 (niet meer 0), maar 15 % boven day-ahead 4,58 en Solcast 4,47: `_ochtendverwachting` kiest het kwartier tot 09:00 met de MEESTE zon → neigt omhoog (n=1). Accu-opbrengst 0,49 incl. voorraad 0,90 ✓. Eerdere meetlogdagen (20-10 −1,02) niet herrekend (alleen nieuwe dagen). Toets nog 2 dagen vóór een voorstel.
- **H-EMS-13 (plan = beslissing):** sinds v5.117.0 0 nieuwe "afwijking sturing" in ~48 kwartieren; nacht 22→23 had geen dip-lading gepland → nachttoets niet mogelijk. L-EMS-028 blijft gebouwd, 7-daagse toets loopt.
- **H-EMS-14 (nieuw) bevestigd in code:** de 17 sprongen "alleen behoefte" (20:11-23:00) wisselen telkens 1,47-1,51 kWh = `CONSUMPTION_CORRECTION_MAX_EXTRA_KWH` (1,5): de live verbruikscorrectie gaat aan/uit (mediaan live > uurprofiel). Na 00:00 (blok 23-10 23:00, niet meer afgekapt) veranderde zo ook de reserve: 10,37→9,85, 9,81→10,21, 9,64→9,26. Nu geen effect (beschikbaar 3,8 ≪ reserve 8,9). **Gebouwd v5.120.0** (meetbaarheid, L-EMS-031): `live_correctie_extra_kwh`/`-verhouding` in uitsplitsing en sprongen. Bekend fenomeen (v5.14.2, compressorbeurten); meten hoe vaak het een niet-afgekapte reserve of verkoopgrens raakt vóór een voorstel (hysterese = sturing → Ruud).
- MC 22:00 Brier 0,286 (n=7; 2× kans 100 % zonder tekortnacht). Avond 22-10: 100 % tot het blok over 25 u → valt onder L-EMS-029 "andere horizon"; afrekening na 09:00.

## 23-10 · samenvatting dag (dagafsluiting 24-10 03:40; tussenronden weggelaten, ingekort na 14 dagen)
- Actief **v5.124.1**; **release v5.125.0** (03:55, L-EMS-032 + L-EMS-033, workflow groen, HACS ververst; wacht op installatie). 0 EMS-fouten.
- Dag 23-10: PV 4,30 kWh (ruw day-ahead 3,94 → **+9,0 %**, gecorrigeerd 3,63 → +18,5 %), import 3,26 (balanceerlading 1,73), export 0,37, accu 5,14 in / 4,03 uit, huis **6,08** (verwacht 8,57 → **−29 %**; planvolging oorzaak verbruik 34 kw.). **Harde regel: 0× onder de reserve** (regeloverschot 0,19). Geen tekortnacht.
- **H-EMS-2:** eerste dag in 17 boven de verwachting; 7 d MAE/bias 21,5/−18,9 %, 14 d 16,6/−15,4, 30 d 12,4/−10,5. `eenzijdige_correctie` blijft −8,1 % (13/14 aan één kant). L-EMS-025: dag 1 raak, dag 2 +18,5 % ernaast (n=2).
- **L-EMS-028:** eerste hele dag "sturing" 0 (96 kw.) → effect houdt; 7-daagse toets loopt tot 29-10.
- **Nabeschouwing 7 d (17..23-10): € 5,39 van € 6,58 = 81,9 %** (was 86,6). Patroon blijft: avondpiek 6/7 dagen te veel ontladen (−€ 1,92), ochtendpiek op 3 dagen 2,3-3,2 kWh vastgehouden (+€ 2,83; 23-10 3,20 kWh na het sparen van L-EMS-026). Ochtendimport 23-10 was maar 0,08 kWh: de vastgehouden energie ging niet naar het huis maar bleef in de accu. Het optimum verkoopt in de ochtendpiek; sturing → H-EMS-11 blijft, geen voorstel bij n=1 na L-EMS-026.
- **H-EMS-14:** 17 sprongen "alleen behoefte" door de live correctie (verhouding tot 4,98), reserve afgekapt → geen sturingseffect; v5.125.0 bewaart ze voortaan over een herstart.
- MC 22:00 Brier 0,333 (n=6; 2× 100 % zonder tekortnacht); nacht →23 telt als "andere horizon". Digital twin MAE 1,20 kWh (n=60): de balanceerlading van 23:00 (L-EMS-034) en de spaarstand staan niet in de twin → L-EMS-030 laadtoets niet zuiver.
- Hypotheses: H-EMS-2 (PV-bias), H-EMS-11 (avond/ochtendpiek), H-EMS-14 (live correctie). L-EMS-034 blijft open.

## 24-10 · samenvatting dag (dagafsluiting 25-10 03:40; tussenronden weggelaten, ingekort na 14 dagen)
- Actief **v5.126.0**; **release v5.126.1** (03:50, L-EMS-035 + L-EMS-036; suite 6140 groen, workflow groen, HACS ververst; wacht op installatie). 0 EMS-fouten; extern: DNS-storing ~00:45 (Nabu Casa, Bitvavo, feeds), Zonneplan 500 rond 00:01.
- Dag 24-10: PV 4,66 kWh (tracker day-ahead 4,89 → **−4,6 %**; gecorrigeerd 4,49 → +3,8 %; Solcast-ochtend 6,30 → −26 %), import 8,69 (laadblok 12:15-16:30), export 0,28, accu 9,55 in / 5,12 uit, huis 8,65 (verwacht 9,04 → −4 %). Planvolging 60,4 % (sturing 0, accu 15). **Harde regel: 0× onder de reserve** (`kwartieren_onder_verkoopreserve` 0, verkocht 0). Geen tekortnacht.
- **H-EMS-2 zwakker:** 7 d MAE/bias 16,4/−13,8 %, 14 d 16,5/−15,2, 30 d 12,1/−10,2 (7 d was 21,5/−18,9). L-EMS-025 na 3 dagen: gecorrigeerd 0 / +18,5 / +3,8 % (MAE 7,4) tegen ruw −8,1 / +9,0 / −4,6 (MAE 7,2) → nog geen winst zichtbaar; toets loopt tot 7 dagen.
- **Nabeschouwing 7 d (18..24-10): € 4,96 van € 6,46 = 76,8 %** (was 81,9). 24-10 € 0,47 van € 0,57; avondpiek voor het eerst positief (+€ 0,29, 3,13 kWh vastgehouden na de balanceerlading), nacht −€ 0,19. 7 d: avondpiek −€ 1,24, ochtendpiek +€ 2,94, nacht +€ 0,63.
- **L-EMS-036 nagemeten (DST-nacht):** prijs `unknown` 02:45-03:00 CEST én 02:45-03:00 CET; 02:00-02:45 CET kreeg de prijzen van het zomertijduur; planvolging mist alle 8 kwartieren 02:00-02:45 (2×; dag 25-10 11 kw. t/m 03:45). Sturing smart, geen schade (12,8-13,1 ct). Opgelost in v5.126.1; volgende echte toets okt 2027.
- **H-EMS-14:** reservesprongen 24-10: 20 (9 alleen behoefte, 3 na herstart). 00:00:00 weer het dagwissel-artefact: lange horizon 6,48 → 9,55 → 6,49 in 26 s (reserve 9,08 → 10,37 → 9,18); 2e keer (22-10 +1,73). Geen sturingseffect (beschikbaar ~6,9 < reserve); nog een middernacht met effect zien vóór een voorstel.
- MC 22:00 Brier 0,500 (n=6; 3× 100 % zonder tekortnacht: →20, →22, →24). Avond 24-10 `kans_pct` 0 tot het blok, incl. lange horizon 100 %. Digital twin 1,51 kWh (was 1,20).
- Hypotheses: H-EMS-2 (PV te hoog; kleiner), H-EMS-11 (avond/ochtendpiek), H-EMS-14 (reservesprongen + middernacht). Release v5.126.1.

## 25-10 · samenvatting dag (dagafsluiting 26-10 03:40; tussenronden weggelaten, ingekort na 14 dagen)
- Actief **v5.127.3**; **release v5.127.4** (03:55, uitlegtekst; suite 6172 groen, workflow groen, HACS ververst; wacht op installatie). 0 EMS-fouten. Dag 25-10 = 25 uur (wintertijd).
- Dag 25-10 (HA-statistiek): PV **5,50 kWh** (day-ahead tracker 7,43 → **−26,1 %**; gecorrigeerd L-EMS-025 6,83 → −19,6 %; bewolking 27 %), import 12,48 (laadblok 12:15-14:53), export 5,29, accu 6,81 in / 9,44 uit, huis **15,3** (dagarchief 14,57; verwacht 8,61 → **+69 %**; witgoed 3,50 kWh: wasmachine 2,33, vaatwasser 1,17; rest 09-13 u 1,3-2,3 kWh/u onverklaard). Planvolging **54,4 %** (90 kw.; accu 28, sturing 7). **Harde regel: 0× onder de reserve** (5,03 kWh verkocht, kleinste marge 0,57, `kwartieren_onder_verkoopreserve` 0). Geen tekortnacht.
- **H-EMS-2 (PV te hoog) scherper:** 7 d MAE/bias 14,5/−11,9 %, 14 d 17,1/−15,8, 30 d 12,6/−10,7 (25/30 negatief). Nieuw per bewolking (30 d): **≤ 50 % −13,1 % (n=9), 50-90 % −13,8 (n=8), > 90 % −7,1 (n=13)** → de overschatting zit vooral op (half)heldere dagen, niet op donkere. L-EMS-025 na 4 dagen: MAE gecorrigeerd 10,5 % tegen ruw 12,0 % (eerste kleine winst).
- **Nabeschouwing 7 d (19..25-10): € 5,87 van € 6,64 = 88,4 %** (was 76,8). 25-10 € 1,40 tegen optimum € 1,23 (avondverkoop 7,68 kWh accu tegen 6,2 optimaal). 7 d: ochtendpiek +€ 2,94, avondpiek −€ 1,42, nacht −€ 1,73.
- **L-EMS-038 uitgezocht (code):** in het lopende blok geeft `_bereken_dynamische_reserve_kwh` None (blok begonnen) → `_get_soc_scaled_discharge_power` "onbekend = niet verkopen" (v5.26.6): de sturing verkoopt in het lopende blok nooit geforceerd. Het plan rekent daar met de bodem (`_planning_reserve_kwh`, v5.28.5 "net als de sturing" - klopt niet) en plant verkoop → "afwijking sturing". Fix in het plan raakt via `_netladen_volgt_in_blok` (sparen in het blok) en Rem 4 (`last_plan_shortfall`) de sturing → **voorstel (open)**, niet gebouwd. Zelf gebouwd: de misleidende uitleg ("alle 2,30 kWh nodig voor de rest van de nacht") → v5.127.4.
- **H-EMS-14:** 25-10 18 echte sprongen (00:00-02:00 lange horizon), 27 `alleen_behoefte`, 3 na herstart; **26-10 00:00 geen middernachtsprong** (na 22-10 en 25-10). MC 22:00 Brier 0,500 (n=6, ongewijzigd). Digital twin MAE **2,36 kWh** (was 1,51; dag met +69 % verbruik).
- v5.127.2-toets (geen netlading-start ≥ 95 %): blok loopt nog (03:55 SoC 79 %, plan 03:00-05:00) → ronde 07:40.
- Hypotheses: H-EMS-2 (PV te hoog, vooral heldere dagen), H-EMS-11 (avond/ochtendpiek), H-EMS-14 (reservesprongen). Release v5.127.4.

## 26-10 · samenvatting dag (dagafsluiting 27-10 03:40; tussenronden weggelaten, ingekort na 14 dagen)
- Actief **v5.135.1**; v5.136.0 gedownload (HACS), wacht op een herstart → **geen EMS-release** (niet stapelen; niets acuut). Fout 0 / storing 0. Geen purge/repack in de log; DNS-storing ~02:12 (extern).
- Dag 26-10: PV **5,40 kWh** (day-ahead 5,24 → **+3,2 %** bij 99,6 % bewolking; gecorrigeerd L-EMS-025 4,81 → +12,3 %), import 11,62 (nachtblok + 12:30-13:00), export 2,80, accu 12,54 in / 9,78 uit, huis **11,5** (dagarchief 10,7; verwacht 8,76 → +22..31 %). Besparing € 1,26. **Harde regel: 0× onder de reserve** (4 verkoopkwartieren 07:15-08:00, 2,10 kWh, kleinste marge 5,99). Geen tekortnacht (nacht 25→26).
- **Planvolging 26-10 43,6 %** (laagste in 14 d; mediaan verschil 249 W tegen 57-152 W): verbruik 24, accu 22, sturing 2. 11 HA-herstarts en nieuwe functies (batterijlader, airco op zonoverschot) op één dag; 7 d 58,6 %.
- **H-EMS-2:** 7 d MAE/bias 13,8/−10,3 %, 14 d 16,8/−15,1, 30 d 12,5/−10,8; per bewolking ≤ 50 % −13,1 (n=9), 50-90 % −13,8 (n=8), > 90 % −7,3 (n=13). **L-EMS-025 dag 5: gecorrigeerd MAE 10,8 tegen ruw 10,2 → correctie nu iets slechter** (26-10 +12,3 tegen +3,2). Afronden 29-10.
- **Nieuw (meetlat, L-EMS-042 open):** nabeschouwing 7 d realisatie **116,6 %** (€ 6,74 van € 5,78): 'best mogelijk' laadt bewust niet uit het net (v4.5), de sturing wel (26-10 netarbitrage € 1,81). Met netladen benaderd 73,2 %. De avondpiek-/ochtendpiekcijfers van H-EMS-11 komen uit die meetlat → H-EMS-11 eerst op een eerlijke meetlat.
- **Nieuw (meetbaarheid, L-EMS-041 gepland):** MC-kalibratie mist de nacht 25→26: om 22:00 liep het blok al (21:30-06:00), `_leg_mc_22u_vast` wordt dan overgeslagen (`start > now`). Brier 0,600 (n=5). 22:00-kans avond 26-10 26,7 % → uitslag vanochtend.
- Nacht 26→27 03:45: beschikbaar 2,30 kWh (SoC 30 %), blok 10:45, MC tot blok 2,1 %. Digital twin MAE 2,02 → **1,83 kWh**. Reservesprongen 2 echt / 38 `alleen_behoefte` / 8 `na_herstart`.
- Stilstand: alleen *Accugezondheid over de tijd* (L-EMS-040, open; deel a gepland na v5.136.0). Nieuw in *Nog niet bepaald* (< 7 d, lopen op): verbruik per dagtype, regressiewoud, scenarioplan.

## 27-10 · samenvatting dag (dagafsluiting 28-10 03:40; tussenronden weggelaten, ingekort na 14 dagen)
- **v5.140.0 actief** (herstart 21:01), geen purge/repack in de log. Fout 0 / storing 0. **Release v5.141.0** (L-EMS-043 + L-EMS-041, zie onder).
- Dag 27-10: PV **5,19 kWh** bij 4,7 % bewolking (day-ahead 5,95 → **−12,9 %**; gecorrigeerd L-EMS-025 5,46 → −5,0 %), import 11,42 (laadblok 14:15-19:15), export 1,39, accu 10,93 in / 8,03 uit, huis **12,3** (verwacht 9,39 → +31 %, 4,3 graaddagen). Besparing € 0,99. **Harde regel: 0× onder de reserve** (0,99 kWh 18:30-18:45, kleinste marge 1,05). Geen tekortnacht (26→27, laagste SoC 20 %).
- **L-EMS-042 eerste dag op de nieuwe meetlat:** realisatie **52,6 %** (€ 1,21 van € 2,30; ≤ 100 % ✓), gemist reserve 0,73 / voorspelling 0,35. Per dagdeel: optimum laadt 's nachts 6,7 kWh uit het net (−1,94) en zet die in de ochtend- (+2,10) en avondpiek (+1,96) in; de sturing laadde pas 14:15. → **H-EMS-11 herstart** op deze meetlat (n=1; oude dagen rollen er tot 03-11 uit).
- **H-EMS-2:** 7 d MAE/bias 14,2/−10,7 %, 14 d 15,8/−14,1, 30 d 12,7/−10,9; per bewolking ≤ 50 % −13,1 (n=10), 50-90 % −14,6 (n=7), > 90 % −7,3 (n=13) → te hoog vooral bij zon. L-EMS-025 dag 6: gecorrigeerd MAE **9,9** tegen ruw 10,7 → weer iets beter; afronden 29-10.
- **H-EMS-15 bevestigd in code:** twin-MAE 1,75 kWh; vensters met een laadblok **2,63** (n=30) tegen 0,87 (n=30). `_run_digital_twin_simulation` laadt in `smart` binnen het blok van het voorspelmoment elk kwartier op vol vermogen, los van het kwartierplan (26-10 00:00 voorspeld 10,3 tegen 2,8 - laden liep tot 05:00) en mist een blok dat later verschuift (27-10 16:15: 0,5 tegen 10,1). → **L-EMS-044** (gepland, adviserende simulatie).
- **H-EMS-14:** nacht 26→27 geen tekort; nacht 27→28 om 04:05 beschikbaar 3,34 tegen nodig tot blok 1,19 (marge 2,15), MC 0 %. 21 sprongen (23 `alleen_behoefte`). Uitslag nacht 27→28 om 07:40.
- MC Brier **0,414** (n=5; 27-10 26,7 % zonder tekort). Kans 27-10 22:00 0,3 %.
- **Gebouwd v5.141.0:** L-EMS-043 (airco-buffer deelt de prijsreeks door `PRICE_SCALE_FACTOR`; geen 'straks 390089400 ct' meer, 'duur kwartier' werkt weer) en L-EMS-041 (22:00-stand ook als het blok al loopt, apart als `nachten_in_blok`). Suite 6331 groen (+6 tests).

## 28-10 · samenvatting dag (dagafsluiting 29-10 03:40; tussenronden weggelaten, ingekort na 14 dagen)
- **v5.142.2 actief**, geen purge/repack in de log. Fout 0 / storing 0; externe DNS-storingen 23:25-01:00 (Zonneplan onbeschikbaar → laatste waarden, afgevangen). **Release v5.143.0** (L-EMS-044, zie onder).
- Dag 28-10: PV **7,96 kWh** (day-ahead 9,56 → **−16,7 %**; gecorrigeerd L-EMS-025 ~8,78 → −9,3 %), import 8,38, export 0,66, accu 9,77 in / 5,67 uit, huis **11,58** (verwacht 10,31 → +12 %, 6,4 graaddagen). Besparing **−€ 0,01** (accu-opbrengst 0,73 = voorraadcorrectie: accu 's avonds vol vastgehouden). **Harde regel: 0× onder de reserve** (geen verkoopkwartieren). Geen tekortnacht (27→28, laagste SoC 29 %); nacht 28→29 loopt in het blok (SoC 91 % om 03:40).
- **H-EMS-11 (n=2 op de nieuwe meetlat):** realisatie **46,4 %** (€ 0,90 van € 1,94; 27-10 52,6 %), zelfde vorm: optimum laadt 's nachts 3,8 kWh uit het net (−2,00) en zet die in ochtend- (+2,70) en avondpiek (+3,57, 6,94 kWh vastgehouden) in. Avondpiek 54 ct tegen terugladen ~52 ct: onder de minimale verkoopwinst van 10 ct (v5.142.0, keuze Ruud) → dagarchief telt € 0,60 als `gemist_door_regel`. Netladen 's nachts minder: afgewezen 28-10 → geen voorstel.
- **H-EMS-2:** 7 d MAE/bias 11,5/−8,0 %, 14 d 16,4/−14,7, 30 d 13,2/−11,5; per bewolking ≤ 50 % −13,1 (n=10), 50-90 % −14,6 (n=7), > 90 % −8,5 (n=13).
- **L-EMS-025 toets afgerond (7 d):** gecorrigeerd MAE **9,8 %** (bias +0,1) tegen ruw 11,5 % (bias −8,0) → **geverifieerd**. **L-EMS-028:** 'sturing' 0 op 27 en 28-10, 0 sinds v5.128 → **geverifieerd**. **L-EMS-043:** 3 momentopnames met juiste ct-bedragen, +0,5 °C bij 'nu 43 / straks 56 ct' → **geverifieerd** (aandeel per dag niet meetbaar: attributen niet in de recorder).
- MC Brier **0,414** (n=5); 22:00-stand 28-10 `in_blok` (L-EMS-041) telt na het dagrecord van 29-10.
- **Gebouwd v5.143.0 (L-EMS-044):** de digital twin volgt waar het kwartierplan reikt de geplande accustap per kwartier (geen vol vermogen meer in elk blokkwartier, geen ontladen waar de sturing vasthoudt); per voorspelling `plan_aandeel`, nieuw attribuut `kwartierplan_gevolgd` (fout per bron). Twin-MAE vóór de bouw **1,962** (nacht 00:15-03:15 voorspeld 10,37 tegen 6,9-8,9). Suite 6359 groen (+9 tests). Workflow groen, HACS ververst; wacht op installatie.
- Stilstand: **geen** (11 wachten, ongewijzigd; sluipverbruik 28/30, NILM 39/53). Airco: aanzet geleerd 19,0 °C (was 19,5), knop uit.

## 29-10 · samenvatting dag (dagafsluiting 30-10 03:40; tussenronden weggelaten, ingekort na 14 dagen)
- **v5.147.0 actief**, geen purge/repack, geen EMS-fouten (alleen onbeschikbaar-waarschuwingen Zonneplan/SolarEdge, niet melden). **Release v5.148.0** (zie onder).
- Dag 29-10: PV **3,68 kWh** (SolarEdge; day-ahead 6,95 → **−47 %**, Solcast slot +1 %), import 6,20, export 0,86, accu 5,59 in / 5,50 uit, huis 8,47 (verwacht 9,2 → −8 %). Besparing **€ 0,87** (opbrengst incl. voorraad 0,19). **Harde regel: 0× onder de reserve.** Geen tekortnacht; nacht 29→30 loopt (03:44 beschikbaar 4,95, MC 0 %, blok 10:45).
- **H-EMS-11:** realisatie 29-10 **80,4 %** (€ 3,53 / 4,39); 3 d 65,4 %. Avondpiek 3e dag op rij vastgehouden (6,29/6,94/5,53 kWh, +1,96/+3,57/+2,93 €); `gemist_door_regel` 29-10 **€ 1,29** (min. verkoopwinst 10 ct, keuze Ruud v5.142.0; 3 d 0,46/0,60/1,29). Alleen vastgelegd, geen voorstel (regel net gekozen).
- **H-EMS-2:** 7 d MAE/bias 17,1/−13,6 %, 14 d 18,8/−17,0, 30 d 14,7/−13,1; ≤ 50 % bewolking −17,9 (n=10). 29-10 sterk: day-ahead zat ernaast, de panelen niet (Solcast achteraf +1 %).
- **Gevonden:** 00:00 melding `solar_underperforming` "élke dag lager, geen goede dag ertussen → vervuiling/uitgevallen streng" bij reeks −26,1/**+3,2**/−12,9/−16,7/−47,0 (geleerde bias None → 0). Onterecht → gebouwd. En dagarchief telt kwartieren rond herstarts niet: zon 3,23 tegen SolarEdge 3,68 (26-10 −0,23) → **L-EMS-047** (meetfout, gepland).
- **L-EMS-041 geverifieerd:** 22:00-stand 29-10 in `nachten_in_blok` (0 %, geen tekort), niet in de Brier; 6/7 dagrecords (26-10 = gat van vóór de fix). Brier **0,268** (n=4).
- **L-EMS-044 dag 1/3:** groep `kwartierplan` n=15 MAE **0,76** (vóór 2,23); restfout avond = H-EMS-14.
- **Gebouwd v5.148.0:** (1) zon-zelfcontrole: installatie-oordeel alleen zonder goede dag, anders 'wisselend' zonder melding; (2) **L-EMS-045** weggehaalde weerbron uit betrouwbaarheid/vergelijking/wachten. Suite 6395 groen (+6), workflow groen, HACS ververst.

## 30-10 · samenvatting dag (dagafsluiting 31-10 03:40; tussenronden weggelaten, ingekort na 14 dagen)
- **v5.150.0 actief**, geen purge/repack, geen EMS-fouten (alleen Zonneplan/Solcast-onbeschikbaar, afgevangen; niet melden). **Release v5.151.0** (L-EMS-047/048/049, zie onder).
- Dag 30-10: PV **5,31 kWh** (tracker day-ahead 5,86 → **−9,4 %**; dagarchief-ochtend 6,89 → −23 %; Solcast 7,34 → −28 %), import 1,17, export 0,57, accu 3,40 in / 4,03 uit, huis **6,54** (verwacht 8,59 → −24 %). **Harde regel: 0× onder de reserve** (0 kWh verkocht). Geen tekortnacht 29→30; nacht 30→31 loopt (03:42 beschikbaar 4,26, MC tot blok 0 %, accu spaart voor de ochtendpiek).
- **H-EMS-2:** 7 d MAE/bias 17,1/−16,2 %, 14 d 19,3/−17,6, 30 d 15,0/−13,3 (26/30 negatief); ≤ 50 % bewolking −17,2 (n=11). Blijft; correctie is Ruuds keuze (L-EMS-025 afgewezen).
- **H-EMS-14 bijgesteld:** op dagniveau is de verbruiksverwachting juist te **laag**: 24..30-10 werkelijk − verwacht +1,25 kWh/dag (5/7 hoger; alleen 29/30-10 lager, niemand thuis). Het te hoge plan zit in het avond-/nachtdeel van het kwartierplan, niet in het dagtotaal → toets: verbruik per dagdeel werkelijk tegen kwartierplan (meetbaarheid, volgende dagafsluiting).
- **Nabeschouwing 24..30-10: 85,5 %** (€ 11,34 / 13,27); 30-10 89 %. Avondpiek 7 d +€ 9,41 en ochtendpiek +€ 8,42 vastgehouden (H-EMS-11; deels de 10 ct-regel).
- MC 22:00 Brier **0,214** (n=5; 30-10 kans 0 %, geen tekort). Twin groep `kwartierplan` n=39 MAE **1,02** (< 1,2; dag 3 sluit 06:40).
- **Gebouwd v5.151.0:** (1) **L-EMS-047** dagarchief vult onvolledige uren aan uit de uurstatistiek (`aangevulde_kwartieren`, `uren_uit_statistiek`); (2) **L-EMS-048** proefstandregels tonen de reden/uitkomst in *wat_ontbreekt*; (3) **L-EMS-049** zonstandtoets rekent met het meetmoment van de sensor (≤ 60 min). Suite **6426 groen** (+12 tests `test_v5151_leerronde.py`), workflow, HACS ververst. Sturing ongewijzigd.
- Stilstand: **geen echte** (13 wachten, 0 doen). Airco besluit "niets", knop uit.

## 31-10 · samenvatting dag (dagafsluiting 01-11 03:40; tussenronden weggelaten, ingekort na 14 dagen)
- **Draait v5.154.1** (herstarts 31-10 16:30/21:32); v5.155.0 staat op GitHub, nog niet in HA → niet stapelen, **geen release**. Geen EMS-fouten na 23:45 (alleen Solcast/Zonneplan-onbeschikbaar, afgevangen); geen purge/repack.
- Dag 31-10: PV **4,94 kWh** (day-ahead 3,82 → **+29,3 %**; dagarchief-ochtend 4,20 → +17,6 %), import 6,43, export 0,38, accu 1,68 in / 3,86 uit, huis **13,17** (verwacht 9,17 → **+3,92 kWh**). **Harde regel: 0× onder de reserve** (0 kWh verkocht). Geen tekortnacht 30→31.
- **L-EMS-047 geverifieerd:** dagarchief zon 4,94 tegen SolarEdge 4,944 op een herstartdag (2 kwartieren aangevuld, 1 uur uit statistiek); verbruik 13,09 tegen balans 13,17 (−0,6 %).
- **H-EMS-2:** 7 d MAE/bias 20,7/−11,4 %, 14 d 18,5/−12,6, 30 d 15,7/−12,2 (25/30 negatief). Per bewolking (30 d): ≤ 50 % **−17,2** (n=11), 50-90 % −16,1 (n=6), > 90 % **−6,1** (n=13) → te hoog vooral bij zon; bij volle bewolking bijna zuiver (31-10 +29 % bij 100 %).
- **H-EMS-14 (dagtotaal te laag):** 7 d +1,88 kWh/dag, 5/7 hoger; weekend 25/31-10 +5,96/+3,92, werkdagen gem. +0,66 (n=5). Dagtypeprofiel bestaat sinds v5.135.0 (≥ 4 waarnemingen per uur) → toets of het weekendverschil blijft na nog 2 weekenden (n te klein).
- **Nabeschouwing 25..31-10: 82,0 %** (€ 11,45 / 13,97); 31-10 46 % (gemist € 0,64 door de verbruiksvoorspelling). Avondpiek vastgehouden 31-10 2,39 kWh (25..30-10 4,5-6,9) → H-EMS-11 neemt af.
- MC 22:00 Brier **0,014** (n=5; 24-10 met kans 100 % zonder tekort viel uit het venster). Hoge kansen nu niet getoetst: avond 31-10 (100 %, blok 13:00) wordt 'andere horizon'. Twin `kwartierplan` n=60 MAE **0,851** (venster vol).
- **Meetbaarheid → L-EMS-050 (open):** temperatuurregressie (voedt `temperatuur_extra_kwh` in de reserve) kreeg in 10 d 1 nieuw paar (7 totaal); ontlaadvensters zijn in de stookperiode vaak < 2 u. Voorstel: daarnaast één paar per nacht uit het vaste venster 22-07.

## 01-11 · samenvatting dag (dagafsluiting 02-11 03:40; tussenronden weggelaten, ingekort na 14 dagen)
- **Draait v5.156.0**; geen purge/repack, geen EMS-fouten na 23:43 (alleen Zonneplan/forecast onbeschikbaar om 00:00, afgevangen). **Gebouwd v5.156.1** (L-EMS-051, zie onder).
- Dag 01-11 (zo): PV **1,83 kWh** (day-ahead 2,68 → **−31,8 %** bij 100 % bewolking), import 8,86, export 0,54, accu 0,92 in / 1,04 uit, huis **10,27** (verwacht 9,64 → **+0,6**). **Harde regel: 0× onder de reserve.** Geen tekortnacht 31→01. Besluit klapt niet meer sinds v5.156.0 (0 wissels na 21:20; daarvoor 4×).
- **H-EMS-2 (PV te hoog):** 7 d MAE/bias 21,5/−12,2 %, 14 d 18,0/−12,0, 30 d 16,6/−13,0 (25/30 negatief). Per bewolking: ≤ 50 % −18,3, 50-90 % −16,1, > 90 % **−8,0** (was −6,1): 01-11 ook bij volle bewolking 32 % te hoog → niet alleen een zonnedag-effect.
- **H-EMS-14 (dagtotaal te laag):** zondag 01-11 **+0,55** (zaterdag +3,92, 25-10 +5,96). Weekend n=3 gem. +3,48, werkdagen +0,66 → verschil blijft, maar 01-11 past er niet in; nog 1 weekend.
- **Nabeschouwing 7 d: 73,9 %** (9,41 / 12,74). 01-11: leverde −0,64, best 0,00, "gemist door voorspelling" 0,64 terwijl het dagarchief −0,04 zag. Nagerekend in de code: de dag begon (22 %) onder de meetlatbodem (15 % van de capaciteit); `beste_planning` begint stil op de bodem en de werkelijkheid wordt tegen de bodem gewaardeerd → niets doen gaf al (bodem − begin) × dagprijs "gemist". Rekenfout → **gebouwd v5.156.1** (`bodem = min(bodem, begin)`, 6 tests, suite 6484 groen, workflow groen, HACS ververst). Rest van 01-11 is echt: voorraad 1,5 kWh DC (22 → 9 %) leverde ~0,12 € AC op (sluimer/rendement).
- **Tekortnacht 01→02 loopt** (eerste in ~8 nachten): 1,51 kWh net met lege accu om 03:45, MC 22:00 **100 %** (soort economisch). Laadbesluit "loont niet" klopt: goedkoopste kwartier 38,7 ct / 0,83 = 46,6 ct > nacht 40-41 ct. Eerste kalibratiepunt met hoge kans; MC Brier n=4 **0,018**.
- Twin `kwartierplan` MAE **0,723**. Stilstand: **geen echte** (11 wachten, 0 doen). Airco besluit "niets", knop uit → rekent.
- Hypotheses: H-EMS-2 (PV te hoog, nu ook bij volle bewolking), H-EMS-14 (weekend te laag; 1 weekend), H-EMS-11 (piek vastgehouden; 01-11 0 kWh → neemt af).

## 02-11 · samenvatting dag (dagafsluiting 03-11 03:40; tussenronden weggelaten, ingekort na 14 dagen)
- **Draait v5.167.0**, v5.168.0 wacht op herstart: geen release. Geen purge/repack; log alleen Solcast-limiet (herstarts, niet melden) en sensoren rond de herstart. **L-EMS-056 klaargezet** op `wip/l-ems-056` (5 tests, suite 6694 groen); dagafsluiting na installatie van v5.168.0.
- Dag 02-11 (ma): PV **1,99 kWh** (day-ahead 4,03 → **−50,6 %**, slechtste dag van 40), import 10,84, export 0,14, accu 1,93 in / 0,91 uit, huis **11,68** (verwacht 10,04 → **+1,64**). **Harde regel: 0× onder de reserve**, regeloverschot 0,034.
- **Nieuw inzicht, meetfout:** `deviation_context.bewolking` heet "van die dag", maar is de stand om **23:59:50**. 02-11: label 25,8 %, terwijl de bewolking tot 15:15 op 100 % stond (instraling 36-136 W/m²). Alle uitsplitsingen van H-EMS-2 per bewolking (≤ 50 % −21,2, > 90 % −8,3) rusten daarop, en `zonbias_percent` kiest er een correctie mee. → **L-EMS-058 (open)**, raakt via de correctie de reserve.
- **H-EMS-2 (PV te hoog):** 7 d MAE/bias **28,2/−19,9 %** (6/7 negatief), 14 d 21,0/−15,1, 30 d 18,2/−14,6 (25/30). Bias per bewolking niet meer gebruiken tot L-EMS-058 besloten is. Solcast vandaag 7,69 (p10 1,87, p90 10,86); breed, dus vandaag telt als toets.
- **Tekortnacht 02→03 loopt:** net 22-03 uur 1,18 kWh, MC 22:00 100 %, plan volgt. Uitslag 09:00 voor L-EMS-054 en H-EMS-15.
- **Nabeschouwing 7 d 62,8 %** (7,58 / 12,07) door de dure dagen 27-29-10 tegen dagen zonder spreiding; 02-11 0,09 / 0,03. Vergelijking met 73,9 % gaat over een ander venster, geen trend. Planvolging 7 d **69,7 %** (02-11 84,5); stijgt mee met de lege accu.
- Verbruik 7 d +0,93 kWh/dag (MAE 1,73); maandag +1,64 past niet in "alleen weekend" (H-EMS-14 blijft geparkeerd). MC Brier n=4 **0,018**. Twin **0,366**.
- Stilstand: **geen echte** (12 wachten, 0 doen). Airco 'niets', knop uit → rekent. Dagen sinds vol: 5.

## 03-11 · samenvatting dag (dagafsluiting 04-11 03:40; tussenronden weggelaten, ingekort na 14 dagen)
- **Gebouwd v5.176.3** (L-EMS-060): bewolking per kwartier overleeft een herstart, en een daglabel vraagt 50 % dekking van de verwachte zon. Suite 6937 groen, workflow groen, HACS ververst. Geen purge/repack gezien. Log: Solcast/Zonneplan rond herstart, 0 fouten.
- Dag 03-11 (di): PV **4,96 kWh** (day-ahead 7,69 → **−35,5 %**), import 7,15, export 0,39, accu 3,41 in / 2,90 uit, huis **11,20** (verwacht 10,05 → **+1,15**). **Harde regel: 0× onder de reserve**, verkocht 0; `geschonden` om 0,228 kWh regeloverschot (rond de zon, vóór v5.175.1).
- **H-EMS-2 (PV te hoog):** 7 d MAE/bias **31,5/−23,1 %** (6/7), 14 d 22,9/−16,9, 30 d 19,3/−15,8 (26/30). Plan-zon 7 d 22,9/−17,3; plantoetsing zelf: 28 van 30 dagen minder zon dan voorspeld (mediaan −13 %).
- **Backtest correctievenster (n=26):** zonder correctie MAE 21,1 / bias −17,9; huidig (14 d) 17,5 / −8,9; mediaan 14 d 17,8; 7 d 17,9. **Een ander venster levert niets op**, de rest is dagruis. Geen voorstel; de bias van −9 blijft staan.
- **L-EMS-059 werkt:** `tekortnacht_tot_nu_kwh` **1,232** om 03:45, boven de 0,5 van een tekortdag; vorige nacht telde maar 0,165 van ~2,5 kWh net.
- **Brier 0,018 → 0,25 is geen verslechtering:** nacht 03-11 staat op kans 100 %, tekort false, omdat die vóór L-EMS-059 te laag telde. Valt vanzelf uit het venster.
- **MC 0 % sinds 03:14 terwijl det. 0,49:** klopt, kans telt pas boven beschikbaar + 0,5 kWh (0,67). Geen fout. Label 03-11 is leeg door de herstarts (L-EMS-060).
- Nabeschouwing 7 d **65,4 %** (6,45 / 9,86). Planvolging 7 d **69,7 %** (03-11 64,9). Verbruik 7 d **+0,81** (MAE 1,62). Twin 0,396.

## 04-11 · samenvatting dag (4 tussenronden 07:40-19:40; ingekort na 14 dagen)
- Dag vol releases uit de chat (v5.176.3 → v5.184.4) en ~12 herstarts; 0 EMS-fouten. Gebouwd door de ronde: v5.181.2 (L-EMS-064 leermodus na herstart, 86 min geen sturing 11:22-12:48) en v5.183.4 (L-EMS-065 huis/zon lopend kwartier; daarna geverifieerd 682 tegen 627 W).
- Harde regel 0× onder de reserve. Nacht 03→04 tekort 1,646 kWh (tekortdag). Zon 6,62 kWh (Solcast −9,0 %). Koken sinds v5.184.1 gevolgd, regeloverschot 0,145 kWh (P1-dips bij aan/uit kookplaat).
- L-EMS-057 geverifieerd (airco 'niets' 's nachts); nieuw L-EMS-063 (ochtend 'verwarmen'), L-EMS-066 (eerste planrij midden in kwartier), L-EMS-067 (laadplan-historie); H-EMS-18: netlaadplan springt na 7/7 herstarts.

## 05-11 · samenvatting dag (dagcontrole 09:15; ingekort na 14 dagen)
- v5.187.0; gemist € 0,32 (0 FOUT); tekortnacht 04→05 2,99 kWh; KNMI 3× ~35 min weg; gebouwd v5.187.1 (L-EMS-067, temperatuurnotitie). PV 7 d bias −15,4 %.

## 07-11 · samenvatting dag (dagcontrole 09:15; ingekort na 14 dagen)
- v5.188.0 (v5.189.0 klaar); gemist € 0,54 (0 FOUT); 3.178× 'state > 255 tekens' en schaduw vast → v5.189.1. PV 06-11 −20,9 %; H-EMS-19 (middernacht-zon).

## 08-11 · samenvatting dag (dagcontrole 09:15; ingekort na 14 dagen)
- v5.192.2; gemist € 0,13 (0 FOUT, 0 PECH); schaduw eerste volle dag; indelingsfout tekortnachten → L-EMS-075. PV 40 d bias −12,9 %.

## 09-11 07:40 · dagcontrole (08-11 06:45 t/m 09-11 07:30; ronde draait nu om ~06:45)
- Draait **v5.194.3**; v5.195.0 om 07:26 door Ruud geïnstalleerd, herstart nog niet. Herstart 09-11 05:23. 0 fouten sinds de herstart.
- **STORING → v5.195.1:** EMS 08-11 16:02 tot 09-11 05:23 vastgelopen (13,4 u, status 'Mogelijk vastgelopen' vanaf 16:16, uitleg bleef op kalibratie). Oorzaak: `_kalibratie_ronde` → `async_set_kalibratie(False)` → `_handmatig_gezet` → `async_update` wacht op `self._lock` dat de ronde zelf houdt (deadlock). Melding 'Kalibratie afgerond' kwam nooit. Ruud zette 16:28 de Zendure zelf op smart.
- Push vanuit de geplande sessie geweigerd (repo niet in de bronnen); v5.195.1 en dit blok 09-11 ~07:50 vanuit de chat op GitHub gezet.
- **Terugkijken 16:00-07:30 (62 kw):** werkelijk € 1,65, LP € 1,34 → **gemist € 0,32**. **1 FOUT** (vastloper): 16:00-16:30 0,27 kWh net bij 46,8 ct met volle accu (~€ 0,12); rest € 0,20 = smart dekte de nacht (39-45 ct) en om 05:30-06:15 opnieuw 2,5 kWh bij gem. 42 ct; LP hield 3,65 kWh vast voor 46-52 ct en vandaag. Kalibratie 10:38-16:02 (8 kWh bij 38-39 ct): keuze Ruud. 06:30-07:30 import bij 51-55 ct met 3,46 kWh vastgehouden voor 79-88 ct vanavond: goed.
- **Kalibratiedag 08-11 economisch (vraag Ruud):** hele venster 08-11 06:45 - 09-11 07:30 werkelijk € 7,85, LP vrij € 7,46 → € 0,38, waarvan € 0,05 de kalibratie (9,29 kWh geladen bij gem. 38,9 ct; LP-goedkoopst 38,0-38,9; uur vasthouden 15:00-16:00 1,0 kWh net bij ~44 ct) en € 0,32 de vastloper erna. Het LP laadt die dag zelf ook 8,4 kWh bij ~38,5 ct en ontlaadt 3,6 kWh bij gem. 51,5 ct: kalibreren op deze dag kostte vrijwel niets.
- **Nacht 07→08 compleet:** huis 22-09 ≈ 2,40 kWh, net 2,33 kWh, accu leeg sinds 07-11 ~19:00, niets geladen. EMS-reden 'goedkoopst 39,7 ct, tekort betaald 45,1 ct, waard 33,8 ct na rendement en slijtage' → economisch, geen fout (nachtprijzen voor 07:00 niet meer in de prijssensor; reden uit het EMS-record). Ochtend 06:45-10:38 accu 10 %, net ~1,9 kWh bij 39-40 ct: geen fout.
- Harde regel: 0 verkoopbesluiten; vlag 09-11 niet geschonden. Rimpel-export 0,28 kWh in Zendure-smart (EMS stil).
- Laadrendement gemeten bij de kalibratie: 9,30 kWh AC → 7,78 kWh (SoC 10→100 %) = **83,6 %**.
- PV 08-11 1,85 kWh tegen Solcast 00:00 3,38 (**−45 %**). H-EMS-2 blijft.
- Tekortdagen 6/7: nachten naar 4-7 nov staan nog als 'planning, bijladen loonde'; de economietoets van v5.193.0 zette ze niet om (alleen 08-11 is economisch). Niet kunnen toetsen of dat terecht is (records niet uit HA te lezen zonder volledige diagnostics) → **H-EMS-20**.
- Economische schaduw: 3 dagregels, 0 volledig (herstart 07-11, kalibratie + vastloper 08-11) → evaluatie schuift op. Stilstand: 8 wachten, 0 doen.
- Niet gemeten: PV/verbruik per uur, SoC-voorspelling, MC-Brier (nacht nog niet af), NILM.


## 10-11 06:45 · dagcontrole (09-11 07:30 t/m 10-11 06:45; geïnstalleerd v5.203.0)
- Achteraf (LP, 93 kwartieren, symmetrische prijs, rendement 84,1/100, slijtage 2 ct, eind-SoC = werkelijk 99 %): werkelijk € 3,42, optimum € 3,25 → **gemist € 0,17** (prijs−EB € 0,18; slijtage 4,22 ct € 0,17). 0 FOUT, 0 PECH: verschil is spreiding van nachtladen over gelijke prijzen (39,7-42 ct) en 0,3 kWh verkocht om 15:45 (63,4 ct) die om 19:30 (65,9 ct) iets meer waard was (€ 0,01; bewaarmarge 5 ct, bewust tot de schaduw-evaluatie).
- Eerste dag na v5.198.0: 15:45-19:15 3,51 kWh verkocht tegen gem. 79,8 ct, accu 19:45 leeg, huis daarna 3,05 kWh van het net tegen 49,6 ct, 's nachts 8,98 kWh geladen tegen 40,4 ct. Onder de oude huisreserve (7,78 kWh) was er niets verkocht: loslaten leverde ≈ € 1,06 op (3,51 × (79,8 − 49,6)).
- Gevonden + gebouwd: v5.203.1 (in de chat gepusht 10-11): de nacht naar 10-11 zou om 09:00 'capaciteit: vol geweest, daarna niets verkocht' heten (vol 05:45 na het nachtladen wist de avondverkoop), en met de oude regel 'het huis gaat voor: stuurfout'. Replay echt dagverloop: nieuw 'verkocht met winst, 3,5 kWh gem. 78,3 ct, tekort 52,5 ct, ~€ 0,90'. Alleen indeling/meldingen; marge telt planning/capaciteit/winst gelijk. → L-EMS-077.
- PV 09-11 6,39 kWh tegen Solcast 00:00 6,82 (−6,3 %); 40 d MAE 18,7 % (was 17,5), bias −14,2 % (was −12,9) → H-EMS-2 (klein en stabiel) geldt niet meer: bias loopt op, vooral november (sterkste uurcorrectie 16 u × 0,47).
- MC 22:00 (09-11) 100 %, tekort kwam (0,54 kWh 22-09 t/m 06:45): goed. Brier 0,175 over 14 avonden.
- H-EMS-20 afgerond: nachten naar 5-8 nov staan nu economisch (v5.197.1); alleen 4 nov planning (valt 11-11 uit de 7 dagen).
- Economische schaduw: 4 dagregels, 0 volledig (09-11 75/96: vastloper tot 05:15). 10-11 tot nu 27/27. Stilstand: 9 wachten, 0 doen; airco-besluit rekent (dagritme 90 %, knop uit).
- Module 1 (AB3000 01029): Ruud 10-11 "samen in de gaten houden". Nulmeting celverschil 100 % 0,09 V (anderen 0,02/0,01), 0 % 0,04 V (0,01), 20-90 % gelijk, laagste cel gelijk. Temperatuur is de plek (bekend). Drempels in de dagcontrole. → H-EMS-21.
- Niet gemeten: kwartierfout 0-1 u (v5.196/197; geen bewaarde kwartiervoorspellingen in de recorder), SoC-voorspelling, NILM, nacht 22-09 compleet (loopt tot 09:00).

laatste ronde: 10-11 06:45, gemeten t/m 10-11 06:45

## 11-11 06:45 · dagcontrole (10-11 06:45 t/m 11-11 06:45; geïnstalleerd v5.209.0 sinds 10-11 16:53)
- Achteraf (LP, 96 kw, marginaal −11,08 ct, rendement 84,1/100, slijtage 4,22 ct, eind-SoC = werkelijk 100 %): werkelijk € 4,41, optimum € 4,30 → **gemist € 0,11**; zonder accu € 6,09. **0 FOUT.** € 0,06 = knop 'Verkopen uit (vandaag)' 15:36 (Ruud): middagladen 1,06 kWh tegen 55,2 ct (12:30-13:45, gepland voor verkoop op de piek 71-74 ct) werd verliesgevend; € 0,05 PECH: ontladen verspreid over het huis (15:30-19:15) i.p.v. geconcentreerd op 16:30-17:45 (huisverbruik niet te voorspellen).
- Regels c: geen verliesgevende verkoop (ochtend 3,88 kWh tegen 69,2 ct, terug tegen 37-55 ct); 18:30-18:45 import 0,49 kWh tegen 61,8/61,4 ct terwijl de accu 19:15 nog 0,12 kWh tegen 59,3 ct gaf: < € 0,01; geen vastgehouden lading (leeg 19:15).
- Loslaten woning-eerst 10-11: ≈ **+€ 0,76** (3,88 kWh verkocht 69,2 ct; avond na leeg 3,19 kWh tegen 51,1 ct).
- Nachtladen 11-11 9,05 kWh tegen 37,3 ct, zelfde blok als het optimum. Nacht 22-06:45 huis 1,58 kWh (voorlopig); telt als tekortnacht (0,73 kWh), indeling om 09:00.
- Regeloverschot in 'huis' 15:30-16:45 0,045 kWh/kw (2 lekkwartieren, vlag huis_gaat_voor rood; regel is sinds v5.198 uit); na v5.209.0 0,012/kw. Eén middag, effect v5.209 nog niet vast te stellen.
- Storingen: Zendure 1× offline 19:45 (accu leeg, geen gevolg); MariaDB 20:06 2× niet bereikbaar (recorder); Zonneplan-kostensensoren 00:03 onbeschikbaar (cache). Push leerlog: 403, 4e dag.
- PV 10-11 1,79 kWh. Plan-bias 10 d **−7,1 %** (30 d −14,4 %, bron 40 d −15,5 %): buiten ±5 % maar verbetert; 7-dagenwaarde niet beschikbaar in de diagnostics → H-EMS-22 (meten of het plan in 7 d < ±5 % komt).
- Module 1: 100 % 0,08 V (was 0,09), 0 % 0,04 V, laagste cel 3,06 (anderen 3,07/3,08), SoC laag ≥ −1 %. Geen drempel. Nieuw: bucket 90 % mediaan 0,03 V (anderen 0,01; nulmeting 0,01), piek einde laden 0,17 V → volgen.
- Schaduw: 1 volle dag van 14 (C2 −0,25 €). Stilstand: 8 wachten, 0 doen. Suite main 7600 groen.
- Niet gemeten: kwartierfout 0-1 u, SoC-voorspelling, NILM, MC-Brier (nacht loopt tot 09:00), dagmaximum celverschil volledig (history afgekapt op 1000 regels).

laatste ronde: 11-11 06:45, gemeten t/m 11-11 06:45

## 11-11 12:15 · vanuit de chat (v5.210.0 t/m v5.214.0; geen dagcontrole)
- **Gebouwd op 11-11 (alle akkoord Ruud, suite 7654 groen):** v5.210.0 Zendure-integratie zelf herladen na 5 min offline (max 1×/uur), prijsverwachting onthouden per kwartier. v5.211.0 snelle zon-correctie stuurt mee (laatste 5 dagen, 0,8-1,2). v5.212.0 live toets: houden/huis getoetst aan het GEMETEN tekort tegen `waarde_inhoud` (0,5 ct, 120 s, max 1 wissel per kwartier). v5.213.0 een rendementsband telt pas vanaf 8 rondes, anders de buurband. v5.214.0 opbouw en meetlat van het verwachte verbruik; wisselregel B11 rekent met `waarde_inhoud`.
- **Nieuwe meetpunten - vanaf nu elke dagcontrole meenemen en in KPI.csv zetten:**
  - `waardeplan.herplanningen.live_wissel` en `live_wissel_eur` (sensor explanation, attribuut waardeplan): aantal wissels en geschat voordeel per dag. Nulmeting: 11-11 11:03-11:15 hield de accu vast bij 1,3-1,6 kW netafname tegen 57,3 ct (plan rekende 0,9 kW); ~1 ct per kwartier gemist. Let op pendelen: meer dan 1 wissel per kwartier hoort niet voor te komen.
  - `accukosten.rendement_per_band` (sensor learned_battery_efficiency): per band `rondes` en `onzekerheid_procentpunt`. Stand 11-11 11:41: ontladen <500 W 100,9 % (29 rondes, ±2,3), 500-1500 W 106,2 % (16, ±2,8), >1500 W 106,9 % (3, ±2,6; was vóór de herstart 101,8 %). Melden zodra >1500 W 8 rondes heeft en zelf gaat meetellen.
  - `pv_voorspelkwaliteit.plan.snellere_correctie` (sensor zonvoorspelling_ijking): `fout_nu` (zonder) tegen `fout_snel` (met). 11-11: 25 dagen 1,20 → 0,96 kWh/dag; de laatste 9 dagen 0,88 → 0,99 (slechter). Wordt `beter` False over 25 dagen: voorleggen om `PV_SNELLE_CORRECTIE_AAN` uit te zetten.
  - `waardeplan.verbruiksmeetlat`: fout en afwijking (W) van de verbruiksverwachting voor dit kwartier, 1 uur en 3 uur vooruit. Begint na elke herstart opnieuw.
  - `waardeplan.vooruit[].verbruik_opbouw`: profiel / omlaag / live / witgoed / verschuiving / klimaat per kwartier.
  - Dagoverzicht: zin "Zendure-integratie ... zelf herladen (tijden)"; in de HA-log de waarschuwing "herlaadt de Zendure-integratie nu zelf".
- **Open vraag H-EMS-20 (nieuw):** om 11:08 rekende het plan met 901 W (11 u), 396 W (12 u), 1404 W (13 u), 1096 W (14 u) tegen een uurprofiel van 497/370/788/697 W. Geen witgoed gepland of lopend. Welk deel is live correctie (budget 1,5 kWh), dagtype of klimaat-extra? Uit te lezen met `verbruik_opbouw` bij de eerstvolgende onverwachte verbruiker.
- Nagerekend met de echte planner: het plan van 11:07 (verkopen 12:30 tegen 57,7 ct, huis op het net 16:00 tegen 59,6 ct) was consistent binnen de banden van dat moment (>1500 W 101,8 %); dat bandcijfer bleek op 3 rondes te rusten.

## 12-11 06:45 · dagcontrole (11-11 06:45 t/m 12-11 06:45; v5.227.0 geïnstalleerd sinds 11-11 20:42)
- Achteraf (LP 96 kw, marginaal −11,08 ct, slijtage 4,22 ct, rendement van de dag zelf 86/91 %, eind 75 %): werkelijk € 3,62, optimum € 3,30 → **gemist € 0,33**; zonder accu € 5,21. **0 FOUT.** € 0,30 = knop 'Verkopen uit (vandaag)', door een gebruiker aangezet 11:08: geen verkoop op de piek 16:15-19:15 (61-68 ct), accu dekte het huis 11:30-21:30. Replay `waardeplan.plan` (repo-code) met de werkelijke data zonder knop verkoopt 16:15-19:15 op 2,4 kW; met het verkoopverbod was de uitvoering vrijwel optimaal (LP € 3,59). € 0,03 pech (11:00-11:15 0,5 kWh net bij 56-57 ct vóór de knop, plan hield vast voor een verkoop).
- Regels c: geen verkoop; geen vastgehouden lading (leeg 21:30); lege accu 21:30-03:00 net 37-47 ct, eerder laden was niet goedkoper.
- Nacht 12-11: 6,54 kWh geladen gem. 35,2 ct (03:00-06:00, zelfde blok als LP), 05:30-06:15 om 06:13 geschrapt, gestopt op 75 %; om 06:45 verkoopt het plan tot ~10:00 tegen 41-45 ct en laadt 10:45 (32,7 ct) en 13:00-15:30 bij (voorlopig).
- Rendement van de dag zelf (HomeWizard via dagverloop): laden 86 %, ontladen 91 % (7,07 kWh AC uit voor 90 % SoC); plan rekent ontladen 99-105 %. Kleine steekproef → H-EMS-23: ontlaadrendement van het plan > 100 % tegen 91 % gemeten op een hele dag.
- Regeloverschot 'huis' 11-11 0,0033 kWh/kw (38 kw; nulmeting 10-11 0,045). Pendel gisteren 104,5 Wh maar alleen 20:42-24:00 (herstarts), geen dagwaarde.
- PV-plan bias 10 d −5,6 % (was −7,1; 30 d −14,8 %), snelle correctie 1,05 → 0,84 kWh/d, beter. Verbruiksmeetlat sinds 20:42: 142/109/88 W (0/1/3 u).
- Module 1: 100 % 0,06 V (0,09 → 0,08 → 0,06), 0 % 0,04 V (anderen 0,01), 90 % 0,01 V, max vandaag 0,03 V, laagste cel 3,10 (gelijk), SoC laag −2 %. Geen drempel; daalt.
- Stilstand 6 wachten, 0 doen. Storingen: alleen cache-waarschuwingen Zonneplan-kosten 00:02 (bekend) en prijzen uit cache na herstart 20:42.
- Niet gemeten: live_wissel 11-11 (teller wist om 00:00), SoC-voorspelling, NILM, MC-Brier (nacht loopt tot 09:00).

- Gebouwd **v5.228.0** (alleen meten): dagverloop-veld `verkoop_pauze` per kwartier en `herplanningen_gisteren` (live wissels van de vorige dag). Suite 7109 groen, workflow groen, Marketplace ververst. Push naar GitHub werkte vandaag weer vanuit de geplande taak.

laatste ronde: 12-11 06:45, gemeten t/m 12-11 06:45

## 12-11 07:35 · vanuit de chat (akkoord Ruud: ontlaadrendement een week meten)
- **H-EMS-23 een week meten, t/m de dagcontrole van 19-11.** Elke dagcontrole: het rendement van de dag zelf uit de HomeWizard-meter van de accu via het dagverloop (laden: opgeslagen kWh / AC in; ontladen: AC uit / afgenomen kWh uit de SoC), naast wat het plan die dag rekende per band (`accukosten.rendement_per_band`, met `rondes` en `onzekerheid_procentpunt`). Zet in KPI.csv: `accu_ontlaadrendement_dag_pct`, `accu_laadrendement_dag_pct`, `accu_ontlaadrendement_plan_pct` (gewogen naar de kWh per band van die dag) en de ontladen kWh als n. Nulmeting 11-11: laden 86 %, ontladen 91 % (7,07 kWh AC uit), plan 99-105 %.
- Geen wijziging aan de sturing in deze week. Op 19-11: gemiddelde over de week (gewogen naar kWh), spreiding per dag, en wat een lager ontlaadrendement in euro's per dag scheelt (naspeling van `waardeplan.plan` met het gemeten cijfer). Ligt het gemeten ontlaadrendement over de week meer dan 3 procentpunt onder wat het plan rekent: voorstel met het eurobedrag aan Ruud. Anders: hypothese sluiten.
- Ook meenemen (ontbrak 12-11): `rondes` per rendementsband (ontladen >1500 W stond 12-11 op 3) en `verbruik_opbouw` bij een onverwachte verbruiker (H-EMS-20).

## 13-11 06:45 · dagcontrole (12-11 06:45 t/m 13-11 06:45; v5.230.0 geïnstalleerd sinds 12-11 09:29)
- Achteraf (LP 96 kw, marginaal −11,08 ct, slijtage 4,22 ct, rendement van de dag 83,5/100 %, start 75 % eind 98 %): werkelijk € 2,46, optimum € 2,36 → **gemist € 0,10, 0 FOUT**. Verschil zit in het middagladen 13:00-15:15 (31-34 ct) voor de avondverkoop 17:15-19:15 (40,8-41,8 ct): bij 83,5 % en 4,22 ct net niet lonend, met de marginale slijtage van het plan wel (model, geen fout). Ochtendverkoop 06:45-10:00 (41-44,5 ct) en nachtladen 01:45-04:45 (~30 ct) gelijk aan het optimum.
- Regels c: verkoop 41-44 ct teruggekocht 30-34 ct (winst); leeg 19:30-22:15 met net 34-40 ct na verkoop op 40,8-41,8 ct (verkoop was meer waard); geen vastgehouden lading. Verkopen optimaal € 0,18 waard; werkelijk € 0,08 beter dan optimum zonder verkopen.
- 13-11 plan (voorlopig): verkoopt 07:30-09:15 (43-49 ct), laadt 11:00-14:30 (32-36 ct), verkoopt 16:30-20:45 (45-53 ct). Volle accu om 06:45 houdt bewust vast voor 07:30.
- H-EMS-23 dag 2: laden 83,5 % (plan 83,3), ontladen 100,8 % op 9,1 kWh >1500 W (plan 101,5). Gat 0,7 pp (11-11: 91 % tegen 99-105). Doorgaan t/m 19-11.
- PV-plan 10 d −4,7 % (binnen ±5; was −5,6), snelle correctie 0,81 kWh/d. PV 12-11 3,76 kWh. Pendel 223 Wh (pas vanaf herstart 09:29); regeloverschot 'huis' 1 kwartier, niet representatief.
- Module 1: 100 % 0,06 V (gelijk), 0 % 0,04 V, laagste cel 3,07 V tegen 3,08/3,09 (12-11 19:15, 2,1 kW, 14 %), SoC laag gelijk. Geen drempel.
- Meldingen zonder grond (→ L-EMS-078/079): 12-11 07:00 push 'accumodule loopt uit de pas' (temperatuur module 1, CUSUM-referentie −1 °C uit de tijd met 00996; sinds de wissel +1..2,5 °C) en 19:11 push 'cel staat te laag' (alle drie modules 3,07-3,10 V onder 2,1 kW bij 14 %).
- Storingen: geen fouten; cache-waarschuwingen Zonneplan-kosten 00:04 (bekend). Stilstand 7 wachten, 0 doen.
- Niet gemeten: MC-Brier (nacht loopt tot 09:00), SoC-voorspelling, NILM, live wissels 12-11. Geen release; suite niet gedraaid (main ongewijzigd sinds v5.230.0, 7121 passed).

## 13-11 notitie uit de chat met Ruud (voor de dagcontrole)
- v5.231.0: luchtreiniger-stand blijft bruikbaar bij een korte onderbreking (was 242 keer in 48 uur onbeschikbaar); controle 13-11 ~14:10 in de chat.
- v5.232.0: nieuw meetpunt `regelkwaliteit` (diagnose, 14 dagen; attributen regelkwaliteit_vandaag/_gisteren op sensor P1 regeldoel). Per dag uren regelend, afname en teruglevering, apart `rustig` en `quooker`. Referentie 10 t/m 13-11: rustig +7 W gemiddeld, quooker +102 W. Graag dagelijks meenemen; melden als `rustig` over een dag met minstens 1 regeluur boven +40 W of onder -40 W gemiddeld komt. Het Quooker-filter uitzetten is 13-11 door Ruud afgewezen (niet voorstellen), net als wijzigingen aan de regeling zelf.
- Afgewezen 13-11: tweede DNS / verbinding meten, MeteoAlarm verwijderen (tablet gebruikt hem), rolluiken als isolatie, boodschappenlijst bij de supermarkt.

laatste ronde: 13-11 06:45, gemeten t/m 13-11 06:45

## 14-11 06:45 · dagcontrole (13-11 06:45 t/m 14-11 06:45; v5.232.0 geïnstalleerd sinds 13-11 12:09)
- Achteraf (LP 96 kw, marginaal −11,08 ct, slijtage 4,22 ct, rendement van de dag 83,8/100 %, start 98 % eind 38 %): werkelijk € 0,62, optimum € 0,57 → **gemist € 0,05, 0 FOUT**; zonder accu € 2,55. Verkoop 07:30-09:15 (43-49 ct), laden 10:45-13:30 (32-35 ct) tot 100 %, verkoop 16:30-20:45 (45-53 ct) tot 10 % = vrijwel het LP-schema; verschil zit in randkwartieren (07:30, 10:45, 17:00, 19:45, 20:45).
- Regels c: verkopen 43-53 ct, terugkoop 32-35 ct (winst); leeg 21:15-04:00 met net 35-44 ct na verkoop op 45,7-46,3 ct (verkoop 1,9 ct/kWh meer waard dan dekken om 21:00); 15:00-15:15 2,4 kW net bij volle accu (38 ct) bewust vastgehouden voor 45-53 ct; geen vastgehouden lading. Loslaten woning-eerst: +€ 0,34.
- Nacht 14-11 (voorlopig): 2,36 kWh geladen 04:00-05:30 gem. 34,8 ct, plan verkoopt 07:30-09:15 (41-44 ct) en laadt 10:30-12:30 (33-34 ct) bij. Met vlakke 4,22 ct slijtage en 83 % ongeveer break-even (−2 tot +0,2 ct/kWh); met de marginale slijtage van het plan positief (model, v5.54). Eindoordeel morgen.
- H-EMS-23 dag 3: laden 82,9 %, ontladen 97,6 % op 12,1 kWh (plan 100,5). Gewogen 3 dagen 97,0 % tegen plan ~100,8 → gat 3,8 pp; doorgaan t/m 19-11.
- Verbruiksmeetlat sinds 13-11 12:09 (75 kw): dit kwartier fout 456 W (+363 te hoog), 1 u 252 (+92), 3 u 207 (+74). Het lopende kwartier zit verder ernaast dan 3 u vooruit (12-11 ook al: 142/109/88). **H-EMS-24 (nieuw):** verwachting van het lopende kwartier blijft na een grote last te hoog (v5.196/v5.197 live correctie?). Uitlezen met `verbruik_opbouw` van het nu-kwartier na de volgende oven/wasmachine; euro-effect nog onbekend (uitvoering volgt P1).
- PV-plan 10 d −1,3 % (binnen ±5; was −4,7), snelle correctie 0,85 kWh/d. PV 13-11 5,96 kWh. Pendel 638,8 Wh over ~12 uur (vanaf herstart 12:09; 12-11 223 Wh vanaf 09:29); regelkwaliteit rustig 0,28 regeluur +8,1 W (te kort voor oordeel); regeloverschot 'huis' 2 kwartieren.
- Module 1: 100 % 0,07 V (0,06 → 0,07; nulmeting 0,09), 0 % 0,04 V, max vandaag 0,03 V, laagste cel 3,06 tegen 3,08/3,09 V (13-11 ~20:48, ~2 kW, ~14 %), SoC laag 9 % tegen 10/12 %. Geen drempel. Push 'cel staat te laag' 13-11 20:48 opnieuw zonder achterblijvende cel (L-EMS-079).
- Storingen: geen fouten; cache-waarschuwingen Zonneplan 00:03 (bekend), prijzen uit cache na herstart 13-11 12:09. Aandachtspunt 'module 1 temperatuur' staat nog (L-EMS-078). Stilstand 7 wachten, 0 doen.
- Suite main 7146 groen (12 overgeslagen). Geen release. Niet gemeten: MC-Brier (nacht loopt tot 09:00), SoC-voorspelling, NILM.

## 14-11 08:30 sessie Ruud: v5.233.0
- L-EMS-078 en L-EMS-079 gebouwd (accutoestand.py): na een modulewissel beginnen de relatieve grootheden van alle modules opnieuw (eerste keer na update ook); push 'cel staat laag' alleen bij achterstand >= 0,05 V. Suite 7156 groen. Geinstalleerd, wacht op herstart door Ruud. Na de herstart is de geschiedenis van de relatieve velden leeg: de drift-toets heeft weer dagen nodig.

laatste ronde: 14-11 06:45, gemeten t/m 14-11 06:45

## 15-11 06:45 · dagcontrole (14-11 06:45 t/m 15-11 06:45; v5.235.0 geïnstalleerd, herstart 14-11 ~19:03)
- Achteraf (LP 96 kw, marginaal −11,08 ct, slijtage 4,22 ct, rendement van de dag 79,6/97,7 %, start 38 % eind 10 %): werkelijk € 2,77, optimum € 2,73 → **gemist € 0,04, 0 FOUT**; zonder accu € 3,52. Middagladen 10:15-14:15 (33-35 ct) tot 94 % en avondverkoop 16:30-19:15 (44-46 ct) = LP-schema; verschil in ochtendverkoop 07:15-08:15 en randkwartieren.
- Eindoordeel nacht 14-11: 2,36 kWh netladen 04:00-05:30 (34,8 ct) verkocht 07:15-09:15 (41-44 ct): met vlakke 4,22 ct en 80-83 % circa −€ 0,05 tot −0,07; met de marginale slijtage van het plan positief (model, v5.54). Geen fout.
- Regels c: avondverkoop 44-46 ct, leeg 20:15 met net 37-40 ct (verkoop meer waard); 14:30-15:15 net 36-40 ct bij 94 % vastgehouden voor 41-46 ct; geen vastgehouden lading. Loslaten woning-eerst: +€ 0,02.
- Nacht 15-11 (voorlopig): niet geladen (28-35 ct), terecht: plan laadt 08:45-13:45 9,3 kWh tegen 24-26 ct, verkoopt 15:30-15:45 en 17:00-17:45 (36-37 ct). Leeg 10 % sinds 20:15.
- H-EMS-23 dag 4: laden 79,6 %, ontladen 97,7 % op 8,95 kWh (plan gewogen 102,0: 500-1500 W 105,2, >1500 W 100,5). 4 dagen ~97,2 tegen ~101,3 → gat ~4 pp; doorgaan t/m 19-11.
- PV-plan 10 d −5,5 % (net buiten ±5; was −1,3) door 14-11 (3,24 kWh, push 'zon minder dan verwacht'); snelle correctie 0,86 kWh/d. Volgen, nog geen structurele afwijking.
- Pendel 243 Wh (pas vanaf herstart 19:03). Regelkwaliteit rustig 0,65 u −14 W (<1 u). Verbruiksmeetlat sinds herstart (rustig) 63/61/49 W; H-EMS-24 wacht op een grote last.
- Module 1: 100 % 0,07 V, 0 % 0,04 V, max vandaag 0,01 V, laagste cel 3,11 tegen 3,11/3,12 V, SoC laag gelijk. Geen drempel; push 'module loopt uit de pas' 14-11 07:01 was vóór v5.233.0 (L-EMS-078), 19:34 hersteld.
- Storingen: geen; cache-waarschuwingen Zonneplan 00:03 en prijzen uit cache na herstart (bekend). Stilstand 7 wachten, 0 doen. Suite main 7168 groen (12 overgeslagen). Geen release.
- Niet gemeten: MC-Brier (nacht loopt tot 09:00), SoC-voorspelling, NILM.

## 16-11 06:45 · dagcontrole (15-11 06:45 t/m 16-11 06:45; v5.235.0 geïnstalleerd, HA-herstart 15-11 ~13:23)
- Achteraf (LP 96 kw, marginaal −11,08 ct, slijtage 4,22 ct, rendement van de dag 86,0/98,9 %, start 10 % eind 98 %): werkelijk € 3,86, optimum € 3,81 → **gemist € 0,05, 0 FOUT**. Verschil alleen randkwartieren (laden 08:45-09:15 26 ct tegen 12:45-13:15 25 ct; nachtladen 01:45/02:45 tegen 04:15-04:45, < 1 ct verschil; verkoop 15:15/16:00 tegen 16:15/16:30).
- Laden 08:45-13:00 8,74 kWh AC (gem. 24,6 ct) tot 99 %, verkoop 15:00-18:45 5,81 kWh uit de accu (2,95 kWh naar het net, gem. 35,7 ct) tot 31 %; 31 % vastgehouden 18:00-23:30 bij 29-34 ct voor de ochtend van 16-11 (37-41 ct): eerder ontladen en 's nachts bijladen (26 ct / 86 % + slijtage) kost meer → goed. Loslaten woning-eerst: +€ 0,05 (optimum zonder verkopen € 3,91).
- Regels c: geen verkoop met verlies (35,7 ct tegen terugkoop 26/0,86 + 4,22 ≈ 34,4 ct), geen import duurder dan later accugebruik, leeg 06:45-08:30 bij 27-29 ct (nacht 15-11 al beoordeeld), geen vastgehouden lading.
- Nacht 16-11 (voorlopig): 23:45 en 01:45-04:45 6,91 kWh geladen bij 26-27 ct tot 98 %; vandaag 37-46 ct → terecht.
- H-EMS-23 dag 5: laden 86,0 % (blok 10→99 % 88,0, nacht 31→98 % 83,8), ontladen 98,9 % op 5,81 kWh (plan per band 100,3-105,1). Gat ontladen ~3 pp, in lijn met dag 1-4; doorgaan t/m 19-11.
- PV-plan 10 d **−7,0 %** (was −5,5 / −1,3), MAE 29,3 %; 14-11 en 15-11 te hoog (ochtendverwachting 5,93/3,36 en 1,69/0,94 kWh). Euro-effect deze dagen ~0 (gemist € 0,04/0,05). Volgen; bij nog 2 dagen buiten ±5 % de oorzaak per uur uitzoeken.
- Verbruik: ochtendverwachting 15-11 9,82 kWh tegen 14,3 kWh na 09:00 (−31 %; 14-11 11,01/14,29). Meetlat sinds herstart (70 kw): dit kwartier 240 W (+101), 1 u 166 (+21), 3 u 161 (+22) → H-EMS-24 voor de 3e keer: lopend kwartier zit verder ernaast dan 1-3 u vooruit.
- Pendel 63,4 Wh (vanaf herstart 13:23); 15-11 0 regeluren en 0 kwartieren stand 'huis' (accu alleen laden/verkopen/houden) → regeloverschot en regelkwaliteit niet te meten; 'regelkwaliteit_gisteren' toont daarom bewust 14-11.
- Module 1: 100 % 0,07 V (3e dag gelijk), 0 % 0,04 V, max vandaag 0,05 V tegen 0,02/0,02 (bij laden tot 98 %), laagste cel 15-11 3,20 tegen 3,19/3,20 V, SoC laag 9-10 tegen 11/10 %. Geen drempel.
- Storingen: geen; cache-waarschuwingen Zonneplan (bekend), prijzen uit cache na herstart. Eenmalig 'system_status took 0.501 s' (15-11 ~22:51). Stilstand 7 wachten, 0 doen. Suite main 7168 groen (12 overgeslagen). Geen release.
- Niet gemeten: MC-Brier (nacht loopt tot 09:00), SoC-voorspelling, NILM.

laatste ronde: 16-11 06:45, gemeten t/m 16-11 06:45

## 17-11 06:45 · dagcontrole (16-11 06:45 t/m 17-11 06:45; v5.236.0 geïnstalleerd, HA-herstart 16-11 ~22:25)
- Achteraf (LP 96 kw, marginaal −11,08 ct, slijtage 4,22 ct, rendement 86/100 %, start 98 % eind 65 %): werkelijk € 2,35, optimum € 2,31 → **gemist € 0,04, 0 FOUT**; zonder accu € 3,28 (zonder voorraadcorrectie). Verschil alleen randkwartieren (verkoop 09:00 41,7 ct en 20:15 41,8 ct; nachtladen 03:00 tegen 05:15).
- 98 % vastgehouden 06:45-16:30 bij net 36-41 ct, verkocht 16:45-20:15 3,19 kWh naar het net (gem. 44,7 ct) tot 12 %: de ontlaadsnelheid (~2,04 kW) bindt, het LP doet hetzelfde → goed. Loslaten woning-eerst: +€ 0,06.
- Regels c: geen verkoop met verlies (44,7 ct tegen terugkoop 33,8 ct/0,87); leeg 20:30-03:00 bij 35-41 ct na verkoop op 41,8-46 ct (verkoop meer waard); geen import duurder dan later accugebruik; geen vastgehouden lading.
- Nacht 17-11 (voorlopig): 03:00-05:15 5,35 kWh geladen bij 33,8 ct tot 66 %; vandaag 35-42,7 ct, geen verkoop gepland (tekort voorzien). Met vlakke slijtage ~break-even, met marginale slijtage positief. Eindoordeel morgen.
- H-EMS-23 dag 6: laden 87,3 %, ontladen ~101 % (SoC-resolutie). In lijn met dag 1-5; doorgaan t/m 19-11.
- PV-plan 10 d **−9,6 %** (−1,3 → −5,5 → −7,0 → −9,6; 4e dag buiten ±5 %), 30 d −12,9 %; ochtendverwachting 7 d −21 % (16-11 2,79 tegen 1,58). plan_review: 24 van 30 dagen minder zon dan voorspeld. Snelle correctie helpt (fout 1,01 → 0,91 kWh/d). Euro-effect deze dagen ~0 (gemist ≤ € 0,05/d). Oorzaak per uur niet uitgezocht: de planvoorspelling per uur wordt niet per dag bewaard (alleen het geleerde uurprofiel, 07-09 en 16-18 u 0,44-0,63).
- Verbruik 16-11 ochtendverwachting 10,89 tegen 11,74 kWh (−7 %; was −31 %).
- Pendel 16-11 197,6 Wh (bewaard over herstart); regelkwaliteit rustig 0,46 u −23,5 W; regeloverschot stand 'huis' 0,011 kWh/kw (5 kw, te weinig).
- Module 1: 100 % 0,07 V (4e dag gelijk), 0 % 0,04 V, max vandaag 0,03 V, laagste cel 3,11 tegen 3,11/3,12 V, SoC laagste stand 11 tegen 12/13 %. Geen drempel.
- Storingen: geen; Zonneplan-sensoren onbeschikbaar na herstart 22:25 tot ~00:00 (cache, bekend), nu weer actueel. Stilstand 6 wachten, 0 doen. Suite 7174 groen (12 overgeslagen). Geen release.
- Niet gemeten: MC-Brier (nacht loopt tot 09:00), SoC-voorspelling, NILM.

laatste ronde: 17-11 06:45, gemeten t/m 17-11 06:45

## 18-11 06:45 · dagcontrole (17-11 06:45 t/m 18-11 06:45; v5.238.0 geïnstalleerd, herstart 17-11 ~12:40)
- Achteraf (LP 96 kw, marginaal −11,08 ct, slijtage 4,22 ct, rendement van de dag 83,5/100 %, start 64 % eind 100 %): werkelijk € 5,13, optimum € 5,08 → **gemist € 0,05, 0 FOUT**; met laadrendement 86 % € 0,12 (modelverschil). Zonder accu € 4,58 (zonder voorraadcorrectie, +3,1 kWh in de accu). Verschil alleen randkwartieren: ontladen 13:00-13:15 (36,1-36,3 ct) tegen 16:15-16:30 (36,5-37,1); nachtladen 00:00-01:45 (23,4-24,8) tegen 05:00-05:15 (23,0-23,1).
- 17-11 zonarm (0,76 kWh): huis op de accu 06:45-11:15 (40-42,7 ct), 48 % vastgehouden 13:30-16:30 (33,9-37,1), huis 16:45-20:15 (36-39,1) tot 11 %; geen verkoop. Regels c: geen verliesverkoop; import 16:30 (37,1) vóór ontladen 19:45 (36,0) ~€ 0,003 (in het gemiste bedrag); leeg 20:30-00:00 bij 27-36 ct, eerder laden was niet goedkoper (min. 33,9 ct + rendement); geen vastgehouden lading. Tekortnacht 1,11 kWh, economisch juist.
- Nacht 18-11: 9,22 kWh geladen 00:00-06:00 gem. 22,5 ct tot 100 % (LP zelfde blok). **Voorlopig:** plan houdt 99 % de hele dag (13,35 kWh import tot 40,1 ct): horizon 69 kw < 96 → lineaire eindwaarde 26,18 ct marginaal (p75 prijsverwachting 19-11 00-12 u; 07-09 u 42,6-44,7 ct). Na de prijzen van ~13:00 opnieuw. Morgen toetsen of vasthouden loonde tegen ontladen op 38-40 ct vanavond.
- H-EMS-23 dag 7: laden 84,4 % (10→100 %, 7,78 / 9,22 kWh), ontladen 100,4 % (64→11 %, 4,58 / 4,56 kWh). In lijn met dag 1-6; eindoordeel 19-11.
- PV-plan 10 d **−13,5 %** (−1,3 → −5,5 → −7,0 → −9,6 → −13,5), 30 d −12,1 %; ochtendopname 08:00 7 d 20,3 / 18,5 = −8,9 %. Per uur: eerste volle dag met uurcijfers is 18-11 (v5.237.0). Euro-effect klein (zonarme dagen, gemist ≤ € 0,05/d).
- Verbruik 17-11: ochtendverwachting 10,87 tegen 14,30 kWh (−24 %).
- Pendel 17-11 247,4 Wh over 8,47 regeluren (~29 Wh/u; rustig −6,9 W, Quooker 0,57 u +531 W); regeloverschot huis 0,010 kWh/kw (37 kw). **Weekoordeel factor 0,5:** regeloverschot 0,003-0,015 tegen nulmeting 0,045 (−65 tot −95 %), nulregeling rustig −7 tot −24 W (niet trager meetbaar); uitdoven na een sprong niet gemeten (geen minuutdata bewaard). Factor helpt: houden; 0,4/0,6 niet te onderbouwen, geen voorstel.
- Module 1: 100 % 0,07 V (5e dag gelijk; anderen 0,01/0,01), 0 % 0,04 V (0,01/0,01), daghoogste 0,17 V bij einde laden 18-11 (anderen 0,04/0,03; gelijk aan 10-11), laagste cel 17-11 3,10 V (3,10/3,11), laagste stand 10 % (00917 10, 02093 11). Geen drempel.
- Storingen: geen; Zonneplan-kostsensoren rond 00:00 kort onbeschikbaar (cache, bekend). Stilstand 5 wachten, 0 doen. Suite 7195 groen (12 overgeslagen). Geen release. LEERLOG 21-10 t/m 03-11 per dag samengevat (dagafsluitingen bewaard, tussenronden weg; volledige tekst in de git-historie).
- Niet gemeten: MC-Brier (nacht loopt tot 09:00), SoC-voorspelling, NILM.

laatste ronde: 18-11 06:45, gemeten t/m 18-11 06:45

## 19-11 06:45 · dagcontrole (18-11 06:45 t/m 19-11 06:45; v5.239.0 geïnstalleerd, herstart 18-11 15:43)
- Achteraf (LP 96 kw, marginaal −11,08 ct, slijtage 4,22 ct, rendement 83,5/100 %, start 100 % eind 99 %): werkelijk € 2,70, optimum € 2,69 → **gemist € 0,02, 0 FOUT, 0 PECH**; zonder accu € 2,71. Alleen verkoop 08:00 (31 ct, 0,32 kWh, met zonherlading netto +0,5 ct) en LP 0,09 kWh ontladen 16:45 (40,1).
- 18-11 accu de hele dag en nacht 99-100 %, huis op het net 28-40 ct, geen nachtladen (33-36 ct). **Toets van gisteren:** vasthouden 18-11 avond (39 ct) voor 19-11 (verkopen 07:30-09:15 en 18:00-19:15 bij 42-44,6 ct) is optimaal: LP 18-11 06:45 t/m 19-11 24:00 met het plan van 19-11 en dezelfde eind-SoC (55 %) € 5,21 tegen werkelijk+plan € 5,20. Avond ontladen + nachtladen kost 30,6 ct marginaal tegen 28,3 opbrengst.
- **Voorlopig 19-11:** plan houdt 55 % (4,75 kWh) over voor 20-11 (verwachting gem. 42, piek 49,6) terwijl het huis 16:00-17:45 importeert bij 41-43 ct; waarde eind-kWh in het LP 28,2 ct marginaal (~39,3 bruto). Loont alleen als 20-11 boven ~40 ct komt: toetsen bij de prijzen van 20-11 (~13:00) en morgen.
- Regels c: geen verliesverkoop, geen import vóór goedkoper kwartier met energie over (binnen 24 u), geen lege accu, geen gemiste verkoopwaarde.
- **H-EMS-23 gesloten:** ontladen 12-18-11 gewogen 99,2 % (46,6 kWh AC; 97,6-101,1), plan ~100,5-102 → gat ~1,5-2 pp (< 3 pp, ~€ 0,04/dag): geen voorstel. Laden 84,0 % (79,6-87,3).
- PV-plan 10 d **−3,9 %** (MAE 0,91 kWh/d), 30 d −11,4 %; snelle correctie 0,98 → 0,89. 18-11 2,01 kWh tegen ochtendplan 1,23 (uren 10-13 te laag, 1 dag uurcijfers). Verbruik 18-11 11,24 tegen 14,11 kWh (−20 %), 3e dag op rij te laag (−7/−24/−20); nacht 1,67 kWh. MC Brier 0,143 (7 nachten).
- **Gebouwd v5.239.1 (L-EMS-080, classificatie):** 'Zonvoorspelling klopt hij nog met de panelen?' gaf 19-11 00:00 'structureel 43 pp lager, élke dag, vervuiling/streng' met reeks −51,5/−53,6/−43,4/−29,3/**+41,0** %. Een dag de andere kant op telt nu als tegenbewijs. Suite 7220 groen, workflow groen, Marketplace ververst.
- Pendel 18-11 76,3 Wh, 0 regeluren (geen stand huis); regeloverschot niet te meten. Module 1: 100 % 0,02 V (bucket nu vol rustmetingen op 100 %; was 0,07 met laadpieken), 0 % 0,04 V (anderen 0,01), daghoogste 0,03, laagste cel 3,19 V (gelijk). Geen drempel.
- Storingen: geen (Zonneplan-kostsensoren rond 00:00 en prijssensor bij herstart: cache, bekend). Stilstand 8 wachten, 0 doen (1 fout geclassificeerd, gebouwd).
- Niet gemeten: regeloverschot en ontlaadrendement 18-11 (geen ontlading), SoC-voorspelling, NILM. Hypotheses: H-EMS-24 (nieuw) verbruiksverwachting koude dagen te laag; eindwaarde-toets na 20-11.

laatste ronde: 19-11 06:45, gemeten t/m 19-11 06:45

## 19-11 11:55 · vanuit de chat (Ruud: "monitor jij alle metingen en update je mij wat te doen, zodat het EMS schoon blijft")
- Nieuw: MEETREGISTER.md op deze branch (zelfde inhoud als claude/ems-meetregister.md in het project). Elke 'alleen meten'-toevoeging heeft daar een regel met besluitdatum en wat er dan gebeurt (voorstel / meting stopt en gaat uit de code / vaste bewaking).
- Dagcontrole: lees het register elke ronde; meld op de kaart en in het eindbericht wat op of over de besluitdatum is, met de uitkomst volgens de regel; werk de regel bij (afgesloten of nieuwe datum). Nieuwe meting in een release = nieuwe regel in het register in dezelfde ronde.
- v5.243.0 (repetitie 2027 met het waardeplan) en v5.244.0 (deed de accu zelf wat het EMS opdroeg) zijn uit de chat uitgebracht, beide alleen meten; zie register nr. 7 en 8. Uitvalproef accu door Ruud achterwege gelaten.
- 19-11 12:10 (Ruud akkoord): P1-factor 0,5 houden; de dagelijkse PENDELMETING STOPT. Voer de alinea 'PENDELEN VAN DE ACCUREGELING' uit de opdracht niet meer uit (geen KPI-regels p1_pendel_wh_dag en ems_regeloverschot_huis_kwh_per_kw, geen 'pendelenergie gisteren' in het eindbericht). Dit besluit gaat voor op de tekst van de opdracht en blijft gelden; neem deze regel mee bij het samenvatten van het leerlog.
- 19-11: v5.245.0 (Powercalc-proef eruit) en v5.246.0 (GACS-eisenspiegel eruit; sensor GACS-zelfbeoordeling blijft voor de cockpit) uit de chat uitgebracht. Ruud: "als iets niet wordt gebruikt kan het eruit" - maar 'niet gebruikt' eerst aantonen met een zoekactie door code, cockpit en tests. Onderzoek naar de oude reserve-regels als terugval loopt (register nr. 13, 26-11).

## 20-11 06:45 · dagcontrole (19-11 06:45 t/m 20-11 06:45; v5.249.0 geïnstalleerd, herstart 19-11 ~14:45)
- Achteraf (LP 96 kw, marginaal −11,08 ct, slijtage 4,22 ct, start 99 % eind 100 %): werkelijk € 3,56, optimum € 3,45 met het gemeten laadrendement van de nacht (78,5 % op SoC) → **gemist € 0,11, 0 FOUT, 1 PECH**; met het planrendement 83,5 % € 0,19 (modelverschil). Zonder accu € 3,48.
- 19-11: verkocht 07:15-08:45 (1,28 kW, 41,6-44,5 ct) en 10:00-10:15; 65 % vastgehouden 12:00-17:00 terwijl wasmachine/vaatwasser 2,5-3,8 kW van het net trokken (37-40 ct); 17:15-19:30 huis + verkoop (2,0 kW, 43-44,6 ct) tot 21 %; nacht 00:00-05:15 8,27 kWh geladen gem. 33,5 ct tot 95 % (06:00 SoC-sprong naar 100). Avondcyclus: opbrengst € 1,16 tegen terugkoop € 1,03 + slijtage € 0,15 = **−€ 0,02 (quitte, PECH)**: met planrendement +1,2 ct/kWh, met het gemeten nachtrendement −0,5 ct/kWh. Verkoopsnelheid ochtend (1,28 i.p.v. 2,4 kW) kost € 0,01.
- Plan van 19-11 ochtend hield 55 % vast voor 20-11; met de prijzen van 20-11 (38-44,1 ct, niet de verwachte piek 49,6) werd het verkopen + nachtladen. Register nr. 1 (21-11) rondt dit af met de werkelijke verkoop van vandaag.
- Regels c: geen verliesverkoop buiten de quitte avondcyclus; geen import duurder dan een later kwartier met accu-energie over (netafname 13:00-15:15 bij 37-40 ct, accu later verkocht op 43-44: vasthouden was meer waard); geen lege accu met eerder goedkoper laden; geen vastgehouden lading.
- PV-plan 10 d **−6,9 %** (−3,9 gisteren), 30 d −11,0 %; per uur 2 dagen: 10-13 u te laag voorspeld, toch dagtotaal te hoog over 10 d → register nr. 2 (24-11). 19-11 2,04 tegen ochtendplan 1,41. Verbruik 19-11 15,24 tegen 12,35 (−19 %), **4e dag op rij te laag** (H-EMS-24). Nacht 1,78 kWh. Brier 0,143.
- Module 1: 100 % 0,02 V (mediaan), 0 % 0,04 V, daghoogste 0,14 V vannacht bovenin (rust 06:43 0,11 V: cellen 3,48/3,37; anderen 0,03/0,02; 18-11 0,17), laagste cel 19-11 3,16 (gelijk), laagste stand 21 % tegen 20/21. Geen drempel.
- Register nr. 7: 29/31 opdrachten gevolgd (93,5 %); beide 'niet gevolgd' zijn laden op 93-95 % SoC (afbouw bovenin), geen weigering. Register nr. 8: eerste waardeplandag 2027 laat € 0,03 liggen.
- **Gebouwd v5.250.0 (L-EMS-081, rapportage/classificatie):** ontdekking meldde 19-11 16:01 drie Eufy-knoppen 'Beeldherkenning' als stekker (push naar Ruud); planningssamenvatting zei 'verkoopt op dit moment niet' terwijl het waardeplan verkoopt. Suite 7283 groen, workflow groen, Marketplace ververst.
- Storingen: geen (cachewaarschuwingen Zonneplan/Solcast rond 00:00, bekend). Stilstand 4 wachten, 0 doen.
- Niet gemeten: SoC-voorspelling, NILM; loslaten woning-eerst niet apart te scheiden (cyclus quitte).

laatste ronde: 20-11 06:45, gemeten t/m 20-11 06:45

## 21-11 06:45 · dagcontrole (20-11 06:45 t/m 21-11 06:45; v5.250.0 geïnstalleerd, geen herstart sinds 20-11 07:07)
- Achteraf (LP 96 kw, marginaal −11,08 ct, slijtage 4,22 ct, start 100 % eind 25 %, zelfde eindvoorraad): werkelijk € 0,82, optimum € 0,82 (met gemeten laadrendement 78 % € 0,83) → **gemist € 0,00, 0 FOUT, 0 PECH**.
- 20-11: verkocht 07:15-09:15 (1,27 kW, 41,6-43,8 ct), 10:30, 15:30-16:45 en 18:00-19:00 (43,0-44,1 ct), 7,1 kWh uit de accu gem. 43,0 ct; leeg (11 %) vanaf 19:15, huis van het net 36-42 ct; 03:45-04:45 1,55 kWh geladen (33,8 ct) tot 25 %. Import 17:00-17:30 bij 43,0-43,4 ct met 44 % in de accu die om 18:00 op 43,0 verkocht: < € 0,01.
- Loslaten woning-eerst: +€ 0,03 (1,35 kWh verkocht 43,09 ct, teruggekocht 40,74 ct). Knop verkopen-uit niet gebruikt.
- Register nr. 1 afgesloten: bewaren 18-11 avond (gem. 38,1 ct, accu vol) → verkocht 19-11 gem. 43,4 ct: loonde (~5 ct/kWh, ca. € 0,30). Vasthouden voor 20-11 werd op 19-11 terecht losgelaten: verwachting 20-11 gem 42,2 / piek 49,6, werkelijk 38,9 / 44,1 (piek 5,5 ct te hoog) → voedt nr. 5.
- Register nr. 3 afgesloten met voorstel **L-EMS-082**: schaduw 14 dagen: productie € 34,14, C0 € 34,49, C2 € 34,83 → marges op 0 bevestigd; schaduw uit de code (Ruud beslist).
- PV-plan 10 d **−0,8 %** (30 d −10,2 %), 20-11 3,06 tegen plan 3,19. Per uur 3 dagen: 10 u (+144 %) en 13 u te laag voorspeld (register nr. 2, 24-11). Verbruik 20-11 10,85 tegen 13,74 verwacht (+27 % te hoog; H-EMS-24 koude dagen: eerste dag de andere kant op). Nacht 1,83 kWh. Brier 7 avonden 0,00.
- Module 1: 100 % 0,02 V, 0 % 0,04 V, laagste cel 20-11 3,04 (anderen 3,05/3,06), laagste stand 11 % gelijk. Geen drempel.
- Register nr. 7: 35/35 gevolgd sinds herstart. Nr. 8: 20-11 waardeplan 2027 laat € 0,00 liggen. Storingen: geen (cachewaarschuwingen Zonneplan rond 00:00, bekend). Stilstand 0. Suite 7283 groen. Geen release.
- Niet gemeten: daghoogste celdelta module 1 (geschiedenis per dag niet eenduidig), SoC-voorspelling, NILM.

laatste ronde: 21-11 06:45, gemeten t/m 21-11 06:45

## 22-11 06:45 · dagcontrole (21-11 06:45 t/m 22-11 06:45; v5.250.0 geïnstalleerd, geen herstart sinds 20-11 07:07)
- Achteraf (LP 96 kw, marginaal −11,08 ct, slijtage 4,22 ct, start 25 % eind 30 %): werkelijk € 1,27, optimum € 1,26 → **gemist € 0,01, 0 FOUT, 0 PECH** (verkoop 1,26 kW gespreid i.p.v. 2,4 kW in de duurste kwartieren). Zonder accu € 1,20.
- 21-11: ochtendverkoop 08:00-09:00 (0,69 kWh, 40,3-43,2 ct) tot 13 %; netladen 11:19-14:15 gem. 32,9 ct tot 81 % (6,71 kWh AC, laadrendement **85 %** op de Zendure-teller; de kwartier-snapshots gaven 8,07 kWh = te hoog), LP laadt in hetzelfde blok; verkoop 16:30-19:45 3,76 kWh gem. 41,6 ct tot 31 %; 31 % vastgehouden voor vanavond (22-11 17:00-19:15 40,3-41,9 ct): terecht, geen extra cyclus.
- Regels c: geen verliesverkoop (middagladen → avondverkoop +0,6 ct/kWh, quitte); import 21:30 (1,6 kW, 37,7 ct) met 31 % in de accu: later kwartier is duurder (41,9), dus geen fout; geen lege accu met eerder goedkoper laden; geen onnodig vastgehouden lading.
- Loslaten woning-eerst: +€ 0,15 (3,76 kWh verkocht 41,61 ct; huis 20:00-06:45 3,03 kWh van het net 36,68 ct). Knop verkopen-uit niet gebruikt.
- PV-plan 10 d **+1,5 %** (30 d −9,2 %); 21-11 4,26 tegen ochtendverwachting 4,95. Per uur 4 dagen: 10 u +116 %, 13 u +35 %, 15 u −36 % (register nr. 2, 24-11). Snelle correctie 0,95 → 0,84 kWh/d. Verbruik 21-11 8,07 tegen 12,97 verwacht (**+61 % te hoog**, 2e dag op rij te hoog na 4 dagen te laag; H-EMS-24 wisselt van teken: geen structurele richting). Nacht 2,12 kWh.
- Module 1: 100 % 0,02 V, 0 % 0,04 V (anderen 0,01/0,01), laagste cel 21-11 3,07 (3,07/3,08), laagste stand 13 % gelijk. Geen drempel.
- Register nr. 7: 80/80 gevolgd sinds herstart (21-11: 49 gevolgd, 7 onbekend). Nr. 8: 21-11 waardeplan 2027 laat € 0,00 liggen (3 dagen € 0,03). Niets op of over de besluitdatum (nr. 4 morgen).
- Storingen: geen (cachewaarschuwingen Zonneplan rond 00:00, bekend). Eenmalig 21-11 21:09 HA-waarschuwing 'Dagarchief bijwerken duurde 2,4 s' (attributen 40 kB, 812 dagen; lokaal 12 ms per berekening, tweemaal per schrijfbeurt): eenmalig, geen release; volgen.
- Stilstand 0. Geen release.
- Niet gemeten: MC-Brier (geen avondmeting opgehaald), daghoogste celdelta module 1, SoC-voorspelling, NILM.

laatste ronde: 22-11 06:45, gemeten t/m 22-11 06:45

## 23-11 06:45 · dagcontrole (22-11 06:45 t/m 23-11 06:45; v5.250.0 geïnstalleerd, geen herstart sinds 20-11 07:07)
- Achteraf (LP 96 kw, marginaal −11,08 ct, slijtage 4,22 ct, laadrendement 78,4 % op de snapshots = zelfde maatstaf, start 30 % eind 98 %): werkelijk € 4,82, optimum € 4,79 → **gemist € 0,04, 0 FOUT, 1 PECH** (middag 22-11 laden op 34,5-35,0 ct i.p.v. nacht 35,0-35,1; nachtprijzen pas ~13:00 bekend). Met Zendure-teller (82,9 %) € 0,13, zelfde uitspraak.
- 22-11: vlakke prijzen 34,5-41,9 ct; accu hield 30-36 % de hele dag en avond vast; 23:45-05:15 7,3 kWh AC geladen op gem. 35,07 ct tot 98 % voor de piek van 23-11 (45-51 ct). Vasthouden in de avond (40,7 ct) terecht: ontladen en terugladen kost 35,1/0,83 + 4,2 = 46,5 ct.
- Regels c: geen verkoop; avondimport bij 36 % niet fout (later duurder, en terugladen duurder dan de besparing); geen lege accu; geen onnodig vastgehouden lading. Loslaten woning-eerst € 0,00; knop verkopen-uit niet gebruikt.
- PV-plan 10 d **+3,6 %** (30 d −8,9 %); 22-11 4,70 tegen ochtendverwachting 5,09. Per uur 5 dagen: 10 u +117 %, 9 u +27 %, 13 u +24 %, 15 u −28 % (register nr. 2 morgen). Verbruik 22-11 16,33 tegen 10,97 verwacht (**−33 %, te laag**; 4,5 °C; na 2 dagen te hoog: H-EMS-24 wisselt nog). Nacht 2,35 kWh.
- Module 1: 100 % 0,02 V, 0 % 0,04 V (anderen 0,01/0,01), laagste cel 22-11 3,16 (3,16/3,16), daghoogste celdelta 0,03 (0,02/0,03). Geen drempel.
- Register nr. 4 **afgesloten**: goedkoopste meerprijs d1 live 1,44 ct (35 d; 7 d 0,32), duurste gemist 0,80 ct → vaste bewaking, geen modelwerk. Nr. 7: nacht 23-11 10 gevolgd, 9 niet_gevolgd; alle zichtbare missers laden bij SoC 83-98 % (1,29-1,99 kW, dalend met SoC: afbouw bovenin). Laadvermogen 40-60 % ~2,25 kW. Oordeel 26-11. Nr. 8: 22-11 € 0,00.
- Storingen 0 (Zonneplan-kostensensoren rond 00:00 onbeschikbaar, bekend). Stilstand 0. Suite 7283 groen. Geen release.
- Niet gemeten: MC-Brier (geen avondmeting), SoC-voorspelling, NILM; de eerste 4 van 9 missers (alleen laatste 5 zichtbaar).

laatste ronde: 23-11 06:45, gemeten t/m 23-11 06:45

## 24-11 06:45 · dagcontrole (23-11 06:45 t/m 24-11 06:45; v5.251.1 geïnstalleerd, herstart 23-11 ~14:53)
- Achteraf (LP 96 kw, marginaal −11,08 ct, slijtage 4,22 ct, laden 82,1 % sluitend op de snapshots, ontladen 99 %, start 98 % eind 100 %): werkelijk € 3,39, optimum € 3,33 → **gemist € 0,06, 1 FOUT, 0 PECH**. Zonder accu € 3,52.
- FOUT 23-11 07:45-10:15: 2,08 kWh verkocht op 46-48 ct (1,25 kW), daarna 11:00-14:15 2,77 kWh AC teruggeladen op 38,3-39,6 ct tot 99 % (Zendure-teller: 74 % laadrendement). Regel c: verkoop + terugkoop kostte meer dan hij opbracht (teller € −0,10, LP € −0,06). Zonder deze cyclus was de accu om 16:15 even vol geweest (avond zat op max vermogen). Oorzaak: plan rekent laden vlak met 82,8 % en ontladen bij 0,5-1,5 kW met 102,8 %; in eigen model quitte. **H-EMS-25 (nieuw):** laden boven ~90 % kost meer (uurstatistiek 10-24/11: 72 % tegen 83-85 % eronder). 24-11 plant hetzelfde patroon (verkoop 06:45-09:15 47-52 ct, bijladen 11:15+ 39-40 ct). Toetsen met minuutdata; bij bevestiging voorstel SoC-afhankelijk laadrendement.
- Avond 16:15-19:15 2,4 kW verkocht 49,7-53 ct tot 10 %; huis 19:30-24:00 3,18 kWh van het net 43,9 ct: loslaten woning-eerst +€ 0,18. Nachtladen 23:45-05:15 9,20 kWh AC gem 37,6 ct (84,6 %), goedkoopste kwartieren ≤ € 0,01 ernaast. Knop verkopen-uit niet gebruikt.
- Register nr. 2 **afgesloten**: per uur 6 dagen 10 u +100 % (+0,30 kWh/d), dagtotaal 10 d −3 %; onder saldering geen euro-effect (zon om 10 u wordt teruggeleverd op 42-46 ct) → geen correctie, vaste bewaking (nodig voor nr. 12, 01-03-2027).
- PV-plan 10 d **−3,0 %** (30 d −8 %). Verbruik 23-11 13,90 kWh; meetlat sinds herstart 1 u vooraf −45 W (te laag), 3 u −39 W. Nacht 3,18 kWh (incl. vaatwasser 03:15).
- Module 1: 100 % **0,09 V** (gisteren 0,02; accu stond vanaf 05:15 op 100 %, eerder 98-99 %; bij 99 % live 0,01; = nulmeting 10-11), 0 % 0,04 V, laagste cel 23-11 3,03 (3,06/3,06), daghoogste celdelta 0,16 (0,05/0,03). Geen drempel; volgen of de 100 %-mediaan verder stijgt.
- Register nr. 7: sinds herstart 44 gevolgd, 2 niet (laden bij 95 %), 5 kan_niet = 95,7 %. Nr. 8: 23-11 € 0,00. Reserveprijs EnergyZero: 96 geleerde kwartieren, opslag 13,1 ct, fout null.
- Storingen 0 (prijssensor kort leeg na herstart 23-11 15:00, Zonneplan-kostensensoren rond 00:00: bekend). Schaduw-entiteiten weg. Stilstand 0. Suite niet gedraaid (geen codewijziging). Geen release.
- Niet gemeten: verbruik tegen ochtendverwachting (geen archiefwaarde opgehaald), MC-Brier, SoC-voorspelling, NILM.

laatste ronde: 24-11 06:45, gemeten t/m 24-11 06:45

## 25-11 06:45 · dagcontrole (24-11 06:45 t/m 25-11 06:45; v5.258.1 actief sinds herstart 05:05)
- Achteraf (LP 96 kw, marginaal −11,08 ct, slijtage 4,22 ct, laden 82,1 %, ontladen 99 %, start 100 % eind 54 %): werkelijk € 4,23, optimum € 4,10 → **gemist € 0,13, 1 FOUT accu, 0 PECH**; zonder accu € 5,75. DP met SoC-afhankelijk laden (85/82/78 %): optimum € 4,02.
- FOUT 24-11: 06:45-09:15 4,63 kWh verkocht op gem. 49,4 ct, 11:30-13:15 3,94 kWh AC bijgeladen op 39,3 ct tot 82 % (laadtoeslag v5.252.0 stopte terecht bij ~80 %); avondpiek 50-55 ct begon op 80 %, accu leeg 18:15. Optimum: 's ochtends 1,8 kWh (07:45-08:15), rest voor de avond. De ruil zelf quitte (33,8 tegen 34,3 ct per kWh inhoud), het verlies zit in de te lege avond (−€ 0,24 avond, +€ 0,06 nacht/rest). Prijzen waren bekend → geen pech. **H-EMS-26 (nieuw):** ontlaadbanden in het plan 100,5 % (<0,5 kW) / 102,2 % (0,5-1,5 kW) / 99,4 % (>1,5 kW): verkopen op middelhoog vermogen lijkt ~3 % goedkoper dan de avond op vol vermogen; gemeten ontladen ~99 %. Tweede dag op rij hetzelfde patroon (23-11 € 0,06). Toetsen met een replay; dan pas voorstel.
- FOUT 25-11 04:24-04:55 airco aan (fout v5.253-5.258.0, opgelost v5.258.1, actief 05:05): 0,8 kWh, € 0,30. 06:30 werkdagstart zoals ingesteld.
- **H-EMS-27 (nieuw):** de werkdag-airco die al draait telt niet in het plan (06:30 gemeten 1432 W, plan 248 W; verbruik_opbouw zonder klimaat_kwh). In `airco_ritme.gebruik_kwh` slaat `zonder_ochtend` ook 'zeker'-uren (airco draait) in 04-11 over. Euro-effect vermoedelijk klein (accu houdt, net dekt). Drie werkdagochtenden meten met de verbruiksmeetlat, dan bouwen als het blijft.
- Regels c: ochtendruil quitte (±0,6 ct/kWh); avondimport 18:30-24:00 4,17 kWh gem 44,2 ct bij lege accu terwijl middag 39,3 ct was → valt onder de FOUT. Nachtladen 04:30-06:15 36,3-37,3 ct (goedkoopste nachtkwartieren). Knop verkopen-uit niet gebruikt. Loslaten woning-eerst +€ 0,23.
- PV-plan 10 d **+1,3 %** (30 d −7,1 %); 24-11 3,49 kWh. Verbruik 24-11 20,9 kWh (airco 10,8: 0,55 kWh/graad, 18,6 °C binnen, −1,1 °C buiten, € 4,88; nr. 16 nulmeting 6,3 kWh/0,45). Nacht 2,70 kWh.
- Module 1: 100 % 0,09 V (gelijk aan gisteren), 0 % 0,04 V (anderen 0,01/0,01), laagste cel 24-11 3,05 (3,07/3,08), daghoogste celdelta 0,03; SoC −3,5 % alleen tijdens laden, bij de lage stand gelijk. Geen drempel.
- Register nr. 5 **beoordeeld**: 6 dagen −1,84 ct (5/6 te laag), fout 2,73 ct → marge-regel houden, eindprijs opnieuw 09-12. Nr. 7: sinds herstart 8/8. Nr. 8: 24-11 € 0,00. Nr. 16: zie boven; nabeschouwing 24-11 gemist € 0,08, leverde € 0,22.
- Storingen 0 (alleen opstartmelding Solcast/energy_production_today na herstart). Stilstand 0. Geen codewijziging, suite niet gedraaid, geen release.
- Niet gemeten: MC-Brier, SoC-voorspelling, NILM; replay van H-EMS-26 (tijd).

laatste ronde: 25-11 06:45, gemeten t/m 25-11 06:45

## 26-11 06:45 · dagcontrole (25-11 06:45 t/m 26-11 06:45; v5.260.0 actief sinds herstart 25-11 17:50)
- Achteraf (LP 96 kw, accudeel, laden 82,1 %, ontladen 99 %, start 54 % eind 99 %): werkelijk € 0,60, optimum € 0,54 → **gemist € 0,06, 0 FOUT, 0 PECH** (nabeschouwing EMS ook € 0,06). Ochtend 08:30-09:15 verkocht 44,6-48,9 ct, 10:45-13:45 bijgeladen 29,6-36 ct tot 100 %, 14:45-18:45 verkocht 48-50 ct tot 11 %, nacht 22:00-05:15 8,9 kWh AC op 33,5-36,9 ct.
- Regels c: ochtendverkoop + middagterugkoop met winst (44,7-48,9 tegen ~32 ct); avondimport 19:00-22:00 3,47 kWh 41,3 ct bij lege accu, maar de lading ging voor 49 ct weg; geen onnodig vastgehouden lading. Loslaten woning-eerst +€ 0,31. Verkoopmarge 2 ct sinds 25-11 17:45 (keuze Ruud). Knop verkopen-uit niet gebruikt.
- PV-plan 10 d **+5,3 %** (plan te laag; 30 d −6,5 %), net buiten ±5 %: komt van 10 u (+71 %, 68 % van het verschil). Onder saldering geen euro-effect (nr. 2 afgesloten); na 31-12 wel relevant, nr. 12 (01-03-2027). Geen voorstel.
- H-EMS-27: 2e werkdagochtend: 26-11 06:30 gemeten 1242 W tegen 332 W (1 u vooraf); werkdag-airco zit niet in het plan. Morgen 3e ochtend, dan oordeel.
- Nr. 16 airco 25-11: 10,7 kWh (0,8 nachtfout), 0,56 kWh/graad (0,52 zonder fout) tegen nulmeting 0,45; binnen 18,7 °C, buiten −0,5; € 4,41. Accu: gemist € 0,06, leverde € 0,33.
- Module 1: 100 % 0,08 V (was 0,09), 0 % 0,04 V (anderen 0,01/0,01), laagste cel 25-11 3,08 (3,10/3,11), daghoogste celdelta **0,20** (hoogste tot nu, bij volladen; bucket 90 % 0,11). Geen drempel; volgen.
- Register nr. 7 **afgesloten**: sinds herstart 36/37 gevolgd (97,3 %), de enige misser en alle eerdere = afbouw bovenin → stap b niet nodig, opdrachten_gevolgd wordt vaste bewaking. Nr. 13 **afgesloten**: oude regels stuurden sinds 10-11 00:30 geen kwartier meer (0 van ~1530) → terugval blijft als vangnet; L-EMS-083 (dode code en rapportages eruit) wacht op Ruud. Nr. 8: 25-11 € 0,00.
- Storingen: 26-11 04:10-04:12 Zendure-integratie zag de accu 2 min offline (2 waarschuwingen), herstelde zelf; plan stond op houden. Stilstand 0. Geen codewijziging, geen release.
- Niet gemeten: MC-Brier, SoC-voorspelling, NILM; replay H-EMS-26.

laatste ronde: 26-11 06:45, gemeten t/m 26-11 06:45

- 26-11 08:50 (chat, Claude): v5.264.0 - de werkdagochtend van de airco zat niet in de verbruiksverwachting doordat `nacht_extra_kwh` het airco-profiel van het hele planvenster (37 uur) van de ochtend aftrok. Nu per uur. De meting "06:30 verwacht tegen gemeten" is dus pas zinvol vanaf de eerste ochtend na de herstart op v5.264.0; de drie ochtenden daarvoor zijn de oude fout.

## 27-11 06:45 · dagcontrole (26-11 06:45 t/m 27-11 06:45; v5.265.0 actief sinds herstart 26-11 13:56, v5.266.1 geïnstalleerd en wacht op herstart)
- Achteraf (LP 96 kw, accudeel, laden 82,1 %, ontladen 99 %, vloer 12 %, laadafbouw boven 80 %, start/eind 99 %): werkelijk € −0,53, optimum € −0,72 → **gemist € 0,19, 0 FOUT, 0 PECH**. Knop verkopen-uit (Ruud, 26-11 10:15-24:00) kostte € 0,05 (LP zonder verkoop € −0,67). Rest € 0,14 zit in de avondverdeling op snapshot-huislast (accu volgde per 5 min het huis onder 2,4 kW, leeg 20:30) en in nachtladen 23:45/01:15-01:30 op 40-41 ct (laadafbouw dwingt eerder beginnen): geen beslisfout aan te wijzen. Nabeschouwing EMS (kalenderdag 26-11): gemist € 0,36, leverde € 1,02.
- Regels c: geen verkoop (knop); avondimport 20:45-23:30 bij lege accu 41,6-51,2 ct na een avond op 51-60 ct: lading ging naar de duurste kwartieren; geen onnodig vastgehouden lading. Ochtend 26-11 06:45-08:15 netafname 44-53 ct met volle accu: zon vulde daarna niet bij boven 100 % en onder saldering is terugleveren gelijkwaardig → terecht.
- **H-EMS-27 geverifieerd** (v5.264.0): 27-11 06:30 verwachtte het plan 1000 W (1 u) / 1427 W (dit kwartier) tegen 248-332 W op 25/26-11; gemeten 2899 W (airco + andere last). Gesloten.
- PV-plan 10 d **+10,2 %** (plan te laag; 30 d −6,1 %), buiten ±5 % en oplopend (+1,3 → +5,3 → +10,2): 10 u +64 % (62 % van het verschil). Onder saldering geen euro-effect; meetregister nr. 12 (01-03-2027) neemt de uurcijfers mee. Geen voorstel.
- Nr. 11 regelkwaliteit **beoordeeld** (besluitdatum): 11 dagen, rustig 17,8 u netto −7,6 W, Quooker 1,6 u +530 W (65 % van de afname), geen storing → sluiten, code eruit = **L-EMS-084** (wacht op Ruud). Nr. 16: airco 26-11 8,5 kWh, 0,45 kWh/graad (= nulmeting), binnen 17,5 °C (iedereen weg 08:16-12:46), € 4,55. Nr. 18: 15 blokken, **geen fase herkend**: accu en zon op L1 overstemmen de airco-fase → meetfout, fix met 2 tests klaar op branch wip/ijking-accufase (niet uitgebracht: v5.266.1 wacht nog op herstart). Nr. 8: 26-11 € 0,00.
- Module 1: 100 % **0,12 V** (was 0,08; accu stond 26-11 acht uur op 98-100 %, bucket ververst; hoogste 0,13), 0 % 0,04 V (anderen 0,04/0,01 bij 100 %, 0,01/0,01 bij 0 %), laagste cel 3,02 (3,04/3,05), daghoogste celdelta 0,12. Geen drempel (≥ 0,13 of 3 dagen stijgend), wel dichtbij: volgen.
- Storingen 0 (Zonneplan-kostensensoren na middernacht onbeschikbaar: bekend). Stilstand 0. Opdrachten 18/19 (misser = afbouw 96 %). Suite op de wip-branch 7301 + 2 geslaagd (bestandslijst bijgewerkt). Geen release.
- Niet gemeten: MC-Brier, SoC-voorspelling, NILM; replay H-EMS-26 (nr. 17, besluit 02-12).

laatste ronde: 27-11 06:45, gemeten t/m 27-11 06:45
