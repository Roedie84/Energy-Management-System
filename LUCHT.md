# Luchtkwaliteit en luchtreiniger - meetlog

Maatstaf: UltimateSensor woonkamer (PM2.5 µg/m³). Getallen staan in LUCHT.csv.

## 11-10 (dag, samengevat; rondes 1-3)
- PM2.5 dag gem 1,08, max 13 (13:25, activiteit, auto), 0 uur > 15; geen piek > 25. Nulpunt nieuwe sturing 12:12.
- Terugblik: kookpiek 08-10 190 halveerde ~5 min (auto), 09-10 piek 30 zonder koken ~23 min; 10-10 koken met keukenraam open max 3,4.
- Stand volgt aanwezigheid; HA herstartte ~elke 10 min 12:10-18:09 (stand dan unavailable, apparaat draait door). Lokaal en sturen zonder fouten, filter 0%. Apparaat-PM2.5 vast op 2 onder ~5 µg/m³.
- CO₂ 4,2 u > 1.200 (max 1.741, avond, ramen dicht): ventileren.

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

## 24-10 00:25 (ronde 25, eerste na middernacht)
- Dag 23-10: gem 0,28 µg/m³, mediaan 0,24, P95 0,57, max 0,86; 0 uur > 15. Schoonste dag sinds 11-10 (22-10: 0,65). 7d (17-23/10) gem 8,0, mediaan dag 1,3 (nulmeting okt 2025 9,1, stookseizoen 2025 vóór reiniger 16,0).
- PM2.5 20:20-00:20: gem 0,30, mediaan 0,26, P95 0,51, max 0,84 (22:25, bij vertrek) (n=48); geen piek > 25, geen kookmoment, ramen dicht.
- Stand: auto 125 min (gem 0,31), mid 115 min (gem 0,29). Aanwezig 0,28 vs afwezig 0,31: op dit niveau geen verschil.
- Werking: auto bij aanwezigheid (20:39), mid precies 15 min na laatste aanwezigheid (22:29:45 → 22:44:45). 5/5 traces zonder fout. 0 HA-herstarts sinds 15:17. Lokaal 48 mislukt op 101.073 (geen nieuwe), uitval 0, sturen 267/268, filter 0%. Apparaat-PM2.5 vast op 2.
- Kookautomation: geen nieuwe traces, geen kookmoment: ongetoetst.
- CO₂ gem 574, max 790; dag 23-10 1,6 u > 1.200 (alleen staart 22-10 tot ~01:35). Schimmelindicator 73-76, binnen 58-65% / 17,0 °C, buiten 99%: vocht hoog door koude ruimte; verwarmen helpt meer dan luchten.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=8), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); volgende kookpiek = eerste toets van mid bij koken. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

## 24-10 04:25 (ronde 26)
- PM2.5 00:20-04:20: gem 0,22, mediaan 0,22, P95 0,34, max 0,49 (00:35) (n=48); 0 uur > 15. Daalt 0,25 → 0,10. Gelijk aan de schoonste nacht (23-10: 0,19).
- Hele periode mid (240 min, geen wissels), niemand aanwezig, tv uit, ramen dicht. Geen piek > 25, geen kookmoment.
- Werking: nachtvenster houdt mid vast; 5/5 traces zonder fout (failed_conditions = 00-06 geen wissels). 0 HA-herstarts sinds 23-10 15:17. Lokaal 48 mislukt op 102.510 (geen nieuwe), uitval 0, sturen 267/268, filter 0%. Apparaat-PM2.5 vast op 2 (Ultimate 0,1-0,5).
- Kookautomation: geen nieuwe traces, geen kookmoment: ongetoetst.
- CO₂ gem 445, max 493 (vorige nachten 565-1.134): avond zonder bezoek/tv-avond. Schimmelindicator 76-77, binnen 62% / 17,0 → 16,4 °C, buiten 99% / 9,8 °C: vocht hoog door koude ruimte; verwarmen helpt meer dan luchten.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=8), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); volgende kookpiek = eerste toets van mid bij koken. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

