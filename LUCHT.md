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

laatste ronde: 11-10 16:25, gemeten t/m 16:20
