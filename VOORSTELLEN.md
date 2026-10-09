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
- Status: **gebouwd v5.45** (08-10 04:33), geïnstalleerd ~06:23 — eerste avond 08-10 22:00 (07-10 22:00 draaide v5.45 nog niet: `kalibratie_22u.nachten` 0)
- (eerder: gepland, zelf bouwen: meetbaarheid)
- Onderbouwing: de MC-sensor heeft geen state_class; kalibratie (Brier 0,038, n=8, 30-09..07-10) kan nu alleen uit ~10 dagen recorder. Na 10 dagen is de voorspelling per nacht weg.
- Bouw: in `reserve_daily_records` per nacht `mc_tekortkans_22u` (en deterministisch tekort) vastleggen; test.
- Meten na bouw: veld aanwezig in het dagrecord en gelijk aan de sensorwaarde om 22:00 (±0,1); `kalibratie_22u.nachten` loopt op.
- 09-10 11:40: dagrecord ontstaat om 00:00 (datum D = nacht tot D 09:00, stand van D−1 22:00) → eerste paar op 10-10 00:00 (avond 08-10 0 %, nacht zonder tekort). Toets in de dagafsluiting van 10-10.
- Gebouwd: `mc_22u_per_avond` (14 avonden, bewaard), `mc_22u` in dagrecord van de nacht erna, attribuut `kalibratie_22u` met Brier. 11 tests.

## L-EMS-003 · PV-energieteller van de cloud-dagteller naar de Modbus-teller
- Status: **akkoord 08-10** → **gebouwd v5.46**, geïnstalleerd 07:03, instelling omgezet 07:04 — eerste meting: kwartier 07:15 pv `measured`, dagopwek 0,0 (geen sprong). Dekking (`kwartieren_bruikbaar` ≥ 90) toetsen in de dagafsluiting van 08-10.
- 09-10 03:40: dagrapport 08-10 bruikbaar 47/74 met 27× `pv_onbekend` (00-07, vóór de omzetting) → verwacht; 09-10 03:15 pv `measured` 's nachts. Toets: dagrapport 09-10 `pv_onbekend` ≈ 0. NB `kwartieren_gemeten` 74/96 komt van herstarts → L-EMS-009.
- Bij de controle vooraf (08-10): eenheid Wh/kWh wordt overal goed omgerekend, maar de premisse "raakt alleen de meetlaag" klopte niet: de dagopwek (`pv_production_today_kwh`) rekent vanaf een bewaard dagbegin van de OUDE meter. Cloud = dagteller (11,868 kWh), Modbus = levensteller (23.426 kWh) → dagopwek ~23.414 kWh. v5.46 onthoudt welke meter bij het dagbegin hoort en ijkt opnieuw bij een andere meter.
- Na installatie v5.46: `ha_set_integration(entry_id=01KYVA81YPQF0PXKHSWFFQS1E5, config={"pv_energy_sensor_entity": "sensor.solaredge_i1_ac_energy"})`, options-dict voor/na vergelijken, logs controleren, dagopwek dezelfde dag controleren (geen sprong).
- Onderbouwing: 07-10/08-10: `pv_energy_sensor_entity` = `sensor.solaredge_production_energy` (SolarEdge-cloud, Wh, dagteller) staat elke nacht 00:04-07:07 op unknown en meldt overdag elke 15 min op :02/:17. De kwartierenergie markeert pv dan `invalid`; het schaduw-dagrapport slaat die ~28 nachtkwartieren over (dekking 80,6% op 07-10). `sensor.solaredge_i1_ac_energy` (Modbus, kWh, levenslang) heeft altijd een stand.
- Voorstel: in de EMS-instellingen de PV-energieteller op `sensor.solaredge_i1_ac_energy` zetten. Raakt alleen de meetlaag (schaduw), niet de sturing.
- Verwacht effect: `kwartieren_ongebruikt.pv_onbekend` van ~28 naar ~0 per dag; dagrapport rekent ook de nacht.
- Meten na wijziging: `kwartieren_bruikbaar` ≥ 90 per dag (v5.45-attribuut in de meetlog).

