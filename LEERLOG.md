# Leerlog Energy Management System

Doorlopende leerronde (elke 4 uur). Alleen gemeten getallen; KPI's in KPI.csv, referenties in BASELINE.md, voorstellen in VOORSTELLEN.md.

## 07-10 23:15 · tussenronde (eerste ronde, baseline uit ~10 dagen historie)
- Gemeten: PV, net, accu per dag 28-09..06-10 (statistics); PV-voorspelling 31 dagen (pv_forecast_accuracy); tekortnachten 7 n; uurlijkse teruglevering 's nachts.
- PV-voorspelling: MAE 10,5% (30 d) → 5,2% (7 d); bias −4,4% / −1,7% (voorspelling iets te hoog). Geen duidelijk verschil bewolkt >70% vs ≤70% (bias −6,8 vs −4,6, n=16/13).
- Tekortnachten 4 van 7 (5,68 kWh): 2 economisch, 2 planning, 0 capaciteit. Reserve te hoog: 0 van 7.
- Opvallend: als de accu 's nachts levert, gaat er constant ~60 Wh/u naar het net (mediaan 60, n=50 uren, 00-07 u gem. 0,35 kWh/nacht). Oorzaak: smart-modus van zendure-ha volgt een P1-doel van ~−50 W (CHANGELOG v0.63.19). Steekproef 07-10 02:00: accu 290 W, P1 −50 W.
- Gevolg: het geleerde nachtverbruik (`p1 + accu + pv`) is huisverbruik zonder dit lek; de accu levert ~50 W meer dan de reserve verwacht → ~0,5-0,8 kWh/nacht over het hele ontlaadvenster. Dit is energie die verkocht wordt terwijl de reserve nodig is (HARDE REGEL "huis gaat voor") → gemeld, voorstel L-EMS-001.
- Hypothese H-EMS-1: het nachtlek verklaart een deel van de tekort-kWh in planning-nachten. Toets volgende ronden: lek-kWh per nacht naast tekort-kWh.
- Hypothese H-EMS-2: PV-bias is nu klein (−2%) en daalt; geen correctie nodig. Volgen tot 14 dagen.
- Niet gemeten (meetbaarheid): uurlijkse PV-voorspelling per uur (geen historie van uurvoorspelling in attributen gevonden; volgt), kwartierbeslissingen tegen achteraf-optimum (nog geen replay gebouwd), SoC-voorspelling tegen werkelijk.
- Geen release (tussenronde; 10 releases vandaag door andere sessies, v5.44 geïnstalleerd).

laatste ronde: 07-10 23:15, gemeten t/m 07-10 23:00

## 07-10 23:40 · tussenronde (handmatig gestart)
- Correctie: de vorige ronde was om 23:15, niet 23:30 (tijdstempels aangepast).
- Sinds 23:15 geen nieuwe gebeurtenis om te meten; geen release.

laatste ronde: 07-10 23:40, gemeten t/m 07-10 23:40

## 07-10 23:45 · tussenronde
- **Correctie 23:15:** de −50 W op de P1 ("nachtlek") is een bewuste instelling (Zendure regelt op P1+50) en zit sinds v5.20 in de reserve (`regelverschuiving_w` = 50, live gecontroleerd in gacs_zelfbeoordeling); de tekorttelling telt hem niet als verkoop (v5.42). Geen schending HARDE REGEL. L-EMS-001 vervallen.
- H-EMS-1 getoetst met uurdata 29-09..07-10 (9 nachten): beide planning-tekortnachten volgden op avondverkoop via `expensive_quarter_peak` onder de reserve (03-10: 1,37 kWh → 0,68 kWh tekort; 04-10: 5,14 kWh, vanaf 19:55 beschikbaar < reserve → 1,68 kWh tekort). Al gevonden en hersteld in v5.28.4 (04-10 10:32). H-EMS-1 verworpen; oorzaak = piekregel.
- Effect v5.28.4 gemeten: sinds 04-10 10:32 0× `expensive_quarter_peak`; 4 nachten (05-10..07-10 + 04→05) zonder tekort; avondverkoop 04-10 alleen boven de reserve (`expensive_quarter`).
- MC-kalibratie (nieuw): tekortkans om 22:00 vs uitkomst, 8 nachten 30-09..07-10: tekortnachten 98/100/45/97%, overige 0/0/0/0% → Brier 0,038 (n=8). Goed onderscheid, n klein → H-EMS-3.
- PV per uur (meetbaar via attribuut `profile` van pv_hourly_forecast_bias): werkelijk/Solcast mediaan 0,90-0,98 rond de middag, 0,52-0,69 om 06-07 en 15-17 UTC. De integratie leert en gebruikt dit profiel al zelf. Tweede voorspelling 13 d: Solcast 6,1% mediaanfout, tweede bron 31,6%.
- Lopend vannacht (→08-10): beschikbaar 4,23 kWh, nodig 4,54 kWh tot blok 12:15 → verwacht tekort 0,31 kWh; MC 41,7%. Toetsen in de dagafsluiting van 09-10.
- Meetbaarheid: MC-tekortkans heeft geen state_class → geen lange statistiek, alleen ~10 d historie. Kandidaat (zelf te bouwen, dagafsluiting): MC-waarde om 22:00 in het dagrecord bewaren.
- Geen release (tussenronde, geen acute bug).