## 24-10 08:25 (ronde 27)
- PM2.5 04:20-08:20: gem 0,31, mediaan 0,20, P95 0,91, max 1,46 (08:15) (n=48); 0 uur > 15. Dag t/m nu ~0,27; 7d (17-23/10) 8,0, mediaan dag 1,3 (nulmeting okt 2025 9,1).
- Geen piek > 25, geen kookmoment (kookplaat/oven inactive), ramen dicht. Nachtminimum 0,05; ochtendactiviteit vanaf 06:59 (tv 07:47): PM2.5 0,1 → 1,35, CO₂ 455 → 730, VOC-index 40 → 168.
- Stand: mid 161 min (gem 0,15), auto 77 min (gem 0,60). Verschil = bron (mensen), geen standeffect.
- Werking: auto bij eerste aanwezigheid na 06:00 (06:59). Na HA-herstart 07:40 om 07:42:48 2 min mid terwijl net aanwezig: de start-trigger (60 s wachten) zag de mmWave 9 s op off en geen 15-min-marge (uptime < 15 min); weer auto 07:44:57. De 24-10-aanpassing dekt alleen de kwartiercontrole, niet de start-trigger. 5/5 traces zonder fout. Lokaal 48 mislukt op 103.932 (geen nieuwe), uitval 0, sturen 270/271, filter 0%. Apparaat-PM2.5 vast op 2.
- Kookautomation: starttrace 07:41 (failed_conditions), geen kookmoment: ongetoetst.
- CO₂ gem 521, max 730: in orde. Schimmelindicator 76 → 80, binnen 62 → 64,5% / 16,4 °C, buiten 99% / 9,6 °C: koude ruimte, vocht hoog; verwarmen helpt meer dan luchten.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=8), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); volgende kookpiek = eerste toets van mid bij koken. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

## 24-10 12:25 (ronde 28)
- PM2.5 08:20-12:20: gem 0,86, mediaan 0,60, P95 1,85, max 1,95 (08:30) (n=48); 0 uur > 15. Dag t/m nu ~0,46; 7d (17-23/10) 8,0, mediaan dag 1,3 (nulmeting okt 2025 9,1).
- Geen piek > 25, geen kookmoment (kookplaat/oven inactive), ramen dicht. Ochtendbult (tv aan tot 09:00) ~1,9; na vertrek daling 1,8 → 0,4-0,7.
- Stand: auto 59 min (gem 1,68), mid 180 min (gem 0,59), 1,3 min unavailable. Aanwezig 1,78 vs afwezig 0,65: bron (mensen), geen standeffect.
- Werking: mid precies 15 min na laatste aanwezigheid (09:03:50 → 09:18:50). HA-herstart 12:15: stand bleef mid, geen onterechte auto. 5/5 traces zonder fout. Lokaal 48 mislukt op 105.339 (geen nieuwe), uitval 0, sturen 271/272, filter 0%. Apparaat-PM2.5 vast op 2.
- Kookautomation: starttrace 12:16 (finished), geen kookmoment: ongetoetst.
- CO₂ daalt 724 → 511 (gem 590), 0 u > 1.200. Schimmelindicator 80 → 74, binnen 64,5 → 60,9% / 16,2 °C, buiten 99% / 10 °C: vocht daalt overdag; koude ruimte blijft het punt - verwarmen helpt meer dan luchten.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=8), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); volgende kookpiek = eerste toets van mid bij koken. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

## 24-10 16:25 (ronde 29)
- PM2.5 12:20-16:20: gem 1,28, mediaan 1,15, P95 2,09, max 2,37 (13:50) (n=48); 0 uur > 15. Dag t/m nu ~0,66; 7d (17-23/10) 8,0, mediaan dag 1,3 (nulmeting okt 2025 9,1).
- Geen piek > 25, geen kookmoment (kookplaat/oven inactive), ramen dicht. Middagbult met aanwezigheid/tv (13:30-14:27): 0,8 → 2,2, daarna terug naar ~0,8.
- Stand: auto 128 min (gem 1,57), mid 112 min (gem 0,99). Aanwezig 1,54 (n=19) vs afwezig 1,11 (n=29): bron (mensen), geen standeffect.
- Werking: 5 wissels naar mid, alle precies 15 min na laatste aanwezigheid (12:57 → 13:12, 14:27 → 14:42, 14:42 → 14:57, 15:18 → 15:33); 14:42 kort aanwezig → auto pas 14:45 via kwartiercontrole. 5/5 traces zonder fout, 0 HA-herstarts. Lokaal 48 mislukt op 106.779 (geen nieuwe), uitval 0, sturen 280/281 (9/9 nieuw bevestigd), filter 0%. Apparaat-PM2.5 2-4 bij Ultimate 1-2,4: volgt grof.
- Kookautomation: geen nieuwe traces, geen kookmoment: ongetoetst.
- CO₂ gem 579, max 789 (13:55), 0 u > 1.200. Schimmelindicator 74 → 64, binnen 60,9 → 55,9% / 16,2-17,2 °C, buiten 99 → 91% / 12,6 °C: droger buiten en iets warmer binnen geeft direct lager vocht - bevestigt: verwarmen/luchten bij droger weer.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=8), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); volgende kookpiek = eerste toets van mid bij koken. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

