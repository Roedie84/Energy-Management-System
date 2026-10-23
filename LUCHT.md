# Luchtkwaliteit en luchtreiniger - meetlog

Maatstaf: UltimateSensor woonkamer (PM2.5 µg/m³). Getallen staan in LUCHT.csv.

## 11-10 12:23 (ronde 1, nulpunt nieuwe sturing)
- PM2.5 dagen 08-10 t/m 11-10: gem 2,8 / 2,3 / 0,9 / 0,7 (WHO-jaar 5). Okt 2026 t/m nu ~2,8 vs nulmeting okt 2025 9,1.
- Pieken > 25: 08-10 17:00 kookpiek 190 (kookplaat aan), halveringstijd ~5 min na kookplaat uit, < 10 na 25 min. 09-10 21:40 piek 30 zonder koken, halveert trager (~23 min), < 10 na 65 min; oorzaak onbekend (raamsensoren toen unavailable).
- 10-10 kookplaat 41 min aan met keukenraam open: max 3,4 - geen piek.
- Stand per piek onbekend: select-entiteit en fan-history pas sinds 11-10 11:15. Automation sinds 12:12: 5 runs, 0 fouten, stand nu auto (aanwezig). Lokaal: 198/198 rondes, 0 uitval, sturen 4/4 bevestigd. Filtergebruik 0%.
- Eigen PM2.5 apparaat staat vrijwel altijd op 2; bij de kookpiek 390 tegen 190 (UltimateSensor): grof, overschat pieken.
- CO₂ 09-10 6 uur > 1.200 ppm (max 1.549, avond) - ventileren, geen luchtreinigerzaak.
- Hypotheses: H1 koken met raam/afzuiging open geeft nauwelijks piek (n=3 kookmomenten). H2 auto halveert een kookpiek in ~5 min; toets per stand bij volgende pieken (n=1). H3 niet-kookpieken 's avonds dalen 4x trager - lagere stand (sleep?) of aanhoudende bron (n=1).

## 11-10 16:25 (ronde 2)
- PM2.5 12:15-16:20: gem 2,4, mediaan 1,2, P95 9,8, max 13 (n=49 blokken); 0 uur > 15. Auto 183 min (gem 2,7), mid 23 min (gem 1,0), stand onbekend 39 min.
- Geen piek > 25. Bult 13:25 tot 13 µg/m³ zonder koken, ramen dicht, stand auto; CO₂ en vocht stegen mee (activiteit). Halveringstijd ~10 min, < 2 na 50 min.
- Aanwezig 3,7 vs afwezig 0,9 µg/m³: verschil komt van de bron (mensen), niet van de stand.
- Werking: stand volgt aanwezigheid (mid ~5 min na vertrek, auto bij terugkomst). Lokaal 741/741 rondes, sturen 7/7 bevestigd, filter 0%. Apparaat-PM2.5 bij de bult max 9 (Ultimate 13): volgt nu redelijk.
- Opvallend: HA herstart ~elke 10 min sinds 12:10 (n=20, ~70 s per keer, uptime bevestigt). Stand dan unavailable; apparaat draait door. Traces gaan bij elke herstart verloren.
- CO₂ gem 777, max 1.007: in orde.
- Hypotheses: H1 koken met raam open → nauwelijks piek (n=3, geen nieuwe toets). H2 auto halveert kookpiek ~5 min (n=1, geen nieuwe kookpiek). H3 niet-kookbronnen dalen trager: 13:25 in auto ~10 min vs 5 bij koken (n=2, zwak - bron mogelijk nog actief).

## 11-10 20:25 (ronde 3)
- PM2.5 16:20-20:20: gem 1,0, mediaan 0,9, P95 1,8, max 2,6 (n=48); 0 uur > 15. Dag t/m nu 1,1; 7d 2,6 (nulmeting okt 2025 9,1).
- Geen piek > 25. Auto 174 min (gem 1,2), mid 57 min (gem 0,5): mid viel in de rustige middag, auto in de avond met activiteit - geen standvergelijking mogelijk.
- 18:20-20:20 avondactiviteit, ramen dicht, auto: CO₂ 510→1.741, VOC-index 50→490, temp +1,4 °C, schimmelindicator 67→80; PM2.5 bleef < 2,6. Kookplaat/oven-status unavailable sinds 17:19, dus koken niet te bevestigen.
- Werking: stand volgt aanwezigheid (mid ~5 min na vertrek). 7 HA-herstarts t/m 18:09, daarna stabiel (>2 u). Lokaal 1878/1878 rondes, sturen 18/18, filter 0%. Apparaat-PM2.5 staat vast op 2: onbruikbaar onder ~5 µg/m³.
- CO₂ 1,4 u > 1.200 en schimmelindicator 80: ventileren 's avonds; geen luchtreinigerzaak.
- Hypotheses: H1 koken met raam/afzuiging → nauwelijks piek (n=3; avond 18:20 mogelijk kookmoment zonder PM-piek, onbevestigd). H2 auto halveert kookpiek ~5 min (n=1, geen nieuwe piek). H3 niet-kookbronnen dalen trager (n=2, geen nieuwe toets).

