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

laatste ronde: 13-10 00:25, gemeten t/m 00:20