laatste ronde: 07-10 23:45, gemeten t/m 07-10 23:44

## 08-10 03:40 · dagafsluiting 07-10
- Dag 07-10: PV 11,87 kWh (voorspeld 12,83, −7,5% bij 100% bewolking), import 0,72, export 2,23, accu 6,61 in / 5,67 uit, huis 9,41 kWh. Nacht 06→07 zonder tekort (SoC 30% om 09:00). 0× verkoop onder de reserve (harde regel gehaald). 15 herstarts.
- PV 30 d MAE 10,8% (bias −4,5), 7 d 5,9% (−2,4) → H-EMS-2 blijft: klein en stabiel. Bewolkt >70% bias −7,2 vs −4,6 (n=15/13), MAE gelijk 9,5% → geen bewolkingseffect op de fout.
- Verbruik (nieuw gemeten): uurprofiel MAE 0,13 kWh/u; nacht 22-09 bias −0,08 kWh (−3%) → reserve-invoer klopt. Dagtotaal −0,49 kWh/dag (mediaan per uur mist witgoed; reserve telt gepland witgoed apart).
- H-EMS-4 (nieuw): achteraf-optimum per uur over 4 dagen (29-09, 30-09, 01-10, 07-10; salderen = symmetrische prijs, slijtage 4,22 ct): werkelijk 1,16 € duurder dan zonder accu, optimum 2,20 € goedkoper. Bij 0 ct slijtage werkelijk ≈ zonder accu (+0,09/dag). Gat: zon opslaan bij ~30 ct levert onder salderen weinig; optimum laadt in de goedkoopste uren en levert in de piek. n=4, aannames (uur, perfecte kennis) → eerst 14 dagen meten, geen voorstel.
- Meetfout gevonden: `sensor.solaredge_production_energy` (cloud-dagteller) staat 00:04-07:07 op unknown → schaduw-dagrapport slaat nachtkwartieren stil over (dekking 80,6%, `kwartieren_gemeten` 76 is misleidend). Zichtbaar gemaakt in v5.45; instelling → L-EMS-003.
- Gebouwd **v5.45** (L-EMS-002): MC-kans 22:00 per avond bewaard + `mc_22u` in dagrecord + `kalibratie_22u` (Brier); dagrapport `kwartieren_bruikbaar/ongebruikt`. 4815 tests groen, workflow groen, HACS ververst.
- Lopend: nacht →08-10 om 04:00 verwacht tekort 0 (MC 2,4%; om 23:45 nog 0,31 kWh/41,7%) → toetsen na 09:00. 09-10 Solcast 1,8 kWh (somber): laadbesluit en reserve volgen.
- Cockpit LET OP 's nachts door tweede PV-voorspelling (forecast.solar) die elk ander uur `unavailable` is (01:04, 03:04) — externe bron, geen EMS-fout.

laatste ronde: 08-10 04:40, gemeten t/m 08-10 04:10