## 12-10 00:25 (ronde 4, eerste na middernacht)
- Dag 11-10: gem 1,08 µg/m³, max 13, 0 uur > 15. 7d 2,6 (nulmeting okt 2025 9,1; stookseizoen 2025 vóór reiniger 16,0).
- PM2.5 20:20-00:20: gem 0,9, mediaan 0,9, P95 1,4, max 1,7 (n=48); geen piek > 25. Auto 165 min (gem 1,0), mid 66 min (gem 0,6, vooral nacht): geen standvergelijking mogelijk.
- Werking: auto bleef aan zolang de tv aan stond (21:24-23:16), mid 6 min na tv uit. Na herstart 22:18 2 min mid terwijl tv aan (tv-status unknown). Lokaal 3006/3006, sturen 20/20, filter 0%. Apparaat-PM2.5 vast op 2.
- HA-herstarts weer terug: 8 tussen 21:01 en 23:30 (~70 s elk). Kookplaat/oven-status sinds 17:19 unavailable.
- CO₂ gem 1.240, 2,75 u > 1.200 (dag 11-10: 4,2 u, max 1.741); daalt pas na 23:00. Avond ventileren.
- Hypotheses: H1 (n=3), H2 (n=1), H3 (n=2): geen nieuwe pieken, geen toets.

## 12-10 04:25 (ronde 5)
- PM2.5 00:20-04:20: gem 0,34, mediaan 0,35, P95 0,42, max 0,54 (n=48); 0 uur > 15. Hele nacht mid (239 min, gem 0,34), niemand aanwezig, ramen dicht, tv uit.
- Geen piek > 25, geen kookmoment (kookplaat/oven-status nog steeds unavailable sinds 11-10 17:19).
- Werking: automation 5/5 traces zonder fout; 1 HA-herstart 03:33 (~70 s), stand daarna direct weer mid. Lokaal 4434/4434, uitval 0, sturen 20/20, filter 0%. Apparaat-PM2.5 vast op 2 (Ultimate 0,3).
- CO₂ daalt 883 → 577 ppm (gem 676), schimmelindicator 75 → 73: in orde.
- Hypotheses: H1 (n=3), H2 (n=1), H3 (n=2): geen nieuwe pieken, geen toets.

## 12-10 08:25 (ronde 6)
- PM2.5 04:20-08:20: gem 0,71, mediaan 0,47, P95 1,58, max 1,86 (n=48); 0 uur > 15. Dag t/m nu 0,48; 7d 2,3 (nulmeting okt 2025 9,1).
- Geen piek > 25. Ochtendactiviteit vanaf ~06:35: PM2.5 0,3 → 1,7, CO₂ 525 → 739, VOC-index 55 → 245; ramen dicht. Kookplaat/oven-status nog steeds unavailable (sinds 11-10 17:19).
- Stand: auto 122 min (gem 1,06, aanwezig), mid 115 min (gem 0,37, afwezig). Verschil = bron, geen standeffect.
- Automation aangepast (12-10, Ruud): mid pas na 15 min zonder aanwezigheid, 00-06 geen wissels. Gemeten: mid 15 min na vertrek (n=2), eerste wissel 06:03. 5/5 traces zonder fout.
- Lokaal 5844/5844, uitval 0, sturen 28/28, filter 0%. HA-herstarts 06:14 en 06:48. Apparaat-PM2.5 vast op 2.
- CO₂ gem 584, max 739: in orde. Schimmelindicator 72-74.
- Hypotheses: H1 (n=3), H2 (n=1), H3 (n=2): geen nieuwe pieken, geen toets.