## L-EMS-004 · sluipverbruik: robuust vloerverbruik in plaats van het dagminimum van losse monsters
- Status: **akkoord 08-10** → **gebouwd v5.46** (08-10), geïnstalleerd 07:03 — eerste meetpunt gehaald (normaal, `methode_versie` 2, reeks leeg); rest na ≥ 10 dagen
- Onderbouwing: uuranalyse 08-10: referentie vloerverbruik −225 W, 21 van 30 dagminima negatief, alarm "gedetecteerd" (accumulator 0,37 kW, drempel 0,15). Het dagminimum neemt de wisselpieken van de accu mee: P1 −2,1..−2,2 kW gedurende ~10 s elke ~25 min terwijl het accuvermogen nog niet bijgewerkt is (recorder 08-10 02:03). Bij 1 monster/min is dat één monster per kwartier; een gemiddelde per 5 min blijft dan ~−220 W, de mediaan per kwartier niet.
- Bouw: vloer = laagste kwartier, kwartier = mediaan van ≥ 5 monsters, begrensd ≥ 0 W. Oude reeks + accumulator + alarm eenmalig gewist (`sluipverbruik_methode_versie` = 2), ook uit de na-de-sensoren-opslag; sensorherstel alleen bij gelijk versienummer. 16 tests (incl. L-EMS-003).
- Meten na bouw: sensor sluipverbruik-detectie direct na update "normaal", `methode_versie` 2; `baseline_load_history` alleen waarden ≥ 0 en in de orde 0,1-0,3 kW; na 10 dagen referentie > 0 W en geen vals alarm.

## L-EMS-005 · smart-stand: nachtelijke teruglevering van −50 W naar −20 W
- Status: **geverifieerd 09-10 07:40** — nacht 08→09 export 00-07 0,163 kWh (basis 0,433, −62%), nachtimport buiten arbitrage 10-17 Wh/u (Quooker-niveau, niet hoger). Eerder: **akkoord 08-10** → **ingesteld door Ruud (08-10, vóór 11:10)**: regelsensor −1003 W bij P1 −1023 W (+20 W, was +50). Effect meten: nacht 08→09 export 00-07 (basis 0,43-0,45 kWh)
- 09-10 03:40: nacht 08→09 00-03 u 27/22/22 Wh/u (basis 08-10 59-65 Wh/u, 00-07 0,433 kWh) → −60%; volledige nacht in de volgende ronde.
- Onderbouwing: elk nachtuur gemiddeld −47..−53 W, ≈ 0,5 kWh accu-energie per nacht het net op (~27 ct).
- Waar het zit: niet in EMS-code/-optie en niet in zendure_ha of de firmware. zendure_ha regelt op p1meter `sensor.hw_p1_vermogen_100w` ("HW P1 Vermogen -50W", platform `rest`, unique_id `HW_P1_Vermogen_Min100`), een eigen REST-sensor in de HA-YAML die de HomeWizard-P1 + 50 W meldt (live 08-10: P1 −54 W, regelsensor −4 W). De Zendure houdt die op 0 → echte P1 −50 W.
- Aanpassen: in de YAML van die REST-sensor de +50 in de value_template vervangen door +20 (naam evt. mee), daarna Ontwikkelhulpmiddelen → YAML → REST-entiteiten herladen (geen herstart nodig). EMS meet de verschuiving live (`regelverschuiving_kw`, v5.20) en rekent vanzelf met 20 W. NB: `TEKORT_IMPORT_MIN_W` = 50 W blijft de vloer in de tekorttelling (export ≤ 50 W telt niet als verkoop) — onschadelijk.
- 08-10 23:40 eerste effect (avond): export tijdens ontlading 20-23 u 23-27 Wh/u (was ~60). Nacht 00-07 in de dagafsluiting.
- Afweging: minder accu-energie het net op, iets vaker kort netimport bij snel stijgend huisverbruik.
- Meten na wijziging: nachtuur-gemiddelde P1 −15..−25 W; nacht-export 00-07 (KPI ems_nacht_export_00_07_kwh) ~0,2 kWh i.p.v. ~0,5; netimport-kwartieren 's nachts niet merkbaar hoger.