## 24-10 20:25 (ronde 30)
- PM2.5 16:20-20:20: gem 0,67, mediaan 0,54, P95 1,26, max 1,62 (16:30) (n=48); 0 uur > 15. Dag t/m nu ~0,67; 7d (17-23/10) 8,0, mediaan dag 1,3 (nulmeting okt 2025 9,1).
- Geen piek > 25, geen kookmoment (kookplaat/oven inactive), ramen dicht, tv uit. Bultjes ~1,2-1,4 bij aanwezigheid (16:30, 17:40-18:00), daarna terug naar 0,3-0,5.
- Stand: auto 112 min (gem 0,79), mid 128 min (gem 0,57). Aanwezig 0,62 (n=17) vs afwezig 0,70 (n=31): geen verschil op dit niveau.
- Werking: mid precies 15 min na laatste aanwezigheid (16:35:27 → 16:50:27, 17:59:36 → 18:14:36); auto direct bij terugkomst (17:34:48, 19:37:47). 5/5 traces zonder fout, 0 HA-herstarts. Lokaal 48 mislukt op 108.222 (geen nieuwe), uitval 0, sturen 284/285, filter 0%. Apparaat-PM2.5 vast op 2.
- Kookautomation: geen nieuwe traces, geen kookmoment: ongetoetst.
- CO₂ gem 589, max 641, 0 u > 1.200. Verwarming aan vanaf ~19:37: binnen 16,4 → 20,5 °C, vocht 58 → 47,8%, schimmelindicator 68 → 64 (buiten 99% / 11 °C). Bevestigt: verwarmen lost het vocht op, niet luchten.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=8), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); volgende kookpiek = eerste toets van mid bij koken. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

## 25-10 00:25 (ronde 31, eerste na middernacht)
- Dag 24-10: gem 0,65 µg/m³, max 2,37 (13:50); 0 uur > 15. 7d (18-24/10) gem 3,7, mediaan dag 1,3 (nulmeting okt 2025 9,1, stookseizoen 2025 vóór reiniger 16,0). De dagen met de pieken van 17/18-10 vallen uit het venster.
- PM2.5 20:20-00:20: gem 0,55, mediaan 0,56, P95 0,75, max 0,98 (21:55) (n=48); geen piek > 25, geen kookmoment (kookplaat/oven inactive), ramen dicht.
- Stand: hele periode auto (240 min). Aanwezig (mmWave) 0,54 (n=21) vs alleen tv aan 0,55 (n=27): geen verschil.
- Werking: tv staat aan sinds 21:53, mmWave sinds 22:52 off; daardoor bleef auto en zet het nachtvenster (00:00) auto vast - als de tv echt uit is maar 'on' meldt, draait hij de hele nacht auto (n=1, volgende ronde toetsen). 5/5 traces zonder fout (00:00/00:15 failed_conditions = nachtvenster). 0 HA-herstarts. Lokaal 48 mislukt op 109.659 (geen nieuwe), uitval 0, sturen 284/285 (geen nieuwe opdrachten), filter 0%. Apparaat-PM2.5 2-3 bij Ultimate 0,4-1,0.
- Kookautomation: geen nieuwe traces, geen kookmoment: ongetoetst.
- CO₂ gem ~680, max 916 (22-23 u), 0 u > 1.200. Verwarming uit ~22:00: binnen 21,4 → 17,6 °C, vocht 46 → 59,8%, schimmelindicator 63 → 77 (buiten 99% / 9,7 °C). Zelfde patroon als vorige avonden: afkoelen geeft het vocht, niet de luchtreiniger.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=8), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); volgende kookpiek = eerste toets van mid bij koken. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

