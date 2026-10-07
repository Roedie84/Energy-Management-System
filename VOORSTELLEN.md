# Voorstellen Energy Management System

Status: open / akkoord / afgewezen / gebouwd vX / geverifieerd / teruggedraaid. Ruud keurt goed via de chat ("akkoord L-EMS-00x").

## L-EMS-001 · nachtlek naar het net meetellen in de nachtbehoefte (of het P1-doel 's nachts op 0)
- Status: **afgewezen (vervallen 07-10 23:45)** — premisse onjuist: de verschuiving zit sinds v5.20 in de reserve (`regelverschuiving_w`) en is een bewuste instelling; tekorttelling telt hem niet als verkoop (v5.42). Getoetst: planning-tekortnachten kwamen van de piekregel (hersteld v5.28.4).
- (oorspronkelijk: open, raakt reserve/sturing)
- Onderbouwing: 28-09..07-10, n=50 nachturen met accu-ontlading: mediaan 60 Wh/u teruglevering (P1 ≈ −50 W in smart-modus). Het geleerde nachtverbruik meet huisverbruik (p1+accu+pv) en mist deze ~50 W. Over een ontlaadvenster van 10-16 u is dat 0,5-0,8 kWh/nacht; tekortnachten waren 0,68-1,88 kWh.
- Voorstel (één van twee): (a) gemeten nachtlek (W, mediaan 7 nachten) optellen bij de nachtbehoefte in reserve/Monte Carlo; of (b) in nachtkwartieren zonder verkoopbesluit het terugleverdoel van zendure-ha op 0 W (raakt externe configuratie).
- Verwacht effect: minder planning-tekortnachten; ~0,4-0,8 kWh/nacht niet meer goedkoop weg en duur terug.
- Meten na bouw: nacht-export 00-07 (KPI ems_nacht_export_00_07_kwh) en tekort-kWh per nacht, 7 nachten voor/na.
- Zelf te bouwen (meetbaarheid) vervalt: `regelverschuiving_w` meet dit al.

## L-EMS-002 · MC-tekortkans van 22:00 bewaren in het dagrecord
- Status: **gepland (zelf bouwen: meetbaarheid, raakt geen sturing)** — bij een dagafsluiting
- Onderbouwing: de MC-sensor heeft geen state_class; kalibratie (Brier 0,038, n=8, 30-09..07-10) kan nu alleen uit ~10 dagen recorder. Na 10 dagen is de voorspelling per nacht weg.
- Bouw: in `reserve_daily_records` per nacht `mc_tekortkans_22u` (en deterministisch tekort) vastleggen; test.
- Meten na bouw: veld aanwezig in het dagrecord en gelijk aan de sensorwaarde om 22:00 (±0,1).