## 08-10 07:40 · tussenronde
- Geïnstalleerd: v5.45 (~06:23) en v5.46 (07:03). L-EMS-003 ingesteld om 07:04 (`pv_energy_sensor_entity` = Modbus-teller): kwartier 07:15 pv al `measured` (cloudteller was tot 07:07 unknown), dagopwek 0,0 → geen sprong. Dekking volgt in de dagafsluiting.
- L-EMS-004: sluipverbruik direct na update `normaal`, `methode_versie` 2, reeks en accumulator leeg → eerste meetpunt gehaald; referentie > 0 W pas na dagen.
- Nacht 07→08 (t/m 07:40): import 22-07 u 0,12 kWh, accu niet leeg (SoC 34% om 07:01) → geen tekort, zoals om 04:00 verwacht. Nacht-export 00-07 0,43 kWh (regelverschuiving −50 W nog actief; L-EMS-005 is een instelling bij Ruud).
- Verbruik tegen wandeling: beschikbaar 5,01 → 1,90 kWh (3,11 gebruikt) terwijl de korte-horizonbehoefte 2,82 daalde → 0,29 kWh (+10%) meer dan voorspeld.
- **H-EMS-5 (nieuw):** MC-tekortkans steeg 3% (04:00) → 96% (07:40) en het verhaal meldt "verwacht tekort tot het goedkope blok 0,61 kWh", maar dat getal is volledig de lange horizon (na 12:15): marge tot het blok zonder lange horizon +1,79 (22:00) → +1,50 kWh (07:42); `lange_horizon_extra` 1,85 → 2,11. MC rekent de lange horizon bewust mee (v5.40), maar `kalibratie_22u` (v5.45) toetst hem tegen de nacht 22-09 → appels/peren. Ook: de Brier 0,038 (n=8) is grotendeels van vóór v5.40; 07-10 22:00 (14,6%) is de eerste avond mét lange horizon.
- Kandidaat (zelf bouwen, rapportage/meetbaarheid, dagafsluiting): tekort en kans apart tot het blok en na het blok tonen + kalibratie op beide → L-EMS-006.
- Geen release (tussenronde, niets acuut).

laatste ronde: 08-10 07:40, gemeten t/m 08-10 07:42

## 08-10 ~10:30 · gebouwd door chatsessie (geen leerronde)
- **v5.47** uitgebracht (workflow groen, release v5.47, HACS ververst): L-EMS-006 (tekort/tekortkans tot het blok vs. na het blok, kalibratie 22:00 alleen tot het blok, nachtmelding tot het blok) en L-EMS-007 (water: m³/gal → liter, debiet → L/min, nieuwe dag alleen bij nieuwe `last_reset`/datum). Sturing, reserve, drempels en marges ongewijzigd. 24 nieuwe tests, 4855 groen.
- Live vóór bouw 10:08: MC 100%, verwacht tekort 1,0 kWh terwijl `nodig_kwh` 2,47 volledig lange horizon (2,468) was; `vandaag_liter` 0,06 (sensor 0,060 m³), trend −100%.
- Leerronde 11:40: L-EMS-006/007 niet opnieuw bouwen; na installatie meten zoals in VOORSTELLEN.md.


## 08-10 11:45 · tussenronde
- Geïnstalleerd: v5.47 (herstart 10:55). Herstarts sinds 07:40: 3 (08:55, 09:01, 10:55).
- **L-EMS-006 eerste meetpunt gehaald:** 11:41 `verwacht_tekort_tot_blok_kwh` 0, MC-stand 0% (vóór bouw 10:08: 100% / 1,0 kWh); `nodig_na_blok_kwh` 2,44 = `lange_horizon_extra` 2,441; beschikbaar 2,94 kWh. Kalibratie (Brier tot blok) pas na 7 avonden vanaf 08-10 22:00.
- **L-EMS-007 eerste meetpunt gehaald:** na herstart 10:55 (utility_meter kort 0,060 m³) `vandaag_liter` 60 = meter 60 L; laatste waarde in `geschiedenis_liter_per_dag` 357 = werkelijke 07-10 (357 L om 23:15). Groei per dagwissel toetsen na 00:00.
- Opgevallen (rapportage): `trend_procent` −84,5 vergelijkt het dagdeel (60 L om 11:40) met de mediaan van hele dagen (386,8, attribuut heet "gemiddeld") → overdag altijd sterk negatief. Kandidaat L-EMS-008 (zelf bouwen, dagafsluiting).
- **L-EMS-003:** meetlog "dekking 100%"; laatste kwartier 11:15 alle tellers `measured`. Dagdekking 08-10 in de dagafsluiting.
- Nacht 07→08 afgerond: geen tekort (dagrecord 07-10 `shortfall` false, 0 kWh). Tekortnachten laatste 7: 3 (4,24 kWh), ongewijzigd.
- PV t/m 11:41: 2,33 kWh tegen Solcast-actueel 2,75 (−15%); uurratio 09:00 0,67, 10:00 0,70 (geleerd profiel 07/08 UTC 0,68/0,90). EMS-dagvoorspelling 10,21, Solcast nu 11,49.
- Beslissingen sinds 07:40 alleen `default_smart` → 0× verkoop onder de reserve (harde regel gehaald).
- Lopend: laadblok 12:15; 09-10 zon 2,61 tegen verbruik 8,31 kWh (meetlog) → laadhoeveelheid en nacht 08→09 volgen.
- Geen release (tussenronde, niets acuut; v5.47 net geïnstalleerd).

laatste ronde: 08-10 11:45, gemeten t/m 08-10 11:42