## 25-10 04:25 (ronde 32)
- PM2.5 00:20 CEST-04:20 CET (5 u, wintertijd): gem 0,18, mediaan 0,15, P95 0,38, max 0,58 (00:55) (n=60); 0 uur > 15. Daalt 0,38 → 0,04. Schoonste nacht tot nu (eerder 0,19-0,35).
- Geen piek > 25, geen kookmoment (kookplaat/oven inactive), ramen dicht.
- Stand: hele periode auto (300 min). Tv was echt aan tot 01:39 (mmWave kort aan bij uitzetten); daarna niemand, maar het nachtvenster (00-06) houdt auto vast - vermoeden uit ronde 31 bevestigd (n=1). Tv aan 0,33 vs daarna 0,13; nacht in auto 0,18 vs mid-nachten 0,19-0,22: auto 's nachts geeft geen meetbare winst.
- Werking: 5/5 traces zonder fout (failed_conditions = nachtvenster). 0 HA-herstarts. Lokaal 48 mislukt op 111.455 (geen nieuwe), uitval 0, sturen 284/285 (geen nieuwe opdrachten), filter 0%. Apparaat-PM2.5 vast op 2.
- Kookautomation: geen nieuwe traces, geen kookmoment: ongetoetst.
- CO₂ daalt 745 → 438 (gem 574), 0 u > 1.200. Schimmelindicator 77 → 75, binnen 60 → 64,4% bij 17,4 → 16,6 °C, buiten 99% / 11,9 °C: afkoelen geeft het vocht.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=8), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); volgende kookpiek = eerste toets van mid bij koken. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

## 25-10 08:25 (ronde 33)
- PM2.5 04:20-08:20: gem 0,50, mediaan 0,53, P95 0,93, max 1,32 (08:15) (n=48); 0 uur > 15. Nachtminimum 0,03 (05:00); vanaf 05:30 stijging naar ~0,5 zonder aanwezigheid of open raam (buitenlucht/ochtend), daarna ochtendactiviteit tot ~1,0.
- Geen piek > 25, geen kookmoment (kookplaat/oven inactive), ramen dicht.
- Stand: auto 144 min (nacht 04:20-06:00 gem 0,27), mid 95 min, 1,3 min unavailable. Aanwezig 0,66 (n=6) vs afwezig 0,48 (n=42): bron (mensen), geen standeffect.
- Werking: HA-herstart 05:59:40; stand na herstart 06:00:55 auto terwijl niemand aanwezig, 06:02 mid - tweede keer een onnodige wissel na herstart (n=2). Daarna mid precies 15 min na laatste aanwezigheid (06:36:36 → 06:51:36, 08:06:17 → 08:21:17), auto direct bij terugkomst (06:29, 07:58). 5/5 traces zonder fout. Lokaal 48 mislukt op 112.874 (geen nieuwe), uitval 0, sturen 289/290 (5/5 nieuw bevestigd), filter 0%. Apparaat-PM2.5 2-5 bij Ultimate 0,5-1,3: volgt grof.
- Kookautomation: starttrace 06:01 (finished), geen kookmoment: ongetoetst.
- CO₂ gem 477, max 526, 0 u > 1.200. Schimmelindicator 75 → 78 → 76, binnen 64,6 → 62,6% bij 16,5 °C, buiten 99% / 10 °C: koude ruimte, vocht hoog; verwarmen helpt meer dan luchten.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=8), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); volgende kookpiek = eerste toets van mid bij koken. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

## 25-10 12:25 (ronde 34)
- PM2.5 08:20-12:20: gem 1,89, mediaan 2,05, P95 2,52, max 3,08 (11:15) (n=48); 0 uur > 15. Dag t/m nu ~0,8; 7d (18-24/10) 3,7, mediaan dag 1,3 (nulmeting okt 2025 9,1).
- Geen piek > 25, ramen dicht. Stijging 1,0 → 2,5 vanaf aanwezigheid (08:52) en verwarming aan (~09:00, 16,4 → 20,6 °C).
- KOOKMOMENT, eerste toets kookautomation: kookplaat 11:27-11:40, ramen dicht, aanwezig. Automation zette voorrang aan en stand mid (11:27:17), terug naar auto 11:41:43. PM2.5 tijdens koken max 2,6 (vooraf 2,35): geen piek, dus halveringstijd in mid nog niet te meten.
- Stand: auto 189 min (gem 1,98), mid 46 min (gem 1,49; afwezig 08:21-08:52 en koken). Aanwezig 2,02 (n=41) vs afwezig 1,09 (n=7): bron (mensen/verwarming), geen standeffect.
- Werking: auto direct bij aanwezigheid (08:52). 4 HA-herstarts (09:29, 09:55, 10:08, 10:53), stand na elke herstart correct auto, geen onnodige wissel. Traces 5/5 + kook 4/4 zonder fout. Lokaal 48 mislukt op 114.168 (geen nieuwe), uitval 0, sturen 292/293 (3/3 nieuw), filter 0%. Apparaat-PM2.5 3-7 bij Ultimate 1-3: ~2x te hoog, volgt grof.
- CO₂ gem 682, max 802, 0 u > 1.200. Verwarming: vocht 62,5 → 50,8% (nu 54), schimmelindicator 76 → 66 (nu 67), buiten 99%: bevestigt weer, verwarmen lost het vocht op.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=9: dicht 190/135/30/454/2,1/1,6/2,6; open 3,4) - weer gesteund. H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); mid bij koken 1x zonder piek, halvering ongetoetst. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1), geen toets.