## 12-10 12:25 (ronde 7)
- PM2.5 08:20-12:20: gem 0,96, mediaan 0,86, P95 1,62, max 1,85 (n=48); 0 uur > 15. Dag t/m nu 0,67; 7d 2,3 (nulmeting okt 2025 9,1).
- Geen piek > 25, geen kookmoment (kookplaat/oven-status nog steeds unavailable sinds 11-10 17:19). Ramen dicht.
- Hele periode niemand aanwezig (sinds 08:05), tv uit. Toch 6x auto (56 min): steeds direct na een HA-herstart. Trace toont oorzaak: de 'uit voor 15 min'-voorwaarde op aanwezigheid begint opnieuw te tellen als de sensor unavailable → off gaat. Onschadelijk voor PM2.5 (auto 1,14 vs mid 0,91), wel onnodige wissels.
- Werking: 5/5 traces zonder fout. 7 HA-herstarts 08:26-10:53, daarna stabiel. Lokaal 7008/7008, uitval 0, sturen 36/36, filter 0%. Apparaat-PM2.5 vast op 2.
- CO₂ gem 589, max 672; schimmelindicator 73 → 63: in orde.
- Hypotheses: H1 (n=3), H2 (n=1), H3 (n=2): geen nieuwe pieken, geen toets.

## 12-10 16:25 (ronde 8)
- PM2.5 12:20-16:20: gem 0,86, mediaan 0,75, P95 1,67, max 1,99 (n=48); 0 uur > 15. Dag t/m nu 0,70; 7d 2,3 (nulmeting okt 2025 9,1).
- Geen piek > 25. Kleine bult 13:00 tot 2,0 zonder aanwezigheid of open raam; CO₂ daalde tegelijk (546 → 445). Kookplaat/oven-status nog steeds unavailable (sinds 11-10 17:19).
- Stand: auto 104 min (gem 1,03), mid 128 min (gem 0,75). Aanwezig 49 min (vanaf 15:20) 1,06 vs afwezig 0,81: verschil = bron.
- Werking: 5x auto zonder aanwezigheid, weer steeds direct na een HA-herstart (zelfde oorzaak als ronde 7). 5/5 traces zonder fout. 7 HA-herstarts 12:37-16:11. Lokaal 8232/8232, uitval 0, sturen 45/45, filter 0%. Apparaat-PM2.5 vast op 2.
- CO₂ gem 486, max 636; schimmelindicator 63 → 57: in orde.
- Hypotheses: H1 (n=3), H2 (n=1), H3 (n=2): geen nieuwe pieken, geen toets.

## 12-10 20:25 (ronde 9)
- PM2.5 16:20-20:20: gem 15,3, mediaan 3,1, P95 68, max 135 (n=48); 0,8 u > 15, 0,7 u > 25. Dag t/m nu 3,6; 7d 2,7 (nulmeting okt 2025 9,1).
- KOOKPIEK: start ~16:57, kookplaat run 17:03-17:15 (status daarvoor unavailable), ramen dicht, stand auto, aanwezig. Max 135 om 17:11. Halveringstijd na kookplaat uit ~12 min (fit 17:15-17:29), over de hele daling 15 min; < 10 pas om ~18:07 (53 min na uit). 08-10 (stand onbekend) halveerde ~5 min: deze keer 2-3x trager.
- Stand: auto 214 min (gem 16,6, incl. piek), mid 25 min (gem 4,2, staart): geen standvergelijking mogelijk.
- Werking: mid precies 15 min na vertrek (18:30). Na HA-herstart 18:34 weer 5 min auto zonder aanwezigheid (bekende oorzaak). 5/5 traces zonder fout. 1 HA-herstart. Lokaal 9645/9645, uitval 0, sturen 49/49, filter 0%. Kookplaatstatus weer beschikbaar sinds 17:03. Apparaat-PM2.5 volgde de piek (max 150): bruikbaar bij hoge waarden.
- CO₂ gem 1.129, 1,1 u > 1.200, max 1.534 (19:55, stijgend), ramen dicht; schimmelindicator 79 na koken, nu 75. Ventileren.
- Hypotheses: H1 koken met raam open → nauwelijks piek, met ramen dicht wel (n=4: 10-10 open max 3,4; 12-10 dicht 135) - gesteund. H2 aangepast: auto halveert kookpiek in ~12 min (n=2: 5 en 12 min, spreiding groot); turbo nog niet getest. H3 niet-kookbronnen dalen trager (n=2, geen toets).

