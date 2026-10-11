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

laatste ronde: 11-10 12:23, gemeten t/m 12:15