## 25-10 16:25 (ronde 35)
- PM2.5 12:20-16:20: gem 2,48, mediaan 2,52, P95 3,0, max 3,51 (13:25) (n=48); 0 uur > 15. Dag t/m nu ~1,2; 7d (18-24/10) 3,7, mediaan dag 1,3 (nulmeting okt 2025 9,1).
- Geen piek > 25, geen kookmoment (kookplaat/oven inactive), ramen dicht. Vlak middagniveau 2,2-3,2 met aanwezigheid en verwarming aan (~20,5 °C); daalt pas na 16:00 naar ~1,6.
- Stand: hele periode auto (238 min, 2,4 min unavailable bij herstarts). Afwezigheid steeds < 15 min (15:22-15:36 = 14 min), dus geen mid. Aanwezig 2,54 (n=42) vs afwezig 2,06 (n=6): bron (mensen), geen standeffect.
- Werking: 2 HA-herstarts (15:53, 16:08), stand na herstart direct auto bij aanwezigheid (correct). Traces 5/5 + kook 2/2 zonder fout. Lokaal 48 mislukt op 115.521 (geen nieuwe), uitval 0, sturen 292/293 (geen nieuwe opdrachten), filter 0%. Apparaat-PM2.5 3-8 bij Ultimate 1,4-3,5: ~2x te hoog, volgt grof.
- CO₂ daalt 767 → ~510 (gem 547), 0 u > 1.200. Schimmelindicator 65-69, vocht 49,8-53% bij ~20,5 °C: in orde zolang de verwarming aan is.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=9), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); mid bij koken 1x zonder piek, halvering ongetoetst. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

## 25-10 20:25 (ronde 36)
- PM2.5 16:20-20:20: gem 1,40, mediaan 1,40, P95 1,74, max 2,07 (18:15) (n=48); 0 uur > 15. Dag t/m nu 1,22; 7d (18-24/10) 3,7, mediaan dag 1,3 (nulmeting okt 2025 9,1).
- Geen piek > 25, geen kookmoment (kookplaat/oven inactive), ramen dicht. Vlak 1,1-1,8.
- Stand: auto 196 min (gem 1,42), mid 42 min (gem 1,30), 2,3 min unavailable. Aanwezig 1,43 (n=33) vs afwezig 1,34 (n=15): geen verschil.
- Werking: mid 15 min na laatste aanwezigheid (16:11 → 16:26, 16:52 → 17:07); auto direct bij terugkomst 16:36 en 17:50, maar 17:08:32 aanwezig → auto pas 17:15 via kwartiercontrole (2e keer, n=2, eerder 14:42). Na herstart 17:24 mid al na 5 min afwezigheid. 5/5 traces zonder fout. Lokaal 48 mislukt op 116.913 (geen nieuwe), uitval 0, sturen 298/299 (6/6 nieuw), filter 0%. Apparaat-PM2.5 2-5 bij Ultimate 1-2: ~2x te hoog.
- CO₂ stijgt 500 → 1.239 (19:40) vanaf aanwezigheid 17:50 met ramen dicht, gem 772, 5 min > 1.200: ventileren (raam op kier/rooster), niet de luchtreiniger. Schimmelindicator 64-69, vocht 47-54% bij ~21 °C: in orde.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=9), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); mid bij koken 1x zonder piek, halvering ongetoetst. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