## 13-10 00:25 (ronde 10, eerste na middernacht)
- Dag 12-10: gem 3,5 µg/m³ (door kookpiek 135), 0,8 u > 15, 0,7 u > 25. 7d 2,7 (nulmeting okt 2025 9,1; stookseizoen 2025 vóór reiniger 16,0).
- PM2.5 20:20-00:20: gem 2,9, mediaan 3,2, P95 4,0, max 4,4 (n=48); geen piek > 25, geen kookmoment, ramen dicht.
- Tv-avond hield PM2.5 op 3-4 (aanwezig 3,5 vs afwezig 1,8): bron = activiteit. Auto 173 min (gem 3,4), mid 61 min (gem 1,4, staart na vertrek): geen standvergelijking.
- Werking: mid 15 min na tv uit (23:15). 4 HA-herstarts; daarna 2 min mid terwijl tv aan (21:54) en 3 min auto na vertrek (23:30) - zelfde oorzaak, timers resetten bij unavailable/unknown. 5/5 traces zonder fout. Lokaal 10947/10947, uitval 0, sturen 53/53, filter 0%. Apparaat-PM2.5 vast op 2 (Ultimate 3-4).
- CO₂ gem 1.281, 2,75 u > 1.200 (dag 12-10: 3,8 u, max 1.543), ramen dicht; daalt pas na ~22:45. Schimmelindicator 76 → 72. Avond ventileren.
- Hypotheses: H1 (n=4, gesteund), H2 auto halveert kookpiek ~5-12 min (n=2), H3 (n=2): geen nieuwe pieken, geen toets.

## 13-10 04:25 (ronde 11)
- PM2.5 00:20-04:20: gem 0,64, mediaan 0,63, P95 0,76, max 0,95 (n=48); 0 uur > 15. Hele periode mid (240 min), niemand aanwezig, tv uit, ramen dicht.
- Geen piek > 25, geen kookmoment. Nachtniveau ~2x hoger dan 12-10 (0,34), mogelijk staart van de tv-avond (start 0,73 → 0,57).
- Werking: 0 HA-herstarts (uptime sinds 23:18), stand stabiel mid. 5/5 traces zonder fout. Lokaal 12390/12390, uitval 0, sturen 53/53, filter 0%. Apparaat-PM2.5 vast op 2.
- CO₂ daalt 910 → 613 ppm (gem 714), schimmelindicator 72 → 71: in orde.
- Hypotheses: H1 (n=4, gesteund), H2 auto halveert kookpiek ~5-12 min (n=2), H3 (n=2): geen nieuwe pieken, geen toets.

## 21-10 20:25 (ronde 12, inhaalslag 13-10 04:20 t/m 21-10 20:20; 8,5 dag geen ronde)
- PM2.5 daggem 13-20/10: 1,1 / 1,5 / 0,8 / 1,7 / 30,9 / 14,8 / 7,0 / 1,3; 21-10 t/m nu 1,4 (max 3,4). 7d gem 8,3 (mediaan dag 1,7): rustige dagen ~1-2, gemiddelde gedragen door twee gebeurtenissen.
- 17-10 19:15 tot 18-10 02:40: geen kookplaat/oven, ramen dicht, CO₂ tot 3.610 (veel mensen). In auto steeg PM2.5 10 → 59 in 50 min; 20:09 handmatig uit (low/auto/low/uit) → 335 om 00:30. Na aanzetten 00:40 (6 min auto, dan low) halvering ~27 min, < 10 om 02:40.
- Kookpieken, ramen dicht, auto: 14-10 30 (halvering ~24 min, kleine piek), 19-10 454 (halvering ~8 min eerste 20 min, ~16 daarna; < 10 na 65 min). Device-PM2.5 volgt grof (601 vs 345, 333 vs 454).
- Werking: stand volgt aanwezigheid 94% (06-24 u); afwijking vooral auto zonder aanwezigheid na HA-herstart. HA-herstarts/dag 3-34 (21-10: 34). Lokaal 36 mislukt op 83.305 (laatste = herstart 20:20), uitval 0, sturen 233/234, filter 0%. Traces 5/5 zonder fout.
- CO₂ 13-18/10 elke dag 6-13 u > 1.200 (max 2.200; 17-10 3.610); 19-21/10 0-5 u. Schimmelindicator 17/18-10 max 93. Nu 1.260 en stijgend, ramen dicht. Ventileren.
- Hypotheses: H1 koken met ramen dicht → piek, raam open niet (n=6: dicht 190/135/30/454, open 3,4) - sterk gesteund. H2 auto halveert kookpiek ~5-12 min (n=4: 5/12/8/24), low ~27 min (n=1): auto ~3x sneller dan low, voorkomt de piek niet; turbo niet getest. H3 (nieuw) bij aanhoudende bron/bezoek houdt auto het niet bij en uit laat het oplopen tot > 300 (n=1).

