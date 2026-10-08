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
- Status: **gebouwd v5.45** (08-10 04:33) — verifiëren na installatie
- (eerder: gepland, zelf bouwen: meetbaarheid)
- Onderbouwing: de MC-sensor heeft geen state_class; kalibratie (Brier 0,038, n=8, 30-09..07-10) kan nu alleen uit ~10 dagen recorder. Na 10 dagen is de voorspelling per nacht weg.
- Bouw: in `reserve_daily_records` per nacht `mc_tekortkans_22u` (en deterministisch tekort) vastleggen; test.
- Meten na bouw: veld aanwezig in het dagrecord en gelijk aan de sensorwaarde om 22:00 (±0,1); `kalibratie_22u.nachten` loopt op.
- Gebouwd: `mc_22u_per_avond` (14 avonden, bewaard), `mc_22u` in dagrecord van de nacht erna, attribuut `kalibratie_22u` met Brier. 11 tests.

## L-EMS-003 · PV-energieteller van de cloud-dagteller naar de Modbus-teller
- Status: **akkoord 08-10** → **gebouwd v5.46 (code)**; instelling nog NIET omgezet — pas na installatie van v5.46
- Bij de controle vooraf (08-10): eenheid Wh/kWh wordt overal goed omgerekend, maar de premisse "raakt alleen de meetlaag" klopte niet: de dagopwek (`pv_production_today_kwh`) rekent vanaf een bewaard dagbegin van de OUDE meter. Cloud = dagteller (11,868 kWh), Modbus = levensteller (23.426 kWh) → dagopwek ~23.414 kWh. v5.46 onthoudt welke meter bij het dagbegin hoort en ijkt opnieuw bij een andere meter.
- Na installatie v5.46: `ha_set_integration(entry_id=01KYVA81YPQF0PXKHSWFFQS1E5, config={"pv_energy_sensor_entity": "sensor.solaredge_i1_ac_energy"})`, options-dict voor/na vergelijken, logs controleren, dagopwek dezelfde dag controleren (geen sprong).
- Onderbouwing: 07-10/08-10: `pv_energy_sensor_entity` = `sensor.solaredge_production_energy` (SolarEdge-cloud, Wh, dagteller) staat elke nacht 00:04-07:07 op unknown en meldt overdag elke 15 min op :02/:17. De kwartierenergie markeert pv dan `invalid`; het schaduw-dagrapport slaat die ~28 nachtkwartieren over (dekking 80,6% op 07-10). `sensor.solaredge_i1_ac_energy` (Modbus, kWh, levenslang) heeft altijd een stand.
- Voorstel: in de EMS-instellingen de PV-energieteller op `sensor.solaredge_i1_ac_energy` zetten. Raakt alleen de meetlaag (schaduw), niet de sturing.
- Verwacht effect: `kwartieren_ongebruikt.pv_onbekend` van ~28 naar ~0 per dag; dagrapport rekent ook de nacht.
- Meten na wijziging: `kwartieren_bruikbaar` ≥ 90 per dag (v5.45-attribuut in de meetlog).

## L-EMS-004 · sluipverbruik: robuust vloerverbruik in plaats van het dagminimum van losse monsters
- Status: **akkoord 08-10** → **gebouwd v5.46** (08-10) — verifiëren na installatie
- Onderbouwing: uuranalyse 08-10: referentie vloerverbruik −225 W, 21 van 30 dagminima negatief, alarm "gedetecteerd" (accumulator 0,37 kW, drempel 0,15). Het dagminimum neemt de wisselpieken van de accu mee: P1 −2,1..−2,2 kW gedurende ~10 s elke ~25 min terwijl het accuvermogen nog niet bijgewerkt is (recorder 08-10 02:03). Bij 1 monster/min is dat één monster per kwartier; een gemiddelde per 5 min blijft dan ~−220 W, de mediaan per kwartier niet.
- Bouw: vloer = laagste kwartier, kwartier = mediaan van ≥ 5 monsters, begrensd ≥ 0 W. Oude reeks + accumulator + alarm eenmalig gewist (`sluipverbruik_methode_versie` = 2), ook uit de na-de-sensoren-opslag; sensorherstel alleen bij gelijk versienummer. 16 tests (incl. L-EMS-003).
- Meten na bouw: sensor sluipverbruik-detectie direct na update "normaal", `methode_versie` 2; `baseline_load_history` alleen waarden ≥ 0 en in de orde 0,1-0,3 kW; na 10 dagen referentie > 0 W en geen vals alarm.

## L-EMS-005 · smart-stand: nachtelijke teruglevering van −50 W naar −20 W
- Status: **akkoord 08-10** → **niet in EMS; instelling bij Ruud** (gedocumenteerd in v5.46)
- Onderbouwing: elk nachtuur gemiddeld −47..−53 W, ≈ 0,5 kWh accu-energie per nacht het net op (~27 ct).
- Waar het zit: niet in EMS-code/-optie en niet in zendure_ha of de firmware. zendure_ha regelt op p1meter `sensor.hw_p1_vermogen_100w` ("HW P1 Vermogen -50W", platform `rest`, unique_id `HW_P1_Vermogen_Min100`), een eigen REST-sensor in de HA-YAML die de HomeWizard-P1 + 50 W meldt (live 08-10: P1 −54 W, regelsensor −4 W). De Zendure houdt die op 0 → echte P1 −50 W.
- Aanpassen: in de YAML van die REST-sensor de +50 in de value_template vervangen door +20 (naam evt. mee), daarna Ontwikkelhulpmiddelen → YAML → REST-entiteiten herladen (geen herstart nodig). EMS meet de verschuiving live (`regelverschuiving_kw`, v5.20) en rekent vanzelf met 20 W. NB: `TEKORT_IMPORT_MIN_W` = 50 W blijft de vloer in de tekorttelling (export ≤ 50 W telt niet als verkoop) — onschadelijk.
- Afweging: minder accu-energie het net op, iets vaker kort netimport bij snel stijgend huisverbruik.
- Meten na wijziging: nachtuur-gemiddelde P1 −15..−25 W; nacht-export 00-07 (KPI ems_nacht_export_00_07_kwh) ~0,2 kWh i.p.v. ~0,5; netimport-kwartieren 's nachts niet merkbaar hoger.
