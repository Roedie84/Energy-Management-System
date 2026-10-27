# Baseline Energy Management System

| KPI | referentie | periode / n | vastgesteld |
|---|---|---|---|
| PV-voorspelling MAE (dag) | 10,5 % (30 d) · 5,2 % (7 d) | 06-09..06-10, n=31 | 07-10 23:15 |
| PV-voorspelling bias | −4,4 % (30 d) · −1,7 % (7 d) | idem | 07-10 23:15 |
| Tekortnachten | 4 / 7 (5,68 kWh) | 30-09..06-10 | 07-10 23:15 |
| Reserve te hoog | 0 / 7 | 30-09..06-10 | 07-10 23:15 |
| Regelverschuiving P1 (bewust, in reserve) | 50 W · ~60 Wh/u tijdens ontlading | 28-09..07-10, n=50 u | 07-10 23:15 (duiding gecorrigeerd 23:45) |
| Gem. vermogen ontlaadvenster | 306 W | 7 nachten | 07-10 23:15 |
| PV-opbrengst | 4,3-12,8 kWh/dag (mediaan 11,2) | 28-09..06-10 | 07-10 23:15 |
| Netimport | 0,6-5,5 kWh/dag (mediaan 2,2) | 28-09..06-10 | 07-10 23:15 |
| MC-tekortkans 22:00, Brier | 0,038 | 30-09..07-10, n=8 | 07-10 23:45 |
| Piekverkoop onder reserve | 0× sinds v5.28.4 | 04-10 10:32..07-10 | 07-10 23:45 |
| PV uurratio werkelijk/Solcast | middag 0,94 · 06-07 en 15-17 UTC 0,52-0,69 | 7 d profiel | 07-10 23:45 |
| PV-voorspelling MAE (dag) | 10,8 % (30 d) · 5,9 % (7 d) | 08-09..07-10 | 08-10 03:40 |
| PV-bias bewolkt >70% / ≤70% | −7,2 % / −4,6 % (MAE 9,5 / 9,5) | 30 d, n=15/13 | 08-10 03:40 |
| Verbruik uurprofiel MAE | 0,13 kWh/u | 7 d leave-one-out | 08-10 03:40 |
| Verbruik nacht 22-09 bias | −0,08 kWh (−3%) · MAE 0,13 | 7 d | 08-10 03:40 |
| Verbruik dagtotaal bias | −0,49 kWh/dag · MAE 0,84 | 7 d | 08-10 03:40 |
| Tekortnachten | 3 / 7 (4,24 kWh) | 01-10..07-10 | 08-10 03:40 |
| Verkoop onder reserve | 0 dagen | 07-10 | 08-10 03:40 |
| Achteraf (uur, 4,22 ct): werkelijk / optimum t.o.v. zonder accu | +0,29 / −0,55 €/dag | 4 dagen | 08-10 03:40 |
| Dagrapport-dekking meetlog | 80,6 % | 07-10 | 08-10 03:40 |
| Nacht-export 00-07 (regelverschuiving −50 W) | 0,43 kWh | nacht 07→08, n=7 u | 08-10 07:40 |
| Nachtverbruik tegen wandeling (22:00→07:40) | +0,29 kWh (+10 %) | 1 nacht | 08-10 07:40 |
| Lange-horizon-extra in de reserve | 1,59-2,11 kWh | 07/08-10 | 08-10 07:40 |
| MC-stand tot het blok na v5.47 (overdag) | 0 % (was 96-100 %) | 08-10 11:41 | 08-10 11:45 |
| Meetlog kwartierdekking na L-EMS-003 | 100 % | 08-10 11:15 | 08-10 11:45 |
| Accurendement AC→AC (Zendure-tellers) | 81,9 % (30 d) · 84,1 % (7 d); geleerd 84,2 % | 08-09..07-10, 215,6 kWh in | 08-10 15:40 |
| MC tot blok overdag buiten pieken | 0-1 % · na huishoudpieken 21-92 % (20 min/dag) | 08-10 07:00-19:40 | 08-10 19:40 |
| PV-voorspelling MAE (dag, day-ahead Solcast) | 9,5 % (30 d) · 5,5 % (14 d) · 6,0 % (7 d); bias −6,2 / −2,7 / −2,5 | 09-09..08-10 | 09-10 03:40 |
| Verbruik uurprofiel MAE | 0,105-0,155 kWh/u | 07-10, 08-10 | 09-10 03:40 |
| Nachtverbruik 22-09 | 2,48 kWh (2,40-2,66) | 7 nachten t/m 07→08 | 09-10 03:40 |
| Nachtimport door Quooker-opwarmen | ~12 Wh/u (~6 Wh × 2/u) | 08-10, 09-10 00-03 | 09-10 03:40 |
| Export tijdens ontlading na L-EMS-005 | 22-27 Wh/u (was 59-65) | 08→09 00-03 u | 09-10 03:40 |
| Achteraf (uur, 4,22 ct): werkelijk / optimum t.o.v. zonder accu | +0,24 / −0,56 €/dag | 5 dagen | 09-10 03:40 |
| Meetlog kwartieren gemeten | 74/96 (20 herstarts) · 76/96 (15) | 08-10, 07-10 | 09-10 03:40 |
| Nacht-export 00-07 na L-EMS-005 | 0,163 kWh (−62%) | nacht 08→09 | 09-10 07:40 |
| PV-voorspelling MAE (dag, day-ahead) | 10,7 % (30 d) · 8,1 % (14 d) · 12,1 % (7 d); bias −7,4 / −5,4 / −8,5 | 10-09..09-10 | 10-10 03:40 |
| Meetlog kwartieren gemeten na L-EMS-009 | 93/96 (22 herstarts, 20 over herstart) · pv_onbekend 0 | 09-10 | 10-10 03:40 |
| SoC-sprong vlak boven leeg | 2× in 10 d (4-5 pp ≈ 0,35 kWh) | 30-09..09-10 | 10-10 03:40 |
| MC 22:00 Brier (tot blok) | 0 (n=1) | avond 08-10 | 10-10 03:40 |
| PV-voorspelling MAE (dag, day-ahead tracker) | 10,5 % (30 d) · 8,2 % (14 d) · 12,4 % (7 d); bias −8,0 / −6,2 / −8,9 | 11-09..10-10 | 11-10 03:40 |
| Nabeschouwing: accu leverde / had kunnen (realisatie) | € 3,10 / € 6,51 (48 %) 7 d · € 3,77 / € 11,60 (32 %) 14 d | 27-09..10-10 | 11-10 03:40 |
| Nabeschouwing: gemist door reserve / voorspelling | € 0,48 / € 2,91 (7 d) | 04..10-10 | 11-10 03:40 |
| Besparing t.o.v. zonder accu-sturing (sensor, per dag) | −0,26..+1,06 €; 10-10 € 1,06 | 05..10-10 | 11-10 03:40 |
| Export op een minder duur kwartier dan de dagtop | 10,95 kWh, ~€ 0,41 in 13 d (momentopname) | 28-09..10-10 | 11-10 03:40 |
| Dagrapport-dekking meetlog | 99,2 % (95/96, 12 over herstart) | 10-10 | 11-10 03:40 |
| MC 22:00 Brier (tot blok) | 0 (n=2: 0 %/geen tekort, 100 %/tekort) | avonden 08-10, 09-10 | 11-10 03:40 |
| Tekortnachten | 2 / 7 (04-10 onbekend, 10-10 economisch 2,36 kWh) | 04..10-10 | 11-10 03:40 |
| PV-voorspelling MAE (dag, day-ahead tracker) | 10,7 % (30 d) · 8,8 % (14 d) · 14,7 % (7 d); bias −8,2 / −6,9 / −11,6 | 12-09..11-10 | 12-10 03:40 |
| MC 22:00 Brier (tot blok) | 0 (n=3) | avonden 08..10-10 | 12-10 03:40 |
| Tekortnachten | 1 / 7 (10-10 economisch 2,36 kWh) | 05..11-10 | 12-10 03:40 |
| Besparing t.o.v. zonder accu-sturing (sensor, per dag) | € 1,09 (11-10) · € 1,06 (10-10) | 10..11-10 | 12-10 03:40 |
| HA-herstarts per dag | 40 (11-10, supervisor) · 12 (10-10) | 10..11-10 | 12-10 03:40 |
| Spaarplan vs verkooptoets tot blok (vóór v5.87) | 8,1 vs ≤ 5,5 kWh, werkelijk 4,58 | avond 10-10 | 12-10 03:40 |
| PV-voorspelling MAE (dag, day-ahead tracker) | 11,3 % (30 d) · 17,3 % (14 d) · 17,4 % (7 d); bias −8,7 / −17,3 / −17,4; 14/14 dagen negatief | 21-09..20-10 | 21-10 19:40 |
| Nabeschouwing: accu leverde / had kunnen (realisatie) | € 6,98 / € 7,69 (91 %) 7 d; gemist voorspelling € 1,11, reserve € 0,40 | 14..20-10 | 21-10 19:40 |
| Ochtendpiek vastgehouden (nabeschouwing per dagdeel) | 1,2-2,3 kWh op 4/7 dagen; netto nacht+ochtend ~€ 1,3/week | 14..20-10 | 21-10 19:40 |
| Tekortnachten | 0 / 7 (20-10 0,05 kWh) | 14..20-10 | 21-10 19:40 |
| MC 22:00 Brier (tot blok) | 0,144 (n=7; →20-10 100 % zonder tekort) | 13..19-10 | 21-10 19:40 |
| Planvolging volgens plan | 60,2 % (7 d, 47,9-72,6) | 14..20-10 | 21-10 19:40 |
| Netimport / PV per dag | 6,24 / 7,33 kWh (7 d gem.) | 14..20-10 | 21-10 19:40 |
| Huisverbruik per dag | 9,6 kWh (7,9-10,7) | 14..20-10 | 21-10 19:40 |
| Accucapaciteit nominaal | 11,52 kWh (4 modules sinds 14-10) | v5.97.1 | 21-10 19:40 |
| PV-voorspelling MAE (dag, day-ahead tracker) | 12,1 % (30 d) · 19,3 % (14 d) · 21,3 % (7 d); bias −10,2 / −19,3 / −21,3; 15 dagen op rij negatief | 22-09..21-10 | 22-10 03:40 |
| Nabeschouwing: accu leverde / had kunnen (realisatie) | € 7,15 / € 8,50 (84 %) 7 d | 15..21-10 | 22-10 03:40 |
| Digital twin accu-inhoud 6 u vooruit, MAE | 1,00 kWh; laden +1,34, nacht −0,73, avond −1,21 (bias) | 20..22-10, n=60 | 22-10 15:40 |
| PV-voorspelling MAE (dag, day-ahead tracker) | 12,1 % (30 d) · 19,4 % (14 d) · 20,5 % (7 d); bias −10,7 / −19,4 / −20,5; 16 dagen op rij negatief | 23-09..22-10 | 23-10 03:40 |
| Nabeschouwing: accu leverde / had kunnen (realisatie) | € 6,54 / € 7,55 (86,6 %) 7 d; avondpiek −€ 1,92/week (6/7 dagen te veel ontladen) | 16..22-10 | 23-10 03:40 |
| Planvolging volgens plan | 62,3 % (7 d, 52,7-72,6) | 16..22-10 | 23-10 03:40 |
| MC 22:00 Brier (tot blok) | 0,286 (n=7; 2× 100 % zonder tekortnacht) | 16..22-10 | 23-10 03:40 |
| Reservesprong door live verbruikscorrectie | ~1,5 kWh per wissel (= begrenzing); 17 op 22-10 avond, 3 op de reserve zelf na 00:00 | 22..23-10 | 23-10 03:40 |
| PV-voorspelling MAE (dag, day-ahead tracker) | 12,4 % (30 d) · 16,6 % (14 d) · 21,5 % (7 d); bias −10,5 / −15,4 / −18,9; 23-10 eerste dag boven verwachting (+9 %) | 24-09..23-10 | 24-10 03:40 |
| Nabeschouwing: accu leverde / had kunnen (realisatie) | € 5,39 / € 6,58 (81,9 %) 7 d; avondpiek −€ 1,92, ochtendpiek vastgehouden +€ 2,83 | 17..23-10 | 24-10 03:40 |
| Planvolging volgens plan | 61,7 % (7 d); "sturing" 0 op 23-10 | 17..23-10 | 24-10 03:40 |
| MC 22:00 Brier (tot blok) | 0,333 (n=6) | 17..22-10 | 24-10 03:40 |
| Digital twin accu-inhoud 6 u vooruit, MAE | 1,20 kWh (n=60) | 21..24-10 | 24-10 03:40 |