## 22-10 00:25 (ronde 13, eerste na middernacht)
- Dag 21-10: gem 1,31 µg/m³, mediaan 1,22, P95 2,1, max 3,4; 0 uur > 15. 7d gem 8,3 (mediaan dag 1,7; nulmeting okt 2025 9,1, stookseizoen 2025 vóór reiniger 16,0).
- PM2.5 20:20-00:20: gem 0,88, mediaan 0,90, P95 1,07, max 1,31 (n=48); geen piek > 25. Aanwezig (tv) 0,94 vs afwezig 0,67: bron. Auto 200 min, mid 38 min.
- Gemist in ronde 12: 21-10 16:59-17:22 kookplaat én oven aan, ramen dicht, auto - PM2.5 max 2,1, geen piek. Ramen dicht geeft dus niet altijd een piek: soort koken/afzuigkap telt.
- Werking: mid 15 min na tv uit (23:26 → 23:41); 5/5 traces zonder fout. HA-herstarts dag 21-10: 35 (deze ronde 2). Lokaal 36 mislukt op 84.677, uitval 0, sturen 234/235, filter 0%. Apparaat-PM2.5 vast op 2.
- CO₂ ronde gem 1.046, 1,4 u > 1.200 (max 1.326, tot 21:45); dag 21-10 2,0 u. Schimmelindicator nu 71. Avond ventileren.
- Hypotheses: H1 bijgesteld - ramen dicht is nodig maar niet voldoende voor een piek (n=7: dicht 190/135/30/454/2,1; open 3,4). H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5): geen nieuwe piek. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1), geen toets.

## 22-10 04:25 (ronde 14)
- PM2.5 00:20-04:20: gem 0,35, mediaan 0,35, P95 0,48, max 0,70 (n=48); 0 uur > 15. Hele periode mid, niemand aanwezig, tv uit, ramen dicht. Gelijk aan de schoonste nacht (12-10: 0,34).
- Geen piek > 25, geen kookmoment.
- Werking: nachtvenster houdt mid vast; 5/5 traces zonder fout (failed_conditions = 00-06 geen wissels). 3 HA-herstarts (01:47, 02:47, 03:33), stand < 20 s unavailable, geen auto-wissel. Lokaal 39 mislukt op 86.100 (+3, allemaal herstarts), uitval 0, sturen 234/235, filter 0%. Apparaat-PM2.5 vast op 2.
- CO₂ daalt 659 → 525 (gem 565), schimmelindicator 71: in orde.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=7), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5), H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1): geen nieuwe pieken, geen toets.

## 22-10 08:25 (ronde 15)
- PM2.5 04:20-08:20: gem 0,29, mediaan 0,28, P95 0,47, max 0,90 (n=48); 0 uur > 15. Dag t/m nu ~0,3; 7d (15-21/10) 8,3, mediaan dag 1,7 (nulmeting okt 2025 9,1).
- Geen piek > 25, geen kookmoment, ramen dicht. Ochtendactiviteit vanaf 07:29: PM2.5 0,3 → 0,9, CO₂ 500 → 719, VOC-index 30 → 235.
- Stand: mid 174 min (gem 0,27, afwezig), auto 65 min (gem 0,33). Aanwezig 0,36 vs afwezig 0,27: bron, geen standeffect.
- Werking: na HA-herstart 07:06 om 07:15 auto zonder aanwezigheid (14 min, tot 07:29) - bekende oorzaak, timer reset bij unavailable. 5/5 traces zonder fout. Lokaal 39 mislukt op 87.521 (geen nieuwe), uitval 0, sturen 235/236, filter 0%. Apparaat-PM2.5 vast op 2 (Ultimate 0,3-0,9).
- CO₂ gem 535, max 719; schimmelindicator 71 → 74: in orde.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=7), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5), H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1): geen nieuwe pieken, geen toets.