## L-EMS-006 · verwacht tekort en tekortkans splitsen: tot het blok / na het blok (lange horizon)
- Status: **gebouwd v5.47**, geïnstalleerd 10:55 — eerste meetpunt gehaald 11:41 (tot blok 0 kWh / 0%, na blok 2,44 apart); Brier-vergelijking na 7 avonden (vanaf 08-10 22:00)
- 09-10 03:40: nacht 08→09 om 03:41 MC tot blok 0% (marge +0,78 kWh), incl. lange horizon 100% (na-blok 4,45 kWh) — splitsing doet wat hij moet. `kalibratie_22u` nog 0 nachten (dagrecord 09-10 om 09:00); v5.57 toont `laatste_avond` al dezelfde avond.
- 08-10 23:40: eerste `mc_22u`-avond: MC 21:12-22:10 doorlopend 0,0% → niet vervuild; dagrecord 09-10 moet `mc_22u.kans_pct` 0 met `basis: tot_blok` dragen.
- 08-10 19:40: overdag MC tot blok 0-1%, behalve 3 korte sprongen (21-92%, samen 20 min) direct na huishoudpieken door de livecorrectie → H-EMS-6; let bij de Brier op vervuilde 22:00-standen.
- (eerder: gepland, zelf bouwen: rapportage en meetbaarheid; raakt de sturing niet)
- Onderbouwing: 08-10 07:42: verhaal "verwacht tekort tot het goedkope blok 0,61 kWh, economisch", MC 96%. Maar `nodig_kwh` 2,51 bevat `lange_horizon_extra` 2,11 (na 12:15); tot het blok is 0,40 nodig tegen 1,90 beschikbaar (marge +1,50). MC steeg 3% → 96% tussen 04:00 en 07:40 terwijl de marge tot het blok slechts van +1,79 naar +1,50 ging. `kalibratie_22u` vergelijkt deze kans (incl. lange horizon) met de tekortnacht 22-09.
- Bouw: in `verwacht_tekort` en het MC-attribuut `tekort_tot_blok_kwh` / `tekort_na_blok_kwh` en `tekortkans_tot_blok_pct` (zelfde trajecten zonder lange extra); verhaaltekst noemt het juiste deel; `kalibratie_22u` per nacht beide kansen + Brier van beide. Tests. De reserve en de sturing blijven ongewijzigd.
- Verwacht effect: eerlijke uitleg ('s ochtends geen vals "tekort tot het blok"); kalibratie tegen de nacht op de juiste kans.
- Meten na bouw: na 7 avonden Brier `tot blok` tegen `met lange horizon` naast elkaar; ochtenden waar de tekst tekort meldt en de import vóór het blok < 0,1 kWh blijft → 0.
- Gebouwd (v5.47): `verwacht_tekort.tekort_kwh` = tot het blok, plus `verwacht_tekort_tot_blok_kwh` / `verwacht_tekort_na_blok_kwh` / `nodig_tot_blok_kwh` / `nodig_na_blok_kwh`. MC-stand = `tekortkans_tot_blok_pct`; apart `tekortkans_incl_lange_horizon_pct`, `mediaan_/p90_/deterministisch_diepste_tekort_tot_blok_kwh` (de bestaande mediaan/p90/deterministisch blijven incl. lange horizon). `mc_22u` krijgt `basis: tot_blok` + `kans_incl_lange_horizon_pct` + `lange_horizon_extra_kwh`; `kalibratie_22u` Brier alleen over `tot_blok`-standen, oude standen geteld in `nachten_oude_basis_uitgesloten`. Brier incl. lange horizon is geen attribuut: na te rekenen uit `mc_22u.kans_incl_lange_horizon_pct` in de dagrecords. Nachtmelding "haalt de nacht niet" vergelijkt nu ook tot het blok (cockpit-LET OP hing er niet van af). 11 tests; 4855 groen.
- Live vóór bouw (08-10 10:08): MC 100%, `nodig_kwh` 2,47 waarvan `lange_horizon_extra` 2,468, verwacht tekort 1,0 kWh → na installatie moet hier `verwacht_tekort_tot_blok_kwh` 0 en de MC-stand ~0% staan.

## L-EMS-007 · watersensoren: eenheid m³ → liter, geen nepdag bij eenheidswissel
- Status: **gebouwd v5.47**, geïnstalleerd 10:55 — meetpunten 11:41 en 15:40 (na herstart 0,105 m³ → 105 L) gehaald (`vandaag_liter` 60 = meter 60 L na herstart met m³-tussenstand; laatste dagwaarde 357 = werkelijk 07-10); dagwissel en 7 dagen nog toetsen
- 09-10 03:40: dagwissel 08→09 goed (+1 waarde: 215 L = utility_meter `last_period` 0,215 m³). Nog 6 dagwissels.
- Onderbouwing: `sensor.water_verbruik_vandaag` (utility_meter, optie `water_daily_total_sensor_entity`) meldt na elke herstart eerst m³ en direct daarna L (recorder 08-10 07:03, 08:54, 09:01: 0,026/0,052/0,060 m³ tussen L-standen; live 10:08 `0.060 m³`). EMS rekende alleen Wh/MWh om → `vandaag_liter` 0,06, `trend_procent` −100, verhaal "0 L". Een sprong L→m³ is een daling en werd als nieuwe dag gearchiveerd (mogelijk de 109,77 in `geschiedenis_liter_per_dag`; niet zeker, niet gewist). `water_total_usage` (m³) en `water_active_usage` (L/min) melden nu de verwachte eenheid, maar werden ook niet omgerekend.
- Bouw: `_read_water_volume_l` (L, mL, m³, gal, ft³, CCF; zonder eenheid: dagtotaal L, meterstand m³) en `_read_water_flow_l_per_min` (L/min, L/h, m³/h, gal/min, …) voor dagtotaal, meterstand, debiet, live listener en aanwezigheid. Daling archiveert alleen bij nieuwe `last_reset` (of zonder `last_reset`: andere lokale datum). 13 tests. Stuurt niets.
- Meten na installatie: na elke herstart `vandaag_liter` ≥ de L-stand van de utility_meter (nooit < 1 bij een stand > 1 L) en `trend_procent` ≠ −100 overdag; `geschiedenis_liter_per_dag` groeit met precies 1 waarde per dag (lengte +1 per dagwissel, geen waarden < 20 L tenzij echt); 7 dagen.


## L-EMS-008 · watertrend: dagdeel tegen hetzelfde dagdeel, niet tegen hele dagen
- Status: **gebouwd v5.49** (chatsessie 08-10 13:31), geïnstalleerd — eerste meetpunt 15:40: overdag `trend_procent` null met toelichting (nog geen 3 dagen profiel); methode 'zelfde_tijdstip' vanaf ~11-10 toetsen
- (eerder: kandidaat, zelf bouwen: rapportage)
- Onderbouwing: 08-10 11:40: `trend_procent` −84,5 = (60 − 386,8)/386,8; 60 L is het verbruik tot 11:40, 386,8 de mediaan van hele dagen (attribuut heet `gemiddeld_liter_per_dag`, is een mediaan). Overdag is de trend dus altijd sterk negatief en zegt niets.
- Bouw (voorstel): trend tegen de verwachte stand op dit tijdstip (mediaan van eerdere dagen tot hetzelfde uur, uit `water_session_history` of een uurprofiel), of pas na 23:00 tonen; attribuut `mediaan_liter_per_dag` naast het oude. Test.
- Meten na bouw: overdag `trend_procent` binnen ±50% op gewone dagen; om 23:59 gelijk aan de oude berekening.

## L-EMS-009 · meetlaag: het kwartier van een herstart meten
- Status: **gebouwd v5.57** (09-10 03:56, zelf gebouwd: meetfout; stuurt niets), geïnstalleerd 06:02 — toets: dagrapport 09-10 (4 herstarts t/m 07:42) in de dagafsluiting van 10-10
- Onderbouwing: dagrapport 08-10 `kwartieren_gemeten` 74 van 96 bij 20 herstarts (18 kwartieren met een herstart); 07-10 76 bij 15. Code: `_kwartiergrens` slaat het eerste kwartier na de start over (`_vorige_standen` None). De tellers (P1, omvormer) lopen in het apparaat door; de accutellers van zendure_ha zijn in HA opgeteld vermogen.
- Bouw: tellerstanden per grens in de bewaarde toestand (`meetlaag_kwartierstanden`); eerste grens na de start gebruikt ze alleen als ze precies 15 min ouder zijn én van dezelfde tellers (anders ongemeten zoals voorheen). Record `over_herstart`, accutellers `partially_estimated`. Dagrapport `kwartieren_niet_gemeten`, `kwartieren_over_herstart`. Ook `kalibratie_22u.laatste_avond` en `avonden_bewaard`. 8 tests (`test_v557_leerronde.py`), suite 4997 groen.
- Meten na installatie: dagrapport `kwartieren_niet_gemeten` ≈ 0 op een dag met herstarts < 15 min, `kwartieren_over_herstart` ≈ aantal herstarts; geen kwartier met `house_kwh` < 0 of > 3 kWh rond een herstart.

## L-EMS-010 · "verkocht met winst" alleen als de verkoop boven de reserve lag
- Status: **open** (rapportage/classificatie, maar raakt een bewuste keuze van v5.55 → Ruud beslist)
- Onderbouwing: sinds v5.55 heten de nachten →03-10 (1,9 kWh verkocht, 0,68 tekort) en →04-10 (4,6 kWh, 1,68 tekort) `verkocht_met_winst`: "bewust, geen stuurfout". De leerronde van 07-10 23:45 toonde dat die verkoop via `expensive_quarter_peak` ONDER de reserve ging (04-10 vanaf 19:55 beschikbaar < reserve) — een fout die v5.28.4 herstelde. Verkoop onder de reserve is een schending van de harde regel "huis gaat voor", ook als de prijs achteraf gunstig uitviel.
- Voorstel: in de tekortsoort eerst toetsen of er die avond verkocht werd terwijl beschikbaar < reserve; zo ja: soort `verkocht_onder_reserve` (LET OP, nooit "bewust"), ongeacht de prijs. Alleen verkoop boven de reserve kan `verkocht_met_winst` zijn. Test met de reeks van 04-10.
- Verwacht effect: een herhaling van de piekregel-bug wordt niet meer weggeschreven als "bewust". Sturing ongewijzigd.
- Meten na bouw: per tekortnacht de soort naast "verkocht onder reserve ja/nee" uit de recorder; 0 nachten `verkocht_met_winst` met verkoop onder de reserve.

## L-EMS-011 · waterontharder: regel krijgt ook bron "waterontharder"
- Status: **gepland (zelf bouwen: rapportage/classificatie; stuurt niets)** — bouwen in de dagafsluiting
- Onderbouwing: 09-10 03:07 sessie 154 L / 38 min: `waarschijnlijk_waterontharder` true en `waterontharder_laatste_regeneratie` gezet, maar in dezelfde regel `bron` null, `zekerheid` "onbekend", `reden` "Geen apparaat actief en geen herkenbaar patroon." Oorzaak: `classify_water_session(liters, duur)` kent de ontharder-vlag niet (coordinator.py, sessie-afsluiting).
- Bouw: bij `is_waterontharder` bron "waterontharder", zekerheid "waarschijnlijk", reden met tijdvenster/volume/duur; anders ongewijzigd. Test met de sessie van 09-10.
- Meten na bouw: volgende regeneratie (~10 dagen) toont bron "waterontharder"; overige sessies ongewijzigd.