## 26-10 00:25 (ronde 37, eerste na middernacht)
- Dag 25-10: gem 1,21, max 3,5 (13:25), 0 uur > 15, geen piek > 25, geen kookpiek (kookmoment 11:27 zonder piek). 7d (19-25/10) 1,76, mediaan dag 1,2 (nulmeting okt 2025 9,1; stookseizoen vóór reiniger 16,0).
- PM2.5 20:20-00:20: gem 1,05, mediaan 1,11, P95 1,57, max 2,2 (20:35) (n=48); 0 uur > 15. Geen kookmoment, ramen dicht.
- Stand: auto 167 min (gem 1,23), mid 73 min (gem 0,61, nacht). Aanwezig 1,24 (n=31) vs afwezig 0,71 (n=17): bron (avond/mensen), geen standeffect.
- Werking: tv uit 22:50, laatste aanwezigheid 22:52 → mid 23:07 (15 min), correct. Kwartiercontroles 5/5 zonder fout; geen HA-herstart. Lokaal 48 mislukt op 118.355 (geen nieuwe), uitval 0, sturen 299/300 (1/1 nieuw), filter 0%. Apparaat-PM2.5 2-4 bij Ultimate 0,3-2: vast op 2, onbruikbaar.
- CO₂ 20:20-22:15 vlak 1.150-1.200 (max 1.215, 4 blokken even > 1.200) bij aanwezigheid en ramen dicht, daarna dalend naar 720; gem 1.046. Dag 25-10 gem 679, max 1.239. Avond ventileren. Vocht 48-52%, schimmelindicator 66-68: in orde.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=9), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); mid bij koken 1x zonder piek, halvering ongetoetst. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

## 26-10 04:25 (ronde 38)
- PM2.5 00:20-04:20: gem 0,41, mediaan 0,41, P95 0,56, max 0,81 (03:25) (n=48); 0 uur > 15. Vlak 0,2-0,7, iets hoger dan de schoonste nachten (0,18-0,22).
- Geen piek > 25, geen kookmoment (kookplaat/oven inactive), ramen dicht, niemand aanwezig, tv uit.
- Stand: hele periode mid (240 min, geen wissels); geen standvergelijking.
- Werking: nachtvenster houdt mid vast; 5/5 traces zonder fout (failed_conditions = 00-06 geen wissels). 0 HA-herstarts. Lokaal 48 mislukt op 119.792 (geen nieuwe), uitval 0, sturen 299/300 (geen nieuwe opdrachten), filter 0%. Apparaat-PM2.5 vast op 2.
- Kookautomation: geen nieuwe traces, geen kookmoment: ongetoetst.
- CO₂ daalt 709 → 563 (gem 613), 0 u > 1.200. Binnen 18,1 → 17,2 °C, vocht 51,8 → 53,6%, schimmelindicator 67 → 70, buiten 99% / 8,9 °C: afkoelen geeft het vocht, zelfde patroon.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=9), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); mid bij koken 1x zonder piek, halvering ongetoetst. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

## 26-10 08:25 (ronde 39)
- PM2.5 04:20-08:20: gem 0,97, mediaan 0,81, P95 2,20, max 2,65 (07:55) (n=48); 0 uur > 15. Dag t/m nu ~0,7; 7d (19-25/10) 1,76, mediaan dag 1,2 (nulmeting okt 2025 9,1).
- Geen piek > 25, geen kookmoment (kookplaat/oven inactive), ramen dicht, tv uit. Ochtendactiviteit vanaf 05:58: PM2.5 0,4 → 2,4, CO₂ 550 → 802, VOC-index 100 → 167.
- Stand: auto 134 min (gem 1,35), mid 104 min (gem 0,45), 2,5 min unavailable. Aanwezig 1,32 (n=29) vs afwezig 0,45 (n=19): bron (mensen), geen standeffect.
- Werking: auto bij eerste aanwezigheid na 06:00 (06:00:01), mid precies 15 min na laatste aanwezigheid (06:28:53 → 06:43:54, 08:05:34 → 08:20:34). Na HA-herstart 07:11 om 07:13:25 mid 24 s na off (geen 15-min-marge na herstart, bekend), 07:15 weer auto. 5/5 traces zonder fout. 2 HA-herstarts (07:11, 07:46). Lokaal 48 mislukt op 121.185 (geen nieuwe), uitval 0, sturen 305/306 (6/6 nieuw), filter 0%. Apparaat-PM2.5 2-6 bij Ultimate 0,3-2,6: ~2x te hoog.
- Kookautomation: 2 starttraces (herstarts), geen kookmoment: ongetoetst.
- CO₂ gem 609, max 802, 0 u > 1.200. Schimmelindicator 69 → 74 → 73, binnen 53,7 → 56% bij 17,2 → 16,9 °C, buiten 99% / 8,4 °C: koude ruimte, vocht hoog; verwarmen helpt meer dan luchten.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=9), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); mid bij koken 1x zonder piek, halvering ongetoetst. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