## 22-10 12:25 (ronde 16)
- PM2.5 08:20-12:20: gem 0,54, mediaan 0,51, P95 0,84, max 1,15 (n=48); 0 uur > 15. Dag t/m nu 0,39; 7d (15-21/10) 8,3, mediaan dag 1,7 (nulmeting okt 2025 9,1).
- Geen piek > 25, geen kookmoment, ramen dicht. Bultje 09:15 (1,15) bij vertrek; daarna daling naar ~0,35-0,5.
- Stand: auto 62 min (gem 0,74, aanwezig tot ~09:09), mid 176 min (gem 0,46, afwezig). Aanwezig 0,69 vs afwezig 0,50: bron, geen standeffect.
- Werking: mid precies 15 min na laatste aanwezigheid (09:09 → 09:24); herstarts 11:19 en 12:20 gaven geen auto-wissel (sensor kwam meteen terug op off). 5/5 traces zonder fout. Lokaal 41 mislukt op 88.842 (+2, herstarts), uitval 0, sturen 236/237, filter 0%. Apparaat-PM2.5 vast op 2.
- CO₂ gem 634, max 797, daalt naar 500; schimmelindicator 74 → 69; binnen 57% / 16,7 °C, buiten 99%: in orde.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=7), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5), H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1): geen nieuwe pieken, geen toets.

## 22-10 16:25 (ronde 17)
- PM2.5 12:20-16:20: gem 0,80, mediaan 0,68, P95 1,31, max 2,03 (13:05) (n=48); 0 uur > 15. Dag t/m nu 0,49; 7d (15-21/10) 8,3, mediaan dag 1,7 (nulmeting okt 2025 9,1).
- Geen piek > 25, geen kookmoment, ramen dicht. Bultje 12:45-13:15 tot 2,0 bij aanwezigheid (CO₂ 485 → 653).
- Stand: auto 149 min (gem 0,89), mid 91 min (gem 0,66). Aanwezig 0,94 vs afwezig 0,70: bron, geen standeffect.
- Werking: mid precies 15 min na vertrek (13:13 → 13:28). 22 min auto zonder aanwezigheid (14:30-14:37, 14:45-15:00) na herstarts 14:17/14:33 - bekende oorzaak (timer reset). 15:29:55 4 s mid terwijl net weg, direct weer auto. Traces 2/2 zonder fout (oudere verloren bij herstart). 6 HA-herstarts. Lokaal 42 mislukt op 90.002 (+1, herstart 12:35), uitval 0, sturen 244/245, filter 0%. Apparaat-PM2.5 vast op 2.
- CO₂ gem 551, max 780 (stijgt sinds 16:00); schimmelindicator 69 → 64; binnen 52% / 20,2 °C: in orde.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=7), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5), H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1): geen nieuwe pieken, geen toets.

## 22-10 20:25 (ronde 18)
- PM2.5 16:20-20:20: gem 1,02, mediaan 0,97, P95 1,40, max 1,64 (17:40) (n=48); 0 uur > 15. Dag t/m nu 0,60; 7d (15-21/10) 8,3, mediaan dag 1,7 (nulmeting okt 2025 9,1).
- Kookmoment: kookplaat 16:45-17:03, ramen dicht, auto, aanwezig - geen piek (1,0 → max 1,55 tijdens koken). Apparaat-PM2.5 1x 3 (16:53).
- Stand: hele periode auto (231 min, ~9 min unavailable), aanwezig; geen mid → geen standvergelijking.
- Werking: stand volgt aanwezigheid; 4/4 traces zonder fout (oudere verloren). 10 HA-herstarts. Lokaal 47 mislukt op 91.213 (+5, herstarts), uitval 0, sturen 244/245, filter 0%.
- CO₂ gem 1.010, 0,4 u > 1.200, max 1.354 (stijgend sinds 19:30, ramen dicht); schimmelindicator 64 → 75, binnen 54%. Avond ventileren.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=8: dicht 190/135/30/454/2,1/1,6; open 3,4) - weer gesteund. H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5), H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1): geen nieuwe piek, geen toets.