| PV-voorspelling MAE (dag, day-ahead tracker) | 12,1 % (30 d) · 16,5 % (14 d) · 16,4 % (7 d); bias −10,2 / −15,2 / −13,8 | 25-09..24-10 | 25-10 03:40 |
| Nabeschouwing: accu leverde / had kunnen (realisatie) | € 4,96 / € 6,46 (76,8 %) 7 d; avondpiek −€ 1,24, ochtendpiek +€ 2,94 | 18..24-10 | 25-10 03:40 |
| Planvolging volgens plan | 59,9 % (7 d); "sturing" 0 op 23- en 24-10 | 18..24-10 | 25-10 03:40 |
| MC 22:00 Brier (tot blok) | 0,500 (n=6; 3× 100 % zonder tekortnacht) | 18..24-10 | 25-10 03:40 |
| Digital twin accu-inhoud 6 u vooruit, MAE | 1,51 kWh | 24-10 | 25-10 03:40 |
| PV-voorspelling MAE (dag, day-ahead tracker) | 12,6 % (30 d) · 17,1 % (14 d) · 14,5 % (7 d); bias −10,7 / −15,8 / −11,9 | 26-09..25-10 | 26-10 03:40 |
| PV-bias per bewolking (30 d) | ≤ 50 % −13,1 % (n=9) · 50-90 % −13,8 (n=8) · > 90 % −7,1 (n=13) | 26-09..25-10 | 26-10 03:40 |
| Nabeschouwing: accu leverde / had kunnen (realisatie) | € 5,87 / € 6,64 (88 %) 7 d; avondpiek −1,42, ochtendpiek +2,94, nacht −1,73 | 19..25-10 | 26-10 03:40 |
| Planvolging "volgens plan" | 59,9 % (7 d, 52,7-68,8); "sturing" 0-9 per dag (25-10: 7, waarvan 6 in het blok) | 19..25-10 | 26-10 03:40 |
| PV-voorspelling MAE (dag, day-ahead tracker) | 12,5 % (30 d) · 16,8 % (14 d) · 13,8 % (7 d); bias −10,8 / −15,1 / −10,3; L-EMS-025 gecorrigeerd 10,8 tegen ruw 10,2 (5 d) | 27-09..26-10 | 27-10 03:40 |
| Nabeschouwing realisatie (meetlat zonder netladen / met netladen benaderd) | 116,6 % / 73,2 % (7 d) | 20..26-10 | 27-10 03:40 |
| Planvolging volgens plan | 58,6 % (7 d, 43,6-68,8) | 20..26-10 | 27-10 03:40 |
| MC 22:00 Brier (tot blok) | 0,600 (n=5; 1 nacht zonder stand: blok liep al) | 20..25-10 | 27-10 03:40 |
| Digital twin accu-inhoud 6 u vooruit, MAE | 1,83 kWh (n=60) | 26..27-10 | 27-10 03:40 |