## 26-10 12:25 (ronde 40)
- PM2.5 08:20-12:20: gem 1,02, mediaan 0,97, P95 1,47, max 2,01 (08:20) (n=48); 0 uur > 15. Dag t/m nu ~0,8; 7d (19-25/10) 1,76, mediaan dag 1,2 (nulmeting okt 2025 9,1).
- Geen piek > 25, geen kookmoment (kookplaat/oven inactive), ramen dicht, tv uit. Vlak 0,7-1,2 na daling vanaf ochtendactiviteit (1,9 → 1,0 in ~30 min, mid).
- Stand: hele periode mid (238 min; 0,6 min auto t/m 08:20:34, 1,1 min unavailable bij herstart). Niemand aanwezig (n=48): geen standvergelijking.
- Werking: mid 15 min na laatste aanwezigheid (08:05:34 → 08:20:34), na HA-herstart 10:27 direct weer mid (correct, niemand aanwezig). 5/5 traces zonder fout. Lokaal 48 mislukt op 122.627 (geen nieuwe), uitval 0, sturen 305/306 (geen nieuwe opdrachten), filter 0%. Apparaat-PM2.5 vast op 2 (2-5) bij Ultimate 0,7-2,0.
- Kookautomation: 1 starttrace (herstart 10:28), geen kookmoment: ongetoetst.
- CO₂ daalt 738 → 543 (gem 602), 0 u > 1.200. Binnen 16,7 °C zonder verwarming, vocht 55,5 → 57%, schimmelindicator 72 → 65 (buiten 8,4 → 12,5 °C, 99%): koude ruimte, vocht hoog; verwarmen helpt meer dan luchten.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=9), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); mid bij koken 1x zonder piek, halvering ongetoetst. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

## 26-10 16:25 (ronde 41)
- PM2.5 12:20-16:20: gem 1,87, mediaan 1,93, P95 3,06, max 5,03 (16:00) (n=48); 0 uur > 15. Dag t/m nu ~1,1; 7d (19-25/10) 1,76, mediaan dag 1,2 (nulmeting okt 2025 9,1).
- Geen piek > 25, geen kookmoment (kookplaat/oven inactive), ramen dicht, tv uit. Stijging 0,8 → ~2 vanaf aanwezigheid (12:52) en verwarming aan (~13:20, 16,7 → 20,8 °C); bultje 5,0 om 16:00 zonder kookmoment.
- Stand: auto 201 min (gem 2,03), mid 36 min (gem 0,84), 3,6 min unavailable. Aanwezig 2,02 (n=42) vs afwezig 0,84 (n=6): bron (mensen/verwarming), geen standeffect.
- Werking: auto direct bij aanwezigheid (12:52:30). 3 HA-herstarts (13:31, 14:59, 15:13). Na herstart 14:59: mid 15:03:30, 2 min na off terwijl net aanwezig, 15:06 weer auto - derde keer (n=3) dat de 15-min-marge na herstart ontbreekt. 5/5 traces zonder fout. Lokaal 48 mislukt op 123.969 (geen nieuwe), uitval 0, sturen 308/309 (3/3 nieuw), filter 0%. Apparaat-PM2.5 3-7 bij Ultimate 1,5-3: ~2x te hoog, volgt grof.
- Kookautomation: 2 starttraces (herstarts), geen kookmoment: ongetoetst.
- CO₂ stijgt 540 → 843 (gem 643), 0 u > 1.200. Verwarming aan: vocht 57,6 → 48,2% (nu 50), schimmelindicator 65 → 61 (nu 65), buiten 99% / 12,5 °C: bevestigt weer, verwarmen lost het vocht op.
- Hypotheses: H1 ramen dicht nodig, niet voldoende voor kookpiek (n=9), H2 auto halveert kookpiek ~5-24 min, low ~27 (n=5); mid bij koken 1x zonder piek, halvering ongetoetst. H3 aanhoudende bron/bezoek: auto houdt het niet bij (n=1). Geen nieuwe piek, geen toets.

laatste ronde: 26-10 16:25, gemeten t/m 16:20