## 23-10 00:25 (ronde 19, eerste na middernacht)
- Dag 22-10: gem 0,65 µg/m³, mediaan 0,58, P95 1,25, max 2,0; 0 uur > 15. Schoonste dag sinds 11-10. 7d (16-22/10) gem 8,2, mediaan dag 1,7 (nulmeting okt 2025 9,1, stookseizoen 2025 vóór reiniger 16,0).
- PM2.5 20:20-00:20: gem 0,86, mediaan 0,93, P95 1,19, max 1,36 (n=48); geen piek > 25, geen kookmoment, ramen dicht.
- Stand: auto 176 min (gem 0,98, tv-avond), mid 64 min (gem 0,52, daling 0,9 → 0,2). Aanwezig 0,97 vs afwezig 0,63: bron, geen standeffect.
- Werking: mid precies 15 min na laatste aanwezigheid (23:01 → 23:16); 5/5 traces zonder fout. 0 HA-herstarts sinds 20:10. Lokaal 47 mislukt op 92.645 (geen nieuwe), uitval 0, sturen 245/246, filter 0%. Apparaat-PM2.5 vast op 2.
- CO₂ hele ronde > 1.200 (gem 1.555, max 1.731 om 21:35), ramen dicht; dag 22-10 4,1 u > 1.200. Schimmelindicator 75 → 79. Avond ventileren.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=8), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5), H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1): geen nieuwe piek, geen toets.

## 23-10 04:25 (ronde 20)
- PM2.5 00:20-04:20: gem 0,19, mediaan 0,19, P95 0,24, max 0,36 (02:15) (n=48); 0 uur > 15. Schoonste nacht sinds 11-10 (eerder 0,34/0,35).
- Hele periode mid (240 min, 10 s unavailable bij herstart 02:47), niemand aanwezig, tv uit, ramen dicht. Geen piek > 25, geen kookmoment.
- Werking: nachtvenster houdt mid vast; 5/5 traces zonder fout (failed_conditions = 00-06 geen wissels). 1 HA-herstart (02:47). Lokaal 48 mislukt op 94.064 (+1, herstart), uitval 0, sturen 245/246, filter 0%. Apparaat-PM2.5 vast op 2 (Ultimate 0,2).
- CO₂ daalt 1.365 → 963 (gem 1.134), 1,25 u > 1.200 (tot ~01:25), ramen dicht: avondlucht trekt traag weg. Schimmelindicator 79 → 77, binnen 62% / 17,3 °C, buiten 99%. Avond ventileren.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=8), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5), H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1): geen nieuwe piek, geen toets.

## 23-10 08:25 (ronde 21)
- PM2.5 04:20-08:20: gem 0,22, mediaan 0,22, P95 0,35, max 0,52 (06:25) (n=48); 0 uur > 15. Dag t/m nu ~0,2; 7d (16-22/10) 8,2, mediaan dag 1,7 (nulmeting okt 2025 9,1).
- Geen piek > 25, geen kookmoment, ramen dicht. Ochtendactiviteit 06:05-06:33: PM2.5 0,15 → 0,39, VOC-index 78 → 361; CO₂ bleef dalen.
- Stand: mid 180 min (gem 0,21), auto 57 min (gem 0,27). Aanwezig 0,25 vs afwezig 0,22: bron, geen standeffect.
- Werking: auto bij aanwezigheid (06:05, 08:01), mid precies 15 min na vertrek (06:32 → 06:47). Na herstart 06:08 1,5 min mid terwijl net aanwezig (06:10:51) - bekende timer-reset. 5/5 traces zonder fout. 2 HA-herstarts (06:08, 07:38). Lokaal 48 mislukt op 95.422 (geen nieuwe), uitval 0, sturen 250/251, filter 0%. Apparaat-PM2.5 vast op 2.
- CO₂ daalt 957 → 751 (gem 845), 0 u > 1.200. Schimmelindicator 77, binnen 64% / 17,0 °C, buiten 99%: vocht blijft hoog na de avond - kort luchten na douchen/koken.
- Nieuw (23-10, Ruud): automation.luchtreiniger_mid_bij_koken_auto_bij_vieze_lucht - alleen starttrace 07:39, nog geen kookmoment: ongetoetst.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=8), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); volgende kookpiek = eerste toets van mid bij koken. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

## 23-10 12:25 (ronde 22)
- PM2.5 08:20-12:20: gem 0,32, mediaan 0,26, P95 0,67, max 0,86 (08:55) (n=48); 0 uur > 15. Dag t/m nu ~0,24; 7d (16-22/10) 8,2, mediaan dag 1,7 (nulmeting okt 2025 9,1).
- Geen piek > 25, geen kookmoment, ramen dicht. Bultje 08:40-09:00 tot 0,86 bij vertrek; daarna ~0,2-0,3.
- Stand: auto 48 min (gem 0,51), mid 191 min (gem 0,27), 1 min unavailable. Aanwezig 0,43 vs afwezig 0,30: bron, geen standeffect.
- Werking: mid precies 15 min na laatste aanwezigheid (08:52 → 09:07); herstart 11:50 gaf geen auto-wissel. Traces 5/5 zonder fout. Lokaal 48 mislukt op 96.788 (geen nieuwe), uitval 0, sturen 251/252, filter 0%. Apparaat-PM2.5 vast op 2.
- Kookautomation: alleen starttraces (07:39, 11:52), nog geen kookmoment: ongetoetst.
- CO₂ gem 725, max 830, daalt naar 624; schimmelindicator 78 → 74, binnen 64% / 16,9 °C, buiten 99%: vocht blijft hoog; kort luchten bij droger weer.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=8), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); volgende kookpiek = eerste toets van mid bij koken. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

## 23-10 16:25 (ronde 23)
- PM2.5 12:20-16:20: gem 0,38, mediaan 0,38, P95 0,61, max 0,77 (16:15) (n=48); 0 uur > 15. Dag t/m nu ~0,28; 7d (16-22/10) 8,2, mediaan dag 1,7 (nulmeting okt 2025 9,1).
- Geen piek > 25, geen kookmoment, ramen dicht.
- Stand: auto 120 min (gem 0,39), mid 118 min (gem 0,38). Aanwezig 0,40 vs afwezig 0,38: geen verschil op dit lage niveau.
- Werking: mid precies 15 min na vertrek (12:35 → 12:50, 13:09 → 13:24). Nieuw effect van de 22-10-aanpassing: binnen 15 min na een herstart valt de marge weg, dus 4x mid al 1-3 min na vertrek (14:56, 15:00, 15:18, 15:30), steeds weer auto bij terugkomst - extra piepjes, geen PM-effect. 5/5 traces zonder fout. 2 HA-herstarts (14:54, 15:17). Lokaal 48 mislukt op 98.195 (geen nieuwe), uitval 0, sturen 264/265, filter 0%. Apparaat-PM2.5 vast op 2.
- Kookautomation: 4 starttraces, voorrang bleef uit, geen kookmoment: ongetoetst.
- CO₂ gem 609, max 736 (stijgt vanaf 16:00); schimmelindicator 74 → 67 → 70, binnen 63% / 17,1 °C, buiten 99%: in orde, vocht hoog.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=8), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); volgende kookpiek = eerste toets van mid bij koken. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

## 23-10 20:25 (ronde 24)
- PM2.5 16:20-20:20: gem 0,27, mediaan 0,21, P95 0,63, max 0,77 (16:20) (n=48); 0 uur > 15. Dag t/m nu ~0,28; 7d (16-22/10) 8,2, mediaan dag 1,7 (nulmeting okt 2025 9,1).
- Geen piek > 25, geen kookmoment (kookplaat/oven inactive), ramen dicht. Niemand thuis sinds 16:22, tv uit.
- Stand: auto 17 min (gem 0,64), mid 223 min (gem 0,24). Verschil = daling na vertrek, geen standeffect.
- Werking: mid precies 15 min na vertrek (16:22 → 16:37); 5/5 traces zonder fout. 0 HA-herstarts (uptime sinds 15:17). Lokaal 48 mislukt op 99.637 (geen nieuwe), uitval 0, sturen 265/266, filter 0%. Apparaat-PM2.5 vast op 2.
- Kookautomation: geen nieuwe traces, geen kookmoment: ongetoetst.
- CO₂ daalt 723 → 529 (gem 632), 0 u > 1.200. Vocht stijgt zonder bewoners 62,8 → 65,5% bij 16,7 °C, schimmelindicator 70 → 76, buiten 99%: koude ruimte, vocht komt niet van binnen - verwarmen helpt meer dan luchten bij dit buitenweer.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=8), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); volgende kookpiek = eerste toets van mid bij koken. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

laatste ronde: 23-10 20:25, gemeten t/m 20:20
